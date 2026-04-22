"""Representation Agent — pick claims and back them with registered charts.

Audit 1.4 + 1.7: the verdict surface emits charts independently of the
claims the verdict is making. This agent closes the loop by extracting the
claims implicit in a `UnifiedIntelligenceOutput`, citing the supporting
evidence from module views, and selecting a registered chart to represent
each claim. It does **not** render charts (the wiring layer does) and does
**not** invent evidence — claims without backing evidence are flagged.

Structured-output pattern follows `briarwood/agent/router.py`:

- A Pydantic schema (`RepresentationPlan`) describes the full response.
- The LLM is called through `LLMClient.complete_structured`, which enforces
  strict JSON via the provider's schema mode.
- Default model is a cheap structured tier (`gpt-4o-mini`) rather than
  `gpt-5` (AUDIT F12: down-tier the default structured model).
- Deterministic fallback runs when no client is configured, transport
  fails, or the LLM returns an empty plan.
"""

from __future__ import annotations

import json
import logging
import os
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from briarwood.agent.llm import LLMClient
from briarwood.representation.charts import (
    ChartSpec,
    all_specs,
    get_spec,
    render as render_chart,
)
from briarwood.routing_schema import UnifiedIntelligenceOutput

_logger = logging.getLogger(__name__)


class ClaimType(str, Enum):
    """Vocabulary of claims the verdict can make.

    Kept narrow on purpose — every entry must map to at least one chart in
    the registry. Adding a claim type without a chart should be a build
    error, not a runtime surprise.
    """

    PRICE_POSITION = "price_position"
    VALUE_DRIVERS = "value_drivers"
    COMP_EVIDENCE = "comp_evidence"
    SCENARIO_RANGE = "scenario_range"
    DOWNSIDE_RISK = "downside_risk"
    RISK_COMPOSITION = "risk_composition"
    RENT_COVERAGE = "rent_coverage"
    RENT_RAMP = "rent_ramp"
    # F5: hidden upside levers that don't show up in the ask-vs-fair-value
    # frame — renovation spread, accessory-unit income, repositioning, etc.
    # Sourced from ``UnifiedIntelligenceOutput.optionality_signal``. No
    # registered chart yet; surfaced as a claim-only selection so the UI
    # can render it in the value_thesis SSE card.
    HIDDEN_UPSIDE = "hidden_upside"


# Known module-view keys the agent can cite as a chart's source.
# Matches the `Session.last_*` slots populated by `handle_decision`.
KNOWN_SOURCE_VIEWS = (
    "last_decision_view",
    "last_value_thesis_view",
    "last_market_support_view",
    "last_risk_view",
    "last_strategy_view",
    "last_rent_outlook_view",
    "last_projection_view",
)


class RepresentationSelection(BaseModel):
    """One (claim, evidence, chart) triple.

    `chart_id` may be `None` when a claim is worth surfacing in prose but
    no registered chart fits (e.g. trust-gate narration). `flagged=True`
    means the agent could not find supporting evidence in module views —
    the SSE layer can drop the selection or surface it as a caveat.
    """

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    claim_type: ClaimType
    supporting_evidence: list[str] = Field(default_factory=list)
    chart_id: str | None = None
    source_view: str | None = None
    flagged: bool = False
    flag_reason: str | None = None


class RepresentationPlan(BaseModel):
    """Ordered list of claim-backed chart selections."""

    model_config = ConfigDict(extra="forbid")

    selections: list[RepresentationSelection] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You are Briarwood's Representation Agent. Your job is to decide which "
    "claims the verdict is making and which registered chart best represents "
    "each claim using the module evidence provided.\n\n"
    "Hard rules:\n"
    "1. Only claim something the module evidence actually supports. If a "
    "claim lacks evidence, still return it but set flagged=true with a "
    "short flag_reason.\n"
    "2. Pick chart_id ONLY from the registry provided below. If no chart "
    "fits, leave chart_id null (do not invent one).\n"
    "3. supporting_evidence entries must cite real field names from the "
    "module views provided (e.g. `last_projection_view.bull_case_value`). "
    "Do not fabricate field names.\n"
    "4. source_view must be one of the keys in module_views (e.g. "
    "`last_projection_view`) or null.\n"
    "5. Prefer 3-5 selections. One chart per claim_type at most.\n"
    "6. Do not restate the same claim with different wording."
)


class RepresentationAgent:
    """Structured-output agent that plans how to represent a verdict.

    Construct with an `LLMClient` to use the LLM path; pass `None` to
    force the deterministic heuristic. The agent post-validates whatever
    the LLM returns (chart_id must be registered, source_view must be a
    known key, supporting_evidence must reference a field present in
    that view) and falls back to deterministic selection when the LLM
    path yields nothing usable.
    """

    name = "representation_agent"

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        model: str | None = None,
        max_selections: int = 6,
    ) -> None:
        self._llm = llm_client
        self._model = model or os.environ.get(
            "BRIARWOOD_REPRESENTATION_MODEL", "gpt-4o-mini"
        )
        self._max_selections = max_selections

    # ------------------------------------------------------------------
    # Public API

    def plan(
        self,
        unified: UnifiedIntelligenceOutput,
        *,
        user_question: str,
        module_views: Mapping[str, Mapping[str, Any] | None],
    ) -> RepresentationPlan:
        """Produce a RepresentationPlan for this verdict.

        `module_views` maps session-view keys (`last_projection_view`,
        `last_risk_view`, ...) to the underlying dicts. None / missing
        views are tolerated — the agent will simply not pick charts that
        depend on them.
        """
        clean_views: dict[str, dict[str, Any]] = {
            key: dict(view)
            for key, view in module_views.items()
            if isinstance(view, Mapping)
        }

        plan = self._plan_via_llm(unified, user_question, clean_views)
        if plan is None or not plan.selections:
            plan = self._deterministic_plan(unified, clean_views)

        return self._postprocess(plan, clean_views)

    def render_events(
        self,
        plan: RepresentationPlan,
        module_views: Mapping[str, Mapping[str, Any] | None],
        *,
        market_view: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Render each selection's chart to an SSE event payload.

        Selections without a chart_id, or whose renderer returns `None`
        (inputs insufficient), are skipped silently. `market_view` is an
        optional override injected into `cma_positioning` so the renderer
        can prefer live-market comps over valuation comps.
        """
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for selection in plan.selections:
            if selection.chart_id is None or selection.flagged:
                continue
            if selection.chart_id in seen:
                continue
            source = selection.source_view
            view = module_views.get(source) if source else None
            inputs: dict[str, Any] = dict(view) if isinstance(view, Mapping) else {}
            if selection.chart_id == "cma_positioning" and isinstance(
                market_view, Mapping
            ):
                inputs["_market_view"] = dict(market_view)
            event = render_chart(selection.chart_id, inputs)
            if event is None:
                continue
            out.append(event)
            seen.add(selection.chart_id)
        return out

    # ------------------------------------------------------------------
    # LLM path

    def _plan_via_llm(
        self,
        unified: UnifiedIntelligenceOutput,
        user_question: str,
        module_views: dict[str, dict[str, Any]],
    ) -> RepresentationPlan | None:
        if self._llm is None:
            return None

        try:
            payload = {
                "user_question": user_question,
                "verdict": _verdict_digest(unified),
                "module_views": _views_digest(module_views),
                "registered_charts": [spec.model_dump() for spec in all_specs()],
                "known_source_views": list(KNOWN_SOURCE_VIEWS),
                "claim_types": [c.value for c in ClaimType],
            }
            response = self._llm.complete_structured(
                system=_SYSTEM_PROMPT,
                user=json.dumps(payload, default=str),
                schema=RepresentationPlan,
                model=self._model,
                max_tokens=1200,
            )
        except Exception as exc:
            _logger.warning("representation LLM call failed: %s", exc)
            return None

        return response

    # ------------------------------------------------------------------
    # Deterministic fallback

    def _deterministic_plan(
        self,
        unified: UnifiedIntelligenceOutput,
        module_views: dict[str, dict[str, Any]],
    ) -> RepresentationPlan:
        """Heuristic plan: inspect the verdict + views and pick charts for
        each claim that has evidence. Used when the LLM path is disabled
        or returns nothing usable. Produces the same shape as the LLM
        path so callers do not branch."""
        selections: list[RepresentationSelection] = []

        value_view = module_views.get("last_value_thesis_view") or {}
        decision_view = module_views.get("last_decision_view") or {}
        projection_view = module_views.get("last_projection_view") or {}
        risk_view = module_views.get("last_risk_view") or {}
        rent_view = module_views.get("last_rent_outlook_view") or {}
        market_view = module_views.get("last_market_support_view") or {}

        ask = _first_num(decision_view.get("ask_price"), value_view.get("ask_price"))
        fair = _first_num(
            decision_view.get("fair_value_base"), value_view.get("fair_value_base")
        )
        premium = _first_num(
            value_view.get("premium_discount_pct"),
            decision_view.get("ask_premium_pct"),
        )
        if ask is not None and fair is not None:
            evidence = [
                f"last_decision_view.fair_value_base={fair}",
                f"last_decision_view.ask_price={ask}",
            ]
            if premium is not None:
                evidence.append(f"last_value_thesis_view.premium_discount_pct={premium}")
            drivers = list(
                value_view.get("key_value_drivers")
                or value_view.get("value_drivers")
                or unified.key_value_drivers
                or []
            )
            if drivers:
                evidence.append(
                    "last_value_thesis_view.key_value_drivers=" + ", ".join(drivers[:3])
                )
            selections.append(
                RepresentationSelection(
                    claim=_price_position_claim(ask, fair, premium),
                    claim_type=ClaimType.PRICE_POSITION,
                    supporting_evidence=evidence,
                    chart_id="value_opportunity",
                    source_view="last_value_thesis_view"
                    if value_view
                    else "last_decision_view",
                )
            )

        comps_source = market_view if market_view.get("comps") else value_view
        comps = [c for c in (comps_source.get("comps") or []) if isinstance(c, dict)]
        priced = [c for c in comps if isinstance(c.get("ask_price"), (int, float))]
        if priced:
            source_key = (
                "last_market_support_view"
                if comps_source is market_view
                else "last_value_thesis_view"
            )
            selections.append(
                RepresentationSelection(
                    claim=(
                        f"Fair value is anchored on {len(priced)} comps "
                        "positioned around the subject."
                    ),
                    claim_type=ClaimType.COMP_EVIDENCE,
                    supporting_evidence=[f"{source_key}.comps[{len(priced)}]"],
                    chart_id="cma_positioning",
                    source_view=source_key,
                )
            )

        scenario_values = [
            ("bull_case_value", projection_view.get("bull_case_value")),
            ("base_case_value", projection_view.get("base_case_value")),
            ("bear_case_value", projection_view.get("bear_case_value")),
        ]
        populated_scenarios = [
            (name, val)
            for name, val in scenario_values
            if isinstance(val, (int, float)) and val
        ]
        if len(populated_scenarios) >= 2:
            selections.append(
                RepresentationSelection(
                    claim=(
                        "5-year outcomes span from bear to bull across the "
                        "scenario set."
                    ),
                    claim_type=ClaimType.SCENARIO_RANGE,
                    supporting_evidence=[
                        f"last_projection_view.{name}={val}"
                        for name, val in populated_scenarios
                    ],
                    chart_id="scenario_fan",
                    source_view="last_projection_view",
                )
            )

        # Only claim the risk-composition chart if the risk module actually
        # ran. Falling back to `decision_view.trust_flags` would attribute
        # evidence to a view we would then cite as the source, even though
        # that view may not be in module_views — the post-processor flags
        # such selections and we would lose the chart anyway. Better to
        # skip the claim entirely when the backing view is absent.
        if "last_risk_view" in module_views and risk_view:
            risk_flags = list(risk_view.get("risk_flags") or [])
            trust_flags = list(risk_view.get("trust_flags") or [])
            if risk_flags or trust_flags:
                evidence: list[str] = []
                if risk_flags:
                    evidence.append(
                        "last_risk_view.risk_flags=" + ", ".join(risk_flags[:4])
                    )
                if trust_flags:
                    evidence.append(
                        "last_risk_view.trust_flags=" + ", ".join(trust_flags[:4])
                    )
                selections.append(
                    RepresentationSelection(
                        claim=(
                            f"Risk profile carries {len(risk_flags)} risk flags"
                            + (
                                f" and {len(trust_flags)} trust flags."
                                if trust_flags
                                else "."
                            )
                        ),
                        claim_type=ClaimType.RISK_COMPOSITION,
                        supporting_evidence=evidence,
                        chart_id="risk_bar",
                        source_view="last_risk_view",
                    )
                )

        if rent_view.get("burn_chart_payload"):
            selections.append(
                RepresentationSelection(
                    claim=(
                        "Rent coverage against the monthly carry is "
                        "available over the hold horizon."
                    ),
                    claim_type=ClaimType.RENT_COVERAGE,
                    supporting_evidence=["last_rent_outlook_view.burn_chart_payload"],
                    chart_id="rent_burn",
                    source_view="last_rent_outlook_view",
                )
            )
        if rent_view.get("ramp_chart_payload"):
            selections.append(
                RepresentationSelection(
                    claim=(
                        "Net cash flow has a break-even path under base/bull/bear "
                        "rent ramps."
                    ),
                    claim_type=ClaimType.RENT_RAMP,
                    supporting_evidence=["last_rent_outlook_view.ramp_chart_payload"],
                    chart_id="rent_ramp",
                    source_view="last_rent_outlook_view",
                )
            )

        # F5: surface hidden-upside levers as a claim-only selection when the
        # optionality_signal on the unified output carries items. No chart is
        # registered for it yet — the value_thesis SSE event is the surface —
        # so we emit a chart-less selection with the lever magnitudes in
        # supporting_evidence. The signal may be empty when the run didn't
        # exercise HIDDEN_UPSIDE or the modules didn't populate magnitudes.
        optionality = unified.optionality_signal
        upside_items = list(optionality.hidden_upside_items)
        if upside_items:
            evidence: list[str] = []
            for item in upside_items[:3]:
                mag_bits: list[str] = []
                if item.magnitude_usd is not None:
                    mag_bits.append(f"${item.magnitude_usd:,.0f}")
                if item.magnitude_pct is not None:
                    mag_bits.append(f"{item.magnitude_pct*100:.1f}%")
                mag = (" @ " + "/".join(mag_bits)) if mag_bits else ""
                evidence.append(f"{item.source_module}.{item.kind}{mag}")
            labels = ", ".join(item.label for item in upside_items[:3])
            selections.append(
                RepresentationSelection(
                    claim=f"Hidden upside levers: {labels}.",
                    claim_type=ClaimType.HIDDEN_UPSIDE,
                    supporting_evidence=evidence,
                    chart_id=None,
                    source_view=None,
                )
            )

        # Surface the stance-level "what_changes_my_view" as a flagged,
        # chart-less claim when we have nothing else to hang it on. Lets
        # callers see the reasoning without forcing a chart.
        if not selections and unified.what_changes_my_view:
            selections.append(
                RepresentationSelection(
                    claim=unified.what_changes_my_view[0],
                    claim_type=ClaimType.DOWNSIDE_RISK,
                    supporting_evidence=[],
                    chart_id=None,
                    flagged=True,
                    flag_reason="no module view available to chart this claim",
                )
            )

        return RepresentationPlan(selections=selections)

    # ------------------------------------------------------------------
    # Validation / normalization

    def _postprocess(
        self,
        plan: RepresentationPlan,
        module_views: dict[str, dict[str, Any]],
    ) -> RepresentationPlan:
        """Validate every selection. Policies:

        - Unknown chart_id → clear chart_id, flag the selection.
        - source_view not in module_views → clear source_view, flag.
        - chart_id present but its required_inputs aren't satisfied by the
          named source view → clear chart_id, flag.
        - No supporting_evidence at all → flag (no fabrication).
        - Claim type does not match the chart's registered claim_types →
          clear chart_id, flag.

        Truncate to `max_selections` and dedupe by (claim_type, chart_id).
        """
        cleaned: list[RepresentationSelection] = []
        seen: set[tuple[str, str | None]] = set()
        for selection in plan.selections:
            s = selection.model_copy(deep=True)
            spec = get_spec(s.chart_id) if s.chart_id else None

            if s.chart_id and spec is None:
                s.flagged = True
                s.flag_reason = _merge_reason(
                    s.flag_reason, f"chart_id '{s.chart_id}' not registered"
                )
                s.chart_id = None

            if s.source_view and s.source_view not in module_views:
                s.flagged = True
                s.flag_reason = _merge_reason(
                    s.flag_reason,
                    f"source_view '{s.source_view}' not present in module_views",
                )
                s.source_view = None

            if spec is not None and s.claim_type.value not in spec.claim_types:
                s.flagged = True
                s.flag_reason = _merge_reason(
                    s.flag_reason,
                    f"chart '{spec.id}' does not support claim_type "
                    f"'{s.claim_type.value}'",
                )
                s.chart_id = None

            if spec is not None and s.source_view and s.chart_id:
                view = module_views.get(s.source_view) or {}
                missing = [f for f in spec.required_inputs if not _has_input(view, f)]
                if missing:
                    s.flagged = True
                    s.flag_reason = _merge_reason(
                        s.flag_reason,
                        f"source_view missing required inputs: {', '.join(missing)}",
                    )
                    s.chart_id = None

            if not s.supporting_evidence:
                s.flagged = True
                s.flag_reason = _merge_reason(
                    s.flag_reason, "no supporting evidence cited"
                )

            key = (s.claim_type.value, s.chart_id)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(s)
            if len(cleaned) >= self._max_selections:
                break
        return RepresentationPlan(selections=cleaned)


# ---- Helpers ---------------------------------------------------------


def _verdict_digest(unified: UnifiedIntelligenceOutput) -> dict[str, Any]:
    return {
        "decision_stance": unified.decision_stance.value,
        "recommendation": unified.recommendation,
        "primary_value_source": unified.primary_value_source,
        "confidence": unified.confidence,
        "value_position": unified.value_position,
        "key_value_drivers": list(unified.key_value_drivers),
        "key_risks": list(unified.key_risks),
        "what_must_be_true": list(unified.what_must_be_true),
        "why_this_stance": list(unified.why_this_stance),
        "what_changes_my_view": list(unified.what_changes_my_view),
        "trust_flags": list(unified.trust_flags),
        "blocked_thesis_warnings": list(unified.blocked_thesis_warnings),
        "contradiction_count": unified.contradiction_count,
    }


def _views_digest(module_views: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return a compact digest of each view — field keys + scalar values.

    Large payloads (comps arrays, chart payloads) are summarized to length
    or key lists so the prompt stays small without losing the signals the
    agent needs to pick a chart.
    """
    digest: dict[str, Any] = {}
    for key, view in module_views.items():
        summary: dict[str, Any] = {}
        for field, val in view.items():
            if isinstance(val, (int, float, str, bool)) or val is None:
                summary[field] = val
            elif isinstance(val, list):
                summary[field] = f"<list len={len(val)}>"
            elif isinstance(val, dict):
                summary[field] = f"<dict keys={sorted(val.keys())[:8]}>"
            else:
                summary[field] = f"<{type(val).__name__}>"
        digest[key] = summary
    return digest


def _first_num(*vals: Any) -> float | None:
    for v in vals:
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _price_position_claim(
    ask: float, fair: float, premium: float | None
) -> str:
    if premium is None:
        return f"Subject is asking ${ask:,.0f} vs fair value ${fair:,.0f}."
    direction = "premium" if premium > 0 else "discount"
    return (
        f"Subject is asking ${ask:,.0f} — a {abs(premium) * 100:.1f}% {direction} "
        f"to fair value ${fair:,.0f}."
    )


def _merge_reason(existing: str | None, incoming: str) -> str:
    if not existing:
        return incoming
    return f"{existing}; {incoming}"


def _has_input(view: Mapping[str, Any], field: str) -> bool:
    """Check if a required_input field is meaningfully populated.

    Lists / dicts pass if non-empty; scalars pass if not None; `comps` and
    `*_payload` are treated as lists/dicts respectively even when nested.
    """
    if field not in view:
        return False
    val = view[field]
    if val is None:
        return False
    if isinstance(val, (list, dict, tuple, set)):
        return bool(val)
    return True


__all__ = [
    "ClaimType",
    "KNOWN_SOURCE_VIEWS",
    "RepresentationAgent",
    "RepresentationPlan",
    "RepresentationSelection",
]

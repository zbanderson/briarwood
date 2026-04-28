"""LLM-driven Value Scout: surface non-obvious angles in a UnifiedIntelligenceOutput.

Phase 4b Cycle 1 of SCOUT_HANDOFF_PLAN.md. The deterministic scout at
``briarwood.value_scout.scout.scout_claim`` runs pure-function patterns
over a built ``VerdictWithComparisonClaim`` inside the claims wedge.
This module is its LLM-driven sibling for the chat tier: it reads a
full ``UnifiedIntelligenceOutput`` plus the user's ``IntentContract``
and returns the 1-2 most non-obvious angles a serious buyer or
investor would care about even though they did not explicitly ask.

Design notes (Cycle 1, per SCOUT_HANDOFF_PLAN.md):

- **One LLM call** wrapped in
  ``briarwood.agent.llm_observability.complete_structured_observed`` at
  surface ``value_scout.scan``. The structured output is a list of
  insights with ``headline / reason / supporting_fields / category /
  confidence``.
- **Numeric grounding** via ``api.guardrails.verify_response`` over the
  joined ``headline + reason`` prose, with the unified output as
  structured inputs. Threshold-level violations trigger a single regen
  attempt at surface ``value_scout.scan.regen``. The regen replaces
  the draft only when it strictly reduces violations.
- **Empty contract on failure to ground.** Unlike the synthesizer
  (which surfaces prose with violations recorded so callers can
  decide), scout returns an empty contract when grounding cannot be
  satisfied after the regen pass. An ungrounded "what's interesting"
  beat is worse than no beat — there is no caller fallback for a
  scout angle, so the safer posture is to drop the surface entirely.
- **Empty contract** ``([], {empty: True, reason: ...})`` for missing
  inputs, blank LLM response, transient exception (after retries),
  budget cap, and ungrounded-after-regen.
- **Cap and ranking.** Returned insights are sorted by LLM-emitted
  confidence descending and capped at ``max_insights`` (default 2 per
  Open Design Decision #2). Confidence is numeric ``[0, 1]`` per Open
  Design Decision #1.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from briarwood.agent.composer import STRICT_REGEN_THRESHOLD
from briarwood.agent.llm import LLMClient
from briarwood.agent.llm_observability import complete_structured_observed
from briarwood.claims.base import SurfacedInsight
from briarwood.cost_guard import BudgetExceeded
from briarwood.intent_contract import IntentContract

from api.guardrails import verify_response

# The verifier kinds that count toward the regen threshold. Mirrors the
# synthesizer's private list — intentionally duplicated so this module
# does not depend on a private symbol elsewhere.
_STRICT_KINDS: tuple[str, ...] = ("ungrounded_number", "ungrounded_entity")

_logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are Briarwood's Value Scout.

Briarwood's deterministic models have already produced a structured
`unified` output for one property. The synthesizer will write the
front-page response using its `## Why` beat to cover the obvious read.
Your job is different.

You read the full `unified` output and the user's `intent` contract,
and you identify the 1-2 most non-obvious angles a serious buyer or
investor would care about EVEN THOUGH they did not explicitly ask.
Examples (illustrative, not exhaustive):

- Rent angle on a value question — strong rent profile or comp-anchored
  yield not foregrounded by the synthesizer's "Why" beat.
- ADU / accessory-unit signal on a flip question — `legal_confidence`
  or `unit_income_offset` evidence the user did not bring up.
- Town-trend tailwind on a comp question — multi-year price trajectory
  the user would not have known to ask about.
- Carry / yield mismatch — operating math that contradicts the headline
  read.
- Optionality — repositioning, multi-unit conversion, scenario dominance.

Return AT MOST 2 insights, ranked by your own confidence. Do NOT pad.
If nothing non-obvious is in the unified output, return zero insights.

For each insight produce:

- `headline` — one short sentence naming the angle. Concrete, not
  generic. ("Belmar shows roughly a 12% three-year price uplift" beats
  "interesting town trend".)
- `reason` — one or two sentences explaining the angle, citing specific
  evidence from the unified output. Numbers must round to values
  present in `unified`.
- `supporting_fields` — list of dotted-path field references into
  `unified` that the insight rests on (e.g.
  `market_value_history.three_year_change_pct`,
  `rental_option.rent_support_score`). Minimum 1, target 2-4.
- `category` — short snake_case label (e.g. `rent_angle`, `adu_signal`,
  `town_trend`, `comp_anomaly`, `carry_yield_mismatch`,
  `optionality`). Invent a new label when none of these fit.
- `confidence` — your self-rated confidence in [0, 1] that this
  insight is both true and non-obvious. Anchors: 1.0 = canonical
  evidence with no ambiguity, 0.7 = solid signal worth surfacing,
  0.5 = borderline, < 0.4 = better not to surface.

Avoid restating what the synthesizer's `## Why` beat will already
cover — the headline verdict, the ask vs fair, the obvious comp
anchor. Surface the angles a smart underwriter would notice on a
second read.

VOICE — match the user's `intent.answer_type`:

- `browse` → first-impression surfacer. The user just clicked the
  listing. Pick the angle that would shift their first read most:
  optionality, hidden upside, an underweighted driver they would not
  have searched for.
- `decision` → decision-pivot surfacer. The user is asking should-I-
  buy. Pick the angle that could move the decision: a carry / yield
  mismatch, a rent reality the verdict didn't pivot on, a comp-set
  anomaly that loosens or tightens the buy case.
- `edge` → skeptical surfacer. The user is testing the value claim.
  Pick the angle that complicates the headline read: a trust gap the
  verdict glosses, a sensitivity that flips the sign, an assumption
  that is doing more load-bearing work than it looks like.

In all tiers: still 1-2 insights, still ranked by your confidence,
still grounded in `supporting_fields`.

NUMERIC GROUNDING (the only hard rule): every dollar amount,
percentage, multiplier, year, or count you cite in `headline` or
`reason` must round to a value present in the `unified` JSON. Rounded
forms like '$820k' or 'roughly 12%' are fine when they round to an
actual value. Do not invent numbers, comp counts, or rates. If you do
not have a number to support a claim, omit the number rather than
estimate.
"""


class _ScoutInsightOut(BaseModel):
    """Per-insight payload from the LLM. Internal — converts to SurfacedInsight."""

    model_config = ConfigDict(extra="forbid")

    headline: str
    reason: str
    supporting_fields: list[str]
    category: str
    confidence: float = Field(ge=0.0, le=1.0)


class _ScoutScanResult(BaseModel):
    """Structured-output schema for the value_scout.scan surface."""

    model_config = ConfigDict(extra="forbid")

    insights: list[_ScoutInsightOut] = Field(default_factory=list)


def _user_prompt(unified: dict[str, Any], intent: IntentContract) -> str:
    payload: dict[str, Any] = {
        "intent": intent.model_dump(mode="json"),
        "unified": unified,
    }
    return json.dumps(payload, default=str, sort_keys=True)


def _joined_prose(insights: list[_ScoutInsightOut]) -> str:
    """Join headline+reason from each insight for the verifier's input.

    The verifier scans free text against the unified output; concatenating
    all insights' prose lets one verifier call cover the whole batch.
    """

    return " ".join(
        f"{insight.headline} {insight.reason}".strip() for insight in insights
    )


def _regen_user_prompt(original_user: str, flagged_values: list[str]) -> str:
    bullet_lines = "\n".join(f'- "{v}"' for v in flagged_values[:6])
    return (
        "Your previous insights cited numbers not present in the `unified` "
        "JSON:\n"
        f"{bullet_lines}\n\n"
        "Rewrite the insights. Every number you cite must round to a value "
        "present in `unified`. If you do not have a number to support a "
        "claim, omit the number. You may return fewer insights or zero "
        "insights if grounding cannot be satisfied.\n\n"
        f"Original task:\n{original_user}"
    )


def _to_surfaced_insight(out: _ScoutInsightOut) -> SurfacedInsight:
    return SurfacedInsight(
        headline=out.headline,
        reason=out.reason,
        supporting_fields=list(out.supporting_fields),
        confidence=out.confidence,
        category=out.category,
    )


def scout_unified(
    *,
    unified: dict[str, Any],
    intent: IntentContract,
    llm: LLMClient | None,
    max_insights: int = 2,
) -> tuple[list[SurfacedInsight], dict[str, Any]]:
    """Scan a UnifiedIntelligenceOutput for non-obvious angles via an LLM.

    Returns ``(insights, report)``. ``insights`` is a list of
    :class:`SurfacedInsight`, sorted by confidence descending and capped
    at ``max_insights``. ``report`` carries the verifier outcome plus
    ``empty: bool`` — when ``empty`` is True, ``reason`` describes why
    no insights were produced. Callers treat ``([], {empty: True, ...})``
    as "no scout output for this turn."

    Numeric grounding mirrors the synthesizer's pattern but with a
    stricter terminal rule: a single regen attempt fires when
    ``STRICT_REGEN_THRESHOLD`` flagged sentences are present in the
    first draft, and the regen replaces the draft only when it strictly
    reduces violations. If grounding cannot be satisfied after that
    pass, the empty contract is returned rather than surfacing
    ungrounded insights.
    """

    if llm is None or not unified:
        return [], {"empty": True, "reason": "llm_or_unified_missing"}

    user_prompt = _user_prompt(unified, intent)
    surface = "value_scout.scan"

    try:
        result = complete_structured_observed(
            surface=surface,
            schema=_ScoutScanResult,
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            provider=llm.__class__.__name__,
            model=None,
            call=lambda: llm.complete_structured(
                system=_SYSTEM_PROMPT,
                user=user_prompt,
                schema=_ScoutScanResult,
            ),
        )
    except BudgetExceeded as exc:
        _logger.warning("value_scout.scan budget cap reached: %s", exc)
        return [], {"empty": True, "reason": "budget_exceeded"}
    except Exception as exc:  # noqa: BLE001 — caller proceeds without scout
        _logger.warning("value_scout.scan draft failed: %s", exc)
        return [], {"empty": True, "reason": f"exception:{type(exc).__name__}"}

    if result is None:
        return [], {"empty": True, "reason": "no_response"}
    if not result.insights:
        return [], {"empty": True, "reason": "no_insights"}

    raw_insights = list(result.insights)
    prose = _joined_prose(raw_insights)
    report = verify_response(prose, unified, tier="value_scout")
    flagged = [v for v in report.violations if v.kind in _STRICT_KINDS]

    if len(flagged) >= STRICT_REGEN_THRESHOLD:
        flagged_values = [v.value for v in flagged]
        regen_user = _regen_user_prompt(user_prompt, flagged_values)
        try:
            regen_result = complete_structured_observed(
                surface="value_scout.scan.regen",
                schema=_ScoutScanResult,
                system=_SYSTEM_PROMPT,
                user=regen_user,
                provider=llm.__class__.__name__,
                model=None,
                call=lambda: llm.complete_structured(
                    system=_SYSTEM_PROMPT,
                    user=regen_user,
                    schema=_ScoutScanResult,
                ),
            )
        except BudgetExceeded as exc:
            _logger.warning(
                "value_scout.scan regen budget cap — dropping draft: %s",
                exc,
            )
            regen_result = None
        except Exception as exc:  # noqa: BLE001 — drop the draft
            _logger.warning("value_scout.scan regen failed: %s", exc)
            regen_result = None

        kept_regen = False
        if regen_result is not None and regen_result.insights:
            regen_prose = _joined_prose(list(regen_result.insights))
            regen_report = verify_response(regen_prose, unified, tier="value_scout")
            if regen_report.sentences_with_violations < report.sentences_with_violations:
                raw_insights = list(regen_result.insights)
                report = regen_report
                kept_regen = True

        if not kept_regen:
            report_dict = report.to_dict()
            report_dict["empty"] = True
            report_dict["reason"] = "ungrounded_after_regen"
            report_dict["surface"] = surface
            return [], report_dict

    raw_insights.sort(key=lambda i: i.confidence, reverse=True)
    capped = raw_insights[:max_insights]

    if not capped:
        return [], {"empty": True, "reason": "all_insights_dropped"}

    insights = [_to_surfaced_insight(i) for i in capped]

    report_dict = report.to_dict()
    report_dict["empty"] = False
    report_dict["surface"] = surface
    report_dict["insights_generated"] = len(result.insights)
    report_dict["insights_surfaced"] = len(insights)
    report_dict["top_confidence"] = insights[0].confidence

    return insights, report_dict


__all__ = ["scout_unified"]

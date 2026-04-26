"""Representation for verdict_with_comparison claims (plan §7).

Translates a validated ``VerdictWithComparisonClaim`` into user-facing
prose plus the SSE events the UI renders (chart + suggestions). Inverts
the control flow of the legacy claim-evidence validation path (see
``briarwood/pipeline/representation.py::ClaimEvidenceValidator``, formerly
named ``RepresentationAgent``) — the claim dictates output shape, and the
LLM's job is strictly to write prose around fixed structure.

Three sub-steps run in order:

1. Deterministic: take ``verdict.headline`` and ``bridge_sentence``
   verbatim. Apply the confidence-to-assertion rubric to the headline.
2. LLM: one tight call that adds 2-4 sentences of supporting prose. If
   ``llm is None`` the step falls back to a deterministic stub so the
   wedge can still produce a response during degraded states.
3. Deterministic: emit a ``horizontal_bar_with_ranges`` chart event and a
   ``suggestions`` event for the claim's next_questions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api import events
from api.prompts import load_prompt
from briarwood.agent.composer import complete_and_verify
from briarwood.agent.llm import LLMClient
from briarwood.claims.representation.rubric import apply_rubric
from briarwood.claims.verdict_with_comparison import (
    ComparisonScenario,
    VerdictWithComparisonClaim,
)

PROMPT_TIER = "claim_verdict_with_comparison"
PROSE_MAX_TOKENS = 220


@dataclass(frozen=True)
class RenderedClaim:
    """Output of representation: prose for the text stream + the SSE
    events that accompany it.

    `events` is a concrete list of dict payloads (already shaped by
    ``api.events.*`` helpers), in emission order. Dispatch wiring in
    step 10 decides where in the stream they land.
    """

    prose: str
    events: list[dict[str, Any]]


def render_claim(
    claim: VerdictWithComparisonClaim,
    *,
    llm: LLMClient | None,
) -> RenderedClaim:
    """Render the full response for a verdict_with_comparison claim."""
    headline = apply_rubric(
        claim.verdict.headline,
        claim.verdict.confidence,
        comp_count=claim.verdict.comp_count,
    )
    bridge = claim.bridge_sentence

    if llm is None:
        llm_prose = _deterministic_prose_fallback(claim)
    else:
        llm_prose = _render_llm_prose(claim, llm=llm)

    prose = _compose_prose(headline=headline, bridge=bridge, body=llm_prose)
    event_list = [
        _build_chart_event(claim),
        _build_suggestions_event(claim),
    ]
    return RenderedClaim(prose=prose, events=event_list)


# ─── Prose assembly ────────────────────────────────────────────────────


def _compose_prose(*, headline: str, bridge: str, body: str) -> str:
    """Join the three prose parts with single spaces, trimming doubles."""
    parts = [p.strip() for p in (headline, bridge, body) if p and p.strip()]
    return " ".join(parts)


def _render_llm_prose(
    claim: VerdictWithComparisonClaim, *, llm: LLMClient
) -> str:
    system = load_prompt(PROMPT_TIER)
    structured_inputs = claim.model_dump(mode="json")
    user = (
        f"verdict_label: {claim.verdict.label}\n"
        f"confidence_band: {claim.verdict.confidence.band}\n"
        f"surfaced_insight: "
        f"{claim.surfaced_insight.headline if claim.surfaced_insight else 'none'}"
    )
    cleaned, _ = complete_and_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=structured_inputs,
        tier=PROMPT_TIER,
        max_tokens=PROSE_MAX_TOKENS,
    )
    return cleaned.strip()


def _deterministic_prose_fallback(claim: VerdictWithComparisonClaim) -> str:
    """One sentence built from the claim — used when llm is None.

    Mirrors the investor persona tone at a much lower resolution. The
    fallback is intentionally terse; the wedge wants any LLM outage to be
    obvious to the user rather than masked behind a convincing template.
    """
    subject = _find_subject(claim.comparison.scenarios)
    subject_val = f"${subject.metric_median:,.0f}/sqft" if subject else "the subject"
    if claim.surfaced_insight is not None:
        return (
            f"Briarwood's subject tier sits at {subject_val}. "
            f"{claim.surfaced_insight.reason}"
        )
    return f"Briarwood's subject tier sits at {subject_val}."


# ─── SSE events ────────────────────────────────────────────────────────


def _build_chart_event(claim: VerdictWithComparisonClaim) -> dict[str, Any]:
    """Emit the horizontal_bar_with_ranges chart spec.

    Subject flag is promoted to `"none"` in the spec (the chart already
    distinguishes subject via `is_subject`); a non-"none" flag value is
    reserved for scenarios Scout or synthesis want to visually accent.
    """
    scenarios_payload: list[dict[str, Any]] = []
    for scenario in claim.comparison.scenarios:
        low, high = scenario.metric_range
        scenarios_payload.append(
            {
                "id": scenario.id,
                "label": scenario.label,
                "low": float(low),
                "high": float(high),
                "median": float(scenario.metric_median),
                "is_subject": bool(scenario.is_subject),
                "flag": scenario.flag,
                "flag_reason": scenario.flag_reason,
                "sample_size": int(scenario.sample_size),
            }
        )
    spec: dict[str, Any] = {
        "kind": "horizontal_bar_with_ranges",
        "unit": claim.comparison.unit,
        "scenarios": scenarios_payload,
        "emphasis_scenario_id": claim.comparison.emphasis_scenario_id,
    }
    unit = claim.comparison.unit or ""
    has_emphasis = claim.comparison.emphasis_scenario_id is not None
    legend: list[dict[str, Any]] = [
        {"label": "Subject", "color": "var(--chart-bear)", "style": "solid"},
        {"label": "Comparison range", "color": "var(--chart-base)", "style": "solid"},
    ]
    if has_emphasis:
        legend.append({"label": "Emphasized scenario", "color": "var(--chart-stress)", "style": "solid"})
    value_format = "currency" if unit in {"", "usd", "$"} else "count"
    return events.chart(
        title="Scenario ranges",
        subtitle="Range and median for each comparison scenario",
        kind="horizontal_bar_with_ranges",
        spec=spec,
        supports_claim="verdict_with_comparison",
        x_axis_label=unit if unit else "Price",
        y_axis_label="Scenario",
        value_format=value_format,
        legend=legend,
    )


def _build_suggestions_event(claim: VerdictWithComparisonClaim) -> dict[str, Any]:
    """Map next_questions into a suggestions event."""
    items = [q.text for q in claim.next_questions if q.text]
    return events.suggestions(items)


# ─── Helpers ───────────────────────────────────────────────────────────


def _find_subject(scenarios: list[ComparisonScenario]) -> ComparisonScenario | None:
    for scenario in scenarios:
        if scenario.is_subject:
            return scenario
    return None

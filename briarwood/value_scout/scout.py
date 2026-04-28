"""Value Scout registry dispatcher.

Runs registered pure-function patterns for the input object's type and,
for chat-tier ``UnifiedIntelligenceOutput`` inputs, also runs the LLM
scout. Returned insights are ranked by ``SurfacedInsight.confidence``.
``scout_claim`` stays as the stable claim-wedge wrapper.
"""
from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from briarwood.agent.turn_manifest import record_note
from briarwood.claims.base import SurfacedInsight
from briarwood.claims.verdict_with_comparison import VerdictWithComparisonClaim
from briarwood.intent_contract import IntentContract, build_contract_from_answer_type
from briarwood.routing_schema import UnifiedIntelligenceOutput
from briarwood.value_scout.llm_scout import scout_unified
from briarwood.value_scout.patterns import (
    adu_signal,
    rent_angle,
    town_trend_tailwind,
    uplift_dominance,
)

Detector = Callable[[Any], SurfacedInsight | None]
InputType = type[VerdictWithComparisonClaim] | type[UnifiedIntelligenceOutput]

_PATTERNS: dict[InputType, tuple[Detector, ...]] = {
    VerdictWithComparisonClaim: (uplift_dominance.detect,),
    UnifiedIntelligenceOutput: (
        rent_angle.detect,
        adu_signal.detect,
        town_trend_tailwind.detect,
    ),
}


def _pattern_insights(input_obj: object, input_type: InputType) -> list[SurfacedInsight]:
    insights: list[SurfacedInsight] = []
    for detector in _PATTERNS.get(input_type, ()):
        result = detector(input_obj)
        if result is not None:
            insights.append(result)
    return insights


def _confidence_key(insight: SurfacedInsight) -> float:
    return float(insight.confidence or 0.0)


def _default_intent_for_unified(
    unified: UnifiedIntelligenceOutput,
) -> IntentContract:
    return build_contract_from_answer_type("browse", unified.confidence)


def _default_intent_for_unified_dict(unified: dict[str, Any]) -> IntentContract:
    confidence = unified.get("confidence", 0.5)
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        score = 0.5
    return build_contract_from_answer_type("browse", score)


def _record_scout_yield(insights_generated: int, surfaced: list[SurfacedInsight]) -> None:
    top_confidence = _confidence_key(surfaced[0]) if surfaced else 0.0
    record_note(
        "value_scout_yield "
        f"insights_generated={insights_generated} "
        f"insights_surfaced={len(surfaced)} "
        f"top_confidence={top_confidence:.3f}"
    )


def scout(
    input_obj: VerdictWithComparisonClaim | UnifiedIntelligenceOutput | dict[str, Any],
    *,
    llm: Any | None = None,
    intent: IntentContract | None = None,
    max_insights: int = 2,
) -> list[SurfacedInsight]:
    """Scan a claim or chat-tier unified output for non-obvious value.

    ``VerdictWithComparisonClaim`` inputs run registered deterministic
    claim patterns. ``UnifiedIntelligenceOutput`` inputs run registered
    deterministic chat-tier patterns plus the LLM scout when ``llm`` is
    provided. Results are sorted by confidence descending and capped to
    ``max_insights``.
    """

    if isinstance(input_obj, VerdictWithComparisonClaim):
        input_type: InputType = VerdictWithComparisonClaim
        insights = _pattern_insights(input_obj, input_type)
    else:
        input_type = UnifiedIntelligenceOutput
        insights_generated = 0
        if isinstance(input_obj, UnifiedIntelligenceOutput):
            unified_model: UnifiedIntelligenceOutput | None = input_obj
            unified_payload = unified_model.model_dump(mode="json")
        else:
            unified_payload = input_obj
            try:
                unified_model = UnifiedIntelligenceOutput.model_validate(input_obj)
            except ValidationError:
                unified_model = None

        insights = (
            _pattern_insights(unified_model, input_type)
            if unified_model is not None
            else []
        )
        insights_generated += len(insights)
        if llm is not None:
            llm_insights, report = scout_unified(
                unified=unified_payload,
                intent=(
                    intent
                    or (
                        _default_intent_for_unified(unified_model)
                        if unified_model is not None
                        else _default_intent_for_unified_dict(unified_payload)
                    )
                ),
                llm=llm,
                max_insights=max_insights,
            )
            insights_generated += int(report.get("insights_generated") or len(llm_insights))
            insights.extend(llm_insights)

    insights.sort(key=_confidence_key, reverse=True)
    surfaced = insights[:max_insights]
    if input_type is UnifiedIntelligenceOutput:
        _record_scout_yield(insights_generated, surfaced)
    return surfaced


def scout_claim(claim: VerdictWithComparisonClaim) -> SurfacedInsight | None:
    """Back-compat claim-wedge wrapper around :func:`scout`."""

    insights = scout(claim, max_insights=1)
    return insights[0] if insights else None

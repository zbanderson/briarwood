from __future__ import annotations

import math
from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.property_data_quality import PropertyDataQualityModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    confidence_band,
    module_payload_from_legacy_result,
)
from briarwood.pipeline.triage import load_model_weights


def run_confidence(context: ExecutionContext) -> dict[str, object]:
    """Confidence Engine v2.

    Trust now reflects property completeness, contradictions, comp quality,
    prior-model agreement, legal certainty, scenario fragility, and reliance
    on estimated/defaulted inputs.
    """

    property_input = build_property_input_from_context(context)
    dq_result = PropertyDataQualityModule().run(property_input)
    dq_confidence = float(dq_result.confidence) if dq_result.confidence is not None else None

    prior_confidences = _collect_prior_confidences(context.prior_outputs)
    weights = load_model_weights() if prior_confidences else {}
    aggregated = _weighted_mean(prior_confidences, weights) if prior_confidences else None
    completeness = _field_completeness(context)
    estimated_reliance = _estimated_reliance(context)
    contradiction_count = _contradiction_count(context)
    comp_quality = _comp_quality(context.prior_outputs)
    model_agreement = _model_agreement(prior_confidences)
    scenario_fragility = _scenario_fragility(context.prior_outputs)
    legal_certainty = _legal_certainty(context.prior_outputs)
    combined = _combine(
        aggregated=aggregated,
        anchor=dq_confidence,
        completeness=completeness,
        contradiction_count=contradiction_count,
        comp_quality=comp_quality,
        model_agreement=model_agreement,
        scenario_fragility=scenario_fragility,
        legal_certainty=legal_certainty,
        estimated_reliance=estimated_reliance,
    )

    warnings: list[str] = []
    if not prior_confidences:
        warnings.append(
            "Confidence module has no prior module outputs to aggregate — falling back to data-quality anchor."
        )
    if contradiction_count:
        warnings.append(
            f"Confidence reduced by {contradiction_count} contradictory property signal(s)."
        )
    if estimated_reliance >= 0.5:
        warnings.append(
            "Confidence reduced because this run relies heavily on estimated or defaulted inputs."
        )

    payload = module_payload_from_legacy_result(
        result=dq_result,
        context=context,
        assumptions_used={
            "legacy_module": "PropertyDataQualityModule",
            "property_id": property_input.property_id,
            "uses_full_engine_report": False,
            "prior_confidence_modules": sorted(prior_confidences.keys()),
            "perf_log_weights_used": bool(weights),
            "confidence_engine_version": "v2",
        },
        warnings=warnings,
        extra_data={
            "prior_module_confidences": prior_confidences,
            "data_quality_confidence": round(dq_confidence, 4) if dq_confidence is not None else None,
            "aggregated_prior_confidence": round(aggregated, 4) if aggregated is not None else None,
            "field_completeness": round(completeness, 4),
            "estimated_reliance": round(estimated_reliance, 4),
            "contradiction_count": contradiction_count,
            "comp_quality": round(comp_quality, 4),
            "model_agreement": round(model_agreement, 4),
            "scenario_fragility": round(scenario_fragility, 4),
            "legal_certainty": round(legal_certainty, 4),
            "combined_confidence": round(combined, 4) if combined is not None else None,
        },
        required_fields=["purchase_price", "sqft", "beds", "baths", "town", "state"],
    )
    if combined is not None:
        payload = payload.model_copy(
            update={
                "confidence": round(combined, 4),
                "confidence_band": confidence_band(combined),
            }
        )
    return payload.model_dump()


def _collect_prior_confidences(prior_outputs: dict[str, Any]) -> dict[str, float]:
    """Extract already-produced module confidence values without recomputing them."""

    values: dict[str, float] = {}
    for module_name, output in dict(prior_outputs or {}).items():
        if not isinstance(output, dict):
            continue
        confidence = output.get("confidence")
        if isinstance(confidence, (int, float)):
            values[str(module_name)] = round(float(confidence), 4)
    return values


def _weighted_mean(
    confidences: dict[str, float],
    weights: dict[str, float],
) -> float | None:
    if not confidences:
        return None
    numerator = 0.0
    denominator = 0.0
    for name, conf in confidences.items():
        w = float(weights.get(name) or 1.0)
        if w <= 0:
            continue
        numerator += w * float(conf)
        denominator += w
    if denominator == 0.0:
        return None
    return numerator / denominator


def _combine(
    *,
    aggregated: float | None,
    anchor: float | None,
    completeness: float,
    contradiction_count: int,
    comp_quality: float,
    model_agreement: float,
    scenario_fragility: float,
    legal_certainty: float,
    estimated_reliance: float,
) -> float | None:
    if aggregated is None and anchor is None:
        return None
    evidence_anchor = aggregated if aggregated is not None else anchor
    if evidence_anchor is None:
        evidence_anchor = 0.4
    if anchor is None:
        anchor = evidence_anchor

    contradiction_penalty = min(contradiction_count * 0.12, 0.45)
    fragility_penalty = max(0.0, min(scenario_fragility, 1.0)) * 0.12
    estimated_penalty = estimated_reliance * 0.15
    combined = (
        0.20 * anchor
        + 0.18 * evidence_anchor
        + 0.16 * completeness
        + 0.14 * comp_quality
        + 0.12 * model_agreement
        + 0.10 * legal_certainty
        + 0.10 * (1.0 - scenario_fragility)
    )
    combined -= contradiction_penalty + fragility_penalty + estimated_penalty
    return max(0.0, min(1.0, combined))


def _field_completeness(context: ExecutionContext) -> float:
    registry = dict(context.missing_data_registry or {})
    provided = len(list(registry.get("provided") or []))
    estimated = len(list(registry.get("estimated") or []))
    defaulted = len(list(registry.get("defaulted") or []))
    missing = len(list(registry.get("missing") or []))
    total = provided + estimated + defaulted + missing
    if total <= 0:
        return 0.4
    return max(0.0, min(1.0, (provided + 0.5 * estimated + 0.25 * defaulted) / total))


def _estimated_reliance(context: ExecutionContext) -> float:
    registry = dict(context.missing_data_registry or {})
    estimated = len(list(registry.get("estimated") or []))
    defaulted = len(list(registry.get("defaulted") or []))
    provided = len(list(registry.get("provided") or []))
    total = estimated + defaulted + provided
    if total <= 0:
        return 0.75
    return max(0.0, min(1.0, (estimated + defaulted) / total))


def _contradiction_count(context: ExecutionContext) -> int:
    property_data = dict(context.property_data or {})
    facts = dict(property_data.get("facts") or {})

    def _value(key: str) -> Any:
        if key in property_data:
            return property_data.get(key)
        return facts.get(key)

    price = _as_float(_value("purchase_price"))
    sqft = _as_float(_value("sqft"))
    beds = _as_float(_value("beds"))
    baths = _as_float(_value("baths"))
    rent = _as_float(context.assumptions.get("estimated_monthly_rent") or _value("estimated_monthly_rent"))

    count = 0
    if price and sqft and sqft > 0:
        ppsf = price / sqft
        if ppsf > 1500 or ppsf < 75:
            count += 1
    if beds and baths is not None and beds >= 5 and baths <= 1.5:
        count += 1
    if price and rent and rent > 0:
        gross_yield = (rent * 12.0) / price
        if gross_yield < 0.02:
            count += 1
    return count


def _comp_quality(prior_outputs: dict[str, Any]) -> float:
    valuation = dict(prior_outputs.get("valuation") or {})
    metrics = dict((valuation.get("data") or {}).get("metrics") or {})
    value = metrics.get("comp_confidence_score")
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 0.55


def _model_agreement(prior_confidences: dict[str, float]) -> float:
    values = list(prior_confidences.values())
    if len(values) <= 1:
        return 0.6
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    stddev = math.sqrt(variance)
    return max(0.0, min(1.0, 1.0 - (stddev / 0.35)))


def _scenario_fragility(prior_outputs: dict[str, Any]) -> float:
    scenario = dict(prior_outputs.get("resale_scenario") or {})
    metrics = dict((scenario.get("data") or {}).get("metrics") or {})
    spread = _as_float(metrics.get("bull_bear_spread_pct") or metrics.get("spread_pct"))
    if spread is not None:
        return max(0.0, min(1.0, spread))
    conf = _as_float(scenario.get("confidence"))
    if conf is None:
        return 0.35
    return max(0.0, min(1.0, 1.0 - conf))


def _legal_certainty(prior_outputs: dict[str, Any]) -> float:
    legal = dict(prior_outputs.get("legal_confidence") or {})
    conf = _as_float(legal.get("confidence"))
    if conf is not None:
        return conf
    return 0.7


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = ["run_confidence"]

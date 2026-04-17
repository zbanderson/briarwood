from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.property_data_quality import PropertyDataQualityModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)
from briarwood.pipeline.triage import load_model_weights


def run_confidence(context: ExecutionContext) -> dict[str, object]:
    """Aggregate prior module confidences with a data-quality anchor.

    Output confidence is a blend of (a) the weighted mean of every upstream
    module's reported confidence — weighted by the perf-log contribution
    weights when available, uniform otherwise — and (b) the property-data
    quality anchor from ``PropertyDataQualityModule``. When no priors are
    available the data-quality anchor is returned alone so the module is
    safe to run first in a plan.
    """

    property_input = build_property_input_from_context(context)
    dq_result = PropertyDataQualityModule().run(property_input)
    dq_confidence = float(dq_result.confidence) if dq_result.confidence is not None else None

    prior_confidences = _collect_prior_confidences(context.prior_outputs)
    weights = load_model_weights() if prior_confidences else {}
    aggregated = _weighted_mean(prior_confidences, weights) if prior_confidences else None

    combined = _combine(aggregated, dq_confidence)

    warnings: list[str] = []
    if not prior_confidences:
        warnings.append(
            "Confidence module has no prior module outputs to aggregate — falling back to data-quality anchor."
        )

    payload = module_payload_from_legacy_result(
        result=dq_result,
        assumptions_used={
            "legacy_module": "PropertyDataQualityModule",
            "property_id": property_input.property_id,
            "uses_full_engine_report": False,
            "prior_confidence_modules": sorted(prior_confidences.keys()),
            "perf_log_weights_used": bool(weights),
            "blend_alpha": 0.5,
        },
        warnings=warnings,
        extra_data={
            "prior_module_confidences": prior_confidences,
            "data_quality_confidence": round(dq_confidence, 4) if dq_confidence is not None else None,
            "aggregated_prior_confidence": round(aggregated, 4) if aggregated is not None else None,
            "combined_confidence": round(combined, 4) if combined is not None else None,
        },
    )
    if combined is not None:
        payload = payload.model_copy(update={"confidence": round(combined, 4)})
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


def _combine(aggregated: float | None, anchor: float | None) -> float | None:
    if aggregated is None and anchor is None:
        return None
    if aggregated is None:
        return anchor
    if anchor is None:
        return aggregated
    blended = 0.5 * aggregated + 0.5 * anchor
    return max(0.0, min(1.0, blended))


__all__ = ["run_confidence"]

from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.property_data_quality import PropertyDataQualityModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)


def run_confidence(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's current confidence wrapper for scoped execution.

    Briarwood does not yet have a fully decoupled standalone confidence engine.
    For Wave 1, this wrapper anchors confidence on ``PropertyDataQualityModule``
    and surfaces any prior module confidences that already exist in scoped
    execution. That keeps the dependency explicit without inventing new scoring.
    """

    property_input = build_property_input_from_context(context)
    result = PropertyDataQualityModule().run(property_input)
    prior_confidence_map = _collect_prior_confidences(context.prior_outputs)
    warnings: list[str] = []
    if not prior_confidence_map:
        warnings.append(
            "Confidence module is currently anchored on property-data quality until a dedicated scoped confidence model is added."
        )

    payload = module_payload_from_legacy_result(
        result=result,
        assumptions_used={
            "legacy_module": "PropertyDataQualityModule",
            "property_id": property_input.property_id,
            "uses_full_engine_report": False,
            "prior_confidence_modules": sorted(prior_confidence_map.keys()),
        },
        warnings=warnings,
    )
    payload.data["prior_module_confidences"] = prior_confidence_map
    return payload.model_dump()


def _collect_prior_confidences(prior_outputs: dict[str, Any]) -> dict[str, float]:
    """Extract already-produced module confidence values without recomputing them."""

    values: dict[str, float] = {}
    for module_name, output in dict(prior_outputs or {}).items():
        if not isinstance(output, dict):
            continue
        confidence = output.get("confidence")
        if isinstance(confidence, (float, int)):
            values[str(module_name)] = round(float(confidence), 4)
    return values


__all__ = ["run_confidence"]

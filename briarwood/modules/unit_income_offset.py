from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.scoped_common import build_property_input_from_context
from briarwood.routing_schema import ModulePayload


def run_unit_income_offset(context: ExecutionContext) -> dict[str, object]:
    """Run the additional-unit income-offset wrapper for scoped execution.

    This wrapper uses prior carry-cost output when available and reuses the
    existing comparable-sales decomposition to surface accessory-unit income
    support without inventing a parallel house-hack model.
    """

    property_input = build_property_input_from_context(context)
    comparable_result = ComparableSalesModule().run(property_input)
    carry_cost_output = context.get_module_output("carry_cost")

    comparable_metrics = dict(comparable_result.metrics or {})
    comparable_payload = getattr(comparable_result, "payload", None)
    additional_unit_income_value = getattr(comparable_payload, "additional_unit_income_value", None)
    additional_unit_count = getattr(comparable_payload, "additional_unit_count", None)
    monthly_total_cost = _carry_cost_metric(carry_cost_output, "monthly_total_cost")
    monthly_cash_flow = _carry_cost_metric(carry_cost_output, "monthly_cash_flow")

    payload = ModulePayload(
        data={
            "module_name": "unit_income_offset",
            "summary": comparable_result.summary,
            "comparable_sales": {
                "summary": comparable_result.summary,
                "metrics": comparable_metrics,
                "confidence": comparable_result.confidence,
            },
            "offset_snapshot": {
                "has_accessory_unit_signal": bool(property_input.has_back_house or property_input.adu_type or property_input.additional_units),
                "additional_unit_income_value": additional_unit_income_value,
                "additional_unit_count": additional_unit_count,
                "back_house_monthly_rent": property_input.back_house_monthly_rent,
                "unit_rents": list(property_input.unit_rents),
                "monthly_total_cost": monthly_total_cost,
                "monthly_cash_flow": monthly_cash_flow,
            },
        },
        confidence=_combined_confidence(comparable_result.confidence, carry_cost_output),
        assumptions_used={
            "legacy_module": "ComparableSalesModule",
            "uses_prior_carry_cost_output": isinstance(carry_cost_output, dict),
            "uses_full_engine_report": False,
        },
        warnings=_warnings_for_unit_offset(property_input, carry_cost_output),
    )
    return payload.model_dump()


def _carry_cost_metric(carry_cost_output: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(carry_cost_output, dict):
        return None
    return carry_cost_output.get("data", {}).get("metrics", {}).get(key)


def _combined_confidence(
    comparable_confidence: float,
    carry_cost_output: dict[str, Any] | None,
) -> float:
    carry_confidence = None
    if isinstance(carry_cost_output, dict) and isinstance(carry_cost_output.get("confidence"), (float, int)):
        carry_confidence = float(carry_cost_output["confidence"])
    if carry_confidence is None:
        return round(float(comparable_confidence), 4)
    return round(min(float(comparable_confidence), carry_confidence), 4)


def _warnings_for_unit_offset(
    property_input,
    carry_cost_output: dict[str, Any] | None,
) -> list[str]:
    warnings: list[str] = []
    if not (property_input.has_back_house or property_input.adu_type or property_input.additional_units):
        warnings.append("No structured accessory-unit signal was present; any offset story should be treated cautiously.")
    if not isinstance(carry_cost_output, dict):
        warnings.append("Carry-cost output was not available, so offset evidence is not framed against current ownership cost.")
    return warnings


__all__ = ["run_unit_income_offset"]

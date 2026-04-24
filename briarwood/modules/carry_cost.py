from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.ownership_economics import OwnershipEconomicsModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)


def run_carry_cost(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's ownership-carry underwriting through a scoped wrapper."""
    try:
        property_input = build_property_input_from_context(context)
        result = OwnershipEconomicsModule().run(property_input)
        assumptions_used = {
            "legacy_module": "OwnershipEconomicsModule",
            "property_id": property_input.property_id,
            "uses_full_engine_report": False,
        }
        return module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            required_fields=["purchase_price", "taxes", "insurance"],
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="carry_cost",
            context=context,
            summary="Carry cost is provisional because core ownership inputs are incomplete.",
            warnings=[f"Carry-cost fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={"uses_full_engine_report": False, "fallback_reason": "sparse_inputs"},
            required_fields=["purchase_price", "taxes", "insurance"],
        ).model_dump()


__all__ = ["run_carry_cost"]

from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.cost_valuation import CostValuationModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)


def run_carry_cost(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's ownership-carry underwriting through a scoped wrapper."""

    property_input = build_property_input_from_context(context)
    result = CostValuationModule().run(property_input)
    assumptions_used = {
        "legacy_module": "CostValuationModule",
        "property_id": property_input.property_id,
        "uses_full_engine_report": False,
    }
    return module_payload_from_legacy_result(
        result=result,
        assumptions_used=assumptions_used,
    ).model_dump()


__all__ = ["run_carry_cost"]

from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)


def run_resale_scenario(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's forward resale scenario through a scoped wrapper.

    Delegates to ``BullBaseBearModule`` which internally runs current-value,
    market-history, town-county outlook, risk, and scarcity sub-modules to
    produce bull / base / bear scenario values.
    """

    property_input = build_property_input_from_context(context)
    result = BullBaseBearModule().run(property_input)
    assumptions_used = {
        "legacy_module": "BullBaseBearModule",
        "property_id": property_input.property_id,
        "uses_full_engine_report": False,
    }
    return module_payload_from_legacy_result(
        result=result,
        assumptions_used=assumptions_used,
    ).model_dump()


__all__ = ["run_resale_scenario"]

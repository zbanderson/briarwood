from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.renovation_scenario import RenovationScenarioModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)


def run_renovation_impact(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's renovation-impact module through a scoped wrapper.

    Delegates to ``RenovationScenarioModule`` which estimates value creation
    from a planned renovation by comparing current vs. post-renovation BCV.
    """

    property_input = build_property_input_from_context(context)
    result = RenovationScenarioModule().run(property_input)
    assumptions_used = {
        "legacy_module": "RenovationScenarioModule",
        "property_id": property_input.property_id,
        "uses_full_engine_report": False,
    }
    return module_payload_from_legacy_result(
        result=result,
        assumptions_used=assumptions_used,
    ).model_dump()


__all__ = ["run_renovation_impact"]

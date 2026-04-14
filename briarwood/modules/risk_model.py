from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)


def run_risk_model(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's risk-constraint logic through a scoped wrapper.

    The planner still declares a dependency on ``valuation`` so V2 execution can
    sequence modules consistently, but this risk module remains mostly
    property-input-driven today.
    """

    property_input = build_property_input_from_context(context)
    result = RiskConstraintsModule().run(property_input)
    payload = module_payload_from_legacy_result(
        result=result,
        assumptions_used={
            "legacy_module": "RiskConstraintsModule",
            "property_id": property_input.property_id,
            "valuation_dependency_declared": True,
            "uses_full_engine_report": False,
        },
    )
    return payload.model_dump()


__all__ = ["run_risk_model"]

from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.macro_reader import apply_macro_nudge
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)

MACRO_MAX_NUDGE = 0.03


def run_valuation(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's legacy current-value logic through a scoped interface.

    Reuses ``CurrentValueModule`` for the core valuation and applies a
    bounded macro confidence nudge based on the county's HPI momentum
    (sourced from FRED). Comp-driven value estimation remains dominant;
    the macro dimension only modestly reinforces or discounts the
    confidence Briarwood reports.
    """

    property_input = build_property_input_from_context(context)
    result = CurrentValueModule().run(property_input)
    macro_nudge = apply_macro_nudge(
        base_confidence=result.confidence,
        context=context,
        dimension="hpi_momentum",
        max_nudge=MACRO_MAX_NUDGE,
    )
    assumptions_used = {
        "legacy_module": "CurrentValueModule",
        "property_id": property_input.property_id,
        "macro_context_used": macro_nudge.signal is not None,
        "uses_full_engine_report": False,
        "notes": [
            "CurrentValueModule still pulls comparable, market-history, income-support, and hybrid anchors internally."
        ],
    }
    payload = module_payload_from_legacy_result(
        result=result,
        assumptions_used=assumptions_used,
        extra_data={"macro_nudge": macro_nudge.to_meta()},
    )
    if macro_nudge.adjusted_confidence is not None:
        payload = payload.model_copy(
            update={"confidence": round(macro_nudge.adjusted_confidence, 4)}
        )
    return payload.model_dump()


__all__ = ["run_valuation"]

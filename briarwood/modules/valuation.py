from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.macro_reader import apply_macro_nudge
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
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

    try:
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
            context=context,
            assumptions_used=assumptions_used,
            extra_data={"macro_nudge": macro_nudge.to_meta()},
            required_fields=["purchase_price", "sqft", "beds", "baths", "town", "state"],
        )
        if macro_nudge.adjusted_confidence is not None:
            payload = payload.model_copy(
                update={"confidence": round(macro_nudge.adjusted_confidence, 4)}
            )
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="valuation",
            context=context,
            summary="Fair value is speculative because the property facts are too sparse or contradictory for a stable comp read.",
            warnings=[f"Valuation fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={"uses_full_engine_report": False, "fallback_reason": "sparse_or_contradictory_inputs"},
            required_fields=["purchase_price", "sqft", "beds", "baths", "town", "state"],
        ).model_dump()


__all__ = ["run_valuation"]

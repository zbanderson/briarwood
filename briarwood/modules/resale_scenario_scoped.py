from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.macro_reader import apply_macro_nudge
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)
from briarwood.modules.town_development_index import apply_dev_index_nudge

MACRO_MAX_NUDGE = 0.04
DEV_INDEX_MAX_NUDGE = 0.04


def run_resale_scenario(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's forward resale scenario through a scoped wrapper.

    Delegates to ``BullBaseBearModule`` which internally runs current-value,
    market-history, town-county outlook, risk, and scarcity sub-modules to
    produce bull / base / bear scenario values. Applies a bounded macro
    confidence nudge based on the county's HPI momentum — strong county
    appreciation modestly reinforces a forward-resale read; weak momentum
    modestly discounts it.
    """

    try:
        property_input = build_property_input_from_context(context)
        result = BullBaseBearModule().run(property_input)
        macro_nudge = apply_macro_nudge(
            base_confidence=result.confidence,
            context=context,
            dimension="hpi_momentum",
            max_nudge=MACRO_MAX_NUDGE,
        )
        dev_nudge = apply_dev_index_nudge(
            base_confidence=macro_nudge.adjusted_confidence
            if macro_nudge.adjusted_confidence is not None
            else result.confidence,
            context=context,
            max_nudge=DEV_INDEX_MAX_NUDGE,
        )
        assumptions_used = {
            "legacy_module": "BullBaseBearModule",
            "property_id": property_input.property_id,
            "macro_context_used": macro_nudge.signal is not None,
            "dev_index_used": dev_nudge.velocity is not None,
            "uses_full_engine_report": False,
        }
        payload = module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            extra_data={
                "macro_nudge": macro_nudge.to_meta(),
                "dev_index_nudge": dev_nudge.to_meta(),
            },
            required_fields=["purchase_price", "taxes", "sqft", "town", "state"],
        )
        if dev_nudge.adjusted_confidence is not None:
            payload = payload.model_copy(
                update={"confidence": round(dev_nudge.adjusted_confidence, 4)}
            )
        elif macro_nudge.adjusted_confidence is not None:
            payload = payload.model_copy(
                update={"confidence": round(macro_nudge.adjusted_confidence, 4)}
            )
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="resale_scenario",
            context=context,
            summary="Forward scenarios are provisional because Briarwood is missing enough basis or market context to project confidently.",
            warnings=[f"Resale-scenario fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={"uses_full_engine_report": False, "fallback_reason": "sparse_inputs"},
            required_fields=["purchase_price", "taxes", "sqft", "town", "state"],
        ).model_dump()


__all__ = ["run_resale_scenario"]

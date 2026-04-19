from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.macro_reader import apply_macro_nudge
from briarwood.modules.rental_ease import RentalEaseModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)

MACRO_MAX_NUDGE = 0.03


def run_rental_option(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's rental-option path through a scoped wrapper.

    Composes ``IncomeSupportModule`` (income underwriting) with
    ``RentalEaseModule`` (rental absorption ease) to produce a combined
    rental-option payload. The county's employment signal applies a
    bounded nudge to rental-ease confidence — a stronger labor market
    modestly reinforces rental demand expectations.
    """

    try:
        property_input = build_property_input_from_context(context)
        income_result = IncomeSupportModule().run(property_input)
        rental_ease_result = RentalEaseModule().run(property_input)
        macro_nudge = apply_macro_nudge(
            base_confidence=rental_ease_result.confidence,
            context=context,
            dimension="employment",
            max_nudge=MACRO_MAX_NUDGE,
        )
        assumptions_used = {
            "legacy_module": "IncomeSupportModule",
            "supporting_module": "RentalEaseModule",
            "property_id": property_input.property_id,
            "macro_context_used": macro_nudge.signal is not None,
            "uses_full_engine_report": False,
        }
        extra_data = {
            "income_support": {
                "score": income_result.score,
                "confidence": income_result.confidence,
                "summary": income_result.summary,
                "metrics": dict(income_result.metrics or {}),
            },
            "macro_nudge": macro_nudge.to_meta(),
        }
        payload = module_payload_from_legacy_result(
            result=rental_ease_result,
            context=context,
            assumptions_used=assumptions_used,
            extra_data=extra_data,
            required_fields=["purchase_price", "estimated_monthly_rent", "sqft", "beds", "baths"],
        )
        if macro_nudge.adjusted_confidence is not None:
            payload = payload.model_copy(
                update={"confidence": round(macro_nudge.adjusted_confidence, 4)}
            )
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="rental_option",
            context=context,
            summary="Rent outlook is provisional because Briarwood lacks enough rent and carry support.",
            warnings=[f"Rental-option fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={"uses_full_engine_report": False, "fallback_reason": "sparse_inputs"},
            required_fields=["purchase_price", "estimated_monthly_rent", "sqft", "beds", "baths"],
        ).model_dump()


__all__ = ["run_rental_option"]

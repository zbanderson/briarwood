from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)


def run_income_support(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's income-support underwriting through a scoped wrapper.

    Sibling to ``rental_option``. The two tools share an engine
    (``IncomeSupportModule``) but present different contracts:

    - ``rental_option`` returns the composite rent-path strategy answer:
      ``RentalEaseModule`` (rent absorption ease) + ``IncomeSupportModule``
      (underwriting) + employment-macro nudge. Use it for STRATEGY /
      RENT_LOOKUP / PROJECTION questions about "if you rent, how viable
      is that path?"
    - ``income_support`` exposes the raw DSCR / rent-coverage / income-support
      ratio directly. Use it for LOOKUP-style questions like "what is the
      DSCR?" or "what's the rent coverage?" without needing the full
      rent-path narrative.

    Anti-recursion: this wrapper instantiates ``IncomeSupportModule``
    in-process and never reads ``context.prior_outputs["income_support"]``.
    Likewise the ``rental_option`` wrapper at
    briarwood/modules/rental_option_scoped.py calls ``IncomeSupportModule``
    directly — NOT through the scoped ``income_support`` tool. This split
    prevents double error-handling and circular registry dependencies.
    Reference: PROMOTION_PLAN.md entry 8.

    Standalone wrapper. Error contract (DECISIONS.md 2026-04-24): any
    exception returns ``module_payload_from_error`` (``mode="fallback"``,
    ``confidence=0.08``). Payload field names from ``IncomeAgentOutput`` are
    preserved unchanged — ``income_support_ratio``, ``rent_coverage``,
    ``price_to_rent``, ``monthly_cash_flow``, ``rent_support_classification``,
    ``effective_monthly_rent``, ``gross_monthly_cost``, and others — so
    consumers (``risk_bar``, ``evidence``, ``comp_intelligence``,
    ``rental_ease``, ``hybrid_value``) continue to read the payload
    identically.
    """
    try:
        property_input = build_property_input_from_context(context)
        result = IncomeSupportModule().run(property_input)
        assumptions_used = {
            "legacy_module": "IncomeSupportModule",
            "property_id": property_input.property_id,
            "exposes_raw_underwriting_signal": True,
            "uses_full_engine_report": False,
            "notes": [
                "income_support exposes DSCR / rent-coverage / income-support"
                " ratio for LOOKUP intents. Use the scoped rental_option tool"
                " for the full rent-path strategy answer."
            ],
        }
        return module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            required_fields=[
                "purchase_price",
                "estimated_monthly_rent",
                "down_payment_percent",
                "interest_rate",
                "loan_term_years",
            ],
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="income_support",
            context=context,
            summary="Rental underwriting is provisional because ask price, rent, or financing assumptions are missing.",
            warnings=[f"Income-support fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "exposes_raw_underwriting_signal": True,
                "uses_full_engine_report": False,
                "fallback_reason": "sparse_underwriting_inputs",
            },
            required_fields=[
                "purchase_price",
                "estimated_monthly_rent",
                "down_payment_percent",
                "interest_rate",
                "loan_term_years",
            ],
        ).model_dump()


__all__ = ["run_income_support"]

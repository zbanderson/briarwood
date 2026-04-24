from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)


def run_market_value_history(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's town/county ZHVI trend lookup through a scoped wrapper.

    Standalone wrapper. Error contract (DECISIONS.md 2026-04-24): any exception
    raised by the underlying ``MarketValueHistoryModule`` (missing town/state,
    empty ZHVI file, provider failure) returns ``module_payload_from_error``
    (``mode="fallback"``, ``confidence=0.08``).

    The payload is geography-level, not property-level. Preserved field names
    from the legacy ``MarketValueHistoryOutput`` (consumed by ``comparable_sales``,
    ``current_value``, and ``bull_base_bear`` via direct class access):
    ``source_name``, ``geography_name``, ``geography_type``, ``current_value``,
    ``one_year_change_pct``, ``three_year_change_pct``, ``history_points``.
    """
    try:
        property_input = build_property_input_from_context(context)
        result = MarketValueHistoryModule().run(property_input)
        assumptions_used = {
            "legacy_module": "MarketValueHistoryModule",
            "property_id": property_input.property_id,
            "geography_level": True,
            "uses_full_engine_report": False,
        }
        return module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            required_fields=["town", "state"],
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="market_value_history",
            context=context,
            summary="Market-trend history unavailable because town / state / ZHVI coverage is missing or malformed.",
            warnings=[f"Market-value-history fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "uses_full_engine_report": False,
                "fallback_reason": "missing_or_malformed_geography",
            },
            required_fields=["town", "state"],
        ).model_dump()


__all__ = ["run_market_value_history"]

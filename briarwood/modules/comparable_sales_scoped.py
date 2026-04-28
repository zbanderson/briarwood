from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)


def run_comparable_sales(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's comp-based fair-value anchor (Engine A) through a scoped wrapper.

    Standalone wrapper. Error contract (DECISIONS.md 2026-04-24): any exception
    raised by ``ComparableSalesModule`` or its internal ``MarketValueHistoryModule``
    / ``ComparableSalesAgent`` lookup returns ``module_payload_from_error``
    (``mode="fallback"``, ``confidence=0.08``).

    Hybrid detection (``_detect_hybrid_valuation``) is baked into the legacy
    ``run()`` — the scoped wrapper absorbs it unchanged. No behavior change.

    Field-name stability. Consumers read the legacy payload by key:
      - briarwood/modules/hybrid_value.py (reads from prior_results.comparable_sales)
      - briarwood/modules/unit_income_offset.py (reads comparable_sales sub-dict)
      - briarwood/claims/pipeline.py:62-88 (post-hoc graft; retirement is a
        follow-up, not this handoff — see ROADMAP.md)
    Preserved keys: ``comparable_value``, ``comp_count``, ``confidence``,
    ``comps_used``, ``rejected_count``, ``direct_value_range``,
    ``income_adjusted_value_range``, ``location_adjustment_range``,
    ``lot_adjustment_range``, ``blended_value_range``, ``comp_confidence_score``,
    ``is_hybrid_valuation``, ``primary_dwelling_value``,
    ``additional_unit_income_value``, ``additional_unit_count``,
    ``additional_unit_annual_income``, ``additional_unit_cap_rate``,
    ``hybrid_valuation_note``.

    Engine A vs Engine B: this module is the fair-value anchor (saved comps,
    backs ``value_thesis.comps``). It is distinct from the user-facing "CMA"
    tool at briarwood/agent/tools.py:1802 (``get_cma``; live-Zillow first,
    backs ``session.last_market_support_view``). See ROADMAP.md 2026-04-24
    *Two comp engines with divergent quality*.
    """
    try:
        property_input = build_property_input_from_context(context)
        result = ComparableSalesModule().run(property_input)
        assumptions_used = {
            "legacy_module": "ComparableSalesModule",
            "engine": "Engine A (saved comps)",
            "property_id": property_input.property_id,
            "uses_full_engine_report": False,
        }
        return module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            required_fields=["sqft", "beds", "baths", "town", "state"],
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="comparable_sales",
            context=context,
            summary="Comp-based fair value is provisional because subject facts, comp coverage, or market history is too sparse.",
            warnings=[f"Comparable-sales fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "engine": "Engine A (saved comps)",
                "uses_full_engine_report": False,
                "fallback_reason": "sparse_inputs_or_provider_error",
            },
            required_fields=["sqft", "beds", "baths", "town", "state"],
        ).model_dump()


def receive_feedback(session_id: str, signal: dict[str, object]) -> dict[str, object]:
    """Record comparable-sales confidence-vs-outcome alignment.

    Stage 4 feedback is record-only: it writes alignment evidence and never
    changes comp weights, thresholds, prompts, or module behavior.
    """

    from briarwood.eval.alignment import receive_feedback_for_module

    return receive_feedback_for_module("comparable_sales", session_id, dict(signal))


__all__ = ["receive_feedback", "run_comparable_sales"]

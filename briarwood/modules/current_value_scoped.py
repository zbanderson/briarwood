from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)


def run_current_value(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's pre-macro-nudge fair-value estimate through a scoped wrapper.

    Sibling to ``valuation``. The two tools share an engine (``CurrentValueModule``)
    but present different contracts:

    - ``valuation`` applies the ≤ 3% HPI-momentum macro confidence nudge. Use it
      for the canonical user-facing "what is this worth?" answer.
    - ``current_value`` returns the same engine output WITHOUT the macro nudge.
      Use it for scenario modeling, stress testing, or when the caller needs to
      isolate macro-side effects from the comp-driven engine.

    Anti-recursion: this wrapper instantiates ``CurrentValueModule`` in-process
    and never reads ``context.prior_outputs["current_value"]``. Likewise the
    ``valuation`` wrapper at briarwood/modules/valuation.py calls
    ``CurrentValueModule`` directly — NOT through the scoped ``current_value``
    tool. This split prevents double error-handling and circular registry
    dependencies. Reference: PROMOTION_PLAN.md entry 3.

    Standalone wrapper. Error contract (DECISIONS.md 2026-04-24): any exception
    returns ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).
    Payload field names from ``CurrentValueOutput`` are preserved unchanged so
    direct callers (``bull_base_bear``, ``teardown_scenario``, ``renovation_scenario``,
    and the ``valuation`` wrapper) continue to read the payload identically.
    """
    try:
        property_input = build_property_input_from_context(context)
        result = CurrentValueModule().run(property_input)
        assumptions_used = {
            "legacy_module": "CurrentValueModule",
            "property_id": property_input.property_id,
            "applies_macro_nudge": False,
            "uses_full_engine_report": False,
            "notes": [
                "current_value is the pre-macro fair-value anchor. Use the scoped"
                " valuation tool for the canonical user-facing number that includes"
                " the HPI-momentum confidence nudge."
            ],
        }
        return module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            required_fields=["purchase_price", "sqft", "beds", "baths", "town", "state"],
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="current_value",
            context=context,
            summary="Pre-macro fair value is speculative because the property facts are too sparse or contradictory for a stable comp read.",
            warnings=[f"Current-value fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "applies_macro_nudge": False,
                "uses_full_engine_report": False,
                "fallback_reason": "sparse_or_contradictory_inputs",
            },
            required_fields=["purchase_price", "sqft", "beds", "baths", "town", "state"],
        ).model_dump()


def receive_feedback(session_id: str, signal: dict[str, object]) -> dict[str, object]:
    """Record current-value confidence-vs-outcome alignment.

    Stage 4 feedback is record-only: it writes alignment evidence and never
    changes valuation weights, thresholds, prompts, or module behavior.
    """

    from briarwood.eval.alignment import receive_feedback_for_module

    return receive_feedback_for_module("current_value", session_id, dict(signal))


__all__ = ["receive_feedback", "run_current_value"]

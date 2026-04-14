from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)


def run_valuation(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's legacy current-value logic through a scoped interface.

    This wrapper is intentionally thin. It reuses ``CurrentValueModule`` so the
    scoped execution path inherits existing valuation behavior without requiring
    the full legacy engine to run end-to-end.
    """

    property_input = build_property_input_from_context(context)
    result = CurrentValueModule().run(property_input)
    assumptions_used = {
        "legacy_module": "CurrentValueModule",
        "property_id": property_input.property_id,
        "uses_full_engine_report": False,
        "notes": [
            "CurrentValueModule still pulls comparable, market-history, income-support, and hybrid anchors internally."
        ],
    }
    return module_payload_from_legacy_result(
        result=result,
        assumptions_used=assumptions_used,
    ).model_dump()


__all__ = ["run_valuation"]

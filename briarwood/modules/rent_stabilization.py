from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.rental_ease import RentalEaseModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_legacy_result,
)
from briarwood.modules.town_county_outlook import TownCountyOutlookModule


def run_rent_stabilization(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's rent-durability path through a scoped wrapper.

    This wrapper keeps the coupling explicit by reusing the existing
    ``RentalEaseModule`` and surfacing town/county support alongside it.
    """

    property_input = build_property_input_from_context(context)
    rental_ease_result = RentalEaseModule().run(property_input)
    town_result = TownCountyOutlookModule().run(property_input)
    assumptions_used = {
        "legacy_module": "RentalEaseModule",
        "supporting_module": "TownCountyOutlookModule",
        "property_id": property_input.property_id,
        "uses_full_engine_report": False,
    }
    extra_data = {
        "town_county_outlook": {
            "score": town_result.score,
            "confidence": town_result.confidence,
            "summary": town_result.summary,
            "metrics": dict(town_result.metrics or {}),
        }
    }
    return module_payload_from_legacy_result(
        result=rental_ease_result,
        assumptions_used=assumptions_used,
        extra_data=extra_data,
    ).model_dump()


__all__ = ["run_rent_stabilization"]

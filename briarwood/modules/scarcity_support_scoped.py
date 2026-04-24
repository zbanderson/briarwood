from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.scarcity_support import ScarcitySupportModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)


def run_scarcity_support(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's town/segment scarcity signal through a scoped wrapper.

    Standalone wrapper. Error contract (DECISIONS.md 2026-04-24): any exception
    raised by the underlying ``ScarcitySupportModule`` or its
    ``TownCountyDataService`` lookup returns ``module_payload_from_error``
    (``mode="fallback"``, ``confidence=0.08``).

    Field-name stability. ``scarcity_support_score`` is read by key in multiple
    consumers — passing the payload through ``module_payload_from_legacy_result``
    preserves it verbatim. Current readers:
      - briarwood/modules/bull_base_bear.py (KEEP-as-internal-helper;
        reclassified from DEPRECATE in Handoff 4 — see DECISIONS.md
        2026-04-24 "PROMOTION_PLAN.md entry 6 decision corrected")
      - briarwood/interactions/town_x_scenario.py
      - briarwood/interactions/valuation_x_town.py
      - briarwood/agents/rental_ease/agent.py
    (Historical reader ``briarwood/decision_model/lens_scoring.py`` was
    deleted in Handoff 4 alongside ``calculate_final_score``. The former
    ``scoring.py`` reads were part of that dead chain and were also
    removed — see DECISIONS.md 2026-04-24 "PROMOTION_PLAN.md entry 15
    scope-limit paragraph corrected.")
    """
    try:
        property_input = build_property_input_from_context(context)
        result = ScarcitySupportModule().run(property_input)
        assumptions_used = {
            "legacy_module": "ScarcitySupportModule",
            "property_id": property_input.property_id,
            "geography_driven": True,
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
            module_name="scarcity_support",
            context=context,
            summary="Scarcity signal unavailable — town/county outlook could not be resolved.",
            warnings=[f"Scarcity-support fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "geography_driven": True,
                "uses_full_engine_report": False,
                "fallback_reason": "missing_or_malformed_geography",
            },
            required_fields=["town", "state"],
        ).model_dump()


__all__ = ["run_scarcity_support"]

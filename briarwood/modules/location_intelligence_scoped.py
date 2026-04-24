from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.location_intelligence import LocationIntelligenceModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)


def run_location_intelligence(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's landmark-proximity benchmarking through a scoped wrapper.

    Standalone wrapper. Error contract (DECISIONS.md 2026-04-24): any exception
    raised by the underlying ``LocationIntelligenceModule`` or its comp-provider
    lookup returns ``module_payload_from_error`` (``mode="fallback"``,
    ``confidence=0.08``).

    Missing-input semantics preserved. The underlying module already populates
    ``confidence_notes`` and ``missing_inputs`` when subject coordinates,
    landmark points, or geo peer comps are absent. ``module_payload_from_legacy_result``
    passes those through unchanged so degraded output remains distinguishable
    from wrapper-caught exceptions.

    Consumers: briarwood/micro_location_engine.py, briarwood/evidence (two paths),
    briarwood/decision_model/scoring.py:295-296, and several eval specs. No
    scoped wrapper covers the MICRO_LOCATION intent family until this promotion.
    """
    try:
        property_input = build_property_input_from_context(context)
        result = LocationIntelligenceModule().run(property_input)
        assumptions_used = {
            "legacy_module": "LocationIntelligenceModule",
            "property_id": property_input.property_id,
            "benchmarks_against_town_peer_comps": True,
            "uses_full_engine_report": False,
        }
        return module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            required_fields=["town", "state", "latitude", "longitude"],
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="location_intelligence",
            context=context,
            summary="Location intelligence unavailable — comp provider or coordinates could not be resolved.",
            warnings=[f"Location-intelligence fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "benchmarks_against_town_peer_comps": True,
                "uses_full_engine_report": False,
                "fallback_reason": "provider_or_geocode_error",
            },
            required_fields=["town", "state", "latitude", "longitude"],
        ).model_dump()


__all__ = ["run_location_intelligence"]

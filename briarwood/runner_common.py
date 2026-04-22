"""Shared utilities used by the routed runner path.

Hosts property-input preparation and validation shared across callers.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from briarwood.schemas import PropertyInput
from briarwood.routing_schema import (
    EngineOutput,
    RoutingDecision,
    UnifiedIntelligenceOutput,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RoutedAnalysisResult:
    """Bundle the routing-layer artifacts produced by the scoped runner."""

    routing_decision: RoutingDecision
    engine_output: EngineOutput
    unified_output: UnifiedIntelligenceOutput
    property_summary: dict[str, Any]


def _prepare_property_input(property_input: PropertyInput) -> None:
    """Apply smart defaults and geocoding to a PropertyInput before analysis."""
    from briarwood.defaults import apply_smart_defaults
    from briarwood.geocoder import apply_geocoding

    # Apply smart defaults for missing financing, costs, and condition
    defaults_result = apply_smart_defaults(property_input)
    property_input.defaults_applied = defaults_result.fields

    # Geocoding is opt-in for app responsiveness. It can introduce slow
    # network waits during report loading, especially in Dash callbacks.
    if os.environ.get("BRIARWOOD_ENABLE_GEOCODING", "").strip().lower() not in {"1", "true", "yes"}:
        return

    # Geocode address if lat/lon missing (enables location_intelligence module).
    # Geocoding is best-effort: network/import failures must not block analysis,
    # but we log them so silent degradation of location_intelligence is debuggable.
    try:
        if apply_geocoding(property_input):
            property_input.geocoded = True
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning(
            "Geocoding skipped for %s: %s", property_input.address, exc
        )


def validate_property_input(property_input: PropertyInput) -> None:
    """Fail fast on obviously invalid inputs before running analysis."""

    numeric_validations = {
        "purchase_price": property_input.purchase_price,
        "beds": property_input.beds,
        "baths": property_input.baths,
        "sqft": property_input.sqft,
        "lot_size": property_input.lot_size,
        "taxes": property_input.taxes,
        "insurance": property_input.insurance,
        "monthly_hoa": property_input.monthly_hoa,
        "estimated_monthly_rent": property_input.estimated_monthly_rent,
    }
    invalid_negative = [
        field_name
        for field_name, value in numeric_validations.items()
        if value is not None and value < 0
    ]
    if invalid_negative:
        raise ValueError(
            "Property input contains negative values for fields that must be non-negative: "
            + ", ".join(sorted(invalid_negative))
        )

    if not property_input.address:
        raise ValueError("Property input is missing address.")
    if not property_input.town or not property_input.state:
        raise ValueError("Property input must include town and state.")

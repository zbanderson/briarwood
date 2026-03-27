from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from briarwood.agents.scarcity.schemas import ScarcitySupportInputs
from briarwood.agents.town_county.providers import (
    FileBackedFloodRiskProvider,
    FileBackedLiquidityProvider,
    FileBackedPopulationProvider,
    FileBackedPriceTrendProvider,
)
from briarwood.agents.town_county.service import TownCountyDataService, TownCountyOutlookResult
from briarwood.agents.town_county.sources import TownCountyOutlookRequest
from briarwood.schemas import PropertyInput


@lru_cache(maxsize=1)
def build_default_town_county_service() -> TownCountyDataService:
    """Create the file-backed location service used by the v1 report pipeline."""

    data_root = Path(__file__).resolve().parents[2] / "data" / "town_county"
    return TownCountyDataService(
        price_provider=FileBackedPriceTrendProvider(data_root / "price_trends.json"),
        population_provider=FileBackedPopulationProvider(data_root / "population_trends.json"),
        flood_provider=FileBackedFloodRiskProvider(data_root / "flood_risk.json"),
        liquidity_provider=FileBackedLiquidityProvider(data_root / "liquidity.json"),
    )


def build_town_county_request(
    property_input: PropertyInput,
    *,
    price_position: str | None = None,
) -> TownCountyOutlookRequest:
    """Map property-level facts into the town/county outlook request."""

    return TownCountyOutlookRequest(
        town=property_input.town,
        state=property_input.state,
        county=property_input.county,
        school_signal=property_input.school_rating,
        days_on_market=property_input.days_on_market,
        price_position=price_position,
    )


def build_scarcity_inputs(
    property_input: PropertyInput,
    *,
    outlook: TownCountyOutlookResult,
) -> ScarcitySupportInputs:
    """Build scarcity inputs from sourced location signals plus property facts.

    The v1 pipeline only populates sourced or directly observed fields. When anchor
    context or local lot benchmarks are unavailable, we intentionally leave them
    unset so the scarcity score lowers confidence rather than inventing support.
    """

    normalized = outlook.normalized.inputs
    lot_size_sqft = None
    if property_input.lot_size is not None:
        lot_size_sqft = int(property_input.lot_size * 43560)

    return ScarcitySupportInputs.model_validate(
        {
            "demand_consistency": {
                "town": property_input.town,
                "state": property_input.state,
                "county": property_input.county,
                "liquidity_signal": normalized.liquidity_signal,
                "days_on_market": property_input.days_on_market,
                "town_price_trend": normalized.town_price_trend,
                "county_price_trend": normalized.county_price_trend,
                "school_signal": normalized.school_signal,
            },
            "location_scarcity": {
                "town": property_input.town,
                "state": property_input.state,
            },
            "land_scarcity": {
                "town": property_input.town,
                "state": property_input.state,
                "lot_size_sqft": lot_size_sqft,
            },
        }
    )

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DemandConsistencyInputs(BaseModel):
    """Inputs for determining whether the market consistently rewards scarce traits."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    county: str | None = None
    liquidity_signal: str | None = Field(default=None, pattern="^(strong|normal|fragile)$")
    months_of_supply: float | None = Field(default=None, ge=0)
    days_on_market: int | None = Field(default=None, ge=0)
    town_price_trend: float | None = None
    county_price_trend: float | None = None
    school_signal: float | None = Field(default=None, ge=0, le=10)


class DemandConsistencyScore(BaseModel):
    """Structured output for market demand consistency."""

    model_config = ConfigDict(extra="forbid")

    demand_consistency_score: float
    demand_consistency_label: str
    confidence: float
    demand_drivers: list[str]
    demand_risks: list[str]
    missing_inputs: list[str]
    unsupported_claims: list[str]
    summary: str


class LocationScarcityInputs(BaseModel):
    """Inputs for judging how hard a property's location advantages are to replicate."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    anchor_type: str | None = None
    distance_to_anchor_miles: float | None = Field(default=None, ge=0)
    comparable_count_within_anchor_radius: int | None = Field(default=None, ge=0)
    anchor_radius_miles: float | None = Field(default=None, gt=0)


class LocationScarcityScore(BaseModel):
    """Structured output for location scarcity."""

    model_config = ConfigDict(extra="forbid")

    location_scarcity_score: float
    location_scarcity_label: str
    confidence: float
    demand_drivers: list[str]
    scarcity_notes: list[str]
    missing_inputs: list[str]
    unsupported_claims: list[str]
    summary: str


class LandScarcityInputs(BaseModel):
    """Inputs for judging how hard a property's lot characteristics are to replicate locally."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    lot_size_sqft: int | None = Field(default=None, ge=0)
    local_median_lot_size_sqft: int | None = Field(default=None, gt=0)
    lot_is_corner: bool | None = None
    adu_possible: bool | None = None
    redevelopment_optional: bool | None = None


class LandScarcityScore(BaseModel):
    """Structured output for land scarcity."""

    model_config = ConfigDict(extra="forbid")

    land_scarcity_score: float
    land_scarcity_label: str
    confidence: float
    demand_drivers: list[str]
    scarcity_notes: list[str]
    missing_inputs: list[str]
    unsupported_claims: list[str]
    summary: str


class ScarcitySupportInputs(BaseModel):
    """Combined inputs for the first scarcity support score."""

    model_config = ConfigDict(extra="forbid")

    demand_consistency: DemandConsistencyInputs
    location_scarcity: LocationScarcityInputs
    land_scarcity: LandScarcityInputs


class ScarcitySupportScore(BaseModel):
    """Combined scarcity support output from early scarcity components."""

    model_config = ConfigDict(extra="forbid")

    demand_consistency_score: float
    location_scarcity_score: float
    land_scarcity_score: float
    scarcity_score: float
    scarcity_support_score: float
    scarcity_label: str
    confidence: float
    demand_drivers: list[str]
    scarcity_notes: list[str]
    missing_inputs: list[str]
    unsupported_claims: list[str]
    summary: str
    buyer_takeaway: str

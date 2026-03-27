from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SourceFieldStatus(BaseModel):
    """Trace how a normalized field was populated."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    source_type: str
    source_name: str
    source_value: str
    is_fallback: bool = False
    notes: str | None = None


class TownCountyInputs(BaseModel):
    """Normalized location inputs for the town/county thesis helper."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    county: str | None = None
    town_price_trend: float | None = None
    county_price_trend: float | None = None
    town_population_trend: float | None = None
    county_population_trend: float | None = None
    school_signal: float | None = Field(default=None, ge=0, le=10)
    flood_risk: str | None = Field(default=None, pattern="^(low|medium|high|none)$")
    liquidity_signal: str | None = Field(default=None, pattern="^(strong|normal|fragile)$")
    scarcity_signal: float | None = Field(default=None, ge=0, le=1)
    days_on_market: int | None = Field(default=None, ge=0)
    price_position: str | None = Field(default=None, pattern="^(supported|neutral|stretched)$")
    data_as_of: str | None = None


class TownCountySourceRecord(BaseModel):
    """Raw source-backed town/county outlook fields before normalization."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    county: str | None = None
    town_price_index_current: float | None = Field(default=None, gt=0)
    town_price_index_prior_year: float | None = Field(default=None, gt=0)
    county_price_index_current: float | None = Field(default=None, gt=0)
    county_price_index_prior_year: float | None = Field(default=None, gt=0)
    town_population_current: int | None = Field(default=None, gt=0)
    town_population_prior: int | None = Field(default=None, gt=0)
    county_population_current: int | None = Field(default=None, gt=0)
    county_population_prior: int | None = Field(default=None, gt=0)
    school_signal: float | None = Field(default=None, ge=0, le=10)
    flood_risk: str | None = Field(default=None, pattern="^(low|medium|high|none)$")
    liquidity_signal: str | None = Field(default=None, pattern="^(strong|normal|fragile)$")
    scarcity_signal: float | None = Field(default=None, ge=0, le=1)
    days_on_market: int | None = Field(default=None, ge=0)
    price_position: str | None = Field(default=None, pattern="^(supported|neutral|stretched)$")
    data_as_of: str | None = None
    source_names: dict[str, str] = Field(default_factory=dict)


class TownCountyNormalizedRecord(BaseModel):
    """Bridge output from source-backed records into deterministic scorer inputs."""

    model_config = ConfigDict(extra="forbid")

    inputs: TownCountyInputs
    field_status: list[SourceFieldStatus]
    missing_inputs: list[str]
    warnings: list[str]


class TownCountyScore(BaseModel):
    """Structured town/county thesis result with confidence and evidence gaps."""

    model_config = ConfigDict(extra="forbid")

    town_demand_score: float
    county_support_score: float | None
    market_alignment_score: float
    town_county_score: float
    location_thesis_label: str
    appreciation_support_view: str
    liquidity_view: str
    confidence: float
    demand_drivers: list[str]
    demand_risks: list[str]
    missing_inputs: list[str]
    assumptions_used: list[str]
    unsupported_claims: list[str]
    summary: str

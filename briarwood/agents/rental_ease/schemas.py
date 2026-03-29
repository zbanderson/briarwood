from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RentalEaseInput(BaseModel):
    """Normalized inputs for the rental ease agent."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    county: str | None = None
    estimated_monthly_rent: float | None = Field(default=None, ge=0)
    rent_source_type: str = Field(default="missing", pattern="^(provided|estimated|missing)$")
    gross_monthly_cost: float | None = Field(default=None, ge=0)
    carrying_cost_complete: bool = False
    financing_complete: bool = False
    income_support_ratio: float | None = Field(default=None, ge=0)
    price_to_rent: float | None = Field(default=None, ge=0)
    rent_support_classification: str | None = None
    monthly_cash_flow: float | None = None
    downside_burden: float | None = Field(default=None, ge=0)
    town_county_score: float | None = Field(default=None, ge=0, le=100)
    town_county_confidence: float | None = Field(default=None, ge=0, le=1)
    liquidity_view: str | None = Field(default=None, pattern="^(strong|normal|fragile)$")
    scarcity_support_score: float | None = Field(default=None, ge=0, le=100)
    scarcity_confidence: float | None = Field(default=None, ge=0, le=1)
    flood_risk: str | None = Field(default=None, pattern="^(low|medium|high|none)$")
    days_on_market: int | None = Field(default=None, ge=0)
    property_type: str | None = None
    beds: int | None = Field(default=None, ge=0)
    baths: float | None = Field(default=None, ge=0)
    sqft: int | None = Field(default=None, ge=0)
    zillow_rent_index_current: float | None = Field(default=None, gt=0)
    zillow_rent_index_prior_year: float | None = Field(default=None, gt=0)
    zillow_renter_demand_index: float | None = Field(default=None, ge=0, le=100)
    zillow_rent_forecast_one_year: float | None = None
    zillow_context_scope: str | None = Field(default=None, pattern="^(town|county)$")


class RentalEaseOutput(BaseModel):
    """Structured rental ease result for Briarwood."""

    model_config = ConfigDict(extra="forbid")

    rental_ease_score: float
    rental_ease_label: str
    liquidity_score: float
    demand_depth_score: float
    rent_support_score: float
    structural_support_score: float
    estimated_days_to_rent: int | None
    summary: str
    drivers: list[str]
    risks: list[str]
    confidence: float
    assumptions: list[str]
    unsupported_claims: list[str]
    warnings: list[str]
    zillow_context_used: bool = False

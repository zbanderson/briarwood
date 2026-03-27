from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from briarwood.agents.market_history.schemas import HistoricalValuePoint


class CurrentValueComponents(BaseModel):
    """Component values that may contribute to Briarwood Current Value."""

    model_config = ConfigDict(extra="forbid")

    market_adjusted_value: float | None = None
    backdated_listing_value: float | None = None
    income_supported_value: float | None = None


class CurrentValueWeights(BaseModel):
    """Normalized weights used to blend current-value components."""

    model_config = ConfigDict(extra="forbid")

    market_adjusted_weight: float = Field(ge=0)
    backdated_listing_weight: float = Field(ge=0)
    income_weight: float = Field(ge=0)


class CurrentValueInput(BaseModel):
    """Inputs required to estimate Briarwood Current Value."""

    model_config = ConfigDict(extra="forbid")

    ask_price: float = Field(gt=0)
    market_value_today: float | None = Field(default=None, gt=0)
    market_history_points: list[HistoricalValuePoint] = Field(default_factory=list)
    beds: int | None = Field(default=None, ge=0)
    baths: float | None = Field(default=None, ge=0)
    lot_size: float | None = Field(default=None, ge=0)
    property_type: str | None = None
    year_built: int | None = Field(default=None, ge=1800, le=2200)
    listing_date: str | None = None
    price_history: list[dict[str, object]] = Field(default_factory=list)
    days_on_market: int | None = Field(default=None, ge=0)
    effective_annual_rent: float | None = Field(default=None, ge=0)
    cap_rate_assumption: float = Field(gt=0.02, lt=0.15)


class CurrentValueOutput(BaseModel):
    """Structured Briarwood Current Value output."""

    model_config = ConfigDict(extra="forbid")

    ask_price: float
    briarwood_current_value: float
    value_low: float
    value_high: float
    mispricing_amount: float
    mispricing_pct: float
    pricing_view: str
    components: CurrentValueComponents
    weights: CurrentValueWeights
    confidence: float
    assumptions: list[str]
    unsupported_claims: list[str]
    warnings: list[str]

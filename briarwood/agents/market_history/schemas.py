from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HistoricalValuePoint(BaseModel):
    """A dated historical market value point."""

    model_config = ConfigDict(extra="forbid")

    date: str
    value: float = Field(gt=0)


class MarketValueHistoryRequest(BaseModel):
    """Request for source-backed market value history."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    county: str | None = None


class MarketValueHistoryOutput(BaseModel):
    """Structured market value history from Zillow-style historical data."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    geography_name: str
    geography_type: str
    points: list[HistoricalValuePoint]
    current_value: float | None
    one_year_change_pct: float | None
    three_year_change_pct: float | None
    confidence: float
    warnings: list[str]
    summary: str

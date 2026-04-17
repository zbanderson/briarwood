"""County-level macro context shared across specialty models.

The routed runner resolves this slice once per session and stores it on
``ExecutionContext.macro_context`` so specialty modules can consume the
same raw FRED indicators plus a set of dimensional signals without each
re-fetching or re-deriving them. All signals are normalized 0..1 to keep
the macro nudge comparable across modules.

Macro is intentionally subordinate: consumers should bound its effect on
their output confidence using ``apply_macro_nudge`` from
``briarwood.modules.macro_reader`` so town-specific and property-specific
evidence keeps dominating.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from briarwood.agents.town_county.providers import FileBackedFredMacroProvider
from briarwood.agents.town_county.sources import FredMacroAdapter, FredMacroSlice


_DEFAULT_FRED_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "town_county" / "fred_macro.json"
)


class MacroContextSlice(BaseModel):
    """Serializable county macro slice for scoped specialty modules."""

    model_config = ConfigDict(extra="forbid")

    county: str
    state: str
    as_of: str | None = None
    source_name: str = "fred_macro"

    unemployment_rate_current: float | None = None
    per_capita_income_current: float | None = None
    per_capita_income_prior: float | None = None
    house_price_index_current: float | None = None
    house_price_index_prior: float | None = None
    median_days_on_market_current: float | None = None
    median_days_on_market_yoy_pct: float | None = None

    employment_signal: float | None = Field(default=None, ge=0.0, le=1.0)
    income_growth_signal: float | None = Field(default=None, ge=0.0, le=1.0)
    hpi_momentum_signal: float | None = Field(default=None, ge=0.0, le=1.0)
    liquidity_signal: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_sentiment: float | None = Field(default=None, ge=0.0, le=1.0)


def derive_macro_slice(raw: FredMacroSlice, *, county: str, state: str) -> MacroContextSlice:
    """Project raw FRED indicators into the dimensional signals modules consume."""

    adapter = FredMacroAdapter()
    employment_signal = adapter._normalize_unemployment(raw.unemployment_rate_current)
    income_growth = adapter._percent_change(
        raw.per_capita_income_current, raw.per_capita_income_prior
    )
    income_growth_signal = adapter._normalize_income_growth(income_growth)
    hpi_growth = adapter._percent_change(
        raw.house_price_index_current, raw.house_price_index_prior
    )
    hpi_momentum_signal = adapter._normalize_hpi_growth(hpi_growth)
    liquidity_signal = adapter._normalize_days_on_market_change(
        raw.median_days_on_market_yoy_pct
    )
    overall_sentiment = adapter.derive_sentiment(raw)

    return MacroContextSlice(
        county=county,
        state=state,
        as_of=raw.as_of,
        source_name=raw.source_name,
        unemployment_rate_current=raw.unemployment_rate_current,
        per_capita_income_current=raw.per_capita_income_current,
        per_capita_income_prior=raw.per_capita_income_prior,
        house_price_index_current=raw.house_price_index_current,
        house_price_index_prior=raw.house_price_index_prior,
        median_days_on_market_current=raw.median_days_on_market_current,
        median_days_on_market_yoy_pct=raw.median_days_on_market_yoy_pct,
        employment_signal=employment_signal,
        income_growth_signal=income_growth_signal,
        hpi_momentum_signal=hpi_momentum_signal,
        liquidity_signal=liquidity_signal,
        overall_sentiment=overall_sentiment,
    )


def resolve_macro_context(
    *,
    county: str | None,
    state: str | None,
    provider: FileBackedFredMacroProvider | None = None,
) -> dict[str, Any] | None:
    """Look up a county's FRED slice and return it as a serializable dict.

    Returns ``None`` when county/state are missing or the provider has no
    matching row — scoped modules must treat an absent slice as "no macro
    signal" rather than a defaulted midpoint.
    """

    if not county or not state:
        return None

    if provider is None:
        if not _DEFAULT_FRED_PATH.exists():
            return None
        provider = FileBackedFredMacroProvider(_DEFAULT_FRED_PATH)
    row = provider.get_county_row(county=str(county), state=str(state))
    if not row:
        return None

    raw = FredMacroAdapter().from_row(row, geography_type="county")
    if raw is None:
        return None

    slice_ = derive_macro_slice(raw, county=str(county), state=str(state))
    return slice_.model_dump()


__all__ = [
    "MacroContextSlice",
    "derive_macro_slice",
    "resolve_macro_context",
]

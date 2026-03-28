from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.agents.town_county.schemas import TownCountySourceRecord


@dataclass(slots=True)
class ZillowTrendSlice:
    """Minimal normalized slice from a Zillow-style home value dataset."""

    geography_name: str
    geography_type: str
    current_value: float | None
    prior_year_value: float | None
    as_of: str | None = None
    source_name: str = "zillow_zhvi"


@dataclass(slots=True)
class CensusPopulationSlice:
    """Minimal normalized slice from a Census-style population dataset."""

    geography_name: str
    geography_type: str
    current_population: int | None
    prior_population: int | None
    as_of: str | None = None
    source_name: str = "census_population"


@dataclass(slots=True)
class FemaFloodSlice:
    """Minimal normalized slice from a FEMA-style hazard dataset."""

    geography_name: str
    geography_type: str
    flood_risk: str | None
    as_of: str | None = None
    source_name: str = "fema_nri"


@dataclass(slots=True)
class LiquiditySlice:
    """Minimal normalized slice from a market-activity dataset."""

    geography_name: str
    geography_type: str
    inventory_count: int | None
    monthly_sales_count: int | None
    months_of_supply: float | None
    as_of: str | None = None
    source_name: str = "market_liquidity_v1"


@dataclass(slots=True)
class FredMacroSlice:
    """Minimal normalized county macro slice backed by FRED-style series."""

    geography_name: str
    geography_type: str
    unemployment_rate_current: float | None
    per_capita_income_current: float | None
    per_capita_income_prior: float | None
    house_price_index_current: float | None
    house_price_index_prior: float | None
    median_days_on_market_current: float | None
    median_days_on_market_yoy_pct: float | None
    as_of: str | None = None
    source_name: str = "fred_macro"


@dataclass(slots=True)
class TownProfileSlice:
    """Town-specific qualitative profile turned into deterministic inputs."""

    geography_name: str
    geography_type: str
    coastal_profile_signal: float | None
    scarcity_signal: float | None
    as_of: str | None = None
    refresh_frequency_days: int | None = None
    source_name: str = "monmouth_coastal_profile_v1"


@dataclass(slots=True)
class TownCountyOutlookRequest:
    """Top-level identity and manually supplied context for location outlook assembly."""

    town: str
    state: str
    county: str | None = None
    school_signal: float | None = None
    scarcity_signal: float | None = None
    days_on_market: int | None = None
    price_position: str | None = None
    source_names: dict[str, str] = field(default_factory=dict)


class ZillowTrendAdapter:
    """Extract a consistent price trend slice from raw Zillow-like rows."""

    def from_row(
        self,
        row: dict[str, object],
        *,
        geography_name_key: str = "RegionName",
        current_value_key: str = "current_value",
        prior_year_value_key: str = "prior_year_value",
        as_of_key: str = "as_of",
        geography_type: str,
    ) -> ZillowTrendSlice:
        return ZillowTrendSlice(
            geography_name=str(row.get(geography_name_key, "")),
            geography_type=geography_type,
            current_value=self._to_float(row.get(current_value_key)),
            prior_year_value=self._to_float(row.get(prior_year_value_key)),
            as_of=self._to_str(row.get(as_of_key)),
        )

    def _to_float(self, value: object) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace(",", ""))

    def _to_str(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


class CensusPopulationAdapter:
    """Extract a consistent population slice from raw Census-like rows."""

    def from_row(
        self,
        row: dict[str, object],
        *,
        geography_name_key: str = "name",
        current_population_key: str = "current_population",
        prior_population_key: str = "prior_population",
        as_of_key: str = "as_of",
        geography_type: str,
    ) -> CensusPopulationSlice:
        return CensusPopulationSlice(
            geography_name=str(row.get(geography_name_key, "")),
            geography_type=geography_type,
            current_population=self._to_int(row.get(current_population_key)),
            prior_population=self._to_int(row.get(prior_population_key)),
            as_of=self._to_str(row.get(as_of_key)),
        )

    def _to_int(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return int(str(value).replace(",", ""))

    def _to_str(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


class FemaFloodAdapter:
    """Normalize FEMA-style flood records into Briarwood risk bands."""

    def from_row(
        self,
        row: dict[str, object],
        *,
        geography_name_key: str = "name",
        risk_key: str = "flood_risk",
        as_of_key: str = "as_of",
        geography_type: str,
    ) -> FemaFloodSlice:
        return FemaFloodSlice(
            geography_name=str(row.get(geography_name_key, "")),
            geography_type=geography_type,
            flood_risk=self._normalize_flood_risk(row.get(risk_key)),
            as_of=self._to_str(row.get(as_of_key)),
        )

    def _normalize_flood_risk(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        raw = str(value).strip().lower()
        mapping = {
            "very low": "low",
            "low": "low",
            "moderate": "medium",
            "medium": "medium",
            "relatively moderate": "medium",
            "high": "high",
            "very high": "high",
            "none": "none",
        }
        return mapping.get(raw)

    def _to_str(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


class LiquidityAdapter:
    """Extract a consistent liquidity slice from raw market-activity rows."""

    def from_row(
        self,
        row: dict[str, object],
        *,
        geography_name_key: str = "name",
        inventory_count_key: str = "inventory_count",
        monthly_sales_count_key: str = "monthly_sales_count",
        months_of_supply_key: str = "months_of_supply",
        as_of_key: str = "as_of",
        geography_type: str,
    ) -> LiquiditySlice:
        return LiquiditySlice(
            geography_name=str(row.get(geography_name_key, "")),
            geography_type=geography_type,
            inventory_count=self._to_int(row.get(inventory_count_key)),
            monthly_sales_count=self._to_int(row.get(monthly_sales_count_key)),
            months_of_supply=self._to_float(row.get(months_of_supply_key)),
            as_of=self._to_str(row.get(as_of_key)),
        )

    def derive_signal(self, slice_data: LiquiditySlice | None) -> str | None:
        if slice_data is None:
            return None

        months_of_supply = slice_data.months_of_supply
        if months_of_supply is None and slice_data.inventory_count and slice_data.monthly_sales_count:
            months_of_supply = slice_data.inventory_count / slice_data.monthly_sales_count

        if months_of_supply is None:
            return None
        if months_of_supply <= 3.0:
            return "strong"
        if months_of_supply <= 6.0:
            return "normal"
        return "fragile"

    def _to_int(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return int(str(value).replace(",", ""))

    def _to_float(self, value: object) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace(",", ""))

    def _to_str(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


class FredMacroAdapter:
    """Normalize FRED-style county macro rows into a sentiment-ready slice."""

    def from_row(
        self,
        row: dict[str, object],
        *,
        geography_name_key: str = "name",
        unemployment_rate_key: str = "unemployment_rate_current",
        pcpi_current_key: str = "per_capita_income_current",
        pcpi_prior_key: str = "per_capita_income_prior",
        hpi_current_key: str = "house_price_index_current",
        hpi_prior_key: str = "house_price_index_prior",
        median_dom_current_key: str = "median_days_on_market_current",
        median_dom_yoy_key: str = "median_days_on_market_yoy_pct",
        as_of_key: str = "as_of",
        geography_type: str,
    ) -> FredMacroSlice:
        return FredMacroSlice(
            geography_name=str(row.get(geography_name_key, "")),
            geography_type=geography_type,
            unemployment_rate_current=self._to_float(row.get(unemployment_rate_key)),
            per_capita_income_current=self._to_float(row.get(pcpi_current_key)),
            per_capita_income_prior=self._to_float(row.get(pcpi_prior_key)),
            house_price_index_current=self._to_float(row.get(hpi_current_key)),
            house_price_index_prior=self._to_float(row.get(hpi_prior_key)),
            median_days_on_market_current=self._to_float(row.get(median_dom_current_key)),
            median_days_on_market_yoy_pct=self._to_float(row.get(median_dom_yoy_key)),
            as_of=self._to_str(row.get(as_of_key)),
        )

    def derive_sentiment(self, slice_data: FredMacroSlice | None) -> float | None:
        if slice_data is None:
            return None

        unemployment_score = self._normalize_unemployment(slice_data.unemployment_rate_current)
        income_growth = self._percent_change(slice_data.per_capita_income_current, slice_data.per_capita_income_prior)
        income_score = self._normalize_income_growth(income_growth)
        hpi_growth = self._percent_change(slice_data.house_price_index_current, slice_data.house_price_index_prior)
        hpi_score = self._normalize_hpi_growth(hpi_growth)
        dom_yoy_score = self._normalize_days_on_market_change(slice_data.median_days_on_market_yoy_pct)

        components = [value for value in (unemployment_score, income_score, hpi_score, dom_yoy_score) if value is not None]
        if not components:
            return None

        weighted_score = (
            0.30 * (unemployment_score if unemployment_score is not None else 0.5)
            + 0.20 * (income_score if income_score is not None else 0.5)
            + 0.30 * (hpi_score if hpi_score is not None else 0.5)
            + 0.20 * (dom_yoy_score if dom_yoy_score is not None else 0.5)
        )
        return max(0.0, min(weighted_score, 1.0))

    def _normalize_unemployment(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 3.5:
            return 0.9
        if value <= 4.5:
            return 0.75
        if value <= 5.5:
            return 0.55
        if value <= 6.5:
            return 0.35
        return 0.15

    def _normalize_income_growth(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0.00:
            return 0.20
        if value <= 0.03:
            return 0.45
        if value <= 0.05:
            return 0.65
        if value <= 0.08:
            return 0.80
        return 0.92

    def _normalize_hpi_growth(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0.00:
            return 0.20
        if value <= 0.03:
            return 0.45
        if value <= 0.06:
            return 0.65
        if value <= 0.10:
            return 0.82
        return 0.92

    def _normalize_days_on_market_change(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= -0.08:
            return 0.88
        if value <= -0.02:
            return 0.75
        if value <= 0.03:
            return 0.55
        if value <= 0.08:
            return 0.35
        return 0.15

    def _percent_change(self, current: float | None, prior: float | None) -> float | None:
        if current is None or prior is None or prior == 0:
            return None
        return (current / prior) - 1

    def _to_float(self, value: object) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace(",", ""))

    def _to_str(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


class TownProfileAdapter:
    """Normalize fixed town-profile rows into explicit coastal support signals."""

    def from_row(
        self,
        row: dict[str, object],
        *,
        geography_name_key: str = "name",
        coastal_profile_signal_key: str = "coastal_profile_signal",
        scarcity_signal_key: str = "scarcity_signal",
        as_of_key: str = "as_of",
        refresh_frequency_days_key: str = "refresh_frequency_days",
        geography_type: str,
    ) -> TownProfileSlice:
        return TownProfileSlice(
            geography_name=str(row.get(geography_name_key, "")),
            geography_type=geography_type,
            coastal_profile_signal=self._to_float(row.get(coastal_profile_signal_key)),
            scarcity_signal=self._to_float(row.get(scarcity_signal_key)),
            as_of=self._to_str(row.get(as_of_key)),
            refresh_frequency_days=self._to_int(row.get(refresh_frequency_days_key)),
        )

    def _to_float(self, value: object) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value))

    def _to_int(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return int(str(value))

    def _to_str(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


class TownCountyOutlookBuilder:
    """Assemble source slices into a source record for the normalization bridge."""

    def build(
        self,
        request: TownCountyOutlookRequest,
        *,
        town_price: ZillowTrendSlice | None = None,
        county_price: ZillowTrendSlice | None = None,
        town_population: CensusPopulationSlice | None = None,
        county_population: CensusPopulationSlice | None = None,
        flood: FemaFloodSlice | None = None,
        liquidity: LiquiditySlice | None = None,
        fred_macro: FredMacroSlice | None = None,
        town_profile: TownProfileSlice | None = None,
    ) -> TownCountySourceRecord:
        source_names = dict(request.source_names)

        if town_price is not None:
            source_names.setdefault("town_price_trend", town_price.source_name)
        if county_price is not None:
            source_names.setdefault("county_price_trend", county_price.source_name)
        if town_population is not None:
            source_names.setdefault("town_population_trend", town_population.source_name)
        if county_population is not None:
            source_names.setdefault("county_population_trend", county_population.source_name)
        if fred_macro is not None:
            source_names.setdefault("county_macro_sentiment", fred_macro.source_name)
        if town_profile is not None and town_profile.coastal_profile_signal is not None:
            source_names.setdefault("coastal_profile_signal", town_profile.source_name)
        if request.school_signal is not None:
            source_names.setdefault("school_signal", "unknown_school_source")
        if flood is not None:
            source_names.setdefault("flood_risk", flood.source_name)
        if liquidity is not None:
            source_names.setdefault("liquidity_signal", liquidity.source_name)
        if request.scarcity_signal is not None:
            source_names.setdefault("scarcity_signal", "manual_briarwood_note")
        elif town_profile is not None and town_profile.scarcity_signal is not None:
            source_names.setdefault("scarcity_signal", town_profile.source_name)
        if request.days_on_market is not None:
            source_names.setdefault("days_on_market", "listing_intake")
        if request.price_position is not None:
            source_names.setdefault("price_position", "pricing_module_v1")

        data_as_of = self._latest_as_of(
            town_price.as_of if town_price else None,
            county_price.as_of if county_price else None,
            town_population.as_of if town_population else None,
            county_population.as_of if county_population else None,
            flood.as_of if flood else None,
            liquidity.as_of if liquidity else None,
            fred_macro.as_of if fred_macro else None,
            town_profile.as_of if town_profile else None,
        )

        return TownCountySourceRecord(
            town=request.town,
            state=request.state,
            county=request.county,
            town_price_index_current=town_price.current_value if town_price else None,
            town_price_index_prior_year=town_price.prior_year_value if town_price else None,
            county_price_index_current=county_price.current_value if county_price else None,
            county_price_index_prior_year=county_price.prior_year_value if county_price else None,
            town_population_current=town_population.current_population if town_population else None,
            town_population_prior=town_population.prior_population if town_population else None,
            county_population_current=county_population.current_population if county_population else None,
            county_population_prior=county_population.prior_population if county_population else None,
            county_macro_sentiment=FredMacroAdapter().derive_sentiment(fred_macro),
            coastal_profile_signal=town_profile.coastal_profile_signal if town_profile else None,
            school_signal=request.school_signal,
            flood_risk=flood.flood_risk if flood else None,
            liquidity_signal=LiquidityAdapter().derive_signal(liquidity),
            scarcity_signal=request.scarcity_signal
            if request.scarcity_signal is not None
            else (town_profile.scarcity_signal if town_profile else None),
            days_on_market=request.days_on_market,
            price_position=request.price_position,
            data_as_of=data_as_of,
            source_names=source_names,
        )

    def _latest_as_of(self, *values: str | None) -> str | None:
        present = [value for value in values if value is not None]
        if not present:
            return None
        return max(present)

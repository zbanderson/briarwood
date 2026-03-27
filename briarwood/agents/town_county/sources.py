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
        if request.school_signal is not None:
            source_names.setdefault("school_signal", "unknown_school_source")
        if flood is not None:
            source_names.setdefault("flood_risk", flood.source_name)
        if liquidity is not None:
            source_names.setdefault("liquidity_signal", liquidity.source_name)
        if request.scarcity_signal is not None:
            source_names.setdefault("scarcity_signal", "manual_briarwood_note")
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
            school_signal=request.school_signal,
            flood_risk=flood.flood_risk if flood else None,
            liquidity_signal=LiquidityAdapter().derive_signal(liquidity),
            scarcity_signal=request.scarcity_signal,
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

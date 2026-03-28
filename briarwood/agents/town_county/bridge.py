from __future__ import annotations

from briarwood.agents.town_county.schemas import (
    SourceFieldStatus,
    TownCountyInputs,
    TownCountyNormalizedRecord,
    TownCountySourceRecord,
)


class TownCountySourceBridge:
    """Normalize source-backed location records into scorer-ready inputs."""

    def normalize(self, payload: TownCountySourceRecord | dict[str, object]) -> TownCountyNormalizedRecord:
        record = payload if isinstance(payload, TownCountySourceRecord) else TownCountySourceRecord.model_validate(payload)

        field_status: list[SourceFieldStatus] = []
        warnings: list[str] = []

        town_price_trend = self._percent_change(record.town_price_index_current, record.town_price_index_prior_year)
        county_price_trend = self._percent_change(record.county_price_index_current, record.county_price_index_prior_year)
        town_population_trend = self._percent_change(record.town_population_current, record.town_population_prior)
        county_population_trend = self._percent_change(record.county_population_current, record.county_population_prior)

        if town_price_trend is not None:
            field_status.append(
                self._field_status(
                    field_name="town_price_trend",
                    record=record,
                    source_value=f"{town_price_trend:.4f}",
                    notes="Derived as trailing change from town price index values.",
                )
            )
        else:
            warnings.append("Town price trend could not be derived from the available source values.")

        if county_price_trend is not None:
            field_status.append(
                self._field_status(
                    field_name="county_price_trend",
                    record=record,
                    source_value=f"{county_price_trend:.4f}",
                    notes="Derived as trailing change from county price index values.",
                )
            )
        else:
            warnings.append("County price trend could not be derived from the available source values.")

        if town_population_trend is not None:
            field_status.append(
                self._field_status(
                    field_name="town_population_trend",
                    record=record,
                    source_value=f"{town_population_trend:.4f}",
                    notes="Derived as trailing change from town population values.",
                )
            )
        else:
            warnings.append("Town population trend could not be derived from the available source values.")

        if county_population_trend is not None:
            field_status.append(
                self._field_status(
                    field_name="county_population_trend",
                    record=record,
                    source_value=f"{county_population_trend:.4f}",
                    notes="Derived as trailing change from county population values.",
                )
            )
        else:
            warnings.append("County population trend could not be derived from the available source values.")

        direct_fields = {
            "county_macro_sentiment": record.county_macro_sentiment,
            "coastal_profile_signal": record.coastal_profile_signal,
            "school_signal": record.school_signal,
            "flood_risk": record.flood_risk,
            "liquidity_signal": record.liquidity_signal,
            "scarcity_signal": record.scarcity_signal,
            "days_on_market": record.days_on_market,
            "price_position": record.price_position,
        }
        for field_name, value in direct_fields.items():
            if value is not None:
                field_status.append(
                    self._field_status(
                        field_name=field_name,
                        record=record,
                        source_value=str(value),
                    )
                )

        inputs = TownCountyInputs(
            town=record.town,
            state=record.state,
            county=record.county,
            town_price_trend=town_price_trend,
            county_price_trend=county_price_trend,
            town_population_trend=town_population_trend,
            county_population_trend=county_population_trend,
            county_macro_sentiment=record.county_macro_sentiment,
            coastal_profile_signal=record.coastal_profile_signal,
            school_signal=record.school_signal,
            flood_risk=record.flood_risk,
            liquidity_signal=record.liquidity_signal,
            scarcity_signal=record.scarcity_signal,
            days_on_market=record.days_on_market,
            price_position=record.price_position,
            data_as_of=record.data_as_of,
        )

        missing_inputs = [
            field_name
            for field_name in (
                "town_price_trend",
                "county_price_trend",
                "town_population_trend",
                "county_population_trend",
                "county_macro_sentiment",
                "coastal_profile_signal",
                "school_signal",
                "flood_risk",
                "liquidity_signal",
                "scarcity_signal",
            )
            if getattr(inputs, field_name) is None
        ]

        if record.data_as_of is None:
            warnings.append("Location outlook record is missing an as-of date.")

        return TownCountyNormalizedRecord(
            inputs=inputs,
            field_status=field_status,
            missing_inputs=missing_inputs,
            warnings=warnings,
        )

    def _percent_change(self, current: float | int | None, prior: float | int | None) -> float | None:
        if current is None or prior is None or prior == 0:
            return None
        return (float(current) / float(prior)) - 1

    def _field_status(
        self,
        *,
        field_name: str,
        record: TownCountySourceRecord,
        source_value: str,
        notes: str | None = None,
    ) -> SourceFieldStatus:
        source_name = record.source_names.get(field_name, "unknown_source")
        source_type = self._source_type_for(field_name)
        return SourceFieldStatus(
            field_name=field_name,
            source_type=source_type,
            source_name=source_name,
            source_value=source_value,
            notes=notes,
        )

    def _source_type_for(self, field_name: str) -> str:
        if field_name in {
            "town_price_trend",
            "county_price_trend",
            "town_population_trend",
            "county_population_trend",
            "county_macro_sentiment",
            "school_signal",
            "flood_risk",
            "liquidity_signal",
        }:
            return "market_source"
        if field_name in {"days_on_market", "price_position"}:
            return "listing_source"
        if field_name in {"scarcity_signal", "coastal_profile_signal"}:
            return "derived"
        return "unknown"


def normalize_town_county_sources(payload: TownCountySourceRecord | dict[str, object]) -> TownCountyNormalizedRecord:
    """Convenience wrapper for source normalization."""

    return TownCountySourceBridge().normalize(payload)

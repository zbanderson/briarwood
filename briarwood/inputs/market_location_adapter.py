from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from briarwood.agents.market_history import FileBackedZillowHistoryProvider, MarketValueHistoryAgent, MarketValueHistoryRequest
from briarwood.agents.town_county.providers import FileBackedTownLandmarkProvider
from briarwood.agents.town_county.sources import TownCountyOutlookRequest
from briarwood.modules.location_context import build_default_town_county_service
from briarwood.schemas import (
    CanonicalPropertyData,
    InputCoverageStatus,
    MarketLocationSignals,
    SourceCoverageItem,
)


class MarketLocationAdapter:
    def __init__(
        self,
        *,
        town_county_service=None,
        market_history_agent: MarketValueHistoryAgent | None = None,
        landmark_provider: FileBackedTownLandmarkProvider | None = None,
    ) -> None:
        self.town_county_service = town_county_service or build_default_town_county_service()
        self.market_history_agent = market_history_agent or MarketValueHistoryAgent(
            FileBackedZillowHistoryProvider(
                Path(__file__).resolve().parents[2] / "data" / "market_history" / "zillow_zhvi_history.json"
            )
        )
        self.landmark_provider = landmark_provider or FileBackedTownLandmarkProvider(
            Path(__file__).resolve().parents[2] / "data" / "town_county" / "monmouth_landmark_points.json"
        )

    def enrich(self, canonical: CanonicalPropertyData) -> CanonicalPropertyData:
        facts = canonical.facts
        if not facts.town or not facts.state:
            return canonical

        outlook = self.town_county_service.build_outlook(
            TownCountyOutlookRequest(
                town=facts.town,
                state=facts.state,
                county=facts.county,
                school_signal=canonical.market_signals.school_rating,
                days_on_market=facts.days_on_market,
            )
        )
        history = self.market_history_agent.run(
            MarketValueHistoryRequest(town=facts.town, state=facts.state, county=facts.county)
        )
        landmark_row = self.landmark_provider.get_town_row(
            town=facts.town,
            state=facts.state,
            county=facts.county,
        )

        inputs = outlook.normalized.inputs
        curated_landmark_points = self._curated_landmark_points(landmark_row)
        merged_landmark_points = (
            canonical.market_signals.landmark_points
            if canonical.market_signals.landmark_points
            else curated_landmark_points
        )
        enriched_market_signals = replace(
            canonical.market_signals,
            town_population_trend=inputs.town_population_trend or canonical.market_signals.town_population_trend,
            town_price_trend=inputs.town_price_trend or canonical.market_signals.town_price_trend,
            county_price_trend=inputs.county_price_trend or canonical.market_signals.county_price_trend,
            county_population_trend=inputs.county_population_trend or canonical.market_signals.county_population_trend,
            county_macro_sentiment=inputs.county_macro_sentiment or canonical.market_signals.county_macro_sentiment,
            liquidity_signal=inputs.liquidity_signal or canonical.market_signals.liquidity_signal,
            scarcity_signal=inputs.scarcity_signal or canonical.market_signals.scarcity_signal,
            coastal_profile_signal=inputs.coastal_profile_signal or canonical.market_signals.coastal_profile_signal,
            school_rating=inputs.school_signal or canonical.market_signals.school_rating,
            flood_risk=inputs.flood_risk or canonical.market_signals.flood_risk,
            market_history_current_value=history.current_value or canonical.market_signals.market_history_current_value,
            market_history_one_year_change_pct=history.one_year_change_pct or canonical.market_signals.market_history_one_year_change_pct,
            market_history_three_year_change_pct=history.three_year_change_pct or canonical.market_signals.market_history_three_year_change_pct,
            market_history_geography_type=history.geography_type or canonical.market_signals.market_history_geography_type,
            market_history_as_of=(history.points[-1].date if history.points else canonical.market_signals.market_history_as_of),
            landmark_points=merged_landmark_points,
        )

        coverage = dict(canonical.source_metadata.source_coverage)
        field_source_map = {status.field_name: status for status in outlook.normalized.field_status}
        coverage["school_signal"] = self._coverage_from_outlook("school_signal", field_source_map.get("school_signal"), fallback_value=enriched_market_signals.school_rating)
        coverage["flood_risk"] = self._coverage_from_outlook("flood_risk", field_source_map.get("flood_risk"), fallback_value=enriched_market_signals.flood_risk)
        coverage["liquidity_signal"] = self._coverage_from_outlook("liquidity_signal", field_source_map.get("liquidity_signal"), fallback_value=enriched_market_signals.liquidity_signal)
        coverage["market_history"] = self._coverage_from_history(history)
        coverage["scarcity_inputs"] = self._scarcity_coverage(field_source_map, enriched_market_signals)
        coverage["landmark_points"] = self._landmark_coverage(landmark_row, enriched_market_signals.landmark_points)

        freshest = max(
            [value for value in [canonical.source_metadata.freshest_as_of, inputs.data_as_of, enriched_market_signals.market_history_as_of, self._landmark_as_of(landmark_row)] if value],
            default=None,
        )
        provenance = list(canonical.source_metadata.provenance)
        provenance.append("market_location_adapter")
        if landmark_row is not None:
            provenance.append("town_landmark_provider")
        return replace(
            canonical,
            market_signals=enriched_market_signals,
            source_metadata=replace(
                canonical.source_metadata,
                source_coverage=coverage,
                provenance=provenance,
                freshest_as_of=freshest,
            ),
        )

    def _coverage_from_outlook(self, category: str, field_status, *, fallback_value) -> SourceCoverageItem:
        if fallback_value is None:
            return SourceCoverageItem(category=category, status=InputCoverageStatus.MISSING)
        source_name = getattr(field_status, "source_name", None)
        note = getattr(field_status, "notes", None)
        return SourceCoverageItem(
            category=category,
            status=InputCoverageStatus.SOURCED,
            source_name=source_name,
            note=note,
        )

    def _coverage_from_history(self, history) -> SourceCoverageItem:
        if not history.points:
            return SourceCoverageItem(category="market_history", status=InputCoverageStatus.MISSING)
        freshness = history.points[-1].date if history.points else None
        return SourceCoverageItem(
            category="market_history",
            status=InputCoverageStatus.SOURCED,
            source_name=history.source_name,
            freshness=freshness,
            note=f"{history.geography_type}-level history",
        )

    def _scarcity_coverage(self, field_source_map: dict[str, object], market_signals: MarketLocationSignals) -> SourceCoverageItem:
        if market_signals.scarcity_signal is None and market_signals.coastal_profile_signal is None:
            return SourceCoverageItem(category="scarcity_inputs", status=InputCoverageStatus.MISSING)
        source_name = None
        notes: list[str] = []
        for field_name in ("scarcity_signal", "coastal_profile_signal"):
            status = field_source_map.get(field_name)
            if status is not None:
                source_name = source_name or getattr(status, "source_name", None)
                if getattr(status, "notes", None):
                    notes.append(getattr(status, "notes"))
        status_value = InputCoverageStatus.ESTIMATED if source_name == "manual_briarwood_note" else InputCoverageStatus.SOURCED
        return SourceCoverageItem(
            category="scarcity_inputs",
            status=status_value,
            source_name=source_name,
            note=" ".join(notes) if notes else "Derived from current location/scarcity source stack.",
        )

    def _curated_landmark_points(self, landmark_row: dict[str, object] | None) -> dict[str, list[dict[str, object]]]:
        if not isinstance(landmark_row, dict):
            return {}
        raw_points = landmark_row.get("landmark_points")
        if not isinstance(raw_points, dict):
            return {}
        curated: dict[str, list[dict[str, object]]] = {}
        for category, points in raw_points.items():
            if not isinstance(category, str) or not isinstance(points, list):
                continue
            valid_points = [point for point in points if isinstance(point, dict)]
            if valid_points:
                curated[category] = valid_points
        return curated

    def _landmark_coverage(
        self,
        landmark_row: dict[str, object] | None,
        landmark_points: dict[str, list[dict[str, object]]],
    ) -> SourceCoverageItem:
        if not landmark_points:
            return SourceCoverageItem(category="landmark_points", status=InputCoverageStatus.MISSING)
        return SourceCoverageItem(
            category="landmark_points",
            status=InputCoverageStatus.SOURCED if landmark_row is not None else InputCoverageStatus.USER_SUPPLIED,
            source_name=str(landmark_row.get("source_name")) if isinstance(landmark_row, dict) and landmark_row.get("source_name") else ("manual landmark entry" if landmark_points else None),
            freshness=self._landmark_as_of(landmark_row),
            note="Curated town landmark anchors are available for geo benchmarking."
            if landmark_row is not None
            else "Landmark anchors were supplied directly on the property input.",
        )

    def _landmark_as_of(self, landmark_row: dict[str, object] | None) -> str | None:
        if not isinstance(landmark_row, dict):
            return None
        value = landmark_row.get("as_of")
        return str(value) if value else None

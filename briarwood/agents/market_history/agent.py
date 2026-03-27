from __future__ import annotations

from typing import Protocol

from briarwood.agents.market_history.schemas import (
    HistoricalValuePoint,
    MarketValueHistoryOutput,
    MarketValueHistoryRequest,
)


class ZillowHistoryProvider(Protocol):
    """Protocol for a provider that can return Zillow-style historical market values."""

    def get_town_history(self, *, town: str, state: str) -> dict[str, object] | None:
        ...

    def get_county_history(self, *, county: str, state: str) -> dict[str, object] | None:
        ...


class MarketValueHistoryAgent:
    """Build market-level historical value context from Zillow-style history series.

    This agent is intentionally market-level, not property-level. Zillow Research's
    public ZHVI series is a strong source for town/county home value context, but it
    is not the same thing as a property's individual Zestimate history.
    """

    def __init__(self, provider: ZillowHistoryProvider) -> None:
        self.provider = provider

    def run(
        self,
        payload: MarketValueHistoryRequest | dict[str, object],
    ) -> MarketValueHistoryOutput:
        request = (
            payload
            if isinstance(payload, MarketValueHistoryRequest)
            else MarketValueHistoryRequest.model_validate(payload)
        )

        warnings: list[str] = []
        row = self.provider.get_town_history(town=request.town, state=request.state)
        geography_type = "town"
        geography_name = request.town

        if row is None and request.county:
            row = self.provider.get_county_history(county=request.county, state=request.state)
            geography_type = "county"
            geography_name = request.county
            warnings.append(
                "Town-level history was unavailable, so Briarwood fell back to county-level Zillow market history."
            )

        if row is None:
            warnings.append("No Zillow-style historical market value series was found for this geography.")
            return MarketValueHistoryOutput(
                source_name="zillow_zhvi",
                geography_name=geography_name,
                geography_type=geography_type,
                points=[],
                current_value=None,
                one_year_change_pct=None,
                three_year_change_pct=None,
                confidence=0.0,
                warnings=warnings,
                summary=(
                    f"Briarwood could not find a Zillow-style historical value series for {geography_name}, {request.state}."
                ),
            )

        points = self._parse_points(row.get("history"))
        current_value = points[-1].value if points else None
        one_year_change_pct = self._change_pct(points, years_back=1)
        three_year_change_pct = self._change_pct(points, years_back=3)
        confidence = 1.0 if geography_type == "town" else 0.8

        warnings.append(
            "This is market-level value context from Zillow-style history data, not a property-specific historical Zestimate."
        )
        summary = self._summary(
            geography_name=geography_name,
            state=request.state,
            geography_type=geography_type,
            one_year_change_pct=one_year_change_pct,
            three_year_change_pct=three_year_change_pct,
        )
        return MarketValueHistoryOutput(
            source_name="zillow_zhvi",
            geography_name=geography_name,
            geography_type=geography_type,
            points=points,
            current_value=current_value,
            one_year_change_pct=one_year_change_pct,
            three_year_change_pct=three_year_change_pct,
            confidence=confidence,
            warnings=warnings,
            summary=summary,
        )

    def _parse_points(self, raw_points: object) -> list[HistoricalValuePoint]:
        if not isinstance(raw_points, list):
            return []
        points: list[HistoricalValuePoint] = []
        for item in raw_points:
            if isinstance(item, dict):
                point = HistoricalValuePoint.model_validate(item)
                points.append(point)
        points.sort(key=lambda point: point.date)
        return points

    def _change_pct(self, points: list[HistoricalValuePoint], *, years_back: int) -> float | None:
        if len(points) <= years_back:
            return None
        current = points[-1].value
        prior = points[-(years_back + 1)].value
        if prior == 0:
            return None
        return round((current - prior) / prior, 4)

    def _summary(
        self,
        *,
        geography_name: str,
        state: str,
        geography_type: str,
        one_year_change_pct: float | None,
        three_year_change_pct: float | None,
    ) -> str:
        if one_year_change_pct is None and three_year_change_pct is None:
            return (
                f"Briarwood found only partial Zillow-style history for {geography_name}, {state}, so trend interpretation is limited."
            )
        one_year_text = "n/a" if one_year_change_pct is None else f"{one_year_change_pct:.1%}"
        three_year_text = "n/a" if three_year_change_pct is None else f"{three_year_change_pct:.1%}"
        return (
            f"Zillow-style {geography_type}-level home value history for {geography_name}, {state} shows "
            f"{one_year_text} change over 1 year and {three_year_text} over 3 years."
        )

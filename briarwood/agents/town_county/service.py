from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from briarwood.agents.town_county.bridge import TownCountySourceBridge
from briarwood.agents.town_county.scoring import TownCountyScorer
from briarwood.agents.town_county.schemas import TownCountyNormalizedRecord, TownCountyScore
from briarwood.agents.town_county.sources import (
    CensusPopulationAdapter,
    CensusPopulationSlice,
    FemaFloodAdapter,
    FemaFloodSlice,
    LiquidityAdapter,
    LiquiditySlice,
    TownCountyOutlookBuilder,
    TownCountyOutlookRequest,
    ZillowTrendAdapter,
    ZillowTrendSlice,
)


@dataclass(slots=True)
class TownCountyOutlookResult:
    """Full town/county outlook bundle from source acquisition through scoring."""

    normalized: TownCountyNormalizedRecord
    score: TownCountyScore


class PriceTrendProvider(Protocol):
    """Provide raw price-trend rows for town and county geographies."""

    def get_town_row(self, *, town: str, state: str) -> dict[str, object] | None:
        ...

    def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
        ...


class PopulationProvider(Protocol):
    """Provide raw population rows for town and county geographies."""

    def get_town_row(self, *, town: str, state: str) -> dict[str, object] | None:
        ...

    def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
        ...


class FloodRiskProvider(Protocol):
    """Provide a raw flood-risk row for the relevant geography."""

    def get_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        ...


class LiquidityProvider(Protocol):
    """Provide a raw market-activity row for the relevant geography."""

    def get_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        ...


class TownCountyDataService:
    """Orchestrate source providers, normalization, and scoring for location outlook."""

    _SOURCE_CONFIDENCE_WEIGHTS = {
        "town_price_trend": 0.20,
        "town_population_trend": 0.15,
        "school_signal": 0.20,
        "county_price_trend": 0.15,
        "county_population_trend": 0.10,
        "liquidity_signal": 0.10,
        "scarcity_signal": 0.05,
        "flood_risk": 0.05,
    }

    def __init__(
        self,
        *,
        price_provider: PriceTrendProvider | None = None,
        population_provider: PopulationProvider | None = None,
        flood_provider: FloodRiskProvider | None = None,
        liquidity_provider: LiquidityProvider | None = None,
        price_adapter: ZillowTrendAdapter | None = None,
        population_adapter: CensusPopulationAdapter | None = None,
        flood_adapter: FemaFloodAdapter | None = None,
        liquidity_adapter: LiquidityAdapter | None = None,
        builder: TownCountyOutlookBuilder | None = None,
        bridge: TownCountySourceBridge | None = None,
        scorer: TownCountyScorer | None = None,
    ) -> None:
        self.price_provider = price_provider
        self.population_provider = population_provider
        self.flood_provider = flood_provider
        self.liquidity_provider = liquidity_provider
        self.price_adapter = price_adapter or ZillowTrendAdapter()
        self.population_adapter = population_adapter or CensusPopulationAdapter()
        self.flood_adapter = flood_adapter or FemaFloodAdapter()
        self.liquidity_adapter = liquidity_adapter or LiquidityAdapter()
        self.builder = builder or TownCountyOutlookBuilder()
        self.bridge = bridge or TownCountySourceBridge()
        self.scorer = scorer or TownCountyScorer()

    def build_outlook(self, request: TownCountyOutlookRequest) -> TownCountyOutlookResult:
        town_price: ZillowTrendSlice | None = None
        county_price: ZillowTrendSlice | None = None
        town_population: CensusPopulationSlice | None = None
        county_population: CensusPopulationSlice | None = None
        flood: FemaFloodSlice | None = None
        liquidity: LiquiditySlice | None = None

        if self.price_provider is not None:
            town_row = self.price_provider.get_town_row(town=request.town, state=request.state)
            if town_row is not None:
                town_price = self.price_adapter.from_row(town_row, geography_type="town")

            if request.county:
                county_row = self.price_provider.get_county_row(county=request.county, state=request.state)
                if county_row is not None:
                    county_price = self.price_adapter.from_row(county_row, geography_type="county")

        if self.population_provider is not None:
            town_row = self.population_provider.get_town_row(town=request.town, state=request.state)
            if town_row is not None:
                town_population = self.population_adapter.from_row(town_row, geography_type="town")

            if request.county:
                county_row = self.population_provider.get_county_row(county=request.county, state=request.state)
                if county_row is not None:
                    county_population = self.population_adapter.from_row(county_row, geography_type="county")

        if self.flood_provider is not None:
            flood_row = self.flood_provider.get_row(town=request.town, state=request.state, county=request.county)
            if flood_row is not None:
                flood = self.flood_adapter.from_row(flood_row, geography_type="town")

        if self.liquidity_provider is not None:
            liquidity_row = self.liquidity_provider.get_row(town=request.town, state=request.state, county=request.county)
            if liquidity_row is not None:
                liquidity = self.liquidity_adapter.from_row(liquidity_row, geography_type="town")

        source_record = self.builder.build(
            request,
            town_price=town_price,
            county_price=county_price,
            town_population=town_population,
            county_population=county_population,
            flood=flood,
            liquidity=liquidity,
        )
        normalized = self.bridge.normalize(source_record)
        raw_score = self.scorer.score(normalized.inputs)
        source_confidence = self._source_confidence(normalized)
        assumptions_used = list(raw_score.assumptions_used)
        unsupported_claims = list(raw_score.unsupported_claims)

        source_notes = self._source_notes(normalized)
        assumptions_used.extend(note for note in source_notes if note not in assumptions_used)
        if source_confidence < raw_score.confidence:
            unsupported_claims.append("Confidence was reduced because some populated fields rely on weaker or manual sources.")

        final_confidence = min(raw_score.confidence, source_confidence)
        score = raw_score.model_copy(
            update={
                "confidence": round(final_confidence, 2),
                "assumptions_used": assumptions_used,
                "unsupported_claims": unsupported_claims,
                "summary": self._summary_with_confidence(raw_score.summary, final_confidence),
            }
        )
        return TownCountyOutlookResult(
            normalized=normalized,
            score=score,
        )

    def _source_confidence(self, normalized: TownCountyNormalizedRecord) -> float:
        field_status_map = {item.field_name: item for item in normalized.field_status}
        total_weight = sum(self._SOURCE_CONFIDENCE_WEIGHTS.values())
        weighted_quality = 0.0

        for field_name, weight in self._SOURCE_CONFIDENCE_WEIGHTS.items():
            status = field_status_map.get(field_name)
            if status is None:
                continue
            quality = self._source_quality(status.source_name, status.source_type, status.is_fallback)
            weighted_quality += weight * quality

        return weighted_quality / total_weight

    def _source_quality(self, source_name: str, source_type: str, is_fallback: bool) -> float:
        explicit_scores = {
            "zillow_zhvi": 1.00,
            "census_population": 1.00,
            "census_acs": 1.00,
            "fema_nri": 1.00,
            "district_signal_v1": 0.75,
            "greatschools": 0.75,
            "market_liquidity_v1": 0.70,
            "manual_briarwood_note": 0.55,
            "listing_intake": 0.85,
            "pricing_module_v1": 0.85,
            "unknown_school_source": 0.50,
            "unknown_liquidity_source": 0.50,
            "unknown_source": 0.50,
        }
        base_score = explicit_scores.get(source_name)
        if base_score is None:
            if source_type == "market_source":
                base_score = 0.70
            elif source_type == "listing_source":
                base_score = 0.80
            elif source_type == "derived":
                base_score = 0.60
            else:
                base_score = 0.50
        if is_fallback:
            return base_score * 0.85
        return base_score

    def _source_notes(self, normalized: TownCountyNormalizedRecord) -> list[str]:
        notes: list[str] = []
        for status in normalized.field_status:
            if status.source_name in {"unknown_school_source", "greatschools"}:
                notes.append("School signal is present, but currently comes from a non-official or placeholder source.")
            elif status.source_name in {"unknown_liquidity_source", "market_liquidity_v1"}:
                notes.append("Liquidity signal is currently model-derived rather than sourced from a dedicated market-activity dataset.")
            elif status.source_name == "manual_briarwood_note":
                notes.append("Scarcity signal is currently a manual Briarwood note, not a benchmarked supply model.")
        return notes

    def _summary_with_confidence(self, summary: str, confidence: float) -> str:
        if confidence >= 0.80:
            confidence_label = "moderate-to-high"
        elif confidence >= 0.60:
            confidence_label = "moderate"
        else:
            confidence_label = "low"
        return f"{summary} Current evidence confidence is {confidence_label}."

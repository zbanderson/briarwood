from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


MetricValue = float | int | str | bool | None


class EvidenceMode(str, Enum):
    PUBLIC_RECORD = "public_record"
    LISTING_ASSISTED = "listing_assisted"
    MLS_CONNECTED = "mls_connected"


class InputCoverageStatus(str, Enum):
    SOURCED = "sourced"
    USER_SUPPLIED = "user_supplied"
    ESTIMATED = "estimated"
    MISSING = "missing"


@dataclass(slots=True)
class SourceCoverageItem:
    category: str
    status: InputCoverageStatus
    source_name: str | None = None
    freshness: str | None = None
    note: str | None = None


@dataclass(slots=True)
class SectionEvidence:
    evidence_mode: EvidenceMode
    categories: list[SourceCoverageItem] = field(default_factory=list)
    major_missing_inputs: list[str] = field(default_factory=list)
    estimated_inputs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PropertyFacts:
    address: str
    town: str
    state: str
    county: str | None = None
    zip_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    beds: int | None = None
    baths: float | None = None
    sqft: int | None = None
    lot_size: float | None = None
    property_type: str | None = None
    architectural_style: str | None = None
    condition_profile: str | None = None
    capex_lane: str | None = None
    year_built: int | None = None
    stories: float | None = None
    garage_spaces: int | None = None
    garage_type: str | None = None
    has_detached_garage: bool | None = None
    has_back_house: bool | None = None
    adu_type: str | None = None
    adu_sqft: int | None = None
    has_basement: bool | None = None
    basement_finished: bool | None = None
    has_pool: bool | None = None
    parking_spaces: int | None = None
    corner_lot: bool | None = None
    driveway_off_street: bool | None = None
    purchase_price: float | None = None
    taxes: float | None = None
    monthly_hoa: float | None = None
    days_on_market: int | None = None
    listing_date: str | None = None
    listing_description: str | None = None
    price_history: list[dict[str, Any]] = field(default_factory=list)
    sale_history: list[dict[str, Any]] = field(default_factory=list)
    source_url: str | None = None


@dataclass(slots=True)
class MarketLocationSignals:
    town_population_trend: float | None = None
    town_price_trend: float | None = None
    county_price_trend: float | None = None
    county_population_trend: float | None = None
    county_macro_sentiment: float | None = None
    liquidity_signal: str | None = None
    scarcity_signal: float | None = None
    coastal_profile_signal: float | None = None
    market_history_current_value: float | None = None
    market_history_one_year_change_pct: float | None = None
    market_history_three_year_change_pct: float | None = None
    market_history_geography_type: str | None = None
    market_history_as_of: str | None = None
    school_rating: float | None = None
    flood_risk: str | None = None
    town_population: int | None = None
    market_price_to_rent_benchmark: float | None = None
    landmark_points: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    zone_flags: dict[str, bool | None] = field(default_factory=dict)
    local_documents: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class UserAssumptions:
    estimated_monthly_rent: float | None = None
    back_house_monthly_rent: float | None = None
    seasonal_monthly_rent: float | None = None
    unit_rents: list[float] = field(default_factory=list)
    insurance: float | None = None
    down_payment_percent: float | None = None
    interest_rate: float | None = None
    loan_term_years: int | None = None
    vacancy_rate: float | None = None
    monthly_maintenance_reserve_override: float | None = None
    condition_profile_override: str | None = None
    capex_lane_override: str | None = None
    repair_capex_budget: float | None = None
    manual_comp_inputs: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SourceMetadata:
    evidence_mode: EvidenceMode
    source_coverage: dict[str, SourceCoverageItem] = field(default_factory=dict)
    provenance: list[str] = field(default_factory=list)
    freshest_as_of: str | None = None


@dataclass(slots=True)
class CanonicalPropertyData:
    property_id: str
    facts: PropertyFacts
    market_signals: MarketLocationSignals = field(default_factory=MarketLocationSignals)
    user_assumptions: UserAssumptions = field(default_factory=UserAssumptions)
    source_metadata: SourceMetadata = field(
        default_factory=lambda: SourceMetadata(evidence_mode=EvidenceMode.PUBLIC_RECORD)
    )


@dataclass(slots=True)
class PropertyInput:
    property_id: str
    address: str
    town: str
    state: str
    beds: int
    baths: float
    sqft: int
    county: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    property_type: str | None = None
    architectural_style: str | None = None
    condition_profile: str | None = None
    capex_lane: str | None = None
    lot_size: float | None = None
    year_built: int | None = None
    stories: float | None = None
    garage_spaces: int | None = None
    garage_type: str | None = None
    has_detached_garage: bool | None = None
    has_back_house: bool | None = None
    adu_type: str | None = None
    adu_sqft: int | None = None
    has_basement: bool | None = None
    basement_finished: bool | None = None
    has_pool: bool | None = None
    parking_spaces: int | None = None
    corner_lot: bool | None = None
    driveway_off_street: bool | None = None
    purchase_price: float | None = None
    taxes: float | None = None
    insurance: float | None = None
    monthly_hoa: float | None = None
    estimated_monthly_rent: float | None = None
    back_house_monthly_rent: float | None = None
    seasonal_monthly_rent: float | None = None
    unit_rents: list[float] = field(default_factory=list)
    down_payment_percent: float | None = None
    interest_rate: float | None = None
    loan_term_years: int | None = None
    days_on_market: int | None = None
    listing_date: str | None = None
    listing_description: str | None = None
    source_url: str | None = None
    price_history: list[dict[str, Any]] = field(default_factory=list)
    vacancy_rate: float | None = None
    monthly_maintenance_reserve_override: float | None = None
    repair_capex_budget: float | None = None
    manual_comp_inputs: list[dict[str, Any]] = field(default_factory=list)
    town_population_trend: float | None = None
    town_price_trend: float | None = None
    school_rating: float | None = None
    flood_risk: str | None = None
    town_population: int | None = None
    market_price_to_rent_benchmark: float | None = None
    landmark_points: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    zone_flags: dict[str, bool | None] = field(default_factory=dict)
    local_documents: list[dict[str, Any]] = field(default_factory=list)
    renovation_scenario: dict[str, Any] | None = None
    teardown_scenario: dict[str, Any] | None = None
    facts: PropertyFacts | None = None
    market_signals: MarketLocationSignals | None = None
    user_assumptions: UserAssumptions | None = None
    source_metadata: SourceMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_canonical(cls, canonical: CanonicalPropertyData) -> "PropertyInput":
        facts = canonical.facts
        market = canonical.market_signals
        assumptions = canonical.user_assumptions
        return cls(
            property_id=canonical.property_id,
            address=facts.address,
            town=facts.town,
            state=facts.state,
            beds=facts.beds or 0,
            baths=facts.baths or 0.0,
            sqft=facts.sqft or 0,
            county=facts.county,
            latitude=facts.latitude,
            longitude=facts.longitude,
            property_type=facts.property_type,
            architectural_style=facts.architectural_style,
            condition_profile=assumptions.condition_profile_override or facts.condition_profile,
            capex_lane=assumptions.capex_lane_override or facts.capex_lane,
            lot_size=facts.lot_size,
            year_built=facts.year_built,
            stories=facts.stories,
            garage_spaces=facts.garage_spaces,
            garage_type=facts.garage_type,
            has_detached_garage=facts.has_detached_garage,
            has_back_house=facts.has_back_house,
            adu_type=facts.adu_type,
            adu_sqft=facts.adu_sqft,
            has_basement=facts.has_basement,
            basement_finished=facts.basement_finished,
            has_pool=facts.has_pool,
            parking_spaces=facts.parking_spaces,
            corner_lot=facts.corner_lot,
            driveway_off_street=facts.driveway_off_street,
            purchase_price=facts.purchase_price,
            taxes=facts.taxes,
            insurance=assumptions.insurance,
            monthly_hoa=facts.monthly_hoa,
            estimated_monthly_rent=assumptions.estimated_monthly_rent,
            back_house_monthly_rent=assumptions.back_house_monthly_rent,
            seasonal_monthly_rent=assumptions.seasonal_monthly_rent,
            unit_rents=list(assumptions.unit_rents),
            down_payment_percent=assumptions.down_payment_percent,
            interest_rate=assumptions.interest_rate,
            loan_term_years=assumptions.loan_term_years,
            days_on_market=facts.days_on_market,
            listing_date=facts.listing_date,
            listing_description=facts.listing_description,
            source_url=facts.source_url,
            price_history=facts.price_history,
            vacancy_rate=assumptions.vacancy_rate,
            monthly_maintenance_reserve_override=assumptions.monthly_maintenance_reserve_override,
            repair_capex_budget=assumptions.repair_capex_budget,
            manual_comp_inputs=assumptions.manual_comp_inputs,
            town_population_trend=market.town_population_trend,
            town_price_trend=market.town_price_trend,
            school_rating=market.school_rating,
            flood_risk=market.flood_risk,
            town_population=market.town_population,
            market_price_to_rent_benchmark=market.market_price_to_rent_benchmark,
            landmark_points=market.landmark_points,
            zone_flags=market.zone_flags,
            local_documents=market.local_documents,
            facts=facts,
            market_signals=market,
            user_assumptions=assumptions,
            source_metadata=canonical.source_metadata,
        )

    def coverage_for(self, category: str) -> SourceCoverageItem:
        if self.source_metadata and category in self.source_metadata.source_coverage:
            return self.source_metadata.source_coverage[category]
        return SourceCoverageItem(category=category, status=InputCoverageStatus.MISSING)


@dataclass(slots=True)
class ModuleResult:
    module_name: str
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    score: float = 0.0
    confidence: float = 0.0
    summary: str = ""
    payload: Any | None = None
    section_evidence: SectionEvidence | None = None


@dataclass(slots=True)
class ValuationOutput:
    purchase_price: float
    price_per_sqft: float | None
    monthly_rent: float | None
    rent_source_type: str
    carrying_cost_complete: bool
    financing_complete: bool
    effective_monthly_rent: float | None
    monthly_taxes: float
    monthly_insurance: float
    monthly_hoa: float
    monthly_maintenance_reserve: float
    monthly_mortgage_payment: float | None
    monthly_total_cost: float
    monthly_cash_flow: float | None
    annual_noi: float | None
    cap_rate: float | None
    gross_yield: float | None
    dscr: float | None
    cash_on_cash_return: float | None
    loan_amount: float | None
    down_payment_amount: float | None

    def to_metrics(self) -> dict[str, MetricValue]:
        return {
            "purchase_price": round(self.purchase_price, 2),
            "price_per_sqft": round(self.price_per_sqft, 2) if self.price_per_sqft is not None else None,
            "monthly_rent": round(self.monthly_rent, 2) if self.monthly_rent is not None else None,
            "rent_source_type": self.rent_source_type,
            "carrying_cost_complete": self.carrying_cost_complete,
            "financing_complete": self.financing_complete,
            "effective_monthly_rent": round(self.effective_monthly_rent, 2)
            if self.effective_monthly_rent is not None
            else None,
            "monthly_taxes": round(self.monthly_taxes, 2),
            "monthly_insurance": round(self.monthly_insurance, 2),
            "monthly_hoa": round(self.monthly_hoa, 2),
            "monthly_maintenance_reserve": round(self.monthly_maintenance_reserve, 2),
            "monthly_mortgage_payment": round(self.monthly_mortgage_payment, 2)
            if self.monthly_mortgage_payment is not None
            else None,
            "monthly_total_cost": round(self.monthly_total_cost, 2),
            "monthly_cash_flow": round(self.monthly_cash_flow, 2) if self.monthly_cash_flow is not None else None,
            "annual_noi": round(self.annual_noi, 2) if self.annual_noi is not None else None,
            "cap_rate": round(self.cap_rate, 4) if self.cap_rate is not None else None,
            "gross_yield": round(self.gross_yield, 4) if self.gross_yield is not None else None,
            "dscr": round(self.dscr, 2) if self.dscr is not None else None,
            "cash_on_cash_return": round(self.cash_on_cash_return, 4)
            if self.cash_on_cash_return is not None
            else None,
            "loan_amount": round(self.loan_amount, 2) if self.loan_amount is not None else None,
            "down_payment_amount": round(self.down_payment_amount, 2)
            if self.down_payment_amount is not None
            else None,
        }


@dataclass(slots=True)
class ScenarioOutput:
    ask_price: float
    bull_case_value: float
    base_case_value: float
    bear_case_value: float
    spread: float
    stress_case_value: float | None = None  # Historical peak-to-trough overlay; not a forecast

    def to_metrics(self) -> dict[str, MetricValue]:
        return {
            "ask_price": round(self.ask_price, 2),
            "bull_case_value": round(self.bull_case_value, 0),
            "base_case_value": round(self.base_case_value, 0),
            "bear_case_value": round(self.bear_case_value, 0),
            "spread": round(self.spread, 0),
            "stress_case_value": round(self.stress_case_value, 0) if self.stress_case_value is not None else None,
        }


@dataclass(slots=True)
class AnalysisReport:
    property_id: str
    address: str
    module_results: dict[str, ModuleResult] = field(default_factory=dict)
    property_input: PropertyInput | None = None

    def get_module(self, module_name: str) -> ModuleResult:
        return self.module_results[module_name]


@dataclass(slots=True)
class LocationBucketBenchmark:
    bucket_label: str
    median_ppsf: float | None = None
    median_price: float | None = None
    median_dom: float | None = None
    comp_count: int = 0


@dataclass(slots=True)
class LocationCategoryIntelligence:
    category: str
    subject_distance_miles: float | None = None
    subject_bucket: str | None = None
    peer_bucket_stats: LocationBucketBenchmark | None = None
    all_bucket_stats: list[LocationBucketBenchmark] = field(default_factory=list)
    town_median_ppsf: float | None = None
    town_median_price: float | None = None
    town_median_dom: float | None = None
    town_comp_count: int = 0
    location_premium_pct: float | None = None
    subject_relative_premium_pct: float | None = None


@dataclass(slots=True)
class LocationIntelligenceOutput:
    subject_ppsf: float | None
    location_score: float
    scarcity_score: float
    confidence: float
    primary_category: str | None = None
    location_premium_pct: float | None = None
    subject_relative_premium_pct: float | None = None
    narratives: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    zone_flags: dict[str, bool | None] = field(default_factory=dict)
    category_results: list[LocationCategoryIntelligence] = field(default_factory=list)


@dataclass(slots=True)
class LocalIntelligenceProject:
    name: str
    type: str | None = None
    units: int | None = None
    status: str | None = None
    location: str | None = None
    notes: str | None = None
    confidence: float = 0.0


@dataclass(slots=True)
class LocalIntelligenceSummary:
    total_projects: int = 0
    total_units: int = 0
    approved_projects: int = 0
    rejected_projects: int = 0
    pending_projects: int = 0


@dataclass(slots=True)
class LocalIntelligenceScores:
    development_activity_score: float = 0.0
    supply_pipeline_score: float = 0.0
    regulatory_trend_score: float = 0.0
    sentiment_score: float = 0.0


@dataclass(slots=True)
class LocalIntelligenceConfidence:
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LocalIntelligenceOutput:
    projects: list[LocalIntelligenceProject] = field(default_factory=list)
    summary: LocalIntelligenceSummary = field(default_factory=LocalIntelligenceSummary)
    scores: LocalIntelligenceScores = field(default_factory=LocalIntelligenceScores)
    narrative: list[str] = field(default_factory=list)
    confidence: LocalIntelligenceConfidence = field(default_factory=LocalIntelligenceConfidence)


@dataclass(slots=True)
class RelativeOpportunityProperty:
    property_id: str
    label: str
    subject_ppsf: float | None = None
    implied_ppsf: float | None = None
    relative_to_model_pct: float | None = None
    purchase_price: float | None = None
    capex: float | None = None
    post_reno_value: float | None = None
    town_momentum_score: float | None = None
    town_momentum_adjustment_pct: float | None = None
    forward_value: float | None = None
    expected_return_pct: float | None = None
    convergence_score: float | None = None
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RelativeOpportunityComparison:
    best_value_creation: str | None = None
    best_location: str | None = None
    best_forward_return: str | None = None
    highest_convergence: str | None = None


@dataclass(slots=True)
class RelativeOpportunityConfidence:
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RelativeOpportunityOutput:
    properties: list[RelativeOpportunityProperty] = field(default_factory=list)
    comparison: RelativeOpportunityComparison = field(default_factory=RelativeOpportunityComparison)
    winner: str | None = None
    reasoning: list[str] = field(default_factory=list)
    confidence: RelativeOpportunityConfidence = field(default_factory=RelativeOpportunityConfidence)


class AnalysisModule(Protocol):
    name: str

    def run(self, property_input: PropertyInput) -> ModuleResult:
        ...

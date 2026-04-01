from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SectionAssessment:
    score: float
    confidence: float
    summary: str


@dataclass(slots=True)
class HeaderSection:
    property_name: str
    address: str
    subtitle: str
    investment_stance: str


@dataclass(slots=True)
class ConclusionSection:
    verdict: str
    key_line: str
    ask_price: float
    briarwood_current_value: float
    bull_value: float
    bear_value: float
    premium_discount_to_ask: float
    value_range_low: float
    value_range_high: float
    pricing_view: str
    explanation: str
    cash_flow_text: str
    top_risk: str
    assessment: SectionAssessment
    why_it_matters: list[str] = field(default_factory=list)
    decision_fit: list[str] = field(default_factory=list)
    what_changes_call: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ThesisSection:
    title: str
    deal_type: str = ""
    must_go_right: list[str] = field(default_factory=list)
    what_breaks: list[str] = field(default_factory=list)
    so_what: list[str] = field(default_factory=list)
    assessment: SectionAssessment = field(
        default_factory=lambda: SectionAssessment(score=0.0, confidence=0.0, summary="")
    )


@dataclass(slots=True)
class MarketDurabilitySection:
    title: str
    summary: str
    confidence_line: str = ""
    supporting_points: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    assessment: SectionAssessment = field(
        default_factory=lambda: SectionAssessment(score=0.0, confidence=0.0, summary="")
    )


@dataclass(slots=True)
class CarrySupportSection:
    title: str
    summary: str
    market_absorption_label: str
    market_absorption_summary: str
    market_absorption_confidence: float
    rental_viability_label: str
    rental_viability_summary: str
    rental_viability_confidence: float
    rental_ease_score_text: str
    estimated_days_to_rent_text: str
    estimated_days_to_rent_context: str
    income_support_ratio_text: str
    estimated_cash_flow_text: str
    market_absorption_warnings: list[str] = field(default_factory=list)
    rental_viability_warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    assessment: SectionAssessment = field(
        default_factory=lambda: SectionAssessment(score=0.0, confidence=0.0, summary="")
    )


@dataclass(slots=True)
class ComparableCompCard:
    address: str
    sale_price_text: str
    adjusted_price_text: str
    sale_date_text: str
    fit_label: str
    source_text: str = ""
    micro_location_notes: list[str] = field(default_factory=list)
    why_comp: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ComparableSalesSection:
    title: str
    summary: str
    comparable_value_text: str
    confidence_text: str
    comp_count_text: str
    freshest_sale_text: str = ""
    median_sale_age_text: str = ""
    screening_summary: str = ""
    curation_summary: str = ""
    verification_summary: str = ""
    methodology_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    comps: list[ComparableCompCard] = field(default_factory=list)
    assessment: SectionAssessment = field(
        default_factory=lambda: SectionAssessment(score=0.0, confidence=0.0, summary="")
    )


@dataclass(slots=True)
class ScenarioPoint:
    label: str
    value: float


@dataclass(slots=True)
class ScenarioFanBand:
    label: str
    value: float


@dataclass(slots=True)
class ScenarioChartSection:
    chart_title: str
    secondary_chart_title: str
    current_ask: float
    current_value_label: str
    current_value: float
    market_reference_label: str
    market_reference_value: float
    forward_year_label: str
    forward_base_value: float
    fan_bands: list[ScenarioFanBand] = field(default_factory=list)
    points: list[ScenarioPoint] = field(default_factory=list)
    plot_html: str = ""
    secondary_plot_html: str = ""
    caption: str = ""


@dataclass(slots=True)
class ScenarioCase:
    name: str
    scenario_value: float
    implied_move_text: str = ""
    assumptions: list[str] = field(default_factory=list)
    key_drivers: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    assessment: SectionAssessment = field(
        default_factory=lambda: SectionAssessment(score=0.0, confidence=0.0, summary="")
    )


@dataclass(slots=True)
class BullBaseBearSection:
    bull_case: ScenarioCase
    base_case: ScenarioCase
    bear_case: ScenarioCase
    stress_case: ScenarioCase | None = None  # Tail-risk historical shock overlay; shown as a warning, not a forecast


@dataclass(slots=True)
class EvidenceStripSection:
    title: str
    evidence_mode_text: str
    overall_report_confidence_text: str
    value_confidence_text: str
    location_confidence_text: str
    rental_confidence_text: str
    scenario_confidence_text: str
    source_coverage_highlights: list[str] = field(default_factory=list)
    major_missing_inputs: list[str] = field(default_factory=list)
    estimated_inputs: list[str] = field(default_factory=list)
    modeled_fields: list[str] = field(default_factory=list)
    non_modeled_fields: list[str] = field(default_factory=list)
    strongest_evidence: list[str] = field(default_factory=list)
    weaker_evidence: list[str] = field(default_factory=list)
    heuristic_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SignalMetric:
    label: str
    value_text: str          # Formatted for display (e.g., "22.4", "$48K (+6.9%)")
    classification: str      # One-word context (e.g., "Expensive", "Meaningful", "Positive")
    context: str             # One sentence explaining what it means


@dataclass(slots=True)
class SignalMetricsSection:
    price_to_rent: SignalMetric | None
    scarcity: SignalMetric | None
    forward_gap: SignalMetric | None
    liquidity: SignalMetric | None
    optionality: SignalMetric | None


@dataclass(slots=True)
class RenovationScenarioSummary:
    renovation_budget: float
    current_bcv: float
    renovated_bcv: float
    gross_value_creation: float
    net_value_creation: float
    roi_pct: float
    cost_per_dollar_of_value: float | None
    condition_change: str
    sqft_change: str | None
    summary: str
    confidence: float
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TeardownPhase1Summary:
    hold_years: int
    total_gross_rent: float
    total_net_cash_flow: float
    burn_down_pct: float
    effective_cost_basis: float
    equity_at_teardown: float
    mortgage_balance_at_teardown: float
    estimated_property_value_at_teardown: float
    narrative: str
    year_by_year: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class TeardownPhase2Summary:
    demolition_cost: float
    construction_cost: float
    lost_rent_during_construction: float
    total_phase2_cost: float
    estimated_new_construction_value: float
    comp_basis: str
    narrative: str


@dataclass(slots=True)
class TeardownProjectTotals:
    total_cash_invested: float
    total_rental_income: float
    final_property_value: float
    final_mortgage_balance: float
    net_equity_position: float
    total_profit: float
    total_roi_pct: float
    annualized_roi_pct: float
    total_timeline_years: float
    narrative: str


@dataclass(slots=True)
class TeardownScenarioSummary:
    hold_years: int
    phase1: TeardownPhase1Summary
    phase2: TeardownPhase2Summary
    project_totals: TeardownProjectTotals
    confidence: float
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InvestmentScenariosSection:
    renovation: RenovationScenarioSummary | None = None
    teardown: TeardownScenarioSummary | None = None


@dataclass(slots=True)
class TearSheet:
    property_id: str
    header: HeaderSection
    conclusion: ConclusionSection
    signal_metrics: SignalMetricsSection
    thesis: ThesisSection
    market_durability: MarketDurabilitySection
    carry_support: CarrySupportSection
    comparable_sales: ComparableSalesSection
    scenario_chart: ScenarioChartSection
    bull_base_bear: BullBaseBearSection
    evidence_strip: EvidenceStripSection
    investment_scenarios: InvestmentScenariosSection | None = None

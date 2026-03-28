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
    ask_price: float
    briarwood_current_value: float
    bull_value: float
    bear_value: float
    premium_discount_to_ask: float
    value_range_low: float
    value_range_high: float
    pricing_view: str
    explanation: str
    assessment: SectionAssessment


@dataclass(slots=True)
class ThesisSection:
    title: str
    bullets: list[str] = field(default_factory=list)
    assessment: SectionAssessment = field(
        default_factory=lambda: SectionAssessment(score=0.0, confidence=0.0, summary="")
    )


@dataclass(slots=True)
class MarketDurabilitySection:
    title: str
    summary: str
    buyer_takeaway: str = ""
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
    support_label: str
    income_support_ratio_text: str
    estimated_cash_flow_text: str
    warnings: list[str] = field(default_factory=list)
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


@dataclass(slots=True)
class TearSheet:
    property_id: str
    header: HeaderSection
    conclusion: ConclusionSection
    thesis: ThesisSection
    market_durability: MarketDurabilitySection
    carry_support: CarrySupportSection
    scenario_chart: ScenarioChartSection
    bull_base_bear: BullBaseBearSection

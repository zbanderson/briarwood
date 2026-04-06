from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from briarwood.agents.comparable_sales.store import JsonActiveListingStore
from briarwood.evidence import (
    compute_confidence_breakdown,
    compute_critical_assumption_statuses,
    compute_metric_input_statuses,
)
from briarwood.modules.town_aggregation_diagnostics import get_town_context
from briarwood.reports.section_helpers import (
    get_comparable_sales,
    get_current_value,
    get_income_support,
    get_rental_ease,
    get_scarcity_support,
    get_scenario_output,
    get_town_county_outlook,
)
from briarwood.reports.sections.conclusion_section import build_conclusion_section
from briarwood.reports.sections.thesis_section import build_thesis_section
from briarwood.schemas import AnalysisReport, InputCoverageStatus, PropertyInput, SectionEvidence

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_LISTINGS_PATH = ROOT / "data" / "comps" / "active_listings.json"


def _fmt_currency(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"${value:,.0f}"


def _fmt_currency_delta(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.0f}"


def _fmt_pct(value: float | None, *, scale_100: bool = True) -> str:
    if value is None:
        return "Unavailable"
    pct = value * 100 if scale_100 else value
    return f"{pct:.1f}%"


def _fmt_number(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}{suffix}"
    return f"{int(value):,}{suffix}"


def _scenario_stress_value(scenario: object) -> float | None:
    return getattr(scenario, "stress_case_value", None)


def _income_attr(income: object, name: str, default=None):
    return getattr(income, name, default)


def _income_list(income: object, name: str) -> list[float]:
    value = getattr(income, name, None)
    return value if isinstance(value, list) else []


def _cost_val_metric(report: AnalysisReport, key: str) -> float | None:
    """Extract a metric from the cost_valuation module result."""
    mod = report.module_results.get("cost_valuation")
    if mod is None:
        return None
    val = mod.metrics.get(key)
    return float(val) if val is not None else None


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value:.2f}x"


def _rent_source_label(source_type: str) -> str:
    """Human-readable label for rent provenance (for trust calibration)."""
    mapping = {
        "manual_input": "(user provided)",
        "provided": "(user provided)",
        "estimated": "(estimated)",
        "missing": "(missing — using fallback)",
    }
    return mapping.get(source_type, "")


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coastal_profile_label(town_county: object) -> str:
    """Derive a coastal profile tag from the town_county outlook."""
    normalized = getattr(town_county, "normalized", None)
    if normalized is None:
        return ""
    inputs = getattr(normalized, "inputs", None)
    if inputs is None:
        return ""
    signal = getattr(inputs, "coastal_profile_signal", None)
    if signal is None or signal <= 0:
        return ""
    if signal >= 0.8:
        return "Beach Premium"
    if signal >= 0.5:
        return "Downtown Premium"
    return "Coastal"


def _module_confidence(report: AnalysisReport, module_name: str) -> float | None:
    module = report.module_results.get(module_name)
    return None if module is None else float(module.confidence)


def _safe_ratio(value: float | None, baseline: float | None) -> float | None:
    if value in (None, 0) or baseline in (None, 0):
        return None
    return round(float(value) / float(baseline), 3)


def _town_relative_opportunity_score(
    *,
    subject_ppsf_vs_town: float | None,
    subject_price_vs_town: float | None,
    town_context_confidence: float | None,
) -> float | None:
    scores: list[float] = []
    if subject_ppsf_vs_town is not None:
        if subject_ppsf_vs_town <= 0.85:
            scores.append(4.8)
        elif subject_ppsf_vs_town <= 0.95:
            scores.append(4.1)
        elif subject_ppsf_vs_town <= 1.05:
            scores.append(3.0)
        elif subject_ppsf_vs_town <= 1.15:
            scores.append(2.1)
        else:
            scores.append(1.3)
    if subject_price_vs_town is not None:
        if subject_price_vs_town <= 0.85:
            scores.append(4.4)
        elif subject_price_vs_town <= 0.95:
            scores.append(3.8)
        elif subject_price_vs_town <= 1.05:
            scores.append(3.0)
        elif subject_price_vs_town <= 1.15:
            scores.append(2.3)
        else:
            scores.append(1.5)
    if not scores:
        return None
    raw_score = sum(scores) / len(scores)
    confidence = town_context_confidence if town_context_confidence is not None else 0.0
    shrunk = 3.0 + (raw_score - 3.0) * max(0.25, min(confidence, 1.0))
    return round(shrunk, 2)


def _liquidity_metrics(report: AnalysisReport) -> tuple[dict[str, Any], list[str], list[str]]:
    module = report.module_results.get("liquidity_signal")
    if module is not None:
        payload = module.payload
        supporting = list(getattr(payload, "supporting_evidence", [])) if payload is not None else []
        unsupported = list(getattr(payload, "unsupported_claims", [])) if payload is not None else []
        return module.metrics, supporting, unsupported

    property_input = report.property_input
    rental_ease = report.module_results.get("rental_ease")
    town = report.module_results.get("town_county_outlook")
    comparable_sales = report.module_results.get("comparable_sales")
    dom = property_input.days_on_market if property_input else None
    rental_score = None if rental_ease is None else rental_ease.metrics.get("liquidity_score")
    market_view = None if town is None else town.metrics.get("liquidity_view")
    score = rental_score or (82.0 if dom is not None and dom <= 21 else 62.0 if dom is not None and dom <= 45 else 42.0 if dom is not None else 50.0)
    label = (
        "Strong Exit Liquidity" if float(score) >= 78 else
        "Normal Exit Liquidity" if float(score) >= 62 else
        "Mixed Exit Liquidity" if float(score) >= 45 else
        "Thin Exit Liquidity"
    )
    supporting = []
    if dom is not None:
        supporting.append(f"{dom} DOM is being used as the primary legacy liquidity proxy.")
    if market_view:
        supporting.append(f"Town/county liquidity backdrop reads {str(market_view).replace('_', ' ')}.")
    unsupported = ["Canonical liquidity was backfilled from older report outputs because this report predates the dedicated liquidity module."]
    return {
        "liquidity_score": score,
        "liquidity_label": label,
        "market_liquidity_view": market_view,
    }, supporting, unsupported


def _market_momentum_metrics(report: AnalysisReport) -> tuple[dict[str, Any], list[str], list[str]]:
    module = report.module_results.get("market_momentum_signal")
    if module is not None:
        payload = module.payload
        drivers = list(getattr(payload, "drivers", [])) if payload is not None else []
        unsupported = list(getattr(payload, "unsupported_claims", [])) if payload is not None else []
        return module.metrics, drivers, unsupported

    history = report.module_results.get("market_value_history")
    town = report.module_results.get("town_county_outlook")
    local = report.module_results.get("local_intelligence")
    one_year = None if history is None else history.metrics.get("one_year_change_pct")
    town_score = None if town is None else town.metrics.get("town_county_score")
    dev = None if local is None else local.metrics.get("development_activity_score")
    base = 50.0
    if isinstance(town_score, (int, float)):
        base = 0.6 * float(town_score) + 0.4 * base
    if isinstance(one_year, (int, float)):
        base += max(-12.0, min(float(one_year) * 250.0, 12.0))
    if isinstance(dev, (int, float)) and dev >= 65:
        base += 5.0
    score = round(max(0.0, min(base, 100.0)), 1)
    label = (
        "Supportive Momentum" if score >= 72 else
        "Constructive Momentum" if score >= 58 else
        "Mixed Momentum" if score >= 45 else
        "Weak Momentum"
    )
    drivers = []
    if isinstance(one_year, (int, float)):
        drivers.append(
            "positive recent price trend" if float(one_year) >= 0.03 else
            "negative recent price trend" if float(one_year) <= -0.02 else
            "flat recent price trend"
        )
    if isinstance(dev, (int, float)) and dev >= 65:
        drivers.append("active redevelopment pipeline")
    unsupported = ["Canonical market momentum was backfilled from older report outputs because this report predates the dedicated momentum module."]
    return {
        "market_momentum_score": score,
        "market_momentum_label": label,
    }, drivers, unsupported


def _coverage_status_label(status: InputCoverageStatus) -> str:
    return status.value.replace("_", " ").title()


@dataclass(slots=True)
class MetricChip:
    label: str
    value: str
    tone: str = "neutral"
    subtitle: str = ""


@dataclass(slots=True)
class SectionConfidenceItem:
    label: str
    confidence: float


@dataclass(slots=True)
class ConfidenceFactorItem:
    """One factor contributing to the global confidence level."""
    label: str
    detail: str
    level: str  # "strong", "ok", "weak"


@dataclass(slots=True)
class InputImpactItem:
    """A missing input and the confidence improvement it would yield."""
    field_label: str
    impact_description: str
    affected_component: str


@dataclass(slots=True)
class ConfidenceComponentItem:
    key: str
    label: str
    confidence: float
    weight: float
    reason: str


@dataclass(slots=True)
class AssumptionTransparencyItem:
    label: str
    value: str
    source_kind: str
    source_label: str
    note: str = ""


@dataclass(slots=True)
class AssumptionStatusItem:
    key: str
    label: str
    status: str
    value: str
    source_label: str
    note: str = ""
    affected_components: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MetricInputStatusItem:
    key: str
    label: str
    status: str
    facts_used: list[str] = field(default_factory=list)
    user_inputs_used: list[str] = field(default_factory=list)
    assumptions_used: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    confidence_impact: str = ""
    prompt_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceViewModel:
    evidence_mode: str
    sourced_inputs: list[str] = field(default_factory=list)
    user_supplied_inputs: list[str] = field(default_factory=list)
    estimated_inputs: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    confidence_components: list[ConfidenceComponentItem] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    assumption_statuses: list[AssumptionStatusItem] = field(default_factory=list)
    transparency_items: list[AssumptionTransparencyItem] = field(default_factory=list)
    metric_statuses: list[MetricInputStatusItem] = field(default_factory=list)
    gap_prompt_fields: list[str] = field(default_factory=list)
    section_confidences: list[SectionConfidenceItem] = field(default_factory=list)


@dataclass(slots=True)
class ValueViewModel:
    component_rows: list[tuple[str, str, str]] = field(default_factory=list)
    pricing_view: str = ""
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass(slots=True)
class RiskLocationViewModel:
    risk_summary: str
    risk_score: float
    town_score: float
    town_label: str
    scarcity_score: float
    liquidity_score: float
    liquidity_label: str
    market_momentum_score: float
    market_momentum_label: str
    flood_risk: str
    liquidity_view: str
    # Surfaced risk/market signals (Group 2)
    stress_case_value: float | None = None
    stress_case_text: str = "Unavailable"
    stress_drawdown_pct: float | None = None
    momentum_direction: str = ""  # "accelerating" / "steady" / "decelerating"
    # Location context (Group 3)
    school_signal: float | None = None
    school_signal_text: str = ""
    coastal_profile_label: str = ""  # "Beach Premium", "Downtown Premium", or ""
    # Scarcity breakdown (Group 5)
    land_scarcity_score: float | None = None
    location_scarcity_score: float | None = None
    drivers: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ForwardViewModel:
    summary: str
    confidence: float
    bull_value_text: str
    base_value_text: str
    bear_value_text: str
    stress_case_value_text: str
    upside_pct_text: str
    downside_pct_text: str
    market_drift_text: str
    location_premium_text: str
    risk_discount_text: str
    optionality_premium_text: str


@dataclass(slots=True)
class IncomeSupportViewModel:
    summary: str
    confidence: float
    rental_ease_label: str
    estimated_days_to_rent_text: str
    total_rent_text: str
    num_units_text: str
    avg_rent_per_unit_text: str
    income_support_ratio_text: str
    monthly_cash_flow_text: str
    operating_cash_flow_text: str
    rent_source_type: str
    risk_view: str
    price_to_rent_text: str
    ptr_classification: str
    # Surfaced investor metrics (Group 1)
    dscr: float | None = None
    dscr_text: str = "Unavailable"
    cash_on_cash_return: float | None = None
    cash_on_cash_return_text: str = "Unavailable"
    gross_yield: float | None = None
    gross_yield_text: str = "Unavailable"
    # Rent source label for trust calibration (Group 4, item 9)
    rent_source_label: str = ""
    unit_breakdown: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompareMetricRow:
    metric: str
    values: dict[str, str]
    raw_values: dict[str, float | None] = field(default_factory=dict)
    deltas: dict[str, str] = field(default_factory=dict)  # label → "+$50K (+6.3%)"
    winner: str = ""  # label of the winning property for this metric
    higher_is_better: bool = True


@dataclass(slots=True)
class CompReviewRow:
    address: str
    sale_price: str
    adjusted_price: str
    fit: str
    status: str
    verification: str
    condition: str
    capex_lane: str
    source_ref: str
    why_comp: str
    cautions: str


@dataclass(slots=True)
class ActiveListingViewRow:
    address: str
    list_price: str
    status: str
    beds: str
    baths: str
    sqft: str
    dom: str
    condition: str
    source_ref: str


@dataclass(slots=True)
class CompsViewModel:
    comparable_value_text: str
    comp_count_text: str
    confidence_text: str
    active_listing_count_text: str
    dataset_name: str
    verification_summary: str
    curation_summary: str
    screening_summary: str
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    rows: list[CompReviewRow] = field(default_factory=list)
    active_listing_rows: list[ActiveListingViewRow] = field(default_factory=list)


@dataclass(slots=True)
class DecisionViewModel:
    recommendation: str
    conviction_score: int
    best_fit: str
    confidence_level: str
    thesis: str
    decisive_driver: str
    break_condition: str
    required_belief: str
    primary_risk: str
    what_changes_view: str
    primary_driver: str
    fit_context: str = ""
    supporting_factors: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    disqualifiers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PropertyAnalysisView:
    property_id: str
    label: str
    address: str
    evidence_mode: str
    condition_profile: str
    capex_lane: str
    overall_confidence: float
    ask_price: float | None
    bcv: float | None
    value_low: float | None
    value_high: float | None
    base_case: float | None
    bull_case: float | None
    bear_case: float | None
    stress_case: float | None
    mispricing_amount: float | None
    mispricing_pct: float | None
    all_in_basis: float | None
    capex_basis_used: float | None
    capex_basis_source: str
    net_opportunity_delta_value: float | None
    net_opportunity_delta_pct: float | None
    pricing_view: str
    memo_verdict: str
    biggest_risk: str
    buyer_fit: list[str]
    top_reasons: list[str]
    what_changes_call: list[str]
    memo_summary: str
    top_positives: list[str]
    top_risks: list[str]
    metric_chips: list[MetricChip]
    value: ValueViewModel
    comps: CompsViewModel
    forward: ForwardViewModel
    income_support: IncomeSupportViewModel
    risk_location: RiskLocationViewModel
    evidence: EvidenceViewModel
    decision: DecisionViewModel | None = None
    town_context: dict[str, Any] = field(default_factory=dict)
    compare_metrics: dict[str, Any] = field(default_factory=dict)
    # Defaults transparency
    defaults_applied: dict[str, str] = field(default_factory=dict)
    geocoded: bool = False
    # Scoring layer
    final_score: float | None = None
    recommendation_tier: str | None = None
    recommendation_action: str | None = None
    score_narrative: str | None = None
    category_scores: Any | None = None  # dict[str, CategoryScore] from engine
    lens_scores: Any | None = None  # LensScores from decision_model
    # Confidence layer
    confidence_level: str = "Estimated"  # "Grounded", "Estimated", "Provisional"
    confidence_factors: list[ConfidenceFactorItem] = field(default_factory=list)
    top_input_impacts: list[InputImpactItem] = field(default_factory=list)


def _coverage_lists(property_input: PropertyInput | None) -> tuple[list[str], list[str], list[str], list[str]]:
    if property_input is None or property_input.source_metadata is None:
        return [], [], [], []
    sourced: list[str] = []
    user_supplied: list[str] = []
    estimated: list[str] = []
    missing: list[str] = []
    for key, item in property_input.source_metadata.source_coverage.items():
        label = key.replace("_", " ")
        if item.status is InputCoverageStatus.SOURCED:
            sourced.append(label)
        elif item.status is InputCoverageStatus.USER_SUPPLIED:
            user_supplied.append(label)
        elif item.status is InputCoverageStatus.ESTIMATED:
            estimated.append(label)
        else:
            missing.append(label)
    return sorted(sourced), sorted(user_supplied), sorted(estimated), sorted(missing)


def _collect_unsupported_claims(report: AnalysisReport) -> list[str]:
    claims: list[str] = []
    for module in report.module_results.values():
        payload = module.payload
        if hasattr(payload, "unsupported_claims"):
            for claim in getattr(payload, "unsupported_claims"):
                if claim not in claims:
                    claims.append(claim)
    return claims


def _section_confidences(report: AnalysisReport) -> list[SectionConfidenceItem]:
    labels = {
        "current_value": "Value",
        "bull_base_bear": "Forward",
        "income_support": "Income",
        "rental_ease": "Rental",
        "town_county_outlook": "Location",
        "scarcity_support": "Scarcity",
        "comparable_sales": "Comps",
    }
    items: list[SectionConfidenceItem] = []
    for module_name, label in labels.items():
        module = report.module_results.get(module_name)
        if module is None:
            continue
        items.append(SectionConfidenceItem(label=label, confidence=float(module.confidence)))
    return items


def _compute_confidence_level(
    report: AnalysisReport,
    overall_confidence: float,
) -> tuple[str, list[ConfidenceFactorItem]]:
    """Compute composite confidence level (High/Medium/Low) with factor breakdown."""
    factors: list[ConfidenceFactorItem] = []

    # 1. Comp quality
    comp_mod = report.module_results.get("comparable_sales")
    comp_count = int(comp_mod.metrics.get("comp_count", 0)) if comp_mod else 0
    if comp_count >= 5:
        factors.append(ConfidenceFactorItem("Comp quality", f"{comp_count} verified comps", "strong"))
    elif comp_count >= 3:
        factors.append(ConfidenceFactorItem("Comp quality", f"{comp_count} comps (limited)", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Comp quality", f"{comp_count} comps (thin)", "weak"))

    # 2. Income data
    cost_val = report.module_results.get("cost_valuation")
    rent_source = str(cost_val.metrics.get("rent_source_type", "missing")) if cost_val else "missing"
    if rent_source in ("manual_input", "provided"):
        factors.append(ConfidenceFactorItem("Income data", "User provided", "strong"))
    elif rent_source == "estimated":
        factors.append(ConfidenceFactorItem("Income data", "Estimated", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Income data", "Missing — using fallback", "weak"))

    # 3. Town data
    town_mod = report.module_results.get("town_county_outlook")
    town_conf = town_mod.confidence if town_mod else 0.0
    if town_conf >= 0.75:
        factors.append(ConfidenceFactorItem("Town data", "Full coverage", "strong"))
    elif town_conf >= 0.50:
        factors.append(ConfidenceFactorItem("Town data", "Partial coverage", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Town data", "Limited or missing", "weak"))

    # 4. Missing inputs
    pi = report.property_input
    critical_missing: list[str] = []
    if pi:
        if pi.taxes is None:
            critical_missing.append("taxes")
        if pi.insurance is None:
            critical_missing.append("insurance")
        if pi.estimated_monthly_rent is None:
            critical_missing.append("rent")
    non_critical_count = len(critical_missing)
    if non_critical_count == 0:
        factors.append(ConfidenceFactorItem("Missing inputs", "None critical", "strong"))
    elif non_critical_count <= 2:
        factors.append(ConfidenceFactorItem("Missing inputs", f"{non_critical_count} non-critical ({', '.join(critical_missing)})", "ok"))
    else:
        factors.append(ConfidenceFactorItem("Missing inputs", f"{non_critical_count} gaps ({', '.join(critical_missing)})", "weak"))

    # Determine level
    weak_count = sum(1 for f in factors if f.level == "weak")
    strong_count = sum(1 for f in factors if f.level == "strong")
    if weak_count >= 2 or overall_confidence < 0.55:
        level = "Provisional"
    elif strong_count >= 3 and overall_confidence >= 0.75:
        level = "Grounded"
    else:
        level = "Estimated"

    return level, factors


_INPUT_IMPACT_MAP: dict[str, tuple[str, str]] = {
    "estimated_monthly_rent": ("Add monthly rent estimate", "income"),
    "unit_rents": ("Add unit-level rents", "income"),
    "taxes": ("Add property taxes", "income"),
    "insurance": ("Add insurance cost", "income"),
    "repair_capex_budget": ("Add renovation/CapEx budget", "capex"),
    "condition_profile_override": ("Confirm property condition", "capex"),
    "condition_confirmed": ("Confirm condition assessment", "capex"),
    "capex_lane_override": ("Override CapEx lane", "capex"),
    "down_payment_percent": ("Set down payment %", "income"),
    "interest_rate": ("Set interest rate", "income"),
    "loan_term_years": ("Set loan term", "income"),
    "local_documents": ("Add local market intel", "market"),
    "market_price_to_rent_benchmark": ("Add price-to-rent benchmark", "income"),
}


def _compute_top_input_impacts(
    metric_statuses: list[object],
    confidence_breakdown: object,
) -> list[InputImpactItem]:
    """Identify the top 3 missing inputs that would most improve confidence."""
    # Build a priority list from metric statuses that are estimated/unresolved
    seen: set[str] = set()
    candidates: list[InputImpactItem] = []
    # Map component keys to their current confidence for impact estimation
    component_conf = {c.key: c.confidence for c in confidence_breakdown.components}

    for status in metric_statuses:
        if status.status == "fact_based":
            continue
        for field_name in status.prompt_fields:
            if field_name in seen:
                continue
            seen.add(field_name)
            label, component = _INPUT_IMPACT_MAP.get(field_name, (field_name.replace("_", " ").title(), "general"))
            current_conf = component_conf.get(component, 0.65)
            # Estimate impact: gap between current and 0.90, scaled
            gap = max(0.90 - current_conf, 0.0)
            impact_pct = round(gap * 100 * 0.4, 0)  # ~40% of the gap as realistic improvement
            if impact_pct < 1:
                continue
            candidates.append(InputImpactItem(
                field_label=label,
                impact_description=f"+{impact_pct:.0f}% confidence in {component} assessment",
                affected_component=component,
            ))

    # Sort by implied impact (descending) and take top 3
    candidates.sort(key=lambda c: float(c.impact_description.split("%")[0].replace("+", "")), reverse=True)
    return candidates[:3]


def _assumption_status_items(report: AnalysisReport) -> list[AssumptionStatusItem]:
    return [
        AssumptionStatusItem(
            key=item.key,
            label=item.label,
            status=item.status,
            value=item.value,
            source_label=item.source_label,
            note=item.note,
            affected_components=list(item.affected_components),
        )
        for item in compute_critical_assumption_statuses(report)
    ]


def _metric_chips(
    *,
    ask_price: float | None,
    bcv: float | None,
    value_low: float | None,
    value_high: float | None,
    mispricing_amount: float | None,
    mispricing_pct: float | None,
    base_case: float | None,
    confidence: float,
) -> list[MetricChip]:
    gap_tone = "positive" if (mispricing_amount or 0) >= 0 else "negative"
    return [
        MetricChip(label="Ask", value=_fmt_currency(ask_price)),
        MetricChip(label="Fair Value", value=_fmt_currency(bcv)),
        MetricChip(
            label="Gap vs Ask",
            value=f"{_fmt_currency_delta(mispricing_amount)} | {_fmt_pct(mispricing_pct, scale_100=False)}",
            tone=gap_tone,
        ),
        MetricChip(label="BCV Range", value=f"{_fmt_currency(value_low)} - {_fmt_currency(value_high)}"),
        MetricChip(label="Base Case", value=_fmt_currency(base_case)),
        MetricChip(label="Confidence", value=_fmt_pct(confidence)),
    ]


def _component_rows(report: AnalysisReport) -> list[tuple[str, str, str]]:
    current_value = get_current_value(report)
    rows = [
        ("Comparable Sales", _fmt_currency(current_value.components.comparable_sales_value), _fmt_pct(current_value.weights.comparable_sales_weight)),
        ("Market-Adjusted", _fmt_currency(current_value.components.market_adjusted_value), _fmt_pct(current_value.weights.market_adjusted_weight)),
        ("Listing-Aligned", _fmt_currency(current_value.components.backdated_listing_value), _fmt_pct(current_value.weights.backdated_listing_weight)),
        ("Income-Supported", _fmt_currency(current_value.components.income_supported_value), _fmt_pct(current_value.weights.income_weight)),
        (
            "Town-Aware Prior",
            _fmt_currency(getattr(current_value.components, "town_prior_value", None)),
            _fmt_pct(getattr(current_value.weights, "town_prior_weight", None)),
        ),
    ]
    return rows


def _comp_rows(report: AnalysisReport) -> list[CompReviewRow]:
    output = get_comparable_sales(report)
    rows: list[CompReviewRow] = []
    for comp in output.comps_used:
        rows.append(
            CompReviewRow(
                address=comp.address,
                sale_price=_fmt_currency(comp.sale_price),
                adjusted_price=_fmt_currency(comp.adjusted_price),
                fit=comp.fit_label.title(),
                status=(comp.comp_status or "unknown").replace("_", " ").title(),
                verification=(comp.sale_verification_status or "unverified").replace("_", " ").title(),
                condition=(comp.condition_profile or "Unavailable").replace("_", " ").title(),
                capex_lane=(comp.capex_lane or "Unavailable").replace("_", " ").title(),
                source_ref=comp.source_ref or "Unavailable",
                why_comp="; ".join(comp.why_comp) or "Unavailable",
                cautions="; ".join(comp.cautions) or "",
            )
        )
    return rows


def _screening_summary(report: AnalysisReport) -> str:
    output = get_comparable_sales(report)
    reasons = ", ".join(
        f"{reason.replace('_', ' ')}: {count}"
        for reason, count in sorted(output.rejection_reasons.items())
    )
    return f"{output.comp_count} kept | {output.rejected_count} screened out" + (f" | {reasons}" if reasons else "")


def _active_listing_rows(report: AnalysisReport) -> list[ActiveListingViewRow]:
    property_input = report.property_input
    if property_input is None or not ACTIVE_LISTINGS_PATH.exists():
        return []

    town = (property_input.town or "").strip().lower()
    state = (property_input.state or "").strip().lower()
    property_type = (property_input.property_type or "").strip().lower()
    price_anchor = property_input.purchase_price

    try:
        dataset = JsonActiveListingStore(ACTIVE_LISTINGS_PATH).load()
    except Exception:
        return []

    filtered = []
    for listing in dataset.listings:
        if town and listing.town.strip().lower() != town:
            continue
        if state and listing.state.strip().lower() != state:
            continue
        if property_type and listing.property_type and listing.property_type.strip().lower() != property_type:
            type_penalty = 1
        else:
            type_penalty = 0
        price_gap = abs((listing.list_price or 0.0) - (price_anchor or listing.list_price or 0.0))
        filtered.append((type_penalty, price_gap, listing.address.lower(), listing))

    filtered.sort(key=lambda item: (item[0], item[1], item[2]))
    rows: list[ActiveListingViewRow] = []
    for _, _, _, listing in filtered:
        rows.append(
            ActiveListingViewRow(
                address=listing.address,
                list_price=_fmt_currency(listing.list_price),
                status=listing.listing_status.replace("_", " ").title(),
                beds=_fmt_number(listing.beds),
                baths=_fmt_number(listing.baths),
                sqft=_fmt_number(listing.sqft),
                dom=_fmt_number(listing.days_on_market, " days"),
                condition=(listing.condition_profile or "Unavailable").replace("_", " ").title(),
                source_ref=listing.source_ref or "Unavailable",
            )
        )
    return rows


def build_property_analysis_view(report: AnalysisReport) -> PropertyAnalysisView:
    property_input = report.property_input
    current_value = get_current_value(report)
    comparable_sales = get_comparable_sales(report)
    active_listing_rows = _active_listing_rows(report)
    scenario = get_scenario_output(report)
    income = get_income_support(report)
    rental_ease = get_rental_ease(report)
    town_county = get_town_county_outlook(report)
    scarcity = get_scarcity_support(report)
    risk = report.get_module("risk_constraints")
    liquidity_metrics, liquidity_supporting, liquidity_unsupported = _liquidity_metrics(report)
    market_momentum_metrics, market_momentum_drivers, market_momentum_unsupported = _market_momentum_metrics(report)
    forward_module = report.get_module("bull_base_bear")
    conclusion = build_conclusion_section(report)
    thesis = build_thesis_section(report)
    sourced, user_supplied, estimated, missing = _coverage_lists(property_input)
    confidence_breakdown = compute_confidence_breakdown(report)
    metric_statuses = compute_metric_input_statuses(report)
    assumption_statuses = _assumption_status_items(report)
    overall_confidence = confidence_breakdown.overall_confidence

    positives = list(town_county.score.demand_drivers[:2]) + list(scarcity.demand_drivers[:1])
    risks = list(rental_ease.risks[:2]) + list(town_county.score.demand_risks[:2])
    positives = [item for item in positives if item][:3]
    risks = [item for item in risks if item][:3]

    ask_price_val = current_value.ask_price
    forward_gap_pct = (
        (scenario.base_case_value - ask_price_val) / ask_price_val
        if ask_price_val
        else None
    )
    town_context_raw = get_town_context(property_input.town if property_input else None)
    subject_ppsf = (ask_price_val / property_input.sqft) if property_input and ask_price_val and property_input.sqft else None
    subject_ppsf_vs_town = _safe_ratio(subject_ppsf, town_context_raw.median_ppsf) if town_context_raw else None
    subject_price_vs_town = _safe_ratio(ask_price_val, town_context_raw.median_price) if town_context_raw else None
    subject_lot_vs_town = _safe_ratio(property_input.lot_size if property_input else None, town_context_raw.median_lot_size) if town_context_raw else None
    town_adjusted_value_gap = (
        round((town_context_raw.median_ppsf - subject_ppsf) / subject_ppsf, 3)
        if town_context_raw and subject_ppsf not in (None, 0) and town_context_raw.median_ppsf not in (None, 0)
        else None
    )
    town_relative_opportunity_score = _town_relative_opportunity_score(
        subject_ppsf_vs_town=subject_ppsf_vs_town,
        subject_price_vs_town=subject_price_vs_town,
        town_context_confidence=(town_context_raw.context_confidence if town_context_raw else None),
    )
    town_context = (
        {
            "town": town_context_raw.town,
            "baseline_median_price": town_context_raw.median_price,
            "baseline_median_ppsf": town_context_raw.median_ppsf,
            "baseline_median_sqft": town_context_raw.median_sqft,
            "baseline_median_lot_size": town_context_raw.median_lot_size,
            "town_price_index": town_context_raw.town_price_index,
            "town_ppsf_index": town_context_raw.town_ppsf_index,
            "town_lot_index": town_context_raw.town_lot_index,
            "town_liquidity_index": town_context_raw.town_liquidity_index,
            "town_context_confidence": town_context_raw.context_confidence,
            "qa_flags": list(town_context_raw.qa_flags),
            "subject_ppsf_vs_town": subject_ppsf_vs_town,
            "subject_price_vs_town": subject_price_vs_town,
            "subject_lot_vs_town": subject_lot_vs_town,
            "town_adjusted_value_gap": town_adjusted_value_gap,
            "town_relative_opportunity_score": town_relative_opportunity_score,
            "qa_summary": (
                "Town context is strong enough to inform pricing context."
                if not town_context_raw.qa_flags and town_context_raw.context_confidence >= 0.78
                else f"Town context is directional only because {', '.join(town_context_raw.qa_flags)}."
                if town_context_raw.qa_flags
                else "Town context is usable, but not clean enough to dominate direct comps."
            ),
        }
        if town_context_raw
        else {}
    )
    compare_metrics = {
        "ask_price": ask_price_val,
        "bcv": current_value.briarwood_current_value,
        "bcv_delta": current_value.mispricing_amount,
        "all_in_basis": getattr(current_value, "all_in_basis", None),
        "net_opportunity_delta_value": getattr(current_value, "net_opportunity_delta_value", None),
        "net_opportunity_delta_pct": getattr(current_value, "net_opportunity_delta_pct", None),
        "bcv_range": f"{current_value.value_low:,.0f}-{current_value.value_high:,.0f}",
        "forward_base_case": scenario.base_case_value,
        "lot_size": property_input.lot_size if property_input else None,
        "sqft": property_input.sqft if property_input else None,
        "taxes": property_input.taxes if property_input else None,
        "dom": property_input.days_on_market if property_input else None,
        "income_support_ratio": income.income_support_ratio,
        "price_to_rent": income.price_to_rent,
        "monthly_cash_flow": _income_attr(income, "monthly_cash_flow"),
        "forward_gap_pct": forward_gap_pct,
        "risk_score": risk.score,
        "liquidity_score": liquidity_metrics.get("liquidity_score"),
        "liquidity_label": liquidity_metrics.get("liquidity_label"),
        "market_momentum_score": market_momentum_metrics.get("market_momentum_score"),
        "market_momentum_label": market_momentum_metrics.get("market_momentum_label"),
        "town_county_score": town_county.score.town_county_score,
        "scarcity_score": scarcity.scarcity_support_score,
        "confidence": overall_confidence,
        "missing_inputs": missing,
        "subject_ppsf": subject_ppsf,
        "town_baseline_median_price": town_context.get("baseline_median_price"),
        "town_baseline_median_ppsf": town_context.get("baseline_median_ppsf"),
        "town_baseline_median_sqft": town_context.get("baseline_median_sqft"),
        "town_price_index": town_context.get("town_price_index"),
        "town_ppsf_index": town_context.get("town_ppsf_index"),
        "town_lot_index": town_context.get("town_lot_index"),
        "town_liquidity_index": town_context.get("town_liquidity_index"),
        "town_context_confidence": town_context.get("town_context_confidence"),
        "town_qa_flags": town_context.get("qa_flags", []),
        "subject_ppsf_vs_town": subject_ppsf_vs_town,
        "subject_price_vs_town": subject_price_vs_town,
        "subject_lot_vs_town": subject_lot_vs_town,
        "town_adjusted_value_gap": town_adjusted_value_gap,
        "town_relative_opportunity_score": town_relative_opportunity_score,
    }

    view = PropertyAnalysisView(
        property_id=report.property_id,
        label=(property_input.address if property_input else report.address).split(",")[0],
        address=property_input.address if property_input else report.address,
        evidence_mode=(property_input.source_metadata.evidence_mode.value.replace("_", " ").title() if property_input and property_input.source_metadata else "Unknown"),
        condition_profile=((property_input.condition_profile or "Unavailable").replace("_", " ").title() if property_input else "Unavailable"),
        capex_lane=((property_input.capex_lane or "Unavailable").replace("_", " ").title() if property_input else "Unavailable"),
        overall_confidence=overall_confidence,
        ask_price=ask_price_val,
        bcv=current_value.briarwood_current_value,
        value_low=current_value.value_low,
        value_high=current_value.value_high,
        base_case=scenario.base_case_value,
        bull_case=scenario.bull_case_value,
        bear_case=scenario.bear_case_value,
        stress_case=_scenario_stress_value(scenario),
        mispricing_amount=current_value.mispricing_amount,
        mispricing_pct=current_value.mispricing_pct,
        all_in_basis=getattr(current_value, "all_in_basis", None),
        capex_basis_used=getattr(current_value, "capex_basis_used", None),
        capex_basis_source=getattr(current_value, "capex_basis_source", None) or "unknown",
        net_opportunity_delta_value=getattr(current_value, "net_opportunity_delta_value", None),
        net_opportunity_delta_pct=getattr(current_value, "net_opportunity_delta_pct", None),
        pricing_view=current_value.pricing_view,
        memo_verdict=conclusion.verdict,
        biggest_risk=conclusion.top_risk,
        buyer_fit=list(conclusion.decision_fit),
        top_reasons=list(conclusion.why_it_matters),
        what_changes_call=list(conclusion.what_changes_call),
        memo_summary=thesis.assessment.summary,
        top_positives=positives,
        top_risks=risks,
        metric_chips=_metric_chips(
            ask_price=ask_price_val,
            bcv=current_value.briarwood_current_value,
            value_low=current_value.value_low,
            value_high=current_value.value_high,
            mispricing_amount=current_value.mispricing_amount,
            mispricing_pct=current_value.mispricing_pct,
            base_case=scenario.base_case_value,
            confidence=overall_confidence,
        ),
        value=ValueViewModel(
            component_rows=_component_rows(report),
            pricing_view=current_value.pricing_view,
            assumptions=list(current_value.assumptions),
            warnings=list(current_value.warnings),
            unsupported_claims=list(current_value.unsupported_claims),
            confidence=float(current_value.confidence),
        ),
        comps=CompsViewModel(
            comparable_value_text=_fmt_currency(comparable_sales.comparable_value),
            comp_count_text=str(comparable_sales.comp_count),
            confidence_text=_fmt_pct(comparable_sales.confidence),
            active_listing_count_text=str(len(active_listing_rows)),
            dataset_name=comparable_sales.dataset_name or "Unavailable",
            verification_summary=comparable_sales.verification_summary or "Unavailable",
            curation_summary=comparable_sales.curation_summary or "Unavailable",
            screening_summary=_screening_summary(report),
            warnings=list(comparable_sales.warnings),
            assumptions=list(comparable_sales.assumptions),
            unsupported_claims=list(comparable_sales.unsupported_claims),
            rows=_comp_rows(report),
            active_listing_rows=active_listing_rows,
        ),
        forward=ForwardViewModel(
            summary=forward_module.summary,
            confidence=float(forward_module.confidence),
            bull_value_text=_fmt_currency(scenario.bull_case_value),
            base_value_text=_fmt_currency(scenario.base_case_value),
            bear_value_text=_fmt_currency(scenario.bear_case_value),
            stress_case_value_text=_fmt_currency(_scenario_stress_value(scenario)),
            upside_pct_text=_fmt_pct((scenario.bull_case_value - ask_price_val) / ask_price_val) if ask_price_val else "Unavailable",
            downside_pct_text=_fmt_pct((scenario.bear_case_value - ask_price_val) / ask_price_val) if ask_price_val else "Unavailable",
            market_drift_text=_fmt_currency(forward_module.metrics.get("market_drift")),
            location_premium_text=_fmt_currency(forward_module.metrics.get("location_premium")),
            risk_discount_text=_fmt_currency(forward_module.metrics.get("risk_discount")),
            optionality_premium_text=_fmt_currency(forward_module.metrics.get("optionality_premium")),
        ),
        income_support=IncomeSupportViewModel(
            summary=_income_attr(income, "summary", "Income support unavailable."),
            confidence=float(_income_attr(income, "confidence", 0.0)),
            rental_ease_label=rental_ease.rental_ease_label,
            estimated_days_to_rent_text=_fmt_number(rental_ease.estimated_days_to_rent, " days"),
            total_rent_text=_fmt_currency(_income_attr(income, "monthly_rent_estimate") or _income_attr(income, "gross_monthly_rent_before_vacancy")),
            num_units_text=_fmt_number(_income_attr(income, "num_units")),
            avg_rent_per_unit_text=_fmt_currency(_income_attr(income, "avg_rent_per_unit")),
            income_support_ratio_text=(f"{_income_attr(income, 'income_support_ratio'):.2f}x" if _income_attr(income, "income_support_ratio") is not None else "Unavailable"),
            monthly_cash_flow_text=_fmt_currency(_income_attr(income, "monthly_cash_flow")),
            operating_cash_flow_text=_fmt_currency(_income_attr(income, "operating_monthly_cash_flow")),
            rent_source_type=str(_income_attr(income, "rent_source_type", "missing")).replace("_", " ").title(),
            risk_view=str(_income_attr(income, "risk_view", "unknown")).replace("_", " ").title(),
            price_to_rent_text=_fmt_number(_income_attr(income, "price_to_rent"), "x"),
            ptr_classification=_income_attr(income, "price_to_rent_classification") or "Unavailable",
            unit_breakdown=[
                (f"Unit {index + 1}", _fmt_currency(value))
                for index, value in enumerate(_income_list(income, "unit_breakdown"))
            ],
            warnings=list(_income_attr(income, "warnings", [])),
            assumptions=list(_income_attr(income, "assumptions", [])),
            unsupported_claims=list(_income_attr(income, "unsupported_claims", [])),
            # Surfaced investor metrics from cost_valuation module
            dscr=_cost_val_metric(report, "dscr"),
            dscr_text=_fmt_ratio(_cost_val_metric(report, "dscr")),
            cash_on_cash_return=_cost_val_metric(report, "cash_on_cash_return"),
            cash_on_cash_return_text=_fmt_pct(_cost_val_metric(report, "cash_on_cash_return")),
            gross_yield=_cost_val_metric(report, "gross_yield"),
            gross_yield_text=_fmt_pct(_cost_val_metric(report, "gross_yield")),
            # Rent source trust label
            rent_source_label=_rent_source_label(str(_income_attr(income, "rent_source_type", "missing"))),
        ),
        risk_location=RiskLocationViewModel(
            risk_summary=risk.summary,
            risk_score=float(risk.score),
            town_score=float(town_county.score.town_county_score),
            town_label=town_county.score.location_thesis_label,
            scarcity_score=float(scarcity.scarcity_support_score),
            liquidity_score=float(liquidity_metrics.get("liquidity_score") or 0.0),
            liquidity_label=str(liquidity_metrics.get("liquidity_label") or "Unknown"),
            market_momentum_score=float(market_momentum_metrics.get("market_momentum_score") or 0.0),
            market_momentum_label=str(market_momentum_metrics.get("market_momentum_label") or "Unknown"),
            flood_risk=property_input.flood_risk if property_input and property_input.flood_risk else "Unavailable",
            liquidity_view=town_county.score.liquidity_view,
            drivers=list(market_momentum_drivers[:2]) + list(liquidity_supporting[:1]) + list(town_county.score.demand_drivers[:1]) + list(scarcity.demand_drivers[:1]),
            risks=list(market_momentum_unsupported[:1]) + list(liquidity_unsupported[:1]) + list(town_county.score.demand_risks[:2]) + list(scarcity.scarcity_notes[:1]),
            warnings=list(risk.metrics.get("warnings", [])) if isinstance(risk.metrics.get("warnings"), list) else [],
            unsupported_claims=list(town_county.score.unsupported_claims) + list(scarcity.unsupported_claims),
            # Surfaced stress scenario and momentum direction
            stress_case_value=_scenario_stress_value(scenario),
            stress_case_text=_fmt_currency(_scenario_stress_value(scenario)),
            stress_drawdown_pct=_as_float(forward_module.metrics.get("stress_macro_shock_pct")),
            momentum_direction=str(market_momentum_metrics.get("market_momentum_direction", "") or ""),
            # Location context: school signal and coastal profile
            school_signal=property_input.school_rating if property_input else None,
            school_signal_text=f"{property_input.school_rating:.1f}/10" if property_input and property_input.school_rating is not None else "",
            coastal_profile_label=_coastal_profile_label(town_county),
            # Scarcity component breakdown
            land_scarcity_score=getattr(scarcity, "land_scarcity_score", None),
            location_scarcity_score=getattr(scarcity, "location_scarcity_score", None),
        ),
        evidence=EvidenceViewModel(
            evidence_mode=(property_input.source_metadata.evidence_mode.value.replace("_", " ").title() if property_input and property_input.source_metadata else "Unknown"),
            sourced_inputs=sourced,
            user_supplied_inputs=user_supplied,
            estimated_inputs=estimated,
            missing_inputs=missing,
            unsupported_claims=_collect_unsupported_claims(report),
            confidence_components=[
                ConfidenceComponentItem(
                    key=item.key,
                    label=item.label,
                    confidence=item.confidence,
                    weight=item.weight,
                    reason=item.reason,
                )
                for item in confidence_breakdown.components
            ],
            confidence_notes=list(confidence_breakdown.notes),
            assumption_statuses=assumption_statuses,
            transparency_items=[],
            metric_statuses=[
                MetricInputStatusItem(
                    key=item.key,
                    label=item.label,
                    status=item.status,
                    facts_used=list(item.facts_used),
                    user_inputs_used=list(item.user_inputs_used),
                    assumptions_used=list(item.assumptions_used),
                    missing_inputs=list(item.missing_inputs),
                    confidence_impact=item.confidence_impact,
                    prompt_fields=list(item.prompt_fields),
                )
                for item in metric_statuses
            ],
            gap_prompt_fields=sorted(
                {
                    field
                    for item in metric_statuses
                    if item.status != "fact_based"
                    for field in item.prompt_fields
                }
            ),
            section_confidences=_section_confidences(report),
        ),
        town_context=town_context,
        compare_metrics=compare_metrics,
    )
    view.evidence.transparency_items = _assumption_transparency_items(
        property_input,
        income=income,
        confidence_components=view.evidence.confidence_components,
    )

    # Defaults transparency
    if property_input is not None:
        view.defaults_applied = getattr(property_input, "defaults_applied", {}) or {}
        view.geocoded = getattr(property_input, "geocoded", False)
    missing_assumptions = [item.label.lower() for item in assumption_statuses if item.status == "missing"]
    estimated_assumptions = [item.label.lower() for item in assumption_statuses if item.status == "estimated"]
    if missing_assumptions:
        view.evidence.confidence_notes.append(
            f"Critical underwriting assumptions still missing: {', '.join(missing_assumptions[:4])}."
        )
    elif estimated_assumptions:
        view.evidence.confidence_notes.append(
            f"Key underwriting assumptions are still estimated: {', '.join(estimated_assumptions[:4])}."
        )
    if town_context:
        if town_context.get("qa_flags"):
            view.evidence.confidence_notes.append(
                f"Town context for {town_context['town']} is weaker because {', '.join(town_context['qa_flags'])}."
            )
        elif town_context.get("town_context_confidence") is not None and town_context["town_context_confidence"] >= 0.78:
            view.evidence.confidence_notes.append(
                f"Town context for {town_context['town']} is well covered and can be used as a secondary pricing benchmark."
            )

    # Scoring layer — gracefully degrade if scoring fails
    try:
        from briarwood.decision_model.scoring import calculate_final_score
        fs = calculate_final_score(report)
        view.final_score = fs.score
        view.recommendation_tier = fs.tier
        view.recommendation_action = fs.action
        view.score_narrative = fs.narrative
        view.category_scores = fs.category_scores
    except Exception:
        pass

    # Lens scoring — multi-perspective evaluation
    try:
        from briarwood.decision_model.lens_scoring import calculate_lens_scores
        view.lens_scores = calculate_lens_scores(report, view.category_scores)
    except Exception:
        pass

    # Confidence layer — global level, factors, and input impacts
    level, factors = _compute_confidence_level(report, overall_confidence)
    view.confidence_level = level
    view.confidence_factors = factors
    view.top_input_impacts = _compute_top_input_impacts(metric_statuses, confidence_breakdown)

    view.decision = _build_decision_view(view)

    return view


def build_evidence_rows(report: AnalysisReport) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    property_input = report.property_input
    if property_input is None or property_input.source_metadata is None:
        return rows
    for category, item in sorted(property_input.source_metadata.source_coverage.items()):
        rows.append(
            {
                "Category": category.replace("_", " ").title(),
                "Status": _coverage_status_label(item.status),
                "Source": item.source_name or "Unavailable",
                "Freshness": item.freshness or "",
                "Note": item.note or "",
            }
        )
    return rows


def build_section_evidence_rows(report: AnalysisReport) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for module in report.module_results.values():
        evidence = module.section_evidence
        if evidence is None:
            continue
        rows.append(_flatten_section_evidence(module.module_name, module.confidence, evidence))
    return rows


def _flatten_section_evidence(module_name: str, confidence: float, evidence: SectionEvidence) -> dict[str, str]:
    return {
        "Section": module_name.replace("_", " ").title(),
        "Confidence": _fmt_pct(confidence),
        "Mode": evidence.evidence_mode.value.replace("_", " ").title(),
        "Estimated": ", ".join(evidence.estimated_inputs[:3]) or "None",
        "Missing": ", ".join(evidence.major_missing_inputs[:3]) or "None",
        "Notes": "; ".join(evidence.notes[:2]) or "",
    }


def _assumption_transparency_items(
    property_input: PropertyInput | None,
    *,
    income: object,
    confidence_components: list[ConfidenceComponentItem],
) -> list[AssumptionTransparencyItem]:
    if property_input is None:
        return []
    assumptions = property_input.user_assumptions
    coverage = property_input.coverage_for
    component_map = {item.key: item for item in confidence_components}
    items: list[AssumptionTransparencyItem] = []

    rent_source = coverage("rent_estimate").status
    rent_value = None
    if assumptions and assumptions.unit_rents:
        rent_value = f"{_fmt_currency(sum(assumptions.unit_rents))}/mo across {len(assumptions.unit_rents)} units"
    elif assumptions and assumptions.estimated_monthly_rent is not None:
        rent_value = f"{_fmt_currency(assumptions.estimated_monthly_rent)}/mo"
    elif _income_attr(income, "monthly_rent_estimate") is not None:
        rent_value = f"{_fmt_currency(_income_attr(income, 'monthly_rent_estimate'))}/mo"
    if rent_value:
        source_kind = "confirmed" if rent_source is InputCoverageStatus.USER_SUPPLIED else "inferred"
        source_label = "User Confirmed" if source_kind == "confirmed" else "Model Inferred"
        note = component_map.get("rent").reason if component_map.get("rent") else ""
        if assumptions and assumptions.rent_confidence_override:
            note = f"{note} Rent confidence override: {assumptions.rent_confidence_override.title()}."
        items.append(
            AssumptionTransparencyItem(
                label="Rent",
                value=rent_value,
                source_kind=source_kind,
                source_label=source_label,
                note=note,
            )
        )

    capex_value = None
    if property_input.repair_capex_budget is not None:
        capex_value = _fmt_currency(property_input.repair_capex_budget)
    elif property_input.capex_lane:
        capex_value = property_input.capex_lane.replace("_", " ").title()
    if capex_value:
        capex_override = bool(
            (assumptions and assumptions.capex_lane_override)
            or getattr(property_input, "capex_confirmed", False)
            or property_input.repair_capex_budget is not None
        )
        source_kind = "confirmed" if capex_override else "inferred"
        source_label = "User Confirmed" if source_kind == "confirmed" else "Model Inferred"
        note = component_map.get("capex").reason if component_map.get("capex") else ""
        items.append(
            AssumptionTransparencyItem(
                label="CapEx",
                value=capex_value,
                source_kind=source_kind,
                source_label=source_label,
                note=note,
            )
        )

    if property_input.condition_profile:
        condition_override = bool((assumptions and assumptions.condition_profile_override) or getattr(property_input, "condition_confirmed", False))
        source_kind = "confirmed" if condition_override else "inferred"
        source_label = "User Confirmed" if source_kind == "confirmed" else "Model Inferred"
        items.append(
            AssumptionTransparencyItem(
                label="Condition",
                value=property_input.condition_profile.replace("_", " ").title(),
                source_kind=source_kind,
                source_label=source_label,
                note="Current condition informs CapEx burden and execution confidence.",
            )
        )

    financing_parts: list[str] = []
    if property_input.down_payment_percent is not None:
        financing_parts.append(f"{property_input.down_payment_percent * 100:.0f}% down")
    if property_input.interest_rate is not None:
        financing_parts.append(f"{property_input.interest_rate * 100:.2f}% rate")
    if property_input.loan_term_years is not None:
        financing_parts.append(f"{property_input.loan_term_years}y term")
    if financing_parts:
        items.append(
            AssumptionTransparencyItem(
                label="Financing",
                value=" / ".join(financing_parts),
                source_kind="confirmed",
                source_label="User Confirmed",
                note="These inputs feed monthly carry, cash flow, and downside support.",
            )
        )
    else:
        items.append(
            AssumptionTransparencyItem(
                label="Financing",
                value="Incomplete",
                source_kind="inferred",
                source_label="Model Inferred",
                note="Monthly carry confidence stays lower until down payment, rate, and term are supplied.",
            )
        )

    preference_parts: list[str] = []
    if getattr(property_input, "strategy_intent", None):
        preference_parts.append(property_input.strategy_intent.replace("_", " ").title())
    if getattr(property_input, "hold_period_years", None) is not None:
        preference_parts.append(f"{property_input.hold_period_years}y hold")
    if getattr(property_input, "risk_tolerance", None):
        preference_parts.append(f"{property_input.risk_tolerance.title()} risk")
    if preference_parts:
        items.append(
            AssumptionTransparencyItem(
                label="Strategy",
                value=" / ".join(preference_parts),
                source_kind="preference",
                source_label="User Preference",
                note="Preference inputs shape interpretation and fit, but do not raise factual confidence on their own.",
            )
        )

    return items


def _confidence_level(confidence: float) -> str:
    if confidence >= 0.8:
        return "Grounded"
    if confidence >= 0.62:
        return "Estimated"
    return "Provisional"


def _strategy_fit_label(lens_scores: Any | None) -> str:
    if lens_scores is None:
        return "Hybrid"
    recommended = (getattr(lens_scores, "recommended_lens", "") or "").strip().lower()
    mapping = {
        "owner": "Primary Residence",
        "investor": "Rental Investor",
        "developer": "Redevelopment",
    }
    if recommended in mapping:
        return mapping[recommended]

    owner = getattr(lens_scores, "owner_score", None)
    investor = getattr(lens_scores, "investor_score", None)
    developer = getattr(lens_scores, "developer_score", None)
    scored = {
        "Primary Residence": owner,
        "Rental Investor": investor,
        "Redevelopment": developer,
    }
    valid = {label: score for label, score in scored.items() if isinstance(score, (int, float))}
    if not valid:
        return "Hybrid"
    ranked = sorted(valid.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) >= 2 and abs(ranked[0][1] - ranked[1][1]) <= 0.35 and ranked[0][0] in {"Primary Residence", "Rental Investor"} and ranked[1][0] in {"Primary Residence", "Rental Investor"}:
        return "Hybrid"
    return ranked[0][0]


def _build_decision_view(view: PropertyAnalysisView) -> DecisionViewModel:
    tier_rank = {
        "Pass": 0,
        "Lean Away": 1,
        "Hold / Dig Deeper": 2,
        "Lean Buy": 3,
        "Buy": 4,
    }
    score_tier = view.recommendation_tier or "Hold / Dig Deeper"
    final_score = float(view.final_score or 0.0)
    valuation_pct = view.net_opportunity_delta_pct if view.net_opportunity_delta_pct is not None else view.mispricing_pct
    monthly_cash_flow = view.compare_metrics.get("monthly_cash_flow")
    income_support_ratio = view.compare_metrics.get("income_support_ratio")
    liquidity_score = view.risk_location.liquidity_score
    momentum_score = view.risk_location.market_momentum_score
    subject_ppsf_vs_town = view.compare_metrics.get("subject_ppsf_vs_town")
    town_adjusted_value_gap = view.compare_metrics.get("town_adjusted_value_gap")
    town_context_confidence = view.compare_metrics.get("town_context_confidence")
    confidence_level = view.confidence_level or _confidence_level(view.overall_confidence)
    best_fit = _strategy_fit_label(view.lens_scores)
    display_fit = best_fit
    fit_context = ""
    renovated_value = view.compare_metrics.get("renovated_bcv")
    assumption_map = {item.key: item for item in (view.evidence.assumption_statuses if view.evidence else [])}
    rent_assumption = assumption_map.get("rent")
    financing_assumption = assumption_map.get("financing")
    condition_assumption = assumption_map.get("condition_profile")
    capex_assumption = assumption_map.get("capex")

    supporting_factors: list[str] = []
    risks: list[str] = []
    dependencies: list[str] = []
    disqualifiers: list[str] = []
    severe_valuation_gap = False
    severe_liquidity_issue = False
    severe_investor_carry_issue = False
    hard_constraints: list[str] = []

    if valuation_pct is not None:
        if valuation_pct >= 0.12:
            supporting_factors.append(f"material value cushion of about {valuation_pct * 100:.0f}%")
        elif valuation_pct >= 0.04:
            supporting_factors.append(f"modest value cushion of about {valuation_pct * 100:.0f}%")
        elif valuation_pct <= -0.20:
            severe_valuation_gap = True
            disqualifiers.append(f"basis looks rich by about {abs(valuation_pct) * 100:.0f}%")
        elif valuation_pct <= -0.10:
            risks.append(f"basis looks rich by about {abs(valuation_pct) * 100:.0f}%")
        elif valuation_pct <= -0.04:
            risks.append(f"basis is slightly rich versus current support ({abs(valuation_pct) * 100:.0f}%)")
    else:
        dependencies.append("valuation support is still incomplete")

    if isinstance(subject_ppsf_vs_town, (int, float)) and isinstance(town_context_confidence, (int, float)) and town_context_confidence >= 0.45:
        if subject_ppsf_vs_town <= 0.92:
            supporting_factors.append("screens cheap relative to the town's median pricing band")
        elif subject_ppsf_vs_town >= 1.10:
            risks.append("screens rich relative to the town's median pricing band")
    elif view.town_context.get("qa_flags"):
        dependencies.append("town-level context is still noisy")

    if isinstance(monthly_cash_flow, (int, float)):
        if monthly_cash_flow >= 250:
            supporting_factors.append("rent support materially offsets monthly carry")
        elif monthly_cash_flow >= -250:
            supporting_factors.append("carry looks manageable, but only modestly supported")
        elif monthly_cash_flow >= -750:
            risks.append("carry still needs meaningful monthly support")
        elif best_fit == "Rental Investor":
            severe_investor_carry_issue = True
            disqualifiers.append("carry is too negative for a pure rental hold")
        else:
            risks.append("carry still needs owner subsidy under current assumptions")
    else:
        dependencies.append("monthly carry is still estimated")

    if isinstance(income_support_ratio, (int, float)) and income_support_ratio < 0.75:
        if best_fit == "Rental Investor":
            disqualifiers.append("income support is weak for an investor-led thesis")
        else:
            risks.append("income support is weak")
    elif isinstance(income_support_ratio, (int, float)) and income_support_ratio < 0.9:
        risks.append("income support is only partial")

    if liquidity_score < 35:
        severe_liquidity_issue = True
        disqualifiers.append("exit liquidity is thin enough to constrain the thesis")
    elif liquidity_score < 50:
        risks.append("exit liquidity is mixed")
    else:
        supporting_factors.append("exit liquidity is serviceable")

    if momentum_score >= 65:
        supporting_factors.append("market backdrop is a constructive tailwind")
    elif momentum_score < 45:
        risks.append("market backdrop is not helping much")

    if view.capex_lane.lower() in {"moderate", "heavy"}:
        capex_confirmed = any(item.source_kind == "confirmed" and item.label == "CapEx" for item in view.evidence.transparency_items)
        if capex_confirmed:
            risks.append(f"{view.capex_lane.lower()} capex burden still matters")
        else:
            dependencies.append("capex burden is still inferred")
            risks.append(f"{view.capex_lane.lower()} capex burden is not yet confirmed")

    if confidence_level == "Provisional":
        dependencies.append("critical inputs still rely on estimates or missing facts")

    if rent_assumption is not None:
        if rent_assumption.status == "missing":
            dependencies.insert(0, "rent assumption is still missing")
        elif rent_assumption.status == "estimated":
            dependencies.insert(0, "rent assumption is still estimated")
    if financing_assumption is not None:
        if financing_assumption.status == "missing":
            dependencies.insert(0, "financing assumptions are still missing")
        elif financing_assumption.status == "estimated":
            dependencies.insert(0, "financing assumptions are only partially confirmed")
    if capex_assumption is not None:
        if capex_assumption.status == "missing":
            dependencies.insert(0, "capex scope is still missing")
        elif capex_assumption.status == "estimated":
            dependencies.insert(0, "capex burden is still inferred")
    if condition_assumption is not None and condition_assumption.status == "missing":
        dependencies.insert(0, "condition still needs to be confirmed")

    if best_fit == "Primary Residence":
        supporting_factors.append("best lens is owner-occupant rather than pure investor")
    elif best_fit == "Redevelopment":
        display_fit = "Value-Add / Renovation"
        supporting_factors.append("upside is more strategy-driven than hold-driven")
        if isinstance(renovated_value, (int, float)):
            fit_context = f"As a renovated case, Briarwood estimates value around {_fmt_currency(renovated_value)}."
        elif view.bull_case is not None:
            fit_context = f"This reads more like a renovation/value-add case than a teardown. Briarwood's upside anchor is about {_fmt_currency(view.bull_case)} in the bull case."

    if view.overall_confidence < 0.40:
        hard_constraints.append("extremely weak confidence")
    elif confidence_level == "Provisional" and final_score >= 3.3:
        hard_constraints.append("confidence is too thin for a clean positive call")
    if severe_liquidity_issue or liquidity_score < 28:
        hard_constraints.append("severe liquidity constraint")
    if severe_investor_carry_issue:
        hard_constraints.append("major income support failure")
    elif isinstance(income_support_ratio, (int, float)) and income_support_ratio < 0.50:
        hard_constraints.append("major income support failure")
    elif isinstance(monthly_cash_flow, (int, float)) and monthly_cash_flow <= -1500:
        hard_constraints.append("major income support failure")
    if score_tier in {"Buy", "Lean Buy"}:
        if rent_assumption is not None and rent_assumption.status == "missing":
            hard_constraints.append("rent assumption is still missing")
        if financing_assumption is not None and financing_assumption.status == "missing":
            hard_constraints.append("financing assumptions are still missing")
    if severe_valuation_gap or view.risk_location.risk_score >= 85:
        hard_constraints.append("severe downside risk")

    primary_driver = "valuation"
    if hard_constraints and any("liquidity" in item for item in hard_constraints):
        primary_driver = "liquidity"
    elif hard_constraints and any("income support" in item for item in hard_constraints):
        primary_driver = "carry"
    elif valuation_pct is not None and abs(valuation_pct) >= 0.04:
        primary_driver = "valuation"
    elif best_fit in {"Primary Residence", "Redevelopment", "Hybrid"}:
        primary_driver = "fit"
    elif monthly_cash_flow is not None:
        primary_driver = "carry"

    recommendation = score_tier
    if hard_constraints:
        hard_set = set(hard_constraints)
        if {"extremely weak confidence", "severe liquidity constraint"} & hard_set:
            recommendation = "Pass" if score_tier in {"Buy", "Lean Buy"} else "Lean Away"
        elif "severe downside risk" in hard_set and score_tier == "Buy":
            recommendation = "Lean Buy"
        elif "major income support failure" in hard_set and score_tier in {"Buy", "Lean Buy"}:
            recommendation = "Hold / Dig Deeper" if best_fit in {"Primary Residence", "Value-Add / Renovation", "Redevelopment", "Hybrid"} else "Lean Away"
        elif {"rent assumption is still missing", "financing assumptions are still missing"} & hard_set and score_tier == "Buy":
            recommendation = "Lean Buy"
        elif "confidence is too thin for a clean positive call" in hard_set and score_tier == "Buy":
            recommendation = "Lean Buy"
    if tier_rank.get(recommendation, 0) > tier_rank.get(score_tier, 0):
        recommendation = score_tier

    if recommendation == "Buy":
        thesis = "The setup is favorable — enough value support, economics, and exit quality to move forward."
    elif recommendation == "Lean Buy":
        thesis = "More right than wrong, but one condition still needs to hold cleanly."
    elif recommendation == "Hold / Dig Deeper":
        thesis = "The deal is viable enough to keep working, but not yet sharp enough to act on."
    elif recommendation == "Lean Away":
        thesis = "The evidence is mostly negative unless one key assumption improves."
    else:
        thesis = "The current underwriting does not clear Briarwood's bar."

    if primary_driver == "valuation" and valuation_pct is not None:
        thesis = (
            f"Current value support is the main reason this works, with about {abs(valuation_pct) * 100:.0f}% "
            f"{'upside versus basis' if valuation_pct >= 0 else 'overpricing versus support'} driving the call."
        )
        if isinstance(town_adjusted_value_gap, (int, float)) and isinstance(town_context_confidence, (int, float)) and town_context_confidence >= 0.45:
            if town_adjusted_value_gap >= 0.06:
                thesis += f" It also screens about {town_adjusted_value_gap * 100:.0f}% cheap relative to its town baseline."
            elif town_adjusted_value_gap <= -0.06:
                thesis += f" It also screens about {abs(town_adjusted_value_gap) * 100:.0f}% rich relative to its town baseline."
    elif primary_driver == "carry":
        thesis = "Hold economics are the main constraint; the property needs more support from rent or a better basis to be compelling."
    elif primary_driver == "liquidity":
        thesis = "Exit liquidity is the main constraint; even a decent price does not fully offset a thin resale path."
    elif primary_driver == "fit":
        thesis = f"The main reason this remains interesting is strategic fit as a {display_fit.lower()} case rather than universal attractiveness."

    decisive_driver = (
        "Value support versus basis"
        if primary_driver == "valuation" else
        "Hold economics"
        if primary_driver == "carry" else
        "Exit liquidity"
        if primary_driver == "liquidity" else
        f"{display_fit} fit"
    )

    break_condition = (
        hard_constraints[0]
        if hard_constraints else
        disqualifiers[0]
        if disqualifiers else
        risks[0]
        if risks else
        view.biggest_risk
        if view.biggest_risk else
        "No single failure point dominates the thesis."
    )

    if dependencies:
        required_belief = dependencies[0].capitalize() + "."
    elif recommendation == "Buy":
        required_belief = "Rent support, capex, and liquidity need to hold close to the current base case."
    elif recommendation == "Lean Buy":
        required_belief = "The key underwriting gap needs to resolve in line with the current base case."
    elif recommendation == "Hold / Dig Deeper":
        required_belief = "One missing underwriting pillar still has to be confirmed before this is actionable."
    elif recommendation == "Lean Away":
        required_belief = "The thesis only improves if basis or support moves materially in your favor."
    else:
        required_belief = "A materially better basis or cleaner evidence set would be needed to revisit the call."

    conviction_raw = ((final_score - 1.0) / 4.0) * 100.0
    conviction_raw *= 0.75 + (0.25 * max(0.0, min(view.overall_confidence, 1.0)))
    conviction_raw -= len(hard_constraints) * 12.0
    conviction_raw -= len(disqualifiers) * 6.0
    conviction_score = max(0, min(int(round(conviction_raw)), 100))

    return DecisionViewModel(
        recommendation=recommendation,
        conviction_score=conviction_score,
        best_fit=display_fit,
        confidence_level=confidence_level,
        thesis=thesis,
        decisive_driver=decisive_driver,
        break_condition=break_condition,
        required_belief=required_belief,
        primary_risk=break_condition,
        what_changes_view=required_belief,
        primary_driver=decisive_driver,
        fit_context=fit_context,
        supporting_factors=supporting_factors[:4],
        risks=risks[:3],
        dependencies=dependencies[:3],
        disqualifiers=(hard_constraints + disqualifiers)[:3],
    )

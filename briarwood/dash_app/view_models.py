from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from briarwood.reports.section_helpers import (
    get_comparable_sales,
    get_current_value,
    get_income_support,
    get_rental_ease,
    get_scarcity_support,
    get_scenario_output,
    get_town_county_outlook,
)
from briarwood.schemas import AnalysisReport, InputCoverageStatus, PropertyInput, SectionEvidence


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


def _module_confidence(report: AnalysisReport, module_name: str) -> float | None:
    module = report.module_results.get(module_name)
    return None if module is None else float(module.confidence)


def _overall_confidence(report: AnalysisReport) -> float:
    key_modules = [
        "current_value",
        "bull_base_bear",
        "town_county_outlook",
        "rental_ease",
    ]
    confidences = [_module_confidence(report, name) for name in key_modules]
    present = [value for value in confidences if value is not None]
    if not present:
        return 0.0
    return round(sum(present) / len(present), 2)


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
class EvidenceViewModel:
    evidence_mode: str
    sourced_inputs: list[str] = field(default_factory=list)
    user_supplied_inputs: list[str] = field(default_factory=list)
    estimated_inputs: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
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
    flood_risk: str
    liquidity_view: str
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
    income_support_ratio_text: str
    monthly_cash_flow_text: str
    operating_cash_flow_text: str
    rent_source_type: str
    risk_view: str
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompareMetricRow:
    metric: str
    values: dict[str, str]


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
class CompsViewModel:
    comparable_value_text: str
    comp_count_text: str
    confidence_text: str
    dataset_name: str
    verification_summary: str
    curation_summary: str
    screening_summary: str
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    rows: list[CompReviewRow] = field(default_factory=list)


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
    mispricing_amount: float | None
    mispricing_pct: float | None
    pricing_view: str
    top_positives: list[str]
    top_risks: list[str]
    metric_chips: list[MetricChip]
    value: ValueViewModel
    comps: CompsViewModel
    forward: ForwardViewModel
    income_support: IncomeSupportViewModel
    risk_location: RiskLocationViewModel
    evidence: EvidenceViewModel
    compare_metrics: dict[str, Any] = field(default_factory=dict)


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
        MetricChip(label="BCV", value=_fmt_currency(bcv)),
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


def build_property_analysis_view(report: AnalysisReport) -> PropertyAnalysisView:
    property_input = report.property_input
    current_value = get_current_value(report)
    comparable_sales = get_comparable_sales(report)
    scenario = get_scenario_output(report)
    income = get_income_support(report)
    rental_ease = get_rental_ease(report)
    town_county = get_town_county_outlook(report)
    scarcity = get_scarcity_support(report)
    risk = report.get_module("risk_constraints")
    forward_module = report.get_module("bull_base_bear")
    sourced, user_supplied, estimated, missing = _coverage_lists(property_input)
    overall_confidence = _overall_confidence(report)

    positives = list(town_county.score.demand_drivers[:2]) + list(scarcity.demand_drivers[:1])
    risks = list(rental_ease.risks[:2]) + list(town_county.score.demand_risks[:2])
    positives = [item for item in positives if item][:3]
    risks = [item for item in risks if item][:3]

    compare_metrics = {
        "ask_price": current_value.ask_price,
        "bcv": current_value.briarwood_current_value,
        "bcv_delta": current_value.mispricing_amount,
        "bcv_range": f"{current_value.value_low:,.0f}-{current_value.value_high:,.0f}",
        "forward_base_case": scenario.base_case_value,
        "lot_size": property_input.lot_size if property_input else None,
        "sqft": property_input.sqft if property_input else None,
        "taxes": property_input.taxes if property_input else None,
        "dom": property_input.days_on_market if property_input else None,
        "income_support_ratio": income.income_support_ratio,
        "risk_score": risk.score,
        "town_county_score": town_county.score.town_county_score,
        "scarcity_score": scarcity.scarcity_support_score,
        "confidence": overall_confidence,
        "missing_inputs": missing,
    }

    return PropertyAnalysisView(
        property_id=report.property_id,
        label=(property_input.address if property_input else report.address).split(",")[0],
        address=property_input.address if property_input else report.address,
        evidence_mode=(property_input.source_metadata.evidence_mode.value.replace("_", " ").title() if property_input and property_input.source_metadata else "Unknown"),
        condition_profile=((property_input.condition_profile or "Unavailable").replace("_", " ").title() if property_input else "Unavailable"),
        capex_lane=((property_input.capex_lane or "Unavailable").replace("_", " ").title() if property_input else "Unavailable"),
        overall_confidence=overall_confidence,
        ask_price=current_value.ask_price,
        bcv=current_value.briarwood_current_value,
        value_low=current_value.value_low,
        value_high=current_value.value_high,
        base_case=scenario.base_case_value,
        bull_case=scenario.bull_case_value,
        bear_case=scenario.bear_case_value,
        mispricing_amount=current_value.mispricing_amount,
        mispricing_pct=current_value.mispricing_pct,
        pricing_view=current_value.pricing_view,
        top_positives=positives,
        top_risks=risks,
        metric_chips=_metric_chips(
            ask_price=current_value.ask_price,
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
            dataset_name=comparable_sales.dataset_name or "Unavailable",
            verification_summary=comparable_sales.verification_summary or "Unavailable",
            curation_summary=comparable_sales.curation_summary or "Unavailable",
            screening_summary=_screening_summary(report),
            warnings=list(comparable_sales.warnings),
            assumptions=list(comparable_sales.assumptions),
            unsupported_claims=list(comparable_sales.unsupported_claims),
            rows=_comp_rows(report),
        ),
        forward=ForwardViewModel(
            summary=forward_module.summary,
            confidence=float(forward_module.confidence),
            bull_value_text=_fmt_currency(scenario.bull_case_value),
            base_value_text=_fmt_currency(scenario.base_case_value),
            bear_value_text=_fmt_currency(scenario.bear_case_value),
            market_drift_text=_fmt_currency(forward_module.metrics.get("market_drift")),
            location_premium_text=_fmt_currency(forward_module.metrics.get("location_premium")),
            risk_discount_text=_fmt_currency(forward_module.metrics.get("risk_discount")),
            optionality_premium_text=_fmt_currency(forward_module.metrics.get("optionality_premium")),
        ),
        income_support=IncomeSupportViewModel(
            summary=income.summary,
            confidence=float(income.confidence),
            rental_ease_label=rental_ease.rental_ease_label,
            estimated_days_to_rent_text=_fmt_number(rental_ease.estimated_days_to_rent, " days"),
            income_support_ratio_text=(f"{income.income_support_ratio:.2f}x" if income.income_support_ratio is not None else "Unavailable"),
            monthly_cash_flow_text=_fmt_currency(income.monthly_cash_flow),
            operating_cash_flow_text=_fmt_currency(income.operating_monthly_cash_flow),
            rent_source_type=income.rent_source_type.replace("_", " ").title(),
            risk_view=income.risk_view.replace("_", " ").title(),
            warnings=list(income.warnings),
            assumptions=list(income.assumptions),
            unsupported_claims=list(income.unsupported_claims),
        ),
        risk_location=RiskLocationViewModel(
            risk_summary=risk.summary,
            risk_score=float(risk.score),
            town_score=float(town_county.score.town_county_score),
            town_label=town_county.score.location_thesis_label,
            scarcity_score=float(scarcity.scarcity_support_score),
            flood_risk=property_input.flood_risk if property_input and property_input.flood_risk else "Unavailable",
            liquidity_view=town_county.score.liquidity_view,
            drivers=list(town_county.score.demand_drivers[:3]) + list(scarcity.demand_drivers[:2]),
            risks=list(town_county.score.demand_risks[:3]) + list(scarcity.scarcity_notes[:2]),
            warnings=list(risk.metrics.get("warnings", [])) if isinstance(risk.metrics.get("warnings"), list) else [],
            unsupported_claims=list(town_county.score.unsupported_claims) + list(scarcity.unsupported_claims),
        ),
        evidence=EvidenceViewModel(
            evidence_mode=(property_input.source_metadata.evidence_mode.value.replace("_", " ").title() if property_input and property_input.source_metadata else "Unknown"),
            sourced_inputs=sourced,
            user_supplied_inputs=user_supplied,
            estimated_inputs=estimated,
            missing_inputs=missing,
            unsupported_claims=_collect_unsupported_claims(report),
            section_confidences=_section_confidences(report),
        ),
        compare_metrics=compare_metrics,
    )


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

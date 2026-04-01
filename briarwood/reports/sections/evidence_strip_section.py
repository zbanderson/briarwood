from __future__ import annotations

from briarwood.evidence import infer_overall_report_confidence
from briarwood.field_audit import audit_property_fields
from briarwood.reports.section_helpers import (
    get_current_value,
    get_income_support,
    get_rental_ease,
    get_town_county_outlook,
)
from briarwood.reports.schemas import EvidenceStripSection
from briarwood.schemas import AnalysisReport, InputCoverageStatus


def build_evidence_strip_section(report: AnalysisReport) -> EvidenceStripSection:
    property_input = report.property_input
    current_value_module = report.get_module("current_value")
    scenario_module = report.get_module("bull_base_bear")
    current_value = get_current_value(report)
    income = get_income_support(report)
    rental_ease = get_rental_ease(report)
    outlook = get_town_county_outlook(report)
    town_score = outlook.score

    strongest_evidence = [
        f"Value model confidence: {current_value_module.confidence:.0%}.",
        "Town/county sentiment uses source-backed local data.",
    ]
    if any("FRED-backed" in note for note in town_score.assumptions_used):
        strongest_evidence.append("County macro sentiment is FRED-backed.")
    if rental_ease.zillow_context_used:
        strongest_evidence.append("Rental ease uses Zillow rental market context as backdrop.")

    weaker_evidence = []
    if town_score.unsupported_claims:
        weaker_evidence.append(town_score.unsupported_claims[0].rstrip(".") + ".")
    if income.effective_monthly_rent is None:
        weaker_evidence.append("Property-level rental fallback is not verified because rent is missing.")
    if report.get_module("scarcity_support").confidence < 0.5:
        weaker_evidence.append("Scarcity support is still thin and should be treated cautiously.")

    heuristic_flags = [
        "12M bull/base/bear remains a heuristic outlook.",
    ]
    if rental_ease.estimated_days_to_rent is not None:
        heuristic_flags.append("Days-to-rent is heuristic, not lease-up precision.")
    if float(rental_ease.confidence) < 0.8:
        heuristic_flags.append("Rental absorption still leans partly on Monmouth coastal priors.")

    coverage_highlights: list[str] = []
    major_missing_inputs: list[str] = []
    estimated_inputs: list[str] = []
    evidence_mode_text = "Unknown"
    overall_report_confidence_text = "n/a"
    if property_input and property_input.source_metadata:
        evidence_mode_text = property_input.source_metadata.evidence_mode.value.replace("_", " ").title()
        coverage = property_input.source_metadata.source_coverage
        for key in ("address", "price_ask", "beds_baths", "sqft", "market_history", "comp_support"):
            item = coverage.get(key)
            if item and item.status != InputCoverageStatus.MISSING:
                coverage_highlights.append(f"{item.category.replace('_', ' ').title()}: {item.status.value.replace('_', ' ')}")
        major_missing_inputs = [
            key.replace("_", " ")
            for key, item in coverage.items()
            if item.status == InputCoverageStatus.MISSING
            and key in {"rent_estimate", "insurance_estimate", "comp_support", "scarcity_inputs", "school_signal"}
        ]
        estimated_inputs = [
            key.replace("_", " ")
            for key, item in coverage.items()
            if item.status == InputCoverageStatus.ESTIMATED
        ]
        overall_report_confidence_text = f"{infer_overall_report_confidence(property_input, [module.confidence for module in report.module_results.values()]):.0%}"
    modeled_fields, non_modeled_fields = audit_property_fields(property_input) if property_input else ([], [])
    if report.get_module("market_value_history").confidence > 0:
        coverage_highlights.append("Market history: sourced")
    comparable_sales_module = report.get_module("comparable_sales")
    if int(comparable_sales_module.metrics.get("comp_count") or 0) > 0:
        coverage_highlights.append("Comp support: available")
    else:
        if "comp support" not in major_missing_inputs:
            major_missing_inputs.append("comp support")
    if income.rent_source_type == "estimated" and "rent estimate" not in estimated_inputs:
        estimated_inputs.append("rent estimate")

    return EvidenceStripSection(
        title="Confidence / Evidence",
        evidence_mode_text=evidence_mode_text,
        overall_report_confidence_text=overall_report_confidence_text,
        value_confidence_text=f"{current_value_module.confidence:.0%}",
        location_confidence_text=f"{town_score.confidence:.0%}",
        rental_confidence_text=f"{min(income.confidence, rental_ease.confidence):.0%}",
        scenario_confidence_text=(
            f"{scenario_module.confidence:.0%} | heuristic"
            if scenario_module.confidence > 0
            else "Heuristic"
        ),
        source_coverage_highlights=_dedupe(coverage_highlights)[:6],
        major_missing_inputs=_dedupe(major_missing_inputs)[:5],
        estimated_inputs=_dedupe(estimated_inputs)[:5],
        modeled_fields=[field.replace("_", " ") for field in modeled_fields[:10]],
        non_modeled_fields=[field.replace("_", " ") for field in non_modeled_fields[:10]],
        strongest_evidence=_dedupe(strongest_evidence)[:4],
        weaker_evidence=_dedupe(weaker_evidence)[:4],
        heuristic_flags=_dedupe(heuristic_flags)[:4],
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output

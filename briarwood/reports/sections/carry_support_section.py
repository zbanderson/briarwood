from __future__ import annotations

from briarwood.reports.section_helpers import get_income_support
from briarwood.reports.schemas import CarrySupportSection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_carry_support_section(report: AnalysisReport) -> CarrySupportSection:
    module = report.get_module("income_support")
    income = get_income_support(report)
    support_label = str(module.metrics.get("support_label", "unavailable")).title()
    ratio_text = (
        f"{income.income_support_ratio:.2f}x"
        if income.income_support_ratio is not None
        else "Unavailable"
    )
    cash_flow_text = (
        f"${income.estimated_monthly_cash_flow:,.0f}/mo"
        if income.estimated_monthly_cash_flow is not None
        else "Unavailable"
    )
    assessment_summary = (
        f"Fallback rent covers about {income.income_support_ratio:.0%} of monthly carrying cost."
        if income.income_support_ratio is not None
        else "Fallback rent support could not be assessed because a rent estimate is missing."
    )
    return CarrySupportSection(
        title="Fallback Rental Support",
        summary=income.explanation,
        support_label=support_label,
        income_support_ratio_text=ratio_text,
        estimated_cash_flow_text=cash_flow_text,
        warnings=income.warnings[:3],
        assessment=SectionAssessment(
            score=module.score,
            confidence=module.confidence,
            summary=assessment_summary,
        ),
    )

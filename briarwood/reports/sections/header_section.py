from __future__ import annotations

from briarwood.reports.section_helpers import get_scenario_output
from briarwood.reports.schemas import HeaderSection
from briarwood.schemas import AnalysisReport


def build_header_section(report: AnalysisReport) -> HeaderSection:
    valuation = report.get_module("cost_valuation")
    scenario = get_scenario_output(report)
    score = valuation.score
    stance = "Constructive"
    if score < 45:
        stance = "Cautious"
    elif score > 65:
        stance = "Attractive"

    spread = scenario.spread
    subtitle = (
        f"{stance} stance based on current underwriting, with "
        f"${spread:,.0f} scenario spread."
        if spread
        else f"{stance} stance based on current underwriting."
    )
    return HeaderSection(
        property_name=report.address,
        address=report.address,
        subtitle=subtitle,
        investment_stance=stance,
    )

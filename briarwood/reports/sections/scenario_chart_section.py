from __future__ import annotations

from briarwood.reports.section_helpers import get_scenario_output, get_valuation_output
from briarwood.reports.schemas import ScenarioChartSection, ScenarioPoint
from briarwood.schemas import AnalysisReport


def build_scenario_chart_section(report: AnalysisReport) -> ScenarioChartSection:
    valuation = get_valuation_output(report)
    scenario = get_scenario_output(report)
    ask_price = valuation.purchase_price
    bear_value = scenario.bear_case_value
    base_value = scenario.base_case_value
    bull_value = scenario.bull_case_value
    return ScenarioChartSection(
        chart_title="Scenario Value vs. Current Ask",
        current_ask=ask_price,
        points=[
            ScenarioPoint(label="Ask", value=ask_price),
            ScenarioPoint(label="Bear", value=bear_value),
            ScenarioPoint(label="Base", value=base_value),
            ScenarioPoint(label="Bull", value=bull_value),
        ],
        caption=(
            "The chart compares current ask to Briarwood scenario values and "
            "highlights the current underwriting range."
        ),
    )

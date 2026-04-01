from __future__ import annotations

from briarwood.reports.schemas import TearSheet
from briarwood.reports.sections.carry_support_section import build_carry_support_section
from briarwood.reports.sections.case_columns_section import build_bull_base_bear_section
from briarwood.reports.sections.comparable_sales_section import build_comparable_sales_section
from briarwood.reports.sections.conclusion_section import build_conclusion_section
from briarwood.reports.sections.evidence_strip_section import build_evidence_strip_section
from briarwood.reports.sections.header_section import build_header_section
from briarwood.reports.sections.market_durability_section import build_market_durability_section
from briarwood.reports.sections.scenario_chart_section import build_scenario_chart_section
from briarwood.reports.sections.signal_metrics_section import build_signal_metrics_section
from briarwood.reports.sections.thesis_section import build_thesis_section
from briarwood.reports.sections.investment_scenarios_section import build_investment_scenarios_section
from briarwood.schemas import AnalysisReport


def build_tear_sheet(report: AnalysisReport) -> TearSheet:
    return TearSheet(
        property_id=report.property_id,
        header=build_header_section(report),
        conclusion=build_conclusion_section(report),
        signal_metrics=build_signal_metrics_section(report),
        thesis=build_thesis_section(report),
        market_durability=build_market_durability_section(report),
        carry_support=build_carry_support_section(report),
        comparable_sales=build_comparable_sales_section(report),
        scenario_chart=build_scenario_chart_section(report),
        bull_base_bear=build_bull_base_bear_section(report),
        evidence_strip=build_evidence_strip_section(report),
        investment_scenarios=build_investment_scenarios_section(report),
    )

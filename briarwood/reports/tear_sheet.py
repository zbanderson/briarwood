from __future__ import annotations

from briarwood.reports.schemas import TearSheet
from briarwood.reports.sections.case_columns_section import build_bull_base_bear_section
from briarwood.reports.sections.conclusion_section import build_conclusion_section
from briarwood.reports.sections.header_section import build_header_section
from briarwood.reports.sections.scenario_chart_section import build_scenario_chart_section
from briarwood.reports.sections.thesis_section import build_thesis_section
from briarwood.schemas import AnalysisReport


def build_tear_sheet(report: AnalysisReport) -> TearSheet:
    return TearSheet(
        property_id=report.property_id,
        header=build_header_section(report),
        conclusion=build_conclusion_section(report),
        thesis=build_thesis_section(report),
        scenario_chart=build_scenario_chart_section(report),
        bull_base_bear=build_bull_base_bear_section(report),
    )

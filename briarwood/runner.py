from __future__ import annotations

from pathlib import Path

from briarwood.engine import AnalysisEngine
from briarwood.inputs.property_loader import load_property_from_json, load_property_from_listing_text
from briarwood.listing_intake.schemas import ListingIntakeResult
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.cost_valuation import CostValuationModule
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scarcity_support import ScarcitySupportModule
from briarwood.modules.town_county_outlook import TownCountyOutlookModule
from briarwood.schemas import AnalysisReport
from briarwood.reports.renderer import render_tear_sheet_html, write_tear_sheet_html
from briarwood.reports.tear_sheet import build_tear_sheet
from briarwood.settings import (
    BullBaseBearSettings,
    CostValuationSettings,
    RiskSettings,
)
import json


def build_engine(
    *,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
) -> AnalysisEngine:
    return AnalysisEngine(
        modules=[
            PropertySnapshotModule(),
            MarketValueHistoryModule(),
            CostValuationModule(settings=cost_settings),
            BullBaseBearModule(settings=bull_base_bear_settings),
            RiskConstraintsModule(settings=risk_settings),
            TownCountyOutlookModule(),
            ScarcitySupportModule(),
        ]
    )


def run_report(
    property_path: str | Path,
    *,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
) -> AnalysisReport:
    property_input = load_property_from_json(property_path)
    engine = build_engine(
        cost_settings=cost_settings,
        bull_base_bear_settings=bull_base_bear_settings,
        risk_settings=risk_settings,
    )
    return engine.run_all(property_input)


def run_report_from_listing_text(
    listing_text: str,
    *,
    property_id: str = "listing-intake",
    source_url: str | None = None,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
) -> AnalysisReport:
    property_input = load_property_from_listing_text(
        listing_text,
        property_id=property_id,
        source_url=source_url,
    )
    engine = build_engine(
        cost_settings=cost_settings,
        bull_base_bear_settings=bull_base_bear_settings,
        risk_settings=risk_settings,
    )
    return engine.run_all(property_input)


def preview_intake_from_listing_text(
    listing_text: str,
    *,
    source_url: str | None = None,
    intake_service: ListingIntakeService | None = None,
) -> ListingIntakeResult:
    service = intake_service or ListingIntakeService()
    return service.intake_text(listing_text, source_url=source_url)


def preview_intake_from_url(
    source_url: str,
    *,
    intake_service: ListingIntakeService | None = None,
) -> ListingIntakeResult:
    service = intake_service or ListingIntakeService()
    return service.intake_url(source_url)


def format_report(report: AnalysisReport, property_path: str | Path) -> str:
    lines = [
        f"Briarwood analysis for {report.address}",
        f"source: {property_path}",
        "",
    ]
    for name, result in report.module_results.items():
        lines.append(f"[{name}]")
        lines.append(f"score: {result.score:.1f}")
        lines.append(f"confidence: {result.confidence:.2f}")
        lines.append(f"summary: {result.summary}")
        lines.append(f"metrics: {result.metrics}")
        lines.append("")
    return "\n".join(lines)


def render_report_html(report: AnalysisReport) -> str:
    tear_sheet = build_tear_sheet(report)
    return render_tear_sheet_html(tear_sheet)


def write_report_html(report: AnalysisReport, output_path: str | Path) -> Path:
    tear_sheet = build_tear_sheet(report)
    return write_tear_sheet_html(tear_sheet, output_path)


def format_tear_sheet_summary(report: AnalysisReport) -> str:
    tear_sheet = build_tear_sheet(report)
    lines = [
        "Briarwood Tear Sheet",
        f"property: {tear_sheet.header.address}",
        "",
        "[header]",
        f"stance: {tear_sheet.header.investment_stance}",
        f"subtitle: {tear_sheet.header.subtitle}",
        "",
        "[conclusion]",
        f"ask_price: {tear_sheet.conclusion.ask_price:,.0f}",
        f"base_value: {tear_sheet.conclusion.base_value:,.0f}",
        f"bull_value: {tear_sheet.conclusion.bull_value:,.0f}",
        f"bear_value: {tear_sheet.conclusion.bear_value:,.0f}",
        f"summary: {tear_sheet.conclusion.assessment.summary}",
        "",
        "[thesis]",
        f"title: {tear_sheet.thesis.title}",
        f"summary: {tear_sheet.thesis.assessment.summary}",
        "bullets:",
    ]
    lines.extend(f"- {bullet}" for bullet in tear_sheet.thesis.bullets)
    lines.extend(
        [
            "",
            "[scenario_chart]",
            f"title: {tear_sheet.scenario_chart.chart_title}",
        ]
    )
    lines.extend(
        f"- {point.label}: {point.value:,.0f}" for point in tear_sheet.scenario_chart.points
    )
    lines.extend(
        [
            "",
            "[bull_base_bear]",
            f"- Bull Case: {tear_sheet.bull_base_bear.bull_case.assessment.summary}",
            f"- Base Case: {tear_sheet.bull_base_bear.base_case.assessment.summary}",
            f"- Bear Case: {tear_sheet.bull_base_bear.bear_case.assessment.summary}",
        ]
    )
    return "\n".join(lines)


def format_intake_preview(
    intake_result: ListingIntakeResult,
    *,
    include_raw: bool = False,
) -> str:
    lines = [
        "Briarwood Intake Preview",
        "",
        "[intake_mode]",
        intake_result.intake_mode,
        "",
        "[normalized_property_data]",
        json.dumps(intake_result.normalized_property_data.to_dict(), indent=2),
        "",
        "[missing_fields]",
        json.dumps(intake_result.missing_fields, indent=2),
        "",
        "[warnings]",
        json.dumps(intake_result.warnings, indent=2),
    ]
    if include_raw:
        lines.extend(
            [
                "",
                "[raw_extracted_data]",
                json.dumps(intake_result.raw_extracted_data.to_dict(), indent=2),
            ]
        )
    return "\n".join(lines)

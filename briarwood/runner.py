from __future__ import annotations

from pathlib import Path

from briarwood.engine import AnalysisEngine
from briarwood.inputs.property_loader import load_property_from_json, load_property_from_listing_text
from briarwood.listing_intake.schemas import ListingIntakeResult
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.cost_valuation import CostValuationModule
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.location_context import build_default_town_county_service
from briarwood.modules.location_intelligence import LocationIntelligenceModule
from briarwood.modules.liquidity_signal import LiquiditySignalModule
from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.modules.market_momentum_signal import MarketMomentumSignalModule
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.renovation_scenario import RenovationScenarioModule
from briarwood.modules.teardown_scenario import TeardownScenarioModule
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.modules.rental_ease import RentalEaseModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scarcity_support import ScarcitySupportModule
from briarwood.modules.town_county_outlook import TownCountyOutlookModule
from briarwood.schemas import AnalysisReport, PropertyInput
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
    market_value_history_module = MarketValueHistoryModule()
    comparable_sales_module = ComparableSalesModule(market_value_history_module=market_value_history_module)
    income_support_module = IncomeSupportModule(settings=cost_settings)
    current_value_module = CurrentValueModule(
        comparable_sales_module=comparable_sales_module,
        market_value_history_module=market_value_history_module,
        income_support_module=income_support_module,
    )
    risk_constraints_module = RiskConstraintsModule(settings=risk_settings)
    town_county_service = build_default_town_county_service()
    town_county_outlook_module = TownCountyOutlookModule(service=town_county_service)
    scarcity_support_module = ScarcitySupportModule(service=town_county_service)
    location_intelligence_module = LocationIntelligenceModule()
    local_intelligence_module = LocalIntelligenceModule()
    renovation_scenario_module = RenovationScenarioModule(
        comparable_sales_module=comparable_sales_module,
        current_value_module=current_value_module,
    )
    teardown_scenario_module = TeardownScenarioModule(
        comparable_sales_module=comparable_sales_module,
        current_value_module=current_value_module,
        income_support_module=income_support_module,
    )
    rental_ease_module = RentalEaseModule(
        income_support_module=income_support_module,
        town_county_outlook_module=town_county_outlook_module,
        scarcity_support_module=scarcity_support_module,
    )
    liquidity_signal_module = LiquiditySignalModule(
        comparable_sales_module=comparable_sales_module,
        rental_ease_module=rental_ease_module,
        town_county_outlook_module=town_county_outlook_module,
    )
    market_momentum_signal_module = MarketMomentumSignalModule(
        market_value_history_module=market_value_history_module,
        town_county_outlook_module=town_county_outlook_module,
        local_intelligence_module=local_intelligence_module,
    )

    return AnalysisEngine(
        modules=[
            PropertySnapshotModule(),
            market_value_history_module,
            comparable_sales_module,
            current_value_module,
            CostValuationModule(settings=cost_settings),
            income_support_module,
            rental_ease_module,
            liquidity_signal_module,
            BullBaseBearModule(
                settings=bull_base_bear_settings,
                current_value_module=current_value_module,
                market_value_history_module=market_value_history_module,
                town_county_outlook_module=town_county_outlook_module,
                risk_constraints_module=risk_constraints_module,
                scarcity_support_module=scarcity_support_module,
            ),
            risk_constraints_module,
            town_county_outlook_module,
            scarcity_support_module,
            location_intelligence_module,
            local_intelligence_module,
            market_momentum_signal_module,
            renovation_scenario_module,
            teardown_scenario_module,
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
    validate_property_input(property_input)
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
    validate_property_input(property_input)
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
        f"briarwood_current_value: {tear_sheet.conclusion.briarwood_current_value:,.0f}",
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
        "",
        "[canonical_evidence_mode]",
        intake_result.normalized_property_data.to_canonical_input().source_metadata.evidence_mode.value,
        "",
        "[source_coverage]",
        json.dumps(
            {
                key: value.status.value
                for key, value in intake_result.normalized_property_data.to_canonical_input().source_metadata.source_coverage.items()
            },
            indent=2,
        ),
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


def validate_property_input(property_input: PropertyInput) -> None:
    """Fail fast on obviously invalid inputs before running analysis."""

    numeric_validations = {
        "purchase_price": property_input.purchase_price,
        "beds": property_input.beds,
        "baths": property_input.baths,
        "sqft": property_input.sqft,
        "lot_size": property_input.lot_size,
        "taxes": property_input.taxes,
        "insurance": property_input.insurance,
        "monthly_hoa": property_input.monthly_hoa,
        "estimated_monthly_rent": property_input.estimated_monthly_rent,
    }
    invalid_negative = [
        field_name
        for field_name, value in numeric_validations.items()
        if value is not None and value < 0
    ]
    if invalid_negative:
        raise ValueError(
            "Property input contains negative values for fields that must be non-negative: "
            + ", ".join(sorted(invalid_negative))
        )

    if not property_input.address:
        raise ValueError("Property input is missing address.")
    if not property_input.town or not property_input.state:
        raise ValueError("Property input must include town and state.")

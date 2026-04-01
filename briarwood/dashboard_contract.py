from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.reports.section_helpers import (
    get_comparable_sales,
    get_current_value,
    get_income_support,
    get_location_intelligence,
    get_rental_ease,
    get_scenario_output,
    get_town_county_outlook,
)
from briarwood.scorecard import ScoreCard, build_scorecard
from briarwood.schemas import AnalysisReport


MODULE_DEPENDENCIES: dict[str, list[str]] = {
    "comparable_sales": [],
    "current_value": ["comparable_sales", "market_value_history", "income_support"],
    "income_support": [],
    "bull_base_bear": ["current_value", "income_support", "town_county_outlook", "scarcity_support", "risk_constraints"],
    "location_intelligence": ["comparable_sales"],
    "local_intelligence": [],
    "risk_constraints": [],
    "town_county_outlook": [],
    "scarcity_support": ["town_county_outlook"],
}


@dataclass(slots=True)
class DashboardSectionSummary:
    result: str
    confidence: float
    key_drivers: list[str] = field(default_factory=list)
    narrative: str = ""
    source_modules: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DashboardAnalysisSummary:
    property_id: str
    address: str
    scorecard: ScoreCard
    sections: dict[str, DashboardSectionSummary]
    module_dependencies: dict[str, list[str]]


def build_dashboard_analysis_summary(report: AnalysisReport) -> DashboardAnalysisSummary:
    current_value = get_current_value(report)
    comps = get_comparable_sales(report)
    scenario = get_scenario_output(report)
    income = get_income_support(report)
    rental = get_rental_ease(report)
    town = get_town_county_outlook(report)
    risk = report.get_module("risk_constraints")
    scarcity = report.get_module("scarcity_support")
    location = report.module_results.get("location_intelligence")
    local = report.module_results.get("local_intelligence")

    sections = {
        "value_support": DashboardSectionSummary(
            result=current_value.pricing_view,
            confidence=report.get_module("current_value").confidence,
            key_drivers=[
                f"BCV ${current_value.briarwood_current_value:,.0f}",
                f"Ask ${current_value.ask_price:,.0f}",
                f"{comps.comp_count} comps",
            ],
            narrative="BCV combines comps, market adjustment, listing alignment, and income support when available.",
            source_modules=["current_value", "comparable_sales"],
        ),
        "income_support": DashboardSectionSummary(
            result=income.rent_support_classification,
            confidence=report.get_module("income_support").confidence,
            key_drivers=[
                f"Rent source {income.rent_source_type}",
                f"Support ratio {income.income_support_ratio:.2f}x" if income.income_support_ratio is not None else "Support ratio unavailable",
                rental.rental_ease_label,
            ],
            narrative=income.summary,
            source_modules=["income_support", "rental_ease"],
        ),
        "location_quality": DashboardSectionSummary(
            result=town.score.location_thesis_label,
            confidence=(
                (
                    report.get_module("town_county_outlook").confidence
                    + report.get_module("scarcity_support").confidence
                    + (location.confidence if location is not None else 0.0)
                )
                / (3 if location is not None else 2)
            ),
            key_drivers=[
                town.score.liquidity_view,
                str(report.get_module("scarcity_support").metrics.get("scarcity_label") or "Scarcity unavailable"),
                (
                    f"Geo {get_location_intelligence(report).primary_category or 'proxy only'}"
                    if location is not None
                    else "Geo benchmarking unavailable"
                ),
            ],
            narrative="Location support blends town context, scarcity, and geo benchmarking when available.",
            source_modules=["town_county_outlook", "scarcity_support"] + (["location_intelligence"] if location is not None else []),
        ),
        "risk": DashboardSectionSummary(
            result=risk.summary,
            confidence=risk.confidence,
            key_drivers=[str(risk.metrics.get("risk_flags") or "none")],
            narrative="Risk is a guardrail layer and should be read as scenario caution, not full underwriting risk.",
            source_modules=["risk_constraints"],
        ),
        "forward": DashboardSectionSummary(
            result=f"Base ${scenario.base_case_value:,.0f}",
            confidence=report.get_module("bull_base_bear").confidence,
            key_drivers=[
                f"Bull ${scenario.bull_case_value:,.0f}",
                f"Base ${scenario.base_case_value:,.0f}",
                f"Bear ${scenario.bear_case_value:,.0f}",
            ],
            narrative=report.get_module("bull_base_bear").summary,
            source_modules=["bull_base_bear", "current_value", "income_support", "town_county_outlook", "scarcity_support", "risk_constraints"],
        ),
        "local_intelligence": DashboardSectionSummary(
            result=(
                f"{int(local.metrics.get('total_projects') or 0)} projects"
                if local is not None
                else "No local intelligence"
            ),
            confidence=(local.confidence if local is not None else 0.0),
            key_drivers=[
                (
                    f"Units {int(local.metrics.get('total_units') or 0)}"
                    if local is not None
                    else "No document set"
                ),
                (
                    f"Regulatory trend {float(local.metrics.get('regulatory_trend_score') or 0):.1f}"
                    if local is not None
                    else "No regulatory signal"
                ),
            ],
            narrative=(local.summary if local is not None else "Town-document pipeline signals have not been supplied."),
            source_modules=(["local_intelligence"] if local is not None else []),
        ),
    }

    return DashboardAnalysisSummary(
        property_id=report.property_id,
        address=report.address,
        scorecard=build_scorecard(report),
        sections=sections,
        module_dependencies=dict(MODULE_DEPENDENCIES),
    )

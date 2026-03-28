from __future__ import annotations

from briarwood.reports.section_helpers import (
    get_current_value,
    get_market_value_history,
    get_scenario_output,
    get_town_county_outlook,
    get_valuation_output,
)
from briarwood.reports.schemas import BullBaseBearSection, ScenarioCase, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_bull_base_bear_section(report: AnalysisReport) -> BullBaseBearSection:
    valuation = get_valuation_output(report)
    current_value = get_current_value(report)
    scenario = get_scenario_output(report)
    scenario_module = report.get_module("bull_base_bear")
    outlook = get_town_county_outlook(report)
    history = get_market_value_history(report)
    risk = report.get_module("risk_constraints")
    ask_price = valuation.purchase_price

    monthly_cash_flow = valuation.monthly_cash_flow
    cap_rate = valuation.cap_rate or 0.0
    gross_yield = valuation.gross_yield or 0.0
    bcv_anchor = _number(scenario_module.metrics.get("bcv_anchor"))
    market_drift = _number(scenario_module.metrics.get("market_drift"))
    location_premium = _number(scenario_module.metrics.get("location_premium"))
    risk_discount = _number(scenario_module.metrics.get("risk_discount"))
    optionality_premium = _number(scenario_module.metrics.get("optionality_premium"))
    base_growth_rate = _number(scenario_module.metrics.get("base_growth_rate"))
    bull_growth_rate = _number(scenario_module.metrics.get("bull_growth_rate"))
    bear_growth_rate = _number(scenario_module.metrics.get("bear_growth_rate"))
    risk_flags = str(risk.metrics.get("risk_flags", "none"))
    town_score = outlook.score
    town_trend = history.one_year_change_pct or 0.0
    location_driver = (
        town_score.demand_drivers[0]
        if town_score.demand_drivers
        else "Location demand remains orderly but not especially strong."
    )
    location_risk = (
        town_score.demand_risks[0]
        if town_score.demand_risks
        else "Location support weakens if the current demand backdrop loses momentum."
    )

    bull_case = ScenarioCase(
        name="Bull Case",
        scenario_value=scenario.bull_case_value,
        assumptions=[
            "Exit demand stays healthy and the market rewards supportive local conditions.",
            f"Forward value compounds at about {bull_growth_rate:.1%} over the next 12 months.",
            f"Historical market appreciation stays near {town_trend:.1%} and location remains {town_score.location_thesis_label}.",
        ],
        key_drivers=[
            f"BCV starts around ${bcv_anchor:,.0f} before the upside case adds drift and optionality.",
            location_driver,
            f"Optionality adds about ${max(optionality_premium, 0.0):,.0f} when scarcity and redevelopment support are present.",
        ],
        risk_factors=[
            "Optimistic exit assumptions may not materialize.",
            "Rate volatility can compress upside.",
        ],
        assessment=SectionAssessment(
            score=65.0,
            confidence=0.65,
            summary=(
                f"Bull case implies {_ratio(scenario.bull_case_value - ask_price, ask_price):.1%} "
                "upside from today's ask if operating support and exit sentiment both improve."
            ),
        ),
    )
    base_case = ScenarioCase(
        name="Base Case",
        scenario_value=scenario.base_case_value,
        assumptions=[
            f"BCV anchor is about ${current_value.briarwood_current_value:,.0f}.",
            f"Base case compounds at about {base_growth_rate:.1%} over the next 12 months.",
            f"Location backdrop remains {town_score.location_thesis_label} rather than improving materially.",
        ],
        key_drivers=[
            f"Market drift contributes about ${market_drift:,.0f}.",
            f"Location premium contributes about ${location_premium:,.0f}.",
            f"Optionality contributes about ${optionality_premium:,.0f}.",
            location_driver,
        ],
        risk_factors=[
            f"Risk discount removes about ${risk_discount:,.0f}.",
            f"Known flagged risks: {risk_flags}.",
            location_risk,
        ],
        assessment=SectionAssessment(
            score=58.0,
            confidence=0.8,
            summary=(
                f"Base case implies {_ratio(scenario.base_case_value - ask_price, ask_price):.1%} "
                "12-month value support versus ask under current assumptions."
            ),
        ),
    )
    bear_case = ScenarioCase(
        name="Bear Case",
        scenario_value=scenario.bear_case_value,
        assumptions=[
            "Exit pricing softens and upside assumptions compress.",
            f"Bear case assumes roughly {bear_growth_rate:.1%} forward value change over the next 12 months.",
            f"Location support slips below today's {town_score.location_thesis_label} reading.",
        ],
        key_drivers=[
            "Value support falls back toward BCV with less help from market drift and optionality.",
            "Lower optimism on exit drives the downside case.",
            "Operating leverage works against returns.",
        ],
        risk_factors=[
            "Sustained negative cash flow reduces hold flexibility.",
            f"Existing constraints can intensify: {risk_flags}.",
            location_risk,
        ],
        assessment=SectionAssessment(
            score=44.0,
            confidence=0.72,
            summary=(
                f"Bear case implies {_ratio(scenario.bear_case_value - ask_price, ask_price):.1%} "
                "12-month downside if current pressures intensify."
            ),
        ),
    )
    return BullBaseBearSection(
        bull_case=bull_case,
        base_case=base_case,
        bear_case=bear_case,
    )


def _number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator

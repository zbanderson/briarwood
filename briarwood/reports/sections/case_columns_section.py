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

    bull_market_drift = _number(scenario_module.metrics.get("bull_market_drift_pct"))
    bull_location = _number(scenario_module.metrics.get("bull_location_pct"))
    bull_risk = _number(scenario_module.metrics.get("bull_risk_pct"))
    bull_optionality = _number(scenario_module.metrics.get("bull_optionality_pct"))
    base_market_drift = _number(scenario_module.metrics.get("base_market_drift_pct"))
    base_location = _number(scenario_module.metrics.get("base_location_pct"))
    base_risk = _number(scenario_module.metrics.get("base_risk_pct"))
    base_optionality = _number(scenario_module.metrics.get("base_optionality_pct"))
    bear_market_drift = _number(scenario_module.metrics.get("bear_market_drift_pct"))
    bear_location = _number(scenario_module.metrics.get("bear_location_pct"))
    bear_risk = _number(scenario_module.metrics.get("bear_risk_pct"))
    trailing_1yr = _number(scenario_module.metrics.get("inputs_trailing_1yr"))
    town_score_val = _number(scenario_module.metrics.get("inputs_town_score"))

    bull_case = ScenarioCase(
        name="Upside Case",
        scenario_value=scenario.bull_case_value,
        implied_move_text=f"{_ratio(scenario.bull_case_value - ask_price, ask_price):+.1%} vs ask",
        assumptions=[
            "Demand stays firm.",
            f"12M value change lands near {bull_growth_rate:.1%}.",
        ],
        key_drivers=[
            f"Fair value anchor ${bcv_anchor:,.0f}.",
            f"Market drift: {bull_market_drift:+.1%}  |  Location: {bull_location:+.1%}  |  Risk: {bull_risk:+.1%}  |  Optionality: {bull_optionality:+.1%}",
            location_driver,
        ],
        risk_factors=[
            "Rates or exit demand cap upside.",
            "Optimistic location support may not stick.",
        ],
        assessment=SectionAssessment(
            score=65.0,
            confidence=0.65,
            summary="Upside case if demand and exit both hold.",
        ),
    )
    base_case = ScenarioCase(
        name="Base Case",
        scenario_value=scenario.base_case_value,
        implied_move_text=f"{_ratio(scenario.base_case_value - ask_price, ask_price):+.1%} vs ask",
        assumptions=[
            f"Fair value anchor holds near ${current_value.briarwood_current_value:,.0f}.",
            f"12M value change lands near {base_growth_rate:.1%}.",
        ],
        key_drivers=[
            f"Fair value anchor ${bcv_anchor:,.0f}.",
            f"Market drift: {base_market_drift:+.1%}  |  Location: {base_location:+.1%}  |  Risk: {base_risk:+.1%}  |  Optionality: {base_optionality:+.1%}",
            f"ZHVI trailing 1yr: {trailing_1yr:+.1%}  |  Town score: {town_score_val:.0f}/100",
        ],
        risk_factors=[
            f"Risk discount removes about ${risk_discount:,.0f}.",
            location_risk,
        ],
        assessment=SectionAssessment(
            score=58.0,
            confidence=0.8,
            summary="Most likely path if the backdrop mostly holds.",
        ),
    )
    bear_case = ScenarioCase(
        name="Downside Case",
        scenario_value=scenario.bear_case_value,
        implied_move_text=f"{_ratio(scenario.bear_case_value - ask_price, ask_price):+.1%} vs ask",
        assumptions=[
            "Exit pricing softens.",
            f"12M value change lands near {bear_growth_rate:.1%}.",
        ],
        key_drivers=[
            f"Fair value anchor ${bcv_anchor:,.0f}.",
            f"Market drift: {bear_market_drift:+.1%}  |  Location: {bear_location:+.1%}  |  Risk: {bear_risk:+.1%}",
            "Risk penalties and location discounts fully materialize in the downside scenario.",
        ],
        risk_factors=[
            "Negative carry reduces flexibility.",
            f"Existing constraints can intensify: {risk_flags}.",
            location_risk,
        ],
        assessment=SectionAssessment(
            score=44.0,
            confidence=0.72,
            summary="Downside path if carry or local support weakens.",
        ),
    )
    stress_case_value = _number(scenario_module.metrics.get("stress_case_value"))
    stress_growth_rate = _number(scenario_module.metrics.get("stress_growth_rate"))
    macro_shock_pct = _number(scenario_module.metrics.get("stress_macro_shock_pct"))
    stress_case: ScenarioCase | None = None
    if stress_case_value > 0:
        stress_case = ScenarioCase(
            name="Stress Case",
            scenario_value=stress_case_value,
            implied_move_text=f"{_ratio(stress_case_value - ask_price, ask_price):+.1%} vs ask",
            assumptions=[
                f"Macro shock of -{macro_shock_pct:.0%} from base (historical coastal correction).",
                "Not a forecast — models peak-to-trough scenarios like NJ 2008–2011.",
            ],
            key_drivers=[
                "Demand collapses following a macro shock (rates spike, recession, or similar).",
                "Exit pricing falls sharply below fair value.",
            ],
            risk_factors=[
                "Negative carry accelerates losses.",
                "Illiquidity worsens — longer hold times at distressed prices.",
            ],
            assessment=SectionAssessment(
                score=25.0,
                confidence=0.55,
                summary=(
                    f"Stress case reflects historical peak-to-trough corrections in coastal NJ markets (2008–2011). "
                    "It is not a probabilistic forecast — use it as a capital-preservation floor."
                ),
            ),
        )

    return BullBaseBearSection(
        bull_case=bull_case,
        base_case=base_case,
        bear_case=bear_case,
        stress_case=stress_case,
    )


def _number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator

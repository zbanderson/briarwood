from __future__ import annotations

from briarwood.reports.section_helpers import get_scenario_output, get_valuation_output
from briarwood.reports.schemas import BullBaseBearSection, ScenarioCase, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_bull_base_bear_section(report: AnalysisReport) -> BullBaseBearSection:
    valuation = get_valuation_output(report)
    scenario = get_scenario_output(report)
    risk = report.get_module("risk_constraints")
    town = report.get_module("town_intelligence")
    ask_price = valuation.purchase_price

    monthly_cash_flow = valuation.monthly_cash_flow
    cap_rate = valuation.cap_rate or 0.0
    gross_yield = valuation.gross_yield or 0.0
    risk_flags = str(risk.metrics.get("risk_flags", "none"))
    town_trend = _number(town.metrics.get("town_price_trend"))

    bull_case = ScenarioCase(
        name="Bull Case",
        scenario_value=scenario.bull_case_value,
        assumptions=[
            "Strong exit environment and stable financing backdrop.",
            f"Town price trend continues around {town_trend:.1%}.",
            "Rent support remains intact with limited vacancy drag.",
        ],
        key_drivers=[
            f"Scenario upside benefits from current gross yield of {gross_yield:.1%}.",
            "Positive market sentiment expands valuation range.",
            "Execution risk remains manageable.",
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
                "upside if operating support and exit sentiment both improve."
            ),
        ),
    )
    base_case = ScenarioCase(
        name="Base Case",
        scenario_value=scenario.base_case_value,
        assumptions=[
            f"Current underwriting implies a {cap_rate:.1%} cap rate.",
            f"Monthly cash flow remains around ${monthly_cash_flow:,.0f}.",
            "No major change to property quality or town profile.",
        ],
        key_drivers=[
            "Value anchored to current purchase underwriting.",
            "Moderate scenario uplift relative to ask.",
            "Town quality and demand support hold steady.",
        ],
        risk_factors=[
            f"Known flagged risks: {risk_flags}.",
            "Execution remains sensitive to financing costs.",
        ],
        assessment=SectionAssessment(
            score=58.0,
            confidence=0.8,
            summary=(
                f"Base case implies {_ratio(scenario.base_case_value - ask_price, ask_price):.1%} "
                "value support versus ask under current assumptions."
            ),
        ),
    )
    bear_case = ScenarioCase(
        name="Bear Case",
        scenario_value=scenario.bear_case_value,
        assumptions=[
            "Exit pricing softens and upside assumptions compress.",
            "Cash flow remains pressured.",
            "Diligence uncovers additional friction or capex needs.",
        ],
        key_drivers=[
            "Value support falls back toward current income profile.",
            "Lower optimism on exit drives the downside case.",
            "Operating leverage works against returns.",
        ],
        risk_factors=[
            "Sustained negative cash flow reduces hold flexibility.",
            f"Existing constraints can intensify: {risk_flags}.",
        ],
        assessment=SectionAssessment(
            score=44.0,
            confidence=0.72,
            summary=(
                f"Bear case implies {_ratio(scenario.bear_case_value - ask_price, ask_price):.1%} "
                "downside if current pressures intensify."
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

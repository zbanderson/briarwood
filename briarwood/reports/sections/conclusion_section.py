from __future__ import annotations

from briarwood.reports.section_helpers import get_scenario_output, get_valuation_output
from briarwood.reports.schemas import ConclusionSection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_conclusion_section(report: AnalysisReport) -> ConclusionSection:
    valuation_module = report.get_module("cost_valuation")
    valuation = get_valuation_output(report)
    scenario = get_scenario_output(report)
    ask_price = valuation.purchase_price
    base_value = scenario.base_case_value
    bull_value = scenario.bull_case_value
    bear_value = scenario.bear_case_value
    cap_rate = valuation.cap_rate
    cash_flow = valuation.monthly_cash_flow
    premium_discount_to_ask = _ratio(base_value - ask_price, ask_price)
    upside_to_bull = _ratio(bull_value - ask_price, ask_price)
    downside_to_bear = _ratio(bear_value - ask_price, ask_price)
    summary = (
        f"Value is triangulated from purchase underwriting, rent support, "
        f"scenario outputs, and cash flow. Current base math implies a "
        f"{_format_percent(cap_rate)} cap rate and monthly cash flow of "
        f"${cash_flow:,.0f}."
    )
    return ConclusionSection(
        ask_price=ask_price,
        base_value=base_value,
        bull_value=bull_value,
        bear_value=bear_value,
        value_range_low=bear_value,
        value_range_high=bull_value,
        premium_discount_to_ask=premium_discount_to_ask,
        explanation=summary,
        assessment=SectionAssessment(
            score=valuation_module.score,
            confidence=valuation_module.confidence,
            summary=(
                f"Base value sits at {_format_percent(premium_discount_to_ask)} versus ask, "
                f"with downside to bear of {_format_percent(downside_to_bear)} and upside to "
                f"bull of {_format_percent(upside_to_bull)}."
            ),
        ),
    )


def _format_percent(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1%}"
    return "n/a"


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator

from __future__ import annotations

from briarwood.reports.section_helpers import get_current_value, get_scenario_output
from briarwood.reports.schemas import ConclusionSection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_conclusion_section(report: AnalysisReport) -> ConclusionSection:
    current_value_module = report.get_module("current_value")
    current_value = get_current_value(report)
    scenario = get_scenario_output(report)
    ask_price = current_value.ask_price
    briarwood_current_value = current_value.briarwood_current_value
    bull_value = scenario.bull_case_value
    bear_value = scenario.bear_case_value
    premium_discount_to_ask = current_value.mispricing_pct
    upside_to_bull = _ratio(bull_value - ask_price, ask_price)
    downside_to_bear = _ratio(bear_value - ask_price, ask_price)
    summary = (
        f"Briarwood Current Value is anchored at {_currency(briarwood_current_value)} with a range of "
        f"{_currency(current_value.value_low)} to {_currency(current_value.value_high)}. "
        f"That reads as {current_value.pricing_view} versus the ask, based on market history, "
        "property adjustment, listing alignment, and income support when available. "
        "The bull, base, and bear figures below are a separate 12-month outlook, not today's value."
    )
    return ConclusionSection(
        ask_price=ask_price,
        briarwood_current_value=briarwood_current_value,
        bull_value=bull_value,
        bear_value=bear_value,
        value_range_low=current_value.value_low,
        value_range_high=current_value.value_high,
        premium_discount_to_ask=premium_discount_to_ask,
        pricing_view=current_value.pricing_view,
        explanation=summary,
        assessment=SectionAssessment(
            score=current_value_module.score,
            confidence=current_value_module.confidence,
            summary=(
                f"Today, BCV sits at {_format_percent(premium_discount_to_ask)} versus ask. "
                f"From there, the 12-month outlook ranges from {_format_percent(downside_to_bear)} downside "
                f"to {_format_percent(upside_to_bull)} upside."
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


def _currency(value: float) -> str:
    return f"${value:,.0f}"

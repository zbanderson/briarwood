from __future__ import annotations

from briarwood.decision_engine import build_decision
from briarwood.reports.section_helpers import get_current_value, get_income_support, get_scenario_output
from briarwood.reports.schemas import ConclusionSection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_conclusion_section(report: AnalysisReport) -> ConclusionSection:
    current_value_module = report.get_module("current_value")
    current_value = get_current_value(report)
    income = get_income_support(report)
    scenario = get_scenario_output(report)
    decision = build_decision(report)

    ask_price = current_value.ask_price
    briarwood_current_value = current_value.briarwood_current_value
    bull_value = scenario.bull_case_value
    bear_value = scenario.bear_case_value
    premium_discount_to_ask = current_value.mispricing_pct
    downside_to_bear = _ratio((bear_value - ask_price) if bear_value is not None and ask_price is not None else None, ask_price)
    upside_to_bull = _ratio((bull_value - ask_price) if bull_value is not None and ask_price is not None else None, ask_price)
    cash_flow = income.monthly_cash_flow

    key_line = f"{decision.primary_reason} {decision.secondary_reason}".strip()
    why_it_matters = [item for item in [decision.primary_reason, decision.secondary_reason] if item]

    return ConclusionSection(
        verdict=decision.recommendation,
        key_line=key_line,
        ask_price=ask_price,
        briarwood_current_value=briarwood_current_value,
        bull_value=bull_value,
        bear_value=bear_value,
        value_range_low=current_value.value_low,
        value_range_high=current_value.value_high,
        premium_discount_to_ask=premium_discount_to_ask,
        pricing_view=current_value.pricing_view,
        cash_flow_text=_cash_flow_text(cash_flow),
        top_risk=decision.required_beliefs[0] if decision.required_beliefs else "No primary risk identified.",
        why_it_matters=why_it_matters,
        decision_fit=list(decision.required_beliefs),
        what_changes_call=list(decision.required_beliefs),
        explanation="The decision call is anchored to price versus fair value, carry, and evidence quality.",
        assessment=SectionAssessment(
            score=current_value_module.score,
            confidence=decision.conviction,
            summary=(
                f"{decision.recommendation}. "
                f"12M range: {_format_percent(downside_to_bear)} to {_format_percent(upside_to_bull)}."
            ),
        ),
    )


def _format_percent(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1%}"
    return "n/a"


def _ratio(numerator: float | None, denominator: float | None) -> float:
    if numerator is None or denominator in (None, 0):
        return 0.0
    return numerator / denominator


def _cash_flow_text(value: float | None) -> str:
    if value is None:
        return "Unverified"
    return f"{value:+,.0f}/mo".replace("+", "$").replace("-", "-$")

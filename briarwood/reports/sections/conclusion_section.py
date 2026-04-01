from __future__ import annotations

from briarwood.reports.section_helpers import get_current_value, get_income_support, get_scenario_output
from briarwood.reports.schemas import ConclusionSection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_conclusion_section(report: AnalysisReport) -> ConclusionSection:
    current_value_module = report.get_module("current_value")
    current_value = get_current_value(report)
    income = get_income_support(report)
    outlook = report.get_module("town_county_outlook")
    scenario = get_scenario_output(report)
    ask_price = current_value.ask_price
    briarwood_current_value = current_value.briarwood_current_value
    bull_value = scenario.bull_case_value
    bear_value = scenario.bear_case_value
    premium_discount_to_ask = current_value.mispricing_pct
    upside_to_bull = _ratio(bull_value - ask_price, ask_price)
    downside_to_bear = _ratio(bear_value - ask_price, ask_price)
    cash_flow = income.monthly_cash_flow
    location_label = str(outlook.metrics.get("location_thesis_label", "mixed")).replace("_", " ")

    verdict = _build_verdict(
        pricing_view=current_value.pricing_view,
        cash_flow=cash_flow,
        location_label=location_label,
    )
    key_line = (
        f"Ask: {_currency(ask_price)} | BCV: {_currency(briarwood_current_value)} | "
        f"Gap: {_format_percent(premium_discount_to_ask)} | "
        f"Cash Flow: {_cash_flow_text(cash_flow)}"
    )
    why_it_matters = _build_why_it_matters(
        premium_discount_to_ask=premium_discount_to_ask,
        cash_flow=cash_flow,
        location_label=location_label,
        downside_to_bear=downside_to_bear,
    )
    decision_fit = _build_decision_fit(
        pricing_view=current_value.pricing_view,
        cash_flow=cash_flow,
        location_label=location_label,
        rent_verified=income.rent_coverage is not None,
    )
    what_changes_call = _build_what_changes_call(
        premium_discount_to_ask=premium_discount_to_ask,
        cash_flow=cash_flow,
        location_label=location_label,
        rent_verified=income.rent_coverage is not None,
    )
    return ConclusionSection(
        verdict=verdict,
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
        top_risk=_build_top_risk(
            premium_discount_to_ask=premium_discount_to_ask,
            cash_flow=cash_flow,
            location_label=location_label,
        ),
        why_it_matters=why_it_matters,
        decision_fit=decision_fit,
        what_changes_call=what_changes_call,
        explanation="BCV anchors today; scenarios show the 12-month range.",
        assessment=SectionAssessment(
            score=current_value_module.score,
            confidence=current_value_module.confidence,
            summary=(
                f"BCV is {_format_percent(premium_discount_to_ask)} versus ask. "
                f"12M range: {_format_percent(downside_to_bear)} to {_format_percent(upside_to_bull)}."
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


def _cash_flow_text(value: float | None) -> str:
    if value is None:
        return "Unverified"
    return f"{value:+,.0f}/mo".replace("+", "$").replace("-", "-$")


def _build_verdict(*, pricing_view: str, cash_flow: float | None, location_label: str) -> str:
    if pricing_view == "appears overpriced" and (cash_flow is None or cash_flow < 0):
        return f"Overpriced with weak carry support"
    if pricing_view == "appears fairly priced" and cash_flow is not None and cash_flow >= 0:
        return "Fairly priced with usable income support"
    if pricing_view == "appears undervalued" and location_label == "supportive":
        return "Valuation support with constructive location backdrop"
    return f"{pricing_view.replace('appears ', '').capitalize()} with {location_label} location support"


def _build_why_it_matters(
    *,
    premium_discount_to_ask: float,
    cash_flow: float | None,
    location_label: str,
    downside_to_bear: float,
) -> list[str]:
    bullets: list[str] = []
    if premium_discount_to_ask < 0:
        bullets.append(f"Ask is {abs(premium_discount_to_ask):.1%} above BCV.")
    else:
        bullets.append(f"BCV is {premium_discount_to_ask:.1%} above ask.")

    if cash_flow is None:
        bullets.append("Rental fallback is unverified.")
    elif cash_flow < 0:
        bullets.append(f"Carry is {_cash_flow_text(cash_flow)}.")
    else:
        bullets.append(f"Carry is {_cash_flow_text(cash_flow)}.")

    if location_label == "supportive":
        bullets.append("Location helps, but leaves little room for error.")
    else:
        bullets.append(f"Location reads {location_label}.")

    if downside_to_bear < -0.08 and len(bullets) < 3:
        bullets.append("Bear case still shows real downside.")
    return bullets[:3]


def _build_decision_fit(
    *,
    pricing_view: str,
    cash_flow: float | None,
    location_label: str,
    rent_verified: bool,
) -> list[str]:
    primary = (
        "Primary home: works if location value matters more than current economics."
        if location_label == "supportive"
        else "Primary home: depends more on personal use than investment support."
    )
    investor = (
        "Investor: weak under current carry."
        if cash_flow is None or cash_flow < 0
        else "Investor: workable if rent assumptions hold."
    )
    hybrid = (
        "Hybrid: fallback depends on rental support being verified."
        if not rent_verified
        else "Hybrid: more defensible if seasonal or fallback rent is realistic."
    )
    realtor = (
        "Realtor angle: supportive location narrative, but pricing needs discipline."
        if pricing_view == "appears overpriced"
        else "Realtor angle: valuation and location can be framed together."
    )
    return [primary, investor, hybrid, realtor]


def _build_top_risk(
    *,
    premium_discount_to_ask: float,
    cash_flow: float | None,
    location_label: str,
) -> str:
    if cash_flow is None:
        return "Rental fallback is not verified."
    if cash_flow < 0:
        return f"Negative carry runs {_cash_flow_text(cash_flow)}."
    if premium_discount_to_ask < 0:
        return f"Pricing still sits {abs(premium_discount_to_ask):.1%} above BCV."
    if location_label != "supportive":
        return f"Location support reads only {location_label}."
    return "Main risk is execution rather than obvious carry stress."


def _build_what_changes_call(
    *,
    premium_discount_to_ask: float,
    cash_flow: float | None,
    location_label: str,
    rent_verified: bool,
) -> list[str]:
    bullets: list[str] = []
    if premium_discount_to_ask < 0:
        bullets.append(f"Ask moves closer to BCV by roughly {abs(premium_discount_to_ask):.1%}.")
    else:
        bullets.append("BCV support remains intact instead of fading.")

    if cash_flow is None:
        bullets.append("Rental fallback gets verified with real rent and financing inputs.")
    elif cash_flow < 0:
        bullets.append("Carry improves toward breakeven or better.")
    else:
        bullets.append("Current carry support holds.")

    if location_label != "supportive":
        bullets.append("Location and demand signals improve.")
    elif not rent_verified:
        bullets.append("Rent and comp evidence deepen beyond directional support.")
    else:
        bullets.append("Evidence quality improves through stronger comps or direct rent support.")
    return bullets[:3]

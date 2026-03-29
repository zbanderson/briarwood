from __future__ import annotations

from briarwood.reports.section_helpers import (
    get_current_value,
    get_market_value_history,
    get_town_county_outlook,
    get_valuation_output,
)
from briarwood.reports.schemas import SectionAssessment, ThesisSection
from briarwood.schemas import AnalysisReport


def build_thesis_section(report: AnalysisReport) -> ThesisSection:
    valuation_module = report.get_module("cost_valuation")
    valuation = get_valuation_output(report)
    current_value = get_current_value(report)
    scenario = report.get_module("bull_base_bear")
    risk = report.get_module("risk_constraints")
    outlook = get_town_county_outlook(report)
    history = get_market_value_history(report)
    snapshot = report.get_module("property_snapshot")

    cap_rate = valuation.cap_rate
    cash_flow = valuation.monthly_cash_flow
    property_age = snapshot.metrics.get("property_age")
    risk_flags = str(risk.metrics.get("risk_flags", "none"))
    town_score = outlook.score
    one_year_change = history.one_year_change_pct
    premium_discount = current_value.mispricing_pct
    thesis_label = _classify_thesis(cash_flow, premium_discount)
    must_go_right = _must_go_right(town_score, one_year_change, cash_flow)
    what_breaks = _what_breaks(
        property_age=property_age,
        risk_flags=risk_flags,
        unsupported_claims=town_score.unsupported_claims,
        cash_flow=cash_flow,
    )
    so_what = _so_what(
        cap_rate=cap_rate,
        cash_flow=cash_flow,
        premium_discount=premium_discount,
        pricing_view=current_value.pricing_view,
    )
    return ThesisSection(
        title="Thesis",
        deal_type=thesis_label,
        must_go_right=must_go_right,
        what_breaks=what_breaks,
        so_what=so_what,
        assessment=SectionAssessment(
            score=valuation_module.score,
            confidence=min(valuation_module.confidence, risk.confidence, town_score.confidence),
            summary="Decision comes down to valuation cushion, carry, and whether location support offsets execution risk.",
        ),
    )


def _number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _percent_or_na(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1%}"
    return "n/a"


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _classify_thesis(cash_flow: object, premium_discount: float) -> str:
    monthly_cash_flow = _number(cash_flow)
    if monthly_cash_flow >= 0 and premium_discount >= 0:
        return "income-supported upside case"
    if monthly_cash_flow < 0 and premium_discount >= 0:
        return "appreciation-led but valuation-supported case"
    if monthly_cash_flow >= 0 and premium_discount < 0:
        return "current-yield hold with limited valuation cushion"
    return "thin-support, execution-sensitive case"


def _must_go_right(town_score: object, one_year_change: float | None, cash_flow: object) -> list[str]:
    bullets: list[str] = []
    if town_score.demand_drivers:
        bullets.append(town_score.demand_drivers[0].rstrip("."))
    if one_year_change is not None:
        bullets.append(f"Market drift holds near {_percent_or_na(one_year_change)}.")
    if _number(cash_flow) < 0:
        bullets.append("Negative carry does not widen materially.")
    else:
        bullets.append("Income support stays intact.")
    return bullets[:3]


def _what_breaks(
    *,
    property_age: object,
    risk_flags: str,
    unsupported_claims: list[str],
    cash_flow: object,
) -> list[str]:
    bullets: list[str] = []
    if _number(cash_flow) < 0:
        bullets.append("Negative carry persists.")
    if isinstance(property_age, (int, float)) and property_age >= 30:
        bullets.append("Older housing stock leads to surprise spend.")
    if risk_flags != "none":
        bullets.append(f"Flagged risks worsen: {risk_flags}.")
    if unsupported_claims:
        bullets.append(unsupported_claims[0].rstrip("."))
    if not bullets:
        bullets.append("Location support softens before value catches up.")
    return bullets[:3]


def _so_what(
    *,
    cap_rate: float | None,
    cash_flow: object,
    premium_discount: float,
    pricing_view: str,
) -> list[str]:
    carry_text = (
        f"Carry runs around ${_number(cash_flow):,.0f}/mo."
        if isinstance(cash_flow, (int, float))
        else "Carry is not fully verified."
    )
    return [
        f"Pricing reads {pricing_view.replace('appears ', '')}.",
        f"Cap rate is {_percent_or_na(cap_rate)}; {carry_text}",
        (
            f"Margin for error is limited with BCV {_percent_or_na(premium_discount)} versus ask."
            if premium_discount < 0
            else f"BCV shows {_percent_or_na(premium_discount)} support versus ask."
        ),
    ]

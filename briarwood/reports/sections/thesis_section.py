from __future__ import annotations

from briarwood.reports.section_helpers import (
    get_market_value_history,
    get_town_county_outlook,
    get_valuation_output,
)
from briarwood.reports.schemas import SectionAssessment, ThesisSection
from briarwood.schemas import AnalysisReport


def build_thesis_section(report: AnalysisReport) -> ThesisSection:
    valuation_module = report.get_module("cost_valuation")
    valuation = get_valuation_output(report)
    scenario = report.get_module("bull_base_bear")
    risk = report.get_module("risk_constraints")
    outlook = get_town_county_outlook(report)
    history = get_market_value_history(report)
    snapshot = report.get_module("property_snapshot")

    cap_rate = valuation.cap_rate
    cash_flow = valuation.monthly_cash_flow
    base_case_value = float(scenario.metrics.get("base_case_value", valuation.purchase_price))
    ask_price = valuation.purchase_price
    property_age = snapshot.metrics.get("property_age")
    risk_flags = str(risk.metrics.get("risk_flags", "none"))
    town_score = outlook.score
    one_year_change = history.one_year_change_pct
    premium_discount = _ratio(base_case_value - ask_price, ask_price)
    thesis_label = _classify_thesis(cash_flow, premium_discount)
    must_be_true = _must_be_true(town_score, one_year_change)
    breaks_it = _breaks_it(
        property_age=property_age,
        risk_flags=risk_flags,
        unsupported_claims=town_score.unsupported_claims,
    )

    bullets = [
        f"What this is: {thesis_label}",
        f"Why it matters: the asset is underwriting to {_percent_or_na(cap_rate)} cap rate with monthly cash flow around ${_number(cash_flow):,.0f}, so the case depends on {'current income support' if _number(cash_flow) >= 0 else 'future value creation more than present income'}.",
        f"What must be true: {must_be_true}",
        f"What breaks it: {breaks_it}",
        f"So what: versus today's ask, Briarwood's base case is {_percent_or_na(premium_discount)} {'above' if premium_discount >= 0 else 'below'} the market marker, which frames this as a {'supported' if premium_discount >= 0 else 'fragile'} underwriting story rather than just a collection of metrics.",
    ]
    summary = (
        f"Briarwood reads this as a {thesis_label.lower()}: the numbers matter because they tell us whether "
        "the asset is already paying for itself, or whether the return story depends on appreciation, cleaner execution, and future multiple support."
    )
    return ThesisSection(
        title="Why This Matters",
        bullets=bullets,
        assessment=SectionAssessment(
            score=valuation_module.score,
            confidence=min(valuation_module.confidence, risk.confidence, town_score.confidence),
            summary=summary,
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


def _must_be_true(town_score: object, one_year_change: float | None) -> str:
    if town_score.demand_drivers:
        primary_driver = town_score.demand_drivers[0].rstrip(".").lower()
        if one_year_change is not None:
            return (
                f"the location thesis needs to stay {town_score.location_thesis_label}, with {primary_driver} "
                f"and historical market momentum holding near {_percent_or_na(one_year_change)}."
            )
        return f"the location thesis needs to stay {town_score.location_thesis_label}, with {primary_driver}."
    if one_year_change is not None:
        return f"historical market momentum needs to stay near {_percent_or_na(one_year_change)} and execution cannot add materially more drag."
    return "the location backdrop needs to remain supportive enough that current pressures do not widen."


def _breaks_it(
    *,
    property_age: object,
    risk_flags: str,
    unsupported_claims: list[str],
) -> str:
    evidence_gap = unsupported_claims[0].rstrip(".").lower() if unsupported_claims else None
    if isinstance(property_age, (int, float)):
        base = (
            f"downside grows quickly if negative carry persists, the property's age ({int(property_age)} years) "
            f"leads to surprise spend, or these risks worsen: {risk_flags}."
        )
    else:
        base = f"downside grows quickly if carry remains weak or these risks worsen: {risk_flags}."
    if evidence_gap:
        return f"{base[:-1]} It also becomes harder to lean on the location thesis if {evidence_gap}."
    return base

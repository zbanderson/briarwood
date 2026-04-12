"""Price sensitivity analysis — recompute verdict, carry, FV gap, and risk at
multiple entry prices to surface clear action thresholds.

The curve is computed by applying the *actual* decision-engine and risk-bar
formulas at each price point (not by interpolating).  Metrics that don't
depend on entry price (fair value, comps, evidence quality) are held constant
from the original report; price-dependent metrics (mortgage carry, mispricing,
income-support ratio) are recomputed from scratch using the real amortisation
formula.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from briarwood.agents.income.finance import (
    calculate_loan_amount,
    calculate_monthly_principal_interest,
)
from briarwood.decision_engine import (
    _carry_band,
    _conviction,
    _recommendation_from_bands,
    _valuation_band,
)
from briarwood.risk_bar import (
    _carry_ratio_risk_score,
    _clamp_score,
    _monthly_shortfall_risk_score,
    _risk_level,
)
from briarwood.schemas import AnalysisReport


# ── Public types ─────────────────────────────────────────────────────────────


class DealCurvePoint(TypedDict):
    price: float
    pct_of_ask: float
    verdict: str
    carry: float | None
    fv_gap: float | None
    risk: int
    conviction: float


class DealCurveThresholds(TypedDict):
    pass_above: float | None
    interesting: float | None
    buy_below: float | None


# ── Internal helpers ─────────────────────────────────────────────────────────

_PRICE_FRACTIONS: tuple[float, ...] = (1.00, 0.95, 0.90, 0.85)

_BUY_VERDICTS = frozenset({"BUY", "LEAN BUY"})
_PASS_VERDICTS = frozenset({"LEAN PASS", "AVOID"})


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _recompute_at_price(
    entry_price: float,
    *,
    fair_value: float,
    effective_monthly_rent: float | None,
    down_payment_pct: float,
    interest_rate: float,
    loan_term_years: int,
    monthly_taxes: float,
    monthly_insurance: float,
    monthly_hoa: float,
    maintenance_pct: float,
    evidence_quality: float,
    base_price_risk: int,
    base_liquidity_risk: int,
    base_execution_risk: int,
    base_confidence_risk: int,
) -> DealCurvePoint:
    """Recompute all four metrics from first principles at *entry_price*."""

    # ── FV gap ───────────────────────────────────────────────────────────
    fv_gap = (fair_value - entry_price) / entry_price if entry_price else None

    # ── Monthly carry ────────────────────────────────────────────────────
    loan_amount = calculate_loan_amount(entry_price, down_payment_pct)
    pi = calculate_monthly_principal_interest(
        principal=loan_amount,
        annual_interest_rate=interest_rate,
        loan_term_years=loan_term_years,
    )
    monthly_maintenance = entry_price * maintenance_pct / 12
    gross_monthly_cost = pi + monthly_taxes + monthly_insurance + monthly_hoa + monthly_maintenance

    monthly_carry: float | None = None
    income_support_ratio: float | None = None
    if effective_monthly_rent is not None:
        monthly_carry = effective_monthly_rent - gross_monthly_cost
        income_support_ratio = (
            effective_monthly_rent / gross_monthly_cost
            if gross_monthly_cost > 0
            else None
        )

    # ── Recommendation (decision engine) ─────────────────────────────────
    v_band = _valuation_band(fv_gap)
    c_band = _carry_band(monthly_carry, income_support_ratio)
    recommendation = _recommendation_from_bands(
        valuation_band=v_band,
        carry_band=c_band,
        fair_value_gap=fv_gap,
        monthly_carry=monthly_carry,
        income_support_ratio=income_support_ratio,
    )
    conviction = _conviction(
        recommendation=recommendation,
        valuation_band=v_band,
        carry_band=c_band,
        evidence_quality=evidence_quality,
    )

    # ── Risk score (price + carry recomputed, others held) ───────────────
    # Price risk
    premium_gap = max(0.0, -(fv_gap or 0.0))
    discount_gap = max(0.0, fv_gap or 0.0)
    price_risk_raw = (premium_gap * 340.0) - (discount_gap * 120.0)
    price_risk = _clamp_score(price_risk_raw)

    # Carry risk
    carry_ratio_score = _carry_ratio_risk_score(income_support_ratio)
    carry_shortfall_score = _monthly_shortfall_risk_score(monthly_carry)
    carry_risk = _clamp_score((carry_ratio_score * 0.65) + (carry_shortfall_score * 0.35))

    # Composite risk — average of all five categories
    composite_risk = _clamp_score(
        (price_risk + carry_risk + base_liquidity_risk + base_execution_risk + base_confidence_risk) / 5
    )

    return DealCurvePoint(
        price=round(entry_price, 0),
        pct_of_ask=round(entry_price / (entry_price / 1.0), 2) if entry_price else 1.0,
        verdict=recommendation,
        carry=round(monthly_carry, 2) if monthly_carry is not None else None,
        fv_gap=round(fv_gap, 4) if fv_gap is not None else None,
        risk=composite_risk,
        conviction=round(conviction, 2),
    )


# ── Public API ───────────────────────────────────────────────────────────────


def build_deal_curve(report: AnalysisReport) -> list[DealCurvePoint]:
    """Generate price sensitivity points at 100%, 95%, 90%, and 85% of ask.

    Each point is independently recomputed through the decision-engine and
    risk-bar formulas — not interpolated.
    """
    pi = report.property_input
    if pi is None or pi.purchase_price is None:
        return []

    ask_price = pi.purchase_price

    # ── Fixed inputs (don't change with price) ───────────────────────────
    cv = report.module_results.get("current_value")
    cv_metrics = cv.metrics if cv is not None else {}
    fair_value = _as_float(cv_metrics.get("briarwood_current_value"))
    if fair_value is None:
        return []

    income = report.module_results.get("income_support")
    income_metrics = income.metrics if income is not None else {}
    effective_monthly_rent = _as_float(
        income_metrics.get("effective_monthly_rent")
    ) or _as_float(
        income_metrics.get("monthly_rent_estimate")
    )

    # Financing parameters
    down_payment_pct = pi.down_payment_percent or 0.20
    interest_rate = pi.interest_rate or 0.07
    loan_term_years = pi.loan_term_years or 30
    monthly_taxes = (pi.taxes or 0.0) / 12
    monthly_insurance = (pi.insurance or 0.0) / 12
    monthly_hoa = pi.monthly_hoa or 0.0
    maintenance_pct = 0.0  # mirrors IncomeAgent default when not provided

    # Evidence quality (held constant)
    from briarwood.decision_engine import _evidence_quality

    comp_mod = report.module_results.get("comparable_sales")
    pdq_mod = report.module_results.get("property_data_quality")
    town_mod = report.module_results.get("town_county_outlook")
    evidence_quality = _evidence_quality(
        current_confidence=_as_float(getattr(cv, "confidence", None)) or 0.0,
        income_confidence=_as_float(getattr(income, "confidence", None)) or 0.0,
        comp_confidence=_as_float(
            (comp_mod.metrics if comp_mod else {}).get("comp_confidence")
        ) or _as_float(getattr(comp_mod, "confidence", None)) or 0.0,
        property_quality_confidence=_as_float(getattr(pdq_mod, "confidence", None)) or 0.0,
        town_confidence=_as_float(getattr(town_mod, "confidence", None)) or 0.0,
    )

    # Non-price-dependent risk scores (held constant)
    from briarwood.risk_bar import (
        _confidence_risk,
        _execution_risk,
        _liquidity_risk,
    )

    base_liquidity_risk = _liquidity_risk(report).score
    base_execution_risk = _execution_risk(report).score
    base_confidence_risk = _confidence_risk(report).score

    # ── Build curve ──────────────────────────────────────────────────────
    points: list[DealCurvePoint] = []
    for frac in _PRICE_FRACTIONS:
        entry = ask_price * frac
        point = _recompute_at_price(
            entry,
            fair_value=fair_value,
            effective_monthly_rent=effective_monthly_rent,
            down_payment_pct=down_payment_pct,
            interest_rate=interest_rate,
            loan_term_years=loan_term_years,
            monthly_taxes=monthly_taxes,
            monthly_insurance=monthly_insurance,
            monthly_hoa=monthly_hoa,
            maintenance_pct=maintenance_pct,
            evidence_quality=evidence_quality,
            base_price_risk=0,  # not used in composite; price_risk is recomputed
            base_liquidity_risk=base_liquidity_risk,
            base_execution_risk=base_execution_risk,
            base_confidence_risk=base_confidence_risk,
        )
        # Patch pct_of_ask to the actual fraction
        point["pct_of_ask"] = frac
        points.append(point)

    return points


def extract_thresholds(curve: list[DealCurvePoint]) -> DealCurveThresholds:
    """Walk the curve to find price boundaries where the verdict changes.

    Returns three threshold prices:
    - pass_above: the highest price where the verdict is still LEAN PASS/AVOID
                  (buy above this and you're likely overpaying)
    - interesting: the price where the verdict shifts to NEUTRAL
    - buy_below:  the lowest price that still produces BUY/LEAN BUY
    """
    if not curve:
        return DealCurveThresholds(pass_above=None, interesting=None, buy_below=None)

    # Sort by price descending (100% → 85%)
    ordered = sorted(curve, key=lambda p: p["price"], reverse=True)

    pass_above: float | None = None
    interesting: float | None = None
    buy_below: float | None = None

    for point in ordered:
        verdict = point["verdict"]
        if verdict in _PASS_VERDICTS:
            pass_above = point["price"]
        elif verdict == "NEUTRAL" and interesting is None:
            interesting = point["price"]
        elif verdict in _BUY_VERDICTS:
            buy_below = point["price"]

    # Edge cases: if all points produce the same verdict
    verdicts = {p["verdict"] for p in ordered}
    if verdicts <= _PASS_VERDICTS:
        # All are pass/avoid — pass_above is the lowest tested price
        pass_above = ordered[-1]["price"]
    elif verdicts <= _BUY_VERDICTS:
        # All are buy — buy_below is the highest tested price
        buy_below = ordered[0]["price"]
    elif verdicts == {"NEUTRAL"}:
        interesting = ordered[0]["price"]

    return DealCurveThresholds(
        pass_above=pass_above,
        interesting=interesting,
        buy_below=buy_below,
    )

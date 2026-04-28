"""Deterministic chat-tier rent-angle Scout pattern."""

from __future__ import annotations

from statistics import median
from typing import Any

from briarwood.claims.base import SurfacedInsight
from briarwood.routing_schema import UnifiedIntelligenceOutput
from briarwood.value_scout.patterns._unified_helpers import (
    as_float,
    first_path,
    get_path,
    unified_dict,
)

COMP_MEDIAN_GROSS_YIELD_THRESHOLD = 0.06
COMP_RENT_CARRY_COVERAGE_THRESHOLD = 1.05
SECONDARY_RENT_SUPPORT_THRESHOLD = 0.70
SECONDARY_CASH_FLOW_FLOOR = -500.0

_COMP_PATHS: tuple[str, ...] = (
    "supporting_facts.cma.comps",
    "supporting_facts.market_support.comps",
    "supporting_facts.comparable_sales.comps_used",
    "supporting_facts.comp_roster",
    "cma.comps",
    "comparable_sales.comps_used",
)

_CARRY_PATHS: tuple[str, ...] = (
    "supporting_facts.carry_cost.monthly_total_cost",
    "supporting_facts.carry_cost.total_monthly_cost",
    "supporting_facts.carry_cost.monthly_carry_cost",
    "carry_cost.monthly_total_cost",
    "carry_cost.total_monthly_cost",
)

_RENT_SUPPORT_PATHS: tuple[str, ...] = (
    "supporting_facts.rental_option.rent_support_score",
    "supporting_facts.strategy_fit.rent_support_score",
    "rental_option.rent_support_score",
)

_CASH_FLOW_PATHS: tuple[str, ...] = (
    "supporting_facts.carry_cost.monthly_cash_flow",
    "supporting_facts.strategy_fit.monthly_cash_flow",
    "carry_cost.monthly_cash_flow",
)


def detect(unified: UnifiedIntelligenceOutput) -> SurfacedInsight | None:
    """Surface rent upside when comp rent evidence or module signals clear rails."""

    data = unified_dict(unified)
    comp_insight = _detect_comp_anchored(data)
    if comp_insight is not None:
        return comp_insight
    return _detect_secondary(data)


def _detect_comp_anchored(data: dict[str, Any]) -> SurfacedInsight | None:
    comps_value, comps_path = first_path(data, _COMP_PATHS)
    if not isinstance(comps_value, list):
        return None

    yields: list[float] = []
    rents: list[float] = []
    for comp in comps_value:
        if not isinstance(comp, dict):
            continue
        rent = as_float(comp.get("rent_zestimate") or comp.get("zillow_market_rent"))
        price = as_float(
            comp.get("sale_price")
            or comp.get("sold_price")
            or comp.get("closed_price")
            or comp.get("ask_price")
        )
        if rent is None or price is None or rent <= 0 or price <= 0:
            continue
        yields.append((rent * 12.0) / price)
        rents.append(rent)

    if not yields:
        return None

    median_yield = median(yields)
    median_rent = median(rents)
    monthly_carry, carry_path = first_path(data, _CARRY_PATHS)
    carry = as_float(monthly_carry)
    rent_covers_carry = (
        carry is not None
        and carry > 0
        and median_rent >= carry * COMP_RENT_CARRY_COVERAGE_THRESHOLD
    )
    yield_clears = median_yield >= COMP_MEDIAN_GROSS_YIELD_THRESHOLD

    if not (yield_clears or rent_covers_carry):
        return None

    supporting_fields = [f"{comps_path}.rent_zestimate", f"{comps_path}.sale_price"]
    if carry_path:
        supporting_fields.append(carry_path)

    confidence = 0.68
    if yield_clears:
        confidence += min(0.12, (median_yield - COMP_MEDIAN_GROSS_YIELD_THRESHOLD) * 4.0)
    if rent_covers_carry:
        confidence += 0.08

    return SurfacedInsight(
        headline="Comp rents point to an underwriting angle.",
        reason=(
            "The comp set's median rent estimate implies about "
            f"{median_yield * 100:.1f}% gross yield, making rent worth a "
            "closer look even if the headline verdict is about price."
        ),
        supporting_fields=supporting_fields[:4],
        category="rent_angle",
        confidence=round(min(confidence, 0.9), 3),
    )


def _detect_secondary(data: dict[str, Any]) -> SurfacedInsight | None:
    if _rent_intent_is_explicit(data):
        return None

    rent_support_raw, rent_support_path = first_path(data, _RENT_SUPPORT_PATHS)
    cash_flow_raw, cash_flow_path = first_path(data, _CASH_FLOW_PATHS)
    rent_support = as_float(rent_support_raw)
    cash_flow = as_float(cash_flow_raw)

    if rent_support is None or rent_support < SECONDARY_RENT_SUPPORT_THRESHOLD:
        return None
    if cash_flow is None or cash_flow < SECONDARY_CASH_FLOW_FLOOR:
        return None

    return SurfacedInsight(
        headline="The rent profile is stronger than the prompt asked for.",
        reason=(
            "Rental support is high and projected cash flow is not deeply "
            "negative, so the income path deserves attention alongside the "
            "headline value read."
        ),
        supporting_fields=[
            path
            for path in (rent_support_path, cash_flow_path)
            if path is not None
        ],
        category="rent_angle",
        confidence=round(min(0.86, 0.62 + (rent_support - 0.7) * 0.5), 3),
    )


def _rent_intent_is_explicit(data: dict[str, Any]) -> bool:
    text = " ".join(
        str(get_path(data, path) or "")
        for path in (
            "supporting_facts.user_text",
            "supporting_facts.query",
            "supporting_facts.question",
        )
    ).lower()
    return any(token in text for token in ("rent", "rental", "tenant", "cash flow"))

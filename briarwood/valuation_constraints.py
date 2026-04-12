from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.schemas import PropertyInput


@dataclass(slots=True)
class MarketFeedbackResult:
    dom_signal: str
    stale_listing: bool
    liquidity_penalty: float
    confidence_impact: float
    value_adjustment: float
    max_supported_value: float | None
    notes: list[str] = field(default_factory=list)


def is_nonstandard_product(property_input: PropertyInput) -> bool:
    description = (property_input.listing_description or "").lower()
    return any(
        [
            bool(property_input.has_back_house),
            bool(property_input.adu_type),
            "cottage" in description,
            "rear house" in description,
            "back house" in description,
            "guest house" in description,
            "multigenerational" in description,
            "in-law" in description,
        ]
    )


def market_friction_discount(
    *,
    property_input: PropertyInput,
    anchor_value: float | None,
) -> tuple[float, list[str]]:
    if anchor_value is None or anchor_value <= 0:
        return 0.0, []

    pct = 0.0
    notes: list[str] = []
    if is_nonstandard_product(property_input):
        pct += 0.04
        notes.append("Non-standard split-structure layout narrows the buyer pool versus clean same-town comps.")
    if property_input.adu_type in {"detached_cottage", "rear_cottage"} or property_input.has_back_house:
        pct += 0.02
        notes.append("Detached cottage / rear-house configuration adds underwriting and buyer-interpretation friction.")
    property_type = (property_input.property_type or "").lower()
    if pct > 0 and property_type in {"single family", "single family residence", "single_family"}:
        pct += 0.01
        notes.append("Retail buyers often price this more cautiously than a standard premium single-family shell.")

    pct = min(pct, 0.08)
    return round(-(anchor_value * pct), 2), notes[:3]


def evaluate_market_feedback(
    *,
    property_input: PropertyInput,
    indicated_value: float | None,
    support_quality: str,
    confidence: float,
    subject_is_nonstandard: bool,
) -> MarketFeedbackResult:
    dom = property_input.days_on_market
    ask = property_input.purchase_price
    if indicated_value is None or indicated_value <= 0:
        return MarketFeedbackResult("unknown", False, 0.0, 0.0, 0.0, None, [])

    if dom is None:
        return MarketFeedbackResult(
            "missing",
            False,
            0.0,
            -0.02,
            0.0,
            None,
            ["Property-level market feedback is limited because days on market is missing."],
        )

    stale_listing = dom >= 60
    dom_signal = "fresh"
    liquidity_penalty = 0.0
    confidence_impact = 0.0
    if dom <= 21:
        dom_signal = "fresh"
    elif dom <= 45:
        dom_signal = "normal"
        liquidity_penalty = 0.01
    elif dom <= 75:
        dom_signal = "slow"
        liquidity_penalty = 0.03
        confidence_impact = -0.04
    elif dom <= 120:
        dom_signal = "stale"
        liquidity_penalty = 0.06
        confidence_impact = -0.08
    else:
        dom_signal = "stale"
        liquidity_penalty = 0.09
        confidence_impact = -0.12

    notes = [f"Days on market ({dom}) indicates {dom_signal} clearing speed for the current ask."]
    if subject_is_nonstandard:
        liquidity_penalty += 0.02
        confidence_impact -= 0.02
        notes.append("Split-structure layout makes stale-listing feedback more important than it would be for a standard Avon shell.")

    premium_allowance = {"strong": 0.03, "moderate": 0.0, "thin": -0.04}.get(support_quality, 0.0)
    if confidence >= 0.75:
        premium_allowance += 0.02
    elif confidence <= 0.60:
        premium_allowance -= 0.02
    premium_allowance -= liquidity_penalty
    premium_allowance = max(-0.15, min(premium_allowance, 0.05))

    max_supported_value = None
    value_adjustment = 0.0
    if ask and ask > 0 and stale_listing:
        max_supported_value = round(ask * (1 + premium_allowance), 2)
        if indicated_value > max_supported_value:
            value_adjustment = round(max_supported_value - indicated_value, 2)
            notes.append(
                f"Stale-listing feedback caps supported value near ${max_supported_value:,.0f} unless stronger clearing evidence emerges."
            )

    return MarketFeedbackResult(
        dom_signal=dom_signal,
        stale_listing=stale_listing,
        liquidity_penalty=round(liquidity_penalty, 4),
        confidence_impact=round(confidence_impact, 4),
        value_adjustment=value_adjustment,
        max_supported_value=max_supported_value,
        notes=notes[:3],
    )

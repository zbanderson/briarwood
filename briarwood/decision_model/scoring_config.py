"""
Scoring configuration for the Briarwood investment decision model.

Weights, thresholds, questions, and recommendation tiers for the
5-category / 20-sub-factor scoring framework.
"""
from __future__ import annotations

# ── Category weights (must sum to 1.0) ─────────────────────────────────────

CATEGORY_WEIGHTS: dict[str, float] = {
    "price_context": 0.25,
    "economic_support": 0.20,
    "optionality": 0.20,
    "market_position": 0.15,
    "risk_layer": 0.20,
}

# ── Sub-factor weights (must sum to 1.0 within each category) ──────────────

SUB_FACTOR_WEIGHTS: dict[str, dict[str, float]] = {
    "price_context": {
        "price_vs_comps": 0.30,
        "ppsf_positioning": 0.20,
        "historical_pricing": 0.25,
        "scarcity_premium": 0.25,
    },
    "economic_support": {
        "rent_support": 0.30,
        "carry_efficiency": 0.25,
        "downside_protection": 0.25,
        "replacement_cost": 0.20,
    },
    "optionality": {
        "adu_expansion": 0.25,
        "renovation_upside": 0.30,
        "strategy_flexibility": 0.25,
        "zoning_optionality": 0.20,
    },
    "market_position": {
        "dom_signal": 0.25,
        "inventory_tightness": 0.25,
        "buyer_seller_balance": 0.25,
        "location_momentum": 0.25,
    },
    "risk_layer": {
        "liquidity_risk": 0.25,
        "capex_risk": 0.25,
        "income_stability": 0.30,
        "macro_regulatory": 0.20,
    },
}

# ── Sub-factor questions (the decision question each factor answers) ───────

SUB_FACTOR_QUESTIONS: dict[str, str] = {
    # Price Context
    "price_vs_comps": "How does the asking price compare to adjusted comparable sales?",
    "ppsf_positioning": "Is the property priced above, at, or below the local $/SF band?",
    "historical_pricing": "Does the ZHVI trend support the current price level?",
    "scarcity_premium": "Does location scarcity justify a pricing premium?",
    # Economic Support
    "rent_support": "Can rental income meaningfully offset carrying costs?",
    "carry_efficiency": "How burdensome is the monthly carry relative to income?",
    "downside_protection": "How much downside buffer exists between BCV and ask?",
    "replacement_cost": "Is the property priced below what it would cost to build new?",
    # Optionality
    "adu_expansion": "Is there physical space or existing structure for an ADU/expansion?",
    "renovation_upside": "Does a renovation scenario create meaningful value above cost?",
    "strategy_flexibility": "Can the owner pivot between hold, rent, renovate, or sell strategies?",
    "zoning_optionality": "Does zoning or lot configuration allow future development options?",
    # Market Position
    "dom_signal": "Is the property absorbing quickly or sitting on market?",
    "inventory_tightness": "How constrained is supply in this micro-market?",
    "buyer_seller_balance": "Does the market favor buyers or sellers right now?",
    "location_momentum": "Is the town/submarket trending positively?",
    # Risk Layer
    "liquidity_risk": "How quickly could this property be resold if needed?",
    "capex_risk": "How much deferred maintenance or surprise capex exposure exists?",
    "income_stability": "How reliable and sustainable is the rental income stream?",
    "macro_regulatory": "Are there flood, regulatory, or macro headwinds?",
}

# ── Recommendation tiers (threshold, tier_name, action) ────────────────────
# Evaluated top-down: first match wins.

RECOMMENDATION_TIERS: list[tuple[float, str, str]] = [
    (4.50, "High Conviction Buy", "Strong fundamentals across all dimensions — act with urgency."),
    (3.75, "Attractive", "Investigate further — the setup is favorable but verify key assumptions."),
    (3.00, "Neutral", "Requires more diligence — some dimensions are weak or unresolved."),
    (2.25, "Caution", "Significant concerns exist — proceed only with a clear thesis for why this is mispriced."),
    (0.00, "Avoid", "Does not meet investment criteria on current information."),
]

# ── Human-readable sub-factor labels (user-facing) ──────────────────────

SUB_FACTOR_LABELS: dict[str, str] = {
    # Price Context
    "price_vs_comps": "Priced right vs. recent sales?",
    "ppsf_positioning": "Price per sqft competitive?",
    "historical_pricing": "Favorable vs. historical trends?",
    "scarcity_premium": "Supply scarcity justifies premium?",
    # Economic Support
    "rent_support": "Does rent support the price?",
    "carry_efficiency": "Can you afford monthly payments?",
    "downside_protection": "Adequate downside buffer?",
    "replacement_cost": "Priced below replacement cost?",
    # Optionality
    "adu_expansion": "Room to add rental income (ADU)?",
    "renovation_upside": "Renovation creates value above cost?",
    "strategy_flexibility": "Can you pivot strategies later?",
    "zoning_optionality": "Zoning allows future development?",
    # Market Position
    "dom_signal": "Properties selling quickly here?",
    "inventory_tightness": "Tight supply / seller's market?",
    "buyer_seller_balance": "Market favors buyers or sellers?",
    "location_momentum": "Town/submarket trending positively?",
    # Risk Layer
    "liquidity_risk": "Easy to resell if needed?",
    "capex_risk": "Surprise maintenance exposure?",
    "income_stability": "Rental income reliable?",
    "macro_regulatory": "Flood, regulatory, or macro risks?",
}

# ── Scoring defaults ───────────────────────────────────────────────────────

NEUTRAL_SCORE: float = 3.0
MIN_SCORE: float = 1.0
MAX_SCORE: float = 5.0

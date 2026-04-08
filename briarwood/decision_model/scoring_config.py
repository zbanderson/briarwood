"""
Scoring configuration for the Briarwood investment decision model.

Weights, thresholds, questions, and recommendation tiers for the
5-category / 20-sub-factor scoring framework.

S9 (audit 2026-04-08): BullBaseBearSettings, RiskSettings, and
DecisionModelSettings were moved here from briarwood/settings.py so
tuning knobs that drive scoring live alongside the rest of the decision
model config. briarwood/settings.py now only holds runtime/app settings.
"""
from __future__ import annotations

from dataclasses import dataclass

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
    (3.30, "Buy", "The setup is favorable enough to keep moving with focused diligence on the weakest point."),
    (2.50, "Neutral", "The thesis is mixed. Resolve the top gap before taking a position."),
    (0.00, "Avoid", "The current evidence does not support moving forward."),
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


# ── Tuning dataclasses (moved from briarwood/settings.py, S9) ──────────────


@dataclass(slots=True)
class BullBaseBearSettings:
    base_score: float = 55.0

    # --- Market drift caps ---
    bbb_market_drift_bull_cap: float = 0.15      # max bull market drift
    bbb_market_drift_bear_floor: float = -0.20   # min (most negative) bear market drift

    # --- Location adjustment scales ---
    # Good town (location_delta > 0): bull full, base half, bear zero
    bbb_location_good_bull_scale: float = 0.10   # location_delta * scale in bull
    bbb_location_good_base_scale: float = 0.05   # location_delta * scale in base
    # Bad town (location_delta < 0): bull zero, base moderate, bear amplified
    bbb_location_bad_base_scale: float = 0.075   # |location_delta| * scale in base
    bbb_location_bad_bear_scale: float = 0.125   # |location_delta| * scale in bear
    bbb_location_premium_cap: float = 0.08       # max location premium (bull)
    bbb_location_discount_floor: float = -0.08   # max location discount (bear)

    # --- Risk adjustment tiers ---
    # risk_score >= tier_1: no penalty
    # risk_score tier_2..tier_1: penalty scales 0 → tier_1_max_penalty
    # risk_score tier_3..tier_2: penalty scales tier_1_max → tier_2_max
    # risk_score < tier_3: penalty scales tier_2_max → tier_3_max
    bbb_risk_tier_1_threshold: float = 85.0
    bbb_risk_tier_2_threshold: float = 70.0
    bbb_risk_tier_3_threshold: float = 50.0
    bbb_risk_tier_1_max_penalty: float = 0.05    # penalty at tier_2 threshold
    bbb_risk_tier_2_max_penalty: float = 0.12    # penalty at tier_3 threshold
    bbb_risk_tier_3_max_penalty: float = 0.20    # penalty at risk_score = 0
    # Scenario attenuation: in bull risks matter less, in bear they fully materialize.
    # Bug 9: raised bull attenuation from 0.30 to 0.50 — structural risks (flood, age)
    # don't disappear in bull markets. 0.50 is a compromise pending structural/cyclical split.
    bbb_risk_bull_attenuation: float = 0.5
    bbb_risk_base_attenuation: float = 0.7
    bbb_risk_bear_attenuation: float = 1.0

    # --- Optionality (scarcity-driven upside, only applies to bull/base) ---
    bbb_max_optionality_premium: float = 0.08    # max uplift from scarcity at 100 score
    bbb_optionality_base_attenuation: float = 0.25  # base gets 25% of bull optionality

    # --- Stress scenario (historical peak-to-trough overlay, not a forecast) ---
    bear_tail_risk_enabled: bool = True
    bbb_stress_drawdown_default: float = 0.25    # -25% from BCV; NJ coastal 2007-2011
    bbb_stress_drawdown_flood_medium: float = 0.30   # -30% for medium flood exposure
    bbb_stress_drawdown_flood_high: float = 0.35     # -35% for high flood exposure

    # --- Confidence deductions ---
    bbb_confidence_base: float = 0.80
    bbb_confidence_deduction_bcv_low: float = 0.15      # BCV confidence < 0.60
    bbb_confidence_deduction_history_short: float = 0.10  # < 2 years of market history
    bbb_confidence_deduction_history_very_short: float = 0.20  # < 1 year of market history
    bbb_confidence_deduction_town_weak: float = 0.05    # town score confidence < 0.70
    bbb_confidence_deduction_risk_weak: float = 0.05    # risk confidence < 0.70
    bbb_confidence_deduction_scarcity_weak: float = 0.05  # scarcity confidence < 0.60
    bbb_confidence_floor: float = 0.35


@dataclass(slots=True)
class RiskSettings:
    older_home_age_threshold: int = 60
    # Bug 5: vacancy penalty thresholds — replaced binary 6% threshold
    # with graduated tiers for smooth penalty accumulation.
    vacancy_tier1_start: float = 0.05     # 0-5%: no penalty
    vacancy_tier1_end: float = 0.08       # 5-8%: ramp 0 → -5
    vacancy_tier1_max_penalty: float = 5.0
    vacancy_tier2_end: float = 0.12       # 8-12%: ramp -5 → -10
    vacancy_tier2_max_penalty: float = 10.0
    vacancy_tier3_end: float = 0.20       # 12-20%: ramp -10 → -20
    vacancy_tier3_max_penalty: float = 20.0
    vacancy_penalty_cap: float = 20.0     # 20%+: capped
    base_score: float = 85.0
    # Flood risk: graduated by tier (was one flat 12-pt penalty for medium or high)
    flood_risk_high_penalty: float = 20.0
    flood_risk_medium_penalty: float = 8.0
    flood_risk_low_penalty: float = 0.0  # "low" and "none" are not penalized
    # Older housing stock: flat penalty (age itself is binary; severity expressed via capex_lane)
    older_home_penalty: float = 8.0
    # Taxes: linear interpolation across breakpoints (was binary at $12K → 12 pts)
    tax_penalty_tier1_threshold: float = 10000.0   # below this: no penalty
    tax_penalty_tier1_max: float = 12000.0          # interpolate 0→12 pts between tier1 and tier2
    tax_penalty_tier2_threshold: float = 15000.0
    tax_penalty_tier2_max: float = 20000.0          # interpolate 12→20 pts between tier2 and tier3
    tax_penalty_tier3_threshold: float = 25000.0    # 25K+ caps at 20 pts
    tax_penalty_cap: float = 20.0
    # Bug 4: DOM graduated function — replaced cliff at 30 days with smooth ramp.
    # 0-14: no penalty (fresh listing). 15-30: ramp 0→5. 31-60: ramp 5→15.
    # 61-90: ramp 15→25. 90+: capped at 25.
    dom_penalty_start: int = 15       # 0–14: no penalty
    dom_penalty_tier1_end: int = 30   # 15–30: interpolate 0→5
    dom_penalty_tier1_max: float = 5.0
    dom_penalty_tier2_end: int = 60   # 31–60: interpolate 5→15
    dom_penalty_tier2_max: float = 15.0
    dom_penalty_tier3_end: int = 90   # 61–90: interpolate 15→25
    dom_penalty_cap: float = 25.0     # 90+: capped at 25
    # Positive credit for low-risk attributes (max total +8 so perfect score = 93)
    low_flood_credit: float = 3.0     # flood_risk == "low" or "none"
    low_tax_credit: float = 2.0       # taxes <= $8K (well below the tier-1 threshold)
    low_tax_credit_threshold: float = 8000.0
    fast_dom_credit: float = 2.0      # days_on_market < 15
    fast_dom_credit_threshold: int = 15
    max_positive_credit: float = 8.0  # cap prevents a perfect-100 score
    # Confidence tiers: scale with how many of the 5 risk dimensions have real data
    confidence_tier_full: float = 0.85   # all 5 dimensions present
    confidence_tier_medium: float = 0.72  # 3–4 dimensions present
    confidence_tier_low: float = 0.55    # fewer than 3 dimensions


@dataclass(slots=True)
class DecisionModelSettings:
    # Bug 6: replacement cost benchmark — extracted from hardcoded $400/sqft.
    # TODO: make geography/property-type aware in a future iteration.
    replacement_cost_per_sqft: float = 400.0


DEFAULT_BULL_BASE_BEAR_SETTINGS = BullBaseBearSettings()
DEFAULT_RISK_SETTINGS = RiskSettings()
DEFAULT_DECISION_MODEL_SETTINGS = DecisionModelSettings()

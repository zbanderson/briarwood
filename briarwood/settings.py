from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CostValuationSettings:
    default_vacancy_rate: float = 0.05
    # Bug 8: higher default for coastal seasonal properties
    default_coastal_seasonal_vacancy_rate: float = 0.15
    default_maintenance_reserve_pct: float = 0.01
    loan_term_years: int = 30
    # Bug 1: lowered from 45 to 25 — remaining 75 pts must be earned from
    # actual income support, cap rate, and cash flow metrics.
    base_score: float = 25.0
    # Bug 2: changed from 500 to 285 so the 20-pt cap is reached at ~7% cap rate
    # instead of 4%, giving meaningful differentiation across the 3-7% spectrum.
    cap_rate_weight: float = 285.0
    cap_rate_score_cap: float = 20.0
    dscr_baseline: float = 1.0
    dscr_weight: float = 25.0
    dscr_score_cap: float = 20.0
    cash_on_cash_weight: float = 120.0
    cash_on_cash_score_cap: float = 10.0
    # Bug 3: both divisors set to 150 for symmetric treatment of positive
    # and negative cash flow (was 100/200 — asymmetry masked downside risk).
    positive_cash_flow_divisor: float = 150.0
    positive_cash_flow_score_cap: float = 5.0
    negative_cash_flow_divisor: float = 150.0
    negative_cash_flow_score_floor: float = -15.0
    # Bug 7: age-based maintenance reserve tiers (override default_maintenance_reserve_pct)
    maintenance_reserve_post_2010: float = 0.0075
    maintenance_reserve_1990_2010: float = 0.01
    maintenance_reserve_1970_1989: float = 0.0125
    maintenance_reserve_1950_1969: float = 0.015
    maintenance_reserve_pre_1950: float = 0.0175
    maintenance_reserve_poor_condition_adder: float = 0.0025
    confidence_floor: float = 0.4
    confidence_range: float = 0.55
    # Confidence caps applied when key inputs are missing or estimated
    confidence_cap_rent_missing: float = 0.48   # no rent data at all — income check unavailable
    confidence_cap_rent_estimated: float = 0.64  # rent is modeled, not sourced
    confidence_cap_financing_incomplete: float = 0.58  # down payment or rate missing
    confidence_cap_insurance_missing: float = 0.62  # insurance not entered


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
class CurrentValueSettings:
    income_cap_rate_assumption: float = 0.05
    # Confidence caps applied when key inputs are missing or estimated
    confidence_cap_rent_missing: float = 0.60   # no rent data — income-backed check unavailable
    confidence_cap_rent_estimated: float = 0.72  # rent is modeled, not sourced
    confidence_cap_financing_incomplete: float = 0.65  # down payment or rate missing
    confidence_cap_insurance_missing: float = 0.62  # insurance not entered


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


@dataclass(slots=True)
class RelativeOpportunitySettings:
    # Confidence caps applied when supporting evidence is incomplete
    confidence_cap_no_local_intel: float = 0.65   # local document intelligence missing for any property
    confidence_cap_capex_heuristics: float = 0.68  # capex estimated from lane, not explicit budget


@dataclass(slots=True)
class RenovationScenarioSettings:
    # Below this budget, skip the scenario (not worth modeling)
    min_renovation_budget: float = 10_000.0
    # Confidence floor regardless of data quality
    confidence_floor: float = 0.40
    # Deducted from confidence when fewer than this many renovated comps found
    min_renovated_comps_for_full_confidence: int = 3
    confidence_penalty_few_renovated_comps: float = 0.15


@dataclass(slots=True)
class TeardownScenarioSettings:
    default_closing_costs_pct: float = 0.03
    default_down_payment_pct: float = 0.20
    default_vacancy_rate_pct: float = 0.05
    default_annual_maintenance_pct: float = 0.01
    default_annual_rent_growth_pct: float = 0.03
    default_tax_escalation_pct: float = 0.02
    default_insurance_escalation_pct: float = 0.03
    default_construction_duration_months: int = 14
    min_hold_years: int = 3
    max_hold_years: int = 15
    confidence_floor: float = 0.35


@dataclass(slots=True)
class AppSettings:
    default_property_path: str = "data/sample_property.json"


DEFAULT_COST_VALUATION_SETTINGS = CostValuationSettings()
DEFAULT_BULL_BASE_BEAR_SETTINGS = BullBaseBearSettings()
DEFAULT_CURRENT_VALUE_SETTINGS = CurrentValueSettings()
DEFAULT_RISK_SETTINGS = RiskSettings()
DEFAULT_DECISION_MODEL_SETTINGS = DecisionModelSettings()
DEFAULT_RELATIVE_OPPORTUNITY_SETTINGS = RelativeOpportunitySettings()
DEFAULT_APP_SETTINGS = AppSettings()
DEFAULT_RENOVATION_SCENARIO_SETTINGS = RenovationScenarioSettings()
DEFAULT_TEARDOWN_SCENARIO_SETTINGS = TeardownScenarioSettings()

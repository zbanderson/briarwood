from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CostValuationSettings:
    default_vacancy_rate: float = 0.05
    default_maintenance_reserve_pct: float = 0.01
    loan_term_years: int = 30
    base_score: float = 45.0
    cap_rate_weight: float = 500.0
    cap_rate_score_cap: float = 20.0
    dscr_baseline: float = 1.0
    dscr_weight: float = 25.0
    dscr_score_cap: float = 20.0
    cash_on_cash_weight: float = 120.0
    cash_on_cash_score_cap: float = 10.0
    positive_cash_flow_divisor: float = 100.0
    positive_cash_flow_score_cap: float = 5.0
    negative_cash_flow_divisor: float = 200.0
    negative_cash_flow_score_floor: float = -15.0
    confidence_floor: float = 0.4
    confidence_range: float = 0.55


@dataclass(slots=True)
class BullBaseBearSettings:
    trend_persistence_weight: float = 0.90
    one_year_history_weight: float = 0.60
    three_year_history_weight: float = 0.40
    max_market_drift_adjustment: float = 0.10
    max_location_premium: float = 0.04
    max_risk_discount: float = 0.05
    max_optionality_premium: float = 0.03
    bull_upside_buffer: float = 0.025
    bear_downside_buffer: float = 0.035
    min_growth_rate: float = -0.12
    max_growth_rate: float = 0.12
    min_spread_ratio: float = 0.05
    base_score: float = 55.0
    spread_weight: float = 20.0
    # Tail-risk stress overlay — models historical coastal peak-to-trough corrections (NJ 2008–2011).
    bear_tail_risk_enabled: bool = True
    bear_macro_shock_pct: float = 0.20  # -20% from base; coastal NJ corrections have reached 25–35%
    bear_macro_shock_label: str = "Stress case: historical coastal correction"


@dataclass(slots=True)
class CurrentValueSettings:
    income_cap_rate_assumption: float = 0.05


@dataclass(slots=True)
class RiskSettings:
    older_home_age_threshold: int = 60
    high_vacancy_threshold: float = 0.06
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
    # DOM: graduated (was binary at 45 days → 12 pts)
    dom_penalty_start: int = 30       # 0–30: no penalty
    dom_penalty_mid: int = 60         # 30–60: interpolate 0→8
    dom_penalty_high: int = 90        # 60–90: interpolate 8→15
    dom_penalty_cap: float = 18.0     # 90+: cap at 18
    # Vacancy: flat (already a rate, threshold is meaningful)
    vacancy_penalty: float = 10.0
    # Positive credit for low-risk attributes (max total +8 so perfect score = 93)
    low_flood_credit: float = 3.0     # flood_risk == "low" or "none"
    low_tax_credit: float = 2.0       # taxes <= $8K (well below the tier-1 threshold)
    low_tax_credit_threshold: float = 8000.0
    fast_dom_credit: float = 2.0      # days_on_market < 15
    fast_dom_credit_threshold: int = 15
    max_positive_credit: float = 8.0  # cap prevents a perfect-100 score


@dataclass(slots=True)
class AppSettings:
    default_property_path: str = "data/sample_property.json"


DEFAULT_COST_VALUATION_SETTINGS = CostValuationSettings()
DEFAULT_BULL_BASE_BEAR_SETTINGS = BullBaseBearSettings()
DEFAULT_CURRENT_VALUE_SETTINGS = CurrentValueSettings()
DEFAULT_RISK_SETTINGS = RiskSettings()
DEFAULT_APP_SETTINGS = AppSettings()

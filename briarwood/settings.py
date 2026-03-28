from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(slots=True)
class CurrentValueSettings:
    income_cap_rate_assumption: float = 0.05


@dataclass(slots=True)
class RiskSettings:
    older_home_age_threshold: int = 60
    high_tax_threshold: float = 12000.0
    high_vacancy_threshold: float = 0.06
    long_days_on_market_threshold: int = 45
    base_score: float = 85.0
    score_penalty_per_flag: float = 12.0
    elevated_flood_risk_levels: set[str] = field(default_factory=lambda: {"medium", "high"})


@dataclass(slots=True)
class AppSettings:
    default_property_path: str = "data/sample_property.json"


DEFAULT_COST_VALUATION_SETTINGS = CostValuationSettings()
DEFAULT_BULL_BASE_BEAR_SETTINGS = BullBaseBearSettings()
DEFAULT_CURRENT_VALUE_SETTINGS = CurrentValueSettings()
DEFAULT_RISK_SETTINGS = RiskSettings()
DEFAULT_APP_SETTINGS = AppSettings()

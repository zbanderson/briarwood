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
class CurrentValueSettings:
    income_cap_rate_assumption: float = 0.05
    # Confidence caps applied when key inputs are missing or estimated
    confidence_cap_rent_missing: float = 0.60   # no rent data — income-backed check unavailable
    confidence_cap_rent_estimated: float = 0.72  # rent is modeled, not sourced
    confidence_cap_financing_incomplete: float = 0.65  # down payment or rate missing
    confidence_cap_insurance_missing: float = 0.62  # insurance not entered


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
DEFAULT_CURRENT_VALUE_SETTINGS = CurrentValueSettings()
DEFAULT_RELATIVE_OPPORTUNITY_SETTINGS = RelativeOpportunitySettings()
DEFAULT_APP_SETTINGS = AppSettings()
DEFAULT_RENOVATION_SCENARIO_SETTINGS = RenovationScenarioSettings()
DEFAULT_TEARDOWN_SCENARIO_SETTINGS = TeardownScenarioSettings()

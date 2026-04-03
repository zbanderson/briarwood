"""
Smart defaults for missing property data.

Populates None fields on PropertyInput with reasonable estimates based on
property type, location, and price. All defaults are transparent — the
`defaults_applied` dict records exactly what was filled in and why.

Philosophy: System works out-of-the-box with minimal input.
Experts can override everything via the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from briarwood.schemas import PropertyInput


@dataclass(slots=True)
class DefaultsApplied:
    """Record of which defaults were applied and their values."""
    fields: dict[str, str] = field(default_factory=dict)

    def record(self, field_name: str, value: object, reason: str) -> None:
        self.fields[field_name] = f"{value} ({reason})"

    @property
    def count(self) -> int:
        return len(self.fields)


# ── NJ coastal market reference rates ──────────────────────────────────────────
# These are static fallbacks. Updated periodically, not live API.

_DEFAULT_INTEREST_RATE = 0.07          # 7.0% — conservative 30yr fixed (2024-2025)
_DEFAULT_DOWN_PAYMENT_PCT = 0.20       # 20% conventional
_DEFAULT_LOAN_TERM_YEARS = 30
_DEFAULT_VACANCY_RATE = 0.05           # 5% for year-round rental
_DEFAULT_INSURANCE_RATE = 0.0035       # 0.35% of property value annually
_DEFAULT_MAINTENANCE_RESERVE_PCT = 0.01  # 1% of property value annually
_NJ_EFFECTIVE_TAX_RATE = 0.0189        # NJ average effective property tax rate


def apply_smart_defaults(property_input: PropertyInput) -> DefaultsApplied:
    """
    Fill None fields on PropertyInput with smart defaults.

    Modifies property_input in place and returns a record of what was applied.
    Only fills fields that are None — never overwrites user-provided data.
    """
    applied = DefaultsApplied()
    price = property_input.purchase_price

    # ── Financing defaults ─────────────────────────────────────────────────

    if property_input.down_payment_percent is None:
        property_input.down_payment_percent = _DEFAULT_DOWN_PAYMENT_PCT
        applied.record("down_payment_percent", "20%", "conventional default")

    if property_input.interest_rate is None:
        property_input.interest_rate = _DEFAULT_INTEREST_RATE
        applied.record("interest_rate", "7.0%", "conservative 30yr fixed estimate")

    if property_input.loan_term_years is None:
        property_input.loan_term_years = _DEFAULT_LOAN_TERM_YEARS
        applied.record("loan_term_years", "30", "standard term")

    # ── Operating cost defaults ────────────────────────────────────────────

    if property_input.taxes is None and price is not None and price > 0:
        estimated_tax = round(price * _NJ_EFFECTIVE_TAX_RATE, 0)
        property_input.taxes = estimated_tax
        applied.record("taxes", f"${estimated_tax:,.0f}", f"estimated at {_NJ_EFFECTIVE_TAX_RATE:.2%} of price")

    if property_input.insurance is None and price is not None and price > 0:
        estimated_ins = round(price * _DEFAULT_INSURANCE_RATE, 0)
        property_input.insurance = estimated_ins
        applied.record("insurance", f"${estimated_ins:,.0f}/yr", f"estimated at {_DEFAULT_INSURANCE_RATE:.2%} of price")

    if property_input.vacancy_rate is None:
        property_input.vacancy_rate = _DEFAULT_VACANCY_RATE
        applied.record("vacancy_rate", "5%", "standard rental vacancy assumption")

    # ── Property characteristic estimates ──────────────────────────────────

    if property_input.lot_size is None and property_input.sqft and property_input.sqft > 0:
        # Rough suburban heuristic: lot ≈ 3-4x building footprint
        # Assume 1-story footprint = sqft (conservative)
        estimated_lot_sqft = property_input.sqft * 3.5
        estimated_lot_acres = round(estimated_lot_sqft / 43560, 2)
        if estimated_lot_acres >= 0.05:  # sanity check
            property_input.lot_size = estimated_lot_acres
            applied.record("lot_size", f"{estimated_lot_acres} acres", "estimated from sqft × 3.5")

    # ── Condition inference ────────────────────────────────────────────────

    if property_input.condition_profile is None and property_input.year_built is not None:
        from briarwood.utils import current_year
        age = current_year() - property_input.year_built
        if age <= 5:
            property_input.condition_profile = "updated"
            applied.record("condition_profile", "updated", f"built {property_input.year_built} (≤5 years)")
        elif age <= 20:
            property_input.condition_profile = "maintained"
            applied.record("condition_profile", "maintained", f"built {property_input.year_built} ({age} years)")
        elif age <= 50:
            property_input.condition_profile = "dated"
            applied.record("condition_profile", "dated", f"built {property_input.year_built} ({age} years)")
        else:
            property_input.condition_profile = "needs_work"
            applied.record("condition_profile", "needs_work", f"built {property_input.year_built} ({age} years)")

    if property_input.capex_lane is None and property_input.condition_profile is not None:
        condition = property_input.condition_profile.lower()
        if condition in ("renovated", "updated"):
            property_input.capex_lane = "light"
        elif condition in ("maintained",):
            property_input.capex_lane = "moderate"
        elif condition in ("dated", "needs_work"):
            property_input.capex_lane = "heavy"
        if property_input.capex_lane is not None:
            applied.record("capex_lane", property_input.capex_lane, f"inferred from condition '{property_input.condition_profile}'")

    return applied

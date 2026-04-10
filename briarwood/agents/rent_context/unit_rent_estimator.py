"""Estimate market rent for individual rental units using town-level priors."""
from __future__ import annotations

from briarwood.agents.rent_context.priors import get_rent_prior
from briarwood.schemas import UnitDetail


# Condition multipliers relative to "maintained" baseline.
_CONDITION_MULT: dict[str, float] = {
    "renovated": 1.12,
    "remodeled": 1.10,
    "updated": 1.06,
    "maintained": 1.00,
    "dated": 0.90,
    "needs_work": 0.80,
}


def estimate_unit_market_rent(
    unit: UnitDetail,
    town: str,
    state: str = "NJ",
) -> UnitDetail:
    """Return a copy of *unit* with market_rent and rent_source populated.

    Strategy:
    1. If user_rent is already set, use it directly (rent_source = "user_input").
    2. If town rent priors exist:
       a. Prefer sqft-based estimate when unit.sqft is known.
       b. Fall back to bed-count lookup from base_monthly_rent_by_bed.
    3. Apply a condition adjustment when condition is known.
    4. If no prior is available, leave market_rent as None.
    """
    if unit.user_rent is not None and unit.user_rent > 0:
        return UnitDetail(
            label=unit.label,
            beds=unit.beds,
            baths=unit.baths,
            sqft=unit.sqft,
            condition=unit.condition,
            user_rent=unit.user_rent,
            market_rent=round(unit.user_rent, 2),
            rent_source="user_input",
        )

    prior = get_rent_prior(town, state)
    if prior is None:
        return unit  # no prior — can't estimate

    rent: float | None = None
    source = "market_estimate"

    # Prefer sqft-based when we have unit sqft
    if unit.sqft and unit.sqft > 0:
        rent = prior.monthly_rent_per_sqft * unit.sqft

    # Fall back to bed-count lookup
    if rent is None and unit.beds is not None:
        bed_key = max(1, min(unit.beds, max(prior.base_monthly_rent_by_bed.keys())))
        rent = prior.base_monthly_rent_by_bed.get(bed_key)

    if rent is None:
        return unit

    # Apply condition adjustment
    cond = (unit.condition or "maintained").lower().strip()
    mult = _CONDITION_MULT.get(cond, 1.0)
    rent = rent * mult

    return UnitDetail(
        label=unit.label,
        beds=unit.beds,
        baths=unit.baths,
        sqft=unit.sqft,
        condition=unit.condition,
        user_rent=unit.user_rent,
        market_rent=round(rent, 2),
        rent_source=source,
    )


def estimate_units_market_rent(
    units: list[UnitDetail],
    town: str,
    state: str = "NJ",
) -> list[UnitDetail]:
    """Estimate market rent for each unit in the list."""
    return [estimate_unit_market_rent(u, town, state) for u in units]


def total_annual_income(units: list[UnitDetail]) -> float:
    """Sum the best-available monthly rent across units and annualize."""
    total = 0.0
    for u in units:
        rent = u.market_rent or u.user_rent or 0.0
        total += rent
    return total * 12

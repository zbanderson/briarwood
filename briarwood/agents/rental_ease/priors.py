from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RentalEasePrior:
    town: str
    state: str
    county: str
    liquidity: float
    seasonality: float
    year_round_demand: float
    structural_desirability: float
    premium_fragility: float
    default_days_to_rent: int


MONMOUTH_RENTAL_EASE_PRIORS: dict[tuple[str, str], RentalEasePrior] = {
    ("belmar", "NJ"): RentalEasePrior(
        town="Belmar",
        state="NJ",
        county="Monmouth",
        liquidity=0.86,
        seasonality=0.62,
        year_round_demand=0.68,
        structural_desirability=0.82,
        premium_fragility=0.34,
        default_days_to_rent=32,
    ),
    ("bradley beach", "NJ"): RentalEasePrior(
        town="Bradley Beach",
        state="NJ",
        county="Monmouth",
        liquidity=0.79,
        seasonality=0.64,
        year_round_demand=0.61,
        structural_desirability=0.77,
        premium_fragility=0.32,
        default_days_to_rent=38,
    ),
    ("avon by the sea", "NJ"): RentalEasePrior(
        town="Avon by the Sea",
        state="NJ",
        county="Monmouth",
        liquidity=0.72,
        seasonality=0.69,
        year_round_demand=0.58,
        structural_desirability=0.88,
        premium_fragility=0.52,
        default_days_to_rent=46,
    ),
    ("sea girt", "NJ"): RentalEasePrior(
        town="Sea Girt",
        state="NJ",
        county="Monmouth",
        liquidity=0.69,
        seasonality=0.67,
        year_round_demand=0.55,
        structural_desirability=0.93,
        premium_fragility=0.58,
        default_days_to_rent=54,
    ),
    ("spring lake", "NJ"): RentalEasePrior(
        town="Spring Lake",
        state="NJ",
        county="Monmouth",
        liquidity=0.63,
        seasonality=0.71,
        year_round_demand=0.53,
        structural_desirability=0.95,
        premium_fragility=0.61,
        default_days_to_rent=58,
    ),
    ("manasquan", "NJ"): RentalEasePrior(
        town="Manasquan",
        state="NJ",
        county="Monmouth",
        liquidity=0.82,
        seasonality=0.58,
        year_round_demand=0.72,
        structural_desirability=0.86,
        premium_fragility=0.37,
        default_days_to_rent=34,
    ),
}


def get_rental_ease_prior(town: str, state: str) -> RentalEasePrior | None:
    """Return the Briarwood v1 rental-ease prior for a supported town."""

    return MONMOUTH_RENTAL_EASE_PRIORS.get((town.strip().lower(), state.strip().upper()))

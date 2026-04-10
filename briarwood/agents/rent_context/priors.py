from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RentPrior:
    town: str
    state: str
    monthly_rent_per_sqft: float
    confidence: float
    base_monthly_rent_by_bed: dict[int, float]


_PRIORS: dict[tuple[str, str], RentPrior] = {
    ("belmar", "NJ"): RentPrior(
        "Belmar",
        "NJ",
        monthly_rent_per_sqft=2.45,
        confidence=0.36,
        base_monthly_rent_by_bed={1: 1800, 2: 3000, 3: 3650, 4: 4400},
    ),
    ("bradley beach", "NJ"): RentPrior(
        "Bradley Beach",
        "NJ",
        monthly_rent_per_sqft=2.35,
        confidence=0.35,
        base_monthly_rent_by_bed={1: 1700, 2: 2850, 3: 3450, 4: 4150},
    ),
    ("avon by the sea", "NJ"): RentPrior(
        "Avon by the Sea",
        "NJ",
        monthly_rent_per_sqft=2.75,
        confidence=0.34,
        base_monthly_rent_by_bed={1: 2200, 2: 3600, 3: 4450, 4: 5400},
    ),
    ("avon-by-the-sea", "NJ"): RentPrior(
        "Avon-by-the-Sea",
        "NJ",
        monthly_rent_per_sqft=2.75,
        confidence=0.34,
        base_monthly_rent_by_bed={1: 2200, 2: 3600, 3: 4450, 4: 5400},
    ),
    ("sea girt", "NJ"): RentPrior(
        "Sea Girt",
        "NJ",
        monthly_rent_per_sqft=2.55,
        confidence=0.34,
        base_monthly_rent_by_bed={1: 2100, 2: 3500, 3: 4300, 4: 5200},
    ),
    ("spring lake", "NJ"): RentPrior(
        "Spring Lake",
        "NJ",
        monthly_rent_per_sqft=2.7,
        confidence=0.34,
        base_monthly_rent_by_bed={1: 2250, 2: 3700, 3: 4550, 4: 5450},
    ),
    ("manasquan", "NJ"): RentPrior(
        "Manasquan",
        "NJ",
        monthly_rent_per_sqft=2.5,
        confidence=0.35,
        base_monthly_rent_by_bed={1: 1900, 2: 3200, 3: 3950, 4: 4750},
    ),
}


def get_rent_prior(town: str, state: str) -> RentPrior | None:
    return _PRIORS.get((town.strip().lower(), state.strip().upper()))

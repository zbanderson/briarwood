"""Shared comp scoring + adjustment logic — works on both Engine A
(saved closed sales) and Engine B (Zillow SOLD + ACTIVE) rows.

Lifted from `briarwood/modules/comparable_sales.py` in CMA Phase 4a
Cycle 3b. Engine A's `_score_comp` continues to work identically — it
now delegates to the pure functions in this module. Cycle 3c's 3-source
merger calls `score_comp_inputs` directly on dict-shaped comp records
(from Zillow's normalized payload) without ever constructing an
`AdjustedComparable`.

Why pure functions on field values rather than methods on comp objects:
the Engine-A path uses Pydantic `AdjustedComparable`; the Engine-B path
uses dict rows from `SearchApiZillowListingCandidate`. Decoupling the
math from the comp shape lets both call the same scoring code.

Per-listing-status divergence:
- ``score_recency_sold(sale_age_days)`` — recent sales score higher.
- ``score_recency_active(days_on_market)`` — fresh listings score higher
  than stale asks. Same banding intuition; different banding values
  because "fresh" is days, not months.

The constants in this module are the single source of truth for comp
scoring. Any consumer that cares about score banding reads them here.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

from briarwood.modules import cma_invariants


# ---------------------------------------------------------------------------
# Score weights — combine into the weighted_score
# ---------------------------------------------------------------------------

WEIGHT_PROXIMITY = 0.30
WEIGHT_RECENCY = 0.25
WEIGHT_SIMILARITY = 0.30
WEIGHT_DATA_QUALITY = 0.15

assert (
    abs(WEIGHT_PROXIMITY + WEIGHT_RECENCY + WEIGHT_SIMILARITY + WEIGHT_DATA_QUALITY - 1.0) < 1e-9
), "score weights must sum to 1.0"


# ---------------------------------------------------------------------------
# Proximity scoring
# ---------------------------------------------------------------------------


def score_proximity(distance_miles: float | None) -> float:
    """Banded proximity score. None → 0.55 (neutral missing-data score).

    Carried forward from Engine A's original `_proximity_score` unchanged.
    """
    if distance_miles is None:
        return 0.55
    if distance_miles <= 0.25:
        return 0.95
    if distance_miles <= 0.5:
        return 0.88
    if distance_miles <= 1.0:
        return 0.78
    if distance_miles <= 2.0:
        return 0.64
    return 0.42


# ---------------------------------------------------------------------------
# Recency scoring — per listing_status
# ---------------------------------------------------------------------------


def score_recency_sold(sale_age_days: int | None) -> float:
    """Banded recency score for SOLD comps. Recent sales score higher.

    Carried forward from Engine A's original `_recency_score` unchanged.
    None → 0.5 (neutral).
    """
    if sale_age_days is None:
        return 0.5
    if sale_age_days <= 90:
        return 0.95
    if sale_age_days <= 180:
        return 0.88
    if sale_age_days <= 365:
        return 0.78
    if sale_age_days <= 730:
        return 0.62
    return 0.4


def score_recency_active(days_on_market: int | None) -> float:
    """Banded recency score for ACTIVE comps. Fresh listings score higher
    than stale asks.

    Resolves the Cycle 3b open design decision (constant weight vs inverse
    days_on_market) in favor of inverse — a just-listed comp is a much
    stronger competitor signal than a 5-month-stale ask.

    Banding intuition: 'fresh' is measured in days for ACTIVE, not months
    like SOLD. None → 0.55 (slightly above neutral; ACTIVE rows usually
    have days_on_market populated, so missing is a soft signal of
    incomplete data rather than an irrelevant comp).
    """
    if days_on_market is None:
        return 0.55
    if days_on_market <= 14:
        return 0.92
    if days_on_market <= 30:
        return 0.85
    if days_on_market <= 60:
        return 0.75
    if days_on_market <= 90:
        return 0.62
    if days_on_market <= 180:
        return 0.45
    # Above ACTIVE_DOM_CAP_DAYS (180) — should be filtered upstream, but
    # if a stale ask slips through, score it low.
    return 0.30


def score_recency(
    *,
    listing_status: str | None,
    sale_age_days: int | None = None,
    days_on_market: int | None = None,
) -> float:
    """Dispatcher: pick the right recency function based on listing_status.

    ``listing_status="sold"`` uses ``sale_age_days``; ``"active"`` uses
    ``days_on_market``. Unknown status defaults to the SOLD path with
    sale_age_days (Engine A's legacy behavior).
    """
    status = (listing_status or "").lower()
    if status == "active":
        return score_recency_active(days_on_market)
    # "sold" or unknown → SOLD scoring (preserves Engine A backwards
    # compatibility for comps with no listing_status).
    return score_recency_sold(sale_age_days)


# ---------------------------------------------------------------------------
# Data quality scoring
# ---------------------------------------------------------------------------

# Verification tiers Engine A and Engine B both produce. Bonus / penalty
# values are tuning knobs.
_VERIFICATION_BONUS = {
    "public_record_verified": 0.08,
    "mls_verified": 0.08,
    "zillow_listing": 0.05,  # Cycle 3b — Zillow data is reasonable but not MLS-grade
    "user_provided": 0.0,
}
_VERIFICATION_PENALTY = {
    "questioned": -0.10,
    "unverified": -0.10,
}

_DATA_QUALITY_FLOOR = 0.2
_DATA_QUALITY_FLOOR_DEGRADED = 0.3
_DATA_QUALITY_CEILING = 1.0


def score_data_quality(
    *,
    present_fields: int,
    total_fields: int,
    verification_status: str | None = None,
) -> float:
    """Score data completeness with per-tier verification adjustment.

    Per CMA Phase 4a Cycle 3b: when more than half of the score inputs
    are missing, return ``_DATA_QUALITY_FLOOR_DEGRADED = 0.3`` as a
    baseline rather than dropping the comp entirely. Zillow rows
    routinely miss `sqft` (~28%) and `lot_sqft` (~19%); we want them
    contributing soft signal rather than being filtered.

    Otherwise: base = present/total, plus verification tier adjustment,
    bounded by [floor, ceiling].
    """
    if total_fields <= 0:
        return _DATA_QUALITY_FLOOR
    present = max(present_fields, 0)
    missing = total_fields - present
    # Degraded path: more than half of inputs missing.
    if missing > total_fields / 2:
        return _DATA_QUALITY_FLOOR_DEGRADED
    base = present / total_fields
    tier = (verification_status or "").strip().lower()
    base += _VERIFICATION_BONUS.get(tier, 0.0)
    base += _VERIFICATION_PENALTY.get(tier, 0.0)
    return max(_DATA_QUALITY_FLOOR, min(base, _DATA_QUALITY_CEILING))


# ---------------------------------------------------------------------------
# Unified comp scoring — entry point for Cycle 3c's 3-source merger
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompScores:
    """All scores for a single comp, computed via the unified pipeline.

    Returned by ``score_comp_inputs``. Engine-A callers attach these to
    the comp via ``comp.model_copy(update=...)``; Engine-B callers
    populate them on the merged comp dict directly.
    """

    proximity_score: float
    recency_score: float
    data_quality_score: float
    similarity_score: float
    weighted_score: float
    is_outlier: bool


def score_comp_inputs(
    *,
    listing_status: str | None,
    distance_miles: float | None,
    sale_age_days: int | None = None,
    days_on_market: int | None = None,
    similarity_score: float = 0.0,
    present_fields: int,
    total_fields: int,
    verification_status: str | None = None,
    extracted_price: float | None = None,
    tax_assessed_value: float | None = None,
) -> CompScores:
    """Score a single comp using the unified pipeline.

    Caller extracts the right field values from whatever comp shape it
    has (Pydantic model for Engine A, dict for Engine B). Outlier check
    runs first — if true, the comp should be filtered upstream and not
    reach the comparable_value calculation.
    """
    is_outlier = cma_invariants.is_outlier_by_tax_assessment(
        extracted_price=extracted_price,
        tax_assessed_value=tax_assessed_value,
    )
    proximity = score_proximity(distance_miles)
    recency = score_recency(
        listing_status=listing_status,
        sale_age_days=sale_age_days,
        days_on_market=days_on_market,
    )
    data_quality = score_data_quality(
        present_fields=present_fields,
        total_fields=total_fields,
        verification_status=verification_status,
    )
    similarity = float(similarity_score or 0.0)
    weighted = round(
        proximity * WEIGHT_PROXIMITY
        + recency * WEIGHT_RECENCY
        + similarity * WEIGHT_SIMILARITY
        + data_quality * WEIGHT_DATA_QUALITY,
        3,
    )
    return CompScores(
        proximity_score=round(proximity, 3),
        recency_score=round(recency, 3),
        data_quality_score=round(data_quality, 3),
        similarity_score=round(similarity, 3),
        weighted_score=weighted,
        is_outlier=is_outlier,
    )


# ---------------------------------------------------------------------------
# Geo helper — lat/lon distance estimator
# ---------------------------------------------------------------------------


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in miles between two lat/lon points.

    Carried forward from Engine A's `_distance_miles`. Uses the
    flat-earth approximation (lat × 69, lon × 53 for mid-Atlantic
    latitudes) — fast, good-enough for proximity banding within
    ~20 miles, but loses accuracy for cross-state comparisons.
    """
    lat_scale = 69.0
    lon_scale = 53.0
    return sqrt(
        ((lat1 - lat2) * lat_scale) ** 2 + ((lon1 - lon2) * lon_scale) ** 2
    )


__all__ = [
    "WEIGHT_PROXIMITY",
    "WEIGHT_RECENCY",
    "WEIGHT_SIMILARITY",
    "WEIGHT_DATA_QUALITY",
    "CompScores",
    "score_proximity",
    "score_recency_sold",
    "score_recency_active",
    "score_recency",
    "score_data_quality",
    "score_comp_inputs",
    "distance_miles",
]

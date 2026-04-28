"""CMA quality invariants — constants + validation helper.

Defines the thresholds the unified CMA pipeline (CMA Phase 4a Cycle 3) uses
to decide whether a comp set is good enough to anchor a user-facing answer,
how to weight SOLD vs ACTIVE comps in fair-value math, and which comps
should be filtered as outliers (e.g., tax-deed sales).

Defaults are informed by the 2026-04-26 SearchApi SOLD probe (see
``CMA_SOLD_PROBE_2026-04-26.md`` at the repo root). Tunable over time;
each constant here is the single source of truth — change it here and
every consumer (Cycle 3 merger, Cycle 5 chart suppression, etc.) sees
the new value.

This module is intentionally constants-and-pure-functions only — no I/O,
no LLM calls, no provider clients. Safe to import from anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from briarwood.agent.tools import CMAResult


# ---------------------------------------------------------------------------
# Comp-count floors
# ---------------------------------------------------------------------------

MIN_TOTAL_COMP_COUNT = 5
"""Below this combined SOLD+ACTIVE count (post-filter), the CMA surface
returns 'insufficient comps to anchor a CMA' rather than a low-confidence
number. Probe found 41 raw SOLD per town readily available; 5 post-filter
is reachable for our markets."""

MIN_SOLD_COUNT = 5
"""Below this post-filter SOLD count, prose qualifies the read as
'active-only' (no closed-sale anchor). SOLD is the primary value signal,
so a thin SOLD count must be visible to the synthesizer."""

MIN_ACTIVE_COUNT = 3
"""Below this, the 'what's competing right now' framing is suppressed and
the CMA surfaces SOLD only. ACTIVE inventory is naturally thinner per
probe (11-20 per town) so the floor is lower."""


# ---------------------------------------------------------------------------
# Distance + age caps
# ---------------------------------------------------------------------------

MAX_DISTANCE_MILES_SAME_TOWN = 2.0
"""Same-town comp radius cap. Engine A's existing radius logic; carry
forward unchanged."""

MAX_DISTANCE_MILES_CROSS_TOWN = 3.0
"""Cross-town comp expansion radius (used when same-town count is below
the minimum)."""

SOLD_AGE_CAP_MONTHS = 18
"""SearchApi's natural SOLD window is roughly 18 months. Anything older
either doesn't appear in returns or signals a non-arms-length / tax-deed
transaction."""

ACTIVE_DOM_CAP_DAYS = 180
"""A listing on market 6+ months is a stale ask — weak comp signal.
``days_on_zillow`` is universally available per probe (100% coverage)."""


# ---------------------------------------------------------------------------
# Confidence floor
# ---------------------------------------------------------------------------

CONFIDENCE_FLOOR = 0.45
"""Aggregate CMA confidence below this suppresses the surface entirely
from BROWSE/DECISION prose AND from the chart layer. Tunable; revisit
after Cycle 5 browser smoke."""


# ---------------------------------------------------------------------------
# Outlier filters
# ---------------------------------------------------------------------------

TAX_ASSESSED_VS_PRICE_BAND: tuple[float, float] = (0.4, 4.0)
"""SOLD comps where ``extracted_price < 0.4 * tax_assessed_value`` or
``> 4 * tax_assessed_value`` are almost certainly tax-deed sales,
foreclosure auctions, or non-arms-length transactions. Drop them before
they enter the comparable_value calculation. Skipped for rows missing
``tax_assessed_value`` (~8% of probe rows)."""


# ---------------------------------------------------------------------------
# SOLD vs ACTIVE weighting
# ---------------------------------------------------------------------------

SOLD_WEIGHT = 1.0
"""SOLD comps carry full weight in the fair-value math — sale prices are
the real signal."""

ACTIVE_WEIGHT = 0.5
"""ACTIVE comps are aspirational asks; weight at half SOLD. Tunable;
revisit after Cycle 5 browser smoke (especially in scarcity markets
where ACTIVE may underweight given seller bias)."""


# ---------------------------------------------------------------------------
# Cross-town adjacency (CMA Phase 4a Cycle 4)
# ---------------------------------------------------------------------------

TOWN_ADJACENCY: dict[str, tuple[str, ...]] = {
    "Belmar": ("Bradley Beach", "Spring Lake", "Avon By The Sea"),
    "Avon By The Sea": ("Bradley Beach", "Belmar"),
    "Bradley Beach": ("Avon By The Sea", "Belmar"),
    "Spring Lake": ("Belmar", "Sea Girt"),
    "Sea Girt": ("Spring Lake", "Manasquan"),
    "Manasquan": ("Sea Girt", "Spring Lake"),
}
"""Cross-town adjacency map for the CMA pipeline. Keyed by human-readable
town name (matches what SearchApi expects in its ``query`` parameter). Each
value is a tuple of neighboring towns to query when same-town SOLD inventory
is below ``MIN_SOLD_COUNT``. Lookups via ``neighbors_for_town`` are
case-insensitive and tolerant of common hyphenation variants
("Avon-by-the-Sea" matches "Avon By The Sea").

The map covers the six Monmouth County shore towns the product is targeted
at today. Extend here when the product expands to a new county; the lookup
helper is data-driven and does not need additional code changes."""


def _canon_town_for_adjacency(value: str) -> str:
    """Lower-case + hyphen-to-space canonicalization for adjacency lookups.
    Mirrors the ``_norm_place`` convention in ``briarwood/agent/tools.py``
    (kept duplicated to avoid a circular import — this module is imported
    by ``tools.py``).
    """
    return " ".join(value.lower().replace("-", " ").split())


def neighbors_for_town(town: str | None) -> tuple[str, ...]:
    """Return the adjacency-map neighbors for ``town``.

    Returns an empty tuple for towns not in ``TOWN_ADJACENCY`` (i.e., towns
    outside the supported product geography) — callers treat that as "no
    cross-town expansion available" and proceed with same-town comps only.
    Match is case-insensitive and tolerant of hyphenation differences.
    """
    if not isinstance(town, str) or not town.strip():
        return ()
    needle = _canon_town_for_adjacency(town)
    for key, neighbors in TOWN_ADJACENCY.items():
        if _canon_town_for_adjacency(key) == needle:
            return neighbors
    return ()


# ---------------------------------------------------------------------------
# Live-empty telemetry behavior
# ---------------------------------------------------------------------------

# When SearchApi returns empty for either listing_status, fall back to
# saved comps but emit an explicit "live SOLD/ACTIVE returned empty"
# record to the per-turn manifest (not silent — Cycle 1 audit found this
# gap). Surface as a user-visible warning ONLY when both SearchApi paths
# AND saved fallback are empty.
LIVE_EMPTY_USER_WARNING_REQUIRES_ALL_SOURCES_EMPTY = True


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CMAValidation:
    """Snapshot of whether a CMAResult passes the quality invariants.

    Returned by ``validate_cma_result``. Consumers (Cycle 3 merger, Cycle 5
    chart suppression) read ``passes`` to decide whether to surface the
    CMA, ``suppressed_reason`` for telemetry/prose qualification, and
    ``qualifications`` to soften prose when the result is borderline.
    """

    passes: bool
    total_count: int
    sold_count: int
    active_count: int
    suppressed_reason: str | None = None
    qualifications: tuple[str, ...] = field(default_factory=tuple)
    dropped_outliers: int = 0


def validate_cma_result(result: "CMAResult", *, dropped_outliers: int = 0) -> CMAValidation:
    """Apply the comp-count and confidence invariants to a CMAResult.

    Returns ``CMAValidation`` with ``passes=False`` when the result should
    be suppressed entirely; ``passes=True`` with optional ``qualifications``
    when the result surfaces but with caveats (e.g., active-only because
    SOLD count is below ``MIN_SOLD_COUNT``).

    ``dropped_outliers`` is the count of comps the upstream merger filtered
    via ``TAX_ASSESSED_VS_PRICE_BAND`` (or other outlier rules). Recorded
    on the validation record for telemetry; doesn't affect the pass/fail
    decision (those comps are already gone).

    The pricing-confidence check uses ``CMAResult.confidence_notes`` length
    as a degraded-confidence proxy until Cycle 3 lands a real
    aggregate-confidence field on CMAResult.
    """
    comps = list(result.comps or [])
    sold_count = sum(1 for c in comps if getattr(c, "listing_status", None) == "sold")
    active_count = sum(1 for c in comps if getattr(c, "listing_status", None) == "active")
    total_count = len(comps)

    qualifications: list[str] = []

    # Hard gate: not enough total comps to back any CMA claim.
    if total_count < MIN_TOTAL_COMP_COUNT:
        return CMAValidation(
            passes=False,
            total_count=total_count,
            sold_count=sold_count,
            active_count=active_count,
            suppressed_reason=(
                f"insufficient comps ({total_count} < {MIN_TOTAL_COMP_COUNT})"
            ),
            dropped_outliers=dropped_outliers,
        )

    # Soft qualification: SOLD count below floor → active-only framing.
    if sold_count < MIN_SOLD_COUNT:
        qualifications.append(
            f"active-only ({sold_count} SOLD comps; below {MIN_SOLD_COUNT} floor)"
        )

    # Soft qualification: ACTIVE count below floor → suppress competition framing.
    if active_count < MIN_ACTIVE_COUNT:
        qualifications.append(
            f"no competition signal ({active_count} ACTIVE comps; below {MIN_ACTIVE_COUNT} floor)"
        )

    return CMAValidation(
        passes=True,
        total_count=total_count,
        sold_count=sold_count,
        active_count=active_count,
        suppressed_reason=None,
        qualifications=tuple(qualifications),
        dropped_outliers=dropped_outliers,
    )


def is_outlier_by_tax_assessment(
    extracted_price: float | None,
    tax_assessed_value: float | None,
) -> bool:
    """True when a SOLD comp's price is inconsistent with its tax-assessed
    value, signaling a tax-deed sale, foreclosure, or non-arms-length
    transaction. Returns False when either input is missing — we don't
    drop comps for missing data, only for explicit price/assessment
    inconsistency.
    """
    if not isinstance(extracted_price, (int, float)) or extracted_price <= 0:
        return False
    if not isinstance(tax_assessed_value, (int, float)) or tax_assessed_value <= 0:
        return False
    ratio = float(extracted_price) / float(tax_assessed_value)
    low, high = TAX_ASSESSED_VS_PRICE_BAND
    return ratio < low or ratio > high


__all__ = [
    "MIN_TOTAL_COMP_COUNT",
    "MIN_SOLD_COUNT",
    "MIN_ACTIVE_COUNT",
    "MAX_DISTANCE_MILES_SAME_TOWN",
    "MAX_DISTANCE_MILES_CROSS_TOWN",
    "SOLD_AGE_CAP_MONTHS",
    "ACTIVE_DOM_CAP_DAYS",
    "CONFIDENCE_FLOOR",
    "TAX_ASSESSED_VS_PRICE_BAND",
    "SOLD_WEIGHT",
    "ACTIVE_WEIGHT",
    "LIVE_EMPTY_USER_WARNING_REQUIRES_ALL_SOURCES_EMPTY",
    "TOWN_ADJACENCY",
    "neighbors_for_town",
    "CMAValidation",
    "validate_cma_result",
    "is_outlier_by_tax_assessment",
]

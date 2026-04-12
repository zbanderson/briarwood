"""Micro-Location Engine.

Produces evidence-aware, individually confidence-rated within-town location
adjustments on top of the base shell value from the Base Comp Selector.

Each location factor is evaluated independently using an evidence hierarchy:
  1. Comp-based feature comparison (highest confidence for location)
  2. Bucket premium interpolation (moderate confidence)
  3. Fallback rule — conservative estimate (low confidence)
  4. Insufficient data — factor relevant but unquantifiable (no confidence)

Factors evaluated:
  - Beach proximity
  - Downtown proximity
  - Train/transit proximity
  - Flood exposure (discount)
  - Block quality / micro-context
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from statistics import median
from typing import Any

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    ComparableSalesOutput,
)
from briarwood.schemas import PropertyInput


# ---------------------------------------------------------------------------
# Distance bucket definitions — miles
# ---------------------------------------------------------------------------

# Beach: 0-3 blocks (~0.15mi), 3-6 blocks (~0.35mi), 6-12 (~0.70mi), >12
_BEACH_THRESHOLDS = [0.15, 0.35, 0.70, 1.5]

# Downtown: walkable (<0.5mi), short drive (<1.0mi), drive (>1.0mi)
_DOWNTOWN_THRESHOLDS = [0.50, 1.0, 2.0]

# Train: walking (<0.5mi), short drive (<1.0mi), drive (>1.0mi)
_TRAIN_THRESHOLDS = [0.50, 1.0, 2.0]


# ---------------------------------------------------------------------------
# Fallback rules — conservative estimates for NJ coastal markets
# ---------------------------------------------------------------------------

# Beach: estimated premium per bucket relative to farthest bucket.
# Based on NJ shore town PPSF gradients: 1-3 blocks trades 20-40% above
# 12+ blocks. These are conservative midpoints as % of base shell.
_FALLBACK_BEACH_PREMIUM_BY_BUCKET = [0.12, 0.06, 0.02, 0.0]  # near → far

# Downtown walkability premium.
# NJ shore downtown-walkable properties trade ~5-10% above non-walkable.
_FALLBACK_DOWNTOWN_PREMIUM_BY_BUCKET = [0.04, 0.015, 0.0]  # near → far

# Train proximity premium.
# NJ Transit-walkable properties trade ~2-5% above non-walkable.
_FALLBACK_TRAIN_PREMIUM_BY_BUCKET = [0.025, 0.01, 0.0]  # near → far

# Flood discount — applied as negative adjustment.
# NJ coastal flood zone properties trade 5-15% below comparable non-flood.
_FALLBACK_FLOOD_DISCOUNT = {
    "high": -0.10,      # High flood risk: -10%
    "medium": -0.05,    # Medium flood risk: -5%
    "low": 0.0,         # Low/no: no discount
    "none": 0.0,
}

# Minimum comps required for feature comparison to be considered moderate confidence.
_MIN_COMPS_PER_BUCKET = 2


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class LocationEvidence:
    """Evidence supporting a location adjustment."""
    subject_distance_miles: float | None = None
    subject_bucket: str | None = None
    near_bucket_median_price: float | None = None
    far_bucket_median_price: float | None = None
    near_bucket_count: int = 0
    far_bucket_count: int = 0
    premium_pct_observed: float | None = None
    landmark_label: str | None = None
    flood_risk_level: str | None = None
    zone_flag_value: bool | None = None
    note: str | None = None


@dataclass(slots=True)
class LocationResult:
    """Result for a single location factor evaluation."""
    applicable: bool
    adjustment: float
    confidence: str  # "high", "moderate", "low", "none", "n/a"
    method: str  # "feature_comparison", "bucket_premium", "fallback_rule", "insufficient_data", "not_applicable"
    evidence: LocationEvidence
    notes: str
    overlap_check: str | None = None


@dataclass(slots=True)
class LocationConfidenceBreakdown:
    """Breakdown of total adjustment by confidence tier."""
    high_confidence_portion: float = 0.0
    moderate_confidence_portion: float = 0.0
    low_confidence_portion: float = 0.0
    unvalued_factors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LocationAdjustedValue:
    """The adjusted value combining base shell + location."""
    base_shell_value: float | None
    plus_location: float
    location_adjusted_value: float | None
    note: str = "Location-adjusted value before feature premiums, market timing, and condition adjustments."


@dataclass(slots=True)
class MicroLocationResult:
    """Complete output of the Micro-Location Engine."""
    factors: dict[str, LocationResult]
    total_location_adjustment: float
    weighted_confidence: str
    confidence_breakdown: LocationConfidenceBreakdown
    overlap_warnings: list[str]
    adjusted_value: LocationAdjustedValue


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_micro_location(
    *,
    property_input: PropertyInput,
    comp_output: ComparableSalesOutput,
    base_comp_selection: BaseCompSelection | None = None,
    town_metrics: dict[str, Any] | None = None,
    location_intelligence: dict[str, Any] | None = None,
) -> MicroLocationResult:
    """Evaluate all micro-location adjustments for a property.

    Args:
        property_input: The subject property.
        comp_output: Full comparable sales output (contains comps_used).
        base_comp_selection: The base comp selection result.
        town_metrics: Town-level metrics (median price, etc.). Optional.
        location_intelligence: Output from LocationIntelligenceModule. Optional.

    Returns:
        MicroLocationResult with per-factor adjustments and totals.
    """
    selection = base_comp_selection or comp_output.base_comp_selection
    comps = list(comp_output.comps_used or [])
    base_shell = (
        (selection.base_shell_value if selection else None)
        or comp_output.comparable_value
    )

    landmarks = property_input.landmark_points or {}
    subject_lat = property_input.latitude
    subject_lon = property_input.longitude

    factors: dict[str, LocationResult] = {}
    overlap_warnings: list[str] = []

    # --- Beach Proximity ---
    factors["beach"] = _evaluate_beach(
        subject_lat, subject_lon, landmarks.get("beach", []),
        comps, base_shell,
    )

    # --- Downtown Proximity ---
    factors["downtown"] = _evaluate_downtown(
        subject_lat, subject_lon, landmarks.get("downtown", []),
        comps, base_shell,
    )

    # --- Train Proximity ---
    factors["train"] = _evaluate_train(
        subject_lat, subject_lon, landmarks.get("train", []),
        comps, base_shell,
    )

    # --- Flood Exposure ---
    factors["flood"] = _evaluate_flood(
        property_input, base_shell,
    )

    # --- Block Quality ---
    factors["block_quality"] = _evaluate_block_quality(property_input)

    # --- Overlap checks ---
    beach = factors["beach"]
    downtown = factors["downtown"]
    if beach.applicable and beach.adjustment > 0 and downtown.applicable and downtown.adjustment > 0:
        overlap_warnings.append(
            "Both beach and downtown proximity are valued. In compact shore towns, "
            "properties near the beach are often also near downtown. The combined "
            "premium may partially overlap."
        )

    # --- Totals ---
    total = sum(f.adjustment for f in factors.values())
    breakdown = _confidence_breakdown(factors)
    weighted_conf = _weighted_confidence(factors, total)

    adjusted = LocationAdjustedValue(
        base_shell_value=round(base_shell, 2) if base_shell else None,
        plus_location=round(total, 2),
        location_adjusted_value=round(base_shell + total, 2) if base_shell else None,
    )

    return MicroLocationResult(
        factors=factors,
        total_location_adjustment=round(total, 2),
        weighted_confidence=weighted_conf,
        confidence_breakdown=breakdown,
        overlap_warnings=overlap_warnings,
        adjusted_value=adjusted,
    )


# ---------------------------------------------------------------------------
# Factor evaluators
# ---------------------------------------------------------------------------

def _evaluate_beach(
    subject_lat: float | None,
    subject_lon: float | None,
    beach_points: list[dict[str, Any]],
    comps: list[AdjustedComparable],
    base_shell: float | None,
) -> LocationResult:
    """Evaluate beach proximity premium."""
    subject_dist = _distance_to_nearest(subject_lat, subject_lon, beach_points)
    if subject_dist is None:
        return _not_applicable("beach", "Subject coordinates or beach landmark data not available.")

    subject_bucket_idx = _bucket_index(subject_dist, _BEACH_THRESHOLDS)
    subject_bucket = _beach_bucket_label(subject_bucket_idx)
    nearest_label = _nearest_point_label(subject_lat, subject_lon, beach_points)

    # If subject is in the farthest bucket, no premium.
    if subject_bucket_idx >= len(_FALLBACK_BEACH_PREMIUM_BY_BUCKET) - 1:
        return LocationResult(
            applicable=True,
            adjustment=0,
            confidence="moderate",
            method="feature_comparison",
            evidence=LocationEvidence(
                subject_distance_miles=round(subject_dist, 3),
                subject_bucket=subject_bucket,
                landmark_label=nearest_label,
            ),
            notes=f"Subject is {subject_dist:.2f}mi from beach ({subject_bucket}). No premium for this distance bucket.",
            overlap_check=None,
        )

    # Attempt feature comparison: comps near beach vs comps far from beach.
    comp_near, comp_far = _split_comps_by_tag(comps, "beach")

    if len(comp_near) >= _MIN_COMPS_PER_BUCKET and len(comp_far) >= _MIN_COMPS_PER_BUCKET:
        med_near = median(c.adjusted_price for c in comp_near)
        med_far = median(c.adjusted_price for c in comp_far)
        observed_premium_pct = (med_near - med_far) / med_far if med_far > 0 else 0
        # Scale the premium by where the subject sits in the near bucket.
        adjustment = round(med_near - med_far, 2)
        # Cap at 25% of base shell.
        if base_shell and abs(adjustment) > base_shell * 0.25:
            adjustment = round(base_shell * 0.25 * (1 if adjustment > 0 else -1), 2)
        return LocationResult(
            applicable=True,
            adjustment=adjustment,
            confidence="moderate",
            method="feature_comparison",
            evidence=LocationEvidence(
                subject_distance_miles=round(subject_dist, 3),
                subject_bucket=subject_bucket,
                near_bucket_median_price=round(med_near, 2),
                far_bucket_median_price=round(med_far, 2),
                near_bucket_count=len(comp_near),
                far_bucket_count=len(comp_far),
                premium_pct_observed=round(observed_premium_pct, 4),
                landmark_label=nearest_label,
            ),
            notes=(
                f"Subject is {subject_dist:.2f}mi from beach ({subject_bucket}). "
                f"Local comp median: ${med_near:,.0f} near vs ${med_far:,.0f} far "
                f"({len(comp_near)} near, {len(comp_far)} far). "
                f"Observed premium: {observed_premium_pct:.1%}."
            ),
            overlap_check="Beach proximity and downtown proximity may overlap in compact shore towns.",
        )

    # Fallback: use conservative bucket premium.
    if base_shell and base_shell > 0:
        premium_pct = _FALLBACK_BEACH_PREMIUM_BY_BUCKET[subject_bucket_idx]
        adjustment = round(base_shell * premium_pct, 2)
    else:
        adjustment = 0
    return LocationResult(
        applicable=True,
        adjustment=adjustment,
        confidence="low",
        method="fallback_rule",
        evidence=LocationEvidence(
            subject_distance_miles=round(subject_dist, 3),
            subject_bucket=subject_bucket,
            near_bucket_count=len(comp_near),
            far_bucket_count=len(comp_far),
            landmark_label=nearest_label,
            note=f"Insufficient comp split for feature comparison ({len(comp_near)} near, {len(comp_far)} far).",
        ),
        notes=(
            f"Subject is {subject_dist:.2f}mi from beach ({subject_bucket}). "
            f"Fallback beach premium of {_FALLBACK_BEACH_PREMIUM_BY_BUCKET[subject_bucket_idx]:.0%} applied. "
            f"Low confidence — insufficient comp evidence for local beach gradient."
        ),
        overlap_check="Beach proximity and downtown proximity may overlap in compact shore towns.",
    )


def _evaluate_downtown(
    subject_lat: float | None,
    subject_lon: float | None,
    downtown_points: list[dict[str, Any]],
    comps: list[AdjustedComparable],
    base_shell: float | None,
) -> LocationResult:
    """Evaluate downtown walkability premium."""
    subject_dist = _distance_to_nearest(subject_lat, subject_lon, downtown_points)
    if subject_dist is None:
        return _not_applicable("downtown", "Subject coordinates or downtown landmark data not available.")

    subject_bucket_idx = _bucket_index(subject_dist, _DOWNTOWN_THRESHOLDS)
    subject_bucket = _proximity_bucket_label(subject_bucket_idx, _DOWNTOWN_THRESHOLDS, "downtown")
    nearest_label = _nearest_point_label(subject_lat, subject_lon, downtown_points)

    if subject_bucket_idx >= len(_FALLBACK_DOWNTOWN_PREMIUM_BY_BUCKET) - 1:
        return LocationResult(
            applicable=True,
            adjustment=0,
            confidence="moderate",
            method="feature_comparison",
            evidence=LocationEvidence(
                subject_distance_miles=round(subject_dist, 3),
                subject_bucket=subject_bucket,
                landmark_label=nearest_label,
            ),
            notes=f"Subject is {subject_dist:.2f}mi from downtown ({subject_bucket}). No walkability premium at this distance.",
            overlap_check=None,
        )

    comp_near, comp_far = _split_comps_by_tag(comps, "downtown")

    if len(comp_near) >= _MIN_COMPS_PER_BUCKET and len(comp_far) >= _MIN_COMPS_PER_BUCKET:
        med_near = median(c.adjusted_price for c in comp_near)
        med_far = median(c.adjusted_price for c in comp_far)
        observed_premium_pct = (med_near - med_far) / med_far if med_far > 0 else 0
        adjustment = round(med_near - med_far, 2)
        if base_shell and abs(adjustment) > base_shell * 0.12:
            adjustment = round(base_shell * 0.12 * (1 if adjustment > 0 else -1), 2)
        return LocationResult(
            applicable=True,
            adjustment=adjustment,
            confidence="moderate",
            method="feature_comparison",
            evidence=LocationEvidence(
                subject_distance_miles=round(subject_dist, 3),
                subject_bucket=subject_bucket,
                near_bucket_median_price=round(med_near, 2),
                far_bucket_median_price=round(med_far, 2),
                near_bucket_count=len(comp_near),
                far_bucket_count=len(comp_far),
                premium_pct_observed=round(observed_premium_pct, 4),
                landmark_label=nearest_label,
            ),
            notes=(
                f"Subject is {subject_dist:.2f}mi from downtown ({subject_bucket}). "
                f"Local comp median: ${med_near:,.0f} near vs ${med_far:,.0f} far "
                f"({len(comp_near)} near, {len(comp_far)} far). "
                f"Observed premium: {observed_premium_pct:.1%}."
            ),
            overlap_check="Downtown and beach proximity may overlap in compact shore towns.",
        )

    if base_shell and base_shell > 0:
        premium_pct = _FALLBACK_DOWNTOWN_PREMIUM_BY_BUCKET[subject_bucket_idx]
        adjustment = round(base_shell * premium_pct, 2)
    else:
        adjustment = 0
    return LocationResult(
        applicable=True,
        adjustment=adjustment,
        confidence="low",
        method="fallback_rule",
        evidence=LocationEvidence(
            subject_distance_miles=round(subject_dist, 3),
            subject_bucket=subject_bucket,
            near_bucket_count=len(comp_near),
            far_bucket_count=len(comp_far),
            landmark_label=nearest_label,
            note=f"Insufficient comp split ({len(comp_near)} near, {len(comp_far)} far).",
        ),
        notes=(
            f"Subject is {subject_dist:.2f}mi from downtown ({subject_bucket}). "
            f"Fallback downtown premium of {_FALLBACK_DOWNTOWN_PREMIUM_BY_BUCKET[subject_bucket_idx]:.1%} applied. "
            f"Low confidence — insufficient comp evidence for local downtown gradient."
        ),
        overlap_check="Downtown and beach proximity may overlap in compact shore towns.",
    )


def _evaluate_train(
    subject_lat: float | None,
    subject_lon: float | None,
    train_points: list[dict[str, Any]],
    comps: list[AdjustedComparable],
    base_shell: float | None,
) -> LocationResult:
    """Evaluate train/transit proximity premium."""
    subject_dist = _distance_to_nearest(subject_lat, subject_lon, train_points)
    if subject_dist is None:
        return _not_applicable("train", "Subject coordinates or train landmark data not available.")

    subject_bucket_idx = _bucket_index(subject_dist, _TRAIN_THRESHOLDS)
    subject_bucket = _proximity_bucket_label(subject_bucket_idx, _TRAIN_THRESHOLDS, "train")
    nearest_label = _nearest_point_label(subject_lat, subject_lon, train_points)

    if subject_bucket_idx >= len(_FALLBACK_TRAIN_PREMIUM_BY_BUCKET) - 1:
        return LocationResult(
            applicable=True,
            adjustment=0,
            confidence="moderate",
            method="feature_comparison",
            evidence=LocationEvidence(
                subject_distance_miles=round(subject_dist, 3),
                subject_bucket=subject_bucket,
                landmark_label=nearest_label,
            ),
            notes=f"Subject is {subject_dist:.2f}mi from train ({subject_bucket}). No transit premium at this distance.",
            overlap_check=None,
        )

    comp_near, comp_far = _split_comps_by_tag(comps, "train")

    if len(comp_near) >= _MIN_COMPS_PER_BUCKET and len(comp_far) >= _MIN_COMPS_PER_BUCKET:
        med_near = median(c.adjusted_price for c in comp_near)
        med_far = median(c.adjusted_price for c in comp_far)
        observed_premium_pct = (med_near - med_far) / med_far if med_far > 0 else 0
        adjustment = round(med_near - med_far, 2)
        if base_shell and abs(adjustment) > base_shell * 0.08:
            adjustment = round(base_shell * 0.08 * (1 if adjustment > 0 else -1), 2)
        return LocationResult(
            applicable=True,
            adjustment=adjustment,
            confidence="moderate",
            method="feature_comparison",
            evidence=LocationEvidence(
                subject_distance_miles=round(subject_dist, 3),
                subject_bucket=subject_bucket,
                near_bucket_median_price=round(med_near, 2),
                far_bucket_median_price=round(med_far, 2),
                near_bucket_count=len(comp_near),
                far_bucket_count=len(comp_far),
                premium_pct_observed=round(observed_premium_pct, 4),
                landmark_label=nearest_label,
            ),
            notes=(
                f"Subject is {subject_dist:.2f}mi from train ({subject_bucket}). "
                f"Local comp median: ${med_near:,.0f} near vs ${med_far:,.0f} far "
                f"({len(comp_near)} near, {len(comp_far)} far). "
                f"Observed premium: {observed_premium_pct:.1%}."
            ),
            overlap_check="Train premium is independent of beach/downtown.",
        )

    if base_shell and base_shell > 0:
        premium_pct = _FALLBACK_TRAIN_PREMIUM_BY_BUCKET[subject_bucket_idx]
        adjustment = round(base_shell * premium_pct, 2)
    else:
        adjustment = 0
    return LocationResult(
        applicable=True,
        adjustment=adjustment,
        confidence="low",
        method="fallback_rule",
        evidence=LocationEvidence(
            subject_distance_miles=round(subject_dist, 3),
            subject_bucket=subject_bucket,
            near_bucket_count=len(comp_near),
            far_bucket_count=len(comp_far),
            landmark_label=nearest_label,
            note=f"Insufficient comp split ({len(comp_near)} near, {len(comp_far)} far).",
        ),
        notes=(
            f"Subject is {subject_dist:.2f}mi from train ({subject_bucket}). "
            f"Fallback train premium of {_FALLBACK_TRAIN_PREMIUM_BY_BUCKET[subject_bucket_idx]:.1%} applied. "
            f"Low confidence — insufficient comp evidence for local transit gradient."
        ),
        overlap_check="Train premium is independent of beach/downtown.",
    )


def _evaluate_flood(
    property_input: PropertyInput,
    base_shell: float | None,
) -> LocationResult:
    """Evaluate flood exposure discount."""
    zone_flags = property_input.zone_flags or {}
    in_flood_zone = zone_flags.get("in_flood_zone")
    flood_risk = (property_input.flood_risk or "").strip().lower()

    # Determine effective flood level.
    if in_flood_zone is True:
        effective_level = "high"
    elif in_flood_zone is False:
        effective_level = "none"
    elif flood_risk in _FALLBACK_FLOOD_DISCOUNT:
        effective_level = flood_risk
    else:
        # No flood data at all.
        return _not_applicable("flood", "No flood risk data available for this property.")

    discount_pct = _FALLBACK_FLOOD_DISCOUNT.get(effective_level, 0.0)

    if discount_pct == 0.0:
        return LocationResult(
            applicable=True,
            adjustment=0,
            confidence="moderate",
            method="fallback_rule",
            evidence=LocationEvidence(
                flood_risk_level=effective_level,
                zone_flag_value=in_flood_zone,
            ),
            notes=f"Flood risk: {effective_level}. No flood discount applied.",
            overlap_check=None,
        )

    if base_shell and base_shell > 0:
        adjustment = round(base_shell * discount_pct, 2)  # negative
    else:
        adjustment = 0

    confidence = "low"
    method = "fallback_rule"
    note_detail = ""
    if in_flood_zone is True:
        note_detail = "Parcel-level flood zone flag is set. "
        confidence = "moderate" if flood_risk == "high" else "low"
    elif flood_risk:
        note_detail = f"Town-level flood risk classification: {flood_risk}. "

    return LocationResult(
        applicable=True,
        adjustment=adjustment,
        confidence=confidence,
        method=method,
        evidence=LocationEvidence(
            flood_risk_level=effective_level,
            zone_flag_value=in_flood_zone,
            note=f"{note_detail}Discount based on NJ coastal flood zone market evidence.",
        ),
        notes=(
            f"Flood exposure: {effective_level}. {note_detail}"
            f"Discount of {abs(discount_pct):.0%} applied to base shell. "
            f"NJ coastal flood zone properties typically trade 5-15% below comparable non-flood properties."
        ),
        overlap_check="Flood discount is independent of proximity premiums and applied additively.",
    )


def _evaluate_block_quality(property_input: PropertyInput) -> LocationResult:
    """Evaluate block/micro-context quality.

    Currently insufficient structured data for quantification. Scaffolded for
    future integration with parcel-level data (street condition, adjacent uses,
    block-level crime, neighbor property condition).
    """
    location_tags = []
    micro_notes = []

    # Check if any location-relevant signals exist on the property input.
    zone_flags = property_input.zone_flags or {}
    in_premium_zone = zone_flags.get("in_beach_premium_zone") or zone_flags.get("in_downtown_zone")

    if in_premium_zone:
        return LocationResult(
            applicable=True,
            adjustment=0,
            confidence="none",
            method="insufficient_data",
            evidence=LocationEvidence(
                zone_flag_value=True,
                note="Premium zone flag detected but no block-level data to quantify.",
            ),
            notes=(
                "Property is flagged in a premium zone (beach or downtown), suggesting favorable block context. "
                "Block-level quantification requires parcel-level data not yet available."
            ),
            overlap_check="Beach/downtown premium zones may already be captured in proximity adjustments.",
        )

    return _not_applicable(
        "block_quality",
        "No block-level quality data available. Requires parcel-level data integration.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _not_applicable(factor_key: str, note: str) -> LocationResult:
    """Standard result for a factor that can't be evaluated."""
    return LocationResult(
        applicable=False,
        adjustment=0,
        confidence="n/a",
        method="not_applicable",
        evidence=LocationEvidence(),
        notes=note,
        overlap_check=None,
    )


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in miles."""
    radius = 3958.8
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def _distance_to_nearest(
    lat: float | None,
    lon: float | None,
    points: list[dict[str, Any]],
) -> float | None:
    """Return distance in miles to the nearest point, or None."""
    if lat is None or lon is None or not points:
        return None
    distances: list[float] = []
    for point in points:
        p_lat = _point_coord(point, "latitude", "lat")
        p_lon = _point_coord(point, "longitude", "lon", "lng")
        if p_lat is None or p_lon is None:
            continue
        distances.append(_haversine_miles(lat, lon, p_lat, p_lon))
    return min(distances) if distances else None


def _nearest_point_label(
    lat: float | None,
    lon: float | None,
    points: list[dict[str, Any]],
) -> str | None:
    """Return the label of the nearest point."""
    if lat is None or lon is None or not points:
        return None
    best_dist = float("inf")
    best_label = None
    for point in points:
        p_lat = _point_coord(point, "latitude", "lat")
        p_lon = _point_coord(point, "longitude", "lon", "lng")
        if p_lat is None or p_lon is None:
            continue
        d = _haversine_miles(lat, lon, p_lat, p_lon)
        if d < best_dist:
            best_dist = d
            best_label = point.get("label")
    return best_label


def _point_coord(point: dict[str, Any], *keys: str) -> float | None:
    """Extract a coordinate value from a landmark point dict."""
    for key in keys:
        val = point.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def _split_comps_by_tag(
    comps: list[AdjustedComparable],
    tag: str,
) -> tuple[list[AdjustedComparable], list[AdjustedComparable]]:
    """Split comps by location_tags presence.

    AdjustedComparable does not carry lat/lon, so we use location_tags
    as a proxy for proximity. Comps tagged with the given category
    (e.g., "beach") are classified as 'near'; those without are 'far'.
    """
    near: list[AdjustedComparable] = []
    far: list[AdjustedComparable] = []
    tag_lower = tag.lower()
    for comp in comps:
        tags = [t.lower() for t in (comp.location_tags or [])]
        if tag_lower in tags or any(tag_lower in t for t in tags):
            near.append(comp)
        else:
            far.append(comp)
    return near, far


def _bucket_index(distance: float, thresholds: list[float]) -> int:
    """Return the bucket index for a distance given threshold boundaries."""
    for i, threshold in enumerate(thresholds):
        if distance <= threshold:
            return i
    return len(thresholds)


def _beach_bucket_label(bucket_idx: int) -> str:
    """Human-readable label for a beach distance bucket."""
    labels = ["0-3 blocks", "3-6 blocks", "6-12 blocks", "12+ blocks", "distant"]
    return labels[min(bucket_idx, len(labels) - 1)]


def _proximity_bucket_label(bucket_idx: int, thresholds: list[float], category: str) -> str:
    """Human-readable label for a generic proximity bucket."""
    if bucket_idx == 0:
        return f"walkable (<{thresholds[0]}mi)"
    elif bucket_idx < len(thresholds):
        return f"short drive ({thresholds[bucket_idx - 1]}-{thresholds[bucket_idx]}mi)"
    else:
        return f"drive (>{thresholds[-1]}mi)"


def _confidence_breakdown(factors: dict[str, LocationResult]) -> LocationConfidenceBreakdown:
    """Aggregate adjustments by confidence tier."""
    high = 0.0
    moderate = 0.0
    low = 0.0
    unvalued: list[str] = []
    for key, f in factors.items():
        if not f.applicable:
            continue
        if f.confidence == "high":
            high += f.adjustment
        elif f.confidence == "moderate":
            moderate += f.adjustment
        elif f.confidence == "low":
            low += f.adjustment
        elif f.confidence in ("none", "n/a") and f.method not in ("not_applicable",):
            unvalued.append(key)
    return LocationConfidenceBreakdown(
        high_confidence_portion=round(high, 2),
        moderate_confidence_portion=round(moderate, 2),
        low_confidence_portion=round(low, 2),
        unvalued_factors=unvalued,
    )


def _weighted_confidence(factors: dict[str, LocationResult], total: float) -> str:
    """Determine overall confidence based on where the adjustment mass sits."""
    if total == 0:
        return "n/a"
    breakdown = _confidence_breakdown(factors)
    abs_total = abs(total)
    high_pct = abs(breakdown.high_confidence_portion) / abs_total if abs_total else 0
    moderate_pct = abs(breakdown.moderate_confidence_portion) / abs_total if abs_total else 0
    if high_pct >= 0.60:
        return "high"
    if (high_pct + moderate_pct) >= 0.60:
        return "moderate"
    return "low"

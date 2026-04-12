"""Feature Adjustment Engine.

Produces evidence-aware, individually confident-rated feature adjustments
on top of the base shell value from the Base Comp Selector.

Each feature is evaluated independently using an evidence hierarchy:
  1. Paired-sale evidence (highest confidence)
  2. Feature-comparison sets (moderate confidence)
  3. Income proxy — for income-producing features (moderate confidence)
  4. Fallback rule — conservative assumption (low confidence)
  5. Insufficient data — feature present but unquantifiable (no confidence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    ComparableSalesOutput,
)
from briarwood.schemas import PropertyInput


# ---------------------------------------------------------------------------
# Fallback constants — conservative estimates used ONLY when no local
# evidence is available. Each is tagged low-confidence in the output.
# ---------------------------------------------------------------------------

# Garage: $/space when no paired evidence. Based on NJ coastal market
# garage additions costing $25-45K but only recouping 50-70%.
_FALLBACK_GARAGE_VALUE_PER_SPACE = 18_000

# Finished basement: $/sqft for below-grade finished space.
# NJ coastal averages $30-45/sqft for finished basement.
_FALLBACK_BASEMENT_FINISHED_PER_SQFT = 35

# Unfinished basement: flat value for storage/utility space.
_FALLBACK_BASEMENT_UNFINISHED = 8_000

# Pool: inground pool premium/discount. NJ coastal inground pools
# recoup 30-60% of cost. Conservative midpoint.
_FALLBACK_POOL_INGROUND = 15_000

# Above-ground pools generally add no value and can be negative.
_FALLBACK_POOL_ABOVE_GROUND = 0

# Extra parking: per-space value for dedicated off-street parking
# beyond standard. Beach towns with scarce parking value this more.
_FALLBACK_PARKING_PER_SPACE = 5_000

# ADU cap rate for income proxy when no local cap rate data.
_FALLBACK_ADU_CAP_RATE = 0.075

# ADU expense ratio applied to gross rent.
_FALLBACK_ADU_EXPENSE_RATIO = 0.30

# Lot land value per sqft for excess lot area (NJ coastal).
_FALLBACK_EXCESS_LAND_PER_SQFT = 5.50

# Town median lot size fallback (acres) if no town data available.
_FALLBACK_TOWN_MEDIAN_LOT_ACRES = 0.10

# Legal multi-unit premium as % of base value.
_FALLBACK_LEGAL_MULTI_UNIT_PCT = 0.04


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FeatureEvidence:
    """Evidence supporting a feature adjustment."""
    paired_sales_found: int = 0
    comparison_set_size: int = 0
    with_feature_median: float | None = None
    without_feature_median: float | None = None
    sample_with: int = 0
    sample_without: int = 0
    local_rent_estimate: float | None = None
    cap_rate_used: float | None = None
    subject_lot_sqft: float | None = None
    town_median_lot_sqft: float | None = None
    excess_sqft: float | None = None
    local_land_value_per_sqft: float | None = None
    raw_excess_value: float | None = None
    far_data_available: bool | None = None
    zoning_data_available: bool | None = None
    note: str | None = None


@dataclass(slots=True)
class FeatureResult:
    """Result for a single feature evaluation."""
    present: bool
    adjustment: float
    confidence: str  # "high", "moderate", "low", "none", "n/a"
    method: str  # "paired_sales", "feature_comparison", "income_proxy", "fallback_rule", "insufficient_data", "not_applicable"
    evidence: FeatureEvidence
    notes: str
    overlap_check: str | None = None


@dataclass(slots=True)
class ConfidenceBreakdown:
    """Breakdown of total adjustment by confidence tier."""
    high_confidence_portion: float = 0.0
    moderate_confidence_portion: float = 0.0
    low_confidence_portion: float = 0.0
    unvalued_features: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AdjustedValue:
    """The final adjusted value combining base shell + features."""
    base_shell_value: float | None
    plus_features: float
    feature_adjusted_value: float | None
    note: str = "Feature-adjusted value before location premiums, market timing, and condition adjustments."


@dataclass(slots=True)
class FeatureAdjustmentResult:
    """Complete output of the Feature Adjustment Engine."""
    features: dict[str, FeatureResult]
    total_feature_adjustment: float
    weighted_confidence: str
    confidence_breakdown: ConfidenceBreakdown
    overlap_warnings: list[str]
    adjusted_value: AdjustedValue


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_feature_adjustments(
    *,
    property_input: PropertyInput,
    comp_output: ComparableSalesOutput,
    base_comp_selection: BaseCompSelection | None = None,
    town_metrics: dict[str, Any] | None = None,
) -> FeatureAdjustmentResult:
    """Evaluate all feature adjustments for a property.

    Args:
        property_input: The subject property.
        comp_output: Full comparable sales output (contains comps_used, base_comp_selection).
        base_comp_selection: The base comp selection result. Falls back to comp_output.base_comp_selection.
        town_metrics: Town-level metrics (median lot size, etc.). Optional.

    Returns:
        FeatureAdjustmentResult with per-feature adjustments and totals.
    """
    selection = base_comp_selection or comp_output.base_comp_selection
    comps = list(comp_output.comps_used or [])
    base_shell = (
        (selection.base_shell_value if selection else None)
        or comp_output.comparable_value
    )

    features: dict[str, FeatureResult] = {}
    overlap_warnings: list[str] = []

    # Track what we value so we can check overlaps.
    adu_valued = False
    lot_premium_valued = False
    garage_valued = False

    # --- ADU ---
    adu_result = _evaluate_adu(property_input, comps, comp_output, base_shell)
    features["adu"] = adu_result
    adu_valued = adu_result.present and adu_result.adjustment > 0

    # --- Garage ---
    garage_result = _evaluate_garage(property_input, comps, base_shell)
    features["garage"] = garage_result
    garage_valued = garage_result.present and garage_result.adjustment > 0

    # --- Basement ---
    features["basement"] = _evaluate_basement(property_input, comps, base_shell)

    # --- Pool ---
    features["pool"] = _evaluate_pool(property_input, comps, base_shell)

    # --- Lot Premium ---
    lot_result = _evaluate_lot_premium(property_input, comps, base_shell, town_metrics)
    features["lot_premium"] = lot_result
    lot_premium_valued = lot_result.present and lot_result.adjustment > 0

    # --- Expansion Potential ---
    expansion_result = _evaluate_expansion(property_input, lot_result)
    features["expansion"] = expansion_result

    # --- Extra Parking ---
    parking_result = _evaluate_extra_parking(property_input, garage_result)
    features["extra_parking"] = parking_result

    # --- Legal Multi-Unit ---
    features["legal_multi_unit"] = _evaluate_legal_multi_unit(property_input, base_shell, adu_valued)

    # --- Special Utility ---
    features["special_utility"] = _evaluate_special_utility(property_input)

    # --- Overlap checks ---
    if adu_valued and comp_output.is_hybrid_valuation:
        overlap_warnings.append(
            "ADU income is already captured in the hybrid valuation's income capitalization. "
            "The feature adjustment engine defers to the hybrid module to avoid double-counting."
        )
        # Zero out the ADU adjustment to avoid double-counting with hybrid valuation.
        features["adu"] = FeatureResult(
            present=True,
            adjustment=0,
            confidence="n/a",
            method="deferred_to_hybrid",
            evidence=adu_result.evidence,
            notes="ADU income is already valued in the hybrid valuation module. Zeroed here to avoid double-counting.",
            overlap_check="Deferred to hybrid_value module which already capitalizes ADU income.",
        )

    if lot_premium_valued and expansion_result.present and expansion_result.adjustment > 0:
        overlap_warnings.append(
            "Both lot premium and expansion potential are valued. "
            "Lot premium covers land value; expansion covers buildable potential. "
            "Verify these are measuring different things for this property."
        )

    if garage_valued and parking_result.present and parking_result.adjustment > 0:
        overlap_warnings.append(
            "Both garage and extra parking are valued. "
            "Ensure garage spaces are not also counted as extra parking."
        )

    # --- Totals ---
    total = sum(f.adjustment for f in features.values())
    breakdown = _confidence_breakdown(features)
    weighted_conf = _weighted_confidence(features, total)

    adjusted = AdjustedValue(
        base_shell_value=round(base_shell, 2) if base_shell else None,
        plus_features=round(total, 2),
        feature_adjusted_value=round(base_shell + total, 2) if base_shell else None,
    )

    return FeatureAdjustmentResult(
        features=features,
        total_feature_adjustment=round(total, 2),
        weighted_confidence=weighted_conf,
        confidence_breakdown=breakdown,
        overlap_warnings=overlap_warnings,
        adjusted_value=adjusted,
    )


# ---------------------------------------------------------------------------
# Feature evaluators
# ---------------------------------------------------------------------------

def _evaluate_adu(
    pi: PropertyInput,
    comps: list[AdjustedComparable],
    comp_output: ComparableSalesOutput,
    base_shell: float | None,
) -> FeatureResult:
    """Evaluate ADU / detached cottage / second structure."""
    has_adu = bool(pi.has_back_house) or bool(pi.adu_type) or bool(pi.additional_units)
    if not has_adu:
        return _not_present("adu", "No ADU, back house, or detached cottage identified.")

    # Try income proxy: capitalize rental income.
    monthly_rent = pi.back_house_monthly_rent or pi.estimated_monthly_rent
    unit_rents = pi.unit_rents or []

    # If hybrid valuation already computed income value, use that as evidence.
    if comp_output.is_hybrid_valuation and comp_output.additional_unit_income_value:
        return FeatureResult(
            present=True,
            adjustment=round(comp_output.additional_unit_income_value, 2),
            confidence="moderate",
            method="income_proxy",
            evidence=FeatureEvidence(
                local_rent_estimate=comp_output.additional_unit_annual_income / 12 if comp_output.additional_unit_annual_income else None,
                cap_rate_used=comp_output.additional_unit_cap_rate,
                note="Value from hybrid valuation income capitalization.",
            ),
            notes=(
                f"ADU valued at ${comp_output.additional_unit_income_value:,.0f} via income capitalization "
                f"from the hybrid valuation module."
            ),
            overlap_check="This value comes from the hybrid valuation module. Do not add separately.",
        )

    # Income proxy from rent data.
    if monthly_rent and monthly_rent > 0:
        annual_gross = monthly_rent * 12
        noi = annual_gross * (1 - _FALLBACK_ADU_EXPENSE_RATIO)
        value = noi / _FALLBACK_ADU_CAP_RATE
        if base_shell:
            value = min(value, base_shell * 0.35)  # cap at 35% of base shell
        return FeatureResult(
            present=True,
            adjustment=round(value, 2),
            confidence="moderate",
            method="income_proxy",
            evidence=FeatureEvidence(
                local_rent_estimate=monthly_rent,
                cap_rate_used=_FALLBACK_ADU_CAP_RATE,
            ),
            notes=(
                f"{'Back house' if pi.has_back_house else 'ADU'} "
                f"({'type: ' + pi.adu_type if pi.adu_type else 'untyped'}). "
                f"Valued via rental income: ${monthly_rent:,.0f}/mo gross, "
                f"{_FALLBACK_ADU_EXPENSE_RATIO:.0%} expense ratio, "
                f"{_FALLBACK_ADU_CAP_RATE:.1%} cap rate."
            ),
            overlap_check="If hybrid valuation also capitalizes ADU income, this should be zeroed to avoid double-counting.",
        )

    if unit_rents:
        total_monthly = sum(unit_rents)
        annual_gross = total_monthly * 12
        noi = annual_gross * (1 - _FALLBACK_ADU_EXPENSE_RATIO)
        value = noi / _FALLBACK_ADU_CAP_RATE
        if base_shell:
            value = min(value, base_shell * 0.35)
        return FeatureResult(
            present=True,
            adjustment=round(value, 2),
            confidence="moderate",
            method="income_proxy",
            evidence=FeatureEvidence(
                local_rent_estimate=total_monthly,
                cap_rate_used=_FALLBACK_ADU_CAP_RATE,
            ),
            notes=(
                f"Multi-unit income from {len(unit_rents)} unit(s). "
                f"Total rent: ${total_monthly:,.0f}/mo gross, "
                f"{_FALLBACK_ADU_EXPENSE_RATIO:.0%} expense ratio, "
                f"{_FALLBACK_ADU_CAP_RATE:.1%} cap rate."
            ),
            overlap_check="If hybrid valuation also capitalizes unit income, this should be zeroed to avoid double-counting.",
        )

    # ADU present but no rent data — insufficient evidence to value.
    return FeatureResult(
        present=True,
        adjustment=0,
        confidence="none",
        method="insufficient_data",
        evidence=FeatureEvidence(
            note="ADU/back house detected but no rental income data available to value it.",
        ),
        notes=(
            f"{'Back house' if pi.has_back_house else 'ADU'} detected "
            f"({'type: ' + pi.adu_type if pi.adu_type else 'untyped'}) "
            f"but no rent data available. Cannot value without income evidence."
        ),
        overlap_check=None,
    )


def _evaluate_garage(
    pi: PropertyInput,
    comps: list[AdjustedComparable],
    base_shell: float | None,
) -> FeatureResult:
    """Evaluate garage value using comp-based feature comparison or fallback."""
    spaces = pi.garage_spaces
    if not spaces or spaces <= 0:
        return _not_present("garage", "No garage identified on subject property.")

    # Attempt feature comparison: comps WITH garage vs WITHOUT.
    with_garage = [c for c in comps if (c.garage_spaces or 0) >= 1]
    without_garage = [c for c in comps if (c.garage_spaces or 0) == 0]

    if len(with_garage) >= 2 and len(without_garage) >= 2:
        med_with = median(c.adjusted_price for c in with_garage)
        med_without = median(c.adjusted_price for c in without_garage)
        delta = med_with - med_without
        # Normalize to per-space by dividing by median garage count.
        avg_spaces = median(c.garage_spaces for c in with_garage if c.garage_spaces)
        per_space = delta / max(avg_spaces, 1)
        adjustment = round(per_space * spaces, 2)
        # Sanity cap: garage shouldn't be more than 10% of base shell.
        if base_shell and abs(adjustment) > base_shell * 0.10:
            adjustment = round(base_shell * 0.10 * (1 if adjustment > 0 else -1), 2)
        return FeatureResult(
            present=True,
            adjustment=adjustment,
            confidence="moderate",
            method="feature_comparison",
            evidence=FeatureEvidence(
                with_feature_median=round(med_with, 2),
                without_feature_median=round(med_without, 2),
                sample_with=len(with_garage),
                sample_without=len(without_garage),
            ),
            notes=(
                f"{spaces}-car {'detached ' if pi.has_detached_garage else ''}garage. "
                f"Local comp median delta: ${delta:,.0f} for garage presence "
                f"({len(with_garage)} with vs {len(without_garage)} without). "
                f"Per-space value: ${per_space:,.0f}."
            ),
            overlap_check="No overlap with extra parking — garage and extra parking are evaluated separately.",
        )

    # Fallback: use conservative per-space value.
    adjustment = _FALLBACK_GARAGE_VALUE_PER_SPACE * spaces
    if base_shell and adjustment > base_shell * 0.08:
        adjustment = round(base_shell * 0.08, 2)
    return FeatureResult(
        present=True,
        adjustment=round(adjustment, 2),
        confidence="low",
        method="fallback_rule",
        evidence=FeatureEvidence(
            comparison_set_size=len(comps),
            note=f"Insufficient with/without garage split in comp set ({len(with_garage)} with, {len(without_garage)} without).",
        ),
        notes=(
            f"{spaces}-car {'detached ' if pi.has_detached_garage else ''}garage. "
            f"Fallback estimate at ${_FALLBACK_GARAGE_VALUE_PER_SPACE:,}/space. "
            f"Low confidence — insufficient paired comp evidence."
        ),
        overlap_check="No overlap with extra parking.",
    )


def _evaluate_basement(
    pi: PropertyInput,
    comps: list[AdjustedComparable],
    base_shell: float | None,
) -> FeatureResult:
    """Evaluate basement value."""
    if not pi.has_basement:
        return _not_present("basement", "No basement identified on subject property.")

    is_finished = bool(pi.basement_finished)
    # Comps don't have basement data, so paired-sale analysis is impossible.
    # Use fallback rules.

    if is_finished:
        # Estimate finished basement sqft as ~40% of above-grade sqft if not known.
        basement_sqft = int((pi.sqft or 1200) * 0.40)
        adjustment = _FALLBACK_BASEMENT_FINISHED_PER_SQFT * basement_sqft
        if base_shell and adjustment > base_shell * 0.12:
            adjustment = round(base_shell * 0.12, 2)
        return FeatureResult(
            present=True,
            adjustment=round(adjustment, 2),
            confidence="low",
            method="fallback_rule",
            evidence=FeatureEvidence(
                comparison_set_size=0,
                note="Comp data does not include basement fields. Cannot perform paired-sale analysis.",
            ),
            notes=(
                f"Finished basement (~{basement_sqft:,} sqft estimated). "
                f"Fallback estimate at ${_FALLBACK_BASEMENT_FINISHED_PER_SQFT}/sqft for finished below-grade space. "
                f"Low confidence — no local paired basement evidence available."
            ),
            overlap_check="Not counted as expansion potential since already finished.",
        )

    # Unfinished basement.
    return FeatureResult(
        present=True,
        adjustment=_FALLBACK_BASEMENT_UNFINISHED,
        confidence="low",
        method="fallback_rule",
        evidence=FeatureEvidence(
            comparison_set_size=0,
            note="Comp data does not include basement fields.",
        ),
        notes=(
            f"Unfinished basement. Fallback estimate of ${_FALLBACK_BASEMENT_UNFINISHED:,} "
            f"for storage/utility value. Low confidence — no local paired evidence."
        ),
        overlap_check="Unfinished basement may represent expansion potential (future build-out).",
    )


def _evaluate_pool(
    pi: PropertyInput,
    comps: list[AdjustedComparable],
    base_shell: float | None,
) -> FeatureResult:
    """Evaluate pool value."""
    if not pi.has_pool:
        return _not_present("pool", "No pool identified on subject property.")

    # No pool data in comps — can't do paired-sale analysis.
    # Use fallback. Assume inground unless listing suggests otherwise.
    adjustment = _FALLBACK_POOL_INGROUND
    if base_shell and adjustment > base_shell * 0.05:
        adjustment = round(base_shell * 0.05, 2)

    return FeatureResult(
        present=True,
        adjustment=adjustment,
        confidence="low",
        method="fallback_rule",
        evidence=FeatureEvidence(
            comparison_set_size=0,
            note="Comp data does not include pool fields. Cannot perform paired-sale analysis.",
        ),
        notes=(
            f"Pool present (assumed inground). "
            f"Fallback estimate of ${_FALLBACK_POOL_INGROUND:,}. "
            f"Pool value varies widely by market and condition. Low confidence."
        ),
        overlap_check=None,
    )


def _evaluate_lot_premium(
    pi: PropertyInput,
    comps: list[AdjustedComparable],
    base_shell: float | None,
    town_metrics: dict[str, Any] | None,
) -> FeatureResult:
    """Evaluate lot premium for excess lot size relative to local norm."""
    lot_acres = pi.lot_size
    if not lot_acres or lot_acres <= 0:
        return _not_present("lot_premium", "Lot size data not available.")

    lot_sqft = lot_acres * 43560

    # Determine town median lot.
    town_median_acres = _FALLBACK_TOWN_MEDIAN_LOT_ACRES
    if town_metrics and town_metrics.get("baseline_median_lot_size"):
        town_median_acres = float(town_metrics["baseline_median_lot_size"])

    # Also try to estimate from comps.
    comp_lots = [c.lot_size for c in comps if c.lot_size and c.lot_size > 0]
    if len(comp_lots) >= 3:
        comp_median_lot = median(comp_lots)
        town_median_acres = comp_median_lot  # prefer comp-derived

    town_median_sqft = town_median_acres * 43560
    excess_sqft = max(0, lot_sqft - town_median_sqft)

    if excess_sqft < 500:
        # Lot is at or below local median — no premium.
        return FeatureResult(
            present=False,
            adjustment=0,
            confidence="n/a",
            method="not_applicable",
            evidence=FeatureEvidence(
                subject_lot_sqft=round(lot_sqft, 0),
                town_median_lot_sqft=round(town_median_sqft, 0),
            ),
            notes=f"Lot ({lot_sqft:,.0f} sqft) is at or below local median ({town_median_sqft:,.0f} sqft). No lot premium.",
            overlap_check=None,
        )

    # Try feature comparison: comps with above-median lots vs below.
    above_median = [c for c in comps if c.lot_size and c.lot_size > town_median_acres * 1.2]
    below_median = [c for c in comps if c.lot_size and c.lot_size <= town_median_acres * 1.2]

    if len(above_median) >= 2 and len(below_median) >= 2:
        med_above = median(c.adjusted_price for c in above_median)
        med_below = median(c.adjusted_price for c in below_median)
        # Normalize to per-sqft excess.
        avg_excess_above = median((c.lot_size - town_median_acres) * 43560 for c in above_median if c.lot_size)
        if avg_excess_above > 0:
            implied_per_sqft = (med_above - med_below) / avg_excess_above
            implied_per_sqft = max(0, min(implied_per_sqft, 25))  # sanity cap
        else:
            implied_per_sqft = _FALLBACK_EXCESS_LAND_PER_SQFT
        adjustment = round(implied_per_sqft * excess_sqft, 2)
        if base_shell and adjustment > base_shell * 0.15:
            adjustment = round(base_shell * 0.15, 2)
        return FeatureResult(
            present=True,
            adjustment=adjustment,
            confidence="moderate",
            method="feature_comparison",
            evidence=FeatureEvidence(
                subject_lot_sqft=round(lot_sqft, 0),
                town_median_lot_sqft=round(town_median_sqft, 0),
                excess_sqft=round(excess_sqft, 0),
                local_land_value_per_sqft=round(implied_per_sqft, 2),
                raw_excess_value=round(implied_per_sqft * excess_sqft, 2),
                with_feature_median=round(med_above, 2),
                without_feature_median=round(med_below, 2),
                sample_with=len(above_median),
                sample_without=len(below_median),
            ),
            notes=(
                f"Lot is {lot_sqft:,.0f} sqft, {excess_sqft:,.0f} sqft above local median. "
                f"Excess land valued at ${implied_per_sqft:.2f}/sqft from comp comparison. "
                f"Premium: ${adjustment:,.0f}."
            ),
            overlap_check="Expansion potential scored separately — lot premium covers land value only.",
        )

    # Fallback: flat $/sqft for excess.
    adjustment = round(_FALLBACK_EXCESS_LAND_PER_SQFT * excess_sqft, 2)
    if base_shell and adjustment > base_shell * 0.12:
        adjustment = round(base_shell * 0.12, 2)
    return FeatureResult(
        present=True,
        adjustment=adjustment,
        confidence="low",
        method="fallback_rule",
        evidence=FeatureEvidence(
            subject_lot_sqft=round(lot_sqft, 0),
            town_median_lot_sqft=round(town_median_sqft, 0),
            excess_sqft=round(excess_sqft, 0),
            local_land_value_per_sqft=_FALLBACK_EXCESS_LAND_PER_SQFT,
            raw_excess_value=round(_FALLBACK_EXCESS_LAND_PER_SQFT * excess_sqft, 2),
        ),
        notes=(
            f"Lot is {lot_sqft:,.0f} sqft, {excess_sqft:,.0f} sqft above local median ({town_median_sqft:,.0f} sqft). "
            f"Excess land valued at fallback rate of ${_FALLBACK_EXCESS_LAND_PER_SQFT:.2f}/sqft. "
            f"Low confidence — insufficient comp lot variation for local evidence."
        ),
        overlap_check="Expansion potential scored separately — lot premium covers land value only.",
    )


def _evaluate_expansion(
    pi: PropertyInput,
    lot_result: FeatureResult,
) -> FeatureResult:
    """Evaluate expansion potential (buildable area, unused FAR)."""
    has_excess_lot = lot_result.present and lot_result.adjustment > 0
    has_unfinished_basement = pi.has_basement and not pi.basement_finished
    zone_flags = pi.zone_flags or {}
    has_zoning_data = bool(zone_flags)

    if not has_excess_lot and not has_unfinished_basement:
        return _not_present("expansion", "No expansion signals identified (lot at or below local norm, no unfinished basement).")

    # We don't have FAR or zoning data to quantify expansion in most cases.
    notes_parts: list[str] = []
    if has_excess_lot:
        notes_parts.append("excess lot suggests room for addition or ADU")
    if has_unfinished_basement:
        notes_parts.append("unfinished basement has build-out potential")

    if not has_zoning_data:
        return FeatureResult(
            present=True,
            adjustment=0,
            confidence="none",
            method="insufficient_data",
            evidence=FeatureEvidence(
                far_data_available=False,
                zoning_data_available=False,
            ),
            notes=(
                f"Expansion potential detected ({', '.join(notes_parts)}) but no FAR or zoning data "
                f"available to quantify. Not valued — would require site-specific feasibility analysis."
            ),
            overlap_check="Lot premium captured land value. Expansion potential not scored due to missing data.",
        )

    # If we have zoning data, we could potentially quantify, but for now flag only.
    return FeatureResult(
        present=True,
        adjustment=0,
        confidence="none",
        method="insufficient_data",
        evidence=FeatureEvidence(
            far_data_available=False,
            zoning_data_available=has_zoning_data,
        ),
        notes=(
            f"Expansion potential detected ({', '.join(notes_parts)}). "
            f"Zoning flags present but FAR data unavailable for quantification."
        ),
        overlap_check="Lot premium captured land value. Expansion valued separately when FAR data is available.",
    )


def _evaluate_extra_parking(
    pi: PropertyInput,
    garage_result: FeatureResult,
) -> FeatureResult:
    """Evaluate extra parking beyond garage."""
    parking = pi.parking_spaces or 0
    garage = pi.garage_spaces or 0

    # Extra parking = parking_spaces minus garage (already counted).
    extra = max(0, parking - garage)

    # Also count off-street driveway if present and no other parking.
    if extra == 0 and pi.driveway_off_street and parking == 0 and garage == 0:
        extra = 1  # count driveway as 1 extra space

    if extra <= 0:
        return _not_present("extra_parking", "No extra parking beyond garage identified.")

    adjustment = round(_FALLBACK_PARKING_PER_SPACE * extra, 2)
    return FeatureResult(
        present=True,
        adjustment=adjustment,
        confidence="low",
        method="fallback_rule",
        evidence=FeatureEvidence(
            note=f"{extra} extra parking space(s) beyond garage.",
        ),
        notes=(
            f"{extra} extra parking space(s) beyond garage. "
            f"Fallback estimate at ${_FALLBACK_PARKING_PER_SPACE:,}/space."
        ),
        overlap_check="Garage spaces counted separately. Only extra spaces beyond garage are valued here.",
    )


def _evaluate_legal_multi_unit(
    pi: PropertyInput,
    base_shell: float | None,
    adu_valued: bool,
) -> FeatureResult:
    """Evaluate legal multi-unit configuration premium."""
    prop_type = (pi.property_type or "").lower()
    is_multi = any(kw in prop_type for kw in ("duplex", "triplex", "fourplex", "multi_family", "multifamily", "two-family", "two family"))
    zone_multi = (pi.zone_flags or {}).get("multi_unit_allowed")

    if not is_multi and not zone_multi:
        return _not_present("legal_multi_unit", "Single-family zoning. No legal multi-unit configuration.")

    if adu_valued:
        # ADU income already captures the multi-unit value. Don't double-count.
        return FeatureResult(
            present=True,
            adjustment=0,
            confidence="n/a",
            method="deferred_to_hybrid",
            evidence=FeatureEvidence(
                note="ADU/multi-unit income already valued separately. No additional premium to avoid double-counting.",
            ),
            notes="Legal multi-unit configuration exists but income value already captured in ADU evaluation.",
            overlap_check="Deferred to ADU evaluation to avoid double-counting income value.",
        )

    # Legal multi-unit without income data — apply modest structural premium.
    if base_shell and base_shell > 0:
        adjustment = round(base_shell * _FALLBACK_LEGAL_MULTI_UNIT_PCT, 2)
    else:
        adjustment = 0
    return FeatureResult(
        present=True,
        adjustment=adjustment,
        confidence="low",
        method="fallback_rule",
        evidence=FeatureEvidence(
            note=f"Legal multi-unit zoning ({prop_type or 'multi-unit zone flag'}). No income data to value via income proxy.",
        ),
        notes=(
            f"Legal multi-unit configuration ({prop_type or 'zoned multi-unit'}). "
            f"No rental income data available. Fallback {_FALLBACK_LEGAL_MULTI_UNIT_PCT:.0%} structural premium applied."
        ),
        overlap_check="No ADU income valued. This captures the structural zoning premium only.",
    )


def _evaluate_special_utility(pi: PropertyInput) -> FeatureResult:
    """Evaluate special utility structures (workshop, barn, commercial overlay, etc.)."""
    # Currently no structured data for these — scan listing description.
    description = (pi.listing_description or "").lower()
    special_features: list[str] = []
    for keyword, label in [
        ("workshop", "workshop"),
        ("barn", "barn"),
        ("commercial", "commercial zoning overlay"),
        ("home office", "dedicated home office structure"),
        ("studio", "studio space"),
    ]:
        if keyword in description:
            special_features.append(label)

    if not special_features:
        return _not_present("special_utility", "No special utility structures identified.")

    return FeatureResult(
        present=True,
        adjustment=0,
        confidence="none",
        method="insufficient_data",
        evidence=FeatureEvidence(
            note=f"Listing mentions: {', '.join(special_features)}. No structured data to value.",
        ),
        notes=(
            f"Special utility detected from listing: {', '.join(special_features)}. "
            f"Cannot value without structured data on size, condition, and local demand."
        ),
        overlap_check=None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _not_present(feature_key: str, note: str) -> FeatureResult:
    """Standard result for a feature not present on the property."""
    return FeatureResult(
        present=False,
        adjustment=0,
        confidence="n/a",
        method="not_applicable",
        evidence=FeatureEvidence(),
        notes=note,
        overlap_check=None,
    )


def _confidence_breakdown(features: dict[str, FeatureResult]) -> ConfidenceBreakdown:
    high = 0.0
    moderate = 0.0
    low = 0.0
    unvalued: list[str] = []
    for key, f in features.items():
        if not f.present:
            continue
        if f.confidence == "high":
            high += f.adjustment
        elif f.confidence == "moderate":
            moderate += f.adjustment
        elif f.confidence == "low":
            low += f.adjustment
        elif f.confidence in ("none", "n/a") and f.method not in ("not_applicable", "deferred_to_hybrid"):
            unvalued.append(key)
    return ConfidenceBreakdown(
        high_confidence_portion=round(high, 2),
        moderate_confidence_portion=round(moderate, 2),
        low_confidence_portion=round(low, 2),
        unvalued_features=unvalued,
    )


def _weighted_confidence(features: dict[str, FeatureResult], total: float) -> str:
    """Determine overall confidence based on where the adjustment mass sits."""
    if total <= 0:
        return "n/a"
    breakdown = _confidence_breakdown(features)
    high_pct = breakdown.high_confidence_portion / total if total else 0
    moderate_pct = breakdown.moderate_confidence_portion / total if total else 0
    if high_pct >= 0.60:
        return "high"
    if (high_pct + moderate_pct) >= 0.60:
        return "moderate"
    return "low"

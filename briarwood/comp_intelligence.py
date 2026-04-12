"""Comp Analysis Integrator.

Single orchestrator that calls each sub-engine in order, resolves
overlaps, composes the final adjusted value as a deterministic
layer-by-layer calculation, and produces one unified output.

Execution order:
  1. Base Comp Selector result (already available on comp_output)
  2. Feature Adjustment Engine
  3. Micro-Location Engine
  4. Town Transfer Engine
  5. Comp Confidence Engine
  6. Value composition (base_shell + features + location + transfer)
  7. Overlap resolution
  8. Output assembly
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from briarwood.agents.comparable_sales.schemas import (
    ComparableSalesOutput,
    ComparableValueRange,
    FeatureAdjustment,
    LocationAdjustment,
    SupportSummary,
    TownTransferAdjustment,
)
from briarwood.comp_confidence_engine import evaluate_comp_confidence
from briarwood.feature_adjustment_engine import (
    FeatureAdjustmentResult,
    evaluate_feature_adjustments,
)
from briarwood.micro_location_engine import (
    MicroLocationResult,
    evaluate_micro_location,
)
from briarwood.schemas import PropertyInput
from briarwood.town_transfer_engine import TransferResult, evaluate_town_transfer


def run_comp_analysis(
    *,
    output: ComparableSalesOutput,
    property_input: PropertyInput,
) -> dict[str, object]:
    """Orchestrate the full comp analysis stack and return a unified result.

    Replaces the former ``build_comp_analysis()`` which ran two parallel
    computation paths (legacy Pydantic adjustments AND engine dataclass
    calls).  This function calls each engine exactly once, composes the
    final adjusted value deterministically, and uses the Comp Confidence
    Engine's composite score as the authoritative confidence.

    Returns a dict matching the ``ComparableCompAnalysis`` schema.
    """

    base_comp_selection = output.base_comp_selection

    # ------------------------------------------------------------------
    # 1. Anchor: base shell value
    # ------------------------------------------------------------------
    base_shell_value = (
        (base_comp_selection.base_shell_value if base_comp_selection is not None else None)
        or _range_midpoint(output.direct_value_range)
        or output.comparable_value
    )

    # ------------------------------------------------------------------
    # 2. Feature Adjustment Engine (independent of location)
    # ------------------------------------------------------------------
    feature_result = evaluate_feature_adjustments(
        property_input=property_input,
        comp_output=output,
        base_comp_selection=base_comp_selection,
    )

    # ------------------------------------------------------------------
    # 3. Micro-Location Engine (independent of features)
    # ------------------------------------------------------------------
    location_result = evaluate_micro_location(
        property_input=property_input,
        comp_output=output,
        base_comp_selection=base_comp_selection,
    )

    # ------------------------------------------------------------------
    # 4. Town Transfer Engine (gates on support_quality)
    # ------------------------------------------------------------------
    transfer_result = evaluate_town_transfer(
        property_input=property_input,
        comp_output=output,
        base_comp_selection=base_comp_selection,
    )

    # ------------------------------------------------------------------
    # 5. Comp Confidence Engine (reads all 4 layers)
    # ------------------------------------------------------------------
    confidence_result = evaluate_comp_confidence(
        comp_output=output,
        base_comp_selection=base_comp_selection,
        feature_result=feature_result,
        location_result=location_result,
        transfer_result=transfer_result,
    )

    # ------------------------------------------------------------------
    # 6. Deterministic value composition
    # ------------------------------------------------------------------
    adjusted_value = _compose_value(
        base_shell_value=base_shell_value,
        feature_result=feature_result,
        location_result=location_result,
        transfer_result=transfer_result,
    )

    # ------------------------------------------------------------------
    # 7. Overlap resolution
    # ------------------------------------------------------------------
    overlap_notes = _resolve_overlaps(feature_result, location_result)

    # ------------------------------------------------------------------
    # 8. Output assembly — single source of truth
    # ------------------------------------------------------------------
    feature_adjustments = _feature_adjustments_from_engine(feature_result)
    location_adjustments = _location_adjustments_from_engine(location_result)
    town_transfer_adjustments = _town_transfer_from_engine(
        transfer_result, property_input.town,
    )
    support_summary = _build_support_summary(output, feature_result, location_result)

    confidence = round(confidence_result.composite_score, 2)

    return {
        "base_shell_value": _round_money(base_shell_value),
        "feature_adjustments": {item.key: item.model_dump() for item in feature_adjustments},
        "location_adjustments": {item.key: item.model_dump() for item in location_adjustments},
        "town_transfer_adjustments": {item.key: item.model_dump() for item in town_transfer_adjustments},
        "adjusted_value": _round_money(adjusted_value),
        "support_summary": support_summary.model_dump(),
        "confidence": confidence,
        "feature_engine": asdict(feature_result),
        "location_engine": asdict(location_result),
        "town_transfer_engine": asdict(transfer_result),
        "confidence_engine": asdict(confidence_result),
    }


# Keep the old name as an alias so existing callers don't break.
build_comp_analysis = run_comp_analysis


# ---------------------------------------------------------------------------
# Value composition
# ---------------------------------------------------------------------------

def _compose_value(
    *,
    base_shell_value: float | None,
    feature_result: FeatureAdjustmentResult,
    location_result: MicroLocationResult,
    transfer_result: TransferResult,
) -> float | None:
    """Deterministic: base_shell + features + location + transfer delta."""
    if base_shell_value is None:
        return None

    value = base_shell_value
    value += feature_result.total_feature_adjustment
    value += location_result.total_location_adjustment

    if transfer_result.used and transfer_result.blended_value is not None:
        # Town transfer replaces the base shell with a blended value.
        # The delta is the difference between the blended and the original
        # base shell (before feature/location adjustments were applied).
        transfer_delta = transfer_result.blended_value - (transfer_result.local_base_value or base_shell_value)
        value += transfer_delta

    return value


# ---------------------------------------------------------------------------
# Overlap resolution
# ---------------------------------------------------------------------------

def _resolve_overlaps(
    feature_result: FeatureAdjustmentResult,
    location_result: MicroLocationResult,
) -> list[str]:
    """Collect overlap warnings from engines and return consolidated notes."""
    warnings: list[str] = []
    warnings.extend(feature_result.overlap_warnings)
    warnings.extend(location_result.overlap_warnings)
    return warnings


# ---------------------------------------------------------------------------
# Schema object builders — one source per adjustment
# ---------------------------------------------------------------------------

def _feature_adjustments_from_engine(result: FeatureAdjustmentResult) -> list[FeatureAdjustment]:
    """Convert engine FeatureResult entries into schema FeatureAdjustment objects."""
    items: list[FeatureAdjustment] = []
    for key, fr in result.features.items():
        items.append(
            FeatureAdjustment(
                key=key,
                amount=_round_money(fr.adjustment) if fr.present and fr.adjustment != 0 else None,
                method=fr.method,
                support_type=_support_type_from_confidence(fr.confidence),
                note=fr.notes,
            )
        )
    return items


def _location_adjustments_from_engine(result: MicroLocationResult) -> list[LocationAdjustment]:
    """Convert engine LocationResult entries into schema LocationAdjustment objects."""
    items: list[LocationAdjustment] = []
    for key, lr in result.factors.items():
        items.append(
            LocationAdjustment(
                key=key,
                amount=_round_money(lr.adjustment) if lr.applicable and lr.adjustment != 0 else None,
                method=lr.method,
                support_type=_support_type_from_confidence(lr.confidence),
                note=lr.notes,
            )
        )
    return items


def _town_transfer_from_engine(
    result: TransferResult,
    subject_town: str,
) -> list[TownTransferAdjustment]:
    """Convert engine TransferResult into schema TownTransferAdjustment."""
    if result.used:
        return [
            TownTransferAdjustment(
                key="cross_town_shell_transfer",
                amount=_round_money(
                    result.blended_value - result.local_base_value
                    if result.blended_value is not None and result.local_base_value is not None
                    else None
                ),
                from_town=result.donor_town,
                to_town=subject_town,
                method=result.method,
                support_type="translated",
                note=result.reason,
            )
        ]
    return [
        TownTransferAdjustment(
            key="cross_town_shell_transfer",
            amount=None,
            from_town=None,
            to_town=subject_town,
            method="not_activated",
            support_type="direct" if True else "translated",
            note=result.reason,
        )
    ]


def _build_support_summary(
    output: ComparableSalesOutput,
    feature_result: FeatureAdjustmentResult,
    location_result: MicroLocationResult,
) -> SupportSummary:
    """Build support summary from base comp selection and engine results."""
    if output.base_comp_selection is not None:
        summary = output.base_comp_selection.support_summary
        base_notes = list(summary.notes)[:2]
    else:
        summary = None
        base_notes = []

    direct_support_count = summary.comp_count if summary else len(output.comps_used)
    same_town_count = summary.same_town_count if summary else len(output.comps_used)
    income_support_count = len([
        comp for comp in output.comps_used
        if getattr(comp, "segmentation_bucket", None) == "income_comps"
    ])
    location_support_count = len([
        comp for comp in output.comps_used
        if getattr(comp, "location_tags", None)
    ])

    # Enrich notes with engine-level observations
    notes = list(base_notes)
    if feature_result.weighted_confidence in ("low", "none"):
        notes.append(f"Feature adjustments have {feature_result.weighted_confidence} confidence — mostly fallback rules.")
    if location_result.weighted_confidence in ("low", "none"):
        notes.append(f"Location adjustments have {location_result.weighted_confidence} confidence — limited spatial evidence.")

    return SupportSummary(
        direct_support_count=direct_support_count,
        translated_support_count=0,
        same_town_count=same_town_count,
        income_support_count=income_support_count,
        location_support_count=location_support_count,
        primary_mode="direct_same_town" if same_town_count > 0 else "translated_cross_town",
        notes=notes[:4],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _support_type_from_confidence(confidence_label: str) -> str:
    """Map engine confidence labels to schema support_type values."""
    return {
        "high": "direct",
        "moderate": "direct",
        "low": "observed",
        "none": "pending",
        "n/a": "pending",
    }.get(confidence_label, "pending")


def _range_midpoint(value_range: ComparableValueRange | None) -> float | None:
    if value_range is None:
        return None
    return value_range.midpoint


def _round_money(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)

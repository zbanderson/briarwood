"""Comp Confidence Engine.

Sits on top of the entire valuation stack — Base Comp Selector, Feature
Adjustment Engine, Micro-Location Engine, Town Transfer Engine — and
answers: "How much should the user trust this valuation, and why?"

Each valuation layer is scored independently (0-1), then combined into a
composite score. No single strong layer can mask a weak one — the
composite is capped relative to the weakest material layer.

Layers evaluated:
  1. Base Shell Support — comp count, tier distribution, similarity, agreement
  2. Feature Adjustments — evidence hierarchy quality, unvalued features
  3. Location Adjustments — evidence hierarchy quality, data availability
  4. Town Transfer — whether borrowed evidence was needed and how reliable it is
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median, stdev

from briarwood.agents.comparable_sales.schemas import (
    BaseCompSelection,
    ComparableSalesOutput,
)
from briarwood.feature_adjustment_engine import FeatureAdjustmentResult
from briarwood.micro_location_engine import MicroLocationResult
from briarwood.town_transfer_engine import TransferResult


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum weight for the base shell layer in the composite.
_BASE_SHELL_MIN_WEIGHT = 0.45

# Layers contributing >= this fraction of total valuation are "material"
# and subject to the weakest-layer floor.
_MATERIALITY_THRESHOLD = 0.10

# Composite can't exceed this multiple of the weakest material layer score.
_WEAKEST_LAYER_CAP = 2.0

# Score assigned to inactive layers (not applicable = neutral, not penalized).
_INACTIVE_SCORE = 0.80

# Map confidence labels to numeric scores.
_LABEL_SCORES: dict[str, float] = {
    "high": 0.90,
    "moderate": 0.65,
    "low": 0.35,
    "none": 0.15,
    "n/a": _INACTIVE_SCORE,
}


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ConfidenceComponent:
    """One factor contributing to a layer's confidence."""
    key: str
    value: float
    contribution: str  # "positive", "neutral", "negative"
    note: str


@dataclass(slots=True)
class LayerConfidence:
    """Confidence assessment for one valuation layer."""
    layer: str  # "base_shell", "features", "location", "town_transfer"
    score: float  # 0-1
    label: str  # "strong", "adequate", "weak", "unsupported"
    active: bool
    dollar_contribution: float
    weight_in_composite: float
    components: list[ConfidenceComponent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConfidenceGap:
    """An actionable gap that would improve confidence."""
    layer: str
    gap: str
    impact: str  # "high", "moderate", "low"
    action: str


@dataclass(slots=True)
class SalesHistoryEvidence:
    """Structured sales-history quality signal for subject or comp history."""

    event_count: int = 0
    complete_event_count: int = 0
    repeat_sale_pairs: int = 0
    history_span_years: float | None = None
    most_recent_hold_years: float | None = None
    history_confidence: float | None = None
    history_confidence_label: str | None = None
    history_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HistoryConfidenceAssessment:
    """Explicit history-confidence result kept separate from value math."""

    score: float
    label: str
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompConfidenceResult:
    """Complete output of the Comp Confidence Engine."""
    composite_score: float
    composite_label: str  # "High", "Medium", "Low"
    layers: dict[str, LayerConfidence]
    weakest_layer: str
    actionable_gaps: list[ConfidenceGap]
    narrative: str
    history_confidence: HistoryConfidenceAssessment | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_comp_confidence(
    *,
    comp_output: ComparableSalesOutput,
    base_comp_selection: BaseCompSelection | None = None,
    feature_result: FeatureAdjustmentResult | None = None,
    location_result: MicroLocationResult | None = None,
    transfer_result: TransferResult | None = None,
    sales_history_evidence: SalesHistoryEvidence | None = None,
) -> CompConfidenceResult:
    """Evaluate confidence across the entire comp valuation stack.

    Args:
        comp_output: Full comparable sales output.
        base_comp_selection: The base comp selection result.
        feature_result: Output from the Feature Adjustment Engine.
        location_result: Output from the Micro-Location Engine.
        transfer_result: Output from the Town Transfer Engine.

    Returns:
        CompConfidenceResult with per-layer scores and composite.
    """
    selection = base_comp_selection or comp_output.base_comp_selection
    base_shell_value = (
        (selection.base_shell_value if selection else None)
        or comp_output.comparable_value
    )

    base_layer = _score_base_shell(comp_output, selection, base_shell_value)
    feature_layer = _score_features(feature_result, base_shell_value)
    location_layer = _score_location(location_result, base_shell_value)
    transfer_layer = _score_town_transfer(transfer_result)

    layers = {
        "base_shell": base_layer,
        "features": feature_layer,
        "location": location_layer,
        "town_transfer": transfer_layer,
    }

    composite, weakest = _compute_composite(layers, base_shell_value)
    label = _composite_label(composite)
    history_confidence = _score_sales_history(sales_history_evidence)
    gaps = _find_gaps(
        layers,
        feature_result,
        location_result,
        transfer_result,
        history_confidence,
    )
    narrative = _build_narrative(layers, composite, label, weakest, history_confidence)
    notes = list(history_confidence.notes) if history_confidence is not None else []

    return CompConfidenceResult(
        composite_score=composite,
        composite_label=label,
        layers=layers,
        weakest_layer=weakest,
        actionable_gaps=gaps[:5],
        narrative=narrative,
        history_confidence=history_confidence,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Layer 1: Base Shell Support
# ---------------------------------------------------------------------------

def _score_base_shell(
    comp_output: ComparableSalesOutput,
    selection: BaseCompSelection | None,
    base_shell_value: float | None,
) -> LayerConfidence:
    components: list[ConfidenceComponent] = []

    # 1. Comp count
    comp_count = selection.support_summary.comp_count if selection else comp_output.comp_count
    count_score = _comp_count_score(comp_count)
    components.append(ConfidenceComponent(
        key="comp_count",
        value=count_score,
        contribution=_contribution(count_score),
        note=f"{comp_count} comps selected",
    ))

    # 2. Support quality
    quality = selection.support_summary.support_quality if selection else "thin"
    quality_score = {"strong": 1.0, "moderate": 0.65, "thin": 0.30}.get(quality, 0.30)
    components.append(ConfidenceComponent(
        key="support_quality",
        value=quality_score,
        contribution=_contribution(quality_score),
        note=f"Support quality: {quality}",
    ))

    # 3. Tier distribution
    tier_score = _tier_distribution_score(selection)
    components.append(ConfidenceComponent(
        key="tier_distribution",
        value=tier_score,
        contribution=_contribution(tier_score),
        note=_tier_distribution_note(selection),
    ))

    # 4. Median similarity
    sim_score = _median_similarity_score(selection)
    components.append(ConfidenceComponent(
        key="median_similarity",
        value=sim_score,
        contribution=_contribution(sim_score),
        note=f"Median comp similarity: {sim_score:.2f}",
    ))

    # 5. Price agreement (inverse CV)
    agreement = _price_agreement_score(comp_output.comps_used)
    components.append(ConfidenceComponent(
        key="price_agreement",
        value=agreement,
        contribution=_contribution(agreement),
        note=f"Comp price agreement: {agreement:.2f}",
    ))

    score = round(max(0.0, min(
        count_score * 0.25
        + quality_score * 0.25
        + tier_score * 0.20
        + sim_score * 0.15
        + agreement * 0.15,
        1.0,
    )), 3)

    return LayerConfidence(
        layer="base_shell",
        score=score,
        label=_score_label(score),
        active=True,
        dollar_contribution=base_shell_value or 0.0,
        weight_in_composite=0.0,
        components=components,
    )


# ---------------------------------------------------------------------------
# Layer 2: Feature Adjustments
# ---------------------------------------------------------------------------

def _score_features(
    result: FeatureAdjustmentResult | None,
    base_shell_value: float | None,
) -> LayerConfidence:
    if result is None:
        return _inactive_layer("features", "Feature engine not evaluated.")

    has_present = any(f.present for f in result.features.values())
    if not has_present:
        return _inactive_layer("features", "No features applicable to this property.")

    total = result.total_feature_adjustment
    components: list[ConfidenceComponent] = []

    # 1. Weighted confidence from the engine
    conf_score = _LABEL_SCORES.get(result.weighted_confidence, 0.50)
    components.append(ConfidenceComponent(
        key="weighted_confidence",
        value=conf_score,
        contribution=_contribution(conf_score),
        note=f"Feature engine weighted confidence: {result.weighted_confidence}",
    ))

    # 2. Evidence tier distribution
    breakdown = result.confidence_breakdown
    abs_total = abs(total) if total != 0 else 1.0
    high_pct = abs(breakdown.high_confidence_portion) / abs_total
    moderate_pct = abs(breakdown.moderate_confidence_portion) / abs_total
    low_pct = abs(breakdown.low_confidence_portion) / abs_total
    tier_score = round(high_pct * 1.0 + moderate_pct * 0.65 + low_pct * 0.30, 3)
    components.append(ConfidenceComponent(
        key="evidence_distribution",
        value=tier_score,
        contribution=_contribution(tier_score),
        note=(
            f"High: {high_pct:.0%}, Moderate: {moderate_pct:.0%}, "
            f"Low: {low_pct:.0%} of feature adjustment dollars"
        ),
    ))

    # 3. Unvalued features
    unvalued_count = len(breakdown.unvalued_features)
    unvalued_penalty = min(unvalued_count * 0.08, 0.25)
    unvalued_score = round(1.0 - unvalued_penalty, 3)
    components.append(ConfidenceComponent(
        key="unvalued_features",
        value=unvalued_score,
        contribution="negative" if unvalued_count > 0 else "neutral",
        note=(
            f"{unvalued_count} feature(s) detected but not valued: "
            f"{', '.join(breakdown.unvalued_features)}"
        ) if unvalued_count else "All detected features valued",
    ))

    # Overlap warning penalty
    overlap_penalty = min(len(result.overlap_warnings) * 0.05, 0.15)

    score = round(max(0.0, min(
        conf_score * 0.40 + tier_score * 0.35 + unvalued_score * 0.25 - overlap_penalty,
        1.0,
    )), 3)

    notes: list[str] = []
    if breakdown.unvalued_features:
        notes.append(f"Unvalued features: {', '.join(breakdown.unvalued_features)}")
    if result.overlap_warnings:
        notes.append(f"{len(result.overlap_warnings)} overlap warning(s)")

    return LayerConfidence(
        layer="features",
        score=score,
        label=_score_label(score),
        active=True,
        dollar_contribution=total,
        weight_in_composite=0.0,
        components=components,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Layer 3: Location Adjustments
# ---------------------------------------------------------------------------

def _score_location(
    result: MicroLocationResult | None,
    base_shell_value: float | None,
) -> LayerConfidence:
    if result is None:
        return _inactive_layer("location", "Location engine not evaluated.")

    has_applicable = any(f.applicable for f in result.factors.values())
    if not has_applicable:
        return _inactive_layer("location", "No location factors applicable.")

    total = result.total_location_adjustment
    components: list[ConfidenceComponent] = []

    # 1. Weighted confidence
    conf_score = _LABEL_SCORES.get(result.weighted_confidence, 0.50)
    components.append(ConfidenceComponent(
        key="weighted_confidence",
        value=conf_score,
        contribution=_contribution(conf_score),
        note=f"Location engine weighted confidence: {result.weighted_confidence}",
    ))

    # 2. Evidence tier distribution
    breakdown = result.confidence_breakdown
    abs_total = abs(total) if total != 0 else 1.0
    high_pct = abs(breakdown.high_confidence_portion) / abs_total
    moderate_pct = abs(breakdown.moderate_confidence_portion) / abs_total
    low_pct = abs(breakdown.low_confidence_portion) / abs_total
    tier_score = round(high_pct * 1.0 + moderate_pct * 0.65 + low_pct * 0.30, 3)
    components.append(ConfidenceComponent(
        key="evidence_distribution",
        value=tier_score,
        contribution=_contribution(tier_score),
        note=(
            f"High: {high_pct:.0%}, Moderate: {moderate_pct:.0%}, "
            f"Low: {low_pct:.0%} of location adjustment dollars"
        ),
    ))

    # 3. Unvalued factors
    unvalued_count = len(breakdown.unvalued_factors)
    unvalued_penalty = min(unvalued_count * 0.08, 0.25)
    unvalued_score = round(1.0 - unvalued_penalty, 3)
    components.append(ConfidenceComponent(
        key="unvalued_factors",
        value=unvalued_score,
        contribution="negative" if unvalued_count > 0 else "neutral",
        note=(
            f"{unvalued_count} location factor(s) detected but not valued: "
            f"{', '.join(breakdown.unvalued_factors)}"
        ) if unvalued_count else "All applicable location factors valued",
    ))

    # Overlap warning penalty
    overlap_penalty = min(len(result.overlap_warnings) * 0.05, 0.15)

    score = round(max(0.0, min(
        conf_score * 0.40 + tier_score * 0.35 + unvalued_score * 0.25 - overlap_penalty,
        1.0,
    )), 3)

    notes: list[str] = []
    if breakdown.unvalued_factors:
        notes.append(f"Unvalued factors: {', '.join(breakdown.unvalued_factors)}")
    if result.overlap_warnings:
        notes.append(f"{len(result.overlap_warnings)} overlap warning(s)")

    return LayerConfidence(
        layer="location",
        score=score,
        label=_score_label(score),
        active=True,
        dollar_contribution=total,
        weight_in_composite=0.0,
        components=components,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Layer 4: Town Transfer
# ---------------------------------------------------------------------------

def _score_town_transfer(
    result: TransferResult | None,
) -> LayerConfidence:
    if result is None or not result.used:
        reason = result.reason if result else "Transfer engine not evaluated."
        return _inactive_layer("town_transfer", reason)

    components: list[ConfidenceComponent] = []

    # 1. Town similarity
    sim = result.similarity_score or 0.0
    components.append(ConfidenceComponent(
        key="town_similarity",
        value=sim,
        contribution=_contribution(sim),
        note=f"Donor town '{result.donor_town}' similarity: {sim:.2f}",
    ))

    # 2. Transferred confidence (already penalized by engine)
    conf = result.transferred_confidence or 0.0
    components.append(ConfidenceComponent(
        key="transferred_confidence",
        value=conf,
        contribution=_contribution(conf),
        note=f"Transferred confidence after penalty: {conf:.2f}",
    ))

    # 3. Warning count
    warning_penalty = min(len(result.warnings) * 0.05, 0.15)
    warning_score = round(1.0 - warning_penalty, 3)
    components.append(ConfidenceComponent(
        key="warnings",
        value=warning_score,
        contribution="negative" if result.warnings else "neutral",
        note=f"{len(result.warnings)} transfer warning(s)" if result.warnings else "No transfer warnings",
    ))

    # Dollar contribution = delta from blending
    dollar_delta = 0.0
    if result.blended_value is not None and result.local_base_value is not None:
        dollar_delta = result.blended_value - result.local_base_value
    elif result.translated_shell_value is not None:
        dollar_delta = result.translated_shell_value - (result.local_base_value or 0.0)

    score = round(max(0.0, min(
        sim * 0.35 + conf * 0.45 + warning_score * 0.20,
        1.0,
    )), 3)

    return LayerConfidence(
        layer="town_transfer",
        score=score,
        label=_score_label(score),
        active=True,
        dollar_contribution=dollar_delta,
        weight_in_composite=0.0,
        components=components,
        notes=list(result.warnings[:3]),
    )


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def _compute_composite(
    layers: dict[str, LayerConfidence],
    base_shell_value: float | None,
) -> tuple[float, str]:
    """Compute dollar-weighted composite with weakest-material-layer floor."""
    active = {k: v for k, v in layers.items() if v.active}
    if not active:
        return 0.0, "base_shell"

    # Assign weights: base shell gets at least _BASE_SHELL_MIN_WEIGHT,
    # adjustment layers share the remainder proportional to |dollar_contribution|.
    base = active.get("base_shell")
    adjustment_layers = {k: v for k, v in active.items() if k != "base_shell"}
    total_adj_dollars = sum(abs(v.dollar_contribution) for v in adjustment_layers.values())

    if base is not None:
        base_val = abs(base_shell_value or 0.0)
        total_val = base_val + total_adj_dollars
        base.weight_in_composite = max(
            _BASE_SHELL_MIN_WEIGHT,
            base_val / total_val if total_val > 0 else 1.0,
        )
        remaining = 1.0 - base.weight_in_composite
    else:
        remaining = 1.0

    if adjustment_layers:
        if total_adj_dollars > 0:
            for layer in adjustment_layers.values():
                layer.weight_in_composite = round(
                    remaining * abs(layer.dollar_contribution) / total_adj_dollars,
                    4,
                )
        else:
            equal_share = remaining / len(adjustment_layers)
            for layer in adjustment_layers.values():
                layer.weight_in_composite = round(equal_share, 4)

    # Weighted average
    total_weight = sum(v.weight_in_composite for v in active.values())
    if total_weight <= 0:
        return 0.0, "base_shell"

    weighted = sum(v.score * v.weight_in_composite for v in active.values()) / total_weight

    # Weakest material layer floor — only layers contributing >= 10%
    # of total valuation (or base_shell, always material).
    total_val = abs(base_shell_value or 0.0) + total_adj_dollars
    material = [
        v for v in active.values()
        if v.layer == "base_shell"
        or (total_val > 0 and abs(v.dollar_contribution) / total_val >= _MATERIALITY_THRESHOLD)
    ]

    weakest_key = "base_shell"
    if material:
        weakest = min(material, key=lambda v: v.score)
        weakest_key = weakest.layer
        cap = weakest.score * _WEAKEST_LAYER_CAP
        weighted = min(weighted, cap)

    return round(max(0.0, min(weighted, 1.0)), 3), weakest_key


# ---------------------------------------------------------------------------
# Actionable gaps
# ---------------------------------------------------------------------------

def _find_gaps(
    layers: dict[str, LayerConfidence],
    feature_result: FeatureAdjustmentResult | None,
    location_result: MicroLocationResult | None,
    transfer_result: TransferResult | None,
    history_confidence: HistoryConfidenceAssessment | None,
) -> list[ConfidenceGap]:
    gaps: list[ConfidenceGap] = []

    # Base shell gaps
    base = layers["base_shell"]
    if base.score < 0.65:
        gaps.append(ConfidenceGap(
            layer="base_shell",
            gap="Thin comp support",
            impact="high",
            action="Add more comparable sales data, especially recent local sales within 0.5mi.",
        ))

    # Feature gaps
    if feature_result is not None:
        for key in feature_result.confidence_breakdown.unvalued_features:
            gaps.append(ConfidenceGap(
                layer="features",
                gap=f"Unvalued feature: {key}",
                impact="moderate",
                action=f"Provide evidence for {key} (paired sale data, local rent data, or zoning/FAR data).",
            ))
        for key, f in feature_result.features.items():
            if f.confidence == "low" and abs(f.adjustment) > 0:
                gaps.append(ConfidenceGap(
                    layer="features",
                    gap=f"{key} adjustment uses fallback rule",
                    impact="moderate" if abs(f.adjustment) > 10_000 else "low",
                    action=f"Add comp evidence for {key} (comps with/without) to upgrade from fallback to feature-comparison.",
                ))

    # Location gaps
    if location_result is not None:
        for key, f in location_result.factors.items():
            if f.confidence == "low" and abs(f.adjustment) > 0:
                gaps.append(ConfidenceGap(
                    layer="location",
                    gap=f"{key} location adjustment uses fallback rule",
                    impact="moderate" if abs(f.adjustment) > 10_000 else "low",
                    action=f"Add comps with location_tags for {key} to enable feature-comparison method.",
                ))

    # Town transfer gaps
    if transfer_result is not None and transfer_result.used:
        gaps.append(ConfidenceGap(
            layer="town_transfer",
            gap="Valuation relies on town-transferred evidence",
            impact="high",
            action="Add direct same-town comparable sales to eliminate need for cross-town transfer.",
        ))

    if history_confidence is not None and history_confidence.score < 0.6:
        gaps.append(ConfidenceGap(
            layer="sales_history",
            gap="Sales history evidence is thin or incomplete",
            impact="moderate",
            action=(
                "Use ATTOM sales-history detail/snapshot to verify repeat-sale chains, "
                "recency ordering, disclosure gaps, and price-per-sqft history for subject and key comps."
            ),
        ))

    impact_order = {"high": 0, "moderate": 1, "low": 2}
    gaps.sort(key=lambda g: impact_order.get(g.impact, 3))
    return gaps


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------

def _build_narrative(
    layers: dict[str, LayerConfidence],
    composite: float,
    label: str,
    weakest: str,
    history_confidence: HistoryConfidenceAssessment | None,
) -> str:
    parts: list[str] = []
    base = layers["base_shell"]
    parts.append(f"base shell support is {base.label}")

    if layers["features"].active:
        parts.append(f"feature adjustments are {layers['features'].label} confidence")
    if layers["location"].active:
        parts.append(f"location adjustments are {layers['location'].label} confidence")
    if layers["town_transfer"].active:
        parts.append(f"town-transferred evidence is {layers['town_transfer'].label}")
    if history_confidence is not None:
        parts.append(f"sales history evidence is {history_confidence.label}")

    detail = ", ".join(parts)

    if label == "High":
        return f"Valuation is well-supported: {detail}."
    if label == "Medium":
        weakest_label = layers[weakest].label
        return f"Valuation has adequate support with some gaps: {detail}. Weakest layer: {weakest} ({weakest_label})."
    return f"Valuation evidence is thin: {detail}. Weakest layer: {weakest} ({layers[weakest].label})."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inactive_layer(layer: str, note: str) -> LayerConfidence:
    return LayerConfidence(
        layer=layer,
        score=_INACTIVE_SCORE,
        label="adequate",
        active=False,
        dollar_contribution=0.0,
        weight_in_composite=0.0,
        notes=[note],
    )


def _comp_count_score(count: int) -> float:
    if count >= 5:
        return 0.95
    if count >= 4:
        return 0.82
    if count >= 3:
        return 0.65
    if count >= 2:
        return 0.40
    if count >= 1:
        return 0.25
    return 0.05


def _tier_distribution_score(selection: BaseCompSelection | None) -> float:
    if selection is None or not selection.selected_comps:
        return 0.30
    tiers = [c.selection_tier for c in selection.selected_comps]
    total = len(tiers)
    tier_weights = {
        "tight_local": 1.0,
        "loose_local": 0.75,
        "broad_local": 0.45,
        "extended_support": 0.20,
    }
    weighted = sum(tier_weights.get(t, 0.20) for t in tiers) / total
    return round(weighted, 3)


def _tier_distribution_note(selection: BaseCompSelection | None) -> str:
    if selection is None or not selection.selected_comps:
        return "No base comp selection available"
    tier_counts: dict[str, int] = {}
    for c in selection.selected_comps:
        tier_counts[c.selection_tier] = tier_counts.get(c.selection_tier, 0) + 1
    parts = [f"{count} {tier}" for tier, count in tier_counts.items()]
    return "Tier mix: " + ", ".join(parts)


def _median_similarity_score(selection: BaseCompSelection | None) -> float:
    if selection is None or not selection.selected_comps:
        return 0.50
    scores = [c.similarity_score for c in selection.selected_comps]
    return round(median(scores), 3)


def _price_agreement_score(comps: list) -> float:
    if len(comps) < 2:
        return 0.50
    prices = [float(c.adjusted_price) for c in comps]
    med = median(prices)
    if med <= 0:
        return 0.50
    try:
        cv = stdev(prices) / med
    except (ValueError, ZeroDivisionError):
        return 0.50
    if cv <= 0.08:
        return 0.95
    if cv <= 0.15:
        return 0.80
    if cv <= 0.25:
        return 0.60
    if cv <= 0.35:
        return 0.40
    return 0.20


def _score_label(score: float) -> str:
    if score >= 0.75:
        return "strong"
    if score >= 0.55:
        return "adequate"
    if score >= 0.30:
        return "weak"
    return "unsupported"


def _composite_label(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.55:
        return "Medium"
    return "Low"


def _contribution(score: float) -> str:
    if score >= 0.70:
        return "positive"
    if score >= 0.45:
        return "neutral"
    return "negative"


def _score_sales_history(
    evidence: SalesHistoryEvidence | None,
) -> HistoryConfidenceAssessment | None:
    if evidence is None:
        return None

    score = evidence.history_confidence
    if not isinstance(score, (float, int)):
        score = 0.3
        score += min(evidence.event_count, 4) * 0.10
        score += min(evidence.complete_event_count, 4) * 0.07
        score += min(evidence.repeat_sale_pairs, 3) * 0.05
        if "disclosure_gap" in evidence.history_flags:
            score -= 0.08
        if "missing_price_per_sqft" in evidence.history_flags:
            score -= 0.05
        score = max(0.15, min(score, 0.95))

    label = evidence.history_confidence_label or _history_label(float(score))
    notes = [
        f"{evidence.event_count} sales history event(s)",
        f"{evidence.complete_event_count} complete event(s)",
    ]
    if evidence.repeat_sale_pairs:
        notes.append(f"{evidence.repeat_sale_pairs} repeat-sale pair(s)")
    if evidence.history_span_years is not None:
        notes.append(f"history span {evidence.history_span_years:.2f} years")
    if evidence.history_flags:
        notes.append("flags: " + ", ".join(evidence.history_flags))
    return HistoryConfidenceAssessment(
        score=round(float(score), 3),
        label=label,
        notes=notes,
    )


def _history_label(score: float) -> str:
    if score >= 0.8:
        return "strong"
    if score >= 0.6:
        return "adequate"
    if score >= 0.35:
        return "weak"
    return "thin"

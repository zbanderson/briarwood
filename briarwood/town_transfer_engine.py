"""Town Transfer Engine.

A FALLBACK translation layer that borrows aggregate pricing evidence from
similar nearby towns when local comp support is thin (< 3 same-town comps
at adequate similarity).

This engine does NOT load cross-town individual comps. Instead, it uses
town-level aggregate metrics (median PPSF, price indexes, coastal profiles)
to compute a translation factor that adjusts the subject's thin local
comp base.

Activation:
  - Only when BaseCompSupportSummary.support_quality == "thin"
  - Returns {"used": False} immediately when local support is adequate

Evidence chain:
  1. Compute town-pair similarity from available metrics
  2. Select best donor town (highest similarity, adequate data quality)
  3. Compute PPSF-ratio translation factor
  4. Apply translation to local base shell value
  5. Penalize confidence substantially
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from briarwood.agents.comparable_sales.schemas import (
    BaseCompSelection,
    ComparableSalesOutput,
)
from briarwood.modules.town_aggregation_diagnostics import (
    TownContext,
    get_town_context,
)
from briarwood.schemas import PropertyInput


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum town-pair similarity to allow transfer.
_MIN_SIMILARITY = 0.40

# Maximum confidence after transfer — even the best transfer is weaker
# than direct local comps.
_MAX_TRANSFERRED_CONFIDENCE = 0.45

# Confidence penalty applied to the comp output's confidence.
_CONFIDENCE_PENALTY = 0.25

# Weight given to the translated value when blending with thin local base.
# A thin local base still has some signal — don't discard it entirely.
_TRANSFER_BLEND_WEIGHT = 0.35

# Minimum sample size in donor town to consider it usable.
_MIN_DONOR_SAMPLE_SIZE = 8

# Maximum PPSF coefficient of variation (std/median) in donor town.
_MAX_DONOR_DISPERSION = 0.40

# Similarity weights for town-pair scoring.
_SIMILARITY_WEIGHTS = {
    "ppsf_index": 0.35,
    "coastal_profile": 0.25,
    "price_level": 0.20,
    "liquidity": 0.10,
    "lot_profile": 0.10,
}

# Curated adjacency groups — towns that share geographic borders and
# market characteristics. Towns within the same group get a similarity
# bonus. This is intentionally small and hand-maintained for the NJ
# shore market.
_ADJACENCY_GROUPS: list[list[str]] = [
    ["Belmar", "Avon By The Sea", "Bradley Beach", "Lake Como"],
    ["Spring Lake", "Spring Lake Heights", "Sea Girt"],
    ["Manasquan", "Brielle", "Point Pleasant Beach"],
    ["Asbury Park", "Ocean Grove", "Neptune"],
]

# Bonus applied to similarity score when towns are in same adjacency group.
_ADJACENCY_BONUS = 0.10


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DonorTownEvidence:
    """Evidence about the selected donor town."""
    donor_town: str
    donor_median_ppsf: float | None = None
    donor_ppsf_index: float | None = None
    donor_price_index: float | None = None
    donor_sample_size: int = 0
    donor_context_confidence: float = 0.0
    subject_median_ppsf: float | None = None
    subject_ppsf_index: float | None = None
    subject_price_index: float | None = None
    subject_sample_size: int = 0
    is_adjacent: bool = False
    coastal_profile_delta: float | None = None


@dataclass(slots=True)
class TownPairScore:
    """Similarity score between two towns."""
    donor_town: str
    similarity: float
    components: dict[str, float] = field(default_factory=dict)
    is_adjacent: bool = False
    disqualified: bool = False
    disqualification_reason: str | None = None


@dataclass(slots=True)
class TransferResult:
    """Complete output of the Town Transfer Engine."""
    used: bool
    reason: str
    donor_town: str | None = None
    translation_factor: float | None = None
    translated_shell_value: float | None = None
    blended_value: float | None = None
    local_base_value: float | None = None
    confidence_penalty: float = 0.0
    transferred_confidence: float | None = None
    similarity_score: float | None = None
    method: str = "not_activated"
    evidence: DonorTownEvidence | None = None
    candidates_evaluated: int = 0
    candidate_scores: list[TownPairScore] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_town_transfer(
    *,
    property_input: PropertyInput,
    comp_output: ComparableSalesOutput,
    base_comp_selection: BaseCompSelection | None = None,
    town_metrics: dict[str, Any] | None = None,
    coastal_profiles: list[dict[str, Any]] | None = None,
) -> TransferResult:
    """Evaluate whether town transfer is needed and compute translated value.

    Args:
        property_input: The subject property.
        comp_output: Full comparable sales output.
        base_comp_selection: The base comp selection result.
        town_metrics: Town-level metrics. Optional.
        coastal_profiles: Coastal profile data per town. Optional.

    Returns:
        TransferResult with used=True if transfer was activated.
    """
    # Step 1: Check activation — only activate on thin support.
    support_quality = _get_support_quality(base_comp_selection)
    if support_quality != "thin":
        return TransferResult(
            used=False,
            reason=f"Local comp support is '{support_quality}' — no transfer needed.",
        )

    # Step 2: Get subject town context.
    subject_context = get_town_context(property_input.town)
    if subject_context is None:
        return TransferResult(
            used=False,
            reason=f"No town context available for '{property_input.town}' — cannot compute transfer.",
            warnings=["Subject town has no aggregate metrics in the dataset."],
        )

    # Step 3: Find candidate donor towns.
    candidates = _find_donor_candidates(
        subject_context=subject_context,
        subject_town=property_input.town,
        coastal_profiles=coastal_profiles or [],
    )

    if not candidates:
        return TransferResult(
            used=False,
            reason="No eligible donor towns found — all candidates disqualified or insufficient data.",
            candidates_evaluated=0,
            warnings=["No towns in the dataset meet donor eligibility criteria."],
        )

    # Step 4: Select best donor.
    eligible = [c for c in candidates if not c.disqualified]
    if not eligible:
        return TransferResult(
            used=False,
            reason="All candidate donor towns were disqualified.",
            candidates_evaluated=len(candidates),
            candidate_scores=candidates[:5],
            warnings=[
                f"{c.donor_town}: {c.disqualification_reason}"
                for c in candidates
                if c.disqualification_reason
            ][:3],
        )

    best = max(eligible, key=lambda c: c.similarity)

    if best.similarity < _MIN_SIMILARITY:
        return TransferResult(
            used=False,
            reason=f"Best donor '{best.donor_town}' similarity {best.similarity:.2f} below minimum {_MIN_SIMILARITY}.",
            candidates_evaluated=len(candidates),
            candidate_scores=candidates[:5],
            warnings=[f"Closest donor town '{best.donor_town}' is not similar enough for reliable transfer."],
        )

    # Step 5: Get donor context and compute translation.
    donor_context = get_town_context(best.donor_town)
    if donor_context is None:
        return TransferResult(
            used=False,
            reason=f"Donor town '{best.donor_town}' context unavailable at translation time.",
            candidates_evaluated=len(candidates),
            candidate_scores=candidates[:5],
        )

    # Step 6: Compute translation factor and translated value.
    local_base = _get_local_base_value(comp_output, base_comp_selection)
    translation_factor = _compute_translation_factor(subject_context, donor_context)

    if translation_factor is None:
        return TransferResult(
            used=False,
            reason="Cannot compute PPSF translation factor — missing median PPSF for subject or donor.",
            candidates_evaluated=len(candidates),
            candidate_scores=candidates[:5],
            warnings=["Both towns need median PPSF data for transfer."],
        )

    translated_shell = _compute_translated_shell_value(
        donor_context=donor_context,
        translation_factor=translation_factor,
        property_input=property_input,
    )

    if translated_shell is None:
        return TransferResult(
            used=False,
            reason="Cannot compute translated shell value — donor median PPSF unavailable.",
            candidates_evaluated=len(candidates),
            candidate_scores=candidates[:5],
        )

    # Step 7: Blend with local base if available.
    blended = _blend_values(local_base, translated_shell)

    # Step 8: Compute confidence.
    raw_confidence = float(comp_output.comp_confidence_score or comp_output.confidence or 0.0)
    transferred_confidence = min(
        max(raw_confidence - _CONFIDENCE_PENALTY, 0.05),
        _MAX_TRANSFERRED_CONFIDENCE,
    )

    # Step 9: Build evidence.
    coastal_delta = _coastal_profile_delta(
        property_input.town, best.donor_town, coastal_profiles or [],
    )
    evidence = DonorTownEvidence(
        donor_town=best.donor_town,
        donor_median_ppsf=donor_context.median_ppsf,
        donor_ppsf_index=donor_context.town_ppsf_index,
        donor_price_index=donor_context.town_price_index,
        donor_sample_size=donor_context.sample_size,
        donor_context_confidence=donor_context.context_confidence,
        subject_median_ppsf=subject_context.median_ppsf,
        subject_ppsf_index=subject_context.town_ppsf_index,
        subject_price_index=subject_context.town_price_index,
        subject_sample_size=subject_context.sample_size,
        is_adjacent=best.is_adjacent,
        coastal_profile_delta=coastal_delta,
    )

    warnings: list[str] = []
    if not best.is_adjacent:
        warnings.append(f"Donor '{best.donor_town}' is not in the same adjacency group as '{property_input.town}'.")
    if donor_context.high_dispersion_flag:
        warnings.append(f"Donor '{best.donor_town}' has high price dispersion — transfer may be less reliable.")
    if translation_factor > 1.30 or translation_factor < 0.70:
        warnings.append(
            f"Translation factor {translation_factor:.2f} is large — "
            f"subject and donor towns may have structurally different markets."
        )
    if local_base is None:
        warnings.append("No local base shell value available — translated value is unblended.")

    return TransferResult(
        used=True,
        reason=f"Local support is thin. Borrowed evidence from '{best.donor_town}' (similarity {best.similarity:.2f}).",
        donor_town=best.donor_town,
        translation_factor=round(translation_factor, 4),
        translated_shell_value=_round_money(translated_shell),
        blended_value=_round_money(blended),
        local_base_value=_round_money(local_base),
        confidence_penalty=_CONFIDENCE_PENALTY,
        transferred_confidence=round(transferred_confidence, 3),
        similarity_score=round(best.similarity, 3),
        method="ppsf_ratio_transfer",
        evidence=evidence,
        candidates_evaluated=len(candidates),
        candidate_scores=candidates[:5],
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Activation check
# ---------------------------------------------------------------------------

def _get_support_quality(base_comp_selection: BaseCompSelection | None) -> str:
    if base_comp_selection is None:
        return "thin"
    return base_comp_selection.support_summary.support_quality


# ---------------------------------------------------------------------------
# Donor candidate discovery
# ---------------------------------------------------------------------------

def _find_donor_candidates(
    *,
    subject_context: TownContext,
    subject_town: str,
    coastal_profiles: list[dict[str, Any]],
) -> list[TownPairScore]:
    """Find and score all candidate donor towns from the dataset."""
    from briarwood.modules.town_aggregation_diagnostics import (
        build_town_aggregation_diagnostics,
    )

    diagnostics = build_town_aggregation_diagnostics()
    if diagnostics.town_summary.empty:
        return []

    subject_town_normalized = subject_town.strip().title()
    coastal_map = _build_coastal_map(coastal_profiles)
    adjacency_map = _build_adjacency_map()

    candidates: list[TownPairScore] = []
    for _, row in diagnostics.town_summary.iterrows():
        candidate_town = str(row["town"])
        if candidate_town == subject_town_normalized or candidate_town == "Unknown":
            continue

        candidate_context = get_town_context(candidate_town)
        if candidate_context is None:
            continue

        score = _score_town_pair(
            subject=subject_context,
            donor=candidate_context,
            subject_town=subject_town_normalized,
            donor_town=candidate_town,
            coastal_map=coastal_map,
            adjacency_map=adjacency_map,
        )
        candidates.append(score)

    candidates.sort(key=lambda c: c.similarity, reverse=True)
    return candidates


def _score_town_pair(
    *,
    subject: TownContext,
    donor: TownContext,
    subject_town: str,
    donor_town: str,
    coastal_map: dict[str, float],
    adjacency_map: dict[str, str],
) -> TownPairScore:
    """Compute similarity score between subject and donor town."""
    # Check disqualification first.
    if donor.sample_size < _MIN_DONOR_SAMPLE_SIZE:
        return TownPairScore(
            donor_town=donor_town,
            similarity=0.0,
            disqualified=True,
            disqualification_reason=f"Sample size {donor.sample_size} below minimum {_MIN_DONOR_SAMPLE_SIZE}.",
        )

    if donor.low_sample_flag:
        return TownPairScore(
            donor_town=donor_town,
            similarity=0.0,
            disqualified=True,
            disqualification_reason="Donor flagged as low-sample town.",
        )

    if donor.median_ppsf is None:
        return TownPairScore(
            donor_town=donor_town,
            similarity=0.0,
            disqualified=True,
            disqualification_reason="No median PPSF available.",
        )

    components: dict[str, float] = {}

    # PPSF index similarity — how close are the price-per-sqft levels?
    ppsf_sim = _index_similarity(subject.town_ppsf_index, donor.town_ppsf_index)
    components["ppsf_index"] = ppsf_sim

    # Coastal profile similarity.
    subject_coastal = coastal_map.get(subject_town)
    donor_coastal = coastal_map.get(donor_town)
    coastal_sim = _value_similarity(subject_coastal, donor_coastal, max_delta=0.30)
    components["coastal_profile"] = coastal_sim

    # Price level similarity.
    price_sim = _index_similarity(subject.town_price_index, donor.town_price_index)
    components["price_level"] = price_sim

    # Liquidity similarity.
    liquidity_sim = _index_similarity(subject.town_liquidity_index, donor.town_liquidity_index)
    components["liquidity"] = liquidity_sim

    # Lot profile similarity.
    lot_sim = _index_similarity(subject.town_lot_index, donor.town_lot_index)
    components["lot_profile"] = lot_sim

    # Weighted similarity.
    weighted = sum(
        _SIMILARITY_WEIGHTS[key] * components.get(key, 0.5)
        for key in _SIMILARITY_WEIGHTS
    )

    # Adjacency bonus.
    is_adjacent = adjacency_map.get(subject_town) == adjacency_map.get(donor_town) and adjacency_map.get(subject_town) is not None
    if is_adjacent:
        weighted = min(weighted + _ADJACENCY_BONUS, 1.0)

    # Dispersion penalty — donor with high dispersion gets penalized.
    if donor.high_dispersion_flag:
        weighted *= 0.80

    return TownPairScore(
        donor_town=donor_town,
        similarity=round(weighted, 3),
        components=components,
        is_adjacent=is_adjacent,
    )


def _index_similarity(a: float | None, b: float | None) -> float:
    """Similarity between two index values (region=100 scale).

    Returns 1.0 for identical indexes, approaching 0.0 as they diverge.
    """
    if a is None or b is None:
        return 0.5  # neutral when data is missing
    # Compute ratio — e.g., 95 vs 110 → 95/110 = 0.864
    ratio = min(a, b) / max(a, b) if max(a, b) > 0 else 1.0
    return round(ratio, 3)


def _value_similarity(a: float | None, b: float | None, max_delta: float = 0.30) -> float:
    """Similarity between two values on [0, 1] scale."""
    if a is None or b is None:
        return 0.5
    delta = abs(a - b)
    return round(max(1.0 - delta / max_delta, 0.0), 3)


def _build_coastal_map(profiles: list[dict[str, Any]]) -> dict[str, float]:
    """Build town → coastal_profile_signal map."""
    result: dict[str, float] = {}
    for profile in profiles:
        name = str(profile.get("name", "")).strip().title()
        signal = profile.get("coastal_profile_signal")
        if name and signal is not None:
            result[name] = float(signal)
    return result


def _build_adjacency_map() -> dict[str, str]:
    """Build town → group_id map from adjacency groups."""
    result: dict[str, str] = {}
    for i, group in enumerate(_ADJACENCY_GROUPS):
        group_id = f"group_{i}"
        for town in group:
            result[town] = group_id
    return result


# ---------------------------------------------------------------------------
# Translation computation
# ---------------------------------------------------------------------------

def _compute_translation_factor(
    subject: TownContext,
    donor: TownContext,
) -> float | None:
    """Compute PPSF ratio between subject and donor town.

    Returns subject_ppsf / donor_ppsf — the factor to multiply donor-derived
    values by to translate them to the subject's market.
    """
    if subject.median_ppsf is None or donor.median_ppsf is None:
        return None
    if donor.median_ppsf <= 0:
        return None
    return subject.median_ppsf / donor.median_ppsf


def _compute_translated_shell_value(
    *,
    donor_context: TownContext,
    translation_factor: float,
    property_input: PropertyInput,
) -> float | None:
    """Compute a translated shell value for the subject using donor town metrics.

    Uses the subject's sqft and the donor's median PPSF, adjusted by the
    translation factor.
    """
    if donor_context.median_ppsf is None:
        return None
    subject_sqft = property_input.sqft
    if subject_sqft is None or subject_sqft <= 0:
        # Fall back to donor median price if subject sqft unavailable.
        if donor_context.median_sale_price is not None:
            return donor_context.median_sale_price * translation_factor
        return None
    # Donor PPSF * subject sqft * translation factor
    # The translation factor already accounts for the PPSF gap, but we use
    # donor PPSF as the base since the donor has better evidence.
    # translated_ppsf = donor_ppsf * (subject_ppsf / donor_ppsf) = subject_ppsf
    # So this simplifies to subject_ppsf * subject_sqft, which is intentional —
    # the donor provides the calibration confidence that the subject's thin
    # local median is in the right ballpark.
    translated_ppsf = donor_context.median_ppsf * translation_factor
    return translated_ppsf * float(subject_sqft)


def _get_local_base_value(
    comp_output: ComparableSalesOutput,
    base_comp_selection: BaseCompSelection | None,
) -> float | None:
    """Extract the local base shell value from existing comp analysis."""
    if base_comp_selection is not None and base_comp_selection.base_shell_value is not None:
        return base_comp_selection.base_shell_value
    return comp_output.comparable_value


def _blend_values(
    local_base: float | None,
    translated: float | None,
) -> float | None:
    """Blend local thin base with translated value.

    When local_base exists, blend using _TRANSFER_BLEND_WEIGHT for the
    translated portion. When local_base is missing, use translated alone.
    """
    if translated is None:
        return local_base
    if local_base is None:
        return translated
    return local_base * (1.0 - _TRANSFER_BLEND_WEIGHT) + translated * _TRANSFER_BLEND_WEIGHT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coastal_profile_delta(
    subject_town: str,
    donor_town: str,
    coastal_profiles: list[dict[str, Any]],
) -> float | None:
    """Absolute difference in coastal profile signals."""
    coastal_map = _build_coastal_map(coastal_profiles)
    subject_val = coastal_map.get(subject_town.strip().title())
    donor_val = coastal_map.get(donor_town.strip().title())
    if subject_val is None or donor_val is None:
        return None
    return round(abs(subject_val - donor_val), 3)


def _round_money(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)

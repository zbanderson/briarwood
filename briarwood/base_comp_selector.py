from __future__ import annotations

from statistics import median

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    BaseCompSelectionItem,
    BaseCompSupportSummary,
    ComparableSalesRequest,
)


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

_TIERS: list[dict[str, object]] = [
    {
        "name": "tight_local",
        "rank": 0,
        "max_distance": 0.5,
        "max_sqft_ratio": 0.20,
        "max_bed_gap": 1,
        "max_bath_gap": 1.0,
        "max_sale_age_days": 180,
    },
    {
        "name": "loose_local",
        "rank": 1,
        "max_distance": 1.5,
        "max_sqft_ratio": 0.30,
        "max_bed_gap": 2,
        "max_bath_gap": 1.0,
        "max_sale_age_days": 365,
    },
    {
        "name": "broad_local",
        "rank": 2,
        "max_distance": 3.0,
        "max_sqft_ratio": 0.40,
        "max_bed_gap": 3,
        "max_bath_gap": 2.0,
        "max_sale_age_days": 548,
    },
]

_MIN_COMPS_PER_TIER = 3
_MAX_SELECTED = 5

# ---------------------------------------------------------------------------
# Similarity score weights — must sum to 1.0
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "property_type": 0.15,
    "distance": 0.15,
    "sqft": 0.15,
    "recency": 0.14,
    "beds": 0.10,
    "baths": 0.07,
    "lot": 0.08,
    "age": 0.06,
    "condition": 0.05,
    "structure": 0.03,
    "data_quality": 0.02,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_base_comp_selection(
    *,
    request: ComparableSalesRequest,
    adjusted_comps: list[AdjustedComparable],
) -> tuple[list[AdjustedComparable], BaseCompSelection]:
    evaluations = [_evaluate_comp(request=request, comp=comp) for comp in adjusted_comps]

    # Hard reject: property type mismatch is never relaxed.
    evaluations = [e for e in evaluations if e["property_type_match"]]

    # Assign tiers (strict to loose).
    for item in evaluations:
        item["tier"], item["tier_rank"] = _assign_tier(item)

    # Build pools per tier.
    tier_pools = {tier["name"]: [] for tier in _TIERS}
    for item in evaluations:
        tier_name = str(item["tier"])
        if tier_name in tier_pools:
            tier_pools[tier_name].append(item)

    # Select: expand through tiers until we have enough comps.
    selected: list[dict[str, object]] = []
    used_tier_names: list[str] = []
    for tier in _TIERS:
        tier_name = str(tier["name"])
        pool = tier_pools[tier_name]
        if pool:
            selected.extend(pool)
            used_tier_names.append(tier_name)
        if len(selected) >= _MIN_COMPS_PER_TIER:
            break

    # Sort by (tier priority, score desc, distance asc, recency asc).
    selected.sort(
        key=lambda item: (
            int(item["tier_rank"]),
            -float(item["score"]),
            float(item["distance_rank"]),
            int(item["sale_age_days"]),
        )
    )
    selected = selected[:_MAX_SELECTED]
    selected_comps = [item["comp"] for item in selected]
    base_shell_value = _weighted_value(selected)

    support_quality = _support_quality(selected, used_tier_names, request)
    median_distance = _median_distance(selected)

    selection = BaseCompSelection(
        selected_comps=[
            BaseCompSelectionItem(
                id=f"{item['comp'].address.lower().replace(' ', '-')}|{item['comp'].sale_date}",
                address=item["comp"].address,
                sale_price=float(item["comp"].sale_price),
                distance_miles=item["comp"].distance_to_subject_miles,
                similarity_score=round(float(item["score"]), 3),
                match_reasons=list(item["matches"])[:5],
                mismatch_flags=list(item["mismatches"])[:5],
                selection_tier=str(item["tier"]),
            )
            for item in selected
        ],
        base_shell_value=round(base_shell_value, 2) if base_shell_value is not None else None,
        support_summary=BaseCompSupportSummary(
            comp_count=len(selected),
            same_town_count=_count_same_town(selected, request.town),
            median_distance=median_distance,
            support_quality=support_quality,
            notes=_support_notes(selected, support_quality, used_tier_names, request),
        ),
    )

    updated_comps: list[AdjustedComparable] = []
    selected_ids = {id(item["comp"]): item for item in selected}
    for comp in adjusted_comps:
        selected_item = selected_ids.get(id(comp))
        if selected_item is None:
            continue
        updated_comps.append(
            comp.model_copy(
                update={
                    "base_similarity_score": round(float(selected_item["score"]), 3),
                    "base_selection_tier": str(selected_item["tier"]),
                }
            )
        )
    return updated_comps, selection


# ---------------------------------------------------------------------------
# Per-comp evaluation
# ---------------------------------------------------------------------------

def _evaluate_comp(*, request: ComparableSalesRequest, comp: AdjustedComparable) -> dict[str, object]:
    matches: list[str] = []
    mismatches: list[str] = []

    # Property type — hard requirement, never relaxed.
    property_type_match = _property_type_match(request.property_type, comp.property_type)
    if property_type_match:
        matches.append("same property-type family")
    else:
        mismatches.append("property type mismatch")

    # Distance
    distance = comp.distance_to_subject_miles
    distance_score, distance_label = _distance_score(distance)
    if distance_label:
        (matches if distance_score >= 0.75 else mismatches).append(distance_label)

    # Dimensional scores
    beds_score, beds_match, beds_mismatch = _closeness_score(
        request.beds, comp.bedrooms, good=0, usable=1, max_gap=2, label="bed count",
    )
    baths_score, baths_match, baths_mismatch = _closeness_score(
        request.baths, comp.bathrooms, good=0.5, usable=1.0, max_gap=1.5, label="bath count",
    )
    sqft_score, sqft_match, sqft_mismatch = _ratio_score(
        request.sqft, comp.sqft, tight=0.12, usable=0.22, max_ratio=0.35, label="living area",
    )
    lot_score, lot_match, lot_mismatch = _ratio_score(
        request.lot_size, comp.lot_size, tight=0.25, usable=0.5, max_ratio=1.0, label="lot size",
    )
    age_score, age_match, age_mismatch = _closeness_score(
        request.year_built, comp.year_built, good=10, usable=25, max_gap=45, label="era",
    )
    condition_score, condition_match, condition_mismatch = _condition_score(
        request.condition_profile, comp.condition_profile,
    )
    structure_score, structure_match, structure_mismatch = _structure_score(
        request.stories, comp.stories,
    )
    recency_score, recency_match, recency_mismatch = _recency_score(comp.sale_age_days)
    data_quality_score = _data_quality_score(comp)

    for match in [beds_match, baths_match, sqft_match, lot_match, age_match, condition_match, structure_match, recency_match]:
        if match:
            matches.append(match)
    for mismatch in [beds_mismatch, baths_mismatch, sqft_mismatch, lot_mismatch, age_mismatch, condition_mismatch, structure_mismatch, recency_mismatch]:
        if mismatch:
            mismatches.append(mismatch)

    score = (
        _WEIGHTS["property_type"] * (1.0 if property_type_match else 0.0)
        + _WEIGHTS["distance"] * distance_score
        + _WEIGHTS["sqft"] * sqft_score
        + _WEIGHTS["recency"] * recency_score
        + _WEIGHTS["beds"] * beds_score
        + _WEIGHTS["baths"] * baths_score
        + _WEIGHTS["lot"] * lot_score
        + _WEIGHTS["age"] * age_score
        + _WEIGHTS["condition"] * condition_score
        + _WEIGHTS["structure"] * structure_score
        + _WEIGHTS["data_quality"] * data_quality_score
    )
    if request.subject_is_nonstandard:
        score -= 0.05
        mismatches.append("split-structure subject; clean single-structure comp may overstate shell demand")
    score = max(0.0, min(score, 1.0))

    return {
        "comp": comp,
        "score": score,
        "matches": matches,
        "mismatches": mismatches,
        "property_type_match": property_type_match,
        "tier": "rejected",  # overwritten by _assign_tier
        "tier_rank": 99,
        "distance_rank": distance if distance is not None else 99.0,
        "sale_age_days": comp.sale_age_days,
        # Raw dimensional values for tier assignment
        "_distance": distance,
        "_bed_gap": _gap(request.beds, comp.bedrooms),
        "_bath_gap": _gap(request.baths, comp.bathrooms),
        "_sqft_ratio": _ratio_gap(request.sqft, comp.sqft),
        "_sale_age_days": comp.sale_age_days,
    }


def _assign_tier(item: dict[str, object]) -> tuple[str, int]:
    """Assign the tightest tier the comp qualifies for."""
    for tier in _TIERS:
        if (
            _within(item["_distance"], float(tier["max_distance"]))
            and float(item["_bed_gap"]) <= int(tier["max_bed_gap"])
            and float(item["_bath_gap"]) <= float(tier["max_bath_gap"])
            and float(item["_sqft_ratio"]) <= float(tier["max_sqft_ratio"])
            and int(item["_sale_age_days"]) <= int(tier["max_sale_age_days"])
        ):
            return str(tier["name"]), int(tier["rank"])
    return "extended_support", 3


# ---------------------------------------------------------------------------
# Support quality and notes
# ---------------------------------------------------------------------------

def _support_quality(selected: list[dict[str, object]], used_tier_names: list[str], request: ComparableSalesRequest) -> str:
    if not selected:
        return "thin"
    scores = [float(item["score"]) for item in selected]
    med_score = median(scores)
    med_distance = _median_distance(selected)
    has_extended = any(str(item["tier"]) == "extended_support" for item in selected)

    quality = "thin"
    if len(selected) >= 4 and med_score >= 0.72 and not has_extended and (med_distance is None or med_distance <= 1.5):
        quality = "strong"
    elif len(selected) >= 3 and med_score >= 0.58:
        quality = "moderate"

    if request.subject_is_nonstandard:
        tier_names = {str(item["tier"]) for item in selected}
        if quality == "strong" and ("loose_local" in tier_names or "broad_local" in tier_names):
            quality = "moderate"
        elif quality == "moderate" and med_score < 0.68:
            quality = "thin"
    return quality


def _support_notes(
    selected: list[dict[str, object]],
    support_quality: str,
    used_tier_names: list[str],
    request: ComparableSalesRequest,
) -> list[str]:
    if not selected:
        return ["No direct local comps cleared the base-shell selector."]
    notes = [
        "Base selector prioritizes same-town, same-type sales with strict-to-loose tier expansion.",
    ]
    tier_names = [str(item["tier"]) for item in selected]
    if "extended_support" in tier_names:
        ext_count = sum(1 for t in tier_names if t == "extended_support")
        notes.append(
            f"{ext_count} comp(s) required extended support (beyond standard tiers). "
            "Shell evidence should be treated cautiously."
        )
    elif "broad_local" in tier_names:
        notes.append("Support extends into the broad local tier but stays within controlled tolerances.")
    elif "loose_local" in tier_names:
        notes.append("Support extends beyond the tightest tier but still stays within close local tolerances.")
    if support_quality == "thin":
        notes.append("Direct shell support is thin; downstream layers should not overstate precision.")
    if request.subject_is_nonstandard:
        notes.append("Because the subject is a split-structure / accessory-unit property, clean same-town comps can overstate shell demand.")
    return notes


# ---------------------------------------------------------------------------
# Weighted base shell value
# ---------------------------------------------------------------------------

def _weighted_value(selected: list[dict[str, object]]) -> float | None:
    if not selected:
        return None
    weights = []
    values = []
    for item in selected:
        comp = item["comp"]
        tier_bonus = {
            "tight_local": 1.0,
            "loose_local": 0.85,
            "broad_local": 0.68,
            "extended_support": 0.50,
        }.get(str(item["tier"]), 0.40)
        # Recency decay: prefer recent sales in the weighted average.
        recency_factor = _recency_decay(int(item["sale_age_days"]))
        weight = max(
            float(item["score"]) * tier_bonus * recency_factor * max(float(getattr(comp, "comp_confidence_weight", 0.0) or 0.0), 0.35),
            0.05,
        )
        weights.append(weight)
        values.append(float(comp.adjusted_price))
    total_weight = sum(weights) or 1.0
    return sum(value * weight for value, weight in zip(values, weights)) / total_weight


def _recency_decay(sale_age_days: int) -> float:
    """Smooth decay so recent sales dominate the weighted average."""
    if sale_age_days <= 90:
        return 1.0
    if sale_age_days <= 180:
        return 0.95
    if sale_age_days <= 365:
        return 0.82
    if sale_age_days <= 548:
        return 0.65
    return 0.45


# ---------------------------------------------------------------------------
# Town membership
# ---------------------------------------------------------------------------

def _count_same_town(selected: list[dict[str, object]], subject_town: str) -> int:
    """Count comps that share the subject's town.

    Today the provider only loads same-town sales, so this will equal
    len(selected). When cross-town support is added, this will start
    distinguishing same-town from adjacent-town comps.
    """
    # TODO: when cross-town comps are supported, compare comp.town to subject_town.
    return len(selected)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _median_distance(selected: list[dict[str, object]]) -> float | None:
    distances = [float(item["comp"].distance_to_subject_miles) for item in selected if item["comp"].distance_to_subject_miles is not None]
    if not distances:
        return None
    return round(float(median(distances)), 2)


def _property_type_match(subject_type: str | None, comp_type: str | None) -> bool:
    subject_family = _property_type_family(subject_type)
    comp_family = _property_type_family(comp_type)
    if subject_family == "unknown" or comp_family == "unknown":
        return True
    return subject_family == comp_family


def _property_type_family(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", " ")
    normalized = " ".join(normalized.split())
    if "single family" in normalized:
        return "single_family"
    if "condo" in normalized or "condominium" in normalized:
        return "condo"
    if "townhouse" in normalized or "townhome" in normalized:
        return "townhouse"
    if "multi family" in normalized or "multifamily" in normalized or "duplex" in normalized or "triplex" in normalized:
        return "multi_family"
    return normalized or "unknown"


def _distance_score(distance: float | None) -> tuple[float, str | None]:
    if distance is None:
        return 0.55, None
    if distance <= 0.25:
        return 1.0, "very close radius (<0.25mi)"
    if distance <= 0.5:
        return 0.92, "close radius (0.25-0.5mi)"
    if distance <= 1.0:
        return 0.80, "near radius (0.5-1.0mi)"
    if distance <= 1.5:
        return 0.70, "local radius (1.0-1.5mi)"
    if distance <= 3.0:
        return 0.52, "extended radius (1.5-3.0mi)"
    if distance <= 5.0:
        return 0.30, "far radius (3-5mi)"
    return 0.08, "outside preferred radius"


def _closeness_score(
    subject: float | None,
    comp: float | None,
    *,
    good: float,
    usable: float,
    max_gap: float,
    label: str,
) -> tuple[float, str | None, str | None]:
    if subject is None or comp is None:
        return 0.55, None, None
    gap = abs(float(subject) - float(comp))
    if gap <= good:
        return 1.0, f"matched {label}", None
    if gap <= usable:
        return 0.8, f"close {label}", None
    if gap <= max_gap:
        return 0.55, None, f"{label} stretches"
    return 0.15, None, f"{label} mismatch"


def _ratio_score(
    subject: float | None,
    comp: float | None,
    *,
    tight: float,
    usable: float,
    max_ratio: float,
    label: str,
) -> tuple[float, str | None, str | None]:
    if subject in (None, 0) or comp in (None, 0):
        return 0.55, None, None
    gap = abs(float(subject) - float(comp)) / max(float(subject), 0.01)
    if gap <= tight:
        return 1.0, f"matched {label}", None
    if gap <= usable:
        return 0.78, f"close {label}", None
    if gap <= max_ratio:
        return 0.5, None, f"{label} stretches"
    return 0.12, None, f"{label} mismatch"


def _condition_score(subject: str | None, comp: str | None) -> tuple[float, str | None, str | None]:
    if not subject or not comp:
        return 0.55, None, None
    if subject == comp:
        return 1.0, "similar condition", None
    rank = {"needs_work": 0, "dated": 1, "maintained": 2, "updated": 3, "renovated": 4}
    subject_rank = rank.get(subject, 2)
    comp_rank = rank.get(comp, 2)
    gap = abs(subject_rank - comp_rank)
    if gap == 1:
        return 0.7, None, "condition differs"
    return 0.35, None, "condition mismatch"


def _structure_score(subject: float | None, comp: float | None) -> tuple[float, str | None, str | None]:
    if subject is None or comp is None:
        return 0.55, None, None
    if abs(float(subject) - float(comp)) < 0.1:
        return 1.0, "similar structure form", None
    if abs(float(subject) - float(comp)) <= 1.0:
        return 0.7, None, "structure form differs"
    return 0.35, None, "structure mismatch"


def _recency_score(sale_age_days: int | None) -> tuple[float, str | None, str | None]:
    if sale_age_days is None:
        return 0.5, None, None
    if sale_age_days <= 90:
        return 1.0, "very recent sale (<3mo)", None
    if sale_age_days <= 180:
        return 0.90, "recent sale (3-6mo)", None
    if sale_age_days <= 365:
        return 0.70, "moderately recent (6-12mo)", None
    if sale_age_days <= 548:
        return 0.48, None, "older sale (12-18mo)"
    return 0.22, None, "stale sale (>18mo)"


def _data_quality_score(comp: AdjustedComparable) -> float:
    """Reward comps with better verification and completeness."""
    verification = str(getattr(comp, "sale_verification_status", "") or "").lower()
    base = {
        "mls_verified": 1.0,
        "public_record_verified": 0.95,
        "public_record_matched": 0.82,
        "seeded": 0.60,
    }.get(verification, 0.55)
    # Slight boost for field completeness.
    fields = [comp.bedrooms, comp.bathrooms, comp.sqft, comp.lot_size, comp.year_built]
    present = sum(v not in (None, 0) for v in fields)
    completeness_bonus = (present / len(fields)) * 0.15
    return min(base + completeness_bonus, 1.0)


def _within(value: float | None, threshold: float) -> bool:
    return value is None or float(value) <= threshold


def _gap(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0
    return abs(float(left) - float(right))


def _ratio_gap(left: float | None, right: float | None) -> float:
    if left in (None, 0) or right in (None, 0):
        return 0.0
    return abs(float(left) - float(right)) / max(float(left), 0.01)

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from briarwood.data_quality.normalizers import (
    is_listing_description_as_address,
    normalize_date,
    normalize_full_address_string,
    normalize_lot_size,
    normalize_numeric,
    normalize_sqft,
    normalize_state,
    normalize_town,
)
from briarwood.data_quality.eligibility import classify_comp_eligibility
from briarwood.data_quality.provenance import FieldCandidate, FieldEvidence, PropertyEvidenceProfile
from briarwood.data_quality.source_policy import (
    IDENTITY_FIELDS,
    RENT_FIELDS,
    SALE_FIELDS,
    STRUCTURAL_FIELDS,
    TAX_FIELDS,
    field_group,
    get_field_policy,
    source_rank,
)
from briarwood.schemas import CanonicalFieldProvenance, CanonicalPropertyData, SourceMetadata, SourceTier, VerifiedStatus


def choose_field_value(field_name: str, candidates: list[FieldCandidate]) -> FieldEvidence:
    valid_candidates = [_normalize_candidate(candidate) for candidate in candidates]
    valid_candidates = [candidate for candidate in valid_candidates if _is_valid_candidate(candidate)]
    now = _utc_now()
    if not valid_candidates:
        return FieldEvidence(
            field_name=field_name,
            chosen_value=None,
            chosen_source="missing",
            chosen_source_tier=99,
            chosen_status="missing",
            arbitration_reason="No valid candidates were available.",
            updated_at=now,
            candidates=list(candidates),
        )

    if len(valid_candidates) == 1:
        chosen = valid_candidates[0]
        return FieldEvidence(
            field_name=field_name,
            chosen_value=chosen.value,
            chosen_source=chosen.source,
            chosen_source_tier=chosen.source_tier,
            chosen_status=_status_for_single_candidate(field_name, chosen),
            arbitration_reason="Only one valid candidate was available.",
            updated_at=now,
            candidates=list(candidates),
        )

    sorted_candidates = sorted(
        valid_candidates,
        key=lambda item: (
            not item.is_user_override,
            source_rank(field_name, item.source, is_user_override=item.is_user_override),
            -_verified_rank(item),
            -_confidence_rank(item),
            item.source_tier,
            -_observed_rank(item),
        ),
    )
    chosen = sorted_candidates[0]
    runner_up = sorted_candidates[1]
    if chosen.is_user_override and not get_field_policy(field_name).allow_user_override_replacement:
        status = "confirmed"
        reason = "Explicit user override retained."
    else:
        conflict = _material_conflict(field_name, chosen.value, runner_up.value)
        if conflict:
            verified_conflict = _verified_rank(chosen) >= 3 and _verified_rank(runner_up) >= 3
            status = "confirmed_with_conflict" if verified_conflict else "needs_review"
            reason = f"Top candidates conflict materially; kept {chosen.source} by field policy priority."
        else:
            status = "confirmed" if _verified_rank(chosen) >= 3 else "estimated"
            reason = f"Selected {chosen.source} based on {field_group(field_name)} field policy."

    return FieldEvidence(
        field_name=field_name,
        chosen_value=chosen.value,
        chosen_source=chosen.source,
        chosen_source_tier=chosen.source_tier,
        chosen_status=status,
        arbitration_reason=reason,
        updated_at=now,
        candidates=list(candidates),
    )


def build_property_evidence_profile(
    canonical_property: CanonicalPropertyData,
    source_payloads: dict[str, Any] | None = None,
) -> PropertyEvidenceProfile:
    source_payloads = source_payloads or {}
    candidate_map = _collect_candidates(canonical_property, source_payloads)
    identity_fields = _evidence_group(IDENTITY_FIELDS, candidate_map)
    structural_fields = _evidence_group(STRUCTURAL_FIELDS, candidate_map)
    tax_fields = _evidence_group(TAX_FIELDS, candidate_map)
    sale_fields = _evidence_group(SALE_FIELDS, candidate_map)
    rent_fields = _evidence_group(RENT_FIELDS, candidate_map)
    summary_flags = _summary_flags(
        identity_fields=identity_fields,
        structural_fields=structural_fields,
        tax_fields=tax_fields,
        sale_fields=sale_fields,
        rent_fields=rent_fields,
    )
    return PropertyEvidenceProfile(
        structural_fields=structural_fields,
        tax_fields=tax_fields,
        sale_fields=sale_fields,
        rent_fields=rent_fields,
        identity_fields=identity_fields,
        summary_flags=summary_flags,
    )


def apply_evidence_profile(
    canonical_property: CanonicalPropertyData,
    source_payloads: dict[str, Any] | None = None,
) -> CanonicalPropertyData:
    profile = build_property_evidence_profile(canonical_property, source_payloads)
    facts = canonical_property.facts
    market = canonical_property.market_signals
    assumptions = canonical_property.user_assumptions
    for field_name, evidence in (
        list(profile.identity_fields.items())
        + list(profile.structural_fields.items())
        + list(profile.tax_fields.items())
        + list(profile.sale_fields.items())
        + list(profile.rent_fields.items())
    ):
        chosen = evidence.chosen_value
        if chosen is None:
            continue
        if hasattr(facts, field_name):
            setattr(facts, field_name, chosen)
        elif hasattr(market, field_name):
            setattr(market, field_name, chosen)
        elif hasattr(assumptions, field_name):
            setattr(assumptions, field_name, chosen)
        elif field_name == "estimated_rent":
            assumptions.estimated_monthly_rent = chosen
        elif field_name == "tax_amount":
            facts.taxes = chosen
        elif field_name == "last_sale_price":
            history = list(facts.sale_history)
            if not history:
                history.append({"price": chosen, "date": profile.sale_fields.get("last_sale_date").chosen_value if profile.sale_fields.get("last_sale_date") else None})
            facts.sale_history = history

    field_provenance = dict(canonical_property.source_metadata.field_provenance)
    for field_name, evidence in (
        list(profile.identity_fields.items())
        + list(profile.structural_fields.items())
        + list(profile.tax_fields.items())
        + list(profile.sale_fields.items())
        + list(profile.rent_fields.items())
    ):
        field_provenance[field_name] = CanonicalFieldProvenance(
            value=evidence.chosen_value,
            source=evidence.chosen_source,
            source_tier=_to_source_tier(evidence.chosen_source_tier),
            verified_status=_to_verified_status(evidence.chosen_status),
            last_updated=evidence.updated_at,
            confidence=_evidence_confidence(evidence),
            mapper_version="arbitration/v1",
            notes=[evidence.arbitration_reason],
        )
    canonical_property.source_metadata = replace(
        canonical_property.source_metadata,
        field_provenance=field_provenance,
        property_evidence_profile=profile,
        mapper_version="arbitration/v1",
    )
    return canonical_property


def property_input_evidence_summary(property_input) -> dict[str, Any] | None:
    metadata = getattr(property_input, "source_metadata", None)
    if metadata is None:
        return None
    profile = metadata.get("property_evidence_profile") if isinstance(metadata, dict) else getattr(metadata, "property_evidence_profile", None)
    if profile is None:
        return None
    if isinstance(profile, PropertyEvidenceProfile):
        return profile.summary_flags
    if isinstance(profile, dict):
        return profile.get("summary_flags")
    return None


def _collect_candidates(canonical_property: CanonicalPropertyData, source_payloads: dict[str, Any]) -> dict[str, list[FieldCandidate]]:
    candidate_map: dict[str, list[FieldCandidate]] = {}
    metadata = canonical_property.source_metadata
    for field_name, provenance in metadata.field_provenance.items():
        candidate_map.setdefault(field_name, []).append(
            FieldCandidate(
                field_name=field_name,
                value=provenance.value,
                source=provenance.source,
                source_tier=_from_source_tier(provenance.source_tier),
                observed_at=provenance.last_updated,
                confidence_hint=f"{provenance.confidence:.2f}",
                is_user_override=provenance.verified_status == VerifiedStatus.USER_CONFIRMED,
                metadata={"mapper_version": provenance.mapper_version, "notes": list(provenance.notes)},
            )
        )
    _add_object_fields(candidate_map, canonical_property.facts, source="canonical_facts", tier=1)
    _add_object_fields(candidate_map, canonical_property.market_signals, source="canonical_market", tier=2)
    _add_object_fields(candidate_map, canonical_property.user_assumptions, source="canonical_assumptions", tier=3)
    for source_name, payload in source_payloads.items():
        if isinstance(payload, dict):
            for field_name, value in payload.items():
                candidate_map.setdefault(field_name, []).append(
                    FieldCandidate(
                        field_name=field_name,
                        value=value,
                        source=source_name,
                        source_tier=_infer_source_tier(source_name),
                    )
                )
    return candidate_map


def _add_object_fields(candidate_map: dict[str, list[FieldCandidate]], obj: object, *, source: str, tier: int) -> None:
    for field_name in getattr(obj, "__dataclass_fields__", {}).keys():
        value = getattr(obj, field_name)
        if value in (None, "", [], {}):
            continue
        candidate_map.setdefault(field_name, []).append(
            FieldCandidate(field_name=field_name, value=value, source=source, source_tier=tier)
        )


def _evidence_group(fields: set[str], candidate_map: dict[str, list[FieldCandidate]]) -> dict[str, FieldEvidence]:
    evidence: dict[str, FieldEvidence] = {}
    for field_name in fields:
        evidence[field_name] = choose_field_value(field_name, candidate_map.get(field_name, []))
    return evidence


def _summary_flags(
    *,
    identity_fields: dict[str, FieldEvidence],
    structural_fields: dict[str, FieldEvidence],
    tax_fields: dict[str, FieldEvidence],
    sale_fields: dict[str, FieldEvidence],
    rent_fields: dict[str, FieldEvidence],
) -> dict[str, Any]:
    structural_score = _quality_score(structural_fields, required={"beds", "baths", "sqft", "property_type"})
    tax_score = _quality_score(tax_fields, required={"tax_amount"})
    sale_score = _quality_score(sale_fields, required={"last_sale_price", "last_sale_date"})
    rent_score = _quality_score(rent_fields, required={"estimated_rent"})
    identity_status = _identity_match_status(identity_fields)
    comp_status = _comp_eligibility_status(identity_fields, structural_score, identity_status)
    gate = classify_comp_eligibility(
        PropertyEvidenceProfile(
            structural_fields=structural_fields,
            tax_fields=tax_fields,
            sale_fields=sale_fields,
            rent_fields=rent_fields,
            identity_fields=identity_fields,
        )
    )
    return {
        "structural_data_quality_score": round(structural_score, 3),
        "tax_data_quality_score": round(tax_score, 3),
        "sale_data_quality_score": round(sale_score, 3),
        "rent_data_quality_score": round(rent_score, 3),
        "identity_match_status": identity_status,
        "comp_eligibility_status": comp_status,
        "comp_eligibility_gate": gate.status,
        "comp_eligibility_reasons": list(gate.reasons),
        "comp_eligibility_warnings": list(gate.warnings),
        "fatal_conflicts": list(gate.fatal_conflicts),
    }


def _quality_score(evidence_map: dict[str, FieldEvidence], *, required: set[str]) -> float:
    if not required:
        return 0.0
    score = 0.0
    max_score = float(len(required))
    for field_name in required:
        evidence = evidence_map.get(field_name)
        if evidence is None or evidence.chosen_status == "missing":
            continue
        if evidence.chosen_status in {"confirmed", "confirmed_with_conflict"}:
            score += 1.0
        elif evidence.chosen_status == "estimated":
            score += 0.55
        elif evidence.chosen_status == "needs_review":
            score += 0.25
    optional_confirmed = sum(
        0.05 for field_name, evidence in evidence_map.items()
        if field_name not in required and evidence.chosen_status in {"confirmed", "confirmed_with_conflict"}
    )
    score += min(optional_confirmed, 0.2)
    return min(score / max_score, 1.0)


def _identity_match_status(identity_fields: dict[str, FieldEvidence]) -> str:
    address = identity_fields.get("address")
    town = identity_fields.get("town")
    state = identity_fields.get("state")
    if address is None or address.chosen_status == "missing" or is_listing_description_as_address(address.chosen_value):
        return "rejected"
    if state is None or str(state.chosen_value or "").upper() != "NJ":
        return "rejected"
    if any(item.chosen_status == "needs_review" for item in identity_fields.values()):
        return "needs_review"
    if town is not None and town.chosen_status == "confirmed_with_conflict":
        return "needs_review"
    return "confirmed"


def _comp_eligibility_status(identity_fields: dict[str, FieldEvidence], structural_score: float, identity_status: str) -> str:
    if identity_status == "rejected":
        return "rejected"
    if identity_status == "needs_review":
        return "needs_review"
    if structural_score < 0.35:
        return "needs_review"
    if structural_score < 0.65:
        return "accepted_with_warnings"
    return "accepted"


def _normalize_candidate(candidate: FieldCandidate) -> FieldCandidate:
    normalizer = _field_normalizer(candidate.field_name)
    value = normalizer(candidate.value) if normalizer is not None else candidate.value
    return replace(candidate, value=value)


def _field_normalizer(field_name: str):
    if field_name == "address":
        return normalize_full_address_string
    if field_name == "town":
        return normalize_town
    if field_name == "state":
        return normalize_state
    if field_name == "property_type":
        return lambda value: str(value).strip().lower() if value not in (None, "", [], {}) else None
    if field_name in {"sale_date", "last_sale_date", "tax_year"}:
        return normalize_date
    if field_name == "lot_size":
        return normalize_lot_size
    if field_name == "sqft":
        return normalize_sqft
    if field_name in STRUCTURAL_FIELDS | TAX_FIELDS | RENT_FIELDS | {"sale_price", "last_sale_price"}:
        return normalize_numeric
    return lambda value: value


def _is_valid_candidate(candidate: FieldCandidate) -> bool:
    value = candidate.value
    if value in (None, "", [], {}):
        return False
    if candidate.field_name == "address" and is_listing_description_as_address(value):
        return False
    if candidate.field_name == "state" and str(value).upper() not in {"NJ"}:
        return False
    return True


def _status_for_single_candidate(field_name: str, candidate: FieldCandidate) -> str:
    if candidate.is_user_override:
        return "confirmed"
    if field_group(field_name) == "rent" and "estimate" in candidate.source.lower():
        return "estimated"
    return "confirmed"


def _material_conflict(field_name: str, left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    if field_name in {"sqft"}:
        return _relative_diff(left, right) > 0.15
    if field_name in {"beds", "baths"}:
        try:
            return abs(float(left) - float(right)) >= 1.0
        except (TypeError, ValueError):
            return str(left) != str(right)
    if field_name in {"town", "state", "address"}:
        return str(left).strip().lower() != str(right).strip().lower()
    if field_name in {"sale_price", "last_sale_price"}:
        return str(left) != str(right)
    if field_name in {"tax_amount", "taxes"}:
        return _relative_diff(left, right) > 0.10
    if field_name in {"sale_date", "last_sale_date", "tax_year"}:
        return str(left) != str(right)
    return False


def _relative_diff(left: Any, right: Any) -> float:
    try:
        left_num = float(left)
        right_num = float(right)
    except (TypeError, ValueError):
        return 1.0 if left != right else 0.0
    baseline = max(abs(left_num), abs(right_num), 1.0)
    return abs(left_num - right_num) / baseline


def _verified_rank(candidate: FieldCandidate) -> int:
    source = candidate.source.lower()
    if candidate.is_user_override:
        return 5
    if any(token in source for token in ["sr1a", "modiv", "public record", "user confirmed", "tax bill"]):
        return 4
    if "attom" in source:
        return 3
    if "listing" in source:
        return 2
    return 1


def _confidence_rank(candidate: FieldCandidate) -> int:
    hint = (candidate.confidence_hint or "").lower()
    if "high" in hint:
        return 3
    if "medium" in hint:
        return 2
    if "low" in hint:
        return 1
    return 0


def _observed_rank(candidate: FieldCandidate) -> int:
    if candidate.observed_at is None:
        return 0
    try:
        return int(datetime.fromisoformat(candidate.observed_at.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _evidence_confidence(evidence: FieldEvidence) -> float:
    if evidence.chosen_status == "confirmed":
        return 0.95
    if evidence.chosen_status == "confirmed_with_conflict":
        return 0.72
    if evidence.chosen_status == "estimated":
        return 0.48
    if evidence.chosen_status == "needs_review":
        return 0.35
    return 0.0


def _to_source_tier(tier: int) -> SourceTier:
    if tier <= 1:
        return SourceTier.TIER_1
    if tier == 2:
        return SourceTier.TIER_2
    return SourceTier.TIER_3


def _from_source_tier(tier: SourceTier) -> int:
    return {
        SourceTier.TIER_1: 1,
        SourceTier.TIER_2: 2,
        SourceTier.TIER_3: 3,
    }[tier]


def _to_verified_status(status: str) -> VerifiedStatus:
    if status == "confirmed":
        return VerifiedStatus.VERIFIED
    if status == "confirmed_with_conflict":
        return VerifiedStatus.CONFLICTED
    if status == "estimated":
        return VerifiedStatus.ESTIMATED
    return VerifiedStatus.UNVERIFIED


def _infer_source_tier(source_name: str) -> int:
    source = source_name.lower()
    if any(token in source for token in ["sr1a", "modiv", "public", "user"]):
        return 1
    if "attom" in source:
        return 2
    return 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

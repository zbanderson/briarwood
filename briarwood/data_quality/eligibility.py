from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.data_quality.provenance import FieldEvidence, PropertyEvidenceProfile


@dataclass(slots=True)
class CompEligibilityResult:
    status: str
    reasons: list[str] = field(default_factory=list)
    fatal_conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    minimum_structural_profile_met: bool = False
    identity_accepted: bool = False


def classify_comp_eligibility(profile: PropertyEvidenceProfile | None) -> CompEligibilityResult:
    if profile is None:
        return CompEligibilityResult(
            status="rejected",
            reasons=["Evidence profile is missing."],
        )

    identity_fields = profile.identity_fields
    structural_fields = profile.structural_fields
    identity_accepted = _identity_accepted(identity_fields)
    minimum_structural_profile_met = _minimum_structural_profile(structural_fields)
    fatal_conflicts = _fatal_conflicts(identity_fields, structural_fields, profile.sale_fields, profile.tax_fields)
    warnings = _warning_conflicts(structural_fields, profile.tax_fields, profile.sale_fields, profile.rent_fields)
    reasons: list[str] = []

    if not identity_accepted:
        reasons.append("Identity is not accepted.")
    if not minimum_structural_profile_met:
        reasons.append("Structural core is incomplete.")
    if fatal_conflicts:
        reasons.append("Fatal provenance conflicts remain unresolved.")

    if not identity_accepted or fatal_conflicts:
        status = "rejected"
    elif not minimum_structural_profile_met:
        status = "market_only"
    elif warnings:
        status = "eligible_with_warnings"
    else:
        status = "eligible"

    return CompEligibilityResult(
        status=status,
        reasons=reasons,
        fatal_conflicts=fatal_conflicts,
        warnings=warnings,
        minimum_structural_profile_met=minimum_structural_profile_met,
        identity_accepted=identity_accepted,
    )


def _identity_accepted(identity_fields: dict[str, FieldEvidence]) -> bool:
    address = identity_fields.get("address")
    state = identity_fields.get("state")
    town = identity_fields.get("town")
    if address is None or address.chosen_status in {"missing", "needs_review", "rejected"}:
        return False
    if state is None or str(state.chosen_value or "").upper() != "NJ":
        return False
    if town is not None and town.chosen_status in {"needs_review", "rejected"}:
        return False
    return True


def _minimum_structural_profile(structural_fields: dict[str, FieldEvidence]) -> bool:
    required = ("beds", "baths", "sqft", "property_type")
    present = 0
    for field_name in required:
        evidence = structural_fields.get(field_name)
        if evidence is None:
            continue
        if evidence.chosen_value not in (None, "", [], {}) and evidence.chosen_status not in {"missing", "rejected"}:
            present += 1
    return present >= 3


def _fatal_conflicts(*groups: dict[str, FieldEvidence]) -> list[str]:
    fields: list[str] = []
    for group in groups:
        for field_name, evidence in group.items():
            if evidence.chosen_status == "needs_review" and field_name in {
                "address",
                "town",
                "state",
                "sqft",
                "last_sale_price",
                "last_sale_date",
                "tax_amount",
            }:
                fields.append(field_name)
    return sorted(set(fields))


def _warning_conflicts(*groups: dict[str, FieldEvidence]) -> list[str]:
    fields: list[str] = []
    for group in groups:
        for field_name, evidence in group.items():
            if evidence.chosen_status == "confirmed_with_conflict":
                fields.append(field_name)
    return sorted(set(fields))

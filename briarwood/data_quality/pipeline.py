from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from briarwood.data_quality.arbitration import build_property_evidence_profile, choose_field_value
from briarwood.data_quality.normalizers import (
    is_listing_description_as_address,
    normalize_address_string,
    normalize_date,
    normalize_lot_size,
    normalize_numeric,
    normalize_sqft,
    normalize_state,
    normalize_town,
)
from briarwood.data_quality.provenance import FieldCandidate, FieldEvidence, PropertyEvidenceProfile
from briarwood.data_quality.source_policy import field_group


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: str
    field: str | None = None
    suggested_fix: str | None = None


@dataclass(slots=True)
class PipelineRecord:
    raw_record: dict[str, Any]
    normalized_record: dict[str, Any]
    canonical_key: str
    issues: list[ValidationIssue] = field(default_factory=list)
    field_evidence: dict[str, FieldEvidence] = field(default_factory=dict)
    evidence_profile: PropertyEvidenceProfile | None = None
    confidence: float = 0.0
    status: str = "needs_review"
    rejection_reason: str | None = None


class DataQualityPipeline:
    STAGES = ("ingest", "normalize", "identity_resolution", "validation", "source_arbitration", "confidence_scoring")

    def __init__(self, *, expected_state: str = "NJ") -> None:
        self.expected_state = expected_state.upper()

    def run(
        self,
        record: dict[str, Any],
        *,
        record_type: str = "sale",
        municipality_context: dict[str, Any] | None = None,
        field_candidates: dict[str, list[FieldCandidate]] | None = None,
    ) -> PipelineRecord:
        ingested = self.ingest(record)
        normalized = self.normalize(ingested)
        canonical_key = self.identity_resolution(normalized, record_type=record_type)
        field_evidence = self.source_arbitration(normalized, field_candidates=field_candidates)
        issues = self.validate(normalized, record_type=record_type, municipality_context=municipality_context, field_evidence=field_evidence)
        evidence_profile = self._build_record_evidence_profile(field_evidence)
        confidence = self.confidence_scoring(field_evidence=field_evidence, issues=issues, evidence_profile=evidence_profile)
        status = self.classify(issues=issues, evidence_profile=evidence_profile)
        rejection_reason = next((issue.message for issue in issues if issue.severity == "error"), None)
        return PipelineRecord(
            raw_record=dict(record),
            normalized_record=normalized,
            canonical_key=canonical_key,
            issues=issues,
            field_evidence=field_evidence,
            evidence_profile=evidence_profile,
            confidence=confidence,
            status=status,
            rejection_reason=rejection_reason,
        )

    def run_many(
        self,
        records: Iterable[dict[str, Any]],
        *,
        record_type: str = "sale",
        municipality_context_by_town: dict[str, dict[str, Any]] | None = None,
    ) -> list[PipelineRecord]:
        results: list[PipelineRecord] = []
        for record in records:
            town = normalize_town(record.get("town")) or "Unknown"
            context = municipality_context_by_town.get(town) if municipality_context_by_town else None
            results.append(self.run(record, record_type=record_type, municipality_context=context))
        return results

    def ingest(self, record: dict[str, Any]) -> dict[str, Any]:
        return dict(record)

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(record)
        normalized["address"] = normalize_address_string(record.get("address"))
        normalized["town"] = normalize_town(record.get("town"))
        normalized["state"] = normalize_state(record.get("state"))
        normalized["zip"] = record.get("zip") or record.get("zip_code")
        for field_name in ("beds", "baths", "sale_price", "list_price", "tax_amount", "taxes", "assessed_value", "market_value", "garage_spaces", "year_built", "stories", "units", "unit_count"):
            normalized[field_name] = normalize_numeric(record.get(field_name))
        normalized["sqft"] = normalize_sqft(record.get("sqft"))
        normalized["lot_size"] = normalize_lot_size(record.get("lot_size"))
        normalized["sale_date"] = normalize_date(record.get("sale_date"))
        normalized["last_sale_date"] = normalize_date(record.get("last_sale_date"))
        normalized["last_sale_price"] = normalize_numeric(record.get("last_sale_price"))
        normalized["estimated_rent"] = normalize_numeric(record.get("estimated_rent") or record.get("estimated_monthly_rent"))
        normalized["listing_description"] = record.get("listing_description") or record.get("source_notes") or record.get("notes")
        return normalized

    def identity_resolution(self, record: dict[str, Any], *, record_type: str) -> str:
        parts = [
            record_type,
            str(record.get("state") or "unknown").lower(),
            str(record.get("town") or "unknown").lower().replace(" ", "-"),
            str(record.get("address") or "unknown").lower().replace(" ", "-"),
            str(record.get("sale_date") or record.get("last_sale_date") or record.get("source_ref") or ""),
        ]
        return "::".join(part.strip("-") for part in parts if part)

    def validate(
        self,
        record: dict[str, Any],
        *,
        record_type: str,
        municipality_context: dict[str, Any] | None,
        field_evidence: dict[str, FieldEvidence],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        issues.extend(validate_address(record))
        issues.extend(validate_state(record, expected_state=self.expected_state))
        issues.extend(validate_required_fields(record, record_type=record_type))
        issues.extend(validate_numeric_ranges(record))
        issues.extend(validate_multi_unit_consistency(record))
        issues.extend(validate_tax_outlier(record, municipality_context))
        issues.extend(validate_field_conflicts(field_evidence))
        return issues

    def source_arbitration(
        self,
        record: dict[str, Any],
        *,
        field_candidates: dict[str, list[FieldCandidate]] | None,
    ) -> dict[str, FieldEvidence]:
        candidate_map = dict(field_candidates or {})
        for field_name, value in record.items():
            if value in (None, "", [], {}):
                continue
            candidate_map.setdefault(field_name, []).append(
                FieldCandidate(
                    field_name=field_name,
                    value=value,
                    source=str(record.get("source_name") or record.get("source_ref") or "record"),
                    source_tier=3,
                    source_record_id=str(record.get("source_ref") or record.get("address") or ""),
                    observed_at=record.get("reviewed_at"),
                    is_user_override=bool(record.get("is_user_override")),
                )
            )
        return {field_name: choose_field_value(field_name, candidates) for field_name, candidates in candidate_map.items()}

    def confidence_scoring(
        self,
        *,
        field_evidence: dict[str, FieldEvidence],
        issues: list[ValidationIssue],
        evidence_profile: PropertyEvidenceProfile,
    ) -> float:
        score = 1.0
        score -= sum(0.20 for issue in issues if issue.severity == "error")
        score -= sum(0.06 for issue in issues if issue.severity == "warning")
        for evidence in field_evidence.values():
            if evidence.chosen_status == "confirmed":
                score += 0.01
            elif evidence.chosen_status == "estimated":
                score -= 0.03
            elif evidence.chosen_status == "needs_review":
                score -= 0.05
        score = (score * 0.5) + (
            (
                evidence_profile.summary_flags.get("structural_data_quality_score", 0.0)
                + evidence_profile.summary_flags.get("tax_data_quality_score", 0.0)
                + evidence_profile.summary_flags.get("sale_data_quality_score", 0.0)
                + evidence_profile.summary_flags.get("rent_data_quality_score", 0.0)
            ) / 4.0
        ) * 0.5
        return max(0.0, min(round(score, 3), 1.0))

    @staticmethod
    def classify(*, issues: list[ValidationIssue], evidence_profile: PropertyEvidenceProfile) -> str:
        comp_status = evidence_profile.summary_flags.get("comp_eligibility_status")
        if comp_status in {"accepted", "accepted_with_warnings", "needs_review", "rejected"}:
            return str(comp_status)
        if any(issue.severity == "error" for issue in issues):
            return "needs_review"
        if issues:
            return "accepted_with_warnings"
        return "accepted"

    def _build_record_evidence_profile(self, field_evidence: dict[str, FieldEvidence]) -> PropertyEvidenceProfile:
        structural = {name: item for name, item in field_evidence.items() if field_group(name) == "structural"}
        tax = {name: item for name, item in field_evidence.items() if field_group(name) == "tax"}
        sale = {name: item for name, item in field_evidence.items() if field_group(name) == "sale"}
        rent = {name: item for name, item in field_evidence.items() if field_group(name) == "rent"}
        identity = {name: item for name, item in field_evidence.items() if field_group(name) == "identity"}
        from briarwood.data_quality.arbitration import _summary_flags  # reuse summary logic
        return PropertyEvidenceProfile(
            structural_fields=structural,
            tax_fields=tax,
            sale_fields=sale,
            rent_fields=rent,
            identity_fields=identity,
            summary_flags=_summary_flags(
                identity_fields=identity,
                structural_fields=structural,
                tax_fields=tax,
                sale_fields=sale,
                rent_fields=rent,
            ),
        )


def validate_address(record: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    address = record.get("address")
    if not address:
        issues.append(ValidationIssue("blank_address", "Address is blank.", "error", field="address", suggested_fix="Provide a real street address."))
        return issues
    if is_listing_description_as_address(address):
        issues.append(ValidationIssue("listing_description_as_address", "Address contains listing-description text.", "error", field="address", suggested_fix="Replace with a normalized street address."))
    return issues


def validate_state(record: dict[str, Any], *, expected_state: str) -> list[ValidationIssue]:
    state = record.get("state")
    if state != expected_state:
        return [ValidationIssue("wrong_state", f"State '{state}' does not match expected state '{expected_state}'.", "error", field="state")]
    return []


def validate_required_fields(record: dict[str, Any], *, record_type: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if any(record.get(field_name) in (None, "") for field_name in ("beds", "baths", "sqft")):
        issues.append(ValidationIssue("missing_structural_fields", "Missing beds, baths, or sqft.", "warning", suggested_fix="Backfill structural core fields."))
    if record_type == "sale":
        if record.get("sale_date") in (None, "") and record.get("last_sale_date") in (None, ""):
            issues.append(ValidationIssue("missing_sale_date", "Sale date is missing.", "error", field="sale_date"))
        if record.get("sale_price") in (None, "") and record.get("last_sale_price") in (None, ""):
            issues.append(ValidationIssue("missing_sale_price", "Sale price is missing.", "error", field="sale_price"))
    return issues


def validate_numeric_ranges(record: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    bounds = {
        "beds": (0, 50),
        "baths": (0, 50),
        "sqft": (100, 200000),
        "lot_size": (0.0, 1000.0),
        "sale_price": (10000, 100000000),
        "last_sale_price": (10000, 100000000),
        "list_price": (10000, 100000000),
        "tax_amount": (1, 1000000),
        "taxes": (1, 1000000),
        "year_built": (1700, 2200),
    }
    for field_name, (minimum, maximum) in bounds.items():
        value = record.get(field_name)
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            issues.append(ValidationIssue("impossible_numeric_values", f"{field_name} is not numeric.", "error", field=field_name))
            continue
        if number < minimum or number > maximum:
            issues.append(ValidationIssue("impossible_numeric_values", f"{field_name}={value} is implausible.", "error", field=field_name))
    return issues


def validate_multi_unit_consistency(record: dict[str, Any]) -> list[ValidationIssue]:
    property_type = str(record.get("property_type") or "").lower()
    unit_count = record.get("units") or record.get("unit_count")
    if any(token in property_type for token in ("duplex", "triplex", "fourplex", "multi")) and unit_count not in (None, ""):
        if float(unit_count) <= 1:
            return [
                ValidationIssue(
                    "multi_unit_inconsistency",
                    "Multi-unit signal conflicts with unit count.",
                    "warning",
                    field="unit_count",
                    suggested_fix="Review unit mix evidence.",
                )
            ]
    return []


def validate_tax_outlier(record: dict[str, Any], municipality_context: dict[str, Any] | None) -> list[ValidationIssue]:
    if not municipality_context:
        return []
    tax_amount = record.get("tax_amount") or record.get("taxes")
    sale_price = record.get("sale_price") or record.get("list_price")
    effective_tax_rate = municipality_context.get("effective_tax_rate")
    if tax_amount in (None, "") or sale_price in (None, "", 0) or effective_tax_rate in (None, "", 0):
        return []
    implied_rate = float(tax_amount) / float(sale_price)
    baseline = float(effective_tax_rate)
    if implied_rate > baseline * 1.8 or implied_rate < baseline * 0.35:
        return [
            ValidationIssue(
                "tax_outlier_vs_municipality",
                "Tax burden is materially out of line with municipal context.",
                "warning",
                field="tax_amount",
                suggested_fix="Review ATTOM tax and NJ tax table sources.",
            )
        ]
    return []


def validate_field_conflicts(field_evidence: dict[str, FieldEvidence]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for field_name, evidence in field_evidence.items():
        if evidence.chosen_status == "confirmed_with_conflict":
            issues.append(ValidationIssue("field_conflict", f"{field_name} has confirmed source conflict.", "warning", field=field_name, suggested_fix=evidence.arbitration_reason))
        elif evidence.chosen_status == "needs_review":
            issues.append(ValidationIssue("field_needs_review", f"{field_name} needs review.", "error", field=field_name, suggested_fix=evidence.arbitration_reason))
    return issues

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EVIDENCE_STATUSES = {
    "confirmed",
    "confirmed_with_conflict",
    "estimated",
    "missing",
    "needs_review",
    "rejected",
}


@dataclass(slots=True)
class FieldCandidate:
    field_name: str
    value: Any
    source: str
    source_tier: int
    source_record_id: str | None = None
    observed_at: str | None = None
    confidence_hint: str | None = None
    is_user_override: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FieldEvidence:
    field_name: str
    chosen_value: Any
    chosen_source: str
    chosen_source_tier: int
    chosen_status: str
    arbitration_reason: str
    updated_at: str
    candidates: list[FieldCandidate] = field(default_factory=list)


@dataclass(slots=True)
class PropertyEvidenceProfile:
    structural_fields: dict[str, FieldEvidence] = field(default_factory=dict)
    tax_fields: dict[str, FieldEvidence] = field(default_factory=dict)
    sale_fields: dict[str, FieldEvidence] = field(default_factory=dict)
    rent_fields: dict[str, FieldEvidence] = field(default_factory=dict)
    identity_fields: dict[str, FieldEvidence] = field(default_factory=dict)
    summary_flags: dict[str, Any] = field(default_factory=dict)

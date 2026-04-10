from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from briarwood.data_quality.pipeline import (
    DataQualityPipeline,
    ValidationIssue,
)
from briarwood.data_quality.normalizers import normalize_address_string, normalize_town


@dataclass(slots=True)
class CleanupAction:
    action: str
    record_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    notes: list[str] = field(default_factory=list)


def delete_junk_records(records: list[dict[str, Any]], *, pipeline: DataQualityPipeline | None = None) -> tuple[list[dict[str, Any]], list[CleanupAction]]:
    quality_pipeline = pipeline or DataQualityPipeline()
    kept: list[dict[str, Any]] = []
    actions: list[CleanupAction] = []
    for record in records:
        result = quality_pipeline.run(record, record_type=_record_type(record))
        if result.status == "rejected":
            actions.append(
                CleanupAction(
                    action="delete_junk_record",
                    record_id=_record_id(record),
                    before=dict(record),
                    after={},
                    notes=[issue.code for issue in result.issues],
                )
            )
            continue
        kept.append(dict(record))
    return kept, actions


def normalize_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    updated = dict(record)
    notes: list[str] = []
    original_address = updated.get("address")
    normalized_address = normalize_address_string(original_address)
    if normalized_address and normalized_address != original_address:
        updated["address"] = normalized_address
        notes.append("normalized_address")
    original_town = updated.get("town")
    normalized_town = normalize_town(original_town)
    if normalized_town != original_town:
        updated["town"] = normalized_town
        notes.append("normalized_town")
    state = str(updated.get("state") or "").strip().upper()
    if state and state != updated.get("state"):
        updated["state"] = state
        notes.append("normalized_state")
    return updated, notes


def cleanup_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[CleanupAction]]:
    cleaned: list[dict[str, Any]] = []
    actions: list[CleanupAction] = []
    for record in records:
        normalized, notes = normalize_record(record)
        cleaned.append(normalized)
        if notes:
            actions.append(
                CleanupAction(
                    action="normalize_record",
                    record_id=_record_id(record),
                    before=dict(record),
                    after=dict(normalized),
                    notes=notes,
                )
            )
    return cleaned, actions


def fix_town_state_labels(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[CleanupAction]]:
    fixed: list[dict[str, Any]] = []
    actions: list[CleanupAction] = []
    for record in records:
        before = dict(record)
        after = dict(record)
        notes: list[str] = []
        town = normalize_town(record.get("town"))
        if town != record.get("town"):
            after["town"] = town
            notes.append("fixed_town_label")
        state = str(record.get("state") or "").strip().upper()
        if state and state != record.get("state"):
            after["state"] = state
            notes.append("fixed_state_label")
        fixed.append(after)
        if notes:
            actions.append(CleanupAction("fix_town_state_labels", _record_id(record), before, after, notes))
    return fixed, actions


def rerun_validation(
    records: list[dict[str, Any]],
    *,
    pipeline: DataQualityPipeline | None = None,
) -> list[tuple[dict[str, Any], str, list[ValidationIssue]]]:
    quality_pipeline = pipeline or DataQualityPipeline()
    output: list[tuple[dict[str, Any], str, list[ValidationIssue]]] = []
    for record in records:
        result = quality_pipeline.run(record, record_type=_record_type(record))
        output.append((dict(record), result.status, list(result.issues)))
    return output


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("source_ref") or record.get("id") or record.get("address") or "unknown-record")


def _record_type(record: dict[str, Any]) -> str:
    return "sale" if record.get("sale_date") or record.get("sale_price") else "listing"

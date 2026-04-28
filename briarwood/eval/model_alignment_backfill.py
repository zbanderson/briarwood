"""Backfill Stage 4 model-alignment rows from saved properties and outcomes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from briarwood.eval.alignment import build_alignment_row, extract_prediction
from briarwood.eval.outcomes import OutcomeRecord, load_outcomes, normalize_address
from briarwood.execution.context import ExecutionContext
from briarwood.modules.comparable_sales_scoped import (
    receive_feedback as receive_comparable_sales_feedback,
)
from briarwood.modules.comparable_sales_scoped import run_comparable_sales
from briarwood.modules.current_value_scoped import (
    receive_feedback as receive_current_value_feedback,
)
from briarwood.modules.current_value_scoped import run_current_value
from briarwood.modules.valuation import receive_feedback as receive_valuation_feedback
from briarwood.modules.valuation import run_valuation


ROOT = Path(__file__).resolve().parents[2]
SAVED_PROPERTIES_DIR = ROOT / "data" / "saved_properties"
DEFAULT_MODULES = ("current_value", "valuation", "comparable_sales")

ModuleRunner = Callable[[ExecutionContext], dict[str, Any]]
FeedbackReceiver = Callable[[str, dict[str, object]], dict[str, object]]

MODULE_RUNNERS: dict[str, ModuleRunner] = {
    "current_value": run_current_value,
    "valuation": run_valuation,
    "comparable_sales": run_comparable_sales,
}
FEEDBACK_RECEIVERS: dict[str, FeedbackReceiver] = {
    "current_value": receive_current_value_feedback,
    "valuation": receive_valuation_feedback,
    "comparable_sales": receive_comparable_sales_feedback,
}


@dataclass(slots=True)
class AlignmentBackfillSkip:
    property_id: str | None
    module_name: str | None
    reason: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AlignmentBackfillResult:
    outcomes_path: str
    dry_run: bool
    outcomes_valid: int = 0
    outcome_errors: list[dict[str, Any]] = field(default_factory=list)
    outcome_duplicate_keys: list[str] = field(default_factory=list)
    properties_matched: int = 0
    module_calls: int = 0
    recorded: int = 0
    skipped: list[AlignmentBackfillSkip] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self, *, include_rows: bool = True) -> dict[str, Any]:
        payload = {
            "outcomes_path": self.outcomes_path,
            "dry_run": self.dry_run,
            "outcomes_valid": self.outcomes_valid,
            "outcome_errors": list(self.outcome_errors),
            "outcome_duplicate_keys": list(self.outcome_duplicate_keys),
            "properties_matched": self.properties_matched,
            "module_calls": self.module_calls,
            "recorded": self.recorded,
            "skipped": [skip.to_dict() for skip in self.skipped],
        }
        if self.error:
            payload["error"] = self.error
        if include_rows:
            payload["rows"] = list(self.rows)
        return payload


def backfill_model_alignment(
    *,
    outcomes_path: Path,
    saved_properties_dir: Path = SAVED_PROPERTIES_DIR,
    modules: list[str] | tuple[str, ...] = DEFAULT_MODULES,
    dry_run: bool = False,
    store: Any | None = None,
    allow_duplicates: bool = False,
    runners: dict[str, ModuleRunner] | None = None,
    receivers: dict[str, FeedbackReceiver] | None = None,
) -> AlignmentBackfillResult:
    """Run priority modules against outcome-matched saved properties.

    The backfill is intentionally record-only. It writes model-alignment rows
    when ``dry_run`` is false, but never changes module weights, thresholds, or
    prompts.
    """

    outcome_result = load_outcomes(outcomes_path)
    result = AlignmentBackfillResult(
        outcomes_path=str(outcomes_path),
        dry_run=dry_run,
        outcomes_valid=outcome_result.valid_count,
        outcome_errors=[err.to_dict() for err in outcome_result.errors],
        outcome_duplicate_keys=list(outcome_result.duplicate_keys),
    )
    if outcome_result.errors:
        result.error = "outcome file has validation errors"
        return result
    if outcome_result.duplicate_keys:
        result.error = "outcome file has duplicate match keys"
        return result

    module_names = [str(module).strip() for module in modules if str(module).strip()]
    invalid_modules = [module for module in module_names if module not in MODULE_RUNNERS]
    if invalid_modules:
        result.error = f"unsupported module(s): {', '.join(invalid_modules)}"
        return result

    active_runners = {**MODULE_RUNNERS, **dict(runners or {})}
    active_receivers = {**FEEDBACK_RECEIVERS, **dict(receivers or {})}
    resolved = _resolve_outcomes(outcome_result.records, saved_properties_dir)
    result.properties_matched = len(resolved)
    for record in outcome_result.records:
        if not any(record is matched_record for matched_record, _ in resolved):
            result.skipped.append(
                AlignmentBackfillSkip(
                    property_id=record.property_id,
                    module_name=None,
                    reason="no_saved_property_match",
                    detail=record.address,
                )
            )

    existing_keys = set()
    if not dry_run and store is not None and not allow_duplicates:
        existing_keys = {
            _alignment_key(row)
            for row in store.model_alignment_rows(limit=None)
        }

    for outcome, resolved_property in resolved:
        try:
            context = load_saved_property_context(
                saved_properties_dir,
                resolved_property.property_id,
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result.skipped.append(
                AlignmentBackfillSkip(
                    property_id=resolved_property.property_id,
                    module_name=None,
                    reason="context_load_failed",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        for module_name in module_names:
            result.module_calls += 1
            payload = active_runners[module_name](context)
            row = _alignment_row_from_payload(
                module_name=module_name,
                property_id=resolved_property.property_id,
                match_method=resolved_property.match_method,
                outcome=outcome,
                payload=payload,
            )
            if row is None:
                result.skipped.append(
                    AlignmentBackfillSkip(
                        property_id=resolved_property.property_id,
                        module_name=module_name,
                        reason="module_prediction_unavailable",
                    )
                )
                continue
            key = _alignment_key(row)
            if key in existing_keys and not allow_duplicates:
                result.skipped.append(
                    AlignmentBackfillSkip(
                        property_id=resolved_property.property_id,
                        module_name=module_name,
                        reason="duplicate_alignment_row",
                    )
                )
                continue
            if dry_run:
                result.rows.append(row)
                result.recorded += 1
                existing_keys.add(key)
                continue

            if store is None:
                from api.store import get_store

                store = get_store()
                if not allow_duplicates:
                    existing_keys = {
                        _alignment_key(existing)
                        for existing in store.model_alignment_rows(limit=None)
                    }
                    if key in existing_keys:
                        result.skipped.append(
                            AlignmentBackfillSkip(
                                property_id=resolved_property.property_id,
                                module_name=module_name,
                                reason="duplicate_alignment_row",
                            )
                        )
                        continue

            signal = {
                "module_payload": payload,
                "outcome": outcome.to_dict(),
                "property_id": resolved_property.property_id,
                "match_method": resolved_property.match_method,
                "store": store,
            }
            recorded = active_receivers[module_name](
                f"stage4-backfill:{resolved_property.property_id}",
                signal,
            )
            if recorded.get("status") != "recorded":
                result.skipped.append(
                    AlignmentBackfillSkip(
                        property_id=resolved_property.property_id,
                        module_name=module_name,
                        reason=str(recorded.get("reason") or "record_failed"),
                    )
                )
                continue
            inserted = dict(recorded.get("row") or {})
            result.rows.append(inserted)
            result.recorded += 1
            existing_keys.add(_alignment_key(inserted))
    return result


@dataclass(frozen=True, slots=True)
class ResolvedProperty:
    property_id: str
    match_method: str


def load_saved_property_context(
    saved_properties_dir: Path,
    property_id: str,
) -> ExecutionContext:
    """Build an execution context from a saved property's inputs/summary pair."""

    property_dir = saved_properties_dir / property_id
    inputs_path = property_dir / "inputs.json"
    if not inputs_path.exists():
        raise ValueError(f"inputs.json not found for {property_id}")
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    summary_path = property_dir / "summary.json"
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists()
        else {}
    )
    return ExecutionContext(
        property_id=property_id,
        property_data=inputs,
        property_summary=summary,
        normalized_context={"property_data": inputs},
    )


def _resolve_outcomes(
    records: list[OutcomeRecord],
    saved_properties_dir: Path,
) -> list[tuple[OutcomeRecord, ResolvedProperty]]:
    addresses = _saved_property_addresses(saved_properties_dir)
    resolved: list[tuple[OutcomeRecord, ResolvedProperty]] = []
    for record in records:
        if (
            record.property_id
            and (saved_properties_dir / record.property_id / "inputs.json").exists()
        ):
            resolved.append((record, ResolvedProperty(record.property_id, "property_id")))
            continue
        if not record.address:
            continue
        candidates = addresses.get(normalize_address(record.address), [])
        if len(candidates) == 1:
            resolved.append((record, ResolvedProperty(candidates[0], "address")))
    return resolved


def _saved_property_addresses(saved_properties_dir: Path) -> dict[str, list[str]]:
    addresses: dict[str, list[str]] = {}
    if not saved_properties_dir.exists():
        return addresses
    for inputs_path in saved_properties_dir.glob("*/inputs.json"):
        property_id = inputs_path.parent.name
        for address in _candidate_saved_addresses(inputs_path):
            key = normalize_address(address)
            if property_id not in addresses.setdefault(key, []):
                addresses[key].append(property_id)
    return addresses


def _candidate_saved_addresses(inputs_path: Path) -> list[str]:
    candidates: list[str] = []
    try:
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return candidates
    facts = inputs.get("facts") if isinstance(inputs.get("facts"), dict) else {}
    for value in (
        facts.get("address"),
        inputs.get("address"),
        inputs.get("property_address"),
    ):
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    summary_path = inputs_path.parent / "summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}
        value = summary.get("address") if isinstance(summary, dict) else None
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    return candidates


def _alignment_row_from_payload(
    *,
    module_name: str,
    property_id: str,
    match_method: str,
    outcome: OutcomeRecord,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    prediction = extract_prediction(module_name, payload)
    if prediction is None:
        return None
    predicted_value, predicted_label, confidence = prediction
    if confidence is None:
        return None
    return build_alignment_row(
        module_name=module_name,
        session_id=f"stage4-backfill:{property_id}",
        module_payload=payload,
        outcome=outcome,
        predicted_value=predicted_value,
        predicted_label=predicted_label,
        confidence=confidence,
        property_id=property_id,
        match_method=match_method,
    )


def _alignment_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("property_id"),
        row.get("module_name"),
        row.get("outcome_type"),
        row.get("outcome_value"),
        row.get("outcome_date"),
        row.get("predicted_value"),
    )


__all__ = [
    "AlignmentBackfillResult",
    "AlignmentBackfillSkip",
    "DEFAULT_MODULES",
    "SAVED_PROPERTIES_DIR",
    "backfill_model_alignment",
    "load_saved_property_context",
]

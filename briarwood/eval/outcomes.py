"""Ground-truth outcome loading for Stage 4 model-accuracy work."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_OUTCOME_TYPES = {"sale_price"}
DEFAULT_JSONL_SOURCE = "manual_json"
DEFAULT_CSV_SOURCE = "manual_csv"


@dataclass(slots=True)
class OutcomeRecord:
    """One ground-truth outcome row.

    ``property_id`` is preferred, but early historical rows may only be
    matchable by address. At least one of ``property_id`` or ``address`` is
    required by the loader.
    """

    property_id: str | None
    address: str | None
    outcome_type: str
    outcome_value: float
    outcome_date: str
    source: str
    source_ref: str | None = None
    confidence: float = 1.0
    notes: str | None = None

    @classmethod
    def from_mapping(
        cls,
        row: dict[str, Any],
        *,
        default_source: str,
    ) -> "OutcomeRecord":
        property_id = _clean_optional_str(row.get("property_id"))
        address = _clean_optional_str(row.get("address"))
        if not property_id and not address:
            raise ValueError("property_id or address is required")

        outcome_type = str(row.get("outcome_type") or "").strip().lower()
        if outcome_type not in SUPPORTED_OUTCOME_TYPES:
            raise ValueError(f"unsupported outcome_type: {outcome_type!r}")

        outcome_value = _parse_positive_float(row.get("outcome_value"), "outcome_value")
        outcome_date = _parse_date(row.get("outcome_date"))
        source = _clean_optional_str(row.get("source")) or default_source
        confidence = _parse_confidence(row.get("confidence", 1.0))

        return cls(
            property_id=property_id,
            address=address,
            outcome_type=outcome_type,
            outcome_value=outcome_value,
            outcome_date=outcome_date,
            source=source,
            source_ref=_clean_optional_str(row.get("source_ref")),
            confidence=confidence,
            notes=_clean_optional_str(row.get("notes")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OutcomeRowError:
    row_number: int
    error: str
    raw: dict[str, Any] | str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OutcomeLoadResult:
    path: str
    records: list[OutcomeRecord] = field(default_factory=list)
    errors: list[OutcomeRowError] = field(default_factory=list)
    duplicate_keys: list[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.records)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def to_summary(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "valid": self.valid_count,
            "errors": [err.to_dict() for err in self.errors],
            "duplicate_keys": list(self.duplicate_keys),
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(slots=True)
class OutcomeMatch:
    outcome: OutcomeRecord
    method: str
    key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "key": self.key,
            "outcome": self.outcome.to_dict(),
        }


class OutcomeIndex:
    """Strict outcome matcher keyed by property id first, address second."""

    def __init__(self, records: Iterable[OutcomeRecord]) -> None:
        self.by_property_id: dict[str, list[OutcomeRecord]] = {}
        self.by_address: dict[str, list[OutcomeRecord]] = {}
        for record in records:
            if record.property_id:
                self.by_property_id.setdefault(_normalize_key(record.property_id), []).append(record)
            if record.address:
                self.by_address.setdefault(normalize_address(record.address), []).append(record)

    def match_mapping(self, row: dict[str, Any]) -> OutcomeMatch | None:
        for property_id in _candidate_property_ids(row):
            key = _normalize_key(property_id)
            records = self.by_property_id.get(key) or []
            if len(records) == 1:
                return OutcomeMatch(records[0], "property_id", key)
            if len(records) > 1:
                return None

        for address in _candidate_addresses(row):
            key = normalize_address(address)
            records = self.by_address.get(key) or []
            if len(records) == 1:
                return OutcomeMatch(records[0], "address", key)
            if len(records) > 1:
                return None
        return None


def load_outcomes(path: Path | str) -> OutcomeLoadResult:
    """Load manual Stage 4 outcome rows from CSV or JSONL."""

    target = Path(path)
    if target.suffix.lower() == ".csv":
        return _load_csv(target)
    if target.suffix.lower() in {".jsonl", ".ndjson"}:
        return _load_jsonl(target)
    raise ValueError(f"unsupported outcome file type: {target.suffix or '<none>'}")


def normalize_address(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_outcome_index(records: Iterable[OutcomeRecord]) -> OutcomeIndex:
    return OutcomeIndex(records)


def _load_jsonl(path: Path) -> OutcomeLoadResult:
    result = OutcomeLoadResult(path=str(path))
    if not path.exists():
        result.errors.append(OutcomeRowError(0, "file not found", str(path)))
        return result
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
                if not isinstance(row, dict):
                    raise ValueError("row must be an object")
                record = OutcomeRecord.from_mapping(row, default_source=DEFAULT_JSONL_SOURCE)
            except (json.JSONDecodeError, ValueError) as exc:
                result.errors.append(OutcomeRowError(line_number, str(exc), text))
                continue
            _append_record(result, record, seen)
    return result


def _load_csv(path: Path) -> OutcomeLoadResult:
    result = OutcomeLoadResult(path=str(path))
    if not path.exists():
        result.errors.append(OutcomeRowError(0, "file not found", str(path)))
        return result
    seen: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                record = OutcomeRecord.from_mapping(dict(row), default_source=DEFAULT_CSV_SOURCE)
            except ValueError as exc:
                result.errors.append(OutcomeRowError(row_number, str(exc), dict(row)))
                continue
            _append_record(result, record, seen)
    return result


def _append_record(
    result: OutcomeLoadResult,
    record: OutcomeRecord,
    seen: set[str],
) -> None:
    key = _dedupe_key(record)
    if key in seen:
        result.duplicate_keys.append(key)
    seen.add(key)
    result.records.append(record)


def _dedupe_key(record: OutcomeRecord) -> str:
    if record.property_id:
        return f"property_id:{_normalize_key(record.property_id)}"
    return f"address:{normalize_address(record.address or '')}"


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower()


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_positive_float(value: Any, field_name: str) -> float:
    if value is None or value == "":
        raise ValueError(f"{field_name} is required")
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _parse_confidence(value: Any) -> float:
    if value is None or value == "":
        return 1.0
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not 0.0 <= parsed <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return parsed


def _parse_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("outcome_date is required")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError("outcome_date must be YYYY-MM-DD") from exc


def _candidate_property_ids(row: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    _collect_named_values(row, {"property_id", "property_slug"}, candidates)
    return list(dict.fromkeys(candidates))


def _candidate_addresses(row: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    _collect_named_values(row, {"address", "full_address", "property_address"}, candidates)
    return list(dict.fromkeys(candidates))


def _collect_named_values(obj: Any, names: set[str], out: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if key_l in names and isinstance(value, (str, int, float)):
                text = str(value).strip()
                if text:
                    out.append(text)
            elif isinstance(value, (dict, list)):
                _collect_named_values(value, names, out)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _collect_named_values(item, names, out)


__all__ = [
    "OutcomeIndex",
    "OutcomeLoadResult",
    "OutcomeMatch",
    "OutcomeRecord",
    "OutcomeRowError",
    "build_outcome_index",
    "load_outcomes",
    "normalize_address",
]

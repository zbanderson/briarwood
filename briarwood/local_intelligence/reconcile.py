from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from briarwood.local_intelligence.models import ReconciliationStatus, TownSignal

_DATE_PROXIMITY_WINDOW = timedelta(days=45)
_TITLE_SIMILARITY_THRESHOLD = 0.82


def reconcile_signals(
    signals: list[TownSignal],
    *,
    existing_signals: list[TownSignal] | None = None,
) -> list[TownSignal]:
    """Merge fresh signals into persisted signal history with deterministic change tracking."""

    now = datetime.now(timezone.utc)
    reconciled: list[TownSignal] = [signal.model_copy(update={"reconciliation_status": None}) for signal in (existing_signals or [])]
    for candidate in sorted(
        signals,
        key=lambda item: (item.source_date or datetime.min.replace(tzinfo=timezone.utc), item.confidence),
        reverse=True,
    ):
        match_index = _find_duplicate_index(candidate, reconciled)
        if match_index is None:
            reconciled.append(
                candidate.model_copy(
                    update={
                        "reconciliation_status": ReconciliationStatus.NEW,
                        "first_seen_at": candidate.first_seen_at or now,
                        "last_seen_at": now,
                        "occurrence_count": max(1, candidate.occurrence_count),
                    }
                )
            )
            continue
        reconciled[match_index] = _merge_signals(reconciled[match_index], candidate, now=now)
    reconciled.sort(key=lambda item: (item.source_date or datetime.min.replace(tzinfo=timezone.utc), item.confidence), reverse=True)
    return reconciled


def _find_duplicate_index(candidate: TownSignal, signals: list[TownSignal]) -> int | None:
    for index, signal in enumerate(signals):
        if _is_duplicate(candidate, signal):
            return index
    return None


def _is_duplicate(left: TownSignal, right: TownSignal) -> bool:
    if left.town.lower() != right.town.lower() or left.state.lower() != right.state.lower():
        return False
    if left.signal_type != right.signal_type:
        return False
    if left.canonical_key and right.canonical_key and left.canonical_key == right.canonical_key:
        return True
    if left.source_document_id == right.source_document_id:
        return True
    if not _dates_are_close(left.source_date, right.source_date):
        return False
    if _location_key(left) and _location_key(left) == _location_key(right):
        return True
    return _title_similarity(left.title, right.title) >= _TITLE_SIMILARITY_THRESHOLD


def _merge_signals(existing: TownSignal, incoming: TownSignal, *, now: datetime) -> TownSignal:
    preferred = existing if existing.confidence >= incoming.confidence else incoming
    facts = _dedupe_text(existing.facts + incoming.facts)
    affected_dimensions = _dedupe_text(existing.affected_dimensions + incoming.affected_dimensions)
    inference = " ".join(_dedupe_text([value for value in (preferred.inference, existing.inference, incoming.inference) if value]))
    evidence_excerpt = max((existing.evidence_excerpt, incoming.evidence_excerpt), key=len)
    metadata = dict(preferred.metadata)
    metadata["related_source_document_ids"] = _dedupe_text(
        [
            existing.source_document_id,
            incoming.source_document_id,
            *[str(item) for item in existing.metadata.get("related_source_document_ids", [])],
            *[str(item) for item in incoming.metadata.get("related_source_document_ids", [])],
        ]
    )
    metadata["source_type_history"] = _dedupe_text(
        [
            existing.source_type.value,
            incoming.source_type.value,
            *[str(item) for item in existing.metadata.get("source_type_history", [])],
            *[str(item) for item in incoming.metadata.get("source_type_history", [])],
        ]
    )
    change_type = _change_type(existing, incoming)
    previous_status = existing.previous_status or (existing.status if change_type == ReconciliationStatus.STATUS_TRANSITION else None)
    return preferred.model_copy(
        update={
            "canonical_key": existing.canonical_key or incoming.canonical_key,
            "facts": facts,
            "affected_dimensions": affected_dimensions,
            "inference": inference or preferred.inference,
            "evidence_excerpt": evidence_excerpt,
            "updated_at": now,
            "first_seen_at": existing.first_seen_at or existing.created_at,
            "last_seen_at": now,
            "last_transition_at": now if change_type == ReconciliationStatus.STATUS_TRANSITION else existing.last_transition_at,
            "occurrence_count": max(1, existing.occurrence_count) + 1,
            "reconciliation_status": change_type,
            "previous_status": previous_status,
            "source_url": incoming.source_url or existing.source_url,
            "metadata": metadata,
        }
    )


def _change_type(existing: TownSignal, incoming: TownSignal) -> ReconciliationStatus:
    if existing.status != incoming.status:
        return ReconciliationStatus.STATUS_TRANSITION
    if _meaningfully_updated(existing, incoming):
        return ReconciliationStatus.UPDATED
    return ReconciliationStatus.UNCHANGED


def _meaningfully_updated(existing: TownSignal, incoming: TownSignal) -> bool:
    return any(
        [
            existing.title != incoming.title,
            existing.evidence_excerpt != incoming.evidence_excerpt,
            existing.inference != incoming.inference,
            _dedupe_text(existing.facts) != _dedupe_text(incoming.facts),
            _dedupe_text(existing.affected_dimensions) != _dedupe_text(incoming.affected_dimensions),
            abs(existing.confidence - incoming.confidence) >= 0.05,
            existing.source_url != incoming.source_url,
        ]
    )


def _dates_are_close(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return True
    return abs(left - right) <= _DATE_PROXIMITY_WINDOW


def _location_key(signal: TownSignal) -> str:
    return " ".join(str(signal.metadata.get("location") or "").lower().split())


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _canonical_text(left), _canonical_text(right)).ratio()


def _canonical_text(value: str) -> str:
    return " ".join(value.lower().split())


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered

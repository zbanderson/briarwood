from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1

from pydantic import ValidationError

from briarwood.local_intelligence.models import SignalStatus, SourceDocument, SourceType, TownSignal, TownSignalDraft


def validate_signal_drafts(
    document: SourceDocument,
    drafts: list[TownSignalDraft],
) -> tuple[list[TownSignal], list[str]]:
    """Convert draft records into canonical TownSignal objects."""

    validated: list[TownSignal] = []
    warnings: list[str] = []
    now = datetime.now(timezone.utc)
    for draft in drafts:
        try:
            validated.append(
                TownSignal(
                    id=_signal_id(document.id, draft.title, draft.evidence_excerpt),
                    town=document.town,
                    state=document.state,
                    signal_type=draft.signal_type,
                    canonical_key=_canonical_key(document.town, document.state, draft.title, draft.signal_type.value, draft.location),
                    title=draft.title.strip(),
                    source_document_id=document.id,
                    source_type=document.source_type,
                    source_date=document.published_at,
                    source_url=document.url,
                    status=draft.status,
                    time_horizon=draft.time_horizon,
                    impact_direction=draft.impact_direction,
                    impact_magnitude=draft.impact_magnitude,
                    confidence=_calibrated_confidence(document, draft),
                    facts=_clean_items(draft.facts),
                    inference=_clean_optional_text(draft.inference),
                    affected_dimensions=_clean_items(draft.affected_dimensions),
                    evidence_excerpt=draft.evidence_excerpt.strip(),
                    created_at=now,
                    updated_at=now,
                    first_seen_at=now,
                    last_seen_at=now,
                    metadata=_draft_metadata(draft),
                )
            )
        except ValidationError as exc:
            warnings.append(f"Discarded malformed TownSignal draft '{draft.title}': {exc.errors()[0]['msg']}")
    return validated, warnings


def _draft_metadata(draft: TownSignalDraft) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if draft.location:
        metadata["location"] = draft.location.strip()
    if draft.units is not None:
        metadata["units"] = draft.units
    if draft.rationale:
        metadata["rationale"] = draft.rationale.strip()
    return metadata


def _signal_id(document_id: str, title: str, evidence_excerpt: str) -> str:
    seed = f"{document_id}|{title.lower()}|{evidence_excerpt[:160].lower()}"
    return f"sig-{sha1(seed.encode('utf-8')).hexdigest()[:12]}"


def _canonical_key(
    town: str,
    state: str,
    title: str,
    signal_type: str,
    location: str | None,
) -> str:
    seed = "|".join(
        [
            town.lower().strip(),
            state.lower().strip(),
            signal_type,
            " ".join((location or title).lower().split()),
        ]
    )
    return f"tsk-{sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def _calibrated_confidence(document: SourceDocument, draft: TownSignalDraft) -> float:
    confidence = float(draft.confidence)
    source_adjustment = {
        SourceType.PLANNING_BOARD_MINUTES: 0.05,
        SourceType.ZONING_BOARD_MINUTES: 0.05,
        SourceType.ORDINANCE: 0.05,
        SourceType.REDEVELOPMENT_PLAN: 0.05,
        SourceType.INFRASTRUCTURE_UPDATE: 0.04,
        SourceType.NEWS: 0.0,
        SourceType.OTHER: -0.08,
    }.get(document.source_type, 0.0)
    confidence += source_adjustment
    if len(draft.facts) >= 2:
        confidence += 0.03
    if not document.url and document.source_type == SourceType.OTHER:
        confidence -= 0.04
    status_cap = {
        SignalStatus.MENTIONED: 0.52,
        SignalStatus.PROPOSED: 0.62,
        SignalStatus.REVIEWED: 0.68,
        SignalStatus.APPROVED: 0.88,
        SignalStatus.FUNDED: 0.9,
        SignalStatus.IN_PROGRESS: 0.9,
        SignalStatus.COMPLETED: 0.92,
        SignalStatus.REJECTED: 0.84,
    }[draft.status]
    return round(max(0.1, min(confidence, status_cap)), 2)


def _clean_items(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    normalized = " ".join(str(value or "").split())
    return normalized or None

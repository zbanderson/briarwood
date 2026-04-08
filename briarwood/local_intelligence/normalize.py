from __future__ import annotations

import re
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

from briarwood.local_intelligence.models import SourceDocument, SourceType


def normalize_source_documents(
    raw_documents: list[SourceDocument | dict[str, Any]] | None,
    *,
    town: str,
    state: str,
) -> list[SourceDocument]:
    """Normalize loose raw document payloads into validated SourceDocument models."""

    normalized: list[SourceDocument] = []
    for raw_document in raw_documents or []:
        if isinstance(raw_document, SourceDocument):
            normalized.append(raw_document)
            continue
        normalized.append(normalize_source_document(raw_document, town=town, state=state))
    return normalized


def normalize_source_document(
    raw_document: dict[str, Any],
    *,
    town: str,
    state: str,
) -> SourceDocument:
    text = str(raw_document.get("cleaned_text") or raw_document.get("raw_text") or raw_document.get("text") or "").strip()
    cleaned_text = _clean_text(text)
    title = str(raw_document.get("title") or raw_document.get("headline") or raw_document.get("document_type") or "Local document").strip()
    document_town = str(raw_document.get("town") or town).strip()
    document_state = str(raw_document.get("state") or state).strip().upper()
    source_type = _normalize_source_type(raw_document.get("source_type") or raw_document.get("document_type"))
    published_at = _parse_datetime(raw_document.get("published_at") or raw_document.get("meeting_date") or raw_document.get("date"))
    retrieved_at = _parse_datetime(raw_document.get("retrieved_at")) or datetime.now(timezone.utc)

    metadata = dict(raw_document.get("metadata") or {})
    for key in ("meeting_date", "date", "document_type"):
        if key in raw_document and key not in metadata:
            metadata[key] = raw_document[key]

    doc_id = str(raw_document.get("id") or _document_id(document_town, document_state, title, published_at, cleaned_text))
    return SourceDocument(
        id=doc_id,
        town=document_town,
        state=document_state,
        source_type=source_type,
        title=title,
        url=_optional_text(raw_document.get("url") or raw_document.get("source_url")),
        published_at=published_at,
        retrieved_at=retrieved_at,
        raw_text=text,
        cleaned_text=cleaned_text,
        metadata=metadata,
    )


def _normalize_source_type(value: object) -> SourceType:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "planning_board_minutes": SourceType.PLANNING_BOARD_MINUTES,
        "planning_minutes": SourceType.PLANNING_BOARD_MINUTES,
        "zoning_board_minutes": SourceType.ZONING_BOARD_MINUTES,
        "zoning_minutes": SourceType.ZONING_BOARD_MINUTES,
        "ordinance": SourceType.ORDINANCE,
        "redevelopment_plan": SourceType.REDEVELOPMENT_PLAN,
        "infrastructure_update": SourceType.INFRASTRUCTURE_UPDATE,
        "news": SourceType.NEWS,
    }
    return mapping.get(raw, SourceType.OTHER)


def _document_id(
    town: str,
    state: str,
    title: str,
    published_at: datetime | None,
    cleaned_text: str,
) -> str:
    seed = "|".join(
        [
            town.lower(),
            state.lower(),
            title.lower(),
            published_at.isoformat() if published_at else "",
            cleaned_text[:240].lower(),
        ]
    )
    return f"doc-{sha1(seed.encode('utf-8')).hexdigest()[:12]}"


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{text}T00:00:00")
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from briarwood.local_intelligence.classification import bucket_town_signals, rank_town_signals
from briarwood.local_intelligence.models import TownSignal
from briarwood.local_intelligence.storage import JsonLocalSignalStore, _slugify

_TIME_LIKE_RE = re.compile(r"^\d{1,2}:\d{2}(?:\s*[ap](?:\.?m\.?)?)?$", re.IGNORECASE)
_ADDRESS_HINT_RE = re.compile(
    r"\b("
    r"st|street|ave|avenue|rd|road|dr|drive|blvd|boulevard|ln|lane|ct|court|"
    r"pl|place|way|terrace|ter|pkwy|parkway|highway|hwy|route|rte|main|broadway"
    r")\b",
    re.IGNORECASE,
)


def build_town_signal_items(
    town: str | None,
    state: str | None,
    *,
    geocode: Callable[[str], tuple[float | None, float | None]] | None = None,
    max_per_bucket: int = 3,
    signal_store: JsonLocalSignalStore | None = None,
    documents_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Serialize persisted town signals into UI-ready drill-in items."""

    if not town or not state:
        return []

    store = signal_store or JsonLocalSignalStore()
    try:
        signals = store.load_town_signals(town=town, state=state)
    except Exception:
        return []
    if not signals:
        return []

    documents_by_id = _load_source_documents(
        town=town,
        state=state,
        documents_root=documents_root,
    )
    buckets = bucket_town_signals(rank_town_signals(signals))
    items: list[dict[str, Any]] = []
    for bucket_name in ("bullish", "bearish", "watch"):
        for signal in buckets.get(bucket_name, [])[:max_per_bucket]:
            items.append(
                _serialize_signal_item(
                    signal,
                    bucket=bucket_name,
                    town=town,
                    state=state,
                    documents_by_id=documents_by_id,
                    geocode=geocode,
                )
            )
    return items


def _serialize_signal_item(
    signal: TownSignal,
    *,
    bucket: str,
    town: str,
    state: str,
    documents_by_id: dict[str, dict[str, Any]],
    geocode: Callable[[str], tuple[float | None, float | None]] | None,
) -> dict[str, Any]:
    location_label = _normalized_location(signal)
    development_lat: float | None = None
    development_lng: float | None = None
    if geocode is not None and location_label and _looks_like_project_address(location_label):
        query = f"{location_label}, {town}, {state}"
        try:
            development_lat, development_lng = geocode(query)
        except Exception:
            development_lat, development_lng = None, None

    source_doc = documents_by_id.get(signal.source_document_id, {})
    source_url = signal.source_url or _clean_optional_str(source_doc.get("url"))
    source_title = (
        _clean_optional_str(source_doc.get("title"))
        or signal.title
    )
    source_date = (
        signal.source_date.isoformat() if signal.source_date is not None else _best_document_date(source_doc)
    )

    return {
        "id": signal.id,
        "bucket": bucket,
        "title": signal.title,
        "status": signal.status.value,
        "display_line": _display_line(signal),
        "project_summary": _project_summary(signal, bucket=bucket, location_label=location_label, source_title=source_title),
        "signal_type": signal.signal_type.value,
        "location_label": location_label,
        "development_lat": development_lat,
        "development_lng": development_lng,
        "confidence": float(signal.confidence),
        "facts": list(signal.facts or []),
        "inference": signal.inference,
        "evidence_excerpt": signal.evidence_excerpt,
        "source_document_id": signal.source_document_id,
        "source_title": source_title,
        "source_type": signal.source_type.value,
        "source_url": source_url,
        "source_date": source_date,
    }


def _load_source_documents(
    *,
    town: str,
    state: str,
    documents_root: Path | None,
) -> dict[str, dict[str, Any]]:
    root = documents_root or Path(__file__).resolve().parents[2] / "data" / "local_intelligence" / "documents"
    path = root / f"{_slugify(f'{town}-{state}')}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    documents = payload.get("documents") if isinstance(payload, dict) else payload
    if not isinstance(documents, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in documents:
        if not isinstance(row, dict):
            continue
        doc_id = _clean_optional_str(row.get("id"))
        if doc_id:
            out[doc_id] = row
    return out


def _display_line(signal: TownSignal) -> str:
    status = signal.status.value.replace("_", " ")
    return f"{signal.title} ({status})"


def _project_summary(
    signal: TownSignal,
    *,
    bucket: str,
    location_label: str | None,
    source_title: str | None,
) -> str:
    status = signal.status.value.replace("_", " ")
    signal_type = signal.signal_type.value.replace("_", " ")
    title = signal.title.strip()
    units = signal.metadata.get("units")
    affected = ", ".join(signal.affected_dimensions[:2]) if signal.affected_dimensions else None

    subject = title
    if _looks_like_generated_title(title) and source_title and source_title != title:
        subject = source_title

    lead_bits = [status.capitalize(), signal_type]
    if subject:
        lead_bits.append(f"item tied to {subject}")
    if location_label and location_label.lower() not in subject.lower():
        lead_bits.append(f"at {location_label}")
    lead = " ".join(bit for bit in lead_bits if bit).strip()
    if isinstance(units, int) and units > 0:
        lead += f", covering about {units} unit{'s' if units != 1 else ''}"
    lead += "."

    impact = _impact_sentence(signal, bucket=bucket, affected=affected)
    return f"{lead} {impact}".strip()


def _impact_sentence(signal: TownSignal, *, bucket: str, affected: str | None) -> str:
    horizon = signal.time_horizon.value.replace("_", " ")
    direction = signal.impact_direction.value
    if bucket == "bullish":
        clause = "Briarwood treats it as a constructive local catalyst"
    elif bucket == "bearish":
        clause = "Briarwood treats it as a local risk that could weigh on the setup"
    else:
        clause = "Briarwood treats it as a watch item rather than a confirmed catalyst"
    if affected:
        return f"{clause} over the {horizon}, with likely effects on {affected}."
    if direction == "positive":
        return f"{clause} over the {horizon}."
    if direction == "negative":
        return f"{clause} over the {horizon}."
    return f"{clause} over the {horizon}, with mixed or still-developing effects."


def _normalized_location(signal: TownSignal) -> str | None:
    raw = signal.metadata.get("location")
    if isinstance(raw, str):
        cleaned = " ".join(raw.split()).strip(" ,.")
        return cleaned or None
    return None


def _looks_like_project_address(value: str) -> bool:
    cleaned = " ".join(value.split()).strip(" ,.")
    if not cleaned:
        return False
    if _TIME_LIKE_RE.match(cleaned):
        return False
    if not any(char.isdigit() for char in cleaned):
        return False
    if not re.search(r"[A-Za-z]{2,}", cleaned):
        return False
    return bool(_ADDRESS_HINT_RE.search(cleaned))


def _looks_like_generated_title(value: str) -> bool:
    cleaned = " ".join(value.split())
    return len(cleaned) > 56 or cleaned.lower().startswith("the borough of")


def _best_document_date(document: dict[str, Any]) -> str | None:
    for key in ("published_at", "retrieved_at"):
        value = _clean_optional_str(document.get(key))
        if value:
            return value
    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        for key in ("published_at", "retrieved_at"):
            value = _clean_optional_str(metadata.get(key))
            if value:
                return value
    return None


def _clean_optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


__all__ = ["build_town_signal_items"]

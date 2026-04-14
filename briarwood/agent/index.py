"""Listing index over data/saved_properties/.

Scans each saved property, extracts facts + summary, computes distance
features from hand-curated town anchors, and persists a single
data/listing_index/index.json. Kept deliberately small and inspectable —
no vector store, no embeddings.

Rebuild by calling build_index(). Search is a pure filter over the
persisted records.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from briarwood.agent.anchors import TownAnchors, anchors_for
from briarwood.agent.tools import SAVED_PROPERTIES_DIR

INDEX_PATH = Path("data/listing_index/index.json")
BLOCK_MILES = 0.06  # NJ shore town residential block ≈ 0.06 mi


@dataclass
class IndexedProperty:
    property_id: str
    address: str | None
    town: str | None
    state: str | None
    latitude: float | None
    longitude: float | None
    beds: int | None
    baths: float | None
    sqft: int | None
    lot_size_acres: float | None
    year_built: int | None
    ask_price: float | None
    confidence: float | None
    distance_to_beach_miles: float | None = None
    distance_to_downtown_miles: float | None = None
    distance_to_train_miles: float | None = None
    blocks_to_beach: float | None = None


@dataclass
class Index:
    properties: list[IndexedProperty] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"properties": [asdict(p) for p in self.properties]}


# ---------- build ----------


def _haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 3958.7613
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _distance(subject: tuple[float, float] | None, anchor: tuple[float, float] | None) -> float | None:
    if subject is None or anchor is None:
        return None
    return round(_haversine_miles(subject, anchor), 3)


def _load_facts(property_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    pdir = SAVED_PROPERTIES_DIR / property_id
    inputs_path = pdir / "inputs.json"
    summary_path = pdir / "summary.json"
    if not inputs_path.exists():
        return None
    inputs = json.loads(inputs_path.read_text())
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    return inputs, summary


def _record_for(property_id: str) -> IndexedProperty | None:
    loaded = _load_facts(property_id)
    if loaded is None:
        return None
    inputs, summary = loaded
    facts = inputs.get("facts", {}) or {}

    lat = facts.get("latitude")
    lon = facts.get("longitude")
    town = facts.get("town")
    state = facts.get("state")
    anchors = anchors_for(town, state)

    subject = (lat, lon) if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) else None

    beach_dist = _distance(subject, anchors.beach) if anchors else None
    downtown_dist = _distance(subject, anchors.downtown) if anchors else None
    train_dist = _distance(subject, anchors.train) if anchors else None
    blocks_to_beach = round(beach_dist / BLOCK_MILES, 1) if beach_dist is not None else None

    return IndexedProperty(
        property_id=property_id,
        address=facts.get("address") or summary.get("address"),
        town=town,
        state=state,
        latitude=lat,
        longitude=lon,
        beds=facts.get("beds"),
        baths=facts.get("baths"),
        sqft=facts.get("sqft"),
        lot_size_acres=facts.get("lot_size"),
        year_built=facts.get("year_built"),
        ask_price=facts.get("purchase_price") or summary.get("ask_price"),
        confidence=summary.get("confidence"),
        distance_to_beach_miles=beach_dist,
        distance_to_downtown_miles=downtown_dist,
        distance_to_train_miles=train_dist,
        blocks_to_beach=blocks_to_beach,
    )


def build_index(property_ids: Iterable[str] | None = None) -> Index:
    ids = (
        list(property_ids)
        if property_ids is not None
        else sorted(p.name for p in SAVED_PROPERTIES_DIR.iterdir() if p.is_dir())
    )
    records = [r for pid in ids if (r := _record_for(pid)) is not None]
    idx = Index(properties=records)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(idx.to_dict(), indent=2))
    return idx


def load_index() -> Index:
    if not INDEX_PATH.exists():
        return build_index()
    data = json.loads(INDEX_PATH.read_text())
    return Index(properties=[IndexedProperty(**p) for p in data.get("properties", [])])


# ---------- search ----------


FILTER_KEYS = {
    "beds_min",
    "beds_max",
    "beds",
    "baths_min",
    "max_price",
    "min_price",
    "max_distance_to_beach_miles",
    "within_blocks_of_beach",
    "max_distance_to_downtown_miles",
    "max_distance_to_train_miles",
    "town",
    "state",
    "min_confidence",
    "year_built_min",
    "year_built_max",
    "lot_size_acres_min",
}


def _matches(p: IndexedProperty, filters: dict[str, Any]) -> bool:
    def ge(value: Any, threshold: Any) -> bool:
        return isinstance(value, (int, float)) and value >= threshold

    def le(value: Any, threshold: Any) -> bool:
        return isinstance(value, (int, float)) and value <= threshold

    if "beds" in filters and p.beds != filters["beds"]:
        return False
    if "beds_min" in filters and not ge(p.beds, filters["beds_min"]):
        return False
    if "beds_max" in filters and not le(p.beds, filters["beds_max"]):
        return False
    if "baths_min" in filters and not ge(p.baths, filters["baths_min"]):
        return False
    if "max_price" in filters and not le(p.ask_price, filters["max_price"]):
        return False
    if "min_price" in filters and not ge(p.ask_price, filters["min_price"]):
        return False
    if "max_distance_to_beach_miles" in filters and not le(
        p.distance_to_beach_miles, filters["max_distance_to_beach_miles"]
    ):
        return False
    if "within_blocks_of_beach" in filters and not le(
        p.blocks_to_beach, filters["within_blocks_of_beach"]
    ):
        return False
    if "max_distance_to_downtown_miles" in filters and not le(
        p.distance_to_downtown_miles, filters["max_distance_to_downtown_miles"]
    ):
        return False
    if "max_distance_to_train_miles" in filters and not le(
        p.distance_to_train_miles, filters["max_distance_to_train_miles"]
    ):
        return False
    if "town" in filters and (p.town or "").strip().lower() != filters["town"].strip().lower():
        return False
    if "state" in filters and (p.state or "").strip().lower() != filters["state"].strip().lower():
        return False
    if "min_confidence" in filters and not ge(p.confidence, filters["min_confidence"]):
        return False
    if "year_built_min" in filters and not ge(p.year_built, filters["year_built_min"]):
        return False
    if "year_built_max" in filters and not le(p.year_built, filters["year_built_max"]):
        return False
    if "lot_size_acres_min" in filters and not ge(p.lot_size_acres, filters["lot_size_acres_min"]):
        return False
    return True


def search(filters: dict[str, Any], *, idx: Index | None = None) -> list[IndexedProperty]:
    unknown = set(filters.keys()) - FILTER_KEYS
    if unknown:
        raise ValueError(f"unknown filter keys: {sorted(unknown)}")
    if idx is None:
        idx = load_index()
    return [p for p in idx.properties if _matches(p, filters)]

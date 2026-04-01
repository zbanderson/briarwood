from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore
from briarwood.dash_app.data import register_manual_analysis


REQUIRED_PROPERTY_FIELDS = [
    "address",
    "town",
    "state",
    "purchase_price",
    "beds",
    "baths",
    "sqft",
]

REQUIRED_COMP_FIELDS = [
    "address",
    "sale_price",
    "sale_date",
    "sqft",
    "beds",
    "baths",
    "lot_size",
    "year_built",
    "verification_status",
    "lat",
    "lon",
]


@dataclass(slots=True)
class EntryPrepContract:
    required_property_fields: list[str] = field(default_factory=lambda: list(REQUIRED_PROPERTY_FIELDS))
    required_comp_fields: list[str] = field(default_factory=lambda: list(REQUIRED_COMP_FIELDS))
    property_save_behavior: str = (
        "Create a saved property JSON, run the existing analysis pipeline, persist summary/report/tear sheet, and surface it in saved properties."
    )
    comp_save_behavior: str = (
        "Validate the comp against ComparableSale, append or upsert into the JSON comp store, and make it immediately available to the comparable-sales module."
    )
    app_surface_behavior: str = (
        "Saved properties should appear in the property selector and saved-properties table. Saved comps should appear in the shared comp dataset used by analysis."
    )


def validate_required_fields(payload: dict[str, object], required_fields: list[str]) -> list[str]:
    return [field for field in required_fields if payload.get(field) in (None, "", [])]


def save_property_entry(subject: dict[str, object], comps: list[dict[str, object]]) -> tuple[str, Path]:
    missing = validate_required_fields(subject, REQUIRED_PROPERTY_FIELDS)
    if missing:
        raise ValueError(f"Property entry is missing required fields: {', '.join(missing)}")
    return register_manual_analysis(subject, comps)


def save_comp_entry(payload: dict[str, object], *, store_path: str | Path) -> ComparableSale:
    missing = validate_required_fields(payload, REQUIRED_COMP_FIELDS)
    if missing:
        raise ValueError(f"Comp entry is missing required fields: {', '.join(missing)}")
    comp = ComparableSale.model_validate(payload)
    store = JsonComparableSalesStore(store_path)
    return store.upsert(comp, match_on="source_ref")

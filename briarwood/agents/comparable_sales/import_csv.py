from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ActiveListingRecord, ComparableSale
from briarwood.agents.comparable_sales.store import JsonActiveListingStore, JsonComparableSalesStore


REQUIRED_FIELDS = [
    "address",
    "sqft",
    "beds",
    "baths",
    "lot_size",
    "year_built",
    "verification_status",
]

FIELD_ALIASES = {
    "address": ["address"],
    "town": ["town"],
    "state": ["state"],
    "list_price": ["list_price", "list price"],
    "sale_price": ["sale_price", "sale price"],
    "sale_date": ["sale_date", "sale date"],
    "sqft": ["sqft"],
    "beds": ["beds"],
    "baths": ["baths"],
    "lot_size": ["lot_size", "lot size"],
    "year_built": ["year_built", "year built"],
    "verification_status": ["verification_status"],
    "property_type": ["property_type", "property type"],
    "days_on_market": ["days_on_market", "days on market"],
    "source_ref": ["source_ref"],
    "source_name": ["source_name"],
    "condition_profile": ["condition_profile"],
    "capex_lane": ["capex_lane"],
    "garage_spaces": ["garage_spaces"],
    "architectural_style": ["architectural_style"],
    "notes": ["notes"],
    "lat": ["lat", "latitude"],
    "lon": ["lon", "lng", "longitude"],
    "status": ["status"],
}


def load_comp_rows(
    path: str | Path,
    *,
    town: str,
    state: str,
    source_name: str,
    as_of: str | None = None,
) -> list[ComparableSale]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Comp CSV is missing a header row.")
        normalized_fieldnames = {_normalize_column_name(name) for name in reader.fieldnames if name}
        missing_columns = [
            field
            for field in REQUIRED_FIELDS
            if not any(alias in normalized_fieldnames for alias in FIELD_ALIASES[field])
        ]
        if missing_columns:
            raise ValueError(f"Comp CSV is missing required columns: {', '.join(missing_columns)}")

        rows: list[ComparableSale] = []
        validation_errors: list[str] = []
        for index, raw in enumerate(reader, start=2):
            row = {key: (value.strip() if isinstance(value, str) else value) for key, value in raw.items()}
            status = _normalize_status(_field_value(row, "status"))
            if status == "for_sale":
                continue
            try:
                sale_price = _parse_float(_field_value(row, "sale_price"))
                sale_date = _normalize_date(_field_value(row, "sale_date"))
                if sale_price is None or sale_date is None:
                    raise ValueError("sold comp rows require sale_price and sale_date")
                rows.append(
                    ComparableSale.model_validate(
                        {
                            "address": _field_value(row, "address"),
                            "town": _field_value(row, "town") or town,
                            "state": (_field_value(row, "state") or state).upper(),
                            "sale_price": sale_price,
                            "sale_date": sale_date,
                            "sqft": _parse_int(_field_value(row, "sqft")),
                            "beds": _parse_int(_field_value(row, "beds")),
                            "baths": _parse_float(_field_value(row, "baths")),
                            "lot_size": _parse_float(_field_value(row, "lot_size")),
                            "year_built": _parse_int(_field_value(row, "year_built")),
                            "verification_status": _normalize_verification_status(_field_value(row, "verification_status")),
                            "latitude": _parse_float(_field_value(row, "lat")),
                            "longitude": _parse_float(_field_value(row, "lon")),
                            "property_type": _field_value(row, "property_type") or None,
                            "days_on_market": _parse_int(_field_value(row, "days_on_market")),
                            "source_name": _field_value(row, "source_name") or source_name,
                            "source_quality": "imported",
                            "source_ref": _field_value(row, "source_ref") or f"{town.upper()}-CSV-{index}",
                            "source_notes": _field_value(row, "notes"),
                            "condition_profile": _normalize_condition_profile(_field_value(row, "condition_profile")),
                            "capex_lane": _normalize_capex_lane(_field_value(row, "capex_lane")),
                            "garage_spaces": _parse_int(_field_value(row, "garage_spaces")),
                            "architectural_style": _field_value(row, "architectural_style") or None,
                            "reviewed_at": as_of,
                            "comp_status": _comp_status_for_verification(_normalize_verification_status(_field_value(row, "verification_status"))),
                            "address_verification_status": "verified",
                            "sale_verification_status": _legacy_sale_verification_status(_normalize_verification_status(_field_value(row, "verification_status"))),
                            "verification_source_type": _verification_source_type(_normalize_verification_status(_field_value(row, "verification_status"))),
                            "verification_source_name": _field_value(row, "source_name") or source_name,
                            "verification_source_id": _field_value(row, "source_ref") or f"{town.upper()}-CSV-{index}",
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001
                validation_errors.append(f"Row {index}: {exc}")
        if validation_errors:
            raise ValueError("Comp CSV validation failed:\n" + "\n".join(validation_errors[:20]))
        return rows


def load_active_listing_rows(
    path: str | Path,
    *,
    town: str,
    state: str,
    source_name: str,
) -> list[ActiveListingRecord]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Comp CSV is missing a header row.")
        rows: list[ActiveListingRecord] = []
        validation_errors: list[str] = []
        for index, raw in enumerate(reader, start=2):
            row = {key: (value.strip() if isinstance(value, str) else value) for key, value in raw.items()}
            status = _normalize_status(_field_value(row, "status"))
            if status not in {"for_sale", "pending", "coming_soon", "active"}:
                continue
            try:
                list_price = _parse_float(_field_value(row, "list_price"))
                if list_price is None:
                    raise ValueError("active listing rows require list_price")
                rows.append(
                    ActiveListingRecord.model_validate(
                        {
                            "address": _field_value(row, "address"),
                            "town": _field_value(row, "town") or town,
                            "state": (_field_value(row, "state") or state).upper(),
                            "list_price": list_price,
                            "listing_status": status,
                            "property_type": _field_value(row, "property_type") or None,
                            "architectural_style": _field_value(row, "architectural_style") or None,
                            "condition_profile": _normalize_condition_profile(_field_value(row, "condition_profile")),
                            "capex_lane": _normalize_capex_lane(_field_value(row, "capex_lane")),
                            "source_name": _field_value(row, "source_name") or source_name,
                            "source_ref": _field_value(row, "source_ref") or f"{town.upper()}-ACTIVE-{index}",
                            "source_notes": _field_value(row, "notes"),
                            "days_on_market": _parse_int(_field_value(row, "days_on_market")),
                            "beds": _parse_int(_field_value(row, "beds")),
                            "baths": _parse_float(_field_value(row, "baths")),
                            "sqft": _parse_int(_field_value(row, "sqft")),
                            "lot_size": _parse_float(_field_value(row, "lot_size")),
                            "year_built": _parse_int(_field_value(row, "year_built")),
                            "garage_spaces": _parse_int(_field_value(row, "garage_spaces")),
                            "latitude": _parse_float(_field_value(row, "lat")),
                            "longitude": _parse_float(_field_value(row, "lon")),
                            "notes": _field_value(row, "notes"),
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001
                validation_errors.append(f"Row {index}: {exc}")
        if validation_errors:
            raise ValueError("Active listing CSV validation failed:\n" + "\n".join(validation_errors[:20]))
        return rows


def append_rows(
    *,
    comps_path: str | Path,
    imported_rows: list[ComparableSale],
    dataset_name: str | None = None,
    as_of: str | None = None,
) -> int:
    store = JsonComparableSalesStore(comps_path)
    dataset = store.load()
    for row in imported_rows:
        dataset.sales.append(row)
    if dataset_name:
        dataset.metadata["dataset_name"] = dataset_name
    if as_of:
        dataset.metadata["as_of"] = as_of
    store.save(dataset)
    return len(imported_rows)


def append_active_rows(
    *,
    active_path: str | Path,
    imported_rows: list[ActiveListingRecord],
    dataset_name: str | None = None,
    as_of: str | None = None,
) -> int:
    store = JsonActiveListingStore(active_path)
    dataset = store.load()
    for row in imported_rows:
        dataset.listings.append(row)
    if dataset_name:
        dataset.metadata["dataset_name"] = dataset_name
    if as_of:
        dataset.metadata["as_of"] = as_of
    store.save(dataset)
    return len(imported_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a strict comparable-sales CSV into Briarwood's JSON dataset.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--comps", default="data/comps/sales_comps.json")
    parser.add_argument("--active-listings", default="data/comps/active_listings.json")
    parser.add_argument("--town", required=True)
    parser.add_argument("--state", default="NJ")
    parser.add_argument("--source-name", default="manual comp import")
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument("--as-of", default=datetime.today().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    rows = load_comp_rows(
        args.input_csv,
        town=args.town,
        state=args.state,
        source_name=args.source_name,
        as_of=args.as_of,
    )
    count = append_rows(
        comps_path=args.comps,
        imported_rows=rows,
        dataset_name=args.dataset_name,
        as_of=args.as_of,
    )
    active_rows = load_active_listing_rows(
        args.input_csv,
        town=args.town,
        state=args.state,
        source_name=args.source_name,
    )
    active_count = append_active_rows(
        active_path=args.active_listings,
        imported_rows=active_rows,
        dataset_name=args.dataset_name,
        as_of=args.as_of,
    )
    print(f"Imported {count} sold comps into {args.comps}")
    print(f"Imported {active_count} active listings into {args.active_listings}")
    return 0


def _parse_float(value: object) -> float | None:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    return float(text)


def _parse_int(value: object) -> int | None:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return None
    return int(float(str(value).strip()))


def _normalize_date(value: object) -> str | None:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized sale_date format: {text}")


def _field_value(row: dict[str, object], logical_name: str) -> object:
    aliases = FIELD_ALIASES[logical_name]
    for key, value in row.items():
        if key is None:
            continue
        normalized = _normalize_column_name(key)
        if normalized in aliases:
            return value
    return None


def _normalize_column_name(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_status(value: object) -> str | None:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return None
    text = str(value).strip().lower().replace(" ", "_")
    if text in {"for_sale", "active", "coming_soon", "pending"}:
        return "for_sale"
    if text in {"sold", "closed"}:
        return "sold"
    return text


def _normalize_verification_status(value: object) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in {"verified", "manual_verified"}:
        return "manual"
    if text in {"broker_verified", "broker"}:
        return "broker_verified"
    if text in {"public_record", "public_record_verified"}:
        return "public_record"
    if text in {"estimated"}:
        return "estimated"
    return "manual"


def _normalize_condition_profile(value: object) -> str | None:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return None
    text = str(value).strip().lower().replace(" ", "_")
    mapping = {
        "new_construction": "renovated",
        "renovated": "renovated",
        "updated": "updated",
        "maintained": "maintained",
        "dated": "dated",
        "needs_work": "needs_work",
    }
    return mapping.get(text)


def _normalize_capex_lane(value: object) -> str | None:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return None
    text = str(value).strip().lower().replace(" ", "_")
    if text in {"light", "moderate", "heavy"}:
        return text
    if text in {"0", "1", "2", "3"}:
        return {"0": "light", "1": "light", "2": "moderate", "3": "heavy"}[text]
    if text in {"4", "5", "6", "7"}:
        return "moderate"
    if text in {"8", "9", "10"}:
        return "heavy"
    return None


def _legacy_sale_verification_status(status: str) -> str:
    return {
        "manual": "seeded",
        "broker_verified": "mls_verified",
        "public_record": "public_record_verified",
        "estimated": "seeded",
    }[status]


def _verification_source_type(status: str) -> str:
    return {
        "manual": "manual_review",
        "broker_verified": "broker_review",
        "public_record": "public_record",
        "estimated": "manual_review",
    }[status]


def _comp_status_for_verification(status: str) -> str:
    return {
        "manual": "seeded",
        "broker_verified": "approved",
        "public_record": "reviewed",
        "estimated": "seeded",
    }[status]


if __name__ == "__main__":
    raise SystemExit(main())

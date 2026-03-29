from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ADDRESS_ALIASES = [
    "address",
    "property_address",
    "site_address",
    "property location",
    "property_location",
]
TOWN_ALIASES = ["town", "municipality", "city", "tax_municipality"]
STATE_ALIASES = ["state", "state_abbr"]
SALE_PRICE_ALIASES = ["sale_price", "consideration", "deed_price", "price"]
SALE_DATE_ALIASES = ["sale_date", "recorded_date", "deed_date", "transfer_date", "recording_date"]
SOURCE_ID_ALIASES = ["source_id", "record_id", "instrument", "instrument_number", "book_page", "deed_book_page"]


@dataclass(slots=True)
class PublicRecordSale:
    address: str
    town: str
    state: str
    sale_price: float | None
    sale_date: str | None
    source_id: str | None
    source_name: str


def load_public_record_rows(path: str | Path, *, default_source_name: str) -> list[PublicRecordSale]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows: list[PublicRecordSale] = []
        for raw in reader:
            if not isinstance(raw, dict):
                continue
            address = _first_value(raw, ADDRESS_ALIASES)
            town = _first_value(raw, TOWN_ALIASES)
            state = (_first_value(raw, STATE_ALIASES) or "NJ").upper()
            if not address or not town:
                continue
            rows.append(
                PublicRecordSale(
                    address=address,
                    town=town,
                    state=state,
                    sale_price=_parse_float(_first_value(raw, SALE_PRICE_ALIASES)),
                    sale_date=_normalize_date(_first_value(raw, SALE_DATE_ALIASES)),
                    source_id=_first_value(raw, SOURCE_ID_ALIASES),
                    source_name=default_source_name,
                )
            )
        return rows


def merge_public_record_verification(
    *,
    comp_dataset: dict[str, object],
    public_records: list[PublicRecordSale],
    as_of: str,
    verified_by: str = "briarwood_public_record_ingest",
) -> dict[str, object]:
    sales = comp_dataset.get("sales", [])
    if not isinstance(sales, list):
        raise ValueError("Comparable-sales payload is missing a sales list.")

    record_index: dict[tuple[str, str, str], list[PublicRecordSale]] = {}
    for record in public_records:
        key = (_normalize_town(record.town), record.state.upper(), _normalize_address(record.address))
        record_index.setdefault(key, []).append(record)

    matched = 0
    for sale in sales:
        if not isinstance(sale, dict):
            continue
        key = (
            _normalize_town(str(sale.get("town", ""))),
            str(sale.get("state", "")).upper(),
            _normalize_address(str(sale.get("address", ""))),
        )
        candidates = record_index.get(key, [])
        best = _best_record_match(
            sale_price=_parse_float(sale.get("sale_price")),
            sale_date=_normalize_date(sale.get("sale_date")),
            candidates=candidates,
        )
        if best is None:
            sale["sale_verification_status"] = sale.get("sale_verification_status") or "seeded"
            sale["verification_source_type"] = sale.get("verification_source_type") or "manual_review"
            sale["verification_source_name"] = sale.get("verification_source_name") or sale.get("source_name")
            sale["verification_source_id"] = sale.get("verification_source_id") or sale.get("source_ref")
            sale["last_verified_by"] = sale.get("last_verified_by") or verified_by
            sale["last_verified_at"] = sale.get("last_verified_at") or as_of
            continue

        matched += 1
        sale["sale_verification_status"] = best["status"]
        sale["verification_source_type"] = "public_record"
        sale["verification_source_name"] = best["record"].source_name
        sale["verification_source_id"] = best["record"].source_id
        sale["last_verified_by"] = verified_by
        sale["last_verified_at"] = as_of
        sale["verification_notes"] = best["notes"]

    metadata = comp_dataset.get("metadata")
    if isinstance(metadata, dict):
        metadata["public_record_refresh_as_of"] = as_of
        metadata["public_record_matches"] = matched
    return comp_dataset


def write_dataset(payload: dict[str, object], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(payload, indent=2) + "\n")


def _best_record_match(
    *,
    sale_price: float | None,
    sale_date: str | None,
    candidates: list[PublicRecordSale],
) -> dict[str, object] | None:
    best: dict[str, object] | None = None
    best_score = -1.0
    for record in candidates:
        date_score = _date_match_score(sale_date, record.sale_date)
        price_score = _price_match_score(sale_price, record.sale_price)
        total = date_score + price_score
        if total > best_score:
            status = "public_record_verified" if date_score >= 0.45 and price_score >= 0.45 else "public_record_matched"
            notes = []
            if record.sale_date:
                notes.append(f"Matched county/public-record sale date {record.sale_date}.")
            if record.sale_price is not None:
                notes.append(f"Matched county/public-record sale price near ${record.sale_price:,.0f}.")
            best = {
                "status": status,
                "record": record,
                "notes": " ".join(notes) or "Matched county/public-record sale row.",
            }
            best_score = total
    if best_score < 0.55:
        return None
    return best


def _date_match_score(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.15
    left_date = _parse_date(left)
    right_date = _parse_date(right)
    if left_date is None or right_date is None:
        return 0.15
    gap = abs((left_date - right_date).days)
    if gap == 0:
        return 0.5
    if gap <= 14:
        return 0.42
    if gap <= 45:
        return 0.3
    if gap <= 90:
        return 0.18
    return 0.0


def _price_match_score(left: float | None, right: float | None) -> float:
    if left is None or right is None or right <= 0:
        return 0.15
    gap = abs(left - right) / right
    if gap <= 0.005:
        return 0.5
    if gap <= 0.02:
        return 0.42
    if gap <= 0.05:
        return 0.28
    if gap <= 0.1:
        return 0.12
    return 0.0


def _normalize_address(value: str) -> str:
    replacements = {
        " avenue ": " ave ",
        " street ": " st ",
        " road ": " rd ",
        " boulevard ": " blvd ",
        " drive ": " dr ",
        " lane ": " ln ",
        " place ": " pl ",
        " court ": " ct ",
    }
    lowered = f" {value.strip().lower()} "
    for source, target in replacements.items():
        lowered = lowered.replace(source, target)
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return " ".join(lowered.split())


def _normalize_town(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("-", " ")
    return " ".join(normalized.split())


def _first_value(row: dict[str, object], aliases: list[str]) -> str | None:
    for key, value in row.items():
        if key is None:
            continue
        normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in [alias.replace("-", "_").replace(" ", "_") for alias in aliases]:
            text = str(value).strip()
            if text:
                return text
    return None


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_date(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def _parse_date(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge Monmouth/public-record sale verification into Briarwood sales comps.")
    parser.add_argument("--input-csv", required=True, help="Path to county/public-record sales CSV.")
    parser.add_argument("--comps", default="data/comps/sales_comps.json", help="Comparable-sales JSON file.")
    parser.add_argument("--output", default="data/comps/sales_comps.json", help="Output JSON file.")
    parser.add_argument("--as-of", required=True, help="Verification date in YYYY-MM-DD format.")
    parser.add_argument("--source-name", default="county public record import", help="Source label for matched rows.")
    parser.add_argument("--verified-by", default="briarwood_public_record_ingest")
    args = parser.parse_args()

    comp_dataset = json.loads(Path(args.comps).read_text())
    public_records = load_public_record_rows(args.input_csv, default_source_name=args.source_name)
    merged = merge_public_record_verification(
        comp_dataset=comp_dataset,
        public_records=public_records,
        as_of=args.as_of,
        verified_by=args.verified_by,
    )
    write_dataset(merged, args.output)
    print(f"Wrote merged comp dataset with {len(public_records)} public-record rows checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

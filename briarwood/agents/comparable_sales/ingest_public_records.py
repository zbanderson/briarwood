from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ComparableSale

logger = logging.getLogger(__name__)


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


def merge_sr1a_verification(
    *,
    comp_dataset: dict[str, object],
    sr1a_sales: list[ComparableSale],
    as_of: str,
    verified_by: str = "briarwood_sr1a_ingest",
) -> dict[str, int]:
    """Match SR1A state-verified sales against existing comps and upgrade verification.

    Matches by normalized address + town. When a match is found, upgrades
    sale_verification_status to "public_record_verified" and stamps the
    SR1A source_ref.

    Returns dict with counts: matched, already_verified, upgraded.
    """
    sales = comp_dataset.get("sales", [])
    if not isinstance(sales, list):
        raise ValueError("Comparable-sales payload is missing a sales list.")

    # Build index of SR1A sales by (town, address)
    sr1a_index: dict[tuple[str, str], list[ComparableSale]] = {}
    for sr1a in sr1a_sales:
        key = (_normalize_town(sr1a.town), _normalize_address(sr1a.address))
        sr1a_index.setdefault(key, []).append(sr1a)

    matched = 0
    already_verified = 0
    upgraded = 0

    for sale in sales:
        if not isinstance(sale, dict):
            continue
        key = (
            _normalize_town(str(sale.get("town", ""))),
            _normalize_address(str(sale.get("address", ""))),
        )
        candidates = sr1a_index.get(key)
        if not candidates:
            continue

        # Find best match by price/date proximity
        best_sr1a = _best_sr1a_match(
            sale_price=_parse_float(sale.get("sale_price")),
            sale_date=_normalize_date(sale.get("sale_date")),
            candidates=candidates,
        )
        if best_sr1a is None:
            continue

        matched += 1
        current_status = sale.get("sale_verification_status", "")
        if current_status == "public_record_verified":
            already_verified += 1
            continue

        upgraded += 1
        sale["sale_verification_status"] = "public_record_verified"
        sale["verification_source_type"] = "sr1a_state_record"
        sale["verification_source_name"] = "NJ SR1A"
        sale["verification_source_id"] = best_sr1a.source_ref
        sale["last_verified_by"] = verified_by
        sale["last_verified_at"] = as_of

    metadata = comp_dataset.get("metadata")
    if isinstance(metadata, dict):
        metadata["sr1a_verification_as_of"] = as_of
        metadata["sr1a_verification_matched"] = matched
        metadata["sr1a_verification_upgraded"] = upgraded

    logger.info(
        "SR1A verification: %d matched, %d already verified, %d upgraded",
        matched, already_verified, upgraded,
    )
    return {"matched": matched, "already_verified": already_verified, "upgraded": upgraded}


def _best_sr1a_match(
    *,
    sale_price: float | None,
    sale_date: str | None,
    candidates: list[ComparableSale],
) -> ComparableSale | None:
    """Find the best SR1A match by price and date proximity."""
    best: ComparableSale | None = None
    best_score = -1.0
    for sr1a in candidates:
        price_score = _price_match_score(sale_price, sr1a.sale_price)
        date_score = _date_match_score(sale_date, sr1a.sale_date)
        total = price_score + date_score
        if total > best_score:
            best = sr1a
            best_score = total
    if best_score < 0.55:
        return None
    return best


def apply_modiv_enrichment(
    *,
    comp_dataset: dict[str, object],
    enricher: "MODIVEnricher",
    district_map_reverse: dict[str, str] | None = None,
) -> dict[str, int]:
    """Enrich existing comp store entries with MOD-IV data (year_built, lot_size, lat/lon).

    Parses block/lot from source_notes, looks up in MOD-IV, and fills
    missing fields. Does not overwrite existing values.

    Returns dict with counts: attempted, matched, year_built, acreage, latlon.
    """
    from briarwood.agents.comparable_sales.modiv_enricher import MODIVEnricher as _ME  # noqa: F811
    from briarwood.agents.comparable_sales.sr1a_parser import MONMOUTH_DISTRICT_CODES

    if district_map_reverse is None:
        district_map_reverse = {v: k for k, v in MONMOUTH_DISTRICT_CODES.items()}

    sales = comp_dataset.get("sales", [])
    if not isinstance(sales, list):
        raise ValueError("Comparable-sales payload is missing a sales list.")

    counts = {"attempted": 0, "matched": 0, "year_built": 0, "acreage": 0, "latlon": 0}

    for sale in sales:
        if not isinstance(sale, dict):
            continue

        # Extract block/lot from source_notes
        notes = sale.get("source_notes", "")
        if not notes:
            continue
        m = re.search(r"Block/Lot\s+([^;/]+)/([^;]+)", notes)
        if not m:
            continue

        block = m.group(1).strip()
        lot = m.group(2).strip()
        town = str(sale.get("town", ""))
        district_code = district_map_reverse.get(town, "")
        if not district_code:
            continue

        counts["attempted"] += 1
        record = enricher.lookup(district_code, block, lot)
        if record is None:
            continue

        counts["matched"] += 1

        if not sale.get("year_built") and record.year_built is not None:
            sale["year_built"] = record.year_built
            counts["year_built"] += 1

        if not sale.get("lot_size") and record.calc_acre is not None:
            sale["lot_size"] = record.calc_acre
            counts["acreage"] += 1

        if not sale.get("latitude") and record.latitude is not None:
            sale["latitude"] = record.latitude
            sale["longitude"] = record.longitude
            counts["latlon"] += 1

    logger.info(
        "MOD-IV enrichment on store: %d attempted, %d matched, "
        "%d year_built, %d acreage, %d lat/lon",
        counts["attempted"], counts["matched"],
        counts["year_built"], counts["acreage"], counts["latlon"],
    )
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Merge Monmouth/public-record sale verification into Briarwood sales comps.")
    parser.add_argument("--input-csv", default=None, help="Path to county/public-record sales CSV.")
    parser.add_argument("--sr1a-dir", default=None, help="Directory containing SR1A flat files for verification.")
    parser.add_argument("--modiv-csv", default=None, help="MOD-IV CSV for enrichment (year_built, lot_size, lat/lon).")
    parser.add_argument("--modiv-geojson", default=None, help="MOD-IV GeoJSON for enrichment.")
    parser.add_argument("--county-code", default="13", help="2-digit NJ county code (default 13 = Monmouth).")
    parser.add_argument("--comps", default="data/comps/sales_comps.json", help="Comparable-sales JSON file.")
    parser.add_argument("--output", default="data/comps/sales_comps.json", help="Output JSON file.")
    parser.add_argument("--as-of", default=None, help="Verification date in YYYY-MM-DD format (default: today).")
    parser.add_argument("--source-name", default="county public record import", help="Source label for matched rows.")
    parser.add_argument("--verified-by", default="briarwood_public_record_ingest")
    args = parser.parse_args()

    as_of = args.as_of or datetime.today().strftime("%Y-%m-%d")

    if not args.input_csv and not args.sr1a_dir and not args.modiv_csv and not args.modiv_geojson:
        parser.error("At least one of --input-csv, --sr1a-dir, --modiv-csv, or --modiv-geojson is required.")

    comp_dataset = json.loads(Path(args.comps).read_text())

    # ── CSV-based verification (original flow) ───────────────────────────
    if args.input_csv:
        public_records = load_public_record_rows(args.input_csv, default_source_name=args.source_name)
        comp_dataset = merge_public_record_verification(
            comp_dataset=comp_dataset,
            public_records=public_records,
            as_of=as_of,
            verified_by=args.verified_by,
        )
        print(f"CSV verification: {len(public_records)} public-record rows checked.")

    # ── SR1A-based verification ──────────────────────────────────────────
    if args.sr1a_dir:
        from briarwood.agents.comparable_sales.sr1a_parser import parse_sr1a_file

        sr1a_path = Path(args.sr1a_dir)
        sr1a_sales: list[ComparableSale] = []
        if sr1a_path.is_file():
            sr1a_files = [sr1a_path]
        elif sr1a_path.is_dir():
            sr1a_files = sorted(
                p for p in sr1a_path.iterdir()
                if p.is_file() and p.suffix in {"", ".txt", ".dat", ".sr1a"}
            )
        else:
            print(f"SR1A path not found: {sr1a_path}")
            return 1

        for f in sr1a_files:
            result = parse_sr1a_file(f, county_code=args.county_code)
            sr1a_sales.extend(result.sales)

        if sr1a_sales:
            counts = merge_sr1a_verification(
                comp_dataset=comp_dataset,
                sr1a_sales=sr1a_sales,
                as_of=as_of,
                verified_by=args.verified_by,
            )
            print(f"SR1A verification: {counts['matched']} matched, {counts['upgraded']} upgraded.")

    # ── MOD-IV enrichment ────────────────────────────────────────────────
    if args.modiv_csv or args.modiv_geojson:
        from briarwood.agents.comparable_sales.modiv_enricher import MODIVEnricher

        enricher = MODIVEnricher()
        if args.modiv_csv:
            enricher.load_csv(args.modiv_csv)
        if args.modiv_geojson:
            enricher.load_geojson(args.modiv_geojson)

        if enricher.record_count > 0:
            counts = apply_modiv_enrichment(
                comp_dataset=comp_dataset,
                enricher=enricher,
            )
            print(f"MOD-IV enrichment: {counts['matched']} matched, "
                  f"{counts['year_built']} year_built, {counts['acreage']} acreage, "
                  f"{counts['latlon']} lat/lon enriched.")

    write_dataset(comp_dataset, args.output)
    print(f"Wrote updated comp dataset to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

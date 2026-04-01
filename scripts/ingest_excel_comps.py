#!/usr/bin/env python3
"""
ingest_excel_comps.py — Ingests comp Excel files into the Briarwood comp database.

Handles:
  briarwood_sold_structured.xlsx   → data/comps/sales_comps.json   (closed sales)
  briarwood_comp_template_v1.xlsx  → data/comps/active_listings.json (active listings)

Usage:
    python scripts/ingest_excel_comps.py [--dry-run]
    python scripts/ingest_excel_comps.py --sold-file PATH --active-file PATH [--dry-run]

Design decisions:
  - sale_date: Required by the schema but absent from the sold file. We default to
    "2025-01-01" (Option B) and flag every record with sale_date_estimated=True in
    verification_notes. The time-adjustment math will be approximate but won't break.
    See SALE_DATE_ESTIMATED constant.
  - Active listings go to active_listings.json using list_price, NOT to sales_comps.json.
    They are asking prices, not transaction prices, and should never be mixed.
  - Lot Size in the active file is in square feet (raw from listing data); we convert
    to acres on ingest. Lot Size in the sold file is empty for all 38 records.
  - Dedup is exact normalized-address match. Near-duplicates (same base address,
    different unit numbers) are flagged in the data-quality report but not merged.
  - Records with null sale_price are skipped (cannot be a comp without a price).
  - Records with formula strings in numeric fields (=C2/F2 etc.) are treated as null.
  - All new records receive address_verification_status="unverified" — they have not
    been manually confirmed. Run the address verification pass separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
SALES_JSON = REPO_ROOT / "data" / "comps" / "sales_comps.json"
ACTIVE_JSON = REPO_ROOT / "data" / "comps" / "active_listings.json"
ICLOUD_DIR = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "briarwood"

# Candidate search paths, tried in priority order (first hit wins).
_SOLD_SEARCH_NAMES = ["briarwood_sold_structured.xlsx"]
_ACTIVE_SEARCH_NAMES = ["briarwood_comp_template_v1.xlsx"]
_SEARCH_DIRS = [
    ICLOUD_DIR,
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    REPO_ROOT / "data",
    REPO_ROOT,
    Path.cwd(),
]


def _find_file(names: list[str]) -> Path | None:
    """Return first existing file matching any name in any search directory."""
    for directory in _SEARCH_DIRS:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return candidate
    return None


def _resolve_file(arg: Path | None, names: list[str], label: str) -> Path:
    """Return an explicit --flag path if given, otherwise auto-discover."""
    if arg is not None:
        if not arg.exists():
            sys.exit(f"{label} not found at: {arg}")
        return arg
    found = _find_file(names)
    if found is None:
        searched = "\n  ".join(str(d) for d in _SEARCH_DIRS)
        sys.exit(
            f"Could not find {label} ({', '.join(names)}).\n"
            f"Searched:\n  {searched}\n"
            f"Drop the file into one of those directories or pass --{'sold' if 'sold' in label.lower() else 'active'}-file PATH."
        )
    print(f"  Auto-discovered {label}: {found}")
    return found

TODAY = date.today().isoformat()  # "2026-04-01"
SALE_DATE_ESTIMATED = "2025-01-01"  # Applied to all sold records lacking a real date
LOT_SQFT_TO_ACRES = 1 / 43_560.0
BEACH_BLOCK_TO_MILES = 0.055  # Shore-town block ≈ 0.05–0.06 mi; use 0.055

# ---------------------------------------------------------------------------
# Town normalization
# ---------------------------------------------------------------------------
TOWN_ALIASES: dict[str, str] = {
    "avon": "Avon By The Sea",
    "avon by the sea": "Avon By The Sea",
    "bradley": "Bradley Beach",
    "bradley beach": "Bradley Beach",
    "wall": "Wall Township",
    "wall township": "Wall Township",
    "belmar": "Belmar",
    "spring lake": "Spring Lake",
    "neptune": "Neptune",
    "neptune city": "Neptune",
    "manasquan": "Manasquan",
    "sea girt": "Sea Girt",
    "brookline": "Brookline",
}


def normalize_town(raw: str | None) -> str | None:
    if not raw:
        return None
    return TOWN_ALIASES.get(raw.strip().lower(), raw.strip().title())


# ---------------------------------------------------------------------------
# Property type normalization
# ---------------------------------------------------------------------------
PROPERTY_TYPE_MAP: dict[str, str] = {
    "sfh": "single family",
    "single family": "single family",
    "single-family": "single family",
    "condo": "condo",
    "condominium": "condo",
    "multi": "multifamily",
    "multifamily": "multifamily",
    "multi family": "multifamily",
    "multi-family": "multifamily",
    "land": "land",
    "vacant land": "land",
}


def normalize_property_type(raw: str | None) -> str | None:
    if not raw:
        return None
    return PROPERTY_TYPE_MAP.get(raw.strip().lower(), raw.strip().lower())


# ---------------------------------------------------------------------------
# Condition profile derivation
# ---------------------------------------------------------------------------
def derive_condition(new_construction: int, renovated: int, tear_down: int) -> str:
    """Map binary flags to condition_profile. Priority: new > renovated > tear_down."""
    if new_construction:
        return "renovated"   # New construction = best available condition tier
    if renovated:
        return "updated"
    if tear_down:
        return "needs_work"
    return "maintained"


# ---------------------------------------------------------------------------
# Location tags from Water Proximity
# ---------------------------------------------------------------------------
WATER_PROXIMITY_TAGS: dict[str, str] = {
    "ocean": "beach_access",
    "lake": "lake_access",
    "river/marina": "marina_access",
    "marina": "marina_access",
    "river": "marina_access",
}


def derive_location_tags(water_proximity: str | None, pool: int = 0) -> list[str]:
    tags: list[str] = []
    if water_proximity:
        tag = WATER_PROXIMITY_TAGS.get(water_proximity.strip().lower())
        if tag:
            tags.append(tag)
    return tags


# ---------------------------------------------------------------------------
# Address normalization for deduplication
# ---------------------------------------------------------------------------
STREET_EXPANSIONS: list[tuple[str, str]] = [
    (r"\bst\b", "street"),
    (r"\bave\b", "avenue"),
    (r"\brd\b", "road"),
    (r"\bdr\b", "drive"),
    (r"\bblvd\b", "boulevard"),
    (r"\bln\b", "lane"),
    (r"\bct\b", "court"),
    (r"\bpl\b", "place"),
    (r"\bcir\b", "circle"),
    (r"\bhwy\b", "highway"),
    (r"\bpkwy\b", "parkway"),
]


def normalize_address(addr: str) -> str:
    """Lowercase, strip zip/state, expand street abbreviations, collapse spaces."""
    a = addr.lower().strip()
    a = re.sub(r",\s*nj\s*\d{5}(-\d{4})?", "", a)
    a = re.sub(r",\s*nj\b", "", a)
    a = re.sub(r"\s+", " ", a)
    for pattern, replacement in STREET_EXPANSIONS:
        a = re.sub(pattern, replacement, a)
    return a.strip()


def base_address(addr: str) -> str:
    """Strip unit/apt designator — used only for near-duplicate detection."""
    a = normalize_address(addr)
    a = re.sub(r"\s+(unit|apt|#|suite)\s*\S+$", "", a)
    return a.strip()


# ---------------------------------------------------------------------------
# Source ref (stable hash-based ID)
# ---------------------------------------------------------------------------
def make_source_ref(address: str, town: str, prefix: str) -> str:
    key = f"{normalize_address(address)}|{town.lower()}"
    h = hashlib.md5(key.encode()).hexdigest()[:8].upper()
    return f"{prefix}-{h}"


# ---------------------------------------------------------------------------
# Safe numeric extraction (handles Excel formula strings)
# ---------------------------------------------------------------------------
def _num(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.startswith("=") or s == "":
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _int(value: object) -> int | None:
    v = _num(value)
    return int(round(v)) if v is not None else None


# ---------------------------------------------------------------------------
# Excel reading
# ---------------------------------------------------------------------------
def read_excel(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    """Return (headers, rows) from the first sheet of an Excel file."""
    try:
        import openpyxl
    except ImportError:
        sys.exit("openpyxl is required: pip install openpyxl")

    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(c) if c is not None else "" for c in next(rows_iter)]
    rows = [dict(zip(headers, row)) for row in rows_iter]
    return headers, rows


# ---------------------------------------------------------------------------
# Parse sold row → ComparableSale-compatible dict
# ---------------------------------------------------------------------------
def parse_sold_row(row: dict, row_num: int) -> tuple[dict | None, list[str]]:
    """
    Returns (record_dict, warnings). Returns (None, warnings) if the row
    must be skipped.
    """
    warnings: list[str] = []
    address_raw = str(row.get("Address") or "").strip()
    if not address_raw:
        return None, ["Row skipped: no address"]

    price = _num(row.get("Price"))
    if price is None or price <= 0:
        return None, [f"{address_raw}: skipped — no valid sale_price"]

    town_raw = str(row.get("Town") or "").strip()
    town = normalize_town(town_raw)
    if not town:
        warnings.append(f"{address_raw}: could not normalize town '{town_raw}'")
        town = town_raw

    # Strip town/state/zip from address if embedded (common in this dataset)
    clean_address = re.sub(r",\s*" + re.escape(town_raw) + r".*$", "", address_raw, flags=re.IGNORECASE).strip()
    if not clean_address:
        clean_address = address_raw

    prop_type = normalize_property_type(str(row.get("Property Type") or ""))
    beds = _int(row.get("Beds"))
    baths = _num(row.get("Baths"))
    sqft = _int(row.get("Sqft"))
    garage = _int(row.get("Garage")) or 0
    pool = _int(row.get("Pool")) or 0
    income_potential = _int(row.get("Income Potential")) or 0
    new_constr = _int(row.get("New Construction")) or 0
    renovated = _int(row.get("Renovated")) or 0
    tear_down = _int(row.get("Tear Down")) or 0
    water_prox = row.get("Water Proximity")
    water_prox = str(water_prox).strip() if water_prox else None

    condition = derive_condition(new_constr, renovated, tear_down)
    location_tags = derive_location_tags(water_prox, pool)

    micro_notes: list[str] = []
    if pool:
        micro_notes.append("Pool present.")
    if income_potential:
        micro_notes.append("Income / rental potential noted.")
    if tear_down:
        micro_notes.append("Listed as tear-down / land value.")

    source_ref = make_source_ref(clean_address, town, "SOLD")

    # Data-quality warnings
    if beds is None:
        warnings.append(f"{clean_address}: beds missing")
    if baths is None:
        warnings.append(f"{clean_address}: baths missing")
    if sqft is None:
        warnings.append(f"{clean_address}: sqft missing")

    record = {
        "address": clean_address,
        "town": town,
        "state": "NJ",
        "property_type": prop_type,
        "architectural_style": None,
        "condition_profile": condition,
        "capex_lane": None,
        "sale_price": price,
        "sale_date": SALE_DATE_ESTIMATED,
        "source_name": "briarwood_sold_structured",
        "source_quality": "imported",
        "source_ref": source_ref,
        "source_notes": "Imported from briarwood_sold_structured.xlsx. sale_date is estimated (2025-01-01); actual date unknown — time adjustment may be unreliable.",
        "reviewed_at": TODAY,
        "comp_status": "seeded",
        "address_verification_status": "verified",
        "sale_verification_status": "seeded",
        "verification_source_type": "manual_review",
        "verification_source_name": "briarwood_sold_structured.xlsx",
        "verification_source_id": source_ref,
        "last_verified_by": "ingest_excel_comps",
        "last_verified_at": TODAY,
        "verification_notes": "Batch import from curated Excel comp sheet. sale_date estimated (2025-01-01) — not in source file; time adjustment may be unreliable.",
        "beds": beds,
        "baths": baths,
        "sqft": sqft,
        "lot_size": None,   # Entirely absent from sold file
        "year_built": None, # Not in source
        "stories": None,    # Not in source
        "garage_spaces": garage,
        "days_on_market": None,
        "distance_to_subject_miles": None,
        "location_tags": location_tags,
        "micro_location_notes": micro_notes,
    }
    return record, warnings


# ---------------------------------------------------------------------------
# Parse active row → ActiveListingRecord-compatible dict
# ---------------------------------------------------------------------------
def parse_active_row(row: dict, row_num: int) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    address_raw = str(row.get("Address") or "").strip()
    if not address_raw:
        return None, ["Row skipped: no address"]

    price = _num(row.get("Price"))
    if price is None or price <= 0:
        return None, [f"{address_raw}: skipped — no valid list_price"]

    town_raw = str(row.get("Town") or "").strip()
    town = normalize_town(town_raw)
    if not town:
        warnings.append(f"{address_raw}: could not normalize town '{town_raw}'")
        town = town_raw

    # Strip town/state/zip from address
    clean_address = re.sub(r",\s*" + re.escape(town_raw) + r".*$", "", address_raw, flags=re.IGNORECASE).strip()
    # Also strip trailing ", NJ XXXXX" that may remain after town removal
    clean_address = re.sub(r",\s*NJ\s*\d{5}.*$", "", clean_address).strip()
    if not clean_address:
        clean_address = address_raw

    prop_type = normalize_property_type(str(row.get("Property Type") or ""))
    beds_raw = _int(row.get("Beds"))
    # Beds=0 is valid (studio); only treat as missing if the cell is actually None
    beds = beds_raw if row.get("Beds") is not None else None
    baths = _num(row.get("Baths"))
    sqft = _int(row.get("Sqft"))

    # Lot size is in sq ft in active file — convert to acres
    lot_sqft = _num(row.get("Lot Size"))
    lot_size = round(lot_sqft * LOT_SQFT_TO_ACRES, 4) if lot_sqft else None

    new_constr = _int(row.get("New Construction")) or 0
    renovated = _int(row.get("Renovated")) or 0
    tear_down = _int(row.get("Tear Down")) or 0
    garage = _int(row.get("Garage")) or 0
    pool = _int(row.get("Pool")) or 0
    income_potential = _int(row.get("Income Potential")) or 0

    beach_blocks = _num(row.get("Beach Distance (Blocks)"))
    water_prox = row.get("Water Proximity")
    water_prox = str(water_prox).strip() if water_prox else None

    condition = derive_condition(new_constr, renovated, tear_down)

    feature_notes = str(row.get("Feature Notes") or "").strip()
    description = str(row.get("Description Snapshot") or "").strip()

    notes_parts: list[str] = []
    if pool:
        notes_parts.append("Pool present.")
    if income_potential:
        notes_parts.append("Income / rental potential noted.")
    if tear_down:
        notes_parts.append("Listed as tear-down / land value.")
    if beach_blocks is not None:
        notes_parts.append(f"Beach distance: ~{beach_blocks:.0f} block(s) (~{beach_blocks * BEACH_BLOCK_TO_MILES:.2f} mi).")
    if feature_notes:
        notes_parts.append(f"Features: {feature_notes}")
    if description:
        notes_parts.append(f"Description: {description[:300]}{'...' if len(description) > 300 else ''}")

    source_ref = make_source_ref(clean_address, town, "ACTIVE")

    if beds is None:
        warnings.append(f"{clean_address}: beds missing")
    if baths is None:
        warnings.append(f"{clean_address}: baths missing")
    if sqft is None:
        warnings.append(f"{clean_address}: sqft missing")
    if lot_size is None:
        warnings.append(f"{clean_address}: lot_size missing")

    record = {
        "address": clean_address,
        "town": town,
        "state": "NJ",
        "list_price": price,
        "listing_status": "for_sale",
        "property_type": prop_type,
        "architectural_style": None,
        "condition_profile": condition,
        "capex_lane": None,
        "source_name": "briarwood_comp_template_v1",
        "source_ref": source_ref,
        "source_notes": f"Imported from briarwood_comp_template_v1.xlsx. Active listing — asking price only.",
        "days_on_market": None,
        "beds": beds,
        "baths": baths,
        "sqft": sqft,
        "lot_size": lot_size,
        "year_built": None,
        "garage_spaces": garage,
        "notes": " | ".join(notes_parts) if notes_parts else None,
    }
    return record, warnings


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------
def build_norm_index(records: list[dict], addr_field: str = "address") -> dict[str, dict]:
    """Return {normalized_address: record} for existing records."""
    return {normalize_address(r[addr_field]): r for r in records}


def find_near_duplicates(
    new_addr: str, existing_index: dict[str, dict]
) -> list[str]:
    """Return list of existing normalized addresses that share the same base address."""
    base = base_address(new_addr)
    return [k for k in existing_index if base_address(k) == base and normalize_address(new_addr) != k]


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------
def ingest(
    sold_file: Path,
    active_file: Path,
    dry_run: bool = False,
) -> None:
    print(f"{'[DRY RUN] ' if dry_run else ''}Briarwood Comp Ingestion")
    print(f"  Sold file:   {sold_file}")
    print(f"  Active file: {active_file}")
    print()

    # ------------------------------------------------------------------
    # Load existing data
    # ------------------------------------------------------------------
    with open(SALES_JSON) as f:
        sales_data = json.load(f)
    existing_sales: list[dict] = sales_data["sales"]

    with open(ACTIVE_JSON) as f:
        active_data = json.load(f)
    existing_active: list[dict] = active_data["listings"]

    sales_index = build_norm_index(existing_sales)
    active_index = build_norm_index(existing_active)

    # ------------------------------------------------------------------
    # Process sold file
    # ------------------------------------------------------------------
    print("=== Processing sold file ===")
    _, sold_rows = read_excel(sold_file)

    new_sales: list[dict] = []
    skipped_sales: list[str] = []
    deduped_sales: list[str] = []
    all_warnings: list[str] = []

    for i, row in enumerate(sold_rows, start=2):  # row 1 = headers
        record, row_warnings = parse_sold_row(row, i)
        all_warnings.extend(row_warnings)

        if record is None:
            skipped_sales.extend(row_warnings)
            continue

        norm = normalize_address(record["address"])
        if norm in sales_index:
            deduped_sales.append(f"  SKIP (exists): {record['address']} | {record['town']}")
            continue

        near_dupes = find_near_duplicates(norm, sales_index)
        if near_dupes:
            all_warnings.append(
                f"NEAR-DUP: '{record['address']}' shares base address with existing: {near_dupes}"
            )

        new_sales.append(record)

    print(f"  Rows read:        {len(sold_rows)}")
    print(f"  New records:      {len(new_sales)}")
    print(f"  Skipped (no price/addr): {len(skipped_sales)}")
    print(f"  Deduplicated:     {len(deduped_sales)}")
    for msg in deduped_sales:
        print(msg)
    print()

    # ------------------------------------------------------------------
    # Process active file
    # ------------------------------------------------------------------
    print("=== Processing active listings file ===")
    _, active_rows = read_excel(active_file)

    new_active: list[dict] = []
    skipped_active: list[str] = []
    deduped_active: list[str] = []

    for i, row in enumerate(active_rows, start=2):
        record, row_warnings = parse_active_row(row, i)
        all_warnings.extend(row_warnings)

        if record is None:
            skipped_active.extend(row_warnings)
            continue

        norm = normalize_address(record["address"])
        if norm in active_index:
            deduped_active.append(f"  SKIP (exists): {record['address']} | {record['town']}")
            continue

        near_dupes = find_near_duplicates(norm, active_index)
        if near_dupes:
            all_warnings.append(
                f"NEAR-DUP (active): '{record['address']}' shares base address with existing: {near_dupes}"
            )

        new_active.append(record)

    print(f"  Rows read:        {len(active_rows)}")
    print(f"  New records:      {len(new_active)}")
    print(f"  Skipped (no price/addr): {len(skipped_active)}")
    print(f"  Deduplicated:     {len(deduped_active)}")
    for msg in deduped_active:
        print(msg)
    print()

    # ------------------------------------------------------------------
    # Validate with Pydantic before writing
    # ------------------------------------------------------------------
    print("=== Validating new records ===")
    sys.path.insert(0, str(REPO_ROOT))
    from briarwood.agents.comparable_sales.schemas import ComparableSale, ActiveListingRecord

    valid_sales: list[dict] = []
    valid_active: list[dict] = []
    validation_errors: list[str] = []

    for rec in new_sales:
        try:
            ComparableSale(**rec)
            valid_sales.append(rec)
        except Exception as e:
            validation_errors.append(f"INVALID SALE: {rec.get('address')} — {e}")

    for rec in new_active:
        try:
            ActiveListingRecord(**rec)
            valid_active.append(rec)
        except Exception as e:
            validation_errors.append(f"INVALID ACTIVE: {rec.get('address')} — {e}")

    if validation_errors:
        print(f"  Validation errors: {len(validation_errors)}")
        for err in validation_errors:
            print(f"    {err}")
    else:
        print(f"  All {len(valid_sales)} sales + {len(valid_active)} active listings pass schema validation.")
    print()

    # ------------------------------------------------------------------
    # Write (unless dry-run)
    # ------------------------------------------------------------------
    if dry_run:
        print("[DRY RUN] Would write:")
        print(f"  sales_comps.json:    {len(existing_sales)} existing + {len(valid_sales)} new = {len(existing_sales) + len(valid_sales)} total")
        print(f"  active_listings.json: {len(existing_active)} existing + {len(valid_active)} new = {len(existing_active) + len(valid_active)} total")
    else:
        sales_data["sales"] = existing_sales + valid_sales
        sales_data["metadata"]["as_of"] = TODAY
        with open(SALES_JSON, "w") as f:
            json.dump(sales_data, f, indent=2)
        print(f"  Wrote sales_comps.json: {len(existing_sales)} + {len(valid_sales)} = {len(sales_data['sales'])} total")

        active_data["listings"] = existing_active + valid_active
        active_data["metadata"]["as_of"] = TODAY
        with open(ACTIVE_JSON, "w") as f:
            json.dump(active_data, f, indent=2)
        print(f"  Wrote active_listings.json: {len(existing_active)} + {len(valid_active)} = {len(active_data['listings'])} total")

    # ------------------------------------------------------------------
    # Data quality report
    # ------------------------------------------------------------------
    print()
    print("=== Data Quality Report ===")

    all_new = valid_sales + valid_active
    if all_new:
        missing_beds = sum(1 for r in all_new if r.get("beds") is None)
        missing_baths = sum(1 for r in all_new if r.get("baths") is None)
        missing_sqft = sum(1 for r in all_new if r.get("sqft") is None)
        missing_lot = sum(1 for r in all_new if r.get("lot_size") is None)
        missing_year = sum(1 for r in all_new if r.get("year_built") is None)
        total = len(all_new)
        print(f"  Records ingested:    {total}  ({len(valid_sales)} sold, {len(valid_active)} active)")
        print(f"  Missing beds:        {missing_beds}/{total} ({missing_beds/total:.0%})")
        print(f"  Missing baths:       {missing_baths}/{total} ({missing_baths/total:.0%})")
        print(f"  Missing sqft:        {missing_sqft}/{total} ({missing_sqft/total:.0%})")
        print(f"  Missing lot_size:    {missing_lot}/{total} ({missing_lot/total:.0%})  [sold file has no lot data; active file has some]")
        print(f"  Missing year_built:  {missing_year}/{total} ({missing_year/total:.0%})  [not in either source file]")
        print(f"  Missing sale_date:   {len(valid_sales)}/{len(valid_sales)} ({100:.0f}%)  [all set to estimated '{SALE_DATE_ESTIMATED}']")

        print()
        print("  Breakdown by town:")
        from collections import Counter
        town_counts = Counter(r["town"] for r in all_new)
        for town, count in sorted(town_counts.items()):
            print(f"    {town:<22} {count}")

        print()
        print("  Breakdown by property type:")
        type_counts = Counter(r.get("property_type", "unknown") or "unknown" for r in all_new)
        for pt, count in sorted(type_counts.items()):
            print(f"    {pt:<20} {count}")

    print()
    print(f"  Skipped records:     {len(skipped_sales) + len(skipped_active)}")
    for msg in skipped_sales + skipped_active:
        print(f"    {msg}")

    warn_msgs = [w for w in all_warnings if "missing" in w.lower() or "NEAR-DUP" in w or "could not" in w.lower()]
    structural_warns = [w for w in warn_msgs if "NEAR-DUP" in w or "could not" in w]
    if structural_warns:
        print()
        print("  Structural warnings (review these):")
        for w in structural_warns:
            print(f"    {w}")

    # ------------------------------------------------------------------
    # Post-ingest validation: run comp agent against a known property
    # ------------------------------------------------------------------
    if not dry_run and valid_sales:
        print()
        print("=== Post-Ingest Smoke Test ===")
        print("  Running comp agent against Belmar SFH sample...")
        try:
            from briarwood.agents.comparable_sales.agent import ComparableSalesAgent
            from briarwood.agents.comparable_sales.schemas import ComparableSalesRequest
            from briarwood.agents.comparable_sales.store import FileBackedComparableSalesProvider

            provider = FileBackedComparableSalesProvider(str(SALES_JSON))
            agent = ComparableSalesAgent(provider)
            request = ComparableSalesRequest(
                town="Belmar",
                state="NJ",
                property_type="single family",
                beds=3,
                baths=2.0,
                sqft=1500,
                lot_size=0.12,
                year_built=1990,
            )
            result = agent.run(request)
            print(f"  Comp agent result: {result.comp_count} comps used, confidence={result.confidence:.2f}")
            print(f"  Comparable value: ${result.comparable_value:,.0f}" if result.comparable_value else "  No value produced")
        except Exception as e:
            print(f"  Smoke test failed: {e}")

    print()
    print("Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing files")
    parser.add_argument(
        "--sold-file", type=Path, default=None,
        help="Path to sold Excel file (auto-discovered from common locations if omitted)",
    )
    parser.add_argument(
        "--active-file", type=Path, default=None,
        help="Path to active listings Excel file (auto-discovered if omitted)",
    )
    args = parser.parse_args()

    sold_file = _resolve_file(args.sold_file, _SOLD_SEARCH_NAMES, "sold file")
    active_file = _resolve_file(args.active_file, _ACTIVE_SEARCH_NAMES, "active file")

    ingest(sold_file=sold_file, active_file=active_file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

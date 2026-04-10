"""
Fetch recent residential sales from ATTOM's sale/snapshot endpoint and merge
into the comp store.

Usage:
    python scripts/fetch_attom_sales.py [--dry-run] [--max-per-town 100]

Requires ATTOM_API_KEY in .env or environment.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Ensure briarwood package (and dotenv) loads
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import briarwood  # noqa: F401 — triggers dotenv

from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore

logger = logging.getLogger(__name__)

ATTOM_BASE = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"

# Target towns with their ZIP codes (ATTOM needs postalcode for area search).
TARGET_TOWNS: dict[str, dict] = {
    "Belmar": {"zip": "07719", "state": "NJ"},
    "Bradley Beach": {"zip": "07720", "state": "NJ"},
    "Avon By The Sea": {"zip": "07717", "state": "NJ"},
    "Asbury Park": {"zip": "07712", "state": "NJ"},
    "Sea Girt": {"zip": "08750", "state": "NJ"},
    "Manasquan": {"zip": "08736", "state": "NJ"},
    "Spring Lake": {"zip": "07762", "state": "NJ"},
}

# Normalized locality names ATTOM may return that we accept.
# ZIP codes can span multiple towns, so we filter by locality.
ALLOWED_LOCALITIES = {
    "belmar", "bradley beach", "avon by the sea", "avon-by-the-sea",
    "asbury park", "sea girt", "manasquan", "spring lake",
    "spring lake heights", "wall", "wall township",
}

# ATTOM property type codes for residential.
PROPERTY_TYPES = ["SFR", "CONDO", "APARTMENT"]

COMPS_PATH = Path("data/comps/sales_comps.json")
REQUEST_DELAY = 0.6  # seconds between API calls


def _attom_get(path: str, params: dict, api_key: str) -> dict:
    """Make a GET request to ATTOM API."""
    url = f"{ATTOM_BASE}{path}?{urlencode(params)}"
    req = Request(url, headers={"apikey": api_key, "Accept": "application/json"})
    resp = urlopen(req, timeout=20)
    return json.loads(resp.read())


def _normalize_property_type(attom_type: str | None) -> str:
    """Map ATTOM property type strings to our schema values."""
    if not attom_type:
        return "single_family"
    t = attom_type.lower()
    if "condo" in t:
        return "condo"
    if "townhouse" in t or "town house" in t:
        return "townhouse"
    if "multi" in t or "duplex" in t or "triplex" in t:
        return "multi_family"
    return "single_family"


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        v = int(val)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_attom_property(prop: dict, town: str, state: str) -> ComparableSale | None:
    """Convert an ATTOM sale/snapshot property to a ComparableSale."""
    address_block = prop.get("address", {})
    building = prop.get("building", {}).get("size", {})
    building_rooms = prop.get("building", {}).get("rooms", {})
    sale_info = prop.get("sale", {})
    sale_amount = sale_info.get("amount", {})
    sale_date_raw = sale_info.get("saleTransDate") or sale_info.get("amount", {}).get("salerecdate", "")
    lot = prop.get("lot", {})
    summary = prop.get("summary", {})
    location = prop.get("location", {})

    address = address_block.get("line1", "").strip()
    if not address:
        return None

    sale_price = _safe_float(sale_amount.get("saleamt"))
    if not sale_price or sale_price < 50000:
        return None

    # Parse sale date
    if not sale_date_raw:
        return None
    try:
        if "T" in sale_date_raw:
            sale_date = sale_date_raw.split("T")[0]
        else:
            sale_date = sale_date_raw[:10]
        # Validate it's a real date
        datetime.strptime(sale_date, "%Y-%m-%d")
    except (ValueError, IndexError):
        return None

    # Filter out very old sales
    try:
        sale_dt = datetime.strptime(sale_date, "%Y-%m-%d")
        if sale_dt < datetime.now() - timedelta(days=365 * 3):
            return None
    except ValueError:
        pass

    beds = _safe_int(building_rooms.get("beds"))
    baths_full = _safe_int(building_rooms.get("bathsfull")) or 0
    baths_half = _safe_int(building_rooms.get("bathshalf")) or 0
    baths = float(baths_full + baths_half * 0.5) if (baths_full or baths_half) else None
    sqft = _safe_int(building.get("universalsize") or building.get("livingsize"))
    lot_acres = _safe_float(lot.get("lotsize1"))
    # ATTOM sometimes returns lot in sqft — convert if > 5 (acres)
    if lot_acres and lot_acres > 5:
        lot_acres = round(lot_acres / 43560, 4)
    year_built = _safe_int(summary.get("yearbuilt"))
    stories = _safe_float(building.get("stories"))
    lat = _safe_float(location.get("latitude"))
    lon = _safe_float(location.get("longitude"))
    prop_type = _normalize_property_type(summary.get("proptype") or summary.get("propsubtype"))

    # Normalize town name from ATTOM (may differ from our standard)
    attom_town = (address_block.get("locality") or town).strip().title()
    # Filter out properties not in our target localities (ZIP codes span towns)
    locality_key = attom_town.lower().replace("-", " ").strip()
    if locality_key not in ALLOWED_LOCALITIES:
        return None
    # Use our canonical town name if ATTOM locality matches
    actual_town = town if locality_key in town.lower().replace("-", " ") else attom_town

    source_ref = f"ATTOM-{actual_town.upper().replace(' ', '-')}-{address.upper().replace(' ', '-')}-{sale_date}"

    return ComparableSale(
        address=address.title(),
        town=actual_town,
        state=state,
        property_type=prop_type,
        sale_price=sale_price,
        sale_date=sale_date,
        beds=beds,
        baths=baths,
        sqft=sqft,
        lot_size=lot_acres,
        year_built=year_built,
        stories=stories,
        latitude=lat,
        longitude=lon,
        source_name="ATTOM sale/snapshot",
        source_quality="api_sourced",
        source_ref=source_ref,
        verification_status="public_record",
        sale_verification_status="public_record_matched",
        verification_source_type="public_record",
        verification_source_name="ATTOM Data Solutions",
        address_verification_status="verified",
        comp_status="seeded",
    )


def fetch_town_sales(
    town: str,
    zip_code: str,
    state: str,
    api_key: str,
    *,
    max_records: int = 100,
    min_sale_date: str | None = None,
) -> list[ComparableSale]:
    """Fetch recent residential sales for a town from ATTOM."""
    if min_sale_date is None:
        min_sale_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    all_sales: list[ComparableSale] = []
    seen_refs: set[str] = set()

    for prop_type in PROPERTY_TYPES:
        page = 1
        page_size = min(50, max_records)
        while len(all_sales) < max_records:
            params = {
                "postalcode": zip_code,
                "minsaleamt": "50000",
                "maxsaleamt": "5000000",
                "startSaleSearchDate": min_sale_date,
                "endSaleSearchDate": datetime.now().strftime("%Y-%m-%d"),
                "propertytype": prop_type,
                "pagesize": str(page_size),
                "page": str(page),
                "orderby": "SaleSearchDate desc",
            }
            try:
                data = _attom_get("/sale/snapshot", params, api_key)
            except HTTPError as e:
                if e.code == 404:
                    break  # no more results
                logger.warning("ATTOM API error for %s/%s page %d: %s", town, prop_type, page, e)
                break
            except Exception as e:
                logger.warning("ATTOM request failed for %s/%s: %s", town, prop_type, e)
                break

            properties = data.get("property", [])
            if not properties:
                break

            for prop in properties:
                sale = _parse_attom_property(prop, town, state)
                if sale and sale.source_ref not in seen_refs:
                    seen_refs.add(sale.source_ref)
                    all_sales.append(sale)

            # Check if there are more pages
            status = data.get("status", {})
            total = int(status.get("total", 0))
            if page * page_size >= total:
                break
            page += 1
            time.sleep(REQUEST_DELAY)

        time.sleep(REQUEST_DELAY)

    return all_sales[:max_records]


def run(
    *,
    dry_run: bool = False,
    max_per_town: int = 100,
    comps_path: Path = COMPS_PATH,
) -> dict:
    """Fetch sales for all target towns and merge into comp store."""
    api_key = os.environ.get("ATTOM_API_KEY", "")
    if not api_key:
        print("ERROR: ATTOM_API_KEY not set. Add it to .env file.")
        return {"error": "no_api_key"}

    store = JsonComparableSalesStore(comps_path)
    dataset = store.load()
    existing_refs = {s.source_ref for s in dataset.sales if s.source_ref}

    results: dict[str, dict] = {}
    total_new = 0
    total_fetched = 0

    for town, info in TARGET_TOWNS.items():
        print(f"\n--- {town} (ZIP {info['zip']}) ---")
        sales = fetch_town_sales(
            town=town,
            zip_code=info["zip"],
            state=info["state"],
            api_key=api_key,
            max_records=max_per_town,
        )
        new_sales = [s for s in sales if s.source_ref not in existing_refs]
        total_fetched += len(sales)
        total_new += len(new_sales)
        results[town] = {"fetched": len(sales), "new": len(new_sales)}
        print(f"  Fetched: {len(sales)}, New (not in store): {len(new_sales)}")

        if not dry_run:
            for sale in new_sales:
                dataset.sales.append(sale)
                existing_refs.add(sale.source_ref)

    if not dry_run and total_new > 0:
        dataset.metadata["attom_bulk_fetch_date"] = datetime.now().strftime("%Y-%m-%d")
        dataset.metadata["attom_bulk_records_added"] = total_new
        store.save(dataset)
        print(f"\nSaved {total_new} new records to {comps_path}")
    elif dry_run:
        print(f"\n[DRY RUN] Would add {total_new} new records")
    else:
        print("\nNo new records to add.")

    print(f"\nSummary: fetched {total_fetched} total, {total_new} new")
    for town, info in results.items():
        print(f"  {town}: {info['fetched']} fetched, {info['new']} new")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch ATTOM sales for target towns")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--max-per-town", type=int, default=100, help="Max records per town")
    parser.add_argument("--comps", type=str, default=str(COMPS_PATH), help="Path to comp store")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run(dry_run=args.dry_run, max_per_town=args.max_per_town, comps_path=Path(args.comps))

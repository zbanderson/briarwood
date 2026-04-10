"""
Enrich comp store records by looking up each address in ATTOM property detail.

Confirms/fills: beds, baths, sqft, year_built, lot_size, stories, garage_spaces,
latitude, longitude, property_type. Also fetches AVM estimate when available.

All ATTOM calls are cached, so re-running is cheap (only new lookups cost API calls).

Usage:
    python scripts/enrich_comps.py --dry-run          # Preview what would change
    python scripts/enrich_comps.py --write             # Enrich and save
    python scripts/enrich_comps.py --write --max 50    # Limit API calls
    python scripts/enrich_comps.py --write --with-avm  # Also fetch AVM valuations
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import briarwood  # noqa: F401 — triggers dotenv

from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore
from briarwood.data_sources.attom_client import AttomClient

logger = logging.getLogger(__name__)

COMPS_PATH = Path("data/comps/sales_comps.json")

# Fields we want to confirm/fill from ATTOM property detail
ENRICHABLE_FIELDS = ("beds", "baths", "sqft", "year_built", "lot_size", "stories",
                     "garage_spaces", "latitude", "longitude", "property_type")

# Map from ATTOM normalized field names to ComparableSale field names
ATTOM_TO_COMP = {
    "beds": "beds",
    "baths": "baths",
    "sqft": "sqft",
    "year_built": "year_built",
    "lot_size": "lot_size",
    "stories": "stories",
    "garage_spaces": "garage_spaces",
    "latitude": "latitude",
    "longitude": "longitude",
    "property_type": "property_type",
}

# ATTOM property type mapping to our schema values
ATTOM_PROP_TYPE_MAP = {
    "SFR": "single_family",
    "CONDO": "condo",
    "TOWNHOUSE": "townhouse",
    "APARTMENT": "multi_family",
    "MOBILE": "mobile",
}


def _normalize_prop_type(attom_type: str | None) -> str | None:
    if not attom_type:
        return None
    return ATTOM_PROP_TYPE_MAP.get(attom_type.upper(), attom_type.lower())


def _clean_address_for_lookup(address: str) -> str:
    """Strip unit numbers, address ranges, and other ATTOM-unfriendly patterns."""
    addr = address.strip()
    # Remove unit/apt/suite designations: "508 SEVENTH AVE UNIT 4" -> "508 SEVENTH AVE"
    addr = re.sub(r',?\s*(UNIT|APT|SUITE|STE|#)\s*\S+', '', addr, flags=re.IGNORECASE)
    # Remove trailing unit after comma: "601 MAIN ST, 2D" -> "601 MAIN ST"
    addr = re.sub(r',\s*[A-Z0-9]{1,4}\s*$', '', addr, flags=re.IGNORECASE)
    # Normalize address ranges: "1280-82 WASHINGTON AVE" -> "1280 WASHINGTON AVE"
    addr = re.sub(r'^(\d+)-\d+\s', r'\1 ', addr)
    return addr.strip()


def _build_address2(sale: ComparableSale) -> str:
    parts = [sale.town, sale.state]
    return ", ".join(p for p in parts if p)


def _needs_enrichment(sale: ComparableSale) -> list[str]:
    """Return list of fields that are missing/None on this comp."""
    missing = []
    for field in ENRICHABLE_FIELDS:
        val = getattr(sale, field, None)
        if val is None:
            missing.append(field)
    return missing


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        v = int(float(val))
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


def enrich_comps(
    *,
    comps_path: Path = COMPS_PATH,
    dry_run: bool = True,
    max_api_calls: int = 500,
    with_avm: bool = False,
) -> dict:
    store = JsonComparableSalesStore(comps_path)
    dataset = store.load()
    attom = AttomClient()

    total = len(dataset.sales)
    enriched_count = 0
    skipped_complete = 0
    skipped_no_address = 0
    api_calls = 0
    api_errors = 0
    cache_hits = 0
    fields_filled: dict[str, int] = {f: 0 for f in ENRICHABLE_FIELDS}
    fields_confirmed: dict[str, int] = {f: 0 for f in ENRICHABLE_FIELDS}
    avm_filled = 0

    for i, sale in enumerate(dataset.sales):
        if not sale.address or sale.address.strip() == "":
            skipped_no_address += 1
            continue

        missing = _needs_enrichment(sale)
        needs_avm = with_avm and not sale.source_provenance.get("avm_value")

        if not missing and not needs_avm:
            skipped_complete += 1
            continue

        if api_calls >= max_api_calls:
            break

        address1 = _clean_address_for_lookup(sale.address)
        address2 = _build_address2(sale)
        canonical_key = f"{address1}-{address2}".upper().replace(" ", "-")

        # Fetch property detail
        resp = attom.property_detail(canonical_key, address1=address1, address2=address2)
        api_calls += (0 if resp.from_cache else 1)
        cache_hits += (1 if resp.from_cache else 0)

        if resp.error:
            api_errors += 1
            continue

        data = resp.normalized_payload
        changed = False

        for attom_field, comp_field in ATTOM_TO_COMP.items():
            attom_val = data.get(attom_field)
            if attom_val is None:
                continue

            current_val = getattr(sale, comp_field, None)

            # Type-cast based on field
            if comp_field in ("beds", "sqft", "year_built", "garage_spaces"):
                attom_val = _safe_int(attom_val)
            elif comp_field in ("baths", "lot_size", "stories", "latitude", "longitude"):
                attom_val = _safe_float(attom_val)
            elif comp_field == "property_type":
                attom_val = _normalize_prop_type(str(attom_val))

            if attom_val is None:
                continue

            if current_val is None:
                # Fill missing field
                setattr(sale, comp_field, attom_val)
                fields_filled[comp_field] = fields_filled.get(comp_field, 0) + 1
                changed = True
            else:
                # Field already exists — record confirmation
                fields_confirmed[comp_field] = fields_confirmed.get(comp_field, 0) + 1

        # Optionally fetch AVM
        if needs_avm and api_calls < max_api_calls:
            avm_resp = attom.avm_detail(canonical_key, address1=address1, address2=address2)
            api_calls += (0 if avm_resp.from_cache else 1)
            cache_hits += (1 if avm_resp.from_cache else 0)

            if avm_resp.ok:
                avm_data = avm_resp.normalized_payload
                if avm_data.get("avm_value"):
                    sale.source_provenance = {
                        **sale.source_provenance,
                        "avm_value": avm_data["avm_value"],
                        "avm_low": avm_data.get("avm_low"),
                        "avm_high": avm_data.get("avm_high"),
                        "avm_confidence": avm_data.get("avm_confidence"),
                        "avm_source": "ATTOM",
                    }
                    avm_filled += 1
                    changed = True

        if changed:
            enriched_count += 1

        # Rate limit for non-cached calls
        if not resp.from_cache:
            time.sleep(0.4)

        # Progress update every 100 records
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{total} records, {api_calls} API calls, {enriched_count} enriched")

    if not dry_run and enriched_count > 0:
        dataset.metadata["attom_enrichment_date"] = time.strftime("%Y-%m-%d")
        dataset.metadata["attom_enrichment_records"] = enriched_count
        store.save(dataset)

    summary = {
        "total_records": total,
        "enriched": enriched_count,
        "skipped_complete": skipped_complete,
        "skipped_no_address": skipped_no_address,
        "api_calls": api_calls,
        "cache_hits": cache_hits,
        "api_errors": api_errors,
        "fields_filled": {k: v for k, v in fields_filled.items() if v > 0},
        "fields_confirmed": {k: v for k, v in fields_confirmed.items() if v > 0},
        "dry_run": dry_run,
    }
    if with_avm:
        summary["avm_filled"] = avm_filled

    return summary


def main():
    parser = argparse.ArgumentParser(description="Enrich comp store with ATTOM property details")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--write", action="store_true", help="Write enriched results back")
    parser.add_argument("--max", type=int, default=500, help="Max API calls (cached calls are free)")
    parser.add_argument("--with-avm", action="store_true", help="Also fetch AVM valuations")
    parser.add_argument("--comps", type=str, default=str(COMPS_PATH), help="Path to comp store")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    dry_run = not args.write
    if args.dry_run:
        dry_run = True

    summary = enrich_comps(
        comps_path=Path(args.comps),
        dry_run=dry_run,
        max_api_calls=args.max,
        with_avm=args.with_avm,
    )

    mode = "[DRY RUN]" if summary["dry_run"] else "[SAVED]"
    print(f"\n{mode} Enrichment Summary:")
    print(f"  Total records: {summary['total_records']}")
    print(f"  Enriched: {summary['enriched']}")
    print(f"  Already complete: {summary['skipped_complete']}")
    print(f"  No address: {summary['skipped_no_address']}")
    print(f"  API calls: {summary['api_calls']} ({summary['cache_hits']} cache hits)")
    print(f"  API errors: {summary['api_errors']}")
    if summary["fields_filled"]:
        print(f"  Fields filled:")
        for field, count in sorted(summary["fields_filled"].items(), key=lambda x: -x[1]):
            print(f"    {field}: {count}")
    if summary["fields_confirmed"]:
        print(f"  Fields confirmed (already had value):")
        for field, count in sorted(summary["fields_confirmed"].items(), key=lambda x: -x[1]):
            print(f"    {field}: {count}")
    if summary.get("avm_filled"):
        print(f"  AVM valuations added: {summary['avm_filled']}")


if __name__ == "__main__":
    main()

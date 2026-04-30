#!/usr/bin/env python3
"""
refresh_active_listings.py — Refresh data/comps/active_listings.json from SearchApi (Zillow).

Cycle 1c — Briarwood May 2026 launch readiness initiative (LAUNCH_CYCLE_1_NEXT_PROMPT.md).

For each of the 8 supported Monmouth coast towns, we:
  - Hit SearchApi's `engine=zillow` listings search (via SearchApiZillowClient.search_listings)
    using the town-keyed query form ("Belmar, NJ"), one page per town, listing_status="for_sale".
  - Canonicalize the resulting `town` strings against the canonical-spelling map below
    (e.g., "Avon-by-the-Sea" -> "Avon By The Sea").
  - Map the SearchApi candidate fields onto the existing active_listings.json schema:
        address, town, state, list_price, listing_status, property_type, beds, baths,
        sqft, year_built, lot_size, garage_spaces, days_on_market,
        architectural_style, condition_profile, capex_lane, source_name, source_ref,
        source_notes, notes
    Producer-side enrichment fields (architectural_style, condition_profile,
    capex_lane) are not present in raw Zillow data and stay null. We add three
    optional traceback fields: latitude, longitude, listing_url, fetched_at.
  - Stamp source_name="SearchApi", source_ref="Zillow".
  - Back up the existing JSON before overwriting; write streamingly so a partial
    run leaves valid JSON.
  - Log per-town counts and any fetch failures to data/eval/<dated>.jsonl.

Hard constraints (from launch prompt):
  - READ-ONLY on producer math (briarwood/modules/*, briarwood/agents/*,
    briarwood/synthesis/*). This script lives under scripts/data_quality/ and
    only IMPORTS from briarwood (does not modify it).
  - BACKUP FIRST. Never overwrite active_listings.json without snapshotting.
  - venv/bin/python3.

Usage:
    venv/bin/python3 -m scripts.data_quality.refresh_active_listings
    venv/bin/python3 -m scripts.data_quality.refresh_active_listings --dry-run
    venv/bin/python3 -m scripts.data_quality.refresh_active_listings --max-per-town 40
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import briarwood  # noqa: F401  # ensures .env is loaded so SEARCHAPI_API_KEY is set

from briarwood.data_sources.searchapi_zillow_client import (
    SearchApiZillowClient,
    SearchApiZillowListingCandidate,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_PATH = REPO_ROOT / "data" / "comps" / "active_listings.json"
BACKUP_PATH = REPO_ROOT / "data" / "comps" / "active_listings_pre_refresh_2026-04-30.json"
LOG_PATH = REPO_ROOT / "data" / "eval" / "active_listings_refresh_2026-04-30.jsonl"


# ---------------------------------------------------------------------------
# Town config
# ---------------------------------------------------------------------------
# Canonical town names (the form we write into active_listings.json).
# Source-of-truth: the prompt's hard constraint that "Wall Township" canonicalizes
# to "Wall". Note: this differs from briarwood/modules/town_aggregation_diagnostics.py
# (which uses "Wall Township") and scripts/ingest_excel_comps.py (also "Wall
# Township"). Following the prompt — canonicalization is part of this refresh.
SUPPORTED_TOWNS: list[str] = [
    "Belmar",
    "Manasquan",
    "Avon By The Sea",
    "Spring Lake",
    "Sea Girt",
    "Bradley Beach",
    "Asbury Park",
    "Wall",
]

# Search query string per canonical town (what we send to SearchApi).
# Zillow's location resolver accepts "City, ST"; for Wall Township the resolver
# expects the township-style spelling, so we query "Wall Township, NJ" but write
# back the canonical "Wall".
SEARCH_QUERY: dict[str, str] = {
    "Belmar": "Belmar, NJ",
    "Manasquan": "Manasquan, NJ",
    "Avon By The Sea": "Avon By The Sea, NJ",
    "Spring Lake": "Spring Lake, NJ",
    "Sea Girt": "Sea Girt, NJ",
    "Bradley Beach": "Bradley Beach, NJ",
    "Asbury Park": "Asbury Park, NJ",
    "Wall": "Wall Township, NJ",
}

# Lookup table: lowercased input -> canonical. Used to consolidate spellings
# returned by Zillow (e.g., "Avon-by-the-Sea") into a single canonical bucket.
TOWN_CANONICAL: dict[str, str] = {
    "belmar": "Belmar",
    "manasquan": "Manasquan",
    "avon by the sea": "Avon By The Sea",
    "avon-by-the-sea": "Avon By The Sea",
    "avon": "Avon By The Sea",
    "spring lake": "Spring Lake",
    "sea girt": "Sea Girt",
    "bradley beach": "Bradley Beach",
    "asbury park": "Asbury Park",
    "wall": "Wall",
    "wall township": "Wall",
}


def canonicalize_town(raw: str | None) -> str | None:
    """Map a raw Zillow town string to its canonical form.

    Returns None if `raw` is empty. Returns title-cased `raw` if not in the
    lookup (so unknown towns still get a sane default; we also surface them
    to stderr).
    """
    if not raw:
        return None
    key = raw.strip().lower()
    if key in TOWN_CANONICAL:
        return TOWN_CANONICAL[key]
    print(f"  [canonicalize] unknown town variant: {raw!r}", file=sys.stderr)
    return raw.strip()


# ---------------------------------------------------------------------------
# Property type mapping (Zillow -> existing schema literals)
# ---------------------------------------------------------------------------
# Existing active_listings.json uses human-readable strings: "Single Family",
# "Duplex", "Condo", "Multi Family". Zillow returns SCREAMING_SNAKE_CASE.
PROPERTY_TYPE_MAP: dict[str, str] = {
    "SINGLE_FAMILY": "Single Family",
    "MULTI_FAMILY": "Multi Family",
    "CONDO": "Condo",
    "TOWNHOUSE": "Townhouse",
    "APARTMENT": "Apartment",
    "MANUFACTURED": "Manufactured",
    "LOT": "Lot",
}


def normalize_property_type(zillow_home_type: str | None) -> str | None:
    if not zillow_home_type:
        return None
    return PROPERTY_TYPE_MAP.get(zillow_home_type.strip().upper(), zillow_home_type.strip().title())


# ---------------------------------------------------------------------------
# Listing-status mapping
# ---------------------------------------------------------------------------
# Existing schema uses lowercase enum-ish values: "for_sale", "pending",
# "coming_soon". Zillow returns "FOR_SALE", "PENDING", etc.
LISTING_STATUS_MAP: dict[str, str] = {
    "FOR_SALE": "for_sale",
    "PENDING": "pending",
    "COMING_SOON": "coming_soon",
    "FOR_RENT": "for_rent",
    "AUCTION": "auction",
    "FORECLOSURE": "foreclosure",
}


def normalize_listing_status(raw: str | None) -> str | None:
    if not raw:
        return "for_sale"
    return LISTING_STATUS_MAP.get(raw.strip().upper(), raw.strip().lower())


# ---------------------------------------------------------------------------
# Lot size: schema stores lot_size in ACRES (existing rows: 0.13, 0.169 etc.)
# ---------------------------------------------------------------------------
def to_acres(lot_sqft: float | None) -> float | None:
    if lot_sqft is None:
        return None
    return round(lot_sqft / 43_560.0, 4)


# ---------------------------------------------------------------------------
# Build one schema row
# ---------------------------------------------------------------------------
def candidate_to_row(
    candidate: SearchApiZillowListingCandidate,
    *,
    expected_canonical_town: str,
    fetched_at: str,
) -> dict[str, Any]:
    """Map a SearchApiZillowListingCandidate onto the active_listings.json row schema.

    Schema (from data/comps/active_listings.json existing rows):
      address, town, state, list_price, listing_status, property_type,
      architectural_style, condition_profile, capex_lane,
      source_name, source_ref, source_notes,
      days_on_market, beds, baths, sqft (optional), lot_size (acres),
      year_built, garage_spaces, notes
    Plus traceback fields we add for the refreshed batch:
      listing_url, latitude, longitude, fetched_at
    """
    canonical_town = canonicalize_town(candidate.town) or expected_canonical_town

    # Some Zillow rows return a town that matches the search query town
    # (e.g., querying "Belmar, NJ" returns rows in Belmar). When the row's
    # town is missing entirely, fall back to the queried town.
    if not canonical_town:
        canonical_town = expected_canonical_town

    return {
        "address": candidate.address,
        "town": canonical_town,
        "state": candidate.state or "NJ",
        "list_price": candidate.price,
        "listing_status": normalize_listing_status(candidate.listing_status),
        "property_type": normalize_property_type(candidate.home_type or candidate.property_type),
        "architectural_style": None,  # not in raw Zillow payload
        "condition_profile": None,    # producer-side enrichment, not raw
        "capex_lane": None,           # producer-side enrichment, not raw
        "source_name": "SearchApi",
        "source_ref": "Zillow",
        "source_notes": f"Refreshed via SearchApi engine=zillow query={expected_canonical_town!r} on {fetched_at}",
        "days_on_market": candidate.days_on_market,
        "beds": candidate.beds,
        "baths": candidate.baths,
        "sqft": candidate.sqft,
        "lot_size": to_acres(candidate.lot_sqft),
        "year_built": None,  # SearchApi candidate dataclass does not expose year_built
        "garage_spaces": None,  # not exposed on candidate dataclass
        "notes": None,
        # Refresh traceback fields (additive — won't break existing readers,
        # which iterate by key; downstream tooling that uses dataclass-strict
        # readers reads via JsonActiveListingStore which doesn't validate
        # extra keys).
        "listing_url": candidate.listing_url,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "zpid": candidate.zpid,
        "fetched_at": fetched_at,
    }


# ---------------------------------------------------------------------------
# Per-town fetch
# ---------------------------------------------------------------------------
def fetch_town(
    client: SearchApiZillowClient,
    canonical_town: str,
    *,
    max_results: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch active listings for one town. Return (rows, log_record)."""
    query = SEARCH_QUERY[canonical_town]
    fetch_start = time.time()
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = client.search_listings(
        query=query,
        page=1,
        max_results=max_results,
        listing_status="for_sale",
    )
    elapsed_ms = int((time.time() - fetch_start) * 1000)

    if response.error:
        return [], {
            "town": canonical_town,
            "query": query,
            "fetched_at": fetched_at,
            "from_cache": response.from_cache,
            "elapsed_ms": elapsed_ms,
            "count": 0,
            "error": response.error,
        }

    candidates = client.to_listing_candidates(response.normalized_payload)
    rows: list[dict[str, Any]] = []
    skipped_no_address = 0
    skipped_no_price = 0
    for cand in candidates:
        if not cand.address:
            skipped_no_address += 1
            continue
        if cand.price is None:
            # An active listing without a list_price isn't useful for comps math.
            skipped_no_price += 1
            continue
        rows.append(
            candidate_to_row(
                cand,
                expected_canonical_town=canonical_town,
                fetched_at=fetched_at,
            )
        )

    return rows, {
        "town": canonical_town,
        "query": query,
        "fetched_at": fetched_at,
        "from_cache": response.from_cache,
        "elapsed_ms": elapsed_ms,
        "count": len(rows),
        "raw_count": len(candidates),
        "skipped_no_address": skipped_no_address,
        "skipped_no_price": skipped_no_price,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def backup_existing(active_path: Path, backup_path: Path) -> None:
    if not active_path.exists():
        print(f"[backup] no existing file at {active_path}; nothing to back up.")
        return
    if backup_path.exists():
        print(f"[backup] backup already exists at {backup_path}; leaving in place.")
        return
    shutil.copy2(active_path, backup_path)
    print(f"[backup] {active_path} -> {backup_path}")


# ---------------------------------------------------------------------------
# Streaming write
# ---------------------------------------------------------------------------
def write_active_listings(rows: list[dict[str, Any]], path: Path) -> None:
    """Atomic-ish write: write to a sibling tmp, then os.replace.

    The whole file is small (sub-megabyte), so a single json.dump is fine —
    "streaming" here means: the on-disk file is never truncated mid-write.
    A crashed process either leaves the .tmp file (which we'd discard on
    rerun) or leaves the original active_listings.json untouched.
    """
    payload = {
        "metadata": {
            "dataset_name": "briarwood_monmouth_sales_v1",
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "refreshed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "SearchApi (Zillow)",
            "refresh_script": "scripts/data_quality/refresh_active_listings.py",
        },
        "listings": rows,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False))
    tmp.replace(path)


def write_log(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Spot-check
# ---------------------------------------------------------------------------
def spot_check(rows: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    if not rows:
        return []
    rng = random.Random(20260430)  # deterministic for reproducibility
    chosen = rng.sample(rows, k=min(n, len(rows)))
    return [
        {
            "address": r.get("address"),
            "town": r.get("town"),
            "list_price": r.get("list_price"),
            "listing_url": r.get("listing_url"),
        }
        for r in chosen
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0] if __doc__ else "")
    parser.add_argument(
        "--max-per-town",
        type=int,
        default=40,
        help="Max listings to take per town (default 40 — natural Zillow page is ~40).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and log, but do NOT overwrite active_listings.json.",
    )
    args = parser.parse_args()

    client = SearchApiZillowClient()
    if not client.is_configured:
        print("[fatal] SEARCHAPI_API_KEY is not configured. Aborting.", file=sys.stderr)
        return 2

    print(f"[refresh] starting at {datetime.now(timezone.utc).isoformat()}")
    print(f"[refresh] target towns: {SUPPORTED_TOWNS}")
    print(f"[refresh] max per town: {args.max_per_town}")
    print()

    # --- Step 1: backup existing file (skip in dry-run)
    if not args.dry_run:
        backup_existing(ACTIVE_PATH, BACKUP_PATH)

    # --- Step 2: per-town fetch loop
    all_rows: list[dict[str, Any]] = []
    log_records: list[dict[str, Any]] = []
    for town in SUPPORTED_TOWNS:
        print(f"[fetch] {town} ({SEARCH_QUERY[town]}) ...")
        rows, log_record = fetch_town(client, town, max_results=args.max_per_town)
        log_records.append(log_record)
        all_rows.extend(rows)
        marker = "OK " if log_record["count"] >= 10 else "LOW"
        cache_marker = " (cached)" if log_record.get("from_cache") else ""
        err = f" — error: {log_record['error']}" if log_record.get("error") else ""
        print(
            f"  {marker} count={log_record['count']:3d} "
            f"raw={log_record.get('raw_count', 0):3d} "
            f"elapsed={log_record['elapsed_ms']}ms{cache_marker}{err}"
        )

    # --- Step 3: write log
    write_log(log_records, LOG_PATH)
    print(f"[log] per-town log -> {LOG_PATH}")

    # --- Step 4: write active_listings.json (unless dry-run)
    if args.dry_run:
        print("[dry-run] skipping write to active_listings.json")
    else:
        write_active_listings(all_rows, ACTIVE_PATH)
        print(f"[write] {ACTIVE_PATH} ({len(all_rows)} listings across {len(SUPPORTED_TOWNS)} towns)")

    # --- Step 5: per-town summary (final breakdown after canonicalization)
    print()
    print("[summary] per-town listing counts (post-canonicalization):")
    bucket: dict[str, int] = {t: 0 for t in SUPPORTED_TOWNS}
    extra: dict[str, int] = {}
    for row in all_rows:
        t = row["town"]
        if t in bucket:
            bucket[t] += 1
        else:
            extra[t] = extra.get(t, 0) + 1
    for town in SUPPORTED_TOWNS:
        n = bucket[town]
        flag = "" if n >= 10 else "  <-- BELOW THRESHOLD"
        print(f"  {town:24s} {n:3d}{flag}")
    if extra:
        print()
        print("[summary] unexpected non-target towns in result set:")
        for t, n in sorted(extra.items()):
            print(f"  {t:24s} {n:3d}")

    # --- Step 6: spot-check
    spot = spot_check(all_rows, n=5)
    print()
    print("[spot-check] 5 random listings (manually verify against Zillow):")
    for s in spot:
        print(f"  - {s['address']} | ${s['list_price']:,} | {s['listing_url']}" if s.get("list_price") else f"  - {s['address']} | (no price) | {s['listing_url']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""One-shot diagnostic: probe SearchApi Zillow SOLD inventory for target towns.

Cycle 1.5 of CMA_HANDOFF_PLAN.md. The plan's Cycle 2 invariants assume
``listing_status="sold"`` returns useful data for our six Monmouth County
target markets. This script verifies that assumption before the unify work
starts.

Run::

    python scripts/probe_searchapi_sold.py

Reads the SearchApi key from ``SEARCHAPI_API_KEY`` (or ``SEARCHAPI_KEY``).
Issues 6 SOLD calls (one per target town) plus 6 ACTIVE calls for a
provenance/coverage comparison. Writes raw results to
``data/diagnostics/searchapi_sold_probe_2026-04-26.json`` and prints a
per-town summary to stdout.
"""

from __future__ import annotations

import json
from pathlib import Path

# Triggers dotenv side-effect so SEARCHAPI_API_KEY loads from .env.
import briarwood  # noqa: F401

from briarwood.data_sources.searchapi_zillow_client import SearchApiZillowClient


TARGET_TOWNS: list[tuple[str, str]] = [
    ("Avon By The Sea", "NJ"),
    ("Belmar", "NJ"),
    ("Bradley Beach", "NJ"),
    ("Manasquan", "NJ"),
    ("Sea Girt", "NJ"),
    ("Spring Lake", "NJ"),
]

OUTPUT_JSON = Path("data/diagnostics/searchapi_sold_probe_2026-04-26.json")
SAVED_COMPS = Path("data/comps/sales_comps.json")


def probe_listings(
    client: SearchApiZillowClient,
    town: str,
    state: str,
    listing_status: str,
) -> dict[str, object]:
    """Issue one search for the given listing_status."""
    response = client.search_listings(
        query=f"{town}, {state}",
        listing_status=listing_status,
        max_results=20,
    )
    candidates = (
        client.to_listing_candidates(response.normalized_payload)
        if response.ok
        else []
    )
    rows = [
        {
            "address": cand.address,
            "town": cand.town,
            "state": cand.state,
            "zip_code": cand.zip_code,
            "price": cand.price,
            "beds": cand.beds,
            "baths": cand.baths,
            "sqft": cand.sqft,
            "property_type": cand.property_type,
            "listing_status": cand.listing_status,
            "zpid": cand.zpid,
            "listing_url": cand.listing_url,
        }
        for cand in candidates
    ]
    return {
        "town": town,
        "state": state,
        "listing_status_query": listing_status,
        "ok": response.ok,
        "from_cache": response.from_cache,
        "error": response.error,
        "row_count": len(rows),
        "rows": rows,
        # Capture the raw payload's raw status field for any rows the
        # normalizer didn't carry through, so we can see what Zillow
        # actually returned.
        "raw_payload_keys": (
            sorted(response.normalized_payload.keys())
            if isinstance(response.normalized_payload, dict)
            else None
        ),
    }


def saved_sales_summary(town: str, state: str) -> dict[str, object]:
    """Per-town counts and date range from the saved sales_comps.json."""
    if not SAVED_COMPS.exists():
        return {"saved_count": 0, "min_sale_date": None, "max_sale_date": None}
    data = json.loads(SAVED_COMPS.read_text())
    sales = [
        sale
        for sale in data.get("sales", [])
        if sale.get("town") == town and sale.get("state") == state
    ]
    sale_dates = sorted(s.get("sale_date") for s in sales if s.get("sale_date"))
    return {
        "saved_count": len(sales),
        "min_sale_date": sale_dates[0] if sale_dates else None,
        "max_sale_date": sale_dates[-1] if sale_dates else None,
    }


def aggregates(rows: list[dict[str, object]]) -> dict[str, object]:
    prices = [r["price"] for r in rows if isinstance(r["price"], (int, float))]
    beds = [r["beds"] for r in rows if isinstance(r["beds"], int)]
    sqfts = [r["sqft"] for r in rows if isinstance(r["sqft"], int)]
    return {
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "price_median": sorted(prices)[len(prices) // 2] if prices else None,
        "beds_distinct": sorted(set(beds)),
        "sqft_min": min(sqfts) if sqfts else None,
        "sqft_max": max(sqfts) if sqfts else None,
        "missing_price_count": sum(
            1 for r in rows if not isinstance(r["price"], (int, float))
        ),
        "missing_beds_count": sum(1 for r in rows if not isinstance(r["beds"], int)),
        "missing_sqft_count": sum(1 for r in rows if not isinstance(r["sqft"], int)),
    }


def main() -> int:
    client = SearchApiZillowClient()
    if not client.is_configured:
        print("ERROR: SearchApiZillowClient is not configured.")
        print("       Set SEARCHAPI_API_KEY (or SEARCHAPI_KEY) in .env or shell.")
        return 1

    results: list[dict[str, object]] = []
    print(f"Probing {len(TARGET_TOWNS)} towns × 2 listing_status values...\n")

    for town, state in TARGET_TOWNS:
        print(f"  {town}, {state}")
        sold = probe_listings(client, town, state, "sold")
        active = probe_listings(client, town, state, "for_sale")
        saved = saved_sales_summary(town, state)
        record = {
            "town": town,
            "state": state,
            "sold": sold,
            "active": active,
            "saved": saved,
            "sold_aggregates": aggregates(sold["rows"]),
            "active_aggregates": aggregates(active["rows"]),
        }
        results.append(record)
        sold_tag = "cached" if sold["from_cache"] else "fresh"
        active_tag = "cached" if active["from_cache"] else "fresh"
        print(
            f"    SOLD     → {sold['row_count']:>3} rows ({sold_tag})"
            + (f"  err: {sold['error']}" if sold["error"] else "")
        )
        print(
            f"    ACTIVE   → {active['row_count']:>3} rows ({active_tag})"
            + (f"  err: {active['error']}" if active["error"] else "")
        )
        print(
            f"    saved    → {saved['saved_count']:>3} rows"
            + (
                f"  ({saved['min_sale_date']} → {saved['max_sale_date']})"
                if saved["min_sale_date"]
                else ""
            )
        )
        print()

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"Raw results written to {OUTPUT_JSON}")

    # Quick aggregate summary across all towns.
    total_sold = sum(r["sold"]["row_count"] for r in results)
    total_active = sum(r["active"]["row_count"] for r in results)
    total_saved = sum(r["saved"]["saved_count"] for r in results)
    print()
    print(f"Across {len(results)} towns: SOLD={total_sold}  ACTIVE={total_active}  SAVED={total_saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

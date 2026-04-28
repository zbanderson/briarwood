"""Regression tests for CMA Phase 4a Cycle 3a normalizer extension.

Pins the new Zillow-rich fields (`date_sold`, `lat`/`lon`, `lot_sqft`,
`tax_assessed_value`, `zestimate`, `rent_zestimate`, `days_on_market`,
`home_type`, `listing_type`, `broker`) round-trip from the raw SearchApi
payload through `_normalize_listing` into `SearchApiZillowListingCandidate`.

Test fixtures are the actual cached raw payloads from the 2026-04-26
SearchApi SOLD probe (`data/cache/searchapi_zillow/*.json`). If the
SearchApi response shape changes upstream, these tests catch it before
production silently drops fields again.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from briarwood.data_sources.searchapi_zillow_client import (
    SearchApiZillowClient,
    _normalize_lot_size,
    _normalize_listing,
)


CACHE_DIR = Path("data/cache/searchapi_zillow")


def _find_cache_file(*, query_prefix: str, listing_status: str) -> Path:
    """Locate the cached raw payload matching the given query + status."""
    for path in CACHE_DIR.glob("*.json"):
        blob = json.loads(path.read_text())
        params = (blob.get("raw_payload") or {}).get("search_parameters") or {}
        if (
            str(params.get("q", "")).lower().startswith(query_prefix.lower())
            and params.get("listing_status") == listing_status
        ):
            return path
    raise FileNotFoundError(
        f"No cache file found for query='{query_prefix}*' status='{listing_status}'"
    )


def _belmar_sold_raw_row() -> dict:
    """First raw SOLD property from the Belmar probe — known to have full
    Zillow-rich data including date_sold, lat/lon, tax_assessed_value, etc."""
    path = _find_cache_file(query_prefix="Belmar", listing_status="sold")
    blob = json.loads(path.read_text())
    return blob["raw_payload"]["properties"][0]


# ---------------------------------------------------------------------------
# _normalize_lot_size — handles the Zillow acres-vs-sqft quirk
# ---------------------------------------------------------------------------


class NormalizeLotSizeTests(unittest.TestCase):
    def test_acres_unit_converts_to_sqft(self):
        # Probe row: lot_sqft=0.33 with lot_area_unit="acres" → 14,374.8 sqft.
        result = _normalize_lot_size({"lot_sqft": 0.33, "lot_area_unit": "acres"}, {})
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 14_374.8, places=1)

    def test_explicit_sqft_unit_is_passthrough(self):
        result = _normalize_lot_size(
            {"lot_sqft": 14_375, "lot_area_unit": "sqft"}, {}
        )
        self.assertEqual(result, 14_375.0)

    def test_small_value_no_unit_assumed_acres(self):
        # Defensive: a value < 100 with no unit specified is almost certainly
        # acres. SearchApi's behavior is inconsistent on whether the unit
        # field is present.
        result = _normalize_lot_size({"lot_sqft": 0.5}, {})
        self.assertEqual(result, 21_780.0)  # 0.5 acres × 43560

    def test_large_value_no_unit_assumed_sqft(self):
        result = _normalize_lot_size({"lot_sqft": 5_000}, {})
        self.assertEqual(result, 5_000.0)

    def test_legacy_lot_size_field_preferred(self):
        # If both lot_size (legacy SearchApi) and lot_sqft (Zillow direct)
        # are present, prefer the legacy field — that's the production-tested
        # path.
        result = _normalize_lot_size(
            {"lot_size": 5_001, "lot_sqft": 0.11, "lot_area_unit": "acres"}, {}
        )
        self.assertEqual(result, 5_001.0)

    def test_missing_returns_none(self):
        self.assertIsNone(_normalize_lot_size({}, {}))


# ---------------------------------------------------------------------------
# _normalize_listing — direct extraction from raw payload
# ---------------------------------------------------------------------------


class NormalizeListingTests(unittest.TestCase):
    """Verify the new fields populate from the actual probe payload."""

    def test_belmar_sold_row_populates_all_new_fields(self):
        raw_row = _belmar_sold_raw_row()
        normalized = _normalize_listing(
            raw_row, source_url="", address_hint="Belmar, NJ"
        )
        # Probe row 0: 1209 16th Ave, Belmar
        self.assertIsNotNone(normalized.get("date_sold"))
        self.assertIn("2026", str(normalized["date_sold"]))
        self.assertIsNotNone(normalized.get("latitude"))
        self.assertIsNotNone(normalized.get("longitude"))
        self.assertIsInstance(normalized["latitude"], float)
        self.assertIsInstance(normalized["longitude"], float)
        self.assertIsNotNone(normalized.get("tax_assessed_value"))
        self.assertGreater(normalized["tax_assessed_value"], 0)
        self.assertIsNotNone(normalized.get("zestimate"))
        self.assertGreater(normalized["zestimate"], 0)
        self.assertIsNotNone(normalized.get("home_type"))
        self.assertIn(normalized["home_type"], ("SINGLE_FAMILY", "MULTI_FAMILY", "CONDO", "TOWNHOUSE"))
        self.assertIsNotNone(normalized.get("listing_type"))

    def test_belmar_sold_row_lot_sqft_converted_from_acres(self):
        raw_row = _belmar_sold_raw_row()
        normalized = _normalize_listing(
            raw_row, source_url="", address_hint="Belmar, NJ"
        )
        # Probe row 0: lot_sqft=0.33 acres in raw → ~14,375 sqft normalized.
        self.assertIsNotNone(normalized.get("lot_sqft"))
        # Sanity check: the normalized value should be > 1000 (no real lot
        # is < 1000 sqft for residential single-family in our markets).
        self.assertGreater(normalized["lot_sqft"], 1_000)

    def test_belmar_sold_row_days_on_market_from_raw_days_on_zillow(self):
        raw_row = _belmar_sold_raw_row()
        normalized = _normalize_listing(
            raw_row, source_url="", address_hint="Belmar, NJ"
        )
        # Probe row 0 had days_on_zillow=6.
        self.assertIsNotNone(normalized.get("days_on_market"))
        self.assertGreaterEqual(normalized["days_on_market"], 0)

    def test_existing_fields_still_extract(self):
        """Don't regress the original normalizer behavior."""
        raw_row = _belmar_sold_raw_row()
        normalized = _normalize_listing(
            raw_row, source_url="", address_hint="Belmar, NJ"
        )
        self.assertIsNotNone(normalized.get("address"))
        self.assertIsNotNone(normalized.get("zpid"))
        self.assertIsNotNone(normalized.get("price"))
        self.assertIsNotNone(normalized.get("beds"))
        self.assertIsNotNone(normalized.get("baths"))

    def test_missing_optional_fields_normalize_to_none(self):
        # Build a minimal raw row missing the new fields. Should not raise.
        raw_row = {
            "address": "123 Test St, Belmar, NJ",
            "extracted_price": 800_000.0,
            "beds": 3,
            "baths": 2,
        }
        normalized = _normalize_listing(
            raw_row, source_url="", address_hint="Belmar"
        )
        self.assertIsNone(normalized.get("date_sold"))
        self.assertIsNone(normalized.get("latitude"))
        self.assertIsNone(normalized.get("longitude"))
        self.assertIsNone(normalized.get("tax_assessed_value"))
        self.assertIsNone(normalized.get("zestimate"))
        self.assertIsNone(normalized.get("home_type"))
        self.assertIsNone(normalized.get("listing_type"))
        self.assertIsNone(normalized.get("broker"))
        self.assertIsNone(normalized.get("lot_sqft"))


# ---------------------------------------------------------------------------
# to_listing_candidates — end-to-end round-trip
# ---------------------------------------------------------------------------


class ToListingCandidatesTests(unittest.TestCase):
    """Build a fresh normalized payload (bypassing cached normalized_payloads
    that were produced before Cycle 3a) and verify the new candidate fields
    populate."""

    def test_round_trip_through_normalizer_to_candidate(self):
        path = _find_cache_file(query_prefix="Belmar", listing_status="sold")
        raw_payload = json.loads(path.read_text())["raw_payload"]
        properties = raw_payload.get("properties", [])
        self.assertGreater(len(properties), 0, "fixture should have properties")

        # Re-normalize using the new code path (cached normalized_payloads
        # were built by the OLD normalizer and don't carry the new fields).
        results = [
            _normalize_listing(p, source_url="", address_hint="Belmar, NJ")
            for p in properties[:5]
        ]
        normalized_payload = {"query": "Belmar, NJ", "page": 1, "results": results}

        client = SearchApiZillowClient(api_key="dummy")
        candidates = client.to_listing_candidates(normalized_payload)
        self.assertEqual(len(candidates), 5)

        # First candidate should have the rich Zillow fields populated.
        cand = candidates[0]
        self.assertIsNotNone(cand.date_sold)
        self.assertIsNotNone(cand.latitude)
        self.assertIsNotNone(cand.longitude)
        self.assertIsNotNone(cand.tax_assessed_value)
        self.assertIsNotNone(cand.zestimate)
        self.assertIsNotNone(cand.home_type)
        self.assertIsNotNone(cand.listing_type)
        self.assertIsNotNone(cand.lot_sqft)
        self.assertIsNotNone(cand.days_on_market)

    def test_field_coverage_matches_probe_findings(self):
        """Probe found 100% date_sold + lat/lon coverage and 92%+
        tax_assessed/zestimate coverage. Pin those expectations against the
        Belmar fixture so a SearchApi schema change shows up."""
        path = _find_cache_file(query_prefix="Belmar", listing_status="sold")
        raw_payload = json.loads(path.read_text())["raw_payload"]
        properties = raw_payload.get("properties", [])
        results = [
            _normalize_listing(p, source_url="", address_hint="Belmar, NJ")
            for p in properties
        ]
        normalized_payload = {"query": "Belmar, NJ", "page": 1, "results": results}
        client = SearchApiZillowClient(api_key="dummy")
        candidates = client.to_listing_candidates(normalized_payload)
        n = len(candidates)
        self.assertGreater(n, 30, "expected ~41 SOLD rows from probe fixture")

        # 100%: date_sold, latitude, longitude per probe.
        self.assertEqual(
            sum(1 for c in candidates if c.date_sold), n, "date_sold should be 100%"
        )
        self.assertEqual(
            sum(1 for c in candidates if c.latitude is not None), n,
            "latitude should be 100%",
        )
        self.assertEqual(
            sum(1 for c in candidates if c.longitude is not None), n,
            "longitude should be 100%",
        )

        # Probe-wide coverage was ~92% for tax_assessed_value and ~93% for
        # zestimate; per-town varies (Belmar zestimate measured at 83%).
        # Pin at 75% as a defensive floor — well above current observation,
        # surfaces a regression if the SearchApi schema starts dropping the
        # field.
        self.assertGreaterEqual(
            sum(1 for c in candidates if c.tax_assessed_value is not None),
            int(n * 0.75),
        )
        self.assertGreaterEqual(
            sum(1 for c in candidates if c.zestimate is not None),
            int(n * 0.75),
        )


if __name__ == "__main__":
    unittest.main()

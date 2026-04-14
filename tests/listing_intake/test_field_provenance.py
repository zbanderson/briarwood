"""Phase 3 tests: listing-intake field provenance now uses per-method confidence.

The previous single-hardcoded-0.88 is gone. Each field is tagged with an
InferenceMethod, which maps to a baseline confidence and a VerifiedStatus.
"""
from __future__ import annotations

import unittest

from briarwood.listing_intake.schemas import (
    NormalizedPropertyData,
    PriceHistoryEntry,
)
from briarwood.schemas import InferenceMethod, VerifiedStatus


def _normalized(**overrides) -> NormalizedPropertyData:
    base = dict(
        address="12 Ocean Ave",
        price=875_000.0,
        beds=3,
        baths=2.0,
        sqft=1_600,
        lot_sqft=6_500,
        property_type="single_family",
        year_built=1995,
        taxes_annual=9_200.0,
        source="zillow",
        source_url="https://example.com/listing/123",
        town="Avon By The Sea",
        state="NJ",
    )
    base.update(overrides)
    return NormalizedPropertyData(**base)


class FieldProvenanceTests(unittest.TestCase):
    def test_extracted_fields_get_extracted_method(self) -> None:
        data = _normalized()
        canonical = data.to_canonical_input()
        provenance = canonical.source_metadata.field_provenance

        # Verbatim fields → EXTRACTED
        self.assertEqual(provenance["address"].inference_method, InferenceMethod.EXTRACTED)
        self.assertEqual(provenance["beds"].inference_method, InferenceMethod.EXTRACTED)
        self.assertEqual(provenance["sqft"].inference_method, InferenceMethod.EXTRACTED)
        self.assertEqual(provenance["purchase_price"].inference_method, InferenceMethod.EXTRACTED)

        # Baseline confidence for EXTRACTED is 0.90 (no longer hardcoded 0.88).
        self.assertAlmostEqual(provenance["address"].confidence, 0.90, places=2)

    def test_lot_size_is_derived(self) -> None:
        data = _normalized()
        canonical = data.to_canonical_input()
        provenance = canonical.source_metadata.field_provenance

        # lot_size is computed from lot_sqft → DERIVED (0.80).
        self.assertIn("lot_size", provenance)
        self.assertEqual(provenance["lot_size"].inference_method, InferenceMethod.DERIVED)
        self.assertAlmostEqual(provenance["lot_size"].confidence, 0.80, places=2)

    def test_listing_date_inferred_when_from_days_on_market(self) -> None:
        # days_on_market set, no real list event in price_history →
        # listing_date is computed as today - dom → INFERRED.
        data = _normalized(days_on_market=14, price_history=[])
        canonical = data.to_canonical_input()
        provenance = canonical.source_metadata.field_provenance

        self.assertIn("listing_date", provenance)
        self.assertEqual(provenance["listing_date"].inference_method, InferenceMethod.INFERRED)
        self.assertAlmostEqual(provenance["listing_date"].confidence, 0.60, places=2)
        self.assertEqual(provenance["listing_date"].verified_status, VerifiedStatus.ESTIMATED)

    def test_listing_date_extracted_when_from_real_list_event(self) -> None:
        # A real "Listed" event with a parseable date → EXTRACTED.
        data = _normalized(
            price_history=[PriceHistoryEntry(date="2026-01-15", event="Listed", price=875_000.0)],
        )
        canonical = data.to_canonical_input()
        provenance = canonical.source_metadata.field_provenance

        self.assertIn("listing_date", provenance)
        self.assertEqual(
            provenance["listing_date"].inference_method, InferenceMethod.EXTRACTED
        )

    def test_missing_fields_do_not_get_provenance_entries(self) -> None:
        data = _normalized(capex_lane=None, condition_profile=None)
        canonical = data.to_canonical_input()
        provenance = canonical.source_metadata.field_provenance

        self.assertNotIn("capex_lane", provenance)
        self.assertNotIn("condition_profile", provenance)


if __name__ == "__main__":
    unittest.main()

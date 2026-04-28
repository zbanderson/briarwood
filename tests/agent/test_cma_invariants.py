"""Regression tests for CMA Phase 4a Cycle 2 invariants.

Pins the constants in ``briarwood/modules/cma_invariants.py`` so future
drift fails CI. Pins ``validate_cma_result`` and
``is_outlier_by_tax_assessment`` against fixtures derived from the
2026-04-26 SearchApi SOLD probe (Belmar $8K and Avon $34K outliers, plus
mixed SOLD/ACTIVE comp sets).
"""

from __future__ import annotations

import unittest

from briarwood.agent.tools import CMAResult, ComparableProperty
from briarwood.modules import cma_invariants


# ---------------------------------------------------------------------------
# Constant pins
# ---------------------------------------------------------------------------


class CMAInvariantConstantsTests(unittest.TestCase):
    """One assertion per constant. If a default changes, this test must be
    updated deliberately so the change shows up in code review."""

    def test_min_total_comp_count_default(self):
        self.assertEqual(cma_invariants.MIN_TOTAL_COMP_COUNT, 5)

    def test_min_sold_count_default(self):
        self.assertEqual(cma_invariants.MIN_SOLD_COUNT, 5)

    def test_min_active_count_default(self):
        self.assertEqual(cma_invariants.MIN_ACTIVE_COUNT, 3)

    def test_max_distance_same_town_default(self):
        self.assertEqual(cma_invariants.MAX_DISTANCE_MILES_SAME_TOWN, 2.0)

    def test_max_distance_cross_town_default(self):
        self.assertEqual(cma_invariants.MAX_DISTANCE_MILES_CROSS_TOWN, 3.0)

    def test_sold_age_cap_months_default(self):
        # 18 months matches SearchApi's natural SOLD window (probe finding).
        self.assertEqual(cma_invariants.SOLD_AGE_CAP_MONTHS, 18)

    def test_active_dom_cap_days_default(self):
        # 6 months on market = stale ask.
        self.assertEqual(cma_invariants.ACTIVE_DOM_CAP_DAYS, 180)

    def test_confidence_floor_default(self):
        self.assertEqual(cma_invariants.CONFIDENCE_FLOOR, 0.45)

    def test_tax_assessed_band_default(self):
        # Catches Belmar $8K (~0.018x) and Avon $34K (~0.05x) probe outliers.
        self.assertEqual(cma_invariants.TAX_ASSESSED_VS_PRICE_BAND, (0.4, 4.0))

    def test_sold_weight_default(self):
        self.assertEqual(cma_invariants.SOLD_WEIGHT, 1.0)

    def test_active_weight_default(self):
        # Asks weighted at half SOLD; tunable for scarcity markets.
        self.assertEqual(cma_invariants.ACTIVE_WEIGHT, 0.5)

    def test_live_empty_warning_requires_all_sources_empty(self):
        self.assertTrue(
            cma_invariants.LIVE_EMPTY_USER_WARNING_REQUIRES_ALL_SOURCES_EMPTY
        )


# ---------------------------------------------------------------------------
# is_outlier_by_tax_assessment
# ---------------------------------------------------------------------------


class TaxAssessmentOutlierTests(unittest.TestCase):
    def test_belmar_eight_thousand_outlier_is_dropped(self):
        # Probe: Belmar SOLD min was $8,000 with tax_assessed ~$453K → 0.018x ratio.
        # Should be flagged as outlier.
        self.assertTrue(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=8_000.0,
                tax_assessed_value=453_600.0,
            )
        )

    def test_avon_thirty_four_thousand_outlier_is_dropped(self):
        # Probe: Avon SOLD min was $34K, likely against a tax_assessed ~$700K → 0.05x.
        self.assertTrue(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=34_000.0,
                tax_assessed_value=700_000.0,
            )
        )

    def test_normal_arms_length_sale_is_not_outlier(self):
        # Belmar 1209 16th Ave probe row: $800K sale, $453.6K tax_assessed → 1.76x.
        # In-band.
        self.assertFalse(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=800_000.0,
                tax_assessed_value=453_600.0,
            )
        )

    def test_high_end_within_band_is_not_outlier(self):
        # 3.9x ratio — in-band (under 4.0 ceiling).
        self.assertFalse(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=1_950_000.0,
                tax_assessed_value=500_000.0,
            )
        )

    def test_above_high_band_is_outlier(self):
        # 5x ratio — above 4.0 ceiling. Could be a remodel-then-flip with
        # stale assessment, but flagging is the conservative call until we
        # have a renovation-aware pass.
        self.assertTrue(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=2_500_000.0,
                tax_assessed_value=500_000.0,
            )
        )

    def test_missing_tax_assessed_value_is_not_dropped(self):
        # ~8% of probe rows lack tax_assessed_value. Don't drop them for
        # missing data.
        self.assertFalse(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=800_000.0,
                tax_assessed_value=None,
            )
        )

    def test_missing_price_is_not_dropped(self):
        self.assertFalse(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=None,
                tax_assessed_value=500_000.0,
            )
        )

    def test_zero_tax_assessed_value_is_not_dropped(self):
        # Defensive: zero or negative inputs treated as missing data.
        self.assertFalse(
            cma_invariants.is_outlier_by_tax_assessment(
                extracted_price=800_000.0,
                tax_assessed_value=0.0,
            )
        )


# ---------------------------------------------------------------------------
# validate_cma_result
# ---------------------------------------------------------------------------


def _make_comp(
    *,
    property_id: str,
    listing_status: str | None = None,
    address: str | None = None,
) -> ComparableProperty:
    """Minimal ComparableProperty fixture for invariant tests."""
    return ComparableProperty(
        property_id=property_id,
        address=address or f"{property_id} Test St",
        town="Belmar",
        state="NJ",
        beds=3,
        baths=2.0,
        ask_price=800_000.0,
        blocks_to_beach=None,
        listing_status=listing_status,
    )


def _make_cma_result(comps: list[ComparableProperty]) -> CMAResult:
    return CMAResult(
        property_id="subject-1",
        address="1008 14th Ave, Belmar, NJ 07719",
        town="Belmar",
        state="NJ",
        ask_price=767_000.0,
        fair_value_base=720_767.0,
        value_low=700_000.0,
        value_high=750_000.0,
        pricing_view=None,
        primary_value_source=None,
        comp_selection_summary=None,
        comps=comps,
        confidence_notes=[],
        missing_fields=[],
    )


class ValidateCMAResultTests(unittest.TestCase):
    def test_passes_when_well_above_floors(self):
        comps = (
            [_make_comp(property_id=f"s{i}", listing_status="sold") for i in range(6)]
            + [_make_comp(property_id=f"a{i}", listing_status="active") for i in range(4)]
        )
        result = _make_cma_result(comps)
        validation = cma_invariants.validate_cma_result(result)
        self.assertTrue(validation.passes)
        self.assertEqual(validation.total_count, 10)
        self.assertEqual(validation.sold_count, 6)
        self.assertEqual(validation.active_count, 4)
        self.assertIsNone(validation.suppressed_reason)
        self.assertEqual(validation.qualifications, ())

    def test_suppressed_when_below_total_floor(self):
        comps = [_make_comp(property_id=f"s{i}", listing_status="sold") for i in range(3)]
        result = _make_cma_result(comps)
        validation = cma_invariants.validate_cma_result(result)
        self.assertFalse(validation.passes)
        self.assertEqual(validation.total_count, 3)
        self.assertIn("insufficient comps", validation.suppressed_reason)

    def test_active_only_qualification_when_sold_below_floor(self):
        # 2 SOLD + 4 ACTIVE = 6 total (passes total floor) but SOLD < 5
        # triggers active-only qualification.
        comps = (
            [_make_comp(property_id=f"s{i}", listing_status="sold") for i in range(2)]
            + [_make_comp(property_id=f"a{i}", listing_status="active") for i in range(4)]
        )
        result = _make_cma_result(comps)
        validation = cma_invariants.validate_cma_result(result)
        self.assertTrue(validation.passes)
        self.assertEqual(validation.sold_count, 2)
        self.assertTrue(
            any("active-only" in q for q in validation.qualifications),
            f"expected active-only qualification, got {validation.qualifications}",
        )

    def test_no_competition_qualification_when_active_below_floor(self):
        # 5 SOLD + 1 ACTIVE = 6 total (passes total floor) but ACTIVE < 3
        # triggers no-competition qualification.
        comps = (
            [_make_comp(property_id=f"s{i}", listing_status="sold") for i in range(5)]
            + [_make_comp(property_id="a0", listing_status="active")]
        )
        result = _make_cma_result(comps)
        validation = cma_invariants.validate_cma_result(result)
        self.assertTrue(validation.passes)
        self.assertEqual(validation.active_count, 1)
        self.assertTrue(
            any("no competition signal" in q for q in validation.qualifications),
            f"expected no-competition qualification, got {validation.qualifications}",
        )

    def test_dropped_outliers_count_propagates(self):
        comps = [_make_comp(property_id=f"s{i}", listing_status="sold") for i in range(6)]
        result = _make_cma_result(comps)
        validation = cma_invariants.validate_cma_result(result, dropped_outliers=2)
        self.assertEqual(validation.dropped_outliers, 2)

    def test_unknown_listing_status_not_counted_as_either(self):
        # Comps with listing_status=None (legacy or saved-only) count toward
        # total but not toward sold/active. Mixed set: 2 sold + 1 active +
        # 3 unknown = 6 total but only 2 SOLD and 1 ACTIVE.
        comps = (
            [_make_comp(property_id=f"s{i}", listing_status="sold") for i in range(2)]
            + [_make_comp(property_id="a0", listing_status="active")]
            + [_make_comp(property_id=f"u{i}", listing_status=None) for i in range(3)]
        )
        result = _make_cma_result(comps)
        validation = cma_invariants.validate_cma_result(result)
        self.assertTrue(validation.passes)  # total >= 5
        self.assertEqual(validation.total_count, 6)
        self.assertEqual(validation.sold_count, 2)
        self.assertEqual(validation.active_count, 1)
        # Both qualifications should fire — sold below 5, active below 3.
        self.assertEqual(len(validation.qualifications), 2)


# ---------------------------------------------------------------------------
# Schema extensions on ComparableProperty
# ---------------------------------------------------------------------------


class ComparablePropertyExtendedFieldsTests(unittest.TestCase):
    """Pin the new optional fields on ComparableProperty so future
    refactors don't silently drop them."""

    def test_legacy_construction_still_works(self):
        # Old callers passing only the 8 required + 3 optional fields
        # should continue to construct without errors.
        comp = ComparableProperty(
            property_id="x",
            address="x",
            town="x",
            state="x",
            beds=3,
            baths=2.0,
            ask_price=800_000.0,
            blocks_to_beach=None,
        )
        self.assertIsNone(comp.listing_status)
        self.assertIsNone(comp.sale_date)
        self.assertIsNone(comp.days_on_market)
        self.assertIsNone(comp.tax_assessed_value)
        self.assertIsNone(comp.zestimate)
        self.assertIsNone(comp.rent_zestimate)
        self.assertIsNone(comp.latitude)
        self.assertIsNone(comp.longitude)
        self.assertIsNone(comp.lot_sqft)

    def test_new_fields_are_settable(self):
        comp = ComparableProperty(
            property_id="x",
            address="1209 16th Ave, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=4,
            baths=2.0,
            ask_price=800_000.0,
            blocks_to_beach=None,
            listing_status="sold",
            sale_date="2026-04-20",
            tax_assessed_value=453_600.0,
            zestimate=800_400.0,
            rent_zestimate=4_047.0,
            latitude=40.17562,
            longitude=-74.037384,
            lot_sqft=14_375.0,  # 0.33 acres
        )
        self.assertEqual(comp.listing_status, "sold")
        self.assertEqual(comp.sale_date, "2026-04-20")
        self.assertEqual(comp.tax_assessed_value, 453_600.0)
        self.assertEqual(comp.zestimate, 800_400.0)
        self.assertEqual(comp.rent_zestimate, 4_047.0)
        self.assertAlmostEqual(comp.latitude, 40.17562, places=4)
        self.assertAlmostEqual(comp.longitude, -74.037384, places=4)
        self.assertEqual(comp.lot_sqft, 14_375.0)

    def test_active_listing_uses_days_on_market(self):
        comp = ComparableProperty(
            property_id="x",
            address="x",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=2.0,
            ask_price=800_000.0,
            blocks_to_beach=None,
            listing_status="active",
            days_on_market=42,
        )
        self.assertEqual(comp.listing_status, "active")
        self.assertEqual(comp.days_on_market, 42)
        self.assertIsNone(comp.sale_date)


if __name__ == "__main__":
    unittest.main()

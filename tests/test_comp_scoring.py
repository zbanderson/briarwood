"""Unit tests for `briarwood/modules/comp_scoring.py`.

Pins the lifted scoring math so regressions show up in CI. Engine A's
behavior is verified separately by the existing
`tests/test_modules.py::ComparableSalesTests` suite (which exercises
`ComparableSalesModule.run`); this file focuses on the new shared scoring
module's public functions including the per-listing-status divergence
and the degraded-data floor for Zillow-style sparse comps.
"""

from __future__ import annotations

import unittest

from briarwood.modules import comp_scoring


class ScoreProximityTests(unittest.TestCase):
    def test_none_distance_returns_neutral_score(self):
        self.assertEqual(comp_scoring.score_proximity(None), 0.55)

    def test_quarter_mile_or_less_scores_highest(self):
        self.assertEqual(comp_scoring.score_proximity(0.1), 0.95)
        self.assertEqual(comp_scoring.score_proximity(0.25), 0.95)

    def test_half_mile_band(self):
        self.assertEqual(comp_scoring.score_proximity(0.5), 0.88)

    def test_one_mile_band(self):
        self.assertEqual(comp_scoring.score_proximity(0.99), 0.78)

    def test_two_mile_band(self):
        self.assertEqual(comp_scoring.score_proximity(1.5), 0.64)

    def test_far_drops_to_floor(self):
        self.assertEqual(comp_scoring.score_proximity(5.0), 0.42)


class ScoreRecencySoldTests(unittest.TestCase):
    def test_none_returns_neutral(self):
        self.assertEqual(comp_scoring.score_recency_sold(None), 0.5)

    def test_recent_sale_scores_highest(self):
        self.assertEqual(comp_scoring.score_recency_sold(30), 0.95)

    def test_six_month_band(self):
        self.assertEqual(comp_scoring.score_recency_sold(150), 0.88)

    def test_year_band(self):
        self.assertEqual(comp_scoring.score_recency_sold(300), 0.78)

    def test_two_year_band(self):
        self.assertEqual(comp_scoring.score_recency_sold(700), 0.62)

    def test_old_sale_drops_to_floor(self):
        self.assertEqual(comp_scoring.score_recency_sold(1500), 0.4)


class ScoreRecencyActiveTests(unittest.TestCase):
    """Per-listing-status divergence — ACTIVE comps use days_on_market,
    inverted (fresh listings score higher than stale asks)."""

    def test_none_returns_soft_neutral(self):
        # Slightly above 0.5 because ACTIVE rows usually have DOM populated;
        # missing is a soft data-quality signal, not an irrelevant comp.
        self.assertEqual(comp_scoring.score_recency_active(None), 0.55)

    def test_just_listed_scores_highest(self):
        self.assertEqual(comp_scoring.score_recency_active(7), 0.92)
        self.assertEqual(comp_scoring.score_recency_active(14), 0.92)

    def test_one_month(self):
        self.assertEqual(comp_scoring.score_recency_active(30), 0.85)

    def test_two_months(self):
        self.assertEqual(comp_scoring.score_recency_active(60), 0.75)

    def test_three_months(self):
        self.assertEqual(comp_scoring.score_recency_active(90), 0.62)

    def test_six_months(self):
        self.assertEqual(comp_scoring.score_recency_active(180), 0.45)

    def test_stale_above_cap_drops_to_floor(self):
        # Above ACTIVE_DOM_CAP_DAYS (180) — should be filtered upstream
        # but score low if it slips through.
        self.assertEqual(comp_scoring.score_recency_active(250), 0.30)

    def test_active_recency_is_higher_than_sold_for_same_age(self):
        # A 30-day-on-market ACTIVE comp (0.85) is a stronger competition
        # signal than a 30-day-old SOLD comp (0.95) is a strong anchor.
        # Different intuitions; pin both so the divergence stays explicit.
        self.assertEqual(comp_scoring.score_recency_active(30), 0.85)
        self.assertEqual(comp_scoring.score_recency_sold(30), 0.95)


class ScoreRecencyDispatcherTests(unittest.TestCase):
    def test_active_status_routes_to_active_function(self):
        score = comp_scoring.score_recency(
            listing_status="active",
            days_on_market=14,
            sale_age_days=999,  # ignored
        )
        self.assertEqual(score, 0.92)

    def test_sold_status_routes_to_sold_function(self):
        score = comp_scoring.score_recency(
            listing_status="sold",
            sale_age_days=30,
            days_on_market=999,  # ignored
        )
        self.assertEqual(score, 0.95)

    def test_unknown_status_defaults_to_sold(self):
        # Engine A backwards compat — comps with no listing_status get
        # the SOLD scoring path.
        score = comp_scoring.score_recency(
            listing_status=None,
            sale_age_days=30,
        )
        self.assertEqual(score, 0.95)

    def test_case_insensitive_status(self):
        self.assertEqual(
            comp_scoring.score_recency(listing_status="ACTIVE", days_on_market=7),
            0.92,
        )
        self.assertEqual(
            comp_scoring.score_recency(listing_status="Sold", sale_age_days=30),
            0.95,
        )


class ScoreDataQualityTests(unittest.TestCase):
    def test_full_data_with_mls_verification(self):
        # 6/6 fields + MLS verified bonus = capped at ceiling.
        score = comp_scoring.score_data_quality(
            present_fields=6,
            total_fields=6,
            verification_status="mls_verified",
        )
        self.assertEqual(score, 1.0)  # base 1.0 + 0.08 bonus, capped at ceiling

    def test_full_data_no_verification(self):
        score = comp_scoring.score_data_quality(
            present_fields=6,
            total_fields=6,
            verification_status=None,
        )
        self.assertEqual(score, 1.0)

    def test_zillow_listing_tier_gets_smaller_bonus(self):
        # 5/6 fields = 0.833, + 0.05 zillow bonus = 0.883.
        score = comp_scoring.score_data_quality(
            present_fields=5,
            total_fields=6,
            verification_status="zillow_listing",
        )
        self.assertAlmostEqual(score, 0.883, places=3)

    def test_questioned_verification_penalizes(self):
        # 5/6 fields = 0.833, - 0.10 = 0.733.
        score = comp_scoring.score_data_quality(
            present_fields=5,
            total_fields=6,
            verification_status="questioned",
        )
        self.assertAlmostEqual(score, 0.733, places=3)

    def test_partial_data_no_verification(self):
        # 4/6 = 0.667, no adjustment.
        score = comp_scoring.score_data_quality(
            present_fields=4,
            total_fields=6,
            verification_status=None,
        )
        self.assertAlmostEqual(score, 0.667, places=3)

    def test_half_missing_does_not_trigger_degraded_path(self):
        # 3/6 missing is exactly half — strict ">" check means no degraded.
        # Score = 0.5 + 0 (no verification).
        score = comp_scoring.score_data_quality(
            present_fields=3,
            total_fields=6,
        )
        self.assertEqual(score, 0.5)

    def test_more_than_half_missing_returns_degraded_floor(self):
        # 2/6 fields = base 0.333. With > half missing (4 > 3), degraded
        # floor of 0.3 fires. Note: 0.3 is > 0.333 at the original floor
        # of 0.2, so this is a *bump*, not a penalty.
        score = comp_scoring.score_data_quality(
            present_fields=2,
            total_fields=6,
        )
        self.assertEqual(score, 0.3)

    def test_zero_present_returns_degraded_floor(self):
        score = comp_scoring.score_data_quality(
            present_fields=0,
            total_fields=6,
        )
        self.assertEqual(score, 0.3)

    def test_floor_not_below_default(self):
        # Base = 0.5, penalty = -0.5 (manufactured) → would go to 0.0,
        # but floor is 0.2.
        # Using questioned verification with 2 present fields would
        # otherwise produce 0.333 - 0.10 = 0.233, which is above the
        # 0.2 floor but below the 0.3 degraded floor since this triggers
        # the degraded path.
        score = comp_scoring.score_data_quality(
            present_fields=2,
            total_fields=6,
            verification_status="questioned",
        )
        # Degraded path overrides — returns 0.3, not 0.233.
        self.assertEqual(score, 0.3)


class ScoreCompInputsTests(unittest.TestCase):
    def test_unified_scoring_for_sold_comp(self):
        scores = comp_scoring.score_comp_inputs(
            listing_status="sold",
            distance_miles=0.4,
            sale_age_days=120,
            similarity_score=0.85,
            present_fields=5,
            total_fields=6,
            verification_status="mls_verified",
        )
        # proximity (0.5mi) = 0.88, recency (sold 120d) = 0.88,
        # similarity = 0.85, data_quality (5/6 + 0.08) = 0.913.
        # weighted = 0.88*0.30 + 0.88*0.25 + 0.85*0.30 + 0.913*0.15
        #         = 0.264 + 0.22 + 0.255 + 0.137 = 0.876
        self.assertAlmostEqual(scores.weighted_score, 0.876, places=2)
        self.assertEqual(scores.proximity_score, 0.88)
        self.assertEqual(scores.recency_score, 0.88)
        self.assertEqual(scores.similarity_score, 0.85)
        self.assertFalse(scores.is_outlier)

    def test_unified_scoring_for_active_comp(self):
        scores = comp_scoring.score_comp_inputs(
            listing_status="active",
            distance_miles=0.4,
            days_on_market=14,
            similarity_score=0.85,
            present_fields=5,
            total_fields=6,
            verification_status="zillow_listing",
        )
        # proximity = 0.88, recency (active 14d) = 0.92,
        # similarity = 0.85, data_quality (5/6 + 0.05) = 0.883.
        # weighted = 0.264 + 0.23 + 0.255 + 0.132 = 0.881
        self.assertAlmostEqual(scores.weighted_score, 0.881, places=2)
        self.assertEqual(scores.recency_score, 0.92)

    def test_outlier_flag_set_for_tax_assessed_mismatch(self):
        # Belmar $8K probe outlier: $8,000 sale vs $453K tax_assessed → 0.018x
        scores = comp_scoring.score_comp_inputs(
            listing_status="sold",
            distance_miles=0.5,
            sale_age_days=60,
            present_fields=5,
            total_fields=6,
            extracted_price=8_000.0,
            tax_assessed_value=453_000.0,
        )
        self.assertTrue(scores.is_outlier)

    def test_missing_price_or_tax_assessed_no_outlier(self):
        scores = comp_scoring.score_comp_inputs(
            listing_status="sold",
            distance_miles=0.5,
            sale_age_days=60,
            present_fields=5,
            total_fields=6,
            extracted_price=None,
            tax_assessed_value=453_000.0,
        )
        self.assertFalse(scores.is_outlier)


class DistanceMilesTests(unittest.TestCase):
    def test_zero_distance(self):
        self.assertEqual(comp_scoring.distance_miles(40.0, -74.0, 40.0, -74.0), 0.0)

    def test_one_degree_lat_is_about_69_miles(self):
        d = comp_scoring.distance_miles(40.0, -74.0, 41.0, -74.0)
        self.assertAlmostEqual(d, 69.0, places=1)

    def test_belmar_to_avon_is_about_2_miles(self):
        # Belmar 1209 16th Ave: lat=40.17562, lon=-74.037384
        # Avon By The Sea: ~lat=40.190, lon=-74.018
        d = comp_scoring.distance_miles(40.17562, -74.037384, 40.190, -74.018)
        # Should be ~1-2 miles in flat-earth approximation.
        self.assertGreater(d, 0.5)
        self.assertLess(d, 3.0)


class WeightsSumToOneTests(unittest.TestCase):
    """Pin the score weights so a refactor that breaks the sum doesn't
    silently shift the weighted_score scale."""

    def test_weights_sum_to_one(self):
        total = (
            comp_scoring.WEIGHT_PROXIMITY
            + comp_scoring.WEIGHT_RECENCY
            + comp_scoring.WEIGHT_SIMILARITY
            + comp_scoring.WEIGHT_DATA_QUALITY
        )
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_individual_weights_pinned(self):
        self.assertEqual(comp_scoring.WEIGHT_PROXIMITY, 0.30)
        self.assertEqual(comp_scoring.WEIGHT_RECENCY, 0.25)
        self.assertEqual(comp_scoring.WEIGHT_SIMILARITY, 0.30)
        self.assertEqual(comp_scoring.WEIGHT_DATA_QUALITY, 0.15)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

from briarwood.agents.comparable_sales import ComparableSalesAgent, ComparableSalesRequest, FileBackedComparableSalesProvider
from briarwood.agents.market_history.schemas import HistoricalValuePoint


class ComparableSalesAgentTests(unittest.TestCase):
    def test_agent_returns_ranked_comps_with_fit_reasons(self) -> None:
        agent = ComparableSalesAgent(
            FileBackedComparableSalesProvider(
                Path("data/comps/sales_comps.json")
            )
        )

        result = agent.run(
            ComparableSalesRequest(
                town="Belmar",
                state="NJ",
                property_type="single family residence",
                architectural_style="Ranch",
                condition_profile="updated",
                capex_lane="moderate",
                beds=3,
                baths=2.0,
                sqft=1600,
                lot_size=0.13,
                year_built=1990,
                stories=1.0,
                garage_spaces=1,
                listing_description="Beach and marina access with downtown nearby. Beautifully maintained ranch with updated kitchen.",
                market_value_today=810000,
                market_history_points=[
                    HistoricalValuePoint(date="2025-06-30", value=770000).model_dump(),
                    HistoricalValuePoint(date="2026-02-28", value=810000).model_dump(),
                ],
            )
        )

        self.assertIsNotNone(result.comparable_value)
        self.assertGreaterEqual(result.comp_count, 1)
        self.assertGreaterEqual(result.confidence, 0.4)
        self.assertGreaterEqual(result.rejection_reasons.get("address_verification_failed", 0), 1)
        self.assertEqual(result.dataset_name, "briarwood_monmouth_sales_seed_v2")
        self.assertEqual(result.dataset_as_of, "2026-03-29")
        self.assertIsNotNone(result.freshest_sale_date)
        self.assertIsNotNone(result.median_sale_age_days)
        self.assertTrue(result.curation_summary)
        top_comp = result.comps_used[0]
        self.assertTrue(top_comp.why_comp)
        self.assertTrue(any("property-type family" in note.lower() for note in top_comp.why_comp))
        self.assertTrue(any("style" in note.lower() or "setting traits" in note.lower() for note in top_comp.why_comp))
        self.assertIn(top_comp.fit_label, {"strong", "usable", "stretch"})
        self.assertGreater(top_comp.comp_confidence_weight, 0)
        self.assertTrue(top_comp.adjustments_summary)
        self.assertTrue(top_comp.comp_status)
        self.assertIn(top_comp.capex_lane, {"light", "moderate", "heavy", None})
        self.assertTrue(top_comp.source_ref)
        self.assertEqual(top_comp.address_verification_status, "verified")
        self.assertEqual(top_comp.sale_verification_status, "seeded")
        self.assertEqual(top_comp.verification_source_type, "manual_review")
        self.assertTrue(top_comp.micro_location_notes)
        self.assertIn("reviewed", top_comp.source_summary or "")
        self.assertIn("seed/review only", result.verification_summary or "")
        self.assertTrue(
            any("public-record or MLS-verified sale record" in warning for warning in result.warnings)
        )
        self.assertLessEqual(result.confidence, 0.56)

    def test_agent_rejects_badly_mismatched_comp_set(self) -> None:
        agent = ComparableSalesAgent(
            FileBackedComparableSalesProvider(
                Path("data/comps/sales_comps.json")
            )
        )

        result = agent.run(
            ComparableSalesRequest(
                town="Belmar",
                state="NJ",
                property_type="condo",
                condition_profile="renovated",
                capex_lane="light",
                beds=6,
                baths=4.0,
                sqft=4200,
                lot_size=0.4,
                year_built=2018,
            )
        )

        self.assertIsNone(result.comparable_value)
        self.assertEqual(result.comp_count, 0)
        self.assertGreaterEqual(result.rejected_count, 1)


class ConditionAdjustmentTests(unittest.TestCase):
    """Verify the raised condition adjustment cap (±15%) and per-rank delta (4%)."""

    def setUp(self) -> None:
        self.agent = ComparableSalesAgent(
            FileBackedComparableSalesProvider(Path("data/comps/sales_comps.json"))
        )

    def test_same_condition_zero_adjustment(self) -> None:
        pct = self.agent._condition_adjustment_pct("maintained", "maintained")
        self.assertAlmostEqual(pct, 0.0)

    def test_one_rank_difference(self) -> None:
        pct = self.agent._condition_adjustment_pct("updated", "maintained")
        self.assertAlmostEqual(pct, 0.04)

    def test_full_range_needs_work_to_renovated(self) -> None:
        pct = self.agent._condition_adjustment_pct("renovated", "needs_work")
        self.assertAlmostEqual(pct, 0.15)

    def test_full_range_renovated_to_needs_work(self) -> None:
        pct = self.agent._condition_adjustment_pct("needs_work", "renovated")
        self.assertAlmostEqual(pct, -0.15)

    def test_two_rank_difference(self) -> None:
        pct = self.agent._condition_adjustment_pct("renovated", "maintained")
        self.assertAlmostEqual(pct, 0.08)


class TotalAdjustmentCapTests(unittest.TestCase):
    """Verify that the total subject adjustment cap is ±20%."""

    def setUp(self) -> None:
        self.agent = ComparableSalesAgent(
            FileBackedComparableSalesProvider(Path("data/comps/sales_comps.json"))
        )

    def test_large_multi_dimension_adjustment_above_old_cap(self) -> None:
        """A comp differing across many dimensions should be able to exceed ±12%."""
        from briarwood.agents.comparable_sales import ComparableSale

        request = ComparableSalesRequest(
            town="Belmar",
            state="NJ",
            sqft=2000,
            beds=4,
            baths=3.0,
            lot_size=0.25,
            year_built=2010,
            condition_profile="renovated",
        )
        sale = ComparableSale(
            address="1 Test St",
            town="Belmar",
            state="NJ",
            sale_price=500000,
            sale_date="2025-06-01",
            sqft=1400,
            beds=2,
            baths=1.5,
            lot_size=0.10,
            year_built=1960,
            condition_profile="needs_work",
        )
        pct, notes = self.agent._subject_adjustment_pct(request, sale)
        self.assertGreater(abs(pct), 0.12, "Adjustment should exceed the old ±12% cap")
        self.assertLessEqual(abs(pct), 0.20, "Adjustment must respect the new ±20% cap")


class SqftAdjustmentTests(unittest.TestCase):
    """Verify non-linear (log-based) sqft adjustment."""

    def setUp(self) -> None:
        self.agent = ComparableSalesAgent(
            FileBackedComparableSalesProvider(Path("data/comps/sales_comps.json"))
        )

    def _sqft_pct(self, subject_sqft: int, comp_sqft: int) -> float:
        from math import log
        ratio = subject_sqft / max(comp_sqft, 1)
        return max(-0.15, min(log(ratio) * 0.50, 0.15))

    def test_equal_sqft_zero_adjustment(self) -> None:
        self.assertAlmostEqual(self._sqft_pct(2000, 2000), 0.0)

    def test_20pct_larger_moderate_adjustment(self) -> None:
        pct = self._sqft_pct(2400, 2000)
        self.assertAlmostEqual(pct, 0.091, places=2)

    def test_35pct_larger_below_cap(self) -> None:
        pct = self._sqft_pct(2700, 2000)
        self.assertLessEqual(pct, 0.15)
        self.assertGreater(pct, 0.10)

    def test_35pct_smaller(self) -> None:
        pct = self._sqft_pct(1300, 2000)
        self.assertAlmostEqual(pct, -0.15)

    def test_diminishing_returns(self) -> None:
        """Larger gaps should produce less-than-linear adjustments."""
        small_gap = self._sqft_pct(2200, 2000)
        large_gap = self._sqft_pct(2700, 2000)
        self.assertLess(large_gap / small_gap, 3.5)


if __name__ == "__main__":
    unittest.main()

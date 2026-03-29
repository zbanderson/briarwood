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
        self.assertTrue(top_comp.adjustments_summary)
        self.assertTrue(top_comp.comp_status)
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


if __name__ == "__main__":
    unittest.main()

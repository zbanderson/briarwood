import unittest

from briarwood.inputs.adapters import PublicRecordAdapter
from briarwood.inputs.market_location_adapter import MarketLocationAdapter
from briarwood.schemas import InputCoverageStatus


class MarketLocationAdapterTests(unittest.TestCase):
    def test_market_location_adapter_enriches_monmouth_input_with_sourced_context(self) -> None:
        canonical = PublicRecordAdapter().build(
            {
                "property_id": "belmar-pr-1",
                "address": "1223 Briarwood Rd",
                "town": "Belmar",
                "state": "NJ",
                "county": "Monmouth",
                "beds": 3,
                "baths": 1.0,
                "sqft": 1196,
                "purchase_price": 674200,
            }
        )

        enriched = MarketLocationAdapter().enrich(canonical)

        self.assertIsNotNone(enriched.market_signals.market_history_current_value)
        self.assertIsNotNone(enriched.market_signals.town_price_trend)
        self.assertIn("beach", enriched.market_signals.landmark_points)
        self.assertIn("downtown", enriched.market_signals.landmark_points)
        self.assertEqual(enriched.source_metadata.source_coverage["market_history"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(enriched.source_metadata.source_coverage["school_signal"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(enriched.source_metadata.source_coverage["flood_risk"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(enriched.source_metadata.source_coverage["liquidity_signal"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(enriched.source_metadata.source_coverage["landmark_points"].status, InputCoverageStatus.SOURCED)

    def test_market_location_adapter_enriches_other_curated_monmouth_towns_with_landmarks(self) -> None:
        canonical = PublicRecordAdapter().build(
            {
                "property_id": "spring-lake-pr-1",
                "address": "305 4th Ave",
                "town": "Spring Lake",
                "state": "NJ",
                "county": "Monmouth",
                "beds": 5,
                "baths": 4.0,
                "sqft": 4119,
                "purchase_price": 3200000,
            }
        )

        enriched = MarketLocationAdapter().enrich(canonical)

        self.assertIn("beach", enriched.market_signals.landmark_points)
        self.assertIn("train", enriched.market_signals.landmark_points)
        self.assertEqual(enriched.source_metadata.source_coverage["landmark_points"].status, InputCoverageStatus.SOURCED)

    def test_public_record_adapter_normalizes_town_aliases_before_enrichment(self) -> None:
        canonical = PublicRecordAdapter().build(
            {
                "property_id": "asb-pr-1",
                "address": "1205 Jeffrey Street",
                "town": "Asb",
                "state": "nj",
                "beds": 3,
                "baths": 2.0,
                "sqft": 1400,
                "purchase_price": 940000,
            }
        )

        enriched = MarketLocationAdapter().enrich(canonical)

        self.assertEqual(enriched.facts.town, "Asbury Park")
        self.assertEqual(enriched.facts.state, "NJ")
        self.assertIsNotNone(enriched.market_signals.market_history_current_value)
        self.assertEqual(enriched.source_metadata.source_coverage["market_history"].status, InputCoverageStatus.SOURCED)


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual(enriched.source_metadata.source_coverage["market_history"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(enriched.source_metadata.source_coverage["school_signal"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(enriched.source_metadata.source_coverage["flood_risk"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(enriched.source_metadata.source_coverage["liquidity_signal"].status, InputCoverageStatus.SOURCED)


if __name__ == "__main__":
    unittest.main()

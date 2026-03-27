import unittest

from briarwood.agents.market_history import (
    FileBackedZillowHistoryProvider,
    MarketValueHistoryAgent,
    MarketValueHistoryOutput,
)


class MarketValueHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        provider = FileBackedZillowHistoryProvider("data/market_history/zillow_zhvi_history.json")
        self.agent = MarketValueHistoryAgent(provider)

    def test_returns_town_level_history_when_available(self) -> None:
        result = self.agent.run({"town": "Belmar", "state": "NJ", "county": "Monmouth"})

        self.assertIsInstance(result, MarketValueHistoryOutput)
        self.assertEqual(result.geography_type, "town")
        self.assertEqual(result.current_value, 810000)
        self.assertAlmostEqual(result.one_year_change_pct or 0.0, 0.0658, places=4)
        self.assertAlmostEqual(result.three_year_change_pct or 0.0, 0.1555, places=4)
        self.assertGreaterEqual(result.confidence, 1.0)

    def test_falls_back_to_county_when_town_history_missing(self) -> None:
        result = self.agent.run({"town": "Unknown", "state": "MA", "county": "Norfolk"})

        self.assertEqual(result.geography_type, "county")
        self.assertEqual(result.geography_name, "Norfolk")
        self.assertEqual(result.current_value, 955000)
        self.assertTrue(result.warnings)
        self.assertLess(result.confidence, 1.0)

    def test_returns_empty_result_when_no_history_found(self) -> None:
        result = self.agent.run({"town": "Unknown", "state": "ZZ"})

        self.assertEqual(result.points, [])
        self.assertIsNone(result.current_value)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("could not find", result.summary.lower())


if __name__ == "__main__":
    unittest.main()

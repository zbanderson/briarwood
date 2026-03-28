import unittest

from briarwood.agents.town_county.providers import (
    FileBackedFloodRiskProvider,
    FileBackedFredMacroProvider,
    FileBackedLiquidityProvider,
    FileBackedPopulationProvider,
    FileBackedPriceTrendProvider,
    FileBackedTownProfileProvider,
)
from briarwood.agents.town_county.service import TownCountyDataService
from briarwood.agents.town_county.sources import TownCountyOutlookRequest


class TownCountyFileBackedServiceTests(unittest.TestCase):
    def test_service_can_build_outlook_from_file_backed_providers(self) -> None:
        service = TownCountyDataService(
            price_provider=FileBackedPriceTrendProvider("data/town_county/price_trends.json"),
            population_provider=FileBackedPopulationProvider("data/town_county/population_trends.json"),
            flood_provider=FileBackedFloodRiskProvider("data/town_county/flood_risk.json"),
            liquidity_provider=FileBackedLiquidityProvider("data/town_county/liquidity.json"),
            fred_macro_provider=FileBackedFredMacroProvider("data/town_county/fred_macro.json"),
            town_profile_provider=FileBackedTownProfileProvider("data/town_county/monmouth_coastal_profiles.json"),
        )

        result = service.build_outlook(
            TownCountyOutlookRequest(
                town="Belmar",
                state="NJ",
                county="Monmouth",
                school_signal=8.1,
                scarcity_signal=0.7,
                days_on_market=19,
                price_position="supported",
                source_names={"school_signal": "district_signal_v1"},
            )
        )

        self.assertAlmostEqual(result.normalized.inputs.town_price_trend or 0.0, 0.0658, places=4)
        self.assertAlmostEqual(result.normalized.inputs.county_population_trend or 0.0, 0.0062, places=4)
        self.assertIsNotNone(result.normalized.inputs.county_macro_sentiment)
        self.assertEqual(result.normalized.inputs.coastal_profile_signal, 0.84)
        self.assertEqual(result.normalized.inputs.flood_risk, "medium")
        self.assertEqual(result.score.location_thesis_label, "supportive")
        self.assertGreater(result.score.area_sentiment_score, 65.0)
        self.assertGreater(result.score.confidence, 0.80)
        self.assertLess(result.score.confidence, 0.95)


if __name__ == "__main__":
    unittest.main()

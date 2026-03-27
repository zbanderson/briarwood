import unittest

from briarwood.agents.town_county.service import TownCountyDataService, TownCountyOutlookResult
from briarwood.agents.town_county.sources import TownCountyOutlookRequest


class StubPriceProvider:
    def get_town_row(self, *, town: str, state: str) -> dict[str, object] | None:
        return {
            "RegionName": town,
            "current_value": 810000,
            "prior_year_value": 760000,
            "as_of": "2026-02-28",
        }

    def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
        return {
            "RegionName": county,
            "current_value": 690000,
            "prior_year_value": 660000,
            "as_of": "2026-02-28",
        }


class StubPopulationProvider:
    def get_town_row(self, *, town: str, state: str) -> dict[str, object] | None:
        return {
            "name": town,
            "current_population": 5750,
            "prior_population": 5680,
            "as_of": "2025-07-01",
        }

    def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
        return {
            "name": county,
            "current_population": 645000,
            "prior_population": 641000,
            "as_of": "2025-07-01",
        }


class StubFloodProvider:
    def get_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        return {
            "name": town,
            "flood_risk": "Low",
            "as_of": "2025-01-01",
        }


class StubLiquidityProvider:
    def get_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        return {
            "name": town,
            "inventory_count": 42,
            "monthly_sales_count": 11,
            "months_of_supply": 3.8,
            "as_of": "2026-02-28",
        }


class TownCountyDataServiceTests(unittest.TestCase):
    def test_service_builds_complete_outlook(self) -> None:
        service = TownCountyDataService(
            price_provider=StubPriceProvider(),
            population_provider=StubPopulationProvider(),
            flood_provider=StubFloodProvider(),
            liquidity_provider=StubLiquidityProvider(),
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

        self.assertIsInstance(result, TownCountyOutlookResult)
        self.assertAlmostEqual(result.normalized.inputs.town_price_trend or 0.0, 0.0658, places=4)
        self.assertEqual(result.score.location_thesis_label, "supportive")
        self.assertLess(result.score.confidence, 0.95)
        self.assertGreater(result.score.confidence, 0.80)
        self.assertFalse(result.normalized.missing_inputs)
        self.assertTrue(result.score.assumptions_used)

    def test_service_handles_missing_provider_data_without_fabricating_values(self) -> None:
        class SparsePriceProvider(StubPriceProvider):
            def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
                return None

        class SparseFloodProvider:
            def get_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
                return None

        service = TownCountyDataService(
            price_provider=SparsePriceProvider(),
            population_provider=StubPopulationProvider(),
            flood_provider=SparseFloodProvider(),
            liquidity_provider=None,
        )

        result = service.build_outlook(
            TownCountyOutlookRequest(
                town="Belmar",
                state="NJ",
                county="Monmouth",
                school_signal=8.1,
            )
        )

        self.assertIsNone(result.normalized.inputs.county_price_trend)
        self.assertIsNone(result.normalized.inputs.flood_risk)
        self.assertIn("county_price_trend", result.normalized.missing_inputs)
        self.assertIn("flood_risk", result.normalized.missing_inputs)
        self.assertIsNotNone(result.score.county_support_score)
        self.assertLess(result.score.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()

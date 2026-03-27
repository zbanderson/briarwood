import unittest

from briarwood.agents.town_county.providers import (
    FileBackedFloodRiskProvider,
    FileBackedLiquidityProvider,
    FileBackedPopulationProvider,
    FileBackedPriceTrendProvider,
)


class TownCountyProviderTests(unittest.TestCase):
    def test_file_backed_price_provider_returns_matching_rows(self) -> None:
        provider = FileBackedPriceTrendProvider("data/town_county/price_trends.json")

        town_row = provider.get_town_row(town="Belmar", state="NJ")
        county_row = provider.get_county_row(county="Monmouth", state="NJ")

        self.assertIsNotNone(town_row)
        self.assertIsNotNone(county_row)
        self.assertEqual(town_row["current_value"], 810000)
        self.assertEqual(county_row["prior_year_value"], 660000)

    def test_file_backed_population_provider_returns_matching_rows(self) -> None:
        provider = FileBackedPopulationProvider("data/town_county/population_trends.json")

        town_row = provider.get_town_row(town="Brookline", state="MA")
        county_row = provider.get_county_row(county="Norfolk", state="MA")

        self.assertEqual(town_row["current_population"], 63200)
        self.assertEqual(county_row["prior_population"], 729000)

    def test_file_backed_flood_provider_returns_matching_rows(self) -> None:
        provider = FileBackedFloodRiskProvider("data/town_county/flood_risk.json")

        row = provider.get_row(town="Belmar", state="NJ")

        self.assertIsNotNone(row)
        self.assertEqual(row["flood_risk"], "Moderate")

    def test_file_backed_liquidity_provider_returns_matching_rows(self) -> None:
        provider = FileBackedLiquidityProvider("data/town_county/liquidity.json")

        row = provider.get_row(town="Belmar", state="NJ")

        self.assertIsNotNone(row)
        self.assertEqual(row["months_of_supply"], 3.8)


if __name__ == "__main__":
    unittest.main()

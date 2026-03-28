import unittest

from briarwood.agents.town_county.sources import (
    CensusPopulationAdapter,
    FemaFloodAdapter,
    FredMacroAdapter,
    LiquidityAdapter,
    LiquiditySlice,
    TownProfileAdapter,
    TownCountyOutlookBuilder,
    TownCountyOutlookRequest,
    ZillowTrendAdapter,
)


class TownCountySourceAdapterTests(unittest.TestCase):
    def test_zillow_adapter_parses_trend_slice(self) -> None:
        row = {
            "RegionName": "Belmar",
            "current_value": "810000",
            "prior_year_value": "760000",
            "as_of": "2026-02-28",
        }

        result = ZillowTrendAdapter().from_row(row, geography_type="town")

        self.assertEqual(result.geography_name, "Belmar")
        self.assertEqual(result.geography_type, "town")
        self.assertEqual(result.current_value, 810000.0)
        self.assertEqual(result.prior_year_value, 760000.0)

    def test_census_adapter_parses_population_slice(self) -> None:
        row = {
            "name": "Belmar",
            "current_population": "5750",
            "prior_population": "5680",
            "as_of": "2025-07-01",
        }

        result = CensusPopulationAdapter().from_row(row, geography_type="town")

        self.assertEqual(result.current_population, 5750)
        self.assertEqual(result.prior_population, 5680)
        self.assertEqual(result.as_of, "2025-07-01")

    def test_fema_adapter_maps_risk_bands(self) -> None:
        row = {
            "name": "Belmar",
            "flood_risk": "Relatively Moderate",
            "as_of": "2025-01-01",
        }

        result = FemaFloodAdapter().from_row(row, geography_type="town")

        self.assertEqual(result.flood_risk, "medium")

    def test_liquidity_adapter_derives_signal_from_months_of_supply(self) -> None:
        row = {
            "name": "Belmar",
            "inventory_count": 42,
            "monthly_sales_count": 11,
            "months_of_supply": 3.8,
            "as_of": "2026-02-28",
        }

        adapter = LiquidityAdapter()
        result = adapter.from_row(row, geography_type="town")

        self.assertEqual(result.months_of_supply, 3.8)
        self.assertEqual(adapter.derive_signal(result), "normal")

    def test_fred_macro_adapter_derives_county_sentiment(self) -> None:
        row = {
            "name": "Monmouth",
            "unemployment_rate_current": 4.1,
            "per_capita_income_current": 104887,
            "per_capita_income_prior": 100491,
            "house_price_index_current": 301.39,
            "house_price_index_prior": 277.94,
            "median_days_on_market_current": 61.5,
            "median_days_on_market_yoy_pct": -0.0315,
            "as_of": "2026-02-13",
        }

        adapter = FredMacroAdapter()
        result = adapter.from_row(row, geography_type="county")

        self.assertEqual(result.unemployment_rate_current, 4.1)
        self.assertGreater(adapter.derive_sentiment(result) or 0.0, 0.7)

    def test_town_profile_adapter_parses_monmouth_profile(self) -> None:
        row = {
            "name": "Sea Girt",
            "coastal_profile_signal": 0.95,
            "scarcity_signal": 0.92,
            "as_of": "2026-03-01",
            "refresh_frequency_days": 90,
        }

        result = TownProfileAdapter().from_row(row, geography_type="town")

        self.assertEqual(result.geography_name, "Sea Girt")
        self.assertEqual(result.coastal_profile_signal, 0.95)
        self.assertEqual(result.scarcity_signal, 0.92)
        self.assertEqual(result.as_of, "2026-03-01")
        self.assertEqual(result.refresh_frequency_days, 90)

    def test_outlook_builder_assembles_source_record(self) -> None:
        zillow = ZillowTrendAdapter()
        census = CensusPopulationAdapter()
        fema = FemaFloodAdapter()

        town_price = zillow.from_row(
            {
                "RegionName": "Belmar",
                "current_value": 810000,
                "prior_year_value": 760000,
                "as_of": "2026-02-28",
            },
            geography_type="town",
        )
        county_price = zillow.from_row(
            {
                "RegionName": "Monmouth County",
                "current_value": 690000,
                "prior_year_value": 660000,
                "as_of": "2026-02-28",
            },
            geography_type="county",
        )
        town_population = census.from_row(
            {
                "name": "Belmar",
                "current_population": 5750,
                "prior_population": 5680,
                "as_of": "2025-07-01",
            },
            geography_type="town",
        )
        county_population = census.from_row(
            {
                "name": "Monmouth County",
                "current_population": 645000,
                "prior_population": 641000,
                "as_of": "2025-07-01",
            },
            geography_type="county",
        )
        flood = fema.from_row(
            {
                "name": "Belmar",
                "flood_risk": "Medium",
                "as_of": "2025-01-01",
            },
            geography_type="town",
        )
        fred_macro = FredMacroAdapter().from_row(
            {
                "name": "Monmouth",
                "unemployment_rate_current": 4.1,
                "per_capita_income_current": 104887,
                "per_capita_income_prior": 100491,
                "house_price_index_current": 301.39,
                "house_price_index_prior": 277.94,
                "median_days_on_market_current": 61.5,
                "median_days_on_market_yoy_pct": -0.0315,
                "as_of": "2026-02-13",
            },
            geography_type="county",
        )
        town_profile = TownProfileAdapter().from_row(
            {
                "name": "Belmar",
                "coastal_profile_signal": 0.84,
                "scarcity_signal": 0.78,
                "as_of": "2026-03-01",
                "refresh_frequency_days": 90,
            },
            geography_type="town",
        )
        liquidity = LiquiditySlice(
            geography_name="Belmar",
            geography_type="town",
            inventory_count=42,
            monthly_sales_count=11,
            months_of_supply=3.8,
            as_of="2026-02-28",
        )

        result = TownCountyOutlookBuilder().build(
            TownCountyOutlookRequest(
                town="Belmar",
                state="NJ",
                county="Monmouth",
                school_signal=8.1,
                scarcity_signal=0.7,
                days_on_market=19,
                price_position="supported",
                source_names={"school_signal": "district_signal_v1"},
            ),
            town_price=town_price,
            county_price=county_price,
            town_population=town_population,
            county_population=county_population,
            flood=flood,
            liquidity=liquidity,
            fred_macro=fred_macro,
            town_profile=town_profile,
        )

        self.assertEqual(result.town, "Belmar")
        self.assertEqual(result.state, "NJ")
        self.assertEqual(result.town_price_index_current, 810000.0)
        self.assertEqual(result.county_population_current, 645000)
        self.assertIsNotNone(result.county_macro_sentiment)
        self.assertEqual(result.coastal_profile_signal, 0.84)
        self.assertEqual(result.flood_risk, "medium")
        self.assertEqual(result.liquidity_signal, "normal")
        self.assertEqual(result.source_names["town_price_trend"], "zillow_zhvi")
        self.assertEqual(result.source_names["county_macro_sentiment"], "fred_macro")
        self.assertEqual(result.source_names["coastal_profile_signal"], "monmouth_coastal_profile_v1")
        self.assertEqual(result.data_as_of, "2026-03-01")


if __name__ == "__main__":
    unittest.main()

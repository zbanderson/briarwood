import unittest

from briarwood.agents.town_county.sources import (
    CensusPopulationAdapter,
    FemaFloodAdapter,
    LiquidityAdapter,
    LiquiditySlice,
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
        )

        self.assertEqual(result.town, "Belmar")
        self.assertEqual(result.state, "NJ")
        self.assertEqual(result.town_price_index_current, 810000.0)
        self.assertEqual(result.county_population_current, 645000)
        self.assertEqual(result.flood_risk, "medium")
        self.assertEqual(result.liquidity_signal, "normal")
        self.assertEqual(result.source_names["town_price_trend"], "zillow_zhvi")
        self.assertEqual(result.data_as_of, "2026-02-28")


if __name__ == "__main__":
    unittest.main()

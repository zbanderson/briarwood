import unittest

from pydantic import ValidationError

from briarwood.agents.town_county.bridge import TownCountySourceBridge, normalize_town_county_sources
from briarwood.agents.town_county.schemas import TownCountyNormalizedRecord, TownCountySourceRecord


def source_payload() -> dict[str, object]:
    return {
        "town": "Belmar",
        "state": "NJ",
        "county": "Monmouth",
        "town_price_index_current": 810000.0,
        "town_price_index_prior_year": 760000.0,
        "county_price_index_current": 690000.0,
        "county_price_index_prior_year": 660000.0,
        "town_population_current": 5750,
        "town_population_prior": 5680,
        "county_population_current": 645000,
        "county_population_prior": 641000,
        "school_signal": 8.1,
        "flood_risk": "medium",
        "liquidity_signal": "normal",
        "scarcity_signal": 0.7,
        "days_on_market": 19,
        "price_position": "supported",
        "data_as_of": "2026-03-01",
        "source_names": {
            "town_price_trend": "zillow_zhvi",
            "county_price_trend": "zillow_zhvi",
            "town_population_trend": "census_acs",
            "county_population_trend": "census_acs",
            "school_signal": "district_signal_v1",
            "flood_risk": "fema_nri",
            "liquidity_signal": "market_liquidity_v1",
            "scarcity_signal": "manual_briarwood_note",
            "days_on_market": "listing_intake",
            "price_position": "pricing_module_v1",
        },
    }


class TownCountyBridgeTests(unittest.TestCase):
    def test_bridge_normalizes_source_record_into_inputs(self) -> None:
        result = TownCountySourceBridge().normalize(source_payload())

        self.assertIsInstance(result, TownCountyNormalizedRecord)
        self.assertAlmostEqual(result.inputs.town_price_trend or 0.0, 0.0658, places=4)
        self.assertAlmostEqual(result.inputs.county_price_trend or 0.0, 0.0455, places=4)
        self.assertAlmostEqual(result.inputs.town_population_trend or 0.0, 0.0123, places=4)
        self.assertEqual(result.inputs.school_signal, 8.1)
        self.assertEqual(result.inputs.flood_risk, "medium")
        self.assertFalse(result.missing_inputs)
        self.assertFalse(result.warnings)
        self.assertGreaterEqual(len(result.field_status), 10)

    def test_bridge_records_missing_derived_fields_instead_of_fabricating_values(self) -> None:
        payload = source_payload()
        payload["town_price_index_prior_year"] = None
        payload["county_population_prior"] = None
        payload["data_as_of"] = None

        result = normalize_town_county_sources(payload)

        self.assertIsNone(result.inputs.town_price_trend)
        self.assertIsNone(result.inputs.county_population_trend)
        self.assertIn("town_price_trend", result.missing_inputs)
        self.assertIn("county_population_trend", result.missing_inputs)
        self.assertTrue(result.warnings)

    def test_invalid_source_payload_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            TownCountySourceRecord.model_validate(
                {
                    "town": "Belmar",
                    "state": "New Jersey",
                    "town_price_index_current": -1,
                }
            )


if __name__ == "__main__":
    unittest.main()

import unittest

from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.modules.location_intelligence import LocationIntelligenceModule
from briarwood.schemas import PropertyInput


class StubComparableSalesProvider:
    def __init__(self, rows):
        self.rows = [ComparableSale.model_validate(row) for row in rows]

    def get_sales(self, *, town: str, state: str):
        town_key = town.strip().lower()
        state_key = state.strip().upper()
        return [
            row
            for row in self.rows
            if row.town.strip().lower() == town_key and row.state.strip().upper() == state_key
        ]


def sample_property() -> PropertyInput:
    return PropertyInput(
        property_id="geo-sample",
        address="1223 Briarwood Rd",
        town="Belmar",
        state="NJ",
        county="Monmouth",
        beds=3,
        baths=1.5,
        sqft=1196,
        purchase_price=674200,
        latitude=40.1800,
        longitude=-74.0300,
        flood_risk="medium",
        landmark_points={
            "beach": [{"latitude": 40.1760, "longitude": -74.0175}],
            "downtown": [{"latitude": 40.1780, "longitude": -74.0230}],
            "train": [{"latitude": 40.1840, "longitude": -74.0280}],
        },
        zone_flags={"in_beach_premium_zone": False, "in_flood_zone": False},
    )


class LocationIntelligenceTests(unittest.TestCase):
    def test_location_intelligence_benchmarks_geo_peer_buckets(self) -> None:
        provider = StubComparableSalesProvider(
            [
                {
                    "address": "100 Ocean Ave",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 820000,
                    "sale_date": "2025-10-01",
                    "sqft": 1200,
                    "latitude": 40.1765,
                    "longitude": -74.0180,
                    "days_on_market": 18,
                },
                {
                    "address": "200 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 760000,
                    "sale_date": "2025-09-15",
                    "sqft": 1250,
                    "latitude": 40.1785,
                    "longitude": -74.0235,
                    "days_on_market": 23,
                },
                {
                    "address": "300 Inland Rd",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 640000,
                    "sale_date": "2025-08-20",
                    "sqft": 1180,
                    "latitude": 40.1910,
                    "longitude": -74.0420,
                    "days_on_market": 31,
                },
                {
                    "address": "400 Cedar Ave",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 690000,
                    "sale_date": "2025-07-10",
                    "sqft": 1210,
                    "latitude": 40.1855,
                    "longitude": -74.0285,
                    "days_on_market": 20,
                },
            ]
        )
        module = LocationIntelligenceModule(provider=provider)

        result = module.run(sample_property())

        self.assertGreater(result.confidence, 0.5)
        self.assertIn("location_score", result.metrics)
        self.assertGreater(result.metrics["geo_peer_comp_count"], 0)
        self.assertIn(result.payload.primary_category, {"beach", "downtown", "train"})
        self.assertTrue(result.payload.category_results)
        self.assertIsNotNone(result.payload.location_premium_pct)
        self.assertTrue(any("bucket" in bullet.lower() for bullet in result.payload.narratives))

    def test_location_intelligence_handles_missing_coordinates_honestly(self) -> None:
        property_input = sample_property()
        property_input.latitude = None
        property_input.longitude = None
        module = LocationIntelligenceModule(provider=StubComparableSalesProvider([]))

        result = module.run(property_input)

        self.assertEqual(result.metrics["geo_peer_comp_count"], 0)
        self.assertLessEqual(result.confidence, 0.25)
        self.assertIn("subject_coordinates", result.payload.missing_inputs)
        self.assertIn("low-confidence", result.summary.lower())


if __name__ == "__main__":
    unittest.main()

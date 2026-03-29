import unittest

from briarwood.agents.rent_context import RentContextAgent


class RentContextAgentTests(unittest.TestCase):
    def test_provided_rent_passes_through(self) -> None:
        result = RentContextAgent().run(
            {
                "town": "Belmar",
                "state": "NJ",
                "sqft": 1800,
                "explicit_monthly_rent": 4200.0,
            }
        )

        self.assertEqual(result.rent_source_type, "provided")
        self.assertEqual(result.rent_estimate, 4200.0)
        self.assertGreaterEqual(result.confidence, 0.85)

    def test_estimated_rent_uses_prior(self) -> None:
        result = RentContextAgent().run(
            {
                "town": "Belmar",
                "state": "NJ",
                "sqft": 1800,
                "explicit_monthly_rent": None,
            }
        )

        self.assertEqual(result.rent_source_type, "estimated")
        self.assertIsNotNone(result.rent_estimate)
        self.assertLess(result.confidence, 0.5)
        self.assertTrue(any("town-level rent prior" in item.lower() for item in result.assumptions))

    def test_missing_rent_stays_missing_without_sqft(self) -> None:
        result = RentContextAgent().run(
            {
                "town": "Belmar",
                "state": "NJ",
                "sqft": None,
                "explicit_monthly_rent": None,
            }
        )

        self.assertEqual(result.rent_source_type, "missing")
        self.assertIsNone(result.rent_estimate)
        self.assertEqual(result.confidence, 0.0)

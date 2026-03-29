import unittest

from briarwood.agents.rental_ease.agent import RentalEaseAgent
from briarwood.agents.rental_ease.schemas import RentalEaseInput, RentalEaseOutput


def sample_payload() -> dict[str, object]:
    return {
        "town": "Belmar",
        "state": "NJ",
        "county": "Monmouth",
        "estimated_monthly_rent": 3600.0,
        "gross_monthly_cost": 3200.0,
        "income_support_ratio": 1.02,
        "price_to_rent": 14.8,
        "town_county_score": 72.0,
        "town_county_confidence": 0.82,
        "liquidity_view": "strong",
        "scarcity_support_score": 66.0,
        "scarcity_confidence": 0.58,
        "flood_risk": "low",
        "days_on_market": 19,
        "beds": 3,
        "baths": 2.0,
        "sqft": 1600,
    }


class RentalEaseAgentTests(unittest.TestCase):
    def test_normal_case_returns_structured_output(self) -> None:
        result = RentalEaseAgent().run(sample_payload())

        self.assertIsInstance(result, RentalEaseOutput)
        self.assertGreaterEqual(result.rental_ease_score, 0.0)
        self.assertLessEqual(result.rental_ease_score, 100.0)
        self.assertEqual(result.rental_ease_label, "Stable Rental Profile")
        self.assertIsNotNone(result.estimated_days_to_rent)
        self.assertTrue(result.drivers)
        self.assertTrue(result.risks)

    def test_missing_rent_reduces_confidence_and_adds_unsupported_claim(self) -> None:
        payload = sample_payload()
        payload["estimated_monthly_rent"] = None
        payload["income_support_ratio"] = None
        payload["price_to_rent"] = None

        result = RentalEaseAgent().run(payload)

        self.assertLess(result.confidence, 0.8)
        self.assertTrue(any("rent evidence is missing" in claim for claim in result.unsupported_claims))
        self.assertGreaterEqual(result.rent_support_score, 0.0)

    def test_missing_town_prior_still_returns_safe_output(self) -> None:
        payload = sample_payload()
        payload["town"] = "Red Bank"

        result = RentalEaseAgent().run(payload)

        self.assertLess(result.confidence, 0.7)
        self.assertIsNone(result.estimated_days_to_rent)
        self.assertTrue(any("No Monmouth County rental-ease prior" in note for note in result.assumptions))

    def test_thin_evidence_lowers_confidence(self) -> None:
        result = RentalEaseAgent().run(
            RentalEaseInput(
                town="Spring Lake",
                state="NJ",
            )
        )

        self.assertLessEqual(result.confidence, 0.4)
        self.assertEqual(result.rental_ease_label, "Seasonal / Mixed")

    def test_label_mapping_supports_high_absorption(self) -> None:
        payload = sample_payload()
        payload["town"] = "Manasquan"
        payload["income_support_ratio"] = 1.15
        payload["price_to_rent"] = 13.2
        payload["town_county_score"] = 81.0
        payload["liquidity_view"] = "strong"
        payload["scarcity_support_score"] = 78.0

        result = RentalEaseAgent().run(payload)

        self.assertEqual(result.rental_ease_label, "High Absorption")

    def test_output_is_deterministic_and_bounded(self) -> None:
        payload = sample_payload()
        first = RentalEaseAgent().run(payload)
        second = RentalEaseAgent().run(payload)

        self.assertEqual(first.rental_ease_score, second.rental_ease_score)
        self.assertGreaterEqual(first.liquidity_score, 0.0)
        self.assertLessEqual(first.structural_support_score, 100.0)

    def test_zillow_rent_context_is_used_as_additional_market_backdrop(self) -> None:
        payload = sample_payload()
        payload["zillow_rent_index_current"] = 3085.0
        payload["zillow_rent_index_prior_year"] = 2940.0
        payload["zillow_renter_demand_index"] = 77.0
        payload["zillow_rent_forecast_one_year"] = 0.028
        payload["zillow_context_scope"] = "town"

        result = RentalEaseAgent().run(payload)

        self.assertTrue(result.zillow_context_used)
        self.assertTrue(any("Zillow rental research is used" in note for note in result.assumptions))
        self.assertTrue(any("Zillow rental demand context" in driver for driver in result.drivers))


if __name__ == "__main__":
    unittest.main()

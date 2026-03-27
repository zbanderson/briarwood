import unittest

from pydantic import ValidationError

from briarwood.agents.town_county.scoring import TownCountyScorer, score_town_county
from briarwood.agents.town_county.schemas import TownCountyInputs, TownCountyScore


def strong_payload() -> dict[str, object]:
    return {
        "town": "Belmar",
        "state": "NJ",
        "county": "Monmouth",
        "town_price_trend": 0.055,
        "county_price_trend": 0.048,
        "town_population_trend": 0.012,
        "county_population_trend": 0.009,
        "school_signal": 8.0,
        "flood_risk": "low",
        "liquidity_signal": "strong",
        "scarcity_signal": 0.8,
        "days_on_market": 14,
        "price_position": "supported",
    }


class TownCountyScoringTests(unittest.TestCase):
    def test_strong_location_case_scores_supportively(self) -> None:
        result = TownCountyScorer().score(strong_payload())

        self.assertIsInstance(result, TownCountyScore)
        self.assertEqual(result.location_thesis_label, "supportive")
        self.assertEqual(result.appreciation_support_view, "strong")
        self.assertEqual(result.liquidity_view, "strong")
        self.assertGreaterEqual(result.town_county_score, 70.0)
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertEqual(result.missing_inputs, [])
        self.assertEqual(result.unsupported_claims, [])

    def test_missing_county_inputs_reduce_confidence_without_fabricating_support(self) -> None:
        payload = strong_payload()
        payload["county_price_trend"] = None
        payload["county_population_trend"] = None

        result = score_town_county(payload)

        self.assertIsNone(result.county_support_score)
        self.assertLess(result.confidence, 0.80)
        self.assertIn("county_price_trend", result.missing_inputs)
        self.assertIn("county_population_trend", result.missing_inputs)
        self.assertIn("County-level structural support could not be confirmed.", result.unsupported_claims)
        self.assertTrue(result.assumptions_used)

    def test_sparse_core_data_yields_low_confidence_descriptive_only_behavior(self) -> None:
        result = TownCountyScorer().score(
            {
                "town": "Belmar",
                "state": "NJ",
                "flood_risk": "medium",
            }
        )

        self.assertEqual(result.location_thesis_label, "low-confidence")
        self.assertLess(result.confidence, 0.40)
        self.assertEqual(result.appreciation_support_view, "limited")
        self.assertIn("Location thesis is low confidence due to missing core data.", result.unsupported_claims)
        self.assertIn("insufficient core location data", result.summary)

    def test_negative_trends_and_fragile_liquidity_create_weak_thesis(self) -> None:
        result = TownCountyScorer().score(
            {
                "town": "Exampletown",
                "state": "MA",
                "town_price_trend": -0.03,
                "county_price_trend": -0.01,
                "town_population_trend": -0.015,
                "county_population_trend": -0.01,
                "school_signal": 4.0,
                "flood_risk": "high",
                "liquidity_signal": "fragile",
                "scarcity_signal": 0.1,
                "days_on_market": 85,
                "price_position": "stretched",
            }
        )

        self.assertEqual(result.location_thesis_label, "weak")
        self.assertEqual(result.liquidity_view, "fragile")
        self.assertLess(result.town_county_score, 45.0)
        self.assertTrue(result.demand_risks)

    def test_invalid_inputs_raise_validation_errors(self) -> None:
        with self.assertRaises(ValidationError):
            TownCountyInputs.model_validate(
                {
                    "town": "",
                    "state": "Massachusetts",
                    "school_signal": 12,
                    "flood_risk": "severe",
                }
            )


if __name__ == "__main__":
    unittest.main()

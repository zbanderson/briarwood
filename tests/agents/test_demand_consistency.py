import unittest

from pydantic import ValidationError

from briarwood.agents.scarcity.demand_consistency import DemandConsistencyScorer, score_demand_consistency
from briarwood.agents.scarcity.schemas import DemandConsistencyInputs, DemandConsistencyScore


def strong_payload() -> dict[str, object]:
    return {
        "town": "Belmar",
        "state": "NJ",
        "county": "Monmouth",
        "liquidity_signal": "strong",
        "months_of_supply": 2.8,
        "days_on_market": 18,
        "town_price_trend": 0.055,
        "county_price_trend": 0.045,
        "school_signal": 8.1,
    }


class DemandConsistencyTests(unittest.TestCase):
    def test_strong_case_scores_as_strong(self) -> None:
        result = DemandConsistencyScorer().score(strong_payload())

        self.assertIsInstance(result, DemandConsistencyScore)
        self.assertEqual(result.demand_consistency_label, "strong")
        self.assertGreaterEqual(result.demand_consistency_score, 75.0)
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertEqual(result.missing_inputs, [])

    def test_mixed_case_with_partial_support_scores_as_mixed_or_supportive(self) -> None:
        result = score_demand_consistency(
            {
                "town": "Belmar",
                "state": "NJ",
                "liquidity_signal": "normal",
                "months_of_supply": 4.2,
                "days_on_market": 34,
                "town_price_trend": 0.012,
            }
        )

        self.assertIn(result.demand_consistency_label, {"mixed", "supportive"})
        self.assertLess(result.confidence, 0.80)
        self.assertIn("county_price_trend", result.missing_inputs)
        self.assertIn("school_signal", result.missing_inputs)

    def test_sparse_case_stays_low_confidence(self) -> None:
        result = DemandConsistencyScorer().score(
            {
                "town": "Belmar",
                "state": "NJ",
            }
        )

        self.assertEqual(result.demand_consistency_label, "low-confidence")
        self.assertLess(result.confidence, 0.40)
        self.assertTrue(result.unsupported_claims)
        self.assertIn("descriptive only", result.summary)

    def test_fragile_case_scores_weak(self) -> None:
        result = DemandConsistencyScorer().score(
            {
                "town": "Exampletown",
                "state": "FL",
                "liquidity_signal": "fragile",
                "months_of_supply": 8.5,
                "days_on_market": 92,
                "town_price_trend": -0.02,
                "county_price_trend": -0.01,
                "school_signal": 4.1,
            }
        )

        self.assertEqual(result.demand_consistency_label, "weak")
        self.assertLess(result.demand_consistency_score, 45.0)
        self.assertTrue(result.demand_risks)

    def test_invalid_inputs_raise_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            DemandConsistencyInputs.model_validate(
                {
                    "town": "",
                    "state": "New Jersey",
                    "school_signal": 14,
                }
            )


if __name__ == "__main__":
    unittest.main()

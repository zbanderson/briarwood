import unittest

from pydantic import ValidationError

from briarwood.agents.scarcity.scarcity_support import ScarcitySupportScorer, score_scarcity_support
from briarwood.agents.scarcity.schemas import ScarcitySupportInputs, ScarcitySupportScore


def strong_payload() -> dict[str, object]:
    return {
        "demand_consistency": {
            "town": "Belmar",
            "state": "NJ",
            "county": "Monmouth",
            "liquidity_signal": "strong",
            "months_of_supply": 2.8,
            "days_on_market": 18,
            "town_price_trend": 0.055,
            "county_price_trend": 0.045,
            "school_signal": 8.1,
        },
        "location_scarcity": {
            "town": "Belmar",
            "state": "NJ",
            "anchor_type": "beach",
            "distance_to_anchor_miles": 0.18,
            "comparable_count_within_anchor_radius": 9,
            "anchor_radius_miles": 0.5,
        },
        "land_scarcity": {
            "town": "Belmar",
            "state": "NJ",
            "lot_size_sqft": 6750,
            "local_median_lot_size_sqft": 4500,
            "lot_is_corner": True,
            "adu_possible": True,
            "redevelopment_optional": True,
        },
    }


class ScarcitySupportTests(unittest.TestCase):
    def test_strong_case_scores_with_high_scarcity_support(self) -> None:
        result = ScarcitySupportScorer().score(strong_payload())

        self.assertIsInstance(result, ScarcitySupportScore)
        self.assertEqual(result.scarcity_label, "high scarcity support")
        self.assertGreaterEqual(result.scarcity_support_score, 75.0)
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertEqual(result.missing_inputs, [])
        self.assertIn("real protection from both scarcity and demand", result.buyer_takeaway)

    def test_mixed_inputs_reduce_confidence_and_support(self) -> None:
        payload = strong_payload()
        payload["demand_consistency"]["school_signal"] = None
        payload["location_scarcity"]["comparable_count_within_anchor_radius"] = None
        payload["land_scarcity"]["local_median_lot_size_sqft"] = None

        result = score_scarcity_support(payload)

        self.assertLess(result.confidence, 0.80)
        self.assertTrue(result.missing_inputs)
        self.assertTrue(result.unsupported_claims)
        self.assertTrue(result.buyer_takeaway)

    def test_invalid_payload_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            ScarcitySupportInputs.model_validate(
                {
                    "demand_consistency": {"town": "", "state": "NJ"},
                    "location_scarcity": {"town": "Belmar", "state": "NJ"},
                    "land_scarcity": {"town": "Belmar", "state": "NJ"},
                }
            )


if __name__ == "__main__":
    unittest.main()

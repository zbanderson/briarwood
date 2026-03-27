import unittest

from pydantic import ValidationError

from briarwood.agents.scarcity.location_scarcity import LocationScarcityScorer, score_location_scarcity
from briarwood.agents.scarcity.schemas import LocationScarcityInputs, LocationScarcityScore


def strong_payload() -> dict[str, object]:
    return {
        "town": "Belmar",
        "state": "NJ",
        "anchor_type": "beach",
        "distance_to_anchor_miles": 0.18,
        "comparable_count_within_anchor_radius": 9,
        "anchor_radius_miles": 0.5,
    }


class LocationScarcityTests(unittest.TestCase):
    def test_strong_location_scarcity_case_scores_strongly(self) -> None:
        result = LocationScarcityScorer().score(strong_payload())

        self.assertIsInstance(result, LocationScarcityScore)
        self.assertEqual(result.location_scarcity_label, "strong")
        self.assertGreaterEqual(result.location_scarcity_score, 75.0)
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertEqual(result.missing_inputs, [])

    def test_meaningful_case_scores_above_baseline(self) -> None:
        result = score_location_scarcity(
            {
                "town": "Asbury Park",
                "state": "NJ",
                "anchor_type": "walkable_downtown",
                "distance_to_anchor_miles": 0.65,
                "comparable_count_within_anchor_radius": 18,
                "anchor_radius_miles": 1.0,
            }
        )

        self.assertIn(result.location_scarcity_label, {"meaningful", "strong"})
        self.assertGreater(result.location_scarcity_score, 60.0)

    def test_sparse_case_stays_low_confidence(self) -> None:
        result = LocationScarcityScorer().score(
            {
                "town": "Belmar",
                "state": "NJ",
            }
        )

        self.assertEqual(result.location_scarcity_label, "low-confidence")
        self.assertLess(result.confidence, 0.40)
        self.assertTrue(result.unsupported_claims)

    def test_weak_case_scores_below_baseline(self) -> None:
        result = LocationScarcityScorer().score(
            {
                "town": "Exampletown",
                "state": "FL",
                "anchor_type": "generic_suburb",
                "distance_to_anchor_miles": 3.4,
                "comparable_count_within_anchor_radius": 75,
                "anchor_radius_miles": 1.0,
            }
        )

        self.assertEqual(result.location_scarcity_label, "weak")
        self.assertLess(result.location_scarcity_score, 45.0)

    def test_invalid_inputs_raise_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            LocationScarcityInputs.model_validate(
                {
                    "town": "",
                    "state": "New Jersey",
                    "distance_to_anchor_miles": -1,
                }
            )


if __name__ == "__main__":
    unittest.main()

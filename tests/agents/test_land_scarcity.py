import unittest

from pydantic import ValidationError

from briarwood.agents.scarcity.land_scarcity import LandScarcityScorer, score_land_scarcity
from briarwood.agents.scarcity.schemas import LandScarcityInputs, LandScarcityScore


def strong_payload() -> dict[str, object]:
    return {
        "town": "Belmar",
        "state": "NJ",
        "lot_size_sqft": 6750,
        "local_median_lot_size_sqft": 4500,
        "lot_is_corner": True,
        "adu_possible": True,
        "redevelopment_optional": True,
    }


class LandScarcityTests(unittest.TestCase):
    def test_strong_land_case_scores_strongly(self) -> None:
        result = LandScarcityScorer().score(strong_payload())

        self.assertIsInstance(result, LandScarcityScore)
        self.assertEqual(result.land_scarcity_label, "strong")
        self.assertGreaterEqual(result.land_scarcity_score, 75.0)
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertEqual(result.missing_inputs, [])

    def test_meaningful_case_scores_above_baseline(self) -> None:
        result = score_land_scarcity(
            {
                "town": "Belmar",
                "state": "NJ",
                "lot_size_sqft": 5600,
                "local_median_lot_size_sqft": 4500,
                "lot_is_corner": False,
                "adu_possible": True,
            }
        )

        self.assertIn(result.land_scarcity_label, {"meaningful", "strong"})
        self.assertGreaterEqual(result.land_scarcity_score, 60.0)

    def test_sparse_case_stays_low_confidence(self) -> None:
        result = LandScarcityScorer().score(
            {
                "town": "Belmar",
                "state": "NJ",
            }
        )

        self.assertEqual(result.land_scarcity_label, "low-confidence")
        self.assertLess(result.confidence, 0.40)
        self.assertTrue(result.unsupported_claims)

    def test_small_lot_without_optionality_scores_weak(self) -> None:
        result = LandScarcityScorer().score(
            {
                "town": "Exampletown",
                "state": "FL",
                "lot_size_sqft": 3200,
                "local_median_lot_size_sqft": 5200,
                "lot_is_corner": False,
                "adu_possible": False,
                "redevelopment_optional": False,
            }
        )

        self.assertEqual(result.land_scarcity_label, "weak")
        self.assertLess(result.land_scarcity_score, 45.0)

    def test_invalid_inputs_raise_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            LandScarcityInputs.model_validate(
                {
                    "town": "",
                    "state": "New Jersey",
                    "lot_size_sqft": -1,
                }
            )


if __name__ == "__main__":
    unittest.main()

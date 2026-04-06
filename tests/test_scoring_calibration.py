from __future__ import annotations

import unittest

from briarwood.decision_model.scoring import get_recommendation_tier


class ScoringCalibrationTests(unittest.TestCase):
    def test_recommendation_tier_thresholds_match_calibration_targets(self) -> None:
        self.assertEqual(get_recommendation_tier(3.81)[0], "Buy")
        self.assertEqual(get_recommendation_tier(3.30)[0], "Lean Buy")
        self.assertEqual(get_recommendation_tier(2.50)[0], "Hold / Dig Deeper")
        self.assertEqual(get_recommendation_tier(2.10)[0], "Lean Away")
        self.assertEqual(get_recommendation_tier(1.99)[0], "Pass")


if __name__ == "__main__":
    unittest.main()

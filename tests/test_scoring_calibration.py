from __future__ import annotations

import unittest

from briarwood.recommendations import recommendation_action_from_score, recommendation_label_from_score


class ScoringCalibrationTests(unittest.TestCase):
    def test_recommendation_tier_thresholds_match_calibration_targets(self) -> None:
        self.assertEqual(recommendation_label_from_score(3.81), "Buy")
        self.assertEqual(recommendation_label_from_score(3.30), "Buy")
        self.assertEqual(recommendation_label_from_score(2.50), "Neutral")
        self.assertEqual(recommendation_label_from_score(2.10), "Avoid")
        self.assertEqual(recommendation_label_from_score(1.99), "Avoid")
        self.assertTrue(recommendation_action_from_score(3.81))


if __name__ == "__main__":
    unittest.main()

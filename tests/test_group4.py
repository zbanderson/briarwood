"""Tests for Group 4: Quick Fixes."""
from __future__ import annotations

import unittest

from briarwood.modules.liquidity_signal import _dom_score


class DomScoreSmoothTests(unittest.TestCase):
    """Verify _dom_score uses smooth interpolation instead of step function."""

    def test_dom_7_top_tier(self) -> None:
        self.assertAlmostEqual(_dom_score(7), 96.0)

    def test_dom_21_boundary(self) -> None:
        self.assertAlmostEqual(_dom_score(21), 82.0)

    def test_dom_45_boundary(self) -> None:
        self.assertAlmostEqual(_dom_score(45), 60.0)

    def test_dom_90_boundary(self) -> None:
        self.assertAlmostEqual(_dom_score(90), 32.0)

    def test_dom_above_90(self) -> None:
        self.assertAlmostEqual(_dom_score(120), 12.0)

    def test_dom_none(self) -> None:
        self.assertIsNone(_dom_score(None))

    def test_smooth_between_7_and_21(self) -> None:
        """DOM 14 should be between 82 and 96, not a hard step."""
        score = _dom_score(14)
        self.assertIsNotNone(score)
        self.assertGreater(score, 82.0)
        self.assertLess(score, 96.0)

    def test_smooth_between_21_and_45(self) -> None:
        """DOM 30 should be between 60 and 82."""
        score = _dom_score(30)
        self.assertIsNotNone(score)
        self.assertGreater(score, 60.0)
        self.assertLess(score, 82.0)

    def test_no_cliff_at_8(self) -> None:
        """Old step function had a 14-point cliff from DOM 7 to 8. Verify smooth transition."""
        score_7 = _dom_score(7)
        score_8 = _dom_score(8)
        self.assertIsNotNone(score_7)
        self.assertIsNotNone(score_8)
        self.assertLess(abs(score_7 - score_8), 3.0, "Should not have a cliff at DOM 7→8")


if __name__ == "__main__":
    unittest.main()

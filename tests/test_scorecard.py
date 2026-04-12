import unittest

from briarwood.runner import run_report
from briarwood.scorecard import build_scorecard


class ScorecardTests(unittest.TestCase):
    def test_scorecard_builds_from_report(self) -> None:
        report = run_report("data/sample_property.json")

        scorecard = build_scorecard(report)

        self.assertGreaterEqual(scorecard.value_support.score, 0.0)
        self.assertTrue(scorecard.value_support.source_modules)
        self.assertTrue(scorecard.location_quality.key_drivers)
        self.assertGreaterEqual(scorecard.overall.score, 0.0)



if __name__ == "__main__":
    unittest.main()

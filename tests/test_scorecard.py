import unittest

from briarwood.dashboard_contract import build_dashboard_analysis_summary
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

    def test_dashboard_contract_exposes_sections_and_dependencies(self) -> None:
        report = run_report("data/sample_property.json")

        contract = build_dashboard_analysis_summary(report)

        self.assertIn("value_support", contract.sections)
        self.assertIn("current_value", contract.module_dependencies)
        self.assertTrue(contract.sections["forward"].source_modules)
        self.assertTrue(contract.scorecard.confidence.narrative)


if __name__ == "__main__":
    unittest.main()

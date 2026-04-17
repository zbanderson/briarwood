from __future__ import annotations

import unittest

from briarwood.eval.operational_sweep import run_operational_sweep


class OperationalSweepTests(unittest.TestCase):
    def test_operational_sweep_returns_expected_sections(self) -> None:
        report = run_operational_sweep()

        self.assertIn("generated_at", report)
        self.assertIn("environment", report)
        self.assertIn("evaluation_surfaces", report)
        self.assertIn("tavily_recommendations", report)
        self.assertIn("attom_recommendations", report)
        self.assertTrue(any(row["name"] == "valuation" for row in report["scoped_modules"]))
        statuses = {row["status"] for row in report["evaluation_surfaces"]}
        self.assertTrue(statuses <= {"runnable_and_passing", "runnable_but_failing", "blocked_by_environment"})


if __name__ == "__main__":
    unittest.main()

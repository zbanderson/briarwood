import unittest

from briarwood.agents.school_signal import SchoolSignalAgent


class SchoolSignalAgentTests(unittest.TestCase):
    def test_agent_builds_supportive_signal_from_public_proxy_inputs(self) -> None:
        result = SchoolSignalAgent().evaluate(
            {
                "geography_name": "Belmar",
                "state": "NJ",
                "achievement_index": 66,
                "growth_index": 63,
                "readiness_index": None,
                "chronic_absenteeism_pct": 11.0,
                "student_teacher_ratio": 13.5,
                "district_coverage": 0.72,
                "source_review_quality": 0.68,
                "as_of": "2026-03-01",
                "refresh_frequency_days": 365,
            }
        )

        self.assertGreaterEqual(result.school_signal, 5.0)
        self.assertLessEqual(result.school_signal, 10.0)
        self.assertGreater(result.confidence, 0.4)
        self.assertIn("proxy", result.assumptions[0].lower())
        self.assertTrue(result.unsupported_claims)

    def test_agent_handles_sparse_inputs_without_fake_precision(self) -> None:
        result = SchoolSignalAgent().evaluate(
            {
                "geography_name": "Test Town",
                "state": "NJ",
                "achievement_index": None,
                "growth_index": None,
                "readiness_index": None,
                "chronic_absenteeism_pct": None,
                "student_teacher_ratio": None,
            }
        )

        self.assertEqual(result.school_signal, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("lacks enough school data", result.summary.lower())


if __name__ == "__main__":
    unittest.main()

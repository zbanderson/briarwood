from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.dash_app.app import (
    _build_landing_subject,
    _can_auto_run_landing_analysis,
    _prime_saved_property_question,
)
from briarwood.dash_app.intelligence import (
    build_area_or_generic_result,
    detect_context_type,
)
from briarwood.intelligence_capture import build_routed_capture_record


class IntelligenceIntakeTests(unittest.TestCase):
    def test_can_auto_run_landing_analysis_with_resolved_address(self) -> None:
        self.assertTrue(
            _can_auto_run_landing_analysis(
                {
                    "route": "new_property",
                    "address": "1205 Jeffrey Street, Asbury Park, NJ",
                }
            )
        )

    def test_cannot_auto_run_landing_analysis_without_address(self) -> None:
        self.assertFalse(
            _can_auto_run_landing_analysis(
                {
                    "route": "new_property",
                    "address": "",
                }
            )
        )

    def test_build_landing_subject_keeps_question_and_source_context(self) -> None:
        subject = _build_landing_subject(
            {
                "route": "new_property",
                "address": "1205 Jeffrey Street, Asbury Park, NJ",
                "source_url": "https://www.zillow.com/example",
                "source_label": "Zillow",
                "notes": "URL provided by user.",
            },
            question="Should I buy this and rent it out?",
        )

        self.assertEqual(subject["address"], "1205 Jeffrey Street, Asbury Park, NJ")
        self.assertEqual(subject["town"], "Asbury Park")
        self.assertEqual(subject["state"], "NJ")
        self.assertIn("Question: Should I buy this and rent it out?", str(subject["notes"]))
        self.assertIn("Source URL (Zillow): https://www.zillow.com/example", str(subject["notes"]))

    def test_prime_saved_property_question_reruns_with_prompt(self) -> None:
        with patch("briarwood.dash_app.app._run_followup_for_property") as mock_run:
            feedback = _prime_saved_property_question(
                "526-west-end-ave",
                "Does Avon have upside potential if I buy at 1.3?",
            )

        mock_run.assert_called_once_with(
            "526-west-end-ave",
            "Does Avon have upside potential if I buy at 1.3?",
            [],
            "landing_question",
        )
        self.assertIn("Ran intelligence", feedback)

    def test_detect_context_type_for_property_route(self) -> None:
        self.assertEqual(
            detect_context_type(
                "Should I buy this?",
                resolution_route="saved_property",
            ),
            "property",
        )

    def test_detect_context_type_for_area_query(self) -> None:
        self.assertEqual(
            detect_context_type(
                "What could go wrong in Belmar?",
                resolution_route="town",
                selected_town="Belmar",
            ),
            "area",
        )

    def test_detect_context_type_for_generic_query(self) -> None:
        self.assertEqual(
            detect_context_type(
                "What should I do?",
                resolution_route="empty",
            ),
            "generic",
        )

    def test_build_area_result_is_conditional_but_not_missing_context(self) -> None:
        session = build_area_or_generic_result(
            question="What should I know about Belmar?",
            context_type="area",
            selected_town="Belmar",
        )

        self.assertEqual(session["context_type"], "area")
        self.assertFalse(session["missing_context"])
        self.assertTrue(session["was_conditional_answer"])
        self.assertEqual(session["lower_section"], "town_results")

    def test_build_generic_result_marks_missing_context(self) -> None:
        session = build_area_or_generic_result(
            question="What should I do?",
            context_type="generic",
        )

        self.assertEqual(session["context_type"], "generic")
        self.assertTrue(session["missing_context"])
        self.assertTrue(session["was_conditional_answer"])

    def test_capture_record_tags_unsupported_or_conditional_paths(self) -> None:
        record = build_routed_capture_record(
            question="What should I know about Belmar?",
            context_type="area",
            routing_decision={"parser_output": {}, "selected_modules": []},
            execution_mode="conditional",
            unified_output={
                "recommendation": "Need more context",
                "decision": "mixed",
                "confidence": 0.2,
                "analysis_depth_used": "snapshot",
                "recommended_next_run": None,
            },
            missing_context=True,
            was_conditional_answer=True,
        )

        self.assertIn("low-confidence-due-to-missing-inputs", record["tags"])
        self.assertIn("missing-scenario-type", record["tags"])
        self.assertIn("unknown-question-pattern", record["tags"])


if __name__ == "__main__":
    unittest.main()

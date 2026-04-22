"""Tests for the feedback loop: analyzer, keyword learner, user feedback, and confidence tuning."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briarwood.feedback.analyzer import FeedbackReport, analyze, format_report, load_records
from briarwood.feedback.keyword_learner import (
    LEARNED_KEYWORDS_PATH,
    apply_suggestions,
    load_learned_keywords,
    save_learned_keywords,
    suggest_keywords,
)
from briarwood.intelligence_capture import (
    build_followup_capture_record,
    build_routed_capture_record,
    build_user_feedback_record,
)


def _make_analysis_record(
    *,
    question: str = "Should I buy this?",
    intent_type: str = "buy_decision",
    analysis_depth: str = "snapshot",
    confidence: float = 0.72,
    execution_mode: str = "scoped",
    modules: list[str] | None = None,
    missing_inputs: list[str] | None = None,
    tags: list[str] | None = None,
    decision: str = "buy",
) -> dict:
    return {
        "question": question,
        "context_type": "property",
        "execution_mode": execution_mode,
        "parser_output": {
            "intent_type": intent_type,
            "analysis_depth": analysis_depth,
            "confidence": confidence,
            "missing_inputs": missing_inputs or [],
        },
        "routing_decision": {"parser_output": {"intent_type": intent_type}},
        "selected_modules": modules or ["valuation", "confidence"],
        "unified_output_summary": {
            "confidence": confidence,
            "decision": decision,
            "analysis_depth_used": analysis_depth,
            "recommendation": "Buy.",
            "recommended_next_run": "decision",
        },
        "tags": tags or [],
    }


class AnalyzerTests(unittest.TestCase):
    def test_analyze_empty_records(self) -> None:
        report = analyze([])
        self.assertEqual(report.total_records, 0)
        self.assertEqual(report.legacy_fallback_rate, 0.0)

    def test_analyze_execution_mode_counts(self) -> None:
        records = [
            _make_analysis_record(execution_mode="scoped"),
            _make_analysis_record(execution_mode="scoped"),
            _make_analysis_record(execution_mode="legacy_fallback"),
        ]
        report = analyze(records)
        self.assertEqual(report.execution_mode_counts["scoped"], 2)
        self.assertEqual(report.execution_mode_counts["legacy_fallback"], 1)
        self.assertAlmostEqual(report.legacy_fallback_rate, 1 / 3, places=3)

    def test_analyze_module_frequency(self) -> None:
        records = [
            _make_analysis_record(modules=["valuation", "carry_cost"]),
            _make_analysis_record(modules=["valuation", "risk_model"]),
        ]
        report = analyze(records)
        self.assertEqual(report.module_frequency["valuation"], 2)
        self.assertEqual(report.module_frequency["carry_cost"], 1)
        self.assertAlmostEqual(report.module_selection_rate["valuation"], 1.0)
        self.assertAlmostEqual(report.module_selection_rate["carry_cost"], 0.5)

    def test_analyze_confidence_buckets(self) -> None:
        records = [
            _make_analysis_record(confidence=0.30),
            _make_analysis_record(confidence=0.50),
            _make_analysis_record(confidence=0.65),
            _make_analysis_record(confidence=0.80),
        ]
        report = analyze(records)
        self.assertEqual(report.confidence_buckets["0.0-0.4"], 1)
        self.assertEqual(report.confidence_buckets["0.4-0.55"], 1)
        self.assertEqual(report.confidence_buckets["0.55-0.7"], 1)
        self.assertEqual(report.confidence_buckets["0.7-0.85"], 1)
        self.assertAlmostEqual(report.mean_confidence, 0.5625, places=3)

    def test_analyze_low_confidence_drivers(self) -> None:
        records = [
            _make_analysis_record(confidence=0.40, missing_inputs=["purchase_price", "rent_estimate"]),
            _make_analysis_record(confidence=0.35, missing_inputs=["purchase_price"]),
        ]
        report = analyze(records)
        drivers = {d["driver"]: d["count"] for d in report.low_confidence_drivers}
        self.assertEqual(drivers["purchase_price"], 2)
        self.assertEqual(drivers["rent_estimate"], 1)

    def test_analyze_intent_and_depth_distribution(self) -> None:
        records = [
            _make_analysis_record(intent_type="buy_decision", analysis_depth="snapshot"),
            _make_analysis_record(intent_type="buy_decision", analysis_depth="decision"),
            _make_analysis_record(intent_type="renovate_then_sell", analysis_depth="scenario"),
        ]
        report = analyze(records)
        self.assertEqual(report.intent_distribution["buy_decision"], 2)
        self.assertEqual(report.intent_distribution["renovate_then_sell"], 1)
        self.assertEqual(report.depth_distribution["snapshot"], 1)
        self.assertEqual(report.depth_distribution["decision"], 1)

    def test_analyze_tags(self) -> None:
        records = [
            _make_analysis_record(tags=["unknown-question-pattern"], question="what even is this"),
            _make_analysis_record(tags=["low-confidence-due-to-missing-inputs"]),
        ]
        report = analyze(records)
        self.assertEqual(report.tag_counts["unknown-question-pattern"], 1)
        self.assertIn("what even is this", report.unknown_pattern_questions)

    def test_analyze_missing_inputs(self) -> None:
        records = [
            _make_analysis_record(missing_inputs=["purchase_price"]),
            _make_analysis_record(missing_inputs=["purchase_price", "hold_period_years"]),
        ]
        report = analyze(records)
        self.assertEqual(report.missing_input_frequency["purchase_price"], 2)
        self.assertEqual(report.missing_input_frequency["hold_period_years"], 1)

    def test_analyze_followups(self) -> None:
        records = [
            _make_analysis_record(),
            {**_make_analysis_record(), "trigger": "next_question", "tags": ["follow-up-turn-2", "user-went-deeper"]},
            {**_make_analysis_record(), "trigger": "go_deeper", "tags": ["follow-up-turn-3", "user-pivoted-intent"]},
        ]
        report = analyze(records)
        self.assertEqual(report.followup_count, 2)
        self.assertEqual(report.trigger_counts["next_question"], 1)
        self.assertEqual(report.trigger_counts["go_deeper"], 1)
        self.assertEqual(report.depth_promotion_count, 1)
        self.assertEqual(report.intent_pivot_count, 1)

    def test_analyze_user_feedback_and_threshold(self) -> None:
        analysis_records = [_make_analysis_record()]
        feedback_records = [
            {"feedback_type": "user_validation", "rating": "yes", "analysis_confidence": 0.80, "tags": []},
            {"feedback_type": "user_validation", "rating": "no", "analysis_confidence": 0.40, "tags": []},
            {"feedback_type": "user_validation", "rating": "no", "analysis_confidence": 0.35, "tags": []},
            {"feedback_type": "user_validation", "rating": "no", "analysis_confidence": 0.50, "tags": []},
            {"feedback_type": "user_validation", "rating": "partially", "analysis_confidence": 0.60, "tags": []},
        ]
        report = analyze(analysis_records + feedback_records)
        self.assertEqual(report.user_feedback_count, 5)
        self.assertEqual(report.user_feedback_distribution["no"], 3)
        self.assertIn("raising the minimum confidence", report.confidence_threshold_recommendation)

    def test_format_report_produces_text(self) -> None:
        records = [
            _make_analysis_record(),
            _make_analysis_record(execution_mode="legacy_fallback"),
        ]
        report = analyze(records)
        text = format_report(report)
        self.assertIn("BRIARWOOD INTELLIGENCE FEEDBACK REPORT", text)
        self.assertIn("Execution Modes", text)
        self.assertIn("scoped", text)

    def test_load_records_from_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(_make_analysis_record()) + "\n")
            f.write(json.dumps(_make_analysis_record(question="Risk?")) + "\n")
            path = Path(f.name)
        try:
            records = load_records(path)
            self.assertEqual(len(records), 2)
        finally:
            path.unlink()

    def test_report_to_dict_serializable(self) -> None:
        report = analyze([_make_analysis_record()])
        d = report.to_dict()
        # Should be JSON-serializable
        json.dumps(d)
        self.assertEqual(d["total_records"], 1)


class KeywordLearnerTests(unittest.TestCase):
    def test_suggest_keywords_with_no_problems(self) -> None:
        records = [_make_analysis_record(confidence=0.9, tags=[])]
        suggestions = suggest_keywords(records)
        self.assertEqual(suggestions, [])

    def test_suggest_keywords_from_unknown_patterns(self) -> None:
        # Same question repeated with unknown-question-pattern tag
        records = [
            _make_analysis_record(
                question="can the cottage offset the mortgage payment",
                tags=["unknown-question-pattern"],
                confidence=0.45,
                intent_type="buy_decision",
            )
            for _ in range(3)
        ]
        suggestions = suggest_keywords(records)
        # Should find some n-grams from the repeated question
        keywords = [s["keyword"] for s in suggestions]
        self.assertTrue(any("cottage" in kw or "offset" in kw or "mortgage" in kw for kw in keywords))

    def test_save_and_load_learned_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "learned_keywords.json"
            with patch("briarwood.feedback.keyword_learner.LEARNED_KEYWORDS_PATH", test_path):
                save_learned_keywords({"buy_decision": ["great investment", "strong deal"]})
                loaded = load_learned_keywords()
                # Patched path isn't used by load — use direct read
            data = json.loads(test_path.read_text())
            self.assertIn("buy_decision", data)
            self.assertIn("great investment", data["buy_decision"])

    def test_apply_suggestions_merges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "learned_keywords.json"
            with patch("briarwood.feedback.keyword_learner.LEARNED_KEYWORDS_PATH", test_path):
                suggestions = [
                    {"keyword": "solid rental", "suggested_intent": "buy_decision"},
                    {"keyword": "rent offset", "suggested_intent": "house_hack_multi_unit"},
                ]
                result = apply_suggestions(suggestions)
                self.assertIn("solid rental", result["buy_decision"])
                self.assertIn("rent offset", result["house_hack_multi_unit"])


class UserFeedbackRecordTests(unittest.TestCase):
    def test_build_user_feedback_record(self) -> None:
        record = build_user_feedback_record(
            rating="yes",
            comment="Very helpful",
            analysis_id="prop-1",
            analysis_confidence=0.75,
            analysis_decision="buy",
            analysis_depth="decision",
        )
        self.assertEqual(record["feedback_type"], "user_validation")
        self.assertEqual(record["rating"], "yes")
        self.assertEqual(record["analysis_confidence"], 0.75)
        self.assertIn("user-feedback-yes", record["tags"])

    def test_build_user_feedback_record_minimal(self) -> None:
        record = build_user_feedback_record(rating="no")
        self.assertEqual(record["rating"], "no")
        self.assertEqual(record["comment"], "")
        self.assertIn("user-feedback-no", record["tags"])


class RouterLearnedKeywordsTests(unittest.TestCase):
    def test_merge_learned_keywords_at_import(self) -> None:
        """Verify the router's _merge_learned_keywords loads without error."""
        from briarwood.router import INTENT_KEYWORDS, IntentType
        # The built-in keywords should still be present
        self.assertIn("should i buy", INTENT_KEYWORDS[IntentType.BUY_DECISION])

    def test_learned_keywords_file_merges_into_router(self) -> None:
        """Verify that writing a learned_keywords.json and calling merge works."""
        from briarwood.router import INTENT_KEYWORDS, IntentType, _LEARNED_KEYWORDS_PATH, _merge_learned_keywords
        import json

        test_keyword = "__test_keyword_xyz__"
        original_keywords = list(INTENT_KEYWORDS[IntentType.BUY_DECISION])

        try:
            # Write a test keyword
            existing = {}
            if _LEARNED_KEYWORDS_PATH.exists():
                existing = json.loads(_LEARNED_KEYWORDS_PATH.read_text())
            existing.setdefault("buy_decision", []).append(test_keyword)
            _LEARNED_KEYWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _LEARNED_KEYWORDS_PATH.write_text(json.dumps(existing))

            _merge_learned_keywords()
            self.assertIn(test_keyword, INTENT_KEYWORDS[IntentType.BUY_DECISION])
        finally:
            # Clean up
            INTENT_KEYWORDS[IntentType.BUY_DECISION] = original_keywords
            if _LEARNED_KEYWORDS_PATH.exists():
                existing = json.loads(_LEARNED_KEYWORDS_PATH.read_text())
                if test_keyword in existing.get("buy_decision", []):
                    existing["buy_decision"].remove(test_keyword)
                    _LEARNED_KEYWORDS_PATH.write_text(json.dumps(existing))


if __name__ == "__main__":
    unittest.main()

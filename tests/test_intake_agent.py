from __future__ import annotations

import unittest

from briarwood.dash_app.intelligence import build_area_or_generic_result
from briarwood.intake_agent import (
    IntakeContextType,
    IntakeExecutionMode,
    IntakeRequest,
    IntakeTriageStatus,
    classify_analysis_lenses,
    dispatch_triage_decision,
    triage_intake_request,
)
from briarwood.intelligence_capture import build_intake_agent_capture_record


class IntakeAgentTests(unittest.TestCase):
    def test_property_question_with_saved_property_routes_to_routed_analysis(self) -> None:
        decision = triage_intake_request(
            IntakeRequest(
                user_question="Should I buy this at 1.3?",
                resolved_context={"route": "saved_property", "property_id": "526-west-end"},
            )
        )

        self.assertEqual(decision.context_type, IntakeContextType.PROPERTY)
        self.assertEqual(decision.triage_status, IntakeTriageStatus.READY)
        self.assertEqual(decision.recommended_execution_mode, IntakeExecutionMode.PROPERTY_ROUTED_ANALYSIS)
        self.assertTrue(decision.should_run_analysis)

    def test_new_property_without_address_needs_property_details(self) -> None:
        decision = triage_intake_request(
            IntakeRequest(
                user_question="Tell me if this has upside",
                address_or_area="",
                listing_url="",
                resolved_context={"route": "new_property", "address": ""},
            )
        )

        self.assertEqual(decision.context_type, IntakeContextType.PROPERTY)
        self.assertEqual(decision.triage_status, IntakeTriageStatus.NEEDS_PROPERTY_DETAILS)
        self.assertEqual(decision.recommended_execution_mode, IntakeExecutionMode.PROPERTY_INTAKE_REQUIRED)

    def test_area_question_routes_to_area_only(self) -> None:
        decision = triage_intake_request(
            IntakeRequest(
                user_question="Does Avon have upside potential?",
                address_or_area="Avon-by-the-Sea",
                resolved_context={"route": "town", "town": "Avon-by-the-Sea"},
            )
        )

        self.assertEqual(decision.context_type, IntakeContextType.AREA)
        self.assertEqual(decision.triage_status, IntakeTriageStatus.AREA_ONLY)
        self.assertEqual(decision.recommended_execution_mode, IntakeExecutionMode.AREA_CONDITIONAL_ANSWER)

    def test_generic_question_needs_context(self) -> None:
        decision = triage_intake_request(
            IntakeRequest(
                user_question="What should I do?",
                resolved_context={"route": "empty"},
            )
        )

        self.assertEqual(decision.context_type, IntakeContextType.GENERIC)
        self.assertEqual(decision.triage_status, IntakeTriageStatus.NEEDS_CONTEXT)
        self.assertTrue(decision.clarification_prompt)

    def test_market_upside_prompt_is_not_classified_as_future_income_only(self) -> None:
        lenses = classify_analysis_lenses(
            "Does Avon have upside if I get in at 20% below ask in a premium market?"
        )

        self.assertIn("market_upside", [item.value for item in lenses])
        self.assertIn("valuation", [item.value for item in lenses])
        self.assertNotEqual([item.value for item in lenses], ["future_income"])

    def test_area_result_uses_market_upside_lens(self) -> None:
        session = build_area_or_generic_result(
            question="Does Avon have upside potential?",
            context_type="area",
            selected_town="Avon-by-the-Sea",
            analysis_lenses=["market_upside"],
        )

        self.assertIn("premium search zone", str(session["recommendation"]).lower())
        self.assertIn("entry basis", str(session["best_path"]).lower())

    def test_dispatch_triage_decision_builds_chat_messages(self) -> None:
        decision = triage_intake_request(
            IntakeRequest(
                user_question="Should I buy 526 W End Ave?",
                resolved_context={"route": "saved_property", "property_id": "526-west-end", "address": "526 W End Ave, Avon-by-the-Sea, NJ"},
            )
        )
        session = dispatch_triage_decision(decision)

        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.messages[0].role, "user")
        self.assertEqual(session.messages[1].role, "assistant")
        self.assertEqual(session.latest_execution_mode, "property_routed_analysis")

    def test_intake_capture_tags_context_and_reroute(self) -> None:
        record = build_intake_agent_capture_record(
            question="Does Avon have upside?",
            triage_decision={
                "context_type": "area",
                "triage_status": "area_only",
                "recommended_execution_mode": "area_conditional_answer",
                "resolved_entity": {"town": "Avon-by-the-Sea"},
            },
            execution_mode="area_conditional_answer",
            prior_session={
                "latest_triage_decision": {
                    "context_type": "generic",
                    "recommended_execution_mode": "generic_clarification",
                }
            },
            final_answer_conditional=True,
        )

        self.assertIn("area-question", record["tags"])
        self.assertIn("question-rerouted", record["tags"])
        self.assertIn("answer-misaligned", record["tags"])


if __name__ == "__main__":
    unittest.main()

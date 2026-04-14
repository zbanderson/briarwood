from __future__ import annotations

import unittest

from briarwood.router import parse_intent_and_depth, route_user_input
from briarwood.routing_schema import (
    AnalysisDepth,
    ExitOption,
    IntentType,
    ModuleName,
    OccupancyType,
    ParserOutput,
)


class RoutingBehaviorTests(unittest.TestCase):
    def test_generic_buy_question_routes_to_buy_decision_snapshot(self) -> None:
        decision = route_user_input("Should I buy this?")

        self.assertEqual(decision.intent_type, IntentType.BUY_DECISION)
        self.assertEqual(decision.analysis_depth, AnalysisDepth.SNAPSHOT)
        self.assertIn(ModuleName.VALUATION, decision.selected_modules)
        self.assertIn(ModuleName.RISK_MODEL, decision.selected_modules)

    def test_short_hold_owner_occupant_routes_to_resale_relevant_path(self) -> None:
        decision = route_user_input("We'd live here for 2 years and then maybe sell")

        self.assertEqual(decision.intent_type, IntentType.OWNER_OCCUPANT_SHORT_HOLD)
        self.assertEqual(decision.parser_output.hold_period_years, 2.0)
        self.assertIn(ExitOption.SELL, decision.parser_output.exit_options)
        self.assertIn(ModuleName.RESALE_SCENARIO, decision.selected_modules)

    def test_owner_occupant_then_rent_makes_hold_to_rent_eligible(self) -> None:
        decision = route_user_input("We would live here first, then rent it out")

        self.assertEqual(decision.intent_type, IntentType.OWNER_OCCUPANT_THEN_RENT)
        self.assertIn(ModuleName.HOLD_TO_RENT, decision.selected_modules)

    def test_renovate_then_sell_routes_to_arv_modules_when_depth_permits(self) -> None:
        decision = route_user_input("Could we renovate this and sell it?")

        self.assertEqual(decision.intent_type, IntentType.RENOVATE_THEN_SELL)
        self.assertIn(ModuleName.RENOVATION_IMPACT, decision.selected_modules)
        self.assertIn(ModuleName.ARV_MODEL, decision.selected_modules)

    def test_house_hack_multi_unit_detects_additional_units(self) -> None:
        decision = route_user_input("Can the back house offset the payment?")

        self.assertEqual(decision.intent_type, IntentType.HOUSE_HACK_MULTI_UNIT)
        self.assertTrue(decision.parser_output.has_additional_units)
        self.assertIn(ModuleName.UNIT_INCOME_OFFSET, decision.selected_modules)

    def test_deep_rent_question_routes_to_deeper_scope(self) -> None:
        decision = route_user_input(
            "What could my forward rent look like if we buy this and renovate after 3 years?"
        )

        self.assertIn(decision.analysis_depth, {AnalysisDepth.SCENARIO, AnalysisDepth.DEEP_DIVE})
        self.assertIn("future_income", decision.parser_output.question_focus)
        self.assertIn("where_is_value", decision.parser_output.question_focus)
        self.assertIn(ModuleName.RENTAL_OPTION, decision.selected_modules)
        self.assertIn(ModuleName.RENOVATION_IMPACT, decision.selected_modules)

    def test_confidence_fallback_uses_llm_parser_when_rules_are_weak(self) -> None:
        llm_result = ParserOutput(
            intent_type=IntentType.HOUSE_HACK_MULTI_UNIT,
            analysis_depth=AnalysisDepth.DEEP_DIVE,
            question_focus=["future_income", "best_path"],
            hold_period_years=None,
            occupancy_type=OccupancyType.OWNER_OCCUPANT,
            renovation_plan=None,
            exit_options=[ExitOption.RENT, ExitOption.HOLD],
            has_additional_units=True,
            confidence=0.93,
            missing_inputs=[],
        )

        parsed = parse_intent_and_depth(
            "Help me think through this property.",
            llm_parser=lambda _text: llm_result,
            confidence_threshold=0.7,
        )

        self.assertIs(parsed, llm_result)

    def test_confidence_no_fallback_returns_rules_result(self) -> None:
        parsed = parse_intent_and_depth(
            "Help me think through this property.",
            llm_parser=None,
            confidence_threshold=0.7,
        )

        self.assertIsInstance(parsed, ParserOutput)
        self.assertLess(parsed.confidence, 0.7)


if __name__ == "__main__":
    unittest.main()

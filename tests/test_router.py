from __future__ import annotations

import unittest

from briarwood.router import (
    RoutingError,
    filter_modules_by_depth_and_focus,
    infer_hold_period_years,
    infer_intent_rules,
    normalize_text,
    parse_intent_and_depth,
    route_user_input,
)
from briarwood.routing_schema import (
    AnalysisDepth,
    ExitOption,
    IntentType,
    ModuleName,
    OccupancyType,
    ParserOutput,
)


class RouterTests(unittest.TestCase):
    def test_normalize_text_rejects_empty_input(self) -> None:
        with self.assertRaises(RoutingError):
            normalize_text("   ")

    def test_simple_buy_question_routes_to_snapshot(self) -> None:
        result = infer_intent_rules("Should I buy this?")

        self.assertEqual(result.intent_type, IntentType.BUY_DECISION)
        self.assertEqual(result.analysis_depth, AnalysisDepth.SNAPSHOT)
        self.assertIn("should_i_buy", result.question_focus)

    def test_forward_rent_and_renovation_question_routes_to_scenario(self) -> None:
        result = infer_intent_rules(
            "What could my forward rent look like if we buy this and renovate after 3 years?"
        )

        self.assertEqual(result.analysis_depth, AnalysisDepth.SCENARIO)
        self.assertIn(result.intent_type, {IntentType.OWNER_OCCUPANT_THEN_RENT, IntentType.RENOVATE_THEN_SELL})
        self.assertIn("future_income", result.question_focus)
        self.assertEqual(result.hold_period_years, 3.0)

    def test_hold_period_extracts_months_as_fractional_years(self) -> None:
        self.assertEqual(infer_hold_period_years("Could we sell after 18 months?"), 1.5)

    def test_module_filter_preserves_confidence_and_focus_modules(self) -> None:
        modules = filter_modules_by_depth_and_focus(
            intent_type=IntentType.OWNER_OCCUPANT_THEN_RENT,
            analysis_depth=AnalysisDepth.SCENARIO,
            question_focus=["future_income", "best_path"],
        )

        self.assertIn(ModuleName.CONFIDENCE, modules)
        self.assertIn(ModuleName.RENTAL_OPTION, modules)
        self.assertIn(ModuleName.HOLD_TO_RENT, modules)
        self.assertNotIn(ModuleName.RENT_STABILIZATION, modules)

    def test_parse_uses_llm_fallback_when_rules_confidence_is_low(self) -> None:
        llm_output = ParserOutput(
            intent_type=IntentType.HOUSE_HACK_MULTI_UNIT,
            analysis_depth=AnalysisDepth.DEEP_DIVE,
            question_focus=["future_income", "best_path"],
            occupancy_type=OccupancyType.OWNER_OCCUPANT,
            exit_options=[ExitOption.RENT, ExitOption.HOLD],
            confidence=0.91,
            has_additional_units=True,
            missing_inputs=[],
        )

        parsed = parse_intent_and_depth(
            "Help me think about this property.",
            llm_parser=lambda _text: llm_output,
            confidence_threshold=0.7,
        )

        self.assertEqual(parsed.intent_type, IntentType.HOUSE_HACK_MULTI_UNIT)
        self.assertEqual(parsed.analysis_depth, AnalysisDepth.DEEP_DIVE)

    def test_route_user_input_builds_routing_decision(self) -> None:
        decision = route_user_input("Should I buy this duplex and rent one unit out?")

        self.assertEqual(decision.intent_type, IntentType.HOUSE_HACK_MULTI_UNIT)
        self.assertIn(ModuleName.CONFIDENCE, decision.selected_modules)
        self.assertGreaterEqual(len(decision.core_questions), 1)

    def test_hidden_upside_focus_pulls_in_renovation_and_arv_for_flip(self) -> None:
        # F5: RENOVATE_THEN_SELL universe owns RENOVATION_IMPACT / ARV_MODEL
        # / RESALE_SCENARIO — hidden_upside focus should surface them even at
        # decision depth, where they aren't in the depth baseline.
        modules = filter_modules_by_depth_and_focus(
            intent_type=IntentType.RENOVATE_THEN_SELL,
            analysis_depth=AnalysisDepth.DECISION,
            question_focus=["hidden_upside"],
        )

        self.assertIn(ModuleName.RENOVATION_IMPACT, modules)
        self.assertIn(ModuleName.ARV_MODEL, modules)
        self.assertIn(ModuleName.RESALE_SCENARIO, modules)

    def test_hidden_upside_focus_pulls_in_unit_income_for_house_hack(self) -> None:
        # F5: HOUSE_HACK_MULTI_UNIT universe owns UNIT_INCOME_OFFSET; hidden
        # upside should keep it selected and never silently drop it.
        modules = filter_modules_by_depth_and_focus(
            intent_type=IntentType.HOUSE_HACK_MULTI_UNIT,
            analysis_depth=AnalysisDepth.DECISION,
            question_focus=["hidden_upside"],
        )

        self.assertIn(ModuleName.UNIT_INCOME_OFFSET, modules)
        self.assertIn(ModuleName.VALUATION, modules)


if __name__ == "__main__":
    unittest.main()

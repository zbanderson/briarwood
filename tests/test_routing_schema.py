from __future__ import annotations

import unittest

from pydantic import ValidationError

from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionType,
    EngineOutput,
    ExitOption,
    IntentType,
    ModuleName,
    ModulePayload,
    OccupancyType,
    ParserOutput,
    RoutingDecision,
    UnifiedIntelligenceOutput,
)


class RoutingSchemaTests(unittest.TestCase):
    def test_parser_output_normalizes_question_focus(self) -> None:
        parsed = ParserOutput(
            intent_type=IntentType.BUY_DECISION,
            analysis_depth=AnalysisDepth.DECISION,
            question_focus=[" Should_I_Buy ", "  WHAT_COULD_GO_WRONG", "", "future_income  "],
            occupancy_type=OccupancyType.INVESTOR,
            exit_options=[ExitOption.HOLD],
            confidence=0.82,
        )

        self.assertEqual(
            parsed.question_focus,
            ["should_i_buy", "what_could_go_wrong", "future_income"],
        )

    def test_parser_output_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            ParserOutput(
                intent_type=IntentType.BUY_DECISION,
                analysis_depth=AnalysisDepth.SNAPSHOT,
                occupancy_type=OccupancyType.UNKNOWN,
                exit_options=[],
                confidence=1.2,
            )

    def test_engine_output_get_accepts_enum_and_string(self) -> None:
        payload = ModulePayload(
            data={"estimated_value": 800000},
            confidence=0.74,
            assumptions_used={"rent_growth": 0.02},
            warnings=[],
        )
        output = EngineOutput(outputs={ModuleName.VALUATION.value: payload})

        self.assertIs(output.get(ModuleName.VALUATION), payload)
        self.assertIs(output.get("valuation"), payload)
        self.assertIsNone(output.get(ModuleName.RISK_MODEL))

    def test_unified_intelligence_output_is_typed(self) -> None:
        result = UnifiedIntelligenceOutput(
            recommendation="Buy if the value gap holds after inspection.",
            decision=DecisionType.BUY,
            best_path="Owner-occupy now, then evaluate a later rent conversion.",
            key_value_drivers=["Below fair value", "Flexible future rental option"],
            key_risks=["Carry may be tight", "Execution risk on deferred repairs"],
            confidence=0.7,
            analysis_depth_used=AnalysisDepth.SCENARIO,
            next_questions=["Can the upstairs unit be rented legally?"],
            recommended_next_run="scenario:hold_to_rent",
            supporting_facts={"valuation_gap_pct": 0.11},
        )

        self.assertEqual(result.decision, DecisionType.BUY)
        self.assertEqual(result.analysis_depth_used, AnalysisDepth.SCENARIO)

    def test_routing_decision_wraps_parser_output(self) -> None:
        parsed = ParserOutput(
            intent_type=IntentType.HOUSE_HACK_MULTI_UNIT,
            analysis_depth=AnalysisDepth.DEEP_DIVE,
            question_focus=["future_income", "best_path"],
            occupancy_type=OccupancyType.OWNER_OCCUPANT,
            exit_options=[ExitOption.RENT, ExitOption.HOLD],
            confidence=0.9,
        )
        decision = RoutingDecision(
            intent_type=parsed.intent_type,
            analysis_depth=parsed.analysis_depth,
            core_questions=[],
            selected_modules=[ModuleName.RENTAL_OPTION, ModuleName.UNIT_INCOME_OFFSET],
            parser_output=parsed,
        )

        self.assertEqual(decision.parser_output.intent_type, IntentType.HOUSE_HACK_MULTI_UNIT)
        self.assertEqual(decision.selected_modules[0], ModuleName.RENTAL_OPTION)


if __name__ == "__main__":
    unittest.main()

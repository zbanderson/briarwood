from __future__ import annotations

import unittest

from briarwood.orchestrator import (
    build_cache_key,
    build_property_summary,
    run_briarwood_analysis,
    supports_scoped_execution,
)
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionType,
    ExitOption,
    IntentType,
    ModuleName,
    OccupancyType,
    ParserOutput,
)


class OrchestratorTests(unittest.TestCase):
    def test_build_property_summary_excludes_listing_description(self) -> None:
        summary = build_property_summary(
            {
                "property_id": "prop-1",
                "address": "1 Test St",
                "town": "Belmar",
                "state": "NJ",
                "purchase_price": 750000,
                "listing_description": "Very long raw listing text that should not pass through.",
                "additional_units": [{"label": "rear"}],
            }
        )

        self.assertEqual(summary["property_id"], "prop-1")
        self.assertEqual(summary["additional_units_count"], 1)
        self.assertNotIn("listing_description", summary)

    def test_build_cache_key_is_stable_for_same_inputs(self) -> None:
        parser_output = ParserOutput(
            intent_type="buy_decision",
            analysis_depth="snapshot",
            question_focus=["should_i_buy"],
            occupancy_type="unknown",
            exit_options=["unknown"],
            confidence=0.75,
            missing_inputs=[],
        )

        property_data = {"property_id": "prop-1"}
        self.assertEqual(
            build_cache_key(property_data, parser_output),
            build_cache_key(property_data, parser_output),
        )

    def test_run_briarwood_analysis_requires_synthesizer(self) -> None:
        with self.assertRaises(ValueError):
            run_briarwood_analysis(property_data={"property_id": "prop-1"}, user_input="Should I buy this?")

    def test_scoped_support_is_true_for_wave_1_snapshot(self) -> None:
        supported, plan = supports_scoped_execution([ModuleName.VALUATION, ModuleName.CONFIDENCE])

        self.assertTrue(supported)
        self.assertIsNotNone(plan)
        self.assertIn("valuation", plan.ordered_modules)
        self.assertIn("confidence", plan.ordered_modules)

    def test_run_briarwood_analysis_wires_runner_and_synthesizer(self) -> None:
        calls: dict[str, object] = {}

        def fake_module_runner(
            selected_modules: list[ModuleName],
            property_data: dict[str, object],
            parser_output: ParserOutput,
        ) -> dict[str, object]:
            calls["selected_modules"] = selected_modules
            calls["property_data"] = property_data
            calls["parser_output"] = parser_output
            return {
                "outputs": {
                    "valuation": {
                        "data": {"fair_value": 810000},
                        "confidence": 0.78,
                        "assumptions_used": {},
                        "warnings": [],
                    }
                }
            }

        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            calls["property_summary"] = property_summary
            calls["parser_output_dump"] = parser_output
            calls["module_results"] = module_results
            return {
                "recommendation": "Buy with measured conviction.",
                "decision": "buy",
                "best_path": "Buy as a straightforward decision case and validate carry next.",
                "key_value_drivers": ["Value support looks positive"],
                "key_risks": ["Carry still needs confirmation"],
                "confidence": 0.73,
                "analysis_depth_used": "snapshot",
                "next_questions": ["What does monthly carry look like at current rates?"],
                "recommended_next_run": "decision:carry_cost",
                "supporting_facts": {"fair_value": 810000},
            }

        result = run_briarwood_analysis(
            property_data={
                "property_id": "prop-1",
                "address": "1 Test St",
                "town": "Belmar",
                "state": "NJ",
                "listing_description": "Should be excluded",
            },
            user_input="Should I buy this?",
            module_runner=fake_module_runner,
            synthesizer=fake_synthesizer,
        )

        self.assertEqual(result.decision, DecisionType.BUY)
        self.assertEqual(result.analysis_depth_used, AnalysisDepth.SNAPSHOT)
        self.assertIn(ModuleName.VALUATION, calls["selected_modules"])
        self.assertNotIn("listing_description", calls["property_summary"])
        self.assertEqual(calls["parser_output_dump"]["analysis_depth"], "snapshot")

    def test_run_briarwood_analysis_uses_scoped_execution_when_supported(self) -> None:
        calls: dict[str, object] = {}

        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            calls["property_summary"] = property_summary
            calls["parser_output_dump"] = parser_output
            calls["module_results"] = module_results
            return {
                "recommendation": "Buy with measured conviction.",
                "decision": "buy",
                "best_path": "Proceed with diligence.",
                "key_value_drivers": ["Value support"],
                "key_risks": ["Carry"],
                "confidence": 0.7,
                "analysis_depth_used": "snapshot",
                "next_questions": [],
                "recommended_next_run": None,
                "supporting_facts": {},
            }

        result = run_briarwood_analysis(
            property_data={
                "property_id": "prop-scoped",
                "address": "1 Test St",
                "town": "Belmar",
                "state": "NJ",
                "beds": 3,
                "baths": 2.0,
                "sqft": 1400,
                "purchase_price": 750000,
            },
            user_input="Should I buy this?",
            synthesizer=fake_synthesizer,
        )

        self.assertEqual(result.decision, DecisionType.BUY)
        self.assertIn("outputs", calls["module_results"])
        self.assertIn("valuation", calls["module_results"]["outputs"])

    def test_run_briarwood_analysis_requires_runner_for_legacy_fallback(self) -> None:
        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            del property_summary, parser_output, module_results
            return {
                "recommendation": "Unavailable",
                "decision": "mixed",
                "best_path": "Unavailable",
                "key_value_drivers": [],
                "key_risks": [],
                "confidence": 0.0,
                "analysis_depth_used": "deep_dive",
                "next_questions": [],
                "recommended_next_run": None,
                "supporting_facts": {},
            }

        with self.assertRaises(ValueError):
            run_briarwood_analysis(
                property_data={
                    "property_id": "prop-fallback",
                    "address": "1 Test St",
                    "town": "Belmar",
                    "state": "NJ",
                },
                user_input="What could my forward rent look like if we buy this and renovate after 3 years?",
                synthesizer=fake_synthesizer,
            )

    def test_repeated_identical_run_reuses_cached_parser_and_synthesis(self) -> None:
        counters = {"llm_parser": 0, "module_runner": 0, "synthesizer": 0}

        def fake_llm_parser(_text: str) -> ParserOutput:
            counters["llm_parser"] += 1
            return ParserOutput(
                intent_type=IntentType.HOUSE_HACK_MULTI_UNIT,
                analysis_depth=AnalysisDepth.DEEP_DIVE,
                question_focus=["future_income", "best_path"],
                occupancy_type=OccupancyType.OWNER_OCCUPANT,
                exit_options=[ExitOption.RENT, ExitOption.HOLD],
                confidence=0.95,
                has_additional_units=True,
                missing_inputs=[],
            )

        def fake_module_runner(
            selected_modules: list[ModuleName],
            property_data: dict[str, object],
            parser_output: ParserOutput,
        ) -> dict[str, object]:
            del selected_modules, property_data, parser_output
            counters["module_runner"] += 1
            return {
                "outputs": {
                    "rental_option": {
                        "data": {"rent_range": [2800, 3200]},
                        "confidence": 0.71,
                        "assumptions_used": {},
                        "warnings": [],
                    }
                }
            }

        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            del property_summary, parser_output, module_results
            counters["synthesizer"] += 1
            return {
                "recommendation": "Mixed. Verify the extra-unit path first.",
                "decision": "mixed",
                "best_path": "Validate rentability before leaning on the offset story.",
                "key_value_drivers": ["Flexible optional income"],
                "key_risks": ["Legality still uncertain"],
                "confidence": 0.68,
                "analysis_depth_used": "deep_dive",
                "next_questions": ["Can the extra unit be rented legally?"],
                "recommended_next_run": "scenario:hold_to_rent",
                "supporting_facts": {"selected_modules": ["rental_option"]},
            }

        property_data = {
            "property_id": "prop-1",
            "address": "1 Test St",
            "town": "Belmar",
            "state": "NJ",
        }
        first = run_briarwood_analysis(
            property_data=property_data,
            user_input="Help me think through this property.",
            llm_parser=fake_llm_parser,
            module_runner=fake_module_runner,
            synthesizer=fake_synthesizer,
        )
        second = run_briarwood_analysis(
            property_data=property_data,
            user_input="Help me think through this property.",
            llm_parser=fake_llm_parser,
            module_runner=fake_module_runner,
            synthesizer=fake_synthesizer,
        )

        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(counters["llm_parser"], 1)
        self.assertEqual(counters["module_runner"], 1)
        self.assertEqual(counters["synthesizer"], 1)

    def test_synthesis_inputs_strip_full_listing_text(self) -> None:
        captured: dict[str, object] = {}

        def fake_module_runner(
            selected_modules: list[ModuleName],
            property_data: dict[str, object],
            parser_output: ParserOutput,
        ) -> dict[str, object]:
            del selected_modules, property_data, parser_output
            return {
                "outputs": {
                    "valuation": {
                        "data": {
                            "raw_text": "should not pass through",
                            "listing_description": "also should not pass through",
                            "fair_value": 810000,
                        },
                        "confidence": 0.78,
                        "assumptions_used": {},
                        "warnings": [],
                    }
                }
            }

        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            captured["property_summary"] = property_summary
            captured["module_results"] = module_results
            return {
                "recommendation": "Buy with caution.",
                "decision": "buy",
                "best_path": "Verify carry and proceed if the value support holds.",
                "key_value_drivers": ["Value support"],
                "key_risks": ["Carry still needs confirmation"],
                "confidence": 0.72,
                "analysis_depth_used": parser_output["analysis_depth"],
                "next_questions": [],
                "recommended_next_run": None,
                "supporting_facts": {},
            }

        run_briarwood_analysis(
            property_data={
                "property_id": "prop-2",
                "address": "2 Test St",
                "town": "Belmar",
                "state": "NJ",
                "listing_description": "A very long listing body that should never go to the model.",
            },
            user_input="Should I buy this?",
            module_runner=fake_module_runner,
            synthesizer=fake_synthesizer,
        )

        summary = captured["property_summary"]
        modules = captured["module_results"]
        self.assertNotIn("listing_description", summary)
        self.assertNotIn("raw_text", modules["outputs"]["valuation"]["data"])
        self.assertNotIn("listing_description", modules["outputs"]["valuation"]["data"])

    def test_missing_property_and_location_context_is_rejected(self) -> None:
        def fake_module_runner(
            selected_modules: list[ModuleName],
            property_data: dict[str, object],
            parser_output: ParserOutput,
        ) -> dict[str, object]:
            del selected_modules, property_data, parser_output
            return {"outputs": {}}

        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            del property_summary, parser_output, module_results
            return {
                "recommendation": "Unavailable",
                "decision": "mixed",
                "best_path": "Unavailable",
                "key_value_drivers": [],
                "key_risks": [],
                "confidence": 0.0,
                "analysis_depth_used": "snapshot",
                "next_questions": [],
                "recommended_next_run": None,
                "supporting_facts": {},
            }

        with self.assertRaises(ValueError):
            run_briarwood_analysis(
                property_data={"property_id": "contextless"},
                user_input="Should I buy this?",
                module_runner=fake_module_runner,
                synthesizer=fake_synthesizer,
            )

    def test_generic_question_is_allowed_when_property_context_exists(self) -> None:
        def fake_module_runner(
            selected_modules: list[ModuleName],
            property_data: dict[str, object],
            parser_output: ParserOutput,
        ) -> dict[str, object]:
            del selected_modules, property_data, parser_output
            return {
                "outputs": {
                    "valuation": {
                        "data": {"fair_value": 810000},
                        "confidence": 0.78,
                        "assumptions_used": {},
                        "warnings": [],
                    }
                }
            }

        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            del property_summary, parser_output, module_results
            return {
                "recommendation": "Buy with measured conviction.",
                "decision": "buy",
                "best_path": "Proceed with diligence.",
                "key_value_drivers": ["Value support"],
                "key_risks": ["Carry"],
                "confidence": 0.7,
                "analysis_depth_used": "snapshot",
                "next_questions": [],
                "recommended_next_run": None,
                "supporting_facts": {},
            }

        result = run_briarwood_analysis(
            property_data={
                "property_id": "prop-context",
                "address": "1 Test St",
                "town": "Belmar",
                "state": "NJ",
            },
            user_input="Should I buy this?",
            module_runner=fake_module_runner,
            synthesizer=fake_synthesizer,
        )

        self.assertEqual(result.decision, DecisionType.BUY)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from briarwood.agent.router import AnswerType
from briarwood.execution.module_sets import ANSWER_TYPE_MODULE_SETS
from briarwood.orchestrator import (
    _sanitize_for_synthesis,
    build_cache_key,
    build_property_summary,
    run_briarwood_analysis,
    run_briarwood_analysis_with_artifacts,
    run_chat_tier_analysis,
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

    def _fact_parser(self) -> ParserOutput:
        return ParserOutput(
            intent_type="buy_decision",
            analysis_depth="snapshot",
            question_focus=["should_i_buy"],
            occupancy_type="unknown",
            exit_options=["unknown"],
            confidence=0.75,
            missing_inputs=[],
        )

    def test_build_cache_key_changes_when_structural_facts_change(self) -> None:
        """F3: same property_id + same parser assumptions but different
        structural facts (beds, sqft, taxes, year_built, ...) must produce a
        different cache key. Prior to the fact fingerprint being added, the
        orchestrator would return stale synthesis/module results when a user
        corrected the record for the same property_id."""
        parser_output = self._fact_parser()
        base = {
            "property_id": "prop-1",
            "beds": 3,
            "baths": 2.0,
            "sqft": 1_800,
            "lot_size": 6_000,
            "year_built": 1958,
            "taxes": 12_500,
            "purchase_price": 750_000,
        }

        baseline_key = build_cache_key(base, parser_output)

        mutations = [
            ("beds", 4),
            ("baths", 2.5),
            ("sqft", 2_000),
            ("lot_size", 7_200),
            ("year_built", 1972),
            ("taxes", 14_000),
            ("purchase_price", 825_000),
            ("property_type", "condo"),
            ("has_additional_units", True),
        ]
        for field, new_value in mutations:
            mutated = dict(base)
            mutated[field] = new_value
            mutated_key = build_cache_key(mutated, parser_output)
            self.assertNotEqual(
                mutated_key,
                baseline_key,
                f"cache key must miss when '{field}' changes ({base.get(field)!r} -> {new_value!r})",
            )

    def test_build_cache_key_carries_schema_version_prefix(self) -> None:
        """F3: the cache key ships the schema version as a literal prefix so
        bumps invalidate every cached entry mass-wise without needing to clear
        the dicts by hand."""
        parser_output = self._fact_parser()
        key = build_cache_key({"property_id": "prop-1", "beds": 3}, parser_output)
        self.assertTrue(key.startswith("v2:"), key)
        tail = key.split(":", 1)[1]
        self.assertEqual(len(tail), 40)
        int(tail, 16)

    def test_build_cache_key_ignores_unrelated_property_fields(self) -> None:
        """Fields outside the fingerprint (e.g., listing description, source
        URL) must not cause spurious cache misses."""
        parser_output = self._fact_parser()
        base = {"property_id": "prop-1", "beds": 3, "sqft": 1_800}
        with_noise = dict(base)
        with_noise["listing_description"] = "Charming two-story with updated kitchen"
        with_noise["source_url"] = "https://example.com/listings/prop-1"
        self.assertEqual(
            build_cache_key(base, parser_output),
            build_cache_key(with_noise, parser_output),
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
        self.assertEqual(result.analysis_depth_used, AnalysisDepth.SNAPSHOT)
        self.assertIn("outputs", calls["module_results"])
        self.assertIn("valuation", calls["module_results"]["outputs"])

    def test_shadow_intelligence_artifact_is_telemetry_only(self) -> None:
        from briarwood.shadow_intelligence import IntentSatisfactionReport, ShadowToolPlan

        class ShadowLLM:
            def __init__(self) -> None:
                self.responses = [
                    ShadowToolPlan(
                        proposed_modules=["valuation", "confidence", "rental_option"],
                        proposed_tools=[],
                        confidence=0.8,
                        reason="rent path may be relevant",
                    ),
                    IntentSatisfactionReport(
                        intent_satisfied=True,
                        confidence=0.7,
                        missing_capabilities=[],
                        suggested_modules=[],
                        suggested_follow_up=None,
                        reason="answered",
                    ),
                ]

            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("shadow intelligence should use structured output")

            def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
                return self.responses.pop(0)

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

        artifacts = run_briarwood_analysis_with_artifacts(
            property_data={
                "property_id": "prop-shadow",
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
            shadow_llm=ShadowLLM(),
        )

        selected_before_shadow = [m.value for m in artifacts["routing_decision"].selected_modules]
        self.assertIn("valuation", selected_before_shadow)
        shadow = artifacts["shadow_intelligence"]
        self.assertIsNotNone(shadow)
        self.assertEqual(shadow["planner"]["proposed_modules"][-1], "rental_option")
        self.assertEqual(shadow["module_diff"]["missing_from_deterministic"], ["rental_option"])
        self.assertEqual(
            [m.value for m in artifacts["routing_decision"].selected_modules],
            selected_before_shadow,
        )

    def test_repeated_identical_run_reuses_cached_parser_and_synthesis(self) -> None:
        counters = {"llm_parser": 0, "synthesizer": 0}

        def fake_llm_parser(_text: str) -> ParserOutput:
            counters["llm_parser"] += 1
            return ParserOutput(
                intent_type=IntentType.BUY_DECISION,
                analysis_depth=AnalysisDepth.SNAPSHOT,
                question_focus=["should_i_buy"],
                occupancy_type=OccupancyType.UNKNOWN,
                exit_options=[ExitOption.UNKNOWN],
                confidence=0.95,
                missing_inputs=[],
            )

        def fake_synthesizer(
            property_summary: dict[str, object],
            parser_output: dict[str, object],
            module_results: dict[str, object],
        ) -> dict[str, object]:
            del property_summary, parser_output, module_results
            counters["synthesizer"] += 1
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

        property_data = {
            "property_id": "prop-cache",
            "address": "1 Test St",
            "town": "Belmar",
            "state": "NJ",
            "beds": 3,
            "baths": 2.0,
            "sqft": 1400,
            "purchase_price": 750000,
        }
        first = run_briarwood_analysis(
            property_data=property_data,
            user_input="Help me think through this property.",
            llm_parser=fake_llm_parser,
            synthesizer=fake_synthesizer,
        )
        second = run_briarwood_analysis(
            property_data=property_data,
            user_input="Help me think through this property.",
            llm_parser=fake_llm_parser,
            synthesizer=fake_synthesizer,
        )

        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(counters["llm_parser"], 1)
        self.assertEqual(counters["synthesizer"], 1)

    def test_sanitize_for_synthesis_strips_raw_text_fields(self) -> None:
        sanitized = _sanitize_for_synthesis(
            {
                "outputs": {
                    "valuation": {
                        "data": {
                            "raw_text": "should not pass through",
                            "listing_description": "also should not pass through",
                            "fair_value": 810000,
                        }
                    }
                }
            }
        )
        valuation_data = sanitized["outputs"]["valuation"]["data"]
        self.assertNotIn("raw_text", valuation_data)
        self.assertNotIn("listing_description", valuation_data)
        self.assertEqual(valuation_data["fair_value"], 810000)

    def test_missing_property_and_location_context_is_rejected(self) -> None:
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
                synthesizer=fake_synthesizer,
            )

    def test_generic_question_is_allowed_when_property_context_exists(self) -> None:
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
                "beds": 3,
                "baths": 2.0,
                "sqft": 1400,
                "purchase_price": 750000,
            },
            user_input="Should I buy this?",
            synthesizer=fake_synthesizer,
        )

        self.assertEqual(result.decision, DecisionType.BUY)


class RunChatTierAnalysisTests(unittest.TestCase):
    """Cycle 2 of OUTPUT_QUALITY_HANDOFF_PLAN.md.

    These tests pin the consolidated chat-tier orchestrator entry. They
    use the real default scoped registry — modules with sparse fixture
    data fall through to the canonical error contract
    (DECISIONS.md 2026-04-24 "Scoped wrapper error contract") and
    produce ``mode in {"error","fallback"}`` payloads. Tests assert
    plan shape + module-set membership rather than payload content.
    """

    def _property(self) -> dict[str, object]:
        return {
            "property_id": "prop-chat-tier",
            "address": "1 Test St",
            "town": "Belmar",
            "state": "NJ",
            "beds": 3,
            "baths": 2.0,
            "sqft": 1400,
            "purchase_price": 750000,
        }

    def test_browse_runs_full_first_read_cascade(self) -> None:
        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.BROWSE,
            user_input="What do you think of this?",
        )

        self.assertEqual(artifact["answer_type"], "browse")
        self.assertIsNotNone(artifact["unified_output"])
        modules_run = set(artifact["modules_run"])
        # The full first-read set is expected to land — these are the
        # modules the audit's live trace flagged as dormant for chat-tier
        # traffic. Cycle 2's reason for existing.
        self.assertIn("comparable_sales", modules_run)
        self.assertIn("location_intelligence", modules_run)
        self.assertIn("strategy_classifier", modules_run)
        self.assertIn("arv_model", modules_run)
        # Expansion may add transitive dependencies; the user-selected
        # set must be a subset of what actually ran.
        self.assertTrue(
            ANSWER_TYPE_MODULE_SETS[AnswerType.BROWSE].issubset(modules_run)
        )

    def test_projection_runs_only_projection_subset(self) -> None:
        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.PROJECTION,
            user_input="What if we got it for $660 and rented it?",
        )

        self.assertEqual(artifact["answer_type"], "projection")
        modules_run = set(artifact["modules_run"])
        self.assertTrue(
            ANSWER_TYPE_MODULE_SETS[AnswerType.PROJECTION].issubset(modules_run)
        )
        # Risk-only modules must NOT have been pulled in for a projection.
        self.assertNotIn("risk_model", modules_run)
        self.assertNotIn("legal_confidence", modules_run)

    def test_risk_runs_risk_subset(self) -> None:
        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.RISK,
            user_input="What could go wrong here?",
        )

        modules_run = set(artifact["modules_run"])
        self.assertTrue(
            ANSWER_TYPE_MODULE_SETS[AnswerType.RISK].issubset(modules_run)
        )
        self.assertIn("risk_model", modules_run)
        # Rent-path modules must not run for a risk turn.
        self.assertNotIn("rental_option", modules_run)
        self.assertNotIn("hold_to_rent", modules_run)

    def test_lookup_short_circuits_with_no_cascade(self) -> None:
        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.LOOKUP,
            user_input="What is the asking price?",
        )

        self.assertEqual(artifact["answer_type"], "lookup")
        self.assertEqual(artifact["modules_run"], [])
        self.assertEqual(artifact["module_results"], {"outputs": {}, "trace": []})
        self.assertIsNone(artifact["unified_output"])
        self.assertEqual(artifact["skipped_reason"], "no_cascade_for_answer_type")

    def test_chitchat_short_circuits_like_lookup(self) -> None:
        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.CHITCHAT,
            user_input="hi",
        )

        self.assertEqual(artifact["modules_run"], [])
        self.assertEqual(artifact["skipped_reason"], "no_cascade_for_answer_type")

    def test_each_module_runs_at_most_once_per_turn(self) -> None:
        """The 2026-04-25 audit's headline finding was 33 module-execution
        events across 5+ plans for ONE chat turn (`valuation` ran 5x,
        `risk_model` 4x fresh, etc.). Cycle 2 turns that into one plan
        per turn — verify no duplication in ``modules_run``."""

        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.BROWSE,
            user_input="What do you think of this?",
        )

        modules_run = artifact["modules_run"]
        self.assertEqual(
            len(modules_run),
            len(set(modules_run)),
            f"Each module must appear once in the consolidated plan; got {modules_run}",
        )

    def test_explicit_parser_output_overrides_synthesized_default(self) -> None:
        explicit = ParserOutput(
            intent_type="renovate_then_sell",
            analysis_depth="scenario",
            question_focus=["where_is_value", "hidden_upside"],
            occupancy_type="investor",
            exit_options=["sell", "redevelop"],
            hold_period_years=2.0,
            renovation_plan=True,
            has_additional_units=False,
            confidence=0.82,
            missing_inputs=[],
        )

        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.EDGE,
            user_input="Where is the value here?",
            parser_output=explicit,
        )

        self.assertEqual(artifact["parser_output"]["intent_type"], "renovate_then_sell")
        self.assertEqual(artifact["parser_output"]["analysis_depth"], "scenario")
        self.assertEqual(artifact["parser_output"]["confidence"], 0.82)

    def test_synthesized_parser_output_carries_answer_type_intent_focus(self) -> None:
        artifact = run_chat_tier_analysis(
            property_data=self._property(),
            answer_type=AnswerType.RISK,
            user_input="What could go wrong?",
        )

        parser = artifact["parser_output"]
        self.assertEqual(parser["intent_type"], "buy_decision")
        self.assertEqual(parser["analysis_depth"], "decision")
        self.assertIn("what_could_go_wrong", parser["question_focus"])


if __name__ == "__main__":
    unittest.main()

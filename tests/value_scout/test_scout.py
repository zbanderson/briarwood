import unittest
import importlib
from typing import Any

from pydantic import BaseModel

from briarwood.agent.llm_observability import get_llm_ledger
from briarwood.agent.turn_manifest import end_turn, start_turn
from briarwood.claims.base import Confidence, Provenance, SurfacedInsight
from briarwood.claims.verdict_with_comparison import (
    Comparison,
    ComparisonScenario,
    Subject,
    Verdict,
    VerdictWithComparisonClaim,
)
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.intent_contract import IntentContract
from briarwood.routing_schema import (
    AnalysisDepth,
    CoreQuestion,
    DecisionType,
    UnifiedIntelligenceOutput,
)
from briarwood.value_scout import scout, scout_claim
from briarwood.value_scout.llm_scout import _ScoutInsightOut, _ScoutScanResult
from briarwood.value_scout.patterns import uplift_dominance
from tests.claims.fixtures import belmar_house

scout_module = importlib.import_module("briarwood.value_scout.scout")


class _ScriptedLLM:
    def __init__(self, response: _ScoutScanResult) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 360) -> str:
        raise AssertionError("scout dispatcher should not call complete()")

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 600,
    ) -> BaseModel | None:
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.response


def _intent() -> IntentContract:
    return IntentContract(
        answer_type="browse",
        core_questions=[CoreQuestion.SHOULD_I_BUY],
        question_focus=["should_i_buy"],
        confidence=0.7,
    )


def _unified() -> UnifiedIntelligenceOutput:
    return UnifiedIntelligenceOutput(
        recommendation="Buy if price improves.",
        decision=DecisionType.BUY,
        best_path="Wait for a better entry.",
        key_value_drivers=["Rent support"],
        key_risks=["Thin carry data"],
        confidence=0.72,
        analysis_depth_used=AnalysisDepth.SNAPSHOT,
        supporting_facts={
            "rental_option": {"rent_support_score": 0.74},
            "market_value_history": {"three_year_change_pct": 0.12},
        },
    )


def _llm_result(confidence: float) -> _ScoutScanResult:
    return _ScoutScanResult(
        insights=[
            _ScoutInsightOut(
                headline="Rent support is strong.",
                reason="rent_support_score sits at 0.74.",
                supporting_fields=["supporting_facts.rental_option.rent_support_score"],
                category="rent_angle",
                confidence=confidence,
            )
        ]
    )


class ScoutEntrypointTests(unittest.TestCase):
    def test_returns_insight_when_a_pattern_fires(self) -> None:
        claim = build_verdict_with_comparison_claim(
            property_summary=belmar_house.property_summary(),
            parser_output=belmar_house.parser_output(),
            module_results=belmar_house.module_results(),
            interaction_trace=belmar_house.interaction_trace(),
        )
        insight = scout_claim(claim)
        direct = uplift_dominance.detect(claim)
        self.assertIsNotNone(insight)
        self.assertIsNotNone(direct)
        assert insight is not None
        assert direct is not None
        self.assertEqual(insight.scenario_id, "renovated_plus_bath")
        self.assertEqual(insight.headline, direct.headline)
        self.assertEqual(insight.reason, direct.reason)
        self.assertEqual(insight.supporting_fields, direct.supporting_fields)
        self.assertEqual(insight.scenario_id, direct.scenario_id)
        self.assertIsNotNone(insight.confidence)

    def test_returns_none_when_no_pattern_matches(self) -> None:
        # Subject-only comparison: nothing for the uplift pattern to compare.
        claim = VerdictWithComparisonClaim(
            subject=Subject(
                property_id="x",
                address="1 Test St",
                beds=3,
                baths=2.0,
                sqft=1800,
                ask_price=650_000.0,
                status="active",
            ),
            verdict=Verdict(
                label="fair",
                headline="headline",
                basis_fmv=650_000.0,
                ask_vs_fmv_delta_pct=0.0,
                method="comparable_sales_v1",
                comp_count=3,
                comp_radius_mi=0.5,
                comp_window_months=6,
                confidence=Confidence.from_score(0.8),
            ),
            bridge_sentence="bridge",
            comparison=Comparison(
                metric="price_per_sqft",
                unit="$/sqft",
                scenarios=[
                    ComparisonScenario(
                        id="subject",
                        label="Subject",
                        metric_range=(350.0, 360.0),
                        metric_median=355.0,
                        is_subject=True,
                        sample_size=3,
                    )
                ],
                chart_rule="horizontal_bar_with_ranges",
            ),
            provenance=Provenance(),
        )
        self.assertIsNone(scout_claim(claim))

    def test_chat_tier_dispatch_uses_llm_scout(self) -> None:
        get_llm_ledger().clear()
        llm = _ScriptedLLM(_llm_result(0.84))

        insights = scout(_unified(), llm=llm, intent=_intent())

        self.assertGreaterEqual(len(insights), 1)
        self.assertEqual(insights[0].category, "rent_angle")
        self.assertEqual(insights[0].confidence, 0.84)
        self.assertEqual(len(llm.calls), 1)
        self.assertIn(
            "value_scout.scan",
            [record.surface for record in get_llm_ledger().records],
        )

    def test_dispatcher_sorts_deterministic_and_llm_insights_by_confidence(self) -> None:
        def deterministic_pattern(_: UnifiedIntelligenceOutput) -> SurfacedInsight:
            return SurfacedInsight(
                headline="Deterministic pattern fired.",
                reason="confidence beats the LLM scout.",
                supporting_fields=["confidence"],
                category="deterministic_test",
                confidence=0.95,
            )

        original = scout_module._PATTERNS
        scout_module._PATTERNS = {
            **original,
            UnifiedIntelligenceOutput: (deterministic_pattern,),
        }
        try:
            insights = scout(
                _unified(),
                llm=_ScriptedLLM(_llm_result(0.70)),
                intent=_intent(),
                max_insights=1,
            )
        finally:
            scout_module._PATTERNS = original

        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0].category, "deterministic_test")
        self.assertEqual(insights[0].confidence, 0.95)

    def test_dispatcher_falls_back_to_patterns_when_llm_returns_empty(self) -> None:
        insights = scout(
            _unified(),
            llm=_ScriptedLLM(_ScoutScanResult(insights=[])),
            intent=_intent(),
        )

        self.assertTrue(insights)
        self.assertEqual(insights[0].category, "town_trend_tailwind")
        self.assertEqual(len(insights), 1)

    def test_dispatcher_patterns_fire_without_llm(self) -> None:
        insights = scout(_unified(), llm=None, intent=_intent())

        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0].category, "town_trend_tailwind")

    def test_dispatcher_records_scout_yield_manifest_note(self) -> None:
        start_turn(user_text="what do you think of this?")
        try:
            scout(
                _unified(),
                llm=_ScriptedLLM(_ScoutScanResult(insights=[])),
                intent=_intent(),
            )
            manifest = end_turn()
        finally:
            end_turn()

        self.assertIsNotNone(manifest)
        assert manifest is not None
        self.assertTrue(
            any(
                note.startswith(
                    "value_scout_yield insights_generated=1 insights_surfaced=1"
                )
                for note in manifest.notes
            )
        )


if __name__ == "__main__":
    unittest.main()

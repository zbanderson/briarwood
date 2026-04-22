"""End-to-end smoke for the canonical routed-analysis path.

Replaces the deleted ``tests/test_integration.py`` (which inspected
tear-sheet HTML). After the Dash/tear-sheet deletion the only verdict
path is ``run_routed_report``; this test pins the unified output's core
invariants so regressions in the scoped execution layer or the
bull/base/bear module surface here instead of in the web UI.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from briarwood.routing_schema import DecisionStance
from briarwood.runner_routed import run_routed_report


FIXTURE = Path(__file__).resolve().parents[1] / "data" / "saved_properties" / "briarwood-rd-belmar" / "inputs.json"


class RunRoutedReportIntegrationTests(unittest.TestCase):
    """One real property through the full routed pipeline, no mocks."""

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE.exists():
            raise unittest.SkipTest(f"integration fixture missing: {FIXTURE}")
        # Projection phrasing selects the resale_scenario module, which carries
        # the bull/base/bear/stress metrics — without it, E7's ordering check
        # has nothing to assert against.
        cls.result = run_routed_report(
            FIXTURE, user_input="What does this become over 5 years?"
        )

    def test_unified_output_has_populated_decision_stance(self) -> None:
        stance = self.result.unified_output.decision_stance
        self.assertIsInstance(stance, DecisionStance)
        # CONDITIONAL is the fallback when trust gates fire; a real
        # property with enrichment should resolve to a concrete stance.
        self.assertTrue(stance.value, "decision_stance must be populated")

    def test_confidence_is_a_probability(self) -> None:
        confidence = self.result.unified_output.confidence
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_recommendation_and_best_path_are_non_empty(self) -> None:
        unified = self.result.unified_output
        self.assertTrue(unified.recommendation.strip())
        self.assertTrue(unified.best_path.strip())

    def test_scenario_ordering_bull_ge_base_ge_bear_gt_stress(self) -> None:
        """bull ≥ base ≥ bear > stress is an invariant of the bull_base_bear
        module (enforced at ``briarwood.modules.bull_base_bear`` and surfaced
        here via ``resale_scenario``). Assert it at the integration boundary
        so any future regression there trips this test."""

        resale = self.result.engine_output.outputs.get("resale_scenario")
        if resale is None:
            self.skipTest("resale_scenario module not selected — projection phrasing expected")

        metrics = resale.data.get("metrics") or {}
        bull = metrics.get("bull_case_value")
        base = metrics.get("base_case_value")
        bear = metrics.get("bear_case_value")
        stress = metrics.get("stress_case_value")

        self.assertIsNotNone(bull)
        self.assertIsNotNone(base)
        self.assertIsNotNone(bear)

        self.assertGreaterEqual(bull, base)
        self.assertGreaterEqual(base, bear)
        if stress is not None:
            self.assertGreater(bear, stress)

    def test_selected_modules_recorded_on_routing_decision(self) -> None:
        selected = self.result.routing_decision.selected_modules
        self.assertTrue(selected, "routing decision must select at least one module")


if __name__ == "__main__":
    unittest.main()

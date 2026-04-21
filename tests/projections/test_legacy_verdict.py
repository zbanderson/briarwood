"""Tests for ``briarwood.projections.legacy_verdict.project_to_legacy``.

These tests lock in two things:

1. The stance → legacy-label mapping table (seven-to-five). Any change to
   ``STANCE_TO_LEGACY_LABEL`` must update this test and the mapping tables
   in ``briarwood/projections/README.md`` and ``STATE_OF_1.0.md``.
2. The projector's deterministic field extraction from
   ``UnifiedIntelligenceOutput`` (primary/secondary reason, beliefs,
   trust-gate flag, conviction).

The projector is a relabel-only surface — it must never re-derive a
verdict. These tests are how we keep it honest.
"""

from __future__ import annotations

import unittest
from typing import Any

from briarwood.projections.legacy_verdict import (
    LEGACY_LABEL_AVOID,
    LEGACY_LABEL_BUY,
    LEGACY_LABEL_LEAN_BUY,
    LEGACY_LABEL_LEAN_PASS,
    LEGACY_LABEL_NEUTRAL,
    STANCE_TO_LEGACY_LABEL,
    project_to_legacy,
)
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionStance,
    DecisionType,
    UnifiedIntelligenceOutput,
)


def _unified(
    *,
    stance: DecisionStance,
    decision: DecisionType = DecisionType.MIXED,
    confidence: float = 0.7,
    why_this_stance: list[str] | None = None,
    key_risks: list[str] | None = None,
    what_must_be_true: list[str] | None = None,
    value_position: dict[str, Any] | None = None,
    recommendation: str = "Routed recommendation line.",
) -> UnifiedIntelligenceOutput:
    return UnifiedIntelligenceOutput(
        recommendation=recommendation,
        decision=decision,
        best_path="best path",
        key_value_drivers=[],
        key_risks=list(key_risks or []),
        confidence=confidence,
        analysis_depth_used=AnalysisDepth.DECISION,
        next_questions=[],
        recommended_next_run=None,
        supporting_facts={},
        decision_stance=stance,
        primary_value_source="valuation",
        value_position=dict(value_position or {}),
        what_must_be_true=list(what_must_be_true or []),
        next_checks=[],
        trust_flags=[],
        trust_summary={},
        contradiction_count=0,
        blocked_thesis_warnings=[],
        why_this_stance=list(why_this_stance or []),
        what_changes_my_view=[],
        interaction_trace={},
    )


class StanceMappingTests(unittest.TestCase):
    """Lock the 7→5 stance table."""

    def test_strong_buy_projects_to_buy(self) -> None:
        out = project_to_legacy(_unified(stance=DecisionStance.STRONG_BUY))
        self.assertEqual(out.recommendation, LEGACY_LABEL_BUY)
        self.assertFalse(out.is_trust_gate_fallback)

    def test_buy_if_price_improves_projects_to_lean_buy(self) -> None:
        out = project_to_legacy(
            _unified(stance=DecisionStance.BUY_IF_PRICE_IMPROVES)
        )
        self.assertEqual(out.recommendation, LEGACY_LABEL_LEAN_BUY)

    def test_execution_dependent_projects_to_lean_buy(self) -> None:
        """EXECUTION_DEPENDENT is a conditional yes, not a NEUTRAL."""
        out = project_to_legacy(
            _unified(stance=DecisionStance.EXECUTION_DEPENDENT)
        )
        self.assertEqual(out.recommendation, LEGACY_LABEL_LEAN_BUY)

    def test_interesting_but_fragile_projects_to_neutral(self) -> None:
        out = project_to_legacy(
            _unified(stance=DecisionStance.INTERESTING_BUT_FRAGILE)
        )
        self.assertEqual(out.recommendation, LEGACY_LABEL_NEUTRAL)
        self.assertFalse(out.is_trust_gate_fallback)

    def test_conditional_projects_to_neutral_with_trust_gate_flag(self) -> None:
        """CONDITIONAL is the trust-gate NEUTRAL — must set the flag."""
        out = project_to_legacy(_unified(stance=DecisionStance.CONDITIONAL))
        self.assertEqual(out.recommendation, LEGACY_LABEL_NEUTRAL)
        self.assertTrue(out.is_trust_gate_fallback)

    def test_pass_unless_changes_projects_to_lean_pass(self) -> None:
        out = project_to_legacy(
            _unified(stance=DecisionStance.PASS_UNLESS_CHANGES)
        )
        self.assertEqual(out.recommendation, LEGACY_LABEL_LEAN_PASS)

    def test_pass_projects_to_avoid(self) -> None:
        out = project_to_legacy(_unified(stance=DecisionStance.PASS))
        self.assertEqual(out.recommendation, LEGACY_LABEL_AVOID)

    def test_stance_table_covers_every_enum_member(self) -> None:
        """No silent missing entry — every DecisionStance must be mapped."""
        for stance in DecisionStance:
            self.assertIn(stance, STANCE_TO_LEGACY_LABEL, f"missing mapping for {stance}")


class ConvictionTests(unittest.TestCase):
    def test_conviction_mirrors_routed_confidence(self) -> None:
        """Projector surfaces routed confidence directly — no blending."""
        out = project_to_legacy(
            _unified(stance=DecisionStance.STRONG_BUY, confidence=0.73)
        )
        self.assertEqual(out.conviction, 0.73)

    def test_conviction_rounds_to_two_decimals(self) -> None:
        out = project_to_legacy(
            _unified(stance=DecisionStance.STRONG_BUY, confidence=0.123456)
        )
        self.assertEqual(out.conviction, 0.12)

    def test_low_confidence_stance_preserved_with_low_conviction(self) -> None:
        """Port of test_decision_engine.test_low_evidence_caps_conviction.

        Legacy test: same recommendation but thinner evidence lowers
        conviction. Routed equivalent: same stance + lower aggregate
        confidence lowers projected conviction. The projector must not
        re-derive a label from confidence.
        """
        strong = project_to_legacy(
            _unified(stance=DecisionStance.STRONG_BUY, confidence=0.82)
        )
        thin = project_to_legacy(
            _unified(stance=DecisionStance.STRONG_BUY, confidence=0.32)
        )
        self.assertEqual(strong.recommendation, thin.recommendation)
        self.assertLess(thin.conviction, strong.conviction)


class ReasonExtractionTests(unittest.TestCase):
    def test_primary_reason_comes_from_why_this_stance(self) -> None:
        out = project_to_legacy(
            _unified(
                stance=DecisionStance.STRONG_BUY,
                why_this_stance=["Comp-supported below the band.", "No conflicts flagged."],
            )
        )
        self.assertEqual(out.primary_reason, "Comp-supported below the band.")

    def test_primary_reason_falls_back_to_recommendation_line(self) -> None:
        out = project_to_legacy(
            _unified(
                stance=DecisionStance.CONDITIONAL,
                why_this_stance=[],
                recommendation="Conditional — trust is too low.",
            )
        )
        self.assertEqual(out.primary_reason, "Conditional — trust is too low.")

    def test_secondary_reason_prefers_key_risks(self) -> None:
        out = project_to_legacy(
            _unified(
                stance=DecisionStance.INTERESTING_BUT_FRAGILE,
                why_this_stance=["Value there."],
                key_risks=["Flood exposure materially understated."],
            )
        )
        self.assertEqual(
            out.secondary_reason, "Flood exposure materially understated."
        )

    def test_secondary_reason_falls_back_to_second_why(self) -> None:
        out = project_to_legacy(
            _unified(
                stance=DecisionStance.STRONG_BUY,
                why_this_stance=["Primary reason.", "Supporting reason."],
                key_risks=[],
            )
        )
        self.assertEqual(out.secondary_reason, "Supporting reason.")

    def test_secondary_reason_falls_back_to_value_position_when_empty(self) -> None:
        """Port of test_decision_engine.test_avoid_when_value_and_carry_are_both_weak
        intent — when the decision is a pass and the only structured signal
        is an above-band premium, the projector still emits a populated
        secondary line rather than blanking.
        """
        out = project_to_legacy(
            _unified(
                stance=DecisionStance.PASS_UNLESS_CHANGES,
                why_this_stance=["Pass — price above band."],
                key_risks=[],
                value_position={"premium_discount_pct": 0.18},
            )
        )
        self.assertIn("18%", out.secondary_reason)


class BeliefsPassthroughTests(unittest.TestCase):
    """Port of test_decision_engine.test_avoid_when_value_and_carry_are_both_weak
    — a strong-pass projection must carry at least two required-beliefs
    items through to the legacy surface so the tear sheet's "conditions"
    block is not empty.
    """

    def test_what_must_be_true_passes_through_capped_at_three(self) -> None:
        out = project_to_legacy(
            _unified(
                stance=DecisionStance.PASS_UNLESS_CHANGES,
                what_must_be_true=[
                    "Price must move inside the risk-adjusted band.",
                    "Carry must improve by at least $1,000/mo.",
                    "Comp depth must grow beyond 3 matches.",
                    "Macro rates must hold through close.",
                ],
            )
        )
        self.assertEqual(len(out.required_beliefs), 3)
        self.assertEqual(
            out.required_beliefs[0],
            "Price must move inside the risk-adjusted band.",
        )

    def test_empty_what_must_be_true_produces_empty_list(self) -> None:
        out = project_to_legacy(_unified(stance=DecisionStance.STRONG_BUY))
        self.assertEqual(out.required_beliefs, [])


class DeterminismTests(unittest.TestCase):
    def test_same_input_produces_same_output(self) -> None:
        """Projector must be deterministic — no LLM, no timestamps."""
        unified = _unified(
            stance=DecisionStance.BUY_IF_PRICE_IMPROVES,
            confidence=0.66,
            why_this_stance=["A", "B"],
            key_risks=["C"],
            what_must_be_true=["D", "E"],
        )
        first = project_to_legacy(unified)
        second = project_to_legacy(unified)
        self.assertEqual(first.model_dump(), second.model_dump())


if __name__ == "__main__":
    unittest.main()

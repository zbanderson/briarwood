"""Dispatch-level claim-pipeline branching contract.

Covers the feature-flagged branch prepended to ``handle_decision`` (plan §8).
These are mock-heavy unit tests focused on the routing logic itself — the
end-to-end happy path runs in the golden test (plan §9).

Contract under test:

1. Flag OFF → claim pipeline never builds, legacy path runs unchanged.
2. Flag ON + wrong archetype → legacy path runs.
3. Flag ON + right archetype + Editor passes → return rendered prose, set
   ``session.last_claim_events``.
4. Flag ON + right archetype + Editor fails → return None from helper,
   ``session.last_claim_rejected`` populated, legacy path runs.
5. Flag ON but claim pipeline raises → fall through to legacy, no
   rejection event set.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from briarwood.agent.dispatch import _maybe_handle_via_claim
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session
from briarwood.claims.archetypes import Archetype
from briarwood.claims.representation import RenderedClaim
from briarwood.editor import EditResult
from tests.claims.fixtures import belmar_house


def _decision() -> RouterDecision:
    return RouterDecision(
        AnswerType.DECISION,
        confidence=0.9,
        target_refs=["belmar-test-001"],
        reason="test",
    )


def _stub_claim() -> "VerdictWithComparisonClaim":  # type: ignore[name-defined]
    from briarwood.claims.synthesis import build_verdict_with_comparison_claim

    return build_verdict_with_comparison_claim(
        property_summary=belmar_house.property_summary(),
        parser_output=belmar_house.parser_output(),
        module_results=belmar_house.module_results(),
        interaction_trace=belmar_house.interaction_trace(),
    )


class ClaimBranchRoutingTests(unittest.TestCase):
    def test_flag_off_returns_none(self) -> None:
        session = Session()
        with patch("briarwood.feature_flags.claims_enabled_for", return_value=False):
            result = _maybe_handle_via_claim(
                "should I buy this?",
                _decision(),
                session,
                llm=None,
                pid="belmar-test-001",
            )
        self.assertIsNone(result)
        self.assertEqual(session.last_claim_events, [])
        self.assertIsNone(session.last_claim_rejected)

    def test_wrong_answer_type_returns_none(self) -> None:
        session = Session()
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.9, target_refs=[], reason="test"
        )
        with patch("briarwood.feature_flags.claims_enabled_for", return_value=True):
            result = _maybe_handle_via_claim(
                "list some houses",
                decision,
                session,
                llm=None,
                pid="belmar-test-001",
            )
        self.assertIsNone(result)


class ClaimBranchHappyPathTests(unittest.TestCase):
    def test_editor_passes_returns_prose_and_sets_events(self) -> None:
        session = Session()
        claim = _stub_claim()
        rendered = RenderedClaim(
            prose="Priced under fair value.",
            events=[
                {"type": "chart", "kind": "horizontal_bar_with_ranges"},
                {"type": "suggestions", "items": ["What next?"]},
            ],
        )
        with patch(
            "briarwood.feature_flags.claims_enabled_for", return_value=True
        ), patch(
            "briarwood.claims.pipeline.build_claim_for_property",
            return_value=claim,
        ), patch(
            "briarwood.value_scout.scout_claim", return_value=None
        ), patch(
            "briarwood.editor.edit_claim",
            return_value=EditResult(passed=True, failures=[]),
        ), patch(
            "briarwood.claims.representation.render_claim",
            return_value=rendered,
        ):
            result = _maybe_handle_via_claim(
                "should I buy this?",
                _decision(),
                session,
                llm=None,
                pid="belmar-test-001",
            )

        self.assertEqual(result, "Priced under fair value.")
        self.assertEqual(len(session.last_claim_events), 2)
        self.assertEqual(session.last_claim_events[0]["type"], "chart")
        self.assertIsNone(session.last_claim_rejected)


class ClaimBranchRejectionTests(unittest.TestCase):
    def test_editor_fails_records_rejection_and_returns_none(self) -> None:
        session = Session()
        claim = _stub_claim()
        with patch(
            "briarwood.feature_flags.claims_enabled_for", return_value=True
        ), patch(
            "briarwood.claims.pipeline.build_claim_for_property",
            return_value=claim,
        ), patch(
            "briarwood.value_scout.scout_claim", return_value=None
        ), patch(
            "briarwood.editor.edit_claim",
            return_value=EditResult(
                passed=False,
                failures=["scenario_data_completeness: sample_size == 0"],
            ),
        ):
            result = _maybe_handle_via_claim(
                "should I buy this?",
                _decision(),
                session,
                llm=None,
                pid="belmar-test-001",
            )

        self.assertIsNone(result)
        self.assertEqual(session.last_claim_events, [])
        self.assertIsNotNone(session.last_claim_rejected)
        rejected = session.last_claim_rejected
        assert rejected is not None
        self.assertEqual(rejected["archetype"], Archetype.VERDICT_WITH_COMPARISON.value)
        self.assertIn(
            "scenario_data_completeness: sample_size == 0",
            rejected["failures"],
        )


class ClaimBranchBuildFailureTests(unittest.TestCase):
    def test_build_exception_falls_through_silently(self) -> None:
        session = Session()
        with patch(
            "briarwood.feature_flags.claims_enabled_for", return_value=True
        ), patch(
            "briarwood.claims.pipeline.build_claim_for_property",
            side_effect=RuntimeError("synthetic failure"),
        ):
            result = _maybe_handle_via_claim(
                "should I buy this?",
                _decision(),
                session,
                llm=None,
                pid="belmar-test-001",
            )

        self.assertIsNone(result)
        self.assertEqual(session.last_claim_events, [])
        self.assertIsNone(session.last_claim_rejected)


class ClaimBranchRenderFailureTests(unittest.TestCase):
    def test_render_exception_falls_through_silently(self) -> None:
        session = Session()
        claim = _stub_claim()
        with patch(
            "briarwood.feature_flags.claims_enabled_for", return_value=True
        ), patch(
            "briarwood.claims.pipeline.build_claim_for_property",
            return_value=claim,
        ), patch(
            "briarwood.value_scout.scout_claim", return_value=None
        ), patch(
            "briarwood.editor.edit_claim",
            return_value=EditResult(passed=True, failures=[]),
        ), patch(
            "briarwood.claims.representation.render_claim",
            side_effect=RuntimeError("render boom"),
        ):
            result = _maybe_handle_via_claim(
                "should I buy this?",
                _decision(),
                session,
                llm=None,
                pid="belmar-test-001",
            )

        self.assertIsNone(result)
        self.assertEqual(session.last_claim_events, [])


if __name__ == "__main__":
    unittest.main()

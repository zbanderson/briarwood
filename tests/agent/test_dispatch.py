"""Dispatch handlers — tool-call budget + routing contracts.

Verifies:
- Lookup handler does NOT call analyze_property.
- Decision handler runs the analyzer once and returns the structured stance.
- Handlers tolerate a missing LLM client (deterministic fallback mode).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.agent.dispatch import (
    handle_decision,
    handle_lookup,
)
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session


REF = "526-west-end-ave"


class LookupHandlerTests(unittest.TestCase):
    def test_lookup_never_calls_analyze_property(self) -> None:
        decision = RouterDecision(
            AnswerType.LOOKUP, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        with patch("briarwood.agent.dispatch.analyze_property") as analyzer:
            response = handle_lookup("what's the address?", decision, session, llm=None)
        analyzer.assert_not_called()
        self.assertIn("West End", response)
        self.assertEqual(session.current_property_id, REF)


class DecisionHandlerTests(unittest.TestCase):
    def test_decision_runs_analyze_and_reports_stance(self) -> None:
        """Clean case: no research-fixable trust flags → single analyze, no research."""
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        fake_payload = {
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "trust_flags": ["incomplete_carry_inputs"],  # NOT research-fixable
            "value_position": {
                "fair_value_base": 1_379_080,
                "ask_price": 1_499_000,
                "premium_discount_pct": 0.087,
            },
            "what_must_be_true": [],
        }
        with patch(
            "briarwood.agent.dispatch.analyze_property", return_value=fake_payload
        ) as analyzer, patch("briarwood.agent.dispatch.research_town") as researcher:
            response = handle_decision(
                "should I buy this?", decision, session, llm=None
            )
        analyzer.assert_called_once_with(REF)
        researcher.assert_not_called()
        self.assertIn("buy_if_price_improves", response)
        self.assertEqual(session.current_property_id, REF)

    def test_decision_auto_researches_on_weak_town_context(self) -> None:
        """Phase C: weak_town_context triggers exactly one auto-research + re-analyze."""
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        before_payload = {
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "trust_flags": ["weak_town_context"],
            "value_position": {"fair_value_base": 1_000_000, "ask_price": 1_100_000, "premium_discount_pct": 0.10},
            "what_must_be_true": [],
        }
        after_payload = {
            **before_payload,
            "trust_flags": [],  # research cleared it
        }
        with patch(
            "briarwood.agent.dispatch.analyze_property",
            side_effect=[before_payload, after_payload],
        ) as analyzer, patch(
            "briarwood.agent.dispatch.research_town",
            return_value={"document_count": 3, "signal_count": 5, "warnings": []},
        ) as researcher:
            response = handle_decision(
                "should I buy this?", decision, session, llm=None
            )
        self.assertEqual(analyzer.call_count, 2)  # one before, one after research
        researcher.assert_called_once()
        self.assertIn("Research update", response)
        self.assertIn("cleared trust flags", response)

    def test_decision_without_property_ref_prompts_for_one(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[], reason="test"
        )
        session = Session()  # no current property
        response = handle_decision("should I buy?", decision, session, llm=None)
        self.assertIn("Which property", response)


if __name__ == "__main__":
    unittest.main()

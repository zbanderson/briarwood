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
    _escalate_browse_affirmative,
    dispatch,
    handle_browse,
    handle_decision,
    handle_edge,
    handle_lookup,
)
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session, Turn


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
            "briarwood.agent.property_view.analyze_property", return_value=fake_payload
        ) as analyzer, patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value={"address": "526 West End Ave", "ask_price": 1_499_000},
        ), patch("briarwood.agent.dispatch.research_town") as researcher:
            response = handle_decision(
                "should I buy this?", decision, session, llm=None
            )
        analyzer.assert_called_once_with(REF, overrides={})
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
            "briarwood.agent.property_view.analyze_property",
            side_effect=[before_payload, after_payload],
        ) as analyzer, patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value={"address": "526 West End Ave", "ask_price": 1_100_000},
        ), patch(
            "briarwood.agent.dispatch._summary_town_state",
            return_value=("Avon By The Sea", "NJ"),
        ), patch(
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

    def test_decision_with_overrides_skips_research(self) -> None:
        """What-if turns re-underwrite at the user's basis — no town fetch."""
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.7, target_refs=[REF], reason="test"
        )
        payload = {
            "decision_stance": "pass",
            "primary_value_source": "current_value",
            "trust_flags": ["weak_town_context"],  # would normally trigger research
            "value_position": {"fair_value_base": 1_000_000, "ask_price": 1_300_000, "premium_discount_pct": 0.30},
            "what_must_be_true": [],
        }
        with patch(
            "briarwood.agent.property_view.analyze_property", return_value=payload
        ) as analyzer, patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value={"address": "526 West End Ave", "ask_price": 1_499_000},
        ), patch(
            "briarwood.agent.dispatch.research_town"
        ) as researcher:
            handle_decision(
                "what if i bought at 1.3m?", decision, Session(), llm=None
            )
        researcher.assert_not_called()
        analyzer.assert_called_once_with(REF, overrides={"ask_price": 1_300_000.0})

    def test_decision_without_property_ref_prompts_for_one(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[], reason="test"
        )
        session = Session()  # no current property
        response = handle_decision("should I buy?", decision, session, llm=None)
        self.assertIn("Which property", response)


class BrowseHandlerTests(unittest.TestCase):
    """Browse: summary + similar listings, NO underwrite cascade."""

    def _decision(self) -> RouterDecision:
        return RouterDecision(
            AnswerType.BROWSE, confidence=0.9, target_refs=[REF], reason="browse keyword"
        )

    def test_browse_never_calls_analyze_property(self) -> None:
        """Browse must NOT trigger the full cascade — that's the whole point."""
        fake_summary = {
            "property_id": REF,
            "address": "526 West End Ave",
            "town": "Avon By The Sea",
            "state": "NJ",
            "beds": 3,
            "baths": 2.0,
            "ask_price": 1_499_000,
            "bcv": 1_379_080,
            "pricing_view": "appears fully valued",
        }
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=fake_summary
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ), patch("briarwood.agent.property_view.analyze_property") as analyzer:
            response = handle_browse(
                "what do you think of 526?", self._decision(), Session(), llm=None
            )
        analyzer.assert_not_called()
        self.assertIn("526 West End Ave", response)
        self.assertIn("Want a full underwrite?", response)

    def test_browse_lists_similar_nearby(self) -> None:
        fake_summary = {
            "property_id": REF,
            "address": "526 West End Ave",
            "town": "Avon By The Sea",
            "state": "NJ",
            "beds": 3,
            "baths": 2.0,
            "ask_price": 1_500_000,
            "bcv": 1_400_000,
            "pricing_view": "fairly valued",
        }
        fake_neighbors = [
            {
                "property_id": "304-14th-ave",
                "address": "304 14th Ave",
                "beds": 3,
                "baths": 2.0,
                "ask_price": 1_425_000,
                "blocks_to_beach": 2.5,
            },
            {
                "property_id": REF,  # subject — must be filtered out
                "address": "526 West End Ave",
                "beds": 3,
                "baths": 2.0,
                "ask_price": 1_499_000,
                "blocks_to_beach": 3.0,
            },
        ]
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=fake_summary
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=fake_neighbors
        ) as search:
            response = handle_browse(
                "what do you think of 526?", self._decision(), Session(), llm=None
            )
        # filters should reflect beds band + price ±25% + town
        call_filters = search.call_args[0][0]
        self.assertEqual(call_filters["beds_min"], 2)
        self.assertEqual(call_filters["beds_max"], 4)
        self.assertEqual(call_filters["town"], "Avon By The Sea")
        self.assertAlmostEqual(call_filters["min_price"], 1_500_000 * 0.75)
        self.assertAlmostEqual(call_filters["max_price"], 1_500_000 * 1.25)
        # subject filtered, neighbor present
        self.assertIn("304-14th-ave", response)
        self.assertNotIn("- 526-west-end-ave", response)

    def test_browse_omits_missing_fields_instead_of_rendering_question_marks(self) -> None:
        """Bug A: null beds/baths must not render as '? bedrooms'."""
        fake_summary = {
            "property_id": REF,
            "address": "526 West End Ave",
            "town": "Avon By The Sea",
            "state": "NJ",
            "beds": None,
            "baths": None,
            "ask_price": 1_499_000,
        }
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=fake_summary
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "tell me about 526", self._decision(), Session(), llm=None
            )
        # Bug A: specific failure modes — placeholder "?" next to bd/ba tokens,
        # and LLM paraphrases like "unspecified bedrooms". The trailing CTA
        # "Want a full underwrite?" is allowed; everything else must be clean.
        self.assertNotIn("?bd", response)
        self.assertNotIn("?ba", response)
        self.assertNotIn("? bd", response)
        self.assertNotIn("? ba", response)
        self.assertNotIn("unspecified", response.lower())
        self.assertIn("526 West End Ave", response)

    def test_browse_does_not_leak_valuation_math(self) -> None:
        """Intent tier: browse is orientation, not valuation — no fair value / premium."""
        fake_summary = {
            "property_id": REF,
            "address": "526 West End Ave",
            "town": "Avon By The Sea",
            "state": "NJ",
            "beds": 3,
            "baths": 2.0,
            "ask_price": 1_499_000,
            "bcv": 1_379_080,
            "pricing_view": "appears fully valued",
        }
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=fake_summary
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "tell me about 526", self._decision(), Session(), llm=None
            )
        self.assertNotIn("fair value", response.lower())
        self.assertNotIn("premium", response.lower())
        # BCV is a valuation concept — must not surface in browse narration either.
        self.assertNotIn("1,379,080", response)

    def test_browse_without_property_prompts_for_one(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.9, target_refs=[], reason="test"
        )
        response = handle_browse(
            "what do you think?", decision, Session(), llm=None
        )
        self.assertIn("Which property", response)


class SessionPropertyLeakTests(unittest.TestCase):
    """Stale session pid must not answer a question about a different property."""

    def test_unresolved_street_address_does_not_fall_back_to_session(self) -> None:
        from briarwood.agent.dispatch import _resolve_property_id

        decision = RouterDecision(
            AnswerType.LOOKUP, confidence=0.9, target_refs=[], reason="test"
        )
        session = Session(current_property_id=REF)  # prior turn left 526 loaded

        # User asks about 1223 Ocean Ave — not saved. Resolver returns None.
        # Session fallback MUST NOT quietly substitute 526.
        with patch("briarwood.agent.resolver.resolve_property_id", return_value=(None, [])):
            pid = _resolve_property_id(decision, session, "tell me about 1223 ocean ave")
        self.assertIsNone(pid)

    def test_follow_up_without_property_reference_uses_session(self) -> None:
        from briarwood.agent.dispatch import _resolve_property_id

        decision = RouterDecision(
            AnswerType.RISK, confidence=0.9, target_refs=[], reason="test"
        )
        session = Session(current_property_id=REF)

        with patch("briarwood.agent.resolver.resolve_property_id", return_value=(None, [])):
            pid = _resolve_property_id(decision, session, "what about the risks?")
        self.assertEqual(pid, REF)


class EdgeHandlerTests(unittest.TestCase):
    def test_edge_threads_overrides_into_analyze_and_thesis(self) -> None:
        """What-if prices must reach both the thesis and the chart analyzer."""
        decision = RouterDecision(
            AnswerType.EDGE, confidence=0.9, target_refs=[REF], reason="test"
        )
        from briarwood.agent.rendering import ChartUnavailable

        fake_thesis = {
            "ask_price": 1_300_000,
            "fair_value_base": 1_379_080,
            "premium_discount_pct": -0.057,
            "pricing_view": "below fair value",
        }
        with patch(
            "briarwood.agent.dispatch.get_value_thesis", return_value=fake_thesis
        ) as thesis, patch(
            "briarwood.agent.dispatch.analyze_property", return_value={}
        ) as analyzer, patch("briarwood.agent.rendering.render_chart") as render:
            render.side_effect = ChartUnavailable("chart not under test")
            handle_edge(
                "what's the edge if I bought 526-west-end-ave at 1.3m?",
                decision,
                Session(),
                llm=None,
            )
        thesis.assert_called_once_with(REF, overrides={"ask_price": 1_300_000.0})
        analyzer.assert_called_once_with(REF, overrides={"ask_price": 1_300_000.0})


class BrowseAffirmativeEscalationTests(unittest.TestCase):
    """After a BROWSE turn, 'yes/ok/sure' should promote to DECISION."""

    def _session_post_browse(self) -> Session:
        s = Session(current_property_id=REF)
        s.turns.append(Turn(user="tell me about it", assistant="…", answer_type="browse"))
        return s

    def _browse_decision(self) -> RouterDecision:
        return RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )

    def test_yes_after_browse_escalates_to_decision(self) -> None:
        out = _escalate_browse_affirmative(
            "yes lets move forward", self._browse_decision(), self._session_post_browse()
        )
        self.assertEqual(out.answer_type, AnswerType.DECISION)
        self.assertEqual(out.target_refs, [REF])
        self.assertEqual(out.reason, "browse-followup escalate")

    def test_ok_sure_after_browse_escalates(self) -> None:
        out = _escalate_browse_affirmative(
            "ok sure", self._browse_decision(), self._session_post_browse()
        )
        self.assertEqual(out.answer_type, AnswerType.DECISION)

    def test_no_escalation_without_prior_browse(self) -> None:
        s = Session(current_property_id=REF)  # no prior turn
        out = _escalate_browse_affirmative("yes", self._browse_decision(), s)
        self.assertEqual(out.answer_type, AnswerType.BROWSE)

    def test_no_escalation_without_pinned_property(self) -> None:
        s = Session()
        s.turns.append(Turn(user="…", assistant="…", answer_type="browse"))
        out = _escalate_browse_affirmative("yes", self._browse_decision(), s)
        self.assertEqual(out.answer_type, AnswerType.BROWSE)

    def test_question_does_not_escalate(self) -> None:
        out = _escalate_browse_affirmative(
            "yes but how big is the yard?",
            self._browse_decision(),
            self._session_post_browse(),
        )
        self.assertEqual(out.answer_type, AnswerType.BROWSE)

    def test_dispatch_routes_affirmative_to_decision_handler(self) -> None:
        """End-to-end: dispatch() should call handle_decision, not handle_browse."""
        from unittest.mock import MagicMock

        from briarwood.agent import dispatch as dispatch_mod

        session = self._session_post_browse()
        decision_mock = MagicMock(return_value="D")
        browse_mock = MagicMock(return_value="B")
        table = {
            **dispatch_mod.DISPATCH_TABLE,
            AnswerType.DECISION: decision_mock,
            AnswerType.BROWSE: browse_mock,
        }
        with patch.object(dispatch_mod, "DISPATCH_TABLE", table):
            out = dispatch("yes", self._browse_decision(), session, llm=None)
        decision_mock.assert_called_once()
        browse_mock.assert_not_called()
        self.assertEqual(out, "D")


if __name__ == "__main__":
    unittest.main()

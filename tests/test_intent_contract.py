"""F9: both routers must agree on core_questions for the same input.

The chat-tier router (``briarwood.agent.router.classify``) produces an
``IntentContract`` describing what answer the user wants. The analysis-tier
router (``briarwood.router.route_user_input``) selects modules and produces
a ``RoutingDecision`` with its own ``core_questions`` list. When the chat
contract is threaded into the analysis router, the analysis router's
``core_questions`` must cover every question the chat tier declared —
otherwise the two tiers drift on intent.

These tests pin that invariant. Browse/decision phrasing is LLM-routed
post-plan C2 — a scripted LLM is injected so the unit test doesn't depend
on the live classifier.
"""

from __future__ import annotations

import unittest

from briarwood.agent.router import AnswerType, PersonaType, UseCaseType, classify
from briarwood.intent_contract import (
    ANSWER_TYPE_TO_CORE_QUESTIONS,
    IntentContract,
    build_contract_from_answer_type,
    core_questions_for_answer_type,
)
from briarwood.router import route_user_input
from briarwood.routing_schema import CoreQuestion


class IntentContractSchemaTests(unittest.TestCase):
    def test_every_answer_type_has_a_mapping(self) -> None:
        """Every ``AnswerType`` must appear in the mapping table so adding
        a new type is a compile-time forcing function, not a runtime drift."""

        missing = [a for a in AnswerType if a.value not in ANSWER_TYPE_TO_CORE_QUESTIONS]
        self.assertEqual(missing, [], f"AnswerType missing from contract map: {missing}")

    def test_decision_maps_to_full_triad(self) -> None:
        questions = core_questions_for_answer_type(AnswerType.DECISION.value)
        self.assertIn(CoreQuestion.SHOULD_I_BUY, questions)
        self.assertIn(CoreQuestion.WHAT_COULD_GO_WRONG, questions)
        self.assertIn(CoreQuestion.WHERE_IS_VALUE, questions)

    def test_edge_maps_includes_hidden_upside(self) -> None:
        """F5 treats hidden upside as a first-class question; EDGE should
        pull it into the contract."""

        questions = core_questions_for_answer_type(AnswerType.EDGE.value)
        self.assertIn(CoreQuestion.HIDDEN_UPSIDE, questions)

    def test_build_contract_clamps_confidence(self) -> None:
        low = build_contract_from_answer_type("decision", -1.0)
        high = build_contract_from_answer_type("decision", 2.0)
        self.assertEqual(low.confidence, 0.0)
        self.assertEqual(high.confidence, 1.0)


class _ScriptedLLM:
    def __init__(self, answer_type: AnswerType):
        self._answer_type = answer_type

    def complete(self, **_k):  # pragma: no cover
        raise AssertionError("router should use complete_structured")

    def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
        return schema(
            answer_type=self._answer_type,
            persona_type=PersonaType.UNKNOWN,
            use_case_type=UseCaseType.UNKNOWN,
            confidence=0.7,
            reason="scripted",
        )


class ChatRouterEmitsContractTests(unittest.TestCase):
    def test_classify_always_populates_intent_contract(self) -> None:
        decision = classify(
            "Should I buy 526-west-end-ave?", client=_ScriptedLLM(AnswerType.DECISION)
        )
        self.assertIsNotNone(decision.intent_contract)
        self.assertIsInstance(decision.intent_contract, IntentContract)
        self.assertEqual(decision.intent_contract.answer_type, decision.answer_type.value)

    def test_classify_browse_emits_should_i_buy_only(self) -> None:
        decision = classify(
            "What do you think of 526-west-end-ave?", client=_ScriptedLLM(AnswerType.BROWSE)
        )
        self.assertIs(decision.answer_type, AnswerType.BROWSE)
        self.assertEqual(
            list(decision.intent_contract.core_questions),
            [CoreQuestion.SHOULD_I_BUY],
        )

    def test_classify_empty_input_emits_empty_contract(self) -> None:
        decision = classify("")
        self.assertIs(decision.answer_type, AnswerType.CHITCHAT)
        self.assertEqual(decision.intent_contract.core_questions, [])


class RouterAgreementTests(unittest.TestCase):
    """Core F9 invariant: when the chat contract flows through, the
    analysis router's ``core_questions`` must cover every question the chat
    tier declared. Extra analysis-tier questions are allowed (the analysis
    router can infer additional focus from intent/depth); dropping a
    chat-declared question is not.
    """

    CASES: list[str] = [
        # Cache-routed decisive phrasing.
        "Should I buy 526-west-end-ave?",
        "Is this a good deal?",
        "Underwrite 526-west-end-ave for me",
        # Cache-routed comparison.
        "Compare 526-west-end-ave vs 119-4th-ave-avon-by-the-sea-nj-07717",
        # Cache-routed projection.
        "What if we invested 100k into it?",
        # Cache-routed browse (via explicit-browse regex).
        "What do you think of 526-west-end-ave?",
    ]

    def test_analysis_router_covers_chat_contract_questions(self) -> None:
        misses: list[tuple[str, set[str], set[str]]] = []
        for text in self.CASES:
            chat_decision = classify(text)
            contract = chat_decision.intent_contract
            self.assertIsNotNone(contract, f"chat router did not emit contract for {text!r}")

            analysis_decision = route_user_input(text, intent_contract=contract)

            chat_questions = {q.value for q in contract.core_questions}
            analysis_questions = {q.value for q in analysis_decision.core_questions}

            if not chat_questions.issubset(analysis_questions):
                misses.append((text, chat_questions, analysis_questions))

        self.assertEqual(
            misses,
            [],
            f"router disagreement on core_questions: {misses}",
        )

    def test_analysis_router_without_contract_may_diverge(self) -> None:
        """Negative control: without the contract, the analysis router is
        free to pick its own focus. This test pins the contract as the
        fix mechanism rather than the pre-existing behavior."""

        text = "Where's the value on 526?"
        chat_decision = classify(text)
        chat_questions = {q.value for q in chat_decision.intent_contract.core_questions}
        # EDGE contract includes HIDDEN_UPSIDE — the rules-based analysis
        # parser doesn't emit HIDDEN_UPSIDE without the contract, so without
        # the contract threaded in, divergence is expected here.
        uncontracted = route_user_input(text)
        uncontracted_questions = {q.value for q in uncontracted.core_questions}
        self.assertNotIn("hidden_upside", uncontracted_questions)
        # With the contract, it flows through.
        contracted = route_user_input(text, intent_contract=chat_decision.intent_contract)
        contracted_questions = {q.value for q in contracted.core_questions}
        self.assertTrue(chat_questions.issubset(contracted_questions))


if __name__ == "__main__":
    unittest.main()

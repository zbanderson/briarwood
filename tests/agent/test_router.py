"""Answer Type Router — canned-question classification.

No live LLM calls; a fake client is injected when a test needs to exercise
the LLM fallback path.
"""

from __future__ import annotations

import unittest

from briarwood.agent.router import AnswerType, classify


CANNED: list[tuple[str, AnswerType]] = [
    # lookup
    ("What's the address of 526-west-end-ave?", AnswerType.LOOKUP),
    ("How many beds does 526-west-end-ave have?", AnswerType.LOOKUP),
    ("What is the list price?", AnswerType.LOOKUP),
    # decision
    ("Should I buy 526-west-end-ave?", AnswerType.DECISION),
    ("Is this a good deal?", AnswerType.DECISION),
    ("Underwrite 526-west-end-ave for me", AnswerType.DECISION),
    ("Worth it at 1.5M?", AnswerType.DECISION),
    # comparison
    ("Compare 526-west-end-ave vs 119-4th-ave-avon-by-the-sea-nj-07717", AnswerType.COMPARISON),
    ("Which one is better, 526-west-end-ave or 304-14th-ave?", AnswerType.COMPARISON),
    # search
    ("Find me 3-bed properties near the beach under 1.5M", AnswerType.SEARCH),
    ("Show me listings in Avon", AnswerType.SEARCH),
    # research
    ("What's happening in Avon-by-the-Sea?", AnswerType.RESEARCH),
    ("Research the town zoning changes", AnswerType.RESEARCH),
    # chitchat
    ("hi", AnswerType.CHITCHAT),
    ("thanks", AnswerType.CHITCHAT),
]


class RouterTests(unittest.TestCase):
    def test_canned_questions_route_correctly(self) -> None:
        misses: list[tuple[str, AnswerType, AnswerType]] = []
        for text, expected in CANNED:
            decision = classify(text)
            if decision.answer_type is not expected:
                misses.append((text, expected, decision.answer_type))
        self.assertEqual(misses, [], f"router misclassified: {misses}")

    def test_extracts_property_ref(self) -> None:
        decision = classify("Should I buy 526-west-end-ave?")
        self.assertIn("526-west-end-ave", decision.target_refs)

    def test_empty_input_is_chitchat(self) -> None:
        self.assertIs(classify("").answer_type, AnswerType.CHITCHAT)

    def test_llm_fallback_used_only_when_no_rule_matches(self) -> None:
        calls: list[str] = []

        class FakeLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                calls.append(user)
                return '{"answer_type": "decision", "reason": "fake"}'

        # Rule-matching question — LLM should NOT be called.
        classify("Should I buy 526-west-end-ave?", client=FakeLLM())
        self.assertEqual(calls, [])

        # No rule — LLM fallback fires.
        result = classify("ruminate on this property for a while", client=FakeLLM())
        self.assertEqual(len(calls), 1)
        self.assertIs(result.answer_type, AnswerType.DECISION)

    def test_absurd_llm_response_does_not_override_rule(self) -> None:
        class BadLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                return "totally not json"

        decision = classify("find me 3 beds near the beach", client=BadLLM())
        self.assertIs(decision.answer_type, AnswerType.SEARCH)


if __name__ == "__main__":
    unittest.main()

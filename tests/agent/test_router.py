"""Answer Type Router — cache rules + LLM classifier.

The router is LLM-first with a small regex cache for unambiguous, high-volume
patterns (greetings, explicit comparisons, explicit buy/pass phrasing,
explicit search imperatives). Everything else goes to the LLM.
"""

from __future__ import annotations

import unittest

from briarwood.agent.router import AnswerType, classify


# Only patterns that should hit the CACHE (no LLM needed).
CACHE_CANNED: list[tuple[str, AnswerType]] = [
    # chitchat (stand-alone greetings)
    ("hi", AnswerType.CHITCHAT),
    ("thanks", AnswerType.CHITCHAT),
    # comparison
    ("Compare 526-west-end-ave vs 119-4th-ave-avon-by-the-sea-nj-07717", AnswerType.COMPARISON),
    ("526-west-end-ave vs 119-4th-ave-avon-by-the-sea-nj-07717", AnswerType.COMPARISON),
    ("Which one is better, 526-west-end-ave or 304-14th-ave?", AnswerType.COMPARISON),
    # decision (explicit decisive verbs only)
    ("Should I buy 526-west-end-ave?", AnswerType.DECISION),
    ("Is this a good deal?", AnswerType.DECISION),
    ("Underwrite 526-west-end-ave for me", AnswerType.DECISION),
    ("Worth buying at 1.5M?", AnswerType.DECISION),
    # search (explicit imperatives)
    ("Show me listings in Avon", AnswerType.SEARCH),
    ("Find me properties near the beach", AnswerType.SEARCH),
    ("Look for similar homes", AnswerType.SEARCH),
]


# Patterns that require the LLM to classify correctly. Test uses a scripted
# FakeLLM that returns whatever the expected answer type is.
LLM_CANNED: list[tuple[str, AnswerType]] = [
    ("What's the address of 526-west-end-ave?", AnswerType.LOOKUP),
    ("How many beds does 526-west-end-ave have?", AnswerType.LOOKUP),
    ("What do you think of 526-west-end-ave?", AnswerType.BROWSE),
    ("Your take on 526-west-end-ave?", AnswerType.BROWSE),
    ("What's happening in Avon-by-the-Sea?", AnswerType.RESEARCH),
    ("What could go wrong with 526?", AnswerType.RISK),
    ("Where's the value on 526?", AnswerType.EDGE),
    ("What's the best way to play 526?", AnswerType.STRATEGY),
    ("How close is 526 to the beach?", AnswerType.MICRO_LOCATION),
    ("What does 526 become over 5 years?", AnswerType.PROJECTION),
    ("How much could 526 rent for?", AnswerType.RENT_LOOKUP),
]


class ScriptedLLM:
    """Fake LLM that returns a pre-computed JSON classification per input."""

    def __init__(self, routing: dict[str, AnswerType]):
        self.routing = routing
        self.calls: list[str] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        self.calls.append(user)
        answer = self.routing.get(user)
        if answer is None:
            return '{"answer_type": "lookup", "reason": "unmatched"}'
        return f'{{"answer_type": "{answer.value}", "reason": "scripted"}}'


class CacheRuleTests(unittest.TestCase):
    def test_cache_patterns_route_without_llm(self) -> None:
        """Cache hits should never consult the LLM — that's the whole point."""

        class UnusedLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("LLM must not be called for cache hits")

        misses: list[tuple[str, AnswerType, AnswerType]] = []
        for text, expected in CACHE_CANNED:
            decision = classify(text, client=UnusedLLM())
            if decision.answer_type is not expected:
                misses.append((text, expected, decision.answer_type))
        self.assertEqual(misses, [], f"cache misclassified: {misses}")


class LLMClassifyTests(unittest.TestCase):
    def test_llm_owns_semantic_routing(self) -> None:
        routing = {text: expected for text, expected in LLM_CANNED}
        llm = ScriptedLLM(routing)
        misses: list[tuple[str, AnswerType, AnswerType]] = []
        for text, expected in LLM_CANNED:
            decision = classify(text, client=llm)
            if decision.answer_type is not expected:
                misses.append((text, expected, decision.answer_type))
        self.assertEqual(misses, [], f"llm misclassified: {misses}")
        # Every LLM-routed turn should have gone through the LLM.
        self.assertEqual(len(llm.calls), len(LLM_CANNED))

    def test_llm_sets_suggestion_marker(self) -> None:
        llm = ScriptedLLM({"What do you think of 526?": AnswerType.BROWSE})
        decision = classify("What do you think of 526?", client=llm)
        self.assertIs(decision.answer_type, AnswerType.BROWSE)
        self.assertIs(decision.llm_suggestion, AnswerType.BROWSE)
        self.assertEqual(decision.reason, "llm classify")

    def test_chitchat_guess_on_substantive_text_falls_back_to_browse(self) -> None:
        """LLMs sometimes dump real questions into chitchat. Safer default:
        BROWSE (quick read), not DECISION (full cascade)."""

        class ChitChatLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                return '{"answer_type": "chitchat", "reason": "unclear"}'

        decision = classify("ruminate on this property", client=ChitChatLLM())
        self.assertIs(decision.answer_type, AnswerType.BROWSE)

    def test_absurd_llm_response_falls_back_to_default(self) -> None:
        class BadLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                return "totally not json"

        decision = classify("ruminate on this property", client=BadLLM())
        self.assertIs(decision.answer_type, AnswerType.LOOKUP)
        self.assertEqual(decision.reason, "default fallback")


class PrecedenceTests(unittest.TestCase):
    def test_explicit_decision_beats_browse_phrasing(self) -> None:
        """Cache rules scan before the LLM: decision verb wins when both
        browse-style and decisive phrasing appear in the same turn."""
        decision = classify("What do you think of 526-west-end-ave? Should I buy?")
        self.assertIs(decision.answer_type, AnswerType.DECISION)

    def test_price_override_short_circuits_to_decision(self) -> None:
        decision = classify("what if I bought 526-west-end-ave at 1.3M?")
        self.assertIs(decision.answer_type, AnswerType.DECISION)
        self.assertEqual(decision.reason, "what-if price override")


class InfrastructureTests(unittest.TestCase):
    def test_extracts_property_ref(self) -> None:
        decision = classify("Should I buy 526-west-end-ave?")
        self.assertIn("526-west-end-ave", decision.target_refs)

    def test_empty_input_is_chitchat(self) -> None:
        self.assertIs(classify("").answer_type, AnswerType.CHITCHAT)

    def test_no_llm_non_cache_falls_back_to_lookup(self) -> None:
        decision = classify("What do you think of 526?")
        self.assertIs(decision.answer_type, AnswerType.LOOKUP)
        self.assertEqual(decision.reason, "default fallback")


if __name__ == "__main__":
    unittest.main()

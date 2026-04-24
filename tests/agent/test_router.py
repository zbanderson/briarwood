"""Answer Type Router — cache rules + LLM classifier.

The router is LLM-first with a small regex cache for unambiguous, high-volume
patterns (greetings, explicit comparisons, explicit buy/pass phrasing,
explicit search imperatives). Everything else goes to the LLM.
"""

from __future__ import annotations

import unittest

from briarwood.agent.router import (
    AnswerType,
    PersonaType,
    RouterClassification,
    UseCaseType,
    classify,
)


# Cache rules are narrow by design (post-plan C2): only chitchat greetings
# and explicit compare strings short-circuit without the LLM. Every other
# intent (decision, projection, search, browse, risk, edge, ...) routes
# through the LLM so the classifier generates training signal.
CACHE_CANNED: list[tuple[str, AnswerType]] = [
    # chitchat (stand-alone greetings)
    ("hi", AnswerType.CHITCHAT),
    ("thanks", AnswerType.CHITCHAT),
    # comparison
    ("Compare 526-west-end-ave vs 119-4th-ave-avon-by-the-sea-nj-07717", AnswerType.COMPARISON),
    ("526-west-end-ave vs 119-4th-ave-avon-by-the-sea-nj-07717", AnswerType.COMPARISON),
    ("Which one is better, 526-west-end-ave or 304-14th-ave?", AnswerType.COMPARISON),
]


# Patterns that require the LLM to classify correctly. Test uses a scripted
# FakeLLM that returns whatever the expected answer type is.
LLM_CANNED: list[tuple[str, AnswerType]] = [
    ("What's the address of 526-west-end-ave?", AnswerType.LOOKUP),
    ("How many beds does 526-west-end-ave have?", AnswerType.LOOKUP),
    ("What's happening in Avon-by-the-Sea?", AnswerType.RESEARCH),
    ("What could go wrong with 526?", AnswerType.RISK),
    ("Where's the value on 526?", AnswerType.EDGE),
    ("What's the best way to play 526?", AnswerType.STRATEGY),
    ("How close is 526 to the beach?", AnswerType.MICRO_LOCATION),
    ("What does 526 become over 5 years?", AnswerType.PROJECTION),
    ("How much could 526 rent for?", AnswerType.RENT_LOOKUP),
    # Decision phrasing now routes through the LLM (was cached).
    ("Should I buy 526-west-end-ave?", AnswerType.DECISION),
    ("Is this a good deal?", AnswerType.DECISION),
    ("Underwrite 526-west-end-ave for me", AnswerType.DECISION),
    # Projection scenarios now routed through the LLM (was cached). Note:
    # entries that contain a price literal ("100k") or renovation+sell
    # phrasing fire the what-if / projection override paths and short-
    # circuit before the LLM — not relevant here.
    ("What's the ARV on 526-west-end-ave?", AnswerType.PROJECTION),
    # Search imperatives now routed through the LLM (was cached).
    ("Show me listings in Avon", AnswerType.SEARCH),
    ("Find me properties near the beach", AnswerType.SEARCH),
    ("Look for similar homes", AnswerType.SEARCH),
    # Browse phrasing now routed through the LLM (was cached).
    ("What do you think of 1008 14th Ave, Belmar, NJ", AnswerType.BROWSE),
    ("Tell me about 1008 14th Avenue, Belmar, NJ 07719", AnswerType.BROWSE),
    ("What do you think of 526-west-end-ave?", AnswerType.BROWSE),
    ("Your take on 526-west-end-ave?", AnswerType.BROWSE),
]


class ScriptedLLM:
    """Fake LLM that returns a pre-computed classification per input.

    After AUDIT 1.2.2 the router uses `complete_structured` with a Pydantic
    schema, so the fake returns `RouterClassification` instances directly."""

    def __init__(self, routing: dict[str, AnswerType]):
        self.routing = routing
        self.calls: list[str] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        raise AssertionError("router should use complete_structured, not complete")

    def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
        self.calls.append(user)
        answer = self.routing.get(user, AnswerType.LOOKUP)
        return schema(
            answer_type=answer,
            persona_type=PersonaType.UNKNOWN,
            use_case_type=UseCaseType.UNKNOWN,
            reason="scripted",
        )


class CacheRuleTests(unittest.TestCase):
    def test_cache_patterns_route_without_llm(self) -> None:
        """Cache hits should never consult the LLM — that's the whole point."""

        class UnusedLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("LLM must not be called for cache hits")

            def complete_structured(self, **_kwargs) -> None:
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

    def test_llm_user_type_metadata_does_not_change_answer_type(self) -> None:
        class InvestorLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("router should use complete_structured")

            def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
                return schema(
                    answer_type=AnswerType.BROWSE,
                    persona_type=PersonaType.INVESTOR,
                    use_case_type=UseCaseType.RENTAL,
                    reason="investment browse",
                )

        decision = classify("What do you think of this as a rental?", client=InvestorLLM())
        self.assertIs(decision.answer_type, AnswerType.BROWSE)
        self.assertIs(decision.user_type.persona_type, PersonaType.INVESTOR)
        self.assertIs(decision.user_type.use_case_type, UseCaseType.RENTAL)

    def test_chitchat_guess_on_substantive_text_falls_back_to_browse(self) -> None:
        """LLMs sometimes dump real questions into chitchat. Safer default:
        BROWSE (quick read), not DECISION (full cascade)."""

        class ChitChatLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("router should use complete_structured")

            def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
                return schema(
                    answer_type=AnswerType.CHITCHAT,
                    persona_type=PersonaType.UNKNOWN,
                    use_case_type=UseCaseType.UNKNOWN,
                    reason="unclear",
                )

        decision = classify("ruminate on this property", client=ChitChatLLM())
        self.assertIs(decision.answer_type, AnswerType.BROWSE)

    def test_absurd_llm_response_falls_back_to_default(self) -> None:
        """AUDIT 1.2.2: the structured path returns `None` on schema /
        transport failure, and the router defaults to LOOKUP."""

        class BadLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("router should use complete_structured")

            def complete_structured(self, **_kwargs) -> None:
                return None

        decision = classify("ruminate on this property", client=BadLLM())
        self.assertIs(decision.answer_type, AnswerType.LOOKUP)
        self.assertEqual(decision.reason, "default fallback")

    def test_router_classification_schema_has_no_ref_sibling_defaults(self) -> None:
        """OpenAI strict mode ignores siblings to `$ref`, so a Pydantic
        `default` on an enum-typed field never reaches the API. Guard
        against re-introducing a default on `persona_type`/`use_case_type`
        (or any future `$ref` field) — that would silently mask LLM
        non-compliance instead of failing validation and falling back.
        """
        schema = RouterClassification.model_json_schema()
        offenders = [
            name for name, prop in schema["properties"].items()
            if "$ref" in prop and "default" in prop
        ]
        self.assertEqual(offenders, [], f"fields with $ref+default: {offenders}")


class PrecedenceTests(unittest.TestCase):
    def test_price_override_short_circuits_to_decision(self) -> None:
        decision = classify("what if I bought 526-west-end-ave at 1.3M?")
        self.assertIs(decision.answer_type, AnswerType.DECISION)
        self.assertEqual(decision.reason, "what-if price override")

    def test_renovation_override_with_rent_question_routes_to_rent_lookup(self) -> None:
        decision = classify(
            "what would a fully renovated 3 bed 2 bath house rent for in belmar, maybe we can buy it, live there, renovate, rent it"
        )
        self.assertIs(decision.answer_type, AnswerType.RENT_LOOKUP)
        self.assertEqual(decision.reason, "override with rent question")


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

    def test_rule_user_type_fallback_is_conservative(self) -> None:
        decision = classify("Could we live in one unit and rent the back house?")
        self.assertIs(decision.answer_type, AnswerType.LOOKUP)
        self.assertIs(decision.user_type.use_case_type, UseCaseType.HOUSE_HACK)

    def test_rule_user_type_covers_buyer_and_developer_signals(self) -> None:
        buyer = classify("As a first-time buyer, could I live here with my family?")
        developer = classify("Could a developer redevelop this lot?")
        self.assertIs(buyer.user_type.persona_type, PersonaType.FIRST_TIME_BUYER)
        self.assertIs(buyer.user_type.use_case_type, UseCaseType.OWNER_OCCUPANT)
        self.assertIs(developer.user_type.persona_type, PersonaType.DEVELOPER)
        self.assertIs(developer.user_type.use_case_type, UseCaseType.DEVELOPMENT)


if __name__ == "__main__":
    unittest.main()

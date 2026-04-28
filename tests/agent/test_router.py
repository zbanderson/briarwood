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
    # Price-analysis phrasings — explicit ask for analysis (not a single fact)
    # routes to DECISION. Added 2026-04-25 after the live-traffic miss where
    # "what is the price analysis for X" was classified as LOOKUP and produced
    # a one-line factual answer. See ROADMAP.md and the prompt's
    # IMPORTANT MAPPINGS section for the full list of analysis triggers.
    ("what is the price analysis for 1008 14th Ave, belmar, nj", AnswerType.DECISION),
    ("analyze the price of 526-west-end-ave", AnswerType.DECISION),
    ("is 526-west-end-ave priced right?", AnswerType.DECISION),
    ("how is 526-west-end-ave priced?", AnswerType.DECISION),
    # Asking-price-as-fact stays LOOKUP — the boundary case.
    ("what is the asking price of 526-west-end-ave?", AnswerType.LOOKUP),
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
    # STRATEGY escalation phrasings — added 2026-04-28 after live-traffic miss
    # where "Walk me through the recommended path" classified as BROWSE and
    # re-ran the full first-read instead of routing to handle_strategy.
    # See ROADMAP.md §4 "Audit router classification boundaries" 2026-04-28
    # additions and ROUTER_AUDIT_HANDOFF_PLAN.md.
    ("Walk me through the recommended path", AnswerType.STRATEGY),
    ("What should I do here?", AnswerType.STRATEGY),
    ("What's the play here?", AnswerType.STRATEGY),
    # EDGE sensitivity / counterfactual phrasings — added 2026-04-28 after
    # live-traffic miss where "What would change your value view?" classified
    # as RISK. RISK enumerates downside; EDGE surfaces what would shift the read.
    ("What would change your view of 526?", AnswerType.EDGE),
    ("What would shift the number?", AnswerType.EDGE),
    ("How sensitive is your number?", AnswerType.EDGE),
    # SEARCH list/show-imperative phrasings — already in ROADMAP entry items
    # 3-4. "show me X" with X = listings/properties is SEARCH, not BROWSE.
    ("Show me the listings here", AnswerType.SEARCH),
    ("List the properties in Belmar", AnswerType.SEARCH),
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
            confidence=0.7,
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
                    confidence=0.8,
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
                    confidence=0.5,
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

    def test_llm_confidence_flows_through_to_decision(self) -> None:
        """Plumbed 2026-04-28 (Round 2 Cycle 1). Previously every LLM
        classification was hardcoded to 0.6; now the LLM's emitted
        confidence flows through (with a 0.4 floor)."""

        class HighConfidenceLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("router should use complete_structured")

            def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
                return schema(
                    answer_type=AnswerType.BROWSE,
                    persona_type=PersonaType.UNKNOWN,
                    use_case_type=UseCaseType.UNKNOWN,
                    confidence=0.92,
                    reason="canonical browse phrasing",
                )

        decision = classify("What do you think of 526?", client=HighConfidenceLLM())
        self.assertEqual(decision.confidence, 0.92)
        self.assertEqual(decision.reason, "llm classify")

    def test_llm_confidence_floored_at_0_4(self) -> None:
        """The 0.4 floor keeps every LLM classification above the 0.3
        default-fallback bucket. Documented as a deliberate guardrail."""

        class LowConfidenceLLM:
            def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
                raise AssertionError("router should use complete_structured")

            def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
                return schema(
                    answer_type=AnswerType.BROWSE,
                    persona_type=PersonaType.UNKNOWN,
                    use_case_type=UseCaseType.UNKNOWN,
                    confidence=0.1,
                    reason="genuinely don't know",
                )

        decision = classify("ambiguous text", client=LowConfidenceLLM())
        self.assertEqual(decision.confidence, 0.4)

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
        # Round 2 Cycle 2 (2026-04-28) tightened the router's
        # what-if-price-override branch to require a material override
        # (ask_price / repair_capex_budget). This test now uses an
        # explicit "if I bought... at 1.3M" framing to exercise the
        # override+rent-question path; the prior mode-only signal no
        # longer triggers the branch by design.
        decision = classify(
            "if I bought a fully renovated 3 bed 2 bath house at 1.3M, what would it rent for"
        )
        self.assertIs(decision.answer_type, AnswerType.RENT_LOOKUP)
        self.assertEqual(decision.reason, "override with rent question")

    def test_bare_renovation_does_not_trigger_what_if_override(self) -> None:
        """Round 2 Cycle 2 (2026-04-28): 'Run renovation scenarios' must
        NOT short-circuit to DECISION via the what-if-price-override
        branch. With Layer A tightening, parse_overrides returns empty
        for bare-renovation, so has_override is False and the turn
        falls through to the LLM (or the no-LLM default fallback)."""
        decision = classify("Run renovation scenarios")
        self.assertNotEqual(decision.reason, "what-if price override")

    def test_renovation_scenarios_with_price_routes_to_projection(self) -> None:
        """Layer B widening: when has_override is True AND the text
        carries a 'renovation scenarios' / 'scenario' / 'run scenarios'
        token, the override branch routes to PROJECTION rather than
        defaulting to DECISION."""
        decision = classify(
            "if I bought at 1.3M what would the renovation scenarios look like"
        )
        self.assertIs(decision.answer_type, AnswerType.PROJECTION)
        self.assertEqual(decision.reason, "override with projection question")


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


class PromptContentRegressionTests(unittest.TestCase):
    """Pin substantive parts of `_LLM_SYSTEM` so future edits don't silently
    revert intent boundaries. These tests inspect the prompt string directly
    — they don't call the LLM. The actual LLM behavior is verified by user
    testing against gpt-4o-mini; these guard against the prompt regressing
    on already-decided rules.

    Added 2026-04-25 (output-quality audit handoff) after a live-traffic miss
    where 'what is the price analysis for X' was classified as LOOKUP."""

    def _prompt(self) -> str:
        from briarwood.agent.router import _LLM_SYSTEM
        return _LLM_SYSTEM.lower()

    def test_lookup_is_described_as_single_fact_only(self) -> None:
        """LOOKUP must read as 'no analysis, no interpretation' — otherwise
        the LLM lumps analysis questions in."""
        prompt = self._prompt()
        self.assertIn("single-fact retrieval", prompt)
        self.assertIn("no analysis or interpretation", prompt)

    def test_decision_includes_price_analysis_phrasings(self) -> None:
        """DECISION must enumerate the price-analysis phrasings so the LLM
        routes 'price analysis', 'analyze the price', etc. correctly."""
        prompt = self._prompt()
        self.assertIn("price analysis", prompt)
        self.assertIn("analyze the price", prompt)
        self.assertIn("priced right", prompt)
        self.assertIn("thoughts on the price", prompt)

    def test_lookup_to_decision_boundary_example_present(self) -> None:
        """The counter-example pair ('asking price' = LOOKUP vs 'price
        analysis' = DECISION) is the clearest disambiguation signal we can
        give the model. Pin it so it doesn't get edited away."""
        prompt = self._prompt()
        self.assertIn("asking price", prompt)
        # Both poles of the boundary must be named.
        self.assertIn("'what is the price analysis", prompt)
        self.assertIn("'what is the asking price", prompt)

    def test_strategy_includes_escalation_phrasings(self) -> None:
        """STRATEGY must absorb 'recommended path' / 'walk me through' /
        'what should I do here' / 'next move'. Added 2026-04-28 after the
        live-traffic miss where 'Walk me through the recommended path'
        re-ran the full BROWSE cascade instead of routing to STRATEGY."""
        prompt = self._prompt()
        self.assertIn("recommended path", prompt)
        self.assertIn("walk me through the recommended path", prompt)
        self.assertIn("what should i do here", prompt)
        self.assertIn("next move", prompt)

    def test_edge_includes_sensitivity_phrasings(self) -> None:
        """EDGE must absorb sensitivity / counterfactual phrasings.
        Added 2026-04-28 after the live-traffic miss where 'What would
        change your value view?' classified as RISK. The boundary is
        'what would *shift* my view' (EDGE) vs 'what could *go wrong*'
        (RISK)."""
        prompt = self._prompt()
        self.assertIn("what would change your view", prompt)
        self.assertIn("what would shift the number", prompt)
        self.assertIn("how sensitive", prompt)
        self.assertIn("load-bearing", prompt)

    def test_edge_absorbs_comp_set_followups(self) -> None:
        """Comp-set follow-ups on a pinned property are EDGE, not RESEARCH
        or BROWSE. Pinned in the prompt so the LLM has a clear mapping."""
        prompt = self._prompt()
        self.assertIn("show me the comps", prompt)
        self.assertIn("list the comps", prompt)
        self.assertIn("why were these comps chosen", prompt)
        self.assertIn("explain your comp choice", prompt)

    def test_search_includes_list_imperative_phrasings(self) -> None:
        """SEARCH must absorb 'show me listings' / 'list the properties'
        — list-style imperatives that name plural inventory artifacts."""
        prompt = self._prompt()
        self.assertIn("show me listings here", prompt)
        self.assertIn("list the properties", prompt)

    def test_browse_to_strategy_boundary_example_present(self) -> None:
        """Counter-example pair pinning the BROWSE→STRATEGY escalation
        boundary so a future prompt edit can't silently regress it."""
        prompt = self._prompt()
        self.assertIn("'walk me through the recommended path for x'", prompt)
        self.assertIn("escalated from first-read", prompt)

    def test_prompt_asks_for_confidence_score(self) -> None:
        """Round 2 Cycle 1 added an explicit ask for `confidence` in the
        JSON response. Pin so a future prompt edit can't silently remove
        the field — without it, every LLM call comes back without a
        confidence and Pydantic validation fails."""
        prompt = self._prompt()
        self.assertIn("\"confidence\": <float 0-1>", prompt)
        self.assertIn("under-confidence is preferred to false certainty", prompt)

    def test_risk_to_edge_boundary_example_present(self) -> None:
        """Counter-example pair pinning the RISK vs EDGE boundary —
        downside enumeration vs counterfactual / sensitivity."""
        prompt = self._prompt()
        self.assertIn("'what could go wrong with x' is risk", prompt)
        self.assertIn("'what would change your view of x' is edge", prompt)


if __name__ == "__main__":
    unittest.main()

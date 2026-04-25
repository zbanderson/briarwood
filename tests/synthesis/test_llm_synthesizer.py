"""Cycle 4 of OUTPUT_QUALITY_HANDOFF_PLAN.md — Layer 3 LLM synthesizer.

Pins the contract the chat-tier prose path will rely on once
``handle_browse`` is wired to call the synthesizer:

- A scripted LLM's text reaches the user verbatim (modulo grounding-marker
  stripping) when the draft is clean.
- The numeric guardrail still fires — a draft that cites numbers absent
  from the unified output triggers a regen attempt and, if the regen
  doesn't help, the violations are recorded in the report.
- The single LLM call is observable in the shared ledger under the
  surface name ``synthesis.llm`` (the regen, when it fires, lands at
  ``synthesis.llm.regen``).
- Empty / missing inputs short-circuit cleanly with
  ``empty=True, reason=...`` so callers can branch.

The tests use a scripted LLM that returns canned strings; the
deterministic verifier path is exercised end-to-end without hitting a
real model.
"""

from __future__ import annotations

from typing import Any

import pytest

from briarwood.agent.llm_observability import get_llm_ledger
from briarwood.intent_contract import IntentContract
from briarwood.routing_schema import CoreQuestion
from briarwood.synthesis.llm_synthesizer import synthesize_with_llm


class _ScriptedLLM:
    """Returns the next queued text response for ``complete()`` calls."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 360) -> str:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        if not self.responses:
            raise RuntimeError("ScriptedLLM exhausted")
        return self.responses.pop(0)

    def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
        raise AssertionError("synthesize_with_llm should not call structured output")


def _intent(answer_type: str = "browse") -> IntentContract:
    return IntentContract(
        answer_type=answer_type,
        core_questions=[CoreQuestion.SHOULD_I_BUY],
        question_focus=["should_i_buy"],
        confidence=0.7,
    )


def _unified_with_numbers() -> dict[str, Any]:
    return {
        "recommendation": "Briarwood reads this as a measured buy if carry holds.",
        "decision": "buy",
        "decision_stance": "buy_if_price_improves",
        "best_path": "Proceed with diligence on rent assumptions.",
        "key_value_drivers": ["Ask sits below the comp anchor by ~3.9%"],
        "key_risks": ["Thin rent inputs", "Carry tightens at higher rates"],
        "trust_flags": ["weak_town_context"],
        "primary_value_source": "current_value",
        "value_position": {
            "ask_price": 1499000,
            "fair_value_base": 1560000,
            "ask_premium_pct": -0.039,
        },
        "confidence": 0.62,
        "analysis_depth_used": "snapshot",
    }


def setup_function() -> None:
    get_llm_ledger().clear()


def test_clean_draft_returns_prose_unchanged_after_marker_strip() -> None:
    draft = (
        "At a $1,499,000 ask the listing sits roughly 3.9% under the "
        "$1,560,000 comp anchor, so on price alone Briarwood reads this as "
        "a measured buy. Carry economics still depend on the rent assumption, "
        "and the town backdrop is lightly documented, so confirm both before "
        "committing."
    )
    llm = _ScriptedLLM([draft])

    prose, report = synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    assert prose == draft
    assert report["empty"] is False
    # Grounded numbers — verifier should pass.
    assert report["sentences_with_violations"] == 0
    assert report["surface"] == "synthesis.llm"
    # Single LLM call recorded under the synthesis.llm surface.
    ledger_records = get_llm_ledger().records
    assert any(r.surface == "synthesis.llm" and r.status == "success" for r in ledger_records)


def test_ledger_metadata_carries_intent_and_tier_hints() -> None:
    llm = _ScriptedLLM(["ok"])
    synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    matches = [r for r in get_llm_ledger().records if r.surface == "synthesis.llm"]
    assert matches, "expected a synthesis.llm ledger record"
    record = matches[-1]
    assert record.metadata.get("tier") == "synthesis_llm"
    assert record.metadata.get("answer_type") == "browse"


def test_ungrounded_numbers_trigger_regen_when_threshold_exceeded() -> None:
    # First draft cites three fabricated dollar amounts; second draft cites
    # only grounded values. The regen path should swap in the cleaner draft.
    bad_draft = (
        "Briarwood thinks the basement rents for $4,200 a month, "
        "comp set lands $87,000 over ask, and the cap rate sits at 6.4%."
    )
    good_draft = (
        "At a $1,499,000 ask the listing sits about 3.9% below the "
        "$1,560,000 comp anchor, which Briarwood reads as a measured buy."
    )
    llm = _ScriptedLLM([bad_draft, good_draft])

    prose, report = synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    # Two LLM calls total — initial + regen.
    assert len(llm.calls) == 2
    assert prose == good_draft
    assert report["sentences_with_violations"] == 0
    # Both surfaces should appear in the ledger.
    surfaces = {r.surface for r in get_llm_ledger().records}
    assert "synthesis.llm" in surfaces
    assert "synthesis.llm.regen" in surfaces


def test_regen_kept_only_when_violations_strictly_decrease() -> None:
    # Both drafts cite ungrounded numbers; regen does NOT improve. Original
    # draft is kept (with the violations recorded in the report).
    bad_draft = "The basement rents for $4,200, comps run $87,000 high, cap rate 6.4%."
    worse_draft = "Basement at $4,200, comps $87,000 high, cap 6.4%, also $9,123 added."
    llm = _ScriptedLLM([bad_draft, worse_draft])

    prose, report = synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    assert prose == bad_draft
    # Violations still present in the kept draft.
    assert report["sentences_with_violations"] >= 1


def test_missing_llm_returns_empty_with_reason() -> None:
    prose, report = synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=None,
    )
    assert prose == ""
    assert report == {"empty": True, "reason": "llm_or_unified_missing"}


def test_empty_unified_short_circuits() -> None:
    llm = _ScriptedLLM(["should not be called"])
    prose, report = synthesize_with_llm(
        unified={},
        intent=_intent("browse"),
        llm=llm,
    )
    assert prose == ""
    assert report["empty"] is True
    assert llm.calls == []


def test_blank_llm_response_returns_empty() -> None:
    llm = _ScriptedLLM([""])
    prose, report = synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )
    assert prose == ""
    assert report == {"empty": True, "reason": "blank_draft"}


def test_llm_exception_swallowed_returns_empty() -> None:
    class _ExplodingLLM:
        def complete(self, *, system: str, user: str, max_tokens: int = 360) -> str:
            raise RuntimeError("provider boom")

    prose, report = synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=_ExplodingLLM(),
    )
    assert prose == ""
    assert report["empty"] is True
    assert report["reason"].startswith("exception:")


def test_intent_payload_is_serialized_into_user_prompt() -> None:
    """The synthesizer must pass the intent contract into the user message
    so the LLM can lead with the right framing — tested by inspecting the
    user prompt the scripted LLM was called with."""

    llm = _ScriptedLLM([
        "At $1,499,000 against a $1,560,000 anchor the math reads as a measured buy."
    ])

    synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("risk"),  # different answer_type to verify it lands
        llm=llm,
    )

    assert len(llm.calls) == 1
    user_prompt = llm.calls[0]["user"]
    assert '"answer_type": "risk"' in user_prompt
    assert '"core_questions"' in user_prompt
    assert '"unified"' in user_prompt
    # Sanity: intent comes BEFORE unified so the LLM frames the answer.
    assert user_prompt.index('"intent"') < user_prompt.index('"unified"')


def test_system_prompt_pins_numeric_grounding_rule() -> None:
    """Regression: the system prompt must continue to require numeric
    grounding even as voice/framing instructions evolve. The composer's
    earlier 'rewrite using only values present' wording was loosened in
    DECISIONS.md 2026-04-25 — the synthesizer must not regress to that
    wording but must keep the numeric rule."""

    llm = _ScriptedLLM(["ok."])
    synthesize_with_llm(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )
    assert len(llm.calls) == 1
    system = llm.calls[0]["system"]
    assert "NUMERIC GROUNDING" in system
    # Allow line wrapping between "value" and "present" in the rule body.
    normalized = " ".join(system.split())
    assert "round to a value present in the `unified` JSON" in normalized
    # The robotic-prose wording must NOT be in the system prompt.
    assert "rewrite using only values present" not in system.lower()

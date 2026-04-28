"""Cycle 1 of SCOUT_HANDOFF_PLAN.md (Phase 4b) — LLM scout module.

Pins the contract chat-tier handlers will rely on once Cycle 2 wires
``scout_unified`` into ``handle_browse``:

- A scripted LLM's structured output reaches the caller — both insights
  surfaced when the draft is clean.
- The numeric guardrail fires — a draft citing numbers absent from the
  unified output triggers a regen attempt at surface
  ``value_scout.scan.regen``; when the regen cannot improve grounding,
  the empty contract is returned (stricter than the synthesizer's
  keep-original posture).
- Empty / missing inputs short-circuit cleanly with
  ``empty=True, reason=...`` so callers can branch.
- Manifest contract: every successful call lands a ``value_scout.scan``
  record in the shared LLM ledger; regen lands at
  ``value_scout.scan.regen``.
- Prompt regression: the system prompt pins the "1-2 most non-obvious
  angles" framing and the supporting-field citation requirement.

The tests use a scripted LLM that returns canned ``_ScoutScanResult``
instances; the deterministic verifier path is exercised end-to-end
without hitting a real model.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from briarwood.agent.llm_observability import get_llm_ledger
from briarwood.intent_contract import IntentContract
from briarwood.routing_schema import CoreQuestion
from briarwood.value_scout import scout_unified
from briarwood.value_scout.llm_scout import (
    _SYSTEM_PROMPT,
    _ScoutInsightOut,
    _ScoutScanResult,
)


class _ScriptedLLM:
    """Returns the next queued structured response for ``complete_structured``."""

    def __init__(self, responses: list[_ScoutScanResult | None | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 360) -> str:
        raise AssertionError("scout_unified should not call complete()")

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 600,
    ) -> BaseModel | None:
        self.calls.append(
            {"system": system, "user": user, "schema": schema, "model": model}
        )
        if not self.responses:
            raise RuntimeError("ScriptedLLM exhausted")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _intent(answer_type: str = "browse") -> IntentContract:
    return IntentContract(
        answer_type=answer_type,
        core_questions=[CoreQuestion.SHOULD_I_BUY],
        question_focus=["should_i_buy"],
        confidence=0.7,
    )


def _unified_with_numbers() -> dict[str, Any]:
    """Unified output where headline values round to grounded numbers.

    The verifier flattens nested values; the numbers cited by clean
    fixtures below ($1,499,000, 12%, 0.62) all round to a value present
    here.
    """

    return {
        "recommendation": "Briarwood reads this as a measured buy if carry holds.",
        "decision": "buy",
        "value_position": {
            "ask_price": 1499000,
            "fair_value_base": 1560000,
            "ask_premium_pct": -0.039,
        },
        "rental_option": {
            "rent_support_score": 0.74,
            "monthly_rent_estimate": 4200,
        },
        "market_value_history": {
            "three_year_change_pct": 0.12,
        },
        "confidence": 0.62,
    }


def _scan_result(insights: list[dict[str, Any]]) -> _ScoutScanResult:
    return _ScoutScanResult(
        insights=[_ScoutInsightOut(**ins) for ins in insights]
    )


def setup_function() -> None:
    get_llm_ledger().clear()


# -----------------------------------------------------------------------
# Clean draft
# -----------------------------------------------------------------------

def test_clean_draft_returns_two_insights_in_confidence_order() -> None:
    llm = _ScriptedLLM([
        _scan_result([
            {
                "headline": "Rent profile is unusually strong.",
                "reason": "The rent support score sits at 0.74 with monthly rent near 4200.",
                "supporting_fields": [
                    "rental_option.rent_support_score",
                    "rental_option.monthly_rent_estimate",
                ],
                "category": "rent_angle",
                "confidence": 0.78,
            },
            {
                "headline": "Town trend is supportive.",
                "reason": "Three-year change runs roughly 12%.",
                "supporting_fields": ["market_value_history.three_year_change_pct"],
                "category": "town_trend",
                "confidence": 0.65,
            },
        ]),
    ])

    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    assert len(insights) == 2
    assert insights[0].category == "rent_angle"
    assert insights[1].category == "town_trend"
    # Confidence ordering descending.
    assert insights[0].confidence == 0.78
    assert insights[1].confidence == 0.65
    # Schema extension surfaced cleanly.
    assert insights[0].headline.startswith("Rent profile")
    assert insights[0].supporting_fields == [
        "rental_option.rent_support_score",
        "rental_option.monthly_rent_estimate",
    ]
    # scenario_id stays None for chat-tier insights.
    assert insights[0].scenario_id is None
    assert insights[1].scenario_id is None

    assert report["empty"] is False
    assert report["surface"] == "value_scout.scan"
    assert report["insights_generated"] == 2
    assert report["insights_surfaced"] == 2
    assert report["top_confidence"] == 0.78


def test_max_insights_caps_returned_list() -> None:
    llm = _ScriptedLLM([
        _scan_result([
            {
                "headline": "Angle one is grounded.",
                "reason": "Backed by rent support score 0.74.",
                "supporting_fields": ["rental_option.rent_support_score"],
                "category": "rent_angle",
                "confidence": 0.85,
            },
            {
                "headline": "Angle two is grounded.",
                "reason": "Three-year change runs roughly 12%.",
                "supporting_fields": ["market_value_history.three_year_change_pct"],
                "category": "town_trend",
                "confidence": 0.70,
            },
            {
                "headline": "Angle three is grounded.",
                "reason": "Ask sits at 1,499,000.",
                "supporting_fields": ["value_position.ask_price"],
                "category": "comp_anomaly",
                "confidence": 0.60,
            },
        ]),
    ])

    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
        max_insights=2,
    )

    assert len(insights) == 2
    # Top two by confidence kept.
    assert [i.confidence for i in insights] == [0.85, 0.70]
    assert report["insights_generated"] == 3
    assert report["insights_surfaced"] == 2


# -----------------------------------------------------------------------
# Numeric grounding & regen
# -----------------------------------------------------------------------

def test_ungrounded_draft_triggers_regen_and_keeps_improved_version() -> None:
    # First draft cites three numbers absent from unified ($999k, 88%, 5.5x);
    # the regen returns a clean version. Both should appear in the ledger.
    bad = _scan_result([
        {
            "headline": "Town comps imply roughly 88% premium support.",
            "reason": "Sale-pricing tilts 5.5x above the comp anchor.",
            "supporting_fields": ["market_value_history.three_year_change_pct"],
            "category": "town_trend",
            "confidence": 0.7,
        },
        {
            "headline": "Operating math hits roughly $999k of upside.",
            "reason": "Rent support sits well above carry.",
            "supporting_fields": ["rental_option.rent_support_score"],
            "category": "carry_yield_mismatch",
            "confidence": 0.65,
        },
    ])
    good = _scan_result([
        {
            "headline": "Rent support is materially above the carry.",
            "reason": "rent_support_score sits at 0.74.",
            "supporting_fields": ["rental_option.rent_support_score"],
            "category": "rent_angle",
            "confidence": 0.78,
        },
    ])
    llm = _ScriptedLLM([bad, good])

    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    # Regen kept (it strictly reduced violations vs the original draft).
    assert len(insights) == 1
    assert insights[0].category == "rent_angle"
    assert report["empty"] is False
    # Both surfaces appear in the ledger.
    surfaces = [r.surface for r in get_llm_ledger().records]
    assert "value_scout.scan" in surfaces
    assert "value_scout.scan.regen" in surfaces


def test_regen_without_improvement_returns_empty_contract() -> None:
    # Both drafts are ungrounded; regen does not strictly reduce violations.
    bad_a = _scan_result([
        {
            "headline": "Premium support implies a roughly 88% comp delta.",
            "reason": "The sale-pricing index runs 5.5x the local anchor.",
            "supporting_fields": ["market_value_history.three_year_change_pct"],
            "category": "town_trend",
            "confidence": 0.7,
        },
    ])
    bad_b = _scan_result([
        {
            "headline": "The premium delta still runs roughly 88%.",
            "reason": "Carry math implies a 5.5x mismatch.",
            "supporting_fields": ["rental_option.rent_support_score"],
            "category": "carry_yield_mismatch",
            "confidence": 0.65,
        },
    ])
    llm = _ScriptedLLM([bad_a, bad_b])

    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    assert insights == []
    assert report["empty"] is True
    assert report["reason"] == "ungrounded_after_regen"
    assert report["surface"] == "value_scout.scan"
    # Regen call DID happen — both surfaces in the ledger.
    surfaces = [r.surface for r in get_llm_ledger().records]
    assert "value_scout.scan" in surfaces
    assert "value_scout.scan.regen" in surfaces


# -----------------------------------------------------------------------
# Empty contract paths
# -----------------------------------------------------------------------

def test_missing_unified_returns_empty_without_llm_call() -> None:
    llm = _ScriptedLLM([])
    insights, report = scout_unified(
        unified={},
        intent=_intent("browse"),
        llm=llm,
    )
    assert insights == []
    assert report == {"empty": True, "reason": "llm_or_unified_missing"}
    # No LLM call attempted.
    assert llm.calls == []


def test_missing_llm_returns_empty_without_call() -> None:
    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=None,
    )
    assert insights == []
    assert report == {"empty": True, "reason": "llm_or_unified_missing"}


def test_blank_response_returns_empty_contract() -> None:
    # ScoutScanResult with empty `insights` list — schema-valid but useless.
    llm = _ScriptedLLM([_ScoutScanResult(insights=[])])
    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )
    assert insights == []
    assert report["empty"] is True
    assert report["reason"] == "no_insights"


def test_no_response_returns_empty_contract() -> None:
    # ``complete_structured`` returns None on every retry → wrapper returns
    # None → scout returns the empty contract.
    llm = _ScriptedLLM([None, None])
    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )
    assert insights == []
    assert report["empty"] is True
    assert report["reason"] == "no_response"


def test_persistent_exception_returns_empty_contract() -> None:
    # Two raises in a row exhausts the structured wrapper's retry budget;
    # it returns None internally, scout maps that to "no_response" rather
    # than a separate "exception" reason. We just confirm no propagation.
    err = RuntimeError("provider blew up")
    llm = _ScriptedLLM([err, err])
    insights, report = scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )
    assert insights == []
    assert report["empty"] is True
    assert report["reason"] == "no_response"


# -----------------------------------------------------------------------
# Manifest / surface label
# -----------------------------------------------------------------------

def test_ledger_records_value_scout_scan_surface() -> None:
    llm = _ScriptedLLM([
        _scan_result([
            {
                "headline": "Rent support is strong.",
                "reason": "rent_support_score sits at 0.74.",
                "supporting_fields": ["rental_option.rent_support_score"],
                "category": "rent_angle",
                "confidence": 0.8,
            },
        ]),
    ])

    scout_unified(
        unified=_unified_with_numbers(),
        intent=_intent("browse"),
        llm=llm,
    )

    records = get_llm_ledger().records
    scan_records = [r for r in records if r.surface == "value_scout.scan"]
    assert len(scan_records) == 1
    assert scan_records[0].status == "success"
    assert scan_records[0].schema_name == "_ScoutScanResult"


# -----------------------------------------------------------------------
# Prompt regression
# -----------------------------------------------------------------------

def test_system_prompt_pins_load_bearing_phrases() -> None:
    # If these phrases drift, the LLM's behavior shifts — pin them.
    assert "1-2 most non-obvious angles" in _SYSTEM_PROMPT
    assert "supporting_fields" in _SYSTEM_PROMPT
    assert "EVEN THOUGH they did not explicitly ask" in _SYSTEM_PROMPT
    assert "NUMERIC GROUNDING" in _SYSTEM_PROMPT
    assert "must round to a value present in the `unified`" in _SYSTEM_PROMPT
    # Per Open Design Decision #1: numeric confidence in [0, 1] with anchors.
    assert "confidence in [0, 1]" in _SYSTEM_PROMPT
    # Per Open Design Decision #2: at most 2 insights per turn for v1.
    assert "AT MOST 2 insights" in _SYSTEM_PROMPT

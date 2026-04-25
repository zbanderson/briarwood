"""Per-AnswerType chat-tier module selections for consolidated execution.

Cycle 2 of OUTPUT_QUALITY_HANDOFF_PLAN.md replaces the fragmented
per-tool execution plans (where each ``tools.py`` function calls
``execute_plan`` with its own narrow module set, producing the
``valuation``-runs-5x duplication and the 13-modules-never-fired
diagnostic captured in DECISIONS.md "Chat-tier fragmented execution"
2026-04-25) with one consolidated plan per chat turn keyed by the
router's ``AnswerType``.

The sets below are starting points to tune with traces; they are not
a fixed contract. ``LOOKUP`` and the non-property tiers (``SEARCH``,
``COMPARISON``, ``RESEARCH``, ``VISUALIZE``, ``MICRO_LOCATION``,
``CHITCHAT``) are intentionally absent — those tiers either don't run
a property cascade (LOOKUP is single-fact retrieval) or have their
own non-cascade flows. Callers should treat a missing key as "no
cascade for this answer type" and short-circuit accordingly.
"""

from __future__ import annotations

from briarwood.agent.router import AnswerType


_FULL_FIRST_READ: frozenset[str] = frozenset(
    {
        "valuation",
        "carry_cost",
        "risk_model",
        "confidence",
        "legal_confidence",
        "comparable_sales",
        "location_intelligence",
        "town_development_index",
        "market_value_history",
        "current_value",
        "hybrid_value",
        "scarcity_support",
        "income_support",
        "rental_option",
        "rent_stabilization",
        "hold_to_rent",
        "resale_scenario",
        "renovation_impact",
        "arv_model",
        "margin_sensitivity",
        "opportunity_cost",
        "strategy_classifier",
        "unit_income_offset",
    }
)


ANSWER_TYPE_MODULE_SETS: dict[AnswerType, frozenset[str]] = {
    AnswerType.BROWSE: _FULL_FIRST_READ,
    AnswerType.DECISION: _FULL_FIRST_READ,
    AnswerType.PROJECTION: frozenset(
        {
            "valuation",
            "carry_cost",
            "comparable_sales",
            "resale_scenario",
            "renovation_impact",
            "arv_model",
            "hold_to_rent",
            "town_development_index",
            "rental_option",
            "hybrid_value",
            "market_value_history",
            "margin_sensitivity",
        }
    ),
    AnswerType.RISK: frozenset(
        {
            "valuation",
            "risk_model",
            "legal_confidence",
            "confidence",
            "location_intelligence",
            "town_development_index",
        }
    ),
    AnswerType.EDGE: frozenset(
        {
            "valuation",
            "comparable_sales",
            "scarcity_support",
            "strategy_classifier",
            "town_development_index",
            "hybrid_value",
            "location_intelligence",
        }
    ),
    AnswerType.STRATEGY: frozenset(
        {
            "strategy_classifier",
            "hold_to_rent",
            "rental_option",
            "opportunity_cost",
            "carry_cost",
            "valuation",
            "hybrid_value",
        }
    ),
    AnswerType.RENT_LOOKUP: frozenset(
        {
            "rental_option",
            "rent_stabilization",
            "income_support",
            "scarcity_support",
            "hold_to_rent",
            "location_intelligence",
        }
    ),
}


def modules_for_answer_type(answer_type: AnswerType) -> frozenset[str]:
    """Return the module set for ``answer_type``, or an empty set if no cascade."""

    return ANSWER_TYPE_MODULE_SETS.get(answer_type, frozenset())


__all__ = ["ANSWER_TYPE_MODULE_SETS", "modules_for_answer_type"]

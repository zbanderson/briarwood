from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from briarwood.shadow_intelligence import (
    IntentSatisfactionReport,
    ShadowToolPlan,
    module_diff,
    run_intent_satisfaction_evaluator,
    run_shadow_tool_planner,
)


class ScriptedLLM:
    def __init__(self, responses: list[BaseModel | None]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        raise AssertionError("shadow intelligence should use structured output")

    def complete_structured(self, *, system, user, schema, model=None, max_tokens=600):
        self.calls.append({"schema": schema.__name__, "user": user})
        return self.responses.pop(0)


def test_shadow_planner_reads_registry_shape_and_returns_plan() -> None:
    llm = ScriptedLLM(
        [
            ShadowToolPlan(
                proposed_modules=["valuation", "carry_cost", "risk_model"],
                proposed_tools=["property_brief"],
                confidence=0.72,
                reason="decision needs carry and risk",
            )
        ]
    )

    plan = run_shadow_tool_planner(
        user_input="Should I buy this?",
        selected_modules=["valuation", "confidence"],
        parser_output={"intent_type": "buy_decision"},
        llm=llm,
        registry={},
    )

    assert plan is not None
    assert "carry_cost" in plan.proposed_modules
    assert llm.calls[0]["schema"] == "ShadowToolPlan"
    assert "tool_registry_markdown" in llm.calls[0]["user"]


def test_intent_satisfaction_schema_and_failure_handling() -> None:
    llm = ScriptedLLM(
        [
            IntentSatisfactionReport(
                intent_satisfied=False,
                confidence=0.61,
                missing_capabilities=["rent coverage"],
                suggested_modules=["rental_option"],
                suggested_follow_up="Ask for rent assumptions.",
                reason="No rent module ran.",
            )
        ]
    )

    report = run_intent_satisfaction_evaluator(
        user_input="Could this rent cover the payment?",
        selected_modules=["valuation"],
        parser_output={"intent_type": "buy_decision"},
        module_results={"outputs": {"valuation": {}}},
        unified_output={"recommendation": "Mixed"},
        llm=llm,
    )

    assert report is not None
    assert report.intent_satisfied is False
    assert report.suggested_modules == ["rental_option"]


def test_module_diff_is_shadow_only_telemetry() -> None:
    assert module_diff(
        selected_modules=["valuation", "confidence"],
        proposed_modules=["valuation", "risk_model"],
    ) == {
        "missing_from_deterministic": ["risk_model"],
        "extra_deterministic": ["confidence"],
    }

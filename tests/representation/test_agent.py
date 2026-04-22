"""Tests for the Representation Agent.

Covers the deterministic fallback, a happy-path LLM selection with a
mocked structured-output client, and the contract guarantees:

- chart_ids outside the registry are stripped + flagged
- claim_types that the chart does not support are flagged
- claims without supporting evidence are flagged (no fabrication)
- claims whose required_inputs are not satisfied by the named source_view
  are flagged
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from briarwood.representation import charts
from briarwood.representation.agent import (
    ClaimType,
    RepresentationAgent,
    RepresentationPlan,
    RepresentationSelection,
)
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionStance,
    DecisionType,
    UnifiedIntelligenceOutput,
)


def _unified(**overrides: Any) -> UnifiedIntelligenceOutput:
    base = dict(
        recommendation="Review setup carefully before offering.",
        decision=DecisionType.MIXED,
        best_path="decision",
        key_value_drivers=["Strong town demand"],
        key_risks=["Thin comp set"],
        confidence=0.62,
        analysis_depth_used=AnalysisDepth.DECISION,
        decision_stance=DecisionStance.BUY_IF_PRICE_IMPROVES,
        primary_value_source="comps",
        value_position={
            "ask_price": 950_000,
            "fair_value_base": 870_000,
            "ask_premium_pct": 0.092,
        },
        what_must_be_true=["Comp set holds"],
        trust_flags=[],
        why_this_stance=["Premium to fair value"],
        what_changes_my_view=["Price cut below 900k"],
    )
    base.update(overrides)
    return UnifiedIntelligenceOutput(**base)


def _views(*, rich: bool = True) -> dict[str, dict[str, Any] | None]:
    if not rich:
        return {
            "last_decision_view": {
                "ask_price": 950_000,
                "fair_value_base": 870_000,
                "decision_stance": DecisionStance.PASS.value,
                "key_risks": ["Thin comp set"],
            },
        }
    return {
        "last_decision_view": {
            "ask_price": 950_000,
            "fair_value_base": 870_000,
            "decision_stance": DecisionStance.BUY_IF_PRICE_IMPROVES.value,
            "key_risks": ["Thin comp set"],
            "trust_flags": [],
        },
        "last_value_thesis_view": {
            "ask_price": 950_000,
            "fair_value_base": 870_000,
            "premium_discount_pct": 0.092,
            "key_value_drivers": ["Strong town demand", "Coastal proximity"],
            "comps": [
                {"address": "100 A St", "ask_price": 880_000},
                {"address": "200 B St", "ask_price": 910_000},
            ],
        },
        "last_market_support_view": {
            "comps": [
                {"address": "300 C St", "ask_price": 905_000},
                {"address": "400 D St", "ask_price": 895_000},
            ],
        },
        "last_risk_view": {
            "risk_flags": ["flood_zone", "thin_comp_set"],
            "trust_flags": ["incomplete_carry_inputs"],
            "total_penalty": 0.18,
            "ask_price": 950_000,
        },
        "last_strategy_view": {"best_path": "buy_and_hold"},
        "last_rent_outlook_view": {
            "burn_chart_payload": {
                "series": [
                    {
                        "year": 0,
                        "rent_base": 3500,
                        "rent_bull": 3800,
                        "rent_bear": 3200,
                        "monthly_obligation": 4200,
                    },
                    {
                        "year": 3,
                        "rent_base": 3900,
                        "rent_bull": 4300,
                        "rent_bear": 3400,
                        "monthly_obligation": 4300,
                    },
                ],
            },
            "ramp_chart_payload": {
                "series": [
                    {"year": 0, "net_0": -700, "net_3": -400, "net_5": 100},
                    {"year": 3, "net_0": -300, "net_3": 0, "net_5": 400},
                ],
                "current_rent": 3500,
                "monthly_obligation": 4200,
                "today_cash_flow": -700,
                "break_even_years": {"0": None, "3": 3, "5": 2},
            },
        },
        "last_projection_view": {
            "ask_price": 950_000,
            "basis_label": "all-in basis",
            "bull_case_value": 1_200_000,
            "base_case_value": 1_050_000,
            "bear_case_value": 900_000,
        },
    }


# ---------------------------------------------------------------- fallback


def test_deterministic_fallback_covers_populated_views() -> None:
    agent = RepresentationAgent(llm_client=None)
    plan = agent.plan(
        _unified(),
        user_question="Should I buy this?",
        module_views=_views(),
    )
    chart_ids = {s.chart_id for s in plan.selections if s.chart_id}
    # Rich views should surface at least the price-position, comp, scenario,
    # risk, rent-coverage, and rent-ramp claims.
    assert "value_opportunity" in chart_ids
    assert "cma_positioning" in chart_ids
    assert "scenario_fan" in chart_ids
    assert "risk_bar" in chart_ids
    assert "rent_burn" in chart_ids
    assert "rent_ramp" in chart_ids


def test_fallback_with_no_views_produces_flagged_or_empty() -> None:
    agent = RepresentationAgent(llm_client=None)
    plan = agent.plan(
        _unified(what_changes_my_view=["Need fresh comps"]),
        user_question="What about this one?",
        module_views={},
    )
    for s in plan.selections:
        assert s.chart_id is None or s.flagged


def test_fallback_does_not_fabricate_evidence() -> None:
    """Every unflagged selection must cite at least one evidence string."""
    agent = RepresentationAgent(llm_client=None)
    plan = agent.plan(
        _unified(),
        user_question="",
        module_views=_views(),
    )
    for s in plan.selections:
        if not s.flagged:
            assert s.supporting_evidence, s.claim


# ---------------------------------------------------------------- LLM path


class _ScriptedLLM:
    """Fake LLMClient that returns a pre-baked structured response."""

    def __init__(self, response: BaseModel | None) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        raise AssertionError("representation agent must use complete_structured")

    def complete_structured(
        self, *, system, user, schema, model=None, max_tokens=600
    ):
        self.calls.append(
            {"schema": schema.__name__, "model": model, "max_tokens": max_tokens}
        )
        return self._response


def test_llm_happy_path_emits_registered_chart() -> None:
    response = RepresentationPlan(
        selections=[
            RepresentationSelection(
                claim="Subject is asking 9.2% above fair value.",
                claim_type=ClaimType.PRICE_POSITION,
                supporting_evidence=[
                    "last_decision_view.ask_price=950000",
                    "last_decision_view.fair_value_base=870000",
                ],
                chart_id="value_opportunity",
                source_view="last_value_thesis_view",
            ),
        ]
    )
    llm = _ScriptedLLM(response)
    agent = RepresentationAgent(llm_client=llm)
    plan = agent.plan(
        _unified(),
        user_question="Should I buy?",
        module_views=_views(),
    )
    assert llm.calls, "LLM should have been called"
    assert plan.selections[0].chart_id == "value_opportunity"
    assert not plan.selections[0].flagged


def test_llm_unknown_chart_id_is_stripped_and_flagged() -> None:
    response = RepresentationPlan(
        selections=[
            RepresentationSelection(
                claim="A claim",
                claim_type=ClaimType.PRICE_POSITION,
                supporting_evidence=["last_decision_view.ask_price=1"],
                chart_id="does_not_exist",
                source_view="last_decision_view",
            ),
        ]
    )
    agent = RepresentationAgent(llm_client=_ScriptedLLM(response))
    plan = agent.plan(_unified(), user_question="", module_views=_views())
    sel = plan.selections[0]
    assert sel.chart_id is None
    assert sel.flagged is True
    assert "does_not_exist" in (sel.flag_reason or "")


def test_llm_missing_evidence_is_flagged() -> None:
    response = RepresentationPlan(
        selections=[
            RepresentationSelection(
                claim="Made-up claim without citation",
                claim_type=ClaimType.PRICE_POSITION,
                supporting_evidence=[],
                chart_id="value_opportunity",
                source_view="last_value_thesis_view",
            ),
        ]
    )
    agent = RepresentationAgent(llm_client=_ScriptedLLM(response))
    plan = agent.plan(_unified(), user_question="", module_views=_views())
    assert plan.selections[0].flagged is True
    assert "no supporting evidence" in (plan.selections[0].flag_reason or "")


def test_llm_claim_type_mismatch_is_flagged() -> None:
    """scenario_fan does not support price_position. Post-processor must
    strip the chart_id and flag the mismatch."""
    response = RepresentationPlan(
        selections=[
            RepresentationSelection(
                claim="Some claim",
                claim_type=ClaimType.PRICE_POSITION,
                supporting_evidence=["last_decision_view.ask_price=1"],
                chart_id="scenario_fan",
                source_view="last_projection_view",
            ),
        ]
    )
    agent = RepresentationAgent(llm_client=_ScriptedLLM(response))
    plan = agent.plan(_unified(), user_question="", module_views=_views())
    sel = plan.selections[0]
    assert sel.chart_id is None
    assert sel.flagged is True


def test_llm_missing_required_inputs_is_flagged() -> None:
    """value_opportunity requires ask_price + fair_value_base. Point it at a
    view that does not carry them — must flag."""
    response = RepresentationPlan(
        selections=[
            RepresentationSelection(
                claim="Asking a premium",
                claim_type=ClaimType.PRICE_POSITION,
                supporting_evidence=["last_strategy_view.best_path"],
                chart_id="value_opportunity",
                source_view="last_strategy_view",
            ),
        ]
    )
    agent = RepresentationAgent(llm_client=_ScriptedLLM(response))
    plan = agent.plan(_unified(), user_question="", module_views=_views())
    sel = plan.selections[0]
    assert sel.chart_id is None
    assert sel.flagged is True
    assert "required inputs" in (sel.flag_reason or "")


def test_llm_failure_falls_back_to_deterministic() -> None:
    agent = RepresentationAgent(llm_client=_ScriptedLLM(None))
    plan = agent.plan(_unified(), user_question="", module_views=_views())
    assert plan.selections, "fallback must still produce selections"
    # Deterministic fallback cites real views, so at least one chart is rendered.
    assert any(s.chart_id for s in plan.selections)


def test_llm_empty_plan_falls_back_to_deterministic() -> None:
    agent = RepresentationAgent(
        llm_client=_ScriptedLLM(RepresentationPlan(selections=[]))
    )
    plan = agent.plan(_unified(), user_question="", module_views=_views())
    assert plan.selections


# ---------------------------------------------------------------- contract


def test_contract_every_emitted_chart_supports_its_claim_type() -> None:
    """Contract: the agent never hands back a selection whose chart does not
    declare the emitted claim_type. Deterministic path is audited here; the
    LLM path inherits the same guarantee via _postprocess."""
    agent = RepresentationAgent(llm_client=None)
    plan = agent.plan(_unified(), user_question="", module_views=_views())
    for s in plan.selections:
        if s.chart_id is None:
            continue
        spec = charts.get_spec(s.chart_id)
        assert spec is not None
        assert s.claim_type.value in spec.claim_types, (
            f"chart {s.chart_id} cannot claim {s.claim_type.value}"
        )


def test_contract_rendered_events_have_matching_kinds() -> None:
    agent = RepresentationAgent(llm_client=None)
    module_views = _views()
    plan = agent.plan(_unified(), user_question="", module_views=module_views)
    rendered = agent.render_events(
        plan,
        module_views,
        market_view=module_views.get("last_market_support_view"),
    )
    rendered_kinds = [ev.get("kind") for ev in rendered]
    assert rendered_kinds, "render_events must yield at least one chart"
    assert all(k in {s.chart_id for s in plan.selections} for k in rendered_kinds)


def test_contract_flagged_selections_are_not_rendered() -> None:
    response = RepresentationPlan(
        selections=[
            RepresentationSelection(
                claim="Valid chart",
                claim_type=ClaimType.PRICE_POSITION,
                supporting_evidence=["last_value_thesis_view.ask_price=950000"],
                chart_id="value_opportunity",
                source_view="last_value_thesis_view",
            ),
            RepresentationSelection(
                claim="Flagged claim",
                claim_type=ClaimType.PRICE_POSITION,
                supporting_evidence=[],
                chart_id="value_opportunity",
                source_view="last_value_thesis_view",
            ),
        ]
    )
    agent = RepresentationAgent(llm_client=_ScriptedLLM(response))
    module_views = _views()
    plan = agent.plan(_unified(), user_question="", module_views=module_views)
    rendered = agent.render_events(plan, module_views)
    # Exactly one render: the flagged entry with empty evidence must be skipped.
    assert len(rendered) == 1

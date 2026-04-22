"""Print Representation Agent selections for 2-3 synthetic property scenarios.

Intentionally lightweight: we do not run the full routed pipeline here —
that requires live module execution and seeded property data. Instead we
construct plausible `UnifiedIntelligenceOutput` + `module_views` payloads
anchored on `data/sample_property.json` so the user can eyeball what the
agent picks against known inputs before wiring the decision stream.

Runs with the deterministic fallback path by default. Set
`BRIARWOOD_REPRESENTATION_USE_LLM=1` to force the LLM path if a client is
configured.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from briarwood.agent.llm import default_client
from briarwood.representation.agent import RepresentationAgent
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionStance,
    DecisionType,
    UnifiedIntelligenceOutput,
)


SAMPLE_PATH = Path("data/sample_property.json")


def _unified(**overrides: Any) -> UnifiedIntelligenceOutput:
    base: dict[str, Any] = dict(
        recommendation="See decision_stance + supporting drivers.",
        decision=DecisionType.MIXED,
        best_path="decision",
        key_value_drivers=[],
        key_risks=[],
        confidence=0.6,
        analysis_depth_used=AnalysisDepth.DECISION,
        decision_stance=DecisionStance.CONDITIONAL,
        primary_value_source="unknown",
        value_position={},
        what_must_be_true=[],
        trust_flags=[],
        trust_summary={},
        contradiction_count=0,
        blocked_thesis_warnings=[],
        why_this_stance=[],
        what_changes_my_view=[],
    )
    base.update(overrides)
    return UnifiedIntelligenceOutput(**base)


def scenario_strong_buy(sample: dict[str, Any]) -> tuple[str, UnifiedIntelligenceOutput, dict[str, Any]]:
    """Priced below fair with clean comps + positive rent coverage."""
    ask = 815_000
    fair = 870_000
    unified = _unified(
        recommendation="Price sits below comp-supported fair value.",
        decision=DecisionType.BUY,
        best_path="buy_and_hold",
        key_value_drivers=["Coastal proximity", "Below comp-median ask"],
        key_risks=["Thin comp set"],
        confidence=0.74,
        decision_stance=DecisionStance.STRONG_BUY,
        primary_value_source="comps",
        value_position={"ask_price": ask, "fair_value_base": fair, "ask_premium_pct": -0.063},
        what_must_be_true=["Comp set stays intact"],
        why_this_stance=["7% ask discount to fair value"],
        what_changes_my_view=["Major flood disclosure surfaces"],
    )
    module_views: dict[str, Any] = {
        "last_decision_view": {
            "address": sample["address"],
            "town": sample["town"],
            "state": sample["state"],
            "ask_price": ask,
            "fair_value_base": fair,
            "value_low": 830_000,
            "value_high": 920_000,
            "decision_stance": DecisionStance.STRONG_BUY.value,
            "primary_value_source": "comps",
            "key_risks": ["Thin comp set"],
            "trust_flags": [],
        },
        "last_value_thesis_view": {
            "ask_price": ask,
            "fair_value_base": fair,
            "premium_discount_pct": -0.063,
            "key_value_drivers": ["Coastal proximity", "Below comp-median ask"],
            "comps": [
                {"address": "100 Ocean Ave", "ask_price": 860_000, "selected_by": "valuation", "feeds_fair_value": True},
                {"address": "205 Monroe Pl", "ask_price": 895_000, "selected_by": "valuation", "feeds_fair_value": True},
                {"address": "312 5th Ave", "ask_price": 870_000, "selected_by": "valuation", "feeds_fair_value": True},
            ],
        },
        "last_market_support_view": {
            "comps": [
                {"address": "410 2nd Ave", "ask_price": 905_000, "selected_by": "live_market"},
                {"address": "512 3rd Ave", "ask_price": 888_000, "selected_by": "live_market"},
            ],
        },
        "last_risk_view": {
            "ask_price": ask,
            "bear_value": 780_000,
            "stress_value": 740_000,
            "risk_flags": ["thin_comp_set"],
            "trust_flags": [],
            "total_penalty": 0.08,
        },
        "last_rent_outlook_view": {
            "burn_chart_payload": {
                "series": [
                    {"year": 0, "rent_base": 3500, "rent_bull": 3800, "rent_bear": 3200, "monthly_obligation": 3900},
                    {"year": 3, "rent_base": 3900, "rent_bull": 4300, "rent_bear": 3450, "monthly_obligation": 4000},
                    {"year": 5, "rent_base": 4250, "rent_bull": 4800, "rent_bear": 3650, "monthly_obligation": 4100},
                ],
            },
            "ramp_chart_payload": {
                "series": [
                    {"year": 0, "net_0": -400, "net_3": -100, "net_5": 200},
                    {"year": 3, "net_0": -100, "net_3": 200, "net_5": 600},
                ],
                "current_rent": 3500,
                "monthly_obligation": 3900,
                "today_cash_flow": -400,
                "break_even_years": {"0": None, "3": 2, "5": 2},
            },
        },
        "last_projection_view": {
            "ask_price": ask,
            "basis_label": "all-in basis",
            "bull_case_value": 1_050_000,
            "base_case_value": 930_000,
            "bear_case_value": 810_000,
        },
    }
    return "Strong buy — priced below fair, clean comps, rent ramps positive", unified, module_views


def scenario_pass_fragile(sample: dict[str, Any]) -> tuple[str, UnifiedIntelligenceOutput, dict[str, Any]]:
    """Ask premium, trust gate near-trip, flood + carry flags."""
    ask = sample["purchase_price"]  # 940000 — priced high in our sample
    fair = 820_000
    unified = _unified(
        recommendation="Priced above comps with multiple trust flags.",
        decision=DecisionType.PASS,
        best_path="pass",
        key_value_drivers=[],
        key_risks=["Flood exposure", "Thin comp set", "Incomplete carry inputs"],
        confidence=0.38,
        decision_stance=DecisionStance.PASS_UNLESS_CHANGES,
        primary_value_source="comps",
        value_position={"ask_price": ask, "fair_value_base": fair, "ask_premium_pct": 0.146},
        what_must_be_true=["Price drops below 870k", "Flood disclosure is clarified"],
        trust_flags=["flood_zone", "incomplete_carry_inputs"],
        why_this_stance=["14% ask premium", "Flood exposure unresolved"],
        what_changes_my_view=["Seller drops ask below 870k"],
        contradiction_count=1,
    )
    module_views: dict[str, Any] = {
        "last_decision_view": {
            "address": sample["address"],
            "town": sample["town"],
            "state": sample["state"],
            "ask_price": ask,
            "fair_value_base": fair,
            "decision_stance": DecisionStance.PASS_UNLESS_CHANGES.value,
            "primary_value_source": "comps",
            "key_risks": ["Flood exposure", "Thin comp set"],
            "trust_flags": ["flood_zone", "incomplete_carry_inputs"],
            "what_changes_my_view": ["Seller drops ask below 870k"],
        },
        "last_value_thesis_view": {
            "ask_price": ask,
            "fair_value_base": fair,
            "premium_discount_pct": 0.146,
            "key_value_drivers": ["Lot size advantage"],
            "comps": [
                {"address": "808 Main St", "ask_price": 810_000, "feeds_fair_value": True},
                {"address": "914 Summer Ave", "ask_price": 835_000, "feeds_fair_value": True},
            ],
        },
        "last_risk_view": {
            "ask_price": ask,
            "bear_value": 740_000,
            "stress_value": 680_000,
            "risk_flags": ["flood_zone", "thin_comp_set"],
            "trust_flags": ["incomplete_carry_inputs"],
            "total_penalty": 0.22,
        },
        "last_projection_view": {
            "ask_price": ask,
            "basis_label": "ask",
            "bull_case_value": 950_000,
            "base_case_value": 870_000,
            "bear_case_value": 780_000,
            "stress_case_value": 720_000,
        },
    }
    return "Pass — ask premium with flood + carry trust flags", unified, module_views


def scenario_sparse(sample: dict[str, Any]) -> tuple[str, UnifiedIntelligenceOutput, dict[str, Any]]:
    """Only price + stance — no comps, no scenarios, no rent outlook.

    Exercises the agent's no-evidence flagging path."""
    ask = sample["purchase_price"]
    fair = 920_000
    unified = _unified(
        recommendation="Need more data before taking a stance.",
        decision=DecisionType.MIXED,
        best_path="review",
        confidence=0.42,
        decision_stance=DecisionStance.CONDITIONAL,
        primary_value_source="unknown",
        value_position={"ask_price": ask, "fair_value_base": fair, "ask_premium_pct": 0.021},
        what_changes_my_view=["Comp set lands with enough coverage to price"],
    )
    module_views: dict[str, Any] = {
        "last_decision_view": {
            "address": sample["address"],
            "ask_price": ask,
            "fair_value_base": fair,
            "decision_stance": DecisionStance.CONDITIONAL.value,
            "primary_value_source": "unknown",
            "trust_flags": ["thin_comp_set"],
            "what_changes_my_view": ["Comp set lands with enough coverage to price"],
        },
    }
    return "Sparse — price only, no comps / scenarios / rent", unified, module_views


def _print_plan(label: str, plan) -> None:
    print("=" * 72)
    print(label)
    print("-" * 72)
    for i, sel in enumerate(plan.selections, 1):
        flag = " [FLAGGED]" if sel.flagged else ""
        print(f"{i:>2}. ({sel.claim_type.value}) {sel.claim}{flag}")
        if sel.chart_id:
            print(f"    chart_id:       {sel.chart_id} (source={sel.source_view})")
        else:
            print(f"    chart_id:       —")
        for evidence in sel.supporting_evidence:
            print(f"    evidence:       {evidence}")
        if sel.flag_reason:
            print(f"    flag_reason:    {sel.flag_reason}")
    print()


def main() -> None:
    sample = json.loads(SAMPLE_PATH.read_text())

    llm = None
    if os.environ.get("BRIARWOOD_REPRESENTATION_USE_LLM") == "1":
        llm = default_client()
        print(f"(LLM client: {type(llm).__name__ if llm else 'None — falling back'})\n")
    else:
        print("(deterministic fallback; set BRIARWOOD_REPRESENTATION_USE_LLM=1 to force LLM)\n")

    agent = RepresentationAgent(llm_client=llm)
    for builder in (scenario_strong_buy, scenario_pass_fragile, scenario_sparse):
        label, unified, views = builder(sample)
        plan = agent.plan(
            unified,
            user_question="Should I buy this?",
            module_views=views,
        )
        _print_plan(label, plan)


if __name__ == "__main__":
    main()

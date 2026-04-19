"""Bridge: scenario × risk.

Spec §4B: a deal whose thesis requires flipping, heavy renovation, or
aggressive rent growth is *execution-dependent*. This bridge reads the
resale-scenario / ARV / margin-sensitivity outputs alongside the risk model
and emits a ``fragility_score`` plus a concrete ``what_must_be_true`` list
the synthesizer will surface.
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _confidence,
    _metrics,
    _payload,
    _score,
)

NAME = "scenario_x_risk"


def run(outputs: ModuleOutputs) -> BridgeRecord:
    scenario = (
        _payload(outputs, "resale_scenario")
        or _payload(outputs, "arv_model")
        or _payload(outputs, "margin_sensitivity")
    )
    risk = _payload(outputs, "risk_model")

    if scenario is None:
        return BridgeRecord(name=NAME, fired=False, reasoning=["no scenario module output"])

    scenario_metrics = _metrics(scenario)
    risk_metrics = _metrics(risk)

    # Fragility = how much execution risk the thesis carries.
    base_fragility = 0.3
    must_be_true: list[str] = []
    reasoning: list[str] = []

    # Scenario's own confidence informs baseline fragility.
    s_conf = _confidence(scenario)
    if s_conf is not None and s_conf < 0.5:
        base_fragility += 0.2
        reasoning.append(f"Scenario confidence low ({s_conf:.2f}) — thesis is already thinly supported.")

    # If the scenario leans on appreciation > a reasonable floor, call it out.
    implied_appreciation = scenario_metrics.get("implied_appreciation_pct") or scenario_metrics.get(
        "annual_appreciation_pct"
    )
    if isinstance(implied_appreciation, (int, float)) and implied_appreciation > 0.05:
        base_fragility += 0.15
        must_be_true.append(
            f"Market appreciation sustains at ≥ {implied_appreciation*100:.1f}% annually."
        )
        reasoning.append("Thesis assumes above-trend appreciation.")

    # Renovation-dependent.
    reno_budget = scenario_metrics.get("renovation_budget") or scenario_metrics.get("capex_basis_used")
    if isinstance(reno_budget, (int, float)) and reno_budget > 50_000:
        base_fragility += 0.1
        must_be_true.append(
            f"Renovation completes within ~${reno_budget:,.0f} budget and projected timeline."
        )
        reasoning.append("Thesis requires material renovation execution.")

    # Risk flags amplify fragility linearly.
    risk_count = int(risk_metrics.get("risk_count") or 0)
    if risk_count:
        base_fragility += 0.05 * risk_count
        must_be_true.append(f"None of the {risk_count} flagged risks materialize materially.")

    fragility = round(min(base_fragility, 1.0), 3)
    what_must_go_right_score = round(max(0.0, 1.0 - fragility), 3)

    if not reasoning:
        reasoning.append("Scenario appears low-execution-risk given current inputs.")

    return BridgeRecord(
        name=NAME,
        inputs_read=["resale_scenario/arv_model/margin_sensitivity", "risk_model"],
        adjustments={
            "fragility_score": fragility,
            "what_must_go_right_score": what_must_go_right_score,
            "what_must_be_true": must_be_true,
            "scenario_score": _score(scenario),
        },
        reasoning=reasoning,
        confidence=1.0 - fragility,
        fired=True,
    )


__all__ = ["NAME", "run"]

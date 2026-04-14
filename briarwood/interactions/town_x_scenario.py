"""Bridge: town × scenario.

Spec §4B: town-level market regime modulates appreciation & rent-growth
realism. A scenario that bakes in 6% annual appreciation in a flat/soft town
is not the same as the same assumption in a scarcity-driven town.

This bridge flags realism gaps and emits an ``appreciation_realism`` label.
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _metrics,
    _payload,
)

NAME = "town_x_scenario"


def run(outputs: ModuleOutputs) -> BridgeRecord:
    scenario = (
        _payload(outputs, "resale_scenario")
        or _payload(outputs, "arv_model")
    )
    town = _payload(outputs, "town_county_outlook") or _payload(outputs, "valuation")

    if scenario is None or town is None:
        return BridgeRecord(
            name=NAME, fired=False, reasoning=["need both scenario and town context"]
        )

    s_metrics = _metrics(scenario)
    t_metrics = _metrics(town)

    implied_app = s_metrics.get("implied_appreciation_pct") or s_metrics.get(
        "annual_appreciation_pct"
    )
    town_score = t_metrics.get("town_county_score") or t_metrics.get("scarcity_support_score")

    reasoning: list[str] = []
    realism = "unknown"

    if isinstance(implied_app, (int, float)) and isinstance(town_score, (int, float)):
        # Rough realism check: strong towns (score ≥ 70) can support 4-6%;
        # weak towns (≤ 35) should cap at ~2%.
        if town_score >= 70 and implied_app <= 0.06:
            realism = "realistic"
            reasoning.append(
                f"Scenario appreciation {implied_app*100:.1f}% is consistent with town strength ({town_score:.0f})."
            )
        elif town_score <= 35 and implied_app > 0.03:
            realism = "optimistic"
            reasoning.append(
                f"Scenario assumes {implied_app*100:.1f}% appreciation in a soft town (score {town_score:.0f})."
            )
        elif implied_app > 0.08:
            realism = "aggressive"
            reasoning.append(
                f"Scenario appreciation {implied_app*100:.1f}% is aggressive in any regime."
            )
        else:
            realism = "reasonable"
            reasoning.append("Appreciation assumption within typical bounds for the town regime.")
    else:
        reasoning.append("Missing appreciation signal and/or town score — cannot cross-check.")

    return BridgeRecord(
        name=NAME,
        inputs_read=["resale_scenario/arv_model", "town_county_outlook/valuation"],
        adjustments={
            "appreciation_realism": realism,
            "implied_appreciation_pct": implied_app,
            "town_score": town_score,
        },
        reasoning=reasoning,
        confidence=0.6,
        fired=realism != "unknown",
    )


__all__ = ["NAME", "run"]

"""Bridge: classify the property's primary value source.

Spec §4B/§9: every property ultimately derives its value from *one* of:

- ``current_value``    — fair comp-supported market price
- ``income``           — cash-flow / rental support
- ``repositioning``    — value-add / reno upside
- ``optionality``      — ADU, subdivide, redevelop potential
- ``scarcity``         — irreplaceable location/town factors

Synthesis uses this classification to prioritize *which* story to tell first
and which trust flags to demand. The classifier is deterministic: it reads
the strategy classifier (Phase 3), valuation metrics, and scenario outputs,
and picks the source whose signals dominate.
"""

from __future__ import annotations

import logging

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _metrics,
    _payload,
)

_logger = logging.getLogger(__name__)

NAME = "primary_value_source"


def run(outputs: ModuleOutputs) -> BridgeRecord:
    strategy_payload = _payload(outputs, "strategy_classifier")
    valuation = _payload(outputs, "valuation")
    scenario = _payload(outputs, "resale_scenario") or _payload(outputs, "arv_model")
    carry = _payload(outputs, "carry_cost")

    reasoning: list[str] = []
    candidates: list[tuple[str, float, str]] = []  # (label, weight, reason)

    # 1. Strategy classifier gives a strong prior.
    strategy = None
    if strategy_payload is not None:
        strategy = (strategy_payload.get("data") or {}).get("strategy")
    strategy_map = {
        "owner_occ_sfh": ("current_value", 0.6, "Owner-occ SFH → value vs comps dominates."),
        "owner_occ_duplex": ("income", 0.7, "Owner-occ multi-unit → rental offset is the thesis."),
        "owner_occ_with_adu": ("optionality", 0.65, "ADU present → optionality dominates."),
        "pure_rental": ("income", 0.8, "Declared investment → income is the thesis."),
        "value_add_sfh": ("repositioning", 0.75, "Condition/capex signals → reposition play."),
        "redevelopment_play": ("optionality", 0.85, "Teardown/land signals → optionality."),
        "scarcity_hold": ("scarcity", 0.8, "Town scarcity dominates the thesis."),
    }
    strategy_fired = strategy in strategy_map
    _logger.debug(
        "primary_value_source.strategy_check fired=%s strategy=%r",
        strategy_fired,
        strategy,
    )
    if strategy_fired:
        label, weight, reason = strategy_map[strategy]
        candidates.append((label, weight, reason))
        reasoning.append(reason)

    # 2. Valuation signals: heavy scenario upside tilts to repositioning.
    val_metrics = _metrics(valuation)
    mispricing_pct = val_metrics.get("mispricing_pct")
    mispricing_fired = (
        isinstance(mispricing_pct, (int, float)) and mispricing_pct > 0.20
    )
    _logger.debug(
        "primary_value_source.valuation_mispricing_check fired=%s mispricing_pct=%r",
        mispricing_fired,
        mispricing_pct,
    )
    if mispricing_fired:
        candidates.append(
            ("current_value", 0.5, f"Comp-based value is {mispricing_pct*100:.0f}% above ask — price vs comps is the story.")
        )

    # 3. Carry-offset-supported deals favor income.
    ratio = None
    if carry is not None:
        rent_x_cost = outputs.get("__bridge__rent_x_cost")  # optional: same-run bridge result
        if isinstance(rent_x_cost, dict):
            ratio = (rent_x_cost.get("adjustments") or {}).get("carry_offset_ratio")
    carry_fired = isinstance(ratio, (int, float)) and ratio >= 1.0
    _logger.debug(
        "primary_value_source.carry_offset_check fired=%s carry_present=%s ratio=%r",
        carry_fired,
        carry is not None,
        ratio,
    )
    if carry_fired:
        candidates.append(("income", 0.6, f"Carry-offset ratio {ratio:.2f} — cash flow supports."))

    # 4. Scenario-heavy deals → repositioning.
    s_metrics = _metrics(scenario)
    scenario_fired = bool(
        s_metrics.get("renovation_budget") or s_metrics.get("capex_basis_used")
    )
    _logger.debug(
        "primary_value_source.scenario_check fired=%s renovation_budget=%r capex_basis_used=%r",
        scenario_fired,
        s_metrics.get("renovation_budget"),
        s_metrics.get("capex_basis_used"),
    )
    if scenario_fired:
        candidates.append(("repositioning", 0.55, "Scenario module carries a renovation budget."))

    if not candidates:
        _logger.info(
            "primary_value_source.unknown strategy=%r mispricing_pct=%r carry_present=%s "
            "carry_ratio=%r renovation_budget=%r capex_basis_used=%r",
            strategy,
            mispricing_pct,
            carry is not None,
            ratio,
            s_metrics.get("renovation_budget"),
            s_metrics.get("capex_basis_used"),
        )
        return BridgeRecord(
            name=NAME,
            fired=False,
            reasoning=["Not enough signal to classify primary value source."],
            adjustments={"primary_value_source": "unknown"},
        )

    # Pick the highest-weighted candidate.
    candidates.sort(key=lambda c: c[1], reverse=True)
    label, weight, _ = candidates[0]

    return BridgeRecord(
        name=NAME,
        inputs_read=["strategy_classifier", "valuation", "carry_cost", "resale_scenario/arv_model"],
        adjustments={
            "primary_value_source": label,
            "runner_up": candidates[1][0] if len(candidates) > 1 else None,
            "all_candidates": [{"source": c[0], "weight": c[1], "reason": c[2]} for c in candidates],
        },
        reasoning=reasoning or ["Classified from weighted signals."],
        confidence=weight,
        fired=True,
    )


__all__ = ["NAME", "run"]

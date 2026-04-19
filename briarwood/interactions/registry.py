"""Registry + runner for the Phase 4 interaction bridges.

Bridges are ordered so that downstream bridges can read prior bridge output
if needed (primary_value_source consults rent_x_cost via the
``__bridge__rent_x_cost`` convention in ``ModuleOutputs``).
"""

from __future__ import annotations

from collections.abc import Callable

from briarwood.interactions import (
    conflict_detector,
    opportunity_x_value,
    primary_value_source,
    rent_x_cost,
    rent_x_risk,
    scenario_x_risk,
    town_x_scenario,
    valuation_x_risk,
    valuation_x_town,
)
from briarwood.interactions.bridge import BridgeRecord, InteractionTrace, ModuleOutputs

BridgeFn = Callable[[ModuleOutputs], BridgeRecord]

# Order matters: primary_value_source reads rent_x_cost's adjustment,
# so rent_x_cost must run first.
BRIDGES: list[tuple[str, BridgeFn]] = [
    (valuation_x_town.NAME, valuation_x_town.run),
    (valuation_x_risk.NAME, valuation_x_risk.run),
    (rent_x_cost.NAME, rent_x_cost.run),
    (rent_x_risk.NAME, rent_x_risk.run),
    (scenario_x_risk.NAME, scenario_x_risk.run),
    (town_x_scenario.NAME, town_x_scenario.run),
    (primary_value_source.NAME, primary_value_source.run),
    (opportunity_x_value.NAME, opportunity_x_value.run),
    (conflict_detector.NAME, conflict_detector.run),
]


def run_all_bridges(module_outputs: ModuleOutputs) -> InteractionTrace:
    """Run every bridge against the module outputs and return a trace.

    Each bridge's record is also stuffed back into ``module_outputs`` under
    a ``__bridge__<name>`` key so later bridges can read prior adjustments
    without coupling through globals.
    """

    trace = InteractionTrace()
    working: dict[str, object] = dict(module_outputs)  # type: ignore[assignment]

    for name, fn in BRIDGES:
        try:
            record = fn(working)  # type: ignore[arg-type]
        except Exception as exc:  # defensive: a bridge bug must not kill the run
            record = BridgeRecord(
                name=name,
                fired=False,
                reasoning=[f"Bridge raised {type(exc).__name__}: {exc}"],
            )
        trace.add(record)
        working[f"__bridge__{name}"] = record.to_dict()

    return trace


__all__ = ["BRIDGES", "run_all_bridges"]

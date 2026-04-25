"""Chart registry for the Representation Agent.

Audit 1.4 / 1.7: the chat surface has six native chart kinds defined across
`api/events.py`, `api/pipeline_adapter.py` (`_native_*_chart`), and
`web/src/lib/chat/events.ts`. They were previously emitted unconditionally
whenever the right session view existed. The registry formalizes them so
the Representation Agent can reason about which chart best backs a given
verdict claim instead of picking by view-presence alone.

Shape of the registry:

- `ChartSpec` — Pydantic descriptor (id, name, description,
  required_inputs, claim_types). This is what the Agent reads.
- `render(chart_id, inputs)` — returns the exact SSE event payload that
  `api/events.chart()` would produce. Renderers are thin wrappers around
  the existing `_native_*_chart` helpers — we do not reimplement chart
  construction. Lazy imports keep us out of import-cycle territory with
  `api/pipeline_adapter.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field


class ChartSpec(BaseModel):
    """Descriptor for one registered chart kind.

    `required_inputs` are fields the renderer reads from its input dict;
    `claim_types` are the Representation claim vocabulary entries the chart
    is eligible for. The Agent filters available charts by claim_type first
    and then confirms the inputs are present before selecting.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required_inputs: list[str] = Field(default_factory=list)
    claim_types: list[str] = Field(default_factory=list)


Renderer = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class _Entry:
    spec: ChartSpec
    renderer: Renderer


_REGISTRY: dict[str, _Entry] = {}


def register(spec: ChartSpec, renderer: Renderer) -> None:
    """Register a chart. Overwrites any prior entry with the same id."""
    _REGISTRY[spec.id] = _Entry(spec=spec, renderer=renderer)


def get_spec(chart_id: str) -> ChartSpec | None:
    entry = _REGISTRY.get(chart_id)
    return entry.spec if entry is not None else None


def all_specs() -> list[ChartSpec]:
    """Stable-ordered list of all registered chart specs."""
    return [entry.spec for entry in _REGISTRY.values()]


def render(chart_id: str, inputs: dict[str, Any]) -> dict[str, Any] | None:
    """Render one chart event by id. Returns `None` if the chart is not
    registered or its renderer rejects the inputs (same fail-closed contract
    as the underlying `_native_*_chart` helpers)."""
    entry = _REGISTRY.get(chart_id)
    if entry is None:
        return None
    try:
        return entry.renderer(inputs or {})
    except Exception:
        # Renderers are intentionally permissive; any unexpected failure
        # maps to "no chart" rather than crashing the decision stream.
        return None


# ---- Renderer wrappers (lazy imports on `api.pipeline_adapter`) -------
#
# Each wrapper just delegates to the existing `_native_*_chart` helper.
# We do not reshape inputs — callers pass the session view dict the
# renderer already understands (e.g. `last_projection_view` for
# scenario_fan). Lazy imports keep us from forming an import cycle with
# `api/pipeline_adapter.py`, which imports from `briarwood/...` at module
# load.


def _render_scenario_fan(inputs: dict[str, Any]) -> dict[str, Any] | None:
    from api.pipeline_adapter import _native_scenario_chart
    return _native_scenario_chart(inputs)


def _render_value_opportunity(inputs: dict[str, Any]) -> dict[str, Any] | None:
    from api.pipeline_adapter import _native_value_chart
    return _native_value_chart(inputs)


def _render_cma_positioning(inputs: dict[str, Any]) -> dict[str, Any] | None:
    from api.pipeline_adapter import _native_cma_chart
    market_view = inputs.get("_market_view") if isinstance(inputs.get("_market_view"), dict) else None
    # Strip the optional market-view hint before forwarding so we don't
    # leak the marker into the renderer's own get() calls.
    view = {k: v for k, v in inputs.items() if k != "_market_view"}
    return _native_cma_chart(view, market_view=market_view)


def _render_risk_bar(inputs: dict[str, Any]) -> dict[str, Any] | None:
    from api.pipeline_adapter import _native_risk_chart
    return _native_risk_chart(inputs)


def _render_rent_burn(inputs: dict[str, Any]) -> dict[str, Any] | None:
    from api.pipeline_adapter import _native_rent_chart
    return _native_rent_chart(inputs)


def _render_rent_ramp(inputs: dict[str, Any]) -> dict[str, Any] | None:
    from api.pipeline_adapter import _native_rent_ramp_chart
    return _native_rent_ramp_chart(inputs)


# ---- Registered chart catalog ----------------------------------------

register(
    ChartSpec(
        id="scenario_fan",
        name="5-year value range",
        description=(
            "Bull/base/bear projected value over a 5-year hold, anchored on "
            "ask or all-in basis."
        ),
        required_inputs=[
            "bull_case_value",
            "base_case_value",
            "bear_case_value",
        ],
        claim_types=["scenario_range", "downside_risk", "renovation_impact", "sensitivity"],
    ),
    _render_scenario_fan,
)

register(
    ChartSpec(
        id="value_opportunity",
        name="Ask vs fair value",
        description=(
            "Subject ask set against Briarwood fair value with the drivers "
            "that moved the read."
        ),
        required_inputs=["ask_price", "fair_value_base"],
        claim_types=["price_position", "value_drivers", "affordability_carry_cost"],
    ),
    _render_value_opportunity,
)

register(
    ChartSpec(
        id="cma_positioning",
        name="Where the comps sit",
        description=(
            "Scatter of comp asks against the subject ask and value band, "
            "labeled by which comps fed fair value."
        ),
        required_inputs=["comps"],
        claim_types=["comp_evidence", "price_position"],
    ),
    _render_cma_positioning,
)

register(
    ChartSpec(
        id="risk_bar",
        name="Risk drivers",
        description=(
            "Per-flag penalty share showing what is pulling the setup off "
            "course versus what is adding trust."
        ),
        required_inputs=["risk_flags"],
        claim_types=["risk_composition", "downside_risk"],
    ),
    _render_risk_bar,
)

register(
    ChartSpec(
        id="rent_burn",
        name="Rent vs monthly cost",
        description=(
            "Rent scenarios against monthly carry across the hold horizon."
        ),
        required_inputs=["burn_chart_payload"],
        claim_types=["rent_coverage", "rent_vs_own", "affordability_carry_cost"],
    ),
    _render_rent_burn,
)

register(
    ChartSpec(
        id="rent_ramp",
        name="Can rent catch up?",
        description=(
            "Net cash flow at base/bull/bear rent ramps with break-even "
            "markers."
        ),
        required_inputs=["ramp_chart_payload"],
        claim_types=["rent_ramp", "rent_coverage", "rent_vs_own", "sensitivity"],
    ),
    _render_rent_ramp,
)


def _render_hidden_upside_band(_inputs: dict[str, Any]) -> dict[str, Any] | None:
    """Prose-only chart: HIDDEN_UPSIDE claims render through the
    `HiddenUpsideBlock` React card rather than an SSE chart event. Registered
    so the Representation Agent and chart-id validator can reference a
    concrete spec for this claim type — returning ``None`` is the contract
    for "no event to emit."""
    return None


register(
    ChartSpec(
        id="hidden_upside_band",
        name="Hidden upside",
        description=(
            "Marker spec for HIDDEN_UPSIDE claims. UI renders via the "
            "HiddenUpsideBlock card; no standalone chart event is emitted."
        ),
        required_inputs=[],
        claim_types=["hidden_upside", "renovation_impact"],
    ),
    _render_hidden_upside_band,
)


def _render_horizontal_bar_with_ranges(_inputs: dict[str, Any]) -> dict[str, Any] | None:
    """Phase-3 wedge chart. The claim-object representation layer
    (`briarwood/claims/representation/`) builds the SSE spec directly from a
    `VerdictWithComparisonClaim`, so the registry entry is a marker for
    discoverability + validation. Returning ``None`` matches the no-event
    contract used by `hidden_upside_band`."""
    return None


register(
    ChartSpec(
        id="horizontal_bar_with_ranges",
        name="Scenario ranges",
        description=(
            "One horizontal range bar per scenario with a median tick, used "
            "by the verdict_with_comparison archetype. The wedge's "
            "representation layer builds the spec directly from the claim."
        ),
        required_inputs=["scenarios"],
        claim_types=["scenario_comparison"],
    ),
    _render_horizontal_bar_with_ranges,
)

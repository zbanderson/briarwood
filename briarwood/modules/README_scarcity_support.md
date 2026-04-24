# scarcity_support — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`scarcity_support` produces a geography-level supply/optionality signal for a property's town or segment. It answers questions like *"how scarce is this segment?"* or *"is there inventory competition?"* by returning a bounded score (`scarcity_support_score`, 0–100), a categorical label (`scarcity_label`), and a buyer-facing narrative (`buyer_takeaway`). Under the hood it pulls town/county outlook data through `TownCountyDataService` and scores it with `ScarcitySupportScorer`. Call this tool when the user's intent involves supply dynamics, inventory competition, or optionality context — it is the standalone tool behind what `risk_model`, `bull_base_bear` (legacy), and several `decision_model` scoring paths consume today.

## Location

- **Entry point:** [briarwood/modules/scarcity_support_scoped.py](scarcity_support_scoped.py) — `run_scarcity_support(context: ExecutionContext) -> dict[str, object]`.
- **Legacy module:** [briarwood/modules/scarcity_support.py:15](scarcity_support.py#L15) — `ScarcitySupportModule.run(property_input)`.
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="scarcity_support", depends_on=[], required_context_keys=["property_data"], runner=run_scarcity_support)`.
- **Schema:** `ScarcitySupportScore` at [briarwood/agents/scarcity/schemas.py](../agents/scarcity/schemas.py).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RESEARCH` — called for "how scarce is this segment?" questions.
- `MICRO_LOCATION` — called as a location context layer.
- `BROWSE` — called for inventory/competition context in browse-mode summaries.
- `DECISION` — called indirectly via `decision_model` scoring paths that consume `scarcity_support_score`.
- Not called for: `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive through `ExecutionContext` and are normalized into a `PropertyInput` via `build_property_input_from_context`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.town` | `str` | required | listing facts | Used as the geography key by `TownCountyDataService`. |
| `context.property_data.state` | `str` | required | listing facts | Same. |
| `context.property_data.county` | `str` | optional | listing facts | Fallback geography. |
| `context.property_data.property_type` | `str` | optional | listing facts | Narrows the segment within a town. |
| `context.property_data.sqft`, `beds`, `baths` | mixed | required | listing facts | Required by `PropertyInput` constructor, not by scarcity logic directly. |

## Outputs

The runner returns `ModulePayload.model_dump()`. The key field `scarcity_support_score` is read by multiple downstream consumers — see Dependencies → Downstream for the list.

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.metrics.scarcity_support_score` | `float` | 0–100 | Rolled-up scarcity score. **Field name is load-bearing — do not reshape.** |
| `data.metrics.scarcity_label` | `str` | enum | Categorical label (e.g., `"high"`, `"moderate"`, `"low"`). |
| `data.metrics.buyer_takeaway` | `str` | prose | One-sentence buyer-facing narrative. |
| `data.metrics.missing_inputs` | `str` | — | Comma-separated list of absent signals (`"none"` when complete). |
| `data.legacy_payload.demand_consistency_score`, `location_scarcity_score`, `land_scarcity_score`, `scarcity_score` | `float` | 0–1 | Sub-component scores from `ScarcitySupportScore`. |
| `data.legacy_payload.demand_drivers`, `scarcity_notes` | `list[str]` | — | Signal lists behind the score. |
| `confidence` | `float` | 0.0–1.0 | Engine confidence. |
| `warnings` | `list[str]` | — | Populated on fallback. |
| `assumptions_used.geography_driven` | `bool` | — | Always `True`. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]`.
- **Benefits from (optional):** `property_summary`, `market_context`.
- **Calls internally:** `TownCountyDataService` + `ScarcitySupportScorer` at [briarwood/agents/scarcity/](../agents/scarcity/).
- **Must not run concurrently with:** none.
- **Downstream consumers (read `scarcity_support_score` by key):**
  - [briarwood/modules/bull_base_bear.py:37](bull_base_bear.py#L37) — deprecating (see PROMOTION_PLAN.md entry 6).
  - [briarwood/interactions/town_x_scenario.py:40](../interactions/town_x_scenario.py#L40)
  - [briarwood/interactions/valuation_x_town.py:82-85](../interactions/valuation_x_town.py#L82-L85)
  - [briarwood/agents/rental_ease/agent.py:74, 202, 287, 327](../agents/rental_ease/agent.py#L74)
  - (Historical: `briarwood/decision_model/scoring.py` and `lens_scoring.py` also read this field. Both paths were deleted in Handoff 4 on 2026-04-24 alongside the `calculate_final_score` chain — see [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 15 scope-limit paragraph corrected.")

## Invariants

- Never raises. All exceptions are caught and replaced with a fallback `ModulePayload` (`mode="fallback"`, `confidence=0.08`).
- `scarcity_support_score` is preserved verbatim from the legacy payload. Field-name stability is load-bearing.
- `confidence ∈ [0.0, 1.0]`.
- Geography-driven — the tool describes the town/segment containing the property, not the property itself.
- Deterministic for fixed inputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.scarcity_support_scoped import run_scarcity_support

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "town": "Avon By The Sea",
        "state": "NJ",
        "county": "Monmouth",
        "property_type": "single_family",
        "sqft": 1_800,
        "beds": 3,
        "baths": 2.0,
    },
)

payload = run_scarcity_support(context)
# payload["data"]["metrics"]["scarcity_support_score"] ≈ 72.0
# payload["data"]["metrics"]["scarcity_label"]         == "moderate"
# payload["confidence"]                                ∈ [0, 1]
```

## Hardcoded Values & TODOs

- Scarcity category thresholds live inside `ScarcitySupportScorer` at [briarwood/agents/scarcity/scarcity_support.py](../agents/scarcity/scarcity_support.py); not configurable from this wrapper.
- `required_fields` hardcoded at [scarcity_support_scoped.py](scarcity_support_scoped.py): `["town", "state"]`.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- The internal `TownCountyDataService` wiring is implementation-private; the tool contract is `PropertyInput → ScarcitySupportScore`.
- Tests: [tests/modules/test_scarcity_support_isolated.py](../../tests/modules/test_scarcity_support_isolated.py) covers isolation, field-name stability, error contract, and registry integration.
- No direct LLM calls; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 7.
- Contract: new scoped runner `run_scarcity_support(context)` wraps `ScarcitySupportModule.run(property_input)` via `module_payload_from_legacy_result`. Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*. Field-name stability on `scarcity_support_score` preserved.

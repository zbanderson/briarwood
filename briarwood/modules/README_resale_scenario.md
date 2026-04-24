# resale_scenario — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`resale_scenario` produces Briarwood's forward bull / base / bear scenario values for a property over a hold horizon. It delegates to `BullBaseBearModule`, which internally fans out to current-value, market-history, town/county outlook, risk-constraints, and scarcity-support to construct the three scenario values, then applies two bounded macro nudges to the *confidence* of that read: a county HPI-momentum nudge (≤ 4%) and a town-development-velocity nudge (≤ 4%). Critically, the nudges adjust confidence — not the scenario values themselves. Call this tool whenever the user's intent involves forward resale, projection-tier questions, or any decision-tier conversation where the spread between bull and bear matters.

## Location

- **Entry point:** [briarwood/modules/resale_scenario_scoped.py:17](resale_scenario_scoped.py#L17) — `run_resale_scenario(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:87-94](../execution/registry.py#L87-L94) — `ModuleSpec(name="resale_scenario", depends_on=["valuation", "carry_cost", "town_development_index"], required_context_keys=["property_data", "assumptions"], runner=run_resale_scenario)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); legacy `ScenarioOutput` shape from `BullBaseBearModule` at [briarwood/modules/bull_base_bear.py](bull_base_bear.py).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `PROJECTION` — always called; this is the forward-resale anchor.
- `DECISION` — called for verdicts that depend on bull/bear spread.
- `STRATEGY` — called for hold-vs-flip and timing questions.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.purchase_price` | `float` | required | listing facts | Required field per [resale_scenario_scoped.py:59](resale_scenario_scoped.py#L59). |
| `context.property_data.taxes` | `float` (annual) | required | listing facts | Same. |
| `context.property_data.sqft`, `town`, `state` | mixed | required | listing facts | Same. |
| `context.assumptions.hold_period_years` | `int` | optional | router / session | Read by `BullBaseBearModule` to set the projection horizon. Audit doc lists this as required; the wrapper does not enforce it but downstream output quality drops without it. |
| `context.prior_outputs.valuation` / `carry_cost` / `town_development_index` | `dict` | optional | executor (via `depends_on`) | Declared to ensure execution order; the wrapper does not directly read these dicts but `BullBaseBearModule` and the dev-index nudge consume them indirectly via `context.get_module_output`. |
| `context.macro_context.hpi_momentum` | signed `float` | optional | macro reader (FRED) | Drives the ≤ 4% confidence nudge at [resale_scenario_scoped.py:31-36](resale_scenario_scoped.py#L31-L36). |
| `context.market_context` | `dict` | optional | router / session | Accepted via `optional_context_keys`. |

## Outputs

`run_resale_scenario` returns `ModulePayload.model_dump()`. Salient fields (from `BullBaseBearModule` legacy result plus the two nudges in `extra_data`):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `ask_price` | `float \| None` | USD | From `ScenarioOutput`. |
| `bull_case_value` | `float \| None` | USD | Same. |
| `base_case_value` | `float \| None` | USD | Same. |
| `bear_case_value` | `float \| None` | USD | Same. |
| `spread` | `float \| None` | USD | `bull - bear`; non-negative. |
| `confidence_by_scenario` | `dict` | — | Per-scenario confidence breakdown from `BullBaseBearModule`. |
| `confidence` | `float \| None` | 0-1 | Outer `ModulePayload.confidence`, replaced by the dev-index-nudged value when computable, else by the macro-nudged value, else unchanged from the legacy result. Rounded to 4 decimals. |
| `extra_data.macro_nudge` | `dict` | — | `apply_macro_nudge` telemetry: signal, applied delta, adjusted confidence. |
| `extra_data.dev_index_nudge` | `dict` | — | `apply_dev_index_nudge` telemetry: velocity, applied delta, adjusted confidence, max nudge. |
| `warnings` | `list[str]` | — | Fallback warnings when sparse inputs hit the exception branch. |
| `assumptions_used.legacy_module` | `str` | — | `"BullBaseBearModule"`. |
| `assumptions_used.macro_context_used` | `bool` | — | True when an `hpi_momentum` macro signal was present. |
| `assumptions_used.dev_index_used` | `bool` | — | True when `dev_index_nudge.velocity` was numeric (i.e., town_development_index produced a velocity). |

## Dependencies

- **Requires (inputs):** `valuation`, `carry_cost`, `town_development_index` (per [registry.py:89](../execution/registry.py#L89)). The wrapper itself does not directly read these from `prior_outputs`; ordering is enforced by the executor and the dev-index nudge reads `town_development_index` via `read_dev_index` at [briarwood/modules/town_development_index.py:276](town_development_index.py#L276).
- **Benefits from (optional):** `market_context`, `macro_context.hpi_momentum`.
- **Calls internally:** `BullBaseBearModule` at [briarwood/modules/bull_base_bear.py](bull_base_bear.py) — which itself runs current-value, market-value-history, town-county-outlook, risk-constraints, scarcity-support; `apply_macro_nudge` at [briarwood/modules/macro_reader.py:78](macro_reader.py#L78); `apply_dev_index_nudge` at [briarwood/modules/town_development_index.py:286](town_development_index.py#L286).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** `opportunity_cost` ([registry.py:159-170](../execution/registry.py#L159-L170)).

## Invariants

- Never raises. All exceptions are caught at [resale_scenario_scoped.py:70-78](resale_scenario_scoped.py#L70-L78) and replaced with a sparse-input fallback payload.
- `bear_case_value <= base_case_value <= bull_case_value` (per `BullBaseBearModule`'s `ScenarioOutput` invariants).
- `spread >= 0`.
- Macro and dev-index nudges are bounded: `MACRO_MAX_NUDGE = 0.04`, `DEV_INDEX_MAX_NUDGE = 0.04` at [resale_scenario_scoped.py:13-14](resale_scenario_scoped.py#L13-L14).
- Nudge order: macro first, then dev_index applied on top of the macro-adjusted confidence (chained at [resale_scenario_scoped.py:37-43](resale_scenario_scoped.py#L37-L43)). Final confidence write at [resale_scenario_scoped.py:61-68](resale_scenario_scoped.py#L61-L68) prefers `dev_index_nudge.adjusted_confidence` if present, else `macro_nudge.adjusted_confidence`.
- `confidence` remains in `[0.0, 1.0]` after both nudges; rounded to 4 decimals.
- Deterministic per input when macro and dev-index data are fixed; no LLM calls in the wrapper.
- Never mutates its inputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.resale_scenario_scoped import run_resale_scenario

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "purchase_price": 850_000,
        "taxes": 14_400,
        "sqft": 2_100,
        "town": "Montclair",
        "state": "NJ",
    },
    assumptions={"hold_period_years": 5},
    macro_context={"hpi_momentum": {"signal": 0.10, "source": "FRED"}},
)

payload = run_resale_scenario(context)
# payload["data"]["metrics"]["bull_case_value"]   ≈  1_120_000
# payload["data"]["metrics"]["base_case_value"]   ≈    980_000
# payload["data"]["metrics"]["bear_case_value"]   ≈    870_000
# payload["data"]["metrics"]["spread"]            ≈    250_000
# payload["extra_data"]["macro_nudge"]["applied_nudge"]      ≈ 0.008
# payload["extra_data"]["dev_index_nudge"]["applied_nudge"]  ≈ 0.012
# payload["confidence"]                                       ∈ [0, 1]
```

## Hardcoded Values & TODOs

- `MACRO_MAX_NUDGE = 0.04` at [resale_scenario_scoped.py:13](resale_scenario_scoped.py#L13).
- `DEV_INDEX_MAX_NUDGE = 0.04` at [resale_scenario_scoped.py:14](resale_scenario_scoped.py#L14).
- Required fields list hardcoded in both success and fallback paths: `["purchase_price", "taxes", "sqft", "town", "state"]`.
- Bull/base/bear thresholds and per-scenario confidence weights live in `BullBaseBearModule` and `BullBaseBearSettings` ([briarwood/decision_model/scoring_config.py](../decision_model/scoring_config.py)) — not in this wrapper.

## Blockers for Tool Use

- None. This module is callable in isolation via `run_resale_scenario(context)` with a populated `ExecutionContext`.

## Notes

- **`BullBaseBearModule` is a KEEP-as-internal-helper, not deprecating.** The scoped `resale_scenario` wrapper *composes* `BullBaseBearModule` — it does not replace it. This is the same pattern as `OwnershipEconomicsModule` behind `carry_cost`, `RentalEaseModule` behind `rental_option`, and `RiskConstraintsModule` behind `risk_model`. The scenario computation logic lives in `BullBaseBearModule`; the wrapper adds confidence nudges and the canonical error contract. See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 6 decision corrected."
- **Town-development velocity affects confidence, not scenario values.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) describes this module as "Uses town_development_index velocity to project appreciation," which reads as if velocity biases the bull/base/bear values themselves. In the current code, velocity flows through `apply_dev_index_nudge` to adjust the *confidence* of the read only. Scenario values come from `BullBaseBearModule` outputs unchanged. Worth re-wording the audit doc when reconciling.
- Tests: [tests/modules/test_resale_scenario_isolated.py](../../tests/modules/test_resale_scenario_isolated.py); macro context covered by [tests/modules/test_macro_context.py](../../tests/modules/test_macro_context.py); broader executor coverage in [tests/test_modules.py](../../tests/test_modules.py).
- No direct LLM calls in the wrapper; cost is zero at this layer.

## Changelog

### 2026-04-24
- Initial README created.
- Clarified that `BullBaseBearModule` is a KEEP-as-internal-helper after the Handoff 4 reclassification. Its prior "deprecating" framing in PROMOTION_PLAN.md entry 6 was based on a misread of `tools.py:1411`. See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 6 decision corrected."

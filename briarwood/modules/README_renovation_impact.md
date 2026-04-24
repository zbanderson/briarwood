# renovation_impact — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`renovation_impact` estimates the dollar value created (or destroyed) by an already-specified renovation scenario. Given a toggled-on `renovation_scenario` on the property input (budget, target condition, optional sqft/beds/baths/ADU/garage changes), it constructs a hypothetical post-renovation `PropertyInput`, runs it through `ComparableSalesModule` and `CurrentValueModule` to obtain a renovated BCV, and reports gross and net value creation, ROI, and cost-per-dollar-of-value. Call this tool when the user's intent is "is this renovation worth it?" or when `arv_model` needs a renovated BCV anchor; the tool is a no-op (returns a blocked `ModuleResult` payload) when no renovation scenario is configured.

## Location

- **Entry point:** [briarwood/modules/renovation_impact_scoped.py:11](renovation_impact_scoped.py#L11) — `run_renovation_impact(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:119-126](../execution/registry.py#L119-L126) — `ModuleSpec(name="renovation_impact", depends_on=[], required_context_keys=["property_data", "assumptions"], runner=run_renovation_impact)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); inner payload shape constructed in `RenovationScenarioModule.run` at [briarwood/modules/renovation_scenario.py:160-175](renovation_scenario.py#L160-L175). Settings at `DEFAULT_RENOVATION_SCENARIO_SETTINGS` in [briarwood/settings.py](../settings.py).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `STRATEGY` — called for flip / value-add paths.
- `PROJECTION` — called when the user asks "what happens if I renovate?"
- `DECISION` — called as a dependency of `arv_model` ([registry.py:127-134](../execution/registry.py#L127-L134)) and `margin_sensitivity` ([registry.py:135-142](../execution/registry.py#L135-L142)).
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.renovation_scenario.enabled` | `bool` | required | user / assumptions | Gate at [renovation_scenario.py:39-45](renovation_scenario.py#L39-L45). When absent or false, the module returns a `not_enabled` blocked result. |
| `context.property_data.renovation_scenario.renovation_budget` | `float` | required when enabled | user / assumptions | Must exceed `settings.min_renovation_budget` or the module returns `missing_inputs` (see [renovation_scenario.py:47-56](renovation_scenario.py#L47-L56)). |
| `context.property_data.renovation_scenario.target_condition` | `str` | optional | assumptions | Defaults to `"renovated"`. |
| `context.property_data.renovation_scenario.sqft_addition` | `int` | optional | assumptions | Added to `property_input.sqft` for the renovated input. |
| `context.property_data.renovation_scenario.beds_after` / `baths_after` | `int` / `float` | optional | assumptions | Override bed/bath counts on the renovated input. |
| `context.property_data.renovation_scenario.adds_adu` | `bool` | optional | assumptions | When true and `adu_type` is missing, defaults to `"detached_cottage"`. |
| `context.property_data.renovation_scenario.adds_garage` | `bool` | optional | assumptions | When true and `garage_spaces` is null/0, sets to `1`. |
| `context.property_data.purchase_price` | `float` | recommended | — | Used as a fallback anchor if `briarwood_current_value` is missing (see [renovation_scenario.py:64](renovation_scenario.py#L64)). |
| `context.property_data.condition_profile`, `sqft`, `beds`, `baths`, `town`, `state`, `garage_spaces`, `adu_type` | mixed | optional | listing facts | Needed by the internal comp and current-value runs. |
| `context.property_summary` | `dict` | optional | — | Accepted via `optional_context_keys`. |
| `context.assumptions` | `dict` | required (may be empty) | router / session | Registry requires the key; scenario fields are nested inside `property_data.renovation_scenario` today, not in `assumptions`. |

## Outputs

`run_renovation_impact` returns `ModulePayload.model_dump()`. When the scenario runs, the payload's inner data comes from the dict built at [renovation_scenario.py:160-174](renovation_scenario.py#L160-L174):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `enabled` | `bool` | — | True when the scenario ran; False on `not_enabled` / `missing_inputs` / `missing_anchor` / `insufficient_support` blocked paths. |
| `renovation_budget` | `float` | USD | Passthrough from input. |
| `current_bcv` | `float` | USD | Pre-renovation Briarwood current value, rounded to 2 decimals. |
| `renovated_bcv` | `float` | USD | Post-renovation Briarwood current value, rounded to 2 decimals. |
| `gross_value_creation` | `float` | USD | `renovated_bcv - current_bcv`. |
| `net_value_creation` | `float` | USD | `gross_value_creation - renovation_budget`. |
| `roi_pct` | `float` | percent (not fraction) | `(net_value_creation / budget) * 100`, rounded to 1 decimal. Zero when budget is zero. |
| `cost_per_dollar_of_value` | `float \| None` | ratio | `budget / gross_value_creation` rounded to 3 decimals; `None` when gross creation is ≤ 0 (stored internally as `float("inf")`). |
| `condition_change` | `str` | prose | `"{original} → {target}"`. |
| `sqft_change` | `str \| None` | prose | `"{old} → {new}"` only when `sqft_addition` was provided. |
| `comp_range_text` | `str` | prose | Summary of the renovated-condition comp range. |
| `confidence` | `float` | 0-1 | Starts at `renovated_cv_result.confidence`, penalized by `confidence_penalty_few_renovated_comps` when fewer than `min_renovated_comps_for_full_confidence` renovated comps are found; floored at `confidence_floor`. Rounded to 2 decimals. |
| `warnings` | `list[str]` | — | Includes warnings from the renovated-condition current-value run plus the "few renovated comps" message when triggered. |
| `summary` | `str` | prose | Full human-readable narrative from `_renovation_narrative` at [renovation_scenario.py:236](renovation_scenario.py#L236). |
| `assumptions_used.legacy_module` | `str` | — | `"RenovationScenarioModule"`. |

**Note on output shape:** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) describe this module as producing `renovation_scope`, `estimated_cost_range`, and `timeline_estimate`. Those fields do NOT exist in the current output. See [DECISIONS.md](../../DECISIONS.md) entry "renovation_impact output schema mismatch in audit docs" (2026-04-24).

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]` at [registry.py:121](../execution/registry.py#L121). Only `property_data` and `assumptions` (per registry) are required.
- **Benefits from (optional):** `property_summary`, and `prior_results["current_value"]` when called from an executor that has already run `valuation` (per [renovation_scenario.py:59-62](renovation_scenario.py#L59-L62)).
- **Calls internally:** `RenovationScenarioModule` at [briarwood/modules/renovation_scenario.py:11](renovation_scenario.py#L11), which in turn calls `ComparableSalesModule` and `CurrentValueModule` on a hypothetical renovated `PropertyInput`.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** `arv_model` ([registry.py:127-134](../execution/registry.py#L127-L134)), `margin_sensitivity` ([registry.py:135-142](../execution/registry.py#L135-L142)).

## Invariants

- **Never raises on valid input.** The scoped entry at [renovation_impact_scoped.py:11-38](renovation_impact_scoped.py#L11-L38) wraps the body in `try/except`; internal failures from the comp / current-value modules return a canonical fallback payload via `module_payload_from_error` at [scoped_common.py:114](scoped_common.py#L114) — `mode="fallback"`, `confidence=0.08`, `warnings=["Renovation-impact fallback: {ExceptionClass}: {message}"]`. See the 2026-04-24 "Scoped wrapper error contract" entry in [DECISIONS.md](../../DECISIONS.md).
- When `renovation_scenario` is absent or disabled, returns a `_blocked_result` with `enabled=False` and a clear summary — not an exception.
- `roi_pct` is returned as a percent (e.g., `12.5` not `0.125`).
- `cost_per_dollar_of_value` is `None` when `gross_value_creation <= 0` (see [renovation_scenario.py:168](renovation_scenario.py#L168)).
- `confidence` is in `[settings.confidence_floor, 1.0]`, rounded to 2 decimals.
- Deterministic per input; no LLM calls, no randomness.
- Never mutates the input `PropertyInput`; it builds a new one via `dataclasses.replace` at [renovation_scenario.py:91](renovation_scenario.py#L91).

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.renovation_impact_scoped import run_renovation_impact

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "purchase_price": 850_000,
        "sqft": 2_100,
        "beds": 4,
        "baths": 2.5,
        "town": "Montclair",
        "state": "NJ",
        "condition_profile": "dated",
        "renovation_scenario": {
            "enabled": True,
            "renovation_budget": 150_000,
            "target_condition": "renovated",
            "sqft_addition": 400,
            "beds_after": 4,
            "baths_after": 3,
        },
    },
    assumptions={},
)

payload = run_renovation_impact(context)
# payload["data"]["enabled"]                  == True
# payload["data"]["gross_value_creation"]     ≈  250_000
# payload["data"]["net_value_creation"]       ≈  100_000
# payload["data"]["roi_pct"]                  ≈   66.7
# payload["data"]["cost_per_dollar_of_value"] ≈    0.6
# payload["confidence"]                       ∈ [0, 1]
```

## Hardcoded Values & TODOs

- `DEFAULT_RENOVATION_SCENARIO_SETTINGS` in [briarwood/settings.py](../settings.py) holds `min_renovation_budget`, `min_renovated_comps_for_full_confidence`, `confidence_penalty_few_renovated_comps`, and `confidence_floor`. None of these are overridable from `ExecutionContext`.
- Default target condition is `"renovated"` at [renovation_scenario.py:74](renovation_scenario.py#L74); default ADU type when `adds_adu` triggers fallback is `"detached_cottage"` at [renovation_scenario.py:89](renovation_scenario.py#L89); default garage count when `adds_garage` triggers fallback is `1` at [renovation_scenario.py:86](renovation_scenario.py#L86).
- Scope / cost-range / timeline estimation is NOT performed — the module takes those as input rather than deriving them.

## Blockers for Tool Use

- None for normal invocation. Internal exceptions degrade to a canonical fallback payload (see Invariants) rather than propagating.

## Notes

- **Output schema contradicts the audit docs.** See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 entry "renovation_impact output schema mismatch in audit docs." Reconcile by rewriting the audit-doc descriptions to match the BCV-delta + ROI shape, or by adding a real scope-estimation module.
- The internal comp and current-value runs use `ComparableSalesModule` — the model [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges flags as not present in the scoped registry. That comment applies transitively to anyone depending on `renovation_impact` for renovated-comp support.
- Tests: currently covered indirectly through executor and orchestrator tests; search `run_renovation_impact` or `RenovationScenarioModule` under [tests/](../../tests/).
- No direct LLM calls; no cost incurred at this wrapper.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: wrapped body in `try/except` and migrated to the canonical error contract. Internal exceptions now return a `module_payload_from_error` fallback (`mode="fallback"`, `confidence=0.08`) rather than propagating. Added [tests/modules/test_renovation_impact_isolated.py](../../tests/modules/test_renovation_impact_isolated.py). See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."

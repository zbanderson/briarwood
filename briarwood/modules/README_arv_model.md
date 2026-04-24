# arv_model — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`arv_model` is a pure composite wrapper that packages the already-computed `valuation` and `renovation_impact` outputs into a single ARV-focused snapshot. It introduces no new valuation math — the renovated BCV (the conceptual after-repair value) is computed upstream by `renovation_impact` (which uses `RenovationScenarioModule` to run `ComparableSalesModule` and `CurrentValueModule` against a hypothetical renovated `PropertyInput`); the current BCV is computed upstream by `valuation`. This module reads both from `prior_outputs`, surfaces them in a clean `arv_snapshot`, and reconciles the two confidence values via `min`. Call this tool whenever the user's intent is "what's it worth after I renovate?" — but ensure both `valuation` and `renovation_impact` have already run, because this module raises `ValueError` if either is missing.

## Location

- **Entry point:** [briarwood/modules/arv_model_scoped.py:9](arv_model_scoped.py#L9) — `run_arv_model(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:127-134](../execution/registry.py#L127-L134) — `ModuleSpec(name="arv_model", depends_on=["valuation", "renovation_impact"], required_context_keys=["property_data", "assumptions"], runner=run_arv_model)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316). No internal schema beyond the inline `arv_snapshot` dict.

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `STRATEGY` — called for flip / value-add paths.
- `PROJECTION` — called when the user asks about post-renovation worth.
- `DECISION` — called as a dependency of `margin_sensitivity` ([registry.py:135-142](../execution/registry.py#L135-L142)) for renovation margin calculations.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)). This module does NOT convert to `PropertyInput`; it reads only `prior_outputs`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.prior_outputs.valuation` | `dict` | required | executor (via `depends_on=["valuation"]`) | Read at [arv_model_scoped.py:18](arv_model_scoped.py#L18); missing causes `ValueError`. |
| `context.prior_outputs.renovation_impact` | `dict` | required | executor (via `depends_on=["renovation_impact"]`) | Read at [arv_model_scoped.py:19](arv_model_scoped.py#L19); missing causes `ValueError`. |
| `context.property_data` / `context.assumptions` | `dict` | required (per registry) | router / session | Required by registry but not directly read by this runner. |
| `context.comp_context` | `dict` | optional | — | Accepted via `optional_context_keys`. |

## Outputs

`run_arv_model` returns `ModulePayload.model_dump()`. The payload's `data` is constructed inline at [arv_model_scoped.py:44-77](arv_model_scoped.py#L44-L77):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `module_name` | `str` | — | `"arv_model"`. |
| `summary` | `str` | prose | Built by `_build_arv_summary` at [arv_model_scoped.py:81-97](arv_model_scoped.py#L81-L97); names `renovated_bcv`, `current_bcv`, `renovation_budget`, `roi_pct` when complete. |
| `valuation.summary` / `metrics` / `confidence` | mixed | — | Echoed sub-dict from prior `valuation` output. |
| `renovation_impact.summary` / `metrics` / `confidence` | mixed | — | Echoed sub-dict from prior `renovation_impact` output. |
| `arv_snapshot.current_bcv` | `float \| None` | USD | From `renovation_impact.metrics.current_bcv` if present, else `valuation.metrics.briarwood_current_value`. |
| `arv_snapshot.renovated_bcv` | `float \| None` | USD | The conceptual ARV — from `renovation_impact.metrics.renovated_bcv`. |
| `arv_snapshot.renovation_budget` | `float` | USD | Default `0.0` when missing. |
| `arv_snapshot.gross_value_creation` | `float` | USD | Default `0.0`. |
| `arv_snapshot.net_value_creation` | `float` | USD | Default `0.0`. |
| `arv_snapshot.roi_pct` | `float` | percent (not fraction) | Default `0.0`. |
| `arv_snapshot.condition_change` | `str \| None` | prose | Passthrough. |
| `arv_snapshot.sqft_change` | `str \| None` | prose | Passthrough. |
| `arv_snapshot.comp_range_text` | `str \| None` | prose | Passthrough. |
| `confidence` | `float \| None` | 0-1 | `min(valuation.confidence, renovation_impact.confidence)` rounded to 4 decimals; `None` when neither is numeric. |
| `warnings` | `list[str]` | — | Deduplicated merge of warnings from both prior outputs. |
| `assumptions_used.composite_from_prior_outputs` | `bool` | — | Always `True`. |
| `assumptions_used.required_prior_modules` | `list[str]` | — | `["valuation", "renovation_impact"]`. |

**Note on output shape:** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) describe outputs `estimated_arv`, `arv_confidence`, `comparable_arv_support`, `component_cost_deltas` and claim "internally: comparable_sales." None of those field names exist in the actual payload, and `comparable_sales` is not called directly here. See [DECISIONS.md](../../DECISIONS.md) entry "arv_model output schema and behavior mismatch in audit docs" (2026-04-24).

## Dependencies

- **Requires (inputs):** `valuation`, `renovation_impact` — both declared at [registry.py:129](../execution/registry.py#L129) AND enforced at runtime via `_require_prior_output` at [arv_model_scoped.py:100-106](arv_model_scoped.py#L100-L106).
- **Benefits from (optional):** `comp_context`.
- **Calls internally:** none. This runner reads `prior_outputs` only.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** `margin_sensitivity` ([registry.py:135-142](../execution/registry.py#L135-L142)).

## Invariants

- **Never raises on missing or degraded priors.** Follows the canonical error contract (DECISIONS.md 2026-04-24): when either prior is absent OR has `mode in {"error","fallback"}`, returns `module_payload_from_missing_prior` at [scoped_common.py:152](scoped_common.py#L152) — `mode="error"`, `confidence=None`, `missing_inputs=[...]`, `data["arv_snapshot"]={}`. On internal composition exceptions returns `module_payload_from_error` — `mode="fallback"`, `confidence=0.08`, `warnings=["Arv-model fallback: ..."]`.
- `arv_snapshot.renovation_budget` / `gross_value_creation` / `net_value_creation` / `roi_pct` default to `0.0` when missing from the renovation output (see [arv_model_scoped.py:31-34](arv_model_scoped.py#L31-L34)).
- `confidence` is the minimum of the two prior confidences; `None` when neither is numeric.
- Warnings are deduplicated by string equality at [arv_model_scoped.py:120-130](arv_model_scoped.py#L120-L130) — order is preserved by first occurrence.
- Deterministic per input; no LLM calls, no randomness.
- Never mutates prior outputs (each is converted to a fresh dict before reads).

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.arv_model_scoped import run_arv_model

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={"sqft": 2_100, "town": "Montclair", "state": "NJ"},
    assumptions={},
    prior_outputs={
        "valuation": {
            "confidence": 0.78,
            "data": {
                "summary": "Briarwood Current Value is about $790,000...",
                "metrics": {"briarwood_current_value": 790_000},
            },
        },
        "renovation_impact": {
            "confidence": 0.65,
            "data": {
                "summary": "Renovation creates ~$250k of value...",
                "metrics": {
                    "current_bcv": 790_000,
                    "renovated_bcv": 1_040_000,
                    "renovation_budget": 150_000,
                    "gross_value_creation": 250_000,
                    "net_value_creation": 100_000,
                    "roi_pct": 66.7,
                    "condition_change": "dated → renovated",
                },
            },
        },
    },
)

payload = run_arv_model(context)
# payload["data"]["arv_snapshot"]["renovated_bcv"]  ==  1_040_000
# payload["data"]["arv_snapshot"]["roi_pct"]        ≈      66.7
# payload["confidence"]                             ==      0.65
```

## Hardcoded Values & TODOs

- Default values `0.0` for `renovation_budget`, `gross_value_creation`, `net_value_creation`, `roi_pct` when missing from upstream — see [arv_model_scoped.py:31-34](arv_model_scoped.py#L31-L34).
- Summary template at [arv_model_scoped.py:89-94](arv_model_scoped.py#L89-L94) is fixed prose; no localization.

## Blockers for Tool Use

- None for normal invocation. Missing priors and internal exceptions degrade to canonical error / fallback payloads (see Invariants) rather than propagating.

## Notes

- **Output schema and behavior contradict audit docs** ([DECISIONS.md](../../DECISIONS.md) 2026-04-24). The audit's framing ("internally: comparable_sales") describes a different design — possibly an earlier intent for a stand-alone ARV model rather than a composite wrapper.
- The `renovated_bcv` field is the conceptual ARV but the field name does not match either common industry usage or the audit doc's `estimated_arv`. When/if this module is rewritten or the audit is reconciled, picking a single canonical name would reduce confusion.
- Tests: covered indirectly via [tests/test_execution_v2.py](../../tests/test_execution_v2.py) and orchestrator suites.
- No direct LLM calls in the wrapper; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: replaced `_require_prior_output` raise with missing-priors degradation via `module_payload_from_missing_prior`; wrapped body in `try/except` for internal exceptions. Composite now treats a prior with `mode in {"error","fallback"}` as missing. Added [tests/modules/test_arv_model_isolated.py](../../tests/modules/test_arv_model_isolated.py). See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."

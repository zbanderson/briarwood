# hold_to_rent — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY (transitional composite)
**Registry:** scoped

## Purpose

`hold_to_rent` is a transitional composite wrapper that packages the already-produced `carry_cost` and `rent_stabilization` outputs into a single hold-path payload for synthesis. It introduces no new math — the carry economics live in `carry_cost`, the rental absorption signals live in `rent_stabilization`, and this module reads both, projects the salient fields into a `hold_path_snapshot` (monthly cash flow, cap rate, rental ease label/score, days-to-rent), and surfaces a `min`-of-confidences rollup. Call this tool whenever the user's intent is a hold-and-rent strategy question; ensure both prerequisites have run first because this module raises `ValueError` if either is missing.

## Location

- **Entry point:** [briarwood/modules/hold_to_rent.py:10](hold_to_rent.py#L10) — `run_hold_to_rent(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:111-118](../execution/registry.py#L111-L118) — `ModuleSpec(name="hold_to_rent", depends_on=["carry_cost", "rent_stabilization"], required_context_keys=["property_data", "assumptions"], runner=run_hold_to_rent)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316). No internal schema beyond the inline `hold_path_snapshot` dict.

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `STRATEGY` — always called; this is the rent-and-hold strategy anchor.
- `PROJECTION` — called when the user asks about future rental cash-flow viability.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`, `LOOKUP`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)). This module does NOT convert to `PropertyInput`; it reads only `prior_outputs`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.prior_outputs.carry_cost` | `dict` | required | executor (via `depends_on`) | Read at [hold_to_rent.py:18](hold_to_rent.py#L18); missing causes `ValueError`. |
| `context.prior_outputs.rent_stabilization` | `dict` | required | executor (via `depends_on`) | Read at [hold_to_rent.py:19](hold_to_rent.py#L19); missing causes `ValueError`. |
| `context.property_data` / `context.assumptions` | `dict` | required (per registry) | router / session | Required by registry but not directly read by this runner. |
| `context.market_context` | `dict` | optional | — | Accepted via `optional_context_keys`. |

## Outputs

`run_hold_to_rent` returns `ModulePayload.model_dump()`. The payload's `data` is constructed inline at [hold_to_rent.py:26-67](hold_to_rent.py#L26-L67):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `module_name` | `str` | — | `"hold_to_rent"`. |
| `summary` | `str` | prose | Concatenation of carry summary + stabilization summary via `_join_summary`. |
| `carry_cost.summary` / `metrics` / `confidence` | mixed | — | Echoed sub-dict from prior `carry_cost` output. |
| `rent_stabilization.summary` / `metrics` / `confidence` | mixed | — | Echoed sub-dict from prior `rent_stabilization` output. |
| `hold_path_snapshot.monthly_cash_flow` | `float \| None` | USD/month | From `carry_cost.metrics.monthly_cash_flow`. |
| `hold_path_snapshot.cap_rate` | `float \| None` | fraction | From `carry_cost.metrics.cap_rate`. |
| `hold_path_snapshot.rental_ease_label` | `str \| None` | enum | From `rent_stabilization.metrics.rental_ease_label`. |
| `hold_path_snapshot.rental_ease_score` | `float \| None` | 0-1 | From `rent_stabilization.metrics.rental_ease_score`. |
| `hold_path_snapshot.estimated_days_to_rent` | `int \| None` | days | From `rent_stabilization.metrics.estimated_days_to_rent`. |
| `confidence` | `float \| None` | 0-1 | `min(carry_cost.confidence, rent_stabilization.confidence)`, rounded to 4 decimals. |
| `confidence_band` | `str` | enum | Per `confidence_band` at [scoped_common.py:152-161](scoped_common.py#L152-L161). |
| `mode` | `str` | enum | `"partial"` when any warnings merged, else `"full"` ([hold_to_rent.py:55](hold_to_rent.py#L55)). |
| `missing_inputs` | `list[str]` | — | Concatenated from both prior outputs. |
| `estimated_inputs` | `list[str]` | — | Concatenated from both prior outputs. |
| `warnings` | `list[str]` | — | Deduplicated merge from both prior outputs. |
| `assumptions_used.composite_from_prior_outputs` | `bool` | — | Always `True`. |
| `assumptions_used.required_prior_modules` | `list[str]` | — | `["carry_cost", "rent_stabilization"]`. |

**Note on output shape:** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) describe outputs `hold_to_rent_viability: float` and `cash_flow_metrics: dict`. Those field names do NOT exist in the actual payload. See [DECISIONS.md](../../DECISIONS.md) entry "hold_to_rent output schema mismatch in audit docs" (2026-04-24).

## Dependencies

- **Requires (inputs):** `carry_cost`, `rent_stabilization` — declared at [registry.py:113](../execution/registry.py#L113) AND enforced at runtime via `_require_prior_output` at [hold_to_rent.py:71-77](hold_to_rent.py#L71-L77).
- **Benefits from (optional):** `market_context`.
- **Calls internally:** none.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none directly.

## Invariants

- **Never raises on missing or degraded priors.** Follows the canonical error contract (DECISIONS.md 2026-04-24): when either prior is absent OR has `mode in {"error","fallback"}`, returns `module_payload_from_missing_prior` — `mode="error"`, `confidence=None`, `missing_inputs=[...]`. On internal exceptions returns `module_payload_from_error` — `mode="fallback"`, `confidence=0.08`.
- `confidence` is the minimum of the two prior confidences; `None` when neither is numeric.
- `mode` is exactly `"partial"` or `"full"` based on whether warnings merged.
- Warnings are deduplicated by string equality at [hold_to_rent.py:91-101](hold_to_rent.py#L91-L101).
- Deterministic per input; no LLM calls, no randomness.
- Never mutates prior outputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.hold_to_rent import run_hold_to_rent

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={"sqft": 2_100, "town": "Montclair", "state": "NJ"},
    assumptions={},
    prior_outputs={
        "carry_cost": {
            "confidence": 0.72,
            "data": {
                "summary": "Monthly carry $5,800; cash flow -$1,600.",
                "metrics": {"monthly_cash_flow": -1_600, "cap_rate": 0.046},
            },
        },
        "rent_stabilization": {
            "confidence": 0.66,
            "data": {
                "summary": "Rental absorption is moderate.",
                "metrics": {"rental_ease_label": "moderate", "rental_ease_score": 3.2, "estimated_days_to_rent": 28},
            },
        },
    },
)

payload = run_hold_to_rent(context)
# payload["data"]["hold_path_snapshot"]["monthly_cash_flow"]    == -1_600
# payload["data"]["hold_path_snapshot"]["rental_ease_label"]    == "moderate"
# payload["confidence"]                                         ==  0.66
# payload["mode"]                                               == "full"   (no warnings)
```

## Hardcoded Values & TODOs

- No constants in this wrapper. All values pass through from prior outputs.
- `mode` is computed twice (line 55 in the constructor's keyword args and again via `_merge_warnings` for `confidence_band`); the duplicated call is cheap but worth noting if this module is rewritten.

## Blockers for Tool Use

- None for normal invocation. Missing priors and internal exceptions degrade to canonical error / fallback payloads (see Invariants) rather than propagating.

## Notes

- **Output schema contradicts audit docs** ([DECISIONS.md](../../DECISIONS.md) 2026-04-24 entry).
- This is explicitly a **transitional composite wrapper** per the docstring at [hold_to_rent.py:11-16](hold_to_rent.py#L11-L16). A future rewrite that adds independent hold-vs-flip math would change the contract here — surface as a "Contract change:" entry in the changelog when that lands.
- Tests: covered indirectly via [tests/test_execution_v2.py](../../tests/test_execution_v2.py).
- No direct LLM calls in the wrapper; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: replaced `_require_prior_output` raise with missing-priors degradation via `module_payload_from_missing_prior`; wrapped body in `try/except`. Composite treats a prior with `mode in {"error","fallback"}` as missing. Added [tests/modules/test_hold_to_rent_isolated.py](../../tests/modules/test_hold_to_rent_isolated.py). See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."

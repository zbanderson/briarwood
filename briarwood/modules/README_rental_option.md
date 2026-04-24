# rental_option — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`rental_option` composes rental-absorption ease with income-support underwriting into a single rental-path payload. It runs `IncomeSupportModule` (price-to-rent, cash flow, DSCR-style signals) and `RentalEaseModule` (liquidity, demand depth, rent support, scarcity) on the same property, then applies a bounded confidence nudge (≤ 3%) using the county's `employment` macro signal. The output anchors the rent-as-an-option strategy answer: "if you rent instead of owner-occupying, how viable is that path?" Call this tool whenever the user's intent is a rent-focused lookup or strategy question; it is the dependency behind `rental_option → valuation` in the scoped DAG.

## When to call `rental_option` vs. `income_support`

`rental_option` and `income_support` share an engine (`IncomeSupportModule`). They exist as distinct scoped tools because they answer different questions.

**Call `rental_option` when:**
- The user is asking *"if you rent it instead of owner-occupying, how viable is that path?"* — a composite `STRATEGY` / `RENT_LOOKUP` answer.
- The answer needs rent-absorption ease (liquidity, days-to-rent, demand depth) alongside the underwriting ratio.
- The employment-macro confidence nudge should apply.

**Call `income_support` when:**
- The user is asking a `LOOKUP`-style underwriting question: *"what's the DSCR?"*, *"what's the rent coverage?"*, *"what's the price-to-rent?"*
- A downstream module needs a raw income-support ratio without the rental-ease context.

**If unsure which applies, default to `rental_option`.** The composite view is safer when intent is ambiguous; `income_support` is the narrower raw-ratio lookup.

**Anti-recursion:** `rental_option` calls `IncomeSupportModule` in-process at [rental_option_scoped.py:26-32](rental_option_scoped.py#L26-L32), NOT via the scoped `income_support` tool. This is deliberate — see [README_income_support.md](README_income_support.md#anti-recursion-contract) for the full contract.

## Location

- **Entry point:** [briarwood/modules/rental_option_scoped.py:16](rental_option_scoped.py#L16) — `run_rental_option(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:95-102](../execution/registry.py#L95-L102) — `ModuleSpec(name="rental_option", depends_on=["valuation"], required_context_keys=["property_data"], runner=run_rental_option)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); inner shapes from `IncomeSupportModule` ([briarwood/modules/income_support.py](income_support.py)) and `RentalEaseModule` ([briarwood/modules/rental_ease.py:15](rental_ease.py#L15)). Macro reader at [briarwood/modules/macro_reader.py:78](macro_reader.py#L78).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RENT_LOOKUP` — always called; produces the rent-as-an-option viability payload.
- `STRATEGY` — called for rent-vs-buy and hold-to-rent paths.
- `PROJECTION` — sometimes called when the user asks about future rent trajectory.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.purchase_price` | `float` | required | user / listing facts | Required field per error branch at [rental_option_scoped.py:57](rental_option_scoped.py#L57). |
| `context.property_data.estimated_monthly_rent` | `float` | required | user / listing / rent context | Same. |
| `context.property_data.sqft` / `beds` / `baths` | mixed | required | listing facts | Same. |
| `context.property_data.down_payment_percent` / `interest_rate` / `loan_term_years` / `taxes` / `insurance` / `monthly_hoa` | mixed | recommended | assumptions | Consumed inside `IncomeSupportModule`; absence degrades confidence and `financing_complete`. |
| `context.property_data.town` / `state` | `str` | recommended | resolver | Used by rent-context agents. |
| `context.prior_outputs.valuation` | `dict` | optional | executor (via `depends_on=["valuation"]`) | Declared dependency orders valuation before this module; rental_option itself does not read valuation fields directly. |
| `context.macro_context.employment` | signed `float` | optional | macro reader (FRED) | Drives the ≤ 3% confidence nudge at [rental_option_scoped.py:30-35](rental_option_scoped.py#L30-L35). |
| `context.market_context` / `comp_context` | `dict` | optional | router / session | Accepted via `optional_context_keys`. |

## Outputs

`run_rental_option` returns `ModulePayload.model_dump()`. Salient fields in the payload (from `RentalEaseModule` output plus grafted extras):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `rental_ease_label` | `str` | enum | `"easy" \| "moderate" \| "difficult" \| "unavailable"`. |
| `liquidity_score` / `demand_depth_score` / `rent_support_score` / `structural_support_score` | `float` | 0-1 | From `RentalEaseModule` output at [rental_ease.py:111-116](rental_ease.py#L111-L116). |
| `estimated_days_to_rent` | `int \| None` | days | Same. |
| `scarcity_support_score` | `float` | 0-1 | Surfaced by the `RentalEaseModule` → internal `ScarcitySupportModule` composition. |
| `zillow_context_used` | `bool` | — | Same. |
| `confidence` | `float` | 0-1 | Outer `ModulePayload.confidence`, overridden at [rental_option_scoped.py:59-62](rental_option_scoped.py#L59-L62) by the macro-nudged value when the nudge fires. |
| `summary` | `str` | prose | Narrative from `RentalEaseModule`. |
| `extra_data.income_support.score` | `float \| None` | 0-1 | From `IncomeSupportModule`. |
| `extra_data.income_support.confidence` | `float` | 0-1 | Same. |
| `extra_data.income_support.summary` | `str` | prose | Same. |
| `extra_data.income_support.metrics` | `dict` | mixed | Rent source, cash flow, price-to-rent, gross yield, DSCR-style fields. |
| `extra_data.macro_nudge` | `dict` | — | `apply_macro_nudge` telemetry: signal, applied delta, adjusted confidence. |
| `warnings` | `list[str]` | — | Fallback warnings only. |
| `assumptions_used.legacy_module` | `str` | — | `"IncomeSupportModule"`. |
| `assumptions_used.supporting_module` | `str` | — | `"RentalEaseModule"`. |
| `assumptions_used.macro_context_used` | `bool` | — | True when an `employment` macro signal was present. |

**Note on output shape:** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) says "rental viability metrics"; [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) lists `rental_viability_score: float` and `rental_viability_metrics: dict` as outputs. Those specific field names do NOT exist in the current payload. See [DECISIONS.md](../../DECISIONS.md) entry "rental_option output schema mismatch in audit docs" (2026-04-24).

## Dependencies

- **Requires (inputs):** `valuation` (via `depends_on` at [registry.py:97](../execution/registry.py#L97)) — the declared dependency orders valuation before rental_option but is not actually consumed inside this runner. The edge exists to guarantee that any consumer of both modules sees a consistent execution order.
- **Benefits from (optional):** `market_context`, `comp_context`, `macro_context.employment`.
- **Calls internally:** `IncomeSupportModule` at [briarwood/modules/income_support.py](income_support.py); `RentalEaseModule` at [briarwood/modules/rental_ease.py:15](rental_ease.py#L15) (which itself calls `ScarcitySupportModule` at [rental_ease.py:40](rental_ease.py#L40)); `apply_macro_nudge` at [briarwood/modules/macro_reader.py:78](macro_reader.py#L78).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none directly — `hold_to_rent` depends on `rent_stabilization` + `carry_cost`, not on `rental_option`.

## Invariants

- Never raises. All exceptions are caught at [rental_option_scoped.py:64-72](rental_option_scoped.py#L64-L72) and replaced with a sparse-input fallback payload.
- Macro nudge is bounded: `MACRO_MAX_NUDGE = 0.03` at [rental_option_scoped.py:13](rental_option_scoped.py#L13). `apply_macro_nudge` clamps the employment signal so the shift never exceeds ±3%.
- `confidence` is in `[0.0, 1.0]` after the nudge; rounded to 4 decimals at [rental_option_scoped.py:61](rental_option_scoped.py#L61).
- `rental_ease_label` is `"unavailable"` when rent context cannot be established.
- Deterministic per input when macro context is fixed; no LLM calls in the wrapper itself.
- Never mutates its inputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.rental_option_scoped import run_rental_option

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "purchase_price": 850_000,
        "estimated_monthly_rent": 4_200,
        "sqft": 2_100,
        "beds": 4,
        "baths": 2.5,
        "town": "Montclair",
        "state": "NJ",
        "down_payment_percent": 0.20,
        "interest_rate": 0.0675,
        "loan_term_years": 30,
        "taxes": 14_400,
        "insurance": 2_100,
    },
    macro_context={"employment": {"signal": 0.08, "source": "FRED"}},
)

payload = run_rental_option(context)
# payload["output"]["rental_ease_label"]             == "moderate"
# payload["output"]["liquidity_score"]               ≈ 0.62
# payload["extra_data"]["income_support"]["metrics"]["price_to_rent"] ≈ 16.9
# payload["extra_data"]["macro_nudge"]["applied_nudge"]               ≈ 0.005
# payload["confidence"]                              ∈ [0, 1]
```

## Hardcoded Values & TODOs

- `MACRO_MAX_NUDGE = 0.03` at [rental_option_scoped.py:13](rental_option_scoped.py#L13) — per-dimension cap on the employment macro confidence adjustment.
- Required fields list hardcoded in both the success and fallback paths: `["purchase_price", "estimated_monthly_rent", "sqft", "beds", "baths"]`.
- The declared `depends_on=["valuation"]` at [registry.py:97](../execution/registry.py#L97) is not backed by reads inside this runner. Either the declaration is ordering-only, or a future change will begin consuming valuation output.

## Blockers for Tool Use

- None. This module is callable in isolation via `run_rental_option(context)` with a populated `ExecutionContext`. The `valuation` dependency is ordering-only and the runner does not require valuation outputs to exist.

## Notes

- **Output schema contradicts audit docs** ([DECISIONS.md](../../DECISIONS.md) 2026-04-24). Reconcile when audit docs are next updated.
- The `IncomeSupportModule` path consumes rent-context agents that may be file-backed; configuration lives inside that module (not this wrapper).
- Tests: covered indirectly via [tests/test_execution_v2.py](../../tests/test_execution_v2.py) and orchestrator suites.
- No LLM calls in this wrapper; cost is zero at this layer.

## Changelog

### 2026-04-24
- Initial README created.
- Dependency change: removed `valuation` from `depends_on` at [registry.py:97](../execution/registry.py#L97). The declared dependency was never consumed by the runner or its helper chain (`RentalEaseModule`, `IncomeSupportModule`), and the full test suite remains green without the ordering constraint.
- Added disambiguation section pointing at the `income_support` scoped tool introduced in Handoff 3. Reciprocal section lives in [README_income_support.md](README_income_support.md). Anti-recursion inline comment added at [rental_option_scoped.py:26-32](rental_option_scoped.py#L26-L32). Reference: [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 8.

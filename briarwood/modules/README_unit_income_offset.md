# unit_income_offset — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`unit_income_offset` surfaces accessory-unit income evidence for properties with structured ADU / back-house / multi-unit signals, alongside the carrying cost the offset would be applied against. It is **not** a standalone capitalization model — it relies on `ComparableSalesModule`'s built-in additional-unit decomposition (which is where the `0.08` cap rate and `0.30` expense ratio actually live) and reads the prior `carry_cost` payload from `prior_outputs` to surface monthly cost/cash-flow context. Call this tool whenever the user's intent involves an ADU "house-hack" question, a multi-unit income offset, or any decision-tier conversation where accessory income changes the carry math; it is meaningful only when the property has a structured accessory-unit signal.

## Location

- **Entry point:** [briarwood/modules/unit_income_offset.py:11](unit_income_offset.py#L11) — `run_unit_income_offset(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:143-150](../execution/registry.py#L143-L150) — `ModuleSpec(name="unit_income_offset", depends_on=["carry_cost"], required_context_keys=["property_data", "assumptions"], runner=run_unit_income_offset)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); inner `ComparableSalesModule` payload shape at [briarwood/modules/comparable_sales.py](comparable_sales.py).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `STRATEGY` — called for ADU / multi-unit "house-hack" paths.
- `DECISION` — called as supporting evidence for owner-occupancy + accessory-income verdicts.
- `EDGE` — called for edge questions about whether accessory income materially changes a verdict.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.has_back_house` / `adu_type` / `additional_units` | mixed | strongly recommended | listing facts | Drives `has_accessory_unit_signal`; absence triggers a warning. |
| `context.property_data.back_house_monthly_rent` | `float \| None` | optional | listing / user | Surfaced unchanged into `offset_snapshot`. |
| `context.property_data.unit_rents` | `list` | optional | listing / user | Surfaced unchanged into `offset_snapshot`. |
| `context.property_data.purchase_price` / `sqft` / `town` / `state` | mixed | required | listing facts | Needed by `ComparableSalesModule`. |
| `context.prior_outputs.carry_cost` | `dict` | optional | executor (via `depends_on=["carry_cost"]`) | Read for `monthly_total_cost`, `monthly_cash_flow`, and `confidence` at [unit_income_offset.py:21-28](unit_income_offset.py#L21-L28). Absence triggers a warning. |
| `context.assumptions` | `dict` | required (per registry) | router / session | Registry requires the key; contents are not read directly. |
| `context.comp_context` | `dict` | optional | earlier comp lookups | Accepted via `optional_context_keys`. |

## Outputs

`run_unit_income_offset` returns `ModulePayload.model_dump()`. The payload's `data` dict is constructed inline at [unit_income_offset.py:30-56](unit_income_offset.py#L30-L56):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `module_name` | `str` | — | `"unit_income_offset"`. |
| `summary` | `str` | prose | Mirrors `comparable_result.summary`. |
| `comparable_sales.summary` | `str` | prose | From `ComparableSalesModule`. |
| `comparable_sales.metrics` | `dict` | mixed | Includes `comparable_value`, `comp_count`, hybrid detection metadata, etc. |
| `comparable_sales.confidence` | `float` | 0-1 | Same. |
| `offset_snapshot.has_accessory_unit_signal` | `bool` | — | True when `has_back_house`, `adu_type`, or any `additional_units` is present. |
| `offset_snapshot.additional_unit_income_value` | `float \| None` | USD | Capitalized unit-income value from the comparable-sales hybrid decomposition. |
| `offset_snapshot.additional_unit_count` | `int \| None` | — | Same source. |
| `offset_snapshot.back_house_monthly_rent` | `float \| None` | USD/month | Passthrough from `property_input.back_house_monthly_rent`. |
| `offset_snapshot.unit_rents` | `list` | mixed | Passthrough from `property_input.unit_rents`. |
| `offset_snapshot.monthly_total_cost` | `float \| None` | USD/month | From prior `carry_cost.data.metrics.monthly_total_cost`; `None` when carry_cost output absent. |
| `offset_snapshot.monthly_cash_flow` | `float \| None` | USD/month | From prior `carry_cost.data.metrics.monthly_cash_flow`; `None` when carry_cost output absent. |
| `confidence` | `float` | 0-1 | `min(comparable_confidence, carry_cost_confidence)`; falls through to `comparable_confidence` alone when carry_cost is absent. Rounded to 4 decimals at [unit_income_offset.py:74-75](unit_income_offset.py#L74-L75). |
| `warnings` | `list[str]` | — | "No structured accessory-unit signal..." when no signal; "Carry-cost output was not available..." when prior carry_cost missing. |
| `assumptions_used.legacy_module` | `str` | — | `"ComparableSalesModule"`. |
| `assumptions_used.uses_prior_carry_cost_output` | `bool` | — | True when prior carry_cost output was a dict. |

**Note on output shape:** [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) lists outputs `offset_monthly_income`, `offset_annual_income`, `cap_rate_assumed`. Those fields do NOT exist in the actual payload. See [DECISIONS.md](../../DECISIONS.md) entry "unit_income_offset drift: output schema and ADU constant location" (2026-04-24).

## Dependencies

- **Requires (inputs):** `carry_cost` (via `depends_on` at [registry.py:145](../execution/registry.py#L145)). Unlike `rental_option`, this dependency IS actually consumed — read at [unit_income_offset.py:21](unit_income_offset.py#L21) and surfaced into `offset_snapshot`.
- **Benefits from (optional):** `comp_context`.
- **Calls internally:** `ComparableSalesModule` at [briarwood/modules/comparable_sales.py](comparable_sales.py).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none directly.

## Invariants

- **Does not raise on most inputs.** The wrapper does not have a try/except, but `ComparableSalesModule.run` is defensive; missing accessory signals produce a non-erroring payload with `additional_unit_income_value=None` and `has_accessory_unit_signal=False`.
- `confidence` is always in `[0.0, 1.0]`; rounded to 4 decimals.
- When `carry_cost` is absent in `prior_outputs`, the confidence drops to `comparable_confidence` alone (no carry penalty applied).
- Warnings are always non-None (empty list when no condition triggered).
- Deterministic per input; no LLM calls in the wrapper.
- Never mutates its inputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.unit_income_offset import run_unit_income_offset

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "purchase_price": 850_000,
        "sqft": 2_400,
        "beds": 4,
        "baths": 3,
        "town": "Montclair",
        "state": "NJ",
        "has_back_house": True,
        "back_house_monthly_rent": 1_900,
        "adu_type": "detached_cottage",
    },
    assumptions={},
    prior_outputs={
        "carry_cost": {
            "confidence": 0.72,
            "data": {"metrics": {"monthly_total_cost": 5_800, "monthly_cash_flow": -1_600}},
        }
    },
)

payload = run_unit_income_offset(context)
# payload["data"]["offset_snapshot"]["has_accessory_unit_signal"]   == True
# payload["data"]["offset_snapshot"]["additional_unit_income_value"] ≈ 280_000
# payload["data"]["offset_snapshot"]["monthly_total_cost"]           ==  5_800
# payload["data"]["offset_snapshot"]["monthly_cash_flow"]            == -1_600
# payload["confidence"]                                              ≈   0.71
```

## Hardcoded Values & TODOs

- **No constants live in this wrapper.** The `0.08` ADU cap rate (`_DEFAULT_ADU_CAP_RATE`) and `0.30` expense ratio (`_ADU_EXPENSE_RATIO`) actually live in [briarwood/modules/comparable_sales.py:28](comparable_sales.py#L28) and [briarwood/modules/comparable_sales.py:32](comparable_sales.py#L32). The audit docs locate them in this module and `hybrid_value.py`; that attribution is incorrect — see [DECISIONS.md](../../DECISIONS.md) 2026-04-24 entry.
- The wrapper has no overrides for assumptions; `assumptions` is required by the registry but not read.

## Blockers for Tool Use

- None for invocation. The module degrades cleanly to "no signal" when no accessory-unit data is present.

## Notes

- **Output schema and constant location contradict the audit docs.** See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 entry. When the audit docs are reconciled, this module should be re-described as "surfaces accessory-unit income evidence and pairs it with carry-cost context; capitalization happens upstream in `ComparableSalesModule`."
- `ComparableSalesModule` is itself a legacy non-scoped model whose status [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges flags ("ComparableSalesModule is not in the scoped registry"). Promoting it would simplify this wrapper's contract.
- Tests: covered indirectly via [tests/test_execution_v2.py](../../tests/test_execution_v2.py) and orchestrator suites; no isolated test file for this module today.
- No direct LLM calls in the wrapper; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: wrapped body in `try/except` and migrated to the canonical error contract. Internal exceptions now return a `module_payload_from_error` fallback (`mode="fallback"`, `confidence=0.08`) rather than propagating. Added [tests/modules/test_unit_income_offset_degraded.py](../../tests/modules/test_unit_income_offset_degraded.py). See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."

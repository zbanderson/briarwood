# margin_sensitivity — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`margin_sensitivity` is a composite wrapper that builds a six-scenario sensitivity table over the renovation economics produced upstream by `arv_model`, `renovation_impact`, and `carry_cost`. It computes how net profit and ROI shift under budget overruns (+20%, +40%), value misses (-10%, -20%), and a combined stress (Budget +20%, Value -10%), and reports a `breakeven_budget` plus a `budget_overrun_margin_pct` showing how far the budget can grow before net value creation hits zero. Call this tool whenever the user's intent is "how risky is this renovation, and where does it break?"; it raises `ValueError` if any of the three prerequisites is missing.

## Location

- **Entry point:** [briarwood/modules/margin_sensitivity_scoped.py:9](margin_sensitivity_scoped.py#L9) — `run_margin_sensitivity(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:135-142](../execution/registry.py#L135-L142) — `ModuleSpec(name="margin_sensitivity", depends_on=["arv_model", "renovation_impact", "carry_cost"], required_context_keys=["property_data", "assumptions"], runner=run_margin_sensitivity)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316). No internal schema beyond the inline `sensitivity_scenarios` list and `margin_snapshot` dict.

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `STRATEGY` — called for renovation / flip paths.
- `RISK` — called when the user asks about renovation downside.
- `DECISION` — called for verdicts on value-add properties.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)). This module reads only `prior_outputs`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.prior_outputs.arv_model` | `dict` | required | executor (via `depends_on`) | Read at [margin_sensitivity_scoped.py:17](margin_sensitivity_scoped.py#L17); missing causes `ValueError`. |
| `context.prior_outputs.renovation_impact` | `dict` | required | executor (via `depends_on`) | Read at [margin_sensitivity_scoped.py:18](margin_sensitivity_scoped.py#L18); missing causes `ValueError`. |
| `context.prior_outputs.carry_cost` | `dict` | required | executor (via `depends_on`) | Read at [margin_sensitivity_scoped.py:19](margin_sensitivity_scoped.py#L19); missing causes `ValueError`. |
| `context.property_data` / `context.assumptions` | `dict` | required (per registry) | router / session | Required by registry but not directly read. |

## Outputs

`run_margin_sensitivity` returns `ModulePayload.model_dump()`. The payload's `data` is constructed inline at [margin_sensitivity_scoped.py:62-88](margin_sensitivity_scoped.py#L62-L88):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `module_name` | `str` | — | `"margin_sensitivity"`. |
| `summary` | `str` | prose | Built by `_build_summary` at [margin_sensitivity_scoped.py:131-153](margin_sensitivity_scoped.py#L131-L153); names base ROI, margin tier (`comfortable`, `moderate`, `thin`, `negative`), and total holding cost. |
| `sensitivity_scenarios` | `list[dict]` | — | Six scenarios from `_build_scenarios` at [margin_sensitivity_scoped.py:92-128](margin_sensitivity_scoped.py#L92-L128). Each entry: `label`, `renovation_budget`, `gross_value_creation`, `hold_cost`, `net_profit`, `roi_pct`, `profitable`. Labels: `"Base case"`, `"Budget +20%"`, `"Budget +40%"`, `"Value -10%"`, `"Value -20%"`, `"Budget +20%, Value -10%"`. |
| `margin_snapshot.renovated_bcv` | `float` | USD | From `arv_snapshot.renovated_bcv`. |
| `margin_snapshot.current_bcv` | `float` | USD | From `arv_snapshot.current_bcv`. |
| `margin_snapshot.renovation_budget` | `float` | USD | Same. |
| `margin_snapshot.gross_value_creation` | `float` | USD | `renovated_bcv - current_bcv`. |
| `margin_snapshot.monthly_carry` | `float` | USD/month | Pulled from `carry_cost` output's `monthly_total_cost` key at [margin_sensitivity_scoped.py:33](margin_sensitivity_scoped.py#L33). |
| `margin_snapshot.holding_months` | `int` | months | Hardcoded `6` at [margin_sensitivity_scoped.py:34](margin_sensitivity_scoped.py#L34). |
| `margin_snapshot.total_hold_cost` | `float` | USD | `monthly_carry * holding_months`. |
| `margin_snapshot.breakeven_budget` | `float` | USD | `gross_value_creation - total_hold_cost`. |
| `margin_snapshot.budget_overrun_margin_pct` | `float` | percent | `(breakeven_budget - renovation_budget) / renovation_budget * 100`. |
| `margin_snapshot.base_roi_pct` | `float` | percent | `arv_snapshot.roi_pct`. |
| `confidence` | `float \| None` | 0-1 | `min(arv.confidence, renovation.confidence, carry.confidence)`, rounded to 4 decimals. |
| `warnings` | `list[str]` | — | Deduplicated merge from all three prior outputs. |
| `assumptions_used.composite_from_prior_outputs` | `bool` | — | Always `True`. |
| `assumptions_used.required_prior_modules` | `list[str]` | — | `["arv_model", "renovation_impact", "carry_cost"]`. |
| `assumptions_used.holding_months_assumption` | `int` | months | `6`. |

**Note on output shape:** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) describe outputs `margin_at_base_case`, `margin_at_90pct_arv`, `margin_at_110pct_cost`, `break_even_thresholds`. None of those exact field names exist; the conceptual coverage is split across the six labeled scenarios in `sensitivity_scenarios` and `breakeven_budget` in `margin_snapshot`. Audit docs need updating.

## Dependencies

- **Requires (inputs):** `arv_model`, `renovation_impact`, `carry_cost` — declared at [registry.py:137](../execution/registry.py#L137) AND enforced at runtime via `_require_prior_output` at [margin_sensitivity_scoped.py:156-162](margin_sensitivity_scoped.py#L156-L162).
- **Benefits from (optional):** none.
- **Calls internally:** none.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none directly.

## Invariants

- **Never raises on missing or degraded priors.** Follows the canonical error contract (DECISIONS.md 2026-04-24): when any prior is absent OR has `mode in {"error","fallback"}`, returns `module_payload_from_missing_prior` — `mode="error"`, `confidence=None`, `missing_inputs=[...]`. Internal exceptions return `module_payload_from_error` — `mode="fallback"`, `confidence=0.08`.
- `confidence` is the minimum of the three prior confidences; `None` when none are numeric.
- `holding_months` is fixed at `6` and surfaced in `assumptions_used.holding_months_assumption`.
- Each scenario in `sensitivity_scenarios` has the same six keys; `profitable` is `net_profit > 0`.
- `_build_summary` margin labels: `> 30% → "comfortable"`, `> 10% → "moderate"`, `> 0% → "thin"`, `<= 0% → "negative"`.
- Deterministic per input; no LLM calls, no randomness.
- Never mutates prior outputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.margin_sensitivity_scoped import run_margin_sensitivity

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={"sqft": 2_100, "town": "Montclair", "state": "NJ"},
    assumptions={},
    prior_outputs={
        "arv_model": {"confidence": 0.65, "data": {"arv_snapshot": {
            "renovated_bcv": 1_040_000, "current_bcv": 790_000,
            "renovation_budget": 150_000, "roi_pct": 66.7,
        }}},
        "renovation_impact": {"confidence": 0.65, "data": {"metrics": {}}},
        "carry_cost": {"confidence": 0.72, "data": {"metrics": {"monthly_total_cost": 5_800}}},
    },
)

payload = run_margin_sensitivity(context)
# payload["data"]["sensitivity_scenarios"][0]["label"]            == "Base case"
# payload["data"]["margin_snapshot"]["monthly_carry"]             == 5_800.0
# payload["data"]["margin_snapshot"]["total_hold_cost"]           == 34_800.0
# payload["data"]["margin_snapshot"]["breakeven_budget"]          == 215_200.0   (gross 250k minus 34.8k carry)
# payload["data"]["margin_snapshot"]["budget_overrun_margin_pct"] ≈  43.5
# payload["confidence"]                                           ==   0.65
```

## Hardcoded Values & TODOs

- `holding_months = 6` at [margin_sensitivity_scoped.py:34](margin_sensitivity_scoped.py#L34) — comment says "standard renovation + sale horizon"; not config-overridable.
- Six scenario multipliers hardcoded in `_build_scenarios` at [margin_sensitivity_scoped.py:106-113](margin_sensitivity_scoped.py#L106-L113).
- Margin tier thresholds (30 / 10 / 0 percent) hardcoded in `_build_summary` at [margin_sensitivity_scoped.py:139-146](margin_sensitivity_scoped.py#L139-L146).
- All three thresholds and the scenarios are deterministic — there is no input that lets the user request additional sensitivity bands.

## Blockers for Tool Use

- None for normal invocation. Missing priors and internal exceptions degrade to canonical error / fallback payloads (see Invariants) rather than propagating.

## Notes

- **Output schema drifts from audit docs** — see "Note on output shape" above.
- Isolated tests live at [tests/modules/test_margin_sensitivity_isolated.py](../../tests/modules/test_margin_sensitivity_isolated.py) — they assert the carry drag is actually applied to `monthly_carry`, `total_hold_cost`, `breakeven_budget`, `budget_overrun_margin_pct`, and every scenario's `hold_cost`.
- No direct LLM calls in this wrapper; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Fixed: `monthly_carry` read the wrong carry-cost key (`total_monthly_cost` → `monthly_total_cost`). Contract unchanged; output fields (`monthly_carry`, `total_hold_cost`, `breakeven_budget`, scenario `net_profit`, `budget_overrun_margin_pct`) are now correctly populated. Added [tests/modules/test_margin_sensitivity_isolated.py](../../tests/modules/test_margin_sensitivity_isolated.py) to prevent regression.
- Contract change: replaced `_require_prior_output` raise with missing-priors degradation via `module_payload_from_missing_prior`; wrapped body in `try/except`. Composite treats a prior with `mode in {"error","fallback"}` as missing. See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."

# opportunity_cost — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`opportunity_cost` is the capital-allocation-vs-alternatives view (Q5 producer). Given the property's entry basis (from `valuation` or the user's declared purchase price) and base-case forward growth (from `resale_scenario`), it projects the property's terminal value over the configured hold horizon and compares it to two passive benchmarks: T-bill (`0.042` default annual return) and S&P 500 (`0.07` default annual return). The comparison is **appreciation-only and gross of tax/leverage** — it answers "does the asset itself outgrow the benchmark?" not "does the levered-and-rented deal IRR clear the benchmark?" Call this tool when the user's intent involves a hold-decision, a "should I just buy index funds instead?" framing, or any projection question where the alternative-investment context matters.

## Location

- **Entry point:** [briarwood/modules/opportunity_cost.py:38](opportunity_cost.py#L38) — `run_opportunity_cost(context: ExecutionContext, *, settings: BenchmarkSettings | None = None) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:159-170](../execution/registry.py#L159-L170) — `ModuleSpec(name="opportunity_cost", depends_on=["valuation", "resale_scenario"], required_context_keys=["property_data"], runner=run_opportunity_cost)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); benchmark settings at [briarwood/settings.py:96](../settings.py#L96) — `BenchmarkSettings`, `DEFAULT_BENCHMARK_SETTINGS`.

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `PROJECTION` — always called; produces the forward terminal-value comparison.
- `STRATEGY` — called for hold-vs-alternative-allocation paths.
- `DECISION` — called when the verdict needs the alternative-allocation context.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)). This module reads `prior_outputs` and a few raw fields directly.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.prior_outputs.valuation` | `dict` | required | executor (via `depends_on`) | Read at [opportunity_cost.py:51](opportunity_cost.py#L51). Missing yields a `mode="error"` payload, not a raise. |
| `context.prior_outputs.resale_scenario` | `dict` | required | executor (via `depends_on`) | Read at [opportunity_cost.py:52](opportunity_cost.py#L52). Same. |
| `context.property_data.purchase_price` | `float` | recommended | listing facts | Preferred entry basis at [opportunity_cost.py:198-200](opportunity_cost.py#L198-L200). |
| `context.property_data` (other fields) | `dict` | required (per registry) | router / session | Required by registry; mostly indirect via the prior outputs. |
| `context.assumptions.hold_period_years` | `int` | optional | router / session | Resolves the hold horizon at [opportunity_cost.py:218-232](opportunity_cost.py#L218-L232); falls back to `property_data.user_assumptions.hold_period_years`, then `BenchmarkSettings.default_hold_years` (5). |

## Outputs

`run_opportunity_cost` returns `ModulePayload.model_dump()`. The payload's `data.metrics` dict (built at [opportunity_cost.py:154-171](opportunity_cost.py#L154-L171)):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `entry_basis` | `float` | USD | Preferred from `property_data.purchase_price`; falls back to `valuation.metrics.ask_price` → `briarwood_current_value` → `fair_value_base` (see [opportunity_cost.py:190-207](opportunity_cost.py#L190-L207)). |
| `hold_years` | `int` | years | Resolved horizon. |
| `property_cagr` | `float` | fraction | Equals `base_growth_rate` from `resale_scenario` by construction of the constant-growth model. |
| `property_terminal_value` | `float` | USD | `entry_basis * (1 + base_growth_rate) ^ hold_years`. |
| `tbill_annual_return` | `float` | fraction | `BenchmarkSettings.tbill_annual_return` (default `0.042`). |
| `tbill_terminal_value` | `float` | USD | Compounded over `hold_years`. |
| `sp500_annual_return` | `float` | fraction | `BenchmarkSettings.sp500_annual_return` (default `0.07`). |
| `sp500_terminal_value` | `float` | USD | Compounded over `hold_years`. |
| `excess_vs_tbill_bps` | `float` | basis points | `(property_cagr − tbill) * 10000`, rounded to 1 decimal. |
| `excess_vs_sp500_bps` | `float` | basis points | Same. |
| `delta_value_vs_tbill` | `float` | USD | `property_terminal − tbill_terminal`. |
| `delta_value_vs_sp500` | `float` | USD | Same. |
| `dominant_benchmark` | `str` | enum | `"sp500"` when property beats S&P; else `"tbill"` (see selection logic at [opportunity_cost.py:130-145](opportunity_cost.py#L130-L145)). |
| `dominant_excess_bps` | `float` | basis points | Excess vs. the dominant benchmark. |
| `dominant_delta_value` | `float` | USD | Delta vs. the dominant benchmark. |
| `meaningful_excess_bps_threshold` | `float` | basis points | `BenchmarkSettings.meaningful_excess_bps` (default `150.0`). |
| `summary` | `str` | prose | Built by `_format_summary` at [opportunity_cost.py:258-273](opportunity_cost.py#L258-L273); includes property CAGR, hold years, dominant benchmark, signed bps. |
| `confidence` | `float \| None` | 0-1 | `min(valuation.confidence, resale_scenario.confidence)` rounded to 4 decimals; halved when degraded (no terminal computed). |
| `confidence_band` | `str` | enum | Per `confidence_band` at [scoped_common.py:152-161](scoped_common.py#L152-L161). |
| `mode` | `str` | enum | `"full"` | `"partial"` (entry basis or growth rate missing) | `"error"` (prior modules missing). |
| `warnings` | `list[str]` | — | "Entry basis unavailable...", "Base-case growth rate unavailable...", or "Missing prior module output: ..." |
| `assumptions_used.tbill_annual_return` / `sp500_annual_return` | `float` | — | Echoed for trust surface. |
| `assumptions_used.hold_years` | `int` | — | Resolved horizon. |
| `assumptions_used.comparison_mode` | `str` | — | `"appreciation_only"`. |
| `assumptions_used.extrapolates_12mo_forward_rate` | `bool` | — | `True` — explicit flag in trust surface. |
| `assumptions_used.gross_of_tax_and_liquidity` | `bool` | — | `True`. |
| `assumptions_used.required_prior_modules` | `list[str]` | — | `["valuation", "resale_scenario"]`. |

## Dependencies

- **Requires (inputs):** `valuation`, `resale_scenario` — declared at [registry.py:161](../execution/registry.py#L161). Unlike `arv_model` and `margin_sensitivity`, this module does NOT raise when prior outputs are missing — it returns a `mode="error"` payload with `confidence=None`.
- **Benefits from (optional):** `assumptions`, `prior_outputs` (other modules' confidences could anchor here in the future).
- **Calls internally:** none.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none directly.

## Invariants

- Never raises. Missing prior outputs degrade gracefully to `mode="error"`; missing entry basis or growth rate degrade to `mode="partial"`; full computation produces `mode="full"`.
- `confidence` is bounded by `min(valuation.confidence, resale_scenario.confidence)` — the module introduces no new information per its docstring at [opportunity_cost.py:241-242](opportunity_cost.py#L241-L242).
- When degraded (cannot compute terminal), confidence is halved at [opportunity_cost.py:255](opportunity_cost.py#L255).
- The constant-growth assumption is explicit and surfaced in `assumptions_used.extrapolates_12mo_forward_rate` so the trust surface can flag the limitation.
- Dominant-benchmark selection is deterministic: S&P wins when property excess vs. S&P is non-negative; otherwise T-bills.
- Property and benchmark terminals share the same entry basis — this is by construction so the comparison is apples-to-apples on starting capital.
- Deterministic per input; no LLM calls, no randomness.
- Never mutates its inputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.opportunity_cost import run_opportunity_cost

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={"purchase_price": 850_000, "sqft": 2_100, "town": "Montclair", "state": "NJ"},
    assumptions={"hold_period_years": 5},
    prior_outputs={
        "valuation": {"confidence": 0.78, "data": {"metrics": {"briarwood_current_value": 790_000}}},
        "resale_scenario": {"confidence": 0.66, "data": {"metrics": {"base_growth_rate": 0.058}}},
    },
)

payload = run_opportunity_cost(context)
# payload["data"]["metrics"]["property_terminal_value"]   ≈  1_127_000
# payload["data"]["metrics"]["tbill_terminal_value"]      ≈  1_044_000
# payload["data"]["metrics"]["sp500_terminal_value"]      ≈  1_192_000
# payload["data"]["metrics"]["excess_vs_tbill_bps"]       ≈  160
# payload["data"]["metrics"]["excess_vs_sp500_bps"]       ≈ -120
# payload["data"]["metrics"]["dominant_benchmark"]        == "tbill"
# payload["mode"]                                         == "full"
# payload["confidence"]                                   ==  0.66
```

## Hardcoded Values & TODOs

- Defaults from `BenchmarkSettings` at [briarwood/settings.py:96-120](../settings.py#L96-L120):
  - `tbill_annual_return = 0.042`
  - `sp500_annual_return = 0.07`
  - `default_hold_years = 5`
  - `meaningful_excess_bps = 150.0`
- Confidence halving on degraded path at [opportunity_cost.py:255](opportunity_cost.py#L255).
- Entry-basis fallback chain at [opportunity_cost.py:203](opportunity_cost.py#L203): `ask_price` → `briarwood_current_value` → `fair_value_base`. The intermediate key `fair_value_base` matches the field name surfaced by `risk_model`'s `valuation_bridge`, not by `valuation` itself; useful as a defensive fallback.

## Blockers for Tool Use

- None for invocation. The module accepts `settings` as a kwarg if a caller wants to override benchmark assumptions per-turn (the registry runner uses defaults).

## Notes

- **Audit-doc alignment is partial.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) cover the conceptual outputs (`property_terminal_value`, `passive_benchmark_return`, `outperformance_vs_tbill`, `outperformance_vs_sp500`) but use slightly different field names than the actual code (`tbill_annual_return` vs `passive_benchmark_return`; `excess_vs_tbill_bps` and `delta_value_vs_tbill` instead of `outperformance_vs_tbill`). Worth re-aligning the audit when reconciling — covered by the existing "Audit docs are drifted" [DECISIONS.md](../../DECISIONS.md) entry.
- **Constant-growth extrapolation is a known limitation.** The module's docstring at [opportunity_cost.py:18-21](opportunity_cost.py#L18-L21) flags this: the 12-month forward rate from `resale_scenario` is extended over 5+ years as a first-pass.
- **Appreciation-only by design.** The carry / income story lives in `carry_cost` and `hold_to_rent`; this module deliberately avoids double-counting them. Per [DECISIONS.md](../../DECISIONS.md) "Two cost questions, one of them is Layer 3", a richer alt-allocation comparison that includes net cash flow belongs in Unified Intelligence (Layer 3), not in this specialty model.
- Tests: [tests/modules/test_opportunity_cost_isolated.py](../../tests/modules/test_opportunity_cost_isolated.py); cross-cutting metrics in [tests/test_opportunity_metrics.py](../../tests/test_opportunity_metrics.py); bridge / interaction tests in [tests/interactions/test_opportunity_x_value.py](../../tests/interactions/test_opportunity_x_value.py).
- No direct LLM calls in the wrapper; cost is zero at this layer.

## Changelog

### 2026-04-24
- Initial README created.

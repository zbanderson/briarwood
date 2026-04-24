# risk_model — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`risk_model` runs the legacy `RiskConstraintsModule` (property-attribute risk flags: condition, title, flood, zoning) and adjusts its reported confidence based on two cross-module signals: a valuation-bridge premium (overpriced vs. Briarwood fair value lowers confidence; underpriced raises it) and a legal-confidence dampener (low legal certainty further reduces confidence). It then applies a bounded macro nudge (≤ 4%) on the county's `liquidity` signal. The output gives synthesis a single risk read with the supporting `valuation_bridge`, `legal_confidence_signal`, and `macro_nudge` telemetry attached. Call this tool whenever the user's intent involves risk framing, decision-tier verdicts, or any edge question where downside is asymmetric.

## Location

- **Entry point:** [briarwood/modules/risk_model.py:19](risk_model.py#L19) — `run_risk_model(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:71-78](../execution/registry.py#L71-L78) — `ModuleSpec(name="risk_model", depends_on=["valuation", "legal_confidence"], required_context_keys=["property_data"], runner=run_risk_model)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); legacy result shape from `RiskConstraintsModule` at [briarwood/modules/risk_constraints.py](risk_constraints.py).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RISK` — always called; this is the risk anchor.
- `DECISION` — always called; the verdict needs the risk-adjusted confidence.
- `EDGE` — called for downside-asymmetric questions.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.purchase_price` | `float` | required | listing facts | Required field per [risk_model.py:76](risk_model.py#L76); also used as `listed_price` in the valuation bridge at [risk_model.py:108-110](risk_model.py#L108-L110). |
| `context.property_data.sqft`, `beds`, `baths` | mixed | required | listing facts | Same. |
| Property condition / title / flood / zoning fields | mixed | optional | intake | Consumed inside `RiskConstraintsModule` to populate risk flags. |
| `context.prior_outputs.valuation` | `dict` | optional | executor (via `depends_on=["valuation"]`) | Reads `data.metrics.briarwood_current_value` at [risk_model.py:104](risk_model.py#L104) for the bridge. Absence yields `premium_pct=None` (no adjustment). |
| `context.prior_outputs.legal_confidence` | `dict` | optional | executor | Reads `confidence` at [risk_model.py:87](risk_model.py#L87). Absence ⇒ no legal-confidence dampener. |
| `context.macro_context.liquidity` | signed `float` | optional | macro reader (FRED) | Drives the ≤ 4% confidence nudge at [risk_model.py:45-50](risk_model.py#L45-L50). |
| `context.market_context` | `dict` | optional | router / session | Accepted via `optional_context_keys`. |

## Outputs

`run_risk_model` returns `ModulePayload.model_dump()`. Salient fields (from `RiskConstraintsModule` legacy result plus `extra_data`):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| (Legacy `RiskConstraintsModule` fields) | mixed | — | Risk flags, downside scenario estimate, etc. — see [briarwood/modules/risk_constraints.py](risk_constraints.py). |
| `confidence` | `float \| None` | 0-1 | Outer `ModulePayload.confidence`, replaced at [risk_model.py:78-79](risk_model.py#L78-L79) with the bridge-adjusted, legal-dampened, macro-nudged value when computable. Rounded to 4 decimals. |
| `extra_data.valuation_bridge.fair_value_base` | `float \| None` | USD | From `valuation.metrics.briarwood_current_value`. |
| `extra_data.valuation_bridge.listed_price` | `float \| None` | USD | From `property_input.purchase_price`. |
| `extra_data.valuation_bridge.premium_pct` | `float \| None` | signed fraction | `(listed - fair) / fair`, rounded to 4 decimals; `None` when either side missing. |
| `extra_data.valuation_bridge.flag` | `str \| None` | enum | `"overpriced_vs_briarwood_fair_value"` when `premium_pct >= 0.15`; `"priced_below_briarwood_fair_value"` when `premium_pct <= -0.10`; `None` otherwise. |
| `extra_data.legal_confidence_signal` | `float \| None` | 0-1 | Echoed from `prior_outputs.legal_confidence.confidence`. |
| `extra_data.macro_nudge` | `dict` | — | `apply_macro_nudge` telemetry: signal, applied delta, adjusted confidence, max nudge. |
| `warnings` | `list[str]` | — | Includes "Listed at $X vs Briarwood fair value $Y — premium Z%." when overpriced; "Legal confidence is low, so risk confidence is dampened." when legal < 0.5. |
| `assumptions_used.legacy_module` | `str` | — | `"RiskConstraintsModule"`. |
| `assumptions_used.valuation_dependency_declared` | `bool` | — | Always `True`. |
| `assumptions_used.valuation_dependency_used` | `bool` | — | True when `premium_pct` could be computed. |
| `assumptions_used.macro_context_used` | `bool` | — | True when a `liquidity` macro signal was present. |

## Dependencies

- **Requires (inputs):** `valuation` (via `depends_on` at [registry.py:73](../execution/registry.py#L73)) — but the runner gracefully handles absence; the dependency declaration ensures order, the bridge logic handles missing data with `premium_pct=None`.
- **Requires `legal_confidence`:** read from `prior_outputs` at [risk_model.py:84](risk_model.py#L84). Declared in the registry's `depends_on` so the executor schedules `legal_confidence` before `risk_model`. Absence (e.g., degraded legal_confidence) is still handled — no dampener is applied when the value is missing.
- **Benefits from (optional):** `prior_outputs`, `market_context`, `macro_context.liquidity`.
- **Calls internally:** `RiskConstraintsModule` at [briarwood/modules/risk_constraints.py](risk_constraints.py); `apply_macro_nudge` at [briarwood/modules/macro_reader.py:78](macro_reader.py#L78).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none directly (the rollup happens inside `confidence`).

## Invariants

- `confidence` remains in `[0.0, 1.0]` after every adjustment step; clamped at [risk_model.py:38-43](risk_model.py#L38-L43).
- Adjustment steps (in order):
  1. Bridge: `-CONFIDENCE_STEP (= 0.05)` when `premium_pct >= OVERPRICED_THRESHOLD (= 0.15)`; `+CONFIDENCE_STEP` when `premium_pct <= UNDERPRICED_THRESHOLD (= -0.10)`.
  2. Legal dampener: `-0.08` when `legal_conf < 0.5`.
  3. Macro nudge: `±MACRO_MAX_NUDGE (= 0.04)` based on `liquidity` signal.
- Macro nudge can only fire if `adjusted_confidence` was set (i.e., previous steps produced a numeric value).
- The wrapper does NOT have a try/except — exceptions in `RiskConstraintsModule.run` propagate. Audit doc framing as "safe to run out of order" applies to the *valuation* dependency only; it does not mean exception-safe.
- Deterministic per input when macro context is fixed; no LLM calls in the wrapper.
- Never mutates its inputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.risk_model import run_risk_model

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={"purchase_price": 850_000, "sqft": 2_100, "beds": 4, "baths": 2.5},
    prior_outputs={
        "valuation": {"data": {"metrics": {"briarwood_current_value": 720_000}}},
        "legal_confidence": {"confidence": 0.62},
    },
    macro_context={"liquidity": {"signal": -0.05, "source": "FRED"}},
)

payload = run_risk_model(context)
# payload["extra_data"]["valuation_bridge"]["premium_pct"]   ≈ 0.181
# payload["extra_data"]["valuation_bridge"]["flag"]          == "overpriced_vs_briarwood_fair_value"
# payload["extra_data"]["legal_confidence_signal"]           == 0.62
# payload["confidence"]                                      ∈ [0, 1]
# payload["warnings"][0] starts with "Listed at $850,000 vs Briarwood fair value $720,000 — premium 18.1%."
```

## Hardcoded Values & TODOs

- `OVERPRICED_THRESHOLD = 0.15` at [risk_model.py:13](risk_model.py#L13).
- `UNDERPRICED_THRESHOLD = -0.10` at [risk_model.py:14](risk_model.py#L14).
- `CONFIDENCE_STEP = 0.05` at [risk_model.py:15](risk_model.py#L15) — the up/down adjustment magnitude.
- `MACRO_MAX_NUDGE = 0.04` at [risk_model.py:16](risk_model.py#L16) — per-dimension cap on the liquidity macro adjustment.
- `0.08` legal-confidence dampener at [risk_model.py:43](risk_model.py#L43).
- `0.5` legal-confidence trigger threshold at [risk_model.py:42](risk_model.py#L42) and [risk_model.py:74](risk_model.py#L74).
- All five thresholds are module-level constants; not config-overridable from `ExecutionContext`.

## Blockers for Tool Use

- None for normal invocation. The runner gracefully degrades when valuation or legal_confidence outputs are absent.

## Notes

- **Audit-doc alignment.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) describe this module accurately — thresholds, adjustments, and the macro nudge match the code. No contradictions flagged.
- `legal_confidence` is declared in `depends_on` as of Handoff 2a Piece 4 (2026-04-24); the dampener at [risk_model.py:42-43](risk_model.py#L42-L43) is now ordered correctly. Absence is still handled (no dampener applied when value is missing).
- Tests: [tests/modules/test_risk_model_isolated.py](../../tests/modules/test_risk_model_isolated.py); UI-side risk bar covered by [tests/test_risk_bar.py](../../tests/test_risk_bar.py).
- No direct LLM calls in this wrapper; cost is zero at this layer.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: wrapped body in `try/except` and migrated to the canonical error contract. Internal exceptions now return a `module_payload_from_error` fallback (`mode="fallback"`, `confidence=0.08`) rather than propagating. The `legal_confidence` read remains optional — absence is valid and handled by the existing None-check at [risk_model.py:42-43](risk_model.py#L42-L43). Added [tests/modules/test_risk_model_degraded.py](../../tests/modules/test_risk_model_degraded.py). See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."
- Dependency change: added `legal_confidence` to `depends_on` at [registry.py:73](../execution/registry.py#L73). Previously the read was undeclared; the executor could schedule `risk_model` before `legal_confidence`, silently no-op'ing the legal-confidence dampener.

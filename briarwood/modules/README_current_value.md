# current_value — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`current_value` produces Briarwood's *pre-macro-nudge* fair-value estimate — the same comp-driven engine output that sits inside `valuation`, but without the ≤ 3% HPI-momentum confidence nudge applied on top. It answers the orchestrator's question *"what is this worth before any macro-side adjustment?"* — useful for scenario modeling, stress testing, and any caller that needs to isolate comp-driven fair value from macro signals. Under the hood it delegates to the legacy `CurrentValueModule`, which composes four internal anchors (comparable sales, market-value history, income support, and hybrid primary-plus-accessory value) into a single reconciled number.

## When to call `current_value` vs. `valuation`

`valuation` and `current_value` share the same engine. They exist as distinct scoped tools because they answer different questions.

**Call `valuation` when:**
- The user is asking "what is this worth?" and expects Briarwood's canonical number.
- Any decision-tier verdict (buy, pass, offer price) depends on the fair-value anchor.
- Risk, resale, rental-option, ARV, or opportunity-cost modules need their upstream valuation anchor (these depend on `valuation`, not `current_value`).

**Call `current_value` when:**
- You are running a scenario or stress test and must remove macro-side confidence effects (e.g., *"what's the comp-driven view if we assume neutral HPI?"*).
- You are comparing pre- and post-macro confidence deltas to surface how much of the verdict rides on macro signals.
- A downstream caller explicitly needs the unmodified engine output — `bull_base_bear`, `teardown_scenario`, and `renovation_scenario` read the legacy `CurrentValueModule` output directly today and conceptually match this contract.

**If unsure which applies, default to `valuation`.** The macro nudge is bounded (≤ 3%) and the user-facing number is what the product promises; `current_value` is a scenario/diagnostic tool, not a user-facing answer.

## Location

- **Entry point:** [briarwood/modules/current_value_scoped.py](current_value_scoped.py) — `run_current_value(context: ExecutionContext) -> dict[str, object]`.
- **Legacy engine:** [briarwood/modules/current_value.py:19](current_value.py#L19) — `CurrentValueModule.run(property_input, *, prior_results=None)`. This is the same engine `valuation` calls in-process.
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="current_value", depends_on=[], required_context_keys=["property_data"], runner=run_current_value)`.
- **Schema:** `CurrentValueOutput` at [briarwood/agents/current_value/schemas.py](../agents/current_value/schemas.py).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RESEARCH` — called for scenario/diagnostic queries about comp-driven fair value in isolation.
- `EDGE` — called for stress-testing questions that hinge on isolating macro effects.
- `DECISION`, `BROWSE`, `LOOKUP` — **prefer `valuation`** for these; use `current_value` only when the caller explicitly wants the pre-macro view.
- Not called for: `CHITCHAT`, `VISUALIZE` without a property context.

## Inputs

Same normalized `PropertyInput` shape as `valuation`. See the [valuation README](README_valuation.md#inputs) for the full table — identical requirements.

The only material difference at the ExecutionContext level: `context.macro_context.hpi_momentum_signal` is read by `valuation` but **ignored** by `current_value`.

## Outputs

`run_current_value` returns `ModulePayload.model_dump()`. The payload shape is identical to `valuation`'s *except*:

- `confidence` does NOT include the macro nudge. `assumptions_used.applies_macro_nudge` is always `False`.
- `data.macro_nudge` is NOT populated (no `meta` block for macro telemetry).
- All engine-output fields (`briarwood_current_value`, `mispricing_pct`, `pricing_view`, `value_low`, `value_high`, `all_in_basis`, etc.) pass through unchanged from the legacy `CurrentValueOutput`.

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.legacy_payload.briarwood_current_value` | `float \| None` | USD | Reconciled fair value; null when data too sparse. Identical to `valuation`'s number on the same inputs. |
| `data.legacy_payload.mispricing_pct` | `float \| None` | signed fraction | vs. listing ask. |
| `data.legacy_payload.pricing_view` | `str` | enum | `"fair" \| "undervalued" \| "overvalued" \| "unavailable"`. |
| `data.legacy_payload.value_low`, `value_high` | `float \| None` | USD | Engine-supplied confidence band. |
| `data.legacy_payload.all_in_basis` | `float \| None` | USD | True cost-to-own anchor. |
| `confidence` | `float` | 0.0–1.0 | **Pre-macro** engine confidence. |
| `assumptions_used.applies_macro_nudge` | `bool` | — | Always `False`. Distinguishing flag. |
| `assumptions_used.legacy_module` | `str` | — | Always `"CurrentValueModule"`. |
| `warnings` | `list[str]` | — | Populated on fallback. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]`.
- **Benefits from (optional):** `property_summary`, `comp_context`, `market_context`.
- **Calls internally:** `CurrentValueModule`, which itself instantiates and runs `ComparableSalesModule`, `MarketValueHistoryModule`, `IncomeSupportModule`, `HybridValueModule`. This is the same in-process composition `valuation` uses; the two scoped tools **do not** share cached results.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none today; added for future Layer 2 use cases requiring the pre-macro view.

## Invariants

- Never raises. All exceptions are caught and replaced with a fallback `ModulePayload` (`mode="fallback"`, `confidence=0.08`).
- `applies_macro_nudge` is always `False` (this is the definitional contract of `current_value`).
- `pricing_view == "unavailable"` when sparse facts or contradictions prevent a stable comp read (delegated to `CurrentValueModule` per [current_value.py:57-59](current_value.py#L57-L59)).
- Deterministic for a fixed input — no LLM calls, no randomness.
- Payload field names under `data.legacy_payload` are preserved unchanged from `CurrentValueOutput` so direct callers can migrate to or from this scoped wrapper without reshaping.

## Anti-recursion contract

The scoped `valuation` wrapper at [briarwood/modules/valuation.py:25-30](valuation.py#L25-L30) calls `CurrentValueModule()` **in-process**, not through the scoped `current_value` tool. This is a deliberate split:

- Prevents double error-handling when both tools run in the same session.
- Prevents circular registry dependencies (neither tool depends on the other).
- Preserves `valuation`'s macro-nudge as the sole distinguishing feature.

The split is enforced by `test_current_value_and_valuation_are_siblings_not_dependents` in [tests/modules/test_current_value_isolated.py](../../tests/modules/test_current_value_isolated.py). Reference: PROMOTION_PLAN.md entry 3.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.current_value_scoped import run_current_value

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "purchase_price": 850_000,
        "sqft": 2_100,
        "beds": 4,
        "baths": 2.5,
        "town": "Montclair",
        "state": "NJ",
    },
    macro_context={"hpi_momentum_signal": 0.8},  # ignored by current_value
)

payload = run_current_value(context)
# payload["data"]["legacy_payload"]["briarwood_current_value"] ≈ 790_000
# payload["data"]["legacy_payload"]["pricing_view"]            == "overvalued"
# payload["confidence"]                                        ∈ [0, 1]  (pre-macro)
# payload["assumptions_used"]["applies_macro_nudge"]           == False
```

## Hardcoded Values & TODOs

- `required_fields` hardcoded at [current_value_scoped.py](current_value_scoped.py): `["purchase_price", "sqft", "beds", "baths", "town", "state"]` — mirrors `valuation`.
- Thresholds for `pricing_view` transitions live inside `CurrentValueModule`; see its source for specifics.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Reversibility.** The two-tool split is deliberate and reversible. If the orchestrator never actually needs the pre-macro view, `current_value` can be de-registered in a future handoff without affecting `valuation` callers. The split was approved in [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 3.
- **Field-name stability.** Preserved so `BullBaseBearModule` (KEEP-as-internal-helper behind scoped `resale_scenario`), `teardown_scenario`, and `renovation_scenario` — which currently instantiate `CurrentValueModule` directly — could migrate to this scoped runner without a contract rewrite.
- Tests: [tests/modules/test_current_value_isolated.py](../../tests/modules/test_current_value_isolated.py) covers isolation, error contract, macro-isolation, and registry integration.
- No direct LLM calls; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 3.
- Contract: new scoped runner `run_current_value(context)` wraps `CurrentValueModule.run(property_input)` via `module_payload_from_legacy_result`; **does NOT apply the macro nudge**. Anti-recursion comment added in [briarwood/modules/valuation.py:25-30](valuation.py#L25-L30). Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*.

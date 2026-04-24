# income_support — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`income_support` exposes the raw rental-underwriting ratios — income-support ratio, rent coverage, price-to-rent, monthly cash flow, and rent-support classification — for a property. It answers lookup-style questions like *"what's the DSCR?"* or *"what's the rent coverage?"* without wrapping the full rent-path strategy narrative. Under the hood it delegates to the legacy `IncomeSupportModule`, which runs Briarwood's `IncomeAgent` against the property's purchase price, financing assumptions, and effective monthly rent (estimated via `RentContextAgent` when absent). Call this tool when the orchestrator needs a raw rental-underwriting number directly.

## When to call `income_support` vs. `rental_option`

`income_support` and `rental_option` share an engine (`IncomeSupportModule`). They exist as distinct scoped tools because they answer different questions.

**Call `income_support` when:**
- The user is asking a `LOOKUP`-style underwriting question: *"what's the DSCR?"*, *"what's the rent coverage?"*, *"what's the price-to-rent?"*, *"does this cash flow at the current rent?"*
- A downstream module needs a raw income-support ratio without the rental-ease context (rent absorption, days-to-rent, liquidity).
- You are stress-testing different rent or financing assumptions and want the underwriting signal in isolation.

**Call `rental_option` when:**
- The user is asking *"if you rent it instead of owner-occupying, how viable is that path?"* — a composite `STRATEGY` / `RENT_LOOKUP` answer.
- The answer needs rent-absorption ease (liquidity, days-to-rent, demand depth) alongside the underwriting ratio.
- The employment-macro confidence nudge should apply (only `rental_option` runs it).

**If unsure which applies, default to `rental_option`.** The composite view is safer when intent is ambiguous; `income_support` is the narrower raw-ratio lookup.

## Location

- **Entry point:** [briarwood/modules/income_support_scoped.py](income_support_scoped.py) — `run_income_support(context: ExecutionContext) -> dict[str, object]`.
- **Legacy engine:** [briarwood/modules/income_support.py:11](income_support.py#L11) — `IncomeSupportModule.run(property_input)`. Same engine `rental_option` calls in-process.
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="income_support", depends_on=[], required_context_keys=["property_data"], runner=run_income_support)`.
- **Schema:** `IncomeAgentOutput` at [briarwood/agents/income/schemas.py](../agents/income/schemas.py).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RENT_LOOKUP` — called for raw DSCR / rent coverage lookups. **Prefer `rental_option`** for full rent-path questions.
- `LOOKUP` — called when the orchestrator needs a single underwriting ratio.
- `STRATEGY` — **prefer `rental_option`** for rent-vs-buy strategy; use `income_support` only when the underwriting ratio is the explicit ask.
- Not called for: `CHITCHAT`, `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` and are normalized into a `PropertyInput` via `build_property_input_from_context`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.purchase_price` | `float` | required | user / listing facts | Null returns a `rent_source_type="unavailable"` payload with confidence 0. |
| `context.property_data.estimated_monthly_rent` | `float` | recommended | user / listing / rent agent | Falls back to `RentContextAgent` estimate when absent. |
| `context.property_data.down_payment_percent` | `float` (0-1) | recommended | assumptions | Missing ⇒ warning + degraded `financing_complete`. |
| `context.property_data.interest_rate` | `float` (0-1) | recommended | assumptions | Same. |
| `context.property_data.loan_term_years` | `int` | recommended | assumptions | Same. |
| `context.property_data.taxes`, `insurance`, `monthly_hoa` | mixed | optional | listing facts | Passed through to `IncomeAgent`. |
| `context.property_data.sqft`, `beds`, `baths` | mixed | required | listing facts | Required by `PropertyInput` constructor. |
| `context.property_data.town`, `state` | `str` | recommended | listing facts | Used by `RentContextAgent` when rent is estimated. |

## Outputs

The runner returns `ModulePayload.model_dump()`. Field-name stability is load-bearing — the following consumers read the legacy payload by key directly and must continue to work:

- `risk_bar` (reads `income_support_ratio`, `rent_coverage`, `monthly_cash_flow`)
- `evidence` (reads `rent_source_type`, `effective_monthly_rent`)
- `comp_intelligence` (reads `price_to_rent`)
- `rental_ease` (consumes `income_support_ratio` as an input)
- `hybrid_value` (consumes effective monthly rent for ADU income decomposition)

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.legacy_payload.income_support_ratio` | `float \| None` | fraction | `effective_monthly_rent / gross_monthly_cost`. |
| `data.legacy_payload.rent_coverage` | `float \| None` | fraction | Same concept, computed at a different granularity. |
| `data.legacy_payload.price_to_rent` | `float \| None` | ratio | `purchase_price / (effective_monthly_rent * 12)`. |
| `data.legacy_payload.monthly_cash_flow` | `float \| None` | USD / month | Effective monthly rent − total monthly cost. |
| `data.legacy_payload.effective_monthly_rent` | `float \| None` | USD / month | After vacancy adjustment. |
| `data.legacy_payload.gross_monthly_cost` | `float \| None` | USD / month | PITI + HOA + reserves. |
| `data.legacy_payload.rent_support_classification` | `str` | enum | e.g., `"strong"`, `"adequate"`, `"weak"`, `"unavailable"`. |
| `data.legacy_payload.price_to_rent_classification` | `str` | enum | Categorical label on `price_to_rent`. |
| `data.legacy_payload.rent_source_type` | `str` | enum | `"actual" \| "estimated" \| "fallback" \| "unavailable"`. |
| `data.legacy_payload.carrying_cost_complete` | `bool` | — | True when taxes/insurance/HOA all present. |
| `data.legacy_payload.financing_complete` | `bool` | — | True when down payment, rate, term all present. |
| `data.legacy_payload.estimated_monthly_cash_flow` | `float \| None` | USD / month | Alternative cash-flow estimate. |
| `data.legacy_payload.num_units`, `avg_rent_per_unit`, `unit_breakdown` | mixed | — | For multi-unit subjects. |
| `confidence` | `float` | 0.0-1.0 | Engine confidence. |
| `warnings` | `list[str]` | — | Populated on fallback or missing financing inputs. |
| `assumptions_used.legacy_module` | `str` | — | Always `"IncomeSupportModule"`. |
| `assumptions_used.exposes_raw_underwriting_signal` | `bool` | — | Always `True`. Distinguishing flag. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]`.
- **Benefits from (optional):** `market_context`, `comp_context`.
- **Calls internally:** `IncomeAgent` + `RentContextAgent` (when rent is estimated).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none directly — `rental_option` calls the legacy `IncomeSupportModule` in-process, not this scoped tool (see Anti-recursion).

## Invariants

- Never raises. All exceptions are caught and replaced with a fallback `ModulePayload` (`mode="fallback"`, `confidence=0.08`).
- `exposes_raw_underwriting_signal` is always `True` (this is the definitional contract of `income_support` vs. `rental_option`).
- `rent_source_type` is never null; missing rent produces `"unavailable"`.
- `income_support_ratio`, `rent_coverage`, `price_to_rent`, and `monthly_cash_flow` are null when `purchase_price` is missing.
- Deterministic for fixed inputs — no LLM calls.
- Payload field names under `data.legacy_payload` are preserved unchanged from `IncomeAgentOutput`.

## Anti-recursion contract

The scoped `rental_option` wrapper at [briarwood/modules/rental_option_scoped.py:26-32](rental_option_scoped.py#L26-L32) calls `IncomeSupportModule()` **in-process**, not through the scoped `income_support` tool. This is a deliberate split:

- Prevents double error-handling when both tools run in the same session.
- Prevents circular registry dependencies (neither tool depends on the other).
- Preserves `rental_option`'s composite role as the sole tool that layers rental-ease + macro nudge on top of the raw underwriting signal.

The split is enforced by `test_income_support_and_rental_option_are_siblings_not_dependents` in [tests/modules/test_income_support_isolated.py](../../tests/modules/test_income_support_isolated.py). Reference: PROMOTION_PLAN.md entry 8.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.income_support_scoped import run_income_support

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
)

payload = run_income_support(context)
# payload["data"]["legacy_payload"]["income_support_ratio"]        ≈ 0.72
# payload["data"]["legacy_payload"]["price_to_rent"]               ≈ 16.9
# payload["data"]["legacy_payload"]["monthly_cash_flow"]           ≈ -850
# payload["data"]["legacy_payload"]["rent_support_classification"] == "weak"
# payload["confidence"]                                            ∈ [0, 1]
# payload["assumptions_used"]["exposes_raw_underwriting_signal"]   == True
```

## Hardcoded Values & TODOs

- `required_fields` hardcoded at [income_support_scoped.py](income_support_scoped.py): `["purchase_price", "estimated_monthly_rent", "down_payment_percent", "interest_rate", "loan_term_years"]`.
- Vacancy and maintenance floors live inside `DEFAULT_COST_VALUATION_SETTINGS` (the legacy settings dataclass name; see [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *CostValuationModule is misnamed*).
- Rent fallback priority is inside `RentContextAgent`; no per-geography override here.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Reversibility.** The two-tool split with `rental_option` is deliberate and reversible. If the orchestrator never actually needs raw-ratio access, `income_support` can be de-registered in a future handoff without affecting `rental_option` callers.
- **Field-name stability is load-bearing.** The consumer list above is not exhaustive; any reshape risks silent regressions. The wrapper passes through `IncomeAgentOutput` verbatim via `module_payload_from_legacy_result`.
- Tests: [tests/modules/test_income_support_isolated.py](../../tests/modules/test_income_support_isolated.py) covers isolation, field-name stability, error contract, and registry integration.
- No direct LLM calls in this wrapper; cost is zero at this layer.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 8.
- Contract: new scoped runner `run_income_support(context)` wraps `IncomeSupportModule.run(property_input)` via `module_payload_from_legacy_result`. Anti-recursion comment added at [briarwood/modules/rental_option_scoped.py:26-32](rental_option_scoped.py#L26-L32). Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*.

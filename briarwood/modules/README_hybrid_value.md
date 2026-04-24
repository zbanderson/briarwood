# hybrid_value — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`hybrid_value` produces a decomposed valuation for properties that combine a primary dwelling with an accessory-income component — duplexes with an owner-occupied unit, single-family homes with an ADU or back house, and related layouts. It splits the property's value into four conceptual parts: the primary-house value (driven by same-category comps), the rear-income value (capitalized accessory rent), an optionality premium (the option to convert or separate), and a market-friction / feedback adjustment. It also produces low / base / high case bands. Call this tool when the subject screens as a hybrid and the orchestrator needs *"why is this hybrid worth what it's worth?"* — the answer `valuation` alone can't give because `valuation` returns a single reconciled number, not a decomposition.

**Only meaningful for hybrid subjects.** When the subject does not screen as hybrid (single-family with no accessory signal), the tool returns a structured payload with `is_hybrid=False`, zero confidence, and a non-hybrid narrative. That is a valid product answer ("not a hybrid property") — **not a module failure** — and callers should key on `is_hybrid` rather than mode to distinguish the two cases.

## Location

- **Entry point:** [briarwood/modules/hybrid_value_scoped.py](hybrid_value_scoped.py) — `run_hybrid_value(context: ExecutionContext) -> dict[str, object]`.
- **Legacy module:** [briarwood/modules/hybrid_value.py:50](hybrid_value.py#L50) — `HybridValueModule.run(property_input, *, prior_results=None)`.
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="hybrid_value", depends_on=["comparable_sales", "income_support"], required_context_keys=["property_data"], runner=run_hybrid_value)`.
- **Schema:** `HybridValueOutput` dataclass at [hybrid_value.py:25-47](hybrid_value.py#L25-L47).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RESEARCH` — called for "why is this hybrid worth what it's worth?" decomposition questions.
- `EDGE` — called for multi-unit / ADU edge-case valuations.
- `DECISION` — called transitively via `current_value` / `valuation` when the subject is hybrid.
- `BROWSE` — sometimes called as context on multi-unit / ADU properties.
- Not called for: `CHITCHAT`, and any subject that clearly does not have an accessory-income component.

## Inputs

Inputs arrive through `ExecutionContext`. Unlike most scoped modules, this one is a **composite** — it requires prior scoped runs.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.prior_outputs.comparable_sales` | `dict` | required | scoped planner | Must have `mode not in {"error", "fallback"}`. |
| `context.prior_outputs.income_support` | `dict` | required | scoped planner | Same. |
| `context.property_data.town`, `state` | `str` | required | listing facts | Same. |
| `context.property_data.sqft`, `beds`, `baths` | mixed | required | listing facts | Required by `PropertyInput` constructor. |
| `context.property_data.has_back_house`, `adu_type`, `additional_units`, `back_house_monthly_rent` | mixed | optional | listing facts | Drive the hybrid-detection rule. |
| `context.property_data.listing_description` | `str` | optional | listing facts | Used for unit parsing. |

## Outputs

The runner returns `ModulePayload.model_dump()`. On the happy path, `data.legacy_payload` mirrors `HybridValueOutput` verbatim.

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.legacy_payload.is_hybrid` | `bool` | — | False when the subject does not screen as hybrid. Valid zero-confidence answer. |
| `data.legacy_payload.reason` | `str` | — | Explanation of the detection decision. |
| `data.legacy_payload.detected_primary_structure_type`, `detected_accessory_income_type` | `str \| None` | — | Sub-classification when hybrid. |
| `data.legacy_payload.primary_house_value` | `float \| None` | USD | Primary-dwelling value from comps. |
| `data.legacy_payload.primary_house_comp_confidence` | `float` | 0-1 | Confidence of the primary comp set. |
| `data.legacy_payload.primary_house_comp_set` | `list[HybridCompEntry]` | — | Top comps used for the primary. |
| `data.legacy_payload.rear_income_value` | `float \| None` | USD | Capitalized rear-income value. |
| `data.legacy_payload.rear_income_method_used` | `str \| None` | — | e.g., `"cap_rate_on_declared_rent"`, `"estimated_market_rent"`. |
| `data.legacy_payload.rear_income_confidence` | `float` | 0-1 | Confidence of the rear-income component. |
| `data.legacy_payload.rent_assumption_summary` | `str` | prose | Narrative on rent inputs. |
| `data.legacy_payload.optionality_premium_value` | `float \| None` | USD | Value of convert/separate optionality. |
| `data.legacy_payload.optionality_reason` | `str` | prose | Why optionality applies. |
| `data.legacy_payload.optionality_confidence` | `float` | 0-1 | |
| `data.legacy_payload.low_case_hybrid_value` | `float \| None` | USD | Low-case band. |
| `data.legacy_payload.base_case_hybrid_value` | `float \| None` | USD | Base case. |
| `data.legacy_payload.high_case_hybrid_value` | `float \| None` | USD | High-case band. |
| `data.legacy_payload.market_friction_discount` | `float \| None` | fraction | Nonstandard-product adjustment. |
| `data.legacy_payload.market_feedback_adjustment` | `float \| None` | fraction | Market-feedback-driven delta. |
| `data.legacy_payload.confidence` | `float` | 0-1 | Overall decomposition confidence. |
| `data.legacy_payload.notes`, `narrative` | mixed | — | Human-readable reasoning. |
| `confidence` | `float \| None` | 0-1 | Outer payload confidence. `None` only on missing-priors error. |
| `mode` | `str` | enum | `"full"` / `"partial"` on happy path. `"error"` on missing priors. `"fallback"` on caught exception. |
| `assumptions_used.composite_from_prior_outputs` | `bool` | — | Always `True`. |

## Dependencies

- **Requires (inputs):** `comparable_sales` AND `income_support` in the scoped registry. Declared as `depends_on=["comparable_sales", "income_support"]` at [briarwood/execution/registry.py](../execution/registry.py). The planner orders both before this module.
- **Benefits from (optional):** `comp_context`.
- **Calls internally:** `HybridValueModule.run(property_input)` (which re-runs its own `ComparableSalesModule` + `IncomeSupportModule` instances in-process — see Invariants).
- **Must not run concurrently with:** none; but the missing-priors gate checks that both upstream modules produced clean output.
- **Downstream consumers:**
  - [briarwood/modules/current_value.py:85-98](current_value.py#L85-L98) — applies hybrid adjustment to fair value.
  - [briarwood/risk_bar.py:116](../risk_bar.py#L116) — reads for risk narration.

## Invariants

- **Missing-priors gate.** When `comparable_sales` OR `income_support` is absent OR has `mode in {"error", "fallback"}`, the wrapper returns `module_payload_from_missing_prior` (`mode="error"`, `confidence=None`, `missing_inputs` populated). Matches the canonical composite pattern at [arv_model_scoped.py:30-41](arv_model_scoped.py#L30-L41).
- **`is_hybrid=False` is NOT an error.** When both priors pass the gate but the legacy module decides the subject is not hybrid, the wrapper returns a legitimate zero-confidence payload with `is_hybrid=False`, `confidence=0.0`, and a non-hybrid narrative. Consumers must key on `data.legacy_payload.is_hybrid`, not on `mode`. Constraint from PROMOTION_PLAN.md entry 2.
- **`comp_is_hybrid` passthrough preserved.** When `comparable_sales` has already performed hybrid decomposition (per its `is_hybrid_valuation` field), the legacy `HybridValueModule` reuses that primary + rear income value rather than re-computing. See [hybrid_value.py:118-132](hybrid_value.py#L118-L132). The scoped wrapper must not collapse this path.
- **In-process dep re-computation.** `HybridValueModule.run(property_input)` is invoked without `prior_results` because `ExecutionContext.prior_outputs` holds scoped payload dicts, not typed `ModuleResult` objects. The legacy module therefore re-runs its comp and income deps in-process. The missing-priors gate is about refusing to run when upstream degraded, not about avoiding redundant compute. See module docstring for full tradeoff discussion.
- Never raises. Internal exceptions → `module_payload_from_error` (`mode="fallback"`, `confidence=0.08`).
- Deterministic per input; no LLM calls.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.hybrid_value_scoped import run_hybrid_value

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "town": "Avon By The Sea",
        "state": "NJ",
        "beds": 4,
        "baths": 2.5,
        "sqft": 2200,
        "lot_size": 9_000,
        "year_built": 1960,
        "purchase_price": 1_150_000,
        "has_back_house": True,
        "adu_type": "detached",
        "back_house_monthly_rent": 2_200,
        "estimated_monthly_rent": 4_500,
    },
    prior_outputs={
        "comparable_sales": {"data": {...}, "mode": "full", "confidence": 0.72, ...},
        "income_support":   {"data": {...}, "mode": "full", "confidence": 0.65, ...},
    },
)

payload = run_hybrid_value(context)
# payload["data"]["legacy_payload"]["is_hybrid"]                       == True
# payload["data"]["legacy_payload"]["primary_house_value"]             ≈ 900_000
# payload["data"]["legacy_payload"]["rear_income_value"]               ≈ 250_000
# payload["data"]["legacy_payload"]["base_case_hybrid_value"]          ≈ 1_180_000
# payload["confidence"]                                                ∈ [0, 1]
```

## Hardcoded Values & TODOs

- Hybrid-detection rules live inside the legacy module at [hybrid_value.py](hybrid_value.py); not configurable from the wrapper.
- ADU cap rate / expense ratio constants (`_DEFAULT_ADU_CAP_RATE = 0.08`, `_ADU_EXPENSE_RATIO = 0.30`) live in [comparable_sales.py:28, 32](comparable_sales.py#L28) — shared with `unit_income_offset` per DECISIONS.md 2026-04-24 *unit_income_offset drift*.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Composite wrapper semantics.** This is the canonical composite pattern: a missing-priors gate using `_collect_missing_priors`, followed by happy-path wrapping in try/except. Mirrors [arv_model_scoped.py](arv_model_scoped.py) and [hold_to_rent.py](hold_to_rent.py).
- Tests: [tests/modules/test_hybrid_value_isolated.py](../../tests/modules/test_hybrid_value_isolated.py) covers happy path (hybrid + non-hybrid), missing-priors (both, single, degraded, non-dict), error contract, and registry integration.
- No direct LLM calls.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry as a composite wrapper; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 2.
- Contract: new scoped runner `run_hybrid_value(context)` with the canonical missing-priors error contract (requires `comparable_sales` and `income_support` to have run cleanly). Happy path delegates to `HybridValueModule.run(property_input)` and passes the result through `module_payload_from_legacy_result`. `is_hybrid=False` short-circuit preserved as a valid zero-confidence payload, not an error. Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*.

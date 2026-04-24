# comparable_sales — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`comparable_sales` is Briarwood's comp-based fair-value anchor — **Engine A**. Given a subject property, it pulls nearby saved sale comps, adjusts each for proximity / recency / data-quality / income-premium / location / lot-size, and produces a blended comparable value with direct, income-adjusted, location-adjusted, lot-adjusted, and blended value ranges. It also performs hybrid detection: when the subject has an accessory unit (back house / ADU), the module decomposes value into primary-dwelling comp value + capitalized rear-income. Call this tool whenever the orchestrator needs a comp-driven fair-value number in isolation — for LOOKUP questions about "what are the comps saying?", for COMPARISON questions about "how does this compare to recent sales?", and as a standalone anchor that downstream composite tools (`hybrid_value`, `unit_income_offset`) read from `prior_outputs`.

**Engine A vs Engine B.** This is not the same as the user-facing "CMA" tool. `get_cma` at [briarwood/agent/tools.py:1802](../agent/tools.py#L1802) is Engine B: live-Zillow-first, falls back to saved comps only when live is empty, and backs `session.last_market_support_view`. The separation is documented at [briarwood/agent/dispatch.py:3697-3699](../agent/dispatch.py#L3697-L3699). See the Notes section for context.

## Location

- **Entry point:** [briarwood/modules/comparable_sales_scoped.py](comparable_sales_scoped.py) — `run_comparable_sales(context: ExecutionContext) -> dict[str, object]`.
- **Legacy module:** [briarwood/modules/comparable_sales.py:35](comparable_sales.py#L35) — `ComparableSalesModule.run(property_input)`.
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="comparable_sales", depends_on=[], required_context_keys=["property_data"], runner=run_comparable_sales)`.
- **Data source:** `data/comps/sales_comps.json` via `FileBackedComparableSalesProvider` (shared with `location_intelligence`).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `LOOKUP` — called for "what are the comps saying?" direct questions.
- `COMPARISON` — called for "how does this compare to recent sales?" questions.
- `DECISION` — often called as part of the decision path (transitively via `valuation` / `current_value`).
- `BROWSE` — called as context for browse-mode summaries.
- Not called for: `CHITCHAT`, pure `VISUALIZE` without comp context.

## Inputs

Inputs arrive through `ExecutionContext` and are normalized into a `PropertyInput` via `build_property_input_from_context`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.town` | `str` | required | listing facts | Town-scoped comp search. |
| `context.property_data.state` | `str` | required | listing facts | Same. |
| `context.property_data.sqft` | `int` | required | listing facts | Critical anchor; comp tolerance is 15% sqft. |
| `context.property_data.beds` | `int` | required | listing facts | Filters comp eligibility. |
| `context.property_data.baths` | `float` | required | listing facts | Same. |
| `context.property_data.property_type` | `str` | optional | listing facts | Narrows comp buckets. |
| `context.property_data.lot_size` | `float` | optional | listing facts | Lot-adjustment range input. |
| `context.property_data.year_built`, `stories`, `garage_spaces` | mixed | optional | listing facts | Adjustment inputs. |
| `context.property_data.purchase_price` | `float` | optional | user / listing | Used as `listing_price` anchor for comp scoring. |
| `context.property_data.has_back_house`, `adu_type`, `additional_units` | mixed | optional | listing facts | Trigger hybrid-decomposition path. |
| `context.property_data.condition_profile`, `capex_lane` | mixed | optional | user / listing | Condition adjustment inputs. |
| `context.property_data.days_on_market` | `int` | optional | listing facts | Freshness signal. |
| `context.property_data.listing_description` | `str` | optional | listing facts | Used for unit parsing on hybrid properties. |
| `context.property_data.manual_comp_inputs` | `list` | optional | user | Manual comps merged with file-backed comps. |

## Outputs

The runner returns `ModulePayload.model_dump()`. Field names under `data.legacy_payload` are preserved verbatim from `ComparableSalesOutput`.

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.metrics.comparable_value` | `float` | USD | Blended fair value from the comp set. |
| `data.metrics.comp_count` | `int` | count | Number of comps used. |
| `data.metrics.comp_confidence` | `float` | 0-1 | Rounded outer confidence. |
| `data.metrics.comp_confidence_score` | `float` | 0-1 | Richer confidence score (comp-matching-quality weighted). |
| `data.metrics.direct_value_midpoint`, `blended_value_midpoint`, etc. | `float \| None` | USD | Range midpoints for range-based consumers. |
| `data.legacy_payload.comparable_value` | `float` | USD | Primary fair-value number. |
| `data.legacy_payload.comp_count` | `int` | count | Same. |
| `data.legacy_payload.confidence` | `float` | 0-1 | Outer legacy confidence. |
| `data.legacy_payload.comps_used` | `list[AdjustedComparable]` | — | Adjusted comp set with per-comp metadata. |
| `data.legacy_payload.rejected_count` | `int` | count | Comps that failed eligibility. |
| `data.legacy_payload.direct_value_range` | `ComparableValueRange \| None` | USD | `{low, midpoint, high}`. |
| `data.legacy_payload.income_adjusted_value_range` | `ComparableValueRange \| None` | USD | After ADU income adjustment. |
| `data.legacy_payload.location_adjustment_range` | `ComparableValueRange \| None` | USD | After micro-location adjustment. |
| `data.legacy_payload.lot_adjustment_range` | `ComparableValueRange \| None` | USD | After lot-size adjustment. |
| `data.legacy_payload.blended_value_range` | `ComparableValueRange \| None` | USD | Final blended range. |
| `data.legacy_payload.comp_confidence_score` | `float \| None` | 0-1 | See above. |
| `data.legacy_payload.is_hybrid_valuation` | `bool` | — | True when hybrid path fired. **Read by `hybrid_value` to short-circuit its own decomposition.** |
| `data.legacy_payload.primary_dwelling_value` | `float \| None` | USD | Primary-house value under hybrid decomposition. |
| `data.legacy_payload.additional_unit_income_value` | `float \| None` | USD | Capitalized rear-income value. |
| `data.legacy_payload.additional_unit_count` | `int` | count | Detected accessory units. |
| `data.legacy_payload.additional_unit_annual_income` | `float \| None` | USD | Gross accessory annual income. |
| `data.legacy_payload.additional_unit_cap_rate` | `float` | fraction | `_DEFAULT_ADU_CAP_RATE = 0.08` at [comparable_sales.py:28](comparable_sales.py#L28). |
| `data.legacy_payload.hybrid_valuation_note` | `str \| None` | — | Human-readable rationale when hybrid fires. |
| `confidence` | `float` | 0.0–1.0 | Outer payload confidence. |
| `warnings` | `list[str]` | — | Populated on fallback. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]`.
- **Benefits from (optional):** `property_summary`, `comp_context`, `market_context`.
- **Calls internally:** `MarketValueHistoryModule` (for market context anchor) + `ComparableSalesAgent` + `FileBackedComparableSalesProvider`.
- **Must not run concurrently with:** none.
- **Downstream consumers (read legacy payload by key):**
  - [briarwood/modules/hybrid_value.py](hybrid_value.py) — reads `is_hybrid_valuation`, `primary_dwelling_value`, and the comp set via `prior_results["comparable_sales"]`.
  - [briarwood/modules/unit_income_offset.py](unit_income_offset.py) — reads the comp sub-dict for ADU offset computation; also depends on ADU constants defined in this file.
  - [briarwood/claims/pipeline.py:62-88](../claims/pipeline.py#L62-L88) — post-hoc graft that instantiates `ComparableSalesModule()` directly. Now eligible for retirement — see [FOLLOW_UPS.md](../../FOLLOW_UPS.md) 2026-04-24 *Retire the ad-hoc ComparableSalesModule() graft in claims/pipeline.py*.

## Invariants

- Never raises. Exceptions caught and replaced with a fallback `ModulePayload` (`mode="fallback"`, `confidence=0.08`, `fallback_reason="sparse_inputs_or_provider_error"`).
- Field names under `data.legacy_payload` are preserved verbatim — field-name stability is load-bearing for `hybrid_value` and `unit_income_offset`.
- `comp_count >= 0`; `comps_used` is always a list (possibly empty).
- `is_hybrid_valuation == True` implies `primary_dwelling_value` and `additional_unit_income_value` are set.
- Hybrid detection at [comparable_sales.py:465, 520](comparable_sales.py#L465) runs inside the legacy `run()`; the scoped wrapper absorbs this without flag.
- Non-standard-product adjustment (`is_nonstandard_product`) applies `market_friction_discount` via `valuation_constraints`.
- Deterministic per input; no LLM calls.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.comparable_sales_scoped import run_comparable_sales

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "town": "Avon By The Sea",
        "state": "NJ",
        "property_type": "single_family",
        "beds": 3,
        "baths": 2.0,
        "sqft": 1800,
        "lot_size": 5000,
        "year_built": 1998,
        "purchase_price": 725_000,
    },
)

payload = run_comparable_sales(context)
# payload["data"]["metrics"]["comparable_value"]      ≈ 735_000
# payload["data"]["metrics"]["comp_count"]            >= 0
# payload["data"]["legacy_payload"]["comps_used"]     # list of AdjustedComparable
# payload["data"]["legacy_payload"]["is_hybrid_valuation"] == False
# payload["confidence"]                               ∈ [0, 1]
```

## Hardcoded Values & TODOs

- ADU cap rate `_DEFAULT_ADU_CAP_RATE = 0.08` at [comparable_sales.py:28](comparable_sales.py#L28).
- ADU expense ratio `_ADU_EXPENSE_RATIO = 0.30` at [comparable_sales.py:32](comparable_sales.py#L32). Relocation proposed in DECISIONS.md 2026-04-24 *unit_income_offset drift*.
- 15% sqft tolerance for comp matching lives in `base_comp_selector.py` at [briarwood/agents/comparable_sales/](../agents/comparable_sales/).
- Cross-town comps TODO flagged in `base_comp_selector.py`.
- Renovation-premium pass-through (`estimate_comp_renovation_premium()`) not yet fed through.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Two comp engines, one tool promoted.** This is Engine A only. Engine B quality work is its own handoff — see [FOLLOW_UPS.md](../../FOLLOW_UPS.md) 2026-04-24 *Two comp engines with divergent quality; CMA (Engine B) needs alpha-quality pass*. Do not conflate this tool's contract with the user-facing "CMA" output.
- **Graft retirement.** The post-hoc graft at `claims/pipeline.py:62-88` is now unnecessary and is eligible for removal. Tracked in [FOLLOW_UPS.md](../../FOLLOW_UPS.md).
- **Hybrid detection is baked in.** The `_detect_hybrid_valuation` path at [comparable_sales.py:465](comparable_sales.py#L465) decides whether to route through the hybrid comp-request builder; `hybrid_value` then reuses this decomposition to avoid double-counting. See `hybrid_value.py:118-132` comp-is-hybrid short-circuit.
- Tests: [tests/modules/test_comparable_sales_isolated.py](../../tests/modules/test_comparable_sales_isolated.py) covers isolation, field-name stability, error contract, and registry integration.
- No direct LLM calls.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 1.
- Contract: new scoped runner `run_comparable_sales(context)` wraps `ComparableSalesModule.run(property_input)` via `module_payload_from_legacy_result`. Field-name stability on all hybrid-decomposition and comp-range keys preserved. Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*. FOLLOW_UPS.md entry added for retiring the `claims/pipeline.py:62-88` graft in a follow-up handoff.

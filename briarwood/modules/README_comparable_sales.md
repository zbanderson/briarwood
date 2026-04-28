# comparable_sales — Scoped Registry Model

**Last Updated:** 2026-04-28 (CMA Phase 4a Cycle 6 — claims graft now routes through this scoped runner)
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
| `context.property_data.sqft` | `int` | required | listing facts | Critical anchor. Sqft gap drives a sliding score penalty in [agent.py:429-444](../agents/comparable_sales/agent.py#L429-L444); rationale thresholds at 10% / 20%. No hard tolerance band. |
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
  - [briarwood/claims/pipeline.py:62-114](../claims/pipeline.py#L62-L114) — post-hoc graft routes through `run_comparable_sales(context)` as of CMA Phase 4a Cycle 6 (2026-04-28). Repackages this runner's `data.legacy_payload` as a `ComparableSalesOutput` pydantic instance under `outputs["comparable_sales"]["payload"]` so the synthesizer's `payload.comps_used` access path stays stable. The graft itself is still required because the orchestrator's routed run does not surface `comparable_sales` as a top-level entry in `module_results["outputs"]` (it runs only as an internal dependency of `valuation`).

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
- Sqft-gap scoring is a sliding penalty in [briarwood/agents/comparable_sales/agent.py:429-444](../agents/comparable_sales/agent.py#L429-L444) — `score -= min(sqft_gap * 0.45, 0.28)`, with explanatory rationale at the 10% and 20% thresholds. There is no hard sqft-tolerance band that rejects comps; weak-sqft matches degrade their score and flow downstream as cautions on the comp.
- **Engine A still same-town-only.** Same-town filtering is enforced at the provider level — [`FileBackedComparableSalesProvider.get_sales`](comparable_sales.py#L76) returns only rows whose normalized town matches the request. Cross-town fallback is not implemented for Engine A's saved-comp path.
- **Engine B has cross-town fallback** as of CMA Phase 4a Cycle 4. When same-town SOLD count is below `MIN_SOLD_COUNT` (5), `get_cma` queries each neighbor in [`cma_invariants.TOWN_ADJACENCY`](cma_invariants.py) for SOLD listings and merges them with `is_cross_town=True` provenance. Cross-town expansion is SOLD-only — ACTIVE inventory is inherently same-town competition, so cross-town ACTIVE is not pulled.
- Renovation-premium pass-through is flagged at [agent.py:784](../agents/comparable_sales/agent.py#L784) as a TODO; `estimate_comp_renovation_premium()` is not yet fed through to the per-comp adjustment.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Two comp engines, one tool promoted.** This is Engine A only. Engine B quality work landed via CMA Phase 4a (2026-04-26 Cycles 1-5; closed out 2026-04-28 in Cycle 6). Engines A and B now share the same scoring pipeline at [`briarwood/modules/comp_scoring.py`](comp_scoring.py); they remain distinct at the *data-source* level (Engine A = saved comps, this tool; Engine B = live Zillow SOLD + ACTIVE + saved fallback, accessed via `get_cma`). Do not conflate this tool's contract with the user-facing "CMA" output.
- **Graft retirement (partial — landed 2026-04-28).** The post-hoc graft at `claims/pipeline.py:62-114` now goes through `run_comparable_sales` (this module's scoped runner) instead of instantiating `ComparableSalesModule` directly. The graft itself is still required for shape adaptation; full removal would require the orchestrator's routed chat-tier run to surface `comparable_sales` as a top-level output. See [ROADMAP.md](../../ROADMAP.md) §4 High *Consolidate chat-tier execution* for that follow-on.
- **Hybrid detection is baked in.** The `_detect_hybrid_valuation` path at [comparable_sales.py:465](comparable_sales.py#L465) decides whether to route through the hybrid comp-request builder; `hybrid_value` then reuses this decomposition to avoid double-counting. See `hybrid_value.py:118-132` comp-is-hybrid short-circuit.
- Tests: [tests/modules/test_comparable_sales_isolated.py](../../tests/modules/test_comparable_sales_isolated.py) covers isolation, field-name stability, error contract, and registry integration.
- No direct LLM calls.

## Changelog

### 2026-04-28 (CMA Phase 4a Cycle 6 — claims graft now routes through scoped runner)
- **Downstream consumer change (no contract change for this module):** [`briarwood/claims/pipeline.py`](../claims/pipeline.py)`:62-114` (`_inject_comparable_sales`) now calls `run_comparable_sales(context)` instead of instantiating `ComparableSalesModule()` directly. The graft repackages this module's `data.legacy_payload` as a `ComparableSalesOutput` pydantic instance under `outputs["comparable_sales"]["payload"]` so the verdict_with_comparison synthesizer's `payload.comps_used` access path is preserved. Field-name stability invariant (preserved by `module_payload_from_legacy_result`) made this a one-line shape adapter rather than a contract rewrite.
- **Why:** the claims wedge was the last out-of-`modules/` caller still instantiating `ComparableSalesModule` directly. Composite consumers under `modules/` (`renovation_scenario`, `teardown_scenario`, `unit_income_offset`, `hybrid_value`, `current_value`) continue to instantiate the legacy module internally — that's the intentional in-process composition pattern, separate from the post-hoc-graft pattern this change retires. Closes ROADMAP §4 Low *Retire the ad-hoc ComparableSalesModule() graft*.
- **Test contract updated:** `tests/claims/test_pipeline.py` patches `run_comparable_sales` instead of `ComparableSalesModule`; pins the new fallback handling (scoped wrapper's `mode="fallback"` path returns no `legacy_payload`, so the graft no-ops gracefully). All 82 claims tests green.

### 2026-04-26 (CMA Phase 4a Cycles 3a-3c)
- **Internal refactor (no contract change for callers):** Engine A's scoring math
  (`_score_comp`, `_proximity_score`, `_recency_score`, `_data_quality_score`)
  now lives in [`briarwood/modules/comp_scoring.py`](comp_scoring.py).
  `ComparableSalesModule.run` continues to return the same shape; the legacy
  function names in `comparable_sales.py` are thin delegators to the shared
  module so existing imports keep working.
- **Engine B unification status:** Engine B (`get_cma` in
  [`briarwood/agent/tools.py`](../agent/tools.py)) now goes through the same
  scoring pipeline. Both SOLD and ACTIVE Zillow listings flow through
  `comp_scoring.score_comp_inputs` with the per-listing-status recency
  divergence (SOLD uses `sale_age_days`; ACTIVE uses inverse `days_on_market`).
  The "Engine A vs Engine B" distinction in the original README still holds at
  the *data-source* level (Engine A = saved comps; Engine B = live Zillow SOLD
  + ACTIVE + saved fallback) but no longer at the *scoring* level — both share
  one scoring code path.
- **`tax_assessed_value` outlier filter** from
  [`briarwood/modules/cma_invariants.py`](cma_invariants.py) is now applied at
  the merge boundary in `get_cma`. Engine A's saved-comp path is unaffected
  (saved comps are pre-vetted; outlier filter targets raw Zillow rows).
- **Slight behavior change for very-incomplete comps:** the data-quality scorer
  has a new `_DATA_QUALITY_FLOOR_DEGRADED = 0.3` baseline that fires when more
  than half a comp's score inputs are missing (Zillow-friendly). For typical
  saved comps with full metadata the score is unchanged.
- **Adjacent docs:** `Engine B alpha-quality pass` ROADMAP entry from
  2026-04-24 is now in execution; tracked end-to-end in
  [`CMA_HANDOFF_PLAN.md`](../../CMA_HANDOFF_PLAN.md). The graft retirement
  ROADMAP entry remains open for a future cycle.

### 2026-04-26 (CMA Phase 4a Cycle 4 — cross-town comp expansion)
- **Engine B contract change (additive):** `ComparableProperty` gains `is_cross_town: bool = False`. Default backwards-compatible; populated `True` on rows that came from a neighboring town's SearchApi SOLD response.
- **New behavior in `get_cma` (Engine B):** when same-town SOLD count is below `MIN_SOLD_COUNT` (5 per [`cma_invariants.py`](cma_invariants.py)), `_live_zillow_cma_candidates` issues additional `listing_status="sold"` calls for each neighbor in `cma_invariants.TOWN_ADJACENCY`. Cross-town rows tag `is_cross_town=True` and carry a neighbor-aware `selection_rationale` (e.g., "live Zillow sold comp from neighboring Bradley Beach"). Cross-town expansion is SOLD-only — ACTIVE listings represent same-town competition and are intentionally not expanded.
- **`comp_selection_summary` format extended:** when cross-town SOLD rows are merged in, the SOLD count parenthetically reports the cross-town subset — e.g. `"Comp set: 5 SOLD (3 cross-town) + 4 ACTIVE."`. No-cross-town turns continue to use the prior format.
- **New shared constant:** [`cma_invariants.TOWN_ADJACENCY`](cma_invariants.py) maps each of the six target Monmouth County shore towns (Belmar, Avon By The Sea, Bradley Beach, Spring Lake, Sea Girt, Manasquan) to its cross-town comp candidates. Helper `cma_invariants.neighbors_for_town(town)` does case-insensitive + hyphen-tolerant lookup; returns empty for towns outside the supported geography (cross-town expansion is then a no-op).
- **Engine A unchanged.** The saved-comp provider at `briarwood/modules/comparable_sales.py:76-86` continues to filter strictly same-town. Cross-town fallback for Engine A is still queued (TOOL_REGISTRY Engine A TODOs); not in scope for Cycle 4.
- **Per-row distance filter deferred.** The plan called for a `MAX_DISTANCE_MILES_CROSS_TOWN = 3.0` per-row distance check, but subject lat/lon is not yet plumbed through `summary.json`. The adjacency map provides the geographic constraint for now (each neighbor entry is hand-tuned to the 6-town shore corridor where every pair is within ~3 mi). Plumbing subject lat/lon and turning the distance cap into an enforced filter is queued for a future cycle.

### 2026-04-26 (CMA Phase 4a Cycle 4 — sqft + same-town prose drift)
- **Drift correction (no contract change):** removed two references to a non-existent `briarwood/agents/comparable_sales/base_comp_selector.py` file (the directory contains `agent.py`, `*_enricher.py`, `*_parser.py`, etc., but not `base_comp_selector.py`).
- **Sqft prose corrected:** the README previously claimed a "15% sqft tolerance for comp matching." There is no hard tolerance — the actual logic at `briarwood/agents/comparable_sales/agent.py:429-444` is a sliding score penalty (`score -= min(sqft_gap * 0.45, 0.28)`) with explanatory rationale thresholds at 10% and 20% gap. The `Inputs` row for `sqft` and the `Hardcoded Values & TODOs` bullet both rewritten against the actual code.
- **Same-town prose corrected:** the README previously said "Cross-town comps TODO flagged in `base_comp_selector.py`." The same-town restriction is in fact enforced at the provider level — `FileBackedComparableSalesProvider.get_sales` at `briarwood/modules/comparable_sales.py:76-86` filters rows by `normalize_town == town_key`, with no TODO comment. Cross-town fallback is queued in `TOOL_REGISTRY.md` and `CMA_HANDOFF_PLAN.md` Cycle 4 — that's the canonical reference now.
- **Renovation-premium TODO grounded:** the bullet now points to the actual TODO comment at `agent.py:784` (`# TODO: feed measured renovation premium from estimate_comp_renovation_premium()`).

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 1.
- Contract: new scoped runner `run_comparable_sales(context)` wraps `ComparableSalesModule.run(property_input)` via `module_payload_from_legacy_result`. Field-name stability on all hybrid-decomposition and comp-range keys preserved. Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*. ROADMAP.md entry added for retiring the `claims/pipeline.py:62-88` graft in a follow-up handoff.

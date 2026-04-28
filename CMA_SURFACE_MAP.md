# CMA Surface Map — Phase 4a Cycle 1

**Generated:** 2026-04-26
**Plan:** [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md) Cycle 1.
**Scope:** Read-only audit. Catalogs every place comps surface in the product, names which engine each surface uses, documents the live-vs-saved fallback behavior of Engine B, and flags gaps surfaced during the audit. Used as input to Cycle 2's owner decision (unify-vs-separate fork).

---

## The two engines

### Engine A — `ComparableSalesModule`

- **File:** [briarwood/modules/comparable_sales.py:35](briarwood/modules/comparable_sales.py#L35).
- **Scoped runner:** [briarwood/modules/comparable_sales_scoped.py](briarwood/modules/comparable_sales_scoped.py) `run_comparable_sales(context)`.
- **Registry entry:** in `briarwood/execution/registry.py` as `ModuleSpec(name="comparable_sales", depends_on=[], required_context_keys=["property_data"])`.
- **Data source:** `data/comps/sales_comps.json` via `FileBackedComparableSalesProvider`.
- **Scoring/adjustment logic** (the load-bearing IP):
  - Per-comp scoring via `comp_scoring.score_comp_inputs` (lifted to [briarwood/modules/comp_scoring.py](briarwood/modules/comp_scoring.py) in CMA Phase 4a Cycle 3a, 2026-04-26; shared with Engine B).
  - Location/lot/income-adjusted bucketing (`direct_value_range`, `income_adjusted_value_range`, `location_adjustment_range`, `lot_adjustment_range`, `blended_value_range`).
  - Sqft scoring is a sliding penalty in [briarwood/agents/comparable_sales/agent.py:429-444](briarwood/agents/comparable_sales/agent.py#L429-L444) — `score -= min(sqft_gap * 0.45, 0.28)` with rationale thresholds at 10% and 20% gap. There is no hard tolerance band; weak-sqft comps degrade their score and flow downstream as cautions.
  - Hybrid detection at `_detect_hybrid_valuation` (line ~465) — when subject has accessory unit / ADU, decomposes into primary-dwelling + capitalized rear-income.
- **Engine A's TODOs** (per [TOOL_REGISTRY.md](TOOL_REGISTRY.md) and the module's own README):
  - Cross-town comp expansion. Engine B has it (Cycle 4 2026-04-26 via `cma_invariants.TOWN_ADJACENCY`); Engine A is still strictly same-town at the provider level ([briarwood/modules/comparable_sales.py:76-86](briarwood/modules/comparable_sales.py#L76-L86)).
  - Renovation premium pass-through (`estimate_comp_renovation_premium` exists but isn't surfaced — deferred to a future cycle, see [ROADMAP.md](ROADMAP.md) §4 Medium).

### Engine B — `get_cma`

- **File:** [briarwood/agent/tools.py:1829](briarwood/agent/tools.py#L1829).
- **Strategy:** Live-Zillow-first via `_live_zillow_cma_candidates` ([tools.py:1944](briarwood/agent/tools.py#L1944)); falls back to saved comps via `_fallback_saved_cma_candidates` ([tools.py:1922](briarwood/agent/tools.py#L1922)) on the conditions in §"Live-vs-saved fallback" below.
- **Scoring/adjustment logic:** **None beyond filter + rank**. Live rows are filtered by town/state match, beds tolerance ±1, price band ±35% of subject ask; survivors are ranked by `_rank_cma_candidates` (same-baths first, then ask-price proximity). No proximity, recency, data-quality, or income-adjustment math.
- **Optional `thesis` short-circuit** (added 2026-04-25 between Cycles 4 and 5 of OUTPUT_QUALITY_HANDOFF_PLAN.md): when caller passes a pre-computed thesis dict (`ask_price`, `fair_value_base`, `value_low`, `value_high`, `pricing_view`, `primary_value_source`), the internal `get_value_thesis` call is skipped — eliminates the leaky module re-runs the chat-tier path used to trigger.
- **Returns `CMAResult`** with: `comps` (list of `ComparableProperty`), the four anchor fields above, `comp_selection_summary` (one-line label: "Live Zillow market comps..." vs "Saved comps..."), `confidence_notes`, `missing_fields`.

---

## Surface inventory

### Engine A surfaces (consume `ComparableSalesModule` output)

| # | Surface | Path | Engine A enters via | What user sees |
|---|---------|------|---------------------|----------------|
| A1 | Consolidated chat-tier plan | [briarwood/orchestrator.py](briarwood/orchestrator.py) `run_chat_tier_analysis` → `run_comparable_sales` | Scoped registry; runs once per turn in the per-AnswerType module set | Comp evidence flows into `unified_output["module_results"]["outputs"]["comparable_sales"]` and indirectly into `unified_output["value_position"]["fair_value_base"]` (via the `valuation` module which reads comparable_sales output) |
| A2 | Layer 3 LLM synthesizer | [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) `synthesize_with_llm` | Reads full `unified_output` including comparable_sales metrics | Prose: "the comps support a fair value of $X" — but the synthesizer doesn't typically name specific comp addresses |
| A3 | `value_thesis_view.comps` field (Engine-A side) | `_build_browse_value_thesis` and `_build_decision_value_thesis` in [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) | Pulls valuation module's `comps_used` (sourced from comparable_sales) | UI: "comps fed fair value" rows tagged `feeds_fair_value: True` |
| A4 | Composite-module consumers | `hybrid_value`, `current_value`, `renovation_scenario`, `teardown_scenario`, `unit_income_offset` (each instantiates `ComparableSalesModule()` directly) | Direct instantiation; each runs as its own scoped module in the consolidated plan | Indirect — feeds downstream value/income/scenario outputs |
| A5 | Claims wedge graft | [briarwood/claims/pipeline.py:62-114](briarwood/claims/pipeline.py#L62-L114) `_inject_comparable_sales` | Calls `run_comparable_sales(context)` (canonical scoped runner) and repackages `data.legacy_payload` as `ComparableSalesOutput` so the synthesizer's `payload.comps_used` access path stays stable | Comp data into `VerdictWithComparisonClaim.comparison.scenarios` (claim-wedge path only). **Direct-instantiation retirement landed CMA Phase 4a Cycle 6** (2026-04-28). The graft itself remains for shape adaptation; full removal gated on top-level surfacing of `comparable_sales` in the orchestrator's routed run — see [ROADMAP.md](ROADMAP.md) §4 High *Consolidate chat-tier execution* |

### Engine B surfaces (consume `get_cma` output)

| # | Surface | Path | Engine B enters via | What user sees |
|---|---------|------|---------------------|----------------|
| B1 | DECISION handler | [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) `handle_decision` line ~2007 | Unconditional `get_cma(pid, overrides=analysis_overrides)` near the top | All B-prefixed downstream surfaces below |
| B2 | BROWSE handler | [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) `handle_browse` line ~4836 | Unconditional `get_cma(pid, overrides=overrides, thesis=cma_thesis)` with the `thesis` short-circuit when chat-tier artifact is populated | All B-prefixed downstream surfaces below |
| B3 | EDGE handler | [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) `handle_edge` line ~3879 | Conditional on `_CMA_RE` / `_COMP_SET_RE` / `_ENTRY_POINT_RE` text-pattern match | All B-prefixed downstream surfaces below — but only when the user phrases the question in those patterns |
| B4 | `session.last_market_support_view` | `_build_market_support_view` / `_pack_market_support_view` in dispatch.py:778-810 | Reads `cma_result.comps` + `comp_selection_summary` | "Where the comps sit" data — flows to chart B6 below |
| B5 | `session.last_comps_preview` | `_build_comps_preview` (decision/edge) / `_build_browse_comps_preview` (browse) | Reads `cma_result.comps` | Compact comps preview UI card (table of addresses + asks) |
| B6 | `cma_positioning` chart spec | [api/pipeline_adapter.py:957](api/pipeline_adapter.py#L957) `_native_cma_chart` | `market_view = last_market_support_view` for comp rows; `view = last_value_thesis_view` for anchors (per 2026-04-26 defensive fix) | "Where the comps sit" scatter chart with subject ask + fair-value band overlay |
| B7 | `cma_positioning` ChartSpec registration | [briarwood/representation/charts.py:174](briarwood/representation/charts.py#L174) `_render_cma_positioning` lazy-imports `_native_cma_chart` | Selectable by Representation Agent for EDGE / DECISION (per `_SYSTEM_PROMPT` line ~142). **NOT in BROWSE chart set** per `_enforce_browse_chart_set` | Chart appears on EDGE / DECISION turns when agent selects it; never on BROWSE today |
| B8 | React `CmaPositioningChart` | [web/src/components/chat/chart-frame.tsx:567](web/src/components/chat/chart-frame.tsx#L567) | TypeScript `CmaPositioningChartSpec` at [web/src/lib/chat/events.ts:51](web/src/lib/chat/events.ts#L51) | Renders chart B6 |
| B9 | `value_thesis_view.comps` field (Engine-B side) | Same `_build_*_value_thesis` functions as A3, but B's contribution is `feeds_fair_value: False` rows | Mixed list (Engine A comps + Engine B comps) | UI: "comps for context" rows shown alongside the fair-value comps |

### Test/mock surfaces

- `tests/agent/test_dispatch.py` — 7 patches of `briarwood.agent.dispatch.get_cma` (in `BrowseHandlerTests`, `DecisionHandlerTests`, `EdgeHandlerTests`, etc.). Each test mocks the function out with a `CMAResult` fixture; no test exercises the live-vs-saved fallback.
- `tests/agent/test_tools.py` — 2 direct `get_cma(...)` calls. One is the regression test pinning the `thesis=...` short-circuit behavior (commit `f018fc4`).
- `tests/test_modules.py` — direct `ComparableSalesModule()` exercise (Engine A unit tests).
- `tests/modules/test_comparable_sales_isolated.py` — `ComparableSalesModule` patched inside the scoped runner (Engine A integration tests).

---

## Live-vs-saved fallback (Engine B detail)

`_live_zillow_cma_candidates` ([tools.py:1944](briarwood/agent/tools.py#L1944)) silently falls back to saved comps via `_fallback_saved_cma_candidates` on **any** of the following:

1. `town` or `state` missing from the property summary.
2. SearchApi client not configured (`SearchApiZillowClient.is_configured` is False — no `SEARCHAPI_API_KEY` env var).
3. SearchApi response not OK (`response.ok` is False — network failure, rate limit, etc.).
4. **All live results filtered out** — after applying:
   - `town` match (`_norm_place(candidate.town) == _norm_place(town)`)
   - `state` match (same)
   - `beds` tolerance ±1
   - Price band: `subject_ask * 0.65 ≤ candidate.price ≤ subject_ask * 1.35`
   - Subject-address dedup (live row matching the subject's normalized address is dropped)
5. Top-4 ranked live rows is empty after `_rank_cma_candidates`.

The fallback function `_fallback_saved_cma_candidates` ([tools.py:1922](briarwood/agent/tools.py#L1922)) reads from `data/comps/sales_comps.json` (the same source Engine A reads from) but **does not route through Engine A's scoring** — it returns rows in raw form, then `_rank_cma_candidates` applies the same same-baths-then-price-proximity ranking as the live path.

Net consequence: Engine B's "saved comp" path produces the same data shape as Engine B's "live comp" path, but neither path benefits from Engine A's `_score_comp` / `_proximity_score` / `_recency_score` / `_data_quality_score` adjustments. **Engine B is engine-light by construction.**

There is no user-facing signal distinguishing live-from-saved — the `comp_selection_summary` string changes ("Live Zillow market comps..." vs "Saved comps..."), but the SSE event payload doesn't carry the distinction, so the UI cannot show a "live" vs "from sales archive" badge.

---

## Gaps surfaced during the audit

These are findings from this audit, not from prior ROADMAP — they're inputs to Cycle 2's invariant definitions.

1. **Engine B has no per-comp quality scoring.** Filter + rank only. Live rows that pass town/state/beds/price filters are presented as comps regardless of distance, recency, condition, or any other signal Engine A weighs.
2. **Engine B has no minimum-comp-count floor.** `get_cma` happily returns `CMAResult(comps=[])` and emits a `confidence_notes` line. Downstream consumers (`_pack_market_support_view`, `_build_comps_preview`) suppress the surface when `comps` is empty, but there's no aggregated signal "this CMA isn't reliable enough to show" — three terrible comps render as a chart the same way three excellent comps would.
3. **Engine B's saved-comp fallback bypasses Engine A's scoring.** Same data file, different code path, no adjustment math. This is the most important quality gap — when live returns empty (a common case for thin markets), the user sees raw saved-comp filter output, not Engine A's adjusted ranges.
4. **`value_thesis_view.comps` is a mixed list.** `_build_*_value_thesis` interleaves Engine A's `comps_used` (tagged `feeds_fair_value: True`) and Engine B's CMA rows (tagged `feeds_fair_value: False`). Useful for UI rendering but blurs engine attribution. If Cycle 2 takes the unify path, this merge becomes natural; if it takes the separate path, the merge needs an explicit boundary.
5. **`cma_positioning` chart is hidden from BROWSE.** Phase 3's `_enforce_browse_chart_set` pins BROWSE to `[market_trend, value_opportunity, scenario_fan]`. The chart, renderer, and React component all work — BROWSE just never selects them. The Phase 3 owner-decision was deliberate (BROWSE prefers town context over CMA for first-impression), but post-CMA-fix the BROWSE chart set should be revisited (planned in CMA_HANDOFF_PLAN Cycle 5).
6. **Engine B test coverage is shallow.** Tests mock `dispatch.get_cma` directly with canned `CMAResult` fixtures. No integration test exercises the SearchApi live path, the live-empty fallback, or the price/beds-band filter math. Cycle 3 will need to add these regardless of the unify-vs-separate fork.
7. **No live-vs-saved signal in the SSE payload.** `comp_selection_summary` is a string the synthesizer sees but the chart/preview cards do not. The user has no way to know whether the comps shown are live listings or sales archive entries.
8. **Two text-mode regexes gate Engine B on EDGE.** `_CMA_RE`, `_COMP_SET_RE`, `_ENTRY_POINT_RE` decide whether `handle_edge` runs `get_cma`. If a user phrases an EDGE-tier comp question outside those regex patterns, no comp data surfaces. The Phase 3 `_enforce_browse_chart_set` is the same problem class on BROWSE; both deserve a less-brittle surface.
9. **The 2026-04-26 `cma_positioning` two-view defensive fix** ([briarwood/representation/agent.py:262](briarwood/representation/agent.py#L262)) is in place but inelegant — it overrides the Representation Agent's source-view choice from outside the agent. The deeper fix (typed `source_views: dict[role, view_key]` on `RepresentationSelection`) is recorded in ROADMAP. Worth retiring during Cycle 5 if the new comp shape from Cycles 3-4 reshapes the data.

---

## Implications for Cycle 2 (owner decision)

**The unify path** would route Engine B's live + saved comps through Engine A's scoring/adjustment pipeline. Concrete shape: `_live_zillow_cma_candidates` and `_fallback_saved_cma_candidates` produce raw rows; `get_cma` then runs them through a shared adjustment helper (lifted from Engine A) before returning the `CMAResult`. Pros: one quality bar across the product; the saved-comp fallback path stops being a quality cliff; comp evidence in BROWSE prose can be a single canonical set. Cons: live Zillow rows have less metadata than saved comps (no rich condition/lot/income data), so several Engine A adjustments may degrade silently; needs careful per-adjustment fallback rules.

**The separate path** would keep Engine B as the user-facing "market support" surface (live-context, lighter scoring) and Engine A as the fair-value anchor (saved comps, full scoring). Concrete shape: Engine B gets its own light scoring (proximity to subject geocoding, listing recency, listing-vs-sale distinction), tracked separately from Engine A's invariants. Pros: clean separation between "fair-value math" and "what's currently on the market"; the user experience stays close to today's structure. Cons: two quality bars to maintain; the prose layer needs to know which engine to cite for what claim.

The audit doesn't make this call — owner decides at the start of Cycle 2.

**One thing the audit makes obvious either way:** the saved-comp fallback in `_fallback_saved_cma_candidates` is currently the worst quality surface in the product. Either path needs to address it.

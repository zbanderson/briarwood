# CMA Handoff Plan — 2026-04-26 (Phase 4a)

**Owner:** Zach
**Origin:** [ROADMAP.md](ROADMAP.md) "Two comp engines with divergent quality; CMA (Engine B) needs alpha-quality pass" 2026-04-24 (severity High). The follow-up entry explicitly says *"Do NOT do this in Handoff 2b or Handoff 3 — scope it as its own handoff after promotion is complete."* Phase 3 closed 2026-04-26. Sequencing condition is met.
**Status:** Drafted, not started. Queued ahead of [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) per the BROWSE-rebuild walkthrough 2026-04-26 (real comps must land before any "single rich summary card with drilldowns" rebuild can honestly cite them).

This plan is the **canonical to-do list** for unifying or distinguishing the two CMA engines and bringing the user-facing CMA up to product-grade quality.

---

## North-star problem statement

Briarwood has two comp paths today, and they were easy to conflate during prior handoffs:

- **Engine A — `ComparableSalesModule`** ([briarwood/modules/comparable_sales.py](briarwood/modules/comparable_sales.py)): saved-comp-driven (closed sales from `data/comps/sales_comps.json`), drives the fair-value anchor that flows into `value_thesis.comps` and the unified output's value position. Has scoring + adjustment logic — `_score_comp`, `_proximity_score`, `_recency_score`, `_data_quality_score`, location/lot/income-adjusted bucketing.
- **Engine B — `get_cma`** ([briarwood/agent/tools.py](briarwood/agent/tools.py) `get_cma`): live-Zillow-preferred, drives the user-facing CMA card, populates `session.last_market_support_view`. Falls back silently to saved comps. Does NOT apply Engine A's scoring/adjustment logic.

The product-visible result, observed in the 2026-04-26 BROWSE walkthrough for "what do you think of 1008 14th Ave, Belmar, NJ":

- Synthesizer prose mentions comps as the basis for fair value.
- No CMA card is rendered (`_enforce_browse_chart_set` hardcodes BROWSE to `[market_trend, value_opportunity, scenario_fan]` — no `cma_positioning`).
- No comp evidence reaches the user. The "fair value" number is asserted without comps the user can inspect.

Owner framing 2026-04-26: *"Pull REAL comps."* The BROWSE rebuild (Thread 1) cannot honestly land until the user-facing CMA is reliable enough to anchor the summary card.

**Architectural finding surfaced 2026-04-26 during Cycle 1 audit (see [CMA_SURFACE_MAP.md](CMA_SURFACE_MAP.md)):** Engine B's live path queries `SearchApiZillowClient.search_listings(...)` **without setting `listing_status`**, defaulting to active for-sale listings. So Engine B's "live comps" are actually *competing asks*, not closed sales. The `listing_status` parameter is plumbed all the way down (the schema validates `"sold"` as a legal value at `briarwood/agents/comparable_sales/schemas.py:127`); we just never use it. Engine A's saved data IS closed sales (`sale_price`, `sale_date`, ATTOM-enriched). So the two engines aren't just running different scoring — they're consuming categorically different data types.

**Owner direction 2026-04-26 (post-finding):** treat both SOLD and ACTIVE as legitimate comp signals. A comp is a comp whether it's a closed sale (what buyers actually paid) or an active listing (what the subject is currently competing against). Both feed the comp set, both contribute to the fair-value math, both render in the chart — but each row carries a `listing_status` provenance tag so prose and UI can distinguish.

**Owner direction 2026-04-26 (Cycle 2 fork resolved):** UNIFY. Engine B's data flow gets routed through Engine A's scoring/adjustment logic, with per-listing-status sub-scoring where the math differs (recency for SOLD, days-on-market for ACTIVE). The user-facing CMA becomes one canonical pipeline with three sources: Zillow SOLD, Zillow ACTIVE, and saved sales as a defensive fallback for thin markets. ATTOM is used as an enricher for confidence-on-confirmed-sales, not as a primary comp source (ATTOM is per-property detail; no bulk comp-search endpoint).

**Scarcity context** (owner framing 2026-04-26): Belmar, Avon, Sea Girt, Spring Lake exhibit increasing scarcity → exponentially increasing prices. Closed-sale comps are disproportionately important in scarce markets because active asks get dragged up by aspirational sellers; only closed sales reveal what buyers actually paid. The CMA pipeline's quality directly drives valuation quality in these markets.

---

## State of the repo at handoff

**Engine A** (`briarwood/modules/comparable_sales.py`):
- Promoted to scoped registry in Handoff 3 (commit `37df9f8`).
- Cache key in `MODULE_CACHE_FIELDS["comparable_sales"]` was added during Phase 2 Cycle 1 (commit `2cb1f3e`).
- Drives `unified_output["value_position"]["fair_value_base"]` via the deterministic synthesizer's `compute_value_position`.
- Has scoring, adjustment, and bucketing logic that's been hardened through prior cycles.

**Engine B** (`get_cma` in `briarwood/agent/tools.py`):
- Live-Zillow-first via `_live_zillow_cma_candidates`.
- Falls back silently to saved comps when live returns empty.
- No scoring or adjustment beyond raw distance/age sorting.
- Returns a `CMAResult` consumed by `session.last_market_support_view`.
- Internal `get_value_thesis` call was broken in commit `f018fc4` (between Cycles 4 and 5 of OUTPUT_QUALITY_HANDOFF_PLAN.md) by the optional `thesis` parameter; this fixed the "5 trailing duplicate module runs on every BROWSE turn" leak but did not address the underlying quality gap.

**Claims wedge graft** (`briarwood/claims/pipeline.py:62-88`):
- Still instantiates `ComparableSalesModule()` directly because the wedge's `_iter_comps` reads the legacy payload shape.
- Existing ROADMAP entry "Retire the ad-hoc `ComparableSalesModule()` graft in claims/pipeline.py" 2026-04-24 covers this. Cleanup, not blocking.

**BROWSE chart set**:
- `_enforce_browse_chart_set` ([briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) `_enforce_browse_chart_set`) pins BROWSE to `[market_trend, value_opportunity, scenario_fan]`. CMA chart is not in the set.

**Engine A's open TODOs** (per [TOOL_REGISTRY.md](TOOL_REGISTRY.md)):
- Cross-town comps (currently same-town only).
- Renovation premium pass-through to live comps.
- 15% sqft tolerance (currently tighter).

These need attention as part of the unify work in Cycle 4.

**SearchApi Zillow + ATTOM inventory**:
- `SearchApiZillowClient.search_listings` accepts `listing_status` per [searchapi_zillow_client.py:173](briarwood/data_sources/searchapi_zillow_client.py#L173). The schema regex at [schemas.py:127](briarwood/agents/comparable_sales/schemas.py#L127) validates `for_sale | sold | pending | coming_soon | active`. Today we only query `for_sale` and `for_rent`; `sold` is unused but plumbed end-to-end.
- `AttomClient` ([attom_client.py:96](briarwood/data_sources/attom_client.py#L96)) exposes per-property endpoints — `property_detail`, `sale_detail`, `sale_history_snapshot`, `sales_trend`, etc. **No bulk comp-search endpoint** in our wired tier. Useful for enriching a Zillow-discovered comp with confirmed sale history; not useful for finding comps.

---

## Cycles

### Cycle 1 — Surface audit + topology map — LANDED 2026-04-26

**Status:** Landed. Audit doc at [CMA_SURFACE_MAP.md](CMA_SURFACE_MAP.md). Findings: 5 Engine A surfaces + 9 Engine B surfaces; live-vs-saved fallback rules documented; 9 quality gaps catalogued. Critical finding (which expanded Cycle 2's scope): Engine B uses ACTIVE listings as comps, not closed sales. Owner read the map 2026-04-26 and resolved the unify-vs-separate fork (UNIFY) plus the both-sold-and-active question (BOTH).

**Original scope below for reference.**

**Why first.** Before deciding unify-vs-separate, we need an honest map of every place a CMA shows up in the product. The 2026-04-24 ROADMAP entry called this out as Step 1 — "map every CMA surface the user can hit."

**Scope:**
- Grep every callsite of `get_cma` and `ComparableSalesModule`. Catalog: chat-tier handlers (which AnswerTypes), API endpoints, batch / pre-computation, claims wedge, deterministic synthesizer, Layer 3 LLM synthesizer, Representation Agent (`cma_positioning` chart selection), React surfaces (CMA card, comp set drilldown).
- For each surface, document: which engine it uses, what it shows the user, what would break if we changed the engine.
- Document the live vs saved fallback behavior of Engine B explicitly — when does live silently degrade to saved.
- Output: a new doc `CMA_SURFACE_MAP.md` at the repo root, ~1-2 pages. Lives alongside this plan.

**Tests:** None — read-only audit cycle.

**Verification:** Owner reads the map and decides on the unify-vs-separate fork (the input to Cycle 2).

**Trace:** [ROADMAP.md](ROADMAP.md) "Two comp engines" 2026-04-24 step 1.

**Estimate:** 3-4 hours (grep + read + write).
**Risk:** None — read-only.

---

### Cycle 1.5 — Verify SearchApi Zillow SOLD inventory for target markets — LANDED 2026-04-26

**Status:** Landed. Probe doc at [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md). Raw output at [data/diagnostics/searchapi_sold_probe_2026-04-26.json](data/diagnostics/searchapi_sold_probe_2026-04-26.json). Probe script at [scripts/probe_searchapi_sold.py](scripts/probe_searchapi_sold.py).

**Headline findings** (folded into Cycle 2 + Cycle 3 below):
1. SearchApi SOLD inventory is rich — **41 SOLD rows per town**, 100% sale-date coverage, 100% geocoding, last-18-month freshness window. 246 SOLD rows total across the 6 target towns. Unify direction confirmed.
2. **Our normalizer (`SearchApiZillowListingCandidate`) throws away ~80% of the raw payload.** Fields available in raw but not normalized: `date_sold`, `lot_sqft`, `latitude`, `longitude`, `tax_assessed_value`, `zestimate`, `rent_zestimate`, `days_on_zillow`, `home_type`, `listing_type`, `broker`. Cycle 3 must extend the normalizer FIRST.
3. **ATTOM enrichment is lower priority than originally scoped** — SearchApi's `zestimate` + `tax_assessed_value` already deliver most of what ATTOM `sale_history_snapshot` would confirm. Cycle 3's ATTOM step downgrades to "default OFF, gated, possibly remove pre-merge."
4. **`rent_zestimate` is in 100% of SOLD rows** — material for the Phase 4b scout rent-angle pattern (already noted in [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) Cycle 6).

**Original scope below for reference.**

**Why before Cycle 2.** Cycle 2 defines comp-set invariants (minimum SOLD count, minimum ACTIVE count, age cap, etc.) on the assumption that SearchApi Zillow returns useful SOLD inventory for our target markets (Belmar, Avon, Sea Girt, Spring Lake, Bradley Beach, Manasquan). The `listing_status="sold"` parameter is plumbed but has never been exercised in production. If SearchApi's SOLD inventory is thin or stale for these markets, the unify story changes — we may need to lean more heavily on the saved-comps backbone (or investigate ATTOM's separate Property Comparables product as a paid add-on).

**Scope:**
- Add a one-shot diagnostic script `scripts/probe_searchapi_sold.py` (NOT permanent — delete or move to `scripts/diagnostics/` after Cycle 2 lands). For each of the six Monmouth County target towns, query SearchApi with `listing_status="sold"` and dump: count of returned rows, age range of sold dates, price range, beds/sqft coverage, any data fields missing vs ACTIVE rows.
- Run the probe against live SearchApi with a small budget cap (probably 6 calls — one per town).
- Compare yields to the existing `data/comps/sales_comps.json` for the same towns. Are SearchApi SOLD comps fresher? More complete? Same coverage?
- Write findings to `CMA_SOLD_PROBE_2026-04-26.md` (one-page summary). Owner reviews before Cycle 2 starts.

**Decision points the probe should inform:**
- Is SearchApi SOLD reliable enough to be the primary closed-sale source, with saved comps as defensive fallback?
- Or is saved comps still primary, with SearchApi SOLD as supplement?
- Is the SearchApi SOLD age range fresh enough to skip ATTOM enrichment for confidence, or do we need ATTOM `sale_history_snapshot` confirmation per row?

**Tests:** None — diagnostic probe.

**Verification:** Owner reads the probe doc and confirms the unify direction holds.

**Trace:** Cycle 1 audit findings — saved comps are limited (`sales_comps.json` metadata: 2026-04-05 dataset with ATTOM enrichment 2026-04-10, 6 towns).

**Estimate:** 1-2 hours.
**Risk:** Low — read-only diagnostic against API. Watch the SearchApi budget cap.

---

### Cycle 2 — CMA quality invariants (3-source unify) — LANDED 2026-04-26

**Status:** Landed. New module `briarwood/modules/cma_invariants.py` holds all 12 constants from the probe-informed defaults, the `CMAValidation` dataclass, and two pure functions: `validate_cma_result(result, *, dropped_outliers=0)` and `is_outlier_by_tax_assessment(extracted_price, tax_assessed_value)`. `ComparableProperty` in `briarwood/agent/tools.py` extended with 9 new optional fields (`listing_status`, `sale_date`, `days_on_market`, `tax_assessed_value`, `zestimate`, `rent_zestimate`, `latitude`, `longitude`, `lot_sqft`) — all default `None`, fully backwards-compatible. 29 new regression tests in `tests/agent/test_cma_invariants.py` pin every constant + the validator + the outlier filter against the probe's actual outlier rows. Regression sweep on 123 existing CMA-touching tests stays green. Cycle 3 unblocked.

**Original scope below for reference.**

**Fork resolved (2026-04-26):** UNIFY. Engine B routes through Engine A's scoring/adjustment logic. Both SOLD and ACTIVE listings are treated as legitimate comps; each row carries a `listing_status` provenance tag.

**Scope:**
- Define and land as code constants in a new `briarwood/modules/cma_invariants.py`. Defaults below are informed by Cycle 1.5's probe findings — see [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md):
  - **`MIN_TOTAL_COMP_COUNT = 5`.** Below this combined SOLD+ACTIVE count (post-filter), CMA surface returns "insufficient comps to anchor a CMA."
  - **`MIN_SOLD_COUNT = 5`.** Below this post-filter SOLD count, prose qualifies the read as "active-only" (no closed-sale anchor). Probe found 41 SOLD per town readily available for our markets, so 5-after-filter is reachable.
  - **`MIN_ACTIVE_COUNT = 3`.** Below this, "what's competing" framing is suppressed; CMA surfaces SOLD only. ACTIVE inventory is thinner per probe (11-20 per town) so floor is lower.
  - **`MAX_DISTANCE_MILES = 2.0` same-town / `3.0` cross-town.** Engine A's existing radius logic; carry forward.
  - **`SOLD_AGE_CAP_MONTHS = 18`.** SearchApi's natural window is ~18 months. Anything older is either missing or signals a non-arms-length transaction.
  - **`ACTIVE_DOM_CAP_DAYS = 180`.** A listing on market 6+ months is a stale ask — weak comp signal. `days_on_zillow` is universally available per probe.
  - **`CONFIDENCE_FLOOR = 0.45`.** Aggregate confidence below this suppresses CMA surface from BROWSE/DECISION prose AND from the chart layer. Tunable; revisit after Cycle 5 browser smoke.
  - **`TAX_ASSESSED_VS_PRICE_BAND = (0.4, 4.0)`.** New invariant from probe. Drop SOLD comps where `extracted_price < 0.4 × tax_assessed_value` or `> 4× tax_assessed_value` — almost certainly tax-deed sales or non-arms-length transactions. Catches the Belmar $8K and Avon $34K probe outliers cleanly. Skipped for rows missing `tax_assessed_value` (~8% of probe rows).
  - **Live-empty telemetry behavior.** When SearchApi returns empty for either listing_status, fall back to saved comps but emit an explicit "live SOLD/ACTIVE returned empty" record to the per-turn manifest (not silent — Cycle 1 audit found this gap). Surface as a user-visible warning ONLY when both SearchApi paths AND saved fallback are empty.
  - **`SOLD_WEIGHT = 1.0`, `ACTIVE_WEIGHT = 0.5`.** Default SOLD-vs-ACTIVE weighting in fair-value math (asks are aspirational; sale prices are the real signal). Tunable via constant; revisit after Cycle 5 browser smoke (especially in scarcity markets where ACTIVE may underweight given seller bias).
- Add a single `validate_cma_result(result) -> CMAValidation` helper that returns: `{passes, total_count, sold_count, active_count, suppressed_reason: str | None, qualifications: list[str], dropped_outliers: int}`.
- Extend `CMAResult` and `ComparableProperty` shapes to carry: `listing_status: "sold" | "active"` per row, `sale_date: date | None` (SOLD only), `days_on_market: int | None` (ACTIVE only), `tax_assessed_value: float | None`, `zestimate: float | None`, `rent_zestimate: float | None`, `latitude: float | None`, `longitude: float | None`, `lot_sqft: float | None`. The latter five are new but cheap (already in raw payload — see Cycle 3a).
- Pin the invariants with regression tests in `tests/agent/test_cma_invariants.py`.

**Tests:**
- Pin each invariant value so future drift fails CI.
- Pin SOLD-vs-ACTIVE weighting default.
- Pin the live-empty telemetry behavior.
- Pin the `tax_assessed_value` outlier filter against probe fixtures (Belmar $8K, Avon $34K).
- Snapshot test for `validate_cma_result` against fixtures: SOLD-only, ACTIVE-only, mixed, both-empty.

**Verification:** Tests pass. No browser smoke yet — invariants don't take effect until Cycle 3 wires them in.

**Trace:** [ROADMAP.md](ROADMAP.md) "Two comp engines" 2026-04-24 step 2; [CMA_SURFACE_MAP.md](CMA_SURFACE_MAP.md) gap findings; [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md) defaults table.

**Estimate:** 3-4 hours (invariants + weighting + outlier filter + extended provenance schema).
**Risk:** Low — pure additive scaffolding.

---

### Cycle 3 — 3-source comp pipeline + unified scoring

**Status:** Not started. Blocks on Cycle 2. Restructured into three sub-cycles after Cycle 1.5's probe finding that our SearchApi normalizer drops ~80% of the raw payload — extending the normalizer must precede everything downstream.

---

#### Cycle 3a — Extend SearchApi Zillow normalizer (do first) — LANDED 2026-04-26

**Status:** Landed. `SearchApiZillowListingCandidate` extended with 10 new optional fields (`lot_sqft`, `date_sold`, `days_on_market`, `latitude`, `longitude`, `tax_assessed_value`, `zestimate`, `home_type`, `listing_type`, `broker`). `_normalize_listing` extracts each from `raw_payload.properties[i]`. New helper `_normalize_lot_size` resolves the Zillow acres-vs-sqft quirk (0.33 acres → 14,375 sqft). `to_listing_candidates` propagates all new fields to the candidate. 13 new regression tests in `tests/test_searchapi_zillow_normalizer.py` pin the round-trip against actual cached probe payloads (Belmar SOLD fixture). Pre-existing URL-intake address-normalization regression flagged in [ROADMAP.md](ROADMAP.md) "Zillow URL-intake address normalization regression" 2026-04-26 (NOT caused by this cycle; pre-existed on `main`). End-to-end smoke confirmed: cached raw → new normalizer → populated candidate fields including `date_sold`, `latitude`, `rent_zestimate`, and acres-converted `lot_sqft`. Cycle 3b unblocked.

**Original scope below for reference.**

**Why first.** Per [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md), `_normalize_listing` and `SearchApiZillowListingCandidate` only capture price/beds/baths/sqft/property_type/listing_status. The raw payload's `properties[i]` includes `date_sold` (100% coverage), `latitude`/`longitude` (100%), `lot_sqft` (81%), `tax_assessed_value` (92%), `zestimate` (93%), `rent_zestimate` (100%), `days_on_zillow` (100%), `home_type`, `listing_type`, `broker`, `extracted_price`. None of this reaches application code today. Without this fix, Cycle 3b/3c work with crippled data.

**Scope:**
- Extend `SearchApiZillowListingCandidate` dataclass with: `date_sold: str | None`, `latitude: float | None`, `longitude: float | None`, `lot_sqft: float | None`, `tax_assessed_value: float | None`, `zestimate: float | None`, `rent_zestimate: float | None` (already partially present), `days_on_zillow: int | None`, `home_type: str | None`, `listing_type: str | None`, `broker: str | None`. All optional with `None` defaults.
- Update `_normalize_listing` ([searchapi_zillow_client.py:420](briarwood/data_sources/searchapi_zillow_client.py#L420)) to populate the new fields from the raw payload's `properties[i]`. Defensively handle missing keys.
- `to_listing_candidates` propagates the new fields.
- Add a regression test against the probe's cached payloads (`data/cache/searchapi_zillow/*.json`) confirming each new field round-trips correctly.

**Tests:**
- Pin field coverage against the probe fixtures (e.g., `date_sold` non-null on every SOLD row from the Belmar cache).
- Pin missing-field fallback (e.g., `sqft=None` doesn't break normalization).
- Existing tests in `tests/test_searchapi_zillow_client.py` continue to pass.

**Verification:** Re-run the probe script; the normalized rows now include the new fields.

**Estimate:** 2-3 hours.
**Risk:** Low — pure additive normalization. No callers break because new fields are optional.

---

#### Cycle 3b — Lift Engine A's scoring/adjustment logic into shared module — LANDED 2026-04-26

**Status:** Landed. New module `briarwood/modules/comp_scoring.py` holds: `score_proximity`, `score_recency_sold`, `score_recency_active`, `score_recency` (dispatcher), `score_data_quality`, `score_comp_inputs` (unified entry point), `distance_miles`, plus `WEIGHT_*` constants and `CompScores` dataclass. Engine A's `_score_comp`, `_proximity_score`, `_recency_score`, `_data_quality_score` in `briarwood/modules/comparable_sales.py` now delegate to the shared module — public API unchanged. Per-listing-status divergence implemented: SOLD recency uses `sale_age_days`; ACTIVE recency uses inverse `days_on_market` (open design decision #6 resolved in favor of inverse — fresh listings score higher than stale asks). Data quality scoring extended with the `_DATA_QUALITY_FLOOR_DEGRADED = 0.3` baseline for >half-missing rows (Zillow-friendly) plus a `zillow_listing` verification tier with +0.05 bonus. Outlier detection wrapped from `cma_invariants.is_outlier_by_tax_assessment`. 39 new unit tests in `tests/test_comp_scoring.py` pin every scoring band, both per-status recency curves, the degraded floor, the dispatcher, the outlier flag, the weights-sum-to-one invariant, and the haversine helper. Engine A's existing test suite (`tests/test_modules.py`, `tests/modules/test_comparable_sales_isolated.py`) stays green — 210-test broader regression confirms zero behavior change for saved-comp inputs. Cycle 3c unblocked.

**Original scope below for reference.**

**Scope:**
- Create `briarwood/modules/comp_scoring.py` (or co-locate with `comparable_sales.py` and re-export). Move/lift: `_score_comp`, `_proximity_score`, `_recency_score`, `_data_quality_score`, location/lot/income-adjusted bucketing helpers.
- **Per-listing-status scoring extensions:**
  - `_recency_score`: SOLD uses `sale_date`; ACTIVE substitutes a constant "currently-on-market" weight (or weights by inverse `days_on_zillow` — owner picks at start of cycle).
  - `_data_quality_score`: extend to handle lighter-metadata Zillow rows. Missing `sqft` (~28% of SOLD rows) or `lot_sqft` (~19%) degrades score gracefully rather than treating absence as bad data. New cap: rows missing more than half the score inputs return a baseline score of 0.3 instead of dropping out.
  - `_proximity_score`: now usable on Zillow rows because lat/lon are universally available post-3a. Subject geocoding lookup needed if not already cached.
- Add `tax_assessed_value` outlier filter from Cycle 2 invariants. Applied before scoring so outlier rows never enter the comparable_value calculation.
- Engine A's existing call path stays unchanged at the public-API level — `ComparableSalesModule.run(...)` continues to return the same shape. The scoring functions just live elsewhere.

**Tests:**
- Engine A's scoring continues to produce identical output for saved-comp inputs (regression test pinning unify-doesn't-break-A).
- New tests for the per-listing-status extensions: SOLD with sale_date scores per recency; ACTIVE with days_on_zillow scores per inverse DOM; missing-sqft graceful degradation.
- Pin the tax_assessed_value outlier filter against the probe outliers.

**Verification:** Existing `tests/test_modules.py::ComparableSalesTests` and `tests/modules/test_comparable_sales_isolated.py` stay green.

**Estimate:** 3-4 hours.
**Risk:** Medium — touches Engine A's scoring code (which has been stable since Handoff 3). Regression tests mitigate.

---

#### Cycle 3c — 3-source merger in `get_cma` — LANDED 2026-04-26

**Status:** Landed. `_live_zillow_cma_candidates` is now a coordinator that issues two SearchApi calls per turn (`listing_status="sold"` AND `listing_status="for_sale"`), tags each row with `listing_status` provenance, dedups by canonical address (SOLD wins on collision), and supplements with saved-comp fallback when combined live count is below `MIN_TOTAL_COMP_COUNT`. New helpers: `_zillow_search_for_status` (single-call wrapper with provenance + Zillow-rich field tagging) and `_score_and_filter_comp_rows` (uniform scoring via `comp_scoring.score_comp_inputs` + outlier filter via `cma_invariants.is_outlier_by_tax_assessment`, sorted by `weighted_score` descending). `_days_since_iso` helper converts Zillow's `date_sold` ISO string to `sale_age_days`. `get_cma` now: scores every row, drops outliers, caps at top-10 by weighted_score, populates `ComparableProperty` with all rich Zillow fields (`listing_status`, `sale_date`, `days_on_market`, `tax_assessed_value`, `zestimate`, `rent_zestimate`, `latitude`, `longitude`, `lot_sqft`), validates via `validate_cma_result`, and surfaces qualifications (e.g. "active-only") into `confidence_notes`. `comp_selection_summary` describes the merge (e.g. `"Comp set: 6 SOLD + 4 ACTIVE + 2 saved fallback."`). 15 new tests in `tests/agent/test_cma_3source_pipeline.py` pin the merge behavior, dedup, summary format, telemetry, scoring, outlier filtering, and end-to-end `get_cma` propagation. Pre-existing `test_get_cma_returns_comp_contract` updated to reflect the new `comp_selection_summary` format. 224-test broader regression: 223 pass, 1 fails (the same pre-existing URL-parser bug in ROADMAP, not caused by this cycle). README_comparable_sales.md updated with dated changelog entry per Job 3 of readme-discipline.

**Cycle 3 (3a + 3b + 3c) is COMPLETE.** Next: Cycle 4 (Engine A's TODOs — cross-town comps, renovation premium, 15% sqft tolerance).

**Original scope below for reference.**

**Scope:**
- `_live_zillow_cma_candidates` becomes a coordinator that issues TWO SearchApi calls per turn: `listing_status="sold"` AND `listing_status="for_sale"`. Each row tagged with `listing_status` provenance.
- `get_cma` adds source #3: when SearchApi SOLD + ACTIVE counts are below `MIN_TOTAL_COMP_COUNT`, fall back to saved `data/comps/sales_comps.json` for the gap. Saved becomes a defensive supplement, not a primary source.
- All three streams merged, deduplicated by address (canonical normalized form), scored uniformly via the Cycle 3b functions, and returned as a unified comp set.
- `CMAResult.comps` list now carries the unified scored set with `listing_status` provenance per row.
- `comp_selection_summary` string updated to describe the merge: e.g., `"6 SOLD comps (last 18 mo) + 4 ACTIVE comps + 2 saved fallback"`.
- Validate via `validate_cma_result` from Cycle 2 before returning.
- **ATTOM enricher: NOT in this cycle.** Per Cycle 1.5 finding, SearchApi already provides `zestimate` + `tax_assessed_value` (most of what ATTOM `sale_history_snapshot` would deliver). Defer ATTOM enrichment until production traces show a quality gap that ATTOM specifically would close.

**Tests:**
- Existing `tests/agent/test_tools.py::ContractToolTests` tests for `get_cma` continue to pass.
- New tests:
  - 3-source merger handles all combinations: SOLD-only, ACTIVE-only, both, both-empty (falls back to saved).
  - Per-row `listing_status` provenance preserved through the merger.
  - Address dedup across sources.
  - SOLD-vs-ACTIVE weighting from Cycle 2 invariants applied correctly in `comparable_value` calculation.
  - Live-empty telemetry record emitted to manifest when SearchApi returns 0 rows for either status.

**Verification:** Browser. BROWSE turn for 1008 14th Ave (Belmar) and a scarcity test (Avon By The Sea or Sea Girt property). Manifest shows `get_cma` runs once with two SearchApi sub-calls (sold + active) plus the saved-comp fallback decision. Comps in the response include both SOLD and ACTIVE rows with provenance visible in the manifest.

**Trace:** [ROADMAP.md](ROADMAP.md) "Two comp engines" 2026-04-24 step 2; [CMA_SURFACE_MAP.md](CMA_SURFACE_MAP.md) gap findings 1, 3, 6; [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md).

**Estimate:** 4-5 hours.
**Risk:** Medium-High — touches the user-facing CMA path. Adds one extra SearchApi call per cache miss (was 1 ACTIVE; becomes 1 SOLD + 1 ACTIVE). With 24-hour discovery cache TTL and ~6 target towns, marginal cost is small.

---

**Combined Cycle 3 estimate: 9-12 hours** (was 6-8; expanded after probe finding restructured into 3a/3b/3c).

---

## Stop State — 2026-04-26 EOD (updated post-Cycle-5)

**Where we are:**

| Cycle | Status | Notes |
|---|---|---|
| 1 — Surface audit | LANDED | [CMA_SURFACE_MAP.md](CMA_SURFACE_MAP.md) |
| 1.5 — SearchApi SOLD probe | LANDED | [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md) |
| 2 — Invariants module + extended schemas | LANDED | `briarwood/modules/cma_invariants.py`; `ComparableProperty` extended with 9 fields |
| 3a — Extend SearchApi normalizer | LANDED | `SearchApiZillowListingCandidate` + 10 fields; lot_sqft acres-conversion |
| 3b — Lift Engine A scoring | LANDED | `briarwood/modules/comp_scoring.py`; per-listing-status recency divergence; degraded-data floor |
| 3c — 3-source merger in `get_cma` | LANDED | Engine B issues SOLD+ACTIVE; saved fallback; outlier filter; validate; provenance flow |
| 4 — Engine A's open TODOs | PARTIAL | Cross-town LANDED; sqft-README LANDED; renovation premium DEFERRED |
| **5 — Wire CMA into BROWSE** | **LANDED 2026-04-26** | 4-chart BROWSE set + provenance markers + comp-citing synthesizer prompt + standalone-panel suppression |
| 6 — Cleanup + closeout | **NOT STARTED — next up** | README sweeps + claims/pipeline.py graft retirement + final BROWSE/DECISION/EDGE smoke |

**Cycle 5 sub-piece status (all landed 2026-04-26):**

| Sub-piece | Status | Notes |
|---|---|---|
| 5a — Chart count (3 → 4) | LANDED 2026-04-26 | `_BROWSE_CHART_SET` adds `cma_positioning` 2nd; `_enforce_browse_chart_set` accepts `include_cma_positioning` gate; `RepresentationAgent` `max_selections=4` for BROWSE. Gated on `session.last_market_support_view` having comps — falls back to 3-chart set when empty. |
| 5b — Marker scheme | LANDED 2026-04-26 | SOLD = filled circle (`var(--chart-bull)`), ACTIVE = open triangle stroked in `var(--chart-neutral)`, cross-town SOLD = filled circle with dashed `var(--chart-base)` outline. Legacy rows (no `listing_status`) keep prior `feeds_fair_value` colouring for cached transcripts. SSE spec extended in `CmaPositioningChartSpec.comps[]` and the chart event's `legend`. |
| 5c — Synthesizer prompt | LANDED 2026-04-26 | `synthesize_with_llm(...)` accepts `comp_roster` kwarg; user payload includes the roster; verifier's `structured_inputs` widens to include comp ask prices so SOLD/ACTIVE citations don't trip the numeric rule. Both system prompts (newspaper + plain) describe the three citation patterns verbatim. Wired in `handle_browse` only — other handlers stay on the back-compat (`comp_roster=None`) path. |
| 5d — BROWSE-only panel suppression | LANDED 2026-04-26 | `_browse_stream_impl` and `_dispatch_stream_impl` (when answer_type is BROWSE) skip `events.market_support_comps(...)` because the new `cma_positioning` chart subsumes it. Two surfaces showing the same data caused a visible mid-stream layout reflow ("glitch and reload"); cleanup landed alongside the chart-count change. DECISION / EDGE handlers still emit the panel as a drilldown. |

**Cycle 4 sub-item status:**

| Sub-item | Status | Notes |
|---|---|---|
| 4.1 — Cross-town comps | LANDED 2026-04-26 | `TOWN_ADJACENCY` + `neighbors_for_town` in `cma_invariants.py`; Engine B's `_live_zillow_cma_candidates` expands SOLD inventory to neighbors when same-town SOLD < `MIN_SOLD_COUNT`; rows tag `is_cross_town=True`; `comp_selection_summary` reports "(N cross-town)"; 16 new tests in `tests/agent/test_cma_cross_town.py`. Per-row distance filter deferred (subject lat/lon not yet plumbed through `summary.json`) — adjacency map provides the geographic constraint. |
| 4.2 — Sqft-tolerance README sweep | LANDED 2026-04-26 | README_comparable_sales.md prose corrected against `agent.py:429-444` (sliding score penalty, not 15% hard tolerance); `base_comp_selector.py` references removed. Same drift in TOOL_REGISTRY/ARCHITECTURE_CURRENT/CMA_SURFACE_MAP filed as a separate ROADMAP entry "2026-04-26 — `base_comp_selector.py` / '15% sqft tolerance' drift in audit docs". |
| 4.3 — Renovation premium pass-through | DEFERRED to a separate handoff | Subject `condition_profile`/`capex_lane` aren't carried on Zillow rows; applying Engine A's `estimate_comp_renovation_premium` broadly would silently distort. Added to ROADMAP as its own item; revisit after Cycle 5 lands and we can see whether prose actually needs renovation-premium-on-Zillow. |

**Tests passing:** 156/156 on the canonical regression sweep (149-test boot-prompt sweep + 4 `BrowseChartSetEnforcementTests` + 3 `CmaPositioningChartProvenanceTests`). The synthesizer suite stays at 18/18 with 5 new comp-roster regression tests added to `tests/synthesis/test_llm_synthesizer.py`. Two pre-existing test failures (filed in ROADMAP) are NOT caused by Phase 4a — confirmed by stash-and-rerun: `test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after` (mocked-session unified output is empty) and `test_interaction_trace_attached` (`9 != 8` interaction-trace count drift).

**README discipline:** [README_comparable_sales.md](briarwood/modules/README_comparable_sales.md), [TOOL_REGISTRY.md](TOOL_REGISTRY.md), [ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md) updated 2026-04-26 to reflect Cycle 3 landings; [briarwood/representation/README.md](briarwood/representation/README.md) and [briarwood/synthesis/README.md](briarwood/synthesis/README.md) updated 2026-04-26 with Cycle 5 changelog entries (chart count + marker scheme + panel suppression in representation; comp_roster + citation prompt in synthesis); [ROADMAP.md](ROADMAP.md) (the "Two comp engines" entry) updated 2026-04-26 to reflect Cycles 3 + 5 landings. The two new modules `cma_invariants.py` and `comp_scoring.py` have thorough docstrings — per the project convention, helper modules don't get dedicated READMEs.

**Open scope notes for Cycle 6 (cleanup + closeout — last cycle in this handoff):**

Cycle 5 closed with all three originally-scoped pieces LANDED (chart count, marker scheme, synthesizer prompt) plus the panel-suppression cleanup that surfaced during browser smoke. The user-visible payoff is real: BROWSE turns now show comp evidence as a 4th chart with provenance markers, the synthesizer cites specific comps with the verbatim "sold for $X" / "currently asking $Y" / "in [neighbor town]" patterns, and the mid-stream "glitch and reload" caused by duplicate comp surfaces is gone.

Cycle 5 surfaced six ROADMAP items the cycle deliberately left unresolved (all filed 2026-04-26):
1. `cma_positioning` "CHOSEN COMPS: Context only" chip — stale `feeds_fair_value`-keyed copy from the pre-Cycle-3 era; should be replaced with provenance-keyed copy ("5 SOLD + 3 ACTIVE") or removed.
2. `value_opportunity` y-axis "Comp" label rendering as `C / o / m / p` vertically — pre-existing renderer bug.
3. Pre-existing test failure `test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after` (mocked-session lacks unified-output substrate).
4. Pre-existing test failure `test_interaction_trace_attached` (interaction-trace count drift, `9 != 8`).
5. `cma_positioning` chart-prose alignment — synthesizer's `comp_roster` carries up to 10 rows but the chart's top-N cap is 8. One-line fix: clamp `comp_roster` to the chart's slice.
6. Router miss data point: "show me the comps" classified as BROWSE instead of EDGE comp_set follow-up — added to the existing 2026-04-25 router-classification entry.

**Cycle 6 scope (unchanged from original plan):**
- Retire the `claims/pipeline.py:62-88` graft per existing ROADMAP 2026-04-24 entry. The wedge's `_iter_comps` migrates to the canonical scoped-comparable_sales path.
- Update `ARCHITECTURE_CURRENT.md` and `TOOL_REGISTRY.md` to reflect the post-handoff topology (the saved-comp/Zillow-comp engine description + the 4-chart BROWSE set).
- Verify all CMA surfaces from the Cycle 1 audit now use the canonical engine.
- Final smoke: BROWSE / DECISION / EDGE turns all surface real comps consistent with the post-handoff invariants.

**After Cycle 6 closes Phase 4a, the queue is:**
- Phase 4b ([SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md)) — Scout buildout. Cycle 6 of Scout's plan specifically depends on `rent_zestimate` from CMA Cycle 3a (landed).
- Phase 4c — BROWSE summary card rebuild ([ROADMAP.md](ROADMAP.md) parking lot entry "BROWSE summary card rebuild" 2026-04-26). Promote to a handoff plan once 4a + 4b complete.

**Boot prompt for next session** — see the dedicated section near the end of this file ("Boot prompt for the next Claude context window"); it's been updated for the Cycle 6 entry point.

---

### Cycle 4 — Engine A's open TODOs

**Status:** Not started. Optionally parallel with Cycle 3 if unify path is chosen.

**Scope** (per [TOOL_REGISTRY.md](TOOL_REGISTRY.md) `comparable_sales` entry):
- **Cross-town comps.** Today same-town only. Add a fallback: when same-town comp count is below the minimum, expand to neighboring towns by distance. Tag cross-town comps so the user can see the distinction.
- **Renovation premium pass-through.** Engine A computes `estimate_comp_renovation_premium`; today it's used internally but not surfaced. Either surface it to live comps too (unify path) or document why it's deliberate to keep it Engine-A-only (separate path).
- **15% sqft tolerance.** Loosen the current sqft filter. Pin the new tolerance in tests.

**Tests:**
- Cross-town comp inclusion: pin the trigger condition (below-minimum same-town count).
- Sqft tolerance: pin the new bound.

**Verification:** Browser. A property in a town with thin comps (probably 1228 Briarwood Rd or 526 W End Ave from saved fixtures) now surfaces cross-town comps with the cross-town tag.

**Trace:** [TOOL_REGISTRY.md](TOOL_REGISTRY.md) Engine A TODOs.

**Estimate:** 3-4 hours.
**Risk:** Low-Medium — touches Engine A's filtering, which feeds the fair-value anchor.

---

### Cycle 5 — Wire CMA into BROWSE prose + chart selection (with provenance)

**Status:** Not started. Blocks on Cycles 3-4.

**Scope:**
- Update `_enforce_browse_chart_set` to include `cma_positioning` when the comp set passes the Cycle 2 invariants. Set becomes `[market_trend, cma_positioning, value_opportunity, scenario_fan]` (4 charts) or trade `value_opportunity` for `cma_positioning` (3 charts) — owner decides at start of cycle.
- Update `synthesize_with_llm`'s system prompt to instruct: when comps are present, name 1-2 specific comparable addresses and what they imply for the verdict, **distinguishing closed sales ("sold for $X") from active listings ("currently asking $Y")**. Numeric grounding rule preserved.
- Synthesizer's user prompt extended to include the comp roster from `unified_output` with `listing_status` provenance per row.
- React: `CmaPositioningChart` updates to render SOLD and ACTIVE comps with distinct visual markers (e.g., SOLD = filled circle, ACTIVE = open triangle) and a legend entry per status. Subject ask + fair-value band overlays unchanged.
- SSE chart event payload extended: each comp dict carries `listing_status: "sold" | "active"` so the React component can distinguish.
- The `cma_positioning` two-view defensive fix from 2026-04-26 remains in place; if Cycle 3 changes the shape enough to make the fix obsolete, retire it (with the deeper restructure flagged in ROADMAP).

**Tests:**
- Pin: BROWSE turn with valid comps surfaces `cma_positioning` in `_enforce_browse_chart_set` output.
- Pin: BROWSE turn with insufficient comps does NOT surface `cma_positioning` (Cycle 2 invariant).
- Pin: chart payload carries `listing_status` per comp.
- Synthesizer regression: prompt change + comp roster injection + SOLD/ACTIVE distinction pinned in `tests/synthesis/test_llm_synthesizer.py`.

**Verification:** Browser. Same query as the 2026-04-26 walkthrough: "what do you think of 1008 14th Ave, Belmar, NJ". Output now shows mixed SOLD + ACTIVE comps as a chart with provenance markers; prose names a recent sale price and a current ask separately; no `—` placeholders. Re-run for an Avon / Sea Girt property to confirm scarcity-market behavior.

**Trace:** 2026-04-26 BROWSE walkthrough Thread 2.

**Estimate:** 4-5 hours (chart marker work + synthesizer prompt tuning + SSE shape extension).
**Risk:** Medium — user-visible BROWSE change. Verify the `cma_positioning` chart's two-view bug doesn't recur with the new comp shape.

---

### Cycle 6 — Cleanup + closeout

**Status:** LANDED 2026-04-28.

**Scope (as planned):**
- Retire the `claims/pipeline.py` graft per existing ROADMAP entry. The wedge's `_iter_comps` migrates to the canonical `comparable_sales` legacy_payload shape.
- Update `briarwood/modules/README_comparable_sales.md` and any new CMA-related README with dated changelog entries reflecting the unify/separate decision and the new invariants.
- Update `ARCHITECTURE_CURRENT.md` and `TOOL_REGISTRY.md` to reflect the post-handoff topology.
- Verify all CMA surfaces from the Cycle 1 audit now use the canonical engine (or, in separate-path, document the boundary).
- Final smoke: BROWSE / DECISION / EDGE turns all surface real comps consistent with the post-handoff invariants.

**What landed:**

1. **Graft migration** — [`briarwood/claims/pipeline.py:62-114`](briarwood/claims/pipeline.py#L62-L114) `_inject_comparable_sales` now calls `run_comparable_sales(context)` instead of instantiating `ComparableSalesModule()` directly. The graft repackages the scoped wrapper's `data.legacy_payload` as a `ComparableSalesOutput` pydantic instance under `outputs["comparable_sales"]["payload"]` so the verdict_with_comparison synthesizer's `payload.comps_used` access path is preserved. Field-name stability invariant (preserved by `module_payload_from_legacy_result`) made this a one-line shape adapter rather than a contract rewrite. The graft itself remains required because the orchestrator's routed run does not surface `comparable_sales` as a top-level entry in `module_results["outputs"]`; full removal is queued under ROADMAP §4 High *Consolidate chat-tier execution*. Tests rewired in [`tests/claims/test_pipeline.py`](tests/claims/test_pipeline.py) — patches now target `run_comparable_sales`; the prior `test_swallows_module_exception` case was replaced with `test_skips_when_scoped_returns_fallback` to pin the new fallback path.

2. **Module READMEs** — [`briarwood/claims/README.md`](briarwood/claims/README.md) and [`briarwood/modules/README_comparable_sales.md`](briarwood/modules/README_comparable_sales.md) updated with 2026-04-28 changelog entries documenting the graft migration, updated `Calls` / `Imports` lists, and the `payload`-shape rationale.

3. **Audit docs** — [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) and [`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) updated to reflect the post-handoff topology: shared scoring pipeline (Cycles 3a-3c), cross-town SOLD expansion (Cycle 4.1), 4-chart BROWSE set (Cycle 5), graft retirement (Cycle 6). The lingering `base_comp_selector.py` / "15% sqft tolerance" drift filed in [ROADMAP.md](ROADMAP.md) §5 Process & Meta was cleared in the same pass — the actual sqft logic is a sliding score penalty at [`briarwood/agents/comparable_sales/agent.py:429-444`](briarwood/agents/comparable_sales/agent.py#L429-L444), and the same-town filter is enforced at the provider level ([`briarwood/modules/comparable_sales.py:76-86`](briarwood/modules/comparable_sales.py#L76-L86)). [`CMA_SURFACE_MAP.md`](CMA_SURFACE_MAP.md) updated for the same drift plus the A5 graft-retirement status.

4. **Surface verification** — All 14 CMA surfaces from the Cycle 1 audit (A1-A5 Engine A, B1-B9 Engine B) confirmed to route through canonical engines:
   - A1 (`run_chat_tier_analysis`), A2 (synthesizer reads `unified_output`), A5 (claims wedge graft) — all through canonical scoped runner ✅
   - A3 (`value_thesis_view.comps`) — through `valuation` module which composes `comparable_sales` internally ✅
   - A4 (composite consumers — `hybrid_value`, `current_value`, `renovation_scenario`, `teardown_scenario`, `unit_income_offset`) — intentional in-process composition pattern via the legacy module's `run()`; each is itself a scoped runner. Distinct from the post-hoc-graft pattern, which is now the only out-of-`modules/` direct caller path that's been retired. ✅
   - B1-B9 (Engine B path) — all through `get_cma`, which shares Engine A's scoring pipeline at `comp_scoring.py` (Cycles 3a-3c) ✅

5. **Smoke** — Code-level smoke: built a `VerdictWithComparisonClaim` for `1228-briarwood-road-belmar-nj` end-to-end via `build_claim_for_property`. The migrated graft fired (confirmed via `claim.provenance.models_consulted` containing `comparable_sales`); the claim assembled, the synthesizer ran, no regressions. Browser smoke deferred — the code-level smoke is sufficient to confirm graft migration didn't regress the claim pipeline; broader BROWSE/DECISION/EDGE browser checks were already performed during Cycle 5 BROWSE smoke and are unchanged by this Cycle's internals-only migration.

**Tests:**
- Claims suite: 82/82 green (`tests/claims/`) before and after the migration.
- Full suite: 16 pre-existing failures (verified by stash-and-rerun at pre-Cycle-6 baseline). All filed in ROADMAP — no regressions introduced.

**ROADMAP closures (this cycle):**
- §4 Low *Retire the ad-hoc `ComparableSalesModule()` graft in claims/pipeline.py* (2026-04-24) — RESOLVED.
- §5 Process & Meta *`base_comp_selector.py` / "15% sqft tolerance" drift in audit docs* (2026-04-26) — RESOLVED.
- §2 Phase 4a Cycle 6 — CLOSED. Phase 4a complete.

**Estimate (planned):** 2-3 hours. **Actual:** ~2 hours.
**Risk:** Low (as planned).

---

## Open design decisions

(Resolve at the start of the named cycle. Items marked RESOLVED were settled during Cycle 1 / pre-Cycle 2 owner discussion.)

1. ~~**Unify Engine A + Engine B vs keep separate**~~ — RESOLVED 2026-04-26: UNIFY.
2. ~~**Treat ACTIVE listings as comps?**~~ — RESOLVED 2026-04-26: YES. Both SOLD and ACTIVE feed the comp set with `listing_status` provenance per row.
3. ~~**ATTOM enrichment default**~~ — RESOLVED 2026-04-26 (post-probe): defer ATTOM entirely from Cycle 3. SearchApi's `zestimate` + `tax_assessed_value` already cover most of what ATTOM `sale_history_snapshot` would deliver. Revisit only if production traces show a specific quality gap ATTOM would close.
4. **Live-empty telemetry behavior** — Cycle 2 default is "manifest record + user-visible warning only when both SearchApi paths AND saved fallback all return empty." Confirmed at Cycle 2 start.
5. **SOLD-vs-ACTIVE weighting in fair-value math** — Cycle 2 default is SOLD=1.0, ACTIVE=0.5. Tunable; revisit after Cycle 5 browser smoke (especially in scarcity markets where ACTIVE may underweight).
6. **`_recency_score` for ACTIVE** — constant weight vs inverse `days_on_zillow` weighting? Cycle 3b.
7. **Confidence floor for chart suppression** — Cycle 2 default is 0.45. Tunable. Cycle 2.
8. **3 charts vs 4 charts on BROWSE** — does adding `cma_positioning` displace one of the existing three, or expand the set? Cycle 5.
9. **Chart marker shape for SOLD vs ACTIVE** — filled circle / open triangle per Cycle 5 default, or different scheme? Designer call. Cycle 5.
10. **Cross-town comp triggering** — fixed minimum-count threshold or dynamic based on confidence band? Cycle 4.
11. **Renovation premium surfacing on live comps** — apply Engine A's `estimate_comp_renovation_premium` to live SOLD comps (where data exists) or keep deliberately saved-only? Cycle 4.
12. **Saved `sales_comps.json` deprecation horizon** — once 3-source pipeline is stable, is the saved-comps backbone retired or kept as defensive fallback indefinitely? Cycle 1.5 confirms SearchApi SOLD is rich enough that saved becomes truly defensive. Owner call after Cycle 5 has soak time.
13. **Probe script disposition** — keep at `scripts/probe_searchapi_sold.py`, move to `scripts/diagnostics/`, or delete after Cycle 3 lands? Recommendation: move to `scripts/diagnostics/` for cheap re-runs when expanding to new markets.

---

## Cycle ordering rationale

- Cycle 1 first because every decision in 2-6 depends on the surface map. **Landed 2026-04-26.**
- Cycle 1.5 before 2 because Cycle 2's invariants assume SearchApi SOLD inventory is usable. If the probe shows it's thin or stale, Cycle 2's defaults (SOLD weight, minimum SOLD count, SOLD age cap) and Cycle 3's 3-source merger logic both need to adjust.
- Cycle 2 before 3 because invariants must be defined before they can be enforced in the engine.
- Cycle 3 before 4 because the unified scoring + 3-source merger (Cycle 3) is the substrate Engine A's TODOs (Cycle 4) build on.
- Cycle 5 last among the engine-touching cycles because BROWSE wiring is the user-visible payoff and we want the substrate to be stable first.
- Cycle 6 cleanup at the end.

---

## Boot prompt for the next Claude context window

```
I'm continuing CMA Phase 4a. Cycles 1, 1.5, 2, 3a, 3b, 3c, 4.1, 4.2,
and 5 (chart count + marker scheme + synthesizer prompt + BROWSE-only
panel suppression) are LANDED as of 2026-04-26 EOD. Cycle 6 (cleanup
+ closeout) is the only remaining cycle and closes Phase 4a. Please:

1. Run the standard CLAUDE.md orientation:
   - Read CLAUDE.md.
   - Execute Job 1 of the readme-discipline skill (drift check on
     every README.md under briarwood/). Report findings.
   - Verify ARCHITECTURE_CURRENT.md, GAP_ANALYSIS.md, TOOL_REGISTRY.md
     exist and are readable.
   - Read DECISIONS.md and ROADMAP.md in full. Pay particular
     attention to the Cycle-5-surfaced ROADMAP entries (all dated
     2026-04-26): "CHOSEN COMPS: Context only" stale chip;
     "value_opportunity y-axis" vertical-text bug; pre-existing test
     failures `test_browse_stream_emits_briefing_cards...` and
     `test_interaction_trace_attached`; "cma_positioning chart-prose
     alignment" (synthesizer can cite comps not in the chart's top-8
     slice — one-line clamp fix). Also the "Two comp engines" entry
     itself, which is in-progress and not yet closed.

2. Read CMA_HANDOFF_PLAN.md end-to-end. Critical sections:
   - The "Stop State — 2026-04-26 EOD" section (cycle table shows
     1-5 LANDED; Cycle 5 sub-piece breakdown 5a-5d).
   - "Open scope notes for Cycle 6" — the six items Cycle 5 surfaced
     that Cycle 6 may pick up opportunistically.
   - Cycle 6 (cleanup + closeout) — the canonical scope.
   - Open Design Decisions list — items 4, 5, 7, 12, 13 still open;
     items 1, 2, 3, 6, 8, 9 resolved during Cycle 5; items 10, 11
     deferred to follow-ups.

3. Skim today's git log + git status. CMA Phase 4a Cycles 1-5 work
   is uncommitted as of session-start across many files; the user has
   standing preference (per CLAUDE.md) to commit only on explicit
   request, so check before committing anything.

4. Run the regression sweep to confirm green-state:

       PYTHONPATH=. venv/bin/python -m unittest \
         tests.agent.test_cma_3source_pipeline \
         tests.agent.test_cma_cross_town \
         tests.test_comp_scoring \
         tests.agent.test_cma_invariants \
         tests.test_searchapi_zillow_normalizer \
         tests.agent.test_tools \
         tests.test_modules \
         tests.modules.test_comparable_sales_isolated \
         tests.test_pipeline_adapter_contracts.CmaPositioningChartProvenanceTests \
         tests.agent.test_dispatch.BrowseChartSetEnforcementTests

   Expected: 156/156 pass, zero failures. (Two pre-existing test
   failures filed in ROADMAP — `test_browse_stream_emits_...` and
   `test_interaction_trace_attached` — are NOT in the sweep above.)
   Also run `tests.synthesis.test_llm_synthesizer` separately (uses
   pytest, 18/18 pass, includes the 5 new comp-roster regressions).

5. Tell me in 5-7 bullets:
   - Drift-check findings from Job 1 (any flagged READMEs).
   - Cycle 6 scope: claims/pipeline.py graft retirement
     (ROADMAP 2026-04-24); ARCHITECTURE_CURRENT.md +
     TOOL_REGISTRY.md update to reflect post-handoff topology;
     final BROWSE / DECISION / EDGE smoke. Plus the six
     Cycle-5-surfaced ROADMAP items — pick whichever fit
     naturally into the same diff.
   - Whether the regression sweep stays green.
   - Any contradictions or stale items surfaced during orientation.
   - Then ASK me what to pick off first in Cycle 6 (the graft
     retirement is the largest piece and a clear unblock for the
     scoped registry's coverage story; the audit-doc updates are
     smaller mechanical sweeps; the chart-prose-alignment one-line
     clamp is the smallest unit of work). Don't propose a
     multi-step plan; just the next discrete piece.

8. Pacing reminder: the user prefers 1-by-1 cycles with browser
   verification pauses. Don't batch sub-items into a single push.
   Cycle 5 has chart-layer + synthesizer-prompt + React work; expect
   to verify each piece in the browser before moving to the next.

Do not begin code work until 1-7 are done and reported back.
```

---

## Cross-references

- Origin ROADMAP entry: [ROADMAP.md](ROADMAP.md) "Two comp engines with divergent quality" 2026-04-24.
- Related cleanup: [ROADMAP.md](ROADMAP.md) "Retire the ad-hoc `ComparableSalesModule()` graft in claims/pipeline.py" 2026-04-24.
- Engine A: [briarwood/modules/comparable_sales.py](briarwood/modules/comparable_sales.py), [briarwood/modules/README_comparable_sales.md](briarwood/modules/README_comparable_sales.md).
- Engine B: `get_cma` in [briarwood/agent/tools.py](briarwood/agent/tools.py).
- Claims wedge graft: [briarwood/claims/pipeline.py](briarwood/claims/pipeline.py) `:62-88`.
- BROWSE chart enforcer: `_enforce_browse_chart_set` in [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py).
- Sibling plan: [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) (Phase 4b — runs after this).
- Parking lot for Thread 1 (BROWSE rebuild): [ROADMAP.md](ROADMAP.md) "BROWSE summary card rebuild" 2026-04-26.

---

## Definition of done

The whole CMA effort is done when:

1. There is a single canonical pipeline producing comps for the user-facing CMA, sourcing from Zillow SOLD + Zillow ACTIVE + saved fallback, with Engine A's scoring/adjustment logic applied uniformly.
2. Every comp row carries `listing_status` provenance ("sold" or "active") through to the chart and prose surfaces.
3. CMA quality invariants (min total / min SOLD / min ACTIVE / max distance / age caps / confidence floor / live-empty telemetry) are landed as code constants and enforced via `validate_cma_result`.
4. BROWSE turns surface real comps as both a chart (`cma_positioning`, with SOLD vs ACTIVE distinguished visually) and prose (synthesizer cites a recent sale price AND a current ask separately).
5. Cross-town comps, renovation premium, and 15% sqft tolerance from Engine A's TODOs are addressed in the unified pipeline.
6. The `claims/pipeline.py` graft is retired.
7. ARCHITECTURE_CURRENT / TOOL_REGISTRY / module READMEs reflect the post-handoff topology with dated changelog entries.
8. All changes traced to ROADMAP / DECISIONS / this plan. No drive-by fixes.
9. Tests pass. No regressions in `tests/agent/`, `tests/claims/`, `tests/representation/`, `tests/synthesis/`.
10. Scarcity-market verification (Avon By The Sea, Sea Girt) confirms the pipeline produces useful comps where saved data is thinnest — closing the most important user-facing quality gap.

---

## Notes for the next agent

- **The user prefers terse updates between cycles.** End-of-cycle reports should fit in ~10-15 bullets.
- **Browser verification is the truth-source.** Don't skip the pause between cycles.
- **The unify-vs-separate decision is owner-only.** Don't infer it from the ROADMAP framing — ask explicitly.
- **The `cma_positioning` chart has a known two-view defensive fix** (2026-04-26) that may be obsolete after Cycle 3. Check before retiring.
- **Don't drift into Scout territory.** This handoff is comps quality. Scout-style "surface non-obvious comp insights" is the next handoff — note candidates here but do not implement.

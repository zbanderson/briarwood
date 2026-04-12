# Briarwood Technical Analysis — Executive Summary

**Date:** 2026-04-11

---

## By the Numbers

| Metric | Value |
|--------|-------|
| Total Python source lines | ~64,800 |
| Dead/redundant lines (confirmed safe to delete) | ~1,900 (3%) |
| Largest file (`components.py`) | 7,992 lines |
| Dead lines in `components.py` alone | ~900 (11% of file) |
| Callbacks in `app.py` | 47 |
| Callbacks with `allow_duplicate=True` | 5 output IDs × 5-7 writers each |
| `dcc.Store` components | 18 |
| Analysis modules in pipeline | 20+ |
| All imported eagerly at startup | Yes |

---

## Top 5 Performance Bottlenecks

1. **`render_main_tab` callback (app.py:3529)** — 7 Inputs, rebuilds entire visible tab on ANY state change. No `ctx.triggered_id` guards. Changing a filter rebuilds the whole page. This is the single biggest source of perceived slowness.

2. **Eager import of all 20+ analysis modules at startup** — `data.py` imports `briarwood.runner` at module level, which pulls in every analysis module and the PDF renderer. This happens before the user sees anything.

3. **`build_property_analysis_view` calls market analysis internally (view_models.py:1804)** — Every property view build triggers `analyze_markets()` when the cache is cold, doubling the cost of property selection.

4. **Markets tab loads ALL saved properties on first visit** — `_opportunity_records()` iterates every discoverable property and runs full analysis for any not yet cached. O(N) cold start.

5. **Zero `clientside_callback` usage** — 5+ pure CSS-toggle callbacks (show/hide drawer, switch chart/table view) make unnecessary server round-trips.

---

## Top 5 Dead Code to Remove Immediately

1. **12 dead functions in `components.py`** (~900 lines) — v1 scoring UI remnants (`render_lens_selector`, `render_score_header`, `render_executive_summary`, `render_category_section`, `render_property_verdict`, `render_perspective_block`, `render_what_if_slider`, etc.) with their private helpers. Never called.

2. **Dead tour system** (~190 lines across app.py + components.py) — `_TOUR_STEPS`, `render_tour_overlay`, tour callbacks all disabled with hardcoded `None`/`-1` returns.

3. **Dead files: `entry_prep.py`, `local_intelligence/ui.py`, `dashboard_contract.py`, `current_value/inspect_data.py`** (~354 lines) — Never imported by production code.

4. **Dead modules: `market_snapshot.py`, `relative_opportunity.py`** (~461 lines + ~184 lines of tests) — Only referenced by their own test files, never imported by engine, runner, or dash app.

5. **Dead `format_tear_sheet_summary()` in runner.py** (~50 lines) — Defined but never called.

---

## Biggest Architectural Blockers to Target UX

1. **Tab routing system** — All navigation flows through `MAIN_TABS` and `render_main_tab`. The landing page is a conditional fallback inside the `tear_sheet` tab, not a first-class screen. Converting to a screen state machine is prerequisite for everything else.

2. **Workspace shell (sidebar + topbar + context bar)** — The 264px navy sidebar, property selector dropdown, and context bar chrome wrap every screen. These are institutional dashboard patterns that must be removed or made conditional per screen.

3. **Dual Layer 1 implementations** — `render_property_decision_summary()` (System A, in components.py, what users see) and `render_quick_decision()` (System B, in components_quick_decision.py, cleaner but never called). Must merge into one and gate the transition to deeper layers.

4. **No progressive disclosure gate** — Layer 1 (decision summary) scrolls directly into Layer 2/3 content (charts, comps, risk). There is no "dig deeper" action between the 10-second answer and the full analysis.

5. **No map component** — No Mapbox, Leaflet, or scattermapbox imports exist anywhere. The target design needs maps on Landing, Town Results, and possibly Markets.

---

## Effort Breakdown

| Work | Effort | Impact |
|------|--------|--------|
| Safe deletes (dead code, files, tour) | **2-4 hours** | Cleaner codebase, ~1,900 fewer lines |
| Performance quick wins (lazy imports, ctx guards, clientside callbacks) | **1-2 days** | 40-60% faster startup, 50-70% fewer redundant rebuilds |
| Deduplication + cache unification | **Half day** | Fewer bugs, less memory waste |
| Screen state machine (replace tabs) | **2-3 days** | Unblocks all UX restructuring |
| Dismantle dashboard chrome (sidebar, topbar, context bar) | **1-2 days** | Enables search-first experience |
| Progressive disclosure gate (L1→L2→L3) | **1-2 days** | Core UX transformation |
| New components (map, simplified cards, monthly reality hero) | **3-5 days** | Fills target UX gaps |
| URL-first intake flow refinement | **1 day** | "Paste and get an answer" experience |

**Total: ~9-16 days of focused work** to go from current state to target UX.

---

## If You Only Do 3 Things, Do These

### 1. Delete the dead code and defer the imports (half day)

Remove ~1,900 lines of dead functions/files/tour system and move `briarwood.runner` and `pdf_renderer` imports to be lazy in `data.py`. Zero risk, immediate payoff: cleaner codebase and 40-60% faster startup. This is free money.

### 2. Split `render_main_tab` and add `ctx.triggered_id` guards (1-2 days)

The single biggest performance problem. The monolithic 7-input callback rebuilds everything on every state change. Split it into per-screen renderers with early-exit guards. This alone will make the app feel dramatically faster.

### 3. Merge Layer 1 systems and add the progressive disclosure gate (2-3 days)

Kill `render_property_decision_summary()` (System A). Promote `render_quick_decision()` (System B) as the primary property view. Add a "Dig Deeper" button that transitions to Layer 2. This is the single most important UX change — it transforms the experience from "wall of analytics" to "answer first, details on demand."

---

## Detailed Reports

| Report | File |
|--------|------|
| Codebase Inventory | [01_codebase_inventory.md](01_codebase_inventory.md) |
| Technical Debt & Dead Code | [02_technical_debt.md](02_technical_debt.md) |
| Performance Analysis | [03_performance.md](03_performance.md) |
| UI Gap Analysis | [04_ui_gap_analysis.md](04_ui_gap_analysis.md) |
| Migration Plan | [05_migration_plan.md](05_migration_plan.md) |

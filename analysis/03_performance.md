# Briarwood Dash App — Performance Analysis

**Date:** 2026-04-11
**Scope:** Startup cost, callback efficiency, data loading, layout weight, client-side burden, caching gaps

---

## Executive Summary

The app has **three dominant bottlenecks**: (1) the `render_main_tab` callback fires on 7 Inputs and rebuilds the entire visible page on every minor state change, (2) `build_property_analysis_view` is expensive and calls `build_market_view_model` (market analysis) inside every single property view build, and (3) the Markets/Opportunities tab eagerly loads and runs full analysis for every saved property via `_opportunity_records`. Startup import time is moderate but not the primary issue — the perceived "heaviness" is almost entirely callback-driven.

---

## 1. Startup Cost

### Import Chain

When `run_dash.py` runs `from briarwood.dash_app.app import app`, the following happens at module level:

1. **`briarwood/__init__.py`** — Loads `.env` via dotenv. Cheap.

2. **`briarwood/dash_app/app.py`** (5,320 lines) — All imports execute at module load:
   - `briarwood.dash_app.components` (7,992 lines) — Imports plotly, dash_table, the quick_decision module, and scoring_config. All component-builder functions are defined but not called.
   - `briarwood.dash_app.data` (764 lines) — Imports `briarwood.runner` which imports **all 20+ analysis modules** (CostValuation, ComparableSales, RiskConstraints, etc.) and `briarwood.reports.pdf_renderer` which imports weasyprint-related code. These are imported **eagerly** even though most users never trigger PDF export or a fresh analysis run from the Dash UI.
   - `briarwood.dash_app.view_models` (2,893 lines) — Imports market_analyzer, value_finder, local_intelligence, evidence, recommendations, reports/section_helpers, thesis/conclusion builders.
   - `briarwood.dash_app.theme` (428 lines) — Pure constants. Cheap.
   - `briarwood.agents.comparable_sales.store` — JSON store loader.
   - `briarwood.evidence` — Confidence breakdown computation.
   - `briarwood.listing_intake.parsers` — URL parser.

3. **`app.layout = _build_layout()`** (line 2621) — Executes `_build_layout()` which builds the shell (sidebar, topbar, tab bar, stores, drawers). This calls:
   - `_build_shell_sidebar("tear_sheet")` — Builds sidebar navigation.
   - `_topbar()`, `_feedback_banner()`, `_main_tab_bar()` — Static layout elements.
   - `_add_property_drawer()`, `_market_property_preview_drawer()` — **Two full drawer layouts built eagerly** and placed in the DOM with `display: none`.

4. **48 `@app.callback` decorators** all register at import time. This is normal Dash behavior.

### Key Startup Issues

| Issue | Severity | Location |
|-------|----------|----------|
| `data.py` imports `briarwood.runner` at module level, pulling in all 20+ analysis modules and the PDF renderer | **High** | `data.py:17-18` |
| All 48 callbacks defined in a single 5,320-line file | **Medium** | `app.py` |
| Two drawer layouts (`_add_property_drawer`, `_market_property_preview_drawer`) built eagerly and hidden | **Low** | `app.py:2611-2612` |

### Recommendation

Defer the import of `briarwood.runner` and `briarwood.reports.pdf_renderer` inside `data.py` to the functions that actually use them (`_load_json_report`, `_load_listing_report`, `export_preset_tear_sheet`, `export_preset_tear_sheet_pdf`). This avoids importing all analysis modules and the PDF stack at startup:

```python
# data.py — current (eager)
from briarwood.runner import run_report, run_report_from_listing_text, write_report_html
from briarwood.reports.pdf_renderer import write_tear_sheet_pdf

# data.py — proposed (lazy)
def _load_json_report(path: str) -> AnalysisReport:
    from briarwood.runner import run_report
    return run_report(DATA_DIR / path)
```

---

## 2. Callback Performance

### The "God Callback": `render_main_tab` (line 3529)

This is the single most impactful performance problem. It has **7 Inputs**:

```python
@app.callback(
    Output("main-tab-content", "children"),
    Input("main-tabs", "value"),                    # tab switch
    Input("property-catalog-version", "data"),      # catalog refresh
    Input("loaded-preset-ids", "data"),              # property list changes
    Input("property-selector-dropdown", "value"),    # property selection
    Input("town-pulse-filter", "data"),              # filter toggle
    Input("selected-market-town", "data"),           # market town selection
    Input("market-sort-mode", "data"),               # sort mode change
)
```

**Problem:** Any change to any of these 7 stores causes a full re-render of the entire visible tab content. Changing the town pulse filter (a small UI toggle) rebuilds the entire tear sheet. Changing the market sort mode rebuilds the entire Markets page. The callback does not use `ctx.triggered_id` to short-circuit irrelevant triggers — it unconditionally rebuilds everything.

**Impact:** The tear sheet path calls `_build_property_view_for_property` (which calls `build_property_analysis_view`) and then `render_tear_sheet_body` — together these build ~200 Plotly chart objects and hundreds of Dash HTML components. The markets path calls `_build_market_view_block` which calls `build_market_view_model` and `_opportunity_records`.

### Callback Cascade on Property Selection

When a user selects a property from the dropdown, this cascade fires:

1. `select_property` (line 3132) → sets `loaded-preset-ids` → triggers 5 callbacks
2. `render_main_tab` (7 inputs) → full page rebuild
3. `refresh_property_controls` → rebuilds dropdown options + saved properties table + comp database table
4. `render_active_property_status` → rebuilds header bar (calls `_load_report_for_property` + `_build_property_view_for_property`)
5. `render_shell_sidebar` (4 inputs) → rebuilds sidebar
6. `render_shell_context_bar` (5 inputs) → rebuilds context bar
7. `render_shell_chrome_styles` (3 inputs) → updates visibility styles
8. `render_analysis_feedback` (4 inputs) → rebuilds feedback banner

That is **8+ callbacks firing in parallel/sequence** for a single dropdown change. Several of them independently call `_load_report_for_property` and `_build_property_view_for_property`, though caching (`@lru_cache` keyed on `(property_id, inputs_mtime_ns)`) mitigates redundant computation after the first call.

### Expensive Individual Callbacks

| Callback | Line | Why It's Expensive |
|----------|------|--------------------|
| `render_main_tab` | 3529 | Rebuilds entire tab; 7 Inputs fire it constantly |
| `render_active_property_status` | 2651 | 3 Inputs; calls `_load_report_for_property` + `_build_property_view_for_property`; generates complex header DOM |
| `render_compare` | 4200 | Loads up to 4 reports and builds views for each |
| `render_analysis_feedback` | 2875 | 4 Inputs; calls `_focused_report` + `_core_missing_fields` |
| `run_manual_analysis` | 4871 | 42 State parameters; runs full analysis pipeline synchronously |
| `highlight_missing_manual_fields` | 4583 | Calls `load_report_for_preset` which may run full analysis |

### Recommendation

Split `render_main_tab` into per-tab callbacks that only fire when their specific tab is active:

```python
@app.callback(
    Output("tear-sheet-content", "children"),
    Input("main-tabs", "value"),
    Input("property-selector-dropdown", "value"),
    Input("town-pulse-filter", "data"),
    State("loaded-preset-ids", "data"),
)
def render_tear_sheet_tab(tab, focus_id, pulse_filter, loaded_ids):
    if tab != "tear_sheet":
        raise PreventUpdate
    ...
```

Use `ctx.triggered_id` in multi-input callbacks to avoid unnecessary work when only one input changed.

---

## 3. Data Loading

### Report Loading: Lazy but Uncapped

Reports are loaded lazily via `load_report_for_preset` (data.py:183) and cached in `_REPORT_CACHE` (a plain dict, no size limit). Each report load calls `preset.loader()` which runs the **full analysis pipeline** (`run_report` or `run_report_from_listing_text`). This can take 1-5 seconds per property depending on comp lookups, geocoding, and module execution.

The `_load_report_cached` function (app.py:1649) adds an `@lru_cache(maxsize=128)` keyed on `(property_id, inputs_mtime_ns)`. This means the LRU cache and the `_REPORT_CACHE` dict are **dual caching** the same data, potentially doubling memory use.

### Markets Tab: Loads ALL Saved Properties

`_build_market_view_block` (line 3875) calls:
1. `build_market_view_model` → `_cached_market_analyses` → `analyze_markets()` which reads JSON files from disk (active listings, sales comps, rent context, local signals) and computes market scores for all towns. Cached with `@lru_cache(maxsize=4)` and a 12-hour disk pickle cache.
2. `_build_market_property_candidates` → `_opportunity_records` which iterates **every discoverable property** and calls `_build_opportunity_record_cached` for each one. First-time cost: runs full analysis for every saved property that hasn't been loaded yet.
3. `_build_value_finder_market_section` → `list_saved_properties()` + `load_reports(saved_ids)` — loads ALL saved property reports again.

**This means the first visit to the Markets tab can trigger N full analysis runs** where N is the number of saved properties.

### `build_property_analysis_view` Calls Market Analysis

At line 1804 in `view_models.py`:
```python
market_view_model = build_market_view_model(property_input.town if property_input else None)
```

Every property view build triggers a market analysis. If the market cache is cold, this runs `analyze_markets()` which reads multiple JSON files and computes metrics for all towns. This means selecting a new property when the cache is cold triggers both property analysis AND market analysis.

### `list_saved_properties` Scans Disk Repeatedly

`list_saved_properties()` (data.py:126) does a full directory scan + JSON parse for every summary file every time it's called. It's called from:
- `refresh_property_controls` (on every catalog version change)
- `_property_options_cached` (building dropdown options)
- `_build_value_finder_market_section` (markets tab)
- `_saved_property_rows` (settings tab)

The `_saved_properties_snapshot` function (app.py:329) adds an `@lru_cache` keyed on directory mtime, but `list_saved_properties` itself has no cache, so any call that doesn't go through the snapshot wrapper re-scans.

### Recommendation

1. Add `@lru_cache` directly to `list_saved_properties` keyed on directory mtime.
2. Remove the `build_market_view_model` call from `build_property_analysis_view` — the property view should not need to run market analysis. Pass the market data in from the caller when needed.
3. Cap `_REPORT_CACHE` size or unify with the LRU cache.

---

## 4. Layout Weight

### Initial DOM

The initial layout tree (`_build_layout`, line 2549) creates:

- **18 `dcc.Store` components** — These are lightweight (just JSON in memory).
- **1 `dcc.Download`** component.
- **Shell structure:** sidebar + topbar + context bar + feedback banner + tab bar + main content area + 2 hidden drawers + tour overlay.
- **Two full drawer forms pre-rendered in the DOM:**
  - `_add_property_drawer()` — The manual property entry form with ~45 input fields, comp entry fields, validation hints.
  - `_market_property_preview_drawer()` — A preview panel with header, content area, and action buttons.

These drawers are always in the DOM even when invisible. The add-property drawer is the heaviest, containing dozens of `dcc.Input`, `dcc.Dropdown`, and label components.

### Tear Sheet Page

`render_tear_sheet_body` (components.py:5938) builds 6 collapsible "question sections" each containing:
- Inline metric strips
- Plotly charts (waterfall, dot plot, bar charts)
- Data tables
- Evidence blocks
- Status chips

Each section is a `_question_section` call that creates ~20-50 Dash components. The full tear sheet body is **300-500+ components** sent as a single JSON payload to the browser.

### Charts Are Always Built

Even in collapsible sections that start closed, the charts are pre-rendered. For example:
```python
chart=html.Div([
    comp_positioning_dot_plot(view, report),
    html.Div(forward_waterfall_chart(report), style={"marginTop": "8px"}),
])
```

These Plotly figure objects are serialized into the layout JSON regardless of whether the section is expanded. The `default_open` flag only controls CSS visibility, not whether the chart is built.

### Recommendation

1. Use Dash's `dcc.Loading` or pattern-matching callbacks to defer chart rendering until a section is expanded.
2. Move the add-property drawer to a callback that builds it only when opened, rather than pre-rendering it in the initial layout.

---

## 5. Client-Side Burden

### No `clientside_callback` Usage

The app uses **zero** `clientside_callback` calls. All callbacks go to the Python server, including purely cosmetic operations like:
- `toggle_forward_view` (line 3487) — toggles `display: none/block` between chart and table
- `toggle_economics_view` (line 3499) — same pattern
- `set_drawer_visibility` (line 3333) — toggles drawer CSS
- `set_market_preview_visibility` (line 3157) — toggles preview panel CSS
- `tour_render` (line 5206) — always returns `None`

These are pure style-toggle operations that could be `clientside_callback` calls, eliminating round-trips to the server.

### `dcc.Store` Usage

18 stores is moderate. The stores hold small data (lists of IDs, booleans, filter strings). No inline large datasets observed. The `user-preferences` store uses `storage_type="local"` (browser localStorage), which is appropriate.

### Google Fonts Load

The `index_string` (line 90) loads two Google Font families (Inter + Source Serif 4) with `display=swap`. This adds a network request before first render. The `preconnect` hints are correctly placed.

### CSS

`workspace.css` (341 lines) is lightweight and focused on dropdown theming and print styles. Not a performance concern.

### Recommendation

Convert the following to `clientside_callback`:
```python
# Example: toggle_forward_view
app.clientside_callback(
    """
    function(mode) {
        return [
            mode === 'table' ? {display: 'none'} : {display: 'block'},
            mode === 'table' ? {display: 'block'} : {display: 'none'}
        ];
    }
    """,
    Output("forward-chart-pane", "style"),
    Output("forward-table-pane", "style"),
    Input("forward-view-toggle", "value"),
)
```

At least 5 callbacks are candidates for client-side conversion.

---

## 6. Caching

### Current Caching

| Cache | Location | Type | Size |
|-------|----------|------|------|
| `_REPORT_CACHE` | data.py:96 | Plain dict | Unbounded |
| `_PRESET_CACHE` | data.py:99 | Tuple `(version, list)` | 1 entry |
| `_load_report_cached` | app.py:1649 | `@lru_cache(128)` | 128 entries |
| `_build_property_view_cached` | app.py:1659 | `@lru_cache(128)` | 128 entries |
| `_build_opportunity_record_cached` | app.py:1592 | `@lru_cache(128)` | 128 entries |
| `_saved_properties_snapshot` | app.py:328 | `@lru_cache(16)` | 16 entries |
| `_property_options_cached` | app.py:345 | `@lru_cache(16)` | 16 entries |
| `_load_active_listings_dataset` | app.py:361 | `@lru_cache(8)` | 8 entries |
| `_search_index` | app.py:537 | `@lru_cache(16)` | 16 entries |
| `_available_town_cards_cached` | app.py:605 | `@lru_cache(16)` | 16 entries |
| `_cached_market_analyses` | view_models.py:1620 | `@lru_cache(4)` + pickle on disk | 4 in-memory + disk |
| `geocode_address` | geocoder.py:27 | `@lru_cache(500)` | 500 entries |

### Caching Gaps

1. **`list_saved_properties()`** — No direct cache. Re-scans disk on every call unless routed through `_saved_properties_snapshot`.

2. **`list_comp_database_rows()`** — No cache. Reads and parses `sales_comps.json` on every call. Called from `refresh_property_controls` which fires on catalog version changes and property list changes.

3. **`build_property_analysis_view()`** — No cache at the view_models level. The `_build_property_view_cached` wrapper in app.py caches it, but if any code calls `build_property_analysis_view` directly (components.py, data.py), it recomputes.

4. **`build_market_view_model()`** — Internally uses `_cached_market_analyses` but builds the MarketsPageViewModel (card list, selected market) fresh each time.

5. **`_opportunity_records()`** — Not cached. Iterates all discoverable property IDs and calls cached sub-functions, but the iteration, sorting, and dict-copying happen every time.

6. **`render_tear_sheet_body()`** — No output cache. The full Dash component tree is rebuilt on every call even if the property hasn't changed.

### Dual Cache Problem

`_REPORT_CACHE` (data.py) and `_load_report_cached` (app.py) both cache the same AnalysisReport objects. When `_load_report_cached` calls `load_report_for_preset`, the report gets stored in both caches. The `_REPORT_CACHE` dict is unbounded and never evicted, so it grows indefinitely during a session.

### Recommendation

1. Remove `_REPORT_CACHE` and rely solely on `_load_report_cached` (or vice versa).
2. Add mtime-keyed `@lru_cache` to `list_comp_database_rows`.
3. Cache `_opportunity_records` output keyed on `(saved_properties_mtime_ns, active_listings_mtime_ns)`.

---

## 7. Unnecessary Module Imports

### `data.py` Imports

```python
from briarwood.runner import run_report, run_report_from_listing_text, write_report_html
from briarwood.reports.pdf_renderer import write_tear_sheet_pdf
```

`briarwood.runner` imports 20+ modules:
- `ComparableSalesModule`, `CostValuationModule`, `CurrentValueModule`, `HybridValueModule`
- `IncomeSupportModule`, `LocationIntelligenceModule`, `LiquiditySignalModule`
- `LocalIntelligenceModule`, `MarketMomentumSignalModule`, `MarketValueHistoryModule`
- `RenovationScenarioModule`, `TeardownScenarioModule`, `PropertySnapshotModule`
- `PropertyDataQualityModule`, `RentalEaseModule`, `RiskConstraintsModule`
- `ScarcitySupportModule`, `TownCountyOutlookModule`, `ValueDriversModule`
- `BullBaseBearModule`
- Plus `briarwood.reports.renderer`, `briarwood.reports.tear_sheet`, `briarwood.listing_intake.service`

`briarwood.reports.pdf_renderer` imports weasyprint dependencies.

**None of these are needed until the user actually runs an analysis or exports a PDF.** Deferring them would significantly reduce startup time.

### `view_models.py` Imports

```python
from briarwood.modules.market_analyzer import MarketAnalysisOutput, analyze_markets
from briarwood.modules.value_finder import ValueFinderOutput, analyze_value_finder
```

These are needed for the Markets tab but not for basic property view rendering. However, since they're only function definitions (not execution), the import cost is the module parse time — moderate.

---

## 8. Architecture-Level Issues

### Monolithic File Structure

- `app.py` (5,320 lines) contains layout, 48 callbacks, and dozens of helper functions in one file.
- `components.py` (7,992 lines) contains all UI component builders.
- Neither uses Dash's `pages` pattern or multi-page app architecture.

This means every import of the app module parses and compiles 5,320+ lines of Python. More importantly, it makes targeted optimization difficult because callback dependencies are interleaved.

### Synchronous Analysis in Callbacks

`run_manual_analysis` (line 4871) runs the full analysis pipeline synchronously in a callback with 42 State parameters. During this time, the Dash server is blocked from serving other requests (assuming single-worker mode). Dash's `background_callback` or `long_callback` features could move this to a background worker.

### `build_property_analysis_view` Does Too Much

This function (view_models.py:1774) is a 160+ line monolith that:
- Extracts data from 10+ module results
- Builds town pulse view model
- Builds conclusion and thesis sections
- Computes confidence breakdowns
- Runs market analysis (!)
- Builds evidence summary
- Builds hybrid value view
- Builds value finder view
- Computes town context metrics
- Assembles a 50+ field PropertyAnalysisView dataclass

It should be split so that expensive sub-computations (market analysis, value finder) are only done when the caller needs them.

---

## 9. Priority Action Plan

### Quick Wins (< 1 day each)

1. **Convert 5 style-toggle callbacks to `clientside_callback`** — Eliminates server round-trips for `toggle_forward_view`, `toggle_economics_view`, `set_drawer_visibility`, `set_market_preview_visibility`, `tour_render`.

2. **Defer `briarwood.runner` and `pdf_renderer` imports in `data.py`** — Move to inside the functions that use them. Reduces startup import chain significantly.

3. **Add `ctx.triggered_id` guards to `render_main_tab`** — If only `town-pulse-filter` changed but the active tab isn't `tear_sheet`, skip the rebuild.

4. **Cache `list_comp_database_rows`** — Add `@lru_cache` keyed on file mtime.

### Medium Effort (1-3 days)

5. **Split `render_main_tab` into per-tab callbacks** — Each tab gets its own callback with only the inputs it needs. The tab-switch callback just shows/hides containers.

6. **Remove `build_market_view_model` call from `build_property_analysis_view`** — Pass market data from the caller only when needed (market preview, value finder).

7. **Unify the dual report cache** — Remove `_REPORT_CACHE` dict from `data.py`; rely on `_load_report_cached` with LRU eviction.

8. **Defer chart building in collapsed sections** — Use pattern-matching callbacks triggered by section expand/collapse.

### Larger Refactors (1+ weeks)

9. **Split `app.py` into a multi-file callback structure** — Group callbacks by feature (property management, market view, compare, form handling, export).

10. **Use `dash.long_callback` for `run_manual_analysis`** — Run analysis in a background process with a progress indicator.

11. **Lazy-load the add-property drawer** — Build it in a callback only when opened instead of placing 45+ input fields in the initial DOM.

12. **Evaluate Dash pages plugin** — Consider `dash.page_registry` for true multi-page architecture with per-page code splitting.

---

## 10. Estimated Impact

| Change | Startup Time | Tab Switch | Property Select |
|--------|-------------|------------|-----------------|
| Defer runner/pdf imports | -40-60% | — | — |
| Split render_main_tab | — | -50-70% | -30-40% |
| Clientside style callbacks | — | -5-10% | — |
| Remove market analysis from property view | — | — | -20-40% (cold cache) |
| Cache opportunity records | — | -40-60% (Markets tab) | — |

The combination of deferring imports (startup) and splitting `render_main_tab` (runtime) should make the app feel noticeably faster within 2-3 days of work.

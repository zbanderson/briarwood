# Migration Plan: Dashboard → Search-First Consumer Product

**Date:** 2026-04-11
**Based on:** Phases 1-4 analysis (inventory, technical debt, performance, UI gap analysis)

---

## Tier 1: Safe Deletes (Do First)

Zero-risk removals. No behavior changes. Estimated savings: ~1,900 lines.

### 1.1 Dead Functions in `components.py`

| Function | Lines | Location |
|----------|-------|----------|
| `render_lens_selector()` | ~70 | components.py:345 |
| `render_score_header()` | ~110 | components.py:416 |
| `_render_category_mini_bars()` | ~50 | components.py:478 |
| `_category_drill_in_summary()` | ~10 | components.py:531 |
| `_render_category_components()` | ~45 | components.py:542 |
| `render_sub_factors()` | ~20 | components.py:587 |
| `render_executive_summary()` | ~85 | components.py:609 |
| `render_category_section()` | ~85 | components.py:696 |
| `render_property_verdict()` | ~160 | components.py:2054 |
| `render_perspective_block()` | ~85 | components.py:2215 |
| `render_what_if_slider()` | ~100 | components.py:6674 |
| `render_single_section()` | ~15 | components.py:7509 |
| `confidence_level_badge()` | ~30 | components.py (only called by dead `render_score_header`) |

**Also remove:**
- Unused aliases: `RESPONSIVE_GRID_2`, `RESPONSIVE_GRID_3`, `RESPONSIVE_GRID_4` (components.py:99-101)
- Unused import: `HEADING_M_STYLE` (components.py:24)
- `_TOUR_STEPS` data block (~110 lines, components.py:6480)
- `render_tour_overlay()` function (components.py)
- `render_tour_trigger_button()` function (components.py)

**Total: ~900 lines from components.py**

### 1.2 Dead Tour System in `app.py`

- Remove `render_tour_overlay` import
- Remove tour trigger button from `_build_layout()` (line 2615)
- Delete `tour_render()` callback (line 5210-5211)
- Delete `tour_auto_show()` callback (line 5222-5223)
- Remove tour-related `dcc.Store` components

**Total: ~40 lines from app.py**

### 1.3 Dead Files

| File | Lines | Reason |
|------|-------|--------|
| `briarwood/entry_prep.py` | 68 | Never imported by any production code |
| `briarwood/local_intelligence/ui.py` | 16 | Never imported; replaced by view_models.py |
| `briarwood/dashboard_contract.py` | 154 | Only imported by test_scorecard.py, not by any production code |
| `briarwood/agents/current_value/inspect_data.py` | 116 | One-off data inspection script, never imported |

**Total: ~354 lines across 4 files**

### 1.4 Dead Modules

| Module | Lines | Test File to Also Remove |
|--------|-------|--------------------------|
| `briarwood/modules/market_snapshot.py` | 190 | `tests/test_market_snapshot.py` (63 lines) |
| `briarwood/modules/relative_opportunity.py` | 271 | `tests/test_relative_opportunity.py` (121 lines) |

**Note:** Verify `relative_opportunity.py` is truly unused — it may be referenced by compare.py. If so, keep it.

**Total: ~645 lines (with tests)**

### 1.5 Dead Function in `runner.py`

- `format_tear_sheet_summary()` at line 238 (~50 lines) — never called anywhere.

### 1.6 Orphaned Data

- Delete `data/local_intelligence/documents/` directory (untracked, unreferenced)

---

## Tier 2: Quick Wins (High Impact, Low Effort)

### 2.1 Defer Heavy Imports in `data.py` (Impact: 40-60% faster startup)

**Current** (data.py:17-18):
```python
from briarwood.runner import run_report, run_report_from_listing_text, write_report_html
from briarwood.reports.pdf_renderer import write_tear_sheet_pdf
```

**Change to:** Move these imports inside the functions that use them:
- `_load_json_report()` → inline `from briarwood.runner import run_report`
- `_load_listing_report()` → inline `from briarwood.runner import run_report_from_listing_text`
- `export_preset_tear_sheet()` → inline `from briarwood.runner import write_report_html`
- `export_preset_tear_sheet_pdf()` → inline `from briarwood.reports.pdf_renderer import write_tear_sheet_pdf`

This avoids importing all 20+ analysis modules and WeasyPrint at startup.

### 2.2 Convert 5 Style-Toggle Callbacks to `clientside_callback` (Impact: eliminate server round-trips)

| Callback | Line | What it does |
|----------|------|-------------|
| `toggle_forward_view` | app.py:3487 | Toggles chart/table display |
| `toggle_economics_view` | app.py:3499 | Toggles chart/table display |
| `set_drawer_visibility` | app.py:3333 | Toggles drawer CSS |
| `set_market_preview_visibility` | app.py:3157 | Toggles preview panel CSS |
| `tour_render` | app.py:5206 | Always returns None (dead) |

### 2.3 Add `ctx.triggered_id` Guards to `render_main_tab` (Impact: 50-70% fewer rebuilds)

The callback at app.py:3529 has 7 Inputs but rebuilds everything regardless of which one fired. Add early-exit guards:

```python
triggered = ctx.triggered_id
if triggered == "town-pulse-filter" and tab != "tear_sheet":
    raise PreventUpdate
if triggered == "market-sort-mode" and tab != "opportunities":
    raise PreventUpdate
# etc.
```

### 2.4 Deduplicate Utility Functions

Create `briarwood/dash_app/utils.py` with shared implementations of:
- `_fmt_currency()` (currently in app.py:399 AND view_models.py:52 with inconsistent null strings)
- `_clean_text()` (app.py:405 AND view_models.py:58)
- `_property_identity()` (app.py:436 AND view_models.py:62)
- `_maps_links()` (app.py:815 AND view_models.py:80)
- `_parse_currency_text()` (components.py:257 AND view_models.py:128)

### 2.5 Remove `build_market_view_model` from `build_property_analysis_view` (Impact: 20-40% faster property select on cold cache)

At view_models.py:1804, every property view build also runs market analysis. Remove this call and pass market data from the caller only when the Markets tab or value finder is active.

### 2.6 Unify Dual Report Cache

Remove `_REPORT_CACHE` (unbounded dict in data.py:96) and rely solely on `_load_report_cached` (`@lru_cache(128)` in app.py:1649). The dual cache wastes memory and makes invalidation unreliable.

### 2.7 Consolidate Inline Imports of `estimate_comp_renovation_premium`

Move the 7 repeated inline imports in components.py (lines 1191, 4172, 4591, 4731, 4754, 5729, 5758) to a single top-level import.

---

## Tier 3: UI Restructuring

### 3.1 Architecture: Replace Tab Routing with Screen State Machine

**Current:** `MAIN_TABS` at app.py:114-121 drives all routing through a single `render_main_tab` callback.

**Target:** A state machine with 6 screens:
```
LANDING → TOWN_RESULTS → PROPERTY_L1 → PROPERTY_L2 → PROPERTY_L3
                                                    ↗
MARKETS ──────────────────────────────────────────────
```

**Implementation:**
1. Replace `main-tabs` with a `dcc.Store(id="current-screen")` holding `{screen: "landing"|"town_results"|"property_l1"|"property_l2"|"property_l3"|"markets", property_id: str|null, town: str|null}`
2. Replace `render_main_tab` with `render_current_screen` that dispatches to per-screen renderers
3. Each screen renderer is its own function (no more 300-line if/elif chain)

### 3.2 File Structure: Map Current Files to Target Screens

| Target Screen | Primary Source | Renderer Function | Data Function |
|---------------|---------------|-------------------|---------------|
| Landing | app.py → `screens/landing.py` | `_property_search_landing()` (app.py:1332) | N/A |
| Town Results | app.py → `screens/town_results.py` | `_build_town_results_view()` (app.py:3719) | `_build_market_view_block()` (app.py:3875) partially |
| Property L1 | components_quick_decision.py → `screens/property_l1.py` | `render_quick_decision()` (components_quick_decision.py:499) — **promote this, kill System A** | `build_quick_decision_view()` (quick_decision.py) |
| Property L2 | scenarios.py + components.py → `screens/property_l2.py` | Extract from `render_tear_sheet_body()` sections: `tear-forward`, `tear-economics`, `tear-optionality` | view_models.py scenario data |
| Property L3 | components.py + data_quality.py → `screens/property_l3.py` | `render_tear_sheet_body()` remaining sections + data quality | `build_property_analysis_view()` |
| Markets | app.py → `screens/markets.py` | Simplified `_build_market_view_block()` | `build_market_view_model()` |

### 3.3 Components to Dismantle

| Component | File | Lines | Action |
|-----------|------|-------|--------|
| Persistent sidebar | app.py:1070-1164 | ~95 | DELETE entirely |
| Topbar with property selector | app.py:1481-1524 | ~44 | REPLACE with contextual header per screen |
| Context bar | app.py:1266-1294 | ~29 | DELETE (info belongs in page content) |
| Six-tab navigation | app.py:114-121, 2007-2012 | ~10 | REPLACE with screen state machine |
| `_main_tab_bar()` | app.py:1998-2046 | ~49 | DELETE |
| Opportunity discovery board | app.py:1805-1987 | ~183 | SIMPLIFY to town cards on Markets screen |
| Portfolio dashboard | components.py:6868-6963 | ~96 | DELETE (institutional pattern) |
| Compare controls | app.py:2488-2546 | ~59 | DEFER to Layer 3 as optional |
| Add-property drawer (45-field form) | app.py:2054-2159 | ~106 | REPLACE with search-driven intake |
| `render_property_decision_summary()` (System A) | components.py:2739-2859 | ~121 | DELETE (replaced by System B's `render_quick_decision()`) |

### 3.4 Callbacks That Survive vs Die

**SURVIVE (keep or adapt):**
- `_resolve_startup_search()` → becomes the primary intake handler
- `render_current_screen()` → replacement for `render_main_tab`
- `run_manual_analysis()` → simplified (use dcc.Store for form state instead of 46 States)
- `refresh_property_controls()` → adapted for search results
- Export callbacks (tear sheet HTML/PDF)

**DIE (remove):**
- `render_shell_sidebar()` — no sidebar
- `render_shell_context_bar()` — no context bar
- `render_shell_chrome_styles()` — no chrome to toggle
- `tour_render()`, `tour_auto_show()` — dead tour
- `toggle_forward_view()`, `toggle_economics_view()` — convert to clientside
- All `allow_duplicate=True` callbacks writing to `loaded-preset-ids` (7 callbacks) — consolidate to 1
- All `allow_duplicate=True` callbacks writing to `main-tabs` (7 callbacks) — replaced by screen state

**REWRITE:**
- `render_main_tab` (app.py:3529) → split into per-screen renderers
- `populate_manual_form` (46 Outputs) → single dcc.Store pattern
- `render_active_property_status` → per-screen contextual header

### 3.5 Proposed New File Structure

```
briarwood/dash_app/
├── __init__.py
├── app.py              # Slim: Dash init, dcc.Store declarations, screen router callback
├── screens/
│   ├── landing.py      # Search bar, recent properties, town cards
│   ├── town_results.py # Town heading, map, property cards
│   ├── property_l1.py  # Quick decision (merged from components_quick_decision.py)
│   ├── property_l2.py  # Value exploration (extracted from tear sheet + scenarios)
│   ├── property_l3.py  # Full analysis (tear sheet body + data quality + compare)
│   └── markets.py      # Town market cards, simplified discovery
├── components/
│   ├── charts.py       # All Plotly chart builders
│   ├── cards.py        # Property cards, metric cards, town cards
│   ├── heroes.py       # Recommendation hero, confidence badges
│   ├── tables.py       # Data tables, comp tables
│   └── common.py       # Shared UI atoms (badges, chips, strips)
├── utils.py            # Shared formatting functions
├── data.py             # Data loading (unchanged, with lazy imports)
├── view_models.py      # View model builders (split market from property)
├── quick_decision.py   # QuickDecisionViewModel builder
├── theme.py            # Design tokens (unchanged)
└── assets/
    └── workspace.css
```

---

## Tier 4: New Development Needed

### 4.1 Map Component (Landing + Town Results)

**What:** Interactive map with property pins using `dash-leaflet` or Plotly `go.Scattermapbox`.

**Data sources already available:**
- Geocoded property lat/lon from saved properties (via `briarwood/geocoder.py`)
- Active listing lat/lon from comp database
- Town landmark points from `data/town_county/monmouth_landmark_points.json`

**Implementation:**
- Add `dash-leaflet` to requirements.txt
- Create a `components/map.py` with `render_property_map(properties, center, zoom)`
- Wire into Town Results and Landing screens

### 4.2 Progressive Disclosure Gate

**What:** A state-driven transition between Layer 1 → Layer 2 → Layer 3.

**Implementation:**
- Add `dcc.Store(id="property-depth")` with values `"l1"`, `"l2"`, `"l3"`
- Layer 1 shows the quick decision view with a "Dig Deeper" button
- Clicking "Dig Deeper" sets depth to `"l2"` and renders scenarios/forward outlook
- Layer 2 shows a "Full Analysis" button
- Full Analysis sets depth to `"l3"` and renders comps, risk, diagnostics

**The button already exists:** `render_full_analysis_button()` at components_quick_decision.py:484 — it just needs to be wired to the depth store instead of switching tabs.

### 4.3 Simplified Property Cards

**What:** Clean property cards for Town Results (address, price, beds/baths, sqft, key metric).

**Current:** `_opportunity_button()` (app.py:1735-1802) renders analytics-heavy cards with scores, recommendations, signals, and strategy tags.

**Target:** Simple card with:
- Address (large)
- Price (large)
- Beds / Baths / Sqft (small)
- One confidence/opportunity signal badge
- Click → navigate to Property L1

### 4.4 Monthly Reality Hero Element

**What:** A primary, large-format display of monthly ownership cost on Layer 1.

**Data available:** `scenario_snapshots` in `QuickDecisionViewModel` already has `monthly_cost`, `rent`, and `net` for bull/base/bear cases.

**Implementation:** Add a `render_monthly_reality_hero(view_model)` component that shows the base-case monthly cost, expected rent, and net position as a visually prominent card between the recommendation hero and key reasons.

### 4.5 URL-First Intake Flow

**What:** Streamlined "paste a Zillow URL → get a 10-second answer" experience.

**Current:** URL parsing exists (`ZillowUrlParser`) but the flow goes through `_resolve_startup_search()` which routes to manual property creation, not directly to Layer 1.

**Target flow:**
1. User pastes URL on Landing
2. System parses listing → runs analysis (show loading spinner via `dcc.Loading`)
3. Navigate directly to Property L1 with the result

**Existing code to reuse:** `run_report_from_listing_text()` in runner.py, `ZillowUrlParser` in listing_intake.

### 4.6 Search Routing

**What:** Replace the global property selector dropdown with search-driven navigation.

**Implementation:**
1. Landing search bar → if address matches saved property, go to Property L1
2. If address matches a town, go to Town Results
3. If URL, run intake flow → Property L1
4. If no match, show "Analyze New Property" option → simplified intake form

The search resolution logic already exists in `_resolve_startup_search()` (app.py:683-722). It needs to be adapted to the screen state machine instead of the tab system.

---

## Implementation Order

### Phase A: Clean (1-2 days)
1. All Tier 1 safe deletes (~1,900 lines removed)
2. Tier 2.1 (defer imports)
3. Tier 2.4 (deduplicate utils)
4. Tier 2.7 (consolidate inline imports)
5. Run full test suite to verify nothing breaks

### Phase B: Optimize (1-2 days)
1. Tier 2.2 (clientside callbacks)
2. Tier 2.3 (ctx.triggered_id guards)
3. Tier 2.5 (decouple market from property view)
4. Tier 2.6 (unify cache)

### Phase C: Restructure UI (3-5 days)
1. Tier 3.1 (screen state machine replacing tabs)
2. Tier 3.2 (split app.py into per-screen files)
3. Tier 3.3 (dismantle sidebar, topbar, context bar)
4. Tier 3.4 (callback consolidation)
5. Tier 4.2 (progressive disclosure gate)

### Phase D: New Features (3-5 days)
1. Tier 4.3 (simplified property cards)
2. Tier 4.4 (monthly reality hero)
3. Tier 4.1 (map component)
4. Tier 4.5 (URL-first intake)
5. Tier 4.6 (search routing refinement)

### Phase E: Polish (1-2 days)
1. Remove dead CSS classes
2. Responsive design pass
3. Loading states and error boundaries
4. Final test suite run

**Total estimated effort: 9-16 days of focused work.**

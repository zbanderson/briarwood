# UI Gap Analysis: Current Implementation vs Target UX Model

**Date:** 2026-04-11
**Scope:** Mapping current Dash app implementation to the "Search -> Answer -> Dig deeper" target UX
**Files analyzed:** app.py (5,320 lines), components.py (7,992 lines), view_models.py (2,893 lines), quick_decision.py (532 lines), components_quick_decision.py (510 lines), scenarios.py (775 lines), data_quality.py (677 lines), compare.py (293 lines), theme.py (428 lines), workspace.css

---

## 1. Component-to-Screen Mapping

### Landing Screen

**Target:** Search bar + "Analyze Property" / "Explore Markets" / "Try Example" buttons. Recent properties. Town cards. NO sidebar, NO tabs, NO charts, NO pre-loaded property.

**Current implementation: `_property_search_landing()` at app.py:1332-1478**

This is the closest match in the codebase. It renders when no property is focused (`_focused_report() is None` and no `selected_market_town`). It includes:
- Search bar (address input at line 1407, URL input at line 1421)
- Three action buttons: "Analyze Property", "Explore Markets", "Try Example" (lines 1437-1439)
- Recent Properties section with clickable cards (lines 1447-1456)
- Available Towns section with clickable town buttons (lines 1457-1468)

**Gaps vs target:**
- The landing hides the sidebar, topbar, and context bar correctly (callback `render_shell_chrome_styles` at app.py:2842-2862 sets `display: none` in landing mode).
- The landing page is correctly chart-free and tab-free.
- **The landing is nested inside the tear_sheet tab's render path** (app.py:3566-3589). It is not a true independent screen -- it is a fallback state within the `tear_sheet` tab. This means the tab system still exists underneath; the landing is a conditional branch, not a first-class route.
- No map component exists on the landing page.
- The "Available Towns" section shows town buttons but with minimal data (signal label, count). No geographic visualization.

**Verdict: ~75% implemented. Functional but architecturally coupled to the tab system.**

---

### Town Results Screen

**Target:** Town name, map with pins, property cards. User must choose -- no auto-open.

**Current implementation: `_build_town_results_view()` at app.py:3719-3860**

Renders when `selected_market_town` is set but no property is focused. Shows:
- Town name as H1 heading with "Town Results" kicker (line 3826-3827)
- Saved property cards using `_opportunity_button()` (line 3759)
- Active listing cards from the comp database (lines 3760-3815)
- Back/Markets navigation buttons
- Google Maps and Apple Maps links per listing

**Gaps vs target:**
- **No map component.** No pins, no geographic visualization. This is the biggest gap -- the target calls for "map with pins" as a primary element.
- Cards are functional but use the `_opportunity_button()` pattern, which is analytics-heavy (shows score, recommendation badge, signal label, signal text, strategy tags). Target wants simpler property cards.
- No auto-open behavior, which is correct per target principles.
- Town-level summary data is minimal (signal, trend, count of analyzed/listings).

**Verdict: ~50% implemented. Text-based property listing exists; no map, no simplified card design.**

---

### Property Layer 1 (Simple Decision)

**Target:** Worth pursuing? Why? What's the catch? Readable in 10 seconds. Shows confidence, value range, monthly reality, best fit.

**Current implementation: Two overlapping systems exist.**

#### System A: `render_property_decision_summary()` at components.py:2739-2859
This is the "Layer-1 decision summary" that renders at the top of Property Analysis. It:
- Calls `build_quick_decision_view()` to get a `QuickDecisionViewModel`
- Renders `render_recommendation_hero()` (the BUY/WATCH/PASS hero from components_quick_decision.py)
- Shows "Best Fit" and "Trust Read" side-by-side cards
- Shows "Why It Could Work" / "What To Watch" / "Works Best For" in a 3-column grid
- Shows "Fast Reality Check" with value metrics strip and jump links

#### System B: `quick_decision.py` + `components_quick_decision.py` (full standalone system)
This is a separate, more complete Layer 1 that was built as a standalone page:
- `build_quick_decision_view()` at quick_decision.py:503-532 produces a `QuickDecisionViewModel` with recommendation, confidence, score, key_reasons, best_use_cases, scenario_snapshots, risks, and value_finder
- `render_quick_decision()` at components_quick_decision.py:499-510 assembles the full page: hero + key reasons + use cases & risks + scenario snapshots + value finder + "View Full Analysis" button
- Jargon-to-plain-English rewrites at quick_decision.py:29-46

**What Layer 1 has vs what it needs:**

| Target requirement | System A (decision summary) | System B (quick_decision) |
|---|---|---|
| Worth pursuing? | Hero with BUY/WATCH/PASS | Hero with BUY/WATCH/PASS |
| Why? | 3 key reasons (text only) | 3-5 key reasons with sentiment icons |
| What's the catch? | 3 risks (text only) | 3 risks as styled bullets |
| Confidence | Trust Read card with High/Med/Low | Confidence dot in hero |
| Value range | Ask/Fair Value/Base/Monthly in metric strip | Value Finder section with opportunity badge |
| Monthly reality | Monthly cash flow in metric strip | Scenario snapshots with monthly cost/rent/net |
| Best fit | Best Fit card with lens label | Best Use Cases with strength badges |
| 10-second readable | Partially -- still dense with jump links and 3-column grid | Better -- more visual hierarchy, cleaner flow |

**Gaps:**
- **System A and System B are not unified.** System A is what actually renders on the Property Analysis page. System B exists as standalone components that are partially imported (the hero is shared, but the rest of System B's page layout `render_quick_decision()` is never called in the main app flow).
- System A still includes jump links to deeper sections ("See Value Scenarios", "See Price Support", "Show More Detail") which violates progressive disclosure -- it reveals the existence of complexity before the user has opted in.
- Neither system shows a clean "monthly reality" number as a primary, hero-level element. Monthly cash flow is buried in a metric strip sublabel.
- The "Trust Read" card in System A shows assumption quality detail, which is an analyst-level concern.
- **No "Dig deeper" gate.** Layer 1 scrolls directly into Layer 2/3 content. There is no opt-in step between the decision summary and the full tear sheet sections below.

**Verdict: ~60% implemented across two competing systems. Need to merge, simplify, and add a progressive disclosure gate.**

---

### Property Layer 2 (Value Exploration)

**Target:** Scenarios (rent, renovate), 12-month thinking, upside/downside. User opted in.

**Current implementation: Partially in tear sheet, partially in Scenarios tab.**

#### In the tear sheet (components.py):
- "What Does the Forward Look Like?" section (`_question_section` with `tear-forward` ID, components.py:6049-6085): fan chart, bull/base/bear, upside/downside percentages, stress case
- "What Does It Cost to Own?" section (`tear-economics`, components.py:6008-6048): income waterfall, PTR, cash flow, DSCR, rental ease
- "Where's the Upside?" section (`tear-optionality`, components.py:6111-6137): condition, capex lane, optionality scoring, scarcity breakdown

#### In the Scenarios tab (scenarios.py):
- `render_scenarios_section()` at scenarios.py:31-37: Historic + Forward outlook chart, Renovation Scenario card, Teardown Scenario card
- Full standalone scenario analysis with metrics, charts, drivers table

**Gaps:**
- The tear sheet sections are collapsible `<details>` elements but **they are all on the same page as Layer 1**. There is no "user opted in" transition -- scrolling past the decision summary immediately exposes all 5 question sections.
- The Scenarios tab is a separate navigation destination requiring sidebar click, not a natural "dig deeper" action from a property page.
- "12-month thinking" is split between the tear sheet's forward section and the Scenarios tab's Historic + Forward Outlook. Redundant rendering paths.
- `render_what_if_metrics()` at components.py:6776-6860 (price/rate sensitivity slider) would belong here but is attached to the tear sheet, not gated behind a progressive layer.

**Verdict: ~55% of the content exists but it is not layered or gated. User sees everything at once.**

---

### Property Layer 3 (Full Analysis)

**Target:** Comps, risk system, assumptions, town intelligence, charts. Investor layer.

**Current implementation: Deeply built. This is where the app is strongest.**

- Full tear sheet body: `render_tear_sheet_body()` at components.py:5938-6175 renders 5 question sections, each with metric strips, charts, extra content blocks, evidence chips, and missing data notes.
- Comp positioning dot plot, forward waterfall chart, income carry waterfall, forward fan chart, risk breakdown bars -- all present in components.py
- Data quality / diagnostics: `render_data_quality_section()` at data_quality.py:31 (full comp database health, per-property comp matching, value driver attribution, input impact signals)
- Score header with category mini-bars and expandable sub-factors: `render_score_header()` at components.py:416-475
- Executive summary with top strengths/risks and key metrics: `render_executive_summary()` at components.py:609-693
- Lens selector (Risk/Investor/Owner/Developer perspective scores): `render_lens_selector()` at components.py:345-413
- Evidence section with per-section confidence indicators
- Town intelligence via `_town_context_block()`, `_location_context_chips()`

**Gaps:**
- This content is NOT behind a progressive disclosure gate. It renders inline below Layer 1.
- The Diagnostics tab (data_quality.py) is only reachable via the sidebar, which doesn't match the "investor layer" concept of progressively deeper exploration from a property.

**Verdict: ~85% implemented in terms of content. Architecture is flat, not layered.**

---

### Markets Tab

**Target:** Secondary. "I don't have a property yet." Leads into Town Results.

**Current implementation: `_build_market_view_block()` at app.py:3875-3983**

- Town cards with market signals, trends, key metrics (inventory, median price, DOM, price trend)
- Sort dropdown (Strongest/Weakest/Most Improving)
- Detail panel for selected town with market read (buyer/seller balance, direction, metrics)
- Town property candidates section showing analyzed properties per town
- Value Finder market section (`_build_value_finder_market_section()`)
- Opportunity discovery section with filter dropdowns (town, recommendation, strategy, price band)

**Gaps:**
- **The Markets tab (`opportunities`) is currently the first tab in MAIN_TABS (app.py:114-121) and feels like a primary destination**, not secondary. The sidebar navigation group labels it under "Markets" alongside "Property Analysis" as peers.
- No map component on the Markets tab either.
- The opportunity discovery section (`_opportunity_discovery_section()` at app.py:1805-1987) is analytics-heavy: "Buy Right Now" / "Neutral Watchlist" / "Avoid For Now" summary cards, 4 filter dropdowns, Top Picks grid, All Surfaced Opportunities list. This is an institutional discovery board, not a consumer "I don't have a property yet" experience.

**Verdict: ~65% implemented. Content is there but the experience is dashboard-heavy, not consumer-friendly.**

---

## 2. Components With NO Place in the Target Design

### Permanent Sidebar Navigation
**File:** app.py:1070-1164 (`_build_shell_sidebar()`, `_shell_nav_groups()`)

The app renders a persistent 264px navy sidebar with 3 groups (Markets, Tools, Admin) containing 6 navigation buttons. This is a workspace/dashboard pattern. The target design has NO sidebar -- navigation should be contextual and search-first.

The sidebar is hidden on the landing page (correct), but reappears the moment a property is loaded. Lines 2842-2862 in app.py manage the show/hide logic.

### Top Bar with Property Selector Dropdown
**File:** app.py:1481-1524 (`_topbar()`)

A persistent top bar showing "Active Workspace" with a property selector dropdown, "+Add Property" button, and export controls. This is institutional workspace chrome. The target replaces this with the search bar and contextual actions.

### Six-Tab Navigation System
**File:** app.py:114-121 (`MAIN_TABS`)

```python
MAIN_TABS = [
    ("opportunities", "Markets"),
    ("tear_sheet", "Property Analysis"),
    ("compare", "Compare"),
    ("scenarios", "Scenarios"),
    ("data_quality", "Diagnostics"),
    ("settings", "Settings"),
]
```

This tab system (currently hidden via `display: none` at app.py:2007-2012 but still driving routing) is a multi-tool dashboard pattern. The target has no persistent tab bar -- screens are reached through progressive disclosure and contextual navigation.

### Property Manager Drawer
**File:** app.py:2054-2159 (`_add_property_drawer()`)

A complex modal with:
- Saved properties DataTable (row-selectable, 6 columns)
- Comp database DataTable (row-selectable, 5 columns)
- Full property input form (30+ fields grouped into Required/Recommended/Optional)
- Manual comp entry form

This is an admin/power-user tool. For the target design, property creation should be search-driven (paste URL or enter address), not form-driven.

### Opportunity Discovery Board
**File:** app.py:1805-1987 (`_opportunity_discovery_section()`)

Summary cards ("Buy Right Now: 3", "Neutral Watchlist: 2", "Avoid For Now: 1"), 4 filter dropdowns, "Top Picks" grid, "All Surfaced Opportunities" list. This is a Bloomberg-style discovery board. The target wants town cards and simple property cards.

### Portfolio Dashboard
**File:** components.py:6868-6963 (`render_portfolio_dashboard()`)

Aggregate dashboard with stat cards (emojis), property rankings table with rank numbers, category heatmap. Pure institutional analytics surface.

### Tour Overlay System
**File:** components.py:6480-6665 (`_TOUR_STEPS`, `render_tour_overlay()`, `render_tour_trigger_button()`)

9-step guided tour with overlay popups. This was built for the old dashboard paradigm -- a consumer search-first product should not need a tour.

### Context Bar
**File:** app.py:1266-1294 (`_build_shell_context_bar()`)

A contextual information bar below the topbar showing eyebrow text, title, subtitle, and inline metric cards. This duplicates information that should be in the page content itself, not in persistent chrome.

### Compare Multi-Tab View
**File:** app.py:2488-2546 (`_compare_controls()`)

Heatmap/Radar/Table/Detail mode selector with section dropdown. Power-user comparison tool. If it exists in the target, it would be a very late-stage Layer 3 feature, not a primary tab.

---

## 3. What's Missing -- Target Screens with No Current Implementation

### Map Components (Landing, Town Results)
No map rendering exists anywhere in the codebase. There are no Mapbox, Leaflet, or Plotly scattermapbox imports. Google Maps and Apple Maps links exist as external links (app.py:815-822), but there is no embedded interactive map.

**What's needed:** `dcc.Graph` with `go.Scattermapbox` or a `dash-leaflet` component. Pin data would come from the existing geocoding and active listings data.

### Progressive Disclosure Gate Between Layers
No mechanism exists to show Layer 1, then require an explicit opt-in action (button click, scroll gate, or tab) before showing Layer 2 content. Currently, `render_tear_sheet_body()` at components.py:5938 renders the decision summary AND all 5 question sections as one continuous page.

**What's needed:** A "See Full Analysis" or "Dig Deeper" action that transitions from Layer 1 to Layer 2, potentially using `dcc.Store` state to track which layer the user has advanced to.

### Simplified Property Cards for Town Results
The current `_opportunity_button()` (app.py:1735-1802) renders an analytics-rich card with recommendation badge, score, signal label/text, strategy tags, and maps links. The target wants simplified property cards (address, price, key stats) that lead to Layer 1.

### "Monthly Reality" as Primary Element
Monthly cash flow appears only in metric strips (small text). The target wants this as a primary, first-read element on Layer 1 -- "What does it actually cost you per month?"

### URL-First Intake Flow
The search bar on the landing page accepts both address and URL input (two separate fields: `landing-address-input` and `landing-url-input`). But the URL parsing is limited to Zillow (`ZillowUrlParser` at app.py:36) and the flow from URL to property creation is routed through `_resolve_startup_search()` (app.py:683-722), which either finds a saved property, matches a town, or creates a new manual record. There is no streamlined "paste a Zillow URL and get a 10-second answer" experience.

---

## 4. "No Dashboard" Principle Violations

### V1: Auto-Loading Data on Tab Switch
**File:** app.py:3539-3678 (`render_main_tab`)

When switching to the `opportunities` tab, the callback immediately runs `_build_market_view_block()` which calls `build_market_view_model()` (view_models.py:1645) which runs `analyze_markets()` -- a potentially expensive operation. The target says "nothing loads until user chooses."

Similarly, switching to `scenarios` or `data_quality` tabs immediately loads and renders the full report analysis without any user opt-in.

### V2: Charts Visible Before Understanding
**File:** components.py:5938-6175 (`render_tear_sheet_body`)

The tear sheet renders charts inline in every section:
- `comp_positioning_dot_plot()` in the price section
- `forward_waterfall_chart()` in the price section
- `income_carry_waterfall()` in the economics section
- `forward_fan_chart()` in the forward section
- `risk_breakdown_bars()` in the risk section

These are behind `<details>` toggles, so they are collapsed by default. But `get_smart_defaults()` (referenced at line 5954) auto-opens certain sections, exposing charts before the user has absorbed the decision summary.

### V3: Sidebar Navigation
**File:** app.py:1070-1164

The persistent navy sidebar with 6 navigation items is a workspace dashboard pattern. See Section 2 above.

### V4: Tab-Heavy Layout
**File:** app.py:114-121

Six tabs (Markets, Property Analysis, Compare, Scenarios, Diagnostics, Settings) even though the tab bar is visually hidden. The tab system still drives routing and mental model.

### V5: Too Many Panels on Property Analysis
When a property is loaded, the user sees:
1. Context bar (eyebrow + title + subtitle + metric cards)
2. Feedback banner (if missing data)
3. Property header bar (sticky, with 8+ inline metrics)
4. Decision summary (hero + fit/trust cards + 3-column reasons/risks/use-cases + reality check strip + jump links)
5. Five question sections (price, economics, forward, risk, optionality) -- each with answer, summary, metric strip, chart, extra content, evidence chips, missing notes
6. Evidence section
7. Town Intelligence section

This is approximately 15-20 visual blocks before the user even scrolls. The target says "one screen = one job."

### V6: Opportunity Discovery Board Loads Everything
**File:** app.py:1669-1687 (`_opportunity_records`)

On Markets tab load, `_opportunity_records()` iterates all discoverable property IDs and calls `_build_opportunity_record_cached()` for each, which loads the report and builds the view model. Even with LRU caching, first load processes every saved property.

### V7: Pre-Loaded Property Dropdown in Topbar
**File:** app.py:1482-1524

The topbar renders a property selector dropdown pre-populated with all saved properties. This is "load everything" behavior -- the target says the user should search and choose.

---

## 5. Institutional Dashboard Patterns to Dismantle

### Pattern 1: Workspace Shell Architecture
**Files:** app.py:2549-2621 (`_build_layout`), app.py:247-262 (`_SHELL_SIDEBAR_STYLE`), app.py:264-270 (`_SHELL_MAIN_COLUMN_STYLE`)

The app is built as a 2-column layout: fixed sidebar + flexible main area with topbar, context bar, feedback banner, and content area. This is a CRM/analytics workspace pattern.

**Code to dismantle:** The `_build_layout()` function at app.py:2549 constructs the shell. The `html.Aside` sidebar, `_topbar()`, context bar, and `_main_tab_bar()` should be removed or made conditional per screen.

### Pattern 2: Global Property Selector
**Files:** app.py:1481-1524 (`_topbar`), app.py:2627-2648 (`refresh_property_controls`)

A global dropdown that tracks "active property" across all tabs. Multiple callbacks depend on `property-selector-dropdown` as an input (at least 8 callbacks reference it). The target design has no global property context -- each screen is self-contained.

### Pattern 3: Loaded Preset ID Tracking
**File:** app.py:2553 (`dcc.Store(id="loaded-preset-ids")`)

A `dcc.Store` tracks which property IDs have been loaded in the current session. This is used by opportunity discovery, market view, compare selection, and the topbar. It assumes a multi-property session, which is a portfolio management pattern.

### Pattern 4: Compare Infrastructure
**Files:** app.py:2488-2546 (`_compare_controls`), compare.py (293 lines), components.py:7928+ (`render_compare_decision_mode`)

Full compare view with 7 sections (Overview, Value, Forward, Risk, Location, Income, Evidence), 4 modes (Heatmap, Radar, Table, Detail), and a `CompareSummary` data model with weighted comparison scores. This is an institutional analysis tool.

### Pattern 5: Data Quality Tab as Peer Navigation
**File:** data_quality.py (677 lines)

Full comp database health dashboard, per-property comp matching, value driver attribution tables. This is a developer/analyst tool presented as a first-class navigation destination alongside property analysis.

### Pattern 6: Context Bar Metrics
**File:** app.py:1178-1263 (`_shell_context_for_tab`)

Each tab gets its own context bar with inline metric cards ("Surfaced: 5 visible opportunity universe", "Loaded: 3 properties in this session"). This is Bloomberg-style contextual intelligence chrome.

---

## 6. Quick Decision System: What Exists vs What Layer 1 Needs

### What Exists

#### quick_decision.py (532 lines)
Pure data derivation layer. Takes an `AnalysisReport`, returns a `QuickDecisionViewModel` containing:
- `recommendation` (Buy/Watch/Pass) -- mapped from score via `_derive_recommendation()` (line 143)
- `confidence` (High/Medium/Low) -- derived from comp confidence + module count (line 150)
- `score` (1.0-5.0) -- from the decision model's `calculate_final_score()` (line 510)
- `key_reasons` (list of KeyReason with text + sentiment) -- top 3-5 from scoring sub-factors, jargon-rewritten (line 167)
- `best_use_cases` (list of UseCase with label + description + strength) -- derived from income, value, teardown, renovation metrics (line 230)
- `scenario_snapshots` (list of ScenarioSnapshot with name, monthly_cost, rent, net position, takeaway) -- bull/base/bear from forward scenarios (line 333)
- `risks` (list of strings) -- top 3 from scoring + fallback generics (line 408)
- `value_finder` (ValueFinderSummary) -- opportunity/overpriced/fair based on BCV vs ask (line 456)

**Key feature:** Jargon-to-plain-English rewrite system at lines 29-46. Converts "PPSF positioning" to "price per square foot compared to similar homes", "ISR" to "income support ratio", etc.

#### components_quick_decision.py (510 lines)
Rendering layer for the `QuickDecisionViewModel`:
- `render_recommendation_hero()` (line 80): Full-width hero card with BUY/WATCH/PASS in 56px Source Serif 4, score in 48px, confidence dot
- `render_key_reasons()` (line 205): Checklist-style reasons with sentiment icons (checkmark/warning/bullet)
- `render_use_cases_and_risks()` (line 292): Side-by-side cards -- use cases with strength badges, risks with warning bullets
- `render_scenario_snapshots()` (line 380): Table with monthly cost, rent, net position columns + takeaway text
- `render_value_finder()` (line 428): Opportunity/Overpriced/Fair Value badge with delta percentage and explanation
- `render_full_analysis_button()` (line 484): "View Full Analysis ->" button that navigates to tear_sheet tab
- `render_quick_decision()` (line 499): Assembles all of the above into one page

### What Layer 1 Actually Needs (vs what exists)

| Need | Status | Gap |
|------|--------|-----|
| Buy/Watch/Pass verdict | DONE | Hero is well-designed, 56px serif type, color-coded |
| Confidence indicator | DONE | Dot + label in hero card |
| Score | DONE | 48px numeral in hero card |
| "Why" reasons (3-5) | DONE | KeyReason with sentiment icons, jargon rewriting |
| "What's the catch" risks | DONE | 3 risks with warning icons |
| Monthly reality (primary) | PARTIAL | Exists in scenario snapshots table but not as hero-level metric. Monthly cost, rent, and net position are in a data table at the bottom, not a prominent card at the top. |
| Value range | PARTIAL | Value Finder shows opportunity delta but not a clean "worth $X-$Y" range. The ask/fair-value/base spread is in System A's metric strip, not in System B. |
| Best fit | DONE | Use cases with strength badges |
| "Dig deeper" action | DONE | "View Full Analysis" button at the bottom |
| 10-second readable | PARTIAL | 5 sections (hero, reasons, use-cases/risks, scenarios, value-finder) is more than 10 seconds. The scenario table especially adds scanning time. |

### Integration Problem

`render_quick_decision()` (the clean page assembly at components_quick_decision.py:499-510) is **never called** in the main app routing. Instead, `render_property_decision_summary()` at components.py:2739 does its own assembly that:
1. Calls `build_quick_decision_view()` (reuses the data)
2. Calls `render_recommendation_hero()` (reuses the hero)
3. But then builds its own layout with Best Fit card, Trust Read card, 3-column reasons/risks/use-cases, and a "Fast Reality Check" strip with jump links

So the app has **two competing Layer 1 implementations**:
- **System B** (`render_quick_decision()`): cleaner, more focused, proper progressive disclosure with "View Full Analysis" button. But never rendered.
- **System A** (`render_property_decision_summary()`): what users actually see. More complex, includes jump links that break progressive disclosure, mixed with the trust/assumption quality concerns.

### What Must Change for Layer 1

1. **Promote monthly reality to hero level.** Add a large-format monthly cost/rent/net metric block directly after the recommendation hero, before reasons.

2. **Remove jump links.** The "See Value Scenarios", "See Price Support", "Show More Detail" buttons at components.py:2831-2851 expose Layer 2/3 before the user opts in.

3. **Merge the two systems.** Use `render_quick_decision()` as the actual Layer 1 renderer. Add the monthly reality and value range elements from System A's metric strip.

4. **Gate the transition to Layer 2.** The "View Full Analysis" button (components_quick_decision.py:484-494) exists but is never rendered in the actual app. It should be the sole transition point from Layer 1 to the deeper sections.

5. **Simplify the scenario table.** The bull/base/bear scenario snapshots table is useful but too dense for a 10-second scan. Consider condensing to a single "Best Case $X / Most Likely $Y / Worst Case $Z" strip.

6. **Remove Trust Read / assumption quality from Layer 1.** The "Trust Read" card in System A (components.py:2760-2780) shows assumption quality detail ("3 of 4 key assumptions are strong"). This is a Layer 3 concern.

---

## Summary: Work Required by Target Screen

| Screen | % Done | Key Gaps |
|--------|--------|----------|
| Landing | 75% | Coupled to tab system; no map |
| Town Results | 50% | No map; analytics-heavy cards |
| Property Layer 1 | 60% | Two competing systems; no disclosure gate; monthly reality not prominent |
| Property Layer 2 | 55% | Content exists but not layered; no opt-in transition |
| Property Layer 3 | 85% | Content very complete; not behind progressive gate |
| Markets Tab | 65% | Dashboard-heavy discovery board; no map |

### Architecture Blockers (Must Fix First)

1. **Tab routing system** (app.py:114-121, 3539-3678): All screens route through `MAIN_TABS`. Need URL-based routing or a state machine that replaces tabs with screen transitions.

2. **Workspace shell** (app.py:2549-2621): The sidebar + topbar + context bar chrome wraps all screens. Need to remove or make conditional per screen type.

3. **Global property state** (`property-selector-dropdown`, `loaded-preset-ids`): Multiple callbacks depend on global property tracking. Need to move to per-screen property context.

4. **Dual Layer 1 systems** (components.py:2739 vs components_quick_decision.py:499): Must merge into one clean implementation.

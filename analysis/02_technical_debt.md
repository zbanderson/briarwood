# Briarwood Technical Debt & Dead Code Audit

**Date:** 2026-04-11
**Scope:** ~64,800 lines across ~150 Python source files (246 total including tests)
**Focus:** Dead code, redundant code, orphaned assets, stale dependencies, callback spaghetti, over-engineering

---

## 1. Dead Code

### 1.1 Dead Functions in `components.py` (7,992 lines)

These public/semi-public functions are **defined but never called** anywhere in the codebase (no import, no call site, not even in tests):

| Function | Line | Lines of Code | Severity |
|----------|------|---------------|----------|
| `render_lens_selector()` | 345 | ~70 | REMOVE |
| `render_score_header()` | 416 | ~110 | REMOVE |
| `render_executive_summary()` | 609 | ~85 | REMOVE |
| `render_category_section()` | 696 | ~85 | REMOVE |
| `render_property_verdict()` | 2054 | ~160 | REMOVE |
| `render_perspective_block()` | 2215 | ~85 | REMOVE |
| `render_what_if_slider()` | 6674 | ~100 | REMOVE |
| `render_single_section()` | 7509 | ~15 | REMOVE |

**Estimated dead lines: ~710 lines (8.9% of components.py)**

These were likely part of an earlier UI revision (v1 scoring header / verdict / lens system) that was superseded by the v2 category-section and decision-summary patterns. `render_what_if_slider` is defined but the what-if feature is driven by `render_what_if_metrics` instead; the slider itself is built inline in `render_tear_sheet_body`.

### 1.2 Dead Functions in `components.py` -- Private helpers only used by dead functions

These are helpers called exclusively by the dead functions above:

| Function | Line | Notes |
|----------|------|-------|
| `_render_category_mini_bars()` | 478 | Only called by dead `render_score_header` |
| `_category_drill_in_summary()` | 531 | Only called by dead `render_score_header` |
| `_render_category_components()` | 542 | Only called by dead `render_score_header` |
| `render_sub_factors()` | 587 | Only called by dead `render_score_header` and `render_category_section` |

### 1.3 Unused Aliases in `components.py`

```python
# Line 99-101 -- defined but never referenced
RESPONSIVE_GRID_2 = GRID_2
RESPONSIVE_GRID_3 = GRID_3
RESPONSIVE_GRID_4 = GRID_4
```

**Severity: REMOVE** -- These are just aliases that were never used.

### 1.4 Unused Import in `components.py`

`HEADING_M_STYLE` is imported (line 24) but never used in the file.

**Severity: REMOVE**

### 1.5 Dead Modules -- Not Used by Engine or Any Live Code

| Module | File | References |
|--------|------|------------|
| `market_snapshot` | `briarwood/modules/market_snapshot.py` | Only referenced in `tests/test_market_snapshot.py` -- never imported by the engine, runner, dash app, or any other production code |
| `relative_opportunity` | `briarwood/modules/relative_opportunity.py` | Only referenced in `tests/test_relative_opportunity.py` -- never imported by the engine, runner, or dash app |

**Severity: REMOVE** -- Both modules are tested in isolation but have zero production call sites. `market_snapshot` depends on `AttomClient` and `NJTaxIntelligenceStore` and appears to be a standalone analytics tool that was never wired into the engine. `relative_opportunity` compares multiple reports but is never called from the dash app's compare flow.

### 1.6 Dead File: `briarwood/entry_prep.py`

Never imported anywhere. Contains `REQUIRED_PROPERTY_FIELDS` list and appears to be an early draft of the manual-entry data pipeline. The functionality now lives in `dash_app/data.py` + `runner.py`.

**Severity: REMOVE**

### 1.7 Dead File: `briarwood/local_intelligence/ui.py`

Never imported anywhere. Contains `build_town_pulse_view()` which creates a `TownPulseView` model. This was likely a prototype that was replaced by the view model approach in `dash_app/view_models.py` (`build_town_pulse_view_model_from_payload`).

**Severity: REMOVE**

### 1.8 Dead File: `briarwood/dashboard_contract.py`

Only imported by `tests/test_scorecard.py`. Never imported by any production code (not in dash app, runner, or engine).

**Severity: REMOVE** (or merge its `MODULE_DEPENDENCIES` map into `decision_model/` if still useful for testing)

### 1.9 Dead Function in `runner.py`

`format_tear_sheet_summary()` (line 238, ~50 lines) is defined but never called anywhere in the codebase.

**Severity: REMOVE**

### 1.10 Dead Tour System

The guided tour feature is fully disabled:
- `render_tour_trigger_button()` is rendered with `display: none` (app.py line 2615)
- `render_tour_overlay` is imported but **never called** in app.py
- `tour_render()` callback always returns `None` (line 5210-5211)
- `tour_auto_show()` callback always returns `-1` (line 5222-5223)
- `_TOUR_STEPS` data (components.py line 6480, ~110 lines) is referenced but the tour never actually renders

The tour system occupies ~190 lines across components.py and app.py.

**Severity: REMOVE** -- All tour callbacks, imports, data, and layout elements can be deleted.

---

## 2. Redundant Code

### 2.1 Duplicate Utility Functions Across Dash Files (CRITICAL)

The following functions are **copy-pasted** with identical or near-identical logic across multiple files:

| Function | Defined In | Notes |
|----------|-----------|-------|
| `_fmt_currency()` | `app.py:399`, `view_models.py:52` | Identical logic, different null string ("---" vs "Unavailable") |
| `_clean_text()` | `app.py:405`, `view_models.py:58` | Identical |
| `_property_identity()` | `app.py:436`, `view_models.py:62` | Identical (23 lines each) |
| `_maps_links()` | `app.py:815`, `view_models.py:80` | Identical |
| `_parse_currency_text()` | `components.py:257`, `view_models.py:128` | Identical |

**Severity: REFACTOR** -- Extract these into a shared `dash_app/utils.py` module. The null-string inconsistency ("---" vs "Unavailable") between `app.py` and `view_models.py` copies of `_fmt_currency` is a latent bug.

### 2.2 Repeated Inline Imports of `estimate_comp_renovation_premium`

`from briarwood.decision_model.scoring import estimate_comp_renovation_premium` appears as a deferred inline import in **7 separate locations** within `components.py` (lines 1191, 4172, 4591, 4731, 4754, 5729, 5758).

**Severity: REFACTOR** -- Move to a top-level import. The deferred pattern was likely used to avoid circular imports but the module graph does not require it here.

### 2.3 Three Generations of Category/Score Rendering

`components.py` contains three overlapping approaches to rendering property scores and categories:

1. **v1** (dead): `render_score_header`, `render_category_section`, `render_lens_selector`, `render_executive_summary`, `render_property_verdict`, `render_perspective_block`
2. **v2** (active): `render_category_section_v2`, `_render_v2_category_bars`, `render_sub_factor_row_v2`
3. **Decision summary** (active): `render_property_decision_summary`, `_compact_verdict_strip`

v1 should be deleted (see Section 1.1). The remaining v2 + decision summary approaches serve different contexts (full tear sheet vs. compact summary).

**Severity: REMOVE v1, KEEP v2 and decision summary.**

---

## 3. Orphaned Assets

### 3.1 Orphaned Data Directory: `data/manual_entries/`

Referenced only via `LEGACY_MANUAL_ENTRY_DIR` in `dash_app/data.py` for backward-compatible loading of old manual entries. If no `.json` files remain in this directory, it can be removed.

**Severity: KEEP (migration path)** -- but add a deprecation log warning when loading from it.

### 3.2 Orphaned Data Directory: `data/local_intelligence/documents/`

Listed as untracked in git status. No Python code references `data/local_intelligence/documents` -- the local intelligence system reads from `data/local_intelligence/signals/`.

**Severity: REMOVE** (or `.gitignore`)

### 3.3 Data Files Referenced by Tests Only

- `data/sample_zillow_listing.txt` -- only used in `tests/test_listing_intake.py`
- `data/sample_zillow_listing_belmar.txt` -- used in tests AND the preset loader in `dash_app/data.py`
- `data/sample_zillow_listing_briarwood_rd_belmar.txt` -- used in tests AND preset loader

The first file is test-only. Consider moving it to `tests/fixtures/`.

**Severity: KEEP** (no harm, but could be organized)

---

## 4. Stale Dependencies

### 4.1 `requirements.txt` Analysis

The `requirements.txt` contains 5 packages:

| Package | Used? | Notes |
|---------|-------|-------|
| `pydantic>=2,<3` | YES | 15 files import it (schemas, models, validation) |
| `openai>=1.0,<2` | YES | Used in `local_intelligence/adapters.py` (deferred import) |
| `dash>=2.18,<3` | YES | Core framework |
| `plotly>=5.24,<6` | YES | Used throughout components |
| `weasyprint>=62,<69` | YES | Used in `reports/pdf_renderer.py` (deferred import) |

**All declared dependencies are used.** The `requirements.txt` is minimal and accurate.

### 4.2 Undeclared Optional Dependencies

- `python-dotenv` -- used in `briarwood/__init__.py` (with graceful fallback via try/except)
- `dash-bootstrap-components` -- used in `dash_app/app.py` (with graceful fallback via shim class)
- `geopy` -- likely used by `briarwood/geocoder.py` (gated behind env var `BRIARWOOD_ENABLE_GEOCODING`)

These are all handled as optional, but documenting them in a `requirements-optional.txt` or `pyproject.toml` `[project.optional-dependencies]` section would improve clarity.

**Severity: KEEP (handled correctly), but document.**

---

## 5. Callback Spaghetti

### 5.1 Callback Count and Output Proliferation

`dash_app/app.py` contains **47 callbacks** total. Many outputs are written by multiple callbacks via `allow_duplicate=True`:

| Output ID | Callback Count | Concern |
|-----------|---------------|---------|
| `loaded-preset-ids.data` | 7 callbacks | High -- hard to trace which callback last set the value |
| `main-tabs.value` | 7 callbacks | High -- tab navigation from 7 different entry points |
| `add-property-open.data` | 6 callbacks | Medium -- drawer open state managed across many callbacks |
| `manual-entry-status.children` | 6 callbacks | Medium -- status text from multiple sources |
| `market-preview-open.data` | 5 callbacks | Medium -- preview drawer toggled from many places |

**Severity: REFACTOR** -- The `loaded-preset-ids` and `main-tabs` outputs should be centralized into a single routing callback that dispatches based on `ctx.triggered_id`, rather than scattered across 7 independent callbacks each using `allow_duplicate=True`.

### 5.2 Monster Callback: `run_manual_analysis`

The `run_manual_analysis` callback (line 4871) has:
- **8 Outputs**
- **1 Input**
- **46 States** (every form field individually)
- Function body is ~250 lines

This is the single largest callback in the app. It reads every manual form field as a separate `State`, constructs a property dict, calls `register_manual_analysis`, and handles update-vs-create logic.

**Severity: REFACTOR** -- Consider using a single `dcc.Store` to hold the entire form state as a dict. The form's 46 fields could be serialized via a client-side callback, and `run_manual_analysis` would receive a single `State("form-data", "data")` instead of 46 individual States.

### 5.3 Monster Callback: `populate_manual_form`

The `populate_manual_form` callback (line 4357) has:
- **46 Outputs** (one for each form field)
- Returns `(no_update,) * 46` on early exit

This is the inverse of `run_manual_analysis`. Same refactoring advice applies.

**Severity: REFACTOR**

### 5.4 `render_main_tab` -- Monolithic Tab Router

`render_main_tab` (line 3529) takes **7 inputs** and handles rendering for all 5+ tab types in a single function body (~300 lines). It mixes routing logic with layout construction.

**Severity: REFACTOR** -- Split into per-tab rendering functions called from the router. The tab-specific rendering logic (market view, tear sheet, compare, scenarios, data quality) should each be its own function.

### 5.5 Redundant `_focused_report()` Calls

Many callbacks independently call `_focused_report(loaded_ids, focus_id)` and `_build_property_view_for_property(property_id)`. These are cached via `@lru_cache`, but the pattern of receiving `loaded_ids` + `focus_id` as separate Inputs and resolving them is repeated in ~10 callbacks.

**Severity: REFACTOR** -- Consider a shared utility or a higher-level Store pattern.

---

## 6. Over-Engineering

### 6.1 `_BENCHMARKS` System (components.py lines 48-83)

A benchmark comparison system with `_BENCHMARKS`, `_BENCHMARK_LOWER_BETTER`, `_benchmark_context()`, and `_benchmark_sublabel()` that computes deltas against hardcoded NJ coastal averages. This is used by a handful of metric display functions. The hardcoded constants (PTR=15, cash_flow=-800, DOM=45, etc.) are not configurable and will silently become stale.

**Severity: KEEP but move constants to `settings.py` or `theme.py` and document the update cadence.**

### 6.2 Three Levels of Confidence Display

`components.py` implements three separate confidence display patterns:
1. `confidence_badge()` -- simple percentage span
2. `confidence_level_badge()` -- multi-line div with icon, label, and narrative
3. `section_confidence_indicator()` -- single-line dot+percentage with color coding

All three are used. However, `confidence_level_badge` is only called by the dead `render_score_header`. After removing dead code, only `confidence_badge` and `section_confidence_indicator` remain.

**Severity: REMOVE `confidence_level_badge` (dead). KEEP the other two (they serve different visual contexts).**

### 6.3 `TownPulseView` Model Duplication

Two separate town pulse view models exist:
- `briarwood/local_intelligence/models.py::TownPulseView` (used by dead `ui.py`)
- `briarwood/dash_app/view_models.py::TownPulseViewModel` (used by the live dash app)

**Severity: REMOVE `TownPulseView` from `models.py` if no other code references it, and delete `ui.py`.**

### 6.4 `_DBCShim` Bootstrap Fallback (app.py lines 22-31)

A shim class that replaces `dash_bootstrap_components` with plain HTML elements if the package is missing. This is 10 lines of code for a fallback that will only be hit if the user forgets to install dbc. It could be replaced by adding `dash-bootstrap-components` to `requirements.txt`.

**Severity: KEEP** -- Pragmatic for lightweight local usage, but consider making dbc a hard dependency.

---

## 7. Summary Table

| Category | Items Found | Est. Removable Lines | Priority |
|----------|------------|---------------------|----------|
| Dead functions in components.py | 12 functions | ~900 | HIGH |
| Dead modules (market_snapshot, relative_opportunity) | 2 files | ~500 | MEDIUM |
| Dead files (entry_prep, local_intelligence/ui, dashboard_contract) | 3 files | ~150 | MEDIUM |
| Dead tour system | 3 callbacks + data | ~190 | HIGH |
| Dead runner function (format_tear_sheet_summary) | 1 function | ~50 | LOW |
| Duplicate utility functions | 5 functions x 2-3 copies | ~120 (after consolidation) | HIGH |
| Repeated inline imports | 7 occurrences | ~7 | LOW |
| Unused aliases and imports | 4 items | ~5 | LOW |
| Callback spaghetti (allow_duplicate proliferation) | 5 outputs, 7+ callbacks each | (no line savings, architectural) | HIGH |
| Monster callbacks (46 States) | 2 callbacks | (no line savings, architectural) | MEDIUM |
| **Total removable lines** | | **~1,920** | |

---

## 8. Recommended Action Plan

### Phase 1: Safe Deletions (1-2 hours, ~1,100 lines)
1. Delete the 12 dead functions and their private helpers from `components.py`
2. Delete unused aliases (`RESPONSIVE_GRID_*`) and unused imports (`HEADING_M_STYLE`)
3. Remove dead tour system (callbacks, data, imports, layout elements)
4. Delete `render_tour_overlay` import from app.py
5. Delete `format_tear_sheet_summary` from `runner.py`
6. Delete `briarwood/entry_prep.py`
7. Delete `briarwood/local_intelligence/ui.py`

### Phase 2: Module Cleanup (1 hour, ~500 lines)
1. Delete `briarwood/modules/market_snapshot.py` and its test
2. Delete `briarwood/modules/relative_opportunity.py` and its test
3. Evaluate `briarwood/dashboard_contract.py` -- delete or merge
4. Remove `data/local_intelligence/documents/` directory

### Phase 3: Deduplication (2-3 hours)
1. Create `briarwood/dash_app/utils.py` with shared `_fmt_currency`, `_clean_text`, `_property_identity`, `_maps_links`, `_parse_currency_text`
2. Update `app.py`, `view_models.py`, and `components.py` to import from the shared module
3. Move `estimate_comp_renovation_premium` import to top-level in `components.py`

### Phase 4: Callback Architecture (4-6 hours)
1. Consolidate `loaded-preset-ids` and `main-tabs` outputs into a single routing callback
2. Replace the 46-State form callbacks with a `dcc.Store`-based approach
3. Split `render_main_tab` into per-tab rendering functions

---

## 9. Files Referenced

Key files examined during this audit:

- `/Users/zachanderson/projects/briarwood/briarwood/dash_app/components.py` (7,992 lines)
- `/Users/zachanderson/projects/briarwood/briarwood/dash_app/app.py` (5,320 lines)
- `/Users/zachanderson/projects/briarwood/briarwood/dash_app/view_models.py` (2,893 lines)
- `/Users/zachanderson/projects/briarwood/briarwood/runner.py`
- `/Users/zachanderson/projects/briarwood/briarwood/engine.py`
- `/Users/zachanderson/projects/briarwood/briarwood/entry_prep.py`
- `/Users/zachanderson/projects/briarwood/briarwood/local_intelligence/ui.py`
- `/Users/zachanderson/projects/briarwood/briarwood/dashboard_contract.py`
- `/Users/zachanderson/projects/briarwood/briarwood/modules/market_snapshot.py`
- `/Users/zachanderson/projects/briarwood/briarwood/modules/relative_opportunity.py`
- `/Users/zachanderson/projects/briarwood/briarwood/dash_app/theme.py`
- `/Users/zachanderson/projects/briarwood/requirements.txt`

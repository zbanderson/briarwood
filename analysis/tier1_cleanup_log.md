# Tier 1 Cleanup Log

**Date:** 2026-04-11  
**Scope:** Safe deletes and lazy imports — no logic refactors, no behavior changes  
**Rule:** Grep before deleting. Git commit after each task. If uncertain, skip and document.

---

## Summary

| Metric | Value |
|---|---|
| Files modified | 15 |
| Files deleted | 8 |
| Net lines removed | ~417 (2,354 deletions − 1,937 insertions) |
| Commits | 6 |
| App starts after cleanup | Yes |
| Tests pass after cleanup | Yes (18/18 in modified test files) |

---

## Task 1: Remove Dead v1 Scoring Functions from `components.py`

**Commit:** `7f9735a` — chore: remove dead v1 scoring functions from components.py  
**Lines removed:** ~860

### Functions removed (12 + 4 helpers):

| Function | Grep result |
|---|---|
| `render_lens_selector` | 0 call sites outside definition |
| `render_score_header` | 0 call sites outside definition |
| `_render_category_mini_bars` | 0 call sites outside definition |
| `_category_drill_in_summary` | 0 call sites outside definition |
| `_render_category_components` | 0 call sites outside definition |
| `render_sub_factors` | 0 call sites outside definition |
| `render_executive_summary` | 0 call sites outside definition |
| `render_category_section` | 0 call sites outside definition |
| `render_property_verdict` | 0 call sites outside definition |
| `_verdict_bullet` | 0 call sites outside definition |
| `_generate_bottom_line` | 0 call sites outside definition |
| `render_perspective_block` | 0 call sites outside definition |
| `render_what_if_slider` | 0 call sites outside definition |
| `render_single_section` | 0 call sites outside definition |
| `confidence_level_badge` | 0 call sites outside definition |
| `_confidence_level_dot` | 0 call sites outside definition |

### Also removed:
- `RESPONSIVE_GRID_*` aliases (unused layout constants)
- `HEADING_M_STYLE` unused import

### Kept (confirmed alive):
- `_compact_lens_badge` — called by live `_compact_verdict_strip` (~line 3044)
- `_confidence_level_color` — called at ~line 2794
- `_LENS_DISPLAY` — used at ~line 6720
- `render_what_if_metrics` — alive, distinct from dead `render_what_if_slider`

**Result:** `components.py` 7,992 → 6,939 lines

---

## Task 2: Remove Dead Tour System

**Commit:** `b413c0a` — chore: remove dead tour system from app.py and components.py

### From `components.py` (~193 lines):
| Item | Grep result |
|---|---|
| `_TOUR_STEPS` data structure | Only used by tour system |
| `render_tour_overlay` | Only used by tour system |
| `render_tour_trigger_button` | Only used by tour system |

### From `app.py` (~125 lines):
- Removed tour imports (`_TOUR_STEPS`, `render_tour_overlay`, `render_tour_trigger_button`)
- Removed tour layout elements (`dcc.Store` for tour-state, tour-step, tour-overlay-container, tour trigger button)
- Removed 3 tour callbacks: `tour_navigate`, `tour_render`, `tour_auto_show`

**Result:** ~318 lines removed across both files

---

## Task 3: Delete Dead Files

**Commit:** `b88aeb5` — chore: delete dead files and clean up references

| File | Lines | Grep confirmation |
|---|---|---|
| `briarwood/entry_prep.py` | 68 | `grep -r entry_prep` → 0 imports anywhere |
| `briarwood/local_intelligence/ui.py` | 16 | Only imported by `__init__.py` (fixed) |
| `briarwood/dashboard_contract.py` | 154 | Only imported by `tests/test_scorecard.py` (fixed) |
| `briarwood/agents/current_value/inspect_data.py` | 116 | `grep -r inspect_data` → 0 imports; one-off script with `if __name__` |

### Cascading fixes required:
- `briarwood/local_intelligence/__init__.py`: removed `from .ui import build_town_pulse_view` and `"build_town_pulse_view"` from `__all__`
- `tests/test_scorecard.py`: removed `from briarwood.dashboard_contract import build_dashboard_analysis_summary` and dead test method `test_dashboard_contract_exposes_sections_and_dependencies`
- `tests/test_local_intelligence.py`: removed `build_town_pulse_view` import and dead assertions (lines 558-566)

**Total:** 354 lines deleted + reference cleanup

---

## Task 4: Delete Dead Modules

**Commit:** `67932f9` — chore: delete dead modules market_snapshot and relative_opportunity

| File | Lines | Grep confirmation |
|---|---|---|
| `briarwood/modules/market_snapshot.py` | 190 | Only referenced by own test file |
| `briarwood/modules/relative_opportunity.py` | 271 | Only referenced by own test file |
| `tests/test_market_snapshot.py` | 63 | Test-only, deleted with module |
| `tests/test_relative_opportunity.py` | 121 | Test-only, deleted with module |

### Not removed (intentionally kept):
- `RelativeOpportunityResult` and related schema classes in `briarwood/schemas.py` — schema removal is riskier; may be referenced by serialized data
- `RelativeOpportunitySettings` in `briarwood/settings.py` — same rationale

**Total:** 645 lines deleted

---

## Task 5: Remove Dead Function from `runner.py`

**Commit:** `06a3e1d` — chore: remove dead format_tear_sheet_summary from runner.py

| Function | Lines | Grep confirmation |
|---|---|---|
| `format_tear_sheet_summary` | 43 | `grep -r format_tear_sheet_summary` → 0 call sites |

**Result:** `runner.py` 423 → 380 lines

---

## Task 6: Lazy Imports in `data.py`

**Commit:** `609308b` — perf: defer runner and pdf_renderer imports in data.py

### Module-level imports removed:
```python
from briarwood.runner import run_report, run_report_from_listing_text, write_report_html
from briarwood.reports.pdf_renderer import write_tear_sheet_pdf
```

### Lazy import added to these functions:
| Function | Deferred import |
|---|---|
| `_load_json_report` | `from briarwood.runner import run_report` |
| `_load_listing_report` | `from briarwood.runner import run_report_from_listing_text` |
| `export_preset_tear_sheet` | `from briarwood.runner import write_report_html` |
| `export_preset_tear_sheet_pdf` | `from briarwood.reports.pdf_renderer import write_tear_sheet_pdf` |
| `_load_comp_database_report` | `from briarwood.runner import run_report` |
| `register_manual_analysis` | `from briarwood.runner import run_report, write_report_html` |
| `_reanalyze_saved_property` | `from briarwood.runner import run_report` |

### Added helper for lambda usage:
```python
def _lazy_run_report(path):
    from briarwood.runner import run_report
    return run_report(path)
```

### Verification:
```python
import briarwood.dash_app.data
import sys
assert "briarwood.runner" not in sys.modules  # PASS
assert "briarwood.reports.pdf_renderer" not in sys.modules  # PASS
```

**Impact:** `briarwood.runner` pulls in 20+ analysis modules. Deferring it means Dash app startup no longer eagerly loads the entire analysis engine.

---

## Task 7: Cleanup Pass

### Checks performed:
1. **Full import check:** `python3 -c "from briarwood.dash_app.app import app"` → OK
2. **Compile check:** All 7 modified `.py` files compile without errors
3. **`__all__` verification:** All 27 entries in `local_intelligence/__all__` resolve correctly
4. **Deleted module verification:** `briarwood.modules.market_snapshot` and `briarwood.modules.relative_opportunity` raise `ModuleNotFoundError` as expected
5. **Stale reference grep:** No remaining references to deleted files/functions (only `town_relative_opportunity_score` metric name, which is live)
6. **Test run:** `pytest tests/test_scorecard.py tests/test_local_intelligence.py` → 18/18 passed

No additional changes needed.

---

## Issues Encountered

1. **Edit mismatch on `render_property_verdict` removal:** File had `"alignItems": "flex-start"` but edit assumed `"alignItems": "baseline"`. Fixed by re-reading file for exact content.
2. **`ModuleNotFoundError` after deleting `local_intelligence/ui.py`:** The `__init__.py` still imported `build_town_pulse_view` from it. Fixed by removing the import line, `__all__` entry, and cleaning test references.
3. **File modified since read error:** Edit tool rejected a change because a prior bash edit had modified the file. Fixed by re-reading before editing.

---

## Items NOT Removed (Intentionally Skipped)

| Item | Reason |
|---|---|
| `RelativeOpportunityResult` in `schemas.py` | Schema class may be referenced by serialized JSON data; riskier to remove |
| `RelativeOpportunitySettings` in `settings.py` | Same rationale as above |
| `MarketSnapshotResult` in `schemas.py` | Same rationale |
| `_compact_lens_badge` in `components.py` | Initially appeared dead but confirmed alive via `_compact_verdict_strip` |
| `_confidence_level_color` in `components.py` | Confirmed alive at line ~2794 |
| `_LENS_DISPLAY` in `components.py` | Confirmed alive at line ~6720 |

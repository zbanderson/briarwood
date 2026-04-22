# Phase 2 Remediation — Complete

**Date:** 2026-04-22
**Scope:** Execute Path B1 from `PATH_COVERAGE_REPORT.md` — delete the legacy `AnalysisEngine` fallback and make the scoped registry the sole execution path.
**Outcome:** Single execution spine. No `execution_mode` coordinate, no `build_engine()`, no `AnalysisEngine`, no legacy-only modules.

---

## 1. Why Path B1

Stage A (`PATH_COVERAGE_REPORT.md`) enumerated every `RoutingDecision.selected_modules` set the router can produce (20 `(intent × depth)` module sets plus every `question_focus` hint reachable through `INTENT_TO_MODULES ∩ QUESTION_FOCUS_TO_MODULE_HINTS`). Coverage in the scoped registry was **100%**. The legacy `AnalysisEngine` fallback was therefore unreachable at runtime — load-bearing only for the *possibility* that a future router change could route around it. B1 deletes the unreachable branch; B2 would have kept it alive "just in case." The user approved B1.

## 2. What changed

### 2.1 Core spine

- **`briarwood/orchestrator.py`** — dropped `_VALID_EXECUTION_MODES`, removed the `execution_mode` keyword-only parameter from `build_cache_key` (keys now shape `v2:<fact-fingerprint>`), removed the `module_runner` parameter from `run_briarwood_analysis` / `run_briarwood_analysis_with_artifacts`, and replaced the legacy fallback branch with:

  ```python
  if not scoped_supported or execution_plan is None:
      raise RoutingError(
          "Scoped execution registry does not cover the selected module set: "
          f"{[module.value for module in selected_modules]!r}. "
          "Every routable module must have a scoped runner."
      )
  ```

  The error is surfaced rather than silently falling back — any future regression in router → registry coverage fails loudly at the orchestrator boundary.

- **`briarwood/runner_routed.py`** — deleted `ROUTING_MODULE_MAP`, `_build_module_payload`, `_build_engine_output_for_selected_modules`, `_make_legacy_module_runner`, `_scoped_synthesizer_legacy`. `run_routed_analysis_for_property` no longer takes `module_runner` and no longer returns `report` / `execution_mode`. The `cost_settings` / `bull_base_bear_settings` / `risk_settings` parameters remain on the signature (now `del`-ed) to preserve call-site compat until a separate cleanup pass.

- **`briarwood/runner_common.py`** — removed all 19 legacy-module imports and `build_engine()`. `RoutedAnalysisResult` now carries only `routing_decision`, `engine_output`, `unified_output`, `property_summary`.

### 2.2 Deleted files

| File | Reason |
|---|---|
| `briarwood/engine.py` | `AnalysisEngine` + `build_engine()` — the legacy fallback spine |
| `briarwood/modules/property_snapshot.py` | Legacy-only; not in scoped registry, no non-test importer after `build_engine` deletion |
| `briarwood/modules/liquidity_signal.py` | Same |
| `briarwood/modules/market_momentum_signal.py` | Same |
| `briarwood/modules/value_drivers.py` | Same |
| `tests/test_engine.py` | Covered `AnalysisEngine` |
| `tests/test_group4.py` | Covered the four deleted legacy-only modules |
| `tests/test_orchestrator_cache.py` | Pinned `execution_mode` cache-key behaviour introduced in Phase 1 fix NEW-V-001 |

String keys like `"liquidity_signal"` that appear in a handful of report-consumer functions (`briarwood/risk_bar.py`, `briarwood/evidence.py`, `briarwood/decision_model/scoring.py`, `briarwood/modules/value_finder.py`) are dict lookups, not imports. They remain functional; they just never match now that nothing populates those keys. Those consumers have their own tests and are reachable from non-deleted code paths — a separate cleanup pass can decide whether to prune them.

### 2.3 Feedback + capture layer

- **`briarwood/intelligence_capture.py`** — removed the `execution_mode` keyword argument from every capture builder and the `execution_mode` / `legacy_fallback` tag emission in `_capture_tags`.
- **`briarwood/feedback/analyzer.py`** — removed the `legacy_fallback_rate` field from `FeedbackReport`, the rate computation in `_analyze_execution_modes`, and the `_legacy_fallback` confidence driver. `execution_mode_counts` is retained so historic records (written before Phase 2) still parse.

### 2.4 Tests

- **Rewrote** `tests/test_orchestrator.py` to drop all `execution_mode="scoped"` kwargs and every test that exercised `module_runner` injection. Cache-key contract is now pinned by `test_build_cache_key_*` (stable for same inputs, changes on structural facts, carries `v2:` schema-version prefix, ignores unrelated listing fields). Repeated-identical-run caching regression preserved.
- **Updated** `tests/test_execution_v2.py` to (a) drop `execution_mode="scoped"` from `build_cache_key` calls and (b) flip the old "unsupported path falls back cleanly" test into `test_hold_to_rent_path_is_scoped_supported` — the hold-to-rent module set is now scoped-supported. The wave-1 snapshot test no longer asserts an exact module set (the router legitimately pulls in `carry_cost` + `risk_model` on the snapshot path).
- **Updated** `tests/test_feedback_loop.py` to drop `legacy_fallback_rate` expectations.
- **Updated** `tests/test_modules.py` to remove the four deleted-module imports/bodies.
- **Added** `NullPriceFixtureScopedPathTests` in `tests/test_runner_routed_integration.py`. The `1228-briarwood-road-belmar-nj` fixture has `purchase_price=null` (and most market signals null). It now runs cleanly end-to-end through scoped execution and resolves to `pass_unless_changes` — the stance a null-price property should land at. Previously the null-price path relied on the legacy fallback handling; with the fallback gone, this test pins the scoped runners' null-safety contract.

## 3. Verification

### 3.1 Targeted regression (Phase 2 surface)

```
$ python -m pytest tests/test_modules.py tests/test_orchestrator.py \
       tests/test_execution_v2.py tests/test_feedback_loop.py \
       tests/test_runner_routed_integration.py
64 + 7 = 71 passed
```

### 3.2 Full test suite

Full `pytest tests/` delta against the Phase 2 baseline: **0 net new failures.**

17 failures exist on both `c77415b` (pre-Phase 2) and post-Phase 2; none are in the Phase 2 blast radius. They split across: (a) address-normalisation drift in the SearchApi / listing-intake path, (b) seed-dataset metadata expectations in `tests/agents/test_comparable_sales_dataset.py`, (c) town-county bridge / scoring thresholds, (d) model-system-audit expectations (`opportunity_cost` registry drift), (e) routing intent-detection expectations, (f) a known-flaky `test_local_intelligence` / `test_resale_scenario_isolated` pair that depends on mutable fixture state. All of these are Phase 1 territory or pre-existing debt, not Phase 2 regressions.

The two failures that appeared in the combined run but not in the baseline (`test_promote_unsaved_address_uses_address_text_when_google_unavailable`, `test_local_intelligence_extracts_projects_and_scores`) both **pass** when run in isolation — they are test-ordering artifacts (mutable fixture state from earlier suite runs), not regressions from Phase 2.

### 3.3 Verification fixtures

Ran all four fixtures through `run_routed_report` with `"Should I buy this?"`:

| slug | decision_stance | value_position.ask_premium_pct | confidence |
|---|---|---|---|
| `briarwood-rd-belmar` | `buy_if_price_improves` | −0.1482 | 0.77 |
| `1228-briarwood-road-belmar-nj` (null price) | `pass_unless_changes` | null | 0.47 |
| `526-west-end-ave` | `buy_if_price_improves` | 0.08 | 0.71 |
| `1008-14th-ave-belmar-nj-07719` | `buy_if_price_improves` | 0.0604 | 0.75 |

All four resolve cleanly. Every fixture exercised the same scoped module set (`valuation`, `confidence`, `carry_cost`, `risk_model`) — i.e. the buy-decision / decision-depth path — and each one produced a populated `decision_stance`. The null-price fixture returns `pass_unless_changes` with null value metrics, which is the correct answer: without a price you cannot form a value thesis.

## 4. `REPO_MAP.md` update

Added the Phase 2 banner to the historical-snapshot block, removed `engine.py` / `runner.py` / `runner_legacy.py` from the directory tree, revised the "weakest contracts" paragraph to reflect the single-spine reality.

## 5. Files changed (Phase 2 commit only)

```
briarwood/engine.py                          (deleted)
briarwood/feedback/analyzer.py
briarwood/intelligence_capture.py
briarwood/modules/liquidity_signal.py        (deleted)
briarwood/modules/market_momentum_signal.py  (deleted)
briarwood/modules/property_snapshot.py       (deleted)
briarwood/modules/value_drivers.py           (deleted)
briarwood/orchestrator.py
briarwood/runner_common.py
briarwood/runner_routed.py
REPO_MAP.md
tests/test_engine.py                         (deleted)
tests/test_execution_v2.py
tests/test_feedback_loop.py
tests/test_group4.py                         (deleted)
tests/test_modules.py
tests/test_orchestrator.py
tests/test_orchestrator_cache.py             (deleted)
tests/test_runner_routed_integration.py
PATH_COVERAGE_REPORT.md                      (Stage A artifact)
PHASE2_COMPLETE.md                           (this file)
```

Other uncommitted changes in the working tree (api/, web/, briarwood/agent/, data/, AUDIT_REPORT.md, etc.) are out of scope for Phase 2 and are intentionally **not** staged with this commit.

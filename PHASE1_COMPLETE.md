# Phase 1 Remediation — Complete

**Date:** 2026-04-22
**Scope:** Six targeted fixes from `VERIFICATION_REPORT.md`. Each lands as its own commit referencing its finding ID. No refactoring beyond the specified change.

---

## Commits

| # | Finding | Commit | Subject |
| --- | --- | --- | --- |
| 1 | NEW-V-001 | [`1c21bdb`](#fix-1--execution_mode-required-in-build_cache_key) | `fix(orchestrator): require execution_mode in build_cache_key` |
| 2 | NEW-V-003 | [`00a4e5e`](#fix-2--extract-numeric-tokens-from-string-payload-fields) | `fix(guardrails): extract numeric tokens from string payload fields` |
| 3 | NEW-V-010 | [`1a96dab`](#fix-3--missing-llm-sentinel--chat-endpoint-error-event) | `fix(router): emit explicit error when LLM is unconfigured` |
| 4 | NEW-V-005 | [`56e0d53`](#fix-4--instrument-primary_value_source-bridge) | `fix(interactions): log primary_value_source bridge decisions` |
| 5 | NEW-V-007 | [`b836421`](#fix-5--soften-valuation_comps-provenance-guard) | `fix(pipeline): soften valuation_comps provenance guard` |
| 6 | NEW-V-009 | [`c77415b`](#fix-6--drop-dead-dash_app-references) | `chore(docs): remove dead Dash workspace references` |

All six land on `main` in order, on top of `b4178f1` (`refactoring post audits from Claude`).

---

## Per-fix detail

### Fix 1 — `execution_mode` required in `build_cache_key`

- **Commit:** `1c21bdb`
- **Files touched:** `briarwood/orchestrator.py`, `tests/test_orchestrator_cache.py` (new), `tests/test_orchestrator.py`, `tests/test_execution_v2.py`.
- **Change:** `build_cache_key(property_data, parser_output, *, execution_mode)` now requires a keyword-only `execution_mode`, validates it against `_VALID_EXECUTION_MODES = frozenset({"scoped", "legacy_fallback"})`, and includes the mode in the payload fingerprint. The `run_briarwood_analysis` call site propagates the actual execution mode.
- **Regression test:** `tests/test_orchestrator_cache.py` pins four contracts — different modes yield different keys, same mode + inputs is stable, missing kwarg raises `TypeError`, unknown or `None` mode raises `ValueError`. All existing call-sites were updated to pass `execution_mode="scoped"` explicitly.

### Fix 2 — Extract numeric tokens from string payload fields

- **Commit:** `00a4e5e`
- **Files touched:** `api/guardrails.py`, `tests/agent/test_guardrails.py`.
- **Change:** `_flatten_input_values`'s string branch now calls `extract_numbers(stripped)` on every string value it walks, and normalises the results into the grounded-number set the verifier checks. A new `bare_magnitude` regex (`(?<![\w.$%])(\d+(?:\.\d+)?)\s?([KkMmBb])\b`) was inserted ahead of `bare_int` so `695k` registers as `695000` rather than the literal `695`.
- **Regression tests:** `FlattenInputValuesTests` asserts `"seller cuts to 695k"` in a list surfaces `"695000"` in the grounded set; `DecisionSummaryVerifierRegressionTests` exercises the end-to-end verifier path to confirm the lead recommendation sentence is no longer stripped. Year `2024` baseline preserved (no false positive) and `"unit 3"` does not fabricate `3`.

### Fix 3 — Missing-LLM sentinel + chat endpoint error event

- **Commit:** `1a96dab`
- **Files touched:** `api/pipeline_adapter.py`, `api/main.py`, `tests/test_chat_api.py`.
- **Change:** `classify_turn` signature became `-> RouterDecision | None`. It now returns `None` when `get_llm()` returns `None` (no provider configured) instead of silently returning a `LOOKUP` decision. In the chat stream (`api/main.py`), an explicit branch emits `events.error("LLM service unavailable — check configuration (OPENAI_API_KEY / ANTHROPIC_API_KEY).")` followed by `events.done()` when the classifier returns `None` **and** the router did not raise (the raise branch is preserved because per task directive the echo fallback question was deferred). A new `classify_raised` flag distinguishes the two paths.
- **Regression tests:** `ClassifyTurnMissingLLMTests` in `tests/test_chat_api.py` pins both contracts — `classify_turn` returns `None` when `get_llm` is patched to `None`, and the chat endpoint emits `error` + `done` (no echo call) when classify returns `None`.
- **Note on location:** the task brief referenced `router.py` but the function actually lives in `api/pipeline_adapter.py` (`classify_turn` is a pipeline-adapter function, not the scoped-execution router). The fix and test were placed there accordingly.

### Fix 4 — Instrument `primary_value_source` bridge

- **Commit:** `56e0d53`
- **Files touched:** `briarwood/interactions/primary_value_source.py`, `tests/interactions/test_bridges.py`.
- **Change:** Added a module-level `_logger = logging.getLogger(__name__)` and a DEBUG log at each of the four conditional branches (strategy check, valuation mispricing check, carry offset check, scenario check) naming the branch and whether it fired. At the final `return "unknown"` path, an INFO log summarises which signals were absent. **No classification logic was changed** — each branch still fires under the same condition as before.
- **Regression test:** `test_primary_value_source_logs_unknown_path` calls `primary_value_source.run({})` against an empty `ModuleOutputs` and uses `self.assertLogs` to assert all four DEBUG branch logs fire with `fired=False` and exactly one INFO `primary_value_source.unknown` log surfaces.
- **Fixture log trace:** see below.

### Fix 5 — Soften `valuation_comps` provenance guard

- **Commit:** `b836421`
- **Files touched:** `api/pipeline_adapter.py`, `tests/test_pipeline_adapter_contracts.py`.
- **Change:** `_assert_valuation_module_comps` was replaced with `_sanitize_valuation_module_comps(payload) -> tuple[dict | None, bool]`. Bad rows (non-dict, or missing `feeds_fair_value=True`) now emit a structured `_logger.warning(...)` and are dropped; the function returns the cleaned payload (`None` if every row was dropped) plus a drift flag. All three call-sites (`_browse_stream_impl`, `_decision_stream_impl`, `_dispatch_stream_impl`) were updated to append `events.partial_data_warning("valuation_comps", "provenance_drift", verdict_reliable=True)` when drift was detected, and to skip the `valuation_comps` event only if the sanitized payload is `None`. Rejection rules are unchanged; only the failure mode is softer.
- **Regression tests:** Updated four existing tests in `ValuationCompsProvenanceTests` to assert drop-and-flag behavior instead of `AssertionError`. Added `test_guard_preserves_non_row_payload_fields` to pin that non-row keys (`address`, `town`, `state`, `summary`) survive the sanitize pass. 36 pipeline-adapter contract tests pass.

### Fix 6 — Drop dead `dash_app` references

- **Commit:** `c77415b`
- **Files touched:** deleted `briarwood/dash_app/` (pycache-only leftover), `README.md`, `REPO_MAP.md`.
- **Change:** The Dash UI source was already deleted in `b4178f1`; only a stale `__pycache__/` directory remained on disk. Removed that directory. In `README.md`, deleted the "Dash Workspace" + "Manual Subject + Comp Entry" sections (lines 506-563) which referenced non-existent `briarwood/dash_app/*.py` files and a `python -m briarwood.dash_app.app` boot command. In `REPO_MAP.md`, dropped the `dash_app/` tree entry, the `dash_app/` table row, the Dash compatibility-UI bullet under "surface layers in active code", and updated chart/table/caching inventory counts to reflect the web-only surface.
- **Grep for lingering references:** `grep -rn "dash_app\|briarwood\.dash_app\|run_dash" --include="*.py"` returns zero matches. Historical docstring/comment mentions of "Dash" in `briarwood/runner_common.py`, `briarwood/geocoder.py`, `briarwood/local_intelligence/models.py`, etc. were left in place — they are explanatory comments about past context, not live code references, so they fall outside the scope of this fix.

---

## Fix 4 log trace — saved-property fixtures

Harness (`/tmp/trace_primary_value_source.py`) loaded each fixture's `data/saved_properties/<id>/inputs.json`, ran the four scoped modules the bridge reads (`valuation`, `risk_model`, `carry_cost`, `strategy_classifier`), and invoked `run_all_bridges` with a `DEBUG`-level handler attached to `briarwood.interactions.primary_value_source`.

### `1228-briarwood-road-belmar-nj` → `current_value`
```
DEBUG primary_value_source.strategy_check fired=True strategy='owner_occ_sfh'
DEBUG primary_value_source.valuation_mispricing_check fired=False mispricing_pct=None
DEBUG primary_value_source.carry_offset_check fired=True carry_present=True ratio=9.41
DEBUG primary_value_source.scenario_check fired=False renovation_budget=None capex_basis_used=None
```

### `briarwood-rd-belmar` → `repositioning`
```
DEBUG primary_value_source.strategy_check fired=True strategy='value_add_sfh'
DEBUG primary_value_source.valuation_mispricing_check fired=False mispricing_pct=0.132
DEBUG primary_value_source.carry_offset_check fired=False carry_present=True ratio=0.584
DEBUG primary_value_source.scenario_check fired=False renovation_budget=None capex_basis_used=None
```

### `526-west-end-ave` → `current_value`
```
DEBUG primary_value_source.strategy_check fired=True strategy='owner_occ_sfh'
DEBUG primary_value_source.valuation_mispricing_check fired=False mispricing_pct=-0.08
DEBUG primary_value_source.carry_offset_check fired=False carry_present=True ratio=0.422
DEBUG primary_value_source.scenario_check fired=False renovation_budget=None capex_basis_used=None
```

### `1008-14th-ave-belmar-nj-07719` → `current_value`
```
DEBUG primary_value_source.strategy_check fired=True strategy='owner_occ_sfh'
DEBUG primary_value_source.valuation_mispricing_check fired=False mispricing_pct=-0.0604
DEBUG primary_value_source.carry_offset_check fired=False carry_present=True ratio=0.527
DEBUG primary_value_source.scenario_check fired=False renovation_budget=None capex_basis_used=None
```

**All four fixtures classify successfully.** The `"unknown"` INFO branch never fired across any of them.

---

## Surprises

### Fix 4 — `unknown` was not a bridge-logic bug

The verification report stated `primary_value_source=unknown` on every priced fixture. The fixture trace above shows **the opposite** — with the bridge actually invoked and logging added, every fixture gets classified (three `current_value`, one `repositioning`). The strategy-classifier prior alone is enough to classify each of them.

**Implication:** if production verdicts still ship with `primary_value_source=unknown`, the failure is *upstream* of the bridge — most likely either (a) the bridge isn't being registered/run in the scoped pipeline, or (b) the `module_results` shape divergence described in NEW-V-001 means the legacy-fallback path doesn't carry `strategy_classifier.data.strategy` where the bridge looks. The new INFO log at the unknown-return path will surface this the next time a real request falls through.

This finding is appended to `VERIFICATION_REPORT.md` under "Follow-up: NEW-V-005 signal trace" so the original report reads correctly alongside the trace.

### Fix 5 — the assertion was fresh code, not legacy cruft

`git blame` on [api/pipeline_adapter.py#L722-L748](api/pipeline_adapter.py#L722-L748) attributes `_assert_valuation_module_comps` to commit `b2d62337` (`feat(representation): add Representation Agent + chart registry`), authored 2026-04-22 — three days before the verification pass. The guard was added as part of the F2 contract work to enforce that `valuation_comps` only carries comps that fed fair value. The audit finding is valid (a stray row shouldn't 500 the stream) but the fix isn't removing crusty legacy code — it's softening a guard that's days old and intentionally strict. The commit message records the history (`Historically this guard raised AssertionError and aborted the stream. NEW-V-007 softened it: ...`) to preserve that context.

### WIP-reconciliation workflow

`api/guardrails.py`, `api/pipeline_adapter.py`, `tests/agent/test_guardrails.py`, and `tests/test_pipeline_adapter_contracts.py` all carried substantial pre-existing uncommitted modifications unrelated to the Phase 1 finding IDs. To keep each fix commit isolated, I stashed the WIP via `cp <file> /tmp/<file>_wip.py`, `git checkout HEAD -- <file>`, applied only the Phase-1 change, committed, then restored the WIP with `cp` and re-applied the Phase-1 change on top. Tests run both after commit and after restore to confirm both states are clean.

---

## Deferred per task directive

- **F-001 echo-stream flag** (hardcoded mock listings behind `_echo_stream`). Task explicitly deferred: the exception branch in `api/main.py` still routes to `_echo_stream`, and only the no-classification-result branch now surfaces an explicit error event. Adding an env gate or blanket echo-disable is Phase 2.
- **Scoped-vs-legacy execution path divergence (F-004 / NEW-V-001).** Orthogonal shape mismatch in `module_results` between scoped and legacy fallback. Fix 1 only guards against cross-mode cache collisions; the actual path-selection / shape-unification question is Phase 2.
- **Stance classifier thresholds (NEW-V-002).** Product decision, out of remediation scope.
- **`primary_value_source` upstream bridge wiring (NEW-V-005).** The bridge itself is now traceable, but Fix 4 does not chase why production verdicts land on `"unknown"`; the trace above indicates it's either bridge registration or the NEW-V-001 shape gap, both of which are Phase 2.

---

## Pre-existing test failure (not introduced by Phase 1)

`tests/test_orchestrator.py::OrchestratorTests::test_repeated_identical_run_reuses_cached_parser_and_synthesis` fails on `main` both with and without the Phase 1 commits applied:

```
E       AssertionError: 0 != 1
tests/test_orchestrator.py:361: AssertionError
```

Confirmed via `git stash` before the first fix touched orchestrator.py. The test expects `module_runner` to run exactly once across two identical calls (cache hit on second), and observes zero runs instead — suggesting the scoped executor short-circuits the module-runner callable entirely on the first pass. This predates Phase 1 and is logged here so Phase 2 doesn't treat it as regression introduced by `1c21bdb`.

---

## Test roll-up

```
tests/test_orchestrator_cache.py .......... (4 passed)         # Fix 1
tests/agent/test_guardrails.py ............ (all passed)        # Fix 2
tests/test_chat_api.py ...................... (2 passed)        # Fix 3
tests/interactions/test_bridges.py ......... (9 passed)         # Fix 4
tests/test_pipeline_adapter_contracts.py ... (36 passed)        # Fix 5
```

Pre-existing failure `tests/test_orchestrator.py::OrchestratorTests::test_repeated_identical_run_reuses_cached_parser_and_synthesis` unchanged from main.

---

*End of Phase 1.*

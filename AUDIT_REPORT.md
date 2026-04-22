# Briarwood Technical Audit — Same-Day Action Plan
**Date:** 2026-04-22
**Workspace:** `briarwood`
**Mode:** Read-only audit. No code changes were made.
**Supersedes:** the earlier `AUDIT_REPORT.md` (same-day, narrative format) — this version is fix-oriented.

---

## Phase 1 — Architecture Map (one page)

### Surface layers
- **FastAPI bridge** (`api/`): owns SSE wire format and conversation persistence.
  - Entry: [api/main.py:230-366](api/main.py#L230-L366) `/api/chat` → classify → `decision_stream` / `search_stream` / `browse_stream` / `dispatch_stream` / `_echo_stream` (fallback).
  - Event protocol: [api/events.py](api/events.py) (28 event types).
  - Adapter glue: [api/pipeline_adapter.py](api/pipeline_adapter.py) (~2,400 lines — projects session views into SSE events).
- **Next.js chat UI** (`web/`): consumes the SSE events. Cards in [web/src/components/chat/](web/src/components/chat/) (26 components, all actively imported).

### Reasoning core (canonical decision path)
- **Routing** [briarwood/router.py](briarwood/router.py) → typed [briarwood/routing_schema.py](briarwood/routing_schema.py) (`RoutingDecision`, `UnifiedIntelligenceOutput`).
- **Orchestrator** [briarwood/orchestrator.py](briarwood/orchestrator.py) — scoped-first with legacy fallback. Caches: `_ROUTING_DECISION_CACHE`, `_MODULE_RESULTS_CACHE`, `_SYNTHESIS_OUTPUT_CACHE`, `_SCOPED_MODULE_OUTPUT_CACHE`.
- **Scoped execution** [briarwood/execution/](briarwood/execution/): `planner.py` → `executor.py` against an `ExecutionContext`, registry in [briarwood/execution/registry.py](briarwood/execution/registry.py).
- **Module library** [briarwood/modules/](briarwood/modules/) — 44 files, mostly heuristics (no sklearn/torch).
- **Bridges** [briarwood/interactions/](briarwood/interactions/) — `run_all_bridges()` reconciles cross-module signals.
- **Unified Intelligence (synthesis)** [briarwood/synthesis/structured.py:34-117](briarwood/synthesis/structured.py#L34-L117) — *the* deterministic decision builder. Genuine fusion: trust gate, stance classifier, conflict integration, optionality signal.

### Runner glue
- [briarwood/runner_routed.py](briarwood/runner_routed.py) — canonical entry from the chat path.
- [briarwood/runner_common.py](briarwood/runner_common.py) — hosts `build_engine()` (lifted from the deleted legacy runner) which wires 19 module instances into a single `AnalysisEngine`. Used as the **legacy fallback** when scoped execution can't satisfy the routed module set.
- [briarwood/engine.py](briarwood/engine.py) — `AnalysisEngine` class. **Live**, only via the fallback above.

### LLM layer
- [briarwood/agent/llm.py](briarwood/agent/llm.py) — `OpenAIChatClient`, `AnthropicChatClient`, both with `complete()` + `complete_structured()` (strict JSON mode / Anthropic tool-use). Cost guard via `briarwood/cost_guard.py`.
- [briarwood/local_intelligence/adapters.py](briarwood/local_intelligence/adapters.py) — separate Responses-API call for town-signal extraction.
- Prompts split between [api/prompts/](api/prompts/) (markdown, ~13 files) and inline `_LLM_SYSTEM` strings inside Python modules (router, composer critic, local_intelligence/prompts.py).

### Models
The repo has **no ML stack** (no sklearn, torch, xgboost in `requirements.txt`). Every "model" in `briarwood/modules/` is a hand-tuned heuristic over property facts. The only learned components are the LLMs (router classification, prose narration, town-signal extraction).

### What was deleted on 2026-04-22 (verdict-path consolidation)
Per [REPO_MAP.md](REPO_MAP.md#L6-L12) and confirmed by direct filesystem check: `briarwood/decision_engine.py`, `briarwood/runner.py`, `briarwood/runner_legacy.py`, `briarwood/dash_app/{app,view_models,...}.py`, `briarwood/reports/{...}`, `briarwood/projections/`, `briarwood/scorecard.py`, `briarwood/deal_curve.py`, `run_dash.py`, `app.py` — **all gone**. The "competing verdict surfaces" finding from prior audits is largely **obsolete**. There is now one canonical verdict path: `synthesis/structured.py → PropertyView.load(depth="decision") → _verdict_from_view → events.verdict()`.

### Unified intelligence layer status
**It exists and is real.** [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) is a single deterministic fusion service with:
- Trust gate (`TRUST_FLOOR_ANY=0.40`, `TRUST_FLOOR_STRONG=0.70`).
- Stance classifier ([structured.py:123-227](briarwood/synthesis/structured.py#L123-L227)) that integrates `value_position`, `valuation_x_risk`, `valuation_x_town`, `scenario_x_risk`, `conflict_detector`.
- Single canonical schema (`UnifiedIntelligenceOutput`).
- Pydantic-validated SSE projector ([api/pipeline_adapter.py:570-660](api/pipeline_adapter.py#L570-L660)) with stance-vocabulary guardrail.

This is a substantial improvement over the prior audit baseline.

---

## Executive Summary (top 5)

1. **F-001 (Critical):** When the LLM router crashes, the `/api/chat` endpoint silently falls through to `_echo_stream` which serves **hardcoded mock listings** (`api/mock_listings.py`) — there is no env flag, no UI banner. Users can see fabricated demo data thinking it's live. [api/main.py:319-320](api/main.py#L319-L320), [api/mock_listings.py](api/mock_listings.py).
2. **F-002 (High):** `_assert_valuation_module_comps()` raises `AssertionError` on a single bad comp row, which aborts the SSE stream mid-flight. One stray flag and the user gets a generic error instead of a partial verdict. [api/pipeline_adapter.py:722-748](api/pipeline_adapter.py#L722-L748), error path: [api/main.py:347-350](api/main.py#L347-L350).
3. **F-003 (High):** The synthesis layer computes `optionality_signal` (hidden upside levers — F5 in the routing schema) and routes it into `value-thesis-card.tsx`, but the **verdict card never surfaces it**. The decision card drops it on the floor along with `primary_value_source` and `all_in_basis`. Real signal, invisible to user. [briarwood/synthesis/structured.py:87,116](briarwood/synthesis/structured.py#L87), [api/pipeline_adapter.py:642-643](api/pipeline_adapter.py#L642-L643), [web/src/components/chat/verdict-card.tsx:38-141](web/src/components/chat/verdict-card.tsx#L38-L141).
4. **F-004 (High):** Two execution paths still exist — scoped (preferred) and a **legacy `AnalysisEngine` fallback** in `runner_common.build_engine()` that wires 19 module instances. When scoped execution can't satisfy a routed module set, the fallback runs but its outputs reach the synthesizer through a different shape. Risk: silently divergent decisions depending on which path was taken, and 19-module construction on every fallback (no caching). [briarwood/runner_common.py:64-145](briarwood/runner_common.py#L64-L145), [briarwood/orchestrator.py:530-549](briarwood/orchestrator.py#L530-L549).
5. **F-005 (High):** `briarwood/dash_app/` directory contains **only `__pycache__`** — every source file was deleted on 2026-04-22 but the folder and its bytecode remain. The bytecode can still be importable on a fresh checkout that re-syncs the cache. Delete the directory.

---

## Findings

### F-001 — Mock listings served on router failure with no warning
- **Severity:** Critical
- **Category:** Pipeline / UI
- **Location:** [api/main.py:293-336](api/main.py#L293-L336), [api/mock_listings.py](api/mock_listings.py)
- **Evidence:**
  ```python
  try:
      decision = classify_turn(last.content)
  except Exception as exc:
      decision = None
      yield events.encode_sse(events.error(...))
  ...
  if decision is None:
      stream = _echo_stream(last.content, pinned_listing)  # ← serves mock listings
  ```
  `_echo_stream` calls `mock_listings_for(text)` which returns hardcoded BELMAR/AVON/ASBURY arrays from `api/mock_listings.py`. There is no env gate.
- **Impact:** During any provider outage, OPENAI_API_KEY misconfiguration, or rate-limit episode, users see fictional listings indistinguishable from real ones. Especially dangerous for the prototype demo.
- **Same-Day Fix:**
  1. Gate `_echo_stream` behind `BRIARWOOD_DEMO_MODE=true` env. If the flag isn't set, return a clear error event ("router unavailable, please retry") and `done()`.
  2. If the flag IS set, prepend a `partial_data_warning(section="echo_fallback", reason="demo_mode", verdict_reliable=False)` event so the UI banners these as demo content. Effort: ~30 min.

### F-002 — Single bad comp row aborts the SSE stream
- **Severity:** High
- **Category:** Pipeline
- **Location:** [api/pipeline_adapter.py:722-748](api/pipeline_adapter.py#L722-L748)
- **Evidence:**
  ```python
  def _assert_valuation_module_comps(payload):
      for index, row in enumerate(payload.get("rows") or []):
          if row.get("feeds_fair_value") is not True:
              raise AssertionError(...)
  ```
  Boundary handler in [api/main.py:347-350](api/main.py#L347-L350) catches the exception and emits a generic `error` event, terminating the stream **before** `verdict`/`scenario_table` etc. have flushed.
- **Impact:** The user gets a cryptic error and loses the rest of the decision response (verdict card, risk profile, narrative). The contract guard is correct in spirit but its enforcement mode is wrong.
- **Same-Day Fix:** Replace `raise AssertionError` with a logger.warning + drop the offending row + emit `partial_data_warning(section="valuation_comps", reason="provenance_drift", verdict_reliable=True)`. Keep streaming. Effort: ~30 min. (Add a regression test in `tests/test_pipeline_adapter_contracts.py`.)

### F-003 — Verdict card silently drops three computed fields
- **Severity:** High
- **Category:** UI / Pipeline
- **Location:**
  - Computed: [briarwood/synthesis/structured.py:87,102,116](briarwood/synthesis/structured.py#L87) (`optionality_signal`, `primary_value_source` in `supporting_facts`).
  - Projected to wire: [api/pipeline_adapter.py:642-660](api/pipeline_adapter.py#L642-L660) (`primary_value_source`, `all_in_basis` are in the verdict event payload).
  - Dropped by UI: [web/src/components/chat/verdict-card.tsx:38-141](web/src/components/chat/verdict-card.tsx#L38-L141) — never read.
  - Wire schema for `optionality_signal` lives on `value_thesis`, not `verdict` ([web/src/lib/chat/events.ts:313](web/src/lib/chat/events.ts#L313)).
- **Impact:** "Hidden upside" is one of the six foundational questions per the prior audit's question matrix and is the F5 line item. It's computed and surfaced into the value-thesis card but the decision card the user reads first never references it. Same for `primary_value_source` (Comps? Hybrid? Income?) — answers a question users routinely ask in the chat.
- **Same-Day Fix:**
  1. Add `primary_value_source` as a one-line subtitle under "Decision" in `verdict-card.tsx` ("Anchored on: comps").
  2. Render `all_in_basis` as a 5th `Stat` cell when it differs from `ask_price` by ≥0.5%.
  3. Add a `optionality_signal` event/projection on the verdict (or render it as a "Hidden upside" pill row). Effort: ~2 hr.

### F-004 — Legacy `AnalysisEngine` fallback path still runs
- **Severity:** High
- **Category:** Unified Layer
- **Location:** [briarwood/runner_common.py:14,64-145](briarwood/runner_common.py#L64), called by [briarwood/orchestrator.py:530-549](briarwood/orchestrator.py#L530-L549) when `supports_scoped_execution()` is False, and by [briarwood/runner_routed.py](briarwood/runner_routed.py).
- **Evidence:** `build_engine()` constructs `AnalysisEngine` with **19 module instances** wired with cross-module dependencies. None of these modules go through the scoped registry; they run via the older `AnalysisModule.run()` interface, then their results are normalized by `_normalize_module_results()` ([briarwood/orchestrator.py:345-357](briarwood/orchestrator.py#L345-L357)) before reaching the same synthesizer.
- **Impact:**
  - Two divergent execution shapes — same property can yield different module result keys depending on whether scoped execution covers all routed modules. Synthesis silently treats them differently because key lookups won't match.
  - `build_engine()` is invoked **on every fallback** with no caching of the engine instance; module init does heavy fixture loading (`build_default_town_county_service`, `MarketValueHistoryModule`).
  - The 19 modules in `build_engine()` include legacy variants (`HybridValueModule`, `BullBaseBearModule`, `RenovationScenarioModule`, `TeardownScenarioModule`, `RentalEaseModule`, `LiquiditySignalModule`, `MarketMomentumSignalModule`, `LocationIntelligenceModule`, `ValueDriversModule`) whose names don't match the scoped-registry module names — so the synthesis cache key collides between scoped and fallback runs (both produce the same `analysis_cache_key` for the same property+parser).
- **Same-Day Fix (read-only triage today, code change later):**
  1. **Today:** Add a one-line log + counter at [briarwood/orchestrator.py:548](briarwood/orchestrator.py#L548) when `execution_mode == "legacy_fallback"` so we can quantify how often it actually fires in the prototype. If the count is zero in a normal session, we can rip it out.
  2. **Today:** Bake `execution_mode` into the analysis cache key (`build_cache_key` in [briarwood/orchestrator.py:171-202](briarwood/orchestrator.py#L171-L202)) so scoped + fallback never share an entry. Effort: ~20 min.
  3. **Deferred:** if the fallback log shows zero hits, delete `runner_common.build_engine()`, `engine.py`, and the 9 unscoped modules.

### F-005 — Dead `briarwood/dash_app/` directory (only `__pycache__` left)
- **Severity:** High (cleanliness, low risk in itself but confusing)
- **Category:** Dead Code
- **Location:** [briarwood/dash_app/](briarwood/dash_app/)
- **Evidence:**
  ```text
  drwxr-xr-x  3 zachanderson  staff   96 Apr 22 08:30 .
  drwxr-xr-x  7 zachanderson  staff  224 Apr 22 08:30 __pycache__
  ```
  All `.py` source files were deleted in the 2026-04-22 consolidation, but the folder remains. README.md, REPO_MAP.md, and CLAUDE.md still reference Dash modules in detail.
- **Impact:** A teammate cloning fresh and running `python -m briarwood.dash_app.app` will trip on stale `.pyc` files; the README's lengthy Dash section misleads new contributors.
- **Same-Day Fix:** `rm -rf briarwood/dash_app/`; delete the Dash sections in [README.md:506-563](README.md#L506) and the Dash row from [REPO_MAP.md](REPO_MAP.md). Effort: ~15 min.

### F-006 — Inline LLM system prompts scattered across modules
- **Severity:** Medium
- **Category:** LLM
- **Location:**
  - Router classifier prompt: [briarwood/agent/router.py](briarwood/agent/router.py) (search `_LLM_SYSTEM`)
  - Composer critic prompt: [briarwood/agent/composer.py](briarwood/agent/composer.py) (search `_CRITIC_SYSTEM`)
  - Local-intelligence extraction: [briarwood/local_intelligence/prompts.py](briarwood/local_intelligence/prompts.py)
- **Evidence:** `api/prompts/` holds 13 markdown prompts (decision_summary, lookup, projection, risk, etc.) but the router and critic prompts live as Python string literals — different lifecycle, no version field, can't A/B without code-deploy.
- **Impact:** Rolling back a bad prompt or running an A/B requires a Python edit + restart. Inconsistent ownership: prose surfaces are versioned, structured surfaces aren't.
- **Same-Day Fix:** Move `_LLM_SYSTEM` (router) and `_CRITIC_SYSTEM` (composer) to `api/prompts/router_classifier.md` and `api/prompts/decision_critic.md`; load via `briarwood.agent.composer.load_prompt`. Effort: ~1.5 hr.

### F-007 — `default_client()` silently downgrades from Anthropic to OpenAI
- **Severity:** Medium
- **Category:** LLM
- **Location:** [briarwood/agent/llm.py:350-370](briarwood/agent/llm.py#L350-L370)
- **Evidence:**
  ```python
  if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
      try:
          return AnthropicChatClient()
      except Exception as exc:
          _logger.warning("Anthropic client init failed, falling back to OpenAI: %s", exc)
  ...
  ```
  The warning logs but no surface signal to the operator.
- **Impact:** A misconfigured Anthropic key, transient SDK import error, or version mismatch silently routes everything through OpenAI — costs land on the wrong provider, A/B comparisons are invalidated.
- **Same-Day Fix:** When `BRIARWOOD_AGENT_PROVIDER=anthropic` is explicit, treat init failure as fatal (raise) instead of falling through. If provider is unset, current behavior is fine. Effort: ~20 min.

### F-008 — gpt-5 (or larger) accepted as router classifier with no ceiling warning
- **Severity:** Medium
- **Category:** LLM
- **Location:** [briarwood/agent/llm.py:144-148](briarwood/agent/llm.py#L144-L148)
- **Evidence:**
  ```python
  # AUDIT F12: ... gpt-5 is over-tiered for it. Default to the cheapest
  # structured-capable OpenAI tier. Env override preserves the prior default.
  use_model = model or os.environ.get("BRIARWOOD_STRUCTURED_MODEL", "gpt-4o-mini")
  ```
  The comment acknowledges the cost issue but the env override accepts any model with no warning.
- **Impact:** A stray env var produces a 50–100× per-call cost regression for a 2-field schema with no telemetry signal.
- **Same-Day Fix:** Add `if use_model.startswith("gpt-5"): _logger.warning("classifier called with %s — over-tiered for 2-field schema", use_model)`. Effort: ~5 min.

### F-009 — Numeric verifier regex doesn't normalize `%`
- **Severity:** Medium
- **Category:** LLM
- **Location:** [briarwood/agent/composer.py](briarwood/agent/composer.py) — search `_NUMERIC_TOKEN_RE`
- **Evidence:**
  ```python
  _NUMERIC_TOKEN_RE = re.compile(r"[$]?\d[\d,]*(?:\.\d+)?%?")
  def _numeric_tokens(text):
      ...
      normalized = match.replace("$", "").replace(",", "")  # ← no .rstrip("%")
  ```
- **Impact:** The grounding verifier's preservation check would treat `"82.5%"` and `"82.5"` as different tokens, but `"82.5%"` and `"825"` (10× misprint) as different too — so it catches some drift but a hallucinated percentage that drops the dot can still pass. Verifier is advisory now ("Strict mode behind BRIARWOOD_STRICT_REGEN") but the same regex feeds the gate.
- **Same-Day Fix:** Add `.rstrip("%")` after the comma/dollar strip. Effort: ~5 min + test.

### F-010 — `market_support_comps` has no source provenance flag in payload
- **Severity:** Medium
- **Category:** Pipeline / UI
- **Location:** [briarwood/agent/tools.py](briarwood/agent/tools.py) — `get_cma()` and `_live_zillow_cma_candidates`/`_fallback_saved_cma_candidates` (~lines 1802-1963).
- **Evidence:** The event factory at [api/events.py:198-206](api/events.py#L198-L206) hardcodes `"source": "live_market"`, but the underlying data source can transparently fall back from live Zillow to saved comps when SearchAPI is unconfigured. The payload doesn't distinguish.
- **Impact:** UI claims "Live market context" while showing cached saved-comp fallbacks. Provenance promise leaks.
- **Same-Day Fix:** Have `get_cma()` return both rows + a `comps_source` literal (`"live_zillow"` | `"saved_fallback"`); plumb to the event payload; UI footnote. Effort: ~1 hr.

### F-011 — Router retries have no backoff or jitter
- **Severity:** Medium
- **Category:** LLM
- **Location:** [briarwood/agent/router.py](briarwood/agent/router.py) — the `for attempt in (1, 2):` block (~lines 210-225)
- **Evidence:** Two immediate retries with no `time.sleep`. On a provider 5xx burst, every concurrent request retries in lockstep.
- **Impact:** Amplifies provider transient errors instead of damping them. Low blast radius today (prototype, low concurrency) but easy fix.
- **Same-Day Fix:** Add `time.sleep(min(0.25 * (2 ** (attempt - 1)) + random.random() * 0.1, 1.5))` on retry. Effort: ~15 min.

### F-012 — README + REPO_MAP describe deleted modules
- **Severity:** Medium (docs)
- **Category:** Dead Code (docs)
- **Location:** [README.md](README.md) (sections "Project Shape", "Run", "Dash Workspace"), [REPO_MAP.md](REPO_MAP.md) (lines 6-12 disclaimer is correct, but the directory tree at lines 18-160 still lists `briarwood/dash_app/`, `briarwood/decision_engine.py`, `app.py`, `run_dash.py`, `briarwood/runner.py`, `briarwood/runner_legacy.py` without flagging them deleted in the table itself).
- **Impact:** Onboarding confusion. Search-by-doc lands on phantom files.
- **Same-Day Fix:** Strip deleted module references from README "Project Shape" and "Run"; update REPO_MAP "Major Directory Summary" table to drop the Dash row. Effort: ~30 min.

### F-013 — Multiple stale audit reports at repo root
- **Severity:** Low
- **Category:** Dead Code (docs)
- **Location:** Root: `AUDIT_REPORT.md` (this file, just rewritten), `AUDIT_REPORT_2.0.md`, `BRIARWOOD-AUDIT.md`, `STATE_OF_1.0.md`, `UX-ASSESSMENT.md`, `unified_intelligence.md`, `analysis/00..05*.md`.
- **Impact:** The last commit message references "refactoring post audits from Claude". Several of these audits cite modules that no longer exist (e.g., `briarwood/decision_engine.py`, `briarwood/pipeline/runner.py`). Future readers will load wrong context.
- **Same-Day Fix:** Move all but the live `AUDIT_REPORT.md` and `unified_intelligence.md` to `analysis/archive/<date>/`. Effort: ~15 min.

### F-014 — Verdict event projection uses `extra="ignore"` without drift logging
- **Severity:** Low
- **Category:** Unified Layer
- **Location:** [api/pipeline_adapter.py:584](api/pipeline_adapter.py#L584) (`model_config = ConfigDict(extra="ignore")`)
- **Evidence:** Comment at lines 580-582 acknowledges this is intentional for replay safety, but unknown-field drift on the *write* side has no observation. If `dispatch._decision_view_to_dict` adds a field, the projector silently swallows it.
- **Impact:** Schema drift between writer (dispatch) and reader (projector) goes undetected until someone reads the projector code. F-003 is the live example.
- **Same-Day Fix:** When `extra="ignore"` triggers, log the dropped keys at DEBUG. Better: add a periodic test that dumps `_DecisionView.model_fields` and compares to the writer's `_decision_view_to_dict` keys. Effort: ~30 min.

### F-015 — 13 modules in `briarwood/modules/` lack inbound references
- **Severity:** Low (verification needed)
- **Category:** Dead Code
- **Location:** [briarwood/modules/](briarwood/modules/) (44 files; registry at [briarwood/execution/registry.py](briarwood/execution/registry.py) wires ~17; `runner_common.build_engine` adds ~19 more for fallback; some overlap).
- **Impact:** Could be 10-13 truly dead files or could be wired indirectly via the agent layer. Phase 5 agent flagged but did not enumerate.
- **Same-Day Fix:** Run `python -c "import briarwood.modules.X"` for each file then `grep -rn "briarwood.modules.X" briarwood/ api/ tests/` — anything with zero non-self matches is dead. Effort: ~45 min, ship the deletes.

---

## Working Well (brief)

- **Unified intelligence is real.** [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) is a single deterministic fusion service with a trust gate, stance classifier, and conflict integration. Not a pass-through.
- **Cache-key correctness fixed.** The previously flagged staleness bug is closed: [briarwood/orchestrator.py:43-63,186-202](briarwood/orchestrator.py#L43-L63) now hashes structural property facts AND assumptions into the analysis cache key.
- **Verdict-card drift gate is in place.** [api/pipeline_adapter.py:570-604](api/pipeline_adapter.py#L570-L604) validates through a Pydantic `_DecisionView` and rejects unknown stance vocab.
- **CMA provenance split exists.** Two distinct events (`valuation_comps` for fed-fair-value rows; `market_support_comps` for live-market context) — even with F-002 and F-010 caveats, the architectural split is correct.
- **Cost guard wraps both providers.** [briarwood/cost_guard.py](briarwood/cost_guard.py) is called from both `OpenAIChatClient` and `AnthropicChatClient` for every call.
- **Frontend has zero dead components.** All 26 cards in [web/src/components/chat/](web/src/components/chat/) have at least one importer.
- **Loading/empty states exist.** Lazy maps render `<MapSkeleton/>` not perpetual spinners; chat-view renders `error` state inline.

---

## Today's Action Plan (sequenced, impact-per-hour)

> **Quick wins first.** Each line: estimated effort → finding IDs.

1. **Gate echo/mock fallback behind `BRIARWOOD_DEMO_MODE`** — 30 min — F-001.
2. **Stop SSE crash on stray comp row** (assert → log+drop+warn) — 30 min — F-002.
3. **Delete `briarwood/dash_app/`** + scrub README/REPO_MAP — 30 min — F-005, partial F-012.
4. **Add `execution_mode` to `build_cache_key`** + log fallback hits — 20 min — F-004 (instrumentation step only).
5. **Add `primary_value_source` + `all_in_basis` to verdict card** — 45 min — F-003 (partial — optionality_signal full surface deferred).
6. **Anthropic init failure → raise when explicit** — 20 min — F-007.
7. **gpt-5 classifier warning** — 5 min — F-008.
8. **Numeric regex `%` strip** + add unit test — 20 min — F-009.
9. **Router retry backoff+jitter** — 15 min — F-011.
10. **Move stale audits to `analysis/archive/`** — 15 min — F-013.
11. **Sweep 13 unreferenced modules**, delete the truly dead — 45 min — F-015.
12. **`extra="ignore"` drift logging** — 30 min — F-014.

**Total today (single engineer): ~5h 25m.**

The four highest-impact fixes (#1, #2, #3 partial, #4 instrumentation) take **~2h** and would meaningfully reduce user-visible risk before close of business.

---

## Deferred Items

- **F-003 full surface (optionality_signal in verdict card):** ~3h, requires a UI design pass on hidden-upside vs key-risks pill grouping.
- **F-004 fallback removal:** depends on F-004 instrumentation results from today; if the fallback log shows zero hits over a few sessions, schedule a delete-PR (1 day to delete, scope test).
- **F-006 prompt centralization:** ~3h, plus governance decision on prompt versioning convention.
- **F-010 CMA provenance plumb:** ~1h backend + ~30 min UI footnote — bundle as a small PR.
- **Portfolio-aware capital allocation** (carried over from prior audit's #5 foundational question): the routed contracts still carry no portfolio state, and `opportunity_cost` only compares to passive benchmarks. Multi-day scope; product decision required first.
- **Hidden-upside as a routed first-class question:** `CoreQuestion.HIDDEN_UPSIDE` enum exists but is not in any default intent or focus mapping ([briarwood/routing_schema.py](briarwood/routing_schema.py)). 1-day scope.

---

*End of audit.*

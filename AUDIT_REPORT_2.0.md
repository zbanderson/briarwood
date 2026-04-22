# Briarwood Intelligence — Audit Report 2.0
Date: 2026-04-22
Workspace: briarwood
Supersedes: AUDIT_REPORT.md (2026-04-19)

## Executive Summary

Since the 2026-04-19 audit, three consolidation commits landed that address the majority of the 12 findings:

- `43b8316` — Consolidate verdict path (stage 1 of 2): deprecate legacy engine, add projector. Deleted `briarwood/pipeline/{runner,unified,decision,feedback,scenario_adapter}.py`. Added `briarwood/projections/legacy_verdict.py`.
- `b2d6233` — Add Representation Agent + chart registry (`briarwood/representation/{agent.py,charts.py}`); chart emission in `api/pipeline_adapter.decision_stream` now routes through the agent.
- `688c592` — F5/F7/F10: hidden upside is first-class, partial-data warnings are explicit, verdict trust details are preserved end-to-end to the UI.

**Scorecard**: 8 of 12 findings fully resolved, 3 partially resolved, 1 not addressed. Five new findings surfaced from the three consolidation commits, concentrated in the Representation Agent and the stage-1-only verdict consolidation.

**What got materially better**: The routed verdict path is now the canonical source at the SSE layer (F1 stage 1, F11). Cache keys now include a 17-field property-fact fingerprint with a schema version prefix (F3). CMA provenance is split into `valuation_comps` vs `market_support_comps` (F2). Hidden upside is a first-class routed output with `OptionalitySignal`/`HiddenUpsideItem` types (F5). Partial-data degradation is surfaced via `_record_partial()` + `partial_data_warning` SSE events (F7). Two routers are bridged by a shared `IntentContract` (F9). Frontend renders the full verdict including `trust_summary`, `why_this_stance`, `what_changes_my_view`, `contradiction_count`, `blocked_thesis_warnings` (F10). Router model down-tiered from `gpt-5` to `gpt-4o-mini` (F12). Docs reconciled with the scoped registry (F8). `briarwood/synthesis/structured.py:34-117`, `briarwood/orchestrator.py:43-202`, `api/events.py:186-205`, `briarwood/routing_schema.py:37,264-276,356-392`, `briarwood/agent/dispatch.py:1413-1470`, `briarwood/intent_contract.py:1-120`, `web/src/components/chat/verdict-card.tsx:127-149`, `briarwood/agent/llm.py:144-148`, `docs/scoped_execution_support.md:19-39`.

**What still stands**: Stage 2 of verdict consolidation (F1) is incomplete — `briarwood/dash_app/quick_decision.py:5,36`, `briarwood/dash_app/view_models.py:15,3063`, `briarwood/reports/sections/thesis_section.py:3,9`, and `briarwood/reports/sections/conclusion_section.py:3,14` still call `decision_engine.build_decision()` directly rather than projecting through `briarwood/projections/legacy_verdict.py`. Portfolio-aware allocation (F4) is untouched — `ExecutionContext` carries no portfolio/holdings and `opportunity_cost` remains passive-benchmark-only. Decision summary prose (F6) still drops `key_risks`, `why_this_stance`, `what_changes_my_view`, `contradiction_count`, `blocked_thesis_warnings` from the LLM prompt input even though all fields are now computed, projected, and rendered on the verdict card. `briarwood/execution/context.py:20-31`, `briarwood/modules/opportunity_cost.py:38-47`, `briarwood/agent/dispatch.py:1618-1630`.

**What got worse (new risks)**: The Representation Agent introduces a new LLM call site with no retry logic (NF4), silent-dropped chart selections when flagged (NF1), an undeclared `session.last_representation_plan` slot that does not persist across session reloads (NF3), an unmapped `HIDDEN_UPSIDE` claim type (NF2), and unvalidated chart-advice patching (NF5). These are the predictable category of risk that comes with adding a new LLM-backed decision surface without copying the verifier/critic/retry pattern already present in the narrative composer. `briarwood/representation/agent.py:221-250,490-530`, `api/pipeline_adapter.py:1280-1297`, `briarwood/agent/session.py:26-59`.

## Phase 1 Verification — Original Findings

### 1.1 Status Roll-Up

| ID | Severity | Title | Status |
| --- | --- | --- | --- |
| F1 | P0 | Multiple Verdict Paths | **Partially resolved** (stage 1 of 2 complete) |
| F2 | P0 | CMA Provenance Mismatch | **Resolved** |
| F3 | P0 | Stale Routed Cache Key | **Resolved** |
| F4 | P1 | No Portfolio-Aware Allocation Logic | **Not addressed** |
| F5 | P1 | Hidden Upside Is Not First-Class Routed Logic | **Resolved** |
| F6 | P1 | Summary Prose Only Partially Coupled To Deterministic Verdict | **Partially resolved** (no change) |
| F7 | P1 | Silent Partial Degradation In Decision Enrichment | **Resolved** |
| F8 | P1 | Docs Contradict Scoped Registry Reality | **Resolved** |
| F9 | P1 | Two Routers Govern One User Flow | **Resolved** |
| F10 | P2 | Frontend Drops Part Of Backend Meaning | **Resolved** |
| F11 | P2 | Parallel Pipeline Architecture Still Lives Beside Routed Core | **Partially resolved** (dead pipeline gone; legacy surfaces via F1 stage 2) |
| F12 | P2 | Router Classification Default Model Is Over-Tiered | **Resolved** |

### 1.2 Finding-by-Finding Verification

#### F1 — Multiple Verdict Paths — **Partially Resolved**

**Original**: Routed chat/API used `build_unified_output()`; Dash/reports used `decision_engine.build_decision(report)`; old pipeline kept a third surface.

**What was done**:
- `briarwood/synthesis/structured.py:34-117` confirmed as the single deterministic verdict entry point.
- `briarwood/decision_engine.py:1-12` now carries a `DEPRECATED` top-of-file notice; scheduled for deletion once consumer migration finishes.
- `briarwood/projections/legacy_verdict.py:1-168` created. `project_to_legacy()` maps the seven `DecisionStance` values to the five legacy labels (`BUY / LEAN BUY / NEUTRAL / LEAN PASS / AVOID`) with an `is_trust_gate_fallback` flag preserving the `CONDITIONAL` vs `INTERESTING_BUT_FRAGILE` distinction.
- `api/pipeline_adapter.py:592-605` — `_stance_must_be_known()` validator rejects legacy labels at the verdict emit boundary.
- The old pipeline verdict files (`briarwood/pipeline/{runner,unified,decision,feedback,scenario_adapter}.py`) were deleted in commit `43b8316`.

**Residual gap (stage 2)**: Four legacy surfaces still call `build_decision()` directly instead of projecting from the routed output:
- `briarwood/dash_app/quick_decision.py:5` imports; line 36 calls.
- `briarwood/dash_app/view_models.py:15` imports; line 3063 calls.
- `briarwood/reports/sections/thesis_section.py:3` imports; line 9 calls.
- `briarwood/reports/sections/conclusion_section.py:3` imports; line 14 calls.

The projector is ready and tested; the remaining work is adapter integration. Until it ships, Dash/report surfaces can still disagree with the chat verdict for the same property. This remains **P0** for trustworthy lineage.

**Evidence**: `briarwood/synthesis/structured.py:34-117`, `briarwood/decision_engine.py:1-12`, `briarwood/projections/legacy_verdict.py:51-168`, `api/pipeline_adapter.py:592-605`, `STATE_OF_1.0.md:62-101`, `tests/projections/test_legacy_verdict.py`.

#### F2 — CMA Provenance Mismatch — **Resolved**

**Original**: `api/events.cma_table()` implied comps that fed fair value; `get_cma()` actually preferred live market comps.

**What was done**:
- `api/events.py:186-194` — new `valuation_comps()` event (`EVENT_VALUATION_COMPS`, `source: "valuation_module"`) sourced from `comparable_sales.comps_used`.
- `api/events.py:197-205` — new `market_support_comps()` event (`EVENT_MARKET_SUPPORT_COMPS`, `source: "live_market"`) sourced from `get_cma()`.
- `briarwood/agent/tools.py:1802-1803` — `get_cma()` docstring updated to explicitly state "prefers live market support before saved comps."
- `briarwood/agent/dispatch.py:1445-1448` — `_build_market_support_view` is a separate enrichment path, failing over to `_record_partial("market_support_comps", exc)` on error.

**Evidence**: `api/events.py:186-205`, `briarwood/agent/tools.py:1802-1803`, `briarwood/agent/dispatch.py:1445-1448`.

#### F3 — Stale Routed Cache Key — **Resolved**

**Original**: `_SYNTHESIS_OUTPUT_CACHE` and `_MODULE_RESULTS_CACHE` keyed by `property_id` + narrow assumptions, omitting material facts (beds/baths/sqft/taxes).

**What was done**:
- `briarwood/orchestrator.py:43-63` — `_CACHE_KEY_PROPERTY_FACTS` tuple lists 17 structural fields (property_type, beds, baths, sqft, lot_size, year_built, purchase_price, taxes, monthly_hoa, has_back_house, adu_type, adu_sqft, has_additional_units, condition_profile, capex_lane, strategy_intent, hold_period_years, risk_tolerance, days_on_market).
- `briarwood/orchestrator.py:146-169` — `_normalize_fact_fingerprint()` coerces types for stable comparison (so `3` and `3.0` collide; missing fields normalize to `None`).
- `briarwood/orchestrator.py:171-202` — `build_cache_key()` hashes `{property_id, assumptions, property_facts}` under a SHA1 digest prefixed with `_CACHE_KEY_VERSION = "v2"` so a future schema bump mass-invalidates every entry.
- `tests/test_orchestrator.py:68-133` — three dedicated tests prove that changing any of 9 structural facts flips the key, and that unrelated fields (listing_description, source_url) do not.

**Residual gap**: The caches remain process-global mutable dicts; no TTL, no lock, no eviction. Inference reuse across requests remains correct, but multi-worker or long-lived processes still grow these caches without bound. Not raised as P0 because it is a memory-growth concern, not a correctness concern.

**Evidence**: `briarwood/orchestrator.py:29-63,146-202,513-588`, `tests/test_orchestrator.py:68-133`.

#### F4 — No Portfolio-Aware Allocation Logic — **Not Addressed**

**Original**: `ExecutionContext` had no portfolio state; `opportunity_cost` compared only to T-bills and S&P 500.

**What was done**: Nothing.

**Current state**:
- `briarwood/execution/context.py:20-31` — `ExecutionContext` fields unchanged: `property_id, property_data, property_summary, parser_output, assumptions, prior_outputs, market_context, comp_context, macro_context, field_provenance, missing_data_registry, normalized_context`. No `portfolio`, `holdings`, or `opportunity_set` field.
- `briarwood/modules/opportunity_cost.py:38-47` — `run_opportunity_cost()` takes only `(context, settings)`; still passive-benchmark-only at lines 120-172.
- `briarwood/execution/registry.py:160-169` — `opportunity_cost` dependencies remain `["valuation", "resale_scenario"]`; no portfolio dependency.

**Remains P1**. The product promise of "allocate capital versus other opportunities" is still not implementable from the routed contracts.

**Evidence**: `briarwood/execution/context.py:20-31`, `briarwood/modules/opportunity_cost.py:38-47,120-172`, `briarwood/execution/registry.py:160-169`.

#### F5 — Hidden Upside Is Not First-Class Routed Logic — **Resolved**

**Original**: `CoreQuestion.HIDDEN_UPSIDE` in the enum but not in `QUESTION_FOCUS_TO_MODULE_HINTS` or `INTENT_TO_QUESTIONS`.

**What was done**:
- `briarwood/routing_schema.py:37` — enum preserved; `:134-135,:140` — now mapped to `IntentType.RENOVATE_THEN_SELL` and `IntentType.HOUSE_HACK_MULTI_UNIT`; `:264-276` — now in `QUESTION_FOCUS_TO_MODULE_HINTS` with modules `VALUATION, RENOVATION_IMPACT, ARV_MODEL, UNIT_INCOME_OFFSET, RESALE_SCENARIO`.
- `briarwood/routing_schema.py:356-374` — new `HiddenUpsideItem` type with `kind, source_module, label, magnitude_usd, magnitude_pct, confidence, rationale`.
- `briarwood/routing_schema.py:377-392` — new `OptionalitySignal` type hanging off `UnifiedIntelligenceOutput` with `primary_source` + `hidden_upside_items`.
- `briarwood/synthesis/structured.py:357-451` — `_optionality_signal()` reads `renovation_impact`, `arv_model`, `unit_income_offset` and emits typed items with module provenance.
- `web/src/lib/chat/events.ts` + `web/src/components/chat/value-thesis-card.tsx` — `optionality_signal` carried on `value_thesis` SSE event; `HiddenUpsideBlock` UI component renders it.
- Tests: `OptionalitySignalTests`, router hidden-upside focus tests.

**Evidence**: `briarwood/routing_schema.py:37,134-135,140,264-276,356-392,433`, `briarwood/synthesis/structured.py:357-451`, `tests/synthesis/test_structured_synthesizer.py`, `tests/test_router.py`.

#### F6 — Summary Prose Only Partially Coupled To Deterministic Verdict — **Partially Resolved (no change this week)**

**Original**: `decision_summary` prompt omitted `key_risks`, `why_this_stance`, `what_changes_my_view`, `contradiction_count`, `blocked_thesis_warnings`.

**Current state**: `briarwood/agent/dispatch.py:1618-1630` — `summary_inputs` dict still contains only `overrides_applied, decision_stance, primary_value_source, ask_price, all_in_basis, fair_value_base, basis_premium_pct, ask_premium_pct, trust_flags, what_must_be_true, research_update`. The five formerly-omitted fields are still not passed to the decision_summary prompt.

This is notable because the adjacent projector at `dispatch.py:373-377` *does* include all five fields on the decision view, and the verdict card on the UI *does* render them now (per F10). The LLM prompt is the one remaining surface where they are dropped.

**Remains P1**. The prose can still remain numerically correct while under-explaining what would change the call.

**Evidence**: `briarwood/agent/dispatch.py:1618-1630` (prompt input) vs `briarwood/agent/dispatch.py:373-377` (projector) vs `web/src/components/chat/verdict-card.tsx:127-149` (UI render). The divergence is the LLM surface specifically.

#### F7 — Silent Partial Degradation In Decision Enrichment — **Resolved**

**Original**: `handle_decision()` silently swallowed exceptions for town summary, CMA, comps preview, value thesis, and scenario enrichments; session loader silently reset corrupt files.

**What was done**:
- `briarwood/agent/dispatch.py:1413-1418` — new `_record_partial(section, exc)` helper logs and appends to `session.last_partial_data_warnings`.
- `briarwood/agent/dispatch.py:1420-1470` — all six enrichments (town summary, CMA, comps preview, value thesis, market_support_comps, projection) now call `_record_partial` in their except branches instead of silently passing.
- `briarwood/agent/session.py:55-58` — new `last_partial_data_warnings: list[dict[str, object]]` field with structure `{section, reason, verdict_reliable}`; cleared per-turn at `:86`; rehydrated at `:133`.
- `api/events.py` — new `EVENT_PARTIAL_DATA_WARNING`; `api/pipeline_adapter.py:1998-2000` emits it before primary cards when warnings exist; `web/src/components/chat/messages.tsx` renders a subtle reliability-toned banner.
- Tests: `DecisionPartialDataWarningTests`.

**Evidence**: `briarwood/agent/dispatch.py:1413-1470`, `briarwood/agent/session.py:55-58,86,133`, `api/events.py` (EVENT_PARTIAL_DATA_WARNING), `api/pipeline_adapter.py:1998-2000`.

#### F8 — Docs Contradict Scoped Registry Reality — **Resolved**

**Original**: `docs/scoped_execution_support.md` said `resale_scenario, rental_option, renovation_impact, arv_model, margin_sensitivity` were unsupported; registry wired concrete runners for all five.

**What was done**:
- `docs/scoped_execution_support.md:19-32` — now correctly enumerates all 15 scoped modules.
- Line 38-39: "With the full module set now registered, every routed intent/depth combination runs through the scoped executor by default."
- Registry still wires all five (cross-check: `briarwood/execution/registry.py:88-141`). Docs now match reality.

**Evidence**: `docs/scoped_execution_support.md:19-39`, `briarwood/execution/registry.py:88-141`.

#### F9 — Two Routers Govern One User Flow — **Resolved**

**Original**: `briarwood/agent/router.py` (chat-tier) and `briarwood/router.py` (analysis) were separate with no translation contract.

**What was done**:
- `briarwood/intent_contract.py` — new module defining a shared `IntentContract` Pydantic model.
- `ANSWER_TYPE_TO_CORE_QUESTIONS` maps chat-tier `AnswerType` values to analysis-tier `CoreQuestion` tuples (includes the new `HIDDEN_UPSIDE` mapping).
- `build_contract_from_answer_type()` translates chat classifications into the analysis vocabulary.
- `align_question_focus_with_contract()` threads chat contract questions into the analysis parser's `question_focus`, ensuring both routers emit matching `core_questions` in the final `RoutingDecision`.

**Evidence**: `briarwood/intent_contract.py:1-120`.

#### F10 — Frontend Drops Part Of Backend Meaning — **Resolved**

**Original**: Verdict UI ignored `trust_summary, why_this_stance, what_changes_my_view, contradiction_count, blocked_thesis_warnings`. Verifier report mostly discarded.

**What was done**:
- `web/src/lib/chat/events.ts:124-148` — `VerdictEvent` now declares all five formerly-omitted fields.
- `web/src/components/chat/verdict-card.tsx:127-149` — `why_this_stance` renders via `ListBlock`; new `VerdictDetails` progressive-disclosure component renders `what_changes_my_view`, `blocked_thesis_warnings`, `contradiction_count`, and full `trust_summary`.
- `web/src/lib/chat/use-chat.ts` — full `verifier_report` preserved on the message (not just `critic`); verifier reasoning toggle exposed in `messages.tsx`.

**Evidence**: `web/src/lib/chat/events.ts:124-148`, `web/src/components/chat/verdict-card.tsx:127-149`, `api/pipeline_adapter.py:617-639`.

#### F11 — Parallel Pipeline Architecture Still Lives Beside Routed Core — **Partially Resolved**

**Original**: `briarwood/pipeline/*` defined its own `UnifiedIntelligenceAgent, DecisionAgent, Pipeline`, and `runner.py`.

**What was done**:
- Deleted in commit `43b8316`: `briarwood/pipeline/runner.py`, `unified.py`, `decision.py`, `feedback.py`, `scenario_adapter.py`.
- Deleted tests: `tests/test_pipeline_e2e.py`, `scripts/demo_eight_layers.py`.
- What remains under `briarwood/pipeline/`: `session.py`, `triage.py`, `feedback_mixin.py`, `enrichment.py`, `presentation.py`, `representation.py` — utility layers imported by the routed stack, not a parallel verdict stack.
- `briarwood/pipeline/__init__.py:1-61` documents the deletions and surviving exports.

**Residual gap**: Same as F1 stage 2 — Dash/report surfaces still use `decision_engine.build_decision()` instead of projecting from the routed output. Once the four consumer files are rewired, `decision_engine.py` can be deleted and F11/F1 will both fully close.

**Evidence**: `briarwood/pipeline/__init__.py:1-61`, `STATE_OF_1.0.md:62-101`.

#### F12 — Router Classification Default Model Is Over-Tiered — **Resolved**

**Original**: Structured router defaulted to `gpt-5` for a two-field schema.

**What was done**:
- `briarwood/agent/llm.py:144-148` — explicit AUDIT F12 comment; default is now `os.environ.get("BRIARWOOD_STRUCTURED_MODEL", "gpt-4o-mini")`.
- `briarwood/representation/agent.py:14-16` — new Representation Agent also defaults to `gpt-4o-mini`.

**Evidence**: `briarwood/agent/llm.py:144-148`, `briarwood/representation/agent.py:14-16`.

## Phase 2 — New Findings From This Week's Changes

The Representation Agent (`b2d6233`) adds ~600 lines of new LLM-backed chart-selection logic. The partial-data / hidden-upside work (`688c592`) adds five new verdict-card fields and a new SSE event. The verdict consolidation stage 1 (`43b8316`) cleanly deleted the old pipeline but left stage 2 for adapter integration.

### 2.1 New Findings Table

| ID | Severity | Title |
| --- | --- | --- |
| NF1 | P2 | Representation Agent flagged selections are silent-dropped without user warning |
| NF2 | P2 | `HIDDEN_UPSIDE` claim type has no registered chart |
| NF3 | P2 | `session.last_representation_plan` is assigned but not declared |
| NF4 | P1 | Representation Agent LLM call has no retry or timeout enforcement |
| NF5 | P2 | Chart advice lookup does not validate chart IDs against the registry |

### 2.2 Detail

#### NF1 — Representation Agent Flagged Selections Are Silent-Dropped (P2)

**What is happening**: The Representation Agent postprocessor flags a selection when (a) chart spec is unknown, (b) source view is missing, (c) claim type does not match the chart's declared claim types, or (d) required inputs are absent. Flagged selections are then skipped at render time with no user-facing signal.

**Why it matters**: A user can receive a visually sparse verdict card without any indication that the representation layer encountered problems. This violates the explicit F7 pattern established the same week: partial-data warnings should surface when enrichment degrades.

**Evidence**: `briarwood/representation/agent.py:490-530` (flagging logic), `:199-201` (silent skip), `api/pipeline_adapter.py:1291-1297` (plan stored for telemetry but no SSE event emitted). Contrast with `briarwood/agent/dispatch.py:1413-1418` + `api/pipeline_adapter.py:1998-2000` which do emit warnings.

**Suggested fix**: Emit `partial_data_warning` when the plan has flagged selections, or when final selection count falls below an expected threshold for the verdict depth.

#### NF2 — `HIDDEN_UPSIDE` Claim Type Has No Registered Chart (P2)

**What is happening**: `ClaimType.HIDDEN_UPSIDE` is a valid value the agent can emit, but zero chart specs in `briarwood/representation/charts.py` list `"hidden_upside"` in their `claim_types`. The design (documented at `agent.py:62-64`) is to surface these as claim-only selections rendered via the `value_thesis` SSE card instead of a chart.

**Why it matters**: The postprocessor only flags a claim type if a chart spec is present for the chart_id; it does not flag orphaned claim types. A typo or a UI refactor that removes the `value_thesis` hidden-upside block would silently drop the claim with no warning anywhere in the pipeline.

**Evidence**: `briarwood/representation/agent.py:43-64,509-516`, `briarwood/representation/charts.py:135-220`.

**Suggested fix**: In `_postprocess()`, flag any claim type not present in any registered chart's `claim_types` list unless `chart_id=None` is explicitly set as a "prose-only" selection. Or register a nominal "claim-only" chart spec so the mapping contract holds.

#### NF3 — `session.last_representation_plan` Is Assigned But Not Declared (P2)

**What is happening**: `api/pipeline_adapter.py:1293` assigns `session.last_representation_plan = {"selections": selections}` inside a broad `try/except` swallowing `AttributeError`. The field is not declared on the `Session` dataclass at `briarwood/agent/session.py:27-59`. Python permits the attribute assignment but:

1. `Session.save()` (`session.py:96-98`) uses `asdict()` so the field is never persisted to disk.
2. `Session.load()` does not rehydrate it.
3. `clear_response_views()` (`session.py:86`) does not clear it.

**Why it matters**: Any downstream consumer that reads `session.last_representation_plan` will see it on a fresh in-memory session but not after a process restart or session reload — exactly the kind of silent schema drift the 2.6 cache section flagged.

**Evidence**: `briarwood/agent/session.py:26-59,86,96-98`, `api/pipeline_adapter.py:1292-1297`.

**Suggested fix**: Declare `last_representation_plan: dict | None = None` on `Session`, include in `clear_response_views()`, and ensure the JSON round-trip preserves it.

#### NF4 — Representation Agent LLM Call Has No Retry (P1)

**What is happening**: `briarwood/representation/agent.py:239-245` calls `complete_structured()` exactly once. Line 246-248: `except Exception as exc: _logger.warning(...); return None` — the agent then falls back to deterministic planning. There is no retry, no backoff, no distinction between transient (timeout, 5xx, rate-limit) and permanent (schema mismatch) failures, and no `partial_data_warning` emission.

**Why it matters**: Transient LLM hiccups will silently degrade the verdict experience to the deterministic fallback with no telemetry flag. Over time this makes representation-layer degradation invisible. The narrative composer at `briarwood/agent/composer.py:377-430` already demonstrates a retry-with-regen + optional critic pattern that was not copied here.

**Evidence**: `briarwood/representation/agent.py:221-250`, `api/pipeline_adapter.py:1280` (exception logged only). Contrast: `briarwood/agent/composer.py:377-430`.

**Suggested fix**: Add one retry with short backoff for transient error classes; distinguish transient vs permanent; emit `partial_data_warning` after retries exhaust so the user sees that the LLM-optimized plan was not available. Raising this to **P1** because it sits in the DECISION path and degrades a user-visible surface.

#### NF5 — Chart Advice Lookup Does Not Validate Chart IDs Against Registry (P2)

**What is happening**: `api/pipeline_adapter.py:1283-1290` patches chart events with visual advice via `_CHART_ID_TO_ADVICE_SECTION` (`:1142-1149`). The lookup is by chart kind; it never calls `briarwood/representation/charts.get_spec()` to confirm the chart_id is registered.

**Why it matters**: Typos and chart-registry drift will silently miss advice with no warning, a mild version of F8 (docs/reality drift) inside the representation subsystem.

**Evidence**: `api/pipeline_adapter.py:1283-1290,1142-1149`, `briarwood/representation/charts.py:64-86`.

**Suggested fix**: Resolve via `get_spec(chart_id)` first and log-warn on miss.

## Phase 3 — Updated Severity Summary

- **P0**: 1 (down from 3) — F1 stage 2 (Dash/report legacy verdict surfaces)
- **P1**: 3 (down from 6) — F4 (portfolio), F6 (summary prose coupling), NF4 (Representation retry)
- **P2**: 5 (up from 3) — NF1, NF2, NF3, NF5, plus F11 which tracks with F1 stage 2

### 3.1 Top 10 Priorities (Updated)

1. **F1 stage 2** — Rewire `dash_app/quick_decision.py`, `dash_app/view_models.py`, `reports/sections/thesis_section.py`, `reports/sections/conclusion_section.py` through `briarwood/projections/legacy_verdict.py`; delete `briarwood/decision_engine.py`. **P0**. Effort: **S–M** (projector already exists).
2. **NF4** — Add retry + `partial_data_warning` to `briarwood/representation/agent.py` LLM call. **P1**. Effort: **S**.
3. **F6** — Add `key_risks, why_this_stance, what_changes_my_view, contradiction_count, blocked_thesis_warnings` to `summary_inputs` at `briarwood/agent/dispatch.py:1618-1630` and to the `decision_summary.md` prompt template. **P1**. Effort: **S**.
4. **F4** — Define a portfolio/opportunity-set contract (new field on `ExecutionContext`; opportunity-cost module re-plumbing). **P1**. Effort: **XL** (no scope reduction this week).
5. **NF3** — Declare `last_representation_plan` on the `Session` dataclass. **P2**. Effort: **S**.
6. **NF1** — Emit `partial_data_warning` from the Representation Agent when selections are flagged. **P2**. Effort: **S**.
7. **NF2** — Flag unmapped `ClaimType` values in the postprocessor or register a prose-only chart spec. **P2**. Effort: **S**.
8. **NF5** — Validate chart IDs against the registry in the advice-patch path. **P2**. Effort: **S**.
9. Cache-hygiene hardening: add TTL or bounded eviction on the process-global orchestrator caches (F3 residual; memory growth, not correctness). **P2**. Effort: **S**.
10. Harden stage-2 integration tests so Dash/report surfaces can't regress to a separate verdict vocabulary once they are projected. **P2**. Effort: **S**.

## Final Assessment

The week's three commits executed the highest-leverage parts of the 2026-04-19 audit with discipline: verdict consolidation stage 1, CMA provenance split, cache-fact fingerprinting, hidden-upside as a first-class routed output, partial-data warnings end-to-end, router bridging, frontend verdict completeness, router model down-tier, and doc reconciliation. The routed deterministic core is now measurably more trustworthy than it was three days ago.

Two structural gaps remain and one new pattern emerged:

1. **Stage 2 of verdict consolidation is the last P0**. Four files still call the deprecated legacy engine. Until they project through the new layer, the original F1 risk (same property yielding different top-line calls across surfaces) is not actually closed.

2. **Portfolio-aware allocation (F4) was deliberately deferred**. The product promise of capital allocation still cannot be answered from the routed contracts.

3. **The Representation Agent introduced the same category of risk it was meant to reduce**: a new LLM surface with no retry, silent fallbacks on flag, and an undeclared session slot. The fixes are small and the patterns to copy (verifier/retry from `composer.py`, `_record_partial` from `dispatch.py`) already exist in the same codebase. Copying them before the representation agent sees real traffic is the cheapest correction window.

## Stop Gate

Read-only audit complete. No code changes made. Awaiting review for Phase 2 action.

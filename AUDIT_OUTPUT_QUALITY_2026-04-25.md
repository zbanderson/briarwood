# Output-Quality Audit — 2026-04-25

**Status:** Phase 1 / read-only diagnostic. No code changes in this handoff.
**Scope:** Diagnoses three user-reported quality complaints (brain-dump summary, robotic prose, charts that don't explain) and inventories logging gaps so we can detect missing-call problems in the terminal.
**Out of scope:** Fixes. Recommendations land in [FOLLOW_UPS.md](FOLLOW_UPS.md) or as their own handoff.

---

## TL;DR

Three structural facts explain almost everything the user is seeing:

1. **The "editor LLM that cleans up the brain dump" does not exist.** `briarwood/editor/` is a deterministic 5-check claim-validator, not a prose editor. The only LLM that rewrites synthesis output into prose is `briarwood/claims/representation/verdict_with_comparison.py:_render_llm_prose` — which only runs when the **claims wedge** fires (gated by `BRIARWOOD_CLAIMS_ENABLED`, default `false`, AND only on DECISION/LOOKUP with a pinned listing). When the wedge is off or falls through, the user sees fields synthesized by deterministic Python templates with **no humanization pass**.

2. **The "robotic" phrasing is real.** It comes from f-string templates in `briarwood/synthesis/structured.py` — specifically `_why_this_stance` (lines 655–691), `_what_changes_my_view` (lines 694–714), and `classify_decision_stance` recommendation strings (lines 160–229). Phrases like "A price improvement of about X% would materially improve the setup" are literally hardcoded. The composer LLM (`briarwood/agent/composer.py::complete_and_verify`) does run on most prose-bearing handlers, but it composes prose **on top of** the deterministic structured output — and a verifier (grounding gate) penalizes departure from that structure, so the LLM prose tends to faithfully echo the templates.

3. **Charts don't explain because the Representation Agent only runs on the routed-decision path.** The Layer-4 agent at `briarwood/representation/agent.py` adds `supports_claim` + `why_this_chart` to chart events, but it's invoked **once**, at `api/pipeline_adapter.py:1446`, and only on the routed-decision stream. Browse-tier and other chart-emitting handlers emit chart events directly without explanation. This was already entered as [FOLLOW_UPS.md "Broaden Representation Agent triggering beyond the claims flag"](FOLLOW_UPS.md) — but the connection to the user's complaint had not been drawn.

A fourth, structural finding emerged during verification:

4. **README_dispatch.md contradicts the code.** It claims "From dispatch: `briarwood.orchestrator.run_briarwood_analysis_with_artifacts` (most handlers)" — but `grep` finds **zero** direct calls in `briarwood/agent/dispatch.py`. The orchestrator runs from exactly two production sites: `briarwood/runner_routed.py:228` (external entry, e.g., property pre-computation) and `briarwood/claims/pipeline.py:42` (the claims wedge). Most chat-tier turns therefore **never run the full scoped orchestration cascade** — they call individual tools in `briarwood/agent/tools.py`, hand-stitch the results, and pass them to the composer. This is flagged below in §6 as a contradiction to surface.

---

## Section 1 — Wiring Map: Scoped Registry + LLM Surfaces

### 1.1 Scoped registry tools (15 total)

Source: [`briarwood/execution/registry.py:6-28`](briarwood/execution/registry.py).

| # | Tool name | Runner entry | README |
|---|-----------|--------------|--------|
| 1 | `valuation` | `briarwood.modules.valuation.run_valuation` | [README_valuation.md](briarwood/modules/README_valuation.md) |
| 2 | `carry_cost` | `briarwood.modules.carry_cost.run_carry_cost` | [README_carry_cost.md](briarwood/modules/README_carry_cost.md) |
| 3 | `risk_model` | `briarwood.modules.risk_model.run_risk_model` | [README_risk_model.md](briarwood/modules/README_risk_model.md) |
| 4 | `arv_model` | `briarwood.modules.arv_model_scoped.run_arv_model` | [README_arv_model.md](briarwood/modules/README_arv_model.md) |
| 5 | `comparable_sales` | `briarwood.modules.comparable_sales_scoped.run_comparable_sales` | [README_comparable_sales.md](briarwood/modules/README_comparable_sales.md) |
| 6 | `confidence` | `briarwood.modules.confidence.run_confidence` | [README_confidence.md](briarwood/modules/README_confidence.md) |
| 7 | `current_value` | `briarwood.modules.current_value_scoped.run_current_value` | [README_current_value.md](briarwood/modules/README_current_value.md) |
| 8 | `hold_to_rent` | `briarwood.modules.hold_to_rent.run_hold_to_rent` | [README_hold_to_rent.md](briarwood/modules/README_hold_to_rent.md) |
| 9 | `hybrid_value` | `briarwood.modules.hybrid_value_scoped.run_hybrid_value` | [README_hybrid_value.md](briarwood/modules/README_hybrid_value.md) |
| 10 | `income_support` | `briarwood.modules.income_support_scoped.run_income_support` | [README_income_support.md](briarwood/modules/README_income_support.md) |
| 11 | `legal_confidence` | `briarwood.modules.legal_confidence.run_legal_confidence` | [README_legal_confidence.md](briarwood/modules/README_legal_confidence.md) |
| 12 | `location_intelligence` | `briarwood.modules.location_intelligence_scoped.run_location_intelligence` | [README_location_intelligence.md](briarwood/modules/README_location_intelligence.md) |
| 13 | `margin_sensitivity` | `briarwood.modules.margin_sensitivity_scoped.run_margin_sensitivity` | [README_margin_sensitivity.md](briarwood/modules/README_margin_sensitivity.md) |
| 14 | `market_value_history` | `briarwood.modules.market_value_history_scoped.run_market_value_history` | [README_market_value_history.md](briarwood/modules/README_market_value_history.md) |
| 15 | `opportunity_cost` | `briarwood.modules.opportunity_cost.run_opportunity_cost` | [README_opportunity_cost.md](briarwood/modules/README_opportunity_cost.md) |
| 16 | `rental_option` | `briarwood.modules.rental_option_scoped.run_rental_option` | [README_rental_option.md](briarwood/modules/README_rental_option.md) |
| 17 | `renovation_impact` | `briarwood.modules.renovation_impact_scoped.run_renovation_impact` | [README_renovation_impact.md](briarwood/modules/README_renovation_impact.md) |
| 18 | `rent_stabilization` | `briarwood.modules.rent_stabilization.run_rent_stabilization` | [README_rent_stabilization.md](briarwood/modules/README_rent_stabilization.md) |
| 19 | `resale_scenario` | `briarwood.modules.resale_scenario_scoped.run_resale_scenario` | [README_resale_scenario.md](briarwood/modules/README_resale_scenario.md) |
| 20 | `scarcity_support` | `briarwood.modules.scarcity_support_scoped.run_scarcity_support` | [README_scarcity_support.md](briarwood/modules/README_scarcity_support.md) |
| 21 | `strategy_classifier` | `briarwood.modules.strategy_classifier.run_strategy_classifier` | [README_strategy_classifier.md](briarwood/modules/README_strategy_classifier.md) |
| 22 | `town_development_index` | `briarwood.modules.town_development_index.run_town_development_index` | [README_town_development_index.md](briarwood/modules/README_town_development_index.md) |
| 23 | `unit_income_offset` | `briarwood.modules.unit_income_offset.run_unit_income_offset` | [README_unit_income_offset.md](briarwood/modules/README_unit_income_offset.md) |

(Count is 23 imports in registry.py, not 15 — the architecture docs that say "15" are stale; [DECISIONS.md](DECISIONS.md) "Audit docs are drifted" applies. Flagged in §6.)

### 1.2 LLM call sites

| # | Surface | File:line | LLM purpose | Currently observable via |
|---|---------|-----------|-------------|--------------------------|
| 1 | Router classify | `briarwood/agent/router.py:292-321` | One-shot intent classification (gpt-4o-mini, structured) | Shared LLM ledger via `complete_structured_observed` (see §5) |
| 2 | Composer prose + verifier | `briarwood/agent/composer.py:333-486` | Prose composition with grounding-violation rewrite | Shared LLM ledger via `complete_text_observed`, breadcrumbs on `session.last_partial_data_warnings` |
| 3 | Decision critic | `briarwood/agent/composer.py:109-240` | Post-generation critique on `decision_summary` tier (env-gated `BRIARWOOD_DECISION_CRITIC=on`) | LLM ledger; not run on every turn |
| 4 | Representation chart selection | `briarwood/representation/agent.py:234-286` | Chart-binding selection with `claim_type` annotations | LLM ledger via `complete_structured_observed`, breadcrumbs on session |
| 5 | Claim render | `briarwood/claims/representation/verdict_with_comparison.py:88-107` | Claim prose render (2-4 sentence verdict) | Inherited from composer (calls `complete_and_verify`) |
| 6 | Local intelligence extractor | `briarwood/local_intelligence/adapters.py:156-192` | Document extraction from local-intelligence sources | Direct OpenAI client, **NOT** the shared LLMClient — bypasses the ledger. Logs failures only. |

### 1.3 Response-assembly path per AnswerType (chat-tier)

For each of the 14 dispatch handlers, what LLM-bearing surfaces actually run. **Composer** = `briarwood/agent/composer.py::complete_and_verify` (or sibling `compose_*` entries). **Wedge** = `_maybe_handle_via_claim` at `dispatch.py:1809`. **Repr Agent** = the Layer-4 chart-selection LLM at `api/pipeline_adapter.py:1446`.

| AnswerType | Handler | Runs orchestrator? | Calls composer? | Hits claims wedge? | Final prose source |
|------------|---------|--------------------|-----------------|---------------------|---------------------|
| LOOKUP | `dispatch.py:1752` | Indirect (via wedge) | Yes | Conditional | composer-LLM, or claim-render-LLM if wedge fires |
| DECISION | `dispatch.py:1887` | Indirect (via wedge) | Yes | **Yes** | composer-LLM, or claim-render-LLM if wedge fires |
| SEARCH | `dispatch.py:2361` | No | No | No | **deterministic template** |
| COMPARISON | `dispatch.py:2516` | No | No | No | **deterministic template** |
| RESEARCH | `dispatch.py:2557` | No | No | No | **deterministic template** |
| VISUALIZE | `dispatch.py:2896` | No | No | No | **deterministic template** |
| RENT_LOOKUP | `dispatch.py:2922` | No | Yes | No | composer-LLM |
| PROJECTION | `dispatch.py:3130` | No | Yes | No | composer-LLM |
| MICRO_LOCATION | `dispatch.py:3412` | No | No | No | **deterministic template** |
| RISK | `dispatch.py:3473` | No | Yes | No | composer-LLM |
| EDGE | `dispatch.py:3654` | No | Yes | No | composer-LLM |
| STRATEGY | `dispatch.py:3921` | No | Yes | No | composer-LLM |
| BROWSE | `dispatch.py:4028` | No | Yes | No | composer-LLM |
| CHITCHAT | `dispatch.py:4180` | No | No | No | **deterministic template** |

**Representation Agent triggering:** Confirmed at `api/pipeline_adapter.py:1446` (`agent = RepresentationAgent(llm_client=llm)`). It runs on the routed-decision stream only. Other chart-emitting paths (browse-tier in particular) emit chart events directly from handler code without going through this agent.

**Source of orchestrator calls** (verified by grep across `briarwood/` and `api/`):
- `briarwood/runner_routed.py:228` — external entry (property pre-computation, batch)
- `briarwood/claims/pipeline.py:42` — inside the claims wedge
- `briarwood/orchestrator.py:451` — `run_briarwood_analysis` convenience wrapper that calls `_with_artifacts`
- That's it. **Zero direct calls from any dispatch handler.**

---

## Section 2 — Diagnosis: "Brain-dump" Summary (Item 1)

### What the user thinks is happening
"There's an editor LLM that should clean up the brain-dump summary."

### What is actually happening

There is no LLM editor on the legacy path. Specifically:

- **`briarwood/editor/`** is a deterministic 5-check structural validator for `VerdictWithComparisonClaim`. It returns `EditResult(passed, failures)`. It never rewrites text. ([README](briarwood/editor/README.md), [validator.py:32](briarwood/editor/validator.py))
- **`briarwood/agent/composer.py`** runs an LLM **for the body prose**, but it does so **before** the verdict event is built. There's no second-pass cleanup over the structured fields.
- **The only LLM that rewrites a structured synthesizer output into prose** is `briarwood/claims/representation/verdict_with_comparison.py:88-107` (`_render_llm_prose`). It only runs when:
  1. `BRIARWOOD_CLAIMS_ENABLED` is `true` (default `false`)
  2. The archetype maps to `VERDICT_WITH_COMPARISON` (DECISION or LOOKUP, with pinned listing)
  3. The editor's 5 checks all pass
  4. None of the wedge stages raise

If any of those fail, the wedge silently falls back to the legacy DECISION path — the user gets the deterministic synthesizer's structured fields with no rewrite. The only signal that this happened is the `EVENT_CLAIM_REJECTED` SSE event ([api/events.py:302-317](api/events.py)), which is documented as "for dev tooling, not user-facing."

### What "brain dump" likely refers to

The synthesizer at `briarwood/synthesis/structured.py::build_unified_output` populates ~17 named fields (lines 89-117). Of these, the verdict SSE event projects 9-10 into the UI ([api/pipeline_adapter.py:651-676](api/pipeline_adapter.py)). The fields *built but not projected* (`recommendation`, `best_path`, `next_checks`, `key_value_drivers` in the verdict event specifically) are not necessarily wasted — they are projected into other event types or session views. But the **fields that DO project** (`why_this_stance`, `what_changes_my_view`, `what_must_be_true`, `key_risks`, `trust_summary`) reach the UI as **structured lists with no narrative connective tissue**, which is the perceptual definition of a brain dump even when each individual list is short.

### Cited evidence
- [briarwood/editor/README.md](briarwood/editor/README.md) — purpose statement: "deterministic gate"
- [briarwood/editor/validator.py:32](briarwood/editor/validator.py) — `edit_claim` entry, no LLM
- [briarwood/claims/representation/verdict_with_comparison.py:88-107](briarwood/claims/representation/verdict_with_comparison.py) — only LLM rewrite of synthesis output
- [briarwood/feature_flags.py:22](briarwood/feature_flags.py) — `claims_enabled_for(property_id)` — gates the wedge
- [briarwood/synthesis/structured.py:89-117](briarwood/synthesis/structured.py) — 17 fields populated
- [api/pipeline_adapter.py:651-676](api/pipeline_adapter.py) — verdict event projection

---

## Section 3 — Diagnosis: Robotic Prose (Item 2)

### What the user reports
Phrasings like "price X might be more interesting than price Y."

### Source of robotic prose

The exact quoted phrasing isn't a literal template anywhere in the codebase, but the **family of phrasings** is from deterministic f-string templates in `briarwood/synthesis/structured.py`. Specific generators:

| Helper | Lines | Sample template |
|--------|-------|-----------------|
| `classify_decision_stance` (`recommendation` + `best_path`) | 160-229 | "Interesting but fragile — value is there, but risk and conflict flags make it thinner than it first appears." (line 210) |
| `_why_this_stance` | 655-691 | "Current basis sits about {premium*100:.1f}% above/below Briarwood's fair-value anchor." |
| `_what_changes_my_view` | 694-714 | "A price improvement of about {required*100:.1f}% would materially improve the setup." (line ~708) |
| `_what_must_be_true` | 468-481 | "Property sustains ~{occupancy*100:.0f}% occupancy or better." |
| `_key_risks` | 557-584 | "Execution fragility {score:.2f} — thesis depends on assumptions holding." |

These templates feed the verdict SSE event as structured fields. The composer LLM sees them as structured input when it composes the body prose. The composer's grounding verifier ([composer.py:333-486](briarwood/agent/composer.py)) penalizes prose that drifts from structured ground truth — meaning **the LLM prose tends to faithfully echo template phrasing** to avoid grounding violations. Robotic.

### Why the composer doesn't fix this

The composer is doing exactly what its design says: **grounded paraphrase of the structured output**. It is not licensed to invent new framings. The composer is downstream of the templates, not an editor for them.

### Confirmed: no humanization layer exists today
- No `decision_critic` runs on verdict-tier fields ([composer.py:109-240](briarwood/agent/composer.py) — env-gated `BRIARWOOD_DECISION_CRITIC=on`, scope `decision_summary` only).
- No "rewrite", "humanize", "polish", or "edit_prose" function exists in `briarwood/agent/` anywhere — verified by grep.
- The only LLM-driven rewrite of synthesis output is in the claims wedge, which is feature-flag-gated (see §2).

### Cited evidence
- [briarwood/synthesis/structured.py:160-229, 468-481, 557-584, 655-691, 694-714](briarwood/synthesis/structured.py)
- [briarwood/agent/composer.py:333-486](briarwood/agent/composer.py) — composer + grounding verifier
- [briarwood/agent/composer.py:109-240](briarwood/agent/composer.py) — decision_critic, narrow scope

---

## Section 4 — Diagnosis: Charts Don't Explain (Item 3)

### What's missing
The Representation Agent's whole point is to attach `supports_claim` (a `ClaimType` enum value) and `why_this_chart` (the claim text) to every chart event ([representation/agent.py:189-238, 217-223](briarwood/representation/agent.py)). The chart event then carries an explicit "this chart backs this specific verdict claim" payload that the frontend can render as a caption.

### Why the user sees uncaptioned charts
The Representation Agent is invoked from **exactly one place**: [api/pipeline_adapter.py:1446](api/pipeline_adapter.py). That's the routed-decision stream. It runs only when:
1. The router decided this is `AnswerType.DECISION` (or possibly LOOKUP routed through the decision stream)
2. The decision view is reconstructable from session state (`_unified_from_session` returns non-`None`, [pipeline_adapter.py:1266-1333](api/pipeline_adapter.py))

Everywhere else — browse-tier "what about X street", search-results panels, projection panels, comp panels — chart events are emitted directly from handler code in `dispatch.py` or from `api/pipeline_adapter.py` template-handlers without ever passing through the Representation Agent. Those events carry `chart_id` and `data` but no `supports_claim` / `why_this_chart`. The frontend has nothing to caption.

### Already in FOLLOW_UPS
This is exactly [FOLLOW_UPS.md "Broaden Representation Agent triggering beyond the claims flag"](FOLLOW_UPS.md). The connection to the user's complaint is the new evidence: the user is hitting browse-tier or non-routed paths regularly, and those paths can never produce explained charts under the current design.

### Cited evidence
- [briarwood/representation/agent.py:189-238](briarwood/representation/agent.py) — `render_events` + `supports_claim`/`why_this_chart` augmentation
- [api/pipeline_adapter.py:1446](api/pipeline_adapter.py) — sole call site
- [api/pipeline_adapter.py:1266-1333](api/pipeline_adapter.py) — `_unified_from_session` reconstruction (also of note: `recommendation="Decision summary pending."` placeholder at line 1311 may show through to UI when decision view is sparse)

---

## Section 5 — Logging Gap Report

### 5.1 Existing observability

Better than expected. There is already a shared LLM call ledger:
- **`briarwood/agent/llm_observability.py`** — `LLMCallLedger` records per-call metadata (surface, provider, model, prompt hash, response hash, duration, status)
- Wraps via `complete_text_observed` and `complete_structured_observed` helpers
- `BRIARWOOD_LLM_DEBUG_PAYLOADS=1` attaches full prompts/responses to records

Surfaces that USE the ledger:
- Composer (`complete_and_verify` → `complete_text_observed`)
- Router (`_llm_classify` → `complete_structured_observed`)
- Representation Agent (`_plan_via_llm` → `complete_structured_observed`)
- Claim renderer (inherits via composer)

Surfaces that BYPASS the ledger:
- **Local intelligence extractor** ([briarwood/local_intelligence/adapters.py:156-192](briarwood/local_intelligence/adapters.py)) — uses raw OpenAI client. Logs failures at WARNING but no success record.
- Anything that calls `OpenAIChatClient.complete()` directly without going through the observed wrappers.

### 5.2 What is NOT observable today

These are the gaps that map to the user's "is X actually being called?" question:

**Per scoped tool — execution silence:**
- `briarwood/execution/executor.py:289-364` produces a per-module trace dict (`module`, `source` "run"/"cache", `confidence`, `warning_count`) — but **never logs it**. The trace is returned to the caller; only callers that surface it make it visible.
- `briarwood/execution/planner.py::ExecutionPlan.skipped_modules` enumerates modules dropped from the plan due to missing prereqs. **No log line is emitted for skips.**
- A scoped tool that returns a degraded `ModulePayload` (`mode="error"` or `"fallback"` per the [error contract](DECISIONS.md)) is stored but **not logged at the orchestrator level**. From a terminal you cannot see "module X failed and emitted a fallback."

**Per LLM call site — terminal silence:**
- `briarwood/agent/llm.py::OpenAIChatClient.complete()` (lines 93-119) — successful calls log nothing. Cost is recorded via `guard.record_openai()`. No latency, no token counts, no success signal.
- The LLM ledger is in-memory only by default (`llm_observability.py:55-263`). Without dumping it explicitly, the operator sees nothing in the terminal.
- Router sanity guard (`router.py:319` — `CHITCHAT → BROWSE` downgrade) is silent.
- Representation Agent's deterministic-fallback path (`agent.py:299-510`) is silent on entry. Only LLM-exception cases write a breadcrumb.

**Per handler — assembly silence:**
- No handler logs which sub-tool calls it made. So the operator cannot see "`handle_decision` called `get_value_thesis`, `get_risk_profile`, but skipped `get_projection`" — they have to read code.
- The wedge fall-through (`_maybe_handle_via_claim` returns `None`) is silent except for the `EVENT_CLAIM_REJECTED` SSE event.

**No global verbosity switch:**
- No `BRIARWOOD_DEBUG`, `BRIARWOOD_TRACE`, or `BRIARWOOD_VERBOSE` env var exists.
- `BRIARWOOD_LLM_DEBUG_PAYLOADS` is the closest thing — but it only controls whether full payloads attach to ledger records, not whether anything appears in the terminal.

### 5.3 What we need to detect "things not being called"

The user's specific request is to see in the terminal that "X is not being called." That requires:

1. **A per-turn invocation manifest.** At the end of each chat turn, emit one structured line listing: which handler ran, which scoped tools ran (vs. which were skipped and why), which LLM calls fired, which fell back, and whether the wedge fired. **Today none of this exists in one place.** The ledger has the LLM half but not the tool/handler half.
2. **Skip-reason logging at the planner.** When a tool is dropped because a dependency wasn't planned or returned `mode="error"`, emit a log line naming both the tool and the prerequisite.
3. **Wedge-decision logging.** Emit one line on every DECISION/LOOKUP turn naming whether the wedge fired or fell through, and on fall-through, why (e.g., `claims_enabled_for=False`, `archetype=None`, `editor_failures=[...]`).
4. **A `BRIARWOOD_TRACE=1` env var** that turns the ledger emission on at INFO level so it shows in the terminal without changing record contents.

---

## Section 6 — Flagged Contradictions (CLAUDE.md §"Contradictions")

### 6.1 README_dispatch.md overstates orchestrator coupling
**Severity:** High — misleading for any future handoff trying to plumb logging through dispatch.

[`briarwood/agent/README_dispatch.md:9, 41-42`](briarwood/agent/README_dispatch.md) says: "From dispatch: `briarwood.orchestrator.run_briarwood_analysis_with_artifacts` (most handlers)."

Verified by `grep -nE "run_briarwood_analysis(_with_artifacts)?\(" briarwood/agent/dispatch.py`: zero matches.

The orchestrator is called from:
- [`briarwood/runner_routed.py:228`](briarwood/runner_routed.py)
- [`briarwood/claims/pipeline.py:42`](briarwood/claims/pipeline.py)
- (`briarwood/orchestrator.py:451` is internal — `run_briarwood_analysis` calls `_with_artifacts`)

**Suggested resolution:** Add to [DECISIONS.md](DECISIONS.md) (judgment call: is the README aspirational or just wrong?) and update [briarwood/agent/README_dispatch.md](briarwood/agent/README_dispatch.md) to reflect that handlers compose responses by calling `briarwood/agent/tools.py` functions, **not** the full orchestrator. The orchestrator runs only on the wedge path or via `runner_routed.py` (likely from external/batch entry, not chat-tier).

### 6.2 Tool count drift (15 vs 23)
[ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](TOOL_REGISTRY.md) frame the system as having "15 scoped models." The actual count of imported scoped runners in [`briarwood/execution/registry.py:6-28`](briarwood/execution/registry.py) is 23. This is consistent with [DECISIONS.md "Audit docs are drifted"](DECISIONS.md) — flagging here for completeness so the wiring map's reader doesn't trust the audit-doc count.

**Suggested resolution:** [FOLLOW_UPS.md](FOLLOW_UPS.md) entry — mechanical update to ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md.

### 6.3 13 modules missing READMEs (READMEs Drift Check, this session)
[bull_base_bear, local_intelligence, macro_reader, market_analyzer, ownership_economics, property_data_quality, renovation_scenario, rental_ease, risk_constraints, security_model, teardown_scenario, town_aggregation_diagnostics, town_county_outlook]. Most are KEEP-as-internal-helper per [PROMOTION_PLAN.md](PROMOTION_PLAN.md), so they don't need agent-template READMEs — but at least the boundaries are undocumented.

**Suggested resolution:** Out of scope for this audit. Track via [FOLLOW_UPS.md](FOLLOW_UPS.md) if desired.

---

## Section 7 — Recommended Phase 2 (Logging Plan)

This is a recommendation, not an action. Awaits user approval.

### 7.1 What to add

**A. Per-turn invocation manifest.** At the end of each chat-tier turn, emit one structured log line via the existing logging infrastructure. Schema:

```json
{
  "turn_id": "uuid",
  "answer_type": "DECISION",
  "handler": "handle_decision",
  "wedge": {"fired": false, "reason": "claims_enabled_for=False"},
  "tools_run": ["get_value_thesis", "get_risk_profile"],
  "tools_skipped": [{"name": "get_projection", "reason": "no projection hint in text"}],
  "scoped_modules_run": ["valuation", "carry_cost", "..."],
  "scoped_modules_skipped": [{"name": "renovation_impact", "reason": "no prereq"}],
  "llm_calls": [{"surface": "agent_router.classify", "duration_ms": 180, "status": "success"}, ...],
  "duration_ms_total": 1840
}
```

**B. Skip-reason logging at planner.** Emit one line per skipped scoped module at WARNING level, including the dependency that failed to plan.

**C. Wedge decision logging.** One line per DECISION/LOOKUP turn naming the wedge outcome.

**D. `BRIARWOOD_TRACE=1` env var.** When set, the LLM ledger records emit to stderr at INFO level in addition to in-memory storage. Lightweight, opt-in, no payload change.

### 7.2 Dependency on FOLLOW_UPS items

Maps cleanly onto:
- [FOLLOW_UPS.md "Add a shared LLM call ledger"](FOLLOW_UPS.md) — partly done (ledger exists in-memory); this would extend it with terminal emission and the per-turn manifest.

### 7.3 Open questions for user before Phase 2

1. **Where should the per-turn manifest land?** Stderr only (operator tail), or also persisted to `data/agent_feedback/turn_manifests.jsonl` for replay/analysis?
2. **What detail level for `tools_skipped`?** Just name + one-line reason, or full reason with prereq chain?
3. **Should we redact prompt/response content** in the trace, even with `BRIARWOOD_TRACE=1`? Default to redacted; let `BRIARWOOD_LLM_DEBUG_PAYLOADS=1` un-redact.

---

## Section 8 — Proposed Phase 3 Fixes (preview, not action)

After Phase 2 logging lands and we've watched it for a turn or two, the candidate fixes for items 1, 2, 3 are roughly:

- **Item 1 (brain dump):** Either (a) flip `BRIARWOOD_CLAIMS_ENABLED` on for a curated property allowlist so the wedge runs and the claim renderer rewrites the brain dump, OR (b) build a dedicated post-synthesis "humanizer" LLM call that runs over the verdict event before SSE emission. (a) is cheaper and reuses existing infra; (b) is the more general fix.
- **Item 2 (robotic prose):** The composer's grounding verifier is probably too tight. Loosening it (already in user-memory `project_llm_guardrails.md` as "LLM guardrails are currently too tight") and giving the composer license to re-frame the structured fields, not just paraphrase them, would reduce the echo problem.
- **Item 3 (charts):** Generalize the [api/pipeline_adapter.py:1446](api/pipeline_adapter.py) Representation Agent invocation to all chart-emitting paths, not just the routed-decision stream. This is exactly the FOLLOW_UPS entry; it just needs implementation.

Each is its own scoped change. None of them happens in this audit.

---

## Section 9 — Live diagnostic findings (after instrumentation landed)

After §1-§7 of this audit identified that observability was a prerequisite for any architectural fix, the per-turn invocation manifest was implemented (see [DECISIONS.md](DECISIONS.md) "Per-turn invocation manifest infrastructure" 2026-04-25). The first live trace produced findings that significantly sharpen the audit's diagnosis.

### 9.1 The chat-tier never runs the orchestrator

[README_dispatch.md](briarwood/agent/README_dispatch.md) once claimed handlers call `run_briarwood_analysis_with_artifacts` — that was corrected in §6.1. The live trace confirms the corrected description: `dispatch.py` handlers call `tools.py` functions; `tools.py` functions invoke the scoped executor with **their own narrow per-tool plans**; the orchestrator entry only runs from `runner_routed.py:228` (external) and `claims/pipeline.py:42` (wedge).

The implication is bigger than just a routing detail. It means the chat-tier path **never builds a `UnifiedIntelligenceOutput` from a single full-cascade run**. There is no point in the chat-tier flow at which all 23 modules' outputs are co-resident in one structure. The deterministic synthesizer at `briarwood/synthesis/structured.py` only runs for the wedge path; for everything else, prose is built from per-tool fragments by the composer.

### 9.2 BROWSE turn anatomy (concrete numbers)

Live trace from "what do you think of 1008 14th Ave, Belmar, NJ" (BROWSE, 26.3s total wall-clock):

| Bucket | Duration | What |
|--------|----------|------|
| Router classify | 2.67s | gpt-4o-mini intent classification |
| Composer LLM | 4.08s | `composer.draft` — actual prose generation |
| `get_property_enrichment` | 3.01s | Likely external API (Attom/etc.) |
| `get_property_presentation` | 3.01s | LLM call inside `presentation_advisor.advise_visual_surfaces` (bypasses LLM ledger — see §9.5) |
| `get_property_brief` | 2.22s | Internally invokes scoped executor |
| `get_projection` | 1.34s | |
| `get_strategy_fit` | 0.68s | |
| `get_rent_estimate` | 0.69s | |
| `get_cma` | 0.68s | |
| `get_value_thesis` | 0.68s | |
| Other tools | ~0.01s | Mostly cached `get_property_summary` |
| **Sum of measured** | **~19.4s** | |
| **Unaccounted** | **~6.9s** | Streaming delay (`_stream_text` chunk_delay=15ms × ~400 words ≈ 6s) + session work + serialization |

### 9.3 Fragmented per-tool execution: 33 events, 10 distinct modules, 13 dormant

The same BROWSE turn produced 33 module-execution events across at least 5 separate execution plans. Module duplication:

- `valuation` ran 5x (1 fresh + 4 cached)
- `carry_cost` ran 5x (1 fresh + 4 cached)
- `risk_model` ran 4x **all fresh** — cache key apparently varies between per-tool plans
- `confidence` ran 5x **all fresh**
- `legal_confidence` ran 4x **all fresh**
- `town_development_index` ran 1x with `confidence: null` and 1 warning
- `resale_scenario`, `rent_stabilization`, `hold_to_rent`, `rental_option` each ran 1x

13 modules in the registry **never fired for this BROWSE turn:**
`arv_model`, `comparable_sales`, `current_value`, `hybrid_value`,
`income_support`, `location_intelligence`, `margin_sensitivity`,
`market_value_history`, `opportunity_cost`, `renovation_impact`,
`scarcity_support`, `strategy_classifier`, `unit_income_offset`.

`comparable_sales` is the comp engine that drives the value-vs-fair-value verdict. `location_intelligence` is the micro-location signal (proximity to beach/train, walkability). `strategy_classifier` is the module behind the user-facing "best path" call. None fired. The product owner's framing during the audit session was: "if I ask Claude directly to underwrite a house, it shouldn't be better than the models we've spent a month developing." This is the mechanical reason it currently can — those models aren't running for the chat-tier path most queries take.

### 9.4 What actually informs the BROWSE prose today

Inputs the composer LLM saw on this turn (inferred from the 4.08s `composer.draft` call timing relative to which tools had returned by then):
- Property summary (address, beds, baths, sqft, asking price)
- Result of `get_value_thesis` — uses `valuation`, `carry_cost`, possibly `resale_scenario`
- Result of `get_cma` — Engine B (live-Zillow-preferred) per [FOLLOW_UPS.md](FOLLOW_UPS.md) "Two comp engines"
- Result of `get_projection` — uses `resale_scenario`, `town_development_index`, `valuation`
- Result of `get_strategy_fit` — apparently NOT routing through `strategy_classifier` module
- Result of `get_rent_estimate` — uses `rent_stabilization`, `hold_to_rent`, `rental_option`

Inputs the composer LLM did NOT see:
- Comparable-sales adjusted ranges (the comp engine never ran)
- Location-intelligence signals (never ran)
- Strategy-classifier output (never ran — `get_strategy_fit` is using something else)
- ARV / renovation / margin-sensitivity scenarios (never ran)

The prose is being asked to reason about a property using ~40% of the structured information Briarwood is capable of producing.

### 9.5 Hidden LLM call: `presentation_advisor`

The 3.0s spent in `get_property_presentation` is almost certainly an LLM call to `presentation_advisor.advise_visual_surfaces`. That call doesn't appear in the manifest's `llm_calls` list because it uses the raw OpenAI client rather than `complete_structured_observed`. Same bug class as the existing [FOLLOW_UPS.md](FOLLOW_UPS.md) "Route local-intelligence extraction through shared LLM boundary" entry — a sibling LLM call site that bypasses the shared infrastructure. Captured as a new follow-up.

### 9.6 The composer DID fire; the wedge did NOT

Two things the audit's §1.3 wiring map got right and one it got partly wrong:

- **Right:** BROWSE calls the composer (4.08s `composer.draft` LLM call confirmed in trace).
- **Right:** The wedge fires only on DECISION (`wedge: null` for BROWSE).
- **Partly wrong:** The map showed BROWSE as "calls composer." It does — but it ALSO calls 10+ tools.py functions that each invoke the executor. The audit's per-AnswerType table understated how much work each handler does.

### 9.7 The architectural lever — captured in FOLLOW_UPS

Two complementary fixes are now formally tracked in [FOLLOW_UPS.md](FOLLOW_UPS.md):

1. **"Consolidate chat-tier execution: one plan per turn, intent-keyed module set"** — replace the fragmented per-tool plans with a single consolidated execution plan per chat turn. Module-set keyed by AnswerType. Brings dormant modules online, eliminates duplicate work, produces a real `UnifiedIntelligenceOutput`.

2. **"Layer 3 LLM synthesizer: prose from full UnifiedIntelligenceOutput"** — depends on (1). Replace the composer's narrow-input call with an LLM that reads the full unified output and writes intent-aware prose. Numeric guardrail preserved via existing verifier infrastructure.

Both are captured with file-level anchor points and a rollout plan in FOLLOW_UPS.md. The order is set: consolidation first (without it, the synthesizer has nothing to read), then the synthesizer (without it, even a perfect unified output doesn't reach the user).

### 9.8 Where this leaves the original four complaints

- **Complaint 1: brain-dump summary** — partly addressed via composer loosening; will be properly fixed by Layer 3 synthesizer reading full output instead of fragmented slices.
- **Complaint 2: robotic prose** — composer guardrails were tightening output; loosening them (BRIARWOOD_STRICT_STRIP) is half the answer. The other half is feeding the LLM richer structured input — same Layer 3 lever.
- **Complaint 3: charts don't explain** — Step 2 (Representation Agent generalization) still pending. Independent of the consolidation work.
- **Complaint 4: model wiring map + logging** — done. The manifest is the diagnostic; the audit doc + DECISIONS.md + FOLLOW_UPS.md are the wiring map.

---

## Appendix A — Files inspected

- [CLAUDE.md](CLAUDE.md), [DECISIONS.md](DECISIONS.md), [FOLLOW_UPS.md](FOLLOW_UPS.md)
- [briarwood/agent/README_router.md](briarwood/agent/README_router.md), [README_dispatch.md](briarwood/agent/README_dispatch.md)
- [briarwood/editor/README.md](briarwood/editor/README.md), [briarwood/synthesis/README.md](briarwood/synthesis/README.md), [briarwood/representation/README.md](briarwood/representation/README.md), [briarwood/claims/README.md](briarwood/claims/README.md)
- [briarwood/execution/registry.py](briarwood/execution/registry.py)
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) (lines 89-117, 160-229, 468-481, 557-584, 655-691, 694-714)
- [briarwood/agent/composer.py](briarwood/agent/composer.py) (lines 109-240, 333-486)
- [briarwood/agent/router.py](briarwood/agent/router.py) (lines 292-321)
- [briarwood/representation/agent.py](briarwood/representation/agent.py) (lines 189-286, 299-510)
- [briarwood/claims/representation/verdict_with_comparison.py](briarwood/claims/representation/verdict_with_comparison.py) (lines 88-107)
- [briarwood/local_intelligence/adapters.py](briarwood/local_intelligence/adapters.py) (lines 156-192)
- [briarwood/execution/executor.py](briarwood/execution/executor.py) (lines 289-364), [planner.py](briarwood/execution/planner.py) (lines 96-131)
- [api/pipeline_adapter.py](api/pipeline_adapter.py) (lines 651-676, 1266-1333, 1446)
- [briarwood/agent/llm_observability.py](briarwood/agent/llm_observability.py)

## Appendix B — README Drift Check (Job 1)

Run at session start.

- ✅ Clean: 30 READMEs verified (all entry-point paths/functions resolve, all "Last Updated: 2026-04-24")
- ⚠️ Drift detected: 0
- 📋 Missing: 13 modules under `briarwood/modules/` without READMEs (bull_base_bear, local_intelligence, macro_reader, market_analyzer, ownership_economics, property_data_quality, renovation_scenario, rental_ease, risk_constraints, security_model, teardown_scenario, town_aggregation_diagnostics, town_county_outlook). All are KEEP-as-internal-helper per [PROMOTION_PLAN.md](PROMOTION_PLAN.md). Not blocking.

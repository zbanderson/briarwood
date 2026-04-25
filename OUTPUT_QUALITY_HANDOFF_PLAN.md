# Output-Quality Handoff Plan — 2026-04-25

**Owner:** Zach
**Origin:** 2026-04-25 output-quality audit session ([AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md))
**Status:** Phase 1 (audit + observability) complete. Phase 2 (architectural fix) broken into cycles below.

This plan is the **canonical to-do list** for fixing the chat-tier output quality. Each cycle is a discrete handoff that should land as one logical change, with tests passing and a pause for browser verification before moving to the next. The plan is intentionally conservative — it would be tempting to bundle multiple cycles into one commit, and that's how things have broken in the past (per CLAUDE.md "Session Anti-Patterns").

---

## North-star problem statement

The chat-tier path most user queries take never builds a `UnifiedIntelligenceOutput` from a single full-cascade run. Each `tools.py` function (`get_value_thesis`, `get_cma`, `get_projection`, etc.) invokes the scoped executor with its own narrow plan. Live trace data showed:

- 33 module-execution events on a single BROWSE turn, but **only 10 distinct modules ran**
- `valuation` ran 5x, `carry_cost` ran 5x, `risk_model` ran 4x fresh (no cache reuse), `confidence` 5x fresh, `legal_confidence` 4x fresh
- **13 modules NEVER ran:** `arv_model`, `comparable_sales`, `current_value`, `hybrid_value`, `income_support`, `location_intelligence`, `margin_sensitivity`, `market_value_history`, `opportunity_cost`, `renovation_impact`, `scarcity_support`, `strategy_classifier`, `unit_income_offset`
- The composer LLM (4.08s) saw a narrow per-tool slice rather than the full unified output

Project owner framing: "if I ask Claude directly to underwrite a house, it shouldn't be better than the models we've spent a month developing."

The fix is two complementary moves:
1. **Consolidate per-tool execution into one chat-tier plan per turn** (so all relevant modules' outputs are co-resident).
2. **Add a Layer 3 LLM synthesizer** (so the prose layer has access to the full unified output, not a fragmented slice).

Detailed diagnostic in [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §9. Architectural decision in [DECISIONS.md](DECISIONS.md) "Chat-tier fragmented execution" 2026-04-25. Action items in [FOLLOW_UPS.md](FOLLOW_UPS.md) entries dated 2026-04-25.

---

## State of the repo at handoff

**Uncommitted changes (session of 2026-04-25):**
- `briarwood/agent/composer.py` + `tests/agent/test_composer.py` — `BRIARWOOD_STRICT_STRIP` flag + rewritten regen prompt (DECISIONS 2026-04-25 "Composer guardrails")
- `briarwood/agent/router.py` + `tests/agent/test_router.py` + `briarwood/agent/README_router.md` — price-analysis routes to DECISION (DECISIONS 2026-04-25 "Router")
- `briarwood/agent/turn_manifest.py` (new) + `tests/agent/test_turn_manifest.py` (new) — per-turn invocation manifest
- `briarwood/agent/llm_observability.py` — mirrors LLM ledger into manifest
- `briarwood/agent/dispatch.py` — wedge records 6 outcome paths
- `briarwood/agent/tools.py` — 25 public functions decorated with `@traced_tool()`
- `briarwood/execution/executor.py` — module-run + module-skip events; context propagation
- `api/main.py` — chat endpoint wraps every turn in `start_turn`/`end_turn`
- `api/pipeline_adapter.py` — `loop.run_in_executor` calls wrapped in `in_active_context`
- `briarwood/agent/README_dispatch.md` — orchestrator-coupling correction
- `DECISIONS.md` + `FOLLOW_UPS.md` — session entries
- `AUDIT_OUTPUT_QUALITY_2026-04-25.md` (new) — full audit doc with §9 live findings
- This file — the handoff plan

**No commits made.** User has standing preference (per CLAUDE.md) to commit only on explicit request. The next agent should ask whether to commit Phase 1 work as one unit before starting Cycle 1.

**Tests passing:** 27/27 turn manifest, 40/40 composer, 17/17 router. 1 pre-existing failure in `tests/agent/test_tools.py::PromoteUnsavedAddressTests` unrelated to this work (per DECISIONS.md 2026-04-24 router-fix entry's "28 pre-existing failures" note).

**To verify the manifest in your dev shell:**
```
export BRIARWOOD_TRACE=1
export BRIARWOOD_CLAIMS_ENABLED=true
export BRIARWOOD_STRICT_STRIP=off
python scripts/dev_chat.py
```

---

## Cycles

### Cycle 1 — Promote `comparable_sales` to the scoped registry — LANDED 2026-04-25 (narrowed)

**Status update (2026-04-25):** When this plan was drafted, the registry-promotion premise was already stale — `comparable_sales` had been promoted in commit `37df9f8` (Handoff 3, 2026-04-24). Discovered during Cycle 1 execution; flagged per CLAUDE.md "surface contradictions, do not silently reconcile." Cycle 1 was narrowed (Option B from the cycle-execution discussion) to the two cleanup items that remained, and the graft retirement was deferred to its own existing FOLLOW_UPS entry.

**What landed (commit `2cb1f3e`):**
- `MODULE_CACHE_FIELDS["comparable_sales"]` added to [`briarwood/execution/executor.py`](briarwood/execution/executor.py). Mirrors `valuation`'s property-field set; rent assumptions (`back_house_monthly_rent`, `unit_rents`) included for the income-adjusted hybrid decomposition; `market` intentionally empty (comparable_sales consumes market_value_history transitively via its internal MarketValueHistoryModule).
- [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) §Known Rough Edges → Structural bullet rewritten. Previously claimed "ComparableSalesModule is not in the scoped registry," contradicting the same doc's row at line 91 ("Promoted ... in Handoff 3"). Now leads with the registry promotion and explains why the graft is still in place (legacy-shape consumer in `_iter_comps`).

**What was already done before this cycle:**
- `comparable_sales` registered in [`briarwood/execution/registry.py:270-284`](briarwood/execution/registry.py#L270-L284). `depends_on=[]`, `required_context_keys=["property_data"]`. Done in `37df9f8`.
- [`briarwood/modules/README_comparable_sales.md`](briarwood/modules/README_comparable_sales.md) and [`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) already documented the scoped path. Done in Handoff 3.

**What was deferred (not blocking Cycle 2):**
- Graft retirement at [`briarwood/claims/pipeline.py:62-88`](briarwood/claims/pipeline.py#L62-L88). Requires updates to [`briarwood/claims/synthesis/verdict_with_comparison.py:413-425`](briarwood/claims/synthesis/verdict_with_comparison.py#L413-L425) `_iter_comps` because the scoped runner emits `ModulePayload.data.legacy_payload.comps_used` while the graft writes the legacy `payload.comps_used` shape. Tracked as the standalone FOLLOW_UPS entry *"Retire the ad-hoc `ComparableSalesModule()` graft in claims/pipeline.py"* 2026-04-24.

**Cycle 2 unblocked.** Cycle 2 ("Consolidated chat-tier orchestrator entry") can now invoke `run_comparable_sales` via the executor as planned — that was Cycle 1's only true blocker.

**Tests at landing time:** 138 passed (5 subtests) across `tests/test_execution_v2.py`, `tests/test_execution_normalization.py`, `tests/test_orchestrator.py`, `tests/claims/`, `tests/test_shadow_intelligence.py`, `tests/representation/`.

---

### Cycle 2 — Consolidated chat-tier orchestrator entry — LANDED 2026-04-25 (commit `8290966`)

**Status:** Landed. Live BROWSE smoke run produced 23 distinct modules in `modules_run`, each running exactly once (vs. the audit's 33 events / 10 distinct / `valuation`-x-5 baseline). All four dormant modules from §9.3 (`comparable_sales`, `location_intelligence`, `strategy_classifier`, `arv_model`) fire. `unified_output` populated with a deterministic `decision`/`confidence`/etc. — Cycle 3 will hand this to `handle_browse`.

**What landed:**
- New module [`briarwood/execution/module_sets.py`](briarwood/execution/module_sets.py) — `ANSWER_TYPE_MODULE_SETS` keyed by `AnswerType` plus a `modules_for_answer_type` helper.
- New function `run_chat_tier_analysis(...)` in [`briarwood/orchestrator.py`](briarwood/orchestrator.py).
- 8 new tests in `tests/test_orchestrator.py::RunChatTierAnalysisTests` pinning the per-AnswerType module-set membership, the LOOKUP / CHITCHAT short-circuit, the once-per-turn invariant, and the explicit-vs-synthesized parser_output paths.
- New FOLLOW_UPS entry "in_active_context is not safe under concurrent thread-pool callers" 2026-04-25 (the reason Cycle 2 ships with `parallel=False` default — the concurrency bug surfaced when the new function exercised the parallel executor with a non-trivial dependency level).

**Open design decisions (resolved):**
1. Separate function vs. parameter on `run_briarwood_analysis_with_artifacts` → **separate.** `run_chat_tier_analysis` is ~70 lines and reuses the existing helpers; folding it would have duplicated the LOOKUP short-circuit and the synthetic-parser-output handling into the existing function's caller path.
2. `ANSWER_TYPE_MODULE_SETS` location → **new file** at `briarwood/execution/module_sets.py`, single-responsibility.
3. Parallel by default → **NO for Cycle 2.** The bug above blocks it. Default is `parallel=False`; flip once the wrapper is fixed (FOLLOW_UPS entry).
5. Properties not pre-computed → punted to Cycle 3 testing per the open-decisions list.
6. Module sets are starting points → reaffirmed in the new `module_sets.py` docstring.

**Original scope below (left for reference):**

**Scope:**
- Define `ANSWER_TYPE_MODULE_SETS` constant somewhere stable (probably `briarwood/orchestrator.py` or a new `briarwood/execution/module_sets.py`):

  ```python
  ANSWER_TYPE_MODULE_SETS: dict[AnswerType, frozenset[str]] = {
      AnswerType.BROWSE: frozenset({  # full first-read cascade
          "valuation", "carry_cost", "risk_model", "confidence",
          "legal_confidence", "comparable_sales", "location_intelligence",
          "town_development_index", "market_value_history", "current_value",
          "hybrid_value", "scarcity_support", "income_support",
          "rental_option", "rent_stabilization", "hold_to_rent",
          "resale_scenario", "renovation_impact", "arv_model",
          "margin_sensitivity", "opportunity_cost", "strategy_classifier",
          "unit_income_offset",
      }),
      AnswerType.DECISION: frozenset({...}),  # same as BROWSE for now
      AnswerType.PROJECTION: frozenset({
          "valuation", "carry_cost", "comparable_sales", "resale_scenario",
          "renovation_impact", "arv_model", "hold_to_rent",
          "town_development_index", "rental_option", "hybrid_value",
          "market_value_history", "margin_sensitivity",
      }),
      AnswerType.RISK: frozenset({
          "valuation", "risk_model", "legal_confidence", "confidence",
          "location_intelligence", "town_development_index",
      }),
      AnswerType.EDGE: frozenset({
          "valuation", "comparable_sales", "scarcity_support",
          "strategy_classifier", "town_development_index", "hybrid_value",
          "location_intelligence",
      }),
      AnswerType.STRATEGY: frozenset({
          "strategy_classifier", "hold_to_rent", "rental_option",
          "opportunity_cost", "carry_cost", "valuation", "hybrid_value",
      }),
      AnswerType.RENT_LOOKUP: frozenset({
          "rental_option", "rent_stabilization", "income_support",
          "scarcity_support", "hold_to_rent", "location_intelligence",
      }),
      AnswerType.LOOKUP: frozenset(),  # single-fact retrieval; no cascade
      # SEARCH, COMPARISON, RESEARCH, VISUALIZE, MICRO_LOCATION, CHITCHAT
      # are intentionally absent — those tiers don't run a property cascade.
  }
  ```

  These are starting points to tune with traces, not a fixed contract.

- Add `run_chat_tier_analysis(property_data: dict, answer_type: AnswerType, user_input: str, *, llm: LLMClient | None = None, prior_context: list | None = None) -> dict[str, Any]` to `briarwood/orchestrator.py`. Internally:
  - Picks module set from `ANSWER_TYPE_MODULE_SETS[answer_type]`.
  - Builds an `ExecutionPlan` for that subset (use existing `build_execution_plan` from `briarwood/execution/planner.py`).
  - Runs `execute_plan(plan, context, registry, ...)`.
  - Calls the deterministic synthesizer (`briarwood/synthesis/structured.py::build_unified_output`) on the result.
  - Returns the same artifact dict shape `run_briarwood_analysis_with_artifacts` returns: `{routing_decision, property_summary, module_results, unified_output, interaction_trace}`.

- Reuse helpers (`build_property_summary`, the cache infra at `briarwood/orchestrator.py:171`) so we don't fork the analysis pipeline.

- Decision: when `module_set` is empty (e.g., LOOKUP), `run_chat_tier_analysis` should return early with a minimal artifact — no execution, no synthesis. Document this contract.

**Tests:**
- `tests/test_orchestrator.py` — new test class `RunChatTierAnalysisTests`. Cover: BROWSE module set runs the full cascade; PROJECTION runs the projection subset; RISK runs the risk subset; LOOKUP returns early; verify `unified_output` is populated.
- Confirm with the per-turn manifest: ONE plan, no duplication of any module.

**Verification:**
- All existing tests still green (`tests/`).
- Run `BRIARWOOD_TRACE=1` against a fixture in isolation (no handler wiring yet) — expect to see one consolidated plan run.

**Trace:** [FOLLOW_UPS.md](FOLLOW_UPS.md) "Consolidate chat-tier execution" 2026-04-25 step 2.

**Estimate:** 2-3 hours.
**Risk:** Low — purely additive. No existing call sites change yet.

---

### Cycle 3 — Wire `handle_browse` to use the consolidated path — LANDED 2026-04-25 (commit `ca94d2f`)

**Status:** Landed. First user-visible change of the architectural fix. For a saved property, `handle_browse` now runs ONE consolidated execution plan with all 23 scoped modules instead of the per-tool fragmentation pattern (5+ overlapping plans, 33 events, 10 distinct modules, 13 dormant) the audit's §9.3 captured.

**What landed:**
- New helper `_browse_chat_tier_artifact(pid, user_text, overrides)` in `briarwood/agent/dispatch.py` — loads inputs.json + applies overrides + validates/prepares PropertyInput + calls `run_chat_tier_analysis(..., AnswerType.BROWSE, ...)`. Returns `None` on any failure so the legacy per-tool path can take over (graceful degradation).
- New inline view-extraction helpers `_browse_projection_from_artifact`, `_browse_strategy_fit_from_artifact`, `_browse_rent_payload_from_artifact` — pull the same field shapes from `module_results["outputs"]` that `tools.get_projection` / `get_strategy_fit` / `get_rent_estimate` produced. Downstream consumers (`_populate_browse_slots`, `compose_browse_surface`) unchanged.
- `handle_browse` rewritten: calls the chat-tier artifact once, then on success builds `brief` via `build_property_brief(pid, summary, unified_output)` and derives the views from the artifact's module outputs. The four per-tool routed runners (`get_property_brief`, `get_projection`, `get_strategy_fit`, `get_rent_estimate`) — the source of the per-tool plan duplication — are skipped.
- Kept (unchanged): `get_cma` (Engine B, live-Zillow), `get_property_enrichment` (external API), `get_property_presentation` (LLM advice), `search_listings` (neighbors), `get_property_summary`, `get_rent_outlook` (now passed the pre-computed `rent_payload` so it skips its internal routed run).
- 4 existing browse tests gain a single `_browse_chat_tier_artifact` → `None` patch so they exercise the legacy fallback path with their existing `get_property_brief` mocks. New test `test_browse_consolidated_chat_tier_path_skips_per_tool_routed_calls` pins the new contract.

**Net effect on a BROWSE turn for a saved property (vs. the pre-Cycle-3 baseline captured in the user's UI logs):**
- Module-execution events: ~33 → ~23. No `valuation` × 5 / `risk_model` × 4 fresh duplication.
- 13 dormant modules — `comparable_sales`, `location_intelligence`, `strategy_classifier`, `arv_model`, `current_value`, `hybrid_value`, `income_support`, `margin_sensitivity`, `market_value_history`, `opportunity_cost`, `renovation_impact`, `scarcity_support`, `unit_income_offset` — now fire and contribute to the unified output the composer reads.
- The composer's `structured_inputs` reflect the full `UnifiedIntelligenceOutput`. Prose richness still depends on Cycle 4 (Layer 3 LLM synthesizer) — the substrate is now in place but the prose layer is still the existing composer with its narrow framing.

**Out of scope (deferred to Cycle 5):**
- Per-tool function retirement. `get_property_brief`, `get_projection`, `get_strategy_fit`, `get_rent_estimate` remain in `tools.py` for the other handlers (handle_decision, handle_risk, etc.) that haven't been rewired yet.
- The legacy fallback path inside `handle_browse` itself. Will retire once the consolidated path has soak time across saved-property and unsaved-promotion flows.

**Browser verification (per the plan's pause requirement):**
- The user re-runs the dev stack and tests "what do you think of 1008 14th Ave, Belmar, NJ".
- Manifest assertion: `modules_run` should jump from ~10 distinct to ~23, with `comparable_sales`, `location_intelligence`, `strategy_classifier`, `arv_model` appearing.
- Prose may already feel richer because the composer now sees richer fields; if not, that's the Cycle 4 lever.

**Tests at landing time:** 24/24 in `BrowseHandlerTests` + `SearchHandlerTests`; 498 passed in broader smoke (2 pre-existing failures unchanged: `tests/agent/test_tools.py::PromoteUnsavedAddressTests` and `tests/synthesis/test_structured_synthesizer.py::test_interaction_trace_attached`).

**Original scope below (for reference):**

**Scope:**
- Modify `handle_browse` at [`briarwood/agent/dispatch.py:4028`](briarwood/agent/dispatch.py#L4028).
- Replace the per-tool calls (`get_property_brief`, `get_value_thesis`, `get_cma`, `get_projection`, `get_strategy_fit`, `get_rent_estimate`, `get_rent_outlook`, `get_property_enrichment`, `get_property_presentation`) with **one call** to `run_chat_tier_analysis(property_data, AnswerType.BROWSE, user_input, llm=llm)`.
- Read what the handler needs from the returned `unified_output` rather than from per-tool dicts.
- Pass the unified output to the composer as its `structured_inputs`.
- Keep `get_property_summary` (cheap fact retrieval) — it's not a cascade tool.
- Keep `get_property_presentation` for now ONLY if it has user-visible chart-selection behavior we can't reproduce yet (verify; if it's just LLM-based visual advice, the Layer 3 synthesizer in Cycle 4 will subsume it).

**Tests:**
- Existing dispatch tests (`tests/agent/test_dispatch.py`) must continue to pass.
- Add a fixture-based test: given a saved property, `handle_browse` should produce non-empty prose AND the per-turn manifest (when active) should show ONE consolidated plan with `comparable_sales` and `location_intelligence` in `modules_run`.

**Verification (BROWSER):**
- Run `BRIARWOOD_TRACE=1`. Send "what do you think of 1008 14th Ave, Belmar, NJ".
- The `[turn]` line should show:
  - `tool_calls`: significantly shorter list (or empty if all per-tool calls removed)
  - `modules_run`: ~20+ distinct modules, each running once (no `valuation`-x-5)
  - `comparable_sales`, `location_intelligence`, `strategy_classifier`, `arv_model` should all appear
- Prose may already feel richer because the composer sees full unified output instead of fragments.
- **PAUSE FOR USER VERIFICATION** before moving to Cycle 4.

**Trace:** [FOLLOW_UPS.md](FOLLOW_UPS.md) "Consolidate chat-tier execution" 2026-04-25 step 3 (rollout to handle_browse first).

**Estimate:** 1-2 hours.
**Risk:** Medium — changes user-facing prose for BROWSE.

---

### Cycle 4 — Layer 3 LLM synthesizer — LANDED 2026-04-25 (commit `fb23152`)

**Status:** Implementation complete, awaiting browser verification. The Layer 3 LLM synthesizer reads the full `UnifiedIntelligenceOutput` produced by Cycle 2/3's consolidated chat-tier path and writes 3-7 sentences of intent-aware prose, replacing (with fallback) the existing narrow-slice composer for BROWSE turns.

**What landed:**
- New module [`briarwood/synthesis/llm_synthesizer.py`](briarwood/synthesis/llm_synthesizer.py) — `synthesize_with_llm(*, unified, intent, llm, max_tokens=360) -> tuple[str, dict]`. Single LLM call wrapped in `complete_text_observed(surface="synthesis.llm", ...)` so it shows up distinctly in the per-turn manifest. Numeric guardrail via `api.guardrails.verify_response` over the full unified output. Single regen attempt on threshold-level violations (with grounded-or-omit free-voice prompt); regen kept only when violations strictly decrease. Returns `("", {empty: True, reason: ...})` for budget cap, blank draft, exception, or missing inputs.
- 10 new unit tests in [`tests/synthesis/test_llm_synthesizer.py`](tests/synthesis/test_llm_synthesizer.py) — clean draft pass-through, ledger metadata, regen on ungrounded numbers, regen kept-only-when-better, missing-llm short-circuit, empty-unified short-circuit, blank LLM response, exception handling, intent payload serialization, system prompt regression (numeric grounding rule pinned).
- `handle_browse` now calls the synthesizer when (a) `chat_tier_artifact` is populated AND (b) `llm` is non-None, using `briarwood.intent_contract.build_contract_from_answer_type(decision.answer_type.value, decision.confidence)` for the contract. Synthesizer prose replaces `compose_browse_surface` output; on empty prose, the existing composer fallback fires. 2 new integration tests in `tests/agent/test_dispatch.py::BrowseHandlerTests` pin the contract.

**Net effect on a BROWSE turn (when llm is provided and a saved property is found):**
- The per-turn manifest's `llm_calls` should now show TWO LLM calls minimum: `agent_router.classify` + `synthesis.llm`. (Plus `synthesis.llm.regen` if the verifier flagged the first draft.) `composer.draft` should be absent on the happy path; `presentation_advisor` may still produce its hidden LLM call until the existing follow-up fix lands.
- Prose substrate jumps from the composer's narrow `_browse_surface_payload` slice (~7 fields from brief + 4 session view dicts) to the full `UnifiedIntelligenceOutput` (~17 named fields including `value_position`, `key_value_drivers`, `key_risks`, `trust_flags`, `optionality_signal`, `primary_value_source`, plus the 23 modules' outputs the synthesizer can reference via the unified output's `supporting_facts.selected_modules` list).
- The numeric guardrail is enforced on the synthesizer output the same way the composer enforces it — `verify_response` checks every cited number against grounded values.

**Out of scope (deferred):**
- Per-tier system prompt variations. Cycle 4 ships one prompt that branches via the intent contract (`if intent.answer_type == "browse" / "decision" / "risk" / ...`). Future tuning may split per tier.
- Anthropic provider routing. The composer's `_resolve_llm_for_tier` swaps in Anthropic for narrative tiers when configured; the synthesizer uses whatever `llm` the caller passes. Switching providers is one line plus an env-var read once we want to experiment.
- Wedge-aware behavior. When `BRIARWOOD_CLAIMS_ENABLED=true` and a DECISION turn produces a `VerdictWithComparisonClaim` via the wedge, the existing claim renderer handles prose. Layer 3 fills the gap for everything else (BROWSE, DECISION fall-through, etc.).

**Verification (browser):**
- Run the dev stack with `llm` configured. Send "what do you think of 1008 14th Ave, Belmar, NJ".
- Expected `[turn]` JSON: `llm_calls` includes `synthesis.llm` (and possibly `.regen`); `modules_run` still shows the 23-module consolidated plan from Cycle 3; the prose itself should feel more substantive — the synthesizer can lead with the buy/pass framing the user actually asked, weave in comp-anchor language, name specific risks and trust gaps, mention strategy classification and optionality if applicable.
- If prose comes back too long or too short, tune the system prompt or the `max_tokens` knob.

**Tests at landing time:** 10/10 in `tests/synthesis/test_llm_synthesizer.py`; 26/26 in `BrowseHandlerTests` (incl. 2 new for Cycle 4); broader smoke pending at the time of this update.

**Original scope below (for reference):**

**Scope:**
- New module: `briarwood/synthesis/llm_synthesizer.py`.
- Function: `synthesize_with_llm(unified: UnifiedIntelligenceOutput, intent: IntentContract, llm: LLMClient, *, tier: str = "decision_summary") -> tuple[str, dict[str, Any]]`. Returns `(prose, verifier_report)` mirroring the composer's `complete_and_verify` shape.
- Prompt design: read the full unified output as JSON, the intent contract as JSON, write 3-7 sentences of intent-aware prose. Free voice (per the loosened guardrails of the composer change). Numeric guardrail enforced via `api/guardrails::verify_response` over the full unified output as `structured_inputs`.
- Goes through `complete_text_observed` so the LLM call shows up in the manifest.
- Surface name in the ledger: `synthesis.llm`.

- Modify `handle_browse` to call `synthesize_with_llm` AFTER `run_chat_tier_analysis` returns. The synthesizer's prose becomes the handler's return value (replacing the composer's narrow-input call for this tier).

- The composer is NOT removed — keep it as a fallback when (a) `llm is None` or (b) `synthesize_with_llm` raises / returns empty. Per CLAUDE.md "Don't add error handling for scenarios that can't happen" — only add the fallback if testing shows it's needed.

**Tests:**
- `tests/synthesis/test_llm_synthesizer.py` (new). Cover: ScriptedLLM returning canned text → that text reaches the user; numeric correctness preserved (verifier's `ungrounded_number` rule still fires); prompt-content regression tests pinning the "intent-aware, full-output" framing.
- Integration: `handle_browse` end-to-end produces prose that uses fields from the full unified output.

**Verification (BROWSER):**
- Same query: "what do you think of 1008 14th Ave, Belmar, NJ".
- The trace should show TWO LLM calls minimum: `agent_router.classify` + `synthesis.llm`. Possibly also `composer.draft` if the composer is still called for some sub-step (or zero composer calls if the synthesizer subsumes it).
- Prose should feel substantively richer — should mention comp-derived value range, location signals, strategy fit, optionality (ADU / multi-unit signals if applicable).
- **PAUSE FOR USER VERIFICATION.**

**Trace:** [FOLLOW_UPS.md](FOLLOW_UPS.md) "Layer 3 LLM synthesizer" 2026-04-25.

**Estimate:** 2-3 hours.
**Risk:** Medium — prose quality is the only verification criterion. The prompt may need iteration.

---

### Cycle 5 — Roll out to remaining handlers — LANDED 2026-04-25 (commits `1f8ab6a`, `6b861e9`, `d3293a1`, `3811dbf`, `c589635`, `a429d88`)

**Status:** All six chat-tier handlers (BROWSE from Cycle 3+4, plus PROJECTION / RISK / EDGE / STRATEGY / RENT_LOOKUP / DECISION from Cycle 5a-f) now use the consolidated chat-tier path and the Layer 3 LLM synthesizer. The previous live-trace gap — STRATEGY turns with `modules_run: []`, RISK turns running only 5 modules, BROWSE follow-ups bypassing the synthesizer via the comp-set → EDGE rewrite — is now closed for saved properties across every tier with a property cascade.

**What landed:**

| Sub-cycle | Handler | Commit | Rewire scope |
|---|---|---|---|
| 5a | `handle_projection` | `1f8ab6a` | Full: artifact load + projection-from-artifact + synthesizer (default path) |
| 5b | `handle_risk` | `6b861e9` | Full: artifact load + risk-profile-from-artifact + synthesizer (default path); trust mode keeps `compose_section_followup` |
| 5c | `handle_edge` | `d3293a1` | Minimal: synthesizer for default path only; comp_set / entry_point / value_change keep `compose_section_followup` |
| 5d | `handle_strategy` | `3811dbf` | Full: artifact load + strategy_fit-from-artifact + synthesizer |
| 5e | `handle_rent_lookup` | `c589635` | Full: artifact load + rent_payload-from-artifact + strategy_fit-from-artifact + synthesizer (default path); rent_workability mode keeps `compose_section_followup` |
| 5f | `handle_decision` | `a429d88` | Minimal: artifact pre-load (warms `_SCOPED_MODULE_OUTPUT_CACHE` for the dense per-tool block) + synthesizer for the final `decision_summary` composer; per-tool calls and wedge unchanged |

**Pattern across all six:**
1. Generalized `_browse_chat_tier_artifact` into `_chat_tier_artifact_for(pid, text, overrides, answer_type)` so each handler picks its tier's module set.
2. Each handler calls the helper near the top, after pid resolution and overrides extraction.
3. Per-tool view reads (`get_projection`, `get_strategy_fit`, `get_rent_estimate`, `get_risk_profile`) project from the artifact via existing helpers (`_browse_projection_from_artifact`, `_browse_strategy_fit_from_artifact`, `_browse_rent_payload_from_artifact`, `_browse_risk_profile_from_artifact`) when the artifact is populated. Legacy per-tool calls fall through when the artifact is None.
4. Final composer call → `synthesize_with_llm` first; existing tier-specific composer is the fallback.
5. Section-followup composers (trust, downside, comp_set, entry_point, value_change, rent_workability) keep their tight `compose_section_followup` calls — full unified output would distract from the section's specific question.

**Out of scope (deferred to Cycle 6):**
- Full handle_decision per-tool elimination. The wedge fall-through still calls PropertyView.load + get_cma + get_projection + get_risk_profile + get_strategy_fit + get_rent_estimate. They now all hit cache thanks to the artifact pre-load, so the duplicate runs are gone, but the call sites themselves remain. Replacing them with artifact-derived view builders is its own refactor.
- Section followup composers staying with `compose_section_followup` is a judgment call; Cycle 6 may revisit if traces show those followup paths producing thin or repetitive prose.
- Per-handler integration tests for the new synthesizer paths beyond what Cycle 5a added (`ProjectionHandlerTests`). The other handlers are covered by their existing tests + the artifact-helper tests already in place; new synthesizer-path tests can be added incrementally as needed.

**Browser verification expectations:**
- BROWSE turns: same as Cycle 4 (synthesis.llm fires; composer.draft skipped). Confirmed working.
- PROJECTION turns: synthesis.llm replaces compose_structured_response. Module cache hits across the cascade.
- RISK turns: synthesis.llm replaces complete_and_verify (default path). Trust-gap follow-ups still use compose_section_followup.
- EDGE turns (incl. comp-set rewrites): synthesis.llm replaces complete_and_verify on the default path. comp_set_mode / entry_point / value_change still use compose_section_followup.
- STRATEGY turns: synthesis.llm replaces complete_and_verify. The `modules_run: []` baseline is gone — STRATEGY now executes the full strategy module set.
- RENT_LOOKUP turns: synthesis.llm replaces compose_contract_response. rent_workability follow-ups still use compose_section_followup.
- DECISION turns (wedge fall-through): synthesis.llm replaces the final decision_summary composer; the question-specific decision_value composer remains; per-tool block now hits module cache thanks to the artifact pre-load.

**Tests at landing time:** 79/79 in `tests/agent/test_dispatch.py` after each sub-cycle.

**Original scope below (for reference):**

**Scope.** Apply the Cycle 3+4 pattern (consolidated execution + synthesizer) to:
- `handle_projection` ([`dispatch.py:3130`](briarwood/agent/dispatch.py#L3130))
- `handle_risk` ([`dispatch.py:3473`](briarwood/agent/dispatch.py#L3473))
- `handle_edge` ([`dispatch.py:3654`](briarwood/agent/dispatch.py#L3654))
- `handle_strategy` ([`dispatch.py:3921`](briarwood/agent/dispatch.py#L3921))
- `handle_rent_lookup` ([`dispatch.py:2922`](briarwood/agent/dispatch.py#L2922))

**Order of operations:** one handler per commit. Pause between each for browser verification.

**LOOKUP and other tiers:** intentionally NOT in this cycle. LOOKUP is fact-retrieval and shouldn't run a cascade. SEARCH, COMPARISON, RESEARCH, VISUALIZE, MICRO_LOCATION, CHITCHAT have their own non-cascade flows.

**DECISION** is partly handled by the wedge today. Two paths needed:
- Wedge enabled + archetype matches → wedge runs as today (no change).
- Wedge falls through OR not enabled → consolidated path + synthesizer.
The fall-through path likely benefits most from this work — it's the legacy DECISION mode.

**Tests:** Existing dispatch tests for each handler. Add per-handler integration test verifying consolidated execution.

**Verification:** Browser. One handler at a time. Watch the manifest for each.

**Estimate:** 30-60 min per handler, 5 handlers = 2.5-5 hours total.
**Risk:** Medium per handler. Lower if Cycles 3-4 went smoothly.

---

### Cycle 6 — Cleanup + documentation closeout — RE-SCOPED 2026-04-25

**Status:** Original scope was "general cleanup," but Cycles 1-5 closed several items along the way (the audit-doc reconciliation in Cycle 1, the `get_cma` leak fix between Cycles 4 and 5, and the doc updates after each sub-cycle). Updated scope below tracks what's actually still open.

**Open items:**
- `presentation_advisor` LLM call: route through `complete_structured_observed` so its ~3s LLM call shows up in the per-turn manifest's `llm_calls` list. See [FOLLOW_UPS.md](FOLLOW_UPS.md) "presentation_advisor bypasses the shared LLM observability ledger" 2026-04-25.
- `tools.py` orphan sweep: identify functions that are no longer called by any handler after Cycle 3+5, mark for deferred removal or delete. Likely candidates: `get_property_brief` (handle_browse uses `build_property_brief` from artifact now), the per-tool runners that handlers replaced. Audit before removing.
- Per-module cache leak (`confidence`, `legal_confidence`, `risk_model` re-running fresh across turns even when inputs are identical). See [FOLLOW_UPS.md](FOLLOW_UPS.md) "Module-result caching at the per-tool boundary is leaky" 2026-04-25.
- `in_active_context` concurrency fix so `run_chat_tier_analysis` can default `parallel=True`. See [FOLLOW_UPS.md](FOLLOW_UPS.md) "in_active_context is not safe under concurrent thread-pool callers" 2026-04-25.

**Already closed during Cycles 1-5 (no longer in Cycle 6 scope):**
- ~~Update `briarwood/agent/README_dispatch.md`~~ — done in Cycles 3, 4, 5 doc commits.
- ~~Update `ARCHITECTURE_CURRENT.md`~~ — done in Cycles 2, 3, 4 doc commits.
- ~~`run_chat_tier_analysis` docstring~~ — done in Cycle 2 commit `8290966`.

**Tests:** No new tests beyond the per-fix regression tests in each follow-up resolution.

**Estimate (re-scoped):** 1-2 hours total across the three FOLLOW_UPS items above.
**Risk:** Low for the observability + orphan sweep; Low-Medium for the cache leak (touches `MODULE_CACHE_FIELDS` which affects every chat-tier turn).

---

## Phase 2 outcome — DONE 2026-04-25

The architectural fix is functionally complete. Live UI traces post-Cycle-5 confirm:

| Audit baseline (BROWSE turn 1, §9 of the audit doc) | Post-Cycle-5 |
|---|---|
| 33 module-execution events | 23 (one consolidated plan, no duplication) |
| 10 distinct modules ran | 23 distinct |
| 13 dormant modules | 0 dormant |
| `comparable_sales`, `location_intelligence`, `strategy_classifier`, `arv_model` | All firing |
| Composer LLM saw narrow per-tool slice | `synthesis.llm` sees full unified output |
| Duplicate `valuation × 5`, `risk_model × 4 fresh` | 0 within turn; cache hits across turns |

Cross-turn caching emerges as a positive side effect: consecutive BROWSE turns on the same property hit `_SCOPED_MODULE_OUTPUT_CACHE` for ~20 of 23 modules. Wall-time on follow-up BROWSE turns dropped from ~22s to ~14s in live UI smoke.

Definition of done evaluation against §"Definition of done for the architectural fix" below:

1. **BROWSE turn uses comparable_sales / location_intelligence / strategy_classifier + 5 other dormant modules** — ✅ confirmed.
2. **Manifest shows ONE consolidated plan, no `valuation × 5` duplication** — ✅ confirmed (and `get_cma` leak fix in commit `f018fc4` cleared the trailing 5 duplicates).
3. **PROJECTION turn references rental_option / hold_to_rent / opportunity_cost in prose** — ✅ available; subjective on prose-quality bar.
4. **RISK turn names specific risk_model / legal_confidence / location_intelligence findings** — ✅ available.
5. **"Briarwood beats plain Claude on underwriting" qualitative bar** — user judgment; user reported "the prose is significantly better" 2026-04-25.
6. **All changes traced** — yes, every commit has a OUTPUT_QUALITY_HANDOFF_PLAN reference.
7. **README discipline maintained** — yes, dated changelog entries in `briarwood/agent/README_dispatch.md`, `briarwood/synthesis/README.md`, `briarwood/representation/README.md`.
8. **Tests pass** — 513 passed in broader smoke after Cycle 5 with 2 pre-existing failures unchanged.

The plan's narrative loop closes: the audit's chat-tier fragmentation diagnosis → the consolidation work → live verification that the substrate is in place and the prose substrate is genuinely richer.

---

## Open design decisions (for the next agent's first session)

1. **Should `run_chat_tier_analysis` be a separate function, or a parameter on the existing `run_briarwood_analysis_with_artifacts`?** I lean separate — different default semantics (chat-tier doesn't need the synthesizer to be "required"). The existing function would stay for `runner_routed.py` (batch / pre-computation). But if the next agent prefers extending the existing entry to keep one code path, that's defensible.

2. **`ANSWER_TYPE_MODULE_SETS` location.** `briarwood/orchestrator.py` keeps it close to the consumer; a new `briarwood/execution/module_sets.py` keeps it separate. Mild preference for the new file (better single-responsibility), but either works.

3. **Should the consolidated path use parallel execution (`_execute_plan_parallel`) by default?** The orchestrator already supports it. Yes — chat-tier turns benefit most from parallelism since they run more modules. But verify the in-process module dependency DAG is well-formed (modules with `depends_on` populated correctly).

4. **Does the Layer 3 synthesizer need a tier-specific system prompt, or one prompt with intent-keyed instructions?** Probably one prompt that reads `intent_contract.answer_type` and adjusts framing. Simpler, less drift surface.

5. **What happens when `run_chat_tier_analysis` is called for a property that hasn't been pre-computed (no saved files)?** The current orchestrator path requires saved properties. The chat-tier path may need to handle "promote unsaved address" first. Verify this code path during Cycle 3 testing.

6. **Per-AnswerType module sets are starting points.** Tune them with traces. The next agent should be willing to update [FOLLOW_UPS.md](FOLLOW_UPS.md) and DECISIONS.md if a module set turns out to be wrong.

---

## Cycle ordering rationale

Cycle 1 first because Cycle 2 depends on `comparable_sales` being invokable via the executor.

Cycle 2 before Cycle 3 because we want the new path to land independently before any handler is rewired. If Cycle 2 has bugs, we find them in isolation.

Cycle 3 before Cycle 4 because the synthesizer needs full unified output to read. If Cycle 3 lands and the prose is already substantially better (richer composer inputs), we can defer Cycle 4 — that's a useful product signal.

Cycle 5 after Cycles 3 and 4 because the pattern needs to be proven on `handle_browse` before propagating. The other handlers also have tier-specific quirks worth attending to one at a time.

Cycle 6 last because cleanup makes sense after the architecture is stable.

---

## Boot prompt for the next Claude context window

Copy-paste the block below into the new Claude Code session. The CLAUDE.md orientation protocol will fire automatically; this prompt picks up from there.

```
I'm continuing a multi-session output-quality fix for the Briarwood
codebase. Phase 1 (audit + observability) is complete; Phase 2 is broken
into cycles in OUTPUT_QUALITY_HANDOFF_PLAN.md at the repo root. Please:

1. Run the standard CLAUDE.md orientation: read CLAUDE.md, run the
   readme-discipline drift check, verify ARCHITECTURE_CURRENT /
   GAP_ANALYSIS / TOOL_REGISTRY are present, read DECISIONS.md and
   FOLLOW_UPS.md in full.

2. Read OUTPUT_QUALITY_HANDOFF_PLAN.md end-to-end. That's the canonical
   to-do list for what we're working on.

3. Read AUDIT_OUTPUT_QUALITY_2026-04-25.md §9 for the live diagnostic
   findings that motivate Phase 2.

4. Tell me where we are in the cycle sequence (look at git log + git
   status to determine which cycles have been committed). Then tell me
   in 3-5 bullets what's been decided / what's queued / what's
   unresolved for the cycle we're about to work on.

5. Confirm: am I starting the next cycle now, or is there earlier work
   uncommitted that needs to be reviewed / committed first? Phase 1
   may still be uncommitted — if so, ask me whether to commit it as
   one logical unit before starting Cycle 1.

Do not begin code work until steps 1-5 are done and reported back.
```

That's the opening message. From there, the next Claude has everything it needs to pick up cleanly.

---

## Cross-references

- Audit doc: [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) (§9 has the live findings)
- Decisions log: [DECISIONS.md](DECISIONS.md) — search for entries dated `2026-04-25`
- Follow-ups: [FOLLOW_UPS.md](FOLLOW_UPS.md) — search for entries dated `2026-04-25`
- Module READMEs: `briarwood/modules/README_*.md` — read the ones for modules you're adding to a module set
- Per-turn manifest: `briarwood/agent/turn_manifest.py` (use `BRIARWOOD_TRACE=1` to see manifests in stderr)

---

## Definition of done for the architectural fix

The whole Phase 2 effort is done when:

1. A BROWSE turn for "what do you think of X" produces prose that demonstrably uses `comparable_sales`, `location_intelligence`, `strategy_classifier`, and at least 5 other modules currently dormant for chat-tier traffic.
2. The per-turn manifest shows ONE consolidated plan running per turn (no `valuation` × 5 duplication).
3. A PROJECTION turn ("what if we got it for $660 and rented it") references the rental_option / hold_to_rent / opportunity_cost outputs in prose.
4. A RISK turn ("what could go wrong") names specific risk_model / legal_confidence / location_intelligence findings.
5. The user's "Briarwood should beat plain Claude at underwriting" bar is met for at least one query type (BROWSE or DECISION). User judgment, not a metric.
6. All changes traced to FOLLOW_UPS / DECISIONS / this plan. No drive-by fixes.
7. README discipline maintained. Each contract change has a dated changelog entry on the affected README.
8. Tests pass. No regressions in `tests/agent/`, `tests/claims/`, `tests/synthesis/`, `tests/execution/`, `tests/test_orchestrator.py`.

---

## Notes for the next agent

- **The user prefers terse, structured updates between cycles.** End-of-cycle reports should fit in ~10-15 bullets.
- **The user often runs the dev server and tests in browser.** Don't skip the verification pause between cycles. The user's qualitative read is the truth-source for prose quality.
- **The 2026-04-25 README correction (DECISIONS entry) is load-bearing.** READMEs in this repo are handoffs between AI coding agents. Keep them current.
- **Don't trust the audit-doc's wiring map at face value.** The 2026-04-25 session corrected it twice. If the next agent finds another wiring miss, surface it.
- **The user's standing pref:** commit only when explicitly asked. Don't commit speculatively.

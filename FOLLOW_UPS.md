# Briarwood — Follow-Ups

Actionable code-level items surfaced during Handoff 1 README writing that were left untouched per Handoff 1's "no application code changes" rule. Each entry should be triagable: state the issue, the affected file paths, the impact, and a suggested approach. Resolve in subsequent handoffs.

Distinct from [DECISIONS.md](DECISIONS.md) (which captures product/architectural decisions and audit-doc drift) and [GAP_ANALYSIS.md](GAP_ANALYSIS.md) (which captures architectural gaps relative to the six-layer target). This file is for "go fix this" items that are smaller in scope than either of those.

---

## 2026-04-24 — Editor / synthesis threshold duplication has no mechanical guard

**Severity:** Medium — silent drift hazard for every claim-object-pipeline run.

**Files:**
- [briarwood/editor/checks.py:14-20](briarwood/editor/checks.py#L14-L20) — `VALUE_FIND_THRESHOLD_PCT`, `OVERPRICED_THRESHOLD_PCT`, `SMALL_SAMPLE_THRESHOLD`.
- [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py) — synthesizer counterparts.

**Issue:** The editor's check thresholds must agree with the synthesizer's; the editor explicitly does not import from synthesis to avoid a layering violation. If either side drifts, the editor either rejects valid claims or passes invalid ones — silently. The hazard is named in the comment at [checks.py:18-20](briarwood/editor/checks.py#L18-L20) but unenforced.

**Suggested fix:** Two options:
1. Move all three constants into a neutral module (e.g., `briarwood/claims/thresholds.py`) and import from both sides.
2. Add a test in `tests/editor/` that imports both modules and asserts equality of the three constants. Cheap, catches drift on every CI run.

---

## 2026-04-24 — Add a shared LLM call ledger

**Severity:** Medium — hard to improve prompts or model routing without comparable telemetry across call sites.

**Files:**
- [briarwood/agent/llm.py](briarwood/agent/llm.py)
- [briarwood/agent/composer.py](briarwood/agent/composer.py)
- [briarwood/agent/router.py](briarwood/agent/router.py)
- [briarwood/representation/agent.py](briarwood/representation/agent.py)
- [briarwood/claims/representation/verdict_with_comparison.py](briarwood/claims/representation/verdict_with_comparison.py)
- [briarwood/local_intelligence/adapters.py](briarwood/local_intelligence/adapters.py)

**Issue:** Router fallback turns, composer verifier reports, representation planning, claim prose, and local-intelligence extraction all expose different levels of LLM observability. There is no single inspectable record of prompt tier, provider/model, structured-vs-prose mode, latency, token/cost estimate, fallback reason, verifier outcome, or whether the user saw LLM prose versus deterministic fallback.

**Suggested fix:** Add a lightweight append-only LLM ledger, likely under `data/agent_feedback/` or `data/learning/`, with one JSONL event per LLM attempt. Record metadata only by default; gate full prompt/response capture behind an explicit debug env var to avoid leaking sensitive payloads. Thread it through the shared `LLMClient` boundary first, then add call-site context (`router`, `decision_summary`, `representation_plan`, etc.).

---

## 2026-04-24 — Extend router classification with telemetry-first `user_type`

**Severity:** Medium — blocks user-type-conditioned orchestration, Value Scout triggering, and tone adaptation.

**Files:**
- [briarwood/agent/router.py](briarwood/agent/router.py)
- [briarwood/agent/session.py](briarwood/agent/session.py)
- [briarwood/interactions/](briarwood/interactions/)
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py)
- [tests/agent/test_router.py](tests/agent/test_router.py)

**Issue:** `GAP_ANALYSIS.md` Layer 1 calls for intent plus user-type classification, but `RouterDecision` only carries `answer_type`. Existing interaction/persona hints accumulate separately and do not feed routing or dispatch. A cold-start misclassification could shape the session incorrectly if treated as authoritative too early.

**Suggested fix:** Add a conservative `user_type` field with values chosen by product decision before implementation. Recommended first pass: `unknown`/`pending` as the default plus low-confidence telemetry, not hard routing behavior. Plumb the field through `RouterDecision` and `Session`, collect examples, and only later let dispatch or Value Scout branch on it.

---

## 2026-04-24 — Prototype Layer 3 intent-satisfaction LLM in shadow mode

**Severity:** Medium — current synthesis can produce grounded prose while still failing to answer the user's actual intent.

**Files:**
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py)
- [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py)
- [briarwood/agent/composer.py](briarwood/agent/composer.py)
- [briarwood/routing_schema.py](briarwood/routing_schema.py)

**Issue:** The deterministic synthesizers assemble valid outputs, and the composer verifies numbers, but nothing asks whether the module set actually satisfied the routed intent. `GAP_ANALYSIS.md` Layer 3 names the missing LLM step: read the intent contract plus module outputs, then declare intent satisfied or identify missing facts/tools.

**Suggested fix:** Add a structured-output shadow evaluator that returns `{intent_satisfied, missing_facts, suggested_tools, explanation}` without changing user-visible behavior. Log results to the LLM ledger. Do not let it trigger re-orchestration until the evaluator has golden tests and retry bounds.

---

## 2026-04-24 — Route local-intelligence extraction through shared LLM boundary

**Severity:** Medium — the only LLM-backed extraction path sits outside shared provider, budget, retry, and telemetry conventions.

**Files:**
- [briarwood/local_intelligence/adapters.py](briarwood/local_intelligence/adapters.py)
- [briarwood/local_intelligence/config.py](briarwood/local_intelligence/config.py)
- [briarwood/agent/llm.py](briarwood/agent/llm.py)
- [briarwood/cost_guard.py](briarwood/cost_guard.py)
- [TOOL_REGISTRY.md](TOOL_REGISTRY.md)

**Issue:** `OpenAILocalIntelligenceExtractor` uses a direct OpenAI client and schema call. That gives it strong extraction structure, but it bypasses the central `LLMClient` abstraction and does not share the same provider routing, budget accounting, retry behavior, or call ledger that router/composer/representation should use.

**Suggested fix:** Either adapt `OpenAILocalIntelligenceExtractor` to accept/use the shared structured `LLMClient`, or explicitly create a local-intelligence-specific LLM adapter that still records cost/telemetry through the shared surfaces. Keep the existing validation pipeline intact.

---

## 2026-04-24 — Broaden Representation Agent triggering beyond the claims flag

**Severity:** Low — Layer 4 mostly exists, but only part of the app benefits from it.

**Files:**
- [briarwood/representation/agent.py](briarwood/representation/agent.py)
- [api/pipeline_adapter.py](api/pipeline_adapter.py)
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py)
- [briarwood/feature_flags.py](briarwood/feature_flags.py)

**Issue:** `GAP_ANALYSIS.md` Layer 4 says the Representation Agent substantially exists, but its use is still gated around the claim-object path while legacy synthesis emits charts directly from handlers. That means chart selection quality and LLM-vs-deterministic fallback behavior differ by execution path.

**Suggested fix:** Add a feature-flagged path that runs the Representation Agent for ordinary decision-tier turns after `UnifiedIntelligenceOutput` and module views are available. Start in shadow mode: compare selected charts to the currently emitted events, log mismatches, and only switch rendering once chart coverage is stable.

---

## 2026-04-24 — Two comp engines with divergent quality; CMA (Engine B) needs alpha-quality pass

**Severity:** High — the user-facing CMA (`get_cma`) is a key platform surface and does not currently meet the quality bar the product owner wants.

**Files:**
- [briarwood/agent/tools.py:1802](briarwood/agent/tools.py#L1802) — `get_cma` (Engine B; live-first)
- [briarwood/agent/tools.py:1834](briarwood/agent/tools.py#L1834) — `CMAResult` shape
- [briarwood/modules/comparable_sales.py:35](briarwood/modules/comparable_sales.py#L35) — `ComparableSalesModule` (Engine A; fair-value anchor)
- [briarwood/agents/comparable_sales/](briarwood/agents/comparable_sales/) — shared agent beneath Engine A (`ComparableSalesAgent`)
- [briarwood/agent/dispatch.py:2636-2637](briarwood/agent/dispatch.py#L2636-L2637) — `_CMA_RE` trigger
- [briarwood/agent/dispatch.py:3697-3699](briarwood/agent/dispatch.py#L3697-L3699) — separation rationale

**Issue:** Briarwood has two comp paths that were easy to conflate during Handoff 2b discovery: (A) `ComparableSalesModule` — saved comps, drives fair-value, appears in `value_thesis.comps`; (B) `get_cma` — live-Zillow-preferred, drives the user-facing "CMA" feature, appears in `session.last_market_support_view`. The separation is documented in dispatch.py but the two paths have independent quality trajectories. Engine B in particular has known gaps: it rides on `_live_zillow_cma_candidates` quality, falls back silently to saved comps, and does not apply Engine A's scoring / adjustment logic (`_score_comp`, `_proximity_score`, `_recency_score`, `_data_quality_score`, location/lot/income-adjusted range bucketing) to live rows. Engine A's own TODOs in TOOL_REGISTRY.md (cross-town comps, renovation premium pass-through, 15% sqft tolerance) also apply to the fair-value path.

**Suggested fix:** Two-step audit. (1) Map every CMA surface the user can hit ("run a CMA" text, Properties UI panels, agent-tool callers) and confirm which engine each one uses. (2) For Engine B, decide whether to unify with Engine A's scoring / adjustment logic or to keep it as a distinct live-only summary with its own quality bar. Either way, define the quality invariants explicitly: minimum comp count, maximum distance, age cap, confidence floor, and behavior when live returns empty. Do NOT do this in Handoff 2b or Handoff 3 — scope it as its own handoff after promotion is complete.

Surfaced during Handoff 2b — see [PROMOTION_PLAN.md](PROMOTION_PLAN.md) entry 1 (`comparable_sales` → PROMOTE, Engine A only).

---

## 2026-04-24 — Retire the ad-hoc `ComparableSalesModule()` graft in claims/pipeline.py

**Severity:** Low — mechanical cleanup; no user-facing impact.

**Files:**
- [briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88) — the post-hoc graft that today instantiates `ComparableSalesModule()` because "the scoped execution registry doesn't surface comparable_sales as a top-level module."

**Issue:** Handoff 3 added a scoped `comparable_sales` runner at [briarwood/modules/comparable_sales_scoped.py](briarwood/modules/comparable_sales_scoped.py) and registered it in [briarwood/execution/registry.py](briarwood/execution/registry.py). The graft in `claims/pipeline.py` is no longer necessary; it can route through the scoped tool to pick up the canonical error contract and planner integration.

**Suggested fix:** Replace the direct `ComparableSalesModule()` instantiation at `claims/pipeline.py:62-88` with `run_comparable_sales(context)` (or the equivalent entry in whatever execution harness claims uses). Verify field-name stability — the graft currently reads the legacy payload shape directly, which is preserved by `module_payload_from_legacy_result`, so the migration is a field-access adjustment rather than a contract rewrite. Out of scope for Handoff 3 — surfaced during the `comparable_sales` promotion per [PROMOTION_PLAN.md](PROMOTION_PLAN.md) entry 1 "Rules of Engagement — no drive-by fixes."

---

## 2026-04-24 — Decision sessions should grep-verify caller claims in real time

**Severity:** Medium — process fix, not a code bug. Prevents amendments-during-execution of the kind seen twice in Handoff 4.

**Files (evidence):**
- [PROMOTION_PLAN.md](PROMOTION_PLAN.md) entry 15 ("Scope limit" paragraph about `_score_*` helpers having active callers)
- [PROMOTION_PLAN.md](PROMOTION_PLAN.md) entry 6 ("resale_scenario replaces bull_base_bear")
- [DECISIONS.md](DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 15 scope-limit paragraph corrected"
- [DECISIONS.md](DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 6 decision corrected"

**Issue:** Handoff 2b's conversational decision session produced a plan that holds up on most entries but had two factual caller-premises turn out to be wrong during Handoff 4 execution:

1. **Entry 15 (`calculate_final_score` → DEPRECATE, scope-limit paragraph):** claimed `_score_*` helpers had active callers and should be preserved. Grep during H4-#2 execution found zero non-aggregator, non-test callers — the entire chain was dead code.
2. **Entry 6 (`bull_base_bear` → DEPRECATE):** claimed `resale_scenario` replaces `bull_base_bear`. Grep during H4-#3 execution found `resale_scenario_scoped.py:30` invokes `BullBaseBearModule().run()` as the core of its implementation — the scoped wrapper *composes* `bull_base_bear`, it does not replace it. Correct classification is KEEP-as-internal-helper.

Both amendments were required mid-execution. The pattern is specific: "plan claims X has/lacks callers → grep contradicts the claim." The failure mode is decision-by-reading versus decision-by-verification.

**Suggested fix:** Future PROMOTION_PLAN-style decision sessions (or any handoff that classifies modules as DEPRECATE, KEEP-as-helper, PROMOTE based on caller topology) should systematically run grep-verification of caller claims *during the session*, not defer that verification to the execution handoff. Concretely: for each classification that hinges on "X has no active callers" or "X replaces Y" or "X is consumed only by Z," run a grep across `briarwood/`, `tests/`, `api/`, and `eval/` for the claimed relationship and attach the grep output (or a summary of it) to the plan entry as evidence. This surfaces false premises while the classification is still open for discussion, rather than forcing mid-execution amendments.

This is not a criticism of Handoff 2b's specific judgment calls — those calls were mostly right and the two that weren't were judgment against the best information available at the time. The lesson is that decision-by-reading has a specific blind spot (callers the reader doesn't know about or forgets to check), and the fix is mechanical verification rather than more careful reading.

---

## 2026-04-25 — Consolidate chat-tier execution: one plan per turn, intent-keyed module set

**Severity:** High — this is the architectural lever for "Briarwood beats plain Claude on underwriting." Today, the modules are running but in a fragmented per-tool way that hides their output from the prose layer.

**Files (anchor points for the consolidation):**
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — handle_browse, handle_decision, handle_projection, handle_risk, handle_edge, handle_strategy, handle_rent_lookup
- [briarwood/agent/tools.py](briarwood/agent/tools.py) — `get_value_thesis`, `get_cma`, `get_projection`, `get_strategy_fit`, `get_rent_estimate`, `get_property_brief`, `get_rent_outlook`, `get_property_enrichment`, `get_property_presentation`
- [briarwood/orchestrator.py](briarwood/orchestrator.py) — `run_briarwood_analysis_with_artifacts` (already exists; runs only via the wedge or `runner_routed.py` today)
- [briarwood/execution/registry.py](briarwood/execution/registry.py) — 23 scoped modules
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) — `build_unified_output` (the deterministic synthesizer, fed by orchestrator outputs)

**Issue.** Per the live diagnostic in [DECISIONS.md](DECISIONS.md) "Chat-tier fragmented execution" 2026-04-25: a single BROWSE turn produced 33 module-execution events across at least 5 separate execution plans, with only 10 distinct modules actually running. 13 modules never ran — including `comparable_sales` (the comp engine), `location_intelligence`, `strategy_classifier`, `arv_model`, `hybrid_value`. The composer LLM that does fire (4s/turn on BROWSE) sees a narrow per-tool slice rather than the full `UnifiedIntelligenceOutput` the orchestrator would have produced.

**Suggested fix (multi-step):**

1. **Per-AnswerType module manifest.** Define which modules each chat-tier AnswerType actually needs:
   - BROWSE / DECISION → full set (~all 23 modules; this is the first-read or buy/pass cascade)
   - PROJECTION → valuation, comparable_sales, scenario modules, rent_stabilization, hold_to_rent, resale_scenario, town_development_index, rental_option, hybrid_value
   - RISK → valuation, risk_model, legal_confidence, confidence, location_intelligence
   - EDGE → valuation, comparable_sales, scarcity_support, strategy_classifier, town_development_index, hybrid_value
   - STRATEGY → strategy_classifier, hold_to_rent, rental_option, opportunity_cost, carry_cost, valuation
   - RENT_LOOKUP → rental_option, rent_stabilization, income_support, scarcity_support, hold_to_rent
   - LOOKUP → no modules (single-fact retrieval)
   - Specific subsets to be tuned with traces, but the principle is intent-keyed not all-or-nothing.

2. **New consolidated chat-tier orchestrator entry.** Either extend `run_briarwood_analysis_with_artifacts` (already in `briarwood/orchestrator.py`) to accept an explicit module-set override, OR add a new `run_chat_tier_analysis(property_data, answer_type, ...)` that selects the module set per (1), runs `build_execution_plan` + `execute_plan` once, and calls `build_unified_output`. Returns the same `UnifiedIntelligenceOutput` shape so consumers don't fork.

3. **Modify dispatch handlers to use the consolidated entry.** Instead of calling 5–10 individual `tools.py` functions that each invoke their own plan, each handler calls the consolidated entry once and reads what it needs from the resulting `UnifiedIntelligenceOutput`. Keep `tools.py` functions around for one-off uses (e.g., `get_property_summary` for cheap fact retrieval) but stop using them as the primary handler scaffolding.

4. **Roll out incrementally.** Start with `handle_browse` (highest-volume non-DECISION tier), verify the prose improves, then extend to `handle_projection`, `handle_risk`, etc. Pin per-handler regression tests.

5. **Surface the diagnostic.** Use `BRIARWOOD_TRACE=1` to verify each turn now runs ONE consolidated plan with no `valuation`-runs-5x duplication, and that previously-dormant modules (`comparable_sales`, `location_intelligence`, etc.) appear in `modules_run`.

**Out of scope here (separate FOLLOW_UPS):**
- Per-tool execution-plan caching tuning (why `risk_model` and `confidence` re-run 4-5x even when they should cache).
- The Layer 3 LLM synthesizer (separate entry below — consolidation is its prerequisite).

Surfaced during the 2026-04-25 output-quality audit handoff. Cross-ref [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §9.

---

## 2026-04-25 — Layer 3 LLM synthesizer: prose from full UnifiedIntelligenceOutput

**Severity:** High — this is the prose-layer companion to the consolidated execution above. Without it, even a fully-populated `UnifiedIntelligenceOutput` reaches the user as a brain dump or as the composer's narrow paraphrase.

**Files:**
- [briarwood/agent/composer.py](briarwood/agent/composer.py) — current prose composer (LLM-backed but with narrow per-tier `structured_inputs`)
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) — current deterministic synthesizer (no LLM, populates UnifiedIntelligenceOutput fields)
- [briarwood/claims/representation/verdict_with_comparison.py](briarwood/claims/representation/verdict_with_comparison.py) — claim-render LLM (only fires for wedge-eligible turns)
- [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 3 — target-state description

**Issue.** Today's prose layer has three modes:
1. **Wedge claim renderer** — LLM rewrites a narrow claim slice (only for DECISION/LOOKUP-with-pinned, only when `BRIARWOOD_CLAIMS_ENABLED=true`).
2. **Composer** — LLM paraphrases per-handler `structured_inputs` (a narrow slice the handler hand-built from `tools.py` outputs).
3. **Deterministic synthesizer** — no LLM; populates ~17 named fields on `UnifiedIntelligenceOutput` with f-string templates (the "robotic prose" source per [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §3).

None of these takes the FULL `UnifiedIntelligenceOutput` and asks an LLM "given this, what should I tell the user?" That is the Layer 3 role per [GAP_ANALYSIS.md](GAP_ANALYSIS.md) (line: "LLM that asks 'did we answer the user's intent?' and re-orchestrates if needed").

**Suggested fix:**

1. **New module: `briarwood/synthesis/llm_synthesizer.py`** (or add to existing `briarwood/synthesis/`). Single function: `synthesize_with_llm(unified: UnifiedIntelligenceOutput, intent: IntentContract, llm: LLMClient) -> str`. Reads the full unified output, the user's intent contract, and produces intent-aware prose. Goes through `complete_structured_observed` so the LLM call shows up in the manifest.

2. **Numeric guardrail.** Numbers cited in the LLM's prose must round to a value present in `unified` (the same rule the composer's verifier already enforces for its narrow inputs). Reuse the verifier infrastructure at `api/guardrails.py`.

3. **Wire into chat-tier handlers** after the consolidated execution above lands. The handler returns whatever the synthesizer produces.

4. **Co-existence with the wedge.** When the wedge fires (DECISION + claims enabled), keep the claim renderer — it's already producing good prose for the verdict-with-comparison archetype. The Layer 3 synthesizer fills the gap for everything else.

5. **Tone / framing.** This is the place where user-type conditioning eventually lands (per [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 1 product decisions on user_type). For initial cut, omit user-type and just use the answer_type + question_focus.

**Dependency.** Blocks on consolidated execution above. Without that, the synthesizer would have an empty or fragmented `UnifiedIntelligenceOutput` to work from.

**Cross-ref:** [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 3, [DECISIONS.md](DECISIONS.md) "Chat-tier fragmented execution" 2026-04-25, user-memory `project_llm_guardrails.md`.

---

## 2026-04-25 — `presentation_advisor` bypasses the shared LLM observability ledger

**Severity:** Low — same bug class as the existing `local_intelligence/adapters.py` entry. Cleanup, not user-facing.

**Files:**
- [briarwood/agent/presentation_advisor.py](briarwood/agent/presentation_advisor.py) — `advise_visual_surfaces`
- [briarwood/agent/llm_observability.py](briarwood/agent/llm_observability.py) — `complete_structured_observed`

**Issue.** The 2026-04-25 audit's live trace showed `get_property_presentation` taking ~3 seconds and emitting no LLM call records to the per-turn manifest. The tool calls `advise_visual_surfaces`, which uses the raw OpenAI client (`llm.complete_structured(...)`) directly rather than going through the observed wrapper. The LLM ledger and the per-turn manifest don't see this call, so cost / latency / success-rate telemetry for it is invisible.

**Suggested fix:** Wrap the call site in `presentation_advisor.py` with `complete_structured_observed(surface="presentation_advisor.advise", ...)` analogous to the router and composer wiring. Same pattern as the `local_intelligence/adapters.py` follow-up entry above, which is a sibling case.

Surfaced during 2026-04-25 output-quality audit handoff. Cross-ref [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §9.

---

## 2026-04-25 — Module-result caching at the per-tool boundary is leaky

**Severity:** Low-medium — efficiency, not correctness. Will be largely obviated when the consolidated execution above lands, but worth a note in case consolidation is delayed.

**Files:**
- [briarwood/execution/executor.py](briarwood/execution/executor.py) — `build_module_cache_key`
- [briarwood/execution/registry.py](briarwood/execution/registry.py) — `MODULE_CACHE_FIELDS` (per-module cache field list)

**Issue.** In a single BROWSE turn, the manifest showed `risk_model` running 4x fresh (no cache hits), `confidence` running 5x fresh, `legal_confidence` running 4x fresh — even though all 4-5 calls were within the same chat turn for the same property. Meanwhile `valuation` and `carry_cost` cached correctly (4 cache hits each after one fresh run). The cache key for `risk_model` / `confidence` / `legal_confidence` apparently includes context fields that vary between the per-tool execution plans, defeating reuse.

**Suggested fix.** Audit `MODULE_CACHE_FIELDS` for the three offenders (`risk_model` is at executor.py:59-69, `confidence` at 71-82). Likely culprit: a field is being read from `assumptions` or `market` that varies per-tool but shouldn't affect the module's output. Add per-module regression tests pinning cache hits across the per-tool boundary.

**Probably moot after consolidation.** If the chat-tier executes one plan per turn (per the consolidation entry above), each module runs at most once per turn and this caching issue doesn't bite. Keep this entry in case consolidation is delayed.

---

## 2026-04-25 — Audit router classification boundaries with real traffic

**Severity:** Medium — every LOOKUP/DECISION miss produces a one-line answer to a question that wanted analysis, which is the user's #1 complaint.

**Files (evidence):**
- [briarwood/agent/router.py:169-219](briarwood/agent/router.py#L169-L219) — `_LLM_SYSTEM` prompt
- [api/prompts/lookup.md](api/prompts/lookup.md) — "Reply in 1–2 sentences" contract
- [tests/agent/test_router.py](tests/agent/test_router.py) — `LLM_CANNED` + `PromptContentRegressionTests`

**Context:** The 2026-04-25 output-quality audit handoff caught one specific miss: "what is the price analysis for 1008 14th Ave, belmar, nj" was classified as `AnswerType.LOOKUP` (conf 0.60), which routed to `handle_lookup` (no wedge, no orchestrator), which obeyed its 1-2 sentence prompt and produced "The asking price for 1008 14th Avenue in Belmar, NJ, is $767,000." The user expected analysis, got one fact. The router prompt has been updated to route price-analysis phrasings to DECISION ([DECISIONS.md](DECISIONS.md) and [briarwood/agent/README_router.md](briarwood/agent/README_router.md) Changelog 2026-04-25).

**The pattern is broader than this one query.** The router uses gpt-4o-mini and a single shot of structured-output classification. Without traffic-driven feedback, intent boundaries that LOOK clear in the prompt drift in practice — the only signal we have is what the LLM produces, and we don't measure it. Cross-references the user-memory note "Intent tiers for single-property questions" (browse vs decision unlock on escalation) and "LLM guardrails are currently too tight" (loosen LLM invocation to generate training signal).

**Issue:** No mechanism exists to detect router classification misses in production traffic. Each miss is invisible until a user notices a thin response and complains. There is no log of "here's how each turn was classified, with what confidence, and what the user did next." The 2026-04-25 audit added one regression case; we'll keep adding them reactively unless we audit the prompt against a real corpus.

**Suggested fix:** Two complementary moves —

1. **Capture classification + outcome per turn** in the per-turn invocation manifest being added in the 2026-04-25 audit's Step 4. Specifically: log `answer_type`, `confidence`, `reason`, the user's text, and (when telemetry catches up) whether the user asked a follow-up that suggests the classification missed. This is observability, not a fix, but it gives us the corpus to audit against.

2. **Audit the prompt against ~20-30 saved real queries** when there's a corpus. Specifically look for boundary cases: "price"-bearing questions that should be DECISION not LOOKUP, "what about"-bearing questions (browse vs decision), "rent"-bearing questions (rent_lookup vs decision-with-rent-context), etc. Update the prompt's IMPORTANT MAPPINGS and Counter-example sections.

Out of scope for the immediate handoff — the immediate fix targeted only the price-analysis miss. The broader audit is queued for after Step 4 logging lands.

---

## 2026-04-25 — `get_cma` internally calls `get_value_thesis`, leaking 5 module re-runs into the chat-tier path

**Severity:** Medium — visible in the per-turn manifest as 5 trailing duplicate module-run events on every BROWSE turn (and likely every other tier that calls `get_cma`). Eliminates Cycle 3's "no duplication" goal until fixed.

**Files:**
- [briarwood/agent/tools.py:1829-1858](briarwood/agent/tools.py#L1829-L1858) — `get_cma` body. Line 1832 calls `get_value_thesis(property_id, overrides=overrides)` to pick up `subject_ask` and `fair_value_base`.
- [briarwood/agent/tools.py:1773](briarwood/agent/tools.py#L1773) — `get_value_thesis` body. Internally calls `run_routed_report`, which spins up a fresh `run_briarwood_analysis_with_artifacts` execution plan and runs ~5 modules (`valuation`, `risk_model`, `confidence`, `legal_confidence`, `carry_cost`) again.
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — `handle_browse` (Cycle 3) keeps `get_cma` because it produces Engine B comps for the user-facing CMA card. The transitive `get_value_thesis` call is the only remaining per-tool routed run inside the consolidated BROWSE path.

**Issue:** Cycle 3 of OUTPUT_QUALITY_HANDOFF_PLAN.md replaces the per-tool routed-runner fragmentation in `handle_browse` with a single `run_chat_tier_analysis` call. The 13 dormant modules now fire and the manifest shows 23 distinct modules in one consolidated plan. Five trailing duplicate runs remain — `valuation` (697ms fresh), `risk_model`, `confidence`, `legal_confidence`, `carry_cost` (cache hit) — because `get_cma` internally calls `get_value_thesis`, which kicks off its own `run_routed_report` despite the chat-tier artifact already containing every field that `get_value_thesis` produces (the comps live in `module_results["outputs"]["comparable_sales"]`; `fair_value_base` lives in `unified_output["value_position"]["fair_value_base"]`; `ask_price` is on the property summary).

The `valuation` module's cache key in `MODULE_CACHE_FIELDS` includes `market_history_*` fields, which appear to differ between the chat-tier execution context and the `get_value_thesis` execution context (synthetic vs. real `ParserOutput` may shape `_extract_execution_assumptions` paths differently, or `_SCOPED_MODULE_OUTPUT_CACHE` keying drifts). Worth investigating why the cache miss when the inputs should be identical.

**Suggested fix:** Two-step.

1. **Break the internal `get_cma` -> `get_value_thesis` coupling.** Add an optional `thesis_subject_ask` / `thesis_fair_value_base` (or `thesis_dict`) parameter to `get_cma`. When provided, skip the internal `get_value_thesis` call. The caller (`handle_browse` post-Cycle-3) already has these values in `chat_tier_artifact["unified_output"]["value_position"]` — pass them in. This eliminates the 5 trailing duplicates without changing Engine B's contract.
2. **Audit why `valuation` cache misses across the consolidated and routed paths** even when property structural fields are identical. Likely related to the broader `MODULE_CACHE_FIELDS` leaky-cache item already in this file (2026-04-25 "Module-result caching at the per-tool boundary is leaky"). May also overlap with the `valuation`-module market_history field plumbing — the chat-tier path's market_context snapshot may differ from the routed path's snapshot in subtle ways.

**Out of scope here:** the broader retirement of `get_value_thesis` itself, which other handlers (`handle_decision`, `handle_strategy`, `handle_browse`'s decision-value-thesis builder for DECISION turns at `dispatch.py:1055`) still rely on. That's Cycle 5 work.

Surfaced during Cycle 3 (commit `ca94d2f`) post-landing UI smoke. Cross-ref [OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md) Cycle 3 status block.

---

## 2026-04-25 — `in_active_context` is not safe under concurrent thread-pool callers

**Severity:** Medium — blocks turning on parallel execution for the chat-tier consolidated path. `run_chat_tier_analysis` (Cycle 2 of OUTPUT_QUALITY_HANDOFF_PLAN.md) currently defaults `parallel=False` because of this.

**Files:**
- [briarwood/agent/turn_manifest.py:332-336](briarwood/agent/turn_manifest.py#L332-L336) — `in_active_context`
- [briarwood/execution/executor.py:444](briarwood/execution/executor.py#L444) — call site `pool.map(in_active_context(_run_one), level)`

**Issue:** The decorator captures `ctx = contextvars.copy_context()` once at decoration time, then `wrapped(*args)` does `ctx.run(fn, *args)`. When the wrapped function is called from `pool.map(wrapped, level)` and the pool runs multiple workers concurrently, two workers attempt to enter the same `ctx` object and the second one raises `RuntimeError: cannot enter context: <Context> is already entered`. The bug is not exercised by any current production caller because `loop.run_in_executor(None, fn)` only fires one call per wrapper, and the existing `_execute_plan_parallel` callers use it with single-module dependency levels in their tests. The bug only fires when (a) `parallel=True` and (b) the dependency DAG contains a level with two or more independent modules — which is the case for every non-trivial module set in `briarwood/execution/module_sets.py::ANSWER_TYPE_MODULE_SETS`.

**Suggested fix:** Capture the parent context's variables at decoration time as a list of `(ContextVar, value)` pairs, then create a fresh empty `contextvars.Context()` per call inside `wrapped`, set the captured vars inside that fresh context, and run `fn` there. Sketch:

```python
def in_active_context(fn):
    snapshot = list(contextvars.copy_context().items())
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        ctx = contextvars.Context()
        def _runner():
            for var, value in snapshot:
                var.set(value)
            return fn(*args, **kwargs)
        return ctx.run(_runner)
    return wrapped
```

Add a regression test under `tests/agent/test_turn_manifest.py` that decorates a single function and runs it concurrently from multiple threads (or via `pool.map(wrapped, ['a', 'b', 'c'])`), asserts no `RuntimeError`, and asserts the manifest ContextVar is visible inside each worker.

**When this lands:** Flip `run_chat_tier_analysis(...)`'s `parallel` default to `True` in [briarwood/orchestrator.py](briarwood/orchestrator.py) and update the docstring + the Cycle 2 / Cycle 3 verification notes in [OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md). Cross-ref this entry from the plan.

Surfaced during 2026-04-25 Cycle 2 implementation (commit landing `run_chat_tier_analysis`).

---

## 2026-04-24 — Strip unreachable defensive fallback in `_classification_user_type`

**Severity:** Low — dead code, not a bug. Deferred to keep the router-schema bug fix surgical.

**Files:**
- [briarwood/agent/router.py:283-284](briarwood/agent/router.py#L283-L284) — `persona = result.persona_type or PersonaType.UNKNOWN` and the analogous `use_case_type` line.

**Issue:** After the 2026-04-24 `RouterClassification` schema fix (see DECISIONS.md same-dated entry), `persona_type` and `use_case_type` are required on the Pydantic model with no default. If the LLM omits either field, `schema.model_validate` raises `ValidationError` and `complete_structured` returns `None` before `_classification_user_type` is reached. The `or PersonaType.UNKNOWN` / `or UseCaseType.UNKNOWN` defensive guards in `_classification_user_type` can therefore never fire — a valid `RouterClassification` always carries a real enum value. The dead code was left in place to keep the bug-fix commit surgical, not because it still serves a purpose.

**Suggested fix:** In a cleanup pass, reduce `_classification_user_type` to:

```python
def _classification_user_type(result: RouterClassification, text: str) -> UserType:
    inferred = _infer_user_type_rules(text)
    persona = result.persona_type
    use_case = result.use_case_type
    if persona is PersonaType.UNKNOWN:
        persona = inferred.persona_type
    if use_case is UseCaseType.UNKNOWN:
        use_case = inferred.use_case_type
    return UserType(persona_type=persona, use_case_type=use_case)
```

Verify by re-running `tests/agent/test_router.py` (all 14 tests should still pass).

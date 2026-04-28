# Scout Handoff Plan — 2026-04-26 (Phase 4b)

**Owner:** Zach
**Origin:** 2026-04-26 BROWSE-rebuild walkthrough. Owner framing: *"Scout needs to be the apex of the product. You have to remember what differentiates briarwood from the zillows / redfins, we're not a discovery tool we are a decision engine, and what powers that is scout. Scout is going to be the thing that answers the question that you dont know to ask."* User-memory: [project_scout_apex.md](/Users/zachanderson/.claude/projects/-Users-zachanderson-projects-briarwood/memory/project_scout_apex.md).
**Status:** **In progress — Cycles 1-2 landed 2026-04-28.** Cycles 3-7 open.
Sequence position: step 4 of [`ROADMAP.md`](ROADMAP.md) §1, unblocked by
the AI-Native Foundation umbrella's user-visible phase landing
(steps 1, 2, 3a, 3b all ✅). Plan was originally drafted 2026-04-26
behind CMA Phase 4a; the substrate has expanded materially since
(see "State of the repo at handoff" below for what's new).

This plan is the **canonical to-do list** for taking Value Scout from "single deterministic pattern, claims-wedge-only" to "LLM-driven Layer 5 surface that runs on every chat-tier turn and answers the question the user didn't know to ask."

---

## North-star problem statement

Briarwood's defensible position against Zillow / Redfin / realtor.com is the **decision-engine framing**: a product that surfaces the angles a user wouldn't have thought to search for. Today, Value Scout is the right concept but the wrong shape:

- **Single pattern** (`uplift_dominance` at [briarwood/value_scout/patterns/uplift_dominance.py](briarwood/value_scout/patterns/uplift_dominance.py)) — pure-function threshold logic on a renovation-uplift comparison. Fires for one specific angle.
- **Claims-wedge-only** — `scout_claim` runs inside `_maybe_handle_via_claim` only. Chat-tier turns never see scout output.
- **Sequential** — runs after `build_claim_for_property`, before `edit_claim`. Layer 5 target per [GAP_ANALYSIS.md](GAP_ANALYSIS.md) calls for parallel firing alongside Layer 2 orchestration.
- **First-non-null selection** — only one pattern to choose from, so "strongest insight" collapses to "the one we have."

The 2026-04-26 BROWSE walkthrough surfaced the gap concretely: the user asked about a 3bd/1ba in Belmar (a strong rental-profile town); the response talked about value, ask vs. fair, and a 5-year scenario fan, but never surfaced the rent angle that any underwriter would notice. The substrate is there — `rental_option`, `rent_stabilization`, `income_support`, `scarcity_support`, `legal_confidence` (ADU / accessory unit signals), `market_value_history` (town trend) all run as part of the consolidated chat-tier plan. Nothing reads them looking for surprises.

The fix: **LLM-driven scout that reads the full `UnifiedIntelligenceOutput` on every BROWSE/DECISION turn**, identifies 1-2 non-obvious angles the user would care about even though they didn't ask, and surfaces them both inline in synthesizer prose ("What's Interesting" beat) AND as a dedicated drilldown surface in the rebuilt summary card.

The deterministic `uplift_dominance` pattern stays — as a rail / fallback for the claim wedge and as one of many candidate insight sources. Not as the primary mode.

---

## State of the repo at handoff

**Existing scout** (`briarwood/value_scout/`):
- Public entry: `scout_claim(claim) -> SurfacedInsight | None` in [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py).
- Pattern registry: `_PATTERNS` tuple, single entry: `uplift_dominance.detect`.
- Schema: `SurfacedInsight` at [briarwood/claims/base.py:49](briarwood/claims/base.py#L49) — fields: `headline`, `reason`, `supporting_fields: list[str]`, `scenario_id: str | None`. Tied to `VerdictWithComparisonClaim` semantics.
- Caller: `_maybe_handle_via_claim` in [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py).
- Tests: [tests/value_scout/](tests/value_scout/).
- README: [briarwood/value_scout/README.md](briarwood/value_scout/README.md) — well-maintained, documents Open Product Decisions (parallel vs sequential, scoring, trigger discipline).

**Substrate the LLM scout will read** (from Phase 2 / Phase 3 / AI-Native work):
- `UnifiedIntelligenceOutput` populated by the consolidated chat-tier path (`run_chat_tier_analysis`) — 23 modules co-resident per turn.
- Layer 3 LLM synthesizer (`briarwood/synthesis/llm_synthesizer.py::synthesize_with_llm`) — newspaper voice, intent-keyed prompt, numeric grounding via `verify_response`, manifest visibility via `complete_text_observed`.
- Representation Agent (`briarwood/representation/agent.py::RepresentationAgent`) — chart selection with `IntentContract`, BROWSE chart-set enforcer.
- `IntentContract` from `briarwood.intent_contract` — passed to synthesizer + representation agent.
- LLM observability infra (`briarwood/agent/llm_observability.py::complete_structured_observed`) — every LLM call shows up in the per-turn manifest's `llm_calls` list with surface label.
- Per-turn manifest (`briarwood/agent/turn_manifest.py`) — `BRIARWOOD_TRACE=1` to inspect.

**AI-Native Foundation substrate added 2026-04-28** — materially changes the
shape of Cycle 6 (telemetry) and unlocks evaluation surfaces this plan
originally lacked:
- **`turn_traces` table** in `data/web/conversations.db` (Stage 1) —
  every turn's full manifest (modules_run, llm_calls_summary, notes,
  duration, answer_type, confidence) persists by default. Scout
  patterns that want to look across turns (e.g. "this property got
  rated, here are the modules that fed the rated turn") can join
  against it without new infrastructure.
- **`data/llm_calls.jsonl`** (Stage 1) — every LLM call persists with
  `surface`, `cost_usd`, `duration_ms`, `turn_id` (Stage 3 addition).
  Scout's `value_scout.scan` surface will appear here from day one
  with no extra wiring; per-turn cost-of-scout becomes a SQL query.
- **`feedback` table** (Stage 2) — user thumbs ratings per
  `message_id`, joinable to `turn_traces` via
  `messages.turn_trace_id`. Scout-influenced turns can be evaluated
  against user signal.
- **In-flight synthesis hint** (Stage 2) — when a recent turn in the
  same conversation got a thumbs-down, the next turn's synthesizer
  appends "vary your framing." Scout rides this hint via the system
  prompt; no separate loop wiring needed for Scout to participate
  in the closure.
- **`/admin` dashboard** (Stage 3) — top-10 highest-cost turns,
  per-turn drill-down with the closure-loop tag highlighted.
  Manual evaluation of scout output gets a single-page surface
  (cost vs. surfaced-insights vs. user-feedback) instead of `sqlite3` shell.

**What changes for Scout because of this:**
- **Cycle 6's "LLM ledger integration" sub-bullet is mostly redundant.**
  The shared ledger exists; `value_scout.scan` will populate it
  automatically through `complete_structured_observed`. What's left
  is the *surface label* (already in scope) and the per-call cost
  attribution (already free via `cost_usd` in the JSONL).
- **Cycle 7's documentation update** picks up an extra README touch:
  the `value_scout.scan` surface should appear in
  [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) §"Persistence"
  alongside the existing surfaces, and in
  [`TOOL_REGISTRY.md`](TOOL_REGISTRY.md).
- **Browser-smoke verification gets a new affordance.** Owner can
  drill into a scout-influenced turn at `/admin/turn/[turn_id]`
  and see all of: which modules ran, what the synthesizer prose
  was, which scout insights surfaced, and whether the user rated
  the turn. This replaces the looser "did the user notice the
  rent angle?" smoke gate with structured per-turn evidence.

**Guardrail context**:
- User has explicitly hardened the "loosen LLM invocation" stance (user-memory `project_llm_guardrails.md`). This handoff is permitted — and expected — to add LLM calls aggressively. Cost optimization is post-quality.
- The numeric-logic guardrail stays. Scout's LLM call must ground any cited number against `unified` via `verify_response`, same rule the synthesizer follows.

**Dependency on CMA**:
- Several candidate scout patterns (comp-anomaly, comp-tightness, hidden-comp-set-strength) need real comps. Cycle 1 of this plan can land the LLM scout module without comp-grounded patterns; Cycle 4+ assume CMA Phase 4a is complete.
- **Rent-angle pattern gets a free ride from CMA Phase 4a Cycle 3a** ([CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md)). The probe found that SearchApi Zillow's SOLD payload includes `rent_zestimate` on **100% of rows** (universal coverage across all 6 target Monmouth towns). Once CMA Cycle 3a extends the normalizer to capture `rent_zestimate`, every comp Briarwood pulls also carries Zillow's rent estimate for that property. The rent-angle scout pattern can compute "comp X sold for $Y with Zillow rent estimate $Z, implying gross yield Q%" without any additional API call. **Material cost reduction** for Cycle 6 — see Cycle 6 scope for how this changes the rent-angle pattern's design.

---

## Cycles

### Cycle 1 — LLM scout module + grounding + tests

**Status:** ✅ **Landed 2026-04-28** (commit `0ce8598`).

**Closeout (2026-04-28).** All scope items shipped. `briarwood/value_scout/llm_scout.py::scout_unified` is callable but not wired to any chat-tier handler — Cycle 2 takes that. `SurfacedInsight` extended with optional `confidence` (Field ge=0, le=1) + `category`; `scenario_id` already nullable so no schema-side change. Existing `scout_claim` and `uplift_dominance` unchanged. 11 new tests in `tests/value_scout/test_llm_scout.py`; full suite at 16 fail / 1573 pass (= 1562 baseline + 11 new), no regressions. One deviation from plan: scout's terminal grounding rule is **stricter** than the synthesizer's — when regen does not strictly reduce violations, scout returns the empty contract rather than surfacing ungrounded insights. The Cycle 1 test description ("regen-without-improvement returns the empty contract") explicitly required this asymmetry; reasoning is that there is no caller fallback for an ungrounded "what's interesting" beat. See [DECISIONS.md](DECISIONS.md) 2026-04-28 entry "Phase 4b Scout Cycle 1 landed" for the full closeout + Guardrail Review. README updates (`briarwood/value_scout/README.md`, `briarwood/claims/README.md`) intentionally deferred to Cycle 7 per this plan's batching convention.

**Why first.** Land the new LLM scout as a callable, tested module before any handler integration. Mirrors Phase 2 Cycle 2 pattern — new function lands in isolation, then handlers get rewired in subsequent cycles.

**Scope:**
- New module `briarwood/value_scout/llm_scout.py`.
- Single function `scout_unified(*, unified: dict, intent: IntentContract, llm: LLMClient, max_insights: int = 2) -> tuple[list[SurfacedInsight], dict]`.
- One LLM call wrapped in `complete_structured_observed(surface="value_scout.scan", ...)`.
- System prompt instructs the LLM to:
  - Read the full `UnifiedIntelligenceOutput`.
  - Identify the 1-2 most non-obvious angles the user would care about even though they didn't explicitly ask. Examples in the prompt: rent angle on a value-question; ADU / multi-unit signal on a flip-question; town-trend tailwind on a comp-question.
  - Cite `supporting_fields` from the unified output (same field-citation discipline as the existing scout).
  - Avoid restating what the synthesizer's "Why" beat will already cover.
- Numeric grounding via `verify_response` over the unified output, same as the synthesizer. Single regen attempt on threshold-level violations; regen kept only when violations strictly decrease (mirror the synthesizer's pattern).
- Returns `([], {empty: True, reason: ...})` for budget cap, blank response, exception, or missing inputs — consistent with the synthesizer's empty-return contract.
- `SurfacedInsight` schema extended with two optional fields: `confidence: float | None` (0-1, the LLM's self-rated confidence) and `category: str | None` (e.g. `"rent_angle"`, `"adu_signal"`, `"town_trend"`, `"comp_anomaly"`). Existing `scenario_id` field becomes optional for chat-tier insights (it's claims-wedge-specific).
- Migration: existing claims-wedge `scout_claim` continues to work unchanged. The new `scout_unified` is additive; the registry refactor in Cycle 5 unifies the two surfaces.

**Tests** (new file `tests/value_scout/test_llm_scout.py`):
- Clean draft: ScriptedLLM returns 2 insights → both reach the caller.
- Numeric grounding: insight with ungrounded number triggers regen; regen-without-improvement returns the empty contract.
- Missing inputs: empty unified → returns empty contract.
- Blank LLM response: returns empty contract.
- Exception handling: provider error returns empty contract, doesn't raise.
- Manifest contract: surface label `value_scout.scan` appears in the active manifest's `llm_calls`.
- Prompt regression: pin the "1-2 most non-obvious angles" + "cite supporting_fields" tokens.

**Verification:** Tests pass. No browser smoke yet — function is callable but not wired.

**Trace:** Owner framing 2026-04-26. User-memory `project_scout_apex.md`. [ROADMAP.md](ROADMAP.md) "Layer 3 intent-satisfaction LLM in shadow mode" 2026-04-24 (related but distinct — that's about answering "did we answer the intent"; this is about "what angles did we miss").

**Estimate:** 4-5 hours.
**Risk:** Low — purely additive, no handler wiring.

---

### Cycle 2 — Wire scout into BROWSE handler + synthesizer prose integration

**Status:** ✅ **Landed 2026-04-28** (commit `038ca51`).

**Closeout (2026-04-28).** All scope items shipped. `handle_browse` now calls `scout_unified` between the representation-plan computation and the synthesizer; insights are cached on `session.last_scout_insights` and passed to `synthesize_with_llm` via a new optional `scout_insights: list[SurfacedInsight] | None` kwarg. The newspaper system prompt's `## What's Interesting` beat is now an explicit "weave the highest-confidence insight, paraphrase (do NOT quote), name the supporting field, tease the drilldown" directive. New `scout_insights` SSE event in `api/events.py` + `api/pipeline_adapter.py`, mirrored in `web/src/lib/chat/events.ts` per AGENTS.md parity. `_MODULE_REGISTRY` now credits "Value Scout" so the modules-ran badge surfaces it. 8 new tests (4 synthesizer, 2 dispatch, 2 pipeline-adapter); full suite at 16 fail / 1581 pass (= 1573 + 8 new), no regressions. `drilldown_target` is emitted as null in this cycle — Cycle 3 fills the `category → drill_in_route` mapping. Browser smoke deferred (auto-mode handoff did not drive a browser); the 2026-04-26 walkthrough query "what do you think of 1008 14th Ave, Belmar, NJ" is the verification gate. See [DECISIONS.md](DECISIONS.md) 2026-04-28 entry "Phase 4b Scout Cycle 2 landed" for the full closeout + Guardrail Review.

**Scope:**
- `handle_browse` (existing structure from Phase 2 / Phase 3): after `run_chat_tier_analysis` returns the artifact, call `scout_unified(unified=artifact["unified_output"], intent=..., llm=llm)`. Cache result on `session.last_scout_insights`.
- Pass scout insights into `synthesize_with_llm` as a new optional `scout_insights: list[SurfacedInsight]` keyword.
- Synthesizer system prompt extended (newspaper voice section): when scout insights are present, the "What's Interesting" beat MUST weave one of them into prose — name the angle, cite the supporting field, and tease the drilldown without spoiling it. Numeric grounding rule preserved verbatim.
- New SSE event type `scout_insights` (or extend the existing chat-event union). Payload: `[{headline, reason, category, confidence, drilldown_target}]`. Wire in `api/pipeline_adapter.py`.
- Cache the scout insights so they're available when the React layer renders the dedicated drilldown surface in Cycle 3.

**Tests:**
- New: `handle_browse` integration test — scout fires on every BROWSE turn when `llm` is provided; prose references at least one scout insight by category.
- Synthesizer test: passing `scout_insights` produces prose containing one of the insight's category tokens.
- Manifest test: `value_scout.scan` LLM call appears alongside `synthesis.llm` for every BROWSE turn.

**Verification:** Browser. The 2026-04-26 walkthrough query: "what do you think of 1008 14th Ave, Belmar, NJ". Expected: synthesizer's "What's Interesting" beat now mentions the rent angle (or ADU signal, or town-trend tailwind, depending on which the LLM picks for this property), naming the relevant module's evidence.

**Trace:** 2026-04-26 BROWSE walkthrough Thread 3.

**Estimate:** 3-4 hours.
**Risk:** Medium — user-visible BROWSE prose change. Iterate the prompt based on browser smoke.

---

### Cycle 3 — Dedicated drilldown surface in BROWSE (frontend)

**Status:** Not started. Blocks on Cycle 2.

**Scope:**
- New React component `WorthACloserLook` (or similar name — owner picks at start of cycle) in `web/src/components/chat/`. Renders 1-2 scout insight cards: each has a category badge, the headline, a one-line reason, and a "Drill in →" link.
- Drilldown target: the relevant module's existing drill-in route (`rent_outlook`, `value_thesis`, `town_context`, etc.). Mapping in TypeScript: `category → drill_in_route`.
- Position in the BROWSE response layout: right under the synthesizer prose, above the existing card stack. (Owner may want to revisit when Thread 1's BROWSE rebuild lands — for v1, prose-then-scout-then-cards is a sensible order.)
- TypeScript event type added at [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) mirroring the new `scout_insights` SSE event.
- Empty state: when scout returns 0 insights, the component renders nothing (no "no insights found" placeholder).

**Tests:**
- React component render test for 0 / 1 / 2 insights.
- Drilldown click target test (assert correct route per category).

**Verification:** Browser. BROWSE turn for 1008 14th Ave shows the new surface with 1-2 cards. Click on each drilldown lands on the right module surface.

**Trace:** 2026-04-26 BROWSE walkthrough Thread 3 ("dangle other interesting ideas in front of them").

**Estimate:** 3-4 hours (mostly React).
**Risk:** Low-Medium — additive frontend. Visual placement may need iteration with the owner.

---

### Cycle 4 — Generalize to DECISION + EDGE handlers

**Status:** Not started. Blocks on Cycle 2 + 3.

**Scope:**
- `handle_decision`: after the wedge falls through (or when wedge is disabled), call `scout_unified` and pipe insights to the Layer 3 synthesizer the same way Cycle 2 did for BROWSE. Wedge-active path is unchanged for now (claim renderer keeps its existing structure).
- `handle_edge`: same pattern; tune the system prompt to bias toward edge-style insights (skeptical surfacing of risk-adjacent angles).
- System prompt: per-tier voice for scout (mirrors the synthesizer's per-tier voice from Phase 3 Cycle D). BROWSE = first-impression surfacer; DECISION = decision-pivot surfacer; EDGE = skeptical surfacer.
- React: dedicated drilldown surface from Cycle 3 reused on DECISION and EDGE responses.

**Tests:**
- Per-handler integration tests pinning scout fires + insights surface correctly.

**Verification:** Browser. DECISION turn surfaces insights distinct from BROWSE (more decision-pivot-flavored). EDGE turn surfaces risk-adjacent insights.

**Estimate:** 3-4 hours.
**Risk:** Low-Medium per handler.

---

### Cycle 5 — Coexistence with claims-wedge scout + scoring channel

**Status:** Not started. Blocks on Cycles 1-4.

**Scope:**
- Refactor `_PATTERNS` registry to dispatch by input type. Today `_PATTERNS` is a flat tuple; becomes a `dict[InputType, tuple[Detector, ...]]` with two keys: `VerdictWithComparisonClaim` (for claim-wedge) and `UnifiedIntelligenceOutput` (for chat-tier).
- Existing `uplift_dominance` pattern stays under the `VerdictWithComparisonClaim` key — claim wedge behavior unchanged.
- Add scoring channel to `SurfacedInsight`: the `confidence` field added in Cycle 1 becomes the universal sort key. Both LLM-emitted insights and pure-function patterns produce a confidence; "strongest" becomes "top-N by confidence."
- New `scout(input_obj, *, llm=None) -> list[SurfacedInsight]` dispatcher that picks the right pattern set + LLM scout based on input type.
- `scout_claim` retained as a wrapper for back-compat; calls the new `scout` with `VerdictWithComparisonClaim`.
- Documentation: update `briarwood/value_scout/README.md` to reflect the new architecture. Note: this is a contract change — append dated changelog.

**Tests:**
- Pin: claim-wedge still uses `uplift_dominance` and produces the same output for the same fixture.
- Pin: chat-tier dispatch uses the LLM scout.
- Pin: scoring sort order — when both deterministic and LLM patterns produce insights, top-N by confidence wins.

**Verification:** Existing claims-wedge tests stay green. Chat-tier tests from Cycles 2-4 stay green. New dispatcher test pins both code paths.

**Estimate:** 3-4 hours.
**Risk:** Medium — touches both code paths simultaneously.

---

### Cycle 6 — Pure-function pattern fallback rails + telemetry

**Status:** Not started. Blocks on Cycle 5. **Strong dependency on CMA Phase 4a Cycle 3a + Cycle 3c** — the rent-angle pattern below uses comp-derived rent data that only exists once CMA's normalizer extension and 3-source merger land.

**Scope:**
- Land 2-3 deterministic pattern detectors as fallback rails. Triggered when LLM scout returns empty or when running in a no-LLM environment (testing, batch). Candidates:
  - **`rent_angle`** — detects properties with comp-anchored rental upside the user didn't ask about. Implementation leans on the `rent_zestimate` field that CMA Phase 4a Cycle 3a extends `SearchApiZillowListingCandidate` to capture (per [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md), `rent_zestimate` is in 100% of SOLD rows). The pattern computes per-comp gross rental yield (`rent_zestimate × 12 / sale_price`) for the comp set; if the median comp gross yield is materially favorable vs. the subject's `carry_cost.monthly_total_cost`, surface as a rent-angle insight. **No extra API call** — the rent data rides on the comp data we're already pulling for the CMA. This is the primary deterministic fallback for the rent-angle question.
  - Secondary check (when CMA isn't available): if `rental_option.rent_support_score >= threshold` AND `carry_cost.monthly_cash_flow > -X` AND no rent-tier intent in user_text, fire the rent-angle insight from the `rental_option` module's existing fields.
  - **`adu_signal`** — detects `legal_confidence.legality_evidence.has_accessory_signal == True` with high confidence.
  - **`town_trend_tailwind`** — detects `market_value_history.three_year_change_pct > 10%` (or similar threshold; defined at start of cycle).
- Each pattern lives in `briarwood/value_scout/patterns/`. Register under the `UnifiedIntelligenceOutput` key in the dispatcher.
- **LLM ledger integration is mostly free** post-AI-Native-Stage-1.
  `value_scout.scan` invocations land in `data/llm_calls.jsonl` with
  `surface`, `cost_usd`, `duration_ms`, `turn_id` automatically via
  `complete_structured_observed`. What this cycle adds: a small
  manifest note (`record_note(...)`) capturing
  `(insights_generated, insights_surfaced, top_confidence)` per turn
  so per-turn drill-down at `/admin/turn/[turn_id]` shows scout's
  yield alongside its cost. Drill-down click telemetry (frontend
  side) is out of scope for v1; defer.
- This gives the owner the data needed for Stage 2 of the LLM-loosening plan ("once quality is in agreement, narrow scope back down for cost") — and the `/admin` dashboard's top-10 highest-cost turns table makes the cost-vs-quality tradeoff legible at a glance.

**Tests:**
- Each pattern has a unit test against a known fixture.
- `rent_angle` test fixture uses the post-CMA-Cycle-3a `CMAResult` shape (with `rent_zestimate` present per comp).
- Dispatcher test: when LLM scout returns empty, pure-function patterns fire as fallback.

**Verification:** Browser. Disable LLM scout via env var; pure-function patterns still surface insights for properties matching their triggers. For rent_angle: a 3bd/1ba property in a strong-rental-profile town like Belmar should surface the angle.

**Estimate:** 4-5 hours.
**Risk:** Low — deterministic patterns are well-understood; ledger integration is straightforward. The rent-angle pattern's design is tighter and cheaper than originally scoped because of the CMA probe finding.

---

### Cycle 7 — Cleanup + closeout

**Status:** Not started.

**Scope:**
- Update [briarwood/value_scout/README.md](briarwood/value_scout/README.md) with Cycle 1-6 changelog entries reflecting all contract changes.
- Update [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 5 section: scout is no longer "partial — sequential in claim wedge only." Mark which Layer 5 target items remain open (parallel-with-Layer-2 firing, user-type conditioning).
- Update [TOOL_REGISTRY.md](TOOL_REGISTRY.md) with the `value_scout.scan` LLM call surface.
- Final smoke: BROWSE / DECISION / EDGE turns all surface scout insights consistent with the per-tier voice from Cycle 4.

**Tests:** Existing tests stay green.

**Verification:** Browser smoke.

**Estimate:** 2-3 hours.
**Risk:** Low.

---

## Open design decisions

(Resolve at the start of the named cycle.)

1. **Per-insight confidence scoring** — numeric (0-1), banded ("high"/"medium"/"low"), or just unsorted? Default: numeric for LLM-emitted, with the band derivable from thresholds (mirror the existing `Confidence` derivation pattern). Cycle 1.
2. **Insight cap per turn** — 1 or 2? Default: 2 for v1, may tighten to 1 after browser smoke. Cycle 1.
3. **Trigger gating** — every turn vs every-N-turns vs context-gated (don't surface X if user already asked about X)? Default: every BROWSE/DECISION/EDGE turn for v1, no context gating. Cycle 2.
4. **Drilldown grammar** — limited to existing module drill-in routes only, or allow ad-hoc deep links? Default: existing drill-in routes only for v1 (predictable surface; ad-hoc links can land later). Cycle 3.
5. **Drilldown surface name** — `WorthACloserLook` / `BriarwoodNoticed` / `OtherAngles` / `WhatYouMissed`? Owner pick. Cycle 3.
6. **Surface placement in BROWSE** — under prose, between cards, end of stack? Default: under prose, above card stack. May change with Thread 1's BROWSE rebuild. Cycle 3.
7. **Per-tier voice splitting** — single prompt with intent-keyed voice (per Phase 3 Cycle D pattern) vs separate per-tier prompts? Default: single prompt with intent-keyed voice. Cycle 4.
8. **Pure-function pattern thresholds** — exact thresholds for `town_trend_tailwind` etc. Owner pick during Cycle 6.
9. **User-type conditioning** (Layer 5 target per [GAP_ANALYSIS.md](GAP_ANALYSIS.md)) — out of scope for v1; revisit when user_type plumbing lands per [ROADMAP.md](ROADMAP.md) "Extend router classification with telemetry-first user_type" 2026-04-24.
10. **Parallel firing alongside Layer 2** (Layer 5 target) — out of scope for v1; sequential post-orchestrator is fine for the latency budget. Revisit if profiling shows scout is the bottleneck.

---

## Cycle ordering rationale

- **Cycle 1 first** — land the LLM scout in isolation. Same pattern as Phase 2 Cycle 2 (`run_chat_tier_analysis`).
- **Cycle 2 before Cycle 3** — backend wiring + synthesizer integration before any frontend work. The synthesizer prose change is the highest-leverage user-visible signal; the dedicated drilldown surface compounds on top.
- **Cycle 4 after Cycles 2-3** — prove the pattern on BROWSE before generalizing.
- **Cycle 5 after Cycle 4** — registry refactor touches both code paths; do it once both are well-understood.
- **Cycle 6 after Cycle 5** — pattern rails + telemetry compound on the dispatcher refactor.
- **Cycle 7 cleanup at the end.**

---

## Boot prompt for the next Claude context window

```
I'm starting the Value Scout buildout (Phase 4b — sequence step 4 in
ROADMAP.md §1). The plan is at SCOUT_HANDOFF_PLAN.md at the repo root.

ALL prerequisites are closed as of 2026-04-28:
- CMA Phase 4a (CMA_HANDOFF_PLAN.md) ✅ — including Cycle 3a's
  rent_zestimate normalizer extension that Cycle 6 of this plan
  depends on for the rent-angle pattern.
- AI-Native Foundation Stage 1 (PERSISTENCE_HANDOFF_PLAN.md) ✅ —
  turn_traces table + data/llm_calls.jsonl + messages metric columns.
- AI-Native Foundation Stage 2 (FEEDBACK_LOOP_HANDOFF_PLAN.md) ✅ —
  feedback table + thumbs UI + closed-loop synthesis hint with the
  feedback:recent-thumbs-down-influenced-synthesis manifest tag.
- AI-Native Foundation Stage 3 (DASHBOARD_HANDOFF_PLAN.md) ✅ —
  /admin and /admin/turn/[turn_id] surfaces under
  BRIARWOOD_ADMIN_ENABLED=1, with the closure-loop tag highlighted
  in the per-turn drill-down.

Substrate this gives Scout (read SCOUT_HANDOFF_PLAN.md "State of the
repo at handoff" → "AI-Native Foundation substrate" for the full
list):
- value_scout.scan LLM call will land in data/llm_calls.jsonl with
  cost / duration / turn_id automatically; no extra wiring.
- Scout-influenced turns can be evaluated at /admin/turn/[turn_id]
  with feedback joined.
- Scout rides the existing thumbs-down synthesis hint; no separate
  feedback loop wiring needed.
- Cycle 6's "LLM ledger integration" bullet is mostly redundant
  (Stage 1 already wrote that infra).

Per CLAUDE.md, before any code:
1. Re-read CLAUDE.md, DECISIONS.md (especially the four 2026-04-28
   entries: Stage 1 landed, Router audit, Router Round 2, Stage 2,
   Stage 3 — five entries on the same date; load all of them),
   ROADMAP.md (§3.2 Phase 4b Scout, §1 sequence step 4).
2. Run README drift check (.claude/skills/readme-discipline/SKILL.md
   Job 1) — Phase 4b in-scope: briarwood/value_scout/* (has README;
   read it), briarwood/agent/dispatch.py (has README_dispatch.md),
   briarwood/synthesis/llm_synthesizer.py (synthesis/README.md),
   briarwood/agent/router.py (README_router.md). Read each.
3. Read SCOUT_HANDOFF_PLAN.md end-to-end. Also read user-memory
   project_scout_apex.md and project_llm_guardrails.md — both are
   load-bearing for the design philosophy. Also read
   project_intent_tiers.md (browse-style ≠ decision cascade).
4. Confirm baseline: 16 pre-existing failures, 1562 passed
   (post-Stage-3 baseline as of 2026-04-28). Stash and re-run if
   anything looks off.
5. Surface git status + git log of last 10 commits and ask whether
   to commit + push the Stage 1/2/3 work first or run with
   uncommitted state.

Do NOT begin code work until 1-5 are done and reported back. Cycle 1
is Open Design Decisions #1 + #2 — pause for owner confirmation
before LLM scout module shape lands.

The full SCOUT_HANDOFF_PLAN.md has 7 cycles; expect the full buildout
to span ~25-35 LLM-time hours across multiple sessions. Cycle 1 is
~30-45 min on its own (LLM scout module + tests, no handler
integration). Pause for owner sign-off between cycles per the
established workflow pattern.
```

---

## Cross-references

- Origin: 2026-04-26 BROWSE walkthrough Thread 3.
- User-memory: [project_scout_apex.md](/Users/zachanderson/.claude/projects/-Users-zachanderson-projects-briarwood/memory/project_scout_apex.md), [project_llm_guardrails.md](/Users/zachanderson/.claude/projects/-Users-zachanderson-projects-briarwood/memory/project_llm_guardrails.md).
- Existing scout: [briarwood/value_scout/README.md](briarwood/value_scout/README.md), [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py).
- Substrate: [briarwood/orchestrator.py](briarwood/orchestrator.py) `run_chat_tier_analysis`, [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) `synthesize_with_llm`, [briarwood/representation/agent.py](briarwood/representation/agent.py) `RepresentationAgent`.
- Layer 5 target: [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 5.
- Related ROADMAP:
  - "Layer 3 intent-satisfaction LLM in shadow mode" 2026-04-24 — related but distinct (intent-satisfaction asks "did we answer"; scout asks "what did we miss").
  - "Extend router classification with telemetry-first user_type" 2026-04-24 — prerequisite for Open Design Decision #9 (user-type conditioning).
- Sibling plans (all closed 2026-04-28):
  - [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md) (Phase 4a) — closed; rent_zestimate normalizer (Cycle 3a) is what Cycle 6 rent-angle pattern consumes.
  - [PERSISTENCE_HANDOFF_PLAN.md](PERSISTENCE_HANDOFF_PLAN.md) (AI-Native Stage 1) — closed; turn_traces + llm_calls.jsonl substrate.
  - [FEEDBACK_LOOP_HANDOFF_PLAN.md](FEEDBACK_LOOP_HANDOFF_PLAN.md) (AI-Native Stage 2) — closed; thumbs UI + closed-loop synthesis hint that scout participates in implicitly.
  - [DASHBOARD_HANDOFF_PLAN.md](DASHBOARD_HANDOFF_PLAN.md) (AI-Native Stage 3) — closed; /admin and /admin/turn/[turn_id] are scout's evaluation surfaces.
- CMA probe (load-bearing for Cycle 6 rent-angle): [CMA_SOLD_PROBE_2026-04-26.md](CMA_SOLD_PROBE_2026-04-26.md). Specifically: `rent_zestimate` field is in 100% of SearchApi SOLD rows; CMA Cycle 3a's normalizer extension surfaces it; Cycle 6 rent-angle pattern consumes it.
- Parking lot for Thread 1 (BROWSE rebuild): [ROADMAP.md](ROADMAP.md) §3.5 Phase 4c — runs after Scout, depends on this work for the "Briarwood noticed" drilldown row.

---

## Definition of done

The Scout effort is done when:

1. Every BROWSE / DECISION / EDGE turn surfaces 1-2 LLM-generated insights tied to non-obvious angles in the unified output.
2. Synthesizer prose's "What's Interesting" beat references at least one scout insight by name.
3. A dedicated drilldown surface in the chat response renders the insights with click-through to the relevant module's drill-in route.
4. The numeric guardrail enforces grounding on every cited number in scout output.
5. Pure-function patterns serve as fallback rails when the LLM is unavailable; the existing `uplift_dominance` claim-wedge pattern continues to function unchanged.
6. The scout dispatcher registry handles both `VerdictWithComparisonClaim` and `UnifiedIntelligenceOutput` input types via a single entry point.
7. Every scout invocation writes a telemetry record to the LLM ledger (insights generated, surfaced, confidence).
8. ARCHITECTURE_CURRENT / GAP_ANALYSIS Layer 5 / TOOL_REGISTRY / value_scout README reflect the post-handoff topology with dated changelog entries.
9. The "Briarwood beats plain Claude on underwriting" qualitative bar is met for BROWSE — owner judgment, not a metric.
10. All changes traced. No drive-by fixes. Tests pass.

---

## Notes for the next agent

- **Scout is the apex of the product.** Read user-memory `project_scout_apex.md` before starting. This is not a "nice to have" surface — it's the differentiator.
- **LLM-on by default.** The user has explicitly hardened the loosen-LLM stance (user-memory `project_llm_guardrails.md`). Cost concerns are post-quality.
- **Numeric guardrail stays.** Every cited number in scout output must round to a value present in `unified`, same rule as the synthesizer.
- **Iterate the prompt with the owner.** Cycle 2 will likely need 2-3 prompt iterations after browser smoke. Don't ship the first prompt and call it done.
- **The CMA dependency is real for some patterns.** Don't try to land the comp-anomaly pattern (Cycle 6) before CMA Phase 4a is complete — it'll rest on Engine B scoring quality that doesn't exist yet.
- **Don't drift into Thread 1 (BROWSE rebuild).** That's the next handoff after this. Note candidate UI changes here but do not implement.
- **Scout output should compound with the synthesizer, not duplicate it.** If scout's category is `rent_angle` and the synthesizer's "Why" beat already covered rent, scout should pick a different angle or surface a deeper rent observation. Tune the system prompt for this.

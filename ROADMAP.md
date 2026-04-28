# Briarwood — Roadmap

The project plan going forward. Three layers in one file:

1. **Active handoff plans** — the multi-cycle structured work currently in
   flight (banner immediately below). Read the plan doc before picking off
   any item that belongs to one.
2. **Strategic umbrellas** — multi-stage roadmaps that span several
   handoffs (e.g. the 2026-04-27 AI-Native Foundation umbrella). Each
   stage becomes its own plan-mode pass.
3. **Tactical follow-ups** — actionable code-level items surfaced during
   prior work and left untouched per the originating handoff's scope
   rules. Triagable entries: issue, affected files, impact, suggested
   approach. Resolve in subsequent handoffs.

This file was previously named `FOLLOW_UPS.md`; renamed to `ROADMAP.md`
on 2026-04-27 to reflect that it now holds the strategic plan as well as
tactical follow-ups.

> **Active handoff plans.** Some follow-ups are part of a structured multi-cycle handoff with its own plan doc. Don't pick those off in isolation — read the plan first.
>
> - **Phase 2 (output quality):** [OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md). All five cycles landed 2026-04-25; Cycle 6 cleanup remains.
> - **Phase 3 (presentation):** [PRESENTATION_HANDOFF_PLAN.md](PRESENTATION_HANDOFF_PLAN.md). Cycles A-D landed 2026-04-26; Open Design Decision #7 (editor pass) tabled.
> - **Phase 4a (CMA quality):** [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md). Cycles 1-5 LANDED 2026-04-26; Cycle 6 (cleanup + closeout) remains.
> - **AI-Native Foundation (umbrella) — NEW 2026-04-27, precedes Phase 4b:** see the *AI-Native Foundation (umbrella)* entry below for the full four-stage roadmap. Drafted 2026-04-27; named principles in [design_doc.md](design_doc.md) § 3.4. Four staged sub-handoffs (artifact persistence; user-feedback loop closure; business-facing dashboard; model-accuracy loop closure). Sequencing call recorded in [DECISIONS.md](DECISIONS.md) 2026-04-27 entry — Stages 1-3 land before Phase 4b so Scout inherits artifacts + closed feedback + dashboard surface; Stage 4 follows Scout. Take Stage 1 next once Phase 4a Cycle 6 closes.
> - **Phase 4b (Scout buildout) — HIGH PRIORITY 2026-04-26 (now follows AI-Native Stages 1-3):** [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md). Drafted 2026-04-26, not started. Substrate now ready (`rent_zestimate` from CMA Cycle 3a is landed). **Pulled forward by owner direction 2026-04-26**: Scout is the apex of the product (per `project_scout_apex.md` user memory) — what differentiates Briarwood from Zillow/Redfin. Today it's claim-wedge-only and gated behind `BRIARWOOD_CLAIMS_ENABLED`. **Resequenced 2026-04-27**: AI-Native Foundation Stages 1-3 land first so Scout has persisted artifacts to mine and closed user feedback to learn from. See [DECISIONS.md](DECISIONS.md) 2026-04-27 entry for the rationale.
> - **Phase 4c (BROWSE summary card rebuild):** parking lot. Promote to a handoff plan once 4a + 4b complete. See "BROWSE summary card rebuild" entry below.

Distinct from [DECISIONS.md](DECISIONS.md) (which captures product/architectural decisions and audit-doc drift) and [GAP_ANALYSIS.md](GAP_ANALYSIS.md) (which captures architectural gaps relative to the six-layer target). This file holds the forward plan — strategic umbrellas and "go fix this" items — while DECISIONS.md is the historical decision log.

---

## 2026-04-27 — AI-Native Foundation (umbrella)

**Severity:** Foundational — constrains every architectural decision going
forward. This umbrella is the canonical scope for the AI-Native Foundation
roadmap; it operationalizes the four AI-native principles named in
[`design_doc.md`](design_doc.md) § 3.4 (Contracts First, Queryable
Outputs, Every Action Is An Artifact, Closed Feedback Loops). Sequencing
recorded in [`DECISIONS.md`](DECISIONS.md) 2026-04-27 entry: Stages 1-3
precede Phase 4b (Scout); Stage 4 follows Scout.

**Read these first** before picking off any sub-handoff:
- [`design_doc.md`](design_doc.md) § 3.4 (the principles)
- [`design_doc.md`](design_doc.md) § 7 (the dual feedback loops; updated
  2026-04-27 to define what "closed" means operationally)
- [`DECISIONS.md`](DECISIONS.md) 2026-04-27 entry (the sequencing call)
- This umbrella entry (the four staged sub-handoffs with file-level scope)

### Why This Umbrella Exists

Briarwood is being built as an AI-native, "queryable" company. The
implications, written down so they stay load-bearing across sessions:

- **Every action leaves an artifact** so the system can be inspected,
  measured, and iterated on with the same rigor as any other product
  surface.
- **Every output feeds back as input** so models improve from use rather
  than only from offline retraining.
- **Every analysis result is machine-consumable** so downstream LLM
  agents (Scout, future agents) can reason over Briarwood outputs
  without parsing prose.

The principles these implications derive from are stated in
[`design_doc.md`](design_doc.md) § 3.4. This umbrella is the build path
for closing the gaps between those principles and the codebase.

The repo is already roughly 85% of the way there. What's missing is
**persistence**, **read-back**, and a **business-facing surface** to view
the resulting data. Each stage below names a specific gap and the
smallest move that closes it.

### Sequencing

This work precedes **Phase 4b (Scout)** — see
[`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md) and the 2026-04-27
[`DECISIONS.md`](DECISIONS.md) entry. Scout will inherit:

- Persisted artifacts to mine (Stage 1)
- Closed user-feedback signal to learn from (Stage 2)
- A business-facing surface where Scout's own outputs can be measured
  (Stage 3)

The cost is a one-handoff Scout deferral. Scout slots back into the
queue after Stage 2 or Stage 3, depending on the signal at that point.

### Stage 1 — Persist Every Action

**Principle:** "Every action is an artifact" ([`design_doc.md`](design_doc.md) § 3.4).

**Gap today:** Per-turn instrumentation is rich and live, but ephemeral.
[`TurnManifest`](briarwood/agent/turn_manifest.py) prints to stderr only
when `BRIARWOOD_TRACE=1`. [`LLMCallLedger`](briarwood/agent/llm_observability.py)
is process-local. There is no durable per-turn record outside the SQLite
conversation transcript at [`api/store.py`](api/store.py), which captures
prose and SSE events but not timings, module attributions, or LLM-call
detail.

**Scope of the handoff:**

1. **Persist `TurnManifest` to a new `turn_traces` table** in
   [`data/web/conversations.db`](api/store.py). One row per chat turn.
   Columns mirror the `TurnManifest` dataclass: `turn_id`, `started_at`,
   `conversation_id`, `answer_type`, `confidence`, `dispatch`,
   `duration_ms_total`, plus JSON-serialized `modules_run`,
   `llm_calls_summary`, `tool_calls`, `notes`. Hook point: extend
   [`api/store.py`](api/store.py) with the schema and insert call;
   wire into the turn-finalization path in
   [`api/pipeline_adapter.py`](api/pipeline_adapter.py).
2. **Append `LLMCallLedger` records to `data/llm_calls.jsonl`.** One JSON
   line per call. Hook point: add a sink in
   [`briarwood/agent/llm_observability.py`](briarwood/agent/llm_observability.py)
   that writes the full `LLMCallRecord` (without `debug_payload` unless
   `BRIARWOOD_LLM_DEBUG_PAYLOADS=1`) on call completion.
3. **Add metric columns to the `messages` table.** New columns on
   [`api/store.py::messages`](api/store.py): `latency_ms`, `answer_type`,
   `success_flag`, `turn_trace_id` (FK to `turn_traces`). Backfill not
   required — new columns are nullable and populated forward.

**Out of scope (deliberate):**
- No backfill of historical conversations.
- No new analysis on the data — that's Stage 3.
- No env-var flag for the persistence path itself; persistence is the
  default once shipped.

**Success criteria:**
- Every chat turn in dev produces one `turn_traces` row + one or more
  rows in `llm_calls.jsonl`.
- The owner can run `sqlite3 data/web/conversations.db 'SELECT
  answer_type, AVG(duration_ms_total) FROM turn_traces GROUP BY 1'`
  and get real numbers.
- No regression in the chat user experience (latency, correctness, UI).

**Effort estimate:** ~1 handoff (one focused day of work).

### Stage 2 — Close The User-Feedback Loop

**Principle:** "Closed feedback loops" ([`design_doc.md`](design_doc.md) § 3.4),
specifically Loop 2 (Communication Calibration) from
[`design_doc.md`](design_doc.md) § 7.

**Gap today:** No user-facing feedback surface exists. There is no
`/api/feedback` endpoint and no thumbs-up/down UI in
[`web/src/components/chat/`](web/src/components/chat). The
[`build_user_feedback_record()`](briarwood/intelligence_capture.py)
helper exists and would write to
[`data/learning/intelligence_feedback.jsonl`](data/learning/intelligence_feedback.jsonl)
correctly — it is simply never called from the API. Worse, even if it
were called, no consumer reads user feedback back into a future turn.
The loop is unbuilt on both ends.

**Scope of the handoff:**

1. **API endpoint.** Add `POST /api/feedback` to
   [`api/main.py`](api/main.py) accepting
   `{message_id, rating: "up"|"down", optional_text?}`. Persist in a new
   `feedback` table in [`api/store.py`](api/store.py) keyed by
   `message_id`, and call
   [`build_user_feedback_record()`](briarwood/intelligence_capture.py) →
   [`append_intelligence_capture()`](briarwood/intelligence_capture.py)
   so the existing analyzer pipeline picks it up.
2. **Minimal UI.** Add thumbs-up / thumbs-down buttons on assistant
   message bubbles in [`web/src/components/chat/`](web/src/components/chat).
   No comment box in v1 — pure binary signal. Optimistic update; toast
   on error.
3. **At least one read-back.** Pick the simplest meaningful consumer to
   prove the loop closes:
   - Surface low-rated turns in
     [`briarwood/feedback/analyzer.py`](briarwood/feedback/analyzer.py)
     output (already infrastructure-shaped for this — the analyzer
     already correlates with confidence).
   - Then thread persona inference into the router via the
     existing-but-unused [`RouterDecision.user_type`](briarwood/agent/router.py)
     field so a sustained pattern of thumbs-down on "investor framing"
     pushes subsequent turns toward a different persona.
   The first read-back is the gate — Stage 2 ships only when at least
   one consumer demonstrably reacts to a rating.

**Out of scope (deliberate):**
- Free-text comment capture (defer to a later iteration).
- Cross-session persona persistence (defer; in-session is enough).
- Rich admin tooling for browsing feedback (that's Stage 3).

**Success criteria:**
- A thumbs-down on turn N visibly influences turn N+1 in at least one
  measurable way (analyzer surfaces it; or router persona shifts; or
  the same property classification is retried under a different intent).
- The loop is named "closed" only when both write-path AND read-path
  exist and the read-path provably runs. Per
  [`design_doc.md`](design_doc.md) § 7: write-only signals are not
  closed loops.

**Effort estimate:** ~1 handoff (likely two days; UI + endpoint + one
real consumer).

### Stage 3 — Business-Facing Dashboard

**Principle:** "Every action is an artifact" — the artifacts are
useless if the owner can't see them.

**Gap today:** No admin / observability surface in
[`web/src/`](web/src). The data from Stage 1 + Stage 2 lives in SQLite
+ JSONL with no read-side UI.

**Scope of the handoff:**

1. **New admin route.** `web/src/app/admin/` (Next.js App Router)
   reading the new `turn_traces` table, the `feedback` table, and
   `data/llm_calls.jsonl`. Server-side only; no auth in v1 (local-only
   admin surface).
2. **Top-line metrics.** A single page showing:
   - Avg + p50 + p95 latency by `answer_type`, last 7 days.
   - LLM cost per turn, last 7 days, broken down by `surface`.
   - Thumbs-up / thumbs-down ratio, last 7 days.
   - Top-10 slowest turns with drill-down link to the full
     `TurnManifest` JSON.
   - Top-10 highest-cost turns with the same drill-down.
3. **One drill-down view.** Per-turn detail page showing the full
   `TurnManifest`: which modules ran, which LLM calls fired, durations,
   warnings, the final response prose, and any feedback received.

**Out of scope (deliberate):**
- Auth / multi-user scoping (single-user local product today).
- Alerting (no thresholds, no notifications — visual inspection only).
- Time-series charts beyond simple weekly aggregates.
- Cost forecasting or budget tracking (different problem).

**Success criteria:**
- The owner can answer "what was the slowest turn this week and why?"
  in under 30 seconds without grepping logs.
- The owner can answer "which `answer_type` is the most expensive on
  average and why?" without writing SQL.

**Effort estimate:** ~1 handoff (likely two-three days; mostly Next.js
+ SQL).

### Stage 4 — Close The Model-Accuracy Loop

**Principle:** "Closed feedback loops" — Loop 1 (Model Accuracy) from
[`design_doc.md`](design_doc.md) § 7.

**Gap today:**
[`data/learning/intelligence_feedback.jsonl`](data/learning/intelligence_feedback.jsonl)
has 6,290 rows but every `outcome` field is `null`. The
[`receive_feedback()`](briarwood/pipeline/feedback_mixin.py) mixin
method on every module is a no-op stub. There is no ground-truth
ingestion path. Without one, the analyzer at
[`briarwood/feedback/analyzer.py`](briarwood/feedback/analyzer.py)
cannot compute the confidence-vs-outcome correlation it is built for.

**Scope of the handoff:**

1. **Ground-truth ingestion.** Pick one signal type (recommended:
   actual sale prices for analyzed properties) and build a one-shot
   ingestion script that backfills `outcome` on prior
   `intelligence_feedback.jsonl` rows. Source: public records or manual
   entry on a backtest set.
2. **Real `receive_feedback()` bodies.** Implement the mixin on the
   highest-confidence-claiming modules first (likely `current_value`,
   `valuation`, `comparable_sales`). The implementation surfaces a
   confidence-vs-outcome alignment score per module, persisted to a new
   `model_alignment` table.
3. **Prompt / weight tuning candidates.** Use the analyzer to surface
   "this module's high-confidence calls underperform on outcome" and
   route those signals to the relevant module owner (the human; this
   stage produces the report, not the auto-tune).

**Out of scope (deliberate):**
- Auto-recalibration of weights or thresholds. Stage 4 produces the
  signal; humans decide on changes. Auto-tuning is a Stage 5
  conversation.
- Cross-property generalization (per-property alignment is enough to
  start).

**Success criteria:**
- A measurable accuracy delta between v1 and v2 of the chosen module on
  the ingested backtest set after one human-driven recalibration cycle.
- The analyzer report becomes part of the standard pre-handoff review
  for any module-touch handoff.

**Effort estimate:** ~1-2 handoffs. Higher uncertainty than Stages 1-3
because ingestion shape depends on data availability.

**Sequencing note:** Stage 4 can sensibly run *after* Phase 4b (Scout) —
Scout will benefit from Stages 1-3 but doesn't strictly need Loop 1
closed to ship. The current ordering puts Stage 4 last in the AI-native
sequence, not last in the overall project.

### What This Umbrella Is Not

- **Not a commitment to build all four stages back-to-back.** Each
  stage is independently approvable. Scout (Phase 4b) slots in after
  Stage 2 or Stage 3 depending on signal at that point.
- **Not a substitute for a handoff plan.** Each stage gets its own
  plan-mode pass with file-level scope, success criteria, and
  verification steps before any code change.
- **Not the only way to make Briarwood AI-native.** The principles in
  [`design_doc.md`](design_doc.md) § 3.4 are load-bearing across many
  future decisions (Scout's design, archetype expansion, cross-session
  memory, etc.). This umbrella closes the most-visible gaps; it
  doesn't exhaust the principles.

**Cross-references.** [`design_doc.md`](design_doc.md) § 3.4
(principles); [`DECISIONS.md`](DECISIONS.md) 2026-04-27 (sequencing
rationale); [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md) (the
deferred handoff).

---

## 2026-04-27 — Semantic-model extraction audit findings (umbrella)

**Severity:** Mixed — one Critical, three High, six Medium, two Low. Surfaced 2026-04-27 by the Phase 1 read-only audit at [SEMANTIC_AUDIT.md](SEMANTIC_AUDIT.md). The audit mapped every metric, threshold, formula, prompt, and entity to its `file:line` and cross-checked against four parallel extraction passes. No code changed in Phase 1.

**Read this first before working any item below.** The individual entries below are the actionable triage; the audit doc is the source-of-truth for inputs/formulas/bands. Each filed item references the audit's Drift section number (`§4.x`) so the full reasoning is one click away.

**Items filed (in order of severity):**

- 2026-04-27 — **CRITICAL**: pricing-view bands disagree with verdict-label thresholds (§4.1)
- 2026-04-27 — **HIGH**: synthesis confidence floors are invisible to the LLM prompts (§4.5)
- 2026-04-27 — **HIGH**: orphan signature metrics — Forward Value Gap & Optionality Score (§4.4)
- 2026-04-27 — **MEDIUM**: BCV component-count drift in prompts and prior docs (4 vs 5) (§4.3)
- 2026-04-27 — **MEDIUM**: rent has three sources with no reconciliation carrier (§4.7)
- 2026-04-27 — **MEDIUM**: numeric-grounding rule in synthesizer is informal — rounding drift accepted (§4.8)
- 2026-04-27 — **MEDIUM**: `scarcity_score` naming collision across two modules
- 2026-04-27 — **MEDIUM**: comp-scoring weights duplicated across two layers (§4.6)
- 2026-04-27 — **MEDIUM**: `pricing_view` is a categorical user-facing output with no confidence
- 2026-04-27 — **LOW**: `valuation` vs `current_value` module naming collision (§4.9)
- 2026-04-27 — **LOW**: `decision_model/scoring.py` looks legacy — verify before delete (§4.10)

**Cross-reference.** The audit's Step 8 recommends three extraction modules that, taken together, would close most of the items above: (a) `briarwood/decision_model/value_position.py` consolidating pricing-view + verdict thresholds + trust floors; (b) `briarwood/decision_model/risk_thresholds.py` centralizing the per-component penalties; (c) `briarwood/scoring_constants.py` for comp-scoring + comp-confidence weights. Don't pick the items below off in isolation when one of these extractions would solve several at once.

The 2026-04-24 entry below ("Editor / synthesis threshold duplication has no mechanical guard") is corroborated by §4.2 and remains open — fold its fix into extraction (a).

---

## 2026-04-27 — CRITICAL: pricing-view bands disagree with verdict-label thresholds

**Severity:** Critical — same property gets contradictory verdicts in chat prose vs claim badge. Highest user-visible drift in the codebase. Surfaced 2026-04-27 by [SEMANTIC_AUDIT.md §4.1](SEMANTIC_AUDIT.md).

**Files:**
- [briarwood/agents/current_value/agent.py:444-451](briarwood/agents/current_value/agent.py#L444-L451) — `_pricing_view(mispricing_pct)` returns "appears undervalued / fairly priced / fully valued / overpriced" using thresholds at +0.08, -0.03, -0.10.
- [briarwood/editor/checks.py:14-15](briarwood/editor/checks.py#L14-L15) — `VALUE_FIND_THRESHOLD_PCT=-5.0`, `OVERPRICED_THRESHOLD_PCT=5.0`.
- [briarwood/claims/synthesis/verdict_with_comparison.py:42-43](briarwood/claims/synthesis/verdict_with_comparison.py#L42-L43) — same thresholds, used to assign `verdict.label` in {value_find, fair, overpriced, insufficient_data}.

**Issue:** Two code paths classify the same human concept ("is this property under-, fair-, or over-priced?") with different thresholds and opposite sign conventions. Worked example: at BCV $1.06M / ask $1.0M the synthesizer prose says *"appears fairly priced"* and the claim verdict says *"value_find"* — same property, two verdicts. At BCV $0.95M / ask $1.0M the prose says *"appears fully valued"* and the verdict says *"overpriced"*. Full ratio table in [SEMANTIC_AUDIT.md §4.1](SEMANTIC_AUDIT.md).

**Suggested fix:** Centralize at a single site. Create `briarwood/decision_model/value_position.py` exporting both the band constants and a single `pricing_view(bcv, ask) -> Label` function. Have `_pricing_view` in `current_value/agent.py` call it; have the editor and `verdict_with_comparison.py` thresholds import the same constants. Add a sweep test that walks BCV/ask ratios from 0.80 to 1.20 in 1% steps and asserts both paths return the same logical band. This single extraction also closes the 2026-04-24 "editor / synthesis threshold duplication" item below.

**Out of scope** for any active handoff — this is the headline finding from the 2026-04-27 audit; it should jump the queue. Two preconditions before the next semantic-layer refactor.

---

## 2026-04-27 — HIGH: synthesis confidence floors are invisible to the LLM prompts

**Severity:** High — the LLM can produce a stance the code will silently downgrade, and the user sees the downgraded stance with the LLM's original justification prose attached.

**Files:**
- [briarwood/synthesis/structured.py:27-28](briarwood/synthesis/structured.py#L27-L28) — `TRUST_FLOOR_STRONG = 0.70`, `TRUST_FLOOR_ANY = 0.40`. Hard gates: ≥0.70 unlocks "strong_buy"; <0.40 collapses stance to CONDITIONAL.
- [briarwood/llm_prompts.py:107-110](briarwood/llm_prompts.py#L107-L110) — `build_synthesis_prompt()` describes trust calibration qualitatively ("lower confidence when modules conflict, when key inputs are missing…") with no numeric anchors.
- [api/prompts/decision_summary.md](api/prompts/decision_summary.md) and the other tier prompts — same qualitative framing.

**Issue:** The code enforces hard numeric gates on stance. The LLM is asked to choose stance + confidence with no knowledge of where the gates sit. A model that emits stance="strong_buy" at confidence 0.55 will have its stance silently rewritten by `structured.py`; the prose justification in the response will still read like a strong-buy rationale, attached to a now-CONDITIONAL stance. The user sees the seam.

**Suggested fix:** Two options, pick one.
1. **Expose the constants in the prompt.** Add a literal sentence ("strong_buy unlocks at confidence ≥ 0.70; below 0.40 the stance must be conditional") and have `build_synthesis_prompt` interpolate the actual values from a single source of truth.
2. **Compute the stance deterministically before composition.** Have `structured.py` decide stance, pass the stance into the prompt as a fixed input, and ask the LLM to write the prose for the given stance rather than choose one.

Option 2 is the more invasive but more robust path. Either way, the floors should also live in the same `briarwood/decision_model/value_position.py` proposed in the pricing-view fix above.

**Out of scope** for any active handoff. Pre-condition for any work that touches the synthesizer prompt.

---

## 2026-04-27 — HIGH: orphan signature metrics — Forward Value Gap & Optionality Score

**Severity:** High — both names appear in product vocabulary and may appear in older internal docs / older external prompts. No code computes either as a scalar. Hallucination risk if any prompt ever names them.

**Files:**
- [briarwood/modules/risk_model.py:109-146](briarwood/modules/risk_model.py#L109-L146) — `premium_pct` is the closest implementation of "Forward Value Gap": a binary flag at ±10/+15, not a continuous gap.
- [briarwood/routing_schema.py:356](briarwood/routing_schema.py#L356) — `OptionalitySignal` Pydantic carrier (carrier, not score).
- [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) — produces qualitative `HiddenUpsideItem` records (label / magnitude / rationale).
- [briarwood/modules/bull_base_bear.py](briarwood/modules/bull_base_bear.py) — `bull_optionality = scarcity_score / 100 × 0.08` is a dollar-impact factor in bull case, not a user-facing score.

**Issue:** The audit prompt (and the "signature metrics" framing in product vocabulary) names both Forward Value Gap and Optionality Score as if they were computed scalars with bands. They aren't. Any prompt or doc that references "Forward Value Gap: 12%" or "Optionality Score: 72" is inventing the number. Today no in-repo prompt names them by that exact phrasing — but the risk is real for older internal materials and for any new prompt that reaches for the vocabulary.

**Suggested fix:** Per-metric decision needed.
- **Forward Value Gap**: either (a) define it formally — `forward_value_gap = (base_case_value − BCV) / BCV` with calibrated bands, surfaced as a first-class metric on the synthesis output — or (b) retire the phrase from product vocabulary and lean on the existing `premium_pct` flag.
- **Optionality Score**: either (a) define a scalar aggregator over `HiddenUpsideItem.magnitude` (with bands), or (b) retire the phrase and lean on the qualitative list as the user surface.

As part of this, grep all prompts and external docs for `"forward value gap"`, `"FVG"`, `"optionality score"`. If any hits exist, fix them in the same pass.

**Out of scope** for active handoffs. Worth a 30-minute owner decision before either Phase 4b (Scout) or any semantic-layer refactor — the answer affects both.

---

## 2026-04-27 — MEDIUM: BCV component-count drift in prompts and prior docs

**Severity:** Medium — wrong-number-of-things in prose; if any prompt still says "the four anchors of BCV," it is incorrect.

**Files:**
- [briarwood/agents/current_value/agent.py:18-24](briarwood/agents/current_value/agent.py#L18-L24) — `_COMPONENT_BASE_WEIGHTS` defines five components: `comparable_sales 0.40`, `market_adjusted 0.24`, `town_prior 0.16`, `backdated_listing 0.12`, `income 0.08` (sums to 1.00).

**Issue:** The recent audit prompt and likely some older internal docs / READMEs reference "BCV's 4 components." Code blends 5. Any downstream prose that names the four anchors is wrong.

**Suggested fix:** One-line grep sweep for `"four anchor"`, `"4 anchor"`, `"four component"`, `"4 component"` across `briarwood/`, `api/prompts/`, all `*.md` at repo root. Fix any hits to reflect five components by name and weight. Cheap; can ride along any future synthesis-prompt or current-value README touch.

**Out of scope** for any current handoff. Drive-by fix during a documentation pass.

---

## 2026-04-27 — MEDIUM: rent has three sources with no reconciliation carrier

**Severity:** Medium — a verdict that says "rent supports this deal" can't tell the user *which rent* it used, and divergence across sources is invisible.

**Files:**
- [briarwood/agents/income/schemas.py:35](briarwood/agents/income/schemas.py#L35) — `IncomeAgentOutput.monthly_rent_estimate` (best-estimate model output).
- [briarwood/agents/rent_context/schemas.py:19](briarwood/agents/rent_context/schemas.py#L19) — `RentContextOutput.market_rent_estimate` (market benchmark).
- [briarwood/schemas.py:462](briarwood/schemas.py#L462) — `ValuationOutput.effective_monthly_rent` (the value actually selected for cash-flow; may be user override, model estimate, or listing-parsed).

**Issue:** Three rent values can disagree silently. The selection logic is implicit in valuation. No structured carrier surfaces "these three estimates disagree by X%" so no prompt can call attention to the divergence. First time a user asks "which rent are you using?" the answer requires reading code.

**Suggested fix:** Add a small `RentReconciliation` dataclass in `briarwood/schemas.py` carrying `model_estimate`, `market_estimate`, `user_override`, `selected_value`, `selection_reason`, and a computed `divergence_pct`. Populate in valuation; surface in the synthesizer prompt as `rent_reconciliation` so prose can name the source. Two-day item.

**Out of scope** for active handoffs. Folds naturally into Phase 4b (Scout) since Scout is about surfacing non-obvious reads, and rent-source divergence is exactly the kind of thing Scout could highlight.

---

## 2026-04-27 — MEDIUM: numeric-grounding rule in synthesizer is informal — rounding drift accepted

**Severity:** Medium — the verifier catches *completely* ungrounded numbers but not "$820k" rendered as "$800k". Rounding drift toward psychologically friendly numbers passes silently.

**Files:**
- [briarwood/synthesis/llm_synthesizer.py:64-165](briarwood/synthesis/llm_synthesizer.py#L64-L165) — `_SYSTEM_PROMPT_NEWSPAPER` says "every dollar amount, percentage, multiplier, year, or count you cite must round to a value present in the `unified` JSON." No precision constant defined; rounded forms like `$820k` are explicitly allowed.
- [briarwood/synthesis/llm_synthesizer.py:335-401](briarwood/synthesis/llm_synthesizer.py#L335-L401) — regen path on verifier failure has the same vagueness.
- [api/guardrails.py](api/guardrails.py) — `Verifier` flags ungrounded numbers/entities; does not detect off-by-rounding.

**Issue:** "Rounds to a value present" has no precision rule. `$820,000` rendered as `$800k` is a 2.4% delta the verifier won't flag (it sees both `$820k` and `$800k` as plausibly rounded forms, only catching values like `$750k` that aren't near any present value). On a $1M property a 2% drift moves the user's reaction noticeably.

**Suggested fix:** Define a rounding precision constant (e.g., `MAX_ROUNDING_DELTA_PCT = 1.0`) in the verifier and enforce: every numeric token in the prose must be within ±X% of a value in `unified`. Reject regen drafts that introduce *new* numbers not in the original draft (current regen prompt allows arbitrary reframing). Test by feeding the verifier a draft with `$800k` when the truth is `$820k` and asserting it flags.

**Out of scope** for active handoffs. Pick up alongside any future synthesizer prompt work.

---

## 2026-04-27 — MEDIUM: `scarcity_score` naming collision across two modules

**Severity:** Medium — two metrics with the same name, different formulas, different inputs. Search-and-replace is treacherous; readers will conflate.

**Files:**
- [briarwood/agents/scarcity/scarcity_support.py:36-82](briarwood/agents/scarcity/scarcity_support.py#L36-L82) — `scarcity_score = 0.55 × location_scarcity + 0.45 × land_scarcity` (then composed into `scarcity_support_score`).
- [briarwood/modules/location_intelligence.py:62-240](briarwood/modules/location_intelligence.py#L62-L240) — `scarcity_score = weighted([(proximity, 0.40), (supply, 0.35), (rarity, 0.25)])`.

**Issue:** Both modules export a field called `scarcity_score`, computed differently from different inputs, with different units (one is 0-100, one is 0-1 scaled). Downstream code that reads "the scarcity score" gets one or the other depending on which module's payload it touched.

**Suggested fix:** Rename one. Two reasonable conventions: (a) prefix by source — `location_scarcity_score` for the location-intelligence one, `support_scarcity_score` for the scarcity-support one; (b) keep `scarcity_score` for the user-facing one (the support module's, which is the one the synthesizer cites) and rename the location-intelligence internal to `location_scarcity_subscore`. Add a one-line comment at each cite explaining the lineage.

**Out of scope** for active handoffs. Half-day rename + grep sweep.

---

## 2026-04-27 — MEDIUM: comp-scoring weights duplicated across two layers

**Severity:** Medium — the two weight sets serve different conceptual layers (single-comp scoring vs comp-stack base-shell layer) but have no comment tying each to its purpose. A future refactor could conflate them.

**Files:**
- [briarwood/modules/comp_scoring.py:221-271](briarwood/modules/comp_scoring.py#L221-L271) — single-comp weighted score: `proximity 0.30 + recency 0.25 + similarity 0.30 + data_quality 0.15`.
- [briarwood/comp_confidence_engine.py:202-273](briarwood/comp_confidence_engine.py#L202-L273) — Layer-1 base-shell confidence: `comp_count 0.25 + support_quality 0.25 + tier_distribution 0.20 + median_similarity 0.15 + price_agreement 0.15`.

**Issue:** Two weight sets in adjacent files. Currently scoring different things; the risk is a future "let's centralize the comp weights" sweep that picks the wrong source-of-truth.

**Suggested fix:** Two paths, pick one.
1. **Inline comments at both sites** spelling out what each weight set scores ("single-comp similarity" vs "comp-stack base-shell layer") and a sentence at top of each file.
2. **Centralize in `briarwood/scoring_constants.py`** with two named tuples — `SINGLE_COMP_WEIGHTS` and `COMP_STACK_BASE_SHELL_WEIGHTS` — and import from both sites.

Option 2 is cleaner and supports the broader extraction recommendation in [SEMANTIC_AUDIT.md §8](SEMANTIC_AUDIT.md).

**Out of scope** for active handoffs.

---

## 2026-04-27 — MEDIUM: `pricing_view` is a user-facing categorical output with no confidence

**Severity:** Medium — user reads "appears overpriced" with no signal of how sure the engine is. Combined with §4.1's drift, the user can also get a label that disagrees with the verdict claim.

**Files:**
- [briarwood/agents/current_value/agent.py:444-451](briarwood/agents/current_value/agent.py#L444-L451) — `_pricing_view` returns a string with no associated confidence.
- [briarwood/agents/current_value/schemas.py:93](briarwood/agents/current_value/schemas.py#L93) — `pricing_view: str` field on `CurrentValueOutput`.
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — many sites consume `pricing_view` and surface it directly to prose without confidence framing (e.g. lines 1017, 1091, 1797, 4072).

**Issue:** Every other major synthesizer field has a confidence band. `pricing_view` is one of the most user-impactful labels and has none. A "appears overpriced" emitted from a low-BCV-confidence run looks identical to one from a high-confidence run.

**Suggested fix:** When the pricing-view fix in §4.1 lands (centralized `value_position.py` module), have it return `(label, confidence)` rather than just `label`. Compute confidence as `min(bcv_confidence, comp_confidence)` or similar; expose to the synthesizer so prose can hedge ("appears overpriced, though comp coverage is thin").

**Out of scope** until the §4.1 centralization lands. Do them together.

---

## 2026-04-27 — LOW: `valuation` vs `current_value` module naming collision

**Severity:** Low — naming hazard only; no functional impact.

**Files:**
- [briarwood/modules/valuation.py:15-57](briarwood/modules/valuation.py#L15-L57) — thin wrapper around `current_value` that adds an HPI macro nudge.
- [briarwood/agents/current_value/agent.py](briarwood/agents/current_value/agent.py) — the actual BCV blender.
- [briarwood/modules/current_value.py](briarwood/modules/current_value.py) — scoped wrapper applying input-quality confidence caps.

**Issue:** Three modules in the call chain produce the same primary field (`briarwood_current_value`). Search for "where is BCV computed" lands in any of them. Future refactors that grep for "valuation" will miss the BCV agent and vice versa.

**Suggested fix:** Either (a) rename `briarwood/modules/valuation.py` → `briarwood/modules/valuation_with_macro_nudge.py` and add a header comment naming it as the macro-nudge wrapper; or (b) consolidate the macro nudge into `current_value` and delete `modules/valuation.py`. Path (b) is cleaner if the nudge isn't used independently.

**Out of scope** for active handoffs. Drive-by fix.

---

## 2026-04-27 — LOW: `decision_model/scoring.py` looks legacy — verify before delete

**Severity:** Low — dead-code candidate; needs verification.

**Files:**
- [briarwood/decision_model/scoring.py](briarwood/decision_model/scoring.py) — file header comment marks it as "largely deprecated."
- [briarwood/decision_model/scoring.py:51](briarwood/decision_model/scoring.py#L51) — `estimate_comp_renovation_premium()` is still consumed by `briarwood/modules/renovation_impact.py` (per audit cross-reference).

**Issue:** The file's own header says "largely deprecated" but at least one function is still in service. Either the comment is stale, or the renovation_impact dependency is itself stale and should be migrated.

**Suggested fix:** Grep for every import of `briarwood.decision_model.scoring`. For each consumer, decide: keep the function (rewrite header comment), or migrate the consumer to a non-deprecated source. If only `renovation_impact` consumes one function, move that function into `renovation_impact.py` and delete the rest of `decision_model/scoring.py`.

**Out of scope** for active handoffs. 1-hour cleanup.

---

## 2026-04-26 — Chart visual quality push — HIGH PRIORITY (umbrella)

**Severity:** High — charts are the user-visible surface where Briarwood looks least like a designed product. Owner feedback 2026-04-25 ("look like something that isn't being designed by a user rather than by an LLM") and 2026-04-26 ("I don't think the charts are great but we can table that") together describe a real quality gap that Phase 3 polish only partially closed.

**Files (the most-touched surfaces):**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) — every chart sub-component (`MarketTrendChart`, `CmaPositioningChart`, `ValueOpportunityChart`, `ScenarioFanChart`, `RentBurnChart`, `RentRampChart`, `RiskBarChart`, `HorizontalBarWithRangesChart`).
- [api/pipeline_adapter.py](api/pipeline_adapter.py) — the `_native_*_chart` event builders (legend / axis-label / value-format payload).
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — the SSE chart-spec types.

**Issue:** The chart layer has accumulated a list of small bugs and stale primitives that, taken together, undermine the impression of a designed product:
1. **`cma_positioning` "CHOSEN COMPS: Context only" chip** is permanently misleading post-Cycle-3 (filed below 2026-04-26).
2. **`value_opportunity` y-axis "Comp" label** renders as a vertical character stack `C / o / m / p` (filed below 2026-04-26).
3. **`cma_positioning` markers don't show diversity in real comp sets** — owner browser smoke 2026-04-26 confirmed all comps render as filled circles because Belmar's top-8 by weighted_score is all SOLD same-town (Cycle 5 marker scheme works but never triggers ACTIVE / cross-town glyphs in this market — comp set scoring needs to surface diversity, or the chart should sample for it).
4. **`cma_positioning` chart-prose alignment** — synthesizer can cite comps not in the chart's top-8 slice (filed below 2026-04-26).
5. **`cma_positioning` source-view drift** — the two-view defensive fix is in place but the deeper restructure (typed `source_views: dict[role, view_key]`) is queued (filed below 2026-04-26).
6. **Live SSE rendering glitch** — charts arrive mid-stream and reflow layout; sometimes need a page reload to render correctly (per user-memory `project_ui_enhancements.md`). The 2026-04-26 BROWSE-only `market_support_comps` panel suppression was a microcosm of this; the broader rendering still has rough edges.
7. **`feeds_fair_value` is dead architecture in the chart layer** — the chip, the marker tone fallback, several test fixtures all key on a flag that no longer carries product meaning post-Cycle-3 (filed below 2026-04-26).
8. **Chart styling is utilitarian** — markers are circles + triangles; legend is a flat row; no animation, no hover affordances, no progressive disclosure. The decision-tier surface needs to feel premium because the user is making a six-figure call.

The individual bugs are filed as separate Low-severity entries below for triage. This umbrella entry is the holding place for the broader theme: a coherent chart-quality push (visual polish, marker diversity, axis fixes, dead-code removal, live-render robustness) is a HIGH-priority quality lever, not a collection of cleanup tasks.

**Suggested approach:** A dedicated chart-quality cycle (or sub-cycle of Phase 4c BROWSE rebuild) with three sub-pieces — (a) close the seven small bugs above as a single sweep, (b) revisit chart styling primitives (markers, axes, captions, legend) for premium feel, (c) audit live SSE rendering for robustness. Estimated 1-2 days; produces the most user-visible quality gain available in the project today.

**Cross-references.** All seven specific items below carry their own filed entries with file paths and one-line scope. Do not pick them off in isolation when this umbrella is open — solve them together.

---

## 2026-04-26 — `cma_positioning` chart-prose alignment: synthesizer can cite comps not visible in the chart

**Severity:** Low — cosmetic / coherence. Surfaced during CMA Phase 4a Cycle 5 browser smoke (1008 14th Ave, Belmar — Turn 2 prose cited "103 2nd Avenue, currently asking $749,000" but the chart's top-8 rows did not include that comp).

**Files:**
- [api/pipeline_adapter.py::_native_cma_chart](api/pipeline_adapter.py) — caps the chart's comp rows at `priced_rows[:8]`.
- [briarwood/agent/dispatch.py::handle_browse](briarwood/agent/dispatch.py) — passes the full `session.last_market_support_view["comps"]` (up to 10 rows per Cycle 3c's top-N cap on `get_cma`) to `synthesize_with_llm` as `comp_roster`.

**Issue:** `get_cma` returns up to 10 comps (post-scoring, post-outlier-filter, top-N by `weighted_score`). The `cma_positioning` chart's `_native_cma_chart` further trims to the top 8 for visual compactness. The Cycle 5 synthesizer wiring passes the full roster to `synthesize_with_llm` — so the LLM can (and on 2026-04-26 did) cite comps that exist in the roster but didn't make the chart's slice. Reading the prose, the user can't reconcile "103 2nd Avenue, currently asking $749,000" with the chart that doesn't show it.

The marker scheme works correctly within the slice that *is* shown. The mismatch is purely a slice-misalignment between the chart and the synthesizer payload.

**Suggested fix:** One-line — clamp the `comp_roster` list `handle_browse` passes to `synthesize_with_llm` to the same top-N the chart renders (8). Mirror the slice exactly, ideally via a shared helper so the two surfaces can never drift again. Cost: the synthesizer loses access to the 9th and 10th ranked comps for citation, but those are by definition the lowest-scoring rows in the comp set so the prose loss is negligible. Alternative: bump the chart's row cap from 8 to 10, which is also one line but makes the chart 25% taller.

**Out of scope** for the current CMA Phase 4a Cycle 5 close-out (panel suppression + marker scheme + synthesizer prompt all landed). One-line cleanup item; can be picked up in Cycle 6 cleanup or any future BROWSE-rendering touch.

---

## 2026-04-26 — Property resolver matches wrong slug ("526 West End Ave" → NC instead of NJ)

**Severity:** Medium — silently sends the user to the wrong property. Surfaced in user-memory note `project_resolver_match_bug.md`; not previously filed in ROADMAP.

**Files:**
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — `_resolve_property_match` (the property-id resolver that maps free-text addresses to saved property slugs).

**Issue:** When the user types "526 West End Ave" without a state qualifier, the resolver matches a North Carolina property slug instead of the correct New Jersey one. Suggests the resolver is either (a) ranking matches by string similarity without weighting state-of-residence / pinned-context, or (b) iterating the saved-properties list in a directory-walk order that lets NC win on a tie. Either way, the user gets a confidently-wrong property loaded.

**Suggested fix:** Audit `_resolve_property_match` for state-aware ranking. Concretely: when the user's text doesn't include a state, prefer matches whose `summary.state` aligns with the session's recent activity (most-recent-property's state, or the inferred town's state). Add a regression test pinning "526 West End Ave" → NJ when the session has prior NJ context.

**Out of scope** for the active CMA Phase 4a work. Drive-by fix during any future dispatch-handler touch.

---

## 2026-04-26 — Live SSE rendering requires a page reload to display correctly

**Severity:** Medium — visible to every user, every BROWSE turn. Surfaced in user-memory note `project_ui_enhancements.md`; not previously filed in ROADMAP as its own entry.

**Files:**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) — chart-rendering SSE-event consumers.
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — SSE event types.
- [api/pipeline_adapter.py](api/pipeline_adapter.py) — chart-event emission ordering.

**Issue:** Owner reports that the chat surface sometimes needs a page reload before charts and structured cards render correctly. Symptoms include partially-loaded card layouts, mid-stream layout reflows when chart events arrive late, and generally a sense that the live-streaming response shape is fragile. The CMA Phase 4a Cycle 5 BROWSE-only `market_support_comps` panel suppression was a microcosm of this — duplicate comp surfaces caused a "glitch and reload" effect that we resolved by dropping one surface, but the broader rendering still has rough edges.

**Suggested fix:** Audit the SSE event order + the React reducer state machine that consumes them. Specifically check: (a) does the chart-card component re-mount when the chart-event arrives mid-stream (vs progressively rendering), (b) is the SSE consumer queueing events properly so partial state doesn't render, (c) are there any race conditions between the prose stream, the structured-card events, and the chart events that cause the layout to flicker?

Folds naturally into the Chart visual quality push above (item #6 in that entry).

**Out of scope** for Phase 4a Cycle 6 (cleanup is server-side). Pick up during Phase 4c BROWSE rebuild or a dedicated chart-quality cycle.

---

## 2026-04-26 — `ARCHITECTURE_CURRENT.md` / `TOOL_REGISTRY.md` keep drifting (process question)

**Severity:** Low — process / architectural question, no functional impact. Surfaced as a pattern observation 2026-04-26 high-level review.

**Files:**
- [ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md)
- [TOOL_REGISTRY.md](TOOL_REGISTRY.md)

**Issue:** Both audit docs have been "corrected" three separate times now: Handoff 2a Piece 6 reconciled nine specific schema drifts (DECISIONS.md 2026-04-24 entries); Cycle 4.2 found the `base_comp_selector.py` / "15% sqft tolerance" drift (filed below); Cycle 6 of Phase 4a is queued to update them again to reflect the post-handoff topology. The pattern is consistent: code changes → README is updated as part of the handoff → audit doc is forgotten and rediscovered drifted on the next handoff.

This isn't a single bug. It's a question about whether these audit docs should exist at all in their current form, or be retired in favor of READMEs-only. The READMEs are the authoritative source per CLAUDE.md priority order; the audit docs are explicitly *secondary* per CLAUDE.md ("known to drift at the field-name level"). Yet they keep being maintained, drift, and need to be re-reconciled.

**Suggested approach:** Three options to discuss with owner —
1. **Retire ARCHITECTURE_CURRENT.md / TOOL_REGISTRY.md.** Replace with a thin top-level index that links to each module's README. The handoff-by-handoff drift problem disappears because the audit content lives where the code does.
2. **Mechanically generate them from READMEs.** A script walks `briarwood/**/README*.md` at CI time and assembles ARCHITECTURE_CURRENT and TOOL_REGISTRY. The audit docs become a generated artifact, not an authored one — drift is impossible.
3. **Status quo + tighter ritual.** Make every PR that touches a module's README also touch the audit doc. CLAUDE.md already nominally requires this; the audit docs drift anyway.

Recommend (1) or (2). Status quo has been re-tried twice and produces the same pattern.

**Out of scope** for Phase 4a Cycle 6 (which itself needs to update the audit docs one more time). Pick up as a meta-cleanup during a quiet handoff.

---

## 2026-04-26 — Pre-existing failure: `StructuredSynthesizerTests::test_interaction_trace_attached`

**Severity:** Low — broken test, no production impact. Surfaced (but not caused) by CMA Phase 4a Cycle 5 synthesizer-prompt regression sweep.

**Files:**
- [tests/synthesis/test_structured_synthesizer.py](tests/synthesis/test_structured_synthesizer.py) `StructuredSynthesizerTests::test_interaction_trace_attached` — line ~174 `self.assertEqual(result["interaction_trace"]["total_count"], 8)` fails with `AssertionError: 9 != 8`.

**Issue:** The deterministic structured synthesizer (`briarwood/synthesis/structured.py::build_unified_output`) attaches an `interaction_trace` summary to the unified output. The test fixture pins `total_count == 8`, but the synthesizer is now reporting 9 — a single record drift somewhere upstream of the trace builder. Confirmed pre-existing on `main` by stashing the Cycle 5 changes and re-running — same failure, same line, same `9 != 8`.

**Suggested fix:** Identify which interaction-trace record is being added (likely a recent observability or telemetry hook recording one extra synthesizer-side event). Either update the test fixture to expect 9, or — if the new record is double-counting — fix the upstream emitter so the count returns to 8. The other assertions in the test (`"records" in result["interaction_trace"]`) all pass, so the trace shape is intact; only the count is drifted.

**Out of scope** for CMA Phase 4a Cycle 5 (synthesizer-prompt update for comp citations does not touch the structured synthesizer or its interaction-trace plumbing). Pick up in Cycle 6 cleanup or as a drive-by during the next synthesis-side change.

---

## 2026-04-26 — Pre-existing failure: `test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after`

**Severity:** Low — broken test, no production impact. Surfaced (but not caused) by CMA Phase 4a Cycle 5 pipeline-adapter test edits.

**Files:**
- [tests/test_pipeline_adapter_contracts.py](tests/test_pipeline_adapter_contracts.py) `PipelineAdapterContractTests::test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after` — line ~748 `self.assertIn("value_opportunity", [...])` fails with `AssertionError: 'value_opportunity' not found in []`.

**Issue:** The test mocks `_load_or_create_session` and populates the session with `last_town_summary`, `last_comps_preview`, `last_value_thesis_view`, `last_market_support_view`, `last_strategy_view`, `last_rent_outlook_view`, `last_projection_view`, etc. It then asserts that chart events for `value_opportunity`, `cma_positioning`, `scenario_fan`, `rent_burn` are emitted. After the 2026-04-25 OUTPUT_QUALITY Phase 2 work consolidated chat-tier execution onto a single artifact (`_chat_tier_artifact_for(...)`) and rewired BROWSE chart selection through the `_representation_charts(...)` path (which calls `_unified_from_session(session)` — returns `None` when no unified output is on the session), the chart-event list comes back empty for this test because the mocked session has no `unified_output` substrate. The companion test `test_dispatch_stream_emits_browse_cards_when_browse_turn_uses_generic_adapter` passes because it exercises a different code path that doesn't depend on the unified output the same way.

Confirmed pre-existing on `main` by stashing the Cycle 5 changes and re-running — same failure, same line.

**Suggested fix:** Extend the test setup to populate `session.last_unified_output` (or whatever the current `_unified_from_session` reads) with a minimal fixture so the chart selection path produces events. The fixture only needs enough structure to satisfy `UnifiedIntelligenceOutput.model_validate`; downstream readers tolerate sparse fields.

**Out of scope** for CMA Phase 4a Cycle 5. Cycle 5 only edited this test to update the `expected_head` order after suppressing `EVENT_MARKET_SUPPORT_COMPS` on BROWSE; the chart-emission failure is independent of that edit.

---

## 2026-04-26 — `cma_positioning` "CHOSEN COMPS: Context only" chip is stale post-Cycle-3 (and `feeds_fair_value` is dead architecture)

**Severity:** Low — cosmetic / misleading copy + dead architectural baggage. Surfaced during CMA Phase 4a Cycle 5 browser smoke. Folds into the umbrella "Chart visual quality push" entry above.

**Files (chip):**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) `CmaPositioningChart` — the metric-chip strip below the chart computes `explicitChosen = spec.comps.filter((comp) => comp.feeds_fair_value != null)` and renders `"Context only"` when `explicitChosen.length === 0`.
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) `_comp_row_from_cma` — does not populate `feeds_fair_value` on Engine-B comp rows.

**Files (broader `feeds_fair_value` retirement):**
- [api/pipeline_adapter.py::_native_cma_chart](api/pipeline_adapter.py) — passes `feeds_fair_value` per comp into the chart spec.
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — `CmaPositioningChartSpec.comps[]` declares `feeds_fair_value?: boolean | null`.
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) — the marker-tone fallback when `listing_status` is null still keys on `feeds_fair_value` to pick `CHART.bull` vs `CHART.neutral`.
- Several test fixtures across `tests/test_pipeline_adapter_contracts.py` and `tests/agent/test_dispatch.py` reference the flag.

**Issue:** The `feeds_fair_value` flag dates from the pre-Cycle-3 era when Engine A (saved comps, fair-value math) and Engine B (live Zillow, user-facing CMA) had different scoring pipelines. `feeds_fair_value: True` meant "this comp shaped the fair-value number"; `False` meant "this comp is context only." After Cycle 3 unified Engine A and Engine B onto the same scoring pipeline (`briarwood/modules/comp_scoring.py`), every comp in the BROWSE / DECISION CMA set is load-bearing — there is no "context only" tier any more. But `_comp_row_from_cma` doesn't set the flag, so the chart frame permanently renders "CHOSEN COMPS: Context only," which is wrong and visible to the user on every BROWSE turn. Beyond the chip itself, the flag persists across the SSE spec, the React component, and several test fixtures — dead architecture that's ripe for a single sweep.

**Suggested fix:** Two-step.

1. **Replace the chip.** Turn the `Chosen comps` chip into a `Comp set` chip that uses the new provenance — e.g. `"5 SOLD + 3 ACTIVE"` (or `"5 SOLD (2 cross-town) + 3 ACTIVE"`). Source the counts from `spec.comps` after the Cycle 5 marker scheme: count `listing_status === "sold"` and `listing_status === "active"` (with the cross-town subset broken out from the SOLD count).
2. **Retire `feeds_fair_value` entirely.** Remove from `_comp_row_from_cma`, `_native_cma_chart`'s spec.comps payload, the `CmaPositioningChartSpec.comps[]` type, the React component's marker-tone fallback (legacy/null `listing_status` rows render with the new `comp_set` provenance instead), and update the test fixtures. The flag is a leftover of the Engine-A/Engine-B-mixed era and no longer carries product meaning. The marker scheme already encodes the load-bearing distinction (SOLD vs ACTIVE).

Recommend doing both as a single sweep — they share the same files. Cleanup, ~1 hour.

**Out of scope** for CMA Phase 4a Cycle 5 (chart-set + marker-scheme + synthesizer prompt). Folds into the Chart visual quality push umbrella above; pick up in that cycle or as a drive-by fix during Phase 4c BROWSE rebuild.

---

## 2026-04-26 — `value_opportunity` chart y-axis label "Comp" renders as a vertical character stack

**Severity:** Low — cosmetic. Surfaced during CMA Phase 4a Cycle 5 browser smoke.

**Files:**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) `ValueOpportunityChart` — uses the shared `AxisLabels` component to render the y-axis label.
- The `_native_value_chart` payload in [api/pipeline_adapter.py](api/pipeline_adapter.py) sets `y_axis_label="Comp"`.

**Issue:** When the y-axis label is a single short word (e.g. `"Comp"`), the SVG text path falls through to per-character placement and the user sees `C / o / m / p` stacked vertically — one character per visual line — rather than the word rendered horizontally with a `transform="rotate(-90)"`. Reproduced on the second turn of the 2026-04-26 Cycle 5 smoke ("What rent would make this deal work?" — value_opportunity chart).

**Suggested fix:** Audit `AxisLabels` (likely defined in the same file) and confirm the y-axis branch uses a transform-rotated `<text>` element with proper `text-anchor` rather than per-character `<text>` placement. The fix is a few lines in the SVG rendering helper.

**Out of scope** for CMA Phase 4a Cycle 5 (which only touches the `cma_positioning` chart). Pre-existing bug in the value_opportunity chart's renderer.

---

## 2026-04-26 — Zillow URL-intake address normalization regression

**Severity:** Medium — affects every user who pastes a Zillow URL to onboard a property. Address comes back lowercased + missing comma separators ("1223 Briarwood Rd Belmar Nj 07719" instead of "1223 Briarwood Rd, Belmar, NJ 07719").

**Files:**
- `tests/test_searchapi_zillow_client.py::SearchApiZillowClientTests::test_url_parser_hydrates_listing_fields_via_searchapi` — pinned the expected output ("1223 Briarwood Rd, Belmar, NJ 07719") but actual is "1223 Briarwood Rd Belmar Nj 07719".
- `tests/test_listing_intake.py::ListingIntakeTests::test_zillow_url_listing_can_be_hydrated_via_searchapi` — same regression, second test file asserting the same fix point.
- Likely culprits: `briarwood/listing_intake/parsers.py::ZillowUrlParser` or the address-fallback path in `briarwood/data_sources/searchapi_zillow_client.py::_normalize_listing` / `_compose_address`.

**Issue:** Test was passing at some prior commit; failing on `main` as of 2026-04-26. Confirmed pre-existing (failure reproduces with `git stash` of all 2026-04-26 changes). Not caused by CMA Phase 4a Cycle 3a. Surfaced during Cycle 3a regression sweep per CLAUDE.md "Contradictions, Drifts, and Bugs Found During Work" — flagged here, not fixed (out of scope for the current handoff).

**Suggested fix:** `git bisect` between the test passing and `main` to identify the regressing commit. The address normalization helpers (`_normalize_address_string`, `_compose_address`, `_parse_address_parts`) are likely candidates. The fallback `_address_hint_from_url` (used when SearchApi returns no row matching) parses the URL slug and may be uppercasing/lowercasing inconsistently.

**Out of scope** for CMA Phase 4a (which is focused on the search-listings CMA path, not the URL-intake hydration path).

---

## 2026-04-26 — BROWSE summary card rebuild (parking lot)

**Severity:** Medium — most-asked product surface; shape is wrong but blocked on substrate.

**Origin.** 2026-04-26 BROWSE walkthrough Thread 1. Owner read of the current "what do you think of 1008 14th Ave, Belmar, NJ" response: the bottom RECOMMENDATION card is filler — restates the recommendation as "WHY THIS PATH" then dumps monthly carry / NOI / rental ease / cash-on-cash with no narrative. Owner direction: rebuild the card so it becomes the single primary summary card, with drilldowns the user can expand into the pieces (comps, value thesis, projection, rent, town, scout insights, etc.). Response shape becomes: prose at top → ONE rich summary card with drilldowns → secondary cards collapse / hide behind drilldowns.

**Why parked.** Two upstream prerequisites must land first or the rebuild can't honestly hold together:
1. **Real comps** — the rebuilt summary card needs to cite real comp evidence in its body. Today's CMA is two-engine and Engine B (the user-facing one) doesn't have Engine A's scoring/adjustment logic. Tracked in [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md) (Phase 4a).
2. **Scout drilldown surface** — the rebuilt card's "Worth a closer look" / "Briarwood noticed" row needs scout output to populate it. Today's scout is single-pattern and claims-wedge-only. Tracked in [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) (Phase 4b).

**Suggested approach when picked up.** Promote this entry to a `BROWSE_REBUILD_HANDOFF_PLAN.md` (Phase 4c) once Phase 4a + Phase 4b land. Scope at that point: collapse the existing card stack into one `BrowseSummaryCard` React component with sectioned drilldowns; integrate the scout drilldown row from Phase 4b Cycle 3; cite real comps from Phase 4a; keep the synthesizer's newspaper-voice prose as the lead. Open layout questions today (e.g., where the chart strip lives relative to the summary card; how drilldowns animate; mobile vs desktop) belong in that plan, not here.

**Cross-ref.** [PRESENTATION_HANDOFF_PLAN.md](PRESENTATION_HANDOFF_PLAN.md) Open Design Decision #7 (editor pass / paragraph-with-interleaved-charts layout) is conceptually adjacent — the rebuild is a chance to revisit whether an editor pass is needed once the substrate is right.

---

## 2026-04-26 — Renovation premium pass-through to live comps (deferred from Cycle 4.3)

**Severity:** Medium — Engine A computes a measured renovation premium that doesn't reach live (Zillow) comps. Affects fair-value math when subject is a renovation play and comps are mostly live rows.

**Files:**
- [briarwood/decision_model/scoring.py:51](briarwood/decision_model/scoring.py#L51) — `estimate_comp_renovation_premium`. Today operates on `AnalysisReport`; Engine-A-internal.
- [briarwood/agents/comparable_sales/agent.py:784](briarwood/agents/comparable_sales/agent.py#L784) — TODO comment: "feed measured renovation premium from estimate_comp_renovation_premium()".
- [briarwood/agent/tools.py](briarwood/agent/tools.py) `get_cma` — Engine B's per-row scoring at `_score_and_filter_comp_rows` would be the integration point.

**Issue:** `estimate_comp_renovation_premium` reads subject `condition_profile` and `capex_lane` to estimate how much of a comp's price-per-sqft delta is renovation-premium. Live Zillow rows don't carry these fields. Two failure modes if applied naively: (a) defaulting subject condition silently distorts the premium math; (b) skipping the premium adjustment for rows missing the data leaves the user-facing CMA blind to renovation differences between subject and comp.

**Suggested fix:** Two-step.
1. Decide whether renovation-premium-on-Zillow is actually load-bearing for prose. Wait for Cycle 5 (BROWSE wiring) to land and observe real-traffic CMA prose. If the synthesizer's comp citations consistently land cleanly without renovation context, the feature can stay deferred or be retired.
2. If needed: extend `estimate_comp_renovation_premium` to accept a `ComparableProperty`-shaped input (or its dict form), with an explicit "no renovation context" branch that surfaces the missing data as a `selection_rationale` qualification rather than silently defaulting. Wire into `_score_and_filter_comp_rows`.

**Out of scope** for the current CMA Phase 4a Cycle 4 work. Originally scoped as Cycle 4.3; deferred per the Cycle 4 wrap-up because the data-availability problem (Zillow rows missing condition data) is real and applying the premium broadly would silently distort. Revisit after Cycle 5 lands.

---

## 2026-04-26 — Plumb subject lat/lon through `summary` for per-row CMA distance filtering

**Severity:** Low-Medium — quality-of-life. Adjacency-map cross-town expansion (CMA Phase 4a Cycle 4.1) provides the geographic constraint today; per-row distance enforcement is the next-cleaner option.

**Files:**
- [briarwood/agent/tools.py](briarwood/agent/tools.py) `get_property_summary` and the `summary` dict shape.
- [briarwood/agent/tools.py](briarwood/agent/tools.py) `_score_and_filter_comp_rows` (currently called with `subject_lat=None, subject_lon=None` defaults; proximity falls back to neutral 0.55).
- [briarwood/modules/cma_invariants.py](briarwood/modules/cma_invariants.py) — `MAX_DISTANCE_MILES_CROSS_TOWN = 3.0` constant exists but isn't enforced anywhere yet.

**Issue:** Cycle 4.1 added cross-town SOLD expansion using a hand-tuned `TOWN_ADJACENCY` map. The map is a reasonable proxy for geographic proximity within the six-town shore corridor, but it's not data-driven and doesn't enforce `MAX_DISTANCE_MILES_CROSS_TOWN`. The cleaner long-term shape is: plumb subject lat/lon through `summary.json` (geocode at intake time, cache), then enforce the 3-mile cap per-row in `_score_and_filter_comp_rows`. That would also let `score_proximity` produce non-neutral scores for both same-town and cross-town rows.

**Suggested fix:**
1. Add `latitude` / `longitude` fields to the property summary contract. Source: existing geocoding in `briarwood/agents/comparable_sales/geocode.py` (already used to enrich saved comps), or a fresh per-property lookup at intake time. Cache on the property's `summary.json`.
2. Pass `subject_lat` / `subject_lon` from `summary` into `_score_and_filter_comp_rows` in `get_cma`.
3. Add an explicit per-row distance filter: drop rows where `distance_to_subject_miles > MAX_DISTANCE_MILES_CROSS_TOWN` (and the row is cross-town) or `> MAX_DISTANCE_MILES_SAME_TOWN` (and the row is same-town). This makes the existing distance constants finally load-bearing.
4. Once distance-based filtering is in place, the adjacency map can stay as a "which towns to query" coarse filter (adjacency limits the SearchApi call surface to nearby towns) while distance becomes the per-row truth.

**Out of scope** for CMA Phase 4a Cycle 4. The adjacency map is sufficient for the current six-town product geography; per-row distance becomes important when (a) we expand beyond Monmouth, or (b) we want non-neutral proximity scoring on Engine B comps.

---

## 2026-04-26 — `base_comp_selector.py` / "15% sqft tolerance" drift in audit docs

**Severity:** Low — mechanical doc drift; no user-facing impact. README is authoritative and now correct; the audit docs (priority #4) need to follow.

**Files carrying the drift:**
- [TOOL_REGISTRY.md](TOOL_REGISTRY.md) `:113` ("15% tolerance"), `:166` ("Hardcoded: 15% sqft tolerance for comp matching"), `:167` ("Cross-town comps TODO flagged in base_comp_selector.py").
- [ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md) `:233` ("Cross-town comp TODO in `base_comp_selector.py`").
- [CMA_SURFACE_MAP.md](CMA_SURFACE_MAP.md) `:20`, `:25` — Cycle 1 audit snapshot; lower-priority reference doc, but worth correcting if the sweep happens.

**Issue:** Three audit docs share the drift cleared in [briarwood/modules/README_comparable_sales.md](briarwood/modules/README_comparable_sales.md) 2026-04-26 (CMA Phase 4a Cycle 4 changelog entry). The cited file `briarwood/agents/comparable_sales/base_comp_selector.py` does not exist; the actual sqft logic at [briarwood/agents/comparable_sales/agent.py:429-444](briarwood/agents/comparable_sales/agent.py#L429-L444) is a sliding score penalty with rationale thresholds at 10% and 20% (no hard tolerance band); the same-town filter is enforced at the provider level ([briarwood/modules/comparable_sales.py:76-86](briarwood/modules/comparable_sales.py#L76-L86)) with no TODO comment.

**Suggested fix:** Mechanical sweep — replace each cited reference with the corrected pointer. README_comparable_sales.md's Cycle 4 changelog entry has the canonical wording; mirror that into the audit docs. Estimated 10 minutes.

**Out of scope** for the CMA Phase 4a Cycle 4 sqft-README sweep (which was scoped as README-only). Surfaced 2026-04-26 during that sweep per CLAUDE.md "Contradictions, Drifts, and Bugs Found During Work."

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

**In progress 2026-04-26** — promoted to handoff [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md). Cycles 1, 1.5, 2, 3a, 3b, 3c, 4.1 (cross-town), 4.2 (sqft-README drift), and 5 (BROWSE wiring) LANDED. Engine A and Engine B now share one scoring pipeline (`briarwood/modules/comp_scoring.py`); Engine B issues SOLD + ACTIVE SearchApi calls plus cross-town SOLD expansion when same-town SOLD count is below `MIN_SOLD_COUNT`; saved comps demoted to defensive fallback; outlier filter via tax-assessed-vs-price ratio; per-row `listing_status` and `is_cross_town` provenance; `validate_cma_result` invariant check. The BROWSE chart set now includes `cma_positioning` (4 charts), gated on the comp set being non-empty; chart markers distinguish SOLD / ACTIVE / cross-town SOLD per row; the standalone `market_support_comps` panel is suppressed on BROWSE because the chart subsumes it; `synthesize_with_llm` accepts a `comp_roster` kwarg so prose cites specific comps with provenance ("sold for $X" / "currently asking $Y" / "in [neighbor town]") and the verifier accepts comp ask prices as grounded values. Cycle 4.3 (renovation premium pass-through) DEFERRED to its own follow-up. Cycle 6 (cleanup — `claims/pipeline.py` graft retirement, README sweeps, smoke) remains. Do not close this entry until CMA Phase 4a is fully closed.

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

**Out of scope here (separate ROADMAP):**
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

## 2026-04-26 — `cma_positioning` source-view drift in non-BROWSE handlers

**Severity:** Medium — surfaces as broken chart anchors (`ASK: —`, `FAIR VALUE: —`) on whichever handler triggers the bug.

**Files:**
- [briarwood/representation/agent.py::render_events](briarwood/representation/agent.py) — chart-id → source-view dispatch
- [api/pipeline_adapter.py::_native_cma_chart](api/pipeline_adapter.py) — renderer that reads ask/fair_value/value_band from a single view dict

**Issue.** The Representation Agent's `RepresentationSelection` carries one `source_view` per chart, but `cma_positioning` fundamentally needs two views: `last_value_thesis_view` for ask / fair_value / value_band anchors, plus `last_market_support_view` for the comp rows. When the agent picks `last_market_support_view` as the single source (because it has the comps the LLM cited), the renderer's anchor lookups silently return None and the chart paints with `—` placeholders. Reproduced 2026-04-26 on a BROWSE turn before the BROWSE chart-set enforcer landed; since BROWSE no longer uses `cma_positioning`, the bug is currently latent for non-BROWSE handlers (DECISION, EDGE) that may select the chart through the agent.

**Resolved 2026-04-26 (partial — defensive fix only).** `agent.render_events` now overrides the primary view to `last_value_thesis_view` whenever the chart kind is `cma_positioning`, with `market_view` already injecting the market-support comps. This prevents the broken-anchor render on any handler that goes through the agent for chart selection.

**Suggested follow-on.** Restructure `RepresentationSelection` to carry an optional `secondary_source_view` (or a typed `source_views: dict[role, view_key]` mapping) so multi-view charts are first-class instead of patched per-chart. Two-views-per-chart will recur as the chart catalog grows; the first instance is `cma_positioning`, the second is likely any future overlay chart that mixes property anchors with comp/market context.

---

## 2026-04-25 — `presentation_advisor` bypasses the shared LLM observability ledger

**Severity:** Low — same bug class as the existing `local_intelligence/adapters.py` entry. Cleanup, not user-facing.

**Files:**
- [briarwood/agent/presentation_advisor.py](briarwood/agent/presentation_advisor.py) — `advise_visual_surfaces`
- [briarwood/agent/llm_observability.py](briarwood/agent/llm_observability.py) — `complete_structured_observed`

**Issue.** The 2026-04-25 audit's live trace showed `get_property_presentation` taking ~3 seconds and emitting no LLM call records to the per-turn manifest. The tool calls `advise_visual_surfaces`, which uses the raw OpenAI client (`llm.complete_structured(...)`) directly rather than going through the observed wrapper. The LLM ledger and the per-turn manifest don't see this call, so cost / latency / success-rate telemetry for it is invisible.

**Suggested fix:** Wrap the call site in `presentation_advisor.py` with `complete_structured_observed(surface="presentation_advisor.advise", ...)` analogous to the router and composer wiring. Same pattern as the `local_intelligence/adapters.py` follow-up entry above, which is a sibling case.

Surfaced during 2026-04-25 output-quality audit handoff. Cross-ref [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §9.

**Resolved 2026-04-26** (Phase 2 Cycle 6 cleanup item 1). `advise_visual_surfaces` at [briarwood/agent/presentation_advisor.py:68](briarwood/agent/presentation_advisor.py#L68) now routes through `complete_structured_observed(surface="presentation_advisor.advise", ...)`. The call shows up in the shared LLM ledger and the per-turn manifest's `llm_calls` list with `surface="presentation_advisor.advise"`. New regression test `tests/agent/test_presentation_advisor.py::PresentationAdvisorTests::test_advise_visual_surfaces_records_call_in_ledger` pins the ledger contract. The `local_intelligence/adapters.py` sibling entry remains open.

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

**Additional misses observed 2026-04-25** (during Cycle 5 post-landing UI smoke):
- "Why were these comps chosen?" → classified as `RESEARCH` (running `research_town`) instead of `EDGE` with the comp_set follow-up path. The contextualize-followup rewrite at [briarwood/agent/dispatch.py:4536-4551](briarwood/agent/dispatch.py#L4536-L4551) has a `_COMP_SET_RE` that matches "comp set" but apparently doesn't catch "Why were these comps chosen" (the regex looks for "comp set", "cma", "comps" with specific context). The user's clear intent was a comp-set followup on the current property; the LLM router took it as a market-research query about the area. This is two-issues-in-one: the context-rewrite regex is too narrow, and the LLM router's RESEARCH classification ignored the pinned property context.

**Additional miss observed 2026-04-26** (during CMA Phase 4a Cycle 5 browser smoke, per-turn manifest evidence):
- "show me the comps" (with a pinned BROWSE-tier property) → classified as `BROWSE` (conf 0.60), dispatched to `browse_stream`. The classifier ran the full BROWSE cascade again instead of routing to `EDGE` with the comp_set follow-up path. Result: same handler, same prose template, same `comp_roster`, near-identical response — visually it looks like the user re-asked "what do you think of X." Same root cause as the "Why were these comps chosen?" miss above: the LLM router doesn't recognize "the comps" / "show me X" phrasings as comp-set follow-ups when there's a pinned property. The `_COMP_SET_RE` regex should also catch "show me the comps", "list the comps", "what are the comps", "the comp set".

When the audit-against-corpus work happens, a few things to check:
1. The `_COMP_SET_RE` regex coverage. "Why were these comps", "what comps did you use", "explain your comp choice", "show me the comps", "list the comps", "what are the comps" should all rewrite to EDGE.
2. The LLM router's prompt should mention that questions referencing "these / your / the" comps with a pinned property are property-followups, not market research.
3. The "Show me listings here" query (Cycle 5 same UI smoke) classified as BROWSE rather than SEARCH — also worth review. The user wanted a list, not the BROWSE-style first-read prose.
4. The "show me the comps" miss (2026-04-26) is the same shape as #3 — "show me X" with X being a Briarwood-side artifact (comps, listings, etc.) should route to a list/drilldown surface, not BROWSE.

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

**Step 1 resolved 2026-04-25** (between Cycles 4 and 5). `get_cma` gains an optional keyword-only `thesis` parameter. When provided (chat-tier callers), the internal `get_value_thesis` call is skipped and `CMAResult` populates directly from the passed dict. `handle_browse` builds the thesis dict from `chat_tier_artifact["unified_output"]["value_position"]` plus the `valuation` module's metrics via the new `_browse_thesis_from_artifact` helper. Default behavior (`thesis=None`) is unchanged for `handle_decision` / `handle_edge` callers, which still go through the per-tool routed pattern until Cycle 5 rewires them. New regression test: `tests/agent/test_tools.py::ContractToolTests::test_get_cma_skips_internal_value_thesis_when_caller_provides_thesis` verifies `get_value_thesis` is NOT called when a thesis is passed.

**Step 2 still open.** The cache-miss audit on `valuation` across the consolidated path vs. `get_value_thesis`'s routed path was deferred — the leak is now zero on `handle_browse` (the consolidated path doesn't trigger the duplicate), so the audit's value drops to "diagnostic curiosity unless we re-enable per-tool routed runs for some reason." Worth noting for whoever picks up the broader `MODULE_CACHE_FIELDS` cleanup item.

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

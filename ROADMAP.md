# Briarwood — Roadmap

The forward plan for the project. Reorganized 2026-04-27 to make status, size,
and dependencies legible at a glance. Same content as before — restructured,
deduplicated, and sized.

This file is now organized into nine sections:

1. **The Sequence** — the ordered list of major moves with one-line "why now" rationale.
2. **Closing Out** — handoff plans 80%+ done with cleanup remaining.
3. **Strategic Initiatives** — multi-handoff umbrellas (AI-Native Foundation, Scout, Semantic Audit, Chart Quality, BROWSE rebuild).
4. **Tactical Backlog** — single-session and short-handoff items, by severity.
5. **Process & Meta** — cross-cutting "how-we-work" items.
6. **Parking Lot** — explicitly deferred work.
7. **Suggestions for Next Planning Session** — proposals for future scope; not yet roadmap items.
8. **Dedup log** — items merged from one location into another during the 2026-04-27 reorg.
9. **Sizing gaps to resolve** — items where size estimate is missing from source docs.

This file was previously named `FOLLOW_UPS.md`; renamed to `ROADMAP.md` on
2026-04-27 to reflect that it now holds the strategic plan as well as tactical
follow-ups. Restructured 2026-04-27 (same day) to add the section organization
above.

Distinct from [DECISIONS.md](DECISIONS.md) (which captures product/architectural
decisions and audit-doc drift) and [GAP_ANALYSIS.md](GAP_ANALYSIS.md) (which
captures architectural gaps relative to the six-layer target). This file holds
the forward plan; DECISIONS.md is the historical decision log.

Briarwood is being built as an AI-native, "queryable" company. See
[`design_doc.md`](design_doc.md) § 3.4 (AI-Native Principles) for the
load-bearing principles. Treat them as constraints on any architectural
decision — when a tradeoff is in front of you, the side that honors more of
those principles wins.

If you find a contradiction between sources, never silently reconcile.
Surface it to the user. Add an entry to DECISIONS.md if the resolution
requires judgment, or to ROADMAP.md if it's mechanical.

**Sizing convention:** `S` = single Claude Code session, < 1 day. `M` = 1
handoff, ~1–2 days. `L` = 2–3 handoffs. `XL` = umbrella with multiple
handoffs.

**Impact label convention** (added 2026-04-28): open roadmap items carry an
`[impact: ...]` tag showing the primary product subsystem touched by the
work. Labels are: `LLM & Synthesis`, `Output & Presentation`,
`Property Analysis`, `Routing & Orchestration`,
`Data, Persistence & Feedback`, `Scout`, `UI & Charts`,
`Docs, Process & Repo Health`, and `Unclassified / Needs Owner Decision`.
When a label is unclear, keep the item on the list and park it as
`Unclassified / Needs Owner Decision` rather than forcing a guess.
See [ROADMAP_TRIAGE.md](ROADMAP_TRIAGE.md) for the scan-friendly no-drop
index.

**Status convention** (added 2026-04-28): every entry's rubric carries a
`**Status:**` line. Default is `OPEN`. Closed items are marked
`RESOLVED YYYY-MM-DD — <where it closed>` and the section heading is
prefixed with `✅`. Resolved entries STAY in their original section; they
are not moved or deleted. The §10 *Resolved Index* table at the bottom of
this file is the scan-friendly view across all closed items.

---

## §1. The Sequence

The ordered list of major moves. Each step carries a `[source]` tag —
`[DECISIONS.md 2026-04-27]` for steps formally decided in that entry,
`[ROADMAP banner]` for steps inherited from the prior banner organization.

1. **Phase 4a Cycle 6 — close the CMA handoff** `[ROADMAP banner]` ✅ RESOLVED 2026-04-28
   *Why now:* Phase 4a is 5/6 cycles landed (CMA quality). Cycle 6 cleanup
   unlocks Phase 4b (Scout) and AI-Native Stage 1.
   *Outcome:* Cycle 6 closed 2026-04-28 — graft retired through canonical
   scoped runner; audit docs reconciled; Phase 4a complete. Sequence step 2
   (AI-Native Stage 1) now unblocked. See [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md)
   Cycle 6 closeout for the full landing notes.
2. **AI-Native Foundation Stage 1 — persistence** `[DECISIONS.md 2026-04-27]` ✅ RESOLVED 2026-04-28
   *Why now:* Scout (Phase 4b) inherits persisted artifacts to mine. Without
   Stage 1, every Scout iteration leaves no inspectable trace.
   *Outcome:* Landed via [PERSISTENCE_HANDOFF_PLAN.md](PERSISTENCE_HANDOFF_PLAN.md)
   Cycles 1-4 on 2026-04-28. `turn_traces` table, `data/llm_calls.jsonl` sink,
   and `messages` metric columns all populated by default; success-criteria
   SQL query returns real numbers. Sequence step 3 (Stages 2-3) now unblocked.
   See §3.1 Stage 1 closeout for landing notes.
3a. **AI-Native Foundation Stage 2 — feedback loop** `[DECISIONS.md 2026-04-27]` ✅ RESOLVED 2026-04-28
    *Why now:* Scout inherits closed user-feedback signal to learn from.
    *Outcome:* Landed via [FEEDBACK_LOOP_HANDOFF_PLAN.md](FEEDBACK_LOOP_HANDOFF_PLAN.md)
    Cycles 1-4 on 2026-04-28. `feedback` table + `POST /api/feedback` +
    thumbs UI in assistant bubbles + closed-loop synthesis hint
    (`feedback:recent-thumbs-down-influenced-synthesis` manifest tag
    surfaces in `turn_traces.notes`). Both write-side and read-side live;
    loop closure auditable in SQL. See §3.1 Stage 2 closeout for landing
    notes. Sub-step 3b (Stage 3 dashboard) remains open.
3b. **AI-Native Foundation Stage 3 — business-facing dashboard** `[DECISIONS.md 2026-04-27]` ✅ RESOLVED 2026-04-28
    *Why now:* Scout outputs need a measurement surface; Stage 1 + Stage 2
    substrate (turn_traces, llm_calls.jsonl, feedback) was live and
    waiting for a read-side UI.
    *Outcome:* Landed via [DASHBOARD_HANDOFF_PLAN.md](DASHBOARD_HANDOFF_PLAN.md)
    Cycles 1-4 on 2026-04-28. Three FastAPI endpoints under `/api/admin/`
    gated behind `BRIARWOOD_ADMIN_ENABLED=1`; Next server-component
    routes at `/admin` (top-line metrics: latency by answer_type, cost
    by surface, thumbs ratio, top-10 slowest, top-10 highest-cost) and
    `/admin/turn/[turn_id]` (full TurnManifest + feedback rows + the
    `feedback:recent-thumbs-down-influenced-synthesis` tag highlighted
    as the Stage 2 closure-loop audit affordance). Plain HTML/CSS bars
    per the owner-locked decision; chart-library evaluation deferred to
    Phase 4c UI reconstruction (§3.4.7). With 3a + 3b both closed, the
    AI-Native Foundation umbrella's user-visible phase is complete and
    sequence step 4 (Phase 4b Scout) is now unblocked.
4. **Phase 4b — Scout buildout** `[DECISIONS.md 2026-04-27]` ✅ RESOLVED 2026-04-28
   *Why now:* Apex differentiator for Briarwood vs Zillow/Redfin/realtor.com.
   Substrate is ready (`rent_zestimate` from CMA Cycle 3a is landed).
   *Cycle 1 outcome:* LLM scout module + tests landed isolated (no handler
   wiring). `scout_unified` callable; `SurfacedInsight` extended with
   optional `confidence` + `category`. 11 new tests.
   *Cycle 2 outcome:* `handle_browse` calls scout between representation
   plan and synthesizer; insights cached on `session.last_scout_insights`
   and threaded into `synthesize_with_llm` via a new kwarg. Newspaper
   "## What's Interesting" beat now an explicit weave-the-insight
   directive. New `scout_insights` SSE event (Python + TS mirror).
   8 new tests; baseline holds at 16 fail / 1581 pass.
   *Cycle 3 outcome:* `ScoutFinds` React component lands as the
   dedicated drilldown surface between synthesizer prose and the
   card stack. `category → drill-in route` mapping in TS
   (`scout-routes.ts`) with graceful fallback for LLM-invented
   categories. Live browser smoke confirmed end-to-end render.
   Two prompt-tuning items filed for Cycle 6 (scout angles too
   synthesizer-adjacent; LLM invents categories outside canonical
   set).
   *Cycle 4 outcome:* Same scout-then-synthesize wiring from Cycle 2
   applied to `handle_decision` (wedge fall-through path) and
   `handle_edge`. Per-tier VOICE block added to scout system prompt
   (browse = first-impression / decision = decision-pivot / edge =
   skeptical). The Cycle 2/3 SSE event + ScoutFinds React surface
   light up automatically on DECISION/EDGE turns — no adapter or
   frontend change needed.
   *Cycle 5 outcome:* `scout(...)` is now the shared registry
   dispatcher across claim-wedge and chat-tier inputs. `_PATTERNS`
   dispatches by input type; `scout_claim` remains as the stable
   claim-wedge wrapper. `SurfacedInsight.confidence` is the universal
   sort key; deterministic `uplift_dominance` derives confidence from
   the dominance multiple. `briarwood/value_scout/README.md` updated
   inline for the contract change.
   *Cycle 6 outcome:* deterministic chat-tier fallback rails
   (`rent_angle`, `adu_signal`, `town_trend_tailwind`) are registered
   under `UnifiedIntelligenceOutput`, so Scout can still surface Finds
   when the LLM scout returns empty or no LLM is available. Chat-tier
   Scout calls now record a manifest yield note
   (`insights_generated`, `insights_surfaced`, `top_confidence`).
   The LLM scout prompt was tuned away from synthesizer-adjacent
   restatements and toward canonical category discipline.
   *Cycle 7 outcome:* closeout docs reconciled across
   `GAP_ANALYSIS.md`, `TOOL_REGISTRY.md`, `ARCHITECTURE_CURRENT.md`,
   `CURRENT_STATE.md`, `ROADMAP.md`, `DECISIONS.md`, and the Scout
   handoff plan. Phase 4b is complete; true parallel firing and
   user-type conditioning remain future Layer 5 target gaps, not
   open Phase 4b work.
5. **AI-Native Foundation Stage 4 — model-accuracy loop** `[DECISIONS.md 2026-04-27]` ✅ RESOLVED 2026-04-28
   *Why now:* Scout shipped; close Loop 1 (per
   [`design_doc.md`](design_doc.md) § 7) with real outcome data.
   *Outcome:* Implementation substrate landed 2026-04-28 via
   [`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md) (manual outcome
   ingestion, one-shot JSONL backfill, saved-property alignment backfill,
   `model_alignment`, module receiver hooks, analyzer reporting). Loop 1
   was then exercised end-to-end against the owner-estimate outcome row
   (`526-w-end-ave-avon-by-the-sea-nj`, expected close $1.385M;
   `data/outcomes/property_outcomes.jsonl`). The first run flagged a real
   intake bug: `inputs.json:facts.town` was `"Avon By The Sea Nj"` (state
   glued onto town string), so the comp store's town-keyed lookup found
   zero matches and `comparable_sales` returned `mode: fallback`,
   confidence 0; `current_value` / `valuation` returned a heavily
   market-adjusted-down $935K vs ask $1.49M. Town string fixed in place
   for this property; re-run produced 3 honest `model_alignment` rows —
   `current_value` and `valuation` at $1,311,200 (APE 5.33%,
   alignment_score 0.73) and `comparable_sales` at $1,484,741 from 5
   same-town SFR comps + rental income (APE 7.20%, alignment_score 0.64).
   All confidences (0.51–0.59) sit below the 0.75 high-confidence
   threshold, so no human-review tuning candidates surfaced; analyzer
   prints clean module-summary report; dedupe verified. Loop 1
   mechanically closed AND surfaced its first real defect (the intake
   normalizer bug, now tracked in §4). Sequence step 6 (Phase 4c BROWSE
   rebuild) now unblocked. Real public-record sale ingestion remains a
   follow-up under §4 ("Automate public-record outcome ingestion") and
   the new ATTOM-outcome adapter slice.
6. **Phase 4c — BROWSE summary card rebuild** `[ROADMAP banner]` — **ACTIVE 2026-04-28**, plan: [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md)
   *Why now:* Substrate (real comps + Scout outputs + closed model-accuracy
   loop) is in place; the rebuilt response surface needs all three to
   honestly hold together.
   *Plan reframe (2026-04-28):* original "one rich summary card with
   drilldowns" replaced with **three stacked sections inside the assistant
   bubble** — Section A (`BrowseRead`: stance pill + headline + masthead
   chart + prose), Section B (`BrowseScout`: peer section, conditional
   null), Section C (`BrowseDeeperRead`: 8 chevron-list drilldowns).
   Newspaper-front-page hierarchy via section sub-heads + thin rules + no
   nested boxed cards. See `BROWSE_REBUILD_HANDOFF_PLAN.md` for the cycle
   plan (5 cycles + closeout, including the §3.4.7 chart-library eval as
   Cycle 5).

Sequencing call recorded in [DECISIONS.md](DECISIONS.md) 2026-04-27 entry —
that entry formally fixes steps 2–5; steps 1 and 6 are bookends inherited
from the prior banner.

---

## §2. Closing Out

Handoff plans 80%+ done, with cleanup remaining.

### Phase 2 — Output Quality (`[size: S]`)

Plan: [OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md). All
five cycles landed 2026-04-25; the architectural fix is functionally complete
(`OUTPUT_QUALITY_HANDOFF_PLAN.md:376` — "Phase 2 outcome — DONE 2026-04-25").

**What's left in Cycle 6** (per `OUTPUT_QUALITY_HANDOFF_PLAN.md:354-373`,
~1–2 hours total):
- `tools.py` orphan sweep — identify functions no longer called by any
  handler after Cycle 3+5; delete or mark for deferred removal.
- Per-module cache leak — `confidence`, `legal_confidence`, `risk_model`
  re-running fresh across turns (cross-references §4 Medium tactical entry
  "MODULE_CACHE_FIELDS leaky").
- `in_active_context` concurrency fix so `run_chat_tier_analysis` can
  default `parallel=True` (cross-references §4 Medium tactical entry
  "in_active_context not safe under concurrent thread-pool callers").

**Blocker:** None.

### Phase 3 — Presentation (`[size: ?]`)

Plan: [PRESENTATION_HANDOFF_PLAN.md](PRESENTATION_HANDOFF_PLAN.md). Cycles
A–D landed 2026-04-26.

**What's left:** Open Design Decision #7 (editor pass) tabled 2026-04-26.
Three options (per `PRESENTATION_HANDOFF_PLAN.md:254-266`):
- **(7a) No editor.** Ship Cycle D as one-shot synthesizer-with-newspaper-prompt.
- **(7b) Editor as Cycle D variant.** Synthesizer drafts grounded prose; editor
  LLM rewrites for voice + interleaves chart explanations. 2× LLM cost.
- **(7c) Deferred Cycle E.** Ship Cycle D one-shot; add editor as follow-on if
  browser smoke shows the response feels like "paragraph + 5 charts in a row."

Recommendation in source doc leans (7c) but decision belongs to the start of
Cycle D, not now.

**Blocker:** Awaiting Cycle D start signal.

### ✅ Phase 4a — CMA Quality (`[size: ?]`)

**Status:** RESOLVED 2026-04-28 — Cycle 6 closed. Phase 4a complete.

Plan: [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md). Cycles 1–5 landed 2026-04-26;
Cycle 6 landed 2026-04-28.

**Cycle 6 outcome** (closed 2026-04-28):
- Retired `claims/pipeline.py:62-114` graft to route through canonical
  `run_comparable_sales(context)` instead of direct `ComparableSalesModule()`
  instantiation. Closes §4 Low tactical entry "Retire ad-hoc
  ComparableSalesModule() graft" (preserved with ✅ marker below). The graft
  itself remains required for shape adaptation; full removal is queued under
  §4 High *Consolidate chat-tier execution*.
- Updated [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) and
  [`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) to reflect post-handoff topology
  (shared scoring pipeline, cross-town SOLD expansion, 4-chart BROWSE set,
  graft retirement). Cleared the lingering `base_comp_selector.py` / "15%
  sqft tolerance" drift in audit docs in the same pass — see §5 entry below
  marked ✅.
- Updated [`CMA_SURFACE_MAP.md`](CMA_SURFACE_MAP.md) for the same drift plus
  A5 graft-retirement status.
- Surface verification: all 14 CMA surfaces from the Cycle 1 audit (A1-A5
  Engine A, B1-B9 Engine B) confirmed routing through canonical engines.
- Smoke: code-level smoke via `build_claim_for_property` confirmed the
  migrated graft fires end-to-end and `comparable_sales` flows through
  `provenance.models_consulted`. Browser smoke deferred — Cycle 5 already
  exercised BROWSE/DECISION/EDGE and Cycle 6's change is internals-only.
- Tests: claims suite 82/82 green; full suite at expected 16-failure
  baseline (all pre-existing, verified by stash-and-rerun).

**Background.** Phase 4a addresses the original 2026-04-24 finding "Two comp
engines with divergent quality" (filed previously as a standalone tactical
entry, absorbed into this Closing Out section). Engine A and Engine B now
share one scoring pipeline (`briarwood/modules/comp_scoring.py`); Engine B
issues SOLD + ACTIVE SearchApi calls plus cross-town SOLD expansion when
same-town SOLD count is below `MIN_SOLD_COUNT`; saved comps demoted to
defensive fallback; outlier filter via tax-assessed-vs-price ratio; per-row
`listing_status` and `is_cross_town` provenance; `validate_cma_result`
invariant check. The BROWSE chart set now includes `cma_positioning` (4
charts), gated on the comp set being non-empty; chart markers distinguish
SOLD / ACTIVE / cross-town SOLD per row; the standalone `market_support_comps`
panel is suppressed on BROWSE because the chart subsumes it; `synthesize_with_llm`
accepts a `comp_roster` kwarg so prose cites specific comps with provenance
("sold for $X" / "currently asking $Y" / "in [neighbor town]") and the
verifier accepts comp ask prices as grounded values. Cycle 4.3 (renovation
premium pass-through) deferred to its own follow-up (§4 Medium).

**Blocker:** None — closed.

---

## §3. Strategic Initiatives

Multi-handoff umbrellas. Each subsection contains: framing paragraph,
stages with size estimates, dependencies, link to handoff plan or design
doc, and a list of tactical items absorbed into the umbrella by the
2026-04-27 reorg.

### §3.1 AI-Native Foundation umbrella (drafted 2026-04-27) `[size: XL]` `[impact: Data, Persistence & Feedback]`

**Severity:** Foundational — constrains every architectural decision going
forward. This umbrella is the canonical scope for the AI-Native Foundation
roadmap; it operationalizes the four AI-native principles named in
[`design_doc.md`](design_doc.md) § 3.4 (Contracts First, Queryable
Outputs, Every Action Is An Artifact, Closed Feedback Loops). Sequencing
recorded in [`DECISIONS.md`](DECISIONS.md) 2026-04-27 entry: Stages 1–3
precede Phase 4b (Scout); Stage 4 follows Scout.

**Read these first** before picking off any sub-handoff:
- [`design_doc.md`](design_doc.md) § 3.4 (the principles)
- [`design_doc.md`](design_doc.md) § 7 (the dual feedback loops; updated
  2026-04-27 to define what "closed" means operationally)
- [`DECISIONS.md`](DECISIONS.md) 2026-04-27 entry (the sequencing call)

#### Why this umbrella exists

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

#### ✅ Stage 1 — Persist Every Action `[size: M]`

**Status:** RESOLVED 2026-04-28 — landed via
[`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md) Cycles 1-4
on 2026-04-28. Three artifacts now persist by default: a `turn_traces`
table (one row per chat turn) and four metric columns on `messages`
both in [`data/web/conversations.db`](api/store.py), plus a
`data/llm_calls.jsonl` sink (one JSON line per LLM call). All three
write paths are exception-safe with `[turn_traces]` /
`[llm_calls.jsonl]` / `[messages.metrics]` prefix logs on failure —
observability never breaks a turn. The success-criteria query from
the plan (`SELECT answer_type, AVG(duration_ms_total) FROM turn_traces
GROUP BY 1`) returns real numbers. Test suite remains at the
pre-handoff baseline (16 pre-existing failures, none touched). See
[ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md) §"Persistence" for
the system-level shape and DECISIONS.md (this date) for the
design-decision history. Deferred follow-ons: JSONL
rotation/compaction policy and Stage 3 analytic-query sketches.

Source: "~1 handoff (one focused day of work)."

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

#### ✅ Stage 2 — Close The User-Feedback Loop `[size: M]` `[impact: Data, Persistence & Feedback]`

**Status:** RESOLVED 2026-04-28 — landed via
[`FEEDBACK_LOOP_HANDOFF_PLAN.md`](FEEDBACK_LOOP_HANDOFF_PLAN.md) Cycles
1-4 on 2026-04-28. Three artifacts now live by default: a `feedback`
table in [`data/web/conversations.db`](api/store.py) with PK on
`message_id` and FKs to `messages` (CASCADE) / `turn_traces` (SET
NULL); a `POST /api/feedback` endpoint with `Literal["up","down"]`
rating and an `up→yes`/`down→no` boundary translator that mirrors the
record into the analyzer's `intelligence_feedback.jsonl` hopper; a
thumbs-up/down `FeedbackBar` on every assistant message bubble in
[`web/src/components/chat/messages.tsx`](web/src/components/chat/messages.tsx)
with optimistic update, inline-error rollback, and rehydration via a
`feedback` LEFT JOIN in `get_conversation`. The closure gate (one
read-back consumer reacting to a rating) is satisfied by the in-flight
synthesis hint at
[`briarwood/synthesis/feedback_hint.py`](briarwood/synthesis/feedback_hint.py):
when the same conversation has a recent thumbs-down, the next turn's
synthesizer system prompt gains a "vary your framing" directive and
the manifest carries the `feedback:recent-thumbs-down-influenced-synthesis`
tag in `notes` for SQL audit. Test suite gained 24 new tests across
`tests/test_api_feedback.py` (16) and `tests/test_feedback_readback.py`
(7) plus the rehydration test (1); all green; baseline of 16
pre-existing failures unchanged. See
[`DECISIONS.md`](DECISIONS.md) 2026-04-28 entry "AI-Native Foundation
Stage 2 landed" for design deviations and Guardrail Review.

Source: "~1 handoff (likely two days; UI + endpoint + one real consumer)."

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

#### ✅ Stage 3 — Business-Facing Dashboard `[size: M-L]`

**Status:** RESOLVED 2026-04-28 — landed via
[`DASHBOARD_HANDOFF_PLAN.md`](DASHBOARD_HANDOFF_PLAN.md) Cycles 1-4 on
2026-04-28. The read-side admin surface is live: three FastAPI
endpoints under `/api/admin/*` gated behind
`BRIARWOOD_ADMIN_ENABLED=1`, fed by SQL aggregators on
[`api/store.py`](api/store.py) (`latency_durations_by_answer_type`,
`thumbs_ratio_since`, `top_slowest_turns`, `get_turn_trace`,
`feedback_for_turn`) and JSONL aggregators in the new
[`api/admin_metrics.py`](api/admin_metrics.py) module
(`cost_by_surface`, `top_costliest_turns`). Next server components at
`web/src/app/admin/page.tsx` (top-line metrics with HTML/CSS bars,
1d/7d/30d window switch) and
`web/src/app/admin/turn/[turn_id]/page.tsx` (full TurnManifest +
feedback rows + the `feedback:recent-thumbs-down-influenced-synthesis`
tag highlighted as the Stage 2 closure-loop audit affordance).
Plumbed `turn_id` into `data/llm_calls.jsonl` writes via
[`briarwood/agent/llm_observability.py`](briarwood/agent/llm_observability.py)
so per-turn cost aggregation works going forward (small Stage 1
follow-on; old JSONL records lack the field and are excluded from the
top-10 highest-cost view). Test suite gained 19 new tests in
`tests/test_api_admin.py`; all green; baseline of 16 pre-existing
failures unchanged. See [`DECISIONS.md`](DECISIONS.md) 2026-04-28
entry "AI-Native Foundation Stage 3 landed" for design deviations
and Guardrail Review.

 `[impact: Data, Persistence & Feedback]`

Source: "~1 handoff (likely two-three days; mostly Next.js + SQL)."

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

#### ✅ Stage 4 — Close The Model-Accuracy Loop `[size: M-L]` `[impact: Data, Persistence & Feedback]`

**Status:** RESOLVED 2026-04-28. Implementation substrate landed earlier
the same day via
[`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md) (outcome ingestion,
one-shot JSONL backfill, saved-property alignment backfill,
`model_alignment`, record-only module feedback hooks, analyzer
reporting). Loop 1 was then exercised end-to-end against an
owner-estimate outcome row at
`data/outcomes/property_outcomes.jsonl`
(`526-w-end-ave-avon-by-the-sea-nj`, expected close $1.385M).

The first run surfaced a real intake bug. The saved property's
`facts.town` field was `"Avon By The Sea Nj"` (state suffix glued onto
town string), so the town-keyed comp store lookup returned zero matches
and `comparable_sales` ran in `mode: fallback` with confidence 0;
`current_value` / `valuation` returned a heavily market-adjusted-down
$935K (APE 32.49%). The town string was corrected on this property
(`Avon By The Sea`) and the backfill re-run produced 3 honest alignment
rows:

- `current_value`: $1,311,200, APE 5.33%, confidence 0.51, alignment_score 0.73
- `valuation`:     $1,311,200, APE 5.33%, confidence 0.51, alignment_score 0.73
- `comparable_sales`: $1,484,741 from 5 same-town SFR comps + rental
  income, APE 7.20%, confidence 0.59, alignment_score 0.64

All confidences sit below the 0.75 high-confidence threshold, so the
analyzer surfaces no human-review tuning candidates. The pre- and
post-fix rows both persist (5 rows total) as an honest audit trail of
what the data corruption hid. Dedupe verified on re-run. The loop has
now closed against a real outcome AND surfaced its first defect — the
intake normalizer bug is filed in §4.

Real public-record sale ingestion still queued under §4
"Automate public-record outcome ingestion" — the proposed
`scripts/fetch_attom_outcomes.py` slice belongs there.

Source: "~1-2 handoffs."

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

**Plan refinement accepted 2026-04-28.**
- V1 outcome source should be manual CSV/JSONL under `data/outcomes/`;
  public-record automation is useful but lower priority and tracked
  separately in §4 Low.
- Start with actual sale-price outcomes and strict matching:
  `property_id` first, normalized address + town/state second, manual
  mapping for ambiguous historical rows. Uncertain matches are reported,
  not guessed.
- Persist per-module alignment in a new `model_alignment` table and score
  the highest-confidence valuation modules first: `current_value`,
  `valuation`, and `comparable_sales`.
- Analyzer output produces human-reviewed prompt/weight tuning candidates
  only. No auto-recalibration, prompt change, or threshold change belongs
  in Stage 4.
- `/admin` alignment visibility is optional and minimal; CLI/JSON analyzer
  output is enough to close Loop 1 if it reads the persisted alignment
  rows.

**Implementation landed 2026-04-28.**
- `briarwood/eval/outcomes.py` loads manual CSV/JSONL sale-price outcomes
  with row-level validation, duplicate-key reporting, strict
  property-id/address matching, and no public-record automation.
- `scripts/ingest_outcomes.py` validates outcome files as a dry-run CLI.
- `scripts/backfill_outcomes.py` attaches outcomes to
  `data/learning/intelligence_feedback.jsonl` rows when a strict match
  exists; it preserves a `.bak`, supports `--dry-run`, and refuses to
  overwrite non-null outcomes unless explicitly requested.
- `briarwood/eval/model_alignment_backfill.py` and
  `scripts/backfill_model_alignment.py` resolve outcome rows to saved
  properties, run `current_value`, `valuation`, and `comparable_sales`, and
  record `model_alignment` rows with `--dry-run` and duplicate protection.
- `api/store.py` now declares `model_alignment` plus insert/read helpers.
- `briarwood/eval/alignment.py` computes absolute error, absolute pct
  error, alignment score, high-confidence flag, and underperformance flag.
- `current_value`, `valuation`, and `comparable_sales` scoped modules now
  expose record-only `receive_feedback(session_id, signal)` hooks.
- `briarwood/feedback/model_alignment_analyzer.py` reads alignment rows and
  surfaces module summaries, top miss examples, and human-review tuning
  candidates. Optional `/admin` visibility was deferred.

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

**Resolution gate (closed 2026-04-28):** owner-supplied outcome file at
`data/outcomes/property_outcomes.jsonl` (one row, expected close on 526 W
End Ave) ran through `scripts/backfill_model_alignment.py`; 2
`model_alignment` rows persisted; analyzer report printed; dedupe verified
on re-run. No auto-recalibration ran. Public-record sale ingestion remains
a separate follow-up.

**Sequencing note:** Stage 4 can sensibly run *after* Phase 4b (Scout) —
Scout will benefit from Stages 1–3 but doesn't strictly need Loop 1
closed to ship. The current ordering puts Stage 4 last in the AI-native
sequence, not last in the overall project.

#### What this umbrella is not

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

**Dependencies:** Phase 4a Cycle 6 closed 2026-04-28 (§2) — Stage 1 is
unblocked. Stage 4 follows Phase 4b.

**Plan docs:**
- Stage 1 (Persist Every Action): [`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md) — drafted 2026-04-28, ready to start.
- Stages 2-4: not yet drafted; each will get its own plan when picked up.

**Absorbed from tactical:**
- 2026-04-24 — Add a shared LLM call ledger (folds into Stage 1's `LLMCallLedger`).

---

### ✅ §3.2 Phase 4b — Scout buildout `[size: XL]` `[impact: Scout]`

**Severity:** Apex differentiation — what separates Briarwood from
Zillow / Redfin / realtor.com. Owner direction 2026-04-26: *"Scout
needs to be the apex of the product. … Scout is going to be the thing
that answers the question that you don't know to ask."*
([SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) header).

**Status:** RESOLVED 2026-04-28 — Cycles 1-7 landed. Phase 4b Scout
buildout complete. Resequenced 2026-04-27 to follow AI-Native Foundation Stages
1–3 (per [DECISIONS.md](DECISIONS.md) 2026-04-27 entry). Substrate is
richer than the original 2026-04-26 framing contemplated:
`rent_zestimate` from CMA Cycle 3a is live, plus the full AI-Native
Foundation surface (`turn_traces`, `data/llm_calls.jsonl` with
`turn_id` linkage, `feedback` table, closed synthesis hint, `/admin`
evaluation surface). See [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
"State of the repo at handoff" → "AI-Native Foundation substrate
added 2026-04-28" for how this changes Scout's Cycles 6-7.

**Cycle 1 outcome (2026-04-28).** LLM scout module
(`briarwood/value_scout/llm_scout.py::scout_unified`) + 11 tests
landed isolated; no handler wiring yet. `SurfacedInsight` extended
with optional `confidence` (numeric `[0,1]`) + `category` (free-form
snake_case). One deviation: scout's terminal grounding rule is
stricter than the synthesizer's — empty contract on regen-without-
improvement instead of keeping ungrounded prose. See [DECISIONS.md](DECISIONS.md)
2026-04-28 entry "Phase 4b Scout Cycle 1 landed" + Guardrail Review.

**Cycle 2 outcome (2026-04-28).** `handle_browse` calls
`scout_unified` between the representation plan and the
synthesizer; insights cached on `session.last_scout_insights` (or
`None` when scout returns empty) and passed into
`synthesize_with_llm` via a new optional `scout_insights` kwarg.
Newspaper system prompt's `## What's Interesting` beat now carries
an explicit "weave the highest-confidence insight, paraphrase (do
NOT quote), name the supporting field, tease the drilldown"
directive. New `scout_insights` SSE event (Python +
`web/src/lib/chat/events.ts` mirror) carries the structured payload
to the React layer with `drilldown_target: null` (Cycle 3 fills the
mapping). `_MODULE_REGISTRY` updated so the modules-ran badge
credits "Value Scout". 8 new tests across synthesizer / dispatch /
pipeline-adapter; baseline holds at 16 fail / 1581 pass. Browser
smoke deferred to live UI session. See [DECISIONS.md](DECISIONS.md)
2026-04-28 entry "Phase 4b Scout Cycle 2 landed".

**Cycle 3 outcome (2026-04-28).** `web/src/components/chat/scout-finds.tsx`
+ `web/src/lib/chat/scout-routes.ts` ship the `ScoutFinds` drilldown
surface; rendered between `GroundedText` and `StrategyPathCard` per
OD #6. Open Design Decisions resolved: #4 existing module routes
only, #5 `ScoutFinds` placeholder name with "Scout Finds" /
"Angles you didn't ask about" UI copy (per `project_brand_evolution.md`),
#6 placement under prose. Verified via `tsc --noEmit` + ESLint +
`next build` + live browser smoke end-to-end render. React-render
unit tests deferred (no JS test framework in repo; meta-infra
decision). Two browser-smoke findings filed for Cycle 6:
(a) scout angles overlap the synthesizer's `## Why` beat instead of
surfacing genuinely non-obvious findings, (b) LLM invents categories
outside the canonical set — fallback works but UI badge reads odd.
See [DECISIONS.md](DECISIONS.md) 2026-04-28 entry "Phase 4b Scout
Cycle 3 landed".

**Cycle 4 outcome (2026-04-28).** `handle_decision` (wedge
fall-through Layer 3 synthesizer path) and `handle_edge` now run
`scout_unified` before `synthesize_with_llm` and pass insights via
the kwarg from Cycle 2. Section-followup composers
(`comp_set`, `entry_point`, `value_change`, etc.) are intentionally
untouched. Per-tier VOICE block added to
`briarwood/value_scout/llm_scout.py::_SYSTEM_PROMPT`:
`browse` = first-impression surfacer, `decision` = decision-pivot
surfacer, `edge` = skeptical surfacer (mirrors synthesizer Phase 3
Cycle D pattern). The SSE event + ScoutFinds React surface from
Cycles 2/3 light up automatically on DECISION/EDGE turns —
`session.last_scout_insights` is the single signal source for
`_browse_stream_impl` and DECISION/EDGE flow through the same
`dispatch_stream`. Browser smoke deferred to next live session.
See [DECISIONS.md](DECISIONS.md) 2026-04-28 entry "Phase 4b Scout
Cycle 4 landed".

**Cycle 5 outcome (2026-04-28).** `briarwood/value_scout/scout.py`
now exposes `scout(input_obj, *, llm=None, intent=None, max_insights=2)`
as the shared registry dispatcher. `_PATTERNS` is keyed by
`VerdictWithComparisonClaim` and `UnifiedIntelligenceOutput`; the existing
`uplift_dominance` detector stays under the claim key. `scout_claim`
is retained indefinitely as a back-compat wrapper around `scout(claim)`.
`SurfacedInsight.confidence` is now the universal Scout sort key:
LLM insights keep their self-rated score, while deterministic
`uplift_dominance` assigns `min(1.0, 0.5 + 0.1 * dominance_multiple)`.
BROWSE / DECISION / EDGE handlers call the dispatcher while preserving
per-tier `intent` voice. `briarwood/value_scout/README.md` was updated
inline for the contract change. Focused tests passed; full-suite baseline
remains off the documented handoff count (pre-Cycle-5 clean-tree run:
20 failures / 3 errors).

**Cycle 6 outcome (2026-04-28).** Deterministic chat-tier fallback rails
landed under `briarwood/value_scout/patterns/`: `rent_angle`,
`adu_signal`, and `town_trend_tailwind`. The shared dispatcher registers
them under `UnifiedIntelligenceOutput`, ranks them in the same confidence
channel as LLM insights, and records a per-turn manifest note with
`insights_generated`, `insights_surfaced`, and `top_confidence`. The LLM
scout prompt now explicitly avoids synthesizer-adjacent restatements and
prefers canonical categories while preserving room for evidence-specific
new labels. Focused tests passed.

**Cycle 7 outcome (2026-04-28).** Closeout docs reconciled. `GAP_ANALYSIS.md`
Layer 5 records Scout as chat-tier live and leaves only parallel firing
and user-type conditioning as target gaps. `TOOL_REGISTRY.md` includes
the `value_scout` entry and `value_scout.scan` LLM surface.
`ARCHITECTURE_CURRENT.md` records Scout in the LLM, orchestration, and
persistence surfaces. `CURRENT_STATE.md`, this roadmap, and
`SCOUT_HANDOFF_PLAN.md` now point the next sequence task to AI-Native
Foundation Stage 4.

**Framing.** Value Scout now has a shared dispatcher for claim-wedge and
chat-tier inputs, deterministic chat-tier fallback rails, and an LLM scout
surface for BROWSE / DECISION / EDGE. It is still sequential rather than
parallel with Layer 2. The target per
[`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md): an LLM-driven scout
that reads the full `UnifiedIntelligenceOutput` on every BROWSE/DECISION
turn, identifies 1–2 non-obvious angles the user would care about, and
surfaces them inline in synthesizer prose ("What's Interesting" beat)
plus as a dedicated drilldown surface in the rebuilt summary card.

**Dependencies:** ✅ AI-Native Foundation Stages 1–3 closed
2026-04-28. Scout inherits persisted artifacts to mine (Stage 1),
closed user feedback to learn from (Stage 2), and a dashboard
surface where its outputs can be measured (Stage 3). Sequence is
unblocked.

**Plan doc:** [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) (complete).

---

### §3.3 Semantic-model audit umbrella (2026-04-27, 11 items) `[size: L]` `[impact: LLM & Synthesis]`

**Severity:** Mixed — one Critical, three High, six Medium, two Low.
Surfaced 2026-04-27 by the Phase 1 read-only audit at
[SEMANTIC_AUDIT.md](SEMANTIC_AUDIT.md). The audit mapped every metric,
threshold, formula, prompt, and entity to its `file:line` and
cross-checked against four parallel extraction passes. No code changed
in Phase 1.

**Read this first before working any item below.** The individual
entries below are the actionable triage; the audit doc is the
source-of-truth for inputs/formulas/bands. Each filed item references
the audit's Drift section number (`§4.x`) so the full reasoning is one
click away.

**Cross-reference.** The audit's Step 8 recommends three extraction
modules that, taken together, would close most of the items below: (a)
`briarwood/decision_model/value_position.py` consolidating pricing-view
+ verdict thresholds + trust floors; (b)
`briarwood/decision_model/risk_thresholds.py` centralizing the
per-component penalties; (c) `briarwood/scoring_constants.py` for
comp-scoring + comp-confidence weights. Don't pick the items below off
in isolation when one of these extractions would solve several at once.

**Plan doc:** [SEMANTIC_AUDIT.md](SEMANTIC_AUDIT.md).

**Status snapshot as of 2026-04-28.** The semantic audit itself is
complete, and some semantic correctness work has already landed. The
§3.3.1 pricing-view/verdict threshold drift is implemented via the shared
`briarwood/decision_model/value_position.py` classifier and sweep tests.
The §3.3.9 confidence-carrier work is partially implemented:
`pricing_view_confidence` and `pricing_view_confidence_band` exist, but
dispatch/synthesis consumers still need to hedge low-confidence
`pricing_view` labels in prose. The rest of the umbrella remains open
unless its individual entry below says otherwise.

**Absorbed from tactical:**
- 2026-04-24 — Editor / synthesis threshold duplication has no mechanical guard
  (corroborated by §4.2; folds into the `value_position.py` extraction).

#### §3.3.1 CRITICAL: pricing-view bands disagree with verdict-label thresholds `[impact: Property Analysis]`

**Severity:** Critical — same property gets contradictory verdicts in
chat prose vs claim badge. Highest user-visible drift in the codebase.
Surfaced 2026-04-27 by [SEMANTIC_AUDIT.md §4.1](SEMANTIC_AUDIT.md).

**Files:**
- [briarwood/agents/current_value/agent.py:444-451](briarwood/agents/current_value/agent.py#L444-L451) — `_pricing_view(mispricing_pct)` returns "appears undervalued / fairly priced / fully valued / overpriced" using thresholds at +0.08, -0.03, -0.10.
- [briarwood/editor/checks.py:14-15](briarwood/editor/checks.py#L14-L15) — `VALUE_FIND_THRESHOLD_PCT=-5.0`, `OVERPRICED_THRESHOLD_PCT=5.0`.
- [briarwood/claims/synthesis/verdict_with_comparison.py:42-43](briarwood/claims/synthesis/verdict_with_comparison.py#L42-L43) — same thresholds, used to assign `verdict.label` in {value_find, fair, overpriced, insufficient_data}.

**Issue:** Two code paths classify the same human concept ("is this
property under-, fair-, or over-priced?") with different thresholds and
opposite sign conventions. Worked example: at BCV $1.06M / ask $1.0M
the synthesizer prose says *"appears fairly priced"* and the claim
verdict says *"value_find"* — same property, two verdicts. At BCV
$0.95M / ask $1.0M the prose says *"appears fully valued"* and the
verdict says *"overpriced"*. Full ratio table in
[SEMANTIC_AUDIT.md §4.1](SEMANTIC_AUDIT.md).

**Suggested fix:** Centralize at a single site. Create
`briarwood/decision_model/value_position.py` exporting both the band
constants and a single `pricing_view(bcv, ask) -> Label` function. Have
`_pricing_view` in `current_value/agent.py` call it; have the editor
and `verdict_with_comparison.py` thresholds import the same constants.
Add a sweep test that walks BCV/ask ratios from 0.80 to 1.20 in 1%
steps and asserts both paths return the same logical band. This single
extraction also closes the absorbed "editor / synthesis threshold
duplication" tactical item.

**2026-04-28 status:** Implemented the shared classifier in
`briarwood/decision_model/value_position.py`, wired current-value,
editor, and claim-verdict paths to it, and added a 0.80–1.20 BCV/ask
ratio sweep test covering all three paths. The small-sample caveat
threshold remains separate and is tracked under the editor/claims
README rough edge rather than this price-label item.

**Original scope note:** This was the headline finding from the
2026-04-27 audit and was queued ahead of the next semantic-layer
refactor. The shared classifier implementation landed on 2026-04-28;
keep this entry for audit traceability and remaining review.

#### §3.3.2 HIGH: synthesis confidence floors are invisible to the LLM prompts `[impact: LLM & Synthesis]`

**Severity:** High — the LLM can produce a stance the code will silently
downgrade, and the user sees the downgraded stance with the LLM's
original justification prose attached.

**Files:**
- [briarwood/synthesis/structured.py:27-28](briarwood/synthesis/structured.py#L27-L28) — `TRUST_FLOOR_STRONG = 0.70`, `TRUST_FLOOR_ANY = 0.40`. Hard gates: ≥0.70 unlocks "strong_buy"; <0.40 collapses stance to CONDITIONAL.
- [briarwood/llm_prompts.py:107-110](briarwood/llm_prompts.py#L107-L110) — `build_synthesis_prompt()` describes trust calibration qualitatively ("lower confidence when modules conflict, when key inputs are missing…") with no numeric anchors.
- [api/prompts/decision_summary.md](api/prompts/decision_summary.md) and the other tier prompts — same qualitative framing.

**Issue:** The code enforces hard numeric gates on stance. The LLM is
asked to choose stance + confidence with no knowledge of where the
gates sit. A model that emits stance="strong_buy" at confidence 0.55
will have its stance silently rewritten by `structured.py`; the prose
justification in the response will still read like a strong-buy
rationale, attached to a now-CONDITIONAL stance. The user sees the
seam.

**Suggested fix:** Two options, pick one.
1. **Expose the constants in the prompt.** Add a literal sentence
   ("strong_buy unlocks at confidence ≥ 0.70; below 0.40 the stance
   must be conditional") and have `build_synthesis_prompt` interpolate
   the actual values from a single source of truth.
2. **Compute the stance deterministically before composition.** Have
   `structured.py` decide stance, pass the stance into the prompt as a
   fixed input, and ask the LLM to write the prose for the given
   stance rather than choose one.

Option 2 is the more invasive but more robust path. Either way, the
floors should also live in the same
`briarwood/decision_model/value_position.py` proposed in the
pricing-view fix above.

**Out of scope** for any active handoff. Pre-condition for any work
that touches the synthesizer prompt.

#### §3.3.3 HIGH: orphan signature metrics — Forward Value Gap & Optionality Score `[impact: Property Analysis]`

**Severity:** High — both names appear in product vocabulary and may
appear in older internal docs / older external prompts. No code computes
either as a scalar. Hallucination risk if any prompt ever names them.

**Files:**
- [briarwood/modules/risk_model.py:109-146](briarwood/modules/risk_model.py#L109-L146) — `premium_pct` is the closest implementation of "Forward Value Gap": a binary flag at ±10/+15, not a continuous gap.
- [briarwood/routing_schema.py:356](briarwood/routing_schema.py#L356) — `OptionalitySignal` Pydantic carrier (carrier, not score).
- [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) — produces qualitative `HiddenUpsideItem` records (label / magnitude / rationale).
- [briarwood/modules/bull_base_bear.py](briarwood/modules/bull_base_bear.py) — `bull_optionality = scarcity_score / 100 × 0.08` is a dollar-impact factor in bull case, not a user-facing score.

**Issue:** The audit prompt (and the "signature metrics" framing in
product vocabulary) names both Forward Value Gap and Optionality Score
as if they were computed scalars with bands. They aren't. Any prompt or
doc that references "Forward Value Gap: 12%" or "Optionality Score:
72" is inventing the number. Today no in-repo prompt names them by
that exact phrasing — but the risk is real for older internal materials
and for any new prompt that reaches for the vocabulary.

**Suggested fix:** Per-metric decision needed.
- **Forward Value Gap**: either (a) define it formally —
  `forward_value_gap = (base_case_value − BCV) / BCV` with calibrated
  bands, surfaced as a first-class metric on the synthesis output — or
  (b) retire the phrase from product vocabulary and lean on the
  existing `premium_pct` flag.
- **Optionality Score**: either (a) define a scalar aggregator over
  `HiddenUpsideItem.magnitude` (with bands), or (b) retire the phrase
  and lean on the qualitative list as the user surface.

As part of this, grep all prompts and external docs for
`"forward value gap"`, `"FVG"`, `"optionality score"`. If any hits
exist, fix them in the same pass.

**Out of scope** for active handoffs. Worth a 30-minute owner decision
before either Phase 4b (Scout) or any semantic-layer refactor — the
answer affects both.

#### §3.3.4 MEDIUM: BCV component-count drift in prompts and prior docs `[impact: Property Analysis]`

**Severity:** Medium — wrong-number-of-things in prose; if any prompt
still says "the four anchors of BCV," it is incorrect.

**Files:**
- [briarwood/agents/current_value/agent.py:18-24](briarwood/agents/current_value/agent.py#L18-L24) — `_COMPONENT_BASE_WEIGHTS` defines five components: `comparable_sales 0.40`, `market_adjusted 0.24`, `town_prior 0.16`, `backdated_listing 0.12`, `income 0.08` (sums to 1.00).

**Issue:** The recent audit prompt and likely some older internal docs /
READMEs reference "BCV's 4 components." Code blends 5. Any downstream
prose that names the four anchors is wrong.

**Suggested fix:** One-line grep sweep for `"four anchor"`, `"4 anchor"`,
`"four component"`, `"4 component"` across `briarwood/`,
`api/prompts/`, all `*.md` at repo root. Fix any hits to reflect five
components by name and weight. Cheap; can ride along any future
synthesis-prompt or current-value README touch.

**Out of scope** for any current handoff. Drive-by fix during a
documentation pass.

#### §3.3.5 MEDIUM: rent has three sources with no reconciliation carrier `[impact: Property Analysis]`

**Severity:** Medium — a verdict that says "rent supports this deal"
can't tell the user *which rent* it used, and divergence across sources
is invisible.

**Files:**
- [briarwood/agents/income/schemas.py:35](briarwood/agents/income/schemas.py#L35) — `IncomeAgentOutput.monthly_rent_estimate` (best-estimate model output).
- [briarwood/agents/rent_context/schemas.py:19](briarwood/agents/rent_context/schemas.py#L19) — `RentContextOutput.market_rent_estimate` (market benchmark).
- [briarwood/schemas.py:462](briarwood/schemas.py#L462) — `ValuationOutput.effective_monthly_rent` (the value actually selected for cash-flow; may be user override, model estimate, or listing-parsed).

**Issue:** Three rent values can disagree silently. The selection logic
is implicit in valuation. No structured carrier surfaces "these three
estimates disagree by X%" so no prompt can call attention to the
divergence. First time a user asks "which rent are you using?" the
answer requires reading code.

**Suggested fix:** Add a small `RentReconciliation` dataclass in
`briarwood/schemas.py` carrying `model_estimate`, `market_estimate`,
`user_override`, `selected_value`, `selection_reason`, and a computed
`divergence_pct`. Populate in valuation; surface in the synthesizer
prompt as `rent_reconciliation` so prose can name the source. Two-day
item.

**Out of scope** for active handoffs. Folds naturally into Phase 4b
(Scout) since Scout is about surfacing non-obvious reads, and
rent-source divergence is exactly the kind of thing Scout could
highlight.

#### §3.3.6 MEDIUM: numeric-grounding rule in synthesizer is informal — rounding drift accepted `[impact: LLM & Synthesis]`

**Severity:** Medium — the verifier catches *completely* ungrounded
numbers but not "$820k" rendered as "$800k". Rounding drift toward
psychologically friendly numbers passes silently.

**Files:**
- [briarwood/synthesis/llm_synthesizer.py:64-165](briarwood/synthesis/llm_synthesizer.py#L64-L165) — `_SYSTEM_PROMPT_NEWSPAPER` says "every dollar amount, percentage, multiplier, year, or count you cite must round to a value present in the `unified` JSON." No precision constant defined; rounded forms like `$820k` are explicitly allowed.
- [briarwood/synthesis/llm_synthesizer.py:335-401](briarwood/synthesis/llm_synthesizer.py#L335-L401) — regen path on verifier failure has the same vagueness.
- [api/guardrails.py](api/guardrails.py) — `Verifier` flags ungrounded numbers/entities; does not detect off-by-rounding.

**Issue:** "Rounds to a value present" has no precision rule.
`$820,000` rendered as `$800k` is a 2.4% delta the verifier won't flag
(it sees both `$820k` and `$800k` as plausibly rounded forms, only
catching values like `$750k` that aren't near any present value). On a
$1M property a 2% drift moves the user's reaction noticeably.

**Suggested fix:** Define a rounding precision constant (e.g.,
`MAX_ROUNDING_DELTA_PCT = 1.0`) in the verifier and enforce: every
numeric token in the prose must be within ±X% of a value in `unified`.
Reject regen drafts that introduce *new* numbers not in the original
draft (current regen prompt allows arbitrary reframing). Test by
feeding the verifier a draft with `$800k` when the truth is `$820k` and
asserting it flags.

**Out of scope** for active handoffs. Pick up alongside any future
synthesizer prompt work.

#### §3.3.7 MEDIUM: `scarcity_score` naming collision across two modules `[impact: Property Analysis]`

**Severity:** Medium — two metrics with the same name, different
formulas, different inputs. Search-and-replace is treacherous; readers
will conflate.

**Files:**
- [briarwood/agents/scarcity/scarcity_support.py:36-82](briarwood/agents/scarcity/scarcity_support.py#L36-L82) — `scarcity_score = 0.55 × location_scarcity + 0.45 × land_scarcity` (then composed into `scarcity_support_score`).
- [briarwood/modules/location_intelligence.py:62-240](briarwood/modules/location_intelligence.py#L62-L240) — `scarcity_score = weighted([(proximity, 0.40), (supply, 0.35), (rarity, 0.25)])`.

**Issue:** Both modules export a field called `scarcity_score`, computed
differently from different inputs, with different units (one is 0-100,
one is 0-1 scaled). Downstream code that reads "the scarcity score"
gets one or the other depending on which module's payload it touched.

**Suggested fix:** Rename one. Two reasonable conventions: (a) prefix
by source — `location_scarcity_score` for the location-intelligence
one, `support_scarcity_score` for the scarcity-support one; (b) keep
`scarcity_score` for the user-facing one (the support module's, which
is the one the synthesizer cites) and rename the location-intelligence
internal to `location_scarcity_subscore`. Add a one-line comment at
each cite explaining the lineage.

**Out of scope** for active handoffs. Half-day rename + grep sweep.

#### §3.3.8 MEDIUM: comp-scoring weights duplicated across two layers `[impact: Property Analysis]`

**Severity:** Medium — the two weight sets serve different conceptual
layers (single-comp scoring vs comp-stack base-shell layer) but have no
comment tying each to its purpose. A future refactor could conflate
them.

**Files:**
- [briarwood/modules/comp_scoring.py:221-271](briarwood/modules/comp_scoring.py#L221-L271) — single-comp weighted score: `proximity 0.30 + recency 0.25 + similarity 0.30 + data_quality 0.15`.
- [briarwood/comp_confidence_engine.py:202-273](briarwood/comp_confidence_engine.py#L202-L273) — Layer-1 base-shell confidence: `comp_count 0.25 + support_quality 0.25 + tier_distribution 0.20 + median_similarity 0.15 + price_agreement 0.15`.

**Issue:** Two weight sets in adjacent files. Currently scoring
different things; the risk is a future "let's centralize the comp
weights" sweep that picks the wrong source-of-truth.

**Suggested fix:** Two paths, pick one.
1. **Inline comments at both sites** spelling out what each weight set
   scores ("single-comp similarity" vs "comp-stack base-shell layer")
   and a sentence at top of each file.
2. **Centralize in `briarwood/scoring_constants.py`** with two named
   tuples — `SINGLE_COMP_WEIGHTS` and `COMP_STACK_BASE_SHELL_WEIGHTS` —
   and import from both sites.

Option 2 is cleaner and supports the broader extraction recommendation
in [SEMANTIC_AUDIT.md §8](SEMANTIC_AUDIT.md).

**Out of scope** for active handoffs.

#### §3.3.9 MEDIUM: `pricing_view` is a user-facing categorical output with no confidence `[impact: Property Analysis]`

**Severity:** Medium — user reads "appears overpriced" with no signal
of how sure the engine is. Combined with §4.1's drift, the user can
also get a label that disagrees with the verdict claim.

**Files:**
- [briarwood/agents/current_value/agent.py:444-451](briarwood/agents/current_value/agent.py#L444-L451) — `_pricing_view` returns a string with no associated confidence.
- [briarwood/agents/current_value/schemas.py:93](briarwood/agents/current_value/schemas.py#L93) — `pricing_view: str` field on `CurrentValueOutput`.
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — many sites consume `pricing_view` and surface it directly to prose without confidence framing (e.g. lines 1017, 1091, 1797, 4072).

**Issue:** Every other major synthesizer field has a confidence band.
`pricing_view` is one of the most user-impactful labels and has none. A
"appears overpriced" emitted from a low-BCV-confidence run looks
identical to one from a high-confidence run.

**Suggested fix:** When the pricing-view fix in §3.3.1 lands
(centralized `value_position.py` module), have it return
`(label, confidence)` rather than just `label`. Compute confidence as
`min(bcv_confidence, comp_confidence)` or similar; expose to the
synthesizer so prose can hedge ("appears overpriced, though comp
coverage is thin").

**2026-04-28 status:** Added `pricing_view_confidence` and
`pricing_view_confidence_band` to current-value/valuation outputs via
the shared value-position classifier. Remaining work: update
`briarwood/agent/dispatch.py` consumers that surface `pricing_view`
directly so they can use the confidence field to hedge low-confidence
labels in prose.

**Original scope note:** This was out of scope until the §3.3.1
centralization landed. As of 2026-04-28, central confidence fields are
in place; consumer prose hedging remains tracked above.

#### §3.3.10 LOW: `valuation` vs `current_value` module naming collision `[impact: Property Analysis]`

**Severity:** Low — naming hazard only; no functional impact.

**Files:**
- [briarwood/modules/valuation.py:15-57](briarwood/modules/valuation.py#L15-L57) — thin wrapper around `current_value` that adds an HPI macro nudge.
- [briarwood/agents/current_value/agent.py](briarwood/agents/current_value/agent.py) — the actual BCV blender.
- [briarwood/modules/current_value.py](briarwood/modules/current_value.py) — scoped wrapper applying input-quality confidence caps.

**Issue:** Three modules in the call chain produce the same primary
field (`briarwood_current_value`). Search for "where is BCV computed"
lands in any of them. Future refactors that grep for "valuation" will
miss the BCV agent and vice versa.

**Suggested fix:** Either (a) rename `briarwood/modules/valuation.py` →
`briarwood/modules/valuation_with_macro_nudge.py` and add a header
comment naming it as the macro-nudge wrapper; or (b) consolidate the
macro nudge into `current_value` and delete `modules/valuation.py`.
Path (b) is cleaner if the nudge isn't used independently.

**Out of scope** for active handoffs. Drive-by fix.

#### §3.3.11 LOW: `decision_model/scoring.py` looks legacy — verify before delete `[impact: Property Analysis]`

**Severity:** Low — dead-code candidate; needs verification.

**Files:**
- [briarwood/decision_model/scoring.py](briarwood/decision_model/scoring.py) — file header comment marks it as "largely deprecated."
- [briarwood/decision_model/scoring.py:51](briarwood/decision_model/scoring.py#L51) — `estimate_comp_renovation_premium()` is still consumed by `briarwood/modules/renovation_impact.py` (per audit cross-reference).

**Issue:** The file's own header says "largely deprecated" but at least
one function is still in service. Either the comment is stale, or the
renovation_impact dependency is itself stale and should be migrated.

**Suggested fix:** Grep for every import of
`briarwood.decision_model.scoring`. For each consumer, decide: keep the
function (rewrite header comment), or migrate the consumer to a
non-deprecated source. If only `renovation_impact` consumes one
function, move that function into `renovation_impact.py` and delete the
rest of `decision_model/scoring.py`.

**Out of scope** for active handoffs. 1-hour cleanup.

---

### §3.4 Chart visual quality push (HIGH, 2026-04-26) `[size: L]` `[impact: UI & Charts]`

**Severity:** High — charts are the user-visible surface where Briarwood
looks least like a designed product. Owner feedback 2026-04-25 ("look
like something that isn't being designed by a user rather than by an
LLM") and 2026-04-26 ("I don't think the charts are great but we can
table that") together describe a real quality gap that Phase 3 polish
only partially closed.

**Files (the most-touched surfaces):**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) — every chart sub-component (`MarketTrendChart`, `CmaPositioningChart`, `ValueOpportunityChart`, `ScenarioFanChart`, `RentBurnChart`, `RentRampChart`, `RiskBarChart`, `HorizontalBarWithRangesChart`).
- [api/pipeline_adapter.py](api/pipeline_adapter.py) — the `_native_*_chart` event builders (legend / axis-label / value-format payload).
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — the SSE chart-spec types.

**Issue:** The chart layer has accumulated a list of small bugs and
stale primitives that, taken together, undermine the impression of a
designed product. Sub-items below.

**Suggested approach:** A dedicated chart-quality cycle (or sub-cycle of
Phase 4c BROWSE rebuild) with three sub-pieces — (a) close the bugs
below as a single sweep, (b) revisit chart styling primitives (markers,
axes, captions, legend) for premium feel, (c) audit live SSE rendering
for robustness. Estimated 1-2 days; produces the most user-visible
quality gain available in the project today.

**Plan doc:** None — tracked in this section only.

**Absorbed from tactical:**
- 2026-04-26 — Live SSE rendering requires page reload (formerly Medium tactical).
- 2026-04-26 — `cma_positioning` chart-prose alignment (formerly Low tactical).
- 2026-04-26 — `cma_positioning` "CHOSEN COMPS: Context only" chip + `feeds_fair_value` dead architecture (formerly Low tactical).
- 2026-04-26 — `value_opportunity` y-axis "Comp" vertical character stack (formerly Low tactical).
- 2026-04-26 — `cma_positioning` source-view drift in non-BROWSE handlers (formerly Medium tactical, partial-resolved 2026-04-26).

#### §3.4.1 `cma_positioning` "CHOSEN COMPS: Context only" chip + `feeds_fair_value` dead architecture `[impact: UI & Charts]`

**Severity:** Low — cosmetic / misleading copy + dead architectural
baggage. Surfaced during CMA Phase 4a Cycle 5 browser smoke.

**Files (chip):**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) `CmaPositioningChart` — the metric-chip strip below the chart computes `explicitChosen = spec.comps.filter((comp) => comp.feeds_fair_value != null)` and renders `"Context only"` when `explicitChosen.length === 0`.
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) `_comp_row_from_cma` — does not populate `feeds_fair_value` on Engine-B comp rows.

**Files (broader `feeds_fair_value` retirement):**
- [api/pipeline_adapter.py::_native_cma_chart](api/pipeline_adapter.py) — passes `feeds_fair_value` per comp into the chart spec.
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — `CmaPositioningChartSpec.comps[]` declares `feeds_fair_value?: boolean | null`.
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) — the marker-tone fallback when `listing_status` is null still keys on `feeds_fair_value` to pick `CHART.bull` vs `CHART.neutral`.
- Several test fixtures across `tests/test_pipeline_adapter_contracts.py` and `tests/agent/test_dispatch.py` reference the flag.

**Issue:** The `feeds_fair_value` flag dates from the pre-Cycle-3 era
when Engine A (saved comps, fair-value math) and Engine B (live Zillow,
user-facing CMA) had different scoring pipelines. After Cycle 3
unified them onto the same scoring pipeline
(`briarwood/modules/comp_scoring.py`), every comp in the BROWSE /
DECISION CMA set is load-bearing — there is no "context only" tier any
more. But `_comp_row_from_cma` doesn't set the flag, so the chart frame
permanently renders "CHOSEN COMPS: Context only," which is wrong and
visible to the user on every BROWSE turn. Beyond the chip itself, the
flag persists across the SSE spec, the React component, and several
test fixtures — dead architecture that's ripe for a single sweep.

**Suggested fix:** Two-step.

1. **Replace the chip.** Turn the `Chosen comps` chip into a `Comp set`
   chip that uses the new provenance — e.g. `"5 SOLD + 3 ACTIVE"` (or
   `"5 SOLD (2 cross-town) + 3 ACTIVE"`). Source the counts from
   `spec.comps` after the Cycle 5 marker scheme: count
   `listing_status === "sold"` and `listing_status === "active"` (with
   the cross-town subset broken out from the SOLD count).
2. **Retire `feeds_fair_value` entirely.** Remove from
   `_comp_row_from_cma`, `_native_cma_chart`'s spec.comps payload, the
   `CmaPositioningChartSpec.comps[]` type, the React component's
   marker-tone fallback (legacy/null `listing_status` rows render with
   the new `comp_set` provenance instead), and update the test
   fixtures.

Recommend doing both as a single sweep — they share the same files.
Cleanup, ~1 hour.

**Out of scope** for any specific cycle today; pick up in this umbrella
or as a drive-by fix during Phase 4c BROWSE rebuild.

#### §3.4.2 `value_opportunity` chart y-axis label "Comp" renders as a vertical character stack `[impact: UI & Charts]`

**Severity:** Low — cosmetic. Surfaced during CMA Phase 4a Cycle 5
browser smoke.

**Files:**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) `ValueOpportunityChart` — uses the shared `AxisLabels` component to render the y-axis label.
- The `_native_value_chart` payload in [api/pipeline_adapter.py](api/pipeline_adapter.py) sets `y_axis_label="Comp"`.

**Issue:** When the y-axis label is a single short word (e.g.
`"Comp"`), the SVG text path falls through to per-character placement
and the user sees `C / o / m / p` stacked vertically — one character
per visual line — rather than the word rendered horizontally with a
`transform="rotate(-90)"`. Reproduced on the second turn of the
2026-04-26 Cycle 5 smoke ("What rent would make this deal work?" —
value_opportunity chart).

**Suggested fix:** Audit `AxisLabels` (likely defined in the same file)
and confirm the y-axis branch uses a transform-rotated `<text>` element
with proper `text-anchor` rather than per-character `<text>` placement.
The fix is a few lines in the SVG rendering helper.

#### §3.4.3 `cma_positioning` chart-prose alignment `[impact: UI & Charts]`

**Severity:** Low — cosmetic / coherence. Surfaced during CMA Phase 4a
Cycle 5 browser smoke (1008 14th Ave, Belmar — Turn 2 prose cited "103
2nd Avenue, currently asking $749,000" but the chart's top-8 rows did
not include that comp).

**Files:**
- [api/pipeline_adapter.py::_native_cma_chart](api/pipeline_adapter.py) — caps the chart's comp rows at `priced_rows[:8]`.
- [briarwood/agent/dispatch.py::handle_browse](briarwood/agent/dispatch.py) — passes the full `session.last_market_support_view["comps"]` (up to 10 rows per Cycle 3c's top-N cap on `get_cma`) to `synthesize_with_llm` as `comp_roster`.

**Issue:** `get_cma` returns up to 10 comps. The `cma_positioning`
chart's `_native_cma_chart` further trims to the top 8 for visual
compactness. The Cycle 5 synthesizer wiring passes the full roster to
`synthesize_with_llm` — so the LLM can (and on 2026-04-26 did) cite
comps that exist in the roster but didn't make the chart's slice.

**Suggested fix:** One-line — clamp the `comp_roster` list `handle_browse`
passes to `synthesize_with_llm` to the same top-N the chart renders
(8). Mirror the slice exactly, ideally via a shared helper. Alternative:
bump the chart's row cap from 8 to 10.

#### §3.4.4 Live SSE rendering requires a page reload to display correctly `[impact: UI & Charts]`

**Severity:** Medium — visible to every user, every BROWSE turn.
Surfaced in user-memory note `project_ui_enhancements.md`.

**Files:**
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) — chart-rendering SSE-event consumers.
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — SSE event types.
- [api/pipeline_adapter.py](api/pipeline_adapter.py) — chart-event emission ordering.

**Issue:** Owner reports that the chat surface sometimes needs a page
reload before charts and structured cards render correctly. Symptoms
include partially-loaded card layouts, mid-stream layout reflows when
chart events arrive late, and generally a sense that the live-streaming
response shape is fragile. The CMA Phase 4a Cycle 5 BROWSE-only
`market_support_comps` panel suppression was a microcosm of this —
duplicate comp surfaces caused a "glitch and reload" effect that we
resolved by dropping one surface, but the broader rendering still has
rough edges.

**Suggested fix:** Audit the SSE event order + the React reducer state
machine that consumes them. Specifically check: (a) does the chart-card
component re-mount when the chart-event arrives mid-stream (vs
progressively rendering), (b) is the SSE consumer queueing events
properly so partial state doesn't render, (c) are there any race
conditions between the prose stream, the structured-card events, and
the chart events that cause the layout to flicker?

#### §3.4.5 `cma_positioning` source-view drift in non-BROWSE handlers `[impact: UI & Charts]`

**Severity:** Medium — surfaces as broken chart anchors (`ASK: —`,
`FAIR VALUE: —`) on whichever handler triggers the bug.

**Files:**
- [briarwood/representation/agent.py::render_events](briarwood/representation/agent.py) — chart-id → source-view dispatch
- [api/pipeline_adapter.py::_native_cma_chart](api/pipeline_adapter.py) — renderer that reads ask/fair_value/value_band from a single view dict

**Issue.** The Representation Agent's `RepresentationSelection` carries
one `source_view` per chart, but `cma_positioning` fundamentally needs
two views: `last_value_thesis_view` for ask / fair_value / value_band
anchors, plus `last_market_support_view` for the comp rows. When the
agent picks `last_market_support_view` as the single source (because
it has the comps the LLM cited), the renderer's anchor lookups silently
return None and the chart paints with `—` placeholders.

**Resolved 2026-04-26 (partial — defensive fix only).**
`agent.render_events` now overrides the primary view to
`last_value_thesis_view` whenever the chart kind is `cma_positioning`,
with `market_view` already injecting the market-support comps. This
prevents the broken-anchor render on any handler that goes through the
agent for chart selection.

**Suggested follow-on.** Restructure `RepresentationSelection` to carry
an optional `secondary_source_view` (or a typed
`source_views: dict[role, view_key]` mapping) so multi-view charts are
first-class instead of patched per-chart.

#### §3.4.6 Other items in the umbrella `[impact: UI & Charts]`

These items are listed in the umbrella body but do not yet have detailed
filings:

- **`cma_positioning` marker diversity in real comp sets** — owner
  browser smoke 2026-04-26 confirmed all comps render as filled circles
  because Belmar's top-8 by weighted_score is all SOLD same-town
  (Cycle 5 marker scheme works but never triggers ACTIVE / cross-town
  glyphs in this market — comp set scoring needs to surface diversity,
  or the chart should sample for it).
- **Chart styling is utilitarian** — markers are circles + triangles;
  legend is a flat row; no animation, no hover affordances, no
  progressive disclosure. The decision-tier surface needs to feel
  premium because the user is making a six-figure call.

#### §3.4.7 Evaluate React-native charting library to replace Plotly-iframe `[impact: UI & Charts]`

**Severity:** Medium — visual quality is the user's #2 UI complaint per
user-memory `project_ui_enhancements.md`; current architecture caps how
much polish is achievable without leaving the Plotly-iframe paradigm.
Filed 2026-04-28 during Stage 2 (feedback loop) plan-mode pass after
the owner asked whether a React-native charting library belonged in
Stage 2 — it does not, but the work is real.

**Files (current architecture — what would change):**
- [api/pipeline_adapter.py](api/pipeline_adapter.py) — handlers
  (`_native_cma_chart`, `_native_value_chart`, etc.) compose Plotly
  HTML and write artifact files under `data/agent_artifacts/{session_id}/`.
- [api/main.py:62-64](api/main.py#L62-L64) — `_ARTIFACTS_DIR` mount at
  `/artifacts` serves those HTML files to the browser.
- [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) —
  wraps each chart in an `<iframe>` pointing at the artifact URL plus
  a thin React shell for chips, axis labels, and provenance markers.
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — `chart` SSE
  event payload carries a URL today, not structured data.

**Issue:** The iframe-Plotly architecture has two ceilings:

1. **Visual polish ceiling.** Per §3.4.6, markers are utilitarian, no
   animation, no hover affordances, no progressive disclosure. Each fix
   under §3.4.1–§3.4.5 has lived inside the iframe boundary and stayed
   correspondingly thin.
2. **Interaction ceiling.** A chart inside an iframe cannot easily
   participate in the surrounding React state — e.g., feedback bar
   tied to a chart, hover-sync between map and chart, chart drilldown
   into a detail panel. Stage 2's feedback affordances (§3.1) and
   Phase 4c's BROWSE summary card (§3.5) both want chart interactions
   that the current architecture makes hard.

Candidate libraries (no recommendation yet — the eval is the work):

| Library | Notes |
|---|---|
| Recharts | Most popular React-native; declarative; D3-based; large community. Default starting point. |
| Apache ECharts via `echarts-for-react` | More chart types and animation polish than Recharts; heavier bundle. |
| Nivo | Strong default aesthetic; opinionated; good for fast polish, less so for custom interactions. |
| `react-google-charts` | Wrapper over Google Charts. Familiar visual language; less idiomatic React. |
| Visx (Airbnb) | Lower-level D3 primitives in React; maximum flexibility, more code per chart. |

**Suggested fix:** Three phases.

1. **Eval (S, ~30–60 min LLM time).** Build one of the highest-stakes
   charts — `cma_positioning` is the right candidate because it
   carries the most provenance complexity — in two or three of the
   candidate libraries against the same dataset. Compare on: visual
   quality, code volume, hover/animation affordances, and whether the
   chart can co-render with surrounding React state (e.g., the new
   `FeedbackBar`).
2. **Architecture change (M).** Redesign the `chart` SSE event to
   carry structured chart data (the spec the producer already builds
   internally), not an HTML artifact URL. Retire the `_ARTIFACTS_DIR`
   mount path for chart use cases (keep it for any non-chart
   artifacts). Update producers to emit data; update `chart-frame.tsx`
   to render via the chosen library.
3. **Roll forward (M).** Migrate the chart catalog one chart at a time
   under flag, validating against the §3.4.1–§3.4.5 fixes still hold
   (no regression in the comp-set chip, no regression on y-axis label
   rendering, etc.).

**Size:** L total. Phase 1 alone is S and is the natural first move —
it answers "is this even worth doing?" before committing to the
architecture change.

**Dependencies:**
- AI-Native Foundation Stage 2 (§3.1) closes first — feedback affordances
  on charts depend on the chart layer being React-native. ✅ closed
  2026-04-28.
- Phase 4a Cycle 5 chart fixes (§3.4.1–§3.4.5) should be settled before
  the migration to avoid carrying unfixed cosmetic bugs forward.
- Phase 4c BROWSE summary card rebuild (§3.5) is downstream — the
  rebuild benefits from React-native charts but does not strictly
  require them.

**Sequencing call (2026-04-28).** Owner-confirmed during Stage 3
plan-mode pass: the chart-library evaluation belongs **with the UI
reconstruction work** (Phase 4c §3.5), not as a separate handoff
ahead of it. The visual-quality complaint and the BROWSE summary-card
rebuild are the same problem viewed from two angles; doing the
chart-lib eval inside the rebuild handoff means the eval is grounded
in the real layout the rebuilt cards demand. Until then, any new
chart surface (e.g. Stage 3 dashboard) ships with plain HTML/CSS
bars — deliberately small visual surface so the §3.4.7 work isn't
done piecemeal.

**Cross-references.** §3.4 chart umbrella (this section); §3.5 Phase 4c
BROWSE rebuild (downstream consumer); user-memory
`project_ui_enhancements.md` ("charts need work, revisit
post-grounding"); [PRESENTATION_HANDOFF_PLAN.md](PRESENTATION_HANDOFF_PLAN.md)
(the chart-prose alignment work that the migration could unify).

---

### §3.5 Phase 4c — BROWSE summary card rebuild `[size: XL]` `[impact: Output & Presentation]`

**Status:** ACTIVE 2026-04-28 — promoted from parking lot. Plan doc:
[`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md).

**Severity:** Medium-High — most-asked product surface; substrate (Phase 4a
real comps + Phase 4b Scout + Stage 4 model-accuracy loop) is now in place
so the rebuild can honestly hold together.

**Origin.** 2026-04-26 BROWSE walkthrough Thread 1. Owner read of the
current "what do you think of 1008 14th Ave, Belmar, NJ" response: the
bottom RECOMMENDATION card is filler — restates the recommendation as
"WHY THIS PATH" then dumps monthly carry / NOI / rental ease /
cash-on-cash with no narrative. Owner direction: rebuild the card so it
becomes the single primary summary card, with drilldowns the user can
expand into the pieces (comps, value thesis, projection, rent, town,
scout insights, etc.). Response shape becomes: prose at top → ONE rich
summary card with drilldowns → secondary cards collapse / hide behind
drilldowns.

**Why parked.** Two upstream prerequisites must land first or the
rebuild can't honestly hold together:
1. **Real comps** — the rebuilt summary card needs to cite real comp
   evidence in its body. Today's CMA is two-engine and Engine B (the
   user-facing one) doesn't have Engine A's scoring/adjustment logic.
   Tracked in [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md) (Phase 4a).
2. **Scout drilldown surface** — the rebuilt card's "Worth a closer
   look" / "Briarwood noticed" row needs scout output to populate it.
   Today's scout is single-pattern and claims-wedge-only. Tracked in
   [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) (Phase 4b).

**Plan reframe (2026-04-28).** Owner sign-off arrived in two passes. The
first pass approved a "one rich summary card with drilldowns" shape; the
second pass reframed it as **three stacked sections** organized like a
newspaper front page:

1. **Section A — `BrowseRead`** (always renders): stance pill + headline + masthead `market_trend` chart + flowed synthesizer prose. "Above the fold."
2. **Section B — `BrowseScout`** (conditional, only when scout fires): peer section with sub-head `WHAT YOU'D MISS`-style label + the existing `ScoutFinds` 0/1/2 cards. Renders nothing when scout returned empty — no placeholder, no rule, no header.
3. **Section C — `BrowseDeeperRead`** (always renders, drilldowns collapsed by default): chevron-list drilldowns into Comps / Value thesis / Projection / Rent / Town / Risk / Confidence & data / Recommended path. Each drilldown embeds its relevant chart inline when expanded.

Visual rhythm via section sub-heads + thin rules + ~2rem padding. **No
nested boxed cards** — that's the difference between "designed by a
newspaper editor" and "designed by an LLM." Detailed cycles, OD
resolutions, retired-vs-section component map, and per-cycle doc-update
list live in
[`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md).

**Cross-ref.** [PRESENTATION_HANDOFF_PLAN.md](PRESENTATION_HANDOFF_PLAN.md)
Open Design Decision #7 (editor pass / paragraph-with-interleaved-charts
layout) closes during Phase 4c Cycle 4 — the layout reframe addresses the
visible "paragraph + 5 charts in a row" complaint structurally.
[ROADMAP.md](ROADMAP.md) §3.4.7 chart-library evaluation is folded into
Phase 4c Cycle 5 per the 2026-04-28 owner sequencing call.

**Plan doc:** [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md).

**Dependencies:** Phase 4a complete ✅; Phase 4b complete ✅; Stage 4
complete ✅. All three substrate prerequisites met 2026-04-28.

---

## §4. Tactical Backlog

Single-session and short-handoff items. Sorted within each tier by
date descending. Open tactical items now carry product subsystem
`[impact: ...]` labels; see §7 for the preserved prong-taxonomy note and
its 2026-04-28 resolution.

### High

#### 2026-04-25 — Consolidate chat-tier execution: one plan per turn, intent-keyed module set `[size: L]` `[impact: Routing & Orchestration]`

**Severity:** High — this is the architectural lever for "Briarwood
beats plain Claude on underwriting." Today, the modules are running but
in a fragmented per-tool way that hides their output from the prose
layer.

**Files (anchor points for the consolidation):**
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — handle_browse, handle_decision, handle_projection, handle_risk, handle_edge, handle_strategy, handle_rent_lookup
- [briarwood/agent/tools.py](briarwood/agent/tools.py) — `get_value_thesis`, `get_cma`, `get_projection`, `get_strategy_fit`, `get_rent_estimate`, `get_property_brief`, `get_rent_outlook`, `get_property_enrichment`, `get_property_presentation`
- [briarwood/orchestrator.py](briarwood/orchestrator.py) — `run_briarwood_analysis_with_artifacts` (already exists; runs only via the wedge or `runner_routed.py` today)
- [briarwood/execution/registry.py](briarwood/execution/registry.py) — 23 scoped modules
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) — `build_unified_output` (the deterministic synthesizer, fed by orchestrator outputs)

**Issue.** Per the live diagnostic in [DECISIONS.md](DECISIONS.md)
"Chat-tier fragmented execution" 2026-04-25: a single BROWSE turn
produced 33 module-execution events across at least 5 separate execution
plans, with only 10 distinct modules actually running. 13 modules never
ran — including `comparable_sales` (the comp engine),
`location_intelligence`, `strategy_classifier`, `arv_model`,
`hybrid_value`. The composer LLM that does fire (4s/turn on BROWSE)
sees a narrow per-tool slice rather than the full
`UnifiedIntelligenceOutput` the orchestrator would have produced.

**Suggested fix (multi-step):**

1. **Per-AnswerType module manifest.** Define which modules each
   chat-tier AnswerType actually needs:
   - BROWSE / DECISION → full set (~all 23 modules; this is the
     first-read or buy/pass cascade)
   - PROJECTION → valuation, comparable_sales, scenario modules,
     rent_stabilization, hold_to_rent, resale_scenario,
     town_development_index, rental_option, hybrid_value
   - RISK → valuation, risk_model, legal_confidence, confidence,
     location_intelligence
   - EDGE → valuation, comparable_sales, scarcity_support,
     strategy_classifier, town_development_index, hybrid_value
   - STRATEGY → strategy_classifier, hold_to_rent, rental_option,
     opportunity_cost, carry_cost, valuation
   - RENT_LOOKUP → rental_option, rent_stabilization, income_support,
     scarcity_support, hold_to_rent
   - LOOKUP → no modules (single-fact retrieval)
   - Specific subsets to be tuned with traces, but the principle is
     intent-keyed not all-or-nothing.

2. **New consolidated chat-tier orchestrator entry.** Either extend
   `run_briarwood_analysis_with_artifacts` (already in
   `briarwood/orchestrator.py`) to accept an explicit module-set
   override, OR add a new
   `run_chat_tier_analysis(property_data, answer_type, ...)` that
   selects the module set per (1), runs `build_execution_plan` +
   `execute_plan` once, and calls `build_unified_output`. Returns the
   same `UnifiedIntelligenceOutput` shape so consumers don't fork.

3. **Modify dispatch handlers to use the consolidated entry.** Instead
   of calling 5–10 individual `tools.py` functions that each invoke
   their own plan, each handler calls the consolidated entry once and
   reads what it needs from the resulting `UnifiedIntelligenceOutput`.
   Keep `tools.py` functions around for one-off uses (e.g.,
   `get_property_summary` for cheap fact retrieval) but stop using
   them as the primary handler scaffolding.

4. **Roll out incrementally.** Start with `handle_browse`
   (highest-volume non-DECISION tier), verify the prose improves, then
   extend to `handle_projection`, `handle_risk`, etc. Pin per-handler
   regression tests.

5. **Surface the diagnostic.** Use `BRIARWOOD_TRACE=1` to verify each
   turn now runs ONE consolidated plan with no `valuation`-runs-5x
   duplication, and that previously-dormant modules
   (`comparable_sales`, `location_intelligence`, etc.) appear in
   `modules_run`.

**Out of scope here (separate ROADMAP):**
- Per-tool execution-plan caching tuning (why `risk_model` and
  `confidence` re-run 4-5x even when they should cache).
- The Layer 3 LLM synthesizer (separate entry below — consolidation is
  its prerequisite).

Surfaced during the 2026-04-25 output-quality audit handoff. Cross-ref
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §9.

#### 2026-04-25 — Layer 3 LLM synthesizer: prose from full UnifiedIntelligenceOutput `[size: M]` `[impact: LLM & Synthesis]`

**Severity:** High — this is the prose-layer companion to the
consolidated execution above. Without it, even a fully-populated
`UnifiedIntelligenceOutput` reaches the user as a brain dump or as the
composer's narrow paraphrase.

**Files:**
- [briarwood/agent/composer.py](briarwood/agent/composer.py) — current prose composer (LLM-backed but with narrow per-tier `structured_inputs`)
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) — current deterministic synthesizer (no LLM, populates UnifiedIntelligenceOutput fields)
- [briarwood/claims/representation/verdict_with_comparison.py](briarwood/claims/representation/verdict_with_comparison.py) — claim-render LLM (only fires for wedge-eligible turns)
- [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 3 — target-state description

**Issue.** Today's prose layer has three modes:
1. **Wedge claim renderer** — LLM rewrites a narrow claim slice (only
   for DECISION/LOOKUP-with-pinned, only when
   `BRIARWOOD_CLAIMS_ENABLED=true`).
2. **Composer** — LLM paraphrases per-handler `structured_inputs` (a
   narrow slice the handler hand-built from `tools.py` outputs).
3. **Deterministic synthesizer** — no LLM; populates ~17 named fields
   on `UnifiedIntelligenceOutput` with f-string templates (the
   "robotic prose" source per
   [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §3).

None of these takes the FULL `UnifiedIntelligenceOutput` and asks an
LLM "given this, what should I tell the user?" That is the Layer 3
role per [GAP_ANALYSIS.md](GAP_ANALYSIS.md).

**Suggested fix:**

1. **New module: `briarwood/synthesis/llm_synthesizer.py`** (or add to
   existing `briarwood/synthesis/`). Single function:
   `synthesize_with_llm(unified: UnifiedIntelligenceOutput, intent: IntentContract, llm: LLMClient) -> str`.
   Reads the full unified output, the user's intent contract, and
   produces intent-aware prose. Goes through
   `complete_structured_observed` so the LLM call shows up in the
   manifest.

2. **Numeric guardrail.** Numbers cited in the LLM's prose must round
   to a value present in `unified` (the same rule the composer's
   verifier already enforces for its narrow inputs). Reuse the
   verifier infrastructure at `api/guardrails.py`.

3. **Wire into chat-tier handlers** after the consolidated execution
   above lands. The handler returns whatever the synthesizer produces.

4. **Co-existence with the wedge.** When the wedge fires (DECISION +
   claims enabled), keep the claim renderer — it's already producing
   good prose for the verdict-with-comparison archetype. The Layer 3
   synthesizer fills the gap for everything else.

5. **Tone / framing.** This is the place where user-type conditioning
   eventually lands (per [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 1
   product decisions on user_type). For initial cut, omit user-type
   and just use the answer_type + question_focus.

**Dependency.** Blocks on consolidated execution above. Without that,
the synthesizer would have an empty or fragmented
`UnifiedIntelligenceOutput` to work from.

**Cross-ref:** [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 3,
[DECISIONS.md](DECISIONS.md) "Chat-tier fragmented execution"
2026-04-25, user-memory `project_llm_guardrails.md`.

### Medium

#### 2026-04-26 — Property resolver matches wrong slug ("526 West End Ave" → NC instead of NJ) `[size: S]` `[impact: Routing & Orchestration]`

**Severity:** Medium — silently sends the user to the wrong property.
Surfaced in user-memory note `project_resolver_match_bug.md`.

**Files:**
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — `_resolve_property_match` (the property-id resolver that maps free-text addresses to saved property slugs).

**Issue:** When the user types "526 West End Ave" without a state
qualifier, the resolver matches a North Carolina property slug instead
of the correct New Jersey one. Suggests the resolver is either (a)
ranking matches by string similarity without weighting state-of-residence
/ pinned-context, or (b) iterating the saved-properties list in a
directory-walk order that lets NC win on a tie. Either way, the user
gets a confidently-wrong property loaded.

**Suggested fix:** Audit `_resolve_property_match` for state-aware
ranking. Concretely: when the user's text doesn't include a state,
prefer matches whose `summary.state` aligns with the session's recent
activity (most-recent-property's state, or the inferred town's state).
Add a regression test pinning "526 West End Ave" → NJ when the session
has prior NJ context.

**Out of scope** for the active CMA Phase 4a work. Drive-by fix during
any future dispatch-handler touch.

#### 2026-04-26 — Zillow URL-intake address normalization regression `[size: S]` `[impact: Property Analysis]`

**Severity:** Medium — affects every user who pastes a Zillow URL to
onboard a property. Address comes back lowercased + missing comma
separators ("1223 Briarwood Rd Belmar Nj 07719" instead of "1223
Briarwood Rd, Belmar, NJ 07719").

**Files:**
- `tests/test_searchapi_zillow_client.py::SearchApiZillowClientTests::test_url_parser_hydrates_listing_fields_via_searchapi` — pinned the expected output ("1223 Briarwood Rd, Belmar, NJ 07719") but actual is "1223 Briarwood Rd Belmar Nj 07719".
- `tests/test_listing_intake.py::ListingIntakeTests::test_zillow_url_listing_can_be_hydrated_via_searchapi` — same regression, second test file asserting the same fix point.
- Likely culprits: `briarwood/listing_intake/parsers.py::ZillowUrlParser` or the address-fallback path in `briarwood/data_sources/searchapi_zillow_client.py::_normalize_listing` / `_compose_address`.

**Issue:** Test was passing at some prior commit; failing on `main` as
of 2026-04-26. Confirmed pre-existing (failure reproduces with
`git stash` of all 2026-04-26 changes). Not caused by CMA Phase 4a
Cycle 3a. Surfaced during Cycle 3a regression sweep per CLAUDE.md
"Contradictions, Drifts, and Bugs Found During Work" — flagged here,
not fixed (out of scope for the current handoff).

**Suggested fix:** `git bisect` between the test passing and `main` to
identify the regressing commit. The address normalization helpers
(`_normalize_address_string`, `_compose_address`,
`_parse_address_parts`) are likely candidates. The fallback
`_address_hint_from_url` (used when SearchApi returns no row matching)
parses the URL slug and may be uppercasing/lowercasing inconsistently.

**Out of scope** for CMA Phase 4a (which is focused on the
search-listings CMA path, not the URL-intake hydration path).

**Updated 2026-04-28 (Stage 4 closeout):** This same parser bug
corrupts `facts.town` in `data/saved_properties/<id>/inputs.json` —
state suffix glues onto the town string (e.g.,
`"Avon By The Sea Nj"`). Downstream impact: the comp store is keyed by
`town.strip().upper().replace(' ', '-')`, so the corrupted town hits
zero matches and `comparable_sales` collapses to `mode: fallback` with
confidence 0; `current_value` and `valuation` similarly lose
town-context anchoring and underpredict by ~30%. Stage 4 alignment
backfill on `526-w-end-ave-avon-by-the-sea-nj` was the canonical
reproducer: APE 32% pre-fix vs 5–7% post-fix across all three priority
modules. Implies every property onboarded via the broken URL parser
since the regression has the same data hazard. Suggested expansion of
the fix: along with the parser fix, add a one-shot scan
(`scripts/audit_saved_property_facts.py`?) that finds saved
`inputs.json` rows where `facts.town` ends in the state code and
corrects them. Two-letter state codes ending in `Nj` / `Ny` /
`Nc` / etc. are the matchable signature.

#### 2026-04-26 — Renovation premium pass-through to live comps (deferred from Cycle 4.3) `[size: M]` `[impact: Property Analysis]`

**Severity:** Medium — Engine A computes a measured renovation premium
that doesn't reach live (Zillow) comps. Affects fair-value math when
subject is a renovation play and comps are mostly live rows.

**Files:**
- [briarwood/decision_model/scoring.py:51](briarwood/decision_model/scoring.py#L51) — `estimate_comp_renovation_premium`. Today operates on `AnalysisReport`; Engine-A-internal.
- [briarwood/agents/comparable_sales/agent.py:784](briarwood/agents/comparable_sales/agent.py#L784) — TODO comment: "feed measured renovation premium from estimate_comp_renovation_premium()".
- [briarwood/agent/tools.py](briarwood/agent/tools.py) `get_cma` — Engine B's per-row scoring at `_score_and_filter_comp_rows` would be the integration point.

**Issue:** `estimate_comp_renovation_premium` reads subject
`condition_profile` and `capex_lane` to estimate how much of a comp's
price-per-sqft delta is renovation-premium. Live Zillow rows don't
carry these fields. Two failure modes if applied naively: (a)
defaulting subject condition silently distorts the premium math; (b)
skipping the premium adjustment for rows missing the data leaves the
user-facing CMA blind to renovation differences between subject and
comp.

**Suggested fix:** Two-step.
1. Decide whether renovation-premium-on-Zillow is actually load-bearing
   for prose. Wait for Cycle 5 (BROWSE wiring) to land and observe
   real-traffic CMA prose. If the synthesizer's comp citations
   consistently land cleanly without renovation context, the feature
   can stay deferred or be retired.
2. If needed: extend `estimate_comp_renovation_premium` to accept a
   `ComparableProperty`-shaped input (or its dict form), with an
   explicit "no renovation context" branch that surfaces the missing
   data as a `selection_rationale` qualification rather than silently
   defaulting. Wire into `_score_and_filter_comp_rows`.

**Out of scope** for the current CMA Phase 4a Cycle 4 work. Originally
scoped as Cycle 4.3; deferred per the Cycle 4 wrap-up.

#### 2026-04-28 — Comp store town-name canonicalization (Avon By The Sea split into 91 + 72 spelling variants) `[size: S]` `[impact: Property Analysis]`

**Severity:** Medium — silently halves the available comp pool for any
Avon-By-The-Sea property and likely affects other towns with
hyphenation variants. Surfaced during Stage 4 Loop 1 closeout.

**Files:**
- [data/comps/sales_comps.json](data/comps/sales_comps.json) — 3,919
  rows; town breakdown shows `"Avon By The Sea": 91` AND
  `"Avon-by-the-Sea": 72` as separate buckets.
- [briarwood/agents/comparable_sales/store.py:66](briarwood/agents/comparable_sales/store.py#L66)
  — `JsonComparableSalesStore` keys by `town.strip().upper().replace(' ', '-')`
  → produces `AVON-BY-THE-SEA` for both forms but only after
  same-string lookup.
- Bulk ingestion sources to audit:
  [`briarwood/agents/comparable_sales/sr1a_parser.py`](briarwood/agents/comparable_sales/sr1a_parser.py),
  [`ingest_public_bulk.py`](briarwood/agents/comparable_sales/ingest_public_bulk.py),
  ATTOM bulk-fetch path under `scripts/fetch_attom_sales.py`.

**Issue:** The 3,919-row comp store has both `"Avon By The Sea"` (91
rows, mostly SR1A public records) and `"Avon-by-the-Sea"` (72 rows,
likely ATTOM-sourced) as distinct town strings. Same physical town,
two buckets. `JsonComparableSalesStore`'s town-key normalizer runs on
`.strip().upper().replace(' ', '-')`, so the two strings produce
different keys (`AVON-BY-THE-SEA` is the same, but lookups by source
town string don't pre-normalize the user's town input). Net effect: a
property looked up as `"Avon By The Sea"` likely sees only the 91
SR1A-sourced rows, missing the 72 ATTOM-sourced rows. Other towns
(Wall vs Wall Township: 890 vs 61 rows) have similar splits.

**Suggested fix:**
1. Add a single `_canonicalize_town(name: str) -> str` helper to
   `briarwood/data_quality/normalizers.py` (or co-locate in
   `comparable_sales/store.py`) that does
   `re.sub(r'[\s\-]+', ' ', name).strip().title()` plus a small
   alias map (`Avon-by-the-Sea` → `Avon By The Sea`,
   `Wall Township` → `Wall`, etc.).
2. Apply on every ingestion entrypoint AND on every lookup-key
   construction.
3. One-shot rewrite of `data/comps/sales_comps.json` to canonicalize
   existing rows (preserve as `.bak`).
4. Regression test with the 526 W End scenario and the Wall/Wall
   Township pair.

**Out of scope** for Stage 4 closeout. Tracked here so future CMA work
or BROWSE rebuild (Phase 4c) can pull it in when comp coverage is the
limiting factor.

#### 2026-04-28 — Backfill `data/outcomes/` from ATTOM sale-history endpoint `[size: M]` `[impact: Data, Persistence & Feedback]`

**Severity:** Medium — Stage 4 Loop 1 closeout established the manual
outcome ingestion path; ATTOM's `sale_history_snapshot()` /
`sale_history_detail()` is the natural automated source for backfilling
real (public-record) outcomes per saved property without waiting for
each property to record a sale through other channels. Codex flagged
this in 3:19 PM 2026-04-28 conversation; surfaces here as the
implementation slice.

**Files:**
- [scripts/fetch_attom_sales.py](scripts/fetch_attom_sales.py) — already
  calls ATTOM `/sale/snapshot` for comp store enrichment; pattern
  reusable.
- [briarwood/data_sources/attom_client.py:130](briarwood/data_sources/attom_client.py#L130)
  — `sale_history_snapshot(...)` and `sale_history_detail(...)` for
  per-property lookups.
- [scripts/backfill_outcomes.py](scripts/backfill_outcomes.py) and
  [scripts/backfill_model_alignment.py](scripts/backfill_model_alignment.py)
  — downstream consumers of the resulting JSONL.
- New script: `scripts/fetch_attom_outcomes.py` (proposed name).

**Issue:** Today Stage 4 needs a hand-curated `data/outcomes/*.jsonl`
file. ATTOM has the public-record sale history per address; we already
hold an `ATTOM_API_KEY`. A small adapter script can iterate
`data/saved_properties/*/inputs.json`, call `sale_history_snapshot`
per address, emit Stage-4-shape outcome rows
(`{property_id, address, outcome_type: "sale_price", outcome_value,
outcome_date, source: "attom_sale_history", source_ref}`), and
optionally chain into `scripts/backfill_outcomes.py` and
`scripts/backfill_model_alignment.py`.

**Suggested fix:** Single new script
`scripts/fetch_attom_outcomes.py` with `--dry-run` first, writing to
`data/outcomes/attom_outcomes_<date>.jsonl`. Skip properties already
present in any existing outcome file unless `--overwrite`. Rate-limit
to ATTOM's ~1 req/sec free-tier ceiling. Tests against a fixture
ATTOM response.

**Out of scope** for Stage 4 closeout. This is the v2 ingestion path
that subsumes the manual entry once it works; manual entry stays as
the v1 fallback.

This entry replaces and supersedes the older
"2026-04-28 — Automate public-record outcome ingestion after Stage 4
manual loop" framing — same theme, sharper next step.

#### 2026-04-26 — Plumb subject lat/lon through `summary` for per-row CMA distance filtering `[size: M]` `[impact: Property Analysis]`

**Severity:** Low-Medium — quality-of-life. Adjacency-map cross-town
expansion (CMA Phase 4a Cycle 4.1) provides the geographic constraint
today; per-row distance enforcement is the next-cleaner option.

**Files:**
- [briarwood/agent/tools.py](briarwood/agent/tools.py) `get_property_summary` and the `summary` dict shape.
- [briarwood/agent/tools.py](briarwood/agent/tools.py) `_score_and_filter_comp_rows` (currently called with `subject_lat=None, subject_lon=None` defaults; proximity falls back to neutral 0.55).
- [briarwood/modules/cma_invariants.py](briarwood/modules/cma_invariants.py) — `MAX_DISTANCE_MILES_CROSS_TOWN = 3.0` constant exists but isn't enforced anywhere yet.

**Issue:** Cycle 4.1 added cross-town SOLD expansion using a hand-tuned
`TOWN_ADJACENCY` map. The map is a reasonable proxy for geographic
proximity within the six-town shore corridor, but it's not data-driven
and doesn't enforce `MAX_DISTANCE_MILES_CROSS_TOWN`. The cleaner
long-term shape is: plumb subject lat/lon through `summary.json`
(geocode at intake time, cache), then enforce the 3-mile cap per-row in
`_score_and_filter_comp_rows`. That would also let `score_proximity`
produce non-neutral scores for both same-town and cross-town rows.

**Suggested fix:**
1. Add `latitude` / `longitude` fields to the property summary contract.
   Source: existing geocoding in
   `briarwood/agents/comparable_sales/geocode.py` (already used to
   enrich saved comps), or a fresh per-property lookup at intake time.
   Cache on the property's `summary.json`.
2. Pass `subject_lat` / `subject_lon` from `summary` into
   `_score_and_filter_comp_rows` in `get_cma`.
3. Add an explicit per-row distance filter: drop rows where
   `distance_to_subject_miles > MAX_DISTANCE_MILES_CROSS_TOWN` (and the
   row is cross-town) or `> MAX_DISTANCE_MILES_SAME_TOWN` (and the row
   is same-town). This makes the existing distance constants finally
   load-bearing.
4. Once distance-based filtering is in place, the adjacency map can
   stay as a "which towns to query" coarse filter (adjacency limits the
   SearchApi call surface to nearby towns) while distance becomes the
   per-row truth.

**Out of scope** for CMA Phase 4a Cycle 4.

#### 2026-04-25 — Module-result caching at the per-tool boundary is leaky `[size: S]` `[impact: Routing & Orchestration]`

**Severity:** Low-medium — efficiency, not correctness. Will be largely
obviated when the consolidated execution above lands, but worth a note
in case consolidation is delayed.

**Files:**
- [briarwood/execution/executor.py](briarwood/execution/executor.py) — `build_module_cache_key`
- [briarwood/execution/registry.py](briarwood/execution/registry.py) — `MODULE_CACHE_FIELDS` (per-module cache field list)

**Issue.** In a single BROWSE turn, the manifest showed `risk_model`
running 4x fresh (no cache hits), `confidence` running 5x fresh,
`legal_confidence` running 4x fresh — even though all 4-5 calls were
within the same chat turn for the same property. Meanwhile `valuation`
and `carry_cost` cached correctly (4 cache hits each after one fresh
run). The cache key for `risk_model` / `confidence` / `legal_confidence`
apparently includes context fields that vary between the per-tool
execution plans, defeating reuse.

**Suggested fix.** Audit `MODULE_CACHE_FIELDS` for the three offenders
(`risk_model` is at executor.py:59-69, `confidence` at 71-82). Likely
culprit: a field is being read from `assumptions` or `market` that
varies per-tool but shouldn't affect the module's output. Add
per-module regression tests pinning cache hits across the per-tool
boundary.

**Probably moot after consolidation.** If the chat-tier executes one
plan per turn (per the consolidation entry above), each module runs at
most once per turn and this caching issue doesn't bite. Keep this
entry in case consolidation is delayed.

#### ✅ 2026-04-25 — Audit router classification boundaries with real traffic `[size: M]`

**Status:** RESOLVED 2026-04-28 — landed via
[`ROUTER_AUDIT_HANDOFF_PLAN.md`](ROUTER_AUDIT_HANDOFF_PLAN.md) Cycles 1-4
on 2026-04-28. Stage 1's `turn_traces` table provided the corpus the
entry was waiting on (5 known misses + 8 synthetic boundary cases). The
prompt at `_LLM_SYSTEM` ([briarwood/agent/router.py:169-244](briarwood/agent/router.py#L169-L244))
gained STRATEGY escalation phrasings, EDGE sensitivity / counterfactual
phrasings, EDGE comp-set follow-ups, SEARCH list-imperative phrasings,
3 new IMPORTANT MAPPINGS lines, and 2 new counter-example pairs (BROWSE
↔ STRATEGY and RISK ↔ EDGE). `_COMP_SET_RE` in
[briarwood/agent/dispatch.py:2720-2727](briarwood/agent/dispatch.py#L2720-L2727)
widened to catch "show me the comps" / "list the comps" / "what comps
did you use" / "explain your comp choice" with a negative case pinned
("comparable sales market" stays RESEARCH). 14 new tests; suite delta
+14 passes, 16 pre-existing failures unchanged. **Guardrail flag
(deferred):** every successful LLM classification is hardcoded to
`confidence=0.6` at [router.py:407](briarwood/agent/router.py#L407);
filed as a follow-on inside this entry. See
[DECISIONS.md](DECISIONS.md) 2026-04-28 entry "Router classification
audit Cycle 1-4 landed" for the full corpus + the Guardrail Review.

**Severity:** Medium — every LOOKUP/DECISION miss produces a one-line
answer to a question that wanted analysis, which is the user's #1
complaint.

**Files (evidence):**
- [briarwood/agent/router.py:169-219](briarwood/agent/router.py#L169-L219) — `_LLM_SYSTEM` prompt
- [api/prompts/lookup.md](api/prompts/lookup.md) — "Reply in 1–2 sentences" contract
- [tests/agent/test_router.py](tests/agent/test_router.py) — `LLM_CANNED` + `PromptContentRegressionTests`

**Context:** The 2026-04-25 output-quality audit handoff caught one
specific miss: "what is the price analysis for 1008 14th Ave, belmar,
nj" was classified as `AnswerType.LOOKUP` (conf 0.60), which routed to
`handle_lookup` (no wedge, no orchestrator), which obeyed its 1-2
sentence prompt and produced "The asking price for 1008 14th Avenue in
Belmar, NJ, is $767,000." The user expected analysis, got one fact.
The router prompt has been updated to route price-analysis phrasings
to DECISION ([DECISIONS.md](DECISIONS.md) and
[briarwood/agent/README_router.md](briarwood/agent/README_router.md)
Changelog 2026-04-25).

**The pattern is broader than this one query.** The router uses
gpt-4o-mini and a single shot of structured-output classification.
Without traffic-driven feedback, intent boundaries that LOOK clear in
the prompt drift in practice — the only signal we have is what the LLM
produces, and we don't measure it. Cross-references the user-memory
note "Intent tiers for single-property questions" (browse vs decision
unlock on escalation) and "LLM guardrails are currently too tight"
(loosen LLM invocation to generate training signal).

**Issue:** No mechanism exists to detect router classification misses
in production traffic. Each miss is invisible until a user notices a
thin response and complains. There is no log of "here's how each turn
was classified, with what confidence, and what the user did next." The
2026-04-25 audit added one regression case; we'll keep adding them
reactively unless we audit the prompt against a real corpus.

**Suggested fix:** Two complementary moves —

1. **Capture classification + outcome per turn** in the per-turn
   invocation manifest being added in the 2026-04-25 audit's Step 4.
   Specifically: log `answer_type`, `confidence`, `reason`, the user's
   text, and (when telemetry catches up) whether the user asked a
   follow-up that suggests the classification missed. This is
   observability, not a fix, but it gives us the corpus to audit
   against.

2. **Audit the prompt against ~20-30 saved real queries** when there's
   a corpus. Specifically look for boundary cases: "price"-bearing
   questions that should be DECISION not LOOKUP, "what about"-bearing
   questions (browse vs decision), "rent"-bearing questions (rent_lookup
   vs decision-with-rent-context), etc. Update the prompt's IMPORTANT
   MAPPINGS and Counter-example sections.

Out of scope for the immediate handoff — the immediate fix targeted
only the price-analysis miss. The broader audit is queued for after
Step 4 logging lands.

**Additional misses observed 2026-04-25** (during Cycle 5 post-landing
UI smoke):
- "Why were these comps chosen?" → classified as `RESEARCH` (running
  `research_town`) instead of `EDGE` with the comp_set follow-up path.
  The contextualize-followup rewrite at
  [briarwood/agent/dispatch.py:4536-4551](briarwood/agent/dispatch.py#L4536-L4551)
  has a `_COMP_SET_RE` that matches "comp set" but apparently doesn't
  catch "Why were these comps chosen" (the regex looks for "comp set",
  "cma", "comps" with specific context). The user's clear intent was a
  comp-set followup on the current property; the LLM router took it as
  a market-research query about the area. This is two-issues-in-one:
  the context-rewrite regex is too narrow, and the LLM router's
  RESEARCH classification ignored the pinned property context.

**Additional miss observed 2026-04-26** (during CMA Phase 4a Cycle 5
browser smoke, per-turn manifest evidence):
- "show me the comps" (with a pinned BROWSE-tier property) → classified
  as `BROWSE` (conf 0.60), dispatched to `browse_stream`. The classifier
  ran the full BROWSE cascade again instead of routing to `EDGE` with
  the comp_set follow-up path. Result: same handler, same prose
  template, same `comp_roster`, near-identical response — visually it
  looks like the user re-asked "what do you think of X." Same root
  cause as the "Why were these comps chosen?" miss above: the LLM
  router doesn't recognize "the comps" / "show me X" phrasings as
  comp-set follow-ups when there's a pinned property. The
  `_COMP_SET_RE` regex should also catch "show me the comps", "list
  the comps", "what are the comps", "the comp set".

When the audit-against-corpus work happens, a few things to check:
1. The `_COMP_SET_RE` regex coverage. "Why were these comps", "what
   comps did you use", "explain your comp choice", "show me the comps",
   "list the comps", "what are the comps" should all rewrite to EDGE.
2. The LLM router's prompt should mention that questions referencing
   "these / your / the" comps with a pinned property are
   property-followups, not market research.
3. The "Show me listings here" query (Cycle 5 same UI smoke) classified
   as BROWSE rather than SEARCH — also worth review. The user wanted a
   list, not the BROWSE-style first-read prose.
4. The "show me the comps" miss (2026-04-26) is the same shape as #3 —
   "show me X" with X being a Briarwood-side artifact (comps, listings,
   etc.) should route to a list/drilldown surface, not BROWSE.

**Additional misses observed 2026-04-28** (during AI-Native Foundation
Stage 1 post-landing UI smoke; Stage 1 persistence is the substrate
this audit was waiting on — the corpus is now writing itself):

- **"Walk me through the recommended path"** (with pinned BROWSE-tier
  property) → classified as `BROWSE` (conf 0.60, reason `'llm
  classify'`), dispatched to `browse_stream`. Should be `STRATEGY`. The
  user's intent is "given this property, what's the recommended path
  forward (hold-to-rent / flip / wait)?" — exactly what
  `handle_strategy` exists to answer. This is the canonical
  *escalation* pattern called out in user-memory
  `project_intent_tiers.md` ("Decision unlocks on escalation"); the
  router stayed inside BROWSE and re-ran the full first-read cascade
  (~24s) instead of routing to STRATEGY. Trace
  `turn_id=341f4fabae8c`, `conversation_id=909d323f8e4f`.

- **"What would change your value view?"** (same pinned property) →
  classified as `RISK` (conf 0.60), dispatched to `dispatch_stream` →
  `handle_risk`. Should be `EDGE`. The user is asking a counterfactual
  / sensitivity question ("which assumptions are load-bearing on your
  number") — `handle_edge` has explicit `value_change` and
  `entry_point` follow-up paths designed for this. RISK enumerates
  downside risk factors; that is not what was asked. Trace
  `turn_id=2ab6e3a94f42`. Same root cause as the "show me the comps"
  miss above: the LLM router doesn't recognize sensitivity / "what
  would shift X" phrasings as EDGE follow-ups when there's a pinned
  property.

**Confidence pattern across all 2026-04-28 misses:** every miss came
back at exactly `conf=0.60` with `reason='llm classify'` — the
router's default-fallback confidence. The classifier is not
differentiating intent boundaries with any signal we can act on.
Cross-references the 2026-04-24 router schema-fix entry (the
`$ref + default` sibling-keys bug that was producing the same
"default fallback" pattern at the schema layer) — that fix landed,
but the classifier's intent boundaries themselves still default-fall
on the close cases.

5. **STRATEGY escalation triggers.** The LLM prompt should enumerate
   "what's the recommended path", "walk me through the recommended
   path", "should I do X or Y", "what should I do here" as STRATEGY
   triggers when a property is pinned. Today the prompt treats them
   as BROWSE follow-ups, which silently re-runs the first-read.
6. **EDGE / RISK boundary.** "What would change your value view",
   "what assumption is load-bearing", "what if X were different",
   "how sensitive is this to Y" are sensitivity / counterfactual
   questions and belong in EDGE, not RISK. RISK is for downside
   factor enumeration ("what could go wrong"). The boundary is
   "what would *shift* my view" (EDGE) vs "what could *go wrong*"
   (RISK). Add explicit counter-examples to the prompt.

#### ✅ 2026-04-28 — Router LLM `confidence=0.6` cap collapses classifier signal `[size: S]`

**Status:** RESOLVED 2026-04-28 — landed via
[`ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md`](ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md)
Cycle 1. `RouterClassification` schema gained `confidence: float`
(constrained `[0.0, 1.0]`); `_LLM_SYSTEM` updated to ask for a 0-1
score with explicit semantic anchors; `classify` plumbs the LLM's
emission into `RouterDecision.confidence` with a deliberate `max(...,
0.4)` floor (keeps every successful classification above the 0.3
default-fallback bucket). 3 new tests for the flow + 1 prompt-content
regression. Stage 3 dashboards now have a real signal to drive
low-confidence drill-downs. See
[briarwood/agent/README_router.md](briarwood/agent/README_router.md)
Changelog 2026-04-28 (Round 2) and DECISIONS.md 2026-04-28 entry
"Router Quality Round 2".

**Severity:** Medium — guardrail holding back routing quality. Per
user-memory `project_llm_guardrails.md` ("Loosen LLM invocation
broadly; ... Flag any guardrail holding back quality").

**Files:**
- [briarwood/agent/router.py:402-412](briarwood/agent/router.py#L402-L412)
  `classify`'s LLM-success branch — `RouterDecision(..., confidence=0.6, ...)`
  hardcoded.
- [briarwood/agent/router.py:245-258](briarwood/agent/router.py#L245-L258)
  `RouterClassification` Pydantic schema — has no `confidence` field
  today.

**Issue.** Every successful LLM classification is hardcoded to
`confidence=0.6` at [router.py:407](briarwood/agent/router.py#L407)
regardless of the model's actual signal. Spotted during 2026-04-28
post-Stage-1 corpus review: every classifier miss in the live UI smoke
came back at exactly `conf=0.60` with `reason='llm classify'`. The
classifier may be very confident on canonical phrasings ("what do you
think of X" → BROWSE) and barely confident on ambiguous ones ("Walk me
through the recommended path" → BROWSE-or-STRATEGY) — but downstream
sees the same 0.6 either way. This collapses the only signal we have
for "should this turn be re-classified" or "should the dashboard flag
this as low-confidence." It also defeats Stage 3's planned "top-N
lowest-confidence turns" drill-down.

**Suggested fix:** Two-step.

1. Add `confidence: float` to `RouterClassification` (in `[0.0, 1.0]`,
   constrained via Pydantic). Update `_LLM_SYSTEM` to ask the LLM for
   "your confidence in this classification on a 0–1 scale" — modeled
   on how the synthesizer's confidence works elsewhere in the codebase.
2. In `classify`, plumb `result.confidence` into
   `RouterDecision.confidence` instead of the hardcoded 0.6. Optional
   floor (e.g., `max(result.confidence, 0.4)`) so the LLM's noise
   doesn't drive everything to LOOKUP via the existing 0.3 fallback
   bucket; document the floor as a deliberate guardrail.

**Tests.** New `LLM_CANNED` cases that pin different confidence values
(via the `ScriptedLLM`) and assert `RouterDecision.confidence` matches
the LLM's emission, not the hardcoded 0.6.

**Out of scope** for the 2026-04-28 router-audit handoff (Cycles 1-4
were prompt + regex only). Surfaced inside that handoff's Guardrail
Review per `project_llm_guardrails.md`. Worth ~30 min next time the
router file is open.

**Follow-on:** Stage 3 dashboard ([ROADMAP.md](ROADMAP.md) §3.1
Stage 3) will get useful "low-confidence turn" drill-downs once this
lands. Without the fix, the drill-down has nothing to filter on.

**Compounding signal-loss with the existing user-type gap.** GAP_ANALYSIS
Layer 1 already flags that `RouterDecision` has no `user_type` field.
Combined with the collapsed `confidence`, the chat router emits two
classification axes (intent + persona) but persists training signal
on neither. The `turn_traces` table records what the classifier said,
but not how confidently it said it or what type of user said it. Both
gaps should be planned together per the GAP_ANALYSIS Layer 1 risk —
"start collecting user-type signal in the router before you start
making decisions based on it" — and the same applies to confidence.

#### ✅ 2026-04-28 — `parse_overrides` bare-renovation false-positive shoehorns scenario requests into DECISION `[size: S]`

**Status:** RESOLVED 2026-04-28 — landed via
[`ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md`](ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md)
Cycle 2. Resolution differs from the original entry's "Layer A
tightening in `parse_overrides`" recommendation: the tightening
landed in `router.py` instead. `parse_overrides` continues to set
`mode="renovated"` whenever `_RENO_RE` matches (preserving downstream
dispatch behavior — `inputs_with_overrides` still receives the
renovation hint), but the router's `has_override` check now requires
a *material* override (`ask_price` or `repair_capex_budget`). Bare
`mode`-only signals flow through to the LLM classifier. Plus Layer B
landed: `_PROJECTION_OVERRIDE_HINT_RE` widened to catch `renovation
scenarios?`, `run scenarios?`, `scenario`, `5-year`, `ten-year`,
`outlook`. 1 new pin in `tests/agent/test_overrides.py` + 2 new
`PrecedenceTests` in `tests/agent/test_router.py`; 1 existing rent-override
test reframed to use an explicit price. See
[briarwood/agent/README_router.md](briarwood/agent/README_router.md)
Changelog 2026-04-28 (Round 2) and DECISIONS.md 2026-04-28 entry
"Router Quality Round 2".

**Severity:** Medium — guardrail-blocks-quality finding from the
2026-04-28 post-router-audit smoke. Per user-memory
`project_llm_guardrails.md` directive ("Flag any guardrail holding back
quality"). Same class as the `confidence=0.6` cap entry above.

**Files:**
- [briarwood/agent/overrides.py:44](briarwood/agent/overrides.py#L44)
  `_RENO_RE = re.compile(r"\b(renovate[d]?|renovation|fully renovated|post[- ]reno|after reno)\b", re.IGNORECASE)`
- [briarwood/agent/overrides.py:131-132](briarwood/agent/overrides.py#L131-L132)
  `parse_overrides` sets `overrides["mode"] = "renovated"` whenever
  `_RENO_RE` matches — no price / capex / question-context required.
- [briarwood/agent/router.py:371-400](briarwood/agent/router.py#L371-L400)
  the what-if-price-override short-circuit reads
  `has_override = bool(parse_overrides(text))` and routes to DECISION
  by default when no rent/projection sub-hint matches.

**Live evidence** (turn_traces row, conversation `8792d9457d14`):

```
user_text="Run renovation scenarios"
answer_type=decision   conf=0.70   reason="what-if price override"
duration_ms=5931   wedge.fired=true   wedge.archetype=verdict_with_comparison
```

The user got a verdict-with-comparison response for what should have
been a renovation-scenario analysis (PROJECTION; the prompt's
PROJECTION definition explicitly names "renovation budget questions,
ARV, resale-after-renovation"). Discovered post-2026-04-28 router audit
when the audit corpus didn't catch it — different bug class (regex +
defaulting in `overrides.py`/`router.py`, not `_LLM_SYSTEM`).

**Trace through the router** for "Run renovation scenarios":
1. `parse_overrides` → `{"mode": "renovated"}` because `_RENO_RE`
   matches the bare word "renovation" — no price, no capex, no
   question-context check.
2. Router: `has_override = True`; runs through the override branch.
3. `_RENT_LOOKUP_HINT_RE` doesn't match → skip.
4. `_PROJECTION_OVERRIDE_HINT_RE` (`arv|after repair value|sell it for|
   resale|turn around and sell|flip`) doesn't match — "renovation" /
   "scenarios" are NOT in the regex.
5. Default: return DECISION.

**Suggested fix (two layers, do both):**

**Layer A — Tighten `parse_overrides` so mode-only is not an override.**
Either:
- (a) Set `overrides["mode"] = "renovated"` only when paired with a
  price, capex, or "value/worth/price" question token. Bare
  "renovation" alone shouldn't count as an override.
- (b) Distinguish overrides from "narrative hints" via two return
  channels: `overrides` (price/capex) vs `narrative_hints` (mode).
  Router only short-circuits on real overrides; narrative hints flow
  to the LLM.

Recommendation: **(a)** — minimum diff, no contract change to
`parse_overrides`'s signature. The downstream `inputs_with_overrides`
already handles mode-only overrides correctly when they're paired with
real input changes; tightening at parse-time is safe.

**Layer B — Widen `_PROJECTION_OVERRIDE_HINT_RE` to catch
scenario/renovation imperatives.** Add tokens like `scenario(s)`,
`run scenarios`, `renovation scenarios` so even if (A) is bypassed,
the override path correctly routes to PROJECTION instead of falling
through to DECISION. Defense in depth.

**Tests.** New `LLM_CANNED` cases pinning "Run renovation scenarios"
→ PROJECTION, "Run scenarios for X" → PROJECTION. New
`PrecedenceTests` case in `tests/agent/test_router.py` asserting that
mode-only `parse_overrides` output does NOT trigger the
what-if-price-override path. New `parse_overrides` tests in
`tests/test_overrides.py` (or wherever) pinning that bare "renovation"
returns `{}`.

**Out of scope** for the closed router-audit handoff (Cycles 1-4 were
prompt + comp-set regex only; this is a different file/different bug
class). Worth ~30 min next time the router/overrides files are open.
Sequence-wise: pair with the `confidence=0.6` fix above for one
"router quality round-2" handoff.

#### 2026-04-28 — `data/llm_calls.jsonl` rotation/compaction policy `[size: S]` `[impact: Data, Persistence & Feedback]`

**Severity:** Low — operational concern, not yet biting. Filed as the
Stage 1 closeout follow-on per [PERSISTENCE_HANDOFF_PLAN.md](PERSISTENCE_HANDOFF_PLAN.md)
§4 Cycle 4 "Out of scope" list.

**Files:**
- [briarwood/agent/llm_observability.py:80-116](briarwood/agent/llm_observability.py#L80-L116) — `LLMCallLedger.append` writes one JSON line per LLM call, append-only, no rotation.
- `data/llm_calls.jsonl` — production sink. Was 11 KB / 21 lines after the 2026-04-28 smoke; growth rate ~7-10 lines per chat turn (every LLM surface gets a record).

**Issue.** The JSONL grows monotonically. At ~10 lines/turn × ~200 turns/week × ~150 bytes/line, that's ~300 KB/week → ~15 MB/year. Not catastrophic but worth a cap before it hits a 100MB-class problem.

**Suggested fix.** Pick one when size becomes annoying:
1. Daily rollover: `data/llm_calls/YYYY-MM-DD.jsonl` instead of one file.
2. Size-based rollover: when current file > N MB, rename to `.1`, start fresh.
3. Compaction: archive older-than-N-days lines into a compressed archive that the Stage 3 dashboard reads on demand.

Recommendation: defer until file size becomes annoying. The path is overridable via `BRIARWOOD_LLM_JSONL_PATH` so an operator can move it manually if needed. Stage 3 dashboard work will likely surface the right cadence.

**Out of scope** until the file is actually large.

#### 2026-04-28 — Stage 3 dashboard analytic-query sketches `[size: S]` `[impact: Data, Persistence & Feedback]`

**Severity:** Low-Medium — substrate is in place; sketches accelerate Stage 3 design.

**Source.** Stage 1 closeout follow-on per [PERSISTENCE_HANDOFF_PLAN.md](PERSISTENCE_HANDOFF_PLAN.md) Cycle 4 + [ROADMAP.md](ROADMAP.md) §3.1 Stage 3 success criteria.

**Files (read targets):**
- `data/web/conversations.db` — `turn_traces`, `messages`, `conversations` tables.
- `data/llm_calls.jsonl` — JSONL sink.

**Suggested sketches** to draft before Stage 3 picks up:

```sql
-- "What was the slowest turn this week and why?"
SELECT turn_id, user_text, answer_type, ROUND(duration_ms_total/1000, 1) AS sec,
       json_array_length(modules_run) AS modules,
       json_array_length(llm_calls_summary) AS llm_calls,
       conversation_id
FROM turn_traces
WHERE started_at > strftime('%s', 'now', '-7 days')
ORDER BY duration_ms_total DESC
LIMIT 10;

-- "Which answer_type is the most expensive on average?"
SELECT answer_type,
       ROUND(AVG(duration_ms_total)) AS avg_ms,
       COUNT(*) AS n
FROM turn_traces
WHERE started_at > strftime('%s', 'now', '-7 days')
GROUP BY answer_type
ORDER BY avg_ms DESC;

-- "Top low-confidence turns" — BLOCKED on the confidence=0.6 fix
-- above. Today every LLM-classified row carries 0.6, so the filter
-- collapses to "everything except cache hits." Sketch retained as
-- the contract Stage 3 will use once the fix lands.
SELECT turn_id, user_text, answer_type, confidence, classification_reason
FROM turn_traces
WHERE confidence < 0.6
  AND started_at > strftime('%s', 'now', '-7 days')
ORDER BY confidence ASC, started_at DESC
LIMIT 20;
```

Plus one cross-table query the dashboard will want:

```sql
-- "Per-conversation fingerprint" — title, last 5 turns with metric
SELECT c.title, m.role, m.content, m.answer_type, m.latency_ms, m.created_at
FROM conversations c
JOIN messages m ON m.conversation_id = c.id
WHERE c.id = ?
ORDER BY m.created_at ASC;
```

**Out of scope** until Stage 3 work begins. Sketches live here so Stage 3 doesn't start cold on the SQL.

#### ✅ 2026-04-28 — `docs/current_docs_index.md` does not list authoritative orientation docs `[size: S]` `[impact: Docs, Process & Repo Health]`

**Status:** RESOLVED 2026-04-28 — `docs/current_docs_index.md` now lists
the same authoritative project-state docs that `CLAUDE.md` / `CODEX.md`
send sessions to: `DECISIONS.md`, `ROADMAP.md`,
`ARCHITECTURE_CURRENT.md`, `GAP_ANALYSIS.md`, and `TOOL_REGISTRY.md`,
plus the now-complete handoff plans that remain useful context.

**Severity:** Low — docs drift; new sessions reading the index miss the canonical orientation set.

**Files:**
- [docs/current_docs_index.md](docs/current_docs_index.md) — claims "Use this file as the starting point for product and implementation work" but lists `AGENTS.md`, `CURRENT_STATE.md`, `docs/scoped_execution_support.md`, `docs/operational_model_sweep.md`, `docs/backend_model_surface_matrix.md`, `unified_intelligence.md`, `briarwood/routing_schema.py`, `briarwood/orchestrator.py`.
- [CLAUDE.md](CLAUDE.md) — repo-root orientation doc says read `DECISIONS.md`, `ROADMAP.md`, `ARCHITECTURE_CURRENT.md`, `GAP_ANALYSIS.md`, `TOOL_REGISTRY.md`. None of those appear in the index.

**Issue.** Two orientation surfaces exist with different recommendations. CLAUDE.md is loaded automatically into every session and is the de-facto authority. `current_docs_index.md` is referenced from the docs directory and reads as a parallel index. The two were authored at different times and have drifted.

**Suggested fix.** Pick one of:
1. Delete `current_docs_index.md`. CLAUDE.md is the orientation doc; the index is redundant.
2. Rewrite `current_docs_index.md` as a *project-state* index (DECISIONS, ROADMAP, ARCHITECTURE_CURRENT, GAP_ANALYSIS, TOOL_REGISTRY, plus the handoff plan docs) that mirrors what CLAUDE.md tells sessions to read.
3. Keep both and add a sentence at the top of each pointing to the other ("CLAUDE.md is the per-session orientation; this index is the supplementary product-state map").

Recommendation: **(1)** if no reader habitually goes to `docs/current_docs_index.md`; otherwise **(2)** so the two stay convergent. Mechanical drift fix; do not silently reconcile per CLAUDE.md.

**Resolution.** Chose option 2: keep `current_docs_index.md` as the
project-state index and make it converge with the root startup docs.

#### 2026-04-25 — `get_cma` Step 2 still open (cache-miss audit) `[size: S]` `[impact: Property Analysis]`

**Severity:** Medium — visible in the per-turn manifest as 5 trailing
duplicate module-run events on every BROWSE turn (and likely every
other tier that calls `get_cma`). Step 1 resolved 2026-04-25; Step 2
remains.

**Files:**
- [briarwood/agent/tools.py:1829-1858](briarwood/agent/tools.py#L1829-L1858) — `get_cma` body. Line 1832 calls `get_value_thesis(property_id, overrides=overrides)` to pick up `subject_ask` and `fair_value_base`.
- [briarwood/agent/tools.py:1773](briarwood/agent/tools.py#L1773) — `get_value_thesis` body. Internally calls `run_routed_report`, which spins up a fresh `run_briarwood_analysis_with_artifacts` execution plan and runs ~5 modules (`valuation`, `risk_model`, `confidence`, `legal_confidence`, `carry_cost`) again.
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — `handle_browse` (Cycle 3) keeps `get_cma` because it produces Engine B comps for the user-facing CMA card. The transitive `get_value_thesis` call is the only remaining per-tool routed run inside the consolidated BROWSE path.

**Step 1 resolved 2026-04-25** (between Cycles 4 and 5). `get_cma`
gains an optional keyword-only `thesis` parameter. When provided
(chat-tier callers), the internal `get_value_thesis` call is skipped
and `CMAResult` populates directly from the passed dict. `handle_browse`
builds the thesis dict from
`chat_tier_artifact["unified_output"]["value_position"]` plus the
`valuation` module's metrics via the new `_browse_thesis_from_artifact`
helper. Default behavior (`thesis=None`) is unchanged for
`handle_decision` / `handle_edge` callers, which still go through the
per-tool routed pattern until Cycle 5 rewires them.

**Step 2 still open.** The cache-miss audit on `valuation` across the
consolidated path vs. `get_value_thesis`'s routed path was deferred —
the leak is now zero on `handle_browse` (the consolidated path doesn't
trigger the duplicate), so the audit's value drops to "diagnostic
curiosity unless we re-enable per-tool routed runs for some reason."
Worth noting for whoever picks up the broader `MODULE_CACHE_FIELDS`
cleanup item.

#### 2026-04-25 — `in_active_context` is not safe under concurrent thread-pool callers `[size: S]` `[impact: Routing & Orchestration]`

**Severity:** Medium — blocks turning on parallel execution for the
chat-tier consolidated path. `run_chat_tier_analysis` (Cycle 2 of
OUTPUT_QUALITY_HANDOFF_PLAN.md) currently defaults `parallel=False`
because of this.

**Files:**
- [briarwood/agent/turn_manifest.py:332-336](briarwood/agent/turn_manifest.py#L332-L336) — `in_active_context`
- [briarwood/execution/executor.py:444](briarwood/execution/executor.py#L444) — call site `pool.map(in_active_context(_run_one), level)`

**Issue:** The decorator captures `ctx = contextvars.copy_context()`
once at decoration time, then `wrapped(*args)` does
`ctx.run(fn, *args)`. When the wrapped function is called from
`pool.map(wrapped, level)` and the pool runs multiple workers
concurrently, two workers attempt to enter the same `ctx` object and
the second one raises
`RuntimeError: cannot enter context: <Context> is already entered`. The
bug is not exercised by any current production caller because
`loop.run_in_executor(None, fn)` only fires one call per wrapper, and
the existing `_execute_plan_parallel` callers use it with single-module
dependency levels in their tests. The bug only fires when (a)
`parallel=True` and (b) the dependency DAG contains a level with two
or more independent modules — which is the case for every non-trivial
module set in `briarwood/execution/module_sets.py::ANSWER_TYPE_MODULE_SETS`.

**Suggested fix:** Capture the parent context's variables at decoration
time as a list of `(ContextVar, value)` pairs, then create a fresh
empty `contextvars.Context()` per call inside `wrapped`, set the
captured vars inside that fresh context, and run `fn` there. Sketch:

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

Add a regression test under `tests/agent/test_turn_manifest.py` that
decorates a single function and runs it concurrently from multiple
threads (or via `pool.map(wrapped, ['a', 'b', 'c'])`), asserts no
`RuntimeError`, and asserts the manifest ContextVar is visible inside
each worker.

**When this lands:** Flip `run_chat_tier_analysis(...)`'s `parallel`
default to `True` in [briarwood/orchestrator.py](briarwood/orchestrator.py)
and update the docstring + the Cycle 2 / Cycle 3 verification notes in
[OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md).
Cross-ref this entry from the plan.

#### 2026-04-24 — Extend router classification with telemetry-first `user_type` `[size: M]` `[impact: Routing & Orchestration]`

**Severity:** Medium — blocks user-type-conditioned orchestration,
Value Scout triggering, and tone adaptation.

**Files:**
- [briarwood/agent/router.py](briarwood/agent/router.py)
- [briarwood/agent/session.py](briarwood/agent/session.py)
- [briarwood/interactions/](briarwood/interactions/)
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py)
- [tests/agent/test_router.py](tests/agent/test_router.py)

**Issue:** `GAP_ANALYSIS.md` Layer 1 calls for intent plus user-type
classification, but `RouterDecision` only carries `answer_type`.
Existing interaction/persona hints accumulate separately and do not
feed routing or dispatch. A cold-start misclassification could shape
the session incorrectly if treated as authoritative too early.

**Suggested fix:** Add a conservative `user_type` field with values
chosen by product decision before implementation. Recommended first
pass: `unknown`/`pending` as the default plus low-confidence telemetry,
not hard routing behavior. Plumb the field through `RouterDecision`
and `Session`, collect examples, and only later let dispatch or Value
Scout branch on it.

#### 2026-04-24 — Prototype Layer 3 intent-satisfaction LLM in shadow mode `[size: M]` `[impact: LLM & Synthesis]`

**Severity:** Medium — current synthesis can produce grounded prose
while still failing to answer the user's actual intent.

**Files:**
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py)
- [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py)
- [briarwood/agent/composer.py](briarwood/agent/composer.py)
- [briarwood/routing_schema.py](briarwood/routing_schema.py)

**Issue:** The deterministic synthesizers assemble valid outputs, and
the composer verifies numbers, but nothing asks whether the module set
actually satisfied the routed intent. `GAP_ANALYSIS.md` Layer 3 names
the missing LLM step: read the intent contract plus module outputs,
then declare intent satisfied or identify missing facts/tools.

**Suggested fix:** Add a structured-output shadow evaluator that
returns `{intent_satisfied, missing_facts, suggested_tools, explanation}`
without changing user-visible behavior. Log results to the LLM ledger.
Do not let it trigger re-orchestration until the evaluator has golden
tests and retry bounds.

#### 2026-04-24 — Route local-intelligence extraction through shared LLM boundary `[size: S]` `[impact: LLM & Synthesis]`

**Severity:** Medium — the only LLM-backed extraction path sits outside
shared provider, budget, retry, and telemetry conventions.

**Files:**
- [briarwood/local_intelligence/adapters.py](briarwood/local_intelligence/adapters.py)
- [briarwood/local_intelligence/config.py](briarwood/local_intelligence/config.py)
- [briarwood/agent/llm.py](briarwood/agent/llm.py)
- [briarwood/cost_guard.py](briarwood/cost_guard.py)
- [TOOL_REGISTRY.md](TOOL_REGISTRY.md)

**Issue:** `OpenAILocalIntelligenceExtractor` uses a direct OpenAI
client and schema call. That gives it strong extraction structure, but
it bypasses the central `LLMClient` abstraction and does not share the
same provider routing, budget accounting, retry behavior, or call
ledger that router/composer/representation should use.

**Suggested fix:** Either adapt
`OpenAILocalIntelligenceExtractor` to accept/use the shared structured
`LLMClient`, or explicitly create a local-intelligence-specific LLM
adapter that still records cost/telemetry through the shared surfaces.
Keep the existing validation pipeline intact.

### Low

#### 2026-04-28 — Add optional `/admin` visibility for `model_alignment` rows `[size: S-M]` `[impact: Data, Persistence & Feedback]`

**Severity:** Low-medium — helpful owner visibility, but not required for
Stage 4 v1 because the CLI/JSON analyzer already reads persisted alignment
rows.

**Files:**
- [api/admin_metrics.py](api/admin_metrics.py) — compose a small alignment
  summary from `ConversationStore.model_alignment_rows`.
- [api/main.py](api/main.py) — optional `/api/admin/*` response extension.
- [web/src/app/admin/page.tsx](web/src/app/admin/page.tsx) — optional small
  section with underperforming module counts and example turn links.

**Issue:** Stage 4 deferred admin UI to keep the model-accuracy loop focused
on data correctness: outcome ingestion, `model_alignment`, receiver hooks,
and analyzer reporting. The owner can inspect alignment through
`python -m briarwood.feedback.model_alignment_analyzer`, but `/admin` does
not yet show the same summary.

**Suggested fix:** Add a compact read-only panel once real alignment rows
exist. Keep it to counts, miss rates, and top examples; do not redesign the
dashboard and do not fold in Phase 4c card work.

**Out of scope** until at least one real outcome file has been backfilled and
the analyzer has non-synthetic rows to display.

#### 2026-04-28 — Automate public-record outcome ingestion after Stage 4 manual loop `[size: M]` `[impact: Data, Persistence & Feedback]`

**Severity:** Low-medium — useful scale-up for the model-accuracy loop,
but not required to close Loop 1 in Stage 4 v1.

**Files (future anchors):**
- `data/outcomes/` — manual outcome files from Stage 4 v1.
- `briarwood/eval/outcomes.py` — planned Stage 4 outcome loader.
- `scripts/ingest_outcomes.py` — planned Stage 4 dry-run ingestion CLI.

**Issue:** Stage 4 v1 intentionally starts with manual CSV/JSONL outcome
files so the loop can close without mixing in public-record API decisions,
scraping reliability, source licensing, or address-match ambiguity. Once
the manual loop proves useful, outcome collection will become the
bottleneck.

**Suggested fix:** Add a separate public-record ingestion path that writes
the same outcome contract Stage 4 defines. It should keep source
provenance, source confidence, and row-level ambiguity reporting, and it
should feed the same `model_alignment` writer rather than inventing a
parallel store.

**Out of scope** for Stage 4 v1. Pick up only after the manual outcome
file, backfill, receiver hooks, and analyzer report are working.

#### 2026-04-26 — Pre-existing failure: `StructuredSynthesizerTests::test_interaction_trace_attached` `[size: S]` `[impact: Docs, Process & Repo Health]`

**Severity:** Low — broken test, no production impact. Surfaced (but
not caused) by CMA Phase 4a Cycle 5 synthesizer-prompt regression
sweep.

**Files:**
- [tests/synthesis/test_structured_synthesizer.py](tests/synthesis/test_structured_synthesizer.py) `StructuredSynthesizerTests::test_interaction_trace_attached` — line ~174 `self.assertEqual(result["interaction_trace"]["total_count"], 8)` fails with `AssertionError: 9 != 8`.

**Issue:** The deterministic structured synthesizer
(`briarwood/synthesis/structured.py::build_unified_output`) attaches an
`interaction_trace` summary to the unified output. The test fixture
pins `total_count == 8`, but the synthesizer is now reporting 9 — a
single record drift somewhere upstream of the trace builder. Confirmed
pre-existing on `main` by stashing the Cycle 5 changes and re-running —
same failure, same line, same `9 != 8`.

**Suggested fix:** Identify which interaction-trace record is being
added (likely a recent observability or telemetry hook recording one
extra synthesizer-side event). Either update the test fixture to
expect 9, or — if the new record is double-counting — fix the upstream
emitter so the count returns to 8. The other assertions in the test
(`"records" in result["interaction_trace"]`) all pass, so the trace
shape is intact; only the count is drifted.

#### 2026-04-26 — Pre-existing failure: `test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after` `[size: S]` `[impact: Docs, Process & Repo Health]`

**Severity:** Low — broken test, no production impact. Surfaced (but
not caused) by CMA Phase 4a Cycle 5 pipeline-adapter test edits.

**Files:**
- [tests/test_pipeline_adapter_contracts.py](tests/test_pipeline_adapter_contracts.py) `PipelineAdapterContractTests::test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after` — line ~748 `self.assertIn("value_opportunity", [...])` fails with `AssertionError: 'value_opportunity' not found in []`.

**Issue:** The test mocks `_load_or_create_session` and populates the
session with `last_town_summary`, `last_comps_preview`,
`last_value_thesis_view`, `last_market_support_view`, `last_strategy_view`,
`last_rent_outlook_view`, `last_projection_view`, etc. It then asserts
that chart events for `value_opportunity`, `cma_positioning`,
`scenario_fan`, `rent_burn` are emitted. After the 2026-04-25
OUTPUT_QUALITY Phase 2 work consolidated chat-tier execution onto a
single artifact (`_chat_tier_artifact_for(...)`) and rewired BROWSE
chart selection through the `_representation_charts(...)` path (which
calls `_unified_from_session(session)` — returns `None` when no unified
output is on the session), the chart-event list comes back empty for
this test because the mocked session has no `unified_output`
substrate. The companion test
`test_dispatch_stream_emits_browse_cards_when_browse_turn_uses_generic_adapter`
passes because it exercises a different code path that doesn't depend
on the unified output the same way.

Confirmed pre-existing on `main` by stashing the Cycle 5 changes and
re-running — same failure, same line.

**Suggested fix:** Extend the test setup to populate
`session.last_unified_output` (or whatever the current
`_unified_from_session` reads) with a minimal fixture so the chart
selection path produces events. The fixture only needs enough
structure to satisfy `UnifiedIntelligenceOutput.model_validate`;
downstream readers tolerate sparse fields.

#### ✅ 2026-04-25 — `presentation_advisor` bypasses the shared LLM observability ledger

**Status:** RESOLVED 2026-04-26 — Phase 2 Cycle 6 cleanup (item 1).

**Severity:** Low — same bug class as the existing
`local_intelligence/adapters.py` entry. Cleanup, not user-facing.

**Files:**
- [briarwood/agent/presentation_advisor.py](briarwood/agent/presentation_advisor.py) — `advise_visual_surfaces`
- [briarwood/agent/llm_observability.py](briarwood/agent/llm_observability.py) — `complete_structured_observed`

**Issue.** The 2026-04-25 audit's live trace showed
`get_property_presentation` taking ~3 seconds and emitting no LLM call
records to the per-turn manifest. The tool calls
`advise_visual_surfaces`, which uses the raw OpenAI client
(`llm.complete_structured(...)`) directly rather than going through the
observed wrapper.

**Resolved 2026-04-26** (Phase 2 Cycle 6 cleanup item 1).
`advise_visual_surfaces` at
[briarwood/agent/presentation_advisor.py:68](briarwood/agent/presentation_advisor.py#L68)
now routes through `complete_structured_observed(surface="presentation_advisor.advise", ...)`.
The call shows up in the shared LLM ledger and the per-turn manifest's
`llm_calls` list with `surface="presentation_advisor.advise"`. New
regression test
`tests/agent/test_presentation_advisor.py::PresentationAdvisorTests::test_advise_visual_surfaces_records_call_in_ledger`
pins the ledger contract. The `local_intelligence/adapters.py` sibling
entry remains open (see Medium tactical above).

#### 2026-04-24 — Broaden Representation Agent triggering beyond the claims flag `[size: M]` `[impact: Output & Presentation]`

**Severity:** Low — Layer 4 mostly exists, but only part of the app
benefits from it.

**Files:**
- [briarwood/representation/agent.py](briarwood/representation/agent.py)
- [api/pipeline_adapter.py](api/pipeline_adapter.py)
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py)
- [briarwood/feature_flags.py](briarwood/feature_flags.py)

**Issue:** `GAP_ANALYSIS.md` Layer 4 says the Representation Agent
substantially exists, but its use is still gated around the claim-object
path while legacy synthesis emits charts directly from handlers. That
means chart selection quality and LLM-vs-deterministic fallback
behavior differ by execution path.

**Suggested fix:** Add a feature-flagged path that runs the
Representation Agent for ordinary decision-tier turns after
`UnifiedIntelligenceOutput` and module views are available. Start in
shadow mode: compare selected charts to the currently emitted events,
log mismatches, and only switch rendering once chart coverage is
stable.

#### ✅ 2026-04-24 — Retire the ad-hoc `ComparableSalesModule()` graft in claims/pipeline.py `[size: S]`

**Status:** RESOLVED 2026-04-28 — CMA Phase 4a Cycle 6 (see [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md) Cycle 6 closeout).

**Severity:** Low — mechanical cleanup; no user-facing impact. Note:
this overlaps with Phase 4a Cycle 6 scope (§2). Kept here as a
tactical pointer; the in-handoff home for the fix is Phase 4a Cycle 6.

**Files:**
- [briarwood/claims/pipeline.py:62-114](briarwood/claims/pipeline.py#L62-L114) — the post-hoc graft. As of 2026-04-28, calls `run_comparable_sales(context)` and repackages `data.legacy_payload` as a `ComparableSalesOutput` pydantic instance under `outputs["comparable_sales"]["payload"]`.

**Issue:** Handoff 3 added a scoped `comparable_sales` runner at
[briarwood/modules/comparable_sales_scoped.py](briarwood/modules/comparable_sales_scoped.py)
and registered it in
[briarwood/execution/registry.py](briarwood/execution/registry.py). The
graft in `claims/pipeline.py` was no longer necessary in its prior form;
it could route through the scoped tool to pick up the canonical error
contract and planner integration.

**Resolution (2026-04-28):** Migrated. The graft now goes through
`run_comparable_sales(context)`. Field-name stability is preserved by
`module_payload_from_legacy_result` — `comps_used` lives at
`data.legacy_payload.comps_used` in the canonical shape; the graft
re-validates that into a `ComparableSalesOutput` so the synthesizer's
`payload.comps_used` access path stays stable. The shape-adapter pattern
remains because the orchestrator's routed run still does not surface
`comparable_sales` as a top-level entry in `module_results["outputs"]` —
full graft removal is queued under §4 High *Consolidate chat-tier
execution*. Tests rewired in `tests/claims/test_pipeline.py`; 82/82 claims
tests green.

#### 2026-04-24 — Strip unreachable defensive fallback in `_classification_user_type` `[size: S]` `[impact: Routing & Orchestration]`

**Severity:** Low — dead code, not a bug. Deferred to keep the
router-schema bug fix surgical.

**Files:**
- [briarwood/agent/router.py:283-284](briarwood/agent/router.py#L283-L284) — `persona = result.persona_type or PersonaType.UNKNOWN` and the analogous `use_case_type` line.

**Issue:** After the 2026-04-24 `RouterClassification` schema fix (see
DECISIONS.md same-dated entry), `persona_type` and `use_case_type` are
required on the Pydantic model with no default. If the LLM omits
either field, `schema.model_validate` raises `ValidationError` and
`complete_structured` returns `None` before
`_classification_user_type` is reached. The
`or PersonaType.UNKNOWN` / `or UseCaseType.UNKNOWN` defensive guards
in `_classification_user_type` can therefore never fire — a valid
`RouterClassification` always carries a real enum value. The dead
code was left in place to keep the bug-fix commit surgical, not
because it still serves a purpose.

**Suggested fix:** In a cleanup pass, reduce
`_classification_user_type` to:

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

Verify by re-running `tests/agent/test_router.py` (all 14 tests should
still pass).

### Absorbed into umbrellas

These tactical items were absorbed into umbrellas during the 2026-04-27
reorg. See §8 Dedup log for full mapping.

- 2026-04-24 — Editor / synthesis threshold duplication has no mechanical guard `[moved to §3.3.1]`
- 2026-04-24 — Add a shared LLM call ledger `[moved to §3.1 — AI-Native Stage 1]`
- 2026-04-24 — Two comp engines with divergent quality `[moved to §2 — Phase 4a Cycle 6]`
- 2026-04-26 — Live SSE rendering requires page reload `[moved to §3.4.4]`
- 2026-04-26 — `cma_positioning` chart-prose alignment `[moved to §3.4.3]`
- 2026-04-26 — `cma_positioning` "CHOSEN COMPS: Context only" chip + `feeds_fair_value` dead architecture `[moved to §3.4.1]`
- 2026-04-26 — `value_opportunity` chart y-axis label "Comp" vertical character stack `[moved to §3.4.2]`
- 2026-04-26 — `cma_positioning` source-view drift in non-BROWSE handlers `[moved to §3.4.5]`

---

## §5. Process & Meta

Cross-cutting "how-we-work" items. No size tags — these are ongoing
process concerns rather than build tasks.

### 2026-04-26 — `ARCHITECTURE_CURRENT.md` / `TOOL_REGISTRY.md` keep drifting (process question)

**Severity:** Low — process / architectural question, no functional
impact. Surfaced as a pattern observation 2026-04-26 high-level review.

**Files:**
- [ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md)
- [TOOL_REGISTRY.md](TOOL_REGISTRY.md)

**Issue:** Both audit docs have been "corrected" three separate times
now: Handoff 2a Piece 6 reconciled nine specific schema drifts
(DECISIONS.md 2026-04-24 entries); Cycle 4.2 found the
`base_comp_selector.py` / "15% sqft tolerance" drift (filed below);
Cycle 6 of Phase 4a is queued to update them again to reflect the
post-handoff topology. The pattern is consistent: code changes →
README is updated as part of the handoff → audit doc is forgotten and
rediscovered drifted on the next handoff.

This isn't a single bug. It's a question about whether these audit
docs should exist at all in their current form, or be retired in favor
of READMEs-only. The READMEs are the authoritative source per
CLAUDE.md priority order; the audit docs are explicitly *secondary*
per CLAUDE.md ("known to drift at the field-name level"). Yet they
keep being maintained, drift, and need to be re-reconciled.

**Suggested approach:** Three options to discuss with owner —
1. **Retire ARCHITECTURE_CURRENT.md / TOOL_REGISTRY.md.** Replace
   with a thin top-level index that links to each module's README. The
   handoff-by-handoff drift problem disappears because the audit
   content lives where the code does.
2. **Mechanically generate them from READMEs.** A script walks
   `briarwood/**/README*.md` at CI time and assembles ARCHITECTURE_CURRENT
   and TOOL_REGISTRY. The audit docs become a generated artifact, not
   an authored one — drift is impossible.
3. **Status quo + tighter ritual.** Make every PR that touches a
   module's README also touch the audit doc. CLAUDE.md already
   nominally requires this; the audit docs drift anyway.

Recommend (1) or (2). Status quo has been re-tried twice and produces
the same pattern.

### ✅ 2026-04-26 — `base_comp_selector.py` / "15% sqft tolerance" drift in audit docs

**Status:** RESOLVED 2026-04-28 — CMA Phase 4a Cycle 6 cleared the drift in [`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) (`:113`, `:166`, `:167`), [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) (`:233`), and [`CMA_SURFACE_MAP.md`](CMA_SURFACE_MAP.md) (`:20`, `:22`, `:25`) in the same pass as the audit-doc post-handoff-topology update.

**Severity:** Low — mechanical doc drift; no user-facing impact.
README is authoritative and now correct; the audit docs (priority #4)
need to follow.

**Files carrying the drift (resolved):**
- [TOOL_REGISTRY.md](TOOL_REGISTRY.md) `:113` ("15% tolerance"), `:166` ("Hardcoded: 15% sqft tolerance for comp matching"), `:167` ("Cross-town comps TODO flagged in base_comp_selector.py").
- [ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md) `:233` ("Cross-town comp TODO in `base_comp_selector.py`").
- [CMA_SURFACE_MAP.md](CMA_SURFACE_MAP.md) `:20`, `:25` — Cycle 1 audit snapshot; lower-priority reference doc, but worth correcting if the sweep happens.

**Issue:** Three audit docs share the drift cleared in
[briarwood/modules/README_comparable_sales.md](briarwood/modules/README_comparable_sales.md)
2026-04-26 (CMA Phase 4a Cycle 4 changelog entry). The cited file
`briarwood/agents/comparable_sales/base_comp_selector.py` does not
exist; the actual sqft logic at
[briarwood/agents/comparable_sales/agent.py:429-444](briarwood/agents/comparable_sales/agent.py#L429-L444)
is a sliding score penalty with rationale thresholds at 10% and 20%
(no hard tolerance band); the same-town filter is enforced at the
provider level
([briarwood/modules/comparable_sales.py:76-86](briarwood/modules/comparable_sales.py#L76-L86))
with no TODO comment.

**Resolution (2026-04-28):** Mechanical sweep applied — each cited reference
replaced with the corrected pointer per the README's canonical wording.
Estimated 10 minutes; actual ~10 minutes.

### 2026-04-24 — Decision sessions should grep-verify caller claims in real time

**Severity:** Medium — process fix, not a code bug. Prevents
amendments-during-execution of the kind seen twice in Handoff 4.

**Files (evidence):**
- [PROMOTION_PLAN.md](PROMOTION_PLAN.md) entry 15 ("Scope limit" paragraph about `_score_*` helpers having active callers)
- [PROMOTION_PLAN.md](PROMOTION_PLAN.md) entry 6 ("resale_scenario replaces bull_base_bear")
- [DECISIONS.md](DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 15 scope-limit paragraph corrected"
- [DECISIONS.md](DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 6 decision corrected"

**Issue:** Handoff 2b's conversational decision session produced a plan
that holds up on most entries but had two factual caller-premises turn
out to be wrong during Handoff 4 execution:

1. **Entry 15 (`calculate_final_score` → DEPRECATE, scope-limit
   paragraph):** claimed `_score_*` helpers had active callers and
   should be preserved. Grep during H4-#2 execution found zero
   non-aggregator, non-test callers — the entire chain was dead code.
2. **Entry 6 (`bull_base_bear` → DEPRECATE):** claimed `resale_scenario`
   replaces `bull_base_bear`. Grep during H4-#3 execution found
   `resale_scenario_scoped.py:30` invokes `BullBaseBearModule().run()`
   as the core of its implementation — the scoped wrapper *composes*
   `bull_base_bear`, it does not replace it. Correct classification is
   KEEP-as-internal-helper.

Both amendments were required mid-execution. The pattern is specific:
"plan claims X has/lacks callers → grep contradicts the claim." The
failure mode is decision-by-reading versus decision-by-verification.

**Suggested fix:** Future PROMOTION_PLAN-style decision sessions (or
any handoff that classifies modules as DEPRECATE, KEEP-as-helper,
PROMOTE based on caller topology) should systematically run
grep-verification of caller claims *during the session*, not defer
that verification to the execution handoff. Concretely: for each
classification that hinges on "X has no active callers" or "X replaces
Y" or "X is consumed only by Z," run a grep across `briarwood/`,
`tests/`, `api/`, and `eval/` for the claimed relationship and attach
the grep output (or a summary of it) to the plan entry as evidence.
This surfaces false premises while the classification is still open
for discussion, rather than forcing mid-execution amendments.

This is not a criticism of Handoff 2b's specific judgment calls —
those calls were mostly right and the two that weren't were judgment
against the best information available at the time. The lesson is
that decision-by-reading has a specific blind spot (callers the
reader doesn't know about or forgets to check), and the fix is
mechanical verification rather than more careful reading.

---

## §6. Parking Lot

No items currently parked outside §3.5 (Phase 4c BROWSE rebuild).
Section header preserved so the convention is established for future
deferrals.

---

## §7. Suggestions for Next Planning Session

Items proposed during the 2026-04-27 reorg but not yet roadmap items.
Each one needs a separate planning session to be promoted into the
main structure.

### Define the prong taxonomy

**Resolution 2026-04-28:** Use product subsystem impact labels instead of the earlier undefined Foundation / Scout / Capital / Realty / Cross-cutting prong set. The canonical labels are defined near the top of this file and applied in the companion no-drop index, [ROADMAP_TRIAGE.md](ROADMAP_TRIAGE.md). Items that cannot be classified confidently must be parked under `Unclassified / Needs Owner Decision` rather than forced into a bucket.

The 2026-04-27 reorg prompt referenced a prong taxonomy (Foundation /
Scout / Capital / Realty / Cross-cutting) for tagging tactical items.
That taxonomy is not defined in any project doc (verified: not in
`CLAUDE.md`, `design_doc.md`, `DECISIONS.md`, prior `ROADMAP.md`).
Without a definition, prong tags would collapse to unknown placeholders
for every item and add no value.

**Prior action:** Define what each prong means as a one-line scope, then
add tags to §4 tactical items. **Resolved by this pass:** use the product
subsystem impact labels defined above instead of prong tags.

### Resolve sizing gaps

Items currently marked `[size: ?]` (see §9 for the full list) need
size estimates assigned. Most can be sourced from the corresponding
handoff plan once that plan is read carefully.

### Phase 2 status discrepancy

`OUTPUT_QUALITY_HANDOFF_PLAN.md:376` says "Phase 2 outcome — DONE
2026-04-25." The §2 Closing Out entry above lists Cycle 6 cleanup as
remaining (~1-2 hrs of items). Both are technically correct: the
architectural fix is done, but tail cleanup remains. A future pass
might rename Cycle 6 from "cleanup" to "tail items" and close Phase 2
formally so the inconsistency is resolved.

---

## §8. Dedup log

Items merged from one location into another during the 2026-04-27
reorg. Each row shows the surviving canonical location and the
absorbed source phrasing.

| # | Surviving (canonical location) | Absorbed phrasing |
|---|---|---|
| 1 | §3.1 AI-Native Stage 1 (`LLMCallLedger`) | 2026-04-24 tactical "Add a shared LLM call ledger" |
| 2 | §3.3.1 Semantic Audit (CRITICAL pricing-view) | 2026-04-24 tactical "Editor / synthesis threshold duplication has no mechanical guard" (corroborated by §4.2) |
| 3 | §2 Phase 4a Cycle 6 | 2026-04-24 tactical "Two comp engines with divergent quality; CMA (Engine B) needs alpha-quality pass" (Phase 4a is the in-flight handoff for this) |
| 4 | §3.4.4 Chart umbrella — Live SSE rendering | 2026-04-26 Medium tactical "Live SSE rendering requires a page reload to display correctly" |
| 5 | §3.4.3 Chart umbrella — chart-prose alignment | 2026-04-26 Low tactical "`cma_positioning` chart-prose alignment: synthesizer can cite comps not visible in the chart" |
| 6 | §3.4.1 Chart umbrella — Context only chip + feeds_fair_value | 2026-04-26 Low tactical "`cma_positioning` 'CHOSEN COMPS: Context only' chip is stale post-Cycle-3 (and `feeds_fair_value` is dead architecture)" |
| 7 | §3.4.2 Chart umbrella — y-axis vertical | 2026-04-26 Low tactical "`value_opportunity` chart y-axis label 'Comp' renders as a vertical character stack" |
| 8 | §3.4.5 Chart umbrella — source-view drift | 2026-04-26 Medium tactical "`cma_positioning` source-view drift in non-BROWSE handlers" |

**Pre-reorg item count:** 45 (`grep -c "^## "` on prior ROADMAP.md).
**Post-reorg item count:** 37 (45 minus 8 dedups).

Note on items NOT deduped despite cross-references:
- "Retire ad-hoc `ComparableSalesModule()` graft" (§4 Low) overlaps
  with Phase 4a Cycle 6 (§2). Kept as tactical pointer because the
  Cycle 6 entry already references it; doing so makes the dependency
  visible without losing the standalone filing.
- "MODULE_CACHE_FIELDS leaky" (§4 Medium) is annotated "likely moot
  post-consolidation" but kept in §4 because the consolidation work is
  itself in §4 High (not an umbrella).
- "presentation_advisor bypasses observability ledger" is kept in §4
  Low with its RESOLVED-2026-04-26 marker preserved (not a dedup; the
  entry tracks resolution).

---

## §9. Sizing gaps to resolve

Items where the source doc didn't state an effort estimate and the
2026-04-27 reorg marked `[size: ?]`. Resolve in the next planning
session.

- ~~**Phase 4a Cycle 6** (§2) — `CMA_HANDOFF_PLAN.md:321-326` describes
  scope but no numeric estimate. Likely S-M.~~ Resolved: actual ~2 hrs
  (S). Cycle 6 closed 2026-04-28 — see §10 Resolved Index.
- **Phase 3 Open Design Decision #7** (§2) — decision-only, no size
  applies until a Cycle E is scoped (assuming option 7c is chosen).

No tactical items in §4 currently have `[size: ?]` — every tactical
entry was sized from its source doc or by analogy to similar items.

---

## §10. Resolved Index

Scan-friendly view of every resolved entry across this file. New rows
land here as items close — corresponding entries are NOT moved or
deleted from their original section; they are marked with `✅` in the
heading and a `**Status:** RESOLVED YYYY-MM-DD — …` line in the rubric.

| # | Date | Item | Closed in | Originally filed in |
|---|------|------|-----------|---------------------|
| 1 | 2026-04-26 | `presentation_advisor` bypasses the shared LLM observability ledger | Phase 2 Cycle 6 cleanup item 1 | §4 Low |
| 2 | 2026-04-28 | Retire the ad-hoc `ComparableSalesModule()` graft in claims/pipeline.py | CMA Phase 4a Cycle 6 (see [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md)) | §4 Low |
| 3 | 2026-04-28 | `base_comp_selector.py` / "15% sqft tolerance" drift in audit docs | CMA Phase 4a Cycle 6 (audit-doc reconciliation pass) | §5 Process & Meta |
| 4 | 2026-04-28 | Phase 4a — CMA Quality | Cycle 6 closeout — graft retired, audit docs reconciled, all 14 Cycle 1 surfaces verified canonical | §2 Closing Out |
| 5 | 2026-04-28 | Sequence step 1 — Phase 4a Cycle 6 — close the CMA handoff | Cycle 6 closeout (step 2 — AI-Native Stage 1 — now unblocked) | §1 The Sequence |
| 6 | 2026-04-28 | AI-Native Foundation Stage 1 — Persist Every Action | [PERSISTENCE_HANDOFF_PLAN.md](PERSISTENCE_HANDOFF_PLAN.md) Cycles 1-4 — `turn_traces`, `data/llm_calls.jsonl`, `messages` metric columns all live | §3.1 Strategic Initiatives |
| 7 | 2026-04-28 | Sequence step 2 — AI-Native Foundation Stage 1 — persistence | Stage 1 closeout (step 3 — Stages 2-3 — now unblocked) | §1 The Sequence |
| 8 | 2026-04-28 | 2026-04-24 — Add a shared LLM call ledger (absorbed into Stage 1) | Stage 1 closeout — JSONL sink in `LLMCallLedger.append` lands the durable mirror | §3.1 / §8 Dedup log row 1 |
| 9 | 2026-04-28 | 2026-04-25 — Audit router classification boundaries with real traffic | [ROUTER_AUDIT_HANDOFF_PLAN.md](ROUTER_AUDIT_HANDOFF_PLAN.md) Cycles 1-4 — STRATEGY/EDGE/SEARCH bucket expansion + `_COMP_SET_RE` widening; 14 new tests | §4 Medium |
| 10 | 2026-04-28 | Router LLM `confidence=0.6` cap collapses classifier signal | [ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md](ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md) Cycle 1 — schema + prompt + plumbing; LLM confidence flows through with 0.4 floor | §4 Medium |
| 11 | 2026-04-28 | `parse_overrides` bare-renovation false-positive shoehorns scenario requests into DECISION | [ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md](ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md) Cycle 2 — router `has_override` tightened to require material override; `_PROJECTION_OVERRIDE_HINT_RE` widened | §4 Medium |
| 12 | 2026-04-28 | AI-Native Foundation Stage 2 — Close The User-Feedback Loop | [FEEDBACK_LOOP_HANDOFF_PLAN.md](FEEDBACK_LOOP_HANDOFF_PLAN.md) Cycles 1-4 — `feedback` table + `POST /api/feedback` + thumbs UI + closed-loop synthesis hint with manifest-note audit tag | §3.1 Strategic Initiatives |
| 13 | 2026-04-28 | Sequence step 3a — AI-Native Foundation Stage 2 — feedback loop | Stage 2 closeout (step 3 split into 3a/3b; 3b — Stage 3 dashboard — remains open) | §1 The Sequence |
| 14 | 2026-04-28 | AI-Native Foundation Stage 3 — Business-Facing Dashboard | [DASHBOARD_HANDOFF_PLAN.md](DASHBOARD_HANDOFF_PLAN.md) Cycles 1-4 — `/api/admin/*` endpoints + `/admin` SSR pages + per-turn drill-down with feedback-loop tag highlighting | §3.1 Strategic Initiatives |
| 15 | 2026-04-28 | Sequence step 3b — AI-Native Foundation Stage 3 — dashboard | Stage 3 closeout. With 3a + 3b both closed, sequence step 4 (Phase 4b Scout) is now unblocked | §1 The Sequence |
| 16 | 2026-04-28 | Phase 4b — Scout buildout | [SCOUT_HANDOFF_PLAN.md](SCOUT_HANDOFF_PLAN.md) Cycles 1-7 — LLM Scout, ScoutFinds, shared dispatcher, deterministic rails, telemetry, and closeout docs | §3.2 Strategic Initiatives |
| 17 | 2026-04-28 | Sequence step 4 — Phase 4b Scout | Scout closeout (step 5 — AI-Native Foundation Stage 4 — now unblocked) | §1 The Sequence |
| 18 | 2026-04-28 | `docs/current_docs_index.md` missing authoritative orientation docs | Docs index convergence pass — added DECISIONS, ROADMAP, ARCHITECTURE_CURRENT, GAP_ANALYSIS, TOOL_REGISTRY, and complete handoff plans | §4 Medium |

**Convention.** When an entry closes:
1. Add `✅` prefix to its section heading.
2. Add `**Status:** RESOLVED YYYY-MM-DD — <where it closed>` as the first line of the entry's rubric (above `**Severity:**` if present).
3. Keep all original framing (Issue, Files, Suggested fix) intact for archaeology — append a `**Resolution:**` paragraph rather than rewriting the body.
4. Add a row to the table above with `[date]`, `[item]`, `[where closed]`, and `[originally filed in]`.

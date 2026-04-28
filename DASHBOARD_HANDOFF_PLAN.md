# AI-Native Foundation Stage 3 — Business-Facing Dashboard

**Status:** ✅ RESOLVED 2026-04-28 — Cycles 1-4 all landed. The
read-side admin surface (`/admin` + `/admin/turn/[turn_id]`) is live
behind `BRIARWOOD_ADMIN_ENABLED=1`; SQL + JSONL aggregators back it.
The Stage 2 closure-loop tag
(`feedback:recent-thumbs-down-influenced-synthesis`) renders
highlighted in the per-turn drill-down. See
[`DECISIONS.md`](DECISIONS.md) 2026-04-28 entry "AI-Native Foundation
Stage 3 landed" for closeout notes.
**Size:** M-L (~115–165 min LLM time across 4 cycles + closeout).
**Sequence position:** Step 3b of [`ROADMAP.md`](ROADMAP.md) §1. Stages 1
and 2 closed 2026-04-28; this is the read-side companion to the
write-side substrate they put in place.

**Principle.** "Every action is an artifact" — [`design_doc.md`](design_doc.md)
§ 3.4. The artifacts Stage 1 + Stage 2 persisted (`turn_traces`,
`data/llm_calls.jsonl`, `feedback`) are useless without a surface
where the owner can read them.

**Why now.**
- Substrate is fully live: `turn_traces` carrying per-turn
  attribution + duration, `data/llm_calls.jsonl` carrying per-call
  cost + token + duration, `feedback` carrying rating per
  message_id. All three populate by default with no env-var gating.
- Phase 4b Scout depends on a measurement surface where Scout's own
  outputs can be evaluated. Without Stage 3, every Scout iteration
  produces signal that lands in SQLite + JSONL but has no
  read-access pattern beyond raw `sqlite3` shell.
- Owner-facing payoff: the success criteria from ROADMAP §3.1 Stage
  3 — *"answer 'what was the slowest turn this week and why?' in
  under 30 seconds without grepping logs"* — is what this stage
  ships.

**Cross-references.**
- [`ROADMAP.md`](ROADMAP.md) §3.1 Stage 3 (this handoff), §1
  sequence step 3b, §3.4.7 (chart library upgrade — out of scope
  here, will be felt later).
- [`design_doc.md`](design_doc.md) § 3.4 (principles), § 7 (the
  feedback loops Stage 3 makes visible).
- [`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md) — the
  Stage 1 plan that wrote `turn_traces` and `llm_calls.jsonl`.
- [`FEEDBACK_LOOP_HANDOFF_PLAN.md`](FEEDBACK_LOOP_HANDOFF_PLAN.md) —
  the Stage 2 plan that wrote `feedback` and the
  `feedback:recent-thumbs-down-influenced-synthesis` manifest tag.

---

## Scope at a glance

Three independent, sequenceable pieces plus a closeout:

1. **Admin endpoints in FastAPI.** `GET /api/admin/metrics` (top-line
   weekly aggregates), `GET /api/admin/turns/recent` (top-10 slowest
   and top-10 highest-cost), `GET /api/admin/turns/{turn_id}` (full
   per-turn detail). Reads from SQLite + the JSONL hopper. No auth
   in v1; gated behind an `BRIARWOOD_ADMIN_ENABLED` env var so a
   misconfigured public-facing FastAPI cannot accidentally serve
   admin data.
2. **`/admin` route in Next** (`web/src/app/admin/page.tsx`). Server
   component reading the metrics endpoints and rendering the
   top-line dashboard. Simple HTML/CSS charts (no chart library —
   §3.4.7 evaluates that separately and shouldn't block this stage).
3. **Per-turn drill-down** at `web/src/app/admin/turn/[turn_id]/page.tsx`.
   Renders the full `TurnManifest` JSON, joins feedback for any
   message in the turn, lists LLM calls with surface + cost + duration.
4. **Closeout.** ROADMAP closures, DECISIONS entry, README discipline
   check, ARCHITECTURE_CURRENT update.

All three pieces are additive. No existing schema or contract is
rewritten.

---

## Out of scope (deliberate)

- **Auth / multi-user scoping.** Single-user local product.
  `BRIARWOOD_ADMIN_ENABLED=1` env-gate is the only access control;
  v2 can layer a real auth pass when multi-user is in scope.
- **Alerting.** No thresholds, no notifications. Visual inspection
  only.
- **Time-series charts beyond simple weekly aggregates.** No daily
  rollups, no sparkline trends, no `cma_positioning`-style polish.
  Bar-width-via-CSS is the rendering model.
- **Cost forecasting / budget tracking.** Different problem from
  cost observability. Stage 4-or-beyond.
- **Real-time updates.** SSR with `cache: "no-store"` is the model;
  the user refreshes the page to refresh metrics.
- **Cross-conversation aggregations beyond the listed metrics.** If
  a question requires a SQL we didn't pre-compute, the answer for
  v1 is "open `sqlite3` and ask it." The dashboard is not a SQL UI.
- **Persisted cost data in SQLite.** Cost lives in
  `data/llm_calls.jsonl` today. v1 reads + parses on every metrics
  request. If file size becomes a bottleneck, the v2 path is to
  fold cost into a new SQLite table — that's a Stage-3.5 conversation,
  not Stage 3.
- **Adding charting library.** §3.4.7 owns that evaluation. Plain
  HTML/CSS bars are sufficient for v1 weekly aggregates.

---

## Current state — what exists today

Read-only inventory before any changes.

### Persisted artifacts (Stage 1 + 2)

- `turn_traces` table: `turn_id` (PK), `conversation_id`, `started_at`
  (epoch s), `duration_ms_total`, `answer_type`, `confidence`,
  `classification_reason`, `dispatch`, `user_text`, plus JSON columns
  `wedge`, `modules_run`, `modules_skipped`, `llm_calls_summary`,
  `tool_calls`, `notes`. Indexes on `(conversation_id, started_at)`
  and `(started_at)`. See [api/store.py](api/store.py) `_init_schema`.
- `messages` table with metric columns `latency_ms`, `answer_type`,
  `success_flag`, `turn_trace_id`. See
  [api/store.py:93-104](api/store.py#L93-L104).
- `feedback` table: `message_id` (PK), `conversation_id`,
  `turn_trace_id`, `rating`, `comment`, `created_at`, `updated_at`.
- `data/llm_calls.jsonl`: one JSON line per call with
  `surface`, `provider`, `model`, `prompt_hash`, `response_hash`,
  `status`, `attempts`, `duration_ms`, `cache_hit`, `error_type`,
  `input_tokens`, `output_tokens`, `cost_usd`, plus a `recorded_at`
  ISO timestamp added at write time. Path overridable via
  `BRIARWOOD_LLM_JSONL_PATH`. See
  [briarwood/agent/llm_observability.py](briarwood/agent/llm_observability.py).

### What's NOT persisted yet

- Per-call linkage from `data/llm_calls.jsonl` back to a specific
  `turn_id`. The JSONL records carry `surface` and timestamps, but
  joining a call back to its turn requires either timestamp-window
  join (fragile) or a future schema additon. v1 dashboard sidesteps
  by aggregating cost without joining: "total cost in last 7 days
  by surface" is computable from the JSONL alone; per-turn cost in
  the drill-down comes from `turn_traces.llm_calls_summary` (which
  the manifest carries).

### Existing FastAPI admin surface

- None. There is no `/api/admin/*` namespace today. Stage 3 adds it.

### Existing Next admin surface

- None. No `web/src/app/admin/` exists.

---

## The pieces — cycle-by-cycle

### Cycle 1 — Admin endpoints in FastAPI (~30–45 min)

**Status:** Not started.

**Scope.**

1. New SQL helpers on `ConversationStore` in
   [api/store.py](api/store.py):
   - `weekly_latency_by_answer_type(since_ms)` → `[{answer_type,
     count, avg_ms, p50_ms, p95_ms}]`
   - `weekly_thumbs_ratio(since_ms)` → `{up: N, down: N, total: N,
     ratio: float | None}`
   - `top_slowest_turns(since_ms, limit=10)` → list of trace rows
     with key columns
   - `recent_turn(turn_id)` → full row (already mostly available
     via existing methods; might need a wrapper)
   - `feedback_for_turn(turn_id)` → ratings on any message in the
     turn (LEFT JOIN `messages` ↔ `feedback` keyed on
     `messages.turn_trace_id`)

2. JSONL aggregator in a new module
   `briarwood/agent/llm_observability_query.py` (or as a sibling
   helper in `api/`):
   - `weekly_cost_by_surface(jsonl_path, since_iso)` →
     `[{surface, count, total_cost_usd, avg_duration_ms}]`
   - `top_costliest_turns_via_jsonl(...)` — note: cannot be done
     without `turn_id` linkage, so this metric uses a different
     proxy: top calls (not turns) by `cost_usd`.

   Actual top-10 *highest-cost turns* uses
   `turn_traces.llm_calls_summary` JSON: parse the JSON column and
   sum `cost_usd` per turn, then ORDER BY total DESC LIMIT 10.

3. New FastAPI endpoints in [api/main.py](api/main.py):
   ```python
   @app.get("/api/admin/metrics")
   def admin_metrics(days: int = 7) -> dict[str, Any]: ...

   @app.get("/api/admin/turns/recent")
   def admin_recent_turns(days: int = 7, limit: int = 10) -> dict[str, Any]: ...

   @app.get("/api/admin/turns/{turn_id}")
   def admin_turn_detail(turn_id: str) -> dict[str, Any]: ...
   ```
   Each gated at the top with:
   ```python
   if os.environ.get("BRIARWOOD_ADMIN_ENABLED") != "1":
       raise HTTPException(status_code=404, detail="not found")
   ```
   (404 not 403 so a probe of a non-admin host doesn't reveal
   the surface exists.)

**Tests** (new `tests/test_api_admin.py`):
- Store-level: round-trip the new SQL helpers against a seeded DB
  (4-5 tests).
- Endpoint-level: 404 when env not set; 200 + correct shape when
  env=1; turn-detail 404 for unknown id (3 tests).

**Verification.** `curl localhost:8000/api/admin/metrics?days=7`
returns JSON with the three top-level keys; `BRIARWOOD_ADMIN_ENABLED=1`
required.

**Risk.** Low. All additive; no existing surface touched.

---

### Cycle 2 — `/admin` top-line page (~45–60 min)

**Status:** Not started.

**Pre-flight.** Per [`web/AGENTS.md`](web/AGENTS.md): re-read the
relevant Next.js guides under `web/node_modules/next/dist/docs/`.
Stage 2 covered route-handlers; Stage 3 needs server components for
the dashboard page. Targets: `app/getting-started/server-and-client-components`,
`app/data-fetching` (server-side fetch from FastAPI).

**Scope.**

1. New server component at `web/src/app/admin/page.tsx`:
   - Fetches `/api/admin/metrics` and `/api/admin/turns/recent`
     server-side (via `cache: "no-store"`).
   - Renders four sections:
     - **Latency by answer_type** — table of (answer_type, count,
       avg, p50, p95) with bar-width visualizations using
       `style={{ width: \`${pct}%\` }}` divs. No chart library.
     - **LLM cost by surface** — same pattern, table + width bars,
       last 7 days.
     - **Thumbs ratio** — three big stat cards (👍 N, 👎 N, ratio %).
     - **Top-10 slowest** — table with link to drill-down.
     - **Top-10 highest-cost** — same.
   - Uses existing app design tokens (`--color-text`,
     `--color-text-faint`, `--color-surface`, etc.) so the visual
     language matches the chat surface.

2. `web/src/lib/admin-api.ts` — server-side fetch helpers (mirror
   `web/src/lib/api.ts` pattern). One function per endpoint, typed
   responses.

3. Optional `?days=N` query string honored on the page; defaults
   to 7. (Reads `searchParams` per the Next.js page contract.)

4. Empty-state handling: when the database has fewer than N turns
   to populate a metric, render "Not enough data yet — keep
   chatting" instead of an empty chart.

**Tests.** No client-side test harness in `web/` today. Server-side
tests cover the data path (Cycle 1's tests). Cycle 2 ships with a
manual verification gate.

**Verification (manual; deferred to user).**
- `BRIARWOOD_ADMIN_ENABLED=1` set on the FastAPI process.
- `cd web && npm run dev` → visit `http://localhost:3000/admin`.
- Confirm: latency table populated, cost table populated, thumbs
  ratio matches `SELECT rating, COUNT(*) FROM feedback`, top-10
  links navigate to the drill-down route (Cycle 3).
- Without `BRIARWOOD_ADMIN_ENABLED=1`, the page should error
  cleanly (the FastAPI returns 404; the server component should
  render an "admin disabled" notice rather than a broken page).

**Risk.** Medium. Web work is the highest-friction part — Next
server components with `searchParams` + typed fetch + design-token
visual is more layout work than the FeedbackBar.

---

### Cycle 3 — Per-turn drill-down (~30–45 min)

**Status:** Not started.

**Scope.**

1. New dynamic route at
   `web/src/app/admin/turn/[turn_id]/page.tsx`:
   - Fetches `/api/admin/turns/{turn_id}` server-side.
   - Renders sections:
     - **Header** — turn_id, conversation_id (link to `/c/[id]`),
       `started_at` (formatted), `answer_type`, `confidence`,
       `dispatch`, `duration_ms_total`.
     - **User text** — the prompt that triggered the turn.
     - **Modules run** — table of (name, source, mode, confidence,
       duration_ms, warnings_count) from
       `turn_traces.modules_run`.
     - **LLM calls** — table from `turn_traces.llm_calls_summary`
       (surface, status, attempts, duration_ms, input_tokens,
       output_tokens, cost_usd). Sum row at the bottom for total
       cost + total duration.
     - **Notes** — render `turn_traces.notes` as a list. Highlight
       any line containing the
       `feedback:recent-thumbs-down-influenced-synthesis` tag —
       this is the closure-loop audit affordance from Stage 2.
     - **Feedback** — any rating on the assistant message in this
       turn (joined via `messages.turn_trace_id`).
     - **Raw JSON** — collapsible `<details>` block with the
       full manifest pretty-printed for debugging.

2. Routing: link from the top-10 tables in Cycle 2's page to
   `/admin/turn/{turn_id}`. Link the conversation_id badge to
   `/c/{conversation_id}` so the owner can jump from "this turn
   was slow" → "let me see how the user phrased the follow-up."

**Tests.** Backend tests in Cycle 1 cover the data shape. UI
manual verification.

**Verification.**
- Click a row from `/admin` → drill-down loads.
- Notes section shows the manifest tag for any turn that received
  the synthesis hint after a thumbs-down.

**Risk.** Low–Medium. Largely table rendering; no novel patterns.

---

### Cycle 4 — Closeout (~10–15 min)

**Status:** Not started.

**Scope.**
- Smoke matrix (deferred to user — auto-mode):
  - Empty DB → `/admin` renders empty-state notices.
  - Populated DB → all five sections show real data.
  - Click drill-down → per-turn detail loads.
  - Without `BRIARWOOD_ADMIN_ENABLED=1` → `/admin` shows the
    disabled notice instead of crashing.
- README discipline check: no in-scope module has a README. Confirm
  no in-scope drift.
- `ARCHITECTURE_CURRENT.md` update: extend §"Persistence" with the
  read-side surface (this is the third sub-section after Stage 1
  and Stage 2's add). Note the `BRIARWOOD_ADMIN_ENABLED` gate.
- ROADMAP closures (per the convention):
  - §3.1 Stage 3 → ✅ + `**Status:**` line.
  - §1 sequence step 3b → ✅. With 3a + 3b both closed, the
    AI-Native Foundation umbrella's first phase is complete; the
    sequence's step 4 (Phase 4b Scout) is now unblocked.
  - §10 Resolved Index rows for Stage 3 + sequence step 3b.
- DECISIONS.md entry summarizing what landed + plan deviations +
  Guardrail Review (per `project_llm_guardrails.md`). Walk the
  admin path for any guardrails that block legitimate signal.

**Tests:** existing tests stay green. Cycle 1's tests are the
regression net.

**Risk.** Low.

---

## Open design decisions

(Resolve at start of named cycle.)

1. **Charting library v1.** Cycle 2. **Resolved 2026-04-28** (owner
   sign-off): plain HTML/CSS bars for the dashboard. The chart-library
   evaluation is bound to the UI reconstruction handoff (Phase 4c §3.5
   / ROADMAP §3.4.7 sequencing note), not done piecemeal across
   surfaces. Stage 3's dashboard is deliberately a small visual
   surface so the §3.4.7 evaluation, when it runs, has a clean canvas
   under real BROWSE-rebuild layout pressure rather than a half-mixed
   chart stack to inherit.

2. **Auth gate.** Cycle 1.
   - **(a) `BRIARWOOD_ADMIN_ENABLED` env var, 404 when not set.**
     **Recommended** — minimum viable obscurity; doesn't reveal the
     surface exists; trivial to disable.
   - (b) No gate at all. Single-user local product. Slightly less
     defensive.
   - (c) Real auth (basic auth, session). Out of scope per ROADMAP
     but the env-var gate is a good placeholder for it.

3. **JSONL parse on every metrics request.** Cycle 1.
   - **(a) Parse the whole file on each request.** Today's file is
     a few thousand lines; parse is sub-100ms. **Recommended** —
     no schema migration, no double-write, easy to reason about.
   - (b) Add a SQLite cost table; `LLMCallLedger.append` writes
     to both. Bigger change; correct posture if file grows past
     a few hundred MB. Defer.

4. **Top-10 highest-cost turns — sourced from `turn_traces.llm_calls_summary`.**
   Cycle 1. The summary JSON contains per-call cost; sum and rank
   by SUM(cost_usd) per turn. Confirm at Cycle 1 start that
   `LLMCallSummary` carries `cost_usd` (it does — see
   [briarwood/agent/turn_manifest.py LLMCallSummary](briarwood/agent/turn_manifest.py)).

5. **Date-range default + UI knob.** Cycle 2.
   - **(a) `?days=7` query string, default 7.** **Recommended** —
     simple, works for the spec.
   - (b) UI control to toggle 1d / 7d / 30d. Cosmetic addition.

6. **Drill-down link target for conversation_id.** Cycle 3.
   - **(a) Link to `/c/[conversation_id]`.** **Recommended** — the
     owner can see the full chat from there, including downstream
     turns.
   - (b) Render the conversation_id as text only.

7. **Empty-state behavior.** Cycle 2.
   - **(a) Render the section with "Not enough data yet" notice.**
     **Recommended** — communicates the surface exists.
   - (b) Hide empty sections entirely. Confusing.

8. **Should the admin route be linked from the main UI?** Cycle 2.
   - **(a) No.** Discoverable only by URL. **Recommended** for v1 —
     keeps it out of the main user-facing surface; aligns with the
     "no auth in v1" posture.
   - (b) Yes (e.g., a small sidebar link). Means anyone with
     access to the chat product can hit `/admin`. Bad fit for v1.

---

## Cycle ordering rationale

- **Cycle 1 first** — backend SQL helpers + endpoints. Substrate
  Cycles 2 + 3 consume.
- **Cycle 2 second** — main metrics page. Pulls Cycle 1's data via
  the new endpoints.
- **Cycle 3 third** — drill-down. Has its own endpoint already in
  place from Cycle 1.
- **Cycle 4 last** — closeout.

If the AGENTS.md gate or web work blocks Cycle 2, the data path is
still verifiable via `curl` against Cycle 1's endpoints; Cycle 3's
drill-down can also be hand-tested via curl. The dashboard is the
visible payoff but not the only proof of closure.

---

## Failure semantics

- All admin endpoints are **read-only.** Cannot break a turn.
- A misbehaving JSONL parse (corrupt line) skips the line and
  continues — never raises through to the endpoint response.
  Mirror Stage 1's exception-swallow discipline.
- The Cycle 2 server component renders an explicit error state if
  the FastAPI fetch fails, rather than crashing the page.

---

## Tests

**Existing tests must stay green.** Pre-handoff baseline: 16
pre-existing failures, 1559 passed (post-Stage-2). Stage 3 adds
~10 new tests in `tests/test_api_admin.py`.

**Manual verification gates** (deferred to user; auto-mode does
not drive a browser):
- After Cycle 1: curl all three endpoints with and without
  `BRIARWOOD_ADMIN_ENABLED=1`.
- After Cycle 2: visit `/admin` in a real browser; confirm five
  sections.
- After Cycle 3: drill into a slowest-turn row; confirm full
  manifest renders.

---

## ROADMAP closures (anticipated)

- §3.1 Stage 3 → RESOLVED on landing (Cycle 4).
- §1 sequence step 3b → RESOLVED on landing.
- With 3a + 3b both closed, the AI-Native Foundation umbrella's
  first phase is complete; sequence step 4 (Phase 4b Scout) is now
  unblocked.
- §10 Resolved Index — 2 rows.

---

## Boot prompt for the next Claude context window

> **NOTE:** This plan closed 2026-04-28 (all four cycles landed; see
> the Status header at the top). Boot prompt below preserved for
> archaeology only; with sequence step 3a + 3b both closed, the next
> session should pick up sequence step 4 — Phase 4b Scout — from a
> fresh plan-mode pass rooted in [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md).

```
[STALE — plan closed; preserved for archaeology only]
I'm starting AI-Native Foundation Stage 3 (sequence step 3b in
ROADMAP.md §1). Plan is in DASHBOARD_HANDOFF_PLAN.md.

Stage 1 closed 2026-04-28. Stage 2 closed 2026-04-28. Substrate
fully live: turn_traces, llm_calls.jsonl, feedback all populating
by default. The feedback synthesis hint adds the
"feedback:recent-thumbs-down-influenced-synthesis" tag to
turn_traces.notes — Cycle 3's drill-down should highlight that
tag as the closure-loop audit affordance.

Per CLAUDE.md, before any code:
1. Re-read CLAUDE.md, DECISIONS.md (especially the 2026-04-28
   Stage 1 / Stage 2 entries), ROADMAP.md (§3.1 Stage 3, §1
   sequence step 3b).
2. Run README drift check
   (.claude/skills/readme-discipline/SKILL.md Job 1) — Stage 3
   in-scope: api/main.py, api/store.py, web/src/app/admin/* (new
   tree), briarwood/agent/llm_observability.py (read-only here).
   None have READMEs. Likely no in-scope drift.
3. Read DASHBOARD_HANDOFF_PLAN.md in full.
4. Confirm baseline still at 16 pre-existing failures.
5. Cycle 2 prerequisite: read web/AGENTS.md, then read the
   Next.js server-component guides under
   web/node_modules/next/dist/docs/01-app/01-getting-started/
   before writing any client-side code.

Open design decisions are in the plan §"Open design decisions"
— defaults are recommended; pause briefly at the start of each
cycle to confirm or override. ODD #1 (chart library) and ODD #2
(auth gate) are the two with the broadest blast radius.

Cycle 4 closes Stage 3 in ROADMAP.md per the 2026-04-28
convention. With 3a + 3b both closed, sequence step 4 (Phase 4b
Scout) is unblocked.
```

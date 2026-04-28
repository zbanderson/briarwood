# AI-Native Foundation Stage 2 — Close The User-Feedback Loop

**Status:** ✅ RESOLVED 2026-04-28 — Cycles 1, 2, 3, 4 all landed. Stage 2
shipped: write-side endpoint + thumbs UI + closed-loop synthesis hint
auditable in `turn_traces.notes`. See [`DECISIONS.md`](DECISIONS.md)
2026-04-28 entry "AI-Native Foundation Stage 2 landed" for closeout
notes; [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md)
§"Persistence" for the system-level shape post-landing;
[`ROADMAP.md`](ROADMAP.md) §3.1 Stage 2 + §10 Resolved Index.
**Size:** M (~75–120 min LLM time across 4 cycles + closeout).
**Sequence position:** Step 3a of [`ROADMAP.md`](ROADMAP.md) §1 (per ODD #10:
the original step 3 splits into 3a/3b at Cycle 4 closeout — this stage
closes 3a; Stage 3 dashboard closes 3b). Stage 1 closed 2026-04-28.

**Resolved-during-drafting design decisions (owner sign-off 2026-04-28):**
- ODD #1 — Rating semantics. Stage 2 ships **response-quality** thumbs
  (Loop 2). Asset-quality rating is a separate feature, not in scope here.
  API contract is `"up"|"down"`; `_RATING_API_TO_RECORD` translates to
  `"yes"|"no"` at the boundary so the existing helper and analyzer's
  threshold logic stay untouched.
- ODD #3 — Read-back consumer. Path (a): in-flight synthesis hint into
  the next-turn prompt + `record_note` tag for SQL audit.
- ODD #8 — Test pollution. Path (b): added
  `BRIARWOOD_INTEL_FEEDBACK_PATH` env override on
  `intelligence_capture.py`; `tests/conftest.py` redirects per session.
- ODD #10 — Sequence-step closure convention. Path (c): split §1
  sequence step 3 into 3a (Stage 2) and 3b (Stage 3) at Cycle 4 closeout.
- Charting library upgrade — out of scope for Stage 2; filed as ROADMAP
  §3.4.7 "Evaluate React-native charting library to replace
  Plotly-iframe" (size L; depends on Stage 2).

**Principle.** "Closed feedback loops" — [`design_doc.md`](design_doc.md) § 3.4,
specifically Loop 2 (Communication Calibration) from § 7. *Write-only signals
are not closed loops.*

**Why now.**
- Stage 1 closed 2026-04-28: `turn_traces` table + `data/llm_calls.jsonl` +
  `messages.{latency_ms, answer_type, success_flag, turn_trace_id}` all
  populating by default. The substrate for keying feedback to a turn (via
  `messages.turn_trace_id`) is live.
- Scout (Phase 4b) inherits a closed user-feedback signal to learn from. Stage
  3 (admin dashboard) needs ratings to display.
- The capture helper exists today (`build_user_feedback_record` at
  [`briarwood/intelligence_capture.py:229-251`](briarwood/intelligence_capture.py))
  and the analyzer already correlates ratings with confidence
  ([`briarwood/feedback/analyzer.py:275-353`](briarwood/feedback/analyzer.py)) —
  the write-side helper is built, it is simply never called from the API.

**Cross-references.**
- [`ROADMAP.md`](ROADMAP.md) §3.1 (umbrella), §3.1 Stage 2 (this handoff),
  §1 sequence step 3.
- [`design_doc.md`](design_doc.md) § 3.4 (principles), § 7 (Loop 2 — Stage 2
  closes it).
- [`DECISIONS.md`](DECISIONS.md) 2026-04-27 entry (sequencing rationale).
- [`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md) — Stage 1's plan;
  format mirrored here.
- User-memory `project_llm_guardrails.md` — drives the guardrail-review pass at
  closeout. `feedback_size_for_llm_dev.md` — sizing convention applied (LLM
  minutes, not human days).

---

## Scope at a glance

Three independent, sequenceable pieces plus a closeout:

1. **`POST /api/feedback` endpoint + `feedback` table** in `api/store.py`,
   keyed by `message_id`. Writes the SQLite row AND mirrors via
   `build_user_feedback_record` → `append_intelligence_capture` so the
   analyzer pipeline picks it up automatically.
2. **Minimal UI**: thumbs-up / thumbs-down on assistant message bubbles in
   `web/src/components/chat/messages.tsx`. No comment box. Optimistic update;
   toast on error.
3. **Read-back consumer**: at least one path where a rating demonstrably
   influences turn N+1. ROADMAP allows two flavors; recommended path
   surfaces a "prior thumbs-down" hint into the next-turn synthesis prompt
   in the same conversation. See Open Design Decision #3.
4. **Closeout**: smoke matrix, ROADMAP closures, DECISIONS entry, README
   discipline check.

All three additive. No existing schema or contract is rewritten.

---

## Out of scope (deliberate)

- **Free-text comment capture.** Open the column for it but ship binary
  rating only. Defer text input UI to a later iteration.
- **Cross-session persona persistence.** Per ROADMAP §3.1 — in-session is
  enough. The router's unused `RouterDecision.user_type` field stays
  unused.
- **Rich admin tooling for browsing feedback.** That's Stage 3.
- **Auth.** Single-user product today. The endpoint takes `message_id`
  only.
- **Backfill.** No retroactive ratings on prior turns. New ratings flow
  forward only.
- **Rating revision history.** `INSERT OR REPLACE` keyed on `message_id`
  (last-write-wins). If the user clicks thumbs-up then thumbs-down, the
  later signal overwrites the earlier. No event log.
- **Rate limiting / spam protection.** Local-only product; one human user.

---

## Current state — what exists today

Read-only inventory before any changes.

### The capture helper (write-side, never called)

- [`briarwood/intelligence_capture.py:229-251`](briarwood/intelligence_capture.py#L229-L251)
  — `build_user_feedback_record(rating, comment="", analysis_id="",
  analysis_confidence=None, analysis_decision="", analysis_depth="")`.
  Returns a dict with `feedback_type="user_validation"`, `tags=["user-feedback-{rating}"]`.
  **Accepted ratings: `"yes"` / `"partially"` / `"no"`** (docstring line 241).
  This is the contract drift surfaced at the top of this plan — see Open
  Design Decision #1.
- [`briarwood/intelligence_capture.py:13-23`](briarwood/intelligence_capture.py#L13-L23)
  — `append_intelligence_capture(record)` writes one JSON line to
  `data/learning/intelligence_feedback.jsonl` with `captured_at` ISO
  timestamp prefixed.
- The JSONL has 6,290 historical analysis rows (per ROADMAP) but zero
  `feedback_type="user_validation"` rows today — the helper has never been
  called.

### The analyzer (read-back, partly built)

- [`briarwood/feedback/analyzer.py:115-117`](briarwood/feedback/analyzer.py#L115-L117)
  — already partitions records on `feedback_type == "user_validation"` and
  routes them to `_analyze_user_feedback`.
- [`briarwood/feedback/analyzer.py:275-303`](briarwood/feedback/analyzer.py#L275-L303)
  — counts by rating, builds `confidence_vs_feedback` pairs, and emits a
  `confidence_threshold_recommendation` once ≥5 pairs exist.
- [`briarwood/feedback/analyzer.py:306-353`](briarwood/feedback/analyzer.py#L306-L353)
  — only branches on `rating == "yes"` and `rating == "no"`; `"partially"`
  and any other label flow through unscored.

### The chat endpoint (consumer hook point)

- [`api/main.py:237-419`](api/main.py#L237-L419) — `POST /api/chat`.
  Captures `assistant_msg_id` at line 417 (Stage 1 wiring). The
  feedback endpoint is parallel — it doesn't insert into this stream;
  it consumes the `message_id` the client receives in the
  `events.message_event(assistant_msg["id"], "assistant")` SSE
  payload at line 418.

### The store (where the table lands)

- [`api/store.py`](api/store.py) — `ConversationStore`. Three tables today:
  `conversations`, `messages` (with Stage 1 metric columns), `turn_traces`.
  `_init_schema` at line 48 is the migration hook for a new `feedback`
  table; the existing per-column ALTER idiom is reusable.

### The chat UI (consumer hook point)

- [`web/src/components/chat/messages.tsx:97-321`](web/src/components/chat/messages.tsx#L97-L321)
  — `AssistantMessage` component. Renders prose, charts, cards,
  `ModuleBadges`, `verifierReport`, `critic`. No interactive footer
  today.
- The component receives `message: ChatMessage`. The `id` field flows
  through from `ChatMessage` (defined in `web/src/lib/chat/use-chat.ts`,
  not read here yet — Cycle 2 starts there).
- **AGENTS.md constraint**: `web/AGENTS.md` warns the local Next.js APIs
  may differ from training. Cycle 2 must read the relevant guide in
  `web/node_modules/next/dist/docs/` before writing client-side code.

### Test infrastructure

- [`tests/conftest.py`](tests/conftest.py) — `pytest_sessionstart` hook
  redirects `BRIARWOOD_LLM_JSONL_PATH` per session (Stage 1 added this).
  **Stage 2 needs analogous redirection for `CAPTURE_PATH`** so test runs
  don't pollute `data/learning/intelligence_feedback.jsonl`. See Open
  Design Decision #8.
- Test file naming: flat (`tests/test_<thing>.py`). NOT
  `tests/api/<name>.py` — that pattern shadows the `api/` package on
  import (Stage 1 lesson; recorded in DECISIONS.md 2026-04-28).

---

## The pieces — cycle-by-cycle

### Cycle 1 — `feedback` table + `POST /api/feedback`

**Status:** ✅ LANDED 2026-04-28.
**Estimate:** ~25–35 min LLM time. **Actual:** ~25 min.

**What landed.**
- `briarwood/intelligence_capture.py` — added `_resolve_capture_path()`
  honoring `BRIARWOOD_INTEL_FEEDBACK_PATH` env var. `CAPTURE_PATH`
  constant preserved for back-compat with the analyzer's import.
- `api/store.py` — new `feedback` table (PK on `message_id`, FKs to
  `messages` CASCADE and `turn_traces` SET NULL, `created_at` /
  `updated_at` ms-epoch columns, indexes on `(conversation_id,
  created_at)` and `(rating, created_at)`).
- `api/store.py::ConversationStore.upsert_feedback(message_id, rating,
  comment=None)` — resolves `conversation_id` / `turn_trace_id` /
  `answer_type` / `confidence` via JOIN on `messages` + `turn_traces`,
  raises `ValueError` for unknown `message_id` and non-assistant role,
  preserves `created_at` across revisions, advances `updated_at`.
- `api/store.py::ConversationStore.recent_feedback_for_conversation(...)`
  — newest-first, optional `since_ms` filter, `limit` cap. Used by
  Cycle 3.
- `api/store.py::ConversationStore.delete_conversation` — extended to
  delete feedback rows before messages (FK enforcement is off
  project-wide; explicit cleanup mirrors the existing `turn_traces`
  null-out pattern).
- `api/main.py` — `POST /api/feedback` with `Literal["up","down"]`
  rating, the `_RATING_API_TO_RECORD` boundary translator
  (`up→yes`, `down→no`), JSONL mirror via
  `build_user_feedback_record` → `append_intelligence_capture` with
  `[feedback.jsonl]` prefix log on swallow. `comment` field accepted
  on the wire but ignored in v1 (per ODD #2 — column reserved for v2).
- `tests/conftest.py` — extended `pytest_sessionstart` hook to also
  redirect `BRIARWOOD_INTEL_FEEDBACK_PATH` per session (mirrors the
  Stage 1 LLM-JSONL redirect pattern).

**Tests added** (8 in `tests/test_api_feedback.py`, all green):
1. `test_upsert_feedback_creates_row` — JOIN-resolved fields land in
   the row + return dict.
2. `test_upsert_feedback_replaces_on_revision` — `created_at`
   preserved, `updated_at` advances.
3. `test_upsert_feedback_rejects_unknown_message` — `ValueError`.
4. `test_upsert_feedback_rejects_non_assistant_role` — `ValueError`.
5. `test_recent_feedback_for_conversation_returns_in_order` —
   newest-first + limit honored.
6. `test_post_returns_404_for_unknown_message` — `ValueError`→404.
7. `test_post_writes_jsonl_mirror` — JSONL line carries
   post-translation `rating="no"`, `analysis_id=<message_id>`,
   `analysis_decision`, `analysis_confidence`, and the
   `user-feedback-no` tag from the helper.
8. `test_post_swallows_jsonl_mirror_error` — endpoint returns 200 +
   SQLite row persists when `append_intelligence_capture` raises.

**Deviations from plan.** None material. Test count came in at 8 vs. 6
estimated because the non-assistant-role guard test and the limit
check on `recent_feedback_for_conversation` were trivial adds.

**Suite delta** (full-suite run 2026-04-28 post-Cycle-1):
1524 passed pre-cycle → **1532 passed**, 16 pre-existing failures
unchanged. No regressions.

**Verification status.**
- Code-level: 8 new tests + 13 API-neighborhood tests
  (`test_api_turn_traces.py`, `test_api_strategy.py`,
  `test_chat_api.py`) green.
- Live `curl` smoke: deferred — auto-mode did not drive a manual
  shell session. Recommended next-session verification:
  ```
  curl -X POST localhost:8000/api/feedback \
    -H 'content-type: application/json' \
    -d '{"message_id":"<real-id>","rating":"down"}'
  sqlite3 data/web/conversations.db 'SELECT * FROM feedback'
  tail -1 data/learning/intelligence_feedback.jsonl
  ```

---

### Cycle 1 — original scope (preserved for archaeology)

**Estimate:** ~25–35 min LLM time.

**Scope.**

1. Extend `_init_schema` at
   [`api/store.py:48`](api/store.py#L48) with a new `feedback` table.
   Recommended schema (subject to design decision #2):
   ```sql
   CREATE TABLE IF NOT EXISTS feedback (
       message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
       conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
       turn_trace_id TEXT REFERENCES turn_traces(turn_id) ON DELETE SET NULL,
       rating TEXT NOT NULL,                  -- normalized: 'up' | 'down'
       comment TEXT,                          -- nullable; reserved for v2
       created_at INTEGER NOT NULL,           -- ms epoch
       updated_at INTEGER NOT NULL            -- ms epoch (revision support)
   );
   CREATE INDEX IF NOT EXISTS feedback_conv_idx
       ON feedback(conversation_id, created_at);
   CREATE INDEX IF NOT EXISTS feedback_rating_idx
       ON feedback(rating, created_at);
   ```
   `message_id` PK with `INSERT OR REPLACE` semantics (last-write-wins on
   re-rating). `comment` column is reserved — column is cheap; UI doesn't
   write to it in v1.

2. Add `ConversationStore.upsert_feedback(...)` and
   `ConversationStore.recent_feedback_for_conversation(...)` methods.
   Sketch:
   ```python
   def upsert_feedback(
       self,
       *,
       message_id: str,
       rating: str,
       comment: str | None = None,
   ) -> dict[str, Any]:
       """Upsert a thumbs rating for an assistant message.

       Returns the resolved row (including conversation_id /
       turn_trace_id resolved by FK lookup). Raises ValueError when
       message_id does not exist or refers to a non-assistant role —
       the API layer translates to 404 / 422."""
       ...

   def recent_feedback_for_conversation(
       self,
       conversation_id: str,
       *,
       since_ms: int | None = None,
       limit: int = 5,
   ) -> list[dict[str, Any]]:
       """Most-recent ratings in a conversation (most-recent first).
       Used by the Cycle 3 read-back consumer. since_ms filters by
       created_at; None means all time."""
       ...
   ```

3. Add `POST /api/feedback` to [`api/main.py`](api/main.py):
   ```python
   class FeedbackRequest(BaseModel):
       message_id: str
       rating: Literal["up", "down"]
       comment: str | None = None  # reserved; ignored in v1

   @app.post("/api/feedback")
   def submit_feedback(body: FeedbackRequest) -> dict[str, str]:
       store = get_store()
       try:
           row = store.upsert_feedback(
               message_id=body.message_id,
               rating=body.rating,
               comment=None,
           )
       except ValueError as exc:
           raise HTTPException(status_code=404, detail=str(exc)) from exc

       # Mirror into the existing analyzer pipeline so the read-back
       # path inherits a single source of structured feedback. JSONL
       # write is exception-safe: a JSONL failure must not roll back
       # the SQLite row.
       try:
           record = build_user_feedback_record(
               rating=_translate_rating_for_record(body.rating),  # see ODD #1
               analysis_id=body.message_id,
               analysis_confidence=row.get("confidence"),
               analysis_decision=row.get("answer_type") or "",
               analysis_depth="",  # unused by analyzer
           )
           append_intelligence_capture(record)
       except Exception as exc:  # noqa: BLE001
           print(
               f"[feedback.jsonl] mirror failed for {body.message_id}: {exc}",
               flush=True,
           )

       return {"status": "ok"}
   ```
   `_translate_rating_for_record` is the boundary translator from ODD #1.

**Tests** (new `tests/test_api_feedback.py`):
- `test_upsert_feedback_creates_row` — POST `up` for a real
  `message_id`; SELECT confirms row with `rating='up'`,
  `conversation_id`/`turn_trace_id` populated from the message.
- `test_upsert_feedback_replaces_on_revision` — POST `up` then `down`
  for the same `message_id`; only one row exists with `rating='down'`
  and `updated_at > created_at`.
- `test_upsert_feedback_404_for_unknown_message` — POST with a bogus
  `message_id`; assert 404, no row inserted.
- `test_upsert_feedback_writes_jsonl_mirror` — point `CAPTURE_PATH` at
  tmp via monkeypatch; POST `up`; assert one JSONL line with
  `feedback_type="user_validation"`, `rating="yes"` (post-translation),
  `analysis_id=<message_id>`.
- `test_upsert_feedback_swallows_jsonl_error` — monkeypatch
  `append_intelligence_capture` to raise; POST should still 200 and
  the SQLite row should still exist (failure log expected).
- `test_recent_feedback_for_conversation_returns_in_order` —
  insert two ratings via the helper; assert `most-recent first`,
  honoring `limit`.

**Verification.**
- `curl -X POST localhost:8000/api/feedback -H 'content-type: application/json' -d '{"message_id":"<real-id>","rating":"down"}'`
  returns 200; `sqlite3 data/web/conversations.db 'SELECT * FROM feedback'`
  shows the row.
- One line appended to `data/learning/intelligence_feedback.jsonl` with
  `feedback_type=user_validation`.

**Risk.** Low. Schema additive; FK violations not enforced (project-wide);
JSONL mirror is failure-safe.

---

### Cycle 2 — Thumbs UI in assistant bubble

**Status:** ✅ LANDED 2026-04-28.
**Estimate:** ~35–50 min LLM time. **Actual:** ~30 min.

**What landed.**
- `web/src/lib/api.ts` — added `user_rating: "up" | "down" | null` to
  `StoredMessage`. Type cascades through the `getConversation` server
  client into the page hydration.
- `web/src/lib/chat/use-chat.ts` — added optional `userRating` to
  `ChatMessage`. The hook does not own this field; the FeedbackBar
  manages its own optimistic state.
- `api/store.py::ConversationStore.get_conversation` — extended the
  per-message SELECT to LEFT JOIN `feedback` on `message_id` so the
  rehydrated payload carries `user_rating` per message (NULL for
  user-role messages and unrated assistant messages).
- `web/src/app/c/[id]/page.tsx` — hydrates `msg.userRating =
  m.user_rating` when mapping `StoredMessage` → `ChatMessage`.
- `web/src/app/api/feedback/route.ts` — new POST route handler,
  `runtime="nodejs"` + `dynamic="force-dynamic"`, mirrors the
  `api/chat/route.ts` reverse-proxy pattern. Forwards
  `{message_id, rating, comment?}` to FastAPI verbatim and returns
  the upstream status / body.
- `web/src/components/chat/messages.tsx` — added `FeedbackBar`
  component plus inline `ThumbIcon` SVG (no icon-library dep).
  Rendered after `VerifierReasoningPanel`, before `CriticPanel`
  (ODD #4 path (a) — bottom of bubble). Suppressed while
  `isStreaming` and while the message id still carries the
  `a-` temp-id prefix (server's real id replaces the temp id via
  the SSE `message` event before `done` fires; belt-and-suspenders).
- Toast plumbing: chose the "no global toast" path. Errors render as
  inline `role="alert"` text adjacent to the bar; the optimistic
  state rolls back to the prior rating.

**Tests added** (1 server-side; client-side is manual smoke):
- `test_get_conversation_rehydrates_user_rating` —
  `feedback_text` row joined into the message dict; non-rated
  assistant messages and user messages both rehydrate as
  `user_rating=None`.

**Plan deviations.**
1. **Dropped a prop-syncing `useEffect` on the FeedbackBar.** Initial
   draft re-synced `rating` from `initialRating` inside
   `useEffect(() => { if (!pending) setRating(initialRating) },
   [initialRating, pending])`. ESLint flagged this as
   `react-hooks/set-state-in-effect` — modern React pattern is to
   key the component on the changing input and remount instead.
   Confirmed the parent (`MessageList`) keys `AssistantMessage` on
   `m.id`, so a conversation switch already remounts the bar. Dropped
   the effect; component now reads `initialRating` once on mount.
2. **No JS test harness exercised.** Repo's web/ has no jsdom or
   component test runner configured. Manual smoke (deferred to
   user) covers the click + toast + rehydration paths. The
   server-side rehydration test covers the persistence contract.

**Verification status.**
- Code-level: `tsc --noEmit` clean, `eslint` clean across all 5
  edited files. Python suite still 21 passed across the API
  neighborhood (8 store/API tests + the new rehydration test +
  Stage 1's tests + chat_api tests).
- Live UI smoke: deferred (auto-mode does not drive a browser).
  Recommended next-session manual smoke:
  ```
  # Terminal 1: uvicorn api.main:app --reload --port 8000
  # Terminal 2: cd web && npm run dev
  # Browser:
  # 1. Send a BROWSE turn, click 👎 → confirm SQLite row + JSONL line.
  # 2. Refresh the page → confirm 👎 rehydrates as filled.
  # 3. Click 👍 → confirm row updates, updated_at advances.
  # 4. Stop FastAPI, click on a fresh message → confirm inline error
  #    + optimistic state reverts.
  ```

---

### Cycle 2 — original scope (preserved for archaeology)

**Estimate:** ~35–50 min LLM time. (Web work is slower because of the
AGENTS.md gate.)

**Pre-flight (mandatory).** Per
[`web/AGENTS.md`](web/AGENTS.md): read the relevant Next.js guides under
`web/node_modules/next/dist/docs/` before writing any client-side
mutation code. Targets to read:
- `app-router/route-handlers` (we already proxy through one for chat)
- `app-router/data-fetching/server-actions` vs client `fetch` — confirm
  which the project uses for non-streaming POSTs (the chat side uses
  client `fetch` against a local Next route; mirror that pattern, do
  not introduce a server action just for this).
- `caching/data-cache` — confirm POST to `/api/feedback` doesn't get
  cached by the client.

**Scope.**

1. Add a `FeedbackBar` component to
   [`web/src/components/chat/messages.tsx`](web/src/components/chat/messages.tsx).
   Two icon buttons (👍 / 👎). Filled-state when active. Disabled-state
   while in-flight or after success. Optimistic update; rollback + toast
   on failure.
   - Placement: rendered AFTER `ModuleBadges` and `VerifierReasoningPanel`,
     BEFORE `CriticPanel`. Bottom of the assistant bubble. Mirrors
     ChatGPT/Claude convention. (Open Design Decision #4.)
   - Suppressed when `message.isStreaming === true` — no rating an
     in-flight response.
2. Add a Next.js route handler at
   `web/src/app/api/feedback/route.ts` that proxies the POST to the
   Python FastAPI bridge (mirror the existing chat-route proxy pattern).
   This keeps CORS local; the Python `/api/feedback` is reachable only
   via the Next proxy.
3. Persist rating state across refresh: when
   `useChat`/`use-chat.ts` hydrates a conversation, surface
   `message.userRating: "up" | "down" | null` from the server. Cycle 2
   adds the field to `ChatMessage` and the SSE rehydration path in
   `api/main.py:get_conversation` reads from the `feedback` table on
   load. (Concrete shape: extend the per-message dict in
   `ConversationStore.get_conversation` at
   [`api/store.py:140-147`](api/store.py#L140-L147) to LEFT JOIN the
   `feedback` table and surface the latest `rating` per `message_id`.)
4. Toast on error: integrate into whatever notification primitive the
   web app already uses; if none, render a transient inline error
   inside the FeedbackBar (no new global state needed). Confirm during
   Cycle 2 start.

**Tests.**
- **Server-side:** `test_get_conversation_returns_user_rating` —
  insert a `down` rating for an assistant message; `get_conversation`
  returns the message with `user_rating: "down"`.
- **Client-side:** if a JS test harness is configured under `web/`,
  add a component test that simulates the click and asserts the
  optimistic state. If not configured, defer to manual smoke and note
  in the closeout.

**Verification (manual; deferred to user — auto-mode does not drive a
browser).**
- Run dev: `cd web && npm run dev` + `uvicorn api.main:app --reload`.
- Send one BROWSE turn. Click 👎 on the assistant response. Check
  `sqlite3 ... 'SELECT * FROM feedback'` → row exists.
- Refresh the page. Confirm the 👎 button reads as filled (state
  rehydrated from the server).
- Click 👍 to revise. Confirm the row updates to `rating='up'`,
  `updated_at` advanced.
- Disconnect FastAPI, click 👍 on a fresh message. Confirm the toast
  fires and the optimistic state rolls back.

**Risk.** Medium. Web work is the highest-friction part of this
handoff (AGENTS.md gate + state hydration + toast plumbing). Keep
the component thin.

---

### Cycle 3 — Read-back consumer (the gate)

**Status:** ✅ LANDED 2026-04-28.
**Estimate:** ~15–30 min LLM time. **Actual:** ~20 min.

**What landed.**
- New module `briarwood/synthesis/feedback_hint.py` with:
  - `_FEEDBACK_HINT` ContextVar — async-task-scoped, propagates across
    the threadpool boundary via the existing
    `briarwood.agent.turn_manifest.in_active_context` decorator.
  - `apply_feedback_hint(store, conversation_id, on_apply=...)`
    context manager — does the SQL lookup once, sets the ContextVar
    when a recent thumbs-down is found, calls `on_apply` for the
    manifest-note side effect, resets on exit. Failure-safe: a
    misbehaving store returns False instead of raising.
  - `current_feedback_hint()` — what the synthesizer reads.
  - `HINT_MANIFEST_TAG = "feedback:recent-thumbs-down-influenced-synthesis"`
    — the audit string for the SQL query
    `SELECT ... FROM turn_traces WHERE notes LIKE '%recent-thumbs-down%'`.
- `briarwood/synthesis/llm_synthesizer.py` — added one import and three
  lines: read the hint via `current_feedback_hint()` and append to
  `system_prompt` before the LLM call. Numeric / citation rules
  unchanged (the hint explicitly says so).
- `api/pipeline_adapter.py` — wrapped the dispatch threadpool call in
  all four entry points (`_browse_stream_impl`, `_decision_stream_impl`,
  `_search_stream_impl`, `_dispatch_stream_impl`) with the
  `apply_feedback_hint` context manager. `on_apply` calls
  `record_note(HINT_MANIFEST_TAG)` so the loop closure surfaces in
  `turn_traces.notes` for SQL audit.

**Why ContextVar instead of kwarg-passthrough.** Plumbing a kwarg
through the seven `synthesize_with_llm` call sites in
`briarwood/agent/dispatch.py` (handle_browse, handle_decision,
handle_research, handle_rent_lookup, handle_risk, handle_edge,
handle_strategy) would have meant 7 surgical edits and 7 future
regression risks — and the synthesizer call signature would have
grown a parameter that's only set from one outer entry point.
ContextVar keeps the seam to exactly two files (the entry layer that
sets, the synthesizer that reads); the existing `in_active_context`
decorator already propagates contextvars across the threadpool
boundary so it composes cleanly with the established pattern.

**Tests added** (7 in `tests/test_feedback_readback.py`, all green):
1. `test_synthesis_hint_added_when_recent_down_rating` — hint set
   inside the context manager, `current_feedback_hint()` returns the
   canonical text.
2. `test_synthesis_hint_omitted_when_no_recent_down` — only thumbs-up
   present; hint is None.
3. `test_synthesis_hint_omitted_when_feedback_table_empty` —
   conversation has zero ratings.
4. `test_synthesis_hint_noop_when_conversation_id_missing` — no
   conversation context (CHITCHAT or non-conversation flow).
5. `test_synthesis_hint_noop_when_store_missing` — defensive guard
   for tests / future surfaces.
6. `test_on_apply_callback_fires_only_when_hint_applies` — the
   manifest-note side effect happens iff the hint applies.
7. `test_synthesis_hint_swallows_store_failure` — a broken store
   degrades to no-op rather than breaking synthesis.

**Plan deviations.**
1. **Larger test pack than estimated** (7 vs. 3). Three of the extra
   tests are defensive guards (None store, None conversation_id,
   raising store) that are cheap to write and protect against future
   regressions. One extra test (`test_synthesis_hint_omitted_when_feedback_table_empty`)
   is a corner case the original 3-test sketch didn't isolate.
2. **Module placement.** Put the helper at
   `briarwood/synthesis/feedback_hint.py` rather than under
   `briarwood/feedback/` (where the analyzer lives). The synthesizer
   is the only consumer; placing the module next to its consumer is
   the cleaner dependency direction. `briarwood/feedback/` would
   imply a wider read-back surface than this stage actually built.

**Verification status.**
- Code-level: 7 new tests + 28 in the API/feedback neighborhood, all
  green. Synthesis suite runs clean (431 passed; 2 failures are in
  the documented 16-failure baseline, both pre-existing).
- Live UI smoke: deferred (auto-mode does not drive a browser).
  Recommended next-session manual smoke:
  ```
  # Chat one turn → 👎 it → chat a follow-up turn in the same
  # conversation. Then:
  sqlite3 data/web/conversations.db \
    "SELECT turn_id, user_text, notes FROM turn_traces \
     WHERE notes LIKE '%recent-thumbs-down%' ORDER BY started_at DESC LIMIT 3"
  # The follow-up turn should appear with the manifest tag in notes.
  # Read the prose visually — it should not be a verbatim repeat of
  # the prior turn's framing.
  ```

---

### Cycle 3 — original scope (preserved for archaeology)

**Estimate:** ~15–30 min LLM time, depending on chosen path (ODD #3).

**Scope (recommended path: in-flight synthesis hint, ODD #3 option a).**

Inject a single-line "prior negative feedback in this conversation"
hint into the synthesis prompt for subsequent turns in the same
conversation. Concrete plumbing:

1. In
   [`api/pipeline_adapter.py`](api/pipeline_adapter.py)'s turn-build
   path (the layer that assembles synthesis context for
   `decision_stream` / `browse_stream` / `dispatch_stream`), call
   `store.recent_feedback_for_conversation(conversation_id, limit=3)`
   before kicking off the synthesizer.
2. If any of the recent ratings is `"down"`, append a single-sentence
   guidance string to the synthesizer's system message:
   *"NOTE: A recent assistant turn in this conversation received a
   thumbs-down. Vary your framing — try a different angle or
   organizational structure than the prior turn."*
3. Record on the manifest via `record_note(...)` so the signal is
   observable in `turn_traces.notes`. Tag string:
   `"feedback:recent-thumbs-down-influenced-synthesis"`.

This is the minimum viable closed loop. The hint is a single sentence;
it does not constrain the synthesizer beyond "vary your framing"; it
demonstrably shapes turn N+1 prose; and the manifest note makes the
loop closure auditable in SQL:
```sql
SELECT turn_id, conversation_id, notes
FROM turn_traces
WHERE notes LIKE '%recent-thumbs-down-influenced-synthesis%';
```

**Alternative (ODD #3 option b) — analyzer-only surfacing.** Extend
[`briarwood/feedback/analyzer.py`](briarwood/feedback/analyzer.py)
with a "recent low-rated turns" panel: query the `feedback` table
directly (not just the JSONL) for the last N `down` ratings, JOIN
against `turn_traces` to surface `turn_id` / `answer_type` /
`duration_ms_total`, render in `format_report`. This is a read-side
artifact, not an in-flight loop. ROADMAP §3.1 success criterion text
allows this path ("analyzer surfaces it") but Loop 2 in §7 implies
in-flight. Choose at Cycle 3 start.

**Tests** (new `tests/test_feedback_readback.py`):
- For option (a):
  - `test_synthesis_hint_added_when_recent_down_rating` — seed a
    `down` rating; trigger a fake synthesis call; assert the system
    message contains the guidance string.
  - `test_synthesis_hint_omitted_when_no_recent_down` — only `up`
    ratings present; assert no hint.
  - `test_manifest_note_records_hint_application` — when hint
    fires, assert `manifest.notes` contains the tag.
- For option (b):
  - `test_analyzer_lists_recent_low_rated_turns` — seed `feedback`
    table + `turn_traces`; analyzer report contains a "Recent
    Low-Rated Turns" section with the right rows.

**Verification.**
- Option (a): chat one turn → 👎 it → chat a follow-up turn in the
  same conversation. Confirm `turn_traces.notes` for the second
  turn contains
  `feedback:recent-thumbs-down-influenced-synthesis`. Read the
  prose visually — it should not be a verbatim repeat of the first
  turn's framing.
- Option (b): seed ratings → run
  `python -m briarwood.feedback.analyzer`. Confirm the new section
  renders.

**Risk.** Low–Medium. Option (a) touches the synthesis prompt
assembly path — confirm at Cycle 3 start exactly which adapter
function is the right insertion point (the pipeline_adapter is
likely; if the synthesizer is invoked deeper, find the right
seam). Add the call at the highest layer that has both
`conversation_id` and the synth context handy — minimizes
plumbing.

---

### Cycle 4 — Closeout

**Status:** Not started.
**Estimate:** ~10–15 min LLM time.

**Scope.**
- Smoke matrix (deferred to user — auto-mode):
  - Chat a BROWSE turn → 👍 → chat a follow-up. Confirm SQLite row,
    JSONL line, and (option a) no hint fired.
  - Chat a DECISION turn → 👎 → chat a follow-up. Confirm hint
    fired and `turn_traces.notes` carries the tag.
  - Refresh the page mid-session; confirm rating state rehydrates.
- README discipline check (per
  [`.claude/skills/readme-discipline/SKILL.md`](.claude/skills/readme-discipline/SKILL.md)
  Job 3): no in-scope module has a README. No README updates expected.
- `ARCHITECTURE_CURRENT.md` update: extend §"Persistence" (added by
  Stage 1) to mention the `feedback` table and its FK to `messages` /
  `turn_traces`. Add a brief note that JSONL mirroring is the
  analyzer's input path.
- `TOOL_REGISTRY.md`: no changes (feedback is observability, not a
  tool).
- ROADMAP closures (per the convention adopted 2026-04-28):
  - §3.1 Stage 2 → ✅ + `**Status:** RESOLVED YYYY-MM-DD — …` line
    inside the Stage 2 entry rubric.
  - §1 sequence step 3 (Stages 2-3) → only Stage 2 closes here;
    leave the sequence row open until Stage 3 closes too. **Open
    Design Decision #10**: confirm the convention for partial-stage
    sequence rows at closeout.
  - §10 Resolved Index: add row(s) for Stage 2 closeout.
- DECISIONS.md entry summarizing what landed + plan deviations +
  Guardrail Review (per `project_llm_guardrails.md`). Walk the new
  feedback path for any guardrails that block legitimate signal
  (auth gates, validators, PII filters, rate limits). Likely-empty
  this round but the walk is mandatory.
- Boot prompt for the next Claude context window (Stage 3 dashboard
  is the next logical step but is `M-L` and may be sequenced after
  Phase 4b Scout — see ROADMAP §3.1 Stage 4 sequencing note).

**Tests:** existing tests stay green. The new tests from Cycles 1–3
are the regression net.

**Risk.** Low. Docs + closeout only.

---

## Open design decisions

(Resolve at the start of the named cycle.)

1. **Rating vocabulary mismatch — API "up/down" vs helper
   "yes/partially/no".** Cycle 1. Surfaced as a CLAUDE.md
   contradiction-flag rather than silently reconciled. Three options:
   - **(a) Map at the API boundary.** API takes `"up"|"down"`;
     `_translate_rating_for_record` maps `up→yes`, `down→no` before
     calling `build_user_feedback_record`. Helper signature unchanged;
     analyzer's `"yes"`/`"no"` branches keep working. **Recommended.**
     Lowest blast radius; preserves the existing analyzer's threshold
     recommendation logic.
   - **(b) Loosen the helper.** Add `"up"` / `"down"` as accepted
     ratings in `build_user_feedback_record`; analyzer's `"no"`
     branch widens to also include `"down"`. Cleaner long-term but
     touches a helper that 6,290 historical-shaped records may key
     off.
   - **(c) Use `"yes"`/`"no"` everywhere.** Diverge from ROADMAP
     wording. Cleanest data shape but contradicts the spec; user
     should approve the spec change first.
   Recommendation: (a). File a §4 Low ROADMAP item to revisit if a
   third rating tier (e.g., "partial") becomes useful.

2. **`feedback` table schema — `comment` column now or later?**
   Cycle 1. v1 doesn't capture comments. Two options:
   - **(a) Reserve the column now.** Cheap to add; saves a future
     ALTER. **Recommended.**
   - **(b) Add the column when v2 ships.** Strict YAGNI but a 30-sec
     ALTER later vs zero cost now.

3. **Read-back consumer choice.** Cycle 3.
   - **(a) In-flight synthesis hint** — recommended; satisfies Loop
     2's "turn N+1 visibly influenced" criterion most strictly.
     Single sentence appended to system message + manifest note.
   - **(b) Analyzer-only surfacing** — extend
     `briarwood/feedback/analyzer.py` to render a "recent
     thumbs-down" panel. Read-side only; no in-flight effect.
   - **(c) Both** — option (a) ships in this stage; option (b) files
     as §4 Low for future.
   Recommendation: (a). (b) is a nice future Stage 3 dashboard
   feature.

4. **UI placement of the `FeedbackBar`.** Cycle 2.
   - **(a) Bottom of the assistant bubble**, after `ModuleBadges`
     and `VerifierReasoningPanel`. **Recommended** — mirrors
     ChatGPT/Claude.
   - **(b) Top of the bubble.** More prominent; competes visually
     with `VerdictCard`.
   - **(c) Inline between prose and cards.** Crowded.

5. **Idempotency on duplicate clicks.** Cycle 2.
   `INSERT OR REPLACE` keyed on `message_id` is the recommendation.
   The UI also disables the button after first send (prevents
   accidental double-submit).

6. **Anonymity / auth.** Cycle 1. Endpoint takes `message_id`
   only; no user id, no session token. Single-user product. Don't
   add auth.

7. **Mirror-write atomicity.** Cycle 1. SQLite write is the source
   of truth; JSONL append is the analyzer's hopper. If JSONL fails,
   log with `[feedback.jsonl]` prefix and keep the SQLite row.
   Mirrors Stage 1's "observability must never break a turn" pattern.

8. **Test pollution.** Cycle 1. New writes via
   `append_intelligence_capture` would land in the real
   `data/learning/intelligence_feedback.jsonl` during test runs and
   corrupt the analyzer's input.
   - **(a) Extend `tests/conftest.py`** to monkeypatch
     `briarwood.intelligence_capture.CAPTURE_PATH` (or set a
     `BRIARWOOD_INTEL_FEEDBACK_PATH` env var if we add one) to a
     per-session tmp file. Mirrors the Stage 1 pattern for
     `BRIARWOOD_LLM_JSONL_PATH`. **Recommended.**
   - **(b) Add an env override to `intelligence_capture.py`** so
     tests can redirect without monkeypatching. Slightly cleaner
     long-term; ~5 extra LOC.
   - **(c) Just monkeypatch in the tests that need it.** Fragile.
   Recommendation: (b) — adds `BRIARWOOD_INTEL_FEEDBACK_PATH` env
   override and `tests/conftest.py` sets it per session. Two-line
   change in `intelligence_capture.py`.

9. **Stage 2 MVP cut.** If a partial-day session is all that's
   available, do **Cycles 1 + 3 only** (skip the UI). The
   feedback can be POSTed via curl for verification, the read-back
   gate is satisfied, and Cycle 2 (UI) can ship as a follow-on.
   Note: ROADMAP §3.1 explicitly lists "Minimal UI" as Stage 2 scope
   — partial-cut breaks the stage's contract. Only viable if the
   alternative is shipping nothing.

10. **Sequence-step closure convention for partial-stage closure.**
    Cycle 4. ROADMAP §1 sequence step 3 reads "AI-Native Foundation
    Stages 2–3 — feedback loop + dashboard." Stage 2 alone closes
    only half the row.
    - **(a) Leave the sequence row open** until Stage 3 also lands.
    Recommended.
    - **(b) Mark the row partially-resolved** (e.g., "✅ 50%" — not
      a convention today). Don't introduce a new marker for a
      one-off.
    - **(c) Split sequence step 3 into 3a (Stage 2) and 3b (Stage
      3).** Cleaner long-term; tiny ROADMAP edit.

---

## Cycle ordering rationale

- **Cycle 1 first** — substrate for everything. Endpoint + table.
- **Cycle 2 second** — depends on Cycle 1's endpoint. Web work has
  the highest friction so banking the substrate first means a
  blocking issue in web doesn't strand Cycle 3.
- **Cycle 3 third** — depends on Cycle 1's `feedback` table; can
  also be exercised via curl-seeded ratings if Cycle 2 stalls.
  Recommended order is 1 → 2 → 3 → 4 because each cycle's manual
  verification builds on the prior.
- **Cycle 4 last** — closeout.

If Cycle 2 hits an unexpected web-side blocker, swap to **1 → 3 →
4 → 2** (ship the data path closed and let the UI follow).

---

## Failure semantics

The pattern across all three cycles: **observability and feedback
must never break a turn.**

- All persistence writes wrapped in `try: ... except Exception:`.
- Failures log via `print(...)` with a recognizable prefix
  (`[feedback]`, `[feedback.jsonl]`) and continue.
- The chat response stream and the feedback POST are independent —
  a `/api/feedback` failure has no path to break a chat turn.
- The Cycle 3 read-back consumer must guard
  `recent_feedback_for_conversation` with try/except — a stale or
  corrupt feedback row cannot break synthesis.

This mirrors Stage 1's pattern at
[`api/store.py`](api/store.py) (the `[turn_traces]` /
`[messages.metrics]` prefix-log convention).

---

## Tests

**Existing tests must stay green.** Pre-handoff baseline is the
Stage 1 baseline: 16 pre-existing failures, none in scope for
Stage 2.

**New tests** per cycle:
- Cycle 1: 6 tests in `tests/test_api_feedback.py`.
- Cycle 2: 1 server-side rehydration test + manual smoke for the
  client component.
- Cycle 3: 3 tests in `tests/test_feedback_readback.py`.

**Total expected new test count:** ~10. (Smaller than Stage 1
because the substrate is reused.)

**Manual verification gates** (all deferred to user; auto-mode
does not drive a browser):
- After Cycle 1: `curl` the endpoint; assert SQLite + JSONL.
- After Cycle 2: smoke the UI in a real browser.
- After Cycle 3: chat → 👎 → chat; confirm the manifest note.
- After Cycle 4: full smoke matrix above.

---

## ROADMAP closures (anticipated)

- §3.1 Stage 2 *Close The User-Feedback Loop* — RESOLVED on
  landing. Add `✅` prefix and `**Status:**` line.
- §10 Resolved Index — add 2 rows: one for Stage 2 itself, one for
  the Cycle 3 read-back consumer (which is the gate criterion).
  Possibly a third row for the boundary translator if ODD #1
  resolves to its own filing.
- §1 sequence step 3 — STAYS OPEN per ODD #10(a); only half closes
  here (Stage 3 is the other half).

---

## Boot prompt for the next Claude context window

> **NOTE:** This plan closed 2026-04-28 (all four cycles landed; see
> the Status header at the top of this file). The boot prompt below
> is preserved for archaeology; the next session should pick up
> sequence step 3b — Stage 3 dashboard — from a fresh plan-mode pass.

```
[STALE — plan closed; preserved for archaeology only]
I'm resuming AI-Native Foundation Stage 2 (sequence step 3a in
ROADMAP.md §1). Plan is in FEEDBACK_LOOP_HANDOFF_PLAN.md.

Cycle 1 LANDED 2026-04-28 — feedback table + POST /api/feedback +
boundary translator + JSONL mirror + 8 new green tests. Suite
delta 1524 → 1532 passed; 16 pre-existing failures unchanged. See
the plan's Cycle 1 "What landed" subsection for the full
file-by-file summary. Next is Cycle 2 (UI thumbs in
web/src/components/chat/).

Resolved-during-drafting design decisions (owner sign-off
2026-04-28; recorded in plan header):
- ODD #1 → response-quality semantics; up→yes / down→no boundary
  translator (asset-quality rating filed as separate future work).
- ODD #3 → in-flight synthesis hint for Cycle 3 read-back.
- ODD #8 → BRIARWOOD_INTEL_FEEDBACK_PATH env override (now live;
  conftest.py redirects per session).
- ODD #10 → split sequence step 3 → 3a/3b at Cycle 4 closeout.
- Charting library upgrade → out of scope; filed as ROADMAP §3.4.7.

Still-open design decisions for the cycles ahead:
- ODD #4 (Cycle 2) — UI placement of FeedbackBar in
  AssistantMessage. Recommendation: bottom of bubble (after
  ModuleBadges and VerifierReasoningPanel, before CriticPanel).
  Mirrors ChatGPT/Claude convention.
- ODD #2 — comment column reserved (already shipped); confirm if
  v2 wants to start writing it.

Per CLAUDE.md, before any code this session:
1. Re-read CLAUDE.md, DECISIONS.md (especially the 2026-04-28
   Stage 1 / Router audit / Router Round 2 entries),
   ROADMAP.md (especially §3.1 Stage 2 + §3.4.7 chart entry).
2. Run README drift check (.claude/skills/readme-discipline/SKILL.md
   Job 1) — Cycle 2/3/4 in-scope: api/main.py, api/store.py,
   briarwood/intelligence_capture.py, briarwood/feedback/analyzer.py,
   api/pipeline_adapter.py (Cycle 3 likely insertion point),
   web/src/components/chat/. None have READMEs. Likely no in-scope
   drift.
3. Read FEEDBACK_LOOP_HANDOFF_PLAN.md in full — the Cycle 1
   "What landed" subsection is the source of truth for what's
   already in place; do NOT re-derive Cycle 1 wiring.
4. Confirm baseline still at 16 pre-existing failures, 1532 passed.

Cycle 2 mandatory pre-flight (per web/AGENTS.md): read the
relevant Next.js guides under web/node_modules/next/dist/docs/
before writing any client-side code. Targets: app-router/
route-handlers, app-router/data-fetching/server-actions vs client
fetch, caching/data-cache. The chat side already uses a Next route
handler proxying to FastAPI — mirror that pattern for /api/feedback.

Cycle 3 (the closure gate per ROADMAP §3.1 Stage 2 success
criterion): in-flight synthesis hint. Insertion point sketched in
the plan as api/pipeline_adapter.py — confirm at Cycle 3 start by
finding the layer that has both conversation_id and the synth
context handy. Add the hint, record_note tag
("feedback:recent-thumbs-down-influenced-synthesis"), and the
3-test pack.

Cycle 4 closes Stage 2 in ROADMAP.md per the 2026-04-28
convention (✅ prefix + **Status:** line + §10 Resolved Index
rows). Also splits §1 sequence step 3 into 3a / 3b per ODD #10.
DECISIONS.md entry summarizes the whole stage + Guardrail Review
walk per project_llm_guardrails.md directive.
```

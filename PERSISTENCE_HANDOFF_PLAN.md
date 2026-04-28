# AI-Native Foundation Stage 1 — Persist Every Action

**Status:** ✅ RESOLVED 2026-04-28 — Cycles 1-4 landed. See
[`DECISIONS.md`](DECISIONS.md) 2026-04-28 entry "AI-Native Foundation
Stage 1 landed" for the closeout, [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md)
§"Persistence" for the system-level shape, and [`ROADMAP.md`](ROADMAP.md)
§3.1 Stage 1 + §10 Resolved Index rows 6, 7, 8.

**Size:** M (~1 handoff, one focused day).
**Sequence position:** Step 2 of [`ROADMAP.md`](ROADMAP.md) §1. Phase 4a Cycle 6
closed 2026-04-28; this is the next move.

**Principle.** "Every action is an artifact" —
[`design_doc.md`](design_doc.md) § 3.4. This handoff is the implementation arm.

**Why now.**
- Phase 4a Cycle 6 closed (graft retired, audit docs reconciled). No upstream
  blockers.
- Scout (Phase 4b) inherits persisted artifacts to mine.
- Stage 3 (admin dashboard) is read-only on top of what Stage 1 writes.
- Stage 4 (model-accuracy loop) correlates persisted module attributions
  against ground-truth outcomes.
- Without Stage 1, every Scout iteration leaves no inspectable trace.

**Cross-references.**
- [`ROADMAP.md`](ROADMAP.md) §3.1 (umbrella), §3.1 Stage 1 (this handoff),
  §1 sequence step 2.
- [`design_doc.md`](design_doc.md) § 3.4 (principles), § 7 (the dual feedback
  loops; Stage 1 is the substrate Loop 1 needs).
- [`DECISIONS.md`](DECISIONS.md) 2026-04-27 entry (sequencing rationale).

---

## Scope at a glance

Three independent, sequenceable pieces:

1. **Persist `TurnManifest` to a new `turn_traces` table** in
   `data/web/conversations.db`. One row per chat turn. Columns mirror the
   `TurnManifest` dataclass.
2. **Append `LLMCallLedger` records to `data/llm_calls.jsonl`.** One JSON
   line per call. Adds a sink in `briarwood/agent/llm_observability.py`.
3. **Add metric columns to the existing `messages` table.** New nullable
   columns: `latency_ms`, `answer_type`, `success_flag`, `turn_trace_id`
   (FK → `turn_traces.turn_id`).

All three are additive. No existing schema or contract is rewritten.

---

## Out of scope (deliberate)

- **No backfill of historical conversations.** New columns are nullable.
- **No new analysis on the data.** That's Stage 3 (admin dashboard).
- **No env-var flag for the persistence path itself.** Persistence is the
  default once shipped. (One narrow exception: the JSONL write needs to be
  exception-safe — see §"Failure semantics" below.)
- **No prompt-cache integration.** Stage 1 records what happened; tuning
  the cache is its own conversation.
- **No `data/llm_calls.jsonl` rotation/compaction.** Operational concern;
  defer until file size becomes an issue.
- **No PII redaction beyond what the existing `BRIARWOOD_LLM_DEBUG_PAYLOADS`
  flag already governs.** `debug_payload` (full prompt + response) is
  excluded from the JSONL by default; flip the flag to opt in.

---

## Current state — what exists today

Read-only inventory before any changes.

### Per-turn state (in-memory, ephemeral)

- [`briarwood/agent/turn_manifest.py:111`](briarwood/agent/turn_manifest.py#L111)
  — `@dataclass TurnManifest`. Fields: `turn_id`, `started_at`, `user_text`,
  `conversation_id`, `answer_type`, `confidence`, `classification_reason`,
  `dispatch`, `wedge`, `modules_run`, `modules_skipped`, `llm_calls`,
  `tool_calls`, `duration_ms_total`, `notes`. Sub-records:
  `ModuleExecutionRecord`, `ModuleSkipRecord`, `WedgeRecord`,
  `LLMCallSummary`, `ToolCallRecord` (lines 50-109).
- `TurnManifest.to_jsonable()` at line 130 already produces a JSON-serializable
  dict — Stage 1 reuses this.
- [`briarwood/agent/turn_manifest.py:170`](briarwood/agent/turn_manifest.py#L170)
  `start_turn(...)` — creates the manifest and binds it to
  `_current_manifest` ContextVar.
- [`briarwood/agent/turn_manifest.py:185`](briarwood/agent/turn_manifest.py#L185)
  `end_turn() -> TurnManifest | None` — finalizes `duration_ms_total` and
  emits to stderr when `BRIARWOOD_TRACE=1`. **Returns the finalized
  manifest** — Stage 1 consumes the return value here.
- API wiring: [`api/main.py:265`](api/main.py#L265) calls `start_turn(...)`
  before the SSE stream, and [`api/main.py:270`](api/main.py#L270) calls
  `end_turn()` in the `finally` of the outer event-source. The inner
  `_event_source_inner()` is where the assistant message gets persisted at
  [`api/main.py:398`](api/main.py#L398).

### LLM call records (process-local)

- [`briarwood/agent/llm_observability.py:36`](briarwood/agent/llm_observability.py#L36)
  — `@dataclass LLMCallRecord`. Fields: `surface`, `schema_name`, `provider`,
  `model`, `prompt_hash`, `response_hash`, `status`, `attempts`,
  `duration_ms`, `cache_hit`, `error_type`, `input_tokens`, `output_tokens`,
  `cost_usd`, `debug_payload`, `metadata`.
- [`briarwood/agent/llm_observability.py:55`](briarwood/agent/llm_observability.py#L55)
  — `class LLMCallLedger`. `append(record)` mirrors a summary into the
  active `TurnManifest` (line 73-91, lazy import to avoid cycle). Singleton
  `_LEDGER` at line 97 with `get_llm_ledger()` accessor.
- `debug_payloads_enabled` property reads `BRIARWOOD_LLM_DEBUG_PAYLOADS` env
  flag at line 65. Stage 1 honors this — `debug_payload` is excluded from
  the JSONL when the flag is off.

### SQLite store

- [`api/store.py:30`](api/store.py#L30) — `class ConversationStore`.
  `_init_schema` at line 48 creates two tables today:
  - `conversations(id, title, created_at, updated_at)`
  - `messages(id, conversation_id, role, content, events, created_at)`
- DB path at [`api/store.py:32`](api/store.py#L32) — env override
  `BRIARWOOD_WEB_DB`, default `data/web/conversations.db`.
- [`api/store.py:118`](api/store.py#L118) `add_message(...)` — current
  insert call. Returns the new row dict.

---

## The three pieces — cycle-by-cycle

### Cycle 1 — `turn_traces` table + write path

**Status:** Not started.

**Scope.**
- Extend `ConversationStore._init_schema` at
  [`api/store.py:48`](api/store.py#L48) with a new `turn_traces` table.
  Recommended schema (subject to design decision #1 below):
  ```sql
  CREATE TABLE IF NOT EXISTS turn_traces (
      turn_id TEXT PRIMARY KEY,
      conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
      started_at REAL NOT NULL,             -- epoch seconds (matches TurnManifest.started_at)
      duration_ms_total REAL NOT NULL,
      answer_type TEXT,
      confidence REAL,
      classification_reason TEXT,
      dispatch TEXT,
      user_text TEXT NOT NULL,
      wedge TEXT,                           -- JSON-serialized WedgeRecord (nullable)
      modules_run TEXT NOT NULL,            -- JSON-serialized list[ModuleExecutionRecord]
      modules_skipped TEXT NOT NULL,        -- JSON-serialized list[ModuleSkipRecord]
      llm_calls_summary TEXT NOT NULL,      -- JSON-serialized list[LLMCallSummary]
      tool_calls TEXT NOT NULL,             -- JSON-serialized list[ToolCallRecord]
      notes TEXT NOT NULL                   -- JSON-serialized list[str]
  );
  CREATE INDEX IF NOT EXISTS turn_traces_conv_idx
      ON turn_traces(conversation_id, started_at);
  CREATE INDEX IF NOT EXISTS turn_traces_started_at_idx
      ON turn_traces(started_at);
  ```
  All JSON columns serialize what `TurnManifest.to_jsonable()` already
  produces — no new shape work.
- Add a new method on `ConversationStore`:
  ```python
  def insert_turn_trace(self, manifest_dict: dict[str, Any]) -> None: ...
  ```
  Takes the dict produced by `TurnManifest.to_jsonable()`. Wraps each
  insert in try/except — see "Failure semantics" below.
- Wire the write into [`api/main.py:270`](api/main.py#L270). Replace the
  bare `end_turn()` in the `finally` with:
  ```python
  finally:
      finalized = end_turn()
      if finalized is not None:
          try:
              store.insert_turn_trace(finalized.to_jsonable())
          except Exception as exc:
              print(f"[turn_traces] persist failed for {finalized.turn_id}: {exc}", flush=True)
  ```

**Tests** (new file `tests/api/test_turn_traces.py`):
- `test_insert_turn_trace_round_trips_basic_manifest` — insert a manifest
  dict, read it back via raw SQL, assert all top-level fields are
  preserved and JSON columns deserialize cleanly.
- `test_insert_turn_trace_handles_minimal_manifest` — manifest with only
  required fields (no wedge, no llm_calls, empty notes). Should not raise.
- `test_insert_turn_trace_swallows_db_error` — simulate a write failure
  (e.g., monkeypatch the connection to raise). Outer call must not
  propagate; assert no row inserted but no exception bubbled.
- `test_finalize_path_persists_when_end_turn_fires` — integration-shaped:
  call `start_turn`/`end_turn` around a fake turn body, assert exactly one
  row inserted via the `_finalize` wiring. Mocks the SSE generator.

**Verification.**
- Live dev: chat one BROWSE turn end-to-end, then run
  `sqlite3 data/web/conversations.db 'SELECT turn_id, answer_type,
  duration_ms_total, json_array_length(modules_run) FROM turn_traces
  ORDER BY started_at DESC LIMIT 1;'`. Expect one row with the right shape.
- No regression in chat UX: latency, prose, charts unchanged.

**Estimate:** 2-3 hours.
**Risk:** Low. Schema is additive; write is exception-safe; no read path
exists yet so a corrupt insert can't break a future turn.

---

### Cycle 2 — `data/llm_calls.jsonl` sink

**Status:** Not started.

**Scope.**
- Extend `LLMCallLedger.append(record)` at
  [`briarwood/agent/llm_observability.py:73`](briarwood/agent/llm_observability.py#L73)
  with a JSONL-write side effect. Sketch:
  ```python
  _JSONL_PATH = Path(os.environ.get("BRIARWOOD_LLM_JSONL_PATH",
                                    "data/llm_calls.jsonl"))

  def append(self, record: LLMCallRecord) -> None:
      self.records.append(record)
      _logger.info("llm_call %s", asdict(record))
      try:
          # Mirror into per-turn manifest (existing).
          ...
      except Exception:
          pass
      try:
          self._write_jsonl(record)
      except Exception as exc:
          _logger.warning("llm_calls.jsonl write failed: %s", exc)

  def _write_jsonl(self, record: LLMCallRecord) -> None:
      payload = asdict(record)
      if not self.debug_payloads_enabled:
          payload.pop("debug_payload", None)
      _JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
      with _JSONL_PATH.open("a", encoding="utf-8") as f:
          f.write(json.dumps(payload, default=str) + "\n")
  ```
- Add ISO-8601 `recorded_at` to the JSONL line (the dataclass doesn't
  carry an absolute timestamp today — the manifest's `started_at` is
  per-turn, not per-call). Sourced from `datetime.now(timezone.utc)` at
  write time. Avoid mutating the dataclass — set it in the dict on the
  way out.
- File-locking is unnecessary: SQLite already serializes per-process
  writes via the existing `_lock`, and the JSONL is append-only with
  fixed-size (~few-KB) lines. POSIX append-mode writes under the typical
  buffer size are atomic enough for this purpose.

**Tests** (extend `tests/agent/test_llm_observability.py`):
- `test_append_writes_jsonl_line_when_enabled` — point `BRIARWOOD_LLM_JSONL_PATH`
  at a tmp file, append a record, assert one line written, JSON decodes
  cleanly, fields match.
- `test_append_omits_debug_payload_when_flag_unset` — set
  `debug_payload={"system": "...", "user": "..."}` on the record, assert
  the JSONL line has NO `debug_payload` key by default.
- `test_append_includes_debug_payload_when_flag_set` — flip
  `BRIARWOOD_LLM_DEBUG_PAYLOADS=1`, assert the JSONL line carries
  `debug_payload`.
- `test_append_swallows_write_error` — point the env var at an
  unwritable path, assert `append` does not raise.
- `test_append_preserves_existing_manifest_mirror` — existing
  `record_llm_call_summary` mirror keeps working alongside the JSONL
  write (regression guard).

**Verification.**
- Live dev: chat one DECISION turn (which fires multiple LLM calls).
  Inspect `tail -f data/llm_calls.jsonl` during the turn — expect one
  line per LLM call.
- `wc -l data/llm_calls.jsonl` after a few turns — line count grows
  monotonically.
- `BRIARWOOD_LLM_DEBUG_PAYLOADS=1 venv/bin/python -m api.main` for one
  manual run — confirm payloads appear, then unset and confirm they
  vanish from new lines.

**Estimate:** 1-2 hours.
**Risk:** Low. Existing ledger contract preserved; JSONL is append-only;
write failures degrade silently (per the project's "observability must
never break a turn" pattern at `llm_observability.py:90`).

---

### Cycle 3 — `messages` metric columns

**Status:** Not started.

**Scope.**
- Extend `_init_schema` at
  [`api/store.py:48`](api/store.py#L48) to add columns. SQLite ALTER
  TABLE pattern:
  ```python
  # Inside _init_schema, after the CREATE TABLE block:
  for column, ddl in [
      ("latency_ms",     "ALTER TABLE messages ADD COLUMN latency_ms INTEGER"),
      ("answer_type",    "ALTER TABLE messages ADD COLUMN answer_type TEXT"),
      ("success_flag",   "ALTER TABLE messages ADD COLUMN success_flag INTEGER"),
      ("turn_trace_id",  "ALTER TABLE messages ADD COLUMN turn_trace_id TEXT REFERENCES turn_traces(turn_id) ON DELETE SET NULL"),
  ]:
      try:
          conn.execute(ddl)
      except sqlite3.OperationalError:
          pass  # column already exists
  ```
  Per-column try/except is the standard SQLite idempotent-migration
  idiom — no version table needed.
- Add a new helper to `ConversationStore`:
  ```python
  def attach_turn_metrics(
      self,
      message_id: str,
      *,
      turn_trace_id: str | None,
      latency_ms: int | None,
      answer_type: str | None,
      success_flag: bool | None,
  ) -> None:
      with self._conn() as conn:
          conn.execute(
              """UPDATE messages SET
                     turn_trace_id = ?,
                     latency_ms = ?,
                     answer_type = ?,
                     success_flag = ?
                 WHERE id = ?""",
              (turn_trace_id, latency_ms, answer_type,
               int(success_flag) if success_flag is not None else None,
               message_id),
          )
  ```
- Wire from [`api/main.py:398-401`](api/main.py#L398-L401). Order matters
  — `assistant_msg = store.add_message(...)` runs first (existing line
  398), then either:
  - **Option A (recommended):** Update the assistant message AFTER
    `end_turn()` collects the manifest. Refactor: read the active
    manifest BEFORE end_turn returns it (via `current_manifest()` at
    line 157 of turn_manifest), capture `turn_id`, `answer_type`,
    `duration_ms_total`, then update the message row in the outer
    `finally`. Sketch:
    ```python
    finally:
        manifest_in_flight = current_manifest()
        finalized = end_turn()
        if finalized is not None:
            try:
                store.insert_turn_trace(finalized.to_jsonable())
            except Exception as exc:
                print(f"[turn_traces] persist failed: {exc}", flush=True)
            try:
                # assistant_msg may not exist if the inner generator errored
                # before line 398 — guard with a nonlocal sentinel.
                if assistant_msg_id is not None:
                    store.attach_turn_metrics(
                        message_id=assistant_msg_id,
                        turn_trace_id=finalized.turn_id,
                        latency_ms=int(finalized.duration_ms_total),
                        answer_type=finalized.answer_type,
                        success_flag=True,  # see decision #2 below
                    )
            except Exception as exc:
                print(f"[messages.metrics] update failed: {exc}", flush=True)
    ```
    Requires hoisting `assistant_msg_id` into the outer scope as
    `None`-initialized.
  - **Option B:** Insert the assistant message AFTER `end_turn()`. Bigger
    refactor (the SSE `message_event` is currently emitted inside the
    inner generator at line 401, before the response stream closes).
    Likely user-visible reordering. Don't pursue.

**Tests** (extend `tests/api/test_store.py` if it exists; otherwise new
`tests/api/test_messages_metrics.py`):
- `test_init_schema_idempotent_when_columns_exist` — call
  `_init_schema` twice on the same DB; assert no exception, columns
  unchanged.
- `test_attach_turn_metrics_updates_row` — insert message, attach
  metrics, read back via raw SQL.
- `test_attach_turn_metrics_handles_missing_message` — call with a
  non-existent message_id; assert no exception (UPDATE on no rows is
  legal).
- `test_assistant_message_carries_metrics_after_turn` — integration:
  post a chat turn through the test client, assert the resulting
  assistant message row has non-NULL `turn_trace_id`, `latency_ms`,
  `answer_type`. Mocks the LLM/router as needed.

**Verification.**
- Live dev: chat one turn, then
  `sqlite3 data/web/conversations.db 'SELECT id, role, latency_ms,
  answer_type, turn_trace_id FROM messages ORDER BY created_at DESC
  LIMIT 4;'`. Expect the latest assistant row to have non-NULL metric
  fields and the latest user row to have NULL fields (no metrics on
  user messages).
- The full SQL the success criteria asks for:
  `SELECT answer_type, AVG(duration_ms_total) FROM turn_traces GROUP BY 1;`

**Estimate:** 1-2 hours.
**Risk:** Low-Medium. The refactor at `api/main.py:398-401` touches the
hot streaming path — keep the change surgical, assert the SSE event
ordering test still passes.

---

### Cycle 4 — Closeout + observability of observability

**Status:** Not started.

**Scope.**
- Smoke matrix: chat one of each AnswerType (BROWSE, DECISION,
  LOOKUP, EDGE, RESEARCH, RENT_LOOKUP, CHITCHAT). For each, assert one
  `turn_traces` row, ≥1 `llm_calls.jsonl` line, and the assistant
  `messages` row carries the metric columns.
- README updates per
  [`.claude/skills/readme-discipline/SKILL.md`](.claude/skills/readme-discipline/SKILL.md)
  Job 3:
  - `briarwood/agent/llm_observability.py` has no README today (helper
    module). If this stage promotes it past helper status, decide
    whether a README is warranted. Recommendation: skip for now;
    inline docstrings are sufficient for a write-only sink.
  - No existing module README is meaningfully changed by this stage —
    `TurnManifest`'s contract is unchanged (it still produces the same
    `to_jsonable` shape).
- `ARCHITECTURE_CURRENT.md` update: add a new "Persistence" section
  describing `turn_traces`, `llm_calls.jsonl`, and the message-metric
  columns.
- `TOOL_REGISTRY.md`: no changes (these aren't tools — they're
  observability artifacts).
- ROADMAP closeout: mark §3.1 Stage 1 ✅ with `**Status:**` line and
  add a row to §10 Resolved Index per the convention adopted
  2026-04-28.
- Follow-on tickets to file under §3.1 Stage 2 (next sequence step):
  - JSONL rotation/compaction policy (operational concern; defer until
    file size becomes an issue, but file the placeholder now).
  - Top-level analytic queries to seed Stage 3's dashboard (defer
    actual queries to Stage 3 — but a "what would we want to see?"
    sketch is cheap to draft now).

**Tests:** Existing tests stay green. The new tests from Cycles 1-3
are the regression net.

**Verification.** Browser smoke + the `sqlite3` query from the success
criteria. **The owner-visible payoff is being able to answer "what was
the slowest turn this week" with a single SQL query.**

**Estimate:** 1-2 hours.
**Risk:** Low.

---

## Open design decisions

(Resolve at the start of the named cycle.)

1. **`turn_traces.user_text` — full text or truncated?** Cycle 1.
   Recommendation: full text. The volume is bounded (~hundreds of bytes
   per turn) and dropping it kills the most useful debugging affordance.
   PII concern is no different from `messages.content` which already
   stores full user text.

2. **`messages.success_flag` semantics.** Cycle 3. What counts as
   "success"? Three readable definitions:
   - (a) Manifest reached `end_turn` without exception (current
     recommendation — easiest to populate).
   - (b) No `events.error(...)` emitted during the stream (more
     restrictive; surfaces classifier failures and SearchAPI fallbacks
     as success=False).
   - (c) The user followed up positively (depends on Stage 2 feedback
     loop — doesn't exist yet).
   Recommendation: (a) for v1; revisit when Stage 2 lands.

3. **JSONL path env override naming.** Cycle 2. Today
   `BRIARWOOD_WEB_DB` exists for the SQLite path. Suggested
   `BRIARWOOD_LLM_JSONL_PATH` mirrors the convention. Confirm at
   Cycle 2 start.

4. **Concurrency posture for JSONL writes.** Cycle 2. Single-process
   web server today; multi-process would need file-locking or a per-PID
   filename. Recommendation: assume single-process (matches the
   SQLite store's `threading.Lock`-based serialization). File a
   follow-on if the deployment shape changes.

5. **Should `turn_traces.user_text` and `messages.content` deduplicate?**
   Cycle 1. They carry the same string today (the user's message body).
   Two reasonable answers:
   - (a) Keep both — `turn_traces` is queryable on its own without
     joining `messages`. Storage cost is negligible.
   - (b) Drop `user_text` from `turn_traces`; require a join on
     `messages` (via a yet-to-be-added FK) to recover the text.
   Recommendation: (a). The whole point of `turn_traces` is fast SQL
   without joins.

6. **`turn_traces.conversation_id` ON DELETE behavior.** Cycle 1.
   `messages` uses `ON DELETE CASCADE` — deleting a conversation deletes
   its messages. Should it also delete the traces? Recommendation: NO,
   use `ON DELETE SET NULL`. Traces are observability data; preserving
   them past conversation deletion is useful for "how did our latency
   trend over the last 30 days regardless of which conversations
   survived?" analyses. This is a deliberate divergence from the
   `messages` cascade.

7. **Should `LLMCallLedger.clear()` truncate the JSONL?** Cycle 2.
   Today `clear()` resets the in-memory list; tests use this between
   runs. Recommendation: NO. JSONL is durable; tests should point
   `BRIARWOOD_LLM_JSONL_PATH` at a tmp file instead.

---

## Cycle ordering rationale

- **Cycle 1 first** because `messages.turn_trace_id` (Cycle 3) FKs into
  `turn_traces`. Cycle 3 cannot run cleanly before Cycle 1 has the table.
- **Cycle 2 anywhere relative to 1 and 3** — the JSONL sink is fully
  decoupled from the SQLite store. Could go in parallel with Cycle 1
  if you want to spread the work; recommended order is 1 → 2 → 3 so
  each cycle's verification builds on the prior cycle's substrate.
- **Cycle 4 last** because it covers the closeout and ROADMAP update.

If you want a one-cycle MVP for a partial-day session: do **Cycle 1
only**. It produces immediate owner-visible value (the SQL query
works), Cycles 2 and 3 are independently approvable adds, and the
contract is set up so they don't refactor anything Cycle 1 lands.

---

## Failure semantics

The pattern across all three cycles: **observability must never break a
turn.**

- Every persistence write is wrapped in `try: ... except Exception:`.
- Failures log via `print(...)` with a recognizable prefix
  (`[turn_traces]`, `[llm_calls.jsonl]`, `[messages.metrics]`) and
  continue.
- The chat response stream remains unaffected. The user sees the same
  prose / charts / suggestions whether persistence succeeded or not.

This mirrors the existing patterns at:
- [`briarwood/agent/llm_observability.py:90`](briarwood/agent/llm_observability.py#L90)
  ("observability must never break a turn" — same phrasing).
- [`api/pipeline_adapter.py:193`](api/pipeline_adapter.py#L193)
  (`# never break a turn on persistence` for `_finalize_session`).

---

## Tests

**Existing tests must stay green.** The full pre-handoff baseline is
1496 passed / 16 failed (all 16 pre-existing per ROADMAP — verified by
stash-and-rerun on 2026-04-28).

**New tests** per cycle (see each cycle's "Tests" subsection above).
Total expected new test count: ~10-12.

**Manual verification gates:**
- After Cycle 1: SQL query against `turn_traces` returns one row per
  chat turn.
- After Cycle 2: `tail -f data/llm_calls.jsonl` during a turn shows one
  line per LLM call.
- After Cycle 3: assistant `messages` rows carry the metric columns.
- After Cycle 4: smoke matrix across BROWSE / DECISION / LOOKUP / EDGE
  / RESEARCH / RENT_LOOKUP / CHITCHAT.

---

## ROADMAP closures (anticipated)

- §3.1 Stage 1 *Persist Every Action* — RESOLVED on landing. Mark §10
  Resolved Index.
- §1 sequence step 2 — RESOLVED on landing.
- The `2026-04-24 — Add a shared LLM call ledger` entry already
  absorbed into §3.1 Stage 1 per §8 Dedup log row 1; closing Stage 1
  closes that absorbed item too.

---

## Boot prompt for the next Claude context window

```
I'm starting AI-Native Foundation Stage 1 (sequence step 2 in
ROADMAP.md §1). Plan is in PERSISTENCE_HANDOFF_PLAN.md.

Phase 4a Cycle 6 closed 2026-04-28 — graft retired, audit docs
reconciled, ROADMAP.md status convention adopted (✅ prefix +
**Status:** line + §10 Resolved Index). I'm picking up Stage 1 fresh.

Per CLAUDE.md, before any code:
1. Re-read CLAUDE.md, DECISIONS.md, ROADMAP.md.
2. Run README drift check (.claude/skills/readme-discipline/SKILL.md
   Job 1) — only `briarwood/agent/llm_observability.py` (no README
   today) and `api/store.py` are in scope; everything else is read-only
   for this stage.
3. Read PERSISTENCE_HANDOFF_PLAN.md in full.
4. Confirm full test suite baseline (16 pre-existing failures,
   verified 2026-04-28).

The plan has 4 cycles; Cycle 1 (turn_traces table + write path) is the
critical-path move. Cycle 4 closes Stage 1 in ROADMAP.md per the
convention adopted 2026-04-28.

Open design decisions are in the plan §"Open design decisions" —
defaults are recommended; pause at the start of each cycle to confirm
or override.
```

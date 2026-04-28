"""SQLite-backed conversation store.

Owned by the Python side per the v0 architecture decision: the router/orchestrator
will need cross-turn memory anyway, so conversations live here and the web client
reads them through the FastAPI bridge.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "web" / "conversations.db"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class ConversationStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or os.environ.get("BRIARWOOD_WEB_DB", DEFAULT_DB_PATH))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    events TEXT,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_conv_idx
                    ON messages(conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS turn_traces (
                    turn_id TEXT PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                    started_at REAL NOT NULL,
                    duration_ms_total REAL NOT NULL,
                    answer_type TEXT,
                    confidence REAL,
                    classification_reason TEXT,
                    dispatch TEXT,
                    user_text TEXT NOT NULL,
                    wedge TEXT,
                    modules_run TEXT NOT NULL,
                    modules_skipped TEXT NOT NULL,
                    llm_calls_summary TEXT NOT NULL,
                    tool_calls TEXT NOT NULL,
                    notes TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS turn_traces_conv_idx
                    ON turn_traces(conversation_id, started_at);
                CREATE INDEX IF NOT EXISTS turn_traces_started_at_idx
                    ON turn_traces(started_at);
                CREATE TABLE IF NOT EXISTS feedback (
                    message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                    turn_trace_id TEXT REFERENCES turn_traces(turn_id) ON DELETE SET NULL,
                    rating TEXT NOT NULL,
                    comment TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS feedback_conv_idx
                    ON feedback(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS feedback_rating_idx
                    ON feedback(rating, created_at);
                """
            )
            # Idempotent forward-only migrations on the messages table.
            # SQLite ADD COLUMN raises OperationalError when the column
            # already exists — caught per-column so re-running the schema
            # init is a no-op once the columns are in place.
            for ddl in (
                "ALTER TABLE messages ADD COLUMN latency_ms INTEGER",
                "ALTER TABLE messages ADD COLUMN answer_type TEXT",
                "ALTER TABLE messages ADD COLUMN success_flag INTEGER",
                "ALTER TABLE messages ADD COLUMN turn_trace_id TEXT "
                "REFERENCES turn_traces(turn_id) ON DELETE SET NULL",
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass

    def create_conversation(self, title: str | None = None) -> dict[str, Any]:
        cid = _new_id()
        ts = _now_ms()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (cid, title or "New chat", ts, ts),
            )
        return {"id": cid, "title": title or "New chat", "created_at": ts, "updated_at": ts}

    def list_conversations(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None
            # LEFT JOIN feedback so a page refresh can render the user's
            # prior thumbs state on assistant messages without a second
            # round-trip. Non-assistant rows always carry user_rating=NULL.
            msgs = conn.execute(
                """SELECT m.id, m.role, m.content, m.events, m.created_at,
                          f.rating AS user_rating
                   FROM messages m
                   LEFT JOIN feedback f ON f.message_id = m.id
                   WHERE m.conversation_id = ?
                   ORDER BY m.created_at ASC""",
                (conversation_id,),
            ).fetchall()
        messages = []
        for m in msgs:
            messages.append(
                {
                    "id": m["id"],
                    "role": m["role"],
                    "content": m["content"],
                    "events": json.loads(m["events"]) if m["events"] else [],
                    "created_at": m["created_at"],
                    "user_rating": m["user_rating"],
                }
            )
        conv = dict(row)
        conv["messages"] = messages
        return conv

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mid = _new_id()
        ts = _now_ms()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, events, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mid, conversation_id, role, content, json.dumps(events) if events else None, ts),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conversation_id)
            )
        return {"id": mid, "role": role, "content": content, "events": events or [], "created_at": ts}

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now_ms(), conversation_id),
            )

    def delete_conversation(self, conversation_id: str) -> None:
        with self._conn() as conn:
            # FK enforcement is off project-wide, so the CASCADE / SET NULL
            # declarations are documentation only. Apply them explicitly:
            # feedback first (FKs into messages, which we're about to delete),
            # then messages, then null-out turn_traces, then the conversation.
            conn.execute(
                "DELETE FROM feedback WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute(
                "UPDATE turn_traces SET conversation_id = NULL WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def attach_turn_metrics(
        self,
        message_id: str,
        *,
        turn_trace_id: str | None,
        latency_ms: int | None,
        answer_type: str | None,
        success_flag: bool | None,
    ) -> None:
        """Backfill the per-turn metric columns on an assistant message row.

        Called once per turn from the chat endpoint's finally block, after
        the manifest has been finalized. Observability must never break a
        turn — failures (including a missing message_id) are logged with
        the ``[messages.metrics]`` prefix and swallowed."""
        try:
            with self._conn() as conn:
                conn.execute(
                    """UPDATE messages SET
                           turn_trace_id = ?,
                           latency_ms = ?,
                           answer_type = ?,
                           success_flag = ?
                       WHERE id = ?""",
                    (
                        turn_trace_id,
                        latency_ms,
                        answer_type,
                        int(success_flag) if success_flag is not None else None,
                        message_id,
                    ),
                )
        except Exception as exc:  # noqa: BLE001 — observability must never break a turn
            print(
                f"[messages.metrics] update failed for {message_id}: {exc}",
                flush=True,
            )

    def upsert_feedback(
        self,
        *,
        message_id: str,
        rating: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Upsert a thumbs rating for an assistant message.

        Resolves ``conversation_id`` and ``turn_trace_id`` from the
        message's row so the feedback row is queryable without a join.
        Last-write-wins on revision (PRIMARY KEY on ``message_id``).

        Returns a dict with the resolved row plus ``answer_type`` (from
        ``messages``) and ``confidence`` (from ``turn_traces`` via the
        message's ``turn_trace_id``) so the API layer can build the
        analyzer mirror record without re-querying.

        Raises ValueError when ``message_id`` does not exist or refers
        to a non-assistant role — the API layer translates to 404 / 422.
        """
        ts = _now_ms()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT m.id, m.conversation_id, m.role, m.turn_trace_id,
                          m.answer_type AS message_answer_type,
                          t.confidence AS turn_confidence,
                          t.answer_type AS turn_answer_type
                   FROM messages m
                   LEFT JOIN turn_traces t ON t.turn_id = m.turn_trace_id
                   WHERE m.id = ?""",
                (message_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown message_id: {message_id}")
            if row["role"] != "assistant":
                raise ValueError(
                    f"feedback only allowed on assistant messages "
                    f"(message {message_id} is role={row['role']!r})"
                )
            existing = conn.execute(
                "SELECT created_at FROM feedback WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else ts
            conn.execute(
                """INSERT OR REPLACE INTO feedback (
                       message_id, conversation_id, turn_trace_id,
                       rating, comment, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    row["conversation_id"],
                    row["turn_trace_id"],
                    rating,
                    comment,
                    created_at,
                    ts,
                ),
            )
            answer_type = row["message_answer_type"] or row["turn_answer_type"]
            return {
                "message_id": message_id,
                "conversation_id": row["conversation_id"],
                "turn_trace_id": row["turn_trace_id"],
                "rating": rating,
                "comment": comment,
                "created_at": created_at,
                "updated_at": ts,
                "answer_type": answer_type,
                "confidence": row["turn_confidence"],
            }

    def recent_feedback_for_conversation(
        self,
        conversation_id: str,
        *,
        since_ms: int | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Most-recent feedback rows for a conversation, newest first.

        Used by the Cycle 3 read-back consumer to detect a recent
        thumbs-down within the same conversation. Failure-safe at the
        caller — the synthesizer must never break on a feedback read.
        """
        params: list[Any] = [conversation_id]
        clause = ""
        if since_ms is not None:
            clause = " AND created_at >= ?"
            params.append(since_ms)
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT message_id, conversation_id, turn_trace_id,
                           rating, comment, created_at, updated_at
                    FROM feedback
                    WHERE conversation_id = ?{clause}
                    ORDER BY created_at DESC
                    LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Stage 3 admin queries ──────────────────────────────────────
    # Read-only helpers powering the admin dashboard. Each returns a
    # plain dict / list of dicts so the admin endpoint can json-encode
    # without further shaping.

    def latency_durations_by_answer_type(
        self,
        *,
        since_seconds: float,
    ) -> dict[str, list[float]]:
        """Return {answer_type: [duration_ms, ...]} for turns started
        on/after ``since_seconds``.

        Raw durations rather than aggregates because SQLite has no
        PERCENTILE_CONT and the dashboard wants p50/p95 — caller computes
        percentiles in Python over the returned arrays."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT answer_type, duration_ms_total
                   FROM turn_traces
                   WHERE started_at >= ?
                     AND duration_ms_total IS NOT NULL""",
                (float(since_seconds),),
            ).fetchall()
        out: dict[str, list[float]] = {}
        for r in rows:
            key = r["answer_type"] or "unclassified"
            out.setdefault(key, []).append(float(r["duration_ms_total"]))
        return out

    def thumbs_ratio_since(self, *, since_ms: int) -> dict[str, Any]:
        """Counts of ``"up"`` / ``"down"`` ratings since ``since_ms``.

        Uses the persisted ``rating`` column directly (no boundary
        translation here — the dashboard reads the wire vocabulary)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT rating, COUNT(*) AS c
                   FROM feedback
                   WHERE created_at >= ?
                   GROUP BY rating""",
                (int(since_ms),),
            ).fetchall()
        counts = {r["rating"]: int(r["c"]) for r in rows}
        up = counts.get("up", 0)
        down = counts.get("down", 0)
        total = up + down
        ratio = (up / total) if total > 0 else None
        return {"up": up, "down": down, "total": total, "ratio": ratio}

    def top_slowest_turns(
        self,
        *,
        since_seconds: float,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Slowest turns in the window, newest first when ties exist."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT turn_id, conversation_id, started_at,
                          duration_ms_total, answer_type, confidence,
                          dispatch, user_text
                   FROM turn_traces
                   WHERE started_at >= ?
                   ORDER BY duration_ms_total DESC, started_at DESC
                   LIMIT ?""",
                (float(since_seconds), int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_turn_trace(self, turn_id: str) -> dict[str, Any] | None:
        """Full row for one turn, with JSON columns deserialized.

        Returns None when the turn_id is unknown — the admin endpoint
        translates to 404."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT turn_id, conversation_id, started_at,
                          duration_ms_total, answer_type, confidence,
                          classification_reason, dispatch, user_text,
                          wedge, modules_run, modules_skipped,
                          llm_calls_summary, tool_calls, notes
                   FROM turn_traces
                   WHERE turn_id = ?""",
                (turn_id,),
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        for col in (
            "wedge",
            "modules_run",
            "modules_skipped",
            "llm_calls_summary",
            "tool_calls",
            "notes",
        ):
            raw = out.get(col)
            if raw is None or raw == "":
                continue
            try:
                out[col] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                # Leave the raw string in place so the dashboard can
                # surface a corrupt-row signal rather than crashing.
                pass
        return out

    def feedback_for_turn(self, turn_id: str) -> list[dict[str, Any]]:
        """Ratings on any message belonging to the given turn.

        Joined via ``messages.turn_trace_id`` (set by Stage 1's metric
        backfill in the API's finally block). Empty list when no
        message in the turn has been rated."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT f.message_id, f.rating, f.comment,
                          f.created_at, f.updated_at
                   FROM feedback f
                   JOIN messages m ON m.id = f.message_id
                   WHERE m.turn_trace_id = ?
                   ORDER BY f.updated_at DESC""",
                (turn_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_turn_trace(self, manifest: dict[str, Any]) -> None:
        """Persist a finalized TurnManifest dict (from
        ``TurnManifest.to_jsonable()``) into the ``turn_traces`` table.

        Observability must never break a turn — any failure here is logged
        with the ``[turn_traces]`` prefix and swallowed."""
        try:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO turn_traces (
                        turn_id, conversation_id, started_at, duration_ms_total,
                        answer_type, confidence, classification_reason, dispatch,
                        user_text, wedge, modules_run, modules_skipped,
                        llm_calls_summary, tool_calls, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        manifest["turn_id"],
                        manifest.get("conversation_id"),
                        float(manifest["started_at"]),
                        float(manifest.get("duration_ms_total") or 0.0),
                        manifest.get("answer_type"),
                        manifest.get("confidence"),
                        manifest.get("classification_reason"),
                        manifest.get("dispatch"),
                        manifest["user_text"],
                        json.dumps(manifest["wedge"]) if manifest.get("wedge") is not None else None,
                        json.dumps(manifest.get("modules_run") or []),
                        json.dumps(manifest.get("modules_skipped") or []),
                        json.dumps(manifest.get("llm_calls") or []),
                        json.dumps(manifest.get("tool_calls") or []),
                        json.dumps(manifest.get("notes") or []),
                    ),
                )
        except Exception as exc:  # noqa: BLE001 — observability must never break a turn
            turn_id = manifest.get("turn_id") if isinstance(manifest, dict) else "<unknown>"
            print(f"[turn_traces] persist failed for {turn_id}: {exc}", flush=True)


_default_store: ConversationStore | None = None


def get_store() -> ConversationStore:
    global _default_store
    if _default_store is None:
        _default_store = ConversationStore()
    return _default_store

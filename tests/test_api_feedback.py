from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    TestClient = None

try:
    from api.main import app
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    app = None

from api.store import ConversationStore


def _seed_assistant_message(
    store: ConversationStore,
    *,
    user_text: str = "what do you think of 1008 14th Ave",
    assistant_text: str = "Looking solid. Comp set supports the ask.",
    turn_trace: dict[str, object] | None = None,
) -> tuple[str, str]:
    """Seed a conversation + user msg + assistant msg + (optional) turn_trace.

    Returns ``(conversation_id, assistant_message_id)``."""
    conv = store.create_conversation(title="t")
    cid = conv["id"]
    store.add_message(cid, "user", user_text)
    assistant = store.add_message(cid, "assistant", assistant_text)
    if turn_trace is not None:
        # Insert the trace and update the message's turn_trace_id to match.
        manifest = {
            "turn_id": turn_trace["turn_id"],
            "conversation_id": cid,
            "started_at": turn_trace.get("started_at", time.time()),
            "duration_ms_total": turn_trace.get("duration_ms_total", 1234.0),
            "answer_type": turn_trace.get("answer_type"),
            "confidence": turn_trace.get("confidence"),
            "classification_reason": turn_trace.get("classification_reason"),
            "dispatch": turn_trace.get("dispatch"),
            "user_text": user_text,
            "wedge": None,
            "modules_run": [],
            "modules_skipped": [],
            "llm_calls": [],
            "tool_calls": [],
            "notes": [],
        }
        store.insert_turn_trace(manifest)
        # Backfill the FK on the assistant message.
        store.attach_turn_metrics(
            assistant["id"],
            turn_trace_id=str(turn_trace["turn_id"]),
            latency_ms=int(manifest["duration_ms_total"]),
            answer_type=str(turn_trace.get("answer_type") or ""),
            success_flag=True,
        )
    return cid, assistant["id"]


class _StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "test.db"
        self.store = ConversationStore(db_path=self.db_path)


class UpsertFeedbackStoreTests(_StoreCase):
    def test_upsert_feedback_creates_row(self) -> None:
        cid, mid = _seed_assistant_message(
            self.store,
            turn_trace={
                "turn_id": "abc123def456",
                "answer_type": "BROWSE",
                "confidence": 0.82,
                "classification_reason": "single property analysis",
                "dispatch": "browse_stream",
            },
        )

        row = self.store.upsert_feedback(message_id=mid, rating="up")

        self.assertEqual(row["message_id"], mid)
        self.assertEqual(row["conversation_id"], cid)
        self.assertEqual(row["turn_trace_id"], "abc123def456")
        self.assertEqual(row["rating"], "up")
        self.assertEqual(row["answer_type"], "BROWSE")
        self.assertAlmostEqual(row["confidence"], 0.82, places=4)

        # Persisted row matches the returned dict.
        with self.store._conn() as conn:
            db_row = conn.execute(
                "SELECT message_id, conversation_id, turn_trace_id, rating, comment, "
                "created_at, updated_at FROM feedback WHERE message_id = ?",
                (mid,),
            ).fetchone()
        self.assertIsNotNone(db_row)
        self.assertEqual(dict(db_row)["rating"], "up")
        self.assertEqual(dict(db_row)["turn_trace_id"], "abc123def456")
        self.assertIsNone(dict(db_row)["comment"])

    def test_upsert_feedback_replaces_on_revision(self) -> None:
        _, mid = _seed_assistant_message(self.store)

        first = self.store.upsert_feedback(message_id=mid, rating="up")
        # Force a millisecond gap so updated_at is monotonically greater.
        time.sleep(0.005)
        second = self.store.upsert_feedback(message_id=mid, rating="down")

        self.assertEqual(first["created_at"], second["created_at"])
        self.assertGreaterEqual(second["updated_at"], first["updated_at"])

        with self.store._conn() as conn:
            rows = conn.execute(
                "SELECT rating FROM feedback WHERE message_id = ?", (mid,)
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rating"], "down")

    def test_upsert_feedback_rejects_unknown_message(self) -> None:
        with self.assertRaises(ValueError):
            self.store.upsert_feedback(message_id="does-not-exist", rating="up")

    def test_upsert_feedback_rejects_non_assistant_role(self) -> None:
        conv = self.store.create_conversation(title="t")
        user_msg = self.store.add_message(conv["id"], "user", "hi")
        with self.assertRaises(ValueError):
            self.store.upsert_feedback(message_id=user_msg["id"], rating="up")

    def test_recent_feedback_for_conversation_returns_in_order(self) -> None:
        cid, mid_a = _seed_assistant_message(self.store)
        # Add a second assistant message in the same conversation.
        msg_b = self.store.add_message(cid, "assistant", "second reply")

        self.store.upsert_feedback(message_id=mid_a, rating="up")
        time.sleep(0.005)
        self.store.upsert_feedback(message_id=msg_b["id"], rating="down")

        rows = self.store.recent_feedback_for_conversation(cid, limit=5)
        self.assertEqual(len(rows), 2)
        # Newest first.
        self.assertEqual(rows[0]["message_id"], msg_b["id"])
        self.assertEqual(rows[0]["rating"], "down")
        self.assertEqual(rows[1]["message_id"], mid_a)

        # Limit honored.
        rows_capped = self.store.recent_feedback_for_conversation(cid, limit=1)
        self.assertEqual(len(rows_capped), 1)
        self.assertEqual(rows_capped[0]["message_id"], msg_b["id"])

    def test_get_conversation_rehydrates_user_rating(self) -> None:
        cid, mid_a = _seed_assistant_message(self.store)
        msg_b = self.store.add_message(cid, "assistant", "second reply")
        self.store.upsert_feedback(message_id=mid_a, rating="down")
        # msg_b deliberately has no rating — should rehydrate as None.

        conv = self.store.get_conversation(cid)
        self.assertIsNotNone(conv)
        by_id = {m["id"]: m for m in conv["messages"]}
        self.assertEqual(by_id[mid_a]["user_rating"], "down")
        self.assertIsNone(by_id[msg_b["id"]]["user_rating"])
        # The seeded user message also rehydrates with no rating.
        for m in conv["messages"]:
            if m["role"] == "user":
                self.assertIsNone(m["user_rating"])


@unittest.skipIf(TestClient is None or app is None, "fastapi is not installed in this environment")
class FeedbackEndpointTests(unittest.TestCase):
    """End-to-end POST /api/feedback against TestClient with a real store
    pointed at a tmp DB."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "test.db"
        self.store = ConversationStore(db_path=self.db_path)

        # Each test gets its own JSONL sink so writes are inspectable
        # without cross-test interference. The session-level redirect from
        # tests/conftest.py guarantees a tmp default; we override per-test
        # for fine-grained inspection.
        self._jsonl_path = Path(self._tmp.name) / "intelligence_feedback.jsonl"
        self._prev_jsonl = os.environ.get("BRIARWOOD_INTEL_FEEDBACK_PATH")
        os.environ["BRIARWOOD_INTEL_FEEDBACK_PATH"] = str(self._jsonl_path)

        self._client = TestClient(app)
        self._patcher = patch("api.main.get_store", return_value=self.store)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        if self._prev_jsonl is None:
            os.environ.pop("BRIARWOOD_INTEL_FEEDBACK_PATH", None)
        else:
            os.environ["BRIARWOOD_INTEL_FEEDBACK_PATH"] = self._prev_jsonl

    def test_post_returns_404_for_unknown_message(self) -> None:
        resp = self._client.post(
            "/api/feedback",
            json={"message_id": "does-not-exist", "rating": "up"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_post_writes_jsonl_mirror(self) -> None:
        _, mid = _seed_assistant_message(
            self.store,
            turn_trace={
                "turn_id": "trace-jsonl",
                "answer_type": "DECISION",
                "confidence": 0.71,
            },
        )

        resp = self._client.post(
            "/api/feedback",
            json={"message_id": mid, "rating": "down"},
        )
        self.assertEqual(resp.status_code, 200)

        # SQLite row exists.
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT rating FROM feedback WHERE message_id = ?", (mid,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["rating"], "down")

        # JSONL line written with the post-translation rating ("no") and
        # the message metadata captured.
        lines = self._jsonl_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["feedback_type"], "user_validation")
        self.assertEqual(record["rating"], "no")
        self.assertEqual(record["analysis_id"], mid)
        self.assertEqual(record["analysis_decision"], "DECISION")
        self.assertAlmostEqual(record["analysis_confidence"], 0.71, places=4)
        self.assertIn("user-feedback-no", record["tags"])

    def test_post_swallows_jsonl_mirror_error(self) -> None:
        _, mid = _seed_assistant_message(self.store)

        with patch(
            "api.main.append_intelligence_capture",
            side_effect=RuntimeError("disk full"),
        ):
            resp = self._client.post(
                "/api/feedback",
                json={"message_id": mid, "rating": "up"},
            )

        # Endpoint returns 200 — observability must never break the action.
        self.assertEqual(resp.status_code, 200)
        # And the SQLite row was still committed.
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT rating FROM feedback WHERE message_id = ?", (mid,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["rating"], "up")

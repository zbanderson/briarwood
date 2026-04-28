"""Tests for the Stage 3 admin dashboard endpoints + data helpers.

Cycle 1 of DASHBOARD_HANDOFF_PLAN.md. Coverage:

Store-level
- ``latency_durations_by_answer_type`` filters by ``started_at`` window.
- ``thumbs_ratio_since`` honors the cutoff and computes the ratio.
- ``top_slowest_turns`` orders by duration, applies limit.
- ``get_turn_trace`` deserializes JSON columns and returns None for
  unknown ids.
- ``feedback_for_turn`` joins via ``messages.turn_trace_id``.

JSONL-level
- ``cost_by_surface`` aggregates a synthetic JSONL by surface +
  filters by recorded_at window.
- ``top_costliest_turns`` groups records by ``turn_id`` and ranks them.

Endpoint-level
- 404 when ``BRIARWOOD_ADMIN_ENABLED`` is unset.
- 200 with the expected shape when the gate is open.
- 404 for unknown turn_id at ``GET /api/admin/turns/{turn_id}``.
"""
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

from api.admin_metrics import (
    compose_metrics,
    compose_recent_turns,
    compose_turn_detail,
    cost_by_surface,
    latency_aggregates,
    top_costliest_turns,
)
from api.store import ConversationStore


def _seed_turn(
    store: ConversationStore,
    *,
    turn_id: str,
    conversation_id: str | None,
    started_at: float,
    duration_ms: float,
    answer_type: str,
    user_text: str = "u",
) -> None:
    manifest = {
        "turn_id": turn_id,
        "conversation_id": conversation_id,
        "started_at": started_at,
        "duration_ms_total": duration_ms,
        "answer_type": answer_type,
        "confidence": 0.7,
        "classification_reason": "seed",
        "dispatch": "browse_stream",
        "user_text": user_text,
        "wedge": None,
        "modules_run": [{"name": "valuation", "duration_ms": 12.0}],
        "modules_skipped": [],
        "llm_calls": [{"surface": "synthesis.llm", "duration_ms": 50.0}],
        "tool_calls": [],
        "notes": [],
    }
    store.insert_turn_trace(manifest)


class _StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "test.db"
        self.store = ConversationStore(db_path=self.db_path)
        # Make sure each test gets its own conversation row (FK source).
        self.cid = self.store.create_conversation(title="t")["id"]


class StoreAdminQueryTests(_StoreCase):
    def test_latency_durations_filters_by_window(self) -> None:
        now = time.time()
        _seed_turn(
            self.store,
            turn_id="recent",
            conversation_id=self.cid,
            started_at=now - 60,
            duration_ms=2000.0,
            answer_type="BROWSE",
        )
        _seed_turn(
            self.store,
            turn_id="ancient",
            conversation_id=self.cid,
            started_at=now - 86400 * 30,
            duration_ms=9999.0,
            answer_type="BROWSE",
        )

        out = self.store.latency_durations_by_answer_type(
            since_seconds=now - 86400 * 7
        )
        self.assertEqual(set(out.keys()), {"BROWSE"})
        self.assertEqual(out["BROWSE"], [2000.0])

    def test_top_slowest_turns_orders_and_limits(self) -> None:
        now = time.time()
        for tid, dur in [("a", 100.0), ("b", 500.0), ("c", 300.0)]:
            _seed_turn(
                self.store,
                turn_id=tid,
                conversation_id=self.cid,
                started_at=now - 60,
                duration_ms=dur,
                answer_type="DECISION",
            )
        rows = self.store.top_slowest_turns(since_seconds=now - 3600, limit=2)
        self.assertEqual([r["turn_id"] for r in rows], ["b", "c"])

    def test_get_turn_trace_deserializes_json_columns(self) -> None:
        now = time.time()
        _seed_turn(
            self.store,
            turn_id="abc",
            conversation_id=self.cid,
            started_at=now,
            duration_ms=42.0,
            answer_type="EDGE",
        )
        trace = self.store.get_turn_trace("abc")
        self.assertIsNotNone(trace)
        self.assertEqual(trace["answer_type"], "EDGE")
        self.assertIsInstance(trace["modules_run"], list)
        self.assertEqual(trace["modules_run"][0]["name"], "valuation")
        self.assertIsInstance(trace["llm_calls_summary"], list)

    def test_get_turn_trace_returns_none_for_unknown(self) -> None:
        self.assertIsNone(self.store.get_turn_trace("nope"))

    def test_thumbs_ratio_since_honors_cutoff(self) -> None:
        now_ms = int(time.time() * 1000)
        msg_a = self.store.add_message(self.cid, "assistant", "first")
        msg_b = self.store.add_message(self.cid, "assistant", "second")
        self.store.upsert_feedback(message_id=msg_a["id"], rating="up")
        self.store.upsert_feedback(message_id=msg_b["id"], rating="down")

        # Recent window covers both.
        out = self.store.thumbs_ratio_since(since_ms=now_ms - 60_000)
        self.assertEqual(out["up"], 1)
        self.assertEqual(out["down"], 1)
        self.assertEqual(out["total"], 2)
        self.assertAlmostEqual(out["ratio"], 0.5, places=4)

        # Window in the future excludes them.
        out_future = self.store.thumbs_ratio_since(since_ms=now_ms + 60_000)
        self.assertEqual(out_future["total"], 0)
        self.assertIsNone(out_future["ratio"])

    def test_feedback_for_turn_joins_via_message(self) -> None:
        now = time.time()
        _seed_turn(
            self.store,
            turn_id="trace1",
            conversation_id=self.cid,
            started_at=now,
            duration_ms=10.0,
            answer_type="BROWSE",
        )
        msg = self.store.add_message(self.cid, "assistant", "hi")
        self.store.attach_turn_metrics(
            msg["id"],
            turn_trace_id="trace1",
            latency_ms=10,
            answer_type="BROWSE",
            success_flag=True,
        )
        self.store.upsert_feedback(message_id=msg["id"], rating="down")
        rows = self.store.feedback_for_turn("trace1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rating"], "down")
        self.assertEqual(rows[0]["message_id"], msg["id"])


class JsonlAggregatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "calls.jsonl"

    def _write(self, records: list[dict[str, object]]) -> None:
        with self.path.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def test_cost_by_surface_aggregates_in_window(self) -> None:
        self._write(
            [
                {
                    "surface": "synthesis.llm",
                    "cost_usd": 0.005,
                    "duration_ms": 800,
                    "status": "success",
                    "recorded_at": "2026-04-28T12:00:00+00:00",
                },
                {
                    "surface": "synthesis.llm",
                    "cost_usd": 0.003,
                    "duration_ms": 600,
                    "status": "success",
                    "recorded_at": "2026-04-28T13:00:00+00:00",
                },
                {
                    "surface": "agent_router.classify",
                    "cost_usd": 0.0001,
                    "duration_ms": 50,
                    "status": "success",
                    "recorded_at": "2026-04-28T14:00:00+00:00",
                },
                # Outside window — excluded.
                {
                    "surface": "synthesis.llm",
                    "cost_usd": 9.99,
                    "duration_ms": 9999,
                    "status": "success",
                    "recorded_at": "2025-01-01T00:00:00+00:00",
                },
                # Corrupt record with no surface — counted under "unknown".
                {
                    "cost_usd": 0.0002,
                    "duration_ms": 10,
                    "status": "success",
                    "recorded_at": "2026-04-28T15:00:00+00:00",
                },
            ]
        )
        rows = cost_by_surface(
            since_iso="2026-04-28T00:00:00+00:00", jsonl_path=self.path
        )
        by_surface = {r["surface"]: r for r in rows}
        self.assertIn("synthesis.llm", by_surface)
        self.assertAlmostEqual(
            by_surface["synthesis.llm"]["total_cost_usd"], 0.008, places=6
        )
        self.assertEqual(by_surface["synthesis.llm"]["count"], 2)
        self.assertEqual(by_surface["unknown"]["count"], 1)
        # Sorted descending by cost.
        self.assertEqual(rows[0]["surface"], "synthesis.llm")

    def test_top_costliest_turns_groups_by_turn_id(self) -> None:
        self._write(
            [
                {
                    "turn_id": "T1",
                    "surface": "a",
                    "cost_usd": 0.01,
                    "recorded_at": "2026-04-28T10:00:00+00:00",
                },
                {
                    "turn_id": "T1",
                    "surface": "b",
                    "cost_usd": 0.02,
                    "recorded_at": "2026-04-28T10:00:01+00:00",
                },
                {
                    "turn_id": "T2",
                    "surface": "a",
                    "cost_usd": 0.005,
                    "recorded_at": "2026-04-28T10:00:02+00:00",
                },
                # No turn_id — excluded.
                {
                    "surface": "a",
                    "cost_usd": 99.0,
                    "recorded_at": "2026-04-28T10:00:03+00:00",
                },
            ]
        )
        rows = top_costliest_turns(
            since_iso="2026-04-28T00:00:00+00:00", limit=10, jsonl_path=self.path
        )
        self.assertEqual([r["turn_id"] for r in rows], ["T1", "T2"])
        self.assertAlmostEqual(rows[0]["total_cost_usd"], 0.03, places=6)
        self.assertEqual(rows[0]["call_count"], 2)

    def test_iter_handles_missing_file_gracefully(self) -> None:
        rows = cost_by_surface(
            since_iso="2026-04-28T00:00:00+00:00",
            jsonl_path=Path(self._tmp.name) / "does-not-exist.jsonl",
        )
        self.assertEqual(rows, [])

    def test_latency_aggregates_compute_p50_p95(self) -> None:
        out = latency_aggregates({"BROWSE": [100, 200, 300, 400, 500]})
        self.assertEqual(len(out), 1)
        row = out[0]
        self.assertEqual(row["count"], 5)
        self.assertEqual(row["avg_ms"], 300)
        self.assertEqual(row["p50_ms"], 300)
        # p95 with linear interp on [100,200,300,400,500]: rank = 0.95*4 = 3.8
        # → between 400 and 500, fraction 0.8 → 480.
        self.assertAlmostEqual(row["p95_ms"], 480, places=4)


@unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
class AdminEndpointGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "test.db"
        self.store = ConversationStore(db_path=self.db_path)
        # Per-test JSONL so test runs are isolated even when admin
        # endpoints read it under-the-hood.
        self._jsonl_path = Path(self._tmp.name) / "calls.jsonl"
        self._prev_jsonl = os.environ.get("BRIARWOOD_LLM_JSONL_PATH")
        os.environ["BRIARWOOD_LLM_JSONL_PATH"] = str(self._jsonl_path)

        self._client = TestClient(app)
        self._patcher = patch("api.main.get_store", return_value=self.store)
        self._patcher.start()
        # Default: gate is closed.
        self._prev_admin = os.environ.get("BRIARWOOD_ADMIN_ENABLED")
        os.environ.pop("BRIARWOOD_ADMIN_ENABLED", None)

    def tearDown(self) -> None:
        self._patcher.stop()
        if self._prev_jsonl is None:
            os.environ.pop("BRIARWOOD_LLM_JSONL_PATH", None)
        else:
            os.environ["BRIARWOOD_LLM_JSONL_PATH"] = self._prev_jsonl
        if self._prev_admin is None:
            os.environ.pop("BRIARWOOD_ADMIN_ENABLED", None)
        else:
            os.environ["BRIARWOOD_ADMIN_ENABLED"] = self._prev_admin

    def _seed_turn(self, turn_id: str, duration_ms: float = 100.0) -> None:
        cid = self.store.create_conversation(title="t")["id"]
        _seed_turn(
            self.store,
            turn_id=turn_id,
            conversation_id=cid,
            started_at=time.time() - 60,
            duration_ms=duration_ms,
            answer_type="BROWSE",
        )

    def test_metrics_returns_404_when_admin_disabled(self) -> None:
        resp = self._client.get("/api/admin/metrics")
        self.assertEqual(resp.status_code, 404)

    def test_recent_returns_404_when_admin_disabled(self) -> None:
        resp = self._client.get("/api/admin/turns/recent")
        self.assertEqual(resp.status_code, 404)

    def test_turn_detail_returns_404_when_admin_disabled(self) -> None:
        resp = self._client.get("/api/admin/turns/whatever")
        self.assertEqual(resp.status_code, 404)

    def test_metrics_returns_shape_when_admin_enabled(self) -> None:
        os.environ["BRIARWOOD_ADMIN_ENABLED"] = "1"
        self._seed_turn("t-1", duration_ms=250.0)
        resp = self._client.get("/api/admin/metrics?days=7")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["days"], 7)
        self.assertIn("latency_by_answer_type", body)
        self.assertIn("cost_by_surface", body)
        self.assertIn("thumbs", body)
        # Latency row shows our seeded turn.
        latency = {row["answer_type"]: row for row in body["latency_by_answer_type"]}
        self.assertIn("BROWSE", latency)
        self.assertEqual(latency["BROWSE"]["count"], 1)

    def test_turn_detail_404_for_unknown_turn(self) -> None:
        os.environ["BRIARWOOD_ADMIN_ENABLED"] = "1"
        resp = self._client.get("/api/admin/turns/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_turn_detail_returns_full_payload_when_admin_enabled(self) -> None:
        os.environ["BRIARWOOD_ADMIN_ENABLED"] = "1"
        self._seed_turn("t-detail", duration_ms=42.0)
        resp = self._client.get("/api/admin/turns/t-detail")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["trace"]["turn_id"], "t-detail")
        self.assertEqual(body["trace"]["answer_type"], "BROWSE")
        self.assertEqual(body["feedback"], [])


@unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
class ComposeIntegrationTests(_StoreCase):
    """Sanity-check that the compose helpers wire the store + JSONL
    aggregators together correctly. Not endpoint-level; exercises the
    same code path the endpoints call."""

    def setUp(self) -> None:
        super().setUp()
        # Repoint the JSONL to an empty per-test file so the
        # session-wide tmp JSONL (populated by other tests' LLM call
        # mocks) doesn't leak into compose_metrics / compose_recent_turns
        # — those helpers read the JSONL on every call.
        self._jsonl_path = Path(self._tmp.name) / "calls.jsonl"
        self._prev_jsonl = os.environ.get("BRIARWOOD_LLM_JSONL_PATH")
        os.environ["BRIARWOOD_LLM_JSONL_PATH"] = str(self._jsonl_path)

    def tearDown(self) -> None:
        if self._prev_jsonl is None:
            os.environ.pop("BRIARWOOD_LLM_JSONL_PATH", None)
        else:
            os.environ["BRIARWOOD_LLM_JSONL_PATH"] = self._prev_jsonl

    def test_compose_metrics_with_no_data_returns_empty_aggregates(self) -> None:
        out = compose_metrics(self.store, days=7)
        self.assertEqual(out["latency_by_answer_type"], [])
        self.assertEqual(out["cost_by_surface"], [])
        self.assertEqual(out["thumbs"]["total"], 0)

    def test_compose_recent_turns_with_no_data_returns_empty_lists(self) -> None:
        out = compose_recent_turns(self.store, days=7, limit=10)
        self.assertEqual(out["slowest"], [])
        self.assertEqual(out["costliest"], [])

    def test_compose_turn_detail_returns_none_for_unknown(self) -> None:
        self.assertIsNone(compose_turn_detail(self.store, "nope"))

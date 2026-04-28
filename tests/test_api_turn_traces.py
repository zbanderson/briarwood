from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from api.store import ConversationStore
from briarwood.agent.turn_manifest import (
    LLMCallSummary,
    ModuleExecutionRecord,
    ModuleSkipRecord,
    ToolCallRecord,
    TurnManifest,
    WedgeRecord,
    end_turn,
    record_classification,
    record_dispatch,
    record_module_run,
    record_note,
    start_turn,
)


class _StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "test.db"
        self.store = ConversationStore(db_path=self.db_path)

    def _make_conv(self) -> str:
        return self.store.create_conversation(title="t")["id"]

    def _populated_manifest(self, conv_id: str) -> dict:
        m = TurnManifest(
            turn_id="abc123def456",
            started_at=1700000000.0,
            user_text="what do you think of 1008 14th Ave",
            conversation_id=conv_id,
            answer_type="BROWSE",
            confidence=0.82,
            classification_reason="single property analysis",
            dispatch="browse_stream",
            wedge=WedgeRecord(
                fired=True, success=True, archetype="value_find", reason=None
            ),
            modules_run=[
                ModuleExecutionRecord(
                    name="valuation", source="run", mode="ok",
                    confidence=0.7, duration_ms=120.5, warnings_count=0,
                ),
                ModuleExecutionRecord(
                    name="risk_model", source="cache", mode="ok",
                    confidence=0.6, duration_ms=2.0, warnings_count=1,
                ),
            ],
            modules_skipped=[
                ModuleSkipRecord(name="opportunity_cost", reason="missing_priors"),
            ],
            llm_calls=[
                LLMCallSummary(
                    surface="agent_router.classify", provider="openai",
                    model="gpt-4o-mini", status="success",
                    duration_ms=312.0, attempts=1,
                ),
            ],
            tool_calls=[
                ToolCallRecord(
                    name="get_cma", duration_ms=812.5, status="success",
                    error_type=None,
                ),
            ],
            duration_ms_total=4321.0,
            notes=["browser smoke pass"],
        )
        return m.to_jsonable()


class InsertTurnTraceTests(_StoreCase):
    def test_insert_turn_trace_round_trips_basic_manifest(self) -> None:
        conv_id = self._make_conv()
        manifest = self._populated_manifest(conv_id)

        self.store.insert_turn_trace(manifest)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM turn_traces WHERE turn_id = ?",
                (manifest["turn_id"],),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["turn_id"], "abc123def456")
        self.assertEqual(row["conversation_id"], conv_id)
        self.assertAlmostEqual(row["started_at"], 1700000000.0)
        self.assertAlmostEqual(row["duration_ms_total"], 4321.0)
        self.assertEqual(row["answer_type"], "BROWSE")
        self.assertAlmostEqual(row["confidence"], 0.82)
        self.assertEqual(row["classification_reason"], "single property analysis")
        self.assertEqual(row["dispatch"], "browse_stream")
        self.assertEqual(row["user_text"], "what do you think of 1008 14th Ave")

        wedge = json.loads(row["wedge"])
        self.assertEqual(wedge["fired"], True)
        self.assertEqual(wedge["archetype"], "value_find")

        modules_run = json.loads(row["modules_run"])
        self.assertEqual(len(modules_run), 2)
        self.assertEqual(modules_run[0]["name"], "valuation")
        self.assertEqual(modules_run[1]["source"], "cache")

        modules_skipped = json.loads(row["modules_skipped"])
        self.assertEqual(modules_skipped[0]["reason"], "missing_priors")

        llm_calls = json.loads(row["llm_calls_summary"])
        self.assertEqual(llm_calls[0]["surface"], "agent_router.classify")
        self.assertEqual(llm_calls[0]["status"], "success")

        tool_calls = json.loads(row["tool_calls"])
        self.assertEqual(tool_calls[0]["name"], "get_cma")

        notes = json.loads(row["notes"])
        self.assertEqual(notes, ["browser smoke pass"])

    def test_insert_turn_trace_handles_minimal_manifest(self) -> None:
        manifest = TurnManifest(
            turn_id="min0000turn0",
            started_at=1700000000.0,
            user_text="hi",
        ).to_jsonable()

        self.store.insert_turn_trace(manifest)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM turn_traces WHERE turn_id = ?",
                (manifest["turn_id"],),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row["conversation_id"])
        self.assertIsNone(row["answer_type"])
        self.assertIsNone(row["confidence"])
        self.assertIsNone(row["wedge"])
        self.assertEqual(json.loads(row["modules_run"]), [])
        self.assertEqual(json.loads(row["modules_skipped"]), [])
        self.assertEqual(json.loads(row["llm_calls_summary"]), [])
        self.assertEqual(json.loads(row["tool_calls"]), [])
        self.assertEqual(json.loads(row["notes"]), [])

    def test_insert_turn_trace_swallows_db_error(self) -> None:
        manifest = TurnManifest(
            turn_id="errboom00000",
            started_at=1700000000.0,
            user_text="boom",
        ).to_jsonable()

        original_conn = self.store._conn

        def boom():  # type: ignore[no-untyped-def]
            raise sqlite3.OperationalError("simulated write failure")

        self.store._conn = boom  # type: ignore[assignment]
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                self.store.insert_turn_trace(manifest)
        finally:
            self.store._conn = original_conn  # type: ignore[assignment]

        self.assertIn("[turn_traces]", buf.getvalue())
        self.assertIn("errboom00000", buf.getvalue())
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM turn_traces WHERE turn_id = ?",
                (manifest["turn_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 0)


class FinalizePathPersistTests(_StoreCase):
    def test_finalize_path_persists_when_end_turn_fires(self) -> None:
        conv_id = self._make_conv()

        start_turn(user_text="why are these the comps?", conversation_id=conv_id)
        record_classification(
            answer_type="EDGE", confidence=0.71, reason="comp_set followup"
        )
        record_dispatch("dispatch_stream")
        record_module_run(
            name="comparable_sales", source="run", mode="ok",
            confidence=0.8, duration_ms=44.0,
        )
        record_note("test breadcrumb")

        finalized = end_turn()
        self.assertIsNotNone(finalized)
        assert finalized is not None
        self.store.insert_turn_trace(finalized.to_jsonable())

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM turn_traces WHERE conversation_id = ?",
                (conv_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["turn_id"], finalized.turn_id)
        self.assertEqual(row["answer_type"], "EDGE")
        self.assertGreaterEqual(row["duration_ms_total"], 0.0)
        modules_run = json.loads(row["modules_run"])
        self.assertEqual(modules_run[0]["name"], "comparable_sales")
        notes = json.loads(row["notes"])
        self.assertEqual(notes, ["test breadcrumb"])


class MessagesMetricColumnsTests(_StoreCase):
    def test_init_schema_idempotent_when_columns_exist(self) -> None:
        # Calling _init_schema twice on the same DB must not raise — the
        # ALTER TABLE ADD COLUMN raises sqlite3.OperationalError on
        # re-add, which the migration loop swallows per-column.
        self.store._init_schema()
        self.store._init_schema()
        with sqlite3.connect(self.db_path) as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        self.assertEqual(
            {"id", "conversation_id", "role", "content", "events", "created_at",
             "latency_ms", "answer_type", "success_flag", "turn_trace_id"},
            cols,
        )

    def test_attach_turn_metrics_updates_row(self) -> None:
        conv_id = self._make_conv()
        msg = self.store.add_message(conv_id, "assistant", "hello world")

        self.store.attach_turn_metrics(
            msg["id"],
            turn_trace_id="trace0000001",
            latency_ms=1234,
            answer_type="BROWSE",
            success_flag=True,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT turn_trace_id, latency_ms, answer_type, success_flag "
                "FROM messages WHERE id = ?",
                (msg["id"],),
            ).fetchone()
        self.assertEqual(row["turn_trace_id"], "trace0000001")
        self.assertEqual(row["latency_ms"], 1234)
        self.assertEqual(row["answer_type"], "BROWSE")
        self.assertEqual(row["success_flag"], 1)

    def test_attach_turn_metrics_handles_missing_message(self) -> None:
        # UPDATE on a non-existent id is legal SQL — zero rows affected.
        # Method must not raise.
        self.store.attach_turn_metrics(
            "doesnotexist",
            turn_trace_id="t",
            latency_ms=1,
            answer_type="LOOKUP",
            success_flag=False,
        )
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE id = ?", ("doesnotexist",)
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_assistant_message_carries_metrics_after_turn(self) -> None:
        # Simulates the api/main.py finally-block wiring: write a user msg,
        # write an assistant msg, drive start_turn/end_turn, then call
        # insert_turn_trace + attach_turn_metrics with the finalized
        # manifest's values. Asserts the assistant row carries metrics and
        # the user row stays clean.
        conv_id = self._make_conv()
        user_msg = self.store.add_message(conv_id, "user", "what about 1008 14th Ave?")

        start_turn(user_text="what about 1008 14th Ave?", conversation_id=conv_id)
        record_classification(
            answer_type="BROWSE", confidence=0.82, reason="single property analysis"
        )
        record_dispatch("browse_stream")
        record_module_run(
            name="valuation", source="run", mode="ok",
            confidence=0.7, duration_ms=120.0,
        )
        assistant_msg = self.store.add_message(
            conv_id, "assistant", "I think this is a fair price...", events=[]
        )

        finalized = end_turn()
        assert finalized is not None
        self.store.insert_turn_trace(finalized.to_jsonable())
        self.store.attach_turn_metrics(
            assistant_msg["id"],
            turn_trace_id=finalized.turn_id,
            latency_ms=int(finalized.duration_ms_total),
            answer_type=finalized.answer_type,
            success_flag=True,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            assistant_row = conn.execute(
                "SELECT turn_trace_id, latency_ms, answer_type, success_flag "
                "FROM messages WHERE id = ?",
                (assistant_msg["id"],),
            ).fetchone()
            user_row = conn.execute(
                "SELECT turn_trace_id, latency_ms, answer_type, success_flag "
                "FROM messages WHERE id = ?",
                (user_msg["id"],),
            ).fetchone()
        self.assertEqual(assistant_row["turn_trace_id"], finalized.turn_id)
        self.assertEqual(assistant_row["answer_type"], "BROWSE")
        self.assertGreaterEqual(assistant_row["latency_ms"], 0)
        self.assertEqual(assistant_row["success_flag"], 1)
        # User row stays clean — metrics only attach to the assistant turn.
        self.assertIsNone(user_row["turn_trace_id"])
        self.assertIsNone(user_row["latency_ms"])
        self.assertIsNone(user_row["answer_type"])
        self.assertIsNone(user_row["success_flag"])


class DeleteConversationCascadeTests(_StoreCase):
    def test_delete_conversation_sets_turn_trace_conversation_id_to_null(self) -> None:
        conv_id = self._make_conv()
        manifest = TurnManifest(
            turn_id="cascade00000",
            started_at=1700000000.0,
            user_text="x",
            conversation_id=conv_id,
        ).to_jsonable()
        self.store.insert_turn_trace(manifest)

        self.store.delete_conversation(conv_id)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT conversation_id FROM turn_traces WHERE turn_id = ?",
                (manifest["turn_id"],),
            ).fetchone()
        self.assertIsNotNone(row, "turn_trace should survive conversation deletion")
        self.assertIsNone(row[0])


if __name__ == "__main__":
    unittest.main()

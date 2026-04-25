"""Per-turn invocation manifest — covers the start/end lifecycle, the
record_* helpers, and the BRIARWOOD_TRACE=1 stderr emission path.

The manifest is a contextvars-backed shim that aggregates per-turn signals
(router classification, dispatch choice, wedge outcome, scoped module runs,
LLM calls). Outside of an active turn, all record_* helpers are no-ops —
that's the contract that lets the manifest be safely imported from offline
scripts and tests."""

from __future__ import annotations

import io
import json
import time
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from briarwood.agent import turn_manifest as tm


class StartEndLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        # Defensive: clear any leftover manifest from prior tests.
        tm.end_turn()

    def tearDown(self) -> None:
        tm.end_turn()

    def test_no_active_manifest_outside_a_turn(self) -> None:
        self.assertIsNone(tm.current_manifest())

    def test_start_turn_installs_manifest(self) -> None:
        m = tm.start_turn(user_text="hello", conversation_id="conv-1")
        self.assertIs(tm.current_manifest(), m)
        self.assertEqual(m.user_text, "hello")
        self.assertEqual(m.conversation_id, "conv-1")
        self.assertTrue(m.turn_id)
        self.assertGreater(m.started_at, 0)

    def test_end_turn_clears_context(self) -> None:
        tm.start_turn(user_text="hello")
        tm.end_turn()
        self.assertIsNone(tm.current_manifest())

    def test_end_turn_without_active_is_no_op(self) -> None:
        # Should not raise.
        result = tm.end_turn()
        self.assertIsNone(result)

    def test_record_helpers_are_no_op_outside_a_turn(self) -> None:
        # All record_* helpers must be safe when no turn is active.
        tm.record_classification(answer_type="lookup", confidence=0.6, reason="x")
        tm.record_dispatch("decision_stream")
        tm.record_wedge(fired=True, success=True)
        tm.record_module_run(name="valuation", source="run")
        tm.record_module_skip(name="risk_model", reason="no prereq")
        tm.record_llm_call_summary(
            surface="composer.draft",
            provider="OpenAI",
            model="gpt-4o-mini",
            status="success",
            duration_ms=120.0,
        )
        tm.record_note("any text")
        # Still no manifest — the helpers didn't accidentally create one.
        self.assertIsNone(tm.current_manifest())


class RecorderHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        tm.end_turn()
        self.manifest = tm.start_turn(user_text="what is the price analysis for X")

    def tearDown(self) -> None:
        tm.end_turn()

    def test_record_classification_populates_fields(self) -> None:
        tm.record_classification(
            answer_type="decision", confidence=0.62, reason="llm classify"
        )
        self.assertEqual(self.manifest.answer_type, "decision")
        self.assertAlmostEqual(self.manifest.confidence, 0.62, places=6)
        self.assertEqual(self.manifest.classification_reason, "llm classify")

    def test_record_dispatch_sets_stream_name(self) -> None:
        tm.record_dispatch("decision_stream")
        self.assertEqual(self.manifest.dispatch, "decision_stream")

    def test_record_wedge_captures_outcome(self) -> None:
        tm.record_wedge(
            fired=True,
            success=False,
            reason="editor_rejected: ['scenario sample size 0']",
            archetype="VERDICT_WITH_COMPARISON",
        )
        self.assertIsNotNone(self.manifest.wedge)
        assert self.manifest.wedge is not None  # for type-checker
        self.assertTrue(self.manifest.wedge.fired)
        self.assertFalse(self.manifest.wedge.success)
        self.assertIn("editor_rejected", self.manifest.wedge.reason or "")
        self.assertEqual(self.manifest.wedge.archetype, "VERDICT_WITH_COMPARISON")

    def test_record_module_run_appends_record(self) -> None:
        tm.record_module_run(
            name="valuation",
            source="run",
            mode="ok",
            confidence=0.71,
            duration_ms=42.0,
            warnings_count=0,
        )
        tm.record_module_run(name="risk_model", source="cache")
        names = [r.name for r in self.manifest.modules_run]
        self.assertEqual(names, ["valuation", "risk_model"])
        self.assertEqual(self.manifest.modules_run[0].mode, "ok")
        self.assertEqual(self.manifest.modules_run[1].source, "cache")

    def test_record_module_skip_appends_record(self) -> None:
        tm.record_module_skip(name="renovation_impact", reason="no prereq")
        tm.record_module_skip(name="margin_sensitivity", reason="no prereq")
        self.assertEqual(len(self.manifest.modules_skipped), 2)
        self.assertEqual(self.manifest.modules_skipped[0].name, "renovation_impact")

    def test_record_llm_call_summary_appends_record(self) -> None:
        tm.record_llm_call_summary(
            surface="agent_router.classify",
            provider="OpenAIChatClient",
            model="gpt-4o-mini",
            status="success",
            duration_ms=180.0,
            attempts=1,
        )
        self.assertEqual(len(self.manifest.llm_calls), 1)
        call = self.manifest.llm_calls[0]
        self.assertEqual(call.surface, "agent_router.classify")
        self.assertEqual(call.status, "success")
        self.assertAlmostEqual(call.duration_ms, 180.0, places=6)

    def test_record_note_appends_breadcrumb(self) -> None:
        tm.record_note("classify_turn raised; falling back to echo")
        self.assertEqual(len(self.manifest.notes), 1)
        self.assertIn("falling back", self.manifest.notes[0])


class StderrEmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        tm.end_turn()

    def tearDown(self) -> None:
        tm.end_turn()

    def test_trace_off_does_not_emit(self) -> None:
        tm.start_turn(user_text="hi")
        tm.record_classification(answer_type="chitchat", confidence=1.0, reason="cache")
        buf = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stderr(buf):
            tm.end_turn()
        self.assertEqual(buf.getvalue(), "")

    def test_trace_on_emits_one_json_line(self) -> None:
        tm.start_turn(user_text="what is the price analysis for 1008 14th Ave")
        tm.record_classification(
            answer_type="decision", confidence=0.62, reason="llm classify"
        )
        tm.record_dispatch("decision_stream")
        tm.record_wedge(fired=True, success=True, archetype="VERDICT_WITH_COMPARISON")
        tm.record_module_run(name="valuation", source="run", mode="ok", confidence=0.71)
        tm.record_module_skip(name="renovation_impact", reason="no prereq")
        tm.record_llm_call_summary(
            surface="composer.draft",
            provider="OpenAIChatClient",
            model="gpt-4o-mini",
            status="success",
            duration_ms=210.0,
        )
        buf = io.StringIO()
        with patch.dict("os.environ", {tm.TRACE_FLAG: "1"}), redirect_stderr(buf):
            tm.end_turn()
        out = buf.getvalue()
        self.assertTrue(out.startswith("[turn] "), f"unexpected prefix: {out!r}")
        # One JSON line.
        self.assertEqual(out.count("\n"), 1)
        line = out.removeprefix("[turn] ").rstrip()
        payload = json.loads(line)
        self.assertEqual(payload["answer_type"], "decision")
        self.assertEqual(payload["dispatch"], "decision_stream")
        self.assertEqual(payload["wedge"]["fired"], True)
        self.assertEqual(payload["wedge"]["success"], True)
        self.assertEqual(payload["modules_run"][0]["name"], "valuation")
        self.assertEqual(payload["modules_skipped"][0]["name"], "renovation_impact")
        self.assertEqual(payload["llm_calls"][0]["surface"], "composer.draft")
        # duration_ms_total is set at end_turn.
        self.assertGreaterEqual(payload["duration_ms_total"], 0)

    def test_trace_off_synonyms_all_disable(self) -> None:
        for val in ("0", "false", "no", "off", "FALSE", ""):
            tm.start_turn(user_text="hi")
            buf = io.StringIO()
            with patch.dict("os.environ", {tm.TRACE_FLAG: val}), redirect_stderr(buf):
                tm.end_turn()
            self.assertEqual(buf.getvalue(), "", f"{val!r} should disable")


class LLMLedgerIntegrationTests(unittest.TestCase):
    """When a turn is active, the existing LLM call ledger should mirror
    each record into the manifest's llm_calls list. Verifies the wiring
    in `briarwood/agent/llm_observability.py::LLMCallLedger.append`."""

    def setUp(self) -> None:
        tm.end_turn()

    def tearDown(self) -> None:
        tm.end_turn()

    def test_ledger_append_mirrors_to_manifest(self) -> None:
        from briarwood.agent.llm_observability import LLMCallRecord, get_llm_ledger

        manifest = tm.start_turn(user_text="hi")
        ledger = get_llm_ledger()
        ledger.append(
            LLMCallRecord(
                surface="agent_router.classify",
                schema_name="RouterClassification",
                provider="OpenAIChatClient",
                model="gpt-4o-mini",
                prompt_hash="abc",
                response_hash="def",
                status="success",
                attempts=1,
                duration_ms=180.0,
            )
        )
        self.assertEqual(len(manifest.llm_calls), 1)
        self.assertEqual(manifest.llm_calls[0].surface, "agent_router.classify")
        self.assertEqual(manifest.llm_calls[0].status, "success")

    def test_ledger_append_outside_turn_is_safe(self) -> None:
        from briarwood.agent.llm_observability import LLMCallRecord, get_llm_ledger

        ledger = get_llm_ledger()
        # No active turn — ledger.append must not raise even though it tries
        # to mirror to the (nonexistent) manifest.
        ledger.append(
            LLMCallRecord(
                surface="x",
                schema_name=None,
                provider=None,
                model=None,
                prompt_hash="hash",
                status="success",
            )
        )


class InActiveContextTests(unittest.TestCase):
    """``in_active_context`` propagates ContextVar values across thread
    boundaries. This is the bug-fix for the 2026-04-25 finding where the
    chat-tier streams ran ``loop.run_in_executor(None, dispatch, ...)`` and
    everything inside dispatch silently no-op'd because the per-turn
    manifest's ContextVar wasn't visible in the worker thread.

    Pin the propagation behavior here so it can't regress."""

    def setUp(self) -> None:
        tm.end_turn()

    def tearDown(self) -> None:
        tm.end_turn()

    def test_record_calls_inside_run_in_executor_reach_manifest(self) -> None:
        """Without the wrapper this test would fail — record_module_run would
        run in a worker thread with an empty context and silently no-op."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        manifest = tm.start_turn(user_text="hi")

        def in_worker() -> None:
            tm.record_module_run(name="valuation", source="run", mode="ok")
            tm.record_tool_call(
                name="get_value_thesis",
                duration_ms=10.0,
                status="success",
            )

        async def main() -> None:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                await loop.run_in_executor(pool, tm.in_active_context(in_worker))

        asyncio.run(main())

        self.assertEqual(len(manifest.modules_run), 1)
        self.assertEqual(manifest.modules_run[0].name, "valuation")
        self.assertEqual(len(manifest.tool_calls), 1)
        self.assertEqual(manifest.tool_calls[0].name, "get_value_thesis")

    def test_pool_map_with_in_active_context_propagates(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        manifest = tm.start_turn(user_text="hi")

        def fake_module_runner(name: str) -> str:
            tm.record_module_run(name=name, source="run", mode="ok")
            return name

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    tm.in_active_context(fake_module_runner),
                    ["valuation", "carry_cost", "risk_model"],
                )
            )
        self.assertEqual(results, ["valuation", "carry_cost", "risk_model"])
        names = [r.name for r in manifest.modules_run]
        self.assertEqual(sorted(names), ["carry_cost", "risk_model", "valuation"])

    def test_worker_without_wrapper_does_not_see_manifest(self) -> None:
        """Negative regression: confirms that the bug is real — without the
        wrapper, ContextVar values do NOT propagate. This test would break
        if Python's executor semantics ever change to auto-propagate context."""
        from concurrent.futures import ThreadPoolExecutor

        manifest = tm.start_turn(user_text="hi")

        def in_worker_unwrapped() -> None:
            tm.record_module_run(name="should_not_appear", source="run")

        with ThreadPoolExecutor(max_workers=1) as pool:
            list(pool.map(lambda _: in_worker_unwrapped(), [None]))

        # Manifest should still be empty — the worker's empty context made
        # the record_module_run a no-op.
        self.assertEqual(manifest.modules_run, [])

    def test_in_active_context_outside_a_turn_is_safe(self) -> None:
        """Capturing an empty context shouldn't error — fn just runs as usual."""

        def add(a: int, b: int) -> int:
            return a + b

        wrapped = tm.in_active_context(add)
        self.assertEqual(wrapped(2, 3), 5)


class TracedToolDecoratorTests(unittest.TestCase):
    """The ``traced_tool`` decorator records duration + status into the
    active manifest. Outside a turn it must be a transparent no-op."""

    def setUp(self) -> None:
        tm.end_turn()

    def tearDown(self) -> None:
        tm.end_turn()

    def test_success_path_records_call(self) -> None:
        @tm.traced_tool()
        def fake_tool(x: int) -> int:
            return x * 2

        manifest = tm.start_turn(user_text="hi")
        result = fake_tool(21)
        self.assertEqual(result, 42)
        self.assertEqual(len(manifest.tool_calls), 1)
        rec = manifest.tool_calls[0]
        self.assertEqual(rec.name, "fake_tool")
        self.assertEqual(rec.status, "success")
        self.assertIsNone(rec.error_type)
        self.assertGreaterEqual(rec.duration_ms, 0)

    def test_exception_path_records_then_propagates(self) -> None:
        @tm.traced_tool()
        def explode() -> None:
            raise ValueError("boom")

        manifest = tm.start_turn(user_text="hi")
        with self.assertRaises(ValueError):
            explode()
        self.assertEqual(len(manifest.tool_calls), 1)
        rec = manifest.tool_calls[0]
        self.assertEqual(rec.status, "exception")
        self.assertEqual(rec.error_type, "ValueError")

    def test_no_op_outside_turn(self) -> None:
        """Decorator is transparent when no manifest is active — same return
        value, no recording, no overhead beyond a single ContextVar.get()."""

        @tm.traced_tool()
        def fake_tool(x: int) -> int:
            return x * 2

        # No turn active.
        self.assertIsNone(tm.current_manifest())
        result = fake_tool(21)
        self.assertEqual(result, 42)

    def test_custom_name_overrides_function_name(self) -> None:
        @tm.traced_tool(name="cma.live")
        def get_cma_internal() -> str:
            return "ok"

        manifest = tm.start_turn(user_text="hi")
        get_cma_internal()
        self.assertEqual(manifest.tool_calls[0].name, "cma.live")

    def test_decorator_preserves_function_metadata(self) -> None:
        """``functools.wraps`` should preserve ``__name__`` and ``__doc__``."""

        @tm.traced_tool()
        def fake_tool() -> None:
            """A docstring."""

        self.assertEqual(fake_tool.__name__, "fake_tool")
        self.assertEqual(fake_tool.__doc__, "A docstring.")

    def test_tool_calls_appear_in_emitted_manifest(self) -> None:
        @tm.traced_tool()
        def fast() -> int:
            return 1

        @tm.traced_tool()
        def slow() -> int:
            time.sleep(0.001)  # 1ms — guaranteed nonzero duration
            return 2

        tm.start_turn(user_text="hi")
        fast()
        slow()

        buf = io.StringIO()
        with patch.dict("os.environ", {tm.TRACE_FLAG: "1"}), redirect_stderr(buf):
            tm.end_turn()
        line = buf.getvalue().removeprefix("[turn] ").rstrip()
        payload = json.loads(line)
        names = [c["name"] for c in payload["tool_calls"]]
        self.assertEqual(names, ["fast", "slow"])
        self.assertEqual(payload["tool_calls"][0]["status"], "success")


if __name__ == "__main__":
    unittest.main()

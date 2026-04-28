"""Tests for the Stage 2 read-back consumer (Cycle 3).

Validates the closure gate per ROADMAP §3.1 Stage 2: a thumbs-down on
turn N visibly influences turn N+1.

Three checks:
1. ``current_feedback_hint()`` returns the canonical text inside the
   ``apply_feedback_hint`` context when the conversation has a recent
   thumbs-down — and ``None`` outside the context.
2. ``current_feedback_hint()`` stays ``None`` when the conversation has
   no recent thumbs-down (only thumbs-ups, or empty feedback table).
3. The ``on_apply`` callback fires when a hint is applied and does NOT
   fire when no hint applies. This is what the pipeline_adapter wires
   to ``record_note(HINT_MANIFEST_TAG)`` so the loop closure is
   auditable in ``turn_traces.notes``.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from api.store import ConversationStore
from briarwood.synthesis.feedback_hint import (
    HINT_MANIFEST_TAG,
    apply_feedback_hint,
    current_feedback_hint,
    feedback_hint_text,
)


def _seed_assistant(store: ConversationStore) -> tuple[str, str]:
    conv = store.create_conversation(title="t")
    cid = conv["id"]
    store.add_message(cid, "user", "u")
    assistant = store.add_message(cid, "assistant", "a")
    return cid, assistant["id"]


class _StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "test.db"
        self.store = ConversationStore(db_path=self.db_path)


class FeedbackHintTests(_StoreCase):
    def test_synthesis_hint_added_when_recent_down_rating(self) -> None:
        cid, mid = _seed_assistant(self.store)
        self.store.upsert_feedback(message_id=mid, rating="down")

        # Outside the context: no hint.
        self.assertIsNone(current_feedback_hint())

        with apply_feedback_hint(self.store, cid) as applied:
            self.assertTrue(applied)
            self.assertEqual(current_feedback_hint(), feedback_hint_text())

        # After exit: contextvar reset.
        self.assertIsNone(current_feedback_hint())

    def test_synthesis_hint_omitted_when_no_recent_down(self) -> None:
        cid, mid = _seed_assistant(self.store)
        self.store.upsert_feedback(message_id=mid, rating="up")

        with apply_feedback_hint(self.store, cid) as applied:
            self.assertFalse(applied)
            self.assertIsNone(current_feedback_hint())

    def test_synthesis_hint_omitted_when_feedback_table_empty(self) -> None:
        cid, _ = _seed_assistant(self.store)

        with apply_feedback_hint(self.store, cid) as applied:
            self.assertFalse(applied)
            self.assertIsNone(current_feedback_hint())

    def test_synthesis_hint_noop_when_conversation_id_missing(self) -> None:
        with apply_feedback_hint(self.store, None) as applied:
            self.assertFalse(applied)
            self.assertIsNone(current_feedback_hint())

    def test_synthesis_hint_noop_when_store_missing(self) -> None:
        with apply_feedback_hint(None, "any-id") as applied:
            self.assertFalse(applied)
            self.assertIsNone(current_feedback_hint())

    def test_on_apply_callback_fires_only_when_hint_applies(self) -> None:
        cid, mid = _seed_assistant(self.store)
        self.store.upsert_feedback(message_id=mid, rating="down")

        applied_calls: list[str] = []
        with apply_feedback_hint(
            self.store, cid, on_apply=lambda: applied_calls.append(HINT_MANIFEST_TAG)
        ):
            pass
        self.assertEqual(applied_calls, [HINT_MANIFEST_TAG])

        # Same conversation but flip the rating to "up" — callback must
        # not fire.
        self.store.upsert_feedback(message_id=mid, rating="up")
        applied_calls.clear()
        with apply_feedback_hint(
            self.store, cid, on_apply=lambda: applied_calls.append(HINT_MANIFEST_TAG)
        ):
            pass
        self.assertEqual(applied_calls, [])

    def test_synthesis_hint_swallows_store_failure(self) -> None:
        """A misbehaving store cannot break a synthesis turn — the hint
        degrades gracefully to no-op."""

        class _BrokenStore:
            def recent_feedback_for_conversation(self, *args, **kwargs):
                raise RuntimeError("DB locked")

        with apply_feedback_hint(_BrokenStore(), "conv-x") as applied:
            self.assertFalse(applied)
            self.assertIsNone(current_feedback_hint())

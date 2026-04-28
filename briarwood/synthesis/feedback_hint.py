"""Stage 2 read-back consumer: in-flight synthesis hint from prior feedback.

When a recent assistant turn in the same conversation received a
thumbs-down, the next turn's synthesizer should vary its framing rather
than repeat the framing that just got rated unfavorably. This module
implements that loop.

Why a ContextVar instead of a kwarg through every call site?
``synthesize_with_llm`` is invoked from ~7 handlers in
``briarwood/agent/dispatch.py`` (handle_browse, handle_decision,
handle_research, handle_rent_lookup, handle_risk, handle_edge,
handle_strategy, ...). Threading a kwarg through each handler would mean
7 surgical edits and 7 future regression risks. The hint is set ONCE in
``api/pipeline_adapter.py`` (the layer that has ``conversation_id`` and
the SQLite store handy) and read ONCE in the synthesizer. ContextVars
are async-task-scoped and propagate across the threadpool boundary the
dispatch handlers run in, so the seam is exactly two files even though
the synthesis call sites are many.

The hint lifecycle is bounded to one turn via ``apply_feedback_hint``,
which is a context manager — set on enter, reset on exit, exception-safe.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Protocol


_FEEDBACK_HINT: ContextVar[str | None] = ContextVar(
    "synthesis_feedback_hint", default=None
)


# The hint text the synthesizer appends to its system prompt. Kept short
# so the cumulative system-prompt budget isn't disturbed; the directive
# is "vary your framing", not a rewrite recipe.
_HINT_TEXT = (
    "OPERATOR NOTE: A recent assistant turn in this same conversation "
    "received a thumbs-down from the user. Vary your framing on this "
    "turn — try a different angle, organizational structure, or "
    "emphasis than the prior turn would have used. Numeric grounding "
    "rules and citation rules are unchanged; only the prose framing "
    "should shift."
)


# Identifier the manifest note carries when the hint fires. Kept stable so
# `SELECT ... FROM turn_traces WHERE notes LIKE '%recent-thumbs-down...'`
# remains the audit query.
HINT_MANIFEST_TAG = "feedback:recent-thumbs-down-influenced-synthesis"


class _StoreLike(Protocol):
    """Minimal subset of ``api.store.ConversationStore`` we depend on.

    Declared as a protocol so tests can pass a fake without instantiating
    the full store, and so this module doesn't import ``api.store`` —
    keeps the dependency direction (briarwood/ does not depend on api/)
    intact.
    """

    def recent_feedback_for_conversation(
        self,
        conversation_id: str,
        *,
        since_ms: int | None = ...,
        limit: int = ...,
    ) -> list[dict[str, object]]: ...


def current_feedback_hint() -> str | None:
    """Read the active hint, or None if no hint is set for this turn."""
    return _FEEDBACK_HINT.get()


def feedback_hint_text() -> str:
    """Expose the canonical hint text for tests + observability tooling."""
    return _HINT_TEXT


def _has_recent_thumbs_down(
    store: _StoreLike,
    conversation_id: str,
    *,
    limit: int = 3,
) -> bool:
    """Return True when any of the last ``limit`` feedback rows in the
    conversation is rated ``"down"``.

    Failure-safe: any exception from the store layer (corrupt row, DB
    locked, schema-mismatch) causes the function to return False so a
    misbehaving feedback table cannot break a synthesis turn. Caller
    sees no hint applied; the loop degrades gracefully."""
    try:
        rows = store.recent_feedback_for_conversation(
            conversation_id, limit=limit
        )
    except Exception as exc:  # noqa: BLE001 — observability must never break a turn
        print(f"[feedback.hint] read failed for {conversation_id}: {exc}", flush=True)
        return False
    return any(r.get("rating") == "down" for r in rows)


@contextmanager
def apply_feedback_hint(
    store: _StoreLike | None,
    conversation_id: str | None,
    *,
    on_apply: object | None = None,
) -> Iterator[bool]:
    """Set the synthesis feedback hint for the duration of one turn.

    Yields ``True`` when the hint was applied (i.e. recent thumbs-down
    found), ``False`` otherwise. Caller can use the yielded value to
    decide whether to record a manifest note.

    Both ``store`` and ``conversation_id`` are optional so caller code in
    ``pipeline_adapter`` can pass through whatever it has without
    branching — a None on either side is a no-op."""
    applied = False
    token = None
    if store is not None and conversation_id:
        if _has_recent_thumbs_down(store, conversation_id):
            token = _FEEDBACK_HINT.set(_HINT_TEXT)
            applied = True
    try:
        if applied and callable(on_apply):
            try:
                on_apply()
            except Exception as exc:  # noqa: BLE001
                print(f"[feedback.hint] on_apply callback failed: {exc}", flush=True)
        yield applied
    finally:
        if token is not None:
            _FEEDBACK_HINT.reset(token)


__all__ = [
    "HINT_MANIFEST_TAG",
    "apply_feedback_hint",
    "current_feedback_hint",
    "feedback_hint_text",
]

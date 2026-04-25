"""Per-turn invocation manifest — terminal-tail visibility for chat turns.

Briarwood's analysis is split across many surfaces — the router, dispatch
handlers, the orchestrator, the scoped executor, the claims wedge, the
composer, the Representation Agent, and several LLM call sites. Each is
already partly observable in isolation (the LLM call ledger at
``briarwood/agent/llm_observability.py``, the executor's per-module trace),
but there is no single place a developer can watch and ask "what fired on
that turn? what didn't?"

This module aggregates the per-turn picture and emits one structured JSON
line to stderr at the end of each chat turn when ``BRIARWOOD_TRACE=1`` is
set. Default-off so production logs stay quiet.

Architecture notes
------------------
The manifest lives in a `contextvars.ContextVar` so async-streaming code in
``api/main.py`` and the `briarwood/agent` layer can append to it without
plumbing it through every signature. The pattern: start a turn at the chat
endpoint boundary, record events from anywhere inside the turn, end the
turn when the stream completes.

Sub-systems integrate via tiny no-op-when-off helpers (``record_*``). When
``current_manifest()`` returns ``None`` (no turn active, or running outside
a chat request), the helpers do nothing — so this module is safe to call
from offline scripts, tests, and batch jobs.
"""

from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, TypeVar

_logger = logging.getLogger(__name__)

# Env flag. Set to "1" / "true" / "yes" to emit the per-turn manifest as a
# single JSON line to stderr at turn end. Default off — the manifest is
# always populated in memory but never printed unless this is set.
TRACE_FLAG = "BRIARWOOD_TRACE"


@dataclass(slots=True)
class ModuleExecutionRecord:
    """One scoped-module run inside a turn."""

    name: str
    source: str  # "run" or "cache"
    mode: str | None = None  # "ok" / "error" / "fallback" / None
    confidence: float | None = None
    duration_ms: float = 0.0
    warnings_count: int = 0


@dataclass(slots=True)
class ModuleSkipRecord:
    """A scoped module that was planned-out (or skipped at the planner)."""

    name: str
    reason: str


@dataclass(slots=True)
class WedgeRecord:
    """The claims wedge attempt. ``fired=True`` means the wedge was tried
    (claims_enabled + archetype matched). ``success`` is True only if the
    full chain (build → scout → editor → render) produced rendered prose."""

    fired: bool
    success: bool | None = None
    reason: str | None = None  # why didn't fire / why fell through
    archetype: str | None = None


@dataclass(slots=True)
class LLMCallSummary:
    """Compact summary of one LLM call. Pulled from the existing LLM ledger
    record at append-time so we don't double-store full prompts/responses."""

    surface: str
    provider: str | None
    model: str | None
    status: str  # "success" / "exception" / "budget_exceeded" / "cache_hit" / etc
    duration_ms: float
    attempts: int = 0


@dataclass(slots=True)
class ToolCallRecord:
    """One ``briarwood/agent/tools.py`` invocation. Most chat-tier handlers
    compose their response by calling several of these in sequence, so this
    is where the bulk of a turn's wall-clock time often lives. Captures the
    name, duration, and success/failure status — not arguments or results,
    by design (tool args can include property IDs and external API
    responses that we don't want in observability logs)."""

    name: str
    duration_ms: float
    status: str  # "success" / "exception"
    error_type: str | None = None


@dataclass(slots=True)
class TurnManifest:
    """The full per-turn record."""

    turn_id: str
    started_at: float  # epoch seconds
    user_text: str
    conversation_id: str | None = None
    answer_type: str | None = None
    confidence: float | None = None
    classification_reason: str | None = None
    dispatch: str | None = None  # "decision_stream" / "search_stream" / "browse_stream" / "dispatch_stream" / "echo"
    wedge: WedgeRecord | None = None
    modules_run: list[ModuleExecutionRecord] = field(default_factory=list)
    modules_skipped: list[ModuleSkipRecord] = field(default_factory=list)
    llm_calls: list[LLMCallSummary] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    duration_ms_total: float = 0.0
    notes: list[str] = field(default_factory=list)  # free-text breadcrumbs

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "started_at": self.started_at,
            "user_text": self.user_text,
            "conversation_id": self.conversation_id,
            "answer_type": self.answer_type,
            "confidence": self.confidence,
            "classification_reason": self.classification_reason,
            "dispatch": self.dispatch,
            "wedge": asdict(self.wedge) if self.wedge is not None else None,
            "modules_run": [asdict(r) for r in self.modules_run],
            "modules_skipped": [asdict(s) for s in self.modules_skipped],
            "llm_calls": [asdict(c) for c in self.llm_calls],
            "tool_calls": [asdict(c) for c in self.tool_calls],
            "duration_ms_total": self.duration_ms_total,
            "notes": list(self.notes),
        }


# Context-local state. Each chat turn (or test case) gets its own manifest;
# threads / async tasks inherit it implicitly via contextvars semantics.
_current_manifest: contextvars.ContextVar[TurnManifest | None] = contextvars.ContextVar(
    "briarwood_current_turn_manifest", default=None
)


def current_manifest() -> TurnManifest | None:
    """Return the active manifest for the current turn, or None if no turn
    is in progress (offline scripts, tests, batch jobs)."""
    return _current_manifest.get()


def trace_enabled() -> bool:
    """Whether ``BRIARWOOD_TRACE`` is set. Read at emission time so tests
    and dev shells can flip it without a restart."""
    raw = os.environ.get(TRACE_FLAG, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def start_turn(
    *, user_text: str, conversation_id: str | None = None
) -> TurnManifest:
    """Begin a new turn manifest and install it as current. Returns the
    manifest so the caller (chat endpoint) can keep a handle on it."""
    manifest = TurnManifest(
        turn_id=uuid.uuid4().hex[:12],
        started_at=time.time(),
        user_text=user_text,
        conversation_id=conversation_id,
    )
    _current_manifest.set(manifest)
    return manifest


def end_turn() -> TurnManifest | None:
    """Finalize the current manifest, emit to stderr when ``BRIARWOOD_TRACE``
    is on, and clear the context. Idempotent — calling without an active
    manifest is a no-op."""
    manifest = _current_manifest.get()
    if manifest is None:
        return None
    manifest.duration_ms_total = (time.time() - manifest.started_at) * 1000
    if trace_enabled():
        _emit_to_stderr(manifest)
    _current_manifest.set(None)
    return manifest


def _emit_to_stderr(manifest: TurnManifest) -> None:
    try:
        line = json.dumps(manifest.to_jsonable(), default=str, sort_keys=True)
    except Exception as exc:  # never break a chat turn over a logging issue
        _logger.warning("turn manifest serialization failed: %s", exc)
        return
    print(f"[turn] {line}", file=sys.stderr, flush=True)


# ----- Recorder helpers (no-op when no manifest is active) -----


def record_classification(
    *, answer_type: str, confidence: float, reason: str
) -> None:
    m = _current_manifest.get()
    if m is None:
        return
    m.answer_type = answer_type
    m.confidence = float(confidence)
    m.classification_reason = reason


def record_dispatch(stream_name: str) -> None:
    m = _current_manifest.get()
    if m is None:
        return
    m.dispatch = stream_name


def record_wedge(
    *,
    fired: bool,
    success: bool | None = None,
    reason: str | None = None,
    archetype: str | None = None,
) -> None:
    m = _current_manifest.get()
    if m is None:
        return
    m.wedge = WedgeRecord(
        fired=fired, success=success, reason=reason, archetype=archetype
    )


def record_module_run(
    *,
    name: str,
    source: str,
    mode: str | None = None,
    confidence: float | None = None,
    duration_ms: float = 0.0,
    warnings_count: int = 0,
) -> None:
    m = _current_manifest.get()
    if m is None:
        return
    m.modules_run.append(
        ModuleExecutionRecord(
            name=name,
            source=source,
            mode=mode,
            confidence=confidence,
            duration_ms=duration_ms,
            warnings_count=warnings_count,
        )
    )


def record_module_skip(*, name: str, reason: str) -> None:
    m = _current_manifest.get()
    if m is None:
        return
    m.modules_skipped.append(ModuleSkipRecord(name=name, reason=reason))


def record_llm_call_summary(
    *,
    surface: str,
    provider: str | None,
    model: str | None,
    status: str,
    duration_ms: float,
    attempts: int = 0,
) -> None:
    """Called from `briarwood.agent.llm_observability.LLMCallLedger.append`.
    Mirrors the ledger record into the per-turn manifest as a compact summary
    so the manifest can stand on its own without joining against the ledger."""
    m = _current_manifest.get()
    if m is None:
        return
    m.llm_calls.append(
        LLMCallSummary(
            surface=surface,
            provider=provider,
            model=model,
            status=status,
            duration_ms=duration_ms,
            attempts=attempts,
        )
    )


def in_active_context(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Capture the caller's contextvars context and return a thread-safe
    wrapper that, when invoked, runs ``fn(*args, **kwargs)`` inside that
    context.

    Use to propagate ContextVar values — including the active per-turn
    manifest — across an executor thread boundary. Python's default
    ``loop.run_in_executor`` does NOT propagate context across threads, so
    without this wrapper any ``record_*`` call inside the worker silently
    no-ops because ``current_manifest()`` returns ``None`` in the worker's
    empty context.

    The context is captured **at the moment this function runs**, which must
    be in the caller's thread — that is why the helper is shaped as a
    decorator-style wrapper rather than a callable-and-args helper. Calling
    ``in_active_context`` itself in the worker thread would capture the
    worker's empty context and defeat the purpose.

    Example::

        # Before (manifest is invisible inside dispatch):
        await loop.run_in_executor(None, dispatch, text, decision, session, llm)

        # After (manifest propagates into the worker thread):
        await loop.run_in_executor(
            None,
            in_active_context(dispatch),
            text, decision, session, llm,
        )
    """
    ctx = contextvars.copy_context()

    @functools.wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return ctx.run(fn, *args, **kwargs)

    return wrapped


def record_tool_call(
    *,
    name: str,
    duration_ms: float,
    status: str,
    error_type: str | None = None,
) -> None:
    """Append a tools.py invocation record. Called by the ``traced_tool``
    decorator. Safe to call when no manifest is active — silently no-ops."""
    m = _current_manifest.get()
    if m is None:
        return
    m.tool_calls.append(
        ToolCallRecord(
            name=name,
            duration_ms=duration_ms,
            status=status,
            error_type=error_type,
        )
    )


F = TypeVar("F", bound=Callable[..., Any])


def traced_tool(name: str | None = None) -> Callable[[F], F]:
    """Decorator that records the wrapped function's invocation into the
    active per-turn manifest, with duration and success/exception status.

    No-op when no manifest is active (offline scripts, tests, batch jobs)
    so this is safe to apply broadly. Argument and return values are NEVER
    recorded — only the function name and timing — to avoid leaking property
    data, addresses, or external API responses into observability logs.

    Example:
        @traced_tool()
        def get_value_thesis(property_id: str, *, overrides=None) -> dict:
            ...

        @traced_tool(name="cma.live")
        def get_cma(...):
            ...
    """

    def decorator(fn: F) -> F:
        tool_name = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _current_manifest.get() is None:
                return fn(*args, **kwargs)
            started = time.perf_counter()
            status = "success"
            error_type: str | None = None
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                status = "exception"
                error_type = type(exc).__name__
                raise
            finally:
                duration_ms = (time.perf_counter() - started) * 1000
                record_tool_call(
                    name=tool_name,
                    duration_ms=duration_ms,
                    status=status,
                    error_type=error_type,
                )

        return wrapper  # type: ignore[return-value]

    return decorator


def record_note(text: str) -> None:
    """Free-text breadcrumb. Use sparingly — this is for one-off signals
    that don't fit the structured fields (e.g., 'router fallthrough to LOOKUP
    default')."""
    m = _current_manifest.get()
    if m is None:
        return
    m.notes.append(text)


__all__ = [
    "LLMCallSummary",
    "ModuleExecutionRecord",
    "ModuleSkipRecord",
    "TRACE_FLAG",
    "ToolCallRecord",
    "TurnManifest",
    "WedgeRecord",
    "current_manifest",
    "end_turn",
    "in_active_context",
    "record_classification",
    "record_dispatch",
    "record_llm_call_summary",
    "record_module_run",
    "record_module_skip",
    "record_note",
    "record_tool_call",
    "record_wedge",
    "start_turn",
    "trace_enabled",
    "traced_tool",
]

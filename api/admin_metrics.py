"""AI-Native Foundation Stage 3 — admin dashboard data layer.

Reads from two sources:

1. ``api.store.ConversationStore`` — SQLite. Per-turn traces, feedback,
   message metrics. Drives latency aggregates, thumbs ratio, top slowest.
2. ``data/llm_calls.jsonl`` — append-only JSONL written by the LLM ledger.
   Drives cost aggregates by surface and the top-10 highest-cost turns
   (the latter requires Stage 3's ``turn_id`` field added 2026-04-28 to
   the JSONL writer).

The composition layer here is deliberately thin — endpoints in
``api/main.py`` call ``compose_metrics`` and ``compose_recent_turns`` and
return the result. No transformation happens at the FastAPI layer.

JSONL parse strategy: read the whole file on every request. The file is
expected to be a few thousand lines for the foreseeable future and
parsing is sub-100ms. If it grows past a few hundred MB, the v2 path is
to fold cost into a SQLite table — that's a Stage-3.5 conversation.

All read paths are exception-safe: a corrupt JSONL line is skipped (not
raised); an unreadable file returns empty aggregates; SQL failures
propagate (the endpoint gate's exception handler turns them into 500s).
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from api.store import ConversationStore


_JSONL_PATH_ENV = "BRIARWOOD_LLM_JSONL_PATH"
_DEFAULT_JSONL_PATH = "data/llm_calls.jsonl"


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile over a pre-sorted list. ``pct`` in
    [0, 1]. Returns None for an empty list so the dashboard renders a
    "not enough data" cell instead of a misleading zero."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = pct * (len(sorted_values) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return sorted_values[lo]
    frac = rank - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def latency_aggregates(
    durations_by_type: dict[str, list[float]],
) -> list[dict[str, Any]]:
    """Reduce raw per-turn durations to one row per answer_type.

    Output rows carry the count, mean, p50, p95 in ms. Sorted by count
    descending so the busiest tiers lead in the dashboard table."""
    out: list[dict[str, Any]] = []
    for answer_type, durations in durations_by_type.items():
        if not durations:
            continue
        srt = sorted(durations)
        count = len(srt)
        out.append(
            {
                "answer_type": answer_type,
                "count": count,
                "avg_ms": sum(srt) / count,
                "p50_ms": _percentile(srt, 0.5),
                "p95_ms": _percentile(srt, 0.95),
            }
        )
    out.sort(key=lambda r: r["count"], reverse=True)
    return out


def _resolve_jsonl_path() -> Path:
    return Path(os.environ.get(_JSONL_PATH_ENV, _DEFAULT_JSONL_PATH))


def _iter_jsonl_records(path: Path) -> Iterable[dict[str, Any]]:
    """Yield parsed JSONL records, silently skipping unreadable/corrupt
    lines. Returns empty when the file does not exist."""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def _record_in_window(record: dict[str, Any], since_iso: str) -> bool:
    recorded = record.get("recorded_at")
    if not isinstance(recorded, str):
        return False
    return recorded >= since_iso


def cost_by_surface(
    *,
    since_iso: str,
    jsonl_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Aggregate JSONL records into per-surface cost / count / duration.

    Sorted by total cost descending. Records outside the time window are
    skipped; records with no ``cost_usd`` (e.g. cache hits, errors) still
    count toward ``count`` so cache-heavy surfaces remain visible."""
    path = jsonl_path or _resolve_jsonl_path()
    by_surface: dict[str, dict[str, float]] = {}
    for rec in _iter_jsonl_records(path):
        if not _record_in_window(rec, since_iso):
            continue
        surface = rec.get("surface") or "unknown"
        slot = by_surface.setdefault(
            surface,
            {"count": 0, "total_cost_usd": 0.0, "total_duration_ms": 0.0, "errors": 0},
        )
        slot["count"] += 1
        cost = rec.get("cost_usd")
        if isinstance(cost, (int, float)):
            slot["total_cost_usd"] += float(cost)
        dur = rec.get("duration_ms")
        if isinstance(dur, (int, float)):
            slot["total_duration_ms"] += float(dur)
        if rec.get("status") not in (None, "success", "cache_hit"):
            slot["errors"] += 1
    rows: list[dict[str, Any]] = []
    for surface, slot in by_surface.items():
        count = int(slot["count"])
        rows.append(
            {
                "surface": surface,
                "count": count,
                "total_cost_usd": round(slot["total_cost_usd"], 6),
                "avg_duration_ms": (
                    slot["total_duration_ms"] / count if count > 0 else None
                ),
                "errors": int(slot["errors"]),
            }
        )
    rows.sort(key=lambda r: r["total_cost_usd"], reverse=True)
    return rows


def top_costliest_turns(
    *,
    since_iso: str,
    limit: int = 10,
    jsonl_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Top-N turns by summed ``cost_usd`` across their LLM calls.

    Requires the Stage 3 ``turn_id`` field on JSONL records (added
    2026-04-28). Records without ``turn_id`` are excluded from this
    aggregate — they predate the linkage. Returns empty when no in-window
    records carry ``turn_id`` yet."""
    path = jsonl_path or _resolve_jsonl_path()
    by_turn: dict[str, dict[str, float]] = {}
    for rec in _iter_jsonl_records(path):
        if not _record_in_window(rec, since_iso):
            continue
        turn_id = rec.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id:
            continue
        slot = by_turn.setdefault(
            turn_id, {"total_cost_usd": 0.0, "call_count": 0}
        )
        slot["call_count"] += 1
        cost = rec.get("cost_usd")
        if isinstance(cost, (int, float)):
            slot["total_cost_usd"] += float(cost)
    rows = [
        {
            "turn_id": tid,
            "total_cost_usd": round(slot["total_cost_usd"], 6),
            "call_count": int(slot["call_count"]),
        }
        for tid, slot in by_turn.items()
    ]
    rows.sort(key=lambda r: r["total_cost_usd"], reverse=True)
    return rows[:limit]


def _seconds_ago(days: int) -> tuple[float, str]:
    """Return ``(epoch_seconds, iso_string)`` for ``days`` ago. The two
    forms cover both ``turn_traces.started_at`` (REAL epoch s) and the
    JSONL ``recorded_at`` (ISO 8601) without forcing the caller to
    convert."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.timestamp(), cutoff.isoformat()


def compose_metrics(store: ConversationStore, *, days: int = 7) -> dict[str, Any]:
    """Single-shot top-line metrics for ``GET /api/admin/metrics``."""
    since_seconds, since_iso = _seconds_ago(days)
    since_ms = int(since_seconds * 1000)
    durations = store.latency_durations_by_answer_type(
        since_seconds=since_seconds
    )
    return {
        "days": days,
        "since_iso": since_iso,
        "latency_by_answer_type": latency_aggregates(durations),
        "cost_by_surface": cost_by_surface(since_iso=since_iso),
        "thumbs": store.thumbs_ratio_since(since_ms=since_ms),
    }


def compose_recent_turns(
    store: ConversationStore,
    *,
    days: int = 7,
    limit: int = 10,
) -> dict[str, Any]:
    """Top-N slowest and top-N costliest, side-by-side. Same window as
    ``compose_metrics`` so dashboard-side cross-checks line up."""
    since_seconds, since_iso = _seconds_ago(days)
    return {
        "days": days,
        "limit": limit,
        "slowest": store.top_slowest_turns(
            since_seconds=since_seconds, limit=limit
        ),
        "costliest": top_costliest_turns(since_iso=since_iso, limit=limit),
    }


def compose_turn_detail(
    store: ConversationStore, turn_id: str
) -> dict[str, Any] | None:
    """Full per-turn payload for ``GET /api/admin/turns/{turn_id}``.

    Returns ``None`` when the turn is unknown — the endpoint translates
    to 404. The returned dict carries the parsed manifest plus any
    feedback rows that joined to its messages."""
    trace = store.get_turn_trace(turn_id)
    if trace is None:
        return None
    return {
        "trace": trace,
        "feedback": store.feedback_for_turn(turn_id),
    }


__all__ = [
    "compose_metrics",
    "compose_recent_turns",
    "compose_turn_detail",
    "cost_by_surface",
    "latency_aggregates",
    "top_costliest_turns",
]

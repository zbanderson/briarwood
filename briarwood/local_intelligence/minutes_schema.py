"""Schemas + staleness helpers for per-town minutes manifests.

Each town gets one ``MinutesRecord`` persisted under
``data/local_intelligence/minutes/<slug>.json``. The record holds a rolling
window of per-month ``MinuteEntry`` summaries plus the metadata needed to
decide whether the town is due for another refresh pass.

The design is deliberately storage-agnostic at the schema layer: the
refresh runner reads and writes records via ``minutes_store.JsonMinutesStore``
but any backend that serializes these Pydantic models will work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MinuteStatus = Literal["fetched", "summary_only", "fetch_failed", "not_published"]


class MinuteEntry(BaseModel):
    """One month of minutes for one board (planning / zoning / council)."""

    model_config = ConfigDict(extra="forbid")

    month: str  # "2026-03"
    board: str
    source_url: str | None = None
    fetched_at: str | None = None
    status: MinuteStatus = "summary_only"
    summary: str = ""
    summary_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    raw_excerpt: str = ""


class MinutesRecord(BaseModel):
    """All stored minute summaries for one town, one board, across months."""

    model_config = ConfigDict(extra="forbid")

    town: str
    state: str
    board: str
    url_template: str
    stale_after_days: int = 30
    rolling_window_months: int = 12
    last_checked_at: str | None = None
    last_successful_refresh_at: str | None = None
    entries: list[MinuteEntry] = Field(default_factory=list)

    def entries_by_month(self) -> dict[str, MinuteEntry]:
        return {entry.month: entry for entry in self.entries}

    def is_stale(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if not self.last_checked_at:
            return True
        try:
            last = datetime.fromisoformat(self.last_checked_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        return (now - last) >= timedelta(days=self.stale_after_days)


def expected_months(now: datetime | None = None, window: int = 12) -> list[str]:
    """Return the rolling list of ``YYYY-MM`` strings ending at ``now`` (inclusive).

    Most recent month first so the runner can process newest first and stop
    early when it encounters a well-known gap.
    """

    now = now or datetime.now(timezone.utc)
    year, month = now.year, now.month
    months: list[str] = []
    for _ in range(max(1, window)):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months


def missing_months(
    record: MinutesRecord,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Months within the rolling window that have no fetched entry yet."""

    have = {entry.month for entry in record.entries if entry.status == "fetched"}
    return [m for m in expected_months(now=now, window=record.rolling_window_months) if m not in have]


__all__ = [
    "MinuteEntry",
    "MinuteStatus",
    "MinutesRecord",
    "expected_months",
    "missing_months",
]

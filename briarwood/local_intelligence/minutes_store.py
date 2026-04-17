"""File-backed store for per-town ``MinutesRecord`` manifests.

One JSON file per ``(town, state, board)`` triple at
``data/local_intelligence/minutes/<slug>.json``. All reads/writes go through
this store so the rest of the system never touches disk layout directly —
swapping to SQLite or an object store later means replacing this module
only.
"""

from __future__ import annotations

import json
from pathlib import Path

from briarwood.local_intelligence.minutes_registry import MinutesFeed
from briarwood.local_intelligence.minutes_schema import MinutesRecord


class JsonMinutesStore:
    """Disk-backed persistence for ``MinutesRecord`` objects."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (
            Path(__file__).resolve().parents[2]
            / "data"
            / "local_intelligence"
            / "minutes"
        )

    def load(self, feed: MinutesFeed) -> MinutesRecord | None:
        path = self._path(feed)
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return MinutesRecord.model_validate(payload)

    def save(self, feed: MinutesFeed, record: MinutesRecord) -> Path:
        path = self._path(feed)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True)
        )
        return path

    def load_or_initialize(self, feed: MinutesFeed) -> MinutesRecord:
        record = self.load(feed)
        if record is not None:
            return record
        return MinutesRecord(
            town=feed.town,
            state=feed.state,
            board=feed.board,
            url_template=feed.index_url_template or feed.direct_url_template or "",
            stale_after_days=feed.stale_after_days,
            rolling_window_months=feed.rolling_window_months,
        )

    def _path(self, feed: MinutesFeed) -> Path:
        return self.root / f"{feed.slug}.json"


__all__ = ["JsonMinutesStore"]

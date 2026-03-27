from __future__ import annotations

import json
from pathlib import Path


class FileBackedZillowHistoryProvider:
    """Load Zillow-style historical home value rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_town_history(self, *, town: str, state: str) -> dict[str, object] | None:
        return self._match(self._data.get("towns", []), geography_name=town, state=state)

    def get_county_history(self, *, county: str, state: str) -> dict[str, object] | None:
        return self._match(self._data.get("counties", []), geography_name=county, state=state)

    def _match(
        self,
        rows: list[dict[str, object]],
        *,
        geography_name: str,
        state: str,
    ) -> dict[str, object] | None:
        target_name = geography_name.strip().lower()
        target_state = state.strip().upper()
        for row in rows:
            row_name = str(row.get("name", "")).strip().lower()
            row_state = str(row.get("state", "")).strip().upper()
            if row_name == target_name and row_state == target_state:
                return row
        return None

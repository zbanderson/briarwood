from __future__ import annotations

import json
from pathlib import Path


class FileBackedPriceTrendProvider:
    """Load town and county price rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_town_row(self, *, town: str, state: str) -> dict[str, object] | None:
        return self._match(self._data.get("towns", []), geography_name=town, state=state)

    def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
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
            row_name = str(row.get("RegionName", "")).strip().lower()
            row_state = str(row.get("State", "")).strip().upper()
            if row_name == target_name and row_state == target_state:
                return row
        return None


class FileBackedPopulationProvider:
    """Load town and county population rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_town_row(self, *, town: str, state: str) -> dict[str, object] | None:
        return self._match(self._data.get("towns", []), geography_name=town, state=state)

    def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
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


class FileBackedFloodRiskProvider:
    """Load town flood-risk rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        target_name = town.strip().lower()
        target_state = state.strip().upper()
        for row in self._data.get("towns", []):
            row_name = str(row.get("name", "")).strip().lower()
            row_state = str(row.get("state", "")).strip().upper()
            if row_name == target_name and row_state == target_state:
                return row
        return None


class FileBackedLiquidityProvider:
    """Load town market-activity rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        target_name = town.strip().lower()
        target_state = state.strip().upper()
        for row in self._data.get("towns", []):
            row_name = str(row.get("name", "")).strip().lower()
            row_state = str(row.get("state", "")).strip().upper()
            if row_name == target_name and row_state == target_state:
                return row
        return None


class FileBackedFredMacroProvider:
    """Load county-level FRED-backed macro rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_county_row(self, *, county: str, state: str) -> dict[str, object] | None:
        target_name = county.strip().lower()
        target_state = state.strip().upper()
        for row in self._data.get("counties", []):
            row_name = str(row.get("name", "")).strip().lower()
            row_state = str(row.get("state", "")).strip().upper()
            if row_name == target_name and row_state == target_state:
                return row
        return None


class FileBackedTownProfileProvider:
    """Load explicit town-profile rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_town_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        target_name = town.strip().lower()
        target_state = state.strip().upper()
        target_county = county.strip().lower() if county else None
        for row in self._data.get("towns", []):
            row_name = str(row.get("name", "")).strip().lower()
            row_state = str(row.get("state", "")).strip().upper()
            row_county = str(row.get("county", "")).strip().lower()
            if row_name == target_name and row_state == target_state:
                if target_county is None or row_county == target_county:
                    return row
        return None


class FileBackedSchoolSignalProvider:
    """Load Briarwood school proxy rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_town_row(self, *, town: str, state: str, county: str | None = None) -> dict[str, object] | None:
        target_name = town.strip().lower()
        target_state = state.strip().upper()
        target_county = county.strip().lower() if county else None
        for row in self._data.get("towns", []):
            row_name = str(row.get("name", "")).strip().lower()
            row_state = str(row.get("state", "")).strip().upper()
            row_county = str(row.get("county", "")).strip().lower()
            if row_name == target_name and row_state == target_state:
                if target_county is None or row_county == target_county:
                    return row
        return None

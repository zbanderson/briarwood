from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class ZillowRentContext(BaseModel):
    """Market-level Zillow rental research context for rental ease."""

    model_config = ConfigDict(extra="forbid")

    geography_name: str
    state: str
    geography_type: str = Field(pattern="^(town|county)$")
    zori_current: float = Field(gt=0)
    zori_prior_year: float = Field(gt=0)
    zordi_score: float = Field(ge=0, le=100)
    zorf_one_year: float
    as_of: str
    source_name: str = "zillow_rent_research"

    @property
    def zori_growth(self) -> float:
        return (self.zori_current / self.zori_prior_year) - 1


class FileBackedZillowRentContextProvider:
    """Load market-level Zillow rent context rows from a JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        self._data = json.loads(Path(path).read_text())

    def get_town_context(self, *, town: str, state: str) -> ZillowRentContext | None:
        row = self._match(self._data.get("towns", []), geography_name=town, state=state)
        return ZillowRentContext.model_validate(row) if row is not None else None

    def get_county_context(self, *, county: str, state: str) -> ZillowRentContext | None:
        row = self._match(self._data.get("counties", []), geography_name=county, state=state)
        return ZillowRentContext.model_validate(row) if row is not None else None

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
            row_name = str(row.get("geography_name", "")).strip().lower()
            row_state = str(row.get("state", "")).strip().upper()
            if row_name == target_name and row_state == target_state:
                return row
        return None

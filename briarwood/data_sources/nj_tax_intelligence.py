from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from briarwood.data_quality.normalizers import normalize_town


@dataclass(slots=True)
class TownTaxIntelligence:
    town: str
    county: str
    tax_year: int
    general_tax_rate: float | None
    effective_tax_rate: float | None
    equalization_ratio: float | None
    equalized_valuation: float | None
    source_file: str
    last_updated: str | None = None


class NJTaxIntelligenceStore:
    def __init__(self, rows: list[TownTaxIntelligence] | None = None) -> None:
        self.rows = rows or []
        self._index = {(row.town, row.county, row.tax_year): row for row in self.rows}

    @classmethod
    def load_csv(cls, path: str | Path) -> "NJTaxIntelligenceStore":
        filepath = Path(path)
        with filepath.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = [row for row in reader]
        records = [normalize_nj_tax_row(row, source_file=str(filepath)) for row in rows]
        return cls([record for record in records if record is not None])

    def get(self, *, town: str, county: str, tax_year: int | None = None) -> TownTaxIntelligence | None:
        normalized_town = normalize_town(town) or "Unknown"
        normalized_county = normalize_county_name(county)
        if tax_year is not None:
            return self._index.get((normalized_town, normalized_county, tax_year))
        matches = [
            row
            for row in self.rows
            if row.town == normalized_town and row.county == normalized_county
        ]
        if not matches:
            return None
        matches.sort(key=lambda row: row.tax_year, reverse=True)
        return matches[0]


def normalize_nj_tax_row(row: dict[str, Any], *, source_file: str) -> TownTaxIntelligence | None:
    town = normalize_town(row.get("town") or row.get("municipality") or row.get("taxing_district")) or "Unknown"
    county = normalize_county_name(row.get("county"))
    tax_year = _optional_int(row.get("tax_year") or row.get("year"))
    if town == "Unknown" or county == "Unknown" or tax_year is None:
        return None
    return TownTaxIntelligence(
        town=town,
        county=county,
        tax_year=tax_year,
        general_tax_rate=_optional_float(row.get("general_tax_rate") or row.get("general_rate")),
        effective_tax_rate=_optional_float(row.get("effective_tax_rate") or row.get("effective_rate")),
        equalization_ratio=_optional_float(row.get("equalization_ratio")),
        equalized_valuation=_optional_float(row.get("equalized_valuation")),
        source_file=source_file,
        last_updated=_optional_text(row.get("last_updated") or row.get("updated_at")),
    )


def town_tax_context(store: NJTaxIntelligenceStore, *, town: str, county: str, tax_year: int | None = None) -> dict[str, Any]:
    record = store.get(town=town, county=county, tax_year=tax_year)
    if record is None:
        return {}
    return {
        "town": record.town,
        "county": record.county,
        "tax_year": record.tax_year,
        "general_tax_rate": record.general_tax_rate,
        "effective_tax_rate": record.effective_tax_rate,
        "equalization_ratio": record.equalization_ratio,
        "equalized_valuation": record.equalized_valuation,
        "source_file": record.source_file,
        "last_updated": record.last_updated,
    }


def normalize_county_name(value: object) -> str:
    text = _optional_text(value)
    if not text:
        return "Unknown"
    cleaned = text.replace(" County", "").strip()
    return cleaned.title()


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

"""
Enrich comparable sales with NJ MOD-IV property tax list data.

MOD-IV provides parcel-level detail (year_built, assessed values, lot acreage,
lat/lon from parcel centroids) that SR1A alone does not carry.

Data source: NJOGIS Open Data MOD-IV for Monmouth County.
The MOD-IV table can be loaded from CSV export, GeoJSON, or shapefile.
Join key: block/lot/qualifier within a district (municipality).
"""
from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.utils import current_year

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MODIVRecord:
    """A single parcel record from the MOD-IV tax list."""
    district_code: str
    block: str
    lot: str
    qualifier: str
    property_class: str
    year_built: int | None
    calc_acre: float | None
    assessed_land: int | None
    assessed_improvement: int | None
    latitude: float | None
    longitude: float | None
    land_description: str


# ── Known column aliases in various MOD-IV CSV exports ────────────────────────

_ALIASES: dict[str, list[str]] = {
    "district_code": ["district_code", "dist_code", "mun_code", "municipality_code", "taxdist"],
    "block": ["block", "blk", "prop_block", "tax_block"],
    "lot": ["lot", "prop_lot", "tax_lot"],
    "qualifier": ["qualifier", "qual", "prop_qual"],
    "property_class": ["property_class", "prop_class", "class", "class_code"],
    "year_built": ["year_built", "yr_built", "yearbuilt", "yr_blt"],
    "calc_acre": ["calc_acre", "calcacre", "acres", "lot_acres", "lot_acreage"],
    "assessed_land": ["assessed_land", "assd_land", "land_value", "val_land", "landvalue"],
    "assessed_improvement": [
        "assessed_improvement", "assd_improv", "improv_value", "bldg_value",
        "val_improv", "improvvalue", "assessed_building",
    ],
    "latitude": ["latitude", "lat", "y", "centroid_lat"],
    "longitude": ["longitude", "lon", "lng", "x", "centroid_lon"],
    "land_description": ["land_description", "land_desc", "landdesc", "prop_desc"],
}


def _resolve_column(headers: list[str], field: str) -> str | None:
    """Find the actual column name that matches a logical field."""
    aliases = _ALIASES.get(field, [field])
    normalized = {h.strip().lower().replace(" ", "_").replace("-", "_"): h for h in headers}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def _safe_float(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    try:
        v = float(value.strip().replace(",", ""))
        return v if v != 0 else None
    except ValueError:
        return None


def _safe_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    try:
        return int(float(value.strip().replace(",", "")))
    except (ValueError, OverflowError):
        return None


def _valid_year_built(year: int | None) -> int | None:
    if year is None:
        return None
    if year < 1700 or year > current_year():
        return None
    return year


def _valid_acreage(acres: float | None) -> float | None:
    """CALC_ACRE can be 0 for irregular-shaped lots — treat as None."""
    if acres is None or acres <= 0:
        return None
    return round(acres, 4)


def _normalize_block_lot(value: str) -> str:
    """Strip leading zeros and whitespace for matching."""
    return re.sub(r"^0+", "", value.strip()) or "0"


@dataclass(slots=True)
class MODIVLookupResult:
    """Counts from a MOD-IV enrichment run."""
    total_records_loaded: int = 0
    lookups_attempted: int = 0
    lookups_matched: int = 0
    year_built_enriched: int = 0
    acreage_enriched: int = 0
    latlon_enriched: int = 0


class MODIVEnricher:
    """Load a MOD-IV export and enrich ComparableSale records by block/lot lookup."""

    def __init__(self) -> None:
        self._index: dict[str, MODIVRecord] = {}

    def load_csv(self, path: str | Path) -> int:
        """Load MOD-IV records from a CSV export. Returns count loaded."""
        filepath = Path(path)
        if not filepath.exists():
            logger.warning("MOD-IV file not found: %s", filepath)
            return 0

        count = 0
        with filepath.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                logger.warning("MOD-IV CSV has no header row")
                return 0

            headers = list(reader.fieldnames)
            col = {field: _resolve_column(headers, field) for field in _ALIASES}

            for row in reader:
                district = (row.get(col["district_code"] or "", "") or "").strip()
                block = (row.get(col["block"] or "", "") or "").strip()
                lot = (row.get(col["lot"] or "", "") or "").strip()
                qualifier = (row.get(col["qualifier"] or "", "") or "").strip()

                if not block or not lot:
                    continue

                record = MODIVRecord(
                    district_code=district,
                    block=block,
                    lot=lot,
                    qualifier=qualifier,
                    property_class=(row.get(col["property_class"] or "", "") or "").strip(),
                    year_built=_valid_year_built(_safe_int(row.get(col["year_built"] or ""))),
                    calc_acre=_valid_acreage(_safe_float(row.get(col["calc_acre"] or ""))),
                    assessed_land=_safe_int(row.get(col["assessed_land"] or "")),
                    assessed_improvement=_safe_int(row.get(col["assessed_improvement"] or "")),
                    latitude=_safe_float(row.get(col["latitude"] or "")),
                    longitude=_safe_float(row.get(col["longitude"] or "")),
                    land_description=(row.get(col["land_description"] or "", "") or "").strip(),
                )
                key = self._make_key(district, block, lot, qualifier)
                self._index[key] = record
                count += 1

        logger.info("MOD-IV loaded %d parcel records from %s", count, filepath)
        return count

    def load_geojson(self, path: str | Path) -> int:
        """Load MOD-IV records from a GeoJSON file with parcel centroids."""
        filepath = Path(path)
        if not filepath.exists():
            logger.warning("MOD-IV GeoJSON not found: %s", filepath)
            return 0

        data = json.loads(filepath.read_text(encoding="utf-8"))
        features = data.get("features", [])
        count = 0

        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry")
            block = str(props.get("BLOCK", props.get("block", ""))).strip()
            lot = str(props.get("LOT", props.get("lot", ""))).strip()
            if not block or not lot:
                continue

            lat, lon = None, None
            if geom and geom.get("type") == "Point":
                coords = geom.get("coordinates", [])
                if len(coords) >= 2:
                    lon, lat = float(coords[0]), float(coords[1])

            district = str(props.get("DIST_CODE", props.get("district_code", ""))).strip()
            qualifier = str(props.get("QUALIFIER", props.get("qualifier", ""))).strip()

            record = MODIVRecord(
                district_code=district,
                block=block,
                lot=lot,
                qualifier=qualifier,
                property_class=str(props.get("PROPERTY_CLASS", props.get("property_class", ""))).strip(),
                year_built=_valid_year_built(_safe_int(str(props.get("YEAR_BUILT", props.get("year_built", ""))))),
                calc_acre=_valid_acreage(_safe_float(str(props.get("CALC_ACRE", props.get("calc_acre", ""))))),
                assessed_land=_safe_int(str(props.get("ASSESSED_LAND", props.get("val_land", "")))),
                assessed_improvement=_safe_int(str(props.get("ASSESSED_IMPROV", props.get("val_improv", "")))),
                latitude=lat,
                longitude=lon,
                land_description=str(props.get("LAND_DESC", props.get("land_description", ""))).strip(),
            )
            key = self._make_key(district, block, lot, qualifier)
            self._index[key] = record
            count += 1

        logger.info("MOD-IV loaded %d parcels from GeoJSON %s", count, filepath)
        return count

    @property
    def record_count(self) -> int:
        return len(self._index)

    def lookup(self, district_code: str, block: str, lot: str, qualifier: str = "") -> MODIVRecord | None:
        """Look up a parcel by district/block/lot/qualifier."""
        key = self._make_key(district_code, block, lot, qualifier)
        record = self._index.get(key)
        if record is not None:
            return record
        # Retry without qualifier (common for non-condo parcels)
        if qualifier:
            key_no_qual = self._make_key(district_code, block, lot, "")
            return self._index.get(key_no_qual)
        return None

    def enrich_sales(self, sales: list[ComparableSale], district_map_reverse: dict[str, str] | None = None) -> MODIVLookupResult:
        """Enrich a list of ComparableSale records with MOD-IV data.

        Parses block/lot from each sale's source_notes (SR1A records embed
        "Block/Lot 123/456" in source_notes).

        Args:
            sales: List of ComparableSale records to enrich in place.
            district_map_reverse: town name → district code mapping. If None,
                builds from MONMOUTH_DISTRICT_CODES.
        """
        from briarwood.agents.comparable_sales.sr1a_parser import MONMOUTH_DISTRICT_CODES

        if district_map_reverse is None:
            district_map_reverse = {v: k for k, v in MONMOUTH_DISTRICT_CODES.items()}

        result = MODIVLookupResult(total_records_loaded=self.record_count)

        for sale in sales:
            block_lot = self._extract_block_lot_from_notes(sale.source_notes)
            if block_lot is None:
                continue

            block, lot = block_lot
            district_code = district_map_reverse.get(sale.town, "")
            if not district_code:
                continue

            result.lookups_attempted += 1
            record = self.lookup(district_code, block, lot)
            if record is None:
                continue

            result.lookups_matched += 1

            # Enrich year_built if not already set
            if sale.year_built is None and record.year_built is not None:
                sale.year_built = record.year_built
                result.year_built_enriched += 1

            # Enrich lot_size (convert acres) if not already set
            if sale.lot_size is None and record.calc_acre is not None:
                sale.lot_size = record.calc_acre
                result.acreage_enriched += 1

            # Enrich lat/lon if not already set
            if sale.latitude is None and record.latitude is not None:
                sale.latitude = record.latitude
                sale.longitude = record.longitude
                result.latlon_enriched += 1

        logger.info(
            "MOD-IV enrichment: %d attempted, %d matched, "
            "%d year_built, %d acreage, %d lat/lon enriched",
            result.lookups_attempted,
            result.lookups_matched,
            result.year_built_enriched,
            result.acreage_enriched,
            result.latlon_enriched,
        )
        return result

    @staticmethod
    def _make_key(district: str, block: str, lot: str, qualifier: str = "") -> str:
        """Normalize and combine into a lookup key."""
        d = district.strip().zfill(2)
        b = _normalize_block_lot(block)
        l = _normalize_block_lot(lot)
        q = qualifier.strip().upper()
        return f"{d}|{b}|{l}|{q}"

    @staticmethod
    def _extract_block_lot_from_notes(notes: str | None) -> tuple[str, str] | None:
        """Extract block/lot from SR1A-generated source_notes like 'Block/Lot 123/456'."""
        if not notes:
            return None
        m = re.search(r"Block/Lot\s+([^;/]+)/([^;]+)", notes)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return None

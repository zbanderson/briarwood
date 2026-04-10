"""
Parse NJ SR1A fixed-width sales files into ComparableSale records.

The SR1A is the state-verified deed transfer record published by the
NJ Division of Taxation.  Layout defined in:
https://www.nj.gov/treasury/taxation/pdf/lpt/SR1A_FileLayout_Description.pdf

Each record is 662 characters, fixed-width, 1-indexed positions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ComparableSale
from briarwood.utils import current_year

logger = logging.getLogger(__name__)

# ── Monmouth County district code → town name ────────────────────────────────
# Source: NJ Division of Taxation, County 13 = Monmouth.
# These are the 53 municipalities in Monmouth County.

MONMOUTH_DISTRICT_CODES: dict[str, str] = {
    "01": "Aberdeen",
    "02": "Allenhurst",
    "03": "Allentown",
    "04": "Asbury Park",
    "05": "Atlantic Highlands",
    "06": "Avon-by-the-Sea",
    "07": "Belmar",
    "08": "Bradley Beach",
    "09": "Brielle",
    "10": "Colts Neck",
    "11": "Deal",
    "12": "Eatontown",
    "13": "Englishtown",
    "14": "Fair Haven",
    "15": "Farmingdale",
    "16": "Freehold Borough",
    "17": "Freehold Township",
    "18": "Hazlet",
    "19": "Highlands",
    "20": "Holmdel",
    "21": "Howell",
    "22": "Interlaken",
    "23": "Keansburg",
    "24": "Keyport",
    "25": "Lake Como",
    "26": "Little Silver",
    "27": "Loch Arbour",
    "28": "Long Branch",
    "29": "Manalapan",
    "30": "Manasquan",
    "31": "Marlboro",
    "32": "Matawan",
    "33": "Middletown",
    "34": "Millstone",
    "35": "Monmouth Beach",
    "36": "Neptune Township",
    "37": "Neptune City",
    "38": "Ocean Township",
    "39": "Oceanport",
    "40": "Red Bank",
    "41": "Roosevelt",
    "42": "Rumson",
    "43": "Sea Bright",
    "44": "Sea Girt",
    "45": "Shrewsbury Borough",
    "46": "Shrewsbury Township",
    "47": "Spring Lake",
    "48": "Spring Lake Heights",
    "49": "Tinton Falls",
    "50": "Union Beach",
    "51": "Upper Freehold",
    "52": "Wall",
    "53": "West Long Branch",
}

# Property classes we consider residential for comp purposes.
RESIDENTIAL_PROPERTY_CLASSES = {"2", " 2", "2 ", "4C"}

# Minimum sale price to filter out nominal / $1 transfers that slip through.
MIN_SALE_PRICE = 10_000


@dataclass(slots=True)
class SR1ARawRecord:
    """Raw parsed fields from a single SR1A line, before mapping to ComparableSale."""
    county_code: str
    district_code: str
    un_type: str
    nu_code: str
    reported_sales_price: int
    verified_sales_price: int
    assessed_land: int
    assessed_bldg: int
    assessed_total: int
    property_location: str
    deed_date: str  # raw MMDDYY
    block: str
    block_suffix: str
    lot: str
    lot_suffix: str
    qualification_code: str
    property_class: str
    condo_flag: str
    year_built: int | None
    living_space: int | None
    serial_number: str
    deed_book: str
    deed_page: str
    grantor_name: str
    grantee_name: str


def _slice(line: str, start: int, end: int) -> str:
    """Extract 1-indexed positions from a fixed-width line."""
    return line[start - 1 : end].strip()


def _parse_int_safe(value: str) -> int | None:
    """Parse a numeric string, returning None for blanks/zeros."""
    cleaned = value.strip()
    if not cleaned or not cleaned.isdigit():
        return None
    v = int(cleaned)
    return v if v > 0 else None


def parse_sr1a_line(line: str) -> SR1ARawRecord | None:
    """Parse a single fixed-width SR1A line into a raw record.

    Returns None if the line is too short or clearly malformed.
    """
    if len(line) < 662:
        return None

    year_built_raw = _parse_int_safe(_slice(line, 652, 655))
    living_space_raw = _parse_int_safe(_slice(line, 656, 662))

    return SR1ARawRecord(
        county_code=_slice(line, 1, 2),
        district_code=_slice(line, 3, 4),
        un_type=_slice(line, 34, 34),
        nu_code=_slice(line, 35, 37),
        reported_sales_price=int(_slice(line, 38, 46) or "0"),
        verified_sales_price=int(_slice(line, 47, 55) or "0"),
        assessed_land=int(_slice(line, 56, 64) or "0"),
        assessed_bldg=int(_slice(line, 65, 73) or "0"),
        assessed_total=int(_slice(line, 74, 82) or "0"),
        property_location=_slice(line, 298, 322),
        deed_date=_slice(line, 339, 344),
        block=_slice(line, 351, 355),
        block_suffix=_slice(line, 356, 359),
        lot=_slice(line, 360, 364),
        lot_suffix=_slice(line, 365, 368),
        qualification_code=_slice(line, 620, 624),
        property_class=_slice(line, 627, 628),
        condo_flag=_slice(line, 649, 649),
        year_built=year_built_raw,
        living_space=living_space_raw,
        serial_number=_slice(line, 99, 105),
        deed_book=_slice(line, 329, 333),
        deed_page=_slice(line, 334, 338),
        grantor_name=_slice(line, 110, 144),
        grantee_name=_slice(line, 204, 238),
    )


def _parse_deed_date(raw: str) -> str | None:
    """Convert SR1A YYMMDD deed date to YYYY-MM-DD.

    Handles 2-digit years: 00-49 → 2000s, 50-99 → 1900s.
    """
    if not raw or len(raw) != 6:
        return None
    try:
        dt = datetime.strptime(raw, "%y%m%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _best_sale_price(record: SR1ARawRecord) -> float | None:
    """Use verified price if available, fall back to reported."""
    if record.verified_sales_price > 0:
        return float(record.verified_sales_price)
    if record.reported_sales_price > 0:
        return float(record.reported_sales_price)
    return None


def _full_block_lot(record: SR1ARawRecord) -> str:
    """Combine block + suffix and lot + suffix into a canonical block/lot string."""
    block = record.block
    if record.block_suffix:
        block += f".{record.block_suffix}"
    lot = record.lot
    if record.lot_suffix:
        lot += f".{record.lot_suffix}"
    return f"{block}/{lot}"


def _is_usable_sale(record: SR1ARawRecord) -> bool:
    """Return True if the sale is arm's-length (usable for ratio study)."""
    return record.un_type.upper() == "U"


def _is_residential(record: SR1ARawRecord) -> bool:
    """Return True if property class indicates residential."""
    pc = record.property_class.strip()
    return pc in RESIDENTIAL_PROPERTY_CLASSES


def _valid_year_built(year: int | None) -> int | None:
    """Validate year_built: reject impossible values."""
    if year is None:
        return None
    if year < 1700 or year > current_year():
        return None
    return year


def _valid_sqft(sqft: int | None) -> int | None:
    """Validate living space: reject zero and implausibly small values."""
    if sqft is None or sqft <= 0:
        return None
    return sqft


def _property_type_from_class(record: SR1ARawRecord) -> str | None:
    """Infer property type from property class and condo flag."""
    pc = record.property_class.strip()
    if pc == "4C":
        return "apartment"
    if record.condo_flag.upper() == "Y" or record.qualification_code.startswith("C"):
        return "condo"
    if pc == "2":
        return "single_family"
    return None


def _source_ref(record: SR1ARawRecord, town: str) -> str:
    """Build a stable, unique source_ref for deduplication."""
    block_lot = _full_block_lot(record)
    date = _parse_deed_date(record.deed_date) or "unknown"
    town_slug = re.sub(r"[^a-z0-9]+", "-", town.lower()).strip("-")
    return f"SR1A-{town_slug}-{block_lot}-{date}"


@dataclass(slots=True)
class SR1AParseResult:
    """Summary of a parse run."""
    total_lines: int = 0
    skipped_short: int = 0
    skipped_county: int = 0
    skipped_non_usable: int = 0
    skipped_non_residential: int = 0
    skipped_no_price: int = 0
    skipped_low_price: int = 0
    skipped_no_date: int = 0
    skipped_district_unknown: int = 0
    parsed: int = 0
    sales: list[ComparableSale] = field(default_factory=list)


def parse_sr1a_file(
    path: str | Path,
    *,
    county_code: str = "13",
    target_districts: list[str] | None = None,
    district_map: dict[str, str] | None = None,
) -> SR1AParseResult:
    """Parse an SR1A fixed-width file and return ComparableSale records.

    Args:
        path: Path to the SR1A flat file.
        county_code: 2-digit county code to filter (default "13" = Monmouth).
        target_districts: If non-empty, only include these district codes.
            Empty list or None = all districts in the county.
        district_map: Mapping of district_code → town name. Defaults to
            MONMOUTH_DISTRICT_CODES for county 13.
    """
    if district_map is None:
        district_map = MONMOUTH_DISTRICT_CODES if county_code == "13" else {}

    result = SR1AParseResult()
    filepath = Path(path)

    if not filepath.exists():
        logger.warning("SR1A file not found: %s", filepath)
        return result

    with filepath.open("r", encoding="latin-1") as fh:
        for line in fh:
            result.total_lines += 1
            raw = parse_sr1a_line(line)
            if raw is None:
                result.skipped_short += 1
                continue

            # County filter
            if raw.county_code != county_code:
                result.skipped_county += 1
                continue

            # District filter
            if target_districts and raw.district_code not in target_districts:
                result.skipped_county += 1
                continue

            # Usable arm's-length sale
            if not _is_usable_sale(raw):
                result.skipped_non_usable += 1
                continue

            # Residential property class
            if not _is_residential(raw):
                result.skipped_non_residential += 1
                continue

            # Sale price
            price = _best_sale_price(raw)
            if price is None:
                result.skipped_no_price += 1
                continue
            if price < MIN_SALE_PRICE:
                result.skipped_low_price += 1
                continue

            # Deed date
            deed_date = _parse_deed_date(raw.deed_date)
            if deed_date is None:
                result.skipped_no_date += 1
                continue

            # Town name
            town = district_map.get(raw.district_code)
            if town is None:
                result.skipped_district_unknown += 1
                continue

            sale = ComparableSale(
                address=raw.property_location or "",
                town=town,
                state="NJ",
                property_type=_property_type_from_class(raw),
                sale_price=price,
                sale_date=deed_date,
                sqft=_valid_sqft(raw.living_space),
                year_built=_valid_year_built(raw.year_built),
                verification_status="public_record",
                source_name="NJ SR1A",
                source_quality="public_record",
                source_ref=_source_ref(raw, town),
                source_notes=f"Block/Lot {_full_block_lot(raw)}; assessed total ${raw.assessed_total:,}",
                comp_status="reviewed",
                address_verification_status="verified",
                sale_verification_status="public_record_verified",
                verification_source_type="public_record",
                verification_source_name="NJ Division of Taxation SR1A",
                verification_source_id=f"SR1A-{raw.serial_number}",
            )
            result.sales.append(sale)
            result.parsed += 1

    logger.info(
        "SR1A parse complete: %d lines, %d parsed, %d non-usable, "
        "%d non-residential, %d skipped (county/district/price/date)",
        result.total_lines,
        result.parsed,
        result.skipped_non_usable,
        result.skipped_non_residential,
        result.skipped_county + result.skipped_no_price + result.skipped_low_price
        + result.skipped_no_date + result.skipped_district_unknown,
    )
    return result

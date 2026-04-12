from __future__ import annotations

from datetime import datetime
import re


MISSING_TEXT = {"", "n/a", "na", "none", "null", "unknown", "--", "-", "tbd"}
ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
ADDRESS_SUFFIX_RE = re.compile(r",?\s*[A-Za-z .'-]+,\s*[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?$")
TOWN_ALIASES = {
    "asb": "Asbury Park",
    "asbury": "Asbury Park",
    "ap": "Asbury Park",
    "avon": "Avon-by-the-Sea",
    "avon by sea": "Avon-by-the-Sea",
    "avon by the sea": "Avon-by-the-Sea",
    "avonbythesea": "Avon-by-the-Sea",
    "spring lake hts": "Spring Lake Heights",
    "wall": "Wall Township",
    "wall twp": "Wall Township",
}
COUNTY_BY_ZIP = {
    "02445": "Norfolk",
    "07719": "Monmouth",
}
COUNTY_BY_TOWN_STATE = {
    ("brookline", "MA"): "Norfolk",
    ("belmar", "NJ"): "Monmouth",
    ("asbury park", "NJ"): "Monmouth",
    ("avon-by-the-sea", "NJ"): "Monmouth",
    ("spring lake heights", "NJ"): "Monmouth",
    ("wall township", "NJ"): "Monmouth",
}
LISTING_DESCRIPTION_HINTS = (
    "welcome to",
    "beautiful",
    "charming",
    "opportunity",
    "minutes from",
    "beach",
    "shore",
    "marina",
    "downtown",
)
MALFORMED_ADDRESS_TOKENS = ("unit available", "call agent", "investor special", "see remarks")


def treat_missing(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in MISSING_TEXT:
            return None
        return text
    return value


def normalize_address_string(value: object) -> str | None:
    text = treat_missing(value)
    if text is None:
        return None
    assert isinstance(text, str)
    text = ZIP_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if parts:
            text = parts[0]
    return text.title() if text else None


def strip_redundant_address_suffix(value: object) -> str | None:
    text = treat_missing(value)
    if text is None:
        return None
    assert isinstance(text, str)
    cleaned = ADDRESS_SUFFIX_RE.sub("", text).strip(" ,")
    cleaned = ZIP_RE.sub("", cleaned).strip(" ,")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def normalize_town(value: object) -> str | None:
    text = treat_missing(value)
    if text is None:
        return None
    assert isinstance(text, str)
    cleaned = re.sub(r"[-_]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    alias = TOWN_ALIASES.get(cleaned.lower())
    return alias or cleaned.title()


def normalize_state(value: object) -> str | None:
    text = treat_missing(value)
    if text is None:
        return None
    assert isinstance(text, str)
    return text.strip().upper()[:2] or None


def infer_county(*, town: object, state: object, zip_code: object = None) -> str | None:
    normalized_zip = treat_missing(zip_code)
    if isinstance(normalized_zip, str):
        zip_match = ZIP_RE.search(normalized_zip)
        if zip_match:
            county = COUNTY_BY_ZIP.get(zip_match.group(0)[:5])
            if county:
                return county

    normalized_town = normalize_town(town)
    normalized_state = normalize_state(state)
    if normalized_town and normalized_state:
        return COUNTY_BY_TOWN_STATE.get((normalized_town.lower(), normalized_state))
    return None


def normalize_numeric(value: object) -> float | int | None:
    coerced = treat_missing(value)
    if coerced is None:
        return None
    if isinstance(coerced, (int, float)):
        return coerced
    try:
        text = str(coerced).replace("$", "").replace(",", "").strip()
        if not text:
            return None
        number = float(text)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def normalize_lot_size(value: object) -> float | None:
    number = normalize_numeric(value)
    if number is None:
        return None
    number = float(number)
    if number > 10:
        number = number / 43560.0
    return round(number, 4) if number > 0 else None


def normalize_sqft(value: object) -> int | None:
    number = normalize_numeric(value)
    if number is None:
        return None
    sqft = int(float(number))
    return sqft if sqft > 0 else None


def normalize_date(value: object) -> str | None:
    text = treat_missing(value)
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.date().isoformat()
    assert isinstance(text, str)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def is_listing_description_as_address(value: object) -> bool:
    text = treat_missing(value)
    if text is None:
        return False
    assert isinstance(text, str)
    lowered = text.lower()
    if len(text) > 120:
        return True
    if not re.search(r"\d", text):
        return any(hint in lowered for hint in LISTING_DESCRIPTION_HINTS)
    return sum(1 for hint in LISTING_DESCRIPTION_HINTS if hint in lowered) >= 2


def is_malformed_address(value: object) -> bool:
    text = treat_missing(value)
    if text is None:
        return True
    assert isinstance(text, str)
    lowered = text.lower()
    if any(token in lowered for token in MALFORMED_ADDRESS_TOKENS):
        return True
    if len(text) < 6:
        return True
    if not re.search(r"\d", text):
        return True
    street_tokens = ("st", "street", "ave", "avenue", "rd", "road", "blvd", "drive", "dr", "lane", "ln", "way", "place", "pl", "court", "ct")
    return not any(re.search(rf"\b{token}\b", lowered) for token in street_tokens)

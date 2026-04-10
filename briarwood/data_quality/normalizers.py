from __future__ import annotations

from datetime import datetime
import re


MISSING_TEXT = {"", "n/a", "na", "none", "null", "unknown", "--", "-", "tbd"}
ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
ADDRESS_SUFFIX_RE = re.compile(r",?\s*[A-Za-z .'-]+,\s*[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?$")
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


def normalize_town(value: object) -> str | None:
    text = treat_missing(value)
    if text is None:
        return None
    assert isinstance(text, str)
    cleaned = re.sub(r"[-_]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else None


def normalize_state(value: object) -> str | None:
    text = treat_missing(value)
    if text is None:
        return None
    assert isinstance(text, str)
    return text.strip().upper()[:2] or None


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
    if number > 5000:
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


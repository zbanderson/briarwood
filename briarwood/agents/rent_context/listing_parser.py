"""Extract per-unit details from a listing description."""
from __future__ import annotations

import re

from briarwood.schemas import UnitDetail

# Patterns that signal the start of a rental-unit description block.
_UNIT_BOUNDARY = re.compile(
    r"""
    (?:(?:downstairs|upstairs|rear|back|lower|upper|unit\s*\d*|apt\.?\s*\d*)\s+is\s+)  # "Downstairs is a …"
    |(?:(?:downstairs|upstairs|rear|back|lower|upper|unit\s*\d*|apt\.?\s*\d*)[\s:,]+(?:a\s+)?)  # "Upstairs: a …"
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SQFT = re.compile(r"(\d{3,5})\s*(?:sf|sq\s*ft|square\s*f(?:ee)?t)", re.IGNORECASE)
_BEDS = re.compile(r"(\d)\s*(?:BR|bed(?:room)?s?)\b", re.IGNORECASE)
_BATHS = re.compile(r"(\d(?:\.\d)?)\s*(?:BA|bath(?:room)?s?)\b", re.IGNORECASE)

_CONDITION_KEYWORDS: dict[str, str] = {
    "renovated": "renovated",
    "remodeled": "remodeled",
    "updated": "updated",
    "new": "updated",
    "modern": "updated",
    "dated": "dated",
    "original": "dated",
    "needs work": "needs_work",
    "needs updating": "dated",
    "fixer": "needs_work",
}

_LABEL_MAP: dict[str, str] = {
    "downstairs": "rear downstairs",
    "lower": "rear downstairs",
    "upstairs": "rear upstairs",
    "upper": "rear upstairs",
    "rear": "rear unit",
    "back": "rear unit",
}


def parse_units_from_listing(description: str) -> list[UnitDetail]:
    """Extract unit details from a listing description.

    Looks for phrases like:
      "Downstairs is a remodeled 700sf 2BR …"
      "Upstairs is a dated 480sf 1BR …"

    Returns a UnitDetail for each detected unit block.
    """
    if not description:
        return []

    units: list[UnitDetail] = []

    # Split on unit-boundary markers and capture which label matched.
    # We'll scan the description for each boundary match and grab the
    # text that follows it (up to the next boundary or end of string).
    boundaries = list(_UNIT_BOUNDARY.finditer(description))
    if not boundaries:
        return []

    for i, match in enumerate(boundaries):
        start = match.end()
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(description)
        chunk = description[start:end]

        # Derive label from the boundary match text.
        boundary_text = match.group(0).strip().lower()
        label = "rear unit"
        for keyword, mapped_label in _LABEL_MAP.items():
            if keyword in boundary_text:
                label = mapped_label
                break

        sqft_m = _SQFT.search(chunk)
        beds_m = _BEDS.search(chunk)
        baths_m = _BATHS.search(chunk)

        # Need at least beds or sqft to consider this a valid unit extraction.
        if beds_m is None and sqft_m is None:
            continue

        condition = None
        chunk_lower = chunk.lower()
        for kw, cond_val in _CONDITION_KEYWORDS.items():
            if kw in chunk_lower:
                condition = cond_val
                break

        units.append(
            UnitDetail(
                label=label,
                beds=int(beds_m.group(1)) if beds_m else None,
                baths=float(baths_m.group(1)) if baths_m else None,
                sqft=int(sqft_m.group(1)) if sqft_m else None,
                condition=condition,
                rent_source="listing_parsed",
            )
        )

    return units

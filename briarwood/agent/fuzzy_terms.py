"""Deterministic natural-language → structured-filter translation.

The LLM is *not* trusted to invent filter keys. This module resolves known
phrases and numeric patterns into the fixed filter keys accepted by
briarwood.agent.index.search. Anything left over is returned as a residual
for optional LLM handling.

Order of resolution in translate():
  1. Longest-phrase fuzzy term match, consumed from the text
  2. Regex pass for numeric constraints (price, beds, baths, blocks, miles)
  3. Residual text returned for the caller to optionally send to an LLM

The dictionary is intentionally small and versioned. Growth requires a
conscious edit here, not a silent LLM expansion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Map fuzzy phrase → fixed filter(s).
FUZZY_TERMS: dict[str, dict[str, Any]] = {
    "on the beach": {"max_distance_to_beach_miles": 0.15},
    "oceanfront": {"max_distance_to_beach_miles": 0.1},
    "closer to the beach": {"max_distance_to_beach_miles": 0.4},
    "close to the beach": {"max_distance_to_beach_miles": 0.5},
    "close to beach": {"max_distance_to_beach_miles": 0.5},
    "near the beach": {"max_distance_to_beach_miles": 0.5},
    "near beach": {"max_distance_to_beach_miles": 0.5},
    "beach block": {"within_blocks_of_beach": 2},
    "walkable": {"max_distance_to_downtown_miles": 0.75},
    "walk to town": {"max_distance_to_downtown_miles": 0.6},
    "near the train": {"max_distance_to_train_miles": 0.5},
    "near train": {"max_distance_to_train_miles": 0.5},
    "near the station": {"max_distance_to_train_miles": 0.5},
    "large lot": {"lot_size_acres_min": 0.25},
    "big lot": {"lot_size_acres_min": 0.25},
    "newer build": {"year_built_min": 1990},
    "older home": {"year_built_max": 1950},
    "historic": {"year_built_max": 1930},
    "turn-key": {"min_confidence": 0.7},
    "turnkey": {"min_confidence": 0.7},
    "nearby": {"max_distance_to_beach_miles": 1.0},
    "close by": {"max_distance_to_beach_miles": 1.0},
    "closeby": {"max_distance_to_beach_miles": 1.0},
}


@dataclass
class TranslationResult:
    filters: dict[str, Any] = field(default_factory=dict)
    matched_phrases: list[str] = field(default_factory=list)
    residual: str = ""


_PRICE_PATTERN = re.compile(
    r"""(?ix)
    (?:
        (?:under|below|less\s+than|max|up\s+to|<=?)\s*
        \$?\s*([\d,\.]+)\s*(k|m)?
    )
    |
    (?:
        (?:over|above|more\s+than|min|>=?)\s*
        \$?\s*([\d,\.]+)\s*(k|m)?
    )
    """
)

_BEDS_PATTERN = re.compile(
    r"""(?ix)
    (?:
        (?P<lo>\d+)\s*(?:\+|\s+or\s+more|\s*plus)[\s-]*(?:bed|beds|bedroom|bedrooms|br)\b
    )
    |
    (?:
        (?P<exact>\d+)[\s-]*(?:bed|beds|bedroom|bedrooms|br)\b
    )
    """
)

_BATHS_PATTERN = re.compile(
    r"(?ix)(?P<n>\d+(?:\.\d+)?)\s*(?:bath|baths|bathroom|bathrooms|ba)\b"
)

_BLOCKS_PATTERN = re.compile(
    r"(?ix)within\s+(?P<n>\d+)\s*blocks?\s*(?:of|to|from)?\s*(?:the\s+)?beach"
)

_MILES_BEACH_PATTERN = re.compile(
    r"(?ix)within\s+(?P<n>\d+(?:\.\d+)?)\s*mi(?:le|les)?\s*(?:of|to|from)?\s*(?:the\s+)?beach"
)


def _parse_money(raw: str, suffix: str | None) -> float | None:
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    if suffix:
        s = suffix.lower()
        if s == "k":
            value *= 1_000
        elif s == "m":
            value *= 1_000_000
    # Bare sub-10 numbers with no suffix (e.g. "under 1.5") are treated as millions.
    if suffix is None and value < 10:
        value *= 1_000_000
    return value


def _apply_longest_phrases(text: str, filters: dict[str, Any], matched: list[str]) -> str:
    lowered = text.lower()
    for phrase in sorted(FUZZY_TERMS, key=len, reverse=True):
        if phrase in lowered:
            for key, value in FUZZY_TERMS[phrase].items():
                filters.setdefault(key, value)
            matched.append(phrase)
            lowered = lowered.replace(phrase, " ")
    return lowered


def _apply_prices(text: str, filters: dict[str, Any]) -> str:
    out = text
    for match in _PRICE_PATTERN.finditer(text):
        if match.group(1):
            price = _parse_money(match.group(1), match.group(2))
            if price is not None:
                filters.setdefault("max_price", price)
        elif match.group(3):
            price = _parse_money(match.group(3), match.group(4))
            if price is not None:
                filters.setdefault("min_price", price)
        out = out.replace(match.group(0), " ")
    return out


def _apply_beds(text: str, filters: dict[str, Any]) -> str:
    out = text
    for match in _BEDS_PATTERN.finditer(text):
        if match.group("lo"):
            filters.setdefault("beds_min", int(match.group("lo")))
        elif match.group("exact"):
            filters.setdefault("beds", int(match.group("exact")))
        out = out.replace(match.group(0), " ")
    return out


def _apply_baths(text: str, filters: dict[str, Any]) -> str:
    out = text
    for match in _BATHS_PATTERN.finditer(text):
        filters.setdefault("baths_min", float(match.group("n")))
        out = out.replace(match.group(0), " ")
    return out


def _apply_proximity(text: str, filters: dict[str, Any]) -> str:
    out = text
    for match in _BLOCKS_PATTERN.finditer(text):
        filters["within_blocks_of_beach"] = int(match.group("n"))
        out = out.replace(match.group(0), " ")
    for match in _MILES_BEACH_PATTERN.finditer(out):
        filters["max_distance_to_beach_miles"] = float(match.group("n"))
        out = out.replace(match.group(0), " ")
    return out


def translate(text: str) -> TranslationResult:
    """Resolve a natural-language query into structured filters."""
    if not text.strip():
        return TranslationResult()

    filters: dict[str, Any] = {}
    matched: list[str] = []

    remaining = _apply_longest_phrases(text, filters, matched)
    remaining = _apply_proximity(remaining, filters)
    remaining = _apply_beds(remaining, filters)
    remaining = _apply_baths(remaining, filters)
    remaining = _apply_prices(remaining, filters)

    # Drop unsupported keys silently — they came from our own dictionary so
    # adding one without a matching filter key in index.py is a bug; flag it
    # here so a test catches it.
    from briarwood.agent.index import FILTER_KEYS

    unknown = set(filters) - FILTER_KEYS
    if unknown:
        raise RuntimeError(
            f"fuzzy_terms produced unsupported filter keys {sorted(unknown)}; "
            "add them to briarwood.agent.index.FILTER_KEYS or fix the dictionary"
        )

    residual = re.sub(r"\s+", " ", remaining).strip()
    return TranslationResult(filters=filters, matched_phrases=matched, residual=residual)

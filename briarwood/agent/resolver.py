"""Property-id resolver.

Users type the same property many ways: "526 W End Ave", "526-w-end-ave",
"526-west-end-ave", "526 west end avenue avon by the sea". The saved-
properties directory uses one canonical slug per property. This module
bridges the two.

Resolution order:
1. Exact dir match.
2. Token-overlap score against every saved dir, expanding common street
   abbreviations both directions (w↔west, ave↔avenue, etc.).
3. Reject if top score is too weak or ambiguous without a clear leader.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from briarwood.agent.tools import SAVED_PROPERTIES_DIR

_DIRECTIONAL = {"w": "west", "e": "east", "n": "north", "s": "south"}
_STREET_TYPE = {
    "ave": "avenue", "st": "street", "rd": "road", "dr": "drive",
    "ln": "lane", "blvd": "boulevard", "pkwy": "parkway", "ct": "court",
    "pl": "place", "ter": "terrace", "hwy": "highway", "cir": "circle",
}
_ABBREV = {**_DIRECTIONAL, **_STREET_TYPE}
_EXPAND: dict[str, str] = {}
for short, long_ in _ABBREV.items():
    _EXPAND[short] = long_
    _EXPAND[long_] = short

_STOP = {"the", "of", "at", "in", "on", "and", "a", "an"}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Digits followed (within a few tokens) by a street-type or directional word.
# Anchors "1223 Briarwood Road" / "526 W End Ave" while rejecting "at 3 bedrooms".
_STREET_WORDS_RE = (
    r"(?:ave|avenue|st|street|rd|road|dr|drive|ln|lane|blvd|boulevard|"
    r"pkwy|parkway|ct|court|pl|place|ter|terrace|hwy|highway|cir|circle|"
    r"way|w|e|n|s|west|east|north|south)"
)
_QUERY_STREET_NUM_RE = re.compile(
    rf"\b(\d+)(?:\s+\w+){{0,3}}?\s+{_STREET_WORDS_RE}\b",
    re.IGNORECASE,
)
_LEADING_DIGITS_RE = re.compile(r"^\s*(\d+)")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def _extract_street_number(text: str) -> str | None:
    """Return the first digit-run adjacent to a street word, or None.

    Distinguishes a real address reference ("1223 Briarwood Road") from
    incidental digits ("at 3 bedrooms", "4-bed homes"). Without this,
    the token-overlap score was happily matching "1223 Ocean Ave" to a
    saved "1232 Ocean Ave".
    """
    m = _QUERY_STREET_NUM_RE.search(text)
    return m.group(1) if m else None


def _candidate_street_number(slug: str) -> str | None:
    """Pull a saved property's street number from slug or inputs.json."""
    m = _LEADING_DIGITS_RE.match(slug)
    if m:
        return m.group(1)
    inputs_path = SAVED_PROPERTIES_DIR / slug / "inputs.json"
    if not inputs_path.exists():
        return None
    try:
        data = json.loads(inputs_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    address = data.get("facts", {}).get("address", "")
    addr_match = _LEADING_DIGITS_RE.match(address)
    return addr_match.group(1) if addr_match else None


def _known_ids() -> list[str]:
    if not SAVED_PROPERTIES_DIR.exists():
        return []
    return sorted(p.name for p in SAVED_PROPERTIES_DIR.iterdir() if p.is_dir())


def _score(query: list[str], candidate: str) -> int:
    cand_tokens = set(_tokens(candidate))
    if not cand_tokens:
        return 0
    score = 0
    for t in query:
        if t in cand_tokens:
            score += 2
        elif _EXPAND.get(t) in cand_tokens:
            score += 2  # abbreviation match counts the same
    return score


def resolve_property_id(text: str) -> tuple[str | None, list[str]]:
    """Resolve free-form user text to a saved-property dir name.

    Returns ``(best_match, ranked_candidates)``. ``best_match`` is None
    when nothing scores above the minimum threshold OR when the top two
    candidates tie on score (ambiguous). ``ranked_candidates`` is always
    returned so callers can surface disambiguation choices.
    """
    known = _known_ids()
    if not known:
        return None, []

    stripped = text.strip().lower()
    if stripped in known:
        return stripped, [stripped]

    query = _tokens(text)
    if not query:
        return None, []

    scored = [(c, _score(query, c)) for c in known]
    scored = [(c, s) for c, s in scored if s >= 4]  # at least 2 solid token hits

    # Street-number guardrail: when the user names a specific address
    # ("1223 Briarwood Road"), reject candidates whose number doesn't match.
    # Token overlap alone will happily fuse 1223 onto a saved 1232.
    query_num = _extract_street_number(text)
    if query_num is not None:
        scored = [(c, s) for c, s in scored if _candidate_street_number(c) == query_num]

    scored.sort(key=lambda x: (-x[1], x[0]))

    if not scored:
        return None, []

    top_score = scored[0][1]
    top = [c for c, s in scored if s == top_score]
    ranked = [c for c, _ in scored]

    # Tie at the top: prefer the candidate with the most of its OWN
    # tokens covered by the query. This rewards specificity when the
    # query mentions town/state, without penalising noisy queries that
    # drag in filler words.
    if len(top) == 1:
        return top[0], ranked
    query_set = set(query) | {_EXPAND[t] for t in query if t in _EXPAND}
    def _coverage(candidate: str) -> int:
        cand_tokens = set(_tokens(candidate))
        return sum(1 for t in cand_tokens if t in query_set or _EXPAND.get(t) in query_set)
    best = max(top, key=lambda c: (_coverage(c), -len(c), c))
    return best, ranked

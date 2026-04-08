"""
Free geocoding using OpenStreetMap Nominatim.

No API key required. Rate limited to 1 request/second per Nominatim ToS.
Results are cached in-memory to avoid repeat requests within a session.
"""
from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache

from briarwood.schemas import PropertyInput

logger = logging.getLogger(__name__)

_LAST_REQUEST_TIME: float = 0.0
_MIN_INTERVAL: float = 1.1  # seconds between requests (Nominatim requires ≥1s)
_USER_AGENT = "BriarwoodRealEstate/1.0 (investment research tool)"
_TIMEOUT = 5
# S7 (audit 2026-04-08): guards _LAST_REQUEST_TIME read/sleep/write against
# concurrent Dash callback threads so we cannot exceed Nominatim's 1 req/sec ToS.
_RATE_LIMIT_LOCK = threading.Lock()


@lru_cache(maxsize=500)
def geocode_address(address: str) -> tuple[float, float] | None:
    """
    Geocode an address string to (lat, lon) via Nominatim.

    Returns None if the address cannot be resolved or the service is unavailable.
    Results are cached for the lifetime of the process.
    """
    global _LAST_REQUEST_TIME

    try:
        import requests  # noqa: delayed import — only needed if geocoding
    except ImportError:
        return None

    # Rate limiting — serialize the read/sleep/write under a lock so concurrent
    # threads cannot race past the interval check.
    with _RATE_LIMIT_LOCK:
        elapsed = time.time() - _LAST_REQUEST_TIME
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)

        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            _LAST_REQUEST_TIME = time.time()
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    return float(results[0]["lat"]), float(results[0]["lon"])
        except (requests.RequestException, ValueError, KeyError) as exc:
            # C2 (audit 2026-04-08): was bare `except Exception: pass` — now
            # narrow to network/parse errors and log so repeated failures are
            # debuggable (timeouts vs. rate-limited vs. malformed JSON).
            logger.warning("Geocoding failed for %r: %s", address, exc)

    return None


def apply_geocoding(property_input: PropertyInput) -> bool:
    """
    Populate lat/lon on PropertyInput if not already present.

    Returns True if geocoding was applied, False otherwise.
    """
    if property_input.latitude is not None and property_input.longitude is not None:
        return False

    parts = [property_input.address, property_input.town, property_input.state]
    full_address = ", ".join(p for p in parts if p)
    if not full_address:
        return False

    coords = geocode_address(full_address)
    if coords is not None:
        property_input.latitude = coords[0]
        property_input.longitude = coords[1]
        return True

    return False

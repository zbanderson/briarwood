"""
Free geocoding using OpenStreetMap Nominatim.

No API key required. Rate limited to 1 request/second per Nominatim ToS.
Results are cached in-memory to avoid repeat requests within a session.
"""
from __future__ import annotations

import time
from functools import lru_cache

from briarwood.schemas import PropertyInput


_LAST_REQUEST_TIME: float = 0.0
_MIN_INTERVAL: float = 1.1  # seconds between requests (Nominatim requires ≥1s)
_USER_AGENT = "BriarwoodRealEstate/1.0 (investment research tool)"
_TIMEOUT = 5


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

    # Rate limiting
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
    except Exception:
        pass

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

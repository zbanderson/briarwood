"""Hand-curated town anchor points for listing-index distance features.

Small by design — only the towns we actually have in saved_properties/.
Expanding requires adding an entry here, not code changes elsewhere. When
we later hook a real gazetteer or municipal-GIS feed this file becomes the
seed + override layer.

Coordinates are (lat, lon). Beach points sit on the oceanfront at the
same block-latitude as the town center.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TownAnchors:
    beach: tuple[float, float] | None = None
    downtown: tuple[float, float] | None = None
    train: tuple[float, float] | None = None


_ANCHORS: dict[tuple[str, str], TownAnchors] = {
    ("avon by the sea", "nj"): TownAnchors(
        beach=(40.1918, -74.0138),        # Ocean Ave & Washington Ave boardwalk
        downtown=(40.1918, -74.0190),      # Main St corridor
        train=(40.2096, -74.0282),         # NJ Transit Bradley Beach station (nearest)
    ),
    ("belmar", "nj"): TownAnchors(
        beach=(40.1790, -74.0130),         # Ocean Ave & 8th Ave
        downtown=(40.1786, -74.0228),      # Main St & 9th Ave
        train=(40.1813, -74.0296),         # NJ Transit Belmar station
    ),
    ("bradley beach", "nj"): TownAnchors(
        beach=(40.2020, -74.0106),
        downtown=(40.2020, -74.0183),
        train=(40.2024, -74.0286),
    ),
}


def anchors_for(town: str | None, state: str | None) -> TownAnchors | None:
    if not town or not state:
        return None
    key = (town.strip().lower(), state.strip().lower())
    return _ANCHORS.get(key)

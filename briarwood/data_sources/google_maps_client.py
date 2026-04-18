from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
STREET_VIEW_URL = "https://maps.googleapis.com/maps/api/streetview"


@dataclass(slots=True)
class GoogleMapsResponse:
    endpoint: str
    cache_key: str
    raw_payload: dict[str, Any] | None
    normalized_payload: dict[str, Any]
    from_cache: bool
    fetched_at: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class GoogleMapsClient:
    """Small Google Maps Platform client for geo and place enrichment."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        cache_dir: str | Path | None = None,
        timeout_seconds: float = 12.0,
        transport: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GOOGLE_MAPS_API_KEY", "")
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[2] / "data" / "cache" / "google_maps")
        self.timeout_seconds = timeout_seconds
        self.transport = transport or _urllib_transport

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def geocode(self, address: str) -> GoogleMapsResponse:
        normalized_address = (address or "").strip()
        cache_key = _cache_key("geocode", {"address": normalized_address})
        cached = self._read_cache(cache_key)
        if cached is not None:
            return _cached_response("geocode", cache_key, cached)
        if not self.api_key:
            return GoogleMapsResponse("geocode", cache_key, None, {}, False, error="GOOGLE_MAPS_API_KEY is not configured.")
        if not normalized_address:
            return GoogleMapsResponse("geocode", cache_key, None, {}, False, error="No address was provided for geocoding.")

        raw_payload = self.transport(
            GEOCODE_URL,
            method="GET",
            params={"address": normalized_address, "key": self.api_key},
            headers={},
            timeout_seconds=self.timeout_seconds,
        )
        normalized = _normalize_geocode(raw_payload)
        fetched_at = _timestamp()
        self._write_cache(cache_key, raw_payload=raw_payload, normalized_payload=normalized, fetched_at=fetched_at)
        return GoogleMapsResponse("geocode", cache_key, raw_payload, normalized, False, fetched_at, None)

    def nearby_places(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_meters: float = 1600.0,
        included_types: list[str] | None = None,
        max_results: int = 8,
    ) -> GoogleMapsResponse:
        payload = {
            "includedTypes": included_types or ["school", "grocery_store", "park", "transit_station"],
            "maxResultCount": max_results,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters,
                }
            },
        }
        cache_key = _cache_key("nearby_places", payload)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return _cached_response("nearby_places", cache_key, cached)
        if not self.api_key:
            return GoogleMapsResponse("nearby_places", cache_key, None, {}, False, error="GOOGLE_MAPS_API_KEY is not configured.")

        raw_payload = self.transport(
            PLACES_NEARBY_URL,
            method="POST",
            params=None,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": ",".join(
                    [
                        "places.id",
                        "places.displayName",
                        "places.formattedAddress",
                        "places.primaryType",
                        "places.location",
                        "places.rating",
                        "places.userRatingCount",
                        "places.googleMapsUri",
                    ]
                ),
            },
            timeout_seconds=self.timeout_seconds,
            body=payload,
        )
        normalized = _normalize_nearby_places(raw_payload, latitude=latitude, longitude=longitude)
        fetched_at = _timestamp()
        self._write_cache(cache_key, raw_payload=raw_payload, normalized_payload=normalized, fetched_at=fetched_at)
        return GoogleMapsResponse("nearby_places", cache_key, raw_payload, normalized, False, fetched_at, None)

    def street_view_image_url(
        self,
        *,
        latitude: float,
        longitude: float,
        size: str = "640x360",
        fov: int = 90,
        pitch: int = 0,
    ) -> str | None:
        if not self.api_key:
            return None
        params = {
            "size": size,
            "location": f"{latitude},{longitude}",
            "fov": str(fov),
            "pitch": str(pitch),
            "key": self.api_key,
        }
        return f"{STREET_VIEW_URL}?{urlencode(params)}"

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _write_cache(
        self,
        cache_key: str,
        *,
        raw_payload: dict[str, Any] | None,
        normalized_payload: dict[str, Any],
        fetched_at: str,
    ) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{cache_key}.json"
        path.write_text(
            json.dumps(
                {
                    "raw_payload": raw_payload,
                    "normalized_payload": normalized_payload,
                    "fetched_at": fetched_at,
                },
                indent=2,
            )
            + "\n"
        )


def _cached_response(endpoint: str, cache_key: str, cached: dict[str, Any]) -> GoogleMapsResponse:
    return GoogleMapsResponse(
        endpoint=endpoint,
        cache_key=cache_key,
        raw_payload=cached.get("raw_payload"),
        normalized_payload=cached.get("normalized_payload", {}),
        from_cache=True,
        fetched_at=cached.get("fetched_at"),
        error=cached.get("error"),
    )


def _normalize_geocode(raw_payload: dict[str, Any]) -> dict[str, Any]:
    results = raw_payload.get("results") if isinstance(raw_payload, dict) else []
    first = results[0] if results else {}
    geometry = first.get("geometry", {}) if isinstance(first, dict) else {}
    location = geometry.get("location", {}) if isinstance(geometry, dict) else {}
    components = first.get("address_components", []) if isinstance(first, dict) else []
    locality = _component_value(components, "locality")
    state = _component_value(components, "administrative_area_level_1", short_name=True)
    postal_code = _component_value(components, "postal_code")
    county = _component_value(components, "administrative_area_level_2")
    return {
        "formatted_address": first.get("formatted_address"),
        "latitude": location.get("lat"),
        "longitude": location.get("lng"),
        "place_id": first.get("place_id"),
        "types": list(first.get("types") or []),
        "town": locality,
        "state": state,
        "county": county.replace(" County", "") if isinstance(county, str) else county,
        "zip_code": postal_code,
    }


def _normalize_nearby_places(raw_payload: dict[str, Any], *, latitude: float, longitude: float) -> dict[str, Any]:
    places = raw_payload.get("places") if isinstance(raw_payload, dict) else []
    normalized_places: list[dict[str, Any]] = []
    nearest_by_type: dict[str, dict[str, Any]] = {}
    type_counts: dict[str, int] = {}
    for row in places or []:
        location = row.get("location", {}) if isinstance(row, dict) else {}
        primary_type = row.get("primaryType")
        place_lat = location.get("latitude")
        place_lng = location.get("longitude")
        distance_m = None
        if isinstance(place_lat, (int, float)) and isinstance(place_lng, (int, float)):
            distance_m = round(_haversine_miles(latitude, longitude, float(place_lat), float(place_lng)) * 1609.34)
        normalized = {
            "place_id": row.get("id"),
            "name": (row.get("displayName") or {}).get("text"),
            "address": row.get("formattedAddress"),
            "primary_type": primary_type,
            "latitude": place_lat,
            "longitude": place_lng,
            "distance_meters": distance_m,
            "rating": row.get("rating"),
            "user_rating_count": row.get("userRatingCount"),
            "google_maps_uri": row.get("googleMapsUri"),
        }
        normalized_places.append(normalized)
        if isinstance(primary_type, str) and primary_type:
            type_counts[primary_type] = type_counts.get(primary_type, 0) + 1
            current = nearest_by_type.get(primary_type)
            if current is None or (
                isinstance(distance_m, int)
                and (
                    current.get("distance_meters") is None
                    or distance_m < current.get("distance_meters")
                )
            ):
                nearest_by_type[primary_type] = normalized
    return {
        "places": normalized_places,
        "type_counts": type_counts,
        "nearest_by_type": nearest_by_type,
    }


def _component_value(components: list[dict[str, Any]], component_type: str, *, short_name: bool = False) -> str | None:
    key = "short_name" if short_name else "long_name"
    for component in components:
        if component_type in (component.get("types") or []):
            value = component.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _cache_key(endpoint: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    import hashlib
    return hashlib.sha1(f"{endpoint}:{serialized}".encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_miles * c


def _urllib_transport(
    url: str,
    *,
    method: str,
    params: dict[str, str] | None,
    headers: dict[str, str],
    timeout_seconds: float,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    full_url = url
    if method.upper() == "GET" and params:
        full_url = f"{url}?{urlencode(params)}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = Request(full_url, headers=headers, data=data, method=method.upper())
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


__all__ = ["GoogleMapsClient", "GoogleMapsResponse"]

from __future__ import annotations

import calendar
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from briarwood.listing_intake.schemas import ListingRawData, PriceHistoryEntry, TaxHistoryEntry


BASE_URL = "https://www.searchapi.io/api/v1/search"
API_KEY_ENV_CANDIDATES = (
    "SEARCHAPI_API_KEY",
    "SEARCH_API_KEY",
    "SEARCHAPI_KEY",
    "SERPER_API_KEY",
    "serper_api_key",
)


@dataclass(slots=True)
class SearchApiZillowResponse:
    cache_key: str
    raw_payload: dict[str, Any] | None
    normalized_payload: dict[str, Any]
    from_cache: bool
    fetched_at: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(slots=True)
class SearchApiZillowListingCandidate:
    zpid: str | None
    address: str | None
    town: str | None
    state: str | None
    zip_code: str | None
    price: float | None
    beds: int | None
    baths: float | None
    sqft: int | None
    property_type: str | None
    listing_status: str | None
    listing_url: str | None
    rent_zestimate: float | None = None
    # CMA Phase 4a Cycle 3a — Zillow-rich fields the probe found we throw
    # away today. All optional with None defaults; backwards-compatible.
    # Bridge to ComparableProperty happens in CMA Cycle 3c (e.g., date_sold
    # → ComparableProperty.sale_date, home_type → property_type override).
    lot_sqft: float | None = None  # actual square feet, post unit conversion
    date_sold: str | None = None  # ISO datetime string (e.g., "2026-04-20T07:00:00Z")
    days_on_market: int | None = None  # mapped from raw days_on_zillow
    latitude: float | None = None
    longitude: float | None = None
    tax_assessed_value: float | None = None
    zestimate: float | None = None  # Zillow's AVM number
    home_type: str | None = None  # Zillow literal (e.g., "SINGLE_FAMILY", "MULTI_FAMILY")
    listing_type: str | None = None  # e.g., "Owner Occupied", "Non Owner Occupied"
    broker: str | None = None


class SearchApiZillowClient:
    """Small client for SearchAPI's Zillow search endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        cache_dir: str | Path | None = None,
        timeout_seconds: float = 12.0,
        retries: int = 1,
        sleep_seconds: float = 0.35,
        transport: Callable[[str, dict[str, str], dict[str, str], float], dict[str, Any]] | None = None,
        discovery_cache_ttl_seconds: int | None = 24 * 3600,
    ) -> None:
        self.api_key = api_key if api_key is not None else _resolve_api_key()
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[2] / "data" / "cache" / "searchapi_zillow")
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.sleep_seconds = sleep_seconds
        self.transport = transport or _urllib_transport
        self.discovery_cache_ttl_seconds = discovery_cache_ttl_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def lookup_listing(self, *, source_url: str, address_hint: str | None = None) -> SearchApiZillowResponse:
        """Search Zillow results for a listing that best matches the given URL/address.

        SearchAPI's `engine=zillow` is a *location* search — Zillow's location
        resolver rejects full street addresses ("Could not find location ..."),
        so we query the City/State/ZIP derived from the URL and rely on
        `_select_best_result` to pick the right candidate by zpid.
        """
        full_address = (address_hint or _address_hint_from_url(source_url) or "").strip()
        query = _location_query_from_address(full_address) or full_address
        cache_key = _cache_key(source_url=source_url, query=query)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return SearchApiZillowResponse(
                cache_key=cache_key,
                raw_payload=cached.get("raw_payload"),
                normalized_payload=cached.get("normalized_payload", {}),
                from_cache=True,
                fetched_at=cached.get("fetched_at"),
                error=cached.get("error"),
            )

        if not self.api_key:
            return SearchApiZillowResponse(
                cache_key=cache_key,
                raw_payload=None,
                normalized_payload={},
                from_cache=False,
                error="SearchAPI Zillow key is not configured.",
            )
        if not query:
            return SearchApiZillowResponse(
                cache_key=cache_key,
                raw_payload=None,
                normalized_payload={},
                from_cache=False,
                error="No address hint was available for Zillow URL hydration.",
            )

        params = {"engine": "zillow", "q": query, "api_key": self.api_key}
        last_error: str | None = None
        for attempt in range(self.retries + 1):
            try:
                raw_payload = self.transport(BASE_URL, params, {}, self.timeout_seconds)
                best = _select_best_result(raw_payload, source_url=source_url, address_hint=full_address)
                normalized = _normalize_listing(best, source_url=source_url, address_hint=full_address)
                fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self._write_cache(
                    cache_key,
                    raw_payload=raw_payload,
                    normalized_payload=normalized,
                    fetched_at=fetched_at,
                )
                return SearchApiZillowResponse(
                    cache_key=cache_key,
                    raw_payload=raw_payload,
                    normalized_payload=normalized,
                    from_cache=False,
                    fetched_at=fetched_at,
                    error=None,
                )
            except Exception as exc:  # pragma: no cover - defensive wrapper
                last_error = str(exc)
                if attempt < self.retries:
                    time.sleep(self.sleep_seconds * (attempt + 1))

        self._write_cache(
            cache_key,
            raw_payload={},
            normalized_payload={},
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            error=last_error,
        )
        return SearchApiZillowResponse(
            cache_key=cache_key,
            raw_payload=None,
            normalized_payload={},
            from_cache=False,
            error=last_error or "Unknown SearchAPI Zillow error",
        )

    def search_listings(
        self,
        *,
        query: str,
        page: int = 1,
        max_results: int = 8,
        listing_status: str | None = None,
        rent_min: int | None = None,
        rent_max: int | None = None,
        beds_min: int | None = None,
        home_type: str | None = None,
    ) -> SearchApiZillowResponse:
        """Run a Zillow discovery query and return normalized candidate rows."""
        normalized_query = (query or "").strip()
        cache_key = _cache_key(
            source_url=f"search::{page}::{listing_status or 'default'}::{rent_min or ''}::{rent_max or ''}::{beds_min or ''}::{home_type or ''}",
            query=normalized_query,
        )
        cached = self._read_cache(cache_key, max_age_seconds=self.discovery_cache_ttl_seconds)
        if cached is not None:
            return SearchApiZillowResponse(
                cache_key=cache_key,
                raw_payload=cached.get("raw_payload"),
                normalized_payload=cached.get("normalized_payload", {}),
                from_cache=True,
                fetched_at=cached.get("fetched_at"),
                error=cached.get("error"),
            )
        if not self.api_key:
            return SearchApiZillowResponse(cache_key, None, {}, False, error="SearchAPI Zillow key is not configured.")
        if not normalized_query:
            return SearchApiZillowResponse(cache_key, None, {}, False, error="No Zillow search query was provided.")

        params = {"engine": "zillow", "q": normalized_query, "page": str(page), "api_key": self.api_key}
        if listing_status:
            params["listing_status"] = listing_status
        if rent_min is not None:
            params["rent_min"] = str(rent_min)
        if rent_max is not None:
            params["rent_max"] = str(rent_max)
        if beds_min is not None:
            params["beds_min"] = str(beds_min)
        if home_type:
            params["home_type"] = home_type
        last_error: str | None = None
        for attempt in range(self.retries + 1):
            try:
                raw_payload = self.transport(BASE_URL, params, {}, self.timeout_seconds)
                candidates = [
                    _normalize_listing(row, source_url="", address_hint=normalized_query)
                    for row in _extract_result_candidates(raw_payload)[:max_results]
                ]
                normalized = {"query": normalized_query, "page": page, "results": candidates}
                fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self._write_cache(
                    cache_key,
                    raw_payload=raw_payload,
                    normalized_payload=normalized,
                    fetched_at=fetched_at,
                )
                return SearchApiZillowResponse(cache_key, raw_payload, normalized, False, fetched_at, None)
            except Exception as exc:  # pragma: no cover - defensive wrapper
                last_error = str(exc)
                if attempt < self.retries:
                    time.sleep(self.sleep_seconds * (attempt + 1))
        return SearchApiZillowResponse(
            cache_key=cache_key,
            raw_payload=None,
            normalized_payload={},
            from_cache=False,
            error=last_error or "Unknown SearchAPI Zillow error",
        )

    def to_listing_raw_data(
        self,
        normalized_payload: dict[str, Any],
        *,
        source_url: str,
        fallback_address: str | None = None,
    ) -> ListingRawData:
        address = normalized_payload.get("address") or fallback_address
        return ListingRawData(
            source="zillow",
            intake_mode="url_intake",
            source_url=source_url,
            address=address,
            price=_to_float(normalized_payload.get("price")),
            beds=_to_int(normalized_payload.get("beds")),
            baths=_to_float(normalized_payload.get("baths")),
            sqft=_to_int(normalized_payload.get("sqft")),
            lot_sqft=_to_int(normalized_payload.get("lot_sqft")),
            property_type=_clean_text(normalized_payload.get("property_type")),
            architectural_style=_clean_text(normalized_payload.get("architectural_style")),
            condition_profile=_clean_text(normalized_payload.get("condition_profile")),
            capex_lane=_clean_text(normalized_payload.get("capex_lane")),
            year_built=_to_int(normalized_payload.get("year_built")),
            stories=_to_float(normalized_payload.get("stories")),
            garage_spaces=_to_int(normalized_payload.get("garage_spaces")),
            days_on_market=_to_int(normalized_payload.get("days_on_market")),
            hoa_monthly=_to_float(normalized_payload.get("hoa_monthly")),
            taxes_annual=_to_float(normalized_payload.get("taxes_annual")),
            listing_description=_clean_text(normalized_payload.get("listing_description")),
            tax_history=_normalize_tax_history(normalized_payload.get("tax_history")),
            price_history=_normalize_price_history(normalized_payload.get("price_history")),
            raw_text=json.dumps(normalized_payload, sort_keys=True),
        )

    def to_listing_candidates(self, normalized_payload: dict[str, Any]) -> list[SearchApiZillowListingCandidate]:
        rows = normalized_payload.get("results")
        if not isinstance(rows, list):
            return []
        candidates: list[SearchApiZillowListingCandidate] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            address = _clean_text(row.get("address"))
            town, state, zip_code = _parse_address_parts(address)
            candidates.append(
                SearchApiZillowListingCandidate(
                    zpid=_clean_text(row.get("zpid")),
                    address=address,
                    town=town,
                    state=state,
                    zip_code=zip_code,
                    price=_to_float(row.get("price")),
                    beds=_to_int(row.get("beds")),
                    baths=_to_float(row.get("baths")),
                    sqft=_to_int(row.get("sqft")),
                    property_type=_clean_text(row.get("property_type")),
                    listing_status=_clean_text(row.get("listing_status")),
                    listing_url=_clean_text(row.get("listing_url")),
                    rent_zestimate=_to_float(row.get("rent_zestimate")),
                    # CMA Phase 4a Cycle 3a — Zillow-rich fields. Already
                    # extracted by _normalize_listing into the row dict;
                    # pass through here. None-defaults keep older cached
                    # payloads compatible.
                    lot_sqft=_to_float(row.get("lot_sqft")),
                    date_sold=_clean_text(row.get("date_sold")),
                    days_on_market=_to_int(row.get("days_on_market")),
                    latitude=_to_float(row.get("latitude")),
                    longitude=_to_float(row.get("longitude")),
                    tax_assessed_value=_to_float(row.get("tax_assessed_value")),
                    zestimate=_to_float(row.get("zestimate")),
                    home_type=_clean_text(row.get("home_type")),
                    listing_type=_clean_text(row.get("listing_type")),
                    broker=_clean_text(row.get("broker")),
                )
            )
        return candidates

    def _read_cache(self, cache_key: str, *, max_age_seconds: int | None = None) -> dict[str, Any] | None:
        path = self.cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if max_age_seconds is None:
            return payload
        fetched_at = payload.get("fetched_at")
        if not isinstance(fetched_at, str):
            return None
        try:
            cached_ts = calendar.timegm(time.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            return None
        if (time.time() - cached_ts) > max_age_seconds:
            return None
        return payload

    def _write_cache(
        self,
        cache_key: str,
        *,
        raw_payload: dict[str, Any],
        normalized_payload: dict[str, Any],
        fetched_at: str,
        error: str | None = None,
    ) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{cache_key}.json"
        path.write_text(
            json.dumps(
                {
                    "raw_payload": raw_payload,
                    "normalized_payload": normalized_payload,
                    "fetched_at": fetched_at,
                    "error": error,
                },
                indent=2,
                sort_keys=True,
            )
        )


def _resolve_api_key() -> str:
    for name in API_KEY_ENV_CANDIDATES:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _cache_key(*, source_url: str, query: str) -> str:
    digest = hashlib.sha1(f"{source_url}|{query}".encode("utf-8")).hexdigest()
    return f"searchapi_zillow_{digest}"


def _address_hint_from_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if not parts:
        return None
    slug = parts[1] if parts[0].lower() == "homedetails" and len(parts) > 1 else parts[0]
    cleaned = slug.replace("-", " ")
    cleaned = re.sub(r"\b\d+_zpid\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else None


def _select_best_result(raw_payload: dict[str, Any], *, source_url: str, address_hint: str) -> dict[str, Any]:
    candidates = _extract_result_candidates(raw_payload)
    if not candidates:
        raise ValueError("SearchAPI Zillow returned no listing candidates.")
    zpid_hint = _zpid_from_url(source_url)
    ranked = sorted(
        candidates,
        key=lambda item: _candidate_score(item, zpid_hint=zpid_hint, address_hint=address_hint),
        reverse=True,
    )
    return ranked[0]


def _extract_result_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in ("organic_results", "results", "search_results", "properties", "listings"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get("property"), dict):
        return [payload["property"]]
    return []


def _candidate_score(candidate: dict[str, Any], *, zpid_hint: str | None, address_hint: str) -> tuple[int, int]:
    score = 0
    candidate_zpid = _clean_text(
        candidate.get("zpid")
        or candidate.get("property_id")
        or candidate.get("listing_id")
    )
    if zpid_hint and candidate_zpid and candidate_zpid == zpid_hint:
        score += 100

    candidate_address = _normalize_address_string(_compose_address(candidate))
    hint = _normalize_address_string(address_hint)
    if candidate_address and hint:
        if candidate_address == hint:
            score += 40
        hint_tokens = set(hint.split())
        address_tokens = set(candidate_address.split())
        score += len(hint_tokens & address_tokens) * 4
    return score, len(candidate_address.split()) if candidate_address else 0


def _normalize_listing(candidate: dict[str, Any], *, source_url: str, address_hint: str) -> dict[str, Any]:
    details = candidate.get("details")
    detail_dict = details if isinstance(details, dict) else {}
    address = _compose_address(candidate) or _compose_address(detail_dict) or address_hint
    listing_url = _clean_text(
        candidate.get("link")
        or candidate.get("listing_url")
        or candidate.get("url")
        or candidate.get("property_url")
        or source_url
    )
    return {
        "address": address,
        "listing_url": listing_url,
        "zpid": _clean_text(candidate.get("zpid") or candidate.get("property_id") or candidate.get("listing_id")),
        "price": _to_float(
            candidate.get("extracted_price")
            or candidate.get("unformatted_price")
            or candidate.get("price")
            or detail_dict.get("price")
        ),
        "beds": _to_int(candidate.get("beds") or candidate.get("bedrooms") or detail_dict.get("beds")),
        "baths": _to_float(candidate.get("baths") or candidate.get("bathrooms") or detail_dict.get("baths")),
        "sqft": _to_int(
            candidate.get("living_area")
            or candidate.get("sqft")
            or candidate.get("living_area_sqft")
            or detail_dict.get("sqft")
        ),
        "lot_sqft": _normalize_lot_size(candidate, detail_dict),
        "property_type": _clean_text(candidate.get("home_type") or candidate.get("property_type") or detail_dict.get("home_type")),
        "year_built": _to_int(candidate.get("year_built") or detail_dict.get("year_built")),
        "days_on_market": _to_int(candidate.get("days_on_zillow") or candidate.get("days_on_market") or detail_dict.get("days_on_market")),
        "hoa_monthly": _to_float(candidate.get("hoa_fee") or candidate.get("hoa_monthly") or detail_dict.get("hoa_monthly")),
        "taxes_annual": _to_float(candidate.get("property_tax") or candidate.get("taxes_annual") or detail_dict.get("taxes_annual")),
        "listing_description": _clean_text(candidate.get("description") or detail_dict.get("description")),
        "listing_status": _clean_text(candidate.get("listing_status") or candidate.get("status")),
        "rent_zestimate": _to_float(candidate.get("rent_zestimate") or detail_dict.get("rent_zestimate")),
        "price_history": candidate.get("price_history") or detail_dict.get("price_history") or [],
        "tax_history": candidate.get("tax_history") or detail_dict.get("tax_history") or [],
        # CMA Phase 4a Cycle 3a — Zillow-rich fields. All optional in the
        # raw payload; missing values normalize to None.
        "date_sold": _clean_text(candidate.get("date_sold") or detail_dict.get("date_sold")),
        "latitude": _to_float(candidate.get("latitude") or detail_dict.get("latitude")),
        "longitude": _to_float(candidate.get("longitude") or detail_dict.get("longitude")),
        "tax_assessed_value": _to_float(candidate.get("tax_assessed_value") or detail_dict.get("tax_assessed_value")),
        "zestimate": _to_float(candidate.get("zestimate") or detail_dict.get("zestimate")),
        "home_type": _clean_text(candidate.get("home_type") or detail_dict.get("home_type")),
        "listing_type": _clean_text(candidate.get("listing_type") or detail_dict.get("listing_type")),
        "broker": _clean_text(candidate.get("broker") or detail_dict.get("broker")),
    }


def _normalize_lot_size(
    candidate: dict[str, Any],
    detail_dict: dict[str, Any],
) -> float | None:
    """Resolve lot size to actual square feet, handling the Zillow-acres quirk.

    SearchApi's Zillow rows label lot size as ``lot_sqft`` but populate it in
    ``lot_area_unit`` units (often acres). A 0.33-acre lot returns
    ``lot_sqft: 0.33``; we want 14,375 sqft. Heuristics applied in priority
    order:

    1. Prefer explicit ``lot_size`` (legacy SearchApi field — usually sqft).
    2. If ``lot_area_unit == "acres"``, convert ``lot_sqft`` (which is acres)
       via ``× 43560``.
    3. If raw value looks like a small number (< 100), assume acres.
    4. Otherwise treat as sqft.

    Returns None when no usable input is present.
    """
    legacy_lot = _to_float(candidate.get("lot_size") or detail_dict.get("lot_size"))
    if legacy_lot is not None:
        return legacy_lot
    raw_value = _to_float(candidate.get("lot_sqft") or detail_dict.get("lot_sqft"))
    if raw_value is None:
        return None
    unit = (
        candidate.get("lot_area_unit")
        or detail_dict.get("lot_area_unit")
        or ""
    )
    unit_str = str(unit).strip().lower() if unit else ""
    if unit_str == "acres" or (unit_str == "" and raw_value < 100):
        return raw_value * 43_560.0
    return raw_value


def _compose_address(candidate: dict[str, Any]) -> str | None:
    address = _clean_text(candidate.get("address") or candidate.get("full_address"))
    if address:
        return address

    street = _clean_text(candidate.get("street_address") or candidate.get("street"))
    city = _clean_text(candidate.get("city"))
    state = _clean_text(candidate.get("state"))
    zip_code = _clean_text(candidate.get("zip") or candidate.get("zipcode") or candidate.get("postal_code"))
    if street and city and state:
        suffix = f" {zip_code}" if zip_code else ""
        return f"{street}, {city}, {state}{suffix}"
    return None


def _normalize_price_history(entries: Any) -> list[PriceHistoryEntry]:
    if not isinstance(entries, list):
        return []
    history: list[PriceHistoryEntry] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        history.append(
            PriceHistoryEntry(
                date=_clean_text(entry.get("date") or entry.get("event_date")),
                event=_clean_text(entry.get("event") or entry.get("event_name")),
                price=_to_float(entry.get("price") or entry.get("value")),
            )
        )
    return history


def _normalize_tax_history(entries: Any) -> list[TaxHistoryEntry]:
    if not isinstance(entries, list):
        return []
    history: list[TaxHistoryEntry] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        history.append(
            TaxHistoryEntry(
                year=_to_int(entry.get("year")),
                tax_paid=_to_float(entry.get("tax_paid") or entry.get("tax") or entry.get("property_tax")),
                assessed_value=_to_float(entry.get("assessed_value") or entry.get("assessment")),
            )
        )
    return history


def _normalize_address_string(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _parse_address_parts(address: str | None) -> tuple[str | None, str | None, str | None]:
    if not address:
        return None, None, None
    match = re.search(r",\s*([^,]+),\s*([A-Z]{2})(?:\s+(\d{5}))?$", address)
    if not match:
        return None, None, None
    return match.group(1).strip(), match.group(2).strip(), match.group(3)


def _zpid_from_url(source_url: str) -> str | None:
    match = re.search(r"/(\d+)_zpid", source_url, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _location_query_from_address(address: str | None) -> str | None:
    """Extract a Zillow-friendly `City, ST` (with optional ZIP) from a slug-
    derived street address. Returns None if no 2-letter state token is found."""
    if not address:
        return None
    tokens = address.replace(",", " ").split()
    if not tokens:
        return None
    # Optional trailing 5-digit ZIP.
    zip_code: str | None = None
    if re.fullmatch(r"\d{5}", tokens[-1]):
        zip_code = tokens[-1]
        tokens = tokens[:-1]
    if not tokens:
        return None
    state_idx: int | None = None
    for i in range(len(tokens) - 1, -1, -1):
        if re.fullmatch(r"[A-Za-z]{2}", tokens[i]) and tokens[i].upper() == tokens[i].upper():
            state_idx = i
            break
    if state_idx is None or state_idx == 0:
        return None
    state = tokens[state_idx].upper()
    # City = tokens between street-end and state. Heuristic: walk back from
    # state until we hit a numeric or street-suffix token. Fall back to one token.
    street_suffixes = {
        "ave", "avenue", "st", "street", "rd", "road", "dr", "drive",
        "ln", "lane", "blvd", "boulevard", "ct", "court", "pl", "place",
        "way", "ter", "terrace", "cir", "circle", "pkwy", "parkway",
    }
    city_tokens: list[str] = []
    for token in reversed(tokens[:state_idx]):
        if token.lower() in street_suffixes or re.fullmatch(r"\d+\w*", token):
            break
        city_tokens.append(token)
    if not city_tokens:
        return None
    city = " ".join(reversed(city_tokens)).title()
    location = f"{city}, {state}"
    if zip_code:
        location = f"{location} {zip_code}"
    return location


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> int | None:
    numeric = _to_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _urllib_transport(url: str, params: dict[str, str], headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    query = urlencode(params)
    request = Request(f"{url}?{query}", headers={"Accept": "application/json", **headers})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:  # pragma: no cover - network dependent
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:  # pragma: no cover - network dependent
        raise RuntimeError(f"Network error: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:  # pragma: no cover - network dependent
        raise RuntimeError("SearchAPI Zillow returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("SearchAPI Zillow returned an unexpected payload shape.")
    return parsed

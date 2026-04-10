from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from briarwood.data_sources.api_strategy import ApiBudgetTracker


logger = logging.getLogger(__name__)

BASE_URL = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"
ENDPOINT_PATHS = {
    "property_detail": "/property/detail",
    "assessment_detail": "/assessment/detail",
    "assessment_history": "/assessmenthistory/detail",
    "sale_detail": "/sale/detail",
    "building_permits": "/buildingpermit/detail",
    "rental_avm": "/avm/rental/detail",
    "sales_trend": "/sale/trend",
    "community_demographics": "/community/detail",
}
ENDPOINT_TIERS = {
    "property_detail": "core",
    "assessment_detail": "core",
    "sale_detail": "core",
    "rental_avm": "conditional",
    "building_permits": "conditional",
    "assessment_history": "conditional",
    "sales_trend": "batch",
    "community_demographics": "batch",
}


@dataclass(slots=True)
class AttomResponse:
    endpoint: str
    cache_key: str
    raw_payload: dict[str, Any] | None
    normalized_payload: dict[str, Any]
    from_cache: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class AttomClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        cache_dir: str | Path | None = None,
        timeout_seconds: float = 15.0,
        retries: int = 2,
        sleep_seconds: float = 0.5,
        tracker: ApiBudgetTracker | None = None,
        transport: Callable[[str, dict[str, str], dict[str, str], float], dict[str, Any]] | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ATTOM_API_KEY", "")
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[2] / "data" / "cache" / "attom")
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.sleep_seconds = sleep_seconds
        self.tracker = tracker or ApiBudgetTracker()
        self.transport = transport or _urllib_transport

    def property_detail(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("property_detail", canonical_key, params=params)

    def assessment_detail(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("assessment_detail", canonical_key, params=params)

    def assessment_history(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("assessment_history", canonical_key, params=params)

    def sale_detail(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("sale_detail", canonical_key, params=params)

    def building_permits(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("building_permits", canonical_key, params=params)

    def rental_avm(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("rental_avm", canonical_key, params=params)

    def sales_trend(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("sales_trend", canonical_key, params=params)

    def community_demographics(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("community_demographics", canonical_key, params=params)

    def _fetch(self, endpoint: str, canonical_key: str, *, params: dict[str, str]) -> AttomResponse:
        cache_key = _cache_key(endpoint=endpoint, canonical_key=canonical_key, params=params)
        cached = self._read_cache(cache_key)
        if cached is not None:
            normalized = self._normalize(endpoint, cached)
            self._log(endpoint, cache_key, "cache_hit", error=None)
            return AttomResponse(endpoint, cache_key, cached, normalized, True, None)

        if not self.api_key:
            error = "ATTOM_API_KEY is not configured."
            self._log(endpoint, cache_key, "config_missing", error=error)
            return AttomResponse(endpoint, cache_key, None, {}, False, error)

        headers = {"apikey": self.api_key, "Accept": "application/json"}
        url = f"{BASE_URL}{ENDPOINT_PATHS[endpoint]}"
        last_error: str | None = None
        for attempt in range(self.retries + 1):
            try:
                raw_payload = self.transport(url, params, headers, self.timeout_seconds)
                self._write_cache(cache_key, raw_payload)
                normalized = self._normalize(endpoint, raw_payload)
                self._log(endpoint, cache_key, "success", error=None, attempt=attempt)
                return AttomResponse(endpoint, cache_key, raw_payload, normalized, False, None)
            except Exception as exc:  # never crash caller
                last_error = str(exc)
                self._log(endpoint, cache_key, "retryable_failure", error=last_error, attempt=attempt)
                if attempt < self.retries:
                    time.sleep(self.sleep_seconds * (attempt + 1))
        return AttomResponse(endpoint, cache_key, None, {}, False, last_error or "Unknown ATTOM error")

    def _normalize(self, endpoint: str, raw_payload: dict[str, Any]) -> dict[str, Any]:
        property_rows = raw_payload.get("property", []) if isinstance(raw_payload, dict) else []
        first_property = property_rows[0] if property_rows else {}
        if endpoint == "property_detail":
            return _normalize_property_detail(first_property)
        if endpoint == "assessment_detail":
            return _normalize_assessment_detail(first_property)
        if endpoint == "assessment_history":
            history = first_property.get("assessmenthistory", []) if isinstance(first_property, dict) else []
            return {"history": history}
        if endpoint == "sale_detail":
            return _normalize_sale_detail(first_property)
        if endpoint == "building_permits":
            permits = first_property.get("buildingpermit", []) if isinstance(first_property, dict) else []
            return {"permit_count": len(permits), "permits": permits}
        if endpoint == "rental_avm":
            return _normalize_rental_avm(first_property)
        if endpoint == "sales_trend":
            sale = raw_payload.get("salestrend", {}) if isinstance(raw_payload, dict) else {}
            return {
                "median_sale_price": sale.get("medsaleprice"),
                "avg_sale_price": sale.get("avgsaleprice"),
                "sale_count": sale.get("salescount"),
            }
        if endpoint == "community_demographics":
            community = raw_payload.get("community", {}) if isinstance(raw_payload, dict) else {}
            return {
                "housing_median_rent": community.get("housing", {}).get("medrent"),
                "occupied_pct": community.get("housing", {}).get("occupied"),
                "vacant_pct": community.get("housing", {}).get("vacant"),
                "vacant_for_sale_pct": community.get("housing", {}).get("vacantforsale"),
                "vacant_for_rent_pct": community.get("housing", {}).get("vacantforrent"),
            }
        return {}

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, cache_key: str, payload: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{cache_key}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _log(self, endpoint: str, cache_key: str, event: str, *, error: str | None, attempt: int = 0) -> None:
        logger.info(
            "ATTOM %s",
            json.dumps(
                {
                    "event": event,
                    "endpoint": endpoint,
                    "endpoint_tier": ENDPOINT_TIERS.get(endpoint, "unknown"),
                    "cache_key": cache_key,
                    "attempt": attempt,
                    "error": error,
                },
                sort_keys=True,
            ),
        )


def _urllib_transport(url: str, params: dict[str, str], headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    query = urlencode(params)
    request = Request(f"{url}?{query}", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while calling ATTOM") from exc
    except URLError as exc:
        raise RuntimeError(f"Network failure while calling ATTOM: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("ATTOM returned malformed JSON") from exc


def _normalize_property_detail(property_row: dict[str, Any]) -> dict[str, Any]:
    building = property_row.get("building", {})
    rooms = building.get("rooms", {})
    size = building.get("size", {})
    summary = property_row.get("summary", {})
    location = property_row.get("location", {})
    lot = property_row.get("lot", {})
    return {
        "address": property_row.get("address", {}).get("oneLine"),
        "beds": rooms.get("beds"),
        "baths": rooms.get("bathstotal") or rooms.get("bathsfull"),
        "sqft": size.get("universalsize") or size.get("livingsize"),
        "year_built": summary.get("yearbuilt"),
        "stories": building.get("summary", {}).get("levels"),
        "garage_spaces": building.get("parking", {}).get("prkgspaces"),
        "lot_size": lot.get("lotsize1"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "property_type": summary.get("proptype"),
    }


def _normalize_assessment_detail(property_row: dict[str, Any]) -> dict[str, Any]:
    assessment = property_row.get("assessment", {})
    return {
        "tax_amount": assessment.get("tax", {}).get("taxamt"),
        "tax_year": assessment.get("tax", {}).get("taxyear"),
        "assessed_land": assessment.get("assessed", {}).get("assdlandvalue"),
        "assessed_improvement": assessment.get("assessed", {}).get("assdimprvalue"),
        "assessed_total": assessment.get("assessed", {}).get("assdttlvalue"),
        "market_value": assessment.get("market", {}).get("mktttlvalue"),
    }


def _normalize_sale_detail(property_row: dict[str, Any]) -> dict[str, Any]:
    sale = property_row.get("sale", {})
    sale_rows = sale.get("saleshistory", []) if isinstance(sale, dict) else []
    latest = sale_rows[0] if sale_rows else {}
    return {
        "last_sale_date": latest.get("saledate"),
        "last_sale_price": latest.get("saleamt"),
        "seller_name": latest.get("seller"),
        "buyer_name": latest.get("buyer"),
    }


def _normalize_rental_avm(property_row: dict[str, Any]) -> dict[str, Any]:
    avm = property_row.get("avm", {})
    return {
        "estimated_monthly_rent": avm.get("rental", {}).get("predictedrent"),
        "rent_low": avm.get("rental", {}).get("predictedrentlow"),
        "rent_high": avm.get("rental", {}).get("predictedrenthigh"),
        "confidence_score": avm.get("rental", {}).get("confidence"),
    }


def _cache_key(*, endpoint: str, canonical_key: str, params: dict[str, str]) -> str:
    raw = json.dumps({"endpoint": endpoint, "canonical_key": canonical_key, "params": params}, sort_keys=True)
    return str(abs(hash(raw)))

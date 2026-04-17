from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import hashlib
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
    "property_detail_with_schools": "/property/detailwithschools",
    "property_expanded": "/property/expandedprofile",
    "assessment_detail": "/assessment/detail",
    "assessment_history": "/assessmenthistory/detail",
    "sale_detail": "/sale/detail",
    "sale_history_detail": "/saleshistory/detail",
    "sale_history_snapshot": "/saleshistory/snapshot",
    "building_permits": "/buildingpermit/detail",
    "rental_avm": "/avm/rental/detail",
    "avm_detail": "/avm/detail",
    "avm_history": "/avm/history/detail",
    "sales_trend": "/sale/trend",
    "community_demographics": "/community/detail",
    "school_snapshot": "/school/snapshot",
    "preforeclosure_snapshot": "/preforeclosure/snapshot",
    "preforeclosure_detail": "/preforeclosure/detail",
}
ENDPOINT_TIERS = {
    "property_detail": "core",
    "property_detail_with_schools": "core",
    "property_expanded": "conditional",
    "assessment_detail": "core",
    "sale_detail": "core",
    "sale_history_detail": "conditional",
    "sale_history_snapshot": "conditional",
    "rental_avm": "conditional",
    "avm_detail": "core",
    "avm_history": "conditional",
    "building_permits": "conditional",
    "assessment_history": "conditional",
    "sales_trend": "batch",
    "community_demographics": "batch",
    "school_snapshot": "batch",
    "preforeclosure_snapshot": "batch",
    "preforeclosure_detail": "conditional",
}
ENDPOINT_FIELD_MAP = {
    "property_detail": ("address", "beds", "baths", "sqft", "year_built", "stories", "garage_spaces", "lot_size", "latitude", "longitude", "property_type"),
    "property_detail_with_schools": ("address", "beds", "baths", "sqft", "year_built", "stories", "garage_spaces", "lot_size", "latitude", "longitude", "property_type", "schools"),
    "property_expanded": ("address", "beds", "baths", "sqft", "year_built", "stories", "garage_spaces", "lot_size", "latitude", "longitude", "property_type", "roof_type", "foundation", "heating", "cooling", "pool", "fireplace", "construction_type"),
    "assessment_detail": ("tax_amount", "tax_year", "assessed_land", "assessed_improvement", "assessed_total", "market_value"),
    "assessment_history": ("history",),
    "sale_detail": ("last_sale_date", "last_sale_price", "seller_name", "buyer_name"),
    "sale_history_detail": ("sale_count", "first_sale_date", "first_sale_price", "last_sale_date", "last_sale_price", "sale_history"),
    "sale_history_snapshot": ("sale_count", "first_sale_date", "first_sale_price", "last_sale_date", "last_sale_price", "sale_history", "history_confidence"),
    "rental_avm": ("estimated_monthly_rent", "rent_low", "rent_high", "confidence_score"),
    "avm_detail": ("avm_value", "avm_low", "avm_high", "avm_confidence", "avm_fsd"),
    "avm_history": ("avm_history",),
    "building_permits": ("permit_count", "permits"),
    "sales_trend": ("median_sale_price", "avg_sale_price", "sale_count", "sale_count_trend", "median_sale_price_trend"),
    "community_demographics": ("housing_median_rent", "occupied_pct", "vacant_pct", "vacant_for_sale_pct", "vacant_for_rent_pct", "population", "household_income"),
    "school_snapshot": ("schools",),
    "preforeclosure_snapshot": ("preforeclosures",),
    "preforeclosure_detail": ("filing_date", "default_amount", "lender", "auction_date", "foreclosure_type"),
}


@dataclass(slots=True)
class AttomResponse:
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

    def sale_history_detail(self, canonical_key: str, **params: str) -> AttomResponse:
        """Full transaction history for one property. Per ATTOM rep: use this
        for per-property trend/hold analysis instead of /sale/detail."""
        return self._fetch("sale_history_detail", canonical_key, params=params)

    def sale_history_snapshot(self, canonical_key: str, **params: str) -> AttomResponse:
        """Lighter-weight sales history lookup for snapshot comp history scans."""
        return self._fetch("sale_history_snapshot", canonical_key, params=params)

    def building_permits(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("building_permits", canonical_key, params=params)

    def rental_avm(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("rental_avm", canonical_key, params=params)

    def sales_trend(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("sales_trend", canonical_key, params=params)

    def community_demographics(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("community_demographics", canonical_key, params=params)

    def property_detail_with_schools(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("property_detail_with_schools", canonical_key, params=params)

    def property_expanded(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("property_expanded", canonical_key, params=params)

    def avm_detail(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("avm_detail", canonical_key, params=params)

    def avm_history(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("avm_history", canonical_key, params=params)

    def school_snapshot(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("school_snapshot", canonical_key, params=params)

    def preforeclosure_snapshot(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("preforeclosure_snapshot", canonical_key, params=params)

    def preforeclosure_detail(self, canonical_key: str, **params: str) -> AttomResponse:
        return self._fetch("preforeclosure_detail", canonical_key, params=params)

    def _fetch(self, endpoint: str, canonical_key: str, *, params: dict[str, str]) -> AttomResponse:
        cache_key = _cache_key(endpoint=endpoint, canonical_key=canonical_key, params=params)
        cached = self._read_cache(cache_key)
        if cached is not None:
            raw_payload = cached.get("raw_payload", {})
            normalized = cached.get("normalized_payload") or self._normalize(endpoint, raw_payload)
            fetched_at = cached.get("fetched_at")
            self.tracker.record_call(endpoint=endpoint, analysis_id=canonical_key, from_cache=True)
            self._log(endpoint, cache_key, "cache_hit", error=None)
            return AttomResponse(endpoint, cache_key, raw_payload, normalized, True, fetched_at, None)

        if not self.api_key:
            error = "ATTOM_API_KEY is not configured."
            self.tracker.record_match_failure(endpoint=endpoint)
            self._log(endpoint, cache_key, "config_missing", error=error)
            return AttomResponse(endpoint, cache_key, None, {}, False, None, error)

        from briarwood.cost_guard import BudgetExceeded, get_guard
        guard = get_guard()
        try:
            guard.check_attom()
        except BudgetExceeded as exc:
            self._log(endpoint, cache_key, "budget_exceeded", error=str(exc))
            return AttomResponse(endpoint, cache_key, None, {}, False, None, str(exc))

        headers = {"apikey": self.api_key, "Accept": "application/json"}
        url = f"{BASE_URL}{ENDPOINT_PATHS[endpoint]}"
        last_error: str | None = None
        for attempt in range(self.retries + 1):
            try:
                raw_payload = self.transport(url, params, headers, self.timeout_seconds)
                normalized = self._normalize(endpoint, raw_payload)
                fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self._write_cache(cache_key, raw_payload=raw_payload, normalized_payload=normalized, fetched_at=fetched_at)
                self.tracker.record_call(endpoint=endpoint, analysis_id=canonical_key, from_cache=False)
                guard.record_attom(from_cache=False)
                self._log(endpoint, cache_key, "success", error=None, attempt=attempt)
                return AttomResponse(endpoint, cache_key, raw_payload, normalized, False, fetched_at, None)
            except Exception as exc:  # never crash caller
                last_error = str(exc)
                if attempt == self.retries:
                    self.tracker.record_match_failure(endpoint=endpoint)
                self._log(endpoint, cache_key, "retryable_failure", error=last_error, attempt=attempt)
                if attempt < self.retries:
                    time.sleep(self.sleep_seconds * (attempt + 1))
        return AttomResponse(endpoint, cache_key, None, {}, False, None, last_error or "Unknown ATTOM error")

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
        if endpoint == "sale_history_detail":
            return _normalize_sale_history_detail(first_property)
        if endpoint == "sale_history_snapshot":
            return _normalize_sale_history_snapshot(first_property, raw_payload)
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
                "sale_count_trend": sale.get("salescounttrend"),
                "median_sale_price_trend": sale.get("medsalepricetrend"),
            }
        if endpoint == "community_demographics":
            community = raw_payload.get("community", {}) if isinstance(raw_payload, dict) else {}
            return {
                "housing_median_rent": community.get("housing", {}).get("medrent"),
                "occupied_pct": community.get("housing", {}).get("occupied"),
                "vacant_pct": community.get("housing", {}).get("vacant"),
                "vacant_for_sale_pct": community.get("housing", {}).get("vacantforsale"),
                "vacant_for_rent_pct": community.get("housing", {}).get("vacantforrent"),
                "population": community.get("demographic", {}).get("population"),
                "household_income": community.get("demographic", {}).get("householdincome"),
            }
        if endpoint == "property_detail_with_schools":
            base = _normalize_property_detail(first_property)
            base["schools"] = first_property.get("school", [])
            return base
        if endpoint == "property_expanded":
            return _normalize_expanded_profile(first_property)
        if endpoint == "avm_detail":
            return _normalize_avm_detail(first_property)
        if endpoint == "avm_history":
            return {"avm_history": first_property.get("avmhistory", [])}
        if endpoint == "school_snapshot":
            schools = raw_payload.get("school", []) if isinstance(raw_payload, dict) else []
            return {"schools": schools}
        if endpoint in ("preforeclosure_snapshot", "preforeclosure_detail"):
            return _normalize_preforeclosure(first_property, raw_payload)
        return {}

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(
        self,
        cache_key: str,
        *,
        raw_payload: dict[str, Any],
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
                sort_keys=True,
            )
        )

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


def _normalize_sale_history_detail(property_row: dict[str, Any]) -> dict[str, Any]:
    """Normalize /saleshistory/detail — full transaction history for one property."""
    sale = property_row.get("sale", {}) if isinstance(property_row, dict) else {}
    rows = sale.get("saleshistory", []) if isinstance(sale, dict) else []
    history = _normalize_sales_history_rows(rows)
    return _summarize_sales_history(history)


def _normalize_sale_history_snapshot(
    property_row: dict[str, Any],
    raw_payload: dict[str, Any],
) -> dict[str, Any]:
    """Normalize /saleshistory/snapshot — lighter-weight history surface."""
    sale = property_row.get("sale", {}) if isinstance(property_row, dict) else {}
    rows = sale.get("saleshistory", []) if isinstance(sale, dict) else []
    if not rows and isinstance(raw_payload, dict):
        rows = raw_payload.get("saleshistory") or raw_payload.get("salesHistory") or []
    history = _normalize_sales_history_rows(rows)
    summary = _summarize_sales_history(history)
    summary["source_surface"] = "snapshot"
    return summary


def _normalize_rental_avm(property_row: dict[str, Any]) -> dict[str, Any]:
    avm = property_row.get("avm", {})
    return {
        "estimated_monthly_rent": avm.get("rental", {}).get("predictedrent"),
        "rent_low": avm.get("rental", {}).get("predictedrentlow"),
        "rent_high": avm.get("rental", {}).get("predictedrenthigh"),
        "confidence_score": avm.get("rental", {}).get("confidence"),
    }


def _normalize_expanded_profile(property_row: dict[str, Any]) -> dict[str, Any]:
    base = _normalize_property_detail(property_row)
    building = property_row.get("building", {})
    construction = building.get("construction", {})
    interior = building.get("interior", {})
    base.update({
        "roof_type": construction.get("roofcover"),
        "foundation": construction.get("foundationtype"),
        "construction_type": construction.get("constructiontype"),
        "heating": building.get("heating", {}).get("heatingtype"),
        "cooling": building.get("heating", {}).get("coolingtype"),
        "pool": building.get("summary", {}).get("pool"),
        "fireplace": interior.get("fplccount"),
    })
    return base


def _normalize_avm_detail(property_row: dict[str, Any]) -> dict[str, Any]:
    avm = property_row.get("avm", {})
    amount = avm.get("amount", {})
    return {
        "avm_value": amount.get("value"),
        "avm_low": amount.get("low"),
        "avm_high": amount.get("high"),
        "avm_confidence": amount.get("scr") or avm.get("confidence"),
        "avm_fsd": amount.get("fsd"),
    }


def _normalize_preforeclosure(property_row: dict[str, Any], raw_payload: dict[str, Any]) -> dict[str, Any]:
    # Snapshot returns a list under "property", detail returns a single
    properties = raw_payload.get("property", []) if isinstance(raw_payload, dict) else []
    foreclosures = []
    for prop in (properties if isinstance(properties, list) else []):
        fc = prop.get("foreclosure", {})
        if not fc:
            continue
        foreclosures.append({
            "filing_date": fc.get("filingdate"),
            "default_amount": fc.get("defaultamount"),
            "lender": fc.get("lender"),
            "auction_date": fc.get("auctiondate"),
            "foreclosure_type": fc.get("fctype"),
            "address": prop.get("address", {}).get("oneLine"),
        })
    if foreclosures:
        return {"preforeclosures": foreclosures}
    # Single-property detail fallback
    fc = property_row.get("foreclosure", {})
    return {
        "filing_date": fc.get("filingdate"),
        "default_amount": fc.get("defaultamount"),
        "lender": fc.get("lender"),
        "auction_date": fc.get("auctiondate"),
        "foreclosure_type": fc.get("fctype"),
        "preforeclosures": [],
    }


def _cache_key(*, endpoint: str, canonical_key: str, params: dict[str, str]) -> str:
    raw = json.dumps({"endpoint": endpoint, "canonical_key": canonical_key, "params": params}, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_sales_history_rows(rows: Any) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        transaction_date = row.get("saleTransDate") or row.get("saledate") or row.get("saleTransdate")
        recording_date = row.get("saleRecDate") or row.get("recordingdate")
        search_date = row.get("saleSearchDate") or row.get("salesearchdate")
        price = _as_number(row.get("saleAmt") or row.get("saleamt"))
        price_per_sqft = _as_number(row.get("pricePerSizeUnit") or row.get("pricepersizeunit"))
        history.append(
            {
                "date": transaction_date or recording_date or search_date,
                "transaction_date": transaction_date,
                "recording_date": recording_date,
                "search_date": search_date,
                "price": price,
                "seller": row.get("seller"),
                "buyer": row.get("buyer"),
                "transaction_type": row.get("saleTransType") or row.get("saletranstype"),
                "deed_type": row.get("saleDocType") or row.get("deedtype"),
                "document_number": row.get("saleDocNum") or row.get("documentnumber"),
                "disclosure_type": row.get("saleDisclosureType") or row.get("saledisclosuretype"),
                "sale_code": row.get("saleCode") or row.get("salecode"),
                "price_per_sqft": price_per_sqft,
                "price_per_bed": _as_number(row.get("pricePerBed") or row.get("priceperbed")),
                "property_quality": row.get("quality"),
                "story_description": row.get("storyDesc") or row.get("storydesc"),
                "units_count": _as_number(row.get("unitsCount") or row.get("unitscount")),
            }
        )
    history.sort(key=lambda item: item.get("date") or "", reverse=True)
    return history


def _summarize_sales_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    last = history[0] if history else {}
    first = history[-1] if history else {}
    repeat_sale_pairs = _build_repeat_sale_pairs(history)
    flags: list[str] = []
    complete_events = 0
    for row in history:
        if row.get("price") and row.get("date"):
            complete_events += 1
        if row.get("disclosure_type") in (None, "", "unknown"):
            flags.append("disclosure_gap")
        if not row.get("price_per_sqft"):
            flags.append("missing_price_per_sqft")
    flags = sorted(set(flags))
    confidence_score = _score_sales_history_confidence(
        event_count=len(history),
        complete_events=complete_events,
        repeat_sale_pairs=len(repeat_sale_pairs),
        flags=flags,
    )
    return {
        "sale_count": len(history),
        "complete_event_count": complete_events,
        "first_sale_date": first.get("date"),
        "first_sale_price": first.get("price"),
        "last_sale_date": last.get("date"),
        "last_sale_price": last.get("price"),
        "sale_history": history,
        "repeat_sale_pairs": repeat_sale_pairs,
        "history_span_years": _year_delta(first.get("date"), last.get("date")),
        "most_recent_hold_years": _most_recent_hold_years(history),
        "history_flags": flags,
        "history_confidence": confidence_score,
        "history_confidence_label": _history_confidence_label(confidence_score),
    }


def _build_repeat_sale_pairs(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    ordered = list(reversed(history))
    for previous, current in zip(ordered, ordered[1:]):
        from_price = _as_number(previous.get("price"))
        to_price = _as_number(current.get("price"))
        years_held = _year_delta(previous.get("date"), current.get("date"))
        price_change = None
        price_change_pct = None
        if from_price is not None and to_price is not None:
            price_change = round(to_price - from_price, 2)
            if from_price:
                price_change_pct = round((to_price - from_price) / from_price, 4)
        pairs.append(
            {
                "from_date": previous.get("date"),
                "to_date": current.get("date"),
                "from_price": from_price,
                "to_price": to_price,
                "price_change": price_change,
                "price_change_pct": price_change_pct,
                "years_held": years_held,
            }
        )
    return pairs


def _score_sales_history_confidence(
    *,
    event_count: int,
    complete_events: int,
    repeat_sale_pairs: int,
    flags: list[str],
) -> float:
    if event_count <= 0:
        return 0.15
    score = 0.35
    score += min(event_count, 4) * 0.10
    score += min(complete_events, 4) * 0.08
    score += min(repeat_sale_pairs, 3) * 0.05
    if "disclosure_gap" in flags:
        score -= 0.08
    if "missing_price_per_sqft" in flags:
        score -= 0.05
    return round(max(0.15, min(score, 0.95)), 3)


def _history_confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "moderate"
    if score >= 0.35:
        return "low"
    return "thin"


def _as_number(value: Any) -> float | int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return number


def _year_delta(older: Any, newer: Any) -> float | None:
    older_dt = _parse_attom_date(older)
    newer_dt = _parse_attom_date(newer)
    if older_dt is None or newer_dt is None:
        return None
    return round((newer_dt - older_dt).days / 365.25, 2)


def _most_recent_hold_years(history: list[dict[str, Any]]) -> float | None:
    if len(history) < 2:
        return None
    newest = history[0]
    prior = history[1]
    return _year_delta(prior.get("date"), newest.get("date"))


def _parse_attom_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None

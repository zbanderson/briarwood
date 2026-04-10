from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

from briarwood.data_quality.normalizers import normalize_town
from briarwood.data_sources.attom_client import AttomClient
from briarwood.data_sources.nj_tax_intelligence import NJTaxIntelligenceStore, town_tax_context


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SALES_PATH = ROOT / "data" / "comps" / "sales_comps.json"
DEFAULT_ACTIVE_PATH = ROOT / "data" / "comps" / "active_listings.json"
DEFAULT_CACHE_DIR = ROOT / "data" / "cache" / "market_snapshots"


@dataclass(slots=True)
class TownMarketSnapshot:
    town: str
    county: str
    median_sale_price: float | None
    avg_sale_price: float | None
    sale_count: int
    sale_count_trend: float | None
    median_rent: float | None
    occupied_pct: float | None
    vacant_pct: float | None
    vacant_for_sale_pct: float | None
    vacant_for_rent_pct: float | None
    general_tax_rate: float | None
    effective_tax_rate: float | None
    equalization_ratio: float | None
    tax_burden_context: str
    equalization_context: str
    permit_activity_summary: str
    data_confidence: float


class MarketSnapshotBuilder:
    def __init__(
        self,
        *,
        attom_client: AttomClient | None = None,
        tax_store: NJTaxIntelligenceStore | None = None,
        sales_path: str | Path = DEFAULT_SALES_PATH,
        active_path: str | Path = DEFAULT_ACTIVE_PATH,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
    ) -> None:
        self.attom_client = attom_client
        self.tax_store = tax_store
        self.sales_path = Path(sales_path)
        self.active_path = Path(active_path)
        self.cache_dir = Path(cache_dir)

    def build_snapshot(self, *, town: str, county: str, state: str = "NJ", use_cache: bool = True) -> TownMarketSnapshot:
        normalized_town = normalize_town(town) or "Unknown"
        cache_key = f"{normalized_town.lower().replace(' ', '-')}-{state.lower()}"
        if use_cache:
            cached = self._read_cache(cache_key)
            if cached is not None:
                return cached

        local_sales = _load_rows(self.sales_path, "sales")
        local_active = _load_rows(self.active_path, "listings")
        sales = [row for row in local_sales if normalize_town(row.get("town")) == normalized_town]
        active = [row for row in local_active if normalize_town(row.get("town")) == normalized_town]
        sale_prices = [float(row["sale_price"]) for row in sales if isinstance(row.get("sale_price"), (int, float))]
        median_sale_price = float(median(sale_prices)) if sale_prices else None
        avg_sale_price = float(mean(sale_prices)) if sale_prices else None

        permit_summary = "ATTOM permits unavailable."
        median_rent = None
        occupied_pct = None
        vacant_pct = None
        vacant_for_sale_pct = None
        vacant_for_rent_pct = None
        sale_count_trend = None
        if self.attom_client is not None:
            town_key = f"{normalized_town}-{county}-{state}"
            demographics = self.attom_client.community_demographics(town_key, state=state, locality=normalized_town)
            median_rent = _as_float(demographics.normalized_payload.get("housing_median_rent"))
            occupied_pct = _as_float(demographics.normalized_payload.get("occupied_pct"))
            vacant_pct = _as_float(demographics.normalized_payload.get("vacant_pct"))
            vacant_for_sale_pct = _as_float(demographics.normalized_payload.get("vacant_for_sale_pct"))
            vacant_for_rent_pct = _as_float(demographics.normalized_payload.get("vacant_for_rent_pct"))
            sales_trend = self.attom_client.sales_trend(town_key, state=state, locality=normalized_town)
            sale_count_trend = _as_float(sales_trend.normalized_payload.get("sale_count_trend"))
            permits = self.attom_client.building_permits(town_key, state=state, locality=normalized_town)
            permit_count = int(permits.normalized_payload.get("permit_count") or 0)
            permit_summary = (
                f"{permit_count} recent permit records surfaced by ATTOM."
                if permit_count
                else "No recent ATTOM permit activity surfaced."
            )

        tax_context = town_tax_context(self.tax_store, town=normalized_town, county=county) if self.tax_store else {}
        confidence = _snapshot_confidence(
            sale_count=len(sales),
            active_count=len(active),
            has_tax_context=bool(tax_context),
            has_demographics=median_rent is not None or occupied_pct is not None,
        )
        snapshot = TownMarketSnapshot(
            town=normalized_town,
            county=county,
            median_sale_price=median_sale_price,
            avg_sale_price=avg_sale_price,
            sale_count=len(sales),
            sale_count_trend=sale_count_trend,
            median_rent=median_rent,
            occupied_pct=occupied_pct,
            vacant_pct=vacant_pct,
            vacant_for_sale_pct=vacant_for_sale_pct,
            vacant_for_rent_pct=vacant_for_rent_pct,
            general_tax_rate=_as_float(tax_context.get("general_tax_rate")),
            effective_tax_rate=_as_float(tax_context.get("effective_tax_rate")),
            equalization_ratio=_as_float(tax_context.get("equalization_ratio")),
            tax_burden_context=_tax_burden_context(tax_context),
            equalization_context=_equalization_context(tax_context),
            permit_activity_summary=permit_summary,
            data_confidence=confidence,
        )
        self._write_cache(cache_key, snapshot)
        return snapshot

    def _read_cache(self, cache_key: str) -> TownMarketSnapshot | None:
        path = self.cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
            return TownMarketSnapshot(**payload)
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    def _write_cache(self, cache_key: str, snapshot: TownMarketSnapshot) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{cache_key}.json"
        path.write_text(json.dumps(asdict(snapshot), indent=2, sort_keys=True))


def _load_rows(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    rows = payload.get(key, []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _snapshot_confidence(*, sale_count: int, active_count: int, has_tax_context: bool, has_demographics: bool) -> float:
    confidence = 0.25
    confidence += min(sale_count / 20.0, 1.0) * 0.35
    confidence += min(active_count / 12.0, 1.0) * 0.15
    confidence += 0.15 if has_tax_context else 0.0
    confidence += 0.10 if has_demographics else 0.0
    return round(min(confidence, 1.0), 3)


def _as_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tax_burden_context(tax_context: dict[str, Any]) -> str:
    effective_tax_rate = _as_float(tax_context.get("effective_tax_rate"))
    if effective_tax_rate is None:
        return "NJ tax context unavailable."
    if effective_tax_rate >= 2.5:
        return f"High municipal tax burden at roughly {effective_tax_rate:.2f}%."
    if effective_tax_rate >= 1.75:
        return f"Moderate municipal tax burden at roughly {effective_tax_rate:.2f}%."
    return f"Relatively lighter municipal tax burden at roughly {effective_tax_rate:.2f}%."


def _equalization_context(tax_context: dict[str, Any]) -> str:
    equalization_ratio = _as_float(tax_context.get("equalization_ratio"))
    if equalization_ratio is None:
        return "Equalization context unavailable."
    if equalization_ratio < 85:
        return f"Equalization ratio near {equalization_ratio:.1f} suggests assessments may lag true value."
    if equalization_ratio > 115:
        return f"Equalization ratio near {equalization_ratio:.1f} suggests assessments may already run above market."
    return f"Equalization ratio near {equalization_ratio:.1f} indicates a relatively balanced assessment base."

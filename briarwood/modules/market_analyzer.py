from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from briarwood.agents.comparable_sales.store import JsonActiveListingStore, JsonComparableSalesStore
from briarwood.local_intelligence.models import ImpactDirection, SignalStatus, TownSignal
from briarwood.local_intelligence.storage import JsonLocalSignalStore, LocalSignalStore
from briarwood.modules.town_aggregation_diagnostics import normalize_town_name


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACTIVE_PATH = ROOT / "data" / "comps" / "active_listings.json"
DEFAULT_SALES_PATH = ROOT / "data" / "comps" / "sales_comps.json"
DEFAULT_RENT_CONTEXT_PATH = ROOT / "data" / "town_county" / "zillow_rent_context.json"

_MULTI_UNIT_TYPES = {"duplex", "triplex", "fourplex", "multi family", "multi_family"}
_STR_KEYWORDS = {
    "beach", "shore", "coastal", "marina", "boardwalk", "downtown", "walkable", "vacation", "summer",
}


@dataclass(slots=True)
class MarketAnalysisOutput:
    town: str
    market_score: float
    structure_score: float
    valuation_score: float
    catalyst_score: float
    investability_score: float
    metrics: dict[str, Any]
    narrative: str


@dataclass(slots=True)
class _TownAggregate:
    town: str
    state: str
    active_prices: list[float]
    sold_prices: list[float]
    ppsf_values: list[float]
    dom_values: list[float]
    active_count: int
    sold_count: int
    sold_dates: list[date]
    price_cut_count: int
    total_listing_count: int
    multi_unit_count: int
    str_signal_count: int
    rent_estimate: float | None
    signals: list[TownSignal]
    sold_dom_series: list[tuple[date, float]]
    sold_price_series: list[tuple[date, float]]


class MarketAnalyzer:
    """Town-level market scanner built from Briarwood's active and sold listing datasets."""

    def __init__(
        self,
        *,
        active_path: str | Path = DEFAULT_ACTIVE_PATH,
        sales_path: str | Path = DEFAULT_SALES_PATH,
        rent_context_path: str | Path = DEFAULT_RENT_CONTEXT_PATH,
        local_signal_store: LocalSignalStore | None = None,
    ) -> None:
        self.active_path = Path(active_path)
        self.sales_path = Path(sales_path)
        self.rent_context_path = Path(rent_context_path)
        self.local_signal_store = local_signal_store or JsonLocalSignalStore()

    def analyze(self) -> list[MarketAnalysisOutput]:
        active_rows = JsonActiveListingStore(self.active_path).load().listings
        sales_rows = JsonComparableSalesStore(self.sales_path).load().sales
        rent_context = _load_rent_context(self.rent_context_path)
        towns = self._aggregate(active_rows=active_rows, sales_rows=sales_rows, rent_context=rent_context)
        if not towns:
            return []

        peer_ppsf = [self._town_avg_ppsf(item) for item in towns.values() if self._town_avg_ppsf(item) is not None]
        peer_prices = [self._town_median_price(item) for item in towns.values() if self._town_median_price(item) is not None]
        peer_ppsf_median = _median_or_none(peer_ppsf)
        peer_price_median = _median_or_none(peer_prices)

        analyses = [
            self._analyze_town(
                town=town,
                aggregate=aggregate,
                peer_ppsf_median=peer_ppsf_median,
                peer_price_median=peer_price_median,
            )
            for town, aggregate in sorted(towns.items())
        ]
        analyses.sort(key=lambda item: (-item.market_score, item.town))
        return analyses

    def _aggregate(
        self,
        *,
        active_rows: list[Any],
        sales_rows: list[Any],
        rent_context: dict[tuple[str, str], float],
    ) -> dict[str, _TownAggregate]:
        towns: dict[str, _TownAggregate] = {}

        def ensure(town: str, state: str) -> _TownAggregate:
            if town not in towns:
                signals = self.local_signal_store.load_town_signals(town=town, state=state)
                towns[town] = _TownAggregate(
                    town=town,
                    state=state,
                    active_prices=[],
                    sold_prices=[],
                    ppsf_values=[],
                    dom_values=[],
                    active_count=0,
                    sold_count=0,
                    sold_dates=[],
                    price_cut_count=0,
                    total_listing_count=0,
                    multi_unit_count=0,
                    str_signal_count=0,
                    rent_estimate=rent_context.get((town, state)),
                    signals=signals,
                    sold_dom_series=[],
                    sold_price_series=[],
                )
            return towns[town]

        for row in active_rows:
            town = normalize_town_name(getattr(row, "town", None))
            state = str(getattr(row, "state", "") or "").strip().upper() or "NA"
            if town == "Unknown":
                continue
            item = ensure(town, state)
            item.active_count += 1
            item.total_listing_count += 1
            if getattr(row, "list_price", None) is not None:
                item.active_prices.append(float(row.list_price))
            ppsf = _price_per_sqft(getattr(row, "list_price", None), getattr(row, "sqft", None))
            if ppsf is not None:
                item.ppsf_values.append(ppsf)
            if getattr(row, "days_on_market", None) is not None:
                item.dom_values.append(float(row.days_on_market))
            if _is_multi_unit(getattr(row, "property_type", None)):
                item.multi_unit_count += 1
            if _has_str_signal(getattr(row, "source_notes", None), getattr(row, "notes", None)):
                item.str_signal_count += 1
            if _has_price_cut_signal(getattr(row, "source_notes", None), getattr(row, "notes", None)):
                item.price_cut_count += 1

        for row in sales_rows:
            town = normalize_town_name(getattr(row, "town", None))
            state = str(getattr(row, "state", "") or "").strip().upper() or "NA"
            if town == "Unknown":
                continue
            item = ensure(town, state)
            item.sold_count += 1
            item.total_listing_count += 1
            if getattr(row, "sale_price", None) is not None:
                item.sold_prices.append(float(row.sale_price))
                sale_price_value = float(row.sale_price)
            else:
                sale_price_value = None
            ppsf = _price_per_sqft(getattr(row, "sale_price", None), getattr(row, "sqft", None))
            if ppsf is not None:
                item.ppsf_values.append(ppsf)
            if getattr(row, "days_on_market", None) is not None:
                item.dom_values.append(float(row.days_on_market))
            sale_date = _parse_date(getattr(row, "sale_date", None))
            if sale_date is not None:
                item.sold_dates.append(sale_date)
                if sale_price_value is not None:
                    item.sold_price_series.append((sale_date, sale_price_value))
                if getattr(row, "days_on_market", None) is not None:
                    item.sold_dom_series.append((sale_date, float(row.days_on_market)))
            if _is_multi_unit(getattr(row, "property_type", None)):
                item.multi_unit_count += 1
            if _has_str_signal(getattr(row, "source_notes", None), getattr(row, "micro_location_notes", None), getattr(row, "location_tags", None)):
                item.str_signal_count += 1

        return towns

    def _analyze_town(
        self,
        *,
        town: str,
        aggregate: _TownAggregate,
        peer_ppsf_median: float | None,
        peer_price_median: float | None,
    ) -> MarketAnalysisOutput:
        avg_ppsf = self._town_avg_ppsf(aggregate)
        median_price = self._town_median_price(aggregate)
        avg_dom = _avg_or_none(aggregate.dom_values)
        inventory_count = aggregate.active_count
        sold_per_month = _sold_per_month(aggregate.sold_count, aggregate.sold_dates)
        price_cuts_pct = (
            aggregate.price_cut_count / aggregate.active_count
            if aggregate.active_count > 0 and aggregate.price_cut_count > 0
            else None
        )
        sell_through_rate = (
            sold_per_month / inventory_count
            if sold_per_month is not None and inventory_count > 0
            else None
        )
        price_trend_pct = _series_trend_pct(aggregate.sold_price_series)
        dom_trend_pct = _series_trend_pct(aggregate.sold_dom_series)
        months_of_supply = (
            inventory_count / sold_per_month
            if sold_per_month not in (None, 0)
            else None
        )

        buyer_vs_seller_score = _market_balance_score(avg_dom=avg_dom, sell_through_rate=sell_through_rate)
        structure_score = _structure_score(
            avg_dom=avg_dom,
            sell_through_rate=sell_through_rate,
            months_of_supply=months_of_supply,
            inventory_count=inventory_count,
        )
        valuation_score = _valuation_score(
            avg_ppsf=avg_ppsf,
            median_price=median_price,
            peer_ppsf_median=peer_ppsf_median,
            peer_price_median=peer_price_median,
        )
        catalyst_score, catalyst_metrics = _catalyst_score(aggregate.signals)
        price_to_rent_ratio = _price_to_rent_ratio(median_price=median_price, monthly_rent=aggregate.rent_estimate)
        rent_yield = _gross_rent_yield(median_price=median_price, monthly_rent=aggregate.rent_estimate)
        multi_unit_share = (
            aggregate.multi_unit_count / aggregate.total_listing_count
            if aggregate.total_listing_count > 0
            else 0.0
        )
        str_viability_signal = (
            aggregate.str_signal_count / aggregate.total_listing_count
            if aggregate.total_listing_count > 0
            else 0.0
        )
        investability_score = _investability_score(
            rent_yield=rent_yield,
            multi_unit_share=multi_unit_share,
            str_viability_signal=str_viability_signal,
            price_to_rent_ratio=price_to_rent_ratio,
        )

        market_score = round(
            (0.28 * structure_score)
            + (0.27 * valuation_score)
            + (0.22 * catalyst_score)
            + (0.23 * investability_score),
            1,
        )

        metrics = {
            "state": aggregate.state,
            "avg_price_per_sqft": _round_or_none(avg_ppsf, 1),
            "median_price": _round_or_none(median_price, 0),
            "avg_dom": _round_or_none(avg_dom, 1),
            "inventory_count": inventory_count,
            "sold_count": aggregate.sold_count,
            "sold_per_month": _round_or_none(sold_per_month, 2),
            "price_cuts_pct": _round_or_none(price_cuts_pct, 3),
            "sell_through_rate": _round_or_none(sell_through_rate, 3),
            "months_of_supply": _round_or_none(months_of_supply, 2),
            "price_trend_pct": _round_or_none(price_trend_pct, 3),
            "dom_trend_pct": _round_or_none(dom_trend_pct, 3),
            "buyer_vs_seller_score": _round_or_none(buyer_vs_seller_score, 1),
            "price_to_rent_ratio": _round_or_none(price_to_rent_ratio, 1),
            "estimated_monthly_rent": _round_or_none(aggregate.rent_estimate, 0),
            "gross_rent_yield": _round_or_none(rent_yield, 3),
            "multi_unit_share": _round_or_none(multi_unit_share, 3),
            "str_viability_signal": _round_or_none(str_viability_signal, 3),
            "peer_price_per_sqft_median": _round_or_none(peer_ppsf_median, 1),
            "relative_ppsf_discount_pct": _round_or_none(_relative_discount(avg_ppsf, peer_ppsf_median), 3),
            "relative_price_discount_pct": _round_or_none(_relative_discount(median_price, peer_price_median), 3),
            **catalyst_metrics,
        }
        narrative = _market_narrative(
            town=town,
            buyer_vs_seller_score=buyer_vs_seller_score,
            valuation_score=valuation_score,
            catalyst_score=catalyst_score,
            investability_score=investability_score,
            metrics=metrics,
        )
        return MarketAnalysisOutput(
            town=town,
            market_score=market_score,
            structure_score=round(structure_score, 1),
            valuation_score=round(valuation_score, 1),
            catalyst_score=round(catalyst_score, 1),
            investability_score=round(investability_score, 1),
            metrics=metrics,
            narrative=narrative,
        )

    @staticmethod
    def _town_avg_ppsf(aggregate: _TownAggregate) -> float | None:
        return _avg_or_none(aggregate.ppsf_values)

    @staticmethod
    def _town_median_price(aggregate: _TownAggregate) -> float | None:
        prices = aggregate.sold_prices or aggregate.active_prices
        return _median_or_none(prices)


def analyze_markets(
    *,
    active_path: str | Path = DEFAULT_ACTIVE_PATH,
    sales_path: str | Path = DEFAULT_SALES_PATH,
    rent_context_path: str | Path = DEFAULT_RENT_CONTEXT_PATH,
    local_signal_store: LocalSignalStore | None = None,
) -> list[MarketAnalysisOutput]:
    return MarketAnalyzer(
        active_path=active_path,
        sales_path=sales_path,
        rent_context_path=rent_context_path,
        local_signal_store=local_signal_store,
    ).analyze()


def _market_balance_score(*, avg_dom: float | None, sell_through_rate: float | None) -> float:
    dom_score = 0.5 if avg_dom is None else 1.0 - _clamp((avg_dom - 18.0) / 72.0, 0.0, 1.0)
    sell_score = 0.5 if sell_through_rate is None else _clamp(sell_through_rate / 0.45, 0.0, 1.0)
    return round(((0.55 * dom_score) + (0.45 * sell_score)) * 10.0, 1)


def _structure_score(
    *,
    avg_dom: float | None,
    sell_through_rate: float | None,
    months_of_supply: float | None,
    inventory_count: int,
) -> float:
    seller_strength = _market_balance_score(avg_dom=avg_dom, sell_through_rate=sell_through_rate)
    buyer_opportunity_dom = 0.4 if avg_dom is None else _clamp((avg_dom - 24.0) / 70.0, 0.0, 1.0)
    buyer_opportunity_supply = 0.35 if months_of_supply is None else _clamp((months_of_supply - 2.5) / 5.0, 0.0, 1.0)
    inventory_depth = _clamp(inventory_count / 12.0, 0.0, 1.0)
    buyer_opportunity = ((0.45 * buyer_opportunity_dom) + (0.40 * buyer_opportunity_supply) + (0.15 * inventory_depth)) * 10.0
    return round(max(seller_strength * 0.95, buyer_opportunity), 1)


def _valuation_score(
    *,
    avg_ppsf: float | None,
    median_price: float | None,
    peer_ppsf_median: float | None,
    peer_price_median: float | None,
) -> float:
    if avg_ppsf is None and median_price is None:
        return 5.0
    ppsf_discount = _relative_discount(avg_ppsf, peer_ppsf_median)
    price_discount = _relative_discount(median_price, peer_price_median)
    components = []
    if ppsf_discount is not None:
        components.append(5.4 + (ppsf_discount * 18.0))
    if price_discount is not None:
        components.append(5.0 + (price_discount * 12.0))
    if not components:
        return 5.0
    return round(_clamp(sum(components) / len(components), 0.0, 10.0), 1)


def _catalyst_score(signals: list[TownSignal]) -> tuple[float, dict[str, Any]]:
    if not signals:
        return 4.2, {
            "confirmed_catalysts": 0,
            "pipeline_catalysts": 0,
            "negative_catalysts": 0,
            "catalyst_signal_count": 0,
        }

    positive = 0.0
    negative = 0.0
    confirmed = 0
    pipeline = 0
    negative_count = 0
    for signal in signals:
        status_weight = _status_weight(signal.status)
        impact_weight = signal.impact_magnitude / 5.0
        weighted = status_weight * impact_weight * float(signal.confidence)
        if signal.impact_direction == ImpactDirection.NEGATIVE:
            negative += weighted
            negative_count += 1
        elif signal.impact_direction == ImpactDirection.POSITIVE:
            positive += weighted
            if signal.status in {SignalStatus.APPROVED, SignalStatus.FUNDED, SignalStatus.IN_PROGRESS, SignalStatus.COMPLETED}:
                confirmed += 1
            else:
                pipeline += 1

    raw = 4.5 + (positive * 2.2) - (negative * 1.3) + (confirmed * 0.35)
    return round(_clamp(raw, 0.0, 10.0), 1), {
        "confirmed_catalysts": confirmed,
        "pipeline_catalysts": pipeline,
        "negative_catalysts": negative_count,
        "catalyst_signal_count": len(signals),
    }


def _investability_score(
    *,
    rent_yield: float | None,
    multi_unit_share: float,
    str_viability_signal: float,
    price_to_rent_ratio: float | None,
) -> float:
    if rent_yield is None and price_to_rent_ratio is None:
        rent_component = 4.8
    elif rent_yield is not None:
        rent_component = _clamp(2.0 + (rent_yield * 110.0), 0.0, 10.0)
    else:
        rent_component = _clamp(12.0 - ((price_to_rent_ratio or 18.0) - 12.0) * 0.55, 0.0, 10.0)
    multi_component = _clamp(3.0 + (multi_unit_share * 18.0), 0.0, 10.0)
    str_component = _clamp(3.5 + (str_viability_signal * 12.0), 0.0, 10.0)
    score = (0.55 * rent_component) + (0.25 * multi_component) + (0.20 * str_component)
    return round(_clamp(score, 0.0, 10.0), 1)


def _market_narrative(
    *,
    town: str,
    buyer_vs_seller_score: float,
    valuation_score: float,
    catalyst_score: float,
    investability_score: float,
    metrics: dict[str, Any],
) -> str:
    market_tone = (
        "seller-leaning"
        if buyer_vs_seller_score >= 6.6
        else "buyer-leaning"
        if buyer_vs_seller_score <= 4.0
        else "more balanced"
    )
    valuation_line = (
        f"Valuation screens attractively, with pricing running about {abs(metrics['relative_ppsf_discount_pct']) * 100:.0f}% below the peer town median on a price-per-foot basis."
        if isinstance(metrics.get("relative_ppsf_discount_pct"), (int, float)) and metrics["relative_ppsf_discount_pct"] > 0.02
        else "Valuation looks closer to the peer set, so upside will need to come more from execution than simple multiple expansion."
        if valuation_score < 5.5
        else "Valuation is modestly favorable versus nearby towns, keeping entry risk contained."
    )
    catalyst_line = (
        f"Local catalyst support is real, with {metrics['confirmed_catalysts']} confirmed development signal(s) and {metrics['pipeline_catalysts']} additional pipeline item(s) on file."
        if catalyst_score >= 6.0
        else "Catalyst visibility is still limited, so the market call leans more on pricing and liquidity than on confirmed local developments."
        if catalyst_score <= 4.5
        else "Catalyst evidence is mixed but directionally supportive enough to keep the town on the watchlist."
    )
    implication = (
        "Net: this market merits near-term sourcing attention because pricing, local signals, and income optionality line up cleanly."
        if investability_score >= 6.5 and valuation_score >= 6.0
        else "Net: this is better framed as a selective hunting ground than a blanket buy signal, with deal quality still needing to do the heavy lifting."
    )
    first_line = (
        f"{town} is currently a {market_tone} market, with average marketing times around {int(round(metrics['avg_dom'])) if metrics.get('avg_dom') is not None else 'n/a'} days and sell-through near {metrics['sell_through_rate']:.2f}x inventory."
        if metrics.get("sell_through_rate") is not None
        else f"{town} reads as {market_tone} for now, although turnover visibility is still incomplete."
    )
    return " ".join([first_line, valuation_line, catalyst_line, implication])


def _load_rent_context(path: Path) -> dict[tuple[str, str], float]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    towns = payload.get("towns", []) if isinstance(payload, dict) else []
    context: dict[tuple[str, str], float] = {}
    for row in towns:
        if not isinstance(row, dict):
            continue
        town = normalize_town_name(row.get("geography_name"))
        state = str(row.get("state") or "").strip().upper()
        rent = row.get("zori_current")
        if town == "Unknown" or not state or not isinstance(rent, (int, float)):
            continue
        context[(town, state)] = float(rent)
    return context


def _price_per_sqft(price: object, sqft: object) -> float | None:
    if not isinstance(price, (int, float)) or not isinstance(sqft, (int, float)) or sqft <= 0:
        return None
    return float(price) / float(sqft)


def _sold_per_month(sold_count: int, sold_dates: list[date]) -> float | None:
    if sold_count <= 0:
        return None
    if len(sold_dates) < 2:
        return float(sold_count)
    first = min(sold_dates)
    last = max(sold_dates)
    month_span = max(((last.year - first.year) * 12) + (last.month - first.month) + 1, 1)
    return sold_count / month_span


def _price_to_rent_ratio(*, median_price: float | None, monthly_rent: float | None) -> float | None:
    if median_price in (None, 0) or monthly_rent in (None, 0):
        return None
    return float(median_price) / (float(monthly_rent) * 12.0)


def _gross_rent_yield(*, median_price: float | None, monthly_rent: float | None) -> float | None:
    if median_price in (None, 0) or monthly_rent in (None, 0):
        return None
    return (float(monthly_rent) * 12.0) / float(median_price)


def _relative_discount(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline in (None, 0):
        return None
    return 1.0 - (float(value) / float(baseline))


def _series_trend_pct(series: list[tuple[date, float]]) -> float | None:
    if len(series) < 4:
        return None
    ordered = sorted(series, key=lambda item: item[0])
    midpoint = max(len(ordered) // 2, 1)
    earlier = [value for _, value in ordered[:midpoint]]
    later = [value for _, value in ordered[midpoint:]]
    if not earlier or not later:
        return None
    earlier_median = _median_or_none(earlier)
    later_median = _median_or_none(later)
    if earlier_median in (None, 0) or later_median is None:
        return None
    return (float(later_median) - float(earlier_median)) / float(earlier_median)


def _is_multi_unit(value: object) -> bool:
    normalized = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    return normalized in _MULTI_UNIT_TYPES


def _has_str_signal(*values: object) -> bool:
    haystack = " ".join(_flatten_text_fragments(values))
    return any(keyword in haystack for keyword in _STR_KEYWORDS)


def _has_price_cut_signal(*values: object) -> bool:
    haystack = " ".join(_flatten_text_fragments(values))
    return "price cut" in haystack or "price reduced" in haystack or "reduced price" in haystack


def _flatten_text_fragments(values: tuple[object, ...]) -> list[str]:
    fragments: list[str] = []
    for value in values:
        if isinstance(value, str):
            fragments.append(value.strip().lower())
        elif isinstance(value, list):
            fragments.extend(str(item).strip().lower() for item in value if item not in (None, ""))
    return fragments


def _status_weight(status: SignalStatus) -> float:
    if status in {SignalStatus.APPROVED, SignalStatus.FUNDED, SignalStatus.IN_PROGRESS, SignalStatus.COMPLETED}:
        return 1.0
    if status in {SignalStatus.REVIEWED, SignalStatus.PROPOSED}:
        return 0.7
    if status == SignalStatus.MENTIONED:
        return 0.45
    if status == SignalStatus.REJECTED:
        return 0.8
    return 0.5


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _avg_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _round_or_none(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))

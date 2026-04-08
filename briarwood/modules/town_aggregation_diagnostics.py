from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
import re

import pandas as pd

from briarwood.agents.comparable_sales.store import JsonActiveListingStore, JsonComparableSalesStore


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SALES_PATH = ROOT / "data" / "comps" / "sales_comps.json"
DEFAULT_ACTIVE_PATH = ROOT / "data" / "comps" / "active_listings.json"

CORE_MISSINGNESS_FIELDS = [
    "price",
    "sqft",
    "lot_size",
    "beds",
    "baths",
    "year_built",
    "days_on_market",
]

LOW_SAMPLE_THRESHOLD = 8
HIGH_MISSINGNESS_THRESHOLD = 0.35
HIGH_DISPERSION_THRESHOLD = 0.35
OUTLIER_HEAVY_THRESHOLD = 0.20
LOW_CONFIDENCE_THRESHOLD = 0.60

_TOWN_NAME_OVERRIDES = {
    "avon by the sea": "Avon By The Sea",
    "avon-by-the-sea": "Avon By The Sea",
}


@dataclass(slots=True)
class TownAggregationDiagnosticsResult:
    town_summary: pd.DataFrame
    cross_town_comparison: pd.DataFrame
    town_premium_index: pd.DataFrame
    feature_sensitivity: pd.DataFrame
    town_qa_flags: pd.DataFrame
    town_calibration: pd.DataFrame
    normalized_records: pd.DataFrame


@dataclass(slots=True)
class TownContext:
    town: str
    listing_count: int
    sold_count: int
    sample_size: int
    median_list_price: float | None
    median_sale_price: float | None
    median_price: float | None
    median_ppsf: float | None
    median_sqft: float | None
    median_lot_size: float | None
    median_days_on_market: float | None
    median_sale_to_list_ratio: float | None
    town_price_index: float | None
    town_ppsf_index: float | None
    town_lot_index: float | None
    town_liquidity_index: float | None
    avg_confidence_score: float | None
    missing_data_rate: float | None
    outlier_count: int
    sqft_coverage_rate: float
    lot_size_coverage_rate: float
    year_built_coverage_rate: float
    ppsf_std_dev: float | None
    low_sample_flag: bool
    high_missingness_flag: bool
    high_dispersion_flag: bool
    outlier_heavy_flag: bool
    low_confidence_flag: bool
    context_confidence: float
    qa_flags: list[str]


def build_town_aggregation_diagnostics(
    *,
    sales_path: str | Path = DEFAULT_SALES_PATH,
    active_path: str | Path = DEFAULT_ACTIVE_PATH,
) -> TownAggregationDiagnosticsResult:
    normalized = load_normalized_market_records(sales_path=sales_path, active_path=active_path)
    town_summary = build_town_baseline_metrics(normalized)
    comparison = build_cross_town_comparison_table(town_summary, normalized)
    premium_index = build_town_premium_index(town_summary, normalized)
    feature_sensitivity = build_feature_sensitivity_by_town(normalized)
    qa_flags = build_town_qa_flags(town_summary, normalized)
    calibration = build_town_calibration_table(normalized)
    return TownAggregationDiagnosticsResult(
        town_summary=town_summary,
        cross_town_comparison=comparison,
        town_premium_index=premium_index,
        feature_sensitivity=feature_sensitivity,
        town_qa_flags=qa_flags,
        town_calibration=calibration,
        normalized_records=normalized,
    )


@lru_cache(maxsize=4)
def _cached_town_aggregation(sales_path_str: str, active_path_str: str) -> TownAggregationDiagnosticsResult:
    return build_town_aggregation_diagnostics(
        sales_path=sales_path_str,
        active_path=active_path_str,
    )


def get_town_context(
    town: str | None,
    *,
    sales_path: str | Path = DEFAULT_SALES_PATH,
    active_path: str | Path = DEFAULT_ACTIVE_PATH,
) -> TownContext | None:
    normalized_town = normalize_town_name(town)
    if normalized_town == "Unknown":
        return None

    diagnostics = _cached_town_aggregation(str(Path(sales_path)), str(Path(active_path)))
    if diagnostics.town_summary.empty:
        return None

    summary_row = diagnostics.town_summary[diagnostics.town_summary["town"] == normalized_town]
    qa_row = diagnostics.town_qa_flags[diagnostics.town_qa_flags["town"] == normalized_town] if not diagnostics.town_qa_flags.empty else pd.DataFrame()
    premium_row = diagnostics.town_premium_index[diagnostics.town_premium_index["town"] == normalized_town] if not diagnostics.town_premium_index.empty else pd.DataFrame()
    if summary_row.empty:
        return None

    summary_item = summary_row.iloc[0]
    qa_item = qa_row.iloc[0] if not qa_row.empty else None
    premium_item = premium_row.iloc[0] if not premium_row.empty else None

    return TownContext(
        town=normalized_town,
        listing_count=int(summary_item.get("listing_count") or 0),
        sold_count=int(summary_item.get("sold_count") or 0),
        sample_size=int(qa_item.get("sample_size") or 0) if qa_item is not None else int((summary_item.get("listing_count") or 0) + (summary_item.get("sold_count") or 0)),
        median_list_price=_coerce_optional_float(summary_item.get("median_list_price")),
        median_sale_price=_coerce_optional_float(summary_item.get("median_sale_price")),
        median_price=_coerce_optional_float(summary_item.get("median_sale_price") if pd.notna(summary_item.get("median_sale_price")) else summary_item.get("median_list_price")),
        median_ppsf=_coerce_optional_float(summary_item.get("median_ppsf")),
        median_sqft=_coerce_optional_float(summary_item.get("median_sqft")),
        median_lot_size=_coerce_optional_float(summary_item.get("median_lot_size")),
        median_days_on_market=_coerce_optional_float(summary_item.get("median_days_on_market")),
        median_sale_to_list_ratio=_coerce_optional_float(summary_item.get("median_sale_to_list_ratio")),
        town_price_index=_coerce_optional_float(premium_item.get("town_price_index")) if premium_item is not None else None,
        town_ppsf_index=_coerce_optional_float(premium_item.get("town_ppsf_index")) if premium_item is not None else None,
        town_lot_index=_coerce_optional_float(premium_item.get("town_lot_index")) if premium_item is not None else None,
        town_liquidity_index=_coerce_optional_float(premium_item.get("town_liquidity_index")) if premium_item is not None else None,
        avg_confidence_score=_coerce_optional_float(summary_item.get("avg_confidence_score")),
        missing_data_rate=_coerce_optional_float(summary_item.get("missing_data_rate")),
        outlier_count=int(summary_item.get("outlier_count") or 0),
        sqft_coverage_rate=float(qa_item.get("sqft_coverage_rate") or 0.0) if qa_item is not None else 0.0,
        lot_size_coverage_rate=float(qa_item.get("lot_size_coverage_rate") or 0.0) if qa_item is not None else 0.0,
        year_built_coverage_rate=float(qa_item.get("year_built_coverage_rate") or 0.0) if qa_item is not None else 0.0,
        ppsf_std_dev=_coerce_optional_float(qa_item.get("ppsf_std_dev")) if qa_item is not None else None,
        low_sample_flag=bool(qa_item.get("low_sample_flag")) if qa_item is not None else False,
        high_missingness_flag=bool(qa_item.get("high_missingness_flag")) if qa_item is not None else False,
        high_dispersion_flag=bool(qa_item.get("high_dispersion_flag")) if qa_item is not None else False,
        outlier_heavy_flag=bool(qa_item.get("outlier_heavy_flag")) if qa_item is not None else False,
        low_confidence_flag=bool(qa_item.get("low_confidence_flag")) if qa_item is not None else False,
        context_confidence=_town_context_confidence(summary_item, qa_item),
        qa_flags=_town_qa_flag_names(qa_item),
    )


def load_normalized_market_records(
    *,
    sales_path: str | Path = DEFAULT_SALES_PATH,
    active_path: str | Path = DEFAULT_ACTIVE_PATH,
    sales_rows: list[dict[str, Any]] | None = None,
    active_rows: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    sales = sales_rows if sales_rows is not None else _load_sales_rows(sales_path)
    active = active_rows if active_rows is not None else _load_active_rows(active_path)

    rows = [_normalize_sale_row(row) for row in sales] + [_normalize_active_row(row) for row in active]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=_normalized_columns())
    for column in _normalized_columns():
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["town"] = frame["town"].apply(normalize_town_name)
    return frame[_normalized_columns()]


def normalize_town_name(value: Any) -> str:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return "Unknown"
    raw = str(value).strip()
    key = raw.lower()
    if key in _TOWN_NAME_OVERRIDES:
        return _TOWN_NAME_OVERRIDES[key]
    cleaned = re.sub(r"[-_]+", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else "Unknown"


def build_town_baseline_metrics(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return pd.DataFrame(columns=[
            "town",
            "listing_count",
            "sold_count",
            "median_list_price",
            "median_sale_price",
            "median_ppsf",
            "median_sqft",
            "median_lot_size",
            "median_beds",
            "median_baths",
            "median_year_built",
            "median_days_on_market",
            "median_sale_to_list_ratio",
            "avg_confidence_score",
            "missing_data_rate",
            "outlier_count",
        ])

    grouped_rows: list[dict[str, Any]] = []
    for town, group in records.groupby("town", dropna=False):
        sold = group[group["record_type"] == "sold"]
        active = group[group["record_type"] == "active"]
        grouped_rows.append(
            {
                "town": town,
                "listing_count": int(len(active)),
                "sold_count": int(len(sold)),
                "median_list_price": _median(active["list_price"]),
                "median_sale_price": _median(sold["sale_price"]),
                "median_ppsf": _median(group["ppsf"]),
                "median_sqft": _median(group["sqft"]),
                "median_lot_size": _median(group["lot_size"]),
                "median_beds": _median(group["beds"]),
                "median_baths": _median(group["baths"]),
                "median_year_built": _median(group["year_built"]),
                "median_days_on_market": _median(group["days_on_market"]),
                "median_sale_to_list_ratio": _median(sold["sale_to_list_ratio"]),
                "avg_confidence_score": _mean(group["confidence_score"]),
                "missing_data_rate": _missing_data_rate(group),
                "outlier_count": _outlier_count(group["ppsf"]),
            }
        )
    return pd.DataFrame(grouped_rows).sort_values(["median_sale_price", "median_list_price"], ascending=[False, False], na_position="last").reset_index(drop=True)


def build_cross_town_comparison_table(town_summary: pd.DataFrame, records: pd.DataFrame) -> pd.DataFrame:
    if town_summary.empty:
        return pd.DataFrame(columns=[
            "town",
            "median_sale_price",
            "median_list_price",
            "median_ppsf",
            "median_sqft",
            "median_lot_size",
            "median_dom",
            "listing_count",
            "sold_count",
            "ppsf_vs_region",
            "price_vs_region",
            "sqft_vs_region",
        ])

    region_sale_price = _median(records.loc[records["record_type"] == "sold", "sale_price"])
    region_list_price = _median(records.loc[records["record_type"] == "active", "list_price"])
    region_ppsf = _median(records["ppsf"])
    region_sqft = _median(records["sqft"])

    frame = town_summary[[
        "town",
        "median_sale_price",
        "median_list_price",
        "median_ppsf",
        "median_sqft",
        "median_lot_size",
        "median_days_on_market",
        "listing_count",
        "sold_count",
    ]].copy()
    frame = frame.rename(columns={"median_days_on_market": "median_dom"})
    frame["ppsf_vs_region"] = frame["median_ppsf"].apply(lambda value: _ratio_to_baseline(value, region_ppsf))
    frame["price_vs_region"] = frame.apply(
        lambda row: _ratio_to_baseline(
            row["median_sale_price"] if pd.notna(row["median_sale_price"]) else row["median_list_price"],
            region_sale_price if pd.notna(region_sale_price) else region_list_price,
        ),
        axis=1,
    )
    frame["sqft_vs_region"] = frame["median_sqft"].apply(lambda value: _ratio_to_baseline(value, region_sqft))
    return frame.sort_values("median_sale_price", ascending=False, na_position="last").reset_index(drop=True)


def build_town_premium_index(town_summary: pd.DataFrame, records: pd.DataFrame) -> pd.DataFrame:
    if town_summary.empty:
        return pd.DataFrame(columns=[
            "town",
            "town_price_index",
            "town_ppsf_index",
            "town_lot_index",
            "town_liquidity_index",
        ])

    region_price = _median(
        records.loc[records["record_type"] == "sold", "sale_price"]
        if not records.loc[records["record_type"] == "sold"].empty
        else records["price"]
    )
    region_ppsf = _median(records["ppsf"])
    region_lot = _median(records["lot_size"])
    region_dom = _median(records["days_on_market"])
    region_ratio = _median(records.loc[records["record_type"] == "sold", "sale_to_list_ratio"])

    rows: list[dict[str, Any]] = []
    for _, row in town_summary.iterrows():
        price_value = row["median_sale_price"] if pd.notna(row["median_sale_price"]) else row["median_list_price"]
        dom_component = _inverse_ratio_to_baseline(row["median_days_on_market"], region_dom)
        ratio_component = _ratio_to_baseline(row["median_sale_to_list_ratio"], region_ratio)
        liquidity_components = [value for value in [dom_component, ratio_component] if value is not None]
        rows.append(
            {
                "town": row["town"],
                # Price / PPSF / lot indexes use region median = 100.
                "town_price_index": _index_to_baseline(price_value, region_price),
                "town_ppsf_index": _index_to_baseline(row["median_ppsf"], region_ppsf),
                "town_lot_index": _index_to_baseline(row["median_lot_size"], region_lot),
                # Liquidity rewards lower DOM and stronger sale-to-list ratio where available.
                "town_liquidity_index": round(sum(liquidity_components) / len(liquidity_components), 1) if liquidity_components else None,
            }
        )
    return pd.DataFrame(rows).sort_values("town_price_index", ascending=False, na_position="last").reset_index(drop=True)


def build_feature_sensitivity_by_town(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return pd.DataFrame(columns=["town", "feature_name", "feature_group", "record_count", "median_price", "median_ppsf", "median_sqft"])

    expanded_rows: list[dict[str, Any]] = []
    for _, row in records.iterrows():
        for feature_name, feature_group in _feature_groups_for_row(row):
            expanded_rows.append(
                {
                    "town": row["town"],
                    "feature_name": feature_name,
                    "feature_group": feature_group,
                    "price": row["price"],
                    "ppsf": row["ppsf"],
                    "sqft": row["sqft"],
                }
            )
    if not expanded_rows:
        return pd.DataFrame(columns=["town", "feature_name", "feature_group", "record_count", "median_price", "median_ppsf", "median_sqft"])

    frame = pd.DataFrame(expanded_rows)
    output_rows: list[dict[str, Any]] = []
    for (town, feature_name, feature_group), group in frame.groupby(["town", "feature_name", "feature_group"], dropna=False):
        output_rows.append(
            {
                "town": town,
                "feature_name": feature_name,
                "feature_group": feature_group,
                "record_count": int(len(group)),
                "median_price": _median(group["price"]),
                "median_ppsf": _median(group["ppsf"]),
                "median_sqft": _median(group["sqft"]),
            }
        )
    return pd.DataFrame(output_rows).sort_values(["town", "feature_name", "record_count"], ascending=[True, True, False]).reset_index(drop=True)


def build_town_qa_flags(town_summary: pd.DataFrame, records: pd.DataFrame) -> pd.DataFrame:
    if town_summary.empty:
        return pd.DataFrame(columns=[
            "town",
            "sample_size",
            "sqft_coverage_rate",
            "lot_size_coverage_rate",
            "year_built_coverage_rate",
            "ppsf_std_dev",
            "low_sample_flag",
            "high_missingness_flag",
            "high_dispersion_flag",
            "outlier_heavy_flag",
            "low_confidence_flag",
        ])

    rows: list[dict[str, Any]] = []
    for _, summary in town_summary.iterrows():
        town = summary["town"]
        group = records[records["town"] == town]
        sample_size = int(len(group))
        ppsf_std = _std(group["ppsf"])
        ppsf_median = _median(group["ppsf"])
        outlier_share = (summary["outlier_count"] / sample_size) if sample_size else None
        avg_confidence = summary["avg_confidence_score"]
        rows.append(
            {
                "town": town,
                "sample_size": sample_size,
                "sqft_coverage_rate": _coverage_rate(group["sqft"]),
                "lot_size_coverage_rate": _coverage_rate(group["lot_size"]),
                "year_built_coverage_rate": _coverage_rate(group["year_built"]),
                "ppsf_std_dev": ppsf_std,
                "low_sample_flag": sample_size < LOW_SAMPLE_THRESHOLD,
                "high_missingness_flag": bool(summary["missing_data_rate"] is not None and summary["missing_data_rate"] > HIGH_MISSINGNESS_THRESHOLD),
                "high_dispersion_flag": bool(
                    ppsf_std is not None and ppsf_median not in (None, 0) and (ppsf_std / ppsf_median) > HIGH_DISPERSION_THRESHOLD
                ),
                "outlier_heavy_flag": bool(outlier_share is not None and outlier_share > OUTLIER_HEAVY_THRESHOLD),
                "low_confidence_flag": bool(avg_confidence is not None and avg_confidence < LOW_CONFIDENCE_THRESHOLD),
            }
        )
    return pd.DataFrame(rows).sort_values(["low_sample_flag", "high_missingness_flag", "town"], ascending=[False, False, True]).reset_index(drop=True)


def build_town_calibration_table(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return pd.DataFrame(columns=[
            "town",
            "record_count",
            "avg_abs_region_price_residual",
            "avg_abs_town_price_residual",
            "avg_abs_region_ppsf_residual",
            "avg_abs_town_ppsf_residual",
            "price_residual_improvement",
            "ppsf_residual_improvement",
            "calibration_note",
        ])

    region_price = _median(records["price"])
    region_ppsf = _median(records["ppsf"])
    town_price_map = records.groupby("town", dropna=False)["price"].median().to_dict()
    town_ppsf_map = records.groupby("town", dropna=False)["ppsf"].median().to_dict()

    working = records.copy()
    working["region_price_residual"] = working["price"].apply(lambda value: _abs_ratio_delta(value, region_price))
    working["town_price_residual"] = working.apply(lambda row: _abs_ratio_delta(row["price"], town_price_map.get(row["town"])), axis=1)
    working["region_ppsf_residual"] = working["ppsf"].apply(lambda value: _abs_ratio_delta(value, region_ppsf))
    working["town_ppsf_residual"] = working.apply(lambda row: _abs_ratio_delta(row["ppsf"], town_ppsf_map.get(row["town"])), axis=1)

    rows: list[dict[str, Any]] = []
    for town, group in working.groupby("town", dropna=False):
        avg_abs_region_price = _mean(group["region_price_residual"])
        avg_abs_town_price = _mean(group["town_price_residual"])
        avg_abs_region_ppsf = _mean(group["region_ppsf_residual"])
        avg_abs_town_ppsf = _mean(group["town_ppsf_residual"])
        price_improvement = _residual_improvement(avg_abs_region_price, avg_abs_town_price)
        ppsf_improvement = _residual_improvement(avg_abs_region_ppsf, avg_abs_town_ppsf)
        rows.append(
            {
                "town": town,
                "record_count": int(len(group)),
                "avg_abs_region_price_residual": avg_abs_region_price,
                "avg_abs_town_price_residual": avg_abs_town_price,
                "avg_abs_region_ppsf_residual": avg_abs_region_ppsf,
                "avg_abs_town_ppsf_residual": avg_abs_town_ppsf,
                "price_residual_improvement": price_improvement,
                "ppsf_residual_improvement": ppsf_improvement,
                "calibration_note": _calibration_note(price_improvement, ppsf_improvement),
            }
        )
    return pd.DataFrame(rows).sort_values("ppsf_residual_improvement", ascending=False, na_position="last").reset_index(drop=True)


def _load_sales_rows(path: str | Path) -> list[dict[str, Any]]:
    dataset = JsonComparableSalesStore(path).load()
    return [sale.model_dump(exclude_none=True) for sale in dataset.sales]


def _load_active_rows(path: str | Path) -> list[dict[str, Any]]:
    dataset = JsonActiveListingStore(path).load()
    return [listing.model_dump(exclude_none=True) for listing in dataset.listings]


def _normalize_sale_row(row: dict[str, Any]) -> dict[str, Any]:
    sale_price = _num(row.get("sale_price"))
    list_price = _num(row.get("list_price"))
    sqft = _num(row.get("sqft"))
    return {
        "town": row.get("town"),
        "record_type": "sold",
        "address": row.get("address"),
        "price": sale_price,
        "list_price": list_price,
        "sale_price": sale_price,
        "sqft": sqft,
        "ppsf": (sale_price / sqft) if sale_price and sqft else None,
        "lot_size": _num(row.get("lot_size")),
        "beds": _num(row.get("beds")),
        "baths": _num(row.get("baths")),
        "year_built": _num(row.get("year_built")),
        "days_on_market": _num(row.get("days_on_market")),
        "sale_to_list_ratio": (sale_price / list_price) if sale_price and list_price else None,
        "confidence_score": _num(row.get("confidence_score")),
        "condition_profile": row.get("condition_profile"),
        "garage_spaces": _num(row.get("garage_spaces")),
        "has_pool": row.get("has_pool"),
        "distance_to_subject_miles": _num(row.get("distance_to_subject_miles")),
        "adu_type": row.get("adu_type"),
        "has_back_house": row.get("has_back_house"),
        "location_tags": row.get("location_tags") or [],
        "micro_location_notes": row.get("micro_location_notes") or [],
    }


def _normalize_active_row(row: dict[str, Any]) -> dict[str, Any]:
    list_price = _num(row.get("list_price"))
    sqft = _num(row.get("sqft"))
    return {
        "town": row.get("town"),
        "record_type": "active",
        "address": row.get("address"),
        "price": list_price,
        "list_price": list_price,
        "sale_price": None,
        "sqft": sqft,
        "ppsf": (list_price / sqft) if list_price and sqft else None,
        "lot_size": _num(row.get("lot_size")),
        "beds": _num(row.get("beds")),
        "baths": _num(row.get("baths")),
        "year_built": _num(row.get("year_built")),
        "days_on_market": _num(row.get("days_on_market")),
        "sale_to_list_ratio": None,
        "confidence_score": _num(row.get("confidence_score")),
        "condition_profile": row.get("condition_profile"),
        "garage_spaces": _num(row.get("garage_spaces")),
        "has_pool": row.get("has_pool"),
        "distance_to_subject_miles": _num(row.get("distance_to_subject_miles")),
        "adu_type": row.get("adu_type"),
        "has_back_house": row.get("has_back_house"),
        "location_tags": row.get("location_tags") or [],
        "micro_location_notes": row.get("micro_location_notes") or [],
    }


def _feature_groups_for_row(row: pd.Series) -> list[tuple[str, str]]:
    groups: list[tuple[str, str]] = []
    garage_spaces = row.get("garage_spaces")
    if pd.notna(garage_spaces):
        groups.append(("garage", "garage" if float(garage_spaces) > 0 else "no_garage"))

    condition = row.get("condition_profile")
    if isinstance(condition, str) and condition:
        groups.append(("condition_profile", condition))

    lot_size = row.get("lot_size")
    if pd.notna(lot_size):
        groups.append(("lot_size_bucket", _lot_size_bucket(float(lot_size))))

    distance = row.get("distance_to_subject_miles")
    if pd.notna(distance):
        groups.append(("beach_distance_bucket", _distance_bucket(float(distance))))

    adu_type = row.get("adu_type")
    has_back_house = row.get("has_back_house")
    if isinstance(adu_type, str) and adu_type:
        groups.append(("income_potential", "adu_or_income_unit"))
    elif bool(has_back_house):
        groups.append(("income_potential", "back_house"))

    water_group = _water_proximity_group(row.get("location_tags"), row.get("micro_location_notes"))
    if water_group is not None:
        groups.append(("water_proximity", water_group))

    has_pool = row.get("has_pool")
    if has_pool is not None and not pd.isna(has_pool):
        groups.append(("pool", "pool" if bool(has_pool) else "no_pool"))
    return groups


def _water_proximity_group(location_tags: Any, notes: Any) -> str | None:
    text_parts: list[str] = []
    if isinstance(location_tags, list):
        text_parts.extend(str(item).lower() for item in location_tags)
    if isinstance(notes, list):
        text_parts.extend(str(item).lower() for item in notes)
    combined = " ".join(text_parts)
    if not combined:
        return None
    if any(keyword in combined for keyword in ("ocean", "beach", "water", "lake", "river")):
        return "water_adjacent_or_proximate"
    return None


def _lot_size_bucket(value: float) -> str:
    if value < 0.10:
        return "<0.10 ac"
    if value < 0.20:
        return "0.10-0.19 ac"
    if value < 0.50:
        return "0.20-0.49 ac"
    return "0.50+ ac"


def _distance_bucket(value: float) -> str:
    if value < 0.5:
        return "<0.5 mi"
    if value < 1.0:
        return "0.5-0.99 mi"
    if value < 2.0:
        return "1.0-1.99 mi"
    return "2.0+ mi"


def _median(series: Any) -> float | None:
    s = pd.Series(series).dropna()
    if s.empty:
        return None
    return round(float(s.median()), 2)


def _mean(series: Any) -> float | None:
    s = pd.Series(series).dropna()
    if s.empty:
        return None
    return round(float(s.mean()), 3)


def _std(series: Any) -> float | None:
    s = pd.Series(series).dropna()
    if len(s) < 2:
        return None
    return round(float(s.std()), 2)


def _coverage_rate(series: Any) -> float:
    s = pd.Series(series)
    if len(s) == 0:
        return 0.0
    return round(float(s.notna().sum() / len(s)), 3)


def _missing_data_rate(group: pd.DataFrame) -> float:
    if group.empty:
        return 0.0
    total_cells = len(group) * len(CORE_MISSINGNESS_FIELDS)
    missing = 0
    for field in CORE_MISSINGNESS_FIELDS:
        missing += int(group[field].isna().sum())
    return round(missing / total_cells, 3) if total_cells else 0.0


def _outlier_count(series: Any) -> int:
    s = pd.Series(series).dropna()
    if len(s) < 4:
        return 0
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return 0
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return int(((s < lower) | (s > upper)).sum())


def _ratio_to_baseline(value: Any, baseline: Any) -> float | None:
    if value in (None, 0) or baseline in (None, 0) or pd.isna(value) or pd.isna(baseline):
        return None
    return round(float(value) / float(baseline), 3)


def _index_to_baseline(value: Any, baseline: Any) -> float | None:
    ratio = _ratio_to_baseline(value, baseline)
    return round(ratio * 100, 1) if ratio is not None else None


def _inverse_ratio_to_baseline(value: Any, baseline: Any) -> float | None:
    if value in (None, 0) or baseline in (None, 0) or pd.isna(value) or pd.isna(baseline):
        return None
    return round((float(baseline) / float(value)) * 100, 1)


def _num(value: Any) -> float | None:
    if value in (None, "", "N/A", "n/a", "--", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_columns() -> list[str]:
    return [
        "town",
        "record_type",
        "address",
        "price",
        "list_price",
        "sale_price",
        "sqft",
        "ppsf",
        "lot_size",
        "beds",
        "baths",
        "year_built",
        "days_on_market",
        "sale_to_list_ratio",
        "confidence_score",
        "condition_profile",
        "garage_spaces",
        "has_pool",
        "distance_to_subject_miles",
        "adu_type",
        "has_back_house",
        "location_tags",
        "micro_location_notes",
    ]


def _town_qa_flag_names(qa_item: Any) -> list[str]:
    if qa_item is None:
        return []
    mapping = {
        "low_sample_flag": "low_sample",
        "high_missingness_flag": "high_missingness",
        "high_dispersion_flag": "high_dispersion",
        "outlier_heavy_flag": "outlier_heavy",
        "low_confidence_flag": "low_confidence",
    }
    return [label for key, label in mapping.items() if bool(qa_item.get(key))]


def _town_context_confidence(summary_item: Any, qa_item: Any) -> float:
    base = 0.84
    if qa_item is None:
        return 0.45

    if bool(qa_item.get("low_sample_flag")):
        base -= 0.16
    if bool(qa_item.get("high_missingness_flag")):
        base -= 0.12
    if bool(qa_item.get("high_dispersion_flag")):
        base -= 0.10
    if bool(qa_item.get("outlier_heavy_flag")):
        base -= 0.08
    if bool(qa_item.get("low_confidence_flag")):
        base -= 0.06

    sqft_cov = float(qa_item.get("sqft_coverage_rate") or 0.0)
    lot_cov = float(qa_item.get("lot_size_coverage_rate") or 0.0)
    year_cov = float(qa_item.get("year_built_coverage_rate") or 0.0)
    coverage_values = [value for value in (sqft_cov, lot_cov, year_cov) if value > 0]
    coverage_avg = (sum(coverage_values) / len(coverage_values)) if coverage_values else 0.0
    if coverage_avg < 0.55:
        base -= 0.10
    elif coverage_avg < 0.75:
        base -= 0.05

    sold_count = int(summary_item.get("sold_count") or 0)
    if sold_count < 3:
        base -= 0.08
    elif sold_count < 6:
        base -= 0.04

    return round(max(0.25, min(base, 0.92)), 2)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _abs_ratio_delta(value: Any, baseline: Any) -> float | None:
    ratio = _ratio_to_baseline(value, baseline)
    if ratio is None:
        return None
    return round(abs(ratio - 1.0), 3)


def _residual_improvement(region_residual: float | None, town_residual: float | None) -> float | None:
    if region_residual is None or town_residual is None:
        return None
    return round(region_residual - town_residual, 3)


def _calibration_note(price_improvement: float | None, ppsf_improvement: float | None) -> str:
    if ppsf_improvement is not None and ppsf_improvement >= 0.08:
        return "Town context materially improves PPSF fit."
    if price_improvement is not None and price_improvement >= 0.08:
        return "Town context materially improves price fit."
    if (ppsf_improvement is not None and ppsf_improvement < 0) or (price_improvement is not None and price_improvement < 0):
        return "Town baseline still fits poorly; review sample quality and outliers."
    return "Town context is directionally useful, but only modestly improves fit."

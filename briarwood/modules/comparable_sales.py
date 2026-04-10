from __future__ import annotations

from pathlib import Path
from math import sqrt

from briarwood.agents.comparable_sales import (
    ComparableSalesAgent,
    ComparableValueRange,
    ComparableSalesOutput,
    ComparableSalesRequest,
    FileBackedComparableSalesProvider,
)
from briarwood.evidence import build_section_evidence
from briarwood.modules.market_value_history import MarketValueHistoryModule, get_market_value_history_payload
from briarwood.schemas import ModuleResult, PropertyInput


class ComparableSalesModule:
    """Build a property-level value anchor from nearby sale comps."""

    name = "comparable_sales"

    def __init__(
        self,
        *,
        agent: ComparableSalesAgent | None = None,
        market_value_history_module: MarketValueHistoryModule | None = None,
    ) -> None:
        self.agent = agent or ComparableSalesAgent(
            FileBackedComparableSalesProvider(
                Path(__file__).resolve().parents[2] / "data" / "comps" / "sales_comps.json"
            )
        )
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        history_result = self.market_value_history_module.run(property_input)
        history = get_market_value_history_payload(history_result)
        output = self.agent.run(
            ComparableSalesRequest(
                town=property_input.town,
                state=property_input.state,
                property_type=property_input.property_type,
                architectural_style=property_input.architectural_style,
                condition_profile=property_input.condition_profile,
                capex_lane=property_input.capex_lane,
                beds=property_input.beds,
                baths=property_input.baths,
                sqft=property_input.sqft,
                lot_size=property_input.lot_size,
                year_built=property_input.year_built,
                stories=property_input.stories,
                garage_spaces=property_input.garage_spaces,
                listing_description=property_input.listing_description,
                market_value_today=history.current_value,
                market_history_points=[point.model_dump() for point in history.points],
                manual_sales=list(property_input.manual_comp_inputs),
                manual_comp_only=False,
            )
        )
        output = _enrich_comp_intelligence(output, property_input)
        return ModuleResult(
            module_name=self.name,
            metrics={
                "comparable_value": output.comparable_value,
                "comp_count": output.comp_count,
                "comp_confidence": round(output.confidence, 2),
                "comp_confidence_score": round(float(output.comp_confidence_score or output.confidence), 2),
                "direct_value_midpoint": output.direct_value_range.midpoint if output.direct_value_range is not None else None,
                "income_adjusted_value_midpoint": output.income_adjusted_value_range.midpoint if output.income_adjusted_value_range is not None else None,
                "location_adjustment_midpoint": output.location_adjustment_range.midpoint if output.location_adjustment_range is not None else None,
                "lot_adjustment_midpoint": output.lot_adjustment_range.midpoint if output.lot_adjustment_range is not None else None,
                "blended_value_midpoint": output.blended_value_range.midpoint if output.blended_value_range is not None else None,
            },
            score=(output.comparable_value is not None) * min(output.confidence * 100, 100.0),
            confidence=output.confidence,
            summary=output.summary,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["comp_support", "sqft", "lot_size", "listing_history"],
                notes=["Comp support is only as strong as the current comp database and its verification tier."],
            ),
        )


def get_comparable_sales_payload(result: ModuleResult) -> ComparableSalesOutput:
    if not isinstance(result.payload, ComparableSalesOutput):
        raise TypeError("comparable_sales module payload is not a ComparableSalesOutput")
    return result.payload


def _enrich_comp_intelligence(
    output: ComparableSalesOutput,
    property_input: PropertyInput,
) -> ComparableSalesOutput:
    comps = list(output.comps_used or [])
    if not comps:
        return output

    scored_comps = [_score_comp(comp, property_input) for comp in comps]
    direct_bucket = [comp for comp in scored_comps if comp.segmentation_bucket == "direct_comps"]
    income_bucket = [comp for comp in scored_comps if comp.segmentation_bucket == "income_comps"]
    location_bucket = [comp for comp in scored_comps if comp.location_tags]
    lot_bucket = [comp for comp in scored_comps if comp.lot_size is not None and property_input.lot_size is not None]

    direct_value_range = _bucket_range(direct_bucket, "Direct comps anchor value around the same unit type and subject-like layout.")
    income_adjusted_value_range = _bucket_range(
        income_bucket,
        "Income comps capture multi-unit, ADU, or back-house style value support.",
    )
    location_adjustment_range = _location_adjustment_range(scored_comps, property_input)
    lot_adjustment_range = _lot_adjustment_range(lot_bucket, property_input)
    blended_value_range = _blend_ranges(
        [
            (direct_value_range, 0.45),
            (income_adjusted_value_range, 0.20),
            (location_adjustment_range, 0.20),
            (lot_adjustment_range, 0.15),
        ],
        fallback=output.comparable_value,
    )
    comp_confidence_score = round(
        min(
            0.95,
            (
                sum(float(comp.weighted_score or 0.0) for comp in scored_comps) / max(len(scored_comps), 1)
            ) * 0.7
            + output.confidence * 0.3,
        ),
        2,
    )

    return output.model_copy(
        update={
            "comps_used": scored_comps,
            "direct_value_range": direct_value_range,
            "income_adjusted_value_range": income_adjusted_value_range,
            "location_adjustment_range": location_adjustment_range,
            "lot_adjustment_range": lot_adjustment_range,
            "blended_value_range": blended_value_range,
            "comp_confidence_score": comp_confidence_score,
        }
    )


def _score_comp(comp, property_input: PropertyInput):
    proximity_score = _proximity_score(getattr(comp, "distance_to_subject_miles", None))
    recency_score = _recency_score(getattr(comp, "sale_age_days", None))
    similarity_score = float(getattr(comp, "similarity_score", 0.0) or 0.0)
    data_quality_score = _data_quality_score(comp)
    weighted_score = round(
        proximity_score * 0.30
        + recency_score * 0.25
        + similarity_score * 0.30
        + data_quality_score * 0.15,
        3,
    )
    return comp.model_copy(
        update={
            "segmentation_bucket": _segmentation_bucket(comp, property_input),
            "proximity_score": round(proximity_score, 3),
            "recency_score": round(recency_score, 3),
            "data_quality_score": round(data_quality_score, 3),
            "weighted_score": weighted_score,
        }
    )


def _segmentation_bucket(comp, property_input: PropertyInput) -> str:
    subject_type = (property_input.property_type or "").lower()
    comp_type = (getattr(comp, "property_type", None) or "").lower()
    subject_is_income = (
        subject_type in {"duplex", "triplex", "fourplex", "multi_family"}
        or bool(property_input.has_back_house)
        or bool(property_input.adu_type)
        or len(property_input.unit_rents or []) >= 2
    )
    comp_is_income = comp_type in {"duplex", "triplex", "fourplex", "multi_family"}
    sqft = getattr(comp, "sqft", None)
    beds = getattr(comp, "bedrooms", None)
    baths = getattr(comp, "bathrooms", None)
    sqft_close = bool(property_input.sqft and sqft and abs(property_input.sqft - sqft) / max(property_input.sqft, 1) <= 0.18)
    beds_close = property_input.beds is not None and beds is not None and abs(property_input.beds - beds) <= 1
    baths_close = property_input.baths is not None and baths is not None and abs(property_input.baths - baths) <= 1.0
    if (subject_is_income or comp_is_income) and (comp_is_income or len(getattr(comp, "location_tags", []) or []) > 0):
        return "income_comps"
    if sqft_close and beds_close and baths_close:
        return "direct_comps"
    return "direct_comps" if not comp_is_income else "income_comps"


def _proximity_score(distance_miles: float | None) -> float:
    if distance_miles is None:
        return 0.55
    if distance_miles <= 0.25:
        return 0.95
    if distance_miles <= 0.5:
        return 0.88
    if distance_miles <= 1.0:
        return 0.78
    if distance_miles <= 2.0:
        return 0.64
    return 0.42


def _recency_score(sale_age_days: int | None) -> float:
    if sale_age_days is None:
        return 0.5
    if sale_age_days <= 90:
        return 0.95
    if sale_age_days <= 180:
        return 0.88
    if sale_age_days <= 365:
        return 0.78
    if sale_age_days <= 730:
        return 0.62
    return 0.4


def _data_quality_score(comp) -> float:
    present = 0
    total = 6
    for value in (
        getattr(comp, "bedrooms", None),
        getattr(comp, "bathrooms", None),
        getattr(comp, "sqft", None),
        getattr(comp, "lot_size", None),
        getattr(comp, "distance_to_subject_miles", None),
        getattr(comp, "sale_verification_status", None),
    ):
        if value not in (None, "", []):
            present += 1
    base = present / total
    verification = str(getattr(comp, "sale_verification_status", "") or "").lower()
    if verification in {"public_record_verified", "mls_verified"}:
        base += 0.08
    elif verification in {"questioned", "unverified"}:
        base -= 0.10
    return max(0.2, min(base, 1.0))


def _bucket_range(comps: list, explanation: str) -> ComparableValueRange | None:
    if not comps:
        return None
    weighted_values = [
        float(comp.adjusted_price) * max(float(comp.weighted_score or 0.0), 0.1)
        for comp in comps
    ]
    weights = [max(float(comp.weighted_score or 0.0), 0.1) for comp in comps]
    midpoint = sum(weighted_values) / sum(weights)
    prices = sorted(float(comp.adjusted_price) for comp in comps)
    low = prices[0]
    high = prices[-1]
    confidence = sum(weights) / len(weights)
    return ComparableValueRange(
        low=round(low, 2),
        midpoint=round(midpoint, 2),
        high=round(high, 2),
        comp_count=len(comps),
        confidence=round(min(confidence, 0.95), 2),
        explanation=explanation,
    )


def _location_adjustment_range(comps: list, property_input: PropertyInput) -> ComparableValueRange | None:
    subject_beach = _nearest_landmark_distance(property_input.latitude, property_input.longitude, property_input.landmark_points.get("beach", []))
    if subject_beach is None:
        return None
    adjusted: list[float] = []
    weights: list[float] = []
    for comp in comps:
        comp_beach = _nearest_landmark_distance(
            getattr(comp, "latitude", None),
            getattr(comp, "longitude", None),
            property_input.landmark_points.get("beach", []),
        )
        if comp_beach is None:
            continue
        diff = comp_beach - subject_beach
        adj_pct = max(-0.08, min(diff * 0.015, 0.08))
        adjusted.append(float(comp.adjusted_price) * (1 + adj_pct))
        weights.append(max(float(comp.weighted_score or 0.0), 0.1))
    if not adjusted:
        return None
    midpoint = sum(value * weight for value, weight in zip(adjusted, weights)) / sum(weights)
    return ComparableValueRange(
        low=round(min(adjusted), 2),
        midpoint=round(midpoint, 2),
        high=round(max(adjusted), 2),
        comp_count=len(adjusted),
        confidence=round(min(sum(weights) / len(weights), 0.92), 2),
        explanation="Beach-distance tiers adjust comp support when subject and comps benchmark to different shoreline proximity bands.",
    )


def _lot_adjustment_range(comps: list, property_input: PropertyInput) -> ComparableValueRange | None:
    if property_input.lot_size in (None, 0):
        return None
    adjusted: list[float] = []
    weights: list[float] = []
    for comp in comps:
        comp_lot = getattr(comp, "lot_size", None)
        if comp_lot in (None, 0):
            continue
        ratio = float(property_input.lot_size) / float(comp_lot)
        adj_pct = max(-0.10, min((ratio - 1.0) * 0.12, 0.12))
        adjusted.append(float(comp.adjusted_price) * (1 + adj_pct))
        weights.append(max(float(comp.weighted_score or 0.0), 0.1))
    if not adjusted:
        return None
    midpoint = sum(value * weight for value, weight in zip(adjusted, weights)) / sum(weights)
    return ComparableValueRange(
        low=round(min(adjusted), 2),
        midpoint=round(midpoint, 2),
        high=round(max(adjusted), 2),
        comp_count=len(adjusted),
        confidence=round(min(sum(weights) / len(weights), 0.9), 2),
        explanation="Lot-size and expandability adjust value support when the subject carries more or less land optionality than the core comp set.",
    )


def _blend_ranges(ranges: list[tuple[ComparableValueRange | None, float]], *, fallback: float | None) -> ComparableValueRange | None:
    active = [(rng, weight) for rng, weight in ranges if rng is not None and rng.midpoint is not None]
    if not active:
        if fallback is None:
            return None
        return ComparableValueRange(low=round(fallback, 2), midpoint=round(fallback, 2), high=round(fallback, 2), comp_count=0, confidence=0.0, explanation="Fallback to the comparable-sales midpoint.")
    total_weight = sum(weight for _, weight in active)
    midpoint = sum(float(rng.midpoint) * weight for rng, weight in active) / total_weight
    low = sum(float(rng.low or rng.midpoint or 0.0) * weight for rng, weight in active) / total_weight
    high = sum(float(rng.high or rng.midpoint or 0.0) * weight for rng, weight in active) / total_weight
    confidence = sum(float(rng.confidence) * weight for rng, weight in active) / total_weight
    comp_count = max(int(rng.comp_count) for rng, _ in active)
    return ComparableValueRange(
        low=round(low, 2),
        midpoint=round(midpoint, 2),
        high=round(high, 2),
        comp_count=comp_count,
        confidence=round(min(confidence, 0.95), 2),
        explanation="Blended anchor combines direct comps with income, location, and lot adjustments as explanatory ranges rather than a single opaque fair-value point.",
    )


def _nearest_landmark_distance(lat: float | None, lon: float | None, landmarks: list[dict]) -> float | None:
    if lat is None or lon is None or not landmarks:
        return None
    distances: list[float] = []
    for point in landmarks:
        point_lat = point.get("latitude")
        point_lon = point.get("longitude")
        if point_lat is None or point_lon is None:
            continue
        distances.append(_distance_miles(float(lat), float(lon), float(point_lat), float(point_lon)))
    return min(distances) if distances else None


def _distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat_scale = 69.0
    lon_scale = 53.0
    return sqrt(((lat1 - lat2) * lat_scale) ** 2 + ((lon1 - lon2) * lon_scale) ** 2)

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from statistics import median

from briarwood.agents.comparable_sales import ComparableSale, FileBackedComparableSalesProvider
from briarwood.evidence import build_section_evidence
from briarwood.schemas import (
    LocationBucketBenchmark,
    LocationCategoryIntelligence,
    LocationIntelligenceOutput,
    ModuleResult,
    PropertyInput,
)


BEACH_BUCKETS = [
    (0.25, "0-0.25"),
    (0.5, "0.25-0.5"),
    (1.0, "0.5-1.0"),
    (2.0, "1.0-2.0"),
    (float("inf"), "2.0+"),
]

DOWNTOWN_BUCKETS = [
    (0.5, "0-0.5"),
    (1.0, "0.5-1.0"),
    (2.0, "1.0-2.0"),
    (float("inf"), "2.0+"),
]

SKI_BUCKETS = [
    (1.0, "0-1"),
    (3.0, "1-3"),
    (5.0, "3-5"),
    (10.0, "5-10"),
    (float("inf"), "10+"),
]

DEFAULT_BUCKETS = [
    (0.5, "0-0.5"),
    (1.0, "0.5-1.0"),
    (2.0, "1.0-2.0"),
    (float("inf"), "2.0+"),
]

CATEGORY_ORDER = ["beach", "downtown", "park", "train", "ski"]
PREMIUM_ZONE_FLAGS = ("in_beach_premium_zone", "in_downtown_zone")


class LocationIntelligenceModule:
    """Benchmark location quality against geo peer buckets using nearby landmark distance."""

    name = "location_intelligence"

    def __init__(self, *, provider: FileBackedComparableSalesProvider | None = None) -> None:
        self.provider = provider or FileBackedComparableSalesProvider(
            Path(__file__).resolve().parents[2] / "data" / "comps" / "sales_comps.json"
        )

    def run(self, property_input: PropertyInput) -> ModuleResult:
        subject_ppsf = _safe_ppsf(property_input.purchase_price, property_input.sqft)
        raw_sales = self._load_sales(property_input)
        sales_with_geo = [sale for sale in raw_sales if _sale_has_geo(sale)]

        confidence_notes: list[str] = []
        missing_inputs: list[str] = []

        if property_input.latitude is None or property_input.longitude is None:
            missing_inputs.append("subject_coordinates")
            confidence_notes.append(
                "Subject coordinates were missing, so Briarwood could not benchmark landmark proximity against town peers."
            )

        available_categories = [
            category
            for category in CATEGORY_ORDER
            if property_input.landmark_points.get(category)
        ]
        if not available_categories:
            missing_inputs.append("landmark_points")
            confidence_notes.append(
                "No landmark point sets were provided, so location scoring relies only on flood and zone-style proxy signals."
            )

        if raw_sales and not sales_with_geo:
            missing_inputs.append("geo_comp_coordinates")
            confidence_notes.append(
                "Town comps were available, but none included coordinates, so bucket benchmarking could not be formed."
            )
        elif not raw_sales:
            missing_inputs.append("geo_peer_comps")
            confidence_notes.append(
                "No same-town geo peer comps were available for location benchmarking."
            )

        category_results: list[LocationCategoryIntelligence] = []
        proximity_components: list[float] = []
        supply_components: list[float] = []
        rarity_components: list[float] = []
        lifestyle_components: list[float] = []

        if property_input.latitude is not None and property_input.longitude is not None:
            for category in available_categories:
                result = self._build_category_result(
                    category=category,
                    subject_lat=property_input.latitude,
                    subject_lon=property_input.longitude,
                    subject_ppsf=subject_ppsf,
                    sales=sales_with_geo,
                    landmarks=property_input.landmark_points.get(category, []),
                )
                if result is None:
                    continue
                category_results.append(result)

                subject_distance = result.subject_distance_miles
                peer_bucket = result.peer_bucket_stats
                if subject_distance is not None:
                    comp_distances = [
                        _distance_to_points(sale.latitude, sale.longitude, property_input.landmark_points.get(category, []))
                        for sale in sales_with_geo
                    ]
                    comp_distances = [distance for distance in comp_distances if distance is not None]
                    if comp_distances:
                        proximity_components.append(_percentile_benefit(subject_distance, comp_distances))
                        lifestyle_components.append(_distance_benefit(subject_distance, category))
                if peer_bucket and result.town_comp_count > 0:
                    bucket_share = peer_bucket.comp_count / result.town_comp_count
                    supply_components.append(_clamp((1.0 - bucket_share) * 100.0))
                    premium = result.location_premium_pct or 0.0
                    rarity_score = _clamp((1.0 - bucket_share) * 65.0 + (25.0 if premium > 0 else 10.0))
                    if any(property_input.zone_flags.get(flag) is True for flag in PREMIUM_ZONE_FLAGS):
                        rarity_score = _clamp(rarity_score + 10.0)
                    rarity_components.append(rarity_score)

        if not category_results and property_input.zone_flags:
            confidence_notes.append(
                "Zone-style location flags were available, but detailed bucket benchmarking was incomplete."
            )

        scarcity_score = _weighted_average(
            [
                (proximity_components, 0.40),
                (supply_components, 0.35),
                (rarity_components, 0.25),
            ],
            fallback=0.0,
        )

        risk_component, risk_notes = _risk_adjustment(property_input)
        confidence_notes.extend(risk_notes)
        location_score = _weighted_average(
            [
                (proximity_components, 0.35),
                ([scarcity_score] if category_results else [], 0.25),
                (lifestyle_components, 0.20),
                ([risk_component] if risk_component is not None else [], 0.20),
            ],
            fallback=0.0,
        )

        headline_result = _headline_category_result(category_results)
        if headline_result is None and not category_results:
            confidence_notes.append(
                "Location support is currently proxy-based rather than benchmarked against distance buckets."
            )

        peer_comp_count = max((result.peer_bucket_stats.comp_count for result in category_results if result.peer_bucket_stats), default=0)
        confidence = _confidence_score(
            subject_has_geo=property_input.latitude is not None and property_input.longitude is not None,
            available_categories=len(available_categories),
            category_results=category_results,
            peer_comp_count=peer_comp_count,
            geo_comp_count=len(sales_with_geo),
            has_zone_flags=bool(property_input.zone_flags),
        )
        confidence_notes.extend(_confidence_depth_notes(peer_comp_count, len(category_results), len(available_categories), len(sales_with_geo)))
        confidence_notes = _dedupe(confidence_notes)
        missing_inputs = _dedupe(missing_inputs)

        output = LocationIntelligenceOutput(
            subject_ppsf=subject_ppsf,
            location_score=round(location_score, 1),
            scarcity_score=round(scarcity_score, 1),
            confidence=round(confidence, 2),
            primary_category=(headline_result.category if headline_result else None),
            location_premium_pct=round(headline_result.location_premium_pct, 4)
            if headline_result and headline_result.location_premium_pct is not None
            else None,
            subject_relative_premium_pct=round(headline_result.subject_relative_premium_pct, 4)
            if headline_result and headline_result.subject_relative_premium_pct is not None
            else None,
            narratives=_build_narratives(
                property_input=property_input,
                category_results=category_results,
                location_score=location_score,
                scarcity_score=scarcity_score,
                confidence=confidence,
            ),
            confidence_notes=confidence_notes,
            missing_inputs=missing_inputs,
            zone_flags=dict(property_input.zone_flags),
            category_results=category_results,
        )

        summary = output.narratives[0] if output.narratives else (
            "Briarwood could not form a benchmarked geo-location view because landmark or coordinate coverage was too thin."
        )
        extra_missing = list(missing_inputs)
        if property_input.latitude is None or property_input.longitude is None:
            extra_missing.append("address_coordinates")
        section_notes = list(confidence_notes)
        section_notes.append(
            "Location intelligence is benchmarked against same-town geo buckets when coordinates exist and otherwise falls back to clearly labeled proxy logic."
        )

        return ModuleResult(
            module_name=self.name,
            metrics={
                "location_score": output.location_score,
                "scarcity_score": output.scarcity_score,
                "location_premium_pct": output.location_premium_pct,
                "subject_relative_premium_pct": output.subject_relative_premium_pct,
                "primary_location_category": output.primary_category,
                "geo_peer_comp_count": len(sales_with_geo),
                "landmark_category_count": len(available_categories),
            },
            score=output.location_score,
            confidence=output.confidence,
            summary=summary,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["comp_support", "flood_risk", "scarcity_inputs"],
                notes=section_notes,
                extra_missing_inputs=extra_missing,
            ),
        )

    def _load_sales(self, property_input: PropertyInput) -> list[ComparableSale]:
        provider_sales = []
        if not (
            property_input.source_metadata is not None
            and "manual_subject_entry" in property_input.source_metadata.provenance
        ):
            provider_sales = self.provider.get_sales(town=property_input.town, state=property_input.state)

        manual_sales = [
            ComparableSale.model_validate(item)
            for item in property_input.manual_comp_inputs
            if isinstance(item, dict)
        ]
        combined = manual_sales + provider_sales
        return [sale for sale in combined if _is_location_eligible_sale(sale)]

    def _build_category_result(
        self,
        *,
        category: str,
        subject_lat: float,
        subject_lon: float,
        subject_ppsf: float | None,
        sales: list[ComparableSale],
        landmarks: list[dict[str, object]],
    ) -> LocationCategoryIntelligence | None:
        subject_distance = _distance_to_points(subject_lat, subject_lon, landmarks)
        if subject_distance is None:
            return None

        bucket_labels = [label for _, label in _bucket_set(category)]
        sales_distances: list[tuple[ComparableSale, float, str]] = []
        for sale in sales:
            distance = _distance_to_points(sale.latitude, sale.longitude, landmarks)
            if distance is None:
                continue
            sales_distances.append((sale, distance, _bucket_for_distance(distance, category)))

        if not sales_distances:
            return LocationCategoryIntelligence(
                category=category,
                subject_distance_miles=round(subject_distance, 3),
                subject_bucket=_bucket_for_distance(subject_distance, category),
                all_bucket_stats=[LocationBucketBenchmark(bucket_label=label) for label in bucket_labels],
            )

        subject_bucket = _bucket_for_distance(subject_distance, category)
        all_bucket_stats = [
            _bucket_benchmark(bucket_label=label, rows=sales_distances)
            for label in bucket_labels
        ]
        peer_bucket = next((bucket for bucket in all_bucket_stats if bucket.bucket_label == subject_bucket), None)
        town_ppsf = [_safe_ppsf(sale.sale_price, sale.sqft) for sale, _, _ in sales_distances]
        town_ppsf = [value for value in town_ppsf if value is not None]
        town_prices = [sale.sale_price for sale, _, _ in sales_distances if sale.sale_price]
        town_dom = [float(sale.days_on_market) for sale, _, _ in sales_distances if sale.days_on_market is not None]

        town_median_ppsf = _median_or_none(town_ppsf)
        peer_median_ppsf = peer_bucket.median_ppsf if peer_bucket else None
        location_premium_pct = None
        if town_median_ppsf and peer_median_ppsf:
            location_premium_pct = (peer_median_ppsf / town_median_ppsf) - 1.0
        subject_relative_premium_pct = None
        if subject_ppsf and peer_median_ppsf:
            subject_relative_premium_pct = (subject_ppsf / peer_median_ppsf) - 1.0

        return LocationCategoryIntelligence(
            category=category,
            subject_distance_miles=round(subject_distance, 3),
            subject_bucket=subject_bucket,
            peer_bucket_stats=peer_bucket,
            all_bucket_stats=all_bucket_stats,
            town_median_ppsf=round(town_median_ppsf, 2) if town_median_ppsf is not None else None,
            town_median_price=round(_median_or_none(town_prices), 2) if town_prices else None,
            town_median_dom=round(_median_or_none(town_dom), 1) if town_dom else None,
            town_comp_count=len(sales_distances),
            location_premium_pct=round(location_premium_pct, 4) if location_premium_pct is not None else None,
            subject_relative_premium_pct=round(subject_relative_premium_pct, 4)
            if subject_relative_premium_pct is not None
            else None,
        )


def _sale_has_geo(sale: ComparableSale) -> bool:
    return sale.latitude is not None and sale.longitude is not None


def _is_location_eligible_sale(sale: ComparableSale) -> bool:
    if sale.address_verification_status == "questioned":
        return False
    if sale.sale_verification_status == "questioned":
        return False
    return True


def _safe_ppsf(price: float | None, sqft: int | None) -> float | None:
    if price is None or sqft in (None, 0):
        return None
    return price / sqft


def _distance_to_points(
    latitude: float | None,
    longitude: float | None,
    points: list[dict[str, object]],
) -> float | None:
    if latitude is None or longitude is None or not points:
        return None
    distances: list[float] = []
    for point in points:
        point_lat = _point_value(point, "latitude", "lat")
        point_lon = _point_value(point, "longitude", "lon", "lng")
        if point_lat is None or point_lon is None:
            continue
        distances.append(_haversine_miles(latitude, longitude, point_lat, point_lon))
    return min(distances) if distances else None


def _point_value(point: dict[str, object], *keys: str) -> float | None:
    for key in keys:
        value = point.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * radius_miles * asin(sqrt(a))


def _bucket_set(category: str) -> list[tuple[float, str]]:
    if category == "beach":
        return BEACH_BUCKETS
    if category == "downtown":
        return DOWNTOWN_BUCKETS
    if category == "ski":
        return SKI_BUCKETS
    return DEFAULT_BUCKETS


def _bucket_for_distance(distance: float, category: str) -> str:
    for threshold, label in _bucket_set(category):
        if distance <= threshold:
            return label
    return _bucket_set(category)[-1][1]


def _bucket_benchmark(
    *,
    bucket_label: str,
    rows: list[tuple[ComparableSale, float, str]],
) -> LocationBucketBenchmark:
    bucket_sales = [(sale, distance) for sale, distance, label in rows if label == bucket_label]
    ppsf_values = [_safe_ppsf(sale.sale_price, sale.sqft) for sale, _ in bucket_sales]
    ppsf_values = [value for value in ppsf_values if value is not None]
    prices = [sale.sale_price for sale, _ in bucket_sales if sale.sale_price]
    dom_values = [float(sale.days_on_market) for sale, _ in bucket_sales if sale.days_on_market is not None]
    return LocationBucketBenchmark(
        bucket_label=bucket_label,
        median_ppsf=round(_median_or_none(ppsf_values), 2) if ppsf_values else None,
        median_price=round(_median_or_none(prices), 2) if prices else None,
        median_dom=round(_median_or_none(dom_values), 1) if dom_values else None,
        comp_count=len(bucket_sales),
    )


def _median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def _percentile_benefit(subject_value: float, peer_values: list[float]) -> float:
    if not peer_values:
        return 0.0
    less_or_equal = sum(1 for value in peer_values if value <= subject_value)
    percentile = less_or_equal / len(peer_values)
    return _clamp((1.0 - percentile) * 100.0)


def _distance_benefit(distance: float, category: str) -> float:
    ideal = {
        "beach": 0.25,
        "downtown": 0.5,
        "park": 0.5,
        "train": 1.0,
        "ski": 3.0,
    }.get(category, 1.0)
    score = 100.0 * max(0.0, 1.0 - (distance / (ideal * 4)))
    return _clamp(score)


def _risk_adjustment(property_input: PropertyInput) -> tuple[float | None, list[str]]:
    notes: list[str] = []
    if property_input.zone_flags.get("in_flood_zone") is True:
        notes.append("Flood-zone flag reduced the location score.")
        return 25.0, notes
    if property_input.zone_flags.get("in_flood_zone") is False:
        return 65.0, notes
    flood_risk = (property_input.flood_risk or "").strip().lower()
    if flood_risk == "low":
        return 70.0, notes
    if flood_risk == "medium":
        notes.append("Flood risk was only partially supportive, so risk adjustment was conservative.")
        return 50.0, notes
    if flood_risk == "high":
        notes.append("High flood-risk context reduced the location score.")
        return 25.0, notes
    return None, notes


def _weighted_average(
    components: list[tuple[list[float], float]],
    *,
    fallback: float,
) -> float:
    weighted_sum = 0.0
    total_weight = 0.0
    for values, weight in components:
        if not values:
            continue
        weighted_sum += (sum(values) / len(values)) * weight
        total_weight += weight
    if total_weight <= 0:
        return fallback
    return weighted_sum / total_weight


def _confidence_score(
    *,
    subject_has_geo: bool,
    available_categories: int,
    category_results: list[LocationCategoryIntelligence],
    peer_comp_count: int,
    geo_comp_count: int,
    has_zone_flags: bool,
) -> float:
    score = 0.0
    if subject_has_geo:
        score += 0.30
    if available_categories:
        score += min(available_categories / 3, 1.0) * 0.20
    if category_results:
        score += min(len(category_results) / 3, 1.0) * 0.20
    if geo_comp_count:
        score += min(geo_comp_count / 8, 1.0) * 0.15
    if peer_comp_count:
        score += min(peer_comp_count / 4, 1.0) * 0.10
    if has_zone_flags:
        score += 0.05
    if not subject_has_geo and not has_zone_flags:
        return 0.0
    if category_results and peer_comp_count < 2:
        score = min(score, 0.52)
    elif category_results and peer_comp_count < 3:
        score = min(score, 0.64)
    return _clamp(score, 0.0, 1.0)


def _confidence_depth_notes(
    peer_comp_count: int,
    category_result_count: int,
    available_category_count: int,
    geo_comp_count: int,
) -> list[str]:
    notes: list[str] = []
    if available_category_count and category_result_count < available_category_count:
        notes.append("Only partial landmark coverage produced usable bucket benchmarks.")
    if geo_comp_count and geo_comp_count < 4:
        notes.append("Geo peer depth was thin, so bucket medians should be treated as directional.")
    if peer_comp_count == 0 and category_result_count > 0:
        notes.append("Subject buckets were identified, but peer bucket medians were not well populated.")
    elif peer_comp_count < 3 and category_result_count > 0:
        notes.append("Peer bucket support was limited to a small comp set.")
    return notes


def _headline_category_result(
    category_results: list[LocationCategoryIntelligence],
) -> LocationCategoryIntelligence | None:
    ranked = [
        result
        for result in category_results
        if result.peer_bucket_stats is not None and result.peer_bucket_stats.comp_count > 0
    ]
    if not ranked:
        return None
    ranked.sort(
        key=lambda result: (
            result.peer_bucket_stats.comp_count if result.peer_bucket_stats else 0,
            0.0 if result.location_premium_pct is None else abs(result.location_premium_pct),
        ),
        reverse=True,
    )
    return ranked[0]


def _build_narratives(
    *,
    property_input: PropertyInput,
    category_results: list[LocationCategoryIntelligence],
    location_score: float,
    scarcity_score: float,
    confidence: float,
) -> list[str]:
    bullets: list[str] = []
    headline = _headline_category_result(category_results)
    if headline and headline.subject_distance_miles is not None:
        category_name = headline.category.replace("_", " ")
        if (headline.location_premium_pct or 0.0) > 0.08:
            bullets.append(
                f"The property sits in an above-average {category_name} bucket for {property_input.town}, where peer PPSF pricing runs above the town median."
            )
        elif (headline.location_premium_pct or 0.0) < -0.08:
            bullets.append(
                f"The property's {category_name} bucket screens as more common than premium relative to town inventory."
            )
        else:
            bullets.append(
                f"Location support looks close to town average once the property is benchmarked against its {category_name} peer bucket."
            )

        relative_premium = headline.subject_relative_premium_pct
        if relative_premium is not None:
            if relative_premium > 0.08:
                bullets.append(
                    "The subject still trades above its geo peer bucket, so location alone does not explain the full PPSF premium."
                )
            elif relative_premium < -0.08:
                bullets.append(
                    "The subject appears discounted relative to similarly positioned geo peers."
                )
            else:
                bullets.append(
                    "The subject's PPSF looks broadly aligned with similarly positioned geo peers."
                )

    if category_results and scarcity_score >= 67:
        bullets.append("Location benefit appears meaningfully scarce relative to the current town peer set.")
    elif category_results and scarcity_score <= 40:
        bullets.append("Location benefit looks fairly common, so scarcity is not doing much of the valuation work.")

    if confidence < 0.45:
        bullets.append("Geo conclusions are still low-confidence because landmark or coordinate coverage is incomplete.")

    return bullets[:4] or [
        "Geo benchmarking was limited, so Briarwood treated location support conservatively."
    ]


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def get_location_intelligence_payload(result: ModuleResult) -> LocationIntelligenceOutput:
    if not isinstance(result.payload, LocationIntelligenceOutput):
        raise TypeError("location_intelligence module payload is not a LocationIntelligenceOutput")
    return result.payload


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered

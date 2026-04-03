from __future__ import annotations

import json
from pathlib import Path

from briarwood.inputs.adapters import ListingTextAdapter, PublicRecordAdapter, normalized_listing_to_canonical
from briarwood.inputs.market_location_adapter import MarketLocationAdapter
from briarwood.inputs.property_support_adapter import PropertySupportAdapter
from briarwood.listing_intake.schemas import ListingIntakeResult, NormalizedPropertyData
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.schemas import (
    CanonicalPropertyData,
    EvidenceMode,
    InputCoverageStatus,
    MarketLocationSignals,
    PropertyFacts,
    PropertyInput,
    SourceCoverageItem,
    SourceMetadata,
    UserAssumptions,
)


def load_property_from_json(path: str | Path) -> PropertyInput:
    data = json.loads(Path(path).read_text())
    if {"facts", "market_signals", "user_assumptions", "source_metadata"} & set(data):
        canonical = _canonical_from_dict(data)
        canonical = _enrich_with_market_context(canonical)
        return PropertyInput.from_canonical(canonical)
    canonical = PublicRecordAdapter().build(data, property_id=str(data.get("property_id") or "property-json"))
    canonical = _enrich_with_market_context(canonical)
    return PropertyInput.from_canonical(canonical)


def load_property_from_normalized_listing(
    normalized_property_data: NormalizedPropertyData,
    *,
    property_id: str = "listing-intake",
) -> PropertyInput:
    canonical = normalized_listing_to_canonical(normalized_property_data, property_id=property_id)
    canonical = _enrich_with_market_context(canonical)
    return PropertyInput.from_canonical(canonical)


def load_property_from_listing_intake_result(
    intake_result: ListingIntakeResult,
    *,
    property_id: str = "listing-intake",
) -> PropertyInput:
    return load_property_from_normalized_listing(
        intake_result.normalized_property_data,
        property_id=property_id,
    )


def load_property_from_listing_source(
    source: str,
    *,
    property_id: str = "listing-intake",
    intake_service: ListingIntakeService | None = None,
) -> PropertyInput:
    service = intake_service or ListingIntakeService()
    intake_result = service.intake(source)
    return load_property_from_listing_intake_result(
        intake_result,
        property_id=property_id,
    )


def load_property_from_listing_text(
    text: str,
    *,
    property_id: str = "listing-intake",
    source_url: str | None = None,
    intake_service: ListingIntakeService | None = None,
) -> PropertyInput:
    adapter = ListingTextAdapter(intake_service=intake_service or ListingIntakeService())
    canonical = adapter.build(text, property_id=property_id, source_url=source_url)
    canonical = _enrich_with_market_context(canonical)
    return PropertyInput.from_canonical(canonical)


def _enrich_with_market_context(canonical: CanonicalPropertyData) -> CanonicalPropertyData:
    canonical = MarketLocationAdapter().enrich(canonical)
    canonical = PropertySupportAdapter().enrich(canonical)
    return canonical


def _canonical_from_dict(data: dict[str, object]) -> CanonicalPropertyData:
    facts_payload = data.get("facts") or {}
    market_payload = data.get("market_signals") or {}
    assumptions_payload = data.get("user_assumptions") or {}
    metadata_payload = data.get("source_metadata") or {}

    facts = PropertyFacts(
        address=str(facts_payload.get("address") or data.get("address") or "Unknown Address"),
        town=str(facts_payload.get("town") or data.get("town") or "Unknown"),
        state=str(facts_payload.get("state") or data.get("state") or "Unknown"),
        county=_optional_str(facts_payload.get("county", data.get("county"))),
        zip_code=_optional_str(facts_payload.get("zip_code")),
        latitude=_optional_float(facts_payload.get("latitude", data.get("latitude"))),
        longitude=_optional_float(facts_payload.get("longitude", data.get("longitude"))),
        beds=_optional_int(facts_payload.get("beds", data.get("beds"))),
        baths=_optional_float(facts_payload.get("baths", data.get("baths"))),
        sqft=_optional_int(facts_payload.get("sqft", data.get("sqft"))),
        lot_size=_optional_float(facts_payload.get("lot_size", data.get("lot_size"))),
        property_type=_optional_str(facts_payload.get("property_type", data.get("property_type"))),
        architectural_style=_optional_str(facts_payload.get("architectural_style", data.get("architectural_style"))),
        condition_profile=_optional_str(facts_payload.get("condition_profile", data.get("condition_profile"))),
        capex_lane=_optional_str(facts_payload.get("capex_lane", data.get("capex_lane"))),
        year_built=_optional_int(facts_payload.get("year_built", data.get("year_built"))),
        stories=_optional_float(facts_payload.get("stories", data.get("stories"))),
        garage_spaces=_optional_int(facts_payload.get("garage_spaces", data.get("garage_spaces"))),
        garage_type=_optional_str(facts_payload.get("garage_type", data.get("garage_type"))),
        has_detached_garage=_optional_bool(facts_payload.get("has_detached_garage", data.get("has_detached_garage"))),
        has_back_house=_optional_bool(facts_payload.get("has_back_house", data.get("has_back_house"))),
        adu_type=_optional_str(facts_payload.get("adu_type", data.get("adu_type"))),
        adu_sqft=_optional_int(facts_payload.get("adu_sqft", data.get("adu_sqft"))),
        has_basement=_optional_bool(facts_payload.get("has_basement", data.get("has_basement"))),
        basement_finished=_optional_bool(facts_payload.get("basement_finished", data.get("basement_finished"))),
        has_pool=_optional_bool(facts_payload.get("has_pool", data.get("has_pool"))),
        parking_spaces=_optional_int(facts_payload.get("parking_spaces", data.get("parking_spaces"))),
        corner_lot=_optional_bool(facts_payload.get("corner_lot", data.get("corner_lot"))),
        driveway_off_street=_optional_bool(facts_payload.get("driveway_off_street", data.get("driveway_off_street"))),
        purchase_price=_optional_float(facts_payload.get("purchase_price", data.get("purchase_price"))),
        taxes=_optional_float(facts_payload.get("taxes", data.get("taxes"))),
        monthly_hoa=_optional_float(facts_payload.get("monthly_hoa", data.get("monthly_hoa"))),
        days_on_market=_optional_int(facts_payload.get("days_on_market", data.get("days_on_market"))),
        listing_date=_optional_str(facts_payload.get("listing_date", data.get("listing_date"))),
        listing_description=_optional_str(facts_payload.get("listing_description", data.get("listing_description"))),
        source_url=_optional_str(facts_payload.get("source_url", data.get("source_url"))),
        price_history=list(facts_payload.get("price_history", data.get("price_history", [])) or []),
        sale_history=list(facts_payload.get("sale_history", [])),
    )
    market_signals = MarketLocationSignals(
        town_population_trend=_optional_float(market_payload.get("town_population_trend", data.get("town_population_trend"))),
        town_price_trend=_optional_float(market_payload.get("town_price_trend", data.get("town_price_trend"))),
        school_rating=_optional_float(market_payload.get("school_rating", data.get("school_rating"))),
        flood_risk=_optional_str(market_payload.get("flood_risk", data.get("flood_risk"))),
        town_population=_optional_int(market_payload.get("town_population", data.get("town_population"))),
        market_price_to_rent_benchmark=_optional_float(
            market_payload.get("market_price_to_rent_benchmark", data.get("market_price_to_rent_benchmark"))
        ),
        landmark_points=_coerce_landmark_points(market_payload.get("landmark_points", data.get("landmark_points"))),
        zone_flags=_coerce_zone_flags(market_payload.get("zone_flags", data.get("zone_flags"))),
        local_documents=_coerce_document_list(market_payload.get("local_documents", data.get("local_documents"))),
    )
    user_assumptions = UserAssumptions(
        estimated_monthly_rent=_optional_float(assumptions_payload.get("estimated_monthly_rent", data.get("estimated_monthly_rent"))),
        back_house_monthly_rent=_optional_float(assumptions_payload.get("back_house_monthly_rent", data.get("back_house_monthly_rent"))),
        seasonal_monthly_rent=_optional_float(assumptions_payload.get("seasonal_monthly_rent", data.get("seasonal_monthly_rent"))),
        unit_rents=_float_list(assumptions_payload.get("unit_rents", data.get("unit_rents", []))),
        rent_confidence_override=_optional_str(assumptions_payload.get("rent_confidence_override", data.get("rent_confidence_override"))),
        insurance=_optional_float(assumptions_payload.get("insurance", data.get("insurance"))),
        down_payment_percent=_optional_float(
            assumptions_payload.get("down_payment_percent", data.get("down_payment_percent"))
        ),
        interest_rate=_optional_float(assumptions_payload.get("interest_rate", data.get("interest_rate"))),
        loan_term_years=_optional_int(assumptions_payload.get("loan_term_years", data.get("loan_term_years"))),
        vacancy_rate=_optional_float(assumptions_payload.get("vacancy_rate", data.get("vacancy_rate"))),
        monthly_maintenance_reserve_override=_optional_float(
            assumptions_payload.get("monthly_maintenance_reserve_override", data.get("monthly_maintenance_reserve_override"))
        ),
        condition_profile_override=_optional_str(assumptions_payload.get("condition_profile_override")),
        condition_confirmed=_optional_bool(assumptions_payload.get("condition_confirmed", data.get("condition_confirmed"))),
        capex_lane_override=_optional_str(assumptions_payload.get("capex_lane_override")),
        capex_confirmed=_optional_bool(assumptions_payload.get("capex_confirmed", data.get("capex_confirmed"))),
        repair_capex_budget=_optional_float(assumptions_payload.get("repair_capex_budget", data.get("repair_capex_budget"))),
        strategy_intent=_optional_str(assumptions_payload.get("strategy_intent", data.get("strategy_intent"))),
        hold_period_years=_optional_int(assumptions_payload.get("hold_period_years", data.get("hold_period_years"))),
        risk_tolerance=_optional_str(assumptions_payload.get("risk_tolerance", data.get("risk_tolerance"))),
        manual_comp_inputs=list(assumptions_payload.get("manual_comp_inputs", data.get("manual_comp_inputs", [])) or []),
    )
    raw_mode = str(metadata_payload.get("evidence_mode") or "public_record")
    evidence_mode = (
        EvidenceMode(raw_mode)
        if raw_mode in {mode.value for mode in EvidenceMode}
        else EvidenceMode.PUBLIC_RECORD
    )
    coverage_payload = metadata_payload.get("source_coverage") or {}
    source_coverage = {
        key: SourceCoverageItem(
            category=key,
            status=InputCoverageStatus(str(value.get("status", "missing"))),
            source_name=_optional_str(value.get("source_name")),
            freshness=_optional_str(value.get("freshness")),
            note=_optional_str(value.get("note")),
        )
        for key, value in coverage_payload.items()
        if isinstance(value, dict)
    }
    metadata = SourceMetadata(
        evidence_mode=evidence_mode,
        source_coverage=source_coverage,
        provenance=list(metadata_payload.get("provenance", [])),
        freshest_as_of=_optional_str(metadata_payload.get("freshest_as_of")),
    )
    return CanonicalPropertyData(
        property_id=str(data.get("property_id") or "property-json"),
        facts=facts,
        market_signals=market_signals,
        user_assumptions=user_assumptions,
        source_metadata=metadata,
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_bool(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    floats: list[float] = []
    for item in value:
        parsed = _optional_float(item)
        if parsed is not None and parsed > 0:
            floats.append(parsed)
    return floats


def _coerce_landmark_points(value: object) -> dict[str, list[dict[str, object]]]:
    if not isinstance(value, dict):
        return {}
    coerced: dict[str, list[dict[str, object]]] = {}
    for key, points in value.items():
        if not isinstance(key, str) or not isinstance(points, list):
            continue
        valid_points = [point for point in points if isinstance(point, dict)]
        if valid_points:
            coerced[key] = valid_points
    return coerced


def _coerce_zone_flags(value: object) -> dict[str, bool | None]:
    if not isinstance(value, dict):
        return {}
    coerced: dict[str, bool | None] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        coerced[key] = _optional_bool(raw)
    return coerced


def _coerce_document_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

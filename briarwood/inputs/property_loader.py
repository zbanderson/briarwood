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
        beds=_optional_int(facts_payload.get("beds", data.get("beds"))),
        baths=_optional_float(facts_payload.get("baths", data.get("baths"))),
        sqft=_optional_int(facts_payload.get("sqft", data.get("sqft"))),
        lot_size=_optional_float(facts_payload.get("lot_size", data.get("lot_size"))),
        property_type=_optional_str(facts_payload.get("property_type", data.get("property_type"))),
        architectural_style=_optional_str(facts_payload.get("architectural_style", data.get("architectural_style"))),
        year_built=_optional_int(facts_payload.get("year_built", data.get("year_built"))),
        stories=_optional_float(facts_payload.get("stories", data.get("stories"))),
        garage_spaces=_optional_int(facts_payload.get("garage_spaces", data.get("garage_spaces"))),
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
        market_price_to_rent_benchmark=_optional_float(
            market_payload.get("market_price_to_rent_benchmark", data.get("market_price_to_rent_benchmark"))
        ),
    )
    user_assumptions = UserAssumptions(
        estimated_monthly_rent=_optional_float(assumptions_payload.get("estimated_monthly_rent", data.get("estimated_monthly_rent"))),
        insurance=_optional_float(assumptions_payload.get("insurance", data.get("insurance"))),
        down_payment_percent=_optional_float(
            assumptions_payload.get("down_payment_percent", data.get("down_payment_percent"))
        ),
        interest_rate=_optional_float(assumptions_payload.get("interest_rate", data.get("interest_rate"))),
        loan_term_years=_optional_int(assumptions_payload.get("loan_term_years", data.get("loan_term_years"))),
        vacancy_rate=_optional_float(assumptions_payload.get("vacancy_rate", data.get("vacancy_rate"))),
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

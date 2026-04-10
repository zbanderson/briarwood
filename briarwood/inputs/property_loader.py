from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from briarwood.inputs.adapters import ListingTextAdapter, PublicRecordAdapter, normalized_listing_to_canonical
from briarwood.data_quality.arbitration import apply_evidence_profile
from briarwood.inputs.market_location_adapter import MarketLocationAdapter
from briarwood.inputs.property_support_adapter import PropertySupportAdapter
from briarwood.listing_intake.schemas import ListingIntakeResult, NormalizedPropertyData
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.schemas import (
    CanonicalFieldProvenance,
    CanonicalPropertyData,
    EvidenceMode,
    InputCoverageStatus,
    MarketLocationSignals,
    OccupancyStrategy,
    PropertyFacts,
    PropertyInput,
    SourceCoverageItem,
    SourceMetadata,
    SourceTier,
    UserAssumptions,
    VerifiedStatus,
)

logger = logging.getLogger(__name__)


# S5 (audit 2026-04-08): pydantic sanity-check at the ingestion boundary. The
# existing dataclass pipeline is preserved — this model only inspects the
# fields that caused real-world issues (out-of-range numerics and typo'd
# enums) and fails loudly before the engine sees nonsense. Rate fields allow
# either 0..1 or 0..100 because cost_valuation._normalize_percent accepts
# both forms.
_FLOOD_VALUES = {None, "none", "low", "medium", "high"}


class _PropertyInputValidationModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address: str
    town: str
    state: str
    beds: int | None = None
    baths: float | None = None
    sqft: int | None = None
    lot_size: float | None = None
    year_built: int | None = None
    purchase_price: float | None = None
    taxes: float | None = None
    insurance: float | None = None
    monthly_hoa: float | None = None
    estimated_monthly_rent: float | None = None
    down_payment_percent: float | None = None
    interest_rate: float | None = None
    loan_term_years: int | None = None
    vacancy_rate: float | None = None
    school_rating: float | None = None
    flood_risk: Literal["none", "low", "medium", "high"] | None = None

    @field_validator("address", "town", "state")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("beds")
    @classmethod
    def _beds_range(cls, value: int | None) -> int | None:
        if value is not None and not 0 <= value <= 50:
            raise ValueError("beds out of range (0..50)")
        return value

    @field_validator("baths")
    @classmethod
    def _baths_range(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 50:
            raise ValueError("baths out of range (0..50)")
        return value

    @field_validator("sqft")
    @classmethod
    def _sqft_range(cls, value: int | None) -> int | None:
        if value is not None and not 0 <= value <= 100_000:
            raise ValueError("sqft out of range (0..100000)")
        return value

    @field_validator("lot_size")
    @classmethod
    def _lot_size_range(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("lot_size must be non-negative")
        return value

    @field_validator("year_built")
    @classmethod
    def _year_built_range(cls, value: int | None) -> int | None:
        if value is not None and not 1600 <= value <= 2100:
            raise ValueError("year_built out of plausible range (1600..2100)")
        return value

    @field_validator(
        "purchase_price",
        "taxes",
        "insurance",
        "monthly_hoa",
        "estimated_monthly_rent",
    )
    @classmethod
    def _money_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("must be non-negative")
        return value

    @field_validator("down_payment_percent", "interest_rate", "vacancy_rate")
    @classmethod
    def _rate_range(cls, value: float | None) -> float | None:
        # Accept either 0..1 or 0..100 form (cost_valuation normalizes).
        if value is not None and not 0 <= value <= 100:
            raise ValueError("rate out of range (0..100)")
        return value

    @field_validator("loan_term_years")
    @classmethod
    def _loan_term_range(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 50:
            raise ValueError("loan_term_years out of range (1..50)")
        return value

    @field_validator("school_rating")
    @classmethod
    def _school_rating_range(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 10:
            raise ValueError("school_rating out of range (0..10)")
        return value


def _validate_property_input(property_input: PropertyInput) -> None:
    """Run pydantic sanity checks on an assembled PropertyInput.

    Fails fast with a clear message when ranges/enums are obviously wrong
    (e.g. negative sqft, interest_rate of 900, flood_risk typo). The existing
    dataclass pipeline handles the actual construction; this just guards the
    boundary so bad data can't silently propagate into scoring.
    """
    try:
        _PropertyInputValidationModel.model_validate(
            {
                "address": property_input.address,
                "town": property_input.town,
                "state": property_input.state,
                "beds": property_input.beds,
                "baths": property_input.baths,
                "sqft": property_input.sqft,
                "lot_size": property_input.lot_size,
                "year_built": property_input.year_built,
                "purchase_price": property_input.purchase_price,
                "taxes": property_input.taxes,
                "insurance": property_input.insurance,
                "monthly_hoa": property_input.monthly_hoa,
                "estimated_monthly_rent": property_input.estimated_monthly_rent,
                "down_payment_percent": property_input.down_payment_percent,
                "interest_rate": property_input.interest_rate,
                "loan_term_years": property_input.loan_term_years,
                "vacancy_rate": property_input.vacancy_rate,
                "school_rating": property_input.school_rating,
                "flood_risk": property_input.flood_risk,
            }
        )
    except ValidationError as exc:
        raise ValueError(
            f"Property input failed validation for {property_input.property_id}: {exc}"
        ) from exc


def load_property_from_json(path: str | Path) -> PropertyInput:
    data = json.loads(Path(path).read_text())
    if {"facts", "market_signals", "user_assumptions", "source_metadata"} & set(data):
        canonical = _canonical_from_dict(data)
        canonical = _enrich_with_market_context(canonical)
        property_input = PropertyInput.from_canonical(canonical)
        _validate_property_input(property_input)
        return property_input
    canonical = PublicRecordAdapter().build(data, property_id=str(data.get("property_id") or "property-json"))
    canonical = _enrich_with_market_context(canonical)
    property_input = PropertyInput.from_canonical(canonical)
    _validate_property_input(property_input)
    return property_input


def load_property_from_normalized_listing(
    normalized_property_data: NormalizedPropertyData,
    *,
    property_id: str = "listing-intake",
) -> PropertyInput:
    canonical = normalized_listing_to_canonical(normalized_property_data, property_id=property_id)
    canonical = _enrich_with_market_context(canonical)
    property_input = PropertyInput.from_canonical(canonical)
    _validate_property_input(property_input)
    return property_input


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
    property_input = PropertyInput.from_canonical(canonical)
    _validate_property_input(property_input)
    return property_input


def _enrich_with_market_context(canonical: CanonicalPropertyData) -> CanonicalPropertyData:
    canonical = MarketLocationAdapter().enrich(canonical)
    canonical = PropertySupportAdapter().enrich(canonical)
    canonical = apply_evidence_profile(canonical)
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
        occupancy_strategy=_optional_occupancy_strategy(assumptions_payload.get("occupancy_strategy", data.get("occupancy_strategy"))),
        owner_occupied_unit_count=_optional_int(assumptions_payload.get("owner_occupied_unit_count", data.get("owner_occupied_unit_count"))),
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
        field_provenance=_coerce_field_provenance(metadata_payload.get("field_provenance")),
        mapper_version=_optional_str(metadata_payload.get("mapper_version")) or "legacy",
        property_evidence_profile=metadata_payload.get("property_evidence_profile"),
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


def _optional_occupancy_strategy(value: object) -> OccupancyStrategy | None:
    text = _optional_str(value)
    if text is None:
        return None
    try:
        return OccupancyStrategy(text.lower())
    except ValueError:
        return None


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


def _coerce_field_provenance(value: object) -> dict[str, CanonicalFieldProvenance]:
    if not isinstance(value, dict):
        return {}
    provenance: dict[str, CanonicalFieldProvenance] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not isinstance(raw, dict):
            continue
        try:
            provenance[key] = CanonicalFieldProvenance(
                value=raw.get("value"),
                source=str(raw.get("source") or "unknown"),
                source_tier=SourceTier(str(raw.get("source_tier") or SourceTier.TIER_3.value)),
                verified_status=VerifiedStatus(str(raw.get("verified_status") or VerifiedStatus.UNVERIFIED.value)),
                last_updated=_optional_str(raw.get("last_updated")),
                confidence=float(raw.get("confidence") or 0.0),
                mapper_version=_optional_str(raw.get("mapper_version")) or "legacy",
                notes=[str(item) for item in list(raw.get("notes", []) or [])],
            )
        except (TypeError, ValueError):
            continue
    return provenance

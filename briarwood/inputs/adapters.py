from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from briarwood.listing_intake.schemas import NormalizedPropertyData
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.schemas import (
    CanonicalFieldProvenance,
    CanonicalPropertyData,
    EvidenceMode,
    InputCoverageStatus,
    MarketLocationSignals,
    OccupancyStrategy,
    PropertyFacts,
    SourceCoverageItem,
    SourceMetadata,
    SourceTier,
    UserAssumptions,
    VerifiedStatus,
)


class CanonicalInputAdapter(Protocol):
    def build(self, *args: object, **kwargs: object) -> CanonicalPropertyData:
        ...


class PublicRecordAdapter:
    def build(self, payload: dict[str, object], *, property_id: str = "public-record") -> CanonicalPropertyData:
        facts = PropertyFacts(
            address=str(payload.get("address") or "Unknown Address"),
            town=str(payload.get("town") or "Unknown"),
            state=str(payload.get("state") or "Unknown"),
            county=_optional_str(payload.get("county")),
            latitude=_optional_float(payload.get("latitude")),
            longitude=_optional_float(payload.get("longitude")),
            beds=_optional_int(payload.get("beds")),
            baths=_optional_float(payload.get("baths")),
            sqft=_optional_int(payload.get("sqft")),
            lot_size=_optional_float(payload.get("lot_size")),
            property_type=_optional_str(payload.get("property_type")),
            architectural_style=_optional_str(payload.get("architectural_style")),
            year_built=_optional_int(payload.get("year_built")),
            stories=_optional_float(payload.get("stories")),
            garage_spaces=_optional_int(payload.get("garage_spaces")),
            purchase_price=_optional_float(payload.get("purchase_price")),
            taxes=_optional_float(payload.get("taxes")),
            monthly_hoa=_optional_float(payload.get("monthly_hoa")),
            days_on_market=_optional_int(payload.get("days_on_market")),
            listing_date=_optional_str(payload.get("listing_date")),
            listing_description=_optional_str(payload.get("listing_description")),
            source_url=_optional_str(payload.get("source_url")),
            price_history=list(payload.get("price_history") or []),
            sale_history=list(payload.get("sale_history") or []),
        )
        market_signals = MarketLocationSignals(
            town_population_trend=_optional_float(payload.get("town_population_trend")),
            town_price_trend=_optional_float(payload.get("town_price_trend")),
            school_rating=_optional_float(payload.get("school_rating")),
            flood_risk=_optional_str(payload.get("flood_risk")),
            town_population=_optional_int(payload.get("town_population")),
            market_price_to_rent_benchmark=_optional_float(payload.get("market_price_to_rent_benchmark")),
            landmark_points=_coerce_landmark_points(payload.get("landmark_points")),
            zone_flags=_coerce_zone_flags(payload.get("zone_flags")),
            local_documents=_coerce_document_list(payload.get("local_documents")),
        )
        assumptions = UserAssumptions(
            occupancy_strategy=_optional_occupancy_strategy(payload.get("occupancy_strategy")),
            owner_occupied_unit_count=_optional_int(payload.get("owner_occupied_unit_count")),
            estimated_monthly_rent=_optional_float(payload.get("estimated_monthly_rent")),
            rent_confidence_override=_optional_str(payload.get("rent_confidence_override")),
            insurance=_optional_float(payload.get("insurance")),
            down_payment_percent=_optional_float(payload.get("down_payment_percent")),
            interest_rate=_optional_float(payload.get("interest_rate")),
            loan_term_years=_optional_int(payload.get("loan_term_years")),
            vacancy_rate=_optional_float(payload.get("vacancy_rate")),
            condition_profile_override=_optional_str(payload.get("condition_profile_override")),
            condition_confirmed=_optional_bool(payload.get("condition_confirmed")),
            capex_lane_override=_optional_str(payload.get("capex_lane_override")),
            capex_confirmed=_optional_bool(payload.get("capex_confirmed")),
            repair_capex_budget=_optional_float(payload.get("repair_capex_budget")),
            strategy_intent=_optional_str(payload.get("strategy_intent")),
            hold_period_years=_optional_int(payload.get("hold_period_years")),
            risk_tolerance=_optional_str(payload.get("risk_tolerance")),
        )
        evidence_mode = (
            EvidenceMode.LISTING_ASSISTED
            if facts.source_url or facts.listing_description or facts.days_on_market is not None or facts.price_history
            else EvidenceMode.PUBLIC_RECORD
        )
        return CanonicalPropertyData(
            property_id=str(payload.get("property_id") or property_id),
            facts=facts,
            market_signals=market_signals,
            user_assumptions=assumptions,
            source_metadata=_infer_source_metadata(
                evidence_mode=evidence_mode,
                facts=facts,
                market_signals=market_signals,
                assumptions=assumptions,
                provenance=["public_record_adapter"],
                field_provenance=_public_record_field_provenance(facts, market_signals, assumptions),
                mapper_version="public_record_adapter/v1",
            ),
        )


class ListingTextAdapter:
    def __init__(self, intake_service: ListingIntakeService | None = None) -> None:
        self.intake_service = intake_service or ListingIntakeService()

    def build(
        self,
        listing_text: str,
        *,
        property_id: str = "listing-intake",
        source_url: str | None = None,
    ) -> CanonicalPropertyData:
        intake_result = self.intake_service.intake_text(listing_text, source_url=source_url)
        return intake_result.normalized_property_data.to_canonical_input(property_id=property_id)


class ManualInputAdapter:
    def apply(self, canonical: CanonicalPropertyData, *, overrides: dict[str, object]) -> CanonicalPropertyData:
        assumptions = replace(
            canonical.user_assumptions,
            occupancy_strategy=_coalesce_occupancy_strategy(overrides.get("occupancy_strategy"), canonical.user_assumptions.occupancy_strategy),
            owner_occupied_unit_count=_coalesce_int(overrides.get("owner_occupied_unit_count"), canonical.user_assumptions.owner_occupied_unit_count),
            estimated_monthly_rent=_coalesce_float(overrides.get("estimated_monthly_rent"), canonical.user_assumptions.estimated_monthly_rent),
            rent_confidence_override=_coalesce_str(overrides.get("rent_confidence_override"), canonical.user_assumptions.rent_confidence_override),
            insurance=_coalesce_float(overrides.get("insurance"), canonical.user_assumptions.insurance),
            down_payment_percent=_coalesce_float(overrides.get("down_payment_percent"), canonical.user_assumptions.down_payment_percent),
            interest_rate=_coalesce_float(overrides.get("interest_rate"), canonical.user_assumptions.interest_rate),
            loan_term_years=_coalesce_int(overrides.get("loan_term_years"), canonical.user_assumptions.loan_term_years),
            vacancy_rate=_coalesce_float(overrides.get("vacancy_rate"), canonical.user_assumptions.vacancy_rate),
            condition_profile_override=_coalesce_str(overrides.get("condition_profile_override"), canonical.user_assumptions.condition_profile_override),
            condition_confirmed=_coalesce_bool(overrides.get("condition_confirmed"), canonical.user_assumptions.condition_confirmed),
            capex_lane_override=_coalesce_str(overrides.get("capex_lane_override"), canonical.user_assumptions.capex_lane_override),
            capex_confirmed=_coalesce_bool(overrides.get("capex_confirmed"), canonical.user_assumptions.capex_confirmed),
            repair_capex_budget=_coalesce_float(overrides.get("repair_capex_budget"), canonical.user_assumptions.repair_capex_budget),
            strategy_intent=_coalesce_str(overrides.get("strategy_intent"), canonical.user_assumptions.strategy_intent),
            hold_period_years=_coalesce_int(overrides.get("hold_period_years"), canonical.user_assumptions.hold_period_years),
            risk_tolerance=_coalesce_str(overrides.get("risk_tolerance"), canonical.user_assumptions.risk_tolerance),
        )
        coverage = dict(canonical.source_metadata.source_coverage)
        for category, key in {
            "occupancy_strategy": "occupancy_strategy",
            "rent_estimate": "estimated_monthly_rent",
            "rent_confidence": "rent_confidence_override",
            "insurance_estimate": "insurance",
            "financing_down_payment": "down_payment_percent",
            "financing_interest_rate": "interest_rate",
            "condition_assumption": "condition_profile_override",
            "capex_assumption": "capex_lane_override",
            "capex_budget": "repair_capex_budget",
            "strategy_intent": "strategy_intent",
        }.items():
            if overrides.get(key) is not None:
                coverage[category] = SourceCoverageItem(
                    category=category,
                    status=InputCoverageStatus.USER_SUPPLIED,
                    source_name="manual override",
                )
        metadata = replace(
            canonical.source_metadata,
            source_coverage=coverage,
            provenance=canonical.source_metadata.provenance + ["manual_input_adapter"],
            field_provenance=_merge_field_provenance(
                canonical.source_metadata.field_provenance,
                _manual_override_field_provenance(overrides),
            ),
            mapper_version="manual_input_adapter/v1",
        )
        return replace(canonical, user_assumptions=assumptions, source_metadata=metadata)


class MLSAdapter:
    def build_stub(
        self,
        *,
        property_id: str,
        address: str,
        town: str,
        state: str,
    ) -> CanonicalPropertyData:
        facts = PropertyFacts(address=address, town=town, state=state)
        return CanonicalPropertyData(
            property_id=property_id,
            facts=facts,
            source_metadata=SourceMetadata(
                evidence_mode=EvidenceMode.MLS_CONNECTED,
                provenance=["mls_adapter_stub"],
                source_coverage={
                    "address": SourceCoverageItem("address", InputCoverageStatus.SOURCED, source_name="mls_stub"),
                    "comp_support": SourceCoverageItem("comp_support", InputCoverageStatus.MISSING, source_name="mls_stub"),
                },
            ),
        )


def normalized_listing_to_canonical(
    normalized: NormalizedPropertyData,
    *,
    property_id: str = "listing-intake",
) -> CanonicalPropertyData:
    return normalized.to_canonical_input(property_id=property_id)


def _infer_source_metadata(
    *,
    evidence_mode: EvidenceMode,
    facts: PropertyFacts,
    market_signals: MarketLocationSignals,
    assumptions: UserAssumptions,
    provenance: list[str],
    field_provenance: dict[str, CanonicalFieldProvenance] | None = None,
    mapper_version: str = "legacy",
) -> SourceMetadata:
    coverage = {
        "address": _coverage("address", facts.address),
        "price_ask": _coverage("price_ask", facts.purchase_price),
        "beds_baths": _coverage("beds_baths", facts.beds if facts.beds else facts.baths),
        "sqft": _coverage("sqft", facts.sqft),
        "lot_size": _coverage("lot_size", facts.lot_size),
        "taxes": _coverage("taxes", facts.taxes),
        "hoa": _coverage("hoa", facts.monthly_hoa),
        "sale_history": _list_coverage("sale_history", facts.sale_history),
        "listing_history": _list_coverage("listing_history", facts.price_history),
        "rent_estimate": _assumption_coverage("rent_estimate", assumptions.estimated_monthly_rent),
        "occupancy_strategy": _assumption_coverage("occupancy_strategy", assumptions.occupancy_strategy),
        "insurance_estimate": _assumption_coverage("insurance_estimate", assumptions.insurance),
        "school_signal": _coverage("school_signal", market_signals.school_rating),
        "flood_risk": _coverage("flood_risk", market_signals.flood_risk),
        "liquidity_signal": _coverage("liquidity_signal", market_signals.town_population_trend),
        "market_history": _coverage("market_history", market_signals.town_price_trend),
        "scarcity_inputs": SourceCoverageItem("scarcity_inputs", InputCoverageStatus.MISSING),
        "comp_support": SourceCoverageItem("comp_support", InputCoverageStatus.MISSING),
        "financing_down_payment": _assumption_coverage("financing_down_payment", assumptions.down_payment_percent),
        "financing_interest_rate": _assumption_coverage("financing_interest_rate", assumptions.interest_rate),
        "rent_confidence": _assumption_coverage("rent_confidence", assumptions.rent_confidence_override),
        "condition_assumption": _assumption_coverage("condition_assumption", assumptions.condition_profile_override),
        "capex_assumption": _assumption_coverage("capex_assumption", assumptions.capex_lane_override),
        "capex_budget": _assumption_coverage("capex_budget", assumptions.repair_capex_budget),
        "strategy_intent": _assumption_coverage("strategy_intent", assumptions.strategy_intent),
    }
    return SourceMetadata(
        evidence_mode=evidence_mode,
        source_coverage=coverage,
        provenance=provenance,
        field_provenance=field_provenance or {},
        mapper_version=mapper_version,
    )


def _public_record_field_provenance(
    facts: PropertyFacts,
    market_signals: MarketLocationSignals,
    assumptions: UserAssumptions,
) -> dict[str, CanonicalFieldProvenance]:
    provenance: dict[str, CanonicalFieldProvenance] = {}
    for field_name in [
        "address", "town", "state", "county", "latitude", "longitude", "beds", "baths", "sqft", "lot_size",
        "property_type", "architectural_style", "year_built", "stories", "garage_spaces", "purchase_price",
        "taxes", "monthly_hoa", "days_on_market", "listing_date", "listing_description", "source_url",
    ]:
        value = getattr(facts, field_name, None)
        if value is None:
            continue
        provenance[field_name] = _provenance_entry(
            value=value,
            source="public_record_adapter",
            tier=SourceTier.TIER_1,
            verified_status=VerifiedStatus.VERIFIED,
            mapper_version="public_record_adapter/v1",
        )
    for field_name in [
        "town_population_trend", "town_price_trend", "school_rating", "flood_risk",
        "town_population", "market_price_to_rent_benchmark",
    ]:
        value = getattr(market_signals, field_name, None)
        if value is None:
            continue
        provenance[field_name] = _provenance_entry(
            value=value,
            source="public_record_adapter",
            tier=SourceTier.TIER_1,
            verified_status=VerifiedStatus.VERIFIED,
            mapper_version="public_record_adapter/v1",
        )
    for field_name in [
        "occupancy_strategy", "owner_occupied_unit_count", "estimated_monthly_rent", "rent_confidence_override",
        "insurance", "down_payment_percent", "interest_rate", "loan_term_years", "vacancy_rate",
        "condition_profile_override", "condition_confirmed", "capex_lane_override", "capex_confirmed",
        "repair_capex_budget", "strategy_intent", "hold_period_years", "risk_tolerance",
    ]:
        value = getattr(assumptions, field_name, None)
        if value is None:
            continue
        provenance[field_name] = _provenance_entry(
            value=value,
            source="public_record_adapter",
            tier=SourceTier.TIER_3,
            verified_status=VerifiedStatus.ESTIMATED,
            mapper_version="public_record_adapter/v1",
        )
    return provenance


def _manual_override_field_provenance(overrides: dict[str, object]) -> dict[str, CanonicalFieldProvenance]:
    provenance: dict[str, CanonicalFieldProvenance] = {}
    for key, value in overrides.items():
        if value in (None, "", []):
            continue
        provenance[key] = _provenance_entry(
            value=value,
            source="manual override",
            tier=SourceTier.TIER_1,
            verified_status=VerifiedStatus.USER_CONFIRMED,
            mapper_version="manual_input_adapter/v1",
        )
    return provenance


def _merge_field_provenance(
    base: dict[str, CanonicalFieldProvenance],
    updates: dict[str, CanonicalFieldProvenance],
) -> dict[str, CanonicalFieldProvenance]:
    merged = dict(base)
    merged.update(updates)
    return merged


def _provenance_entry(
    *,
    value: object,
    source: str,
    tier: SourceTier,
    verified_status: VerifiedStatus,
    mapper_version: str,
    confidence: float = 0.9,
) -> CanonicalFieldProvenance:
    return CanonicalFieldProvenance(
        value=value,
        source=source,
        source_tier=tier,
        verified_status=verified_status,
        confidence=confidence,
        mapper_version=mapper_version,
    )


def _coverage(category: str, value: object) -> SourceCoverageItem:
    if value is None or value == "" or value == 0:
        return SourceCoverageItem(category=category, status=InputCoverageStatus.MISSING)
    return SourceCoverageItem(category=category, status=InputCoverageStatus.SOURCED)


def _list_coverage(category: str, value: list[object]) -> SourceCoverageItem:
    if not value:
        return SourceCoverageItem(category=category, status=InputCoverageStatus.MISSING)
    return SourceCoverageItem(category=category, status=InputCoverageStatus.SOURCED)


def _assumption_coverage(category: str, value: object) -> SourceCoverageItem:
    if value is None or value == "" or value == 0:
        return SourceCoverageItem(category=category, status=InputCoverageStatus.MISSING)
    return SourceCoverageItem(category=category, status=InputCoverageStatus.USER_SUPPLIED, source_name="manual assumption")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _optional_occupancy_strategy(value: object) -> OccupancyStrategy | None:
    text = _optional_str(value)
    try:
        return OccupancyStrategy(text) if text is not None else None
    except ValueError:
        return None


def _coalesce_float(left: object, right: float | None) -> float | None:
    return _optional_float(left) if left is not None else right


def _coalesce_int(left: object, right: int | None) -> int | None:
    return _optional_int(left) if left is not None else right


def _coalesce_str(left: object, right: str | None) -> str | None:
    return _optional_str(left) if left is not None else right


def _coalesce_bool(left: object, right: bool | None) -> bool | None:
    return _optional_bool(left) if left is not None else right


def _coalesce_occupancy_strategy(left: object, right: OccupancyStrategy | None) -> OccupancyStrategy | None:
    return _optional_occupancy_strategy(left) if left is not None else right


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
        if isinstance(raw, bool):
            coerced[key] = raw
            continue
        if raw in {None, ""}:
            coerced[key] = None
            continue
        text = str(raw).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            coerced[key] = True
        elif text in {"false", "0", "no", "n"}:
            coerced[key] = False
        else:
            coerced[key] = None
    return coerced


def _coerce_document_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

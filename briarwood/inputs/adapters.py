from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from briarwood.listing_intake.schemas import NormalizedPropertyData
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.schemas import (
    CanonicalPropertyData,
    EvidenceMode,
    InputCoverageStatus,
    MarketLocationSignals,
    PropertyFacts,
    SourceCoverageItem,
    SourceMetadata,
    UserAssumptions,
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
            market_price_to_rent_benchmark=_optional_float(payload.get("market_price_to_rent_benchmark")),
        )
        assumptions = UserAssumptions(
            estimated_monthly_rent=_optional_float(payload.get("estimated_monthly_rent")),
            insurance=_optional_float(payload.get("insurance")),
            down_payment_percent=_optional_float(payload.get("down_payment_percent")),
            interest_rate=_optional_float(payload.get("interest_rate")),
            loan_term_years=_optional_int(payload.get("loan_term_years")),
            vacancy_rate=_optional_float(payload.get("vacancy_rate")),
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
            estimated_monthly_rent=_coalesce_float(overrides.get("estimated_monthly_rent"), canonical.user_assumptions.estimated_monthly_rent),
            insurance=_coalesce_float(overrides.get("insurance"), canonical.user_assumptions.insurance),
            down_payment_percent=_coalesce_float(overrides.get("down_payment_percent"), canonical.user_assumptions.down_payment_percent),
            interest_rate=_coalesce_float(overrides.get("interest_rate"), canonical.user_assumptions.interest_rate),
            loan_term_years=_coalesce_int(overrides.get("loan_term_years"), canonical.user_assumptions.loan_term_years),
            vacancy_rate=_coalesce_float(overrides.get("vacancy_rate"), canonical.user_assumptions.vacancy_rate),
        )
        coverage = dict(canonical.source_metadata.source_coverage)
        for category, key in {
            "rent_estimate": "estimated_monthly_rent",
            "insurance_estimate": "insurance",
            "financing_down_payment": "down_payment_percent",
            "financing_interest_rate": "interest_rate",
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
        "insurance_estimate": _assumption_coverage("insurance_estimate", assumptions.insurance),
        "school_signal": _coverage("school_signal", market_signals.school_rating),
        "flood_risk": _coverage("flood_risk", market_signals.flood_risk),
        "liquidity_signal": _coverage("liquidity_signal", market_signals.town_population_trend),
        "market_history": _coverage("market_history", market_signals.town_price_trend),
        "scarcity_inputs": SourceCoverageItem("scarcity_inputs", InputCoverageStatus.MISSING),
        "comp_support": SourceCoverageItem("comp_support", InputCoverageStatus.MISSING),
        "financing_down_payment": _assumption_coverage("financing_down_payment", assumptions.down_payment_percent),
        "financing_interest_rate": _assumption_coverage("financing_interest_rate", assumptions.interest_rate),
    }
    return SourceMetadata(
        evidence_mode=evidence_mode,
        source_coverage=coverage,
        provenance=provenance,
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


def _coalesce_float(left: object, right: float | None) -> float | None:
    return _optional_float(left) if left is not None else right


def _coalesce_int(left: object, right: int | None) -> int | None:
    return _optional_int(left) if left is not None else right

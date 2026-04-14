from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from briarwood.schemas import (
    CanonicalFieldProvenance,
    CanonicalPropertyData,
    EvidenceMode,
    InferenceMethod,
    InputCoverageStatus,
    MarketLocationSignals,
    PropertyFacts,
    PropertyInput,
    SourceCoverageItem,
    SourceMetadata,
    SourceTier,
    UserAssumptions,
    VerifiedStatus,
    baseline_confidence_for,
)


@dataclass(slots=True)
class PriceHistoryEntry:
    date: str | None = None
    event: str | None = None
    price: float | None = None


@dataclass(slots=True)
class TaxHistoryEntry:
    year: int | None = None
    tax_paid: float | None = None
    assessed_value: float | None = None


@dataclass(slots=True)
class ListingRawData:
    source: str
    intake_mode: str
    source_url: str | None = None
    address: str | None = None
    price: float | None = None
    beds: int | None = None
    baths: float | None = None
    sqft: int | None = None
    lot_sqft: int | None = None
    property_type: str | None = None
    architectural_style: str | None = None
    condition_profile: str | None = None
    capex_lane: str | None = None
    year_built: int | None = None
    stories: float | None = None
    garage_spaces: int | None = None
    days_on_market: int | None = None
    price_per_sqft: float | None = None
    hoa_monthly: float | None = None
    taxes_annual: float | None = None
    listing_description: str | None = None
    tax_history: list[TaxHistoryEntry] = field(default_factory=list)
    price_history: list[PriceHistoryEntry] = field(default_factory=list)
    raw_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NormalizedPropertyData:
    address: str | None = None
    price: float | None = None
    beds: int | None = None
    baths: float | None = None
    sqft: int | None = None
    lot_sqft: int | None = None
    property_type: str | None = None
    architectural_style: str | None = None
    condition_profile: str | None = None
    capex_lane: str | None = None
    year_built: int | None = None
    stories: float | None = None
    garage_spaces: int | None = None
    days_on_market: int | None = None
    price_per_sqft: float | None = None
    hoa_monthly: float | None = None
    taxes_annual: float | None = None
    listing_description: str | None = None
    source_url: str | None = None
    town: str | None = None
    state: str | None = None
    county: str | None = None
    zip_code: str | None = None
    source: str | None = None
    tax_history: list[TaxHistoryEntry] = field(default_factory=list)
    price_history: list[PriceHistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_canonical_input(self, *, property_id: str = "listing-intake") -> CanonicalPropertyData:
        lot_size_acres = None
        if self.lot_sqft is not None:
            lot_size_acres = round(self.lot_sqft / 43560, 4)
        listing_date = _infer_listing_date(self.price_history, self.days_on_market)
        facts = PropertyFacts(
            address=self.address or "Unknown Address",
            town=self.town or "Unknown",
            state=self.state or "Unknown",
            county=self.county,
            zip_code=self.zip_code,
            beds=self.beds,
            baths=self.baths,
            sqft=self.sqft,
            lot_size=lot_size_acres,
            property_type=self.property_type,
            architectural_style=self.architectural_style,
            condition_profile=self.condition_profile,
            capex_lane=self.capex_lane,
            year_built=self.year_built,
            stories=self.stories,
            garage_spaces=self.garage_spaces,
            purchase_price=self.price,
            taxes=self.taxes_annual,
            monthly_hoa=self.hoa_monthly,
            days_on_market=self.days_on_market,
            listing_date=listing_date,
            listing_description=self.listing_description,
            source_url=self.source_url,
            price_history=[asdict(entry) for entry in self.price_history],
            sale_history=[],
        )
        market_signals = MarketLocationSignals()
        assumptions = UserAssumptions()
        source_coverage = {
            "address": _coverage("address", facts.address, source_name=self.source or "listing_text"),
            "price_ask": _coverage("price_ask", facts.purchase_price, source_name=self.source or "listing_text"),
            "beds_baths": _coverage(
                "beds_baths",
                facts.beds if facts.beds is not None else facts.baths,
                source_name=self.source or "listing_text",
            ),
            "sqft": _coverage("sqft", facts.sqft, source_name=self.source or "listing_text"),
            "lot_size": _coverage("lot_size", facts.lot_size, source_name=self.source or "listing_text"),
            "taxes": _coverage("taxes", facts.taxes, source_name=self.source or "listing_text"),
            "hoa": _coverage("hoa", facts.monthly_hoa, source_name=self.source or "listing_text"),
            "sale_history": SourceCoverageItem("sale_history", InputCoverageStatus.MISSING),
            "listing_history": _list_coverage("listing_history", facts.price_history, source_name=self.source or "listing_text"),
            "rent_estimate": SourceCoverageItem("rent_estimate", InputCoverageStatus.MISSING),
            "insurance_estimate": SourceCoverageItem("insurance_estimate", InputCoverageStatus.MISSING),
            "school_signal": SourceCoverageItem("school_signal", InputCoverageStatus.MISSING),
            "flood_risk": SourceCoverageItem("flood_risk", InputCoverageStatus.MISSING),
            "liquidity_signal": SourceCoverageItem("liquidity_signal", InputCoverageStatus.MISSING),
            "market_history": SourceCoverageItem("market_history", InputCoverageStatus.MISSING),
            "scarcity_inputs": SourceCoverageItem("scarcity_inputs", InputCoverageStatus.MISSING),
            "comp_support": SourceCoverageItem("comp_support", InputCoverageStatus.MISSING),
            "financing_down_payment": SourceCoverageItem("financing_down_payment", InputCoverageStatus.MISSING),
            "financing_interest_rate": SourceCoverageItem("financing_interest_rate", InputCoverageStatus.MISSING),
        }
        metadata = SourceMetadata(
            evidence_mode=EvidenceMode.LISTING_ASSISTED,
            source_coverage=source_coverage,
            provenance=[f"{self.source or 'listing_text'}:{self.source_url or 'text'}"],
            field_provenance=_listing_field_provenance(self, facts),
            mapper_version="listing_intake/v1",
        )
        return CanonicalPropertyData(
            property_id=property_id,
            facts=facts,
            market_signals=market_signals,
            user_assumptions=assumptions,
            source_metadata=metadata,
        )

    def to_property_input(self, *, property_id: str = "listing-intake") -> PropertyInput:
        return PropertyInput.from_canonical(self.to_canonical_input(property_id=property_id))


@dataclass(slots=True)
class ListingIntakeResult:
    intake_mode: str
    raw_extracted_data: ListingRawData
    normalized_property_data: NormalizedPropertyData
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _coverage(category: str, value: object, *, source_name: str | None = None) -> SourceCoverageItem:
    if value is None or value == "" or value == 0:
        return SourceCoverageItem(category=category, status=InputCoverageStatus.MISSING, source_name=source_name)
    return SourceCoverageItem(category=category, status=InputCoverageStatus.SOURCED, source_name=source_name)


def _list_coverage(category: str, value: list[object], *, source_name: str | None = None) -> SourceCoverageItem:
    if not value:
        return SourceCoverageItem(category=category, status=InputCoverageStatus.MISSING, source_name=source_name)
    return SourceCoverageItem(category=category, status=InputCoverageStatus.SOURCED, source_name=source_name)


def _infer_listing_date(
    price_history: list[PriceHistoryEntry],
    days_on_market: int | None,
) -> str | None:
    if days_on_market is not None:
        return (date.today() - timedelta(days=days_on_market)).isoformat()

    dated_entries = []
    for entry in price_history:
        parsed_date = _parse_date(entry.date)
        if parsed_date is None:
            continue
        event = (entry.event or "").lower()
        if "list" in event:
            dated_entries.append(parsed_date)
    if dated_entries:
        return max(dated_entries).isoformat()
    return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _listing_field_provenance(
    normalized: NormalizedPropertyData,
    facts: PropertyFacts,
) -> dict[str, CanonicalFieldProvenance]:
    """Build per-field provenance with extraction-method-aware confidence.

    Phase 3 replaces a single hardcoded 0.88 with per-field classification:
    most listing-intake fields are EXTRACTED verbatim, ``lot_size`` is DERIVED
    (unit conversion from ``lot_sqft``), and ``listing_date`` is INFERRED when
    the normalizer fell back to ``today - days_on_market`` rather than a real
    list event in the price history.
    """

    source_name = normalized.source or "listing_text"
    all_fields = [
        "address", "town", "state", "county", "zip_code", "beds", "baths", "sqft", "lot_size",
        "property_type", "architectural_style", "condition_profile", "capex_lane", "year_built", "stories",
        "garage_spaces", "purchase_price", "taxes", "monthly_hoa", "days_on_market", "listing_date",
        "listing_description", "source_url",
    ]
    derived_fields = {"lot_size"}  # computed from lot_sqft via unit conversion
    listing_date_method = _classify_listing_date_method(normalized)

    provenance: dict[str, CanonicalFieldProvenance] = {}
    for field_name in all_fields:
        value = getattr(facts, field_name, None)
        if value is None:
            continue

        if field_name == "listing_date":
            method = listing_date_method
        elif field_name in derived_fields:
            method = InferenceMethod.DERIVED
        else:
            method = InferenceMethod.EXTRACTED

        verified = {
            InferenceMethod.EXTRACTED: VerifiedStatus.VERIFIED,
            InferenceMethod.DERIVED: VerifiedStatus.VERIFIED,
            InferenceMethod.USER_PROVIDED: VerifiedStatus.USER_CONFIRMED,
            InferenceMethod.INFERRED: VerifiedStatus.ESTIMATED,
            InferenceMethod.DEFAULTED: VerifiedStatus.UNVERIFIED,
        }[method]

        provenance[field_name] = CanonicalFieldProvenance(
            value=value,
            source=source_name,
            source_tier=SourceTier.TIER_1,
            verified_status=verified,
            confidence=baseline_confidence_for(method),
            mapper_version="listing_intake/v1",
            inference_method=method,
        )
    return provenance


def _classify_listing_date_method(normalized: NormalizedPropertyData) -> InferenceMethod:
    """EXTRACTED if listing_date came from a real list event, else INFERRED."""

    for entry in normalized.price_history or []:
        event = (entry.event or "").lower()
        if "list" in event and _parse_date(entry.date) is not None:
            return InferenceMethod.EXTRACTED
    return InferenceMethod.INFERRED

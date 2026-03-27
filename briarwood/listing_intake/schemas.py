from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from briarwood.schemas import PropertyInput


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
    year_built: int | None = None
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
    year_built: int | None = None
    days_on_market: int | None = None
    price_per_sqft: float | None = None
    hoa_monthly: float | None = None
    taxes_annual: float | None = None
    listing_description: str | None = None
    source_url: str | None = None
    town: str | None = None
    state: str | None = None
    zip_code: str | None = None
    source: str | None = None
    tax_history: list[TaxHistoryEntry] = field(default_factory=list)
    price_history: list[PriceHistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_property_input(self, *, property_id: str = "listing-intake") -> PropertyInput:
        lot_size_acres = None
        if self.lot_sqft is not None:
            lot_size_acres = round(self.lot_sqft / 43560, 4)
        return PropertyInput(
            property_id=property_id,
            address=self.address or "Unknown Address",
            town=self.town or "Unknown",
            state=self.state or "Unknown",
            beds=self.beds or 0,
            baths=self.baths or 0.0,
            sqft=self.sqft or 0,
            lot_size=lot_size_acres,
            year_built=self.year_built,
            purchase_price=self.price,
            taxes=self.taxes_annual,
            days_on_market=self.days_on_market,
        )


@dataclass(slots=True)
class ListingIntakeResult:
    intake_mode: str
    raw_extracted_data: ListingRawData
    normalized_property_data: NormalizedPropertyData
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

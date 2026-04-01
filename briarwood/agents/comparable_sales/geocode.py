from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from briarwood.agents.comparable_sales.schemas import ActiveListingRecord, ComparableSale


@dataclass(slots=True)
class GeocodeResult:
    latitude: float | None
    longitude: float | None
    confidence: float = 0.0
    source: str | None = None


class AddressGeocoder(Protocol):
    def geocode(self, *, address: str, town: str, state: str) -> GeocodeResult | None:
        ...


def enrich_sale_with_geocode(sale: ComparableSale, geocoder: AddressGeocoder) -> ComparableSale:
    if sale.latitude is not None and sale.longitude is not None:
        return sale
    result = geocoder.geocode(address=sale.address, town=sale.town, state=sale.state)
    if result is None or result.latitude is None or result.longitude is None:
        return sale
    return sale.model_copy(update={"latitude": result.latitude, "longitude": result.longitude})


def enrich_listing_with_geocode(listing: ActiveListingRecord, geocoder: AddressGeocoder) -> ActiveListingRecord:
    if listing.latitude is not None and listing.longitude is not None:
        return listing
    result = geocoder.geocode(address=listing.address, town=listing.town, state=listing.state)
    if result is None or result.latitude is None or result.longitude is None:
        return listing
    return listing.model_copy(update={"latitude": result.latitude, "longitude": result.longitude})

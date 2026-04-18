from __future__ import annotations

import re

from briarwood.data_quality.normalizers import infer_county, normalize_state, normalize_town
from briarwood.listing_intake.schemas import (
    ListingIntakeResult,
    ListingRawData,
    NormalizedPropertyData,
)


def normalize_listing(raw_data: ListingRawData, warnings: list[str] | None = None) -> ListingIntakeResult:
    warnings = list(warnings or [])
    town, state, zip_code = _parse_location(raw_data.address)
    county = _infer_county(town=town, state=state, zip_code=zip_code)
    price_per_sqft = _compute_price_per_sqft(raw_data.price, raw_data.sqft)

    normalized = NormalizedPropertyData(
        address=raw_data.address,
        price=raw_data.price,
        beds=raw_data.beds,
        baths=raw_data.baths,
        sqft=raw_data.sqft,
        lot_sqft=raw_data.lot_sqft,
        property_type=raw_data.property_type,
        architectural_style=raw_data.architectural_style,
        condition_profile=raw_data.condition_profile,
        capex_lane=raw_data.capex_lane,
        year_built=raw_data.year_built,
        stories=raw_data.stories,
        garage_spaces=raw_data.garage_spaces,
        days_on_market=raw_data.days_on_market,
        price_per_sqft=price_per_sqft,
        hoa_monthly=raw_data.hoa_monthly,
        taxes_annual=raw_data.taxes_annual,
        listing_description=raw_data.listing_description,
        source_url=raw_data.source_url,
        town=town,
        state=state,
        county=county,
        zip_code=zip_code,
        source=raw_data.source,
        tax_history=raw_data.tax_history,
        price_history=raw_data.price_history,
    )

    missing_fields = [
        field_name
        for field_name, value in {
            "address": normalized.address,
            "price": normalized.price,
            "beds": normalized.beds,
            "baths": normalized.baths,
            "sqft": normalized.sqft,
            "property_type": normalized.property_type,
            "year_built": normalized.year_built,
            "days_on_market": normalized.days_on_market,
            "price_per_sqft": normalized.price_per_sqft,
            "hoa_monthly": normalized.hoa_monthly,
        }.items()
        if value is None or value == ""
    ]

    if raw_data.intake_mode == "url_intake" and _looks_url_only(raw_data):
        warnings.append("URL-only intake stores source metadata and inferred address text, but does not extract real listing fields.")
    if normalized.address and (normalized.town is None or normalized.state is None):
        warnings.append("Address was found, but town/state could not be parsed cleanly.")

    return ListingIntakeResult(
        intake_mode=raw_data.intake_mode,
        raw_extracted_data=raw_data,
        normalized_property_data=normalized,
        missing_fields=missing_fields,
        warnings=warnings,
    )


def _compute_price_per_sqft(price: float | None, sqft: int | None) -> float | None:
    if price is None or sqft in (None, 0):
        return None
    return round(price / sqft, 2)


def _parse_location(address: str | None) -> tuple[str | None, str | None, str | None]:
    if not address:
        return None, None, None
    match = re.search(r",\s*([^,]+),\s*([A-Z]{2})(?:\s+(\d{5}))?$", address)
    if not match:
        state_match = re.search(r"\b([A-Z]{2})(?:\s+(\d{5}))?$", address)
        if state_match:
            state = normalize_state(state_match.group(1).strip())
            zip_code = state_match.group(2)
            prefix = address[: state_match.start()].strip(" ,")
            words = [part for part in re.split(r"\s+", prefix) if part]
            if state and words:
                for idx in range(len(words)):
                    candidate_town = normalize_town(" ".join(words[idx:]))
                    if candidate_town and infer_county(town=candidate_town, state=state):
                        return candidate_town, state, zip_code
                candidate_town = normalize_town(words[-1])
                if candidate_town:
                    return candidate_town, state, zip_code
    if not match:
        return None, None, None
    town = normalize_town(match.group(1).strip())
    state = normalize_state(match.group(2).strip())
    return town, state, match.group(3)


def _infer_county(*, town: str | None, state: str | None, zip_code: str | None) -> str | None:
    return infer_county(town=town, state=state, zip_code=zip_code)


def _looks_url_only(raw_data: ListingRawData) -> bool:
    return (
        raw_data.price is None
        and raw_data.beds is None
        and raw_data.baths is None
        and raw_data.sqft is None
        and raw_data.year_built is None
        and raw_data.hoa_monthly is None
        and raw_data.taxes_annual is None
        and not raw_data.tax_history
        and not raw_data.price_history
    )

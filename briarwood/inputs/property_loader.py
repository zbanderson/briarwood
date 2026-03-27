from __future__ import annotations

import json
from pathlib import Path

from briarwood.listing_intake.schemas import ListingIntakeResult, NormalizedPropertyData
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.schemas import PropertyInput


def load_property_from_json(path: str | Path) -> PropertyInput:
    data = json.loads(Path(path).read_text())
    return PropertyInput(**data)


def load_property_from_normalized_listing(
    normalized_property_data: NormalizedPropertyData,
    *,
    property_id: str = "listing-intake",
) -> PropertyInput:
    return normalized_property_data.to_property_input(property_id=property_id)


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
    service = intake_service or ListingIntakeService()
    intake_result = service.intake_text(text, source_url=source_url)
    return load_property_from_listing_intake_result(
        intake_result,
        property_id=property_id,
    )

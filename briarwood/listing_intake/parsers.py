from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from briarwood.data_sources.searchapi_zillow_client import SearchApiZillowClient
from briarwood.listing_intake.schemas import (
    ListingRawData,
    PriceHistoryEntry,
    TaxHistoryEntry,
)


@dataclass(slots=True)
class ListingParser:
    source_name: str

    def can_parse(self, source: str) -> bool:
        raise NotImplementedError

    def parse(self, source: str) -> tuple[ListingRawData, list[str]]:
        raise NotImplementedError


class ZillowUrlParser(ListingParser):
    def __init__(self, *, client: SearchApiZillowClient | None = None) -> None:
        super().__init__(source_name="zillow")
        self.client = client or SearchApiZillowClient()

    def can_parse(self, source: str) -> bool:
        return source.strip().startswith(("http://", "https://")) and "zillow.com" in source

    def parse(self, source: str) -> tuple[ListingRawData, list[str]]:
        parsed = urlparse(source.strip())
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        slug = ""
        if parts:
            slug = parts[1] if parts[0].lower() == "homedetails" and len(parts) > 1 else parts[0]
        address = _address_from_slug(slug)
        if self.client.is_configured:
            response = self.client.lookup_listing(source_url=source.strip(), address_hint=address)
            if response.ok and response.normalized_payload:
                raw = self.client.to_listing_raw_data(
                    response.normalized_payload,
                    source_url=source.strip(),
                    fallback_address=address,
                )
                warnings = [
                    "Live Zillow hydration succeeded via SearchAPI.",
                ]
                if raw.sqft is None or raw.listing_description is None:
                    warnings.append(
                        "Live Zillow hydration returned partial field coverage; pasted listing text can still add richer description and history detail."
                    )
                return raw, warnings
            warnings = [
                f"SearchAPI Zillow hydration failed; falling back to URL metadata only ({response.error})."
            ]
        else:
            warnings = [
                "URL intake is metadata-only unless SearchAPI Zillow is configured.",
            ]
        warnings.append(
            "Provide pasted listing text to extract richer fields like description, HOA, tax history, and price history."
        )
        raw = ListingRawData(
            source=self.source_name,
            intake_mode="url_intake",
            source_url=source.strip(),
            address=address,
        )
        return raw, warnings


class ZillowTextParser(ListingParser):
    def __init__(self) -> None:
        super().__init__(source_name="zillow")

    def can_parse(self, source: str) -> bool:
        text = source.lower()
        return "zillow" in text or any(
            token in text for token in ("beds", "baths", "sqft", "what's special", "facts & features")
        )

    def parse(self, source: str) -> tuple[ListingRawData, list[str]]:
        text = source.replace("\r", "")
        raw = ListingRawData(
            source=self.source_name,
            intake_mode="text_intake",
            address=_extract_address(text),
            price=_extract_price(text),
            beds=_extract_beds(text),
            baths=_extract_baths(text),
            sqft=_extract_sqft(text),
            lot_sqft=_extract_lot_sqft(text),
            property_type=_extract_property_type(text),
            architectural_style=_extract_architectural_style(text),
            condition_profile=_extract_condition_profile(text),
            capex_lane=_extract_capex_lane(text),
            year_built=_extract_year_built(text),
            stories=_extract_stories(text),
            garage_spaces=_extract_garage_spaces(text),
            days_on_market=_extract_days_on_market(text),
            hoa_monthly=_extract_hoa(text),
            taxes_annual=_extract_annual_taxes(text),
            listing_description=_extract_description(text),
            tax_history=_extract_tax_history(text),
            price_history=_extract_price_history(text),
            raw_text=source,
        )
        warnings: list[str] = []
        if raw.sqft is None:
            warnings.append("Living area square footage was not found in the pasted listing text.")
        if raw.days_on_market is None and re.search(r"\bminutes?\s+on\s+zillow\b", text, re.IGNORECASE):
            warnings.append("Listing shows minutes on Zillow rather than a day count; days_on_market was left null.")
        if raw.hoa_monthly is None and re.search(r"Has HOA:\s*No", text, re.IGNORECASE):
            warnings.append("HOA is marked as not present; hoa_monthly remains null unless an explicit amount is shown.")
        if not raw.tax_history:
            warnings.append("Structured public tax history was not found in the pasted listing text.")
        if not raw.price_history:
            warnings.append("Structured price history was not found in the pasted listing text.")
        return raw, warnings


def get_default_parsers() -> list[ListingParser]:
    return [
        ZillowUrlParser(),
        ZillowTextParser(),
    ]


def _address_from_slug(slug: str) -> str | None:
    if not slug:
        return None
    cleaned = slug.replace("-", " ")
    cleaned = re.sub(r"\b\d+_zpid\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else None


def _extract_address(text: str) -> str | None:
    patterns = [
        r"^\s*([0-9][^\n]+,\s*[A-Za-z .'-]+,\s*[A-Z]{2}\s+\d{5})",
        r"^\s*([0-9][^\n]+,\s*[A-Za-z .'-]+,\s*[A-Z]{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _extract_price(text: str) -> float | None:
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\$[\d,]+", stripped):
            return _money_to_float(stripped)
    labeled = re.search(r"Price\s*\$([\d,]+)", text, re.IGNORECASE)
    if labeled:
        return _money_to_float(labeled.group(1))
    return None


def _extract_beds(text: str) -> int | None:
    patterns = [
        r"^\s*(\d+)\s*\n\s*beds?\b",
        r"Bedrooms:\s*(\d+)",
        r"(\d+)\s*bd\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _extract_baths(text: str) -> float | None:
    patterns = [
        r"^\s*(\d+(?:\.\d+)?)\s*\n\s*baths?\b",
        r"Bathrooms:\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*ba\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return float(match.group(1))
    return None


def _extract_sqft(text: str) -> int | None:
    patterns = [
        r"Living area[: ]+\s*([\d,]+)\s*sq\.?\s*ft\.?",
        r"Interior livable area[: ]+\s*([\d,]+)\s*sq\.?\s*ft\.?",
        r"^\s*([\d,]+)\s*\n\s*sqft\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).replace(",", "")
            if value != "--":
                return int(value)
    for line in text.splitlines():
        lowered = line.lower()
        if "sqft" in lowered and "lot" not in lowered:
            match = re.search(r"([\d,]+)\s*sqft", line, re.IGNORECASE)
            if match:
                return int(match.group(1).replace(",", ""))
    return None


def _extract_lot_sqft(text: str) -> int | None:
    patterns = [
        r"Lot size[: ]+\s*([\d,]+)\s*sqft",
        r"([\d,]+)\s*Square Feet Lot",
        r"Lot\s*[\n ]*Size:\s*([\d,]+)\s*Square Feet",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _extract_property_type(text: str) -> str | None:
    patterns = [
        r"Property subtype:\s*([^\n]+)",
        r"Property type:\s*([^\n]+)",
        r"Home type:\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _normalize_property_type(match.group(1).strip())
    lowered = text.lower()
    for property_type in ("single family residence", "single family", "condo", "townhouse", "multi family", "co-op"):
        if property_type in lowered:
            return _normalize_property_type(property_type)
    return None


def _extract_year_built(text: str) -> int | None:
    patterns = [
        r"Built in (\d{4})",
        r"Year built:\s*(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_architectural_style(text: str) -> str | None:
    patterns = [
        r"Architectural style:\s*([^\n]+)",
        r"Style:\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip().title()
    lowered = text.lower()
    for style in ("ranch", "colonial", "cape", "victorian", "contemporary", "craftsman", "bungalow"):
        if f"{style} style" in lowered:
            return style.title()
    return None


def _extract_stories(text: str) -> float | None:
    match = re.search(r"Stories:\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_condition_profile(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ("gut renovated", "fully renovated", "completely renovated", "brand new interior")):
        return "renovated"
    if any(token in lowered for token in ("updated", "renovated", "freshly painted", "new sink", "new kitchen", "new bath", "move in ready")):
        return "updated"
    if any(token in lowered for token in ("needs work", "as is", "fixer", "contractor special", "tear down", "rehab")):
        return "needs_work"
    if any(token in lowered for token in ("original condition", "dated", "maintained", "well kept")):
        return "maintained"
    return None


def _extract_capex_lane(text: str) -> str | None:
    condition = _extract_condition_profile(text)
    if condition == "renovated":
        return "light"
    if condition in {"updated", "maintained"}:
        return "moderate"
    if condition == "needs_work":
        return "heavy"
    return None


def _extract_garage_spaces(text: str) -> int | None:
    patterns = [
        r"Attached garage spaces:\s*(\d+)",
        r"Garage spaces:\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_days_on_market(text: str) -> int | None:
    days_match = re.search(r"(\d+)\s+days?\s+on\s+Zillow", text, re.IGNORECASE)
    if days_match:
        return int(days_match.group(1))
    minutes_match = re.search(r"(\d+)\s+minutes?\s+on\s+Zillow", text, re.IGNORECASE)
    if minutes_match:
        return 0
    date_match = re.search(r"Date on market:\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    if date_match:
        month, day, year = [int(part) for part in date_match.group(1).split("/")]
        listing_date = date(year, month, day)
        return max((date.today() - listing_date).days, 0)
    return None


def _extract_hoa(text: str) -> float | None:
    explicit = re.search(r"\$([\d,]+)\s*HOA", text, re.IGNORECASE)
    if explicit:
        return _money_to_float(explicit.group(1))
    explicit_monthly = re.search(r"HOA[: ]+\$?([\d,]+)\s*/?\s*(month|mo)", text, re.IGNORECASE)
    if explicit_monthly:
        return _money_to_float(explicit_monthly.group(1))
    if re.search(r"Has HOA:\s*No", text, re.IGNORECASE):
        return 0.0
    return None


def _extract_annual_taxes(text: str) -> float | None:
    match = re.search(r"Annual tax amount:\s*\$([\d,]+)", text, re.IGNORECASE)
    if match:
        return _money_to_float(match.group(1))
    if history := _extract_tax_history(text):
        return history[0].tax_paid
    return None


def _extract_description(text: str) -> str | None:
    patterns = [
        r"What's special\s*(.*?)\s*Show more",
        r"(?:Overview|Description):\s*(.*?)(?:Price history|Tax history|Facts & features|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            description = re.sub(r"\s+", " ", match.group(1)).strip()
            return description or None
    return None


def _extract_tax_history(text: str) -> list[TaxHistoryEntry]:
    entries: list[TaxHistoryEntry] = []
    table_pattern = re.compile(
        r"^\s*(\d{4})\s+\$([\d,]+)(?:\s*[+-][\d.]+%)?\s+\$([\d,]+)\s*$",
        re.MULTILINE,
    )
    for year, taxes, assessed in table_pattern.findall(text):
        entries.append(
            TaxHistoryEntry(
                year=int(year),
                tax_paid=_money_to_float(taxes),
                assessed_value=_money_to_float(assessed),
            )
        )
    if entries:
        return entries

    fallback_pattern = re.compile(
        r"(\d{4})\s+Taxes?\s+\$([\d,]+)(?:\s+Assessed value\s+\$([\d,]+))?",
        re.IGNORECASE,
    )
    for year, taxes, assessed in fallback_pattern.findall(text):
        entries.append(
            TaxHistoryEntry(
                year=int(year),
                tax_paid=_money_to_float(taxes),
                assessed_value=_money_to_float(assessed) if assessed else None,
            )
        )
    return entries


def _extract_price_history(text: str) -> list[PriceHistoryEntry]:
    entries: list[PriceHistoryEntry] = []
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        inline_match = re.match(r"(\d{1,2}/\d{1,2}/\d{4})\s+(.+)", line)
        if inline_match:
            event = inline_match.group(2).strip()
            price_line = lines[index + 1] if index + 1 < len(lines) else ""
            price_match = re.search(r"\$([\d,]+)", price_line)
            if event and price_match:
                entries.append(
                    PriceHistoryEntry(
                        date=inline_match.group(1),
                        event=event,
                        price=_money_to_float(price_match.group(1)),
                    )
                )
    if entries:
        return entries

    fallback = re.compile(
        r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\s+([A-Za-z ]+)\s+\$?([\d,]+)",
        re.IGNORECASE,
    )
    for date_value, event, price in fallback.findall(text):
        entries.append(
            PriceHistoryEntry(
                date=date_value.strip(),
                event=event.strip(),
                price=_money_to_float(price),
            )
        )
    return entries


def _normalize_property_type(value: str) -> str:
    cleaned = value.replace("SingleFamily", "Single Family")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()


def _money_to_float(value: str) -> float:
    cleaned = value.replace("$", "").replace(",", "").strip()
    return float(cleaned)

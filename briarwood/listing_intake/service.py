from __future__ import annotations

from briarwood.listing_intake.normalizer import normalize_listing
from briarwood.listing_intake.parsers import (
    ListingParser,
    ZillowTextParser,
    ZillowUrlParser,
    get_default_parsers,
)
from briarwood.listing_intake.schemas import ListingIntakeResult


class ListingIntakeService:
    def __init__(self, parsers: list[ListingParser] | None = None) -> None:
        self.parsers = parsers or get_default_parsers()

    def intake(self, source: str) -> ListingIntakeResult:
        source = source.strip()
        for parser in self.parsers:
            if parser.can_parse(source):
                raw_data, warnings = parser.parse(source)
                return normalize_listing(raw_data, warnings)
        raw_data, warnings = self.parsers[-1].parse(source)
        warnings.append("Source did not clearly match a known provider; fallback text parsing was used.")
        return normalize_listing(raw_data, warnings)

    def intake_url(self, url: str) -> ListingIntakeResult:
        parser = next(
            (
                candidate
                for candidate in self.parsers
                if isinstance(candidate, ZillowUrlParser) and candidate.can_parse(url)
            ),
            ZillowUrlParser(),
        )
        raw_data, warnings = parser.parse(url)
        return normalize_listing(raw_data, warnings)

    def intake_text(self, text: str, *, source_url: str | None = None) -> ListingIntakeResult:
        parser = ZillowTextParser()
        raw_data, warnings = parser.parse(text)
        raw_data.source_url = source_url
        return normalize_listing(raw_data, warnings)

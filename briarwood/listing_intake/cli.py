from __future__ import annotations

import argparse
import json
from pathlib import Path

from briarwood.listing_intake.service import ListingIntakeService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize a listing into Briarwood property intake data. "
            "Zillow URL intake is metadata-only; Briarwood does not fetch or scrape live Zillow pages."
        )
    )
    parser.add_argument(
        "input_value",
        help=(
            "A Zillow URL or a path to a text file containing pasted listing text. "
            "For Zillow URLs, only the URL metadata is parsed unless listing text is provided separately."
        ),
    )
    return parser.parse_args()


def _load_input(input_value: str) -> str:
    path = Path(input_value)
    if path.exists():
        return path.read_text()
    return input_value


def main() -> None:
    args = parse_args()
    service = ListingIntakeService()
    result = service.intake(_load_input(args.input_value))
    print(
        json.dumps(
            {
                "intake_mode": result.intake_mode,
                "raw_extracted_data": result.raw_extracted_data.to_dict(),
                "normalized_property_data": result.normalized_property_data.to_dict(),
                "missing_fields": result.missing_fields,
                "warnings": result.warnings,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

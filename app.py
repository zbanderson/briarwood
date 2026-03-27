import argparse
from pathlib import Path

from briarwood.runner import (
    format_intake_preview,
    format_report,
    preview_intake_from_listing_text,
    preview_intake_from_url,
    run_report,
    run_report_from_listing_text,
    write_report_html,
)
from briarwood.settings import CostValuationSettings
from briarwood.settings import DEFAULT_APP_SETTINGS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Briarwood property report.")
    parser.add_argument(
        "property_path",
        nargs="?",
        default=None,
        help="Path to a property JSON file.",
    )
    parser.add_argument(
        "--listing-text-file",
        help="Path to a text file containing pasted listing text for text_intake mode.",
    )
    parser.add_argument(
        "--source-url",
        help="Optional source URL to associate with listing text intake.",
    )
    parser.add_argument(
        "--property-id",
        help="Optional property id override, especially useful for listing text intake.",
    )
    parser.add_argument(
        "--preview-intake",
        action="store_true",
        help="Preview the canonical listing intake object without running valuation or tear sheet generation.",
    )
    parser.add_argument(
        "--debug-raw",
        action="store_true",
        help="Include raw extracted listing fields in intake preview output.",
    )
    parser.add_argument(
        "--loan-term-years",
        type=int,
        help="Override the mortgage loan term used by the cost / valuation module.",
    )
    parser.add_argument(
        "--default-vacancy-rate",
        type=float,
        help="Override the default vacancy rate when the property file does not include one.",
    )
    parser.add_argument(
        "--html-out",
        help="Write a tear sheet HTML file to this path.",
    )
    return parser.parse_args()


def build_cost_settings(args: argparse.Namespace) -> CostValuationSettings | None:
    overrides: dict[str, float | int] = {}
    if args.loan_term_years is not None:
        overrides["loan_term_years"] = args.loan_term_years
    if args.default_vacancy_rate is not None:
        overrides["default_vacancy_rate"] = args.default_vacancy_rate
    if not overrides:
        return None
    return CostValuationSettings(**overrides)


def main() -> None:
    args = parse_args()
    cost_settings = build_cost_settings(args)
    report_source_label: str

    if args.preview_intake:
        if args.listing_text_file:
            listing_text_path = Path(args.listing_text_file)
            listing_text = listing_text_path.read_text()
            intake_result = preview_intake_from_listing_text(
                listing_text,
                source_url=args.source_url,
            )
        elif args.source_url:
            intake_result = preview_intake_from_url(args.source_url)
        else:
            raise SystemExit("preview mode requires --listing-text-file or --source-url")

        print()
        print(format_intake_preview(intake_result, include_raw=args.debug_raw))
        return

    if args.listing_text_file:
        listing_text_path = Path(args.listing_text_file)
        listing_text = listing_text_path.read_text()
        report = run_report_from_listing_text(
            listing_text,
            property_id=args.property_id or "listing-intake",
            source_url=args.source_url,
            cost_settings=cost_settings,
        )
        report_source_label = str(listing_text_path)
    else:
        property_path = Path(args.property_path or DEFAULT_APP_SETTINGS.default_property_path)
        report = run_report(
            property_path,
            cost_settings=cost_settings,
        )
        report_source_label = str(property_path)

    print()
    print(format_report(report, report_source_label))
    if args.html_out:
        output_path = write_report_html(report, args.html_out)
        print(f"tear sheet html: {output_path}")


if __name__ == "__main__":
    main()

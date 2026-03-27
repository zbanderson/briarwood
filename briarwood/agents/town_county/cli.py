from __future__ import annotations

import argparse
import json

from briarwood.agents.town_county.providers import (
    FileBackedFloodRiskProvider,
    FileBackedLiquidityProvider,
    FileBackedPopulationProvider,
    FileBackedPriceTrendProvider,
)
from briarwood.agents.town_county.service import TownCountyDataService, TownCountyOutlookResult
from briarwood.agents.town_county.sources import TownCountyOutlookRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Briarwood town/county outlook from file-backed data.")
    parser.add_argument("--town", required=True, help="Town or city name.")
    parser.add_argument("--state", required=True, help="Two-letter state code.")
    parser.add_argument("--county", help="County name without the word County.")
    parser.add_argument("--school-signal", type=float, help="Optional normalized school signal on a 0-10 scale.")
    parser.add_argument(
        "--scarcity-signal",
        type=float,
        help="Optional scarcity signal on a 0-1 scale.",
    )
    parser.add_argument("--days-on-market", type=int, help="Optional property days on market.")
    parser.add_argument(
        "--price-position",
        choices=["supported", "neutral", "stretched"],
        help="Optional pricing posture from the value module.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full outlook payload as JSON instead of the human-readable summary.",
    )
    return parser.parse_args()


def build_file_backed_service() -> TownCountyDataService:
    return TownCountyDataService(
        price_provider=FileBackedPriceTrendProvider("data/town_county/price_trends.json"),
        population_provider=FileBackedPopulationProvider("data/town_county/population_trends.json"),
        flood_provider=FileBackedFloodRiskProvider("data/town_county/flood_risk.json"),
        liquidity_provider=FileBackedLiquidityProvider("data/town_county/liquidity.json"),
    )


def format_outlook(result: TownCountyOutlookResult) -> str:
    score = result.score
    normalized = result.normalized
    lines = [
        "Briarwood Town/County Outlook",
        "",
        f"location_thesis_label: {score.location_thesis_label}",
        f"town_county_score: {score.town_county_score:.2f}",
        f"confidence: {score.confidence:.2f}",
        f"appreciation_support_view: {score.appreciation_support_view}",
        f"liquidity_view: {score.liquidity_view}",
        "",
        f"summary: {score.summary}",
        "",
        "demand_drivers:",
    ]
    lines.extend(f"- {item}" for item in score.demand_drivers or ["none"])
    lines.extend(
        [
            "",
            "demand_risks:",
        ]
    )
    lines.extend(f"- {item}" for item in score.demand_risks or ["none"])
    lines.extend(
        [
            "",
            "missing_inputs:",
        ]
    )
    lines.extend(f"- {item}" for item in normalized.missing_inputs or ["none"])
    lines.extend(
        [
            "",
            "warnings:",
        ]
    )
    lines.extend(f"- {item}" for item in normalized.warnings or ["none"])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    service = build_file_backed_service()
    result = service.build_outlook(
        TownCountyOutlookRequest(
            town=args.town,
            state=args.state.upper(),
            county=args.county,
            school_signal=args.school_signal,
            scarcity_signal=args.scarcity_signal,
            days_on_market=args.days_on_market,
            price_position=args.price_position,
        )
    )
    if args.json:
        print(
            json.dumps(
                {
                    "normalized": result.normalized.model_dump(),
                    "score": result.score.model_dump(),
                },
                indent=2,
            )
        )
        return
    print(format_outlook(result))


if __name__ == "__main__":
    main()

"""Deterministic chat-tier town-trend tailwind Scout pattern."""

from __future__ import annotations

from briarwood.claims.base import SurfacedInsight
from briarwood.routing_schema import UnifiedIntelligenceOutput
from briarwood.value_scout.patterns._unified_helpers import as_float, first_path, unified_dict

THREE_YEAR_TAILWIND_THRESHOLD = 0.10

_THREE_YEAR_PATHS: tuple[str, ...] = (
    "supporting_facts.market_value_history.three_year_change_pct",
    "market_value_history.three_year_change_pct",
)

_GEOGRAPHY_PATHS: tuple[str, ...] = (
    "supporting_facts.market_value_history.geography_name",
    "market_value_history.geography_name",
)


def detect(unified: UnifiedIntelligenceOutput) -> SurfacedInsight | None:
    """Surface a town-level appreciation tailwind above the cycle threshold."""

    data = unified_dict(unified)
    change_raw, change_path = first_path(data, _THREE_YEAR_PATHS)
    change = as_float(change_raw)
    if change is None or change < THREE_YEAR_TAILWIND_THRESHOLD:
        return None

    geography, geography_path = first_path(data, _GEOGRAPHY_PATHS)
    place = str(geography) if geography else "the town"

    return SurfacedInsight(
        headline="The town trend is doing quiet work.",
        reason=(
            f"{place} is showing about {change * 100:.1f}% three-year price "
            "growth, a tailwind that may not show up in a simple ask-versus-"
            "fair-value read."
        ),
        supporting_fields=[
            path for path in (change_path, geography_path) if path is not None
        ],
        category="town_trend_tailwind",
        confidence=round(min(0.86, 0.62 + (change - THREE_YEAR_TAILWIND_THRESHOLD) * 1.2), 3),
    )

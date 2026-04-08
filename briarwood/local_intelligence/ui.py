from __future__ import annotations

from briarwood.local_intelligence.models import TownPulseView, TownSummary


def build_town_pulse_view(summary: TownSummary) -> TownPulseView:
    """Create a lightweight UI view-model for future town and tear-sheet surfaces."""

    return TownPulseView(
        heading=f"Town Pulse: {summary.town}, {summary.state}",
        confidence_label=summary.confidence_label,
        bullish_items=list(summary.bullish_signals),
        bearish_items=list(summary.bearish_signals),
        watch_items=list(summary.watch_items),
        narrative_summary=summary.narrative_summary,
    )

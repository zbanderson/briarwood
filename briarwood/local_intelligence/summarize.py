from __future__ import annotations

from datetime import datetime, timezone

from briarwood.local_intelligence.classification import bucket_town_signals, rank_town_signals
from briarwood.local_intelligence.models import TownSignal, TownSummary


def build_town_summary(*, town: str, state: str, signals: list[TownSignal]) -> TownSummary:
    """Summarize reconciled signals into a compact, decision-first Town Pulse."""

    ranked = rank_town_signals(signals)
    buckets = bucket_town_signals(ranked)
    bullish = buckets["bullish"]
    bearish = buckets["bearish"]
    watch = buckets["watch"]

    confidence_label = _confidence_label(ranked)
    if not ranked:
        narrative = (
            f"Briarwood does not yet have enough local source material to form a confident Town Pulse for {town}, {state}."
        )
    else:
        narrative = _narrative(town, bullish, bearish, watch, confidence_label)

    return TownSummary(
        town=town,
        state=state,
        bullish_signals=[_signal_line(signal) for signal in bullish[:3]],
        bearish_signals=[_signal_line(signal) for signal in bearish[:3]],
        watch_items=[_signal_line(signal) for signal in watch[:3]],
        confidence_label=confidence_label,
        narrative_summary=narrative,
        generated_at=datetime.now(timezone.utc),
    )
def _confidence_label(signals: list[TownSignal]) -> str:
    if not signals:
        return "Low"
    average_confidence = sum(signal.confidence for signal in signals) / len(signals)
    if len(signals) >= 4 and average_confidence >= 0.72:
        return "High"
    if len(signals) >= 2 and average_confidence >= 0.52:
        return "Medium"
    return "Low"


def _narrative(
    town: str,
    bullish: list[TownSignal],
    bearish: list[TownSignal],
    watch: list[TownSignal],
    confidence_label: str,
) -> str:
    clauses: list[str] = []
    if bullish:
        clauses.append(f"{town} has {len(bullish)} constructive catalyst{'s' if len(bullish) != 1 else ''}")
    if bearish:
        clauses.append(f"{len(bearish)} local risk signal{'s' if len(bearish) != 1 else ''} need monitoring")
    if watch:
        clauses.append(f"{len(watch)} item{'s' if len(watch) != 1 else ''} remain on the watchlist")
    if not clauses:
        clauses.append(f"{town} currently has only weak or ambiguous local signals")
    return f"{'; '.join(clauses)}. Confidence is {confidence_label.lower()}."


def _signal_line(signal: TownSignal) -> str:
    status = signal.status.value.replace("_", " ")
    return f"{signal.title} ({status})"

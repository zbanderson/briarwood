from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from briarwood.local_intelligence.models import ImpactDirection, SignalStatus, TownSignal

TownPulseBucket = Literal["bullish", "bearish", "watch"]

TOWN_PULSE_BUCKET_LABELS: dict[TownPulseBucket, str] = {
    "bullish": "Catalysts",
    "bearish": "Risks",
    "watch": "Watch",
}

TOWN_PULSE_BUCKET_DEFINITIONS: dict[TownPulseBucket, str] = {
    "bullish": "Confirmed or well-supported positive local signals that could improve value, demand, liquidity, or town quality.",
    "bearish": "Confirmed or well-supported negative local signals that could hurt value, rents, liquidity, resilience, or execution.",
    "watch": "Early-stage, mixed, neutral, or lower-confidence signals that matter, but should not yet be treated as a firm catalyst or risk.",
}

LOW_CONFIDENCE_WATCH_THRESHOLD = 0.58
EARLY_STAGE_WATCH_STATUSES = {
    SignalStatus.MENTIONED,
    SignalStatus.PROPOSED,
    SignalStatus.REVIEWED,
}


def classify_town_signal(signal: TownSignal) -> TownPulseBucket:
    """Assign a Town Pulse bucket using explicit, trust-oriented rules."""

    if signal.status in EARLY_STAGE_WATCH_STATUSES or signal.confidence < LOW_CONFIDENCE_WATCH_THRESHOLD:
        return "watch"
    if signal.impact_direction == ImpactDirection.POSITIVE:
        return "bullish"
    if signal.impact_direction == ImpactDirection.NEGATIVE:
        return "bearish"
    return "watch"


def rank_town_signals(signals: list[TownSignal]) -> list[TownSignal]:
    return sorted(signals, key=town_signal_priority, reverse=True)


def bucket_town_signals(signals: list[TownSignal]) -> dict[TownPulseBucket, list[TownSignal]]:
    bullish: list[TownSignal] = []
    bearish: list[TownSignal] = []
    watch: list[TownSignal] = []
    for signal in rank_town_signals(signals):
        bucket = classify_town_signal(signal)
        if bucket == "bullish":
            bullish.append(signal)
        elif bucket == "bearish":
            bearish.append(signal)
        else:
            watch.append(signal)
    return {
        "bullish": dedupe_title_signals(bullish),
        "bearish": dedupe_title_signals(bearish),
        "watch": dedupe_title_signals(watch),
    }


def town_signal_priority(signal: TownSignal) -> float:
    status_bonus = {
        SignalStatus.COMPLETED: 18.0,
        SignalStatus.IN_PROGRESS: 16.0,
        SignalStatus.FUNDED: 15.0,
        SignalStatus.APPROVED: 14.0,
        SignalStatus.REJECTED: 11.0,
        SignalStatus.REVIEWED: 8.0,
        SignalStatus.PROPOSED: 6.0,
        SignalStatus.MENTIONED: 3.0,
    }.get(signal.status, 0.0)
    impact_bonus = {
        ImpactDirection.POSITIVE: 8.0,
        ImpactDirection.NEGATIVE: 8.0,
        ImpactDirection.MIXED: 4.0,
        ImpactDirection.NEUTRAL: 2.0,
    }.get(signal.impact_direction, 0.0)
    recency_bonus = 0.0
    if signal.source_date is not None:
        days_old = max(0.0, (datetime.now(timezone.utc) - signal.source_date).days)
        recency_bonus = max(0.0, 20.0 - min(days_old / 12.0, 20.0))
    return (signal.confidence * 100.0) + status_bonus + impact_bonus + recency_bonus


def dedupe_title_signals(signals: list[TownSignal]) -> list[TownSignal]:
    seen: set[str] = set()
    deduped: list[TownSignal] = []
    for signal in signals:
        key = " ".join(signal.title.lower().split())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)
    return deduped

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ValuePositionLabel = Literal["value_find", "fair", "overpriced", "insufficient_data"]
ConfidenceBand = Literal["high", "medium", "low", "very_low"]

VALUE_FIND_THRESHOLD_PCT = -5.0
OVERPRICED_THRESHOLD_PCT = 5.0

PRICING_VIEW_BY_LABEL: dict[ValuePositionLabel, str] = {
    "value_find": "appears undervalued",
    "fair": "appears fairly priced",
    "overpriced": "appears overpriced",
    "insufficient_data": "unavailable",
}


@dataclass(frozen=True)
class ValuePositionConfidence:
    """Confidence attached to a user-facing value-position label."""

    score: float
    band: ConfidenceBand


@dataclass(frozen=True)
class ValuePosition:
    """Canonical BCV-vs-ask classification for value-position labels."""

    label: ValuePositionLabel
    pricing_view: str
    ask_vs_fmv_delta_pct: float | None
    bcv_vs_ask_delta_pct: float | None
    confidence: ValuePositionConfidence | None = None


def classify_ask_vs_fmv_delta_pct(delta_pct: float | None) -> ValuePositionLabel:
    """Classify ask premium/discount versus FMV using canonical thresholds."""
    if delta_pct is None:
        return "insufficient_data"
    if delta_pct <= VALUE_FIND_THRESHOLD_PCT:
        return "value_find"
    if delta_pct >= OVERPRICED_THRESHOLD_PCT:
        return "overpriced"
    return "fair"


def classify_bcv_vs_ask_delta_pct(delta_pct: float | None) -> ValuePositionLabel:
    """Classify BCV premium/discount versus ask using canonical thresholds."""
    if delta_pct is None or delta_pct <= -100:
        return "insufficient_data"
    ask_vs_fmv_delta_pct = (-(delta_pct / 100.0) / (1.0 + (delta_pct / 100.0))) * 100.0
    return classify_ask_vs_fmv_delta_pct(ask_vs_fmv_delta_pct)


def classify_value_position(
    *,
    bcv: float | None,
    ask: float | None,
    bcv_confidence: float | None = None,
    comp_confidence: float | None = None,
) -> ValuePosition:
    """Classify a property's value position from Briarwood value and ask."""
    if bcv is None or ask is None or bcv <= 0 or ask <= 0:
        label: ValuePositionLabel = "insufficient_data"
        return ValuePosition(
            label=label,
            pricing_view=PRICING_VIEW_BY_LABEL[label],
            ask_vs_fmv_delta_pct=None,
            bcv_vs_ask_delta_pct=None,
            confidence=None,
        )

    ask_vs_fmv_delta_pct = ((ask - bcv) / bcv) * 100.0
    bcv_vs_ask_delta_pct = ((bcv - ask) / ask) * 100.0
    label = classify_ask_vs_fmv_delta_pct(ask_vs_fmv_delta_pct)

    return ValuePosition(
        label=label,
        pricing_view=PRICING_VIEW_BY_LABEL[label],
        ask_vs_fmv_delta_pct=ask_vs_fmv_delta_pct,
        bcv_vs_ask_delta_pct=bcv_vs_ask_delta_pct,
        confidence=_pricing_view_confidence(
            bcv_confidence=bcv_confidence,
            comp_confidence=comp_confidence,
        ),
    )


def pricing_view_for_label(label: ValuePositionLabel) -> str:
    """Return the current-value prose label for a canonical value label."""
    return PRICING_VIEW_BY_LABEL[label]


def _pricing_view_confidence(
    *,
    bcv_confidence: float | None,
    comp_confidence: float | None,
) -> ValuePositionConfidence | None:
    scores = [
        float(score)
        for score in (bcv_confidence, comp_confidence)
        if score is not None
    ]
    if not scores:
        return None
    score = max(0.0, min(min(scores), 1.0))
    if score >= 0.90:
        band: ConfidenceBand = "high"
    elif score >= 0.70:
        band = "medium"
    elif score >= 0.50:
        band = "low"
    else:
        band = "very_low"
    return ValuePositionConfidence(score=score, band=band)

"""Security Model — crime index, trend, neighborhood safety score.

Stub scorer that reads town-level signals from
``data/local_intelligence/signals/{town-state}.json`` and derives a 0–100
safety score. Returns a neutral score + low confidence when no crime/safety
signals are present, so the pipeline can run before real data arrives.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from briarwood.pipeline.feedback_mixin import FeedbackReceiverMixin


ROOT = Path(__file__).resolve().parents[2]
SIGNALS_DIR = ROOT / "data" / "local_intelligence" / "signals"

SAFETY_SIGNAL_TYPES = {"crime", "safety", "public_safety", "enforcement"}

_TREND_MAP = {"positive": "improving", "negative": "declining", "neutral": "stable"}


class SecurityModel(FeedbackReceiverMixin):
    """Produces a safety score from town-level intelligence signals."""

    name = "security_model"

    def __init__(self, signals_dir: Path | None = None) -> None:
        self._signals_dir = Path(signals_dir) if signals_dir else SIGNALS_DIR

    def run(self, property_input: dict[str, Any]) -> dict[str, Any]:
        town = str(property_input.get("town") or "").strip().lower().replace(" ", "-")
        state = str(property_input.get("state") or "").strip().lower()
        signals = self._load_signals(town, state)

        safety_signals = [
            s for s in signals if str(s.get("signal_type") or "").lower() in SAFETY_SIGNAL_TYPES
        ]

        if not safety_signals:
            return {
                "data": {
                    "score": 70.0,
                    "crime_index": None,
                    "trend": "unknown",
                    "notes": "No crime/safety signals available; neutral prior used.",
                    "signal_count": 0,
                },
                "confidence": 0.3,
                "warnings": ["no_safety_signals"],
            }

        positives = sum(1 for s in safety_signals if s.get("impact_direction") == "positive")
        negatives = sum(1 for s in safety_signals if s.get("impact_direction") == "negative")
        magnitude = sum(int(s.get("impact_magnitude") or 0) for s in safety_signals)

        # 0-100 with neutral baseline 70; negatives drag down, positives boost
        score = 70.0 + (positives * 4.0) - (negatives * 6.0) - (magnitude * 0.5)
        score = max(0.0, min(100.0, score))

        dominant = "neutral"
        if negatives > positives:
            dominant = "negative"
        elif positives > negatives:
            dominant = "positive"
        trend = _TREND_MAP.get(dominant, "stable")

        confidence = min(0.9, 0.4 + 0.1 * len(safety_signals))

        return {
            "data": {
                "score": round(score, 1),
                "crime_index": round(100.0 - score, 1),
                "trend": trend,
                "notes": f"Derived from {len(safety_signals)} safety signal(s).",
                "signal_count": len(safety_signals),
                "positive_count": positives,
                "negative_count": negatives,
            },
            "confidence": round(confidence, 2),
            "warnings": [],
        }

    def _load_signals(self, town: str, state: str) -> list[dict[str, Any]]:
        if not town or not state:
            return []
        path = self._signals_dir / f"{town}-{state}.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        signals = payload.get("signals") if isinstance(payload, dict) else None
        return [s for s in signals or [] if isinstance(s, dict)]


__all__ = ["SecurityModel"]

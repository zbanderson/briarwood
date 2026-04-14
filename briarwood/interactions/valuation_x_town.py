"""Bridge: valuation × town/scarcity.

Spec §4B: scarcity & desirability modulate the *acceptable premium band*
around comparable-sales-derived value. A property in a scarcity-driven market
can legitimately trade above comps; the same premium in a soft market is a
red flag.

This bridge reads valuation metrics + town outlook and emits an adjusted
premium-band opinion. It does not mutate the valuation payload.
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _confidence,
    _metrics,
    _payload,
)

NAME = "valuation_x_town"

# Baseline band around comp-derived value before town adjustments.
BASELINE_PREMIUM_BAND = 0.07  # ±7%
SCARCITY_BONUS = 0.08         # strong scarcity widens the upside band
WEAK_MARKET_PENALTY = 0.04    # soft town tightens it


def run(outputs: ModuleOutputs) -> BridgeRecord:
    valuation = _payload(outputs, "valuation")
    # Town context lives in the town_county module in legacy paths and in the
    # valuation module's own ``town_context_confidence`` metric in scoped paths.
    val_metrics = _metrics(valuation)
    town_conf = val_metrics.get("town_context_confidence")

    if valuation is None:
        return BridgeRecord(name=NAME, fired=False, reasoning=["valuation output missing"])

    # Pull scarcity / desirability signals. We fall back to town_context_confidence
    # when a dedicated town_x module is not available.
    scarcity_signal = _extract_scarcity_signal(outputs)
    strength = _classify_strength(scarcity_signal, town_conf)

    upper = BASELINE_PREMIUM_BAND
    lower = -BASELINE_PREMIUM_BAND
    reasoning: list[str] = []

    if strength == "strong":
        upper += SCARCITY_BONUS
        reasoning.append(
            "Town signals indicate scarcity/desirability — widening acceptable premium above comps."
        )
    elif strength == "weak":
        upper -= WEAK_MARKET_PENALTY
        reasoning.append(
            "Town signals indicate soft absorption — tightening acceptable premium above comps."
        )
    else:
        reasoning.append("Town signals neutral; using baseline premium band.")

    return BridgeRecord(
        name=NAME,
        inputs_read=["valuation", "town_county_outlook/scarcity"],
        adjustments={
            "premium_band_upper_pct": round(upper, 4),
            "premium_band_lower_pct": round(lower, 4),
            "town_strength": strength,
            "baseline_premium_band": BASELINE_PREMIUM_BAND,
        },
        reasoning=reasoning,
        confidence=_confidence(valuation) or 0.5,
        fired=True,
    )


def _extract_scarcity_signal(outputs: ModuleOutputs) -> float | None:
    """Pull a numeric scarcity score from whichever module surfaces it."""

    # Scarcity can live in a town module, a valuation town prior, or a
    # dedicated scarcity support output. We accept the first that appears.
    for module_name in ("town_county_outlook", "scarcity_support", "valuation"):
        payload = _payload(outputs, module_name)
        metrics = _metrics(payload)
        for key in ("scarcity_support_score", "scarcity_score", "town_county_score"):
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _classify_strength(signal: float | None, town_conf: float | None) -> str:
    """Collapse the scarcity signal into strong/neutral/weak.

    Uses score when available; falls back to town_context_confidence. Returns
    ``neutral`` when neither signal is usable.
    """

    if signal is not None:
        if signal >= 70:
            return "strong"
        if signal <= 35:
            return "weak"
        return "neutral"
    if isinstance(town_conf, (int, float)):
        if town_conf >= 0.75:
            return "strong"
        if town_conf <= 0.35:
            return "weak"
    return "neutral"


__all__ = ["NAME", "run"]

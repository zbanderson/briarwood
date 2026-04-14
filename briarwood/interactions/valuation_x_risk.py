"""Bridge: valuation × risk.

Spec §4B: liquidity & fragility modulate *price acceptability*. A fair comp
price in a high-vacancy, high-flood area is functionally worse than the same
price in a stable area — risk should scale the acceptable discount demand.
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _confidence,
    _metrics,
    _payload,
)

NAME = "valuation_x_risk"

# How much additional discount to demand per risk "unit" (flag count or penalty).
DISCOUNT_PER_FLAG = 0.02      # 2% per flagged risk dimension
MAX_DISCOUNT = 0.15           # cap so risk can't swing the band arbitrarily


def run(outputs: ModuleOutputs) -> BridgeRecord:
    valuation = _payload(outputs, "valuation")
    risk = _payload(outputs, "risk_model")

    if valuation is None or risk is None:
        return BridgeRecord(
            name=NAME,
            fired=False,
            reasoning=["Need both valuation and risk_model outputs."],
        )

    risk_metrics = _metrics(risk)
    val_metrics = _metrics(valuation)

    risk_count = int(risk_metrics.get("risk_count") or 0)
    total_penalty = float(risk_metrics.get("total_penalty") or 0.0)
    risk_flags = risk_metrics.get("risk_flags") or ""

    # Penalty-driven discount when available (more precise); fall back to count.
    if total_penalty > 0:
        extra_discount = min(total_penalty * DISCOUNT_PER_FLAG, MAX_DISCOUNT)
    else:
        extra_discount = min(risk_count * DISCOUNT_PER_FLAG, MAX_DISCOUNT)

    reasoning: list[str] = []
    if extra_discount > 0:
        reasoning.append(
            f"Risk model flagged {risk_count} concern(s) ({risk_flags}); "
            f"demanding an extra {extra_discount*100:.1f}% discount vs comps."
        )
    else:
        reasoning.append("No risk flags; price acceptability unchanged.")

    # Confidence on the adjustment is the floor of the two input confidences.
    conf = min(
        filter(lambda x: x is not None, [_confidence(valuation), _confidence(risk)]),
        default=0.5,
    )

    return BridgeRecord(
        name=NAME,
        inputs_read=["valuation", "risk_model"],
        adjustments={
            "extra_discount_demanded_pct": round(extra_discount, 4),
            "risk_count": risk_count,
            "risk_flags": risk_flags,
            "ask_price": val_metrics.get("all_in_basis"),
            "briarwood_current_value": val_metrics.get("briarwood_current_value"),
        },
        reasoning=reasoning,
        confidence=float(conf),
        fired=extra_discount > 0 or risk_count > 0,
    )


__all__ = ["NAME", "run"]

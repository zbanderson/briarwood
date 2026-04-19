"""Bridge: rent × risk.

Spec §4B: legal / zoning / seasonality risks should *downgrade income
confidence*. An estimated rent of $4,500 in a town with rent-stabilization
uncertainty or an unverified ADU is not the same number as $4,500 in a
clean, legally verified full-rental single-family.

This bridge consumes rent-stabilization + legal confidence + risk flags and
emits an adjusted rent-confidence number. The raw rent figure is left
untouched — synthesis can cite both.
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _confidence,
    _metrics,
    _payload,
)

NAME = "rent_x_risk"

LEGAL_UNVERIFIED_PENALTY = 0.30
RENT_STABILIZATION_PENALTY = 0.20
RISK_FLAG_PENALTY_PER = 0.05


def run(outputs: ModuleOutputs) -> BridgeRecord:
    rent = _payload(outputs, "rental_option") or _payload(outputs, "hold_to_rent")
    if rent is None:
        return BridgeRecord(name=NAME, fired=False, reasoning=["no rent-producing module ran"])

    raw_conf = _confidence(rent) or 0.7
    adjusted = raw_conf
    reasoning: list[str] = []

    # Legal confidence downgrade (accessory units, uncertain zoning).
    legal = _payload(outputs, "legal_confidence")
    legal_conf = _confidence(legal)
    if legal is not None and legal_conf is not None and legal_conf < 0.5:
        adjusted -= LEGAL_UNVERIFIED_PENALTY
        reasoning.append(
            f"Legal confidence low ({legal_conf:.2f}); discounting rent confidence for unverified units."
        )

    # Rent stabilization unknowns.
    stab = _payload(outputs, "rent_stabilization")
    stab_data = (stab or {}).get("data") or {}
    stab_outlook = stab_data.get("town_county_outlook") or {}
    if isinstance(stab_outlook, dict):
        stab_flag = stab_outlook.get("rent_stabilization_flag") or stab_outlook.get("stabilization_risk")
        if stab_flag:
            adjusted -= RENT_STABILIZATION_PENALTY
            reasoning.append(
                "Rent stabilization / regulatory exposure flagged — downgrading rent confidence."
            )

    # General risk flags that impact rental realism (flood, high vacancy).
    risk = _payload(outputs, "risk_model")
    risk_metrics = _metrics(risk)
    risk_flags = str(risk_metrics.get("risk_flags") or "").lower()
    income_relevant = [
        tok for tok in ("flood", "vacancy", "seasonality", "short_term") if tok in risk_flags
    ]
    if income_relevant:
        adjusted -= RISK_FLAG_PENALTY_PER * len(income_relevant)
        reasoning.append(
            f"Income-relevant risk flags active: {', '.join(income_relevant)}."
        )

    adjusted = max(0.0, min(adjusted, 1.0))
    rent_haircut_pct = round(max(0.0, min(raw_conf - adjusted, 0.45)), 4)
    fired = adjusted < raw_conf

    if not reasoning:
        reasoning.append("No income-relevant risk downgrades.")

    return BridgeRecord(
        name=NAME,
        inputs_read=["rental_option/hold_to_rent", "legal_confidence", "rent_stabilization", "risk_model"],
        adjustments={
            "raw_rent_confidence": round(raw_conf, 4),
            "adjusted_rent_confidence": round(adjusted, 4),
            "downgrade_amount": round(raw_conf - adjusted, 4),
            "rent_haircut_pct": rent_haircut_pct,
        },
        reasoning=reasoning,
        confidence=round(adjusted, 4),
        fired=fired,
    )


__all__ = ["NAME", "run"]

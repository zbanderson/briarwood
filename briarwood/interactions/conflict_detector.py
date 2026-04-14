"""Bridge: explicit contradiction detection.

Spec §4B: synthesis should surface tension like "desirable town but poor
entry price", "strong rent but high fragility", "comp-supported but
legally unverified ADU". This bridge enumerates a set of cross-module
contradictions and records each one that fires.
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _confidence,
    _metrics,
    _payload,
)

NAME = "conflict_detector"


def run(outputs: ModuleOutputs) -> BridgeRecord:
    conflicts: list[dict[str, str]] = []

    val = _payload(outputs, "valuation")
    town = _payload(outputs, "town_county_outlook")
    risk = _payload(outputs, "risk_model")
    legal = _payload(outputs, "legal_confidence")
    rent = _payload(outputs, "rental_option") or _payload(outputs, "hold_to_rent")
    carry = _payload(outputs, "carry_cost")

    val_metrics = _metrics(val)
    town_metrics = _metrics(town)
    risk_metrics = _metrics(risk)

    # Conflict 1: desirable town, poor entry price.
    # Only use a real 0-100 town score here; dollar-amount priors are not scores.
    town_score = town_metrics.get("town_county_score")
    mispricing = val_metrics.get("mispricing_pct")
    if isinstance(town_score, (int, float)) and town_score >= 70:
        if isinstance(mispricing, (int, float)) and mispricing < -0.05:
            conflicts.append({
                "code": "desirable_town_poor_entry",
                "message": "Town signals are strong but the current price sits above comp-supported value.",
            })

    # Conflict 2: rent confidence high but legal confidence low.
    if rent is not None and legal is not None:
        r_conf = _confidence(rent) or 0.0
        l_conf = _confidence(legal) or 1.0
        if r_conf >= 0.7 and l_conf <= 0.4:
            conflicts.append({
                "code": "rent_vs_legal",
                "message": "Rental income confidence is high but legal/zoning confidence is low — rent is fragile if unit isn't legal.",
            })

    # Conflict 3: comps support price but risk flags dominate.
    if isinstance(mispricing, (int, float)) and abs(mispricing) <= 0.05:
        risk_count = int(risk_metrics.get("risk_count") or 0)
        if risk_count >= 3:
            conflicts.append({
                "code": "fair_price_high_risk",
                "message": f"Price is fair vs comps but {risk_count} risk flags are active.",
            })

    # Conflict 4: strong cash flow but execution-dependent.
    carry_metrics = _metrics(carry)
    rent_source_type = carry_metrics.get("rent_source_type")
    if rent_source_type == "estimated":
        if isinstance(mispricing, (int, float)) and mispricing > 0.15:
            conflicts.append({
                "code": "upside_depends_on_estimated_rent",
                "message": "Valuation upside leans on estimated (not verified) rent — thesis depends on rent assumption holding.",
            })

    return BridgeRecord(
        name=NAME,
        inputs_read=["valuation", "town_county_outlook", "risk_model", "legal_confidence", "rental_option", "carry_cost"],
        adjustments={
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
        },
        reasoning=(
            [c["message"] for c in conflicts]
            if conflicts
            else ["No explicit conflicts detected."]
        ),
        confidence=0.7 if conflicts else 0.9,
        fired=bool(conflicts),
    )


__all__ = ["NAME", "run"]

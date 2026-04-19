"""Bridge: rent × cost.

Spec §4B: carry_offset_ratio = rent / carry_cost. Break-even probability is
how reliably the rent covers the monthly obligations. Occupancy dependency
captures how many months of vacancy the deal can survive.

This bridge reads carry_cost and rental inputs and produces the ratio
metrics that downstream synthesis needs to make trade-off statements like
"this only works if you keep it 95% occupied."
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _confidence,
    _legacy,
    _metrics,
    _payload,
)

NAME = "rent_x_cost"


def run(outputs: ModuleOutputs) -> BridgeRecord:
    carry = _payload(outputs, "carry_cost")
    # rental_option / hold_to_rent both expose rent info; prefer the first found.
    rent_source = None
    for candidate in ("rental_option", "hold_to_rent", "unit_income_offset"):
        if _payload(outputs, candidate) is not None:
            rent_source = candidate
            break

    if carry is None:
        return BridgeRecord(name=NAME, fired=False, reasoning=["carry_cost output missing"])

    carry_metrics = _metrics(carry)
    carry_legacy = _legacy(carry)

    monthly_rent = _as_float(carry_metrics.get("monthly_rent"))
    monthly_cost = _as_float(
        carry_legacy.get("monthly_total_cost")
        or carry_legacy.get("total_monthly_cost")
        or carry_legacy.get("monthly_carry_cost")
        or carry_legacy.get("gross_monthly_cost")
    )

    if monthly_rent is None or monthly_cost is None or monthly_cost <= 0:
        return BridgeRecord(
            name=NAME,
            inputs_read=["carry_cost"] + ([rent_source] if rent_source else []),
            fired=False,
            reasoning=["Need monthly_rent and monthly_cost to compute carry-offset ratio."],
        )

    carry_offset_ratio = round(monthly_rent / monthly_cost, 3)
    monthly_gap = round(monthly_rent - monthly_cost, 2)
    break_even_rent = round(monthly_cost, 2)

    # Occupancy dependency: fraction of months that must be rented to break even.
    # If rent > cost, any occupancy ≥ (cost/rent) works. If rent < cost, no
    # realistic occupancy covers the deal without external cash.
    if monthly_rent > 0:
        required_occupancy = min(max(monthly_cost / monthly_rent, 0.0), 1.0)
    else:
        required_occupancy = 1.0

    # Break-even probability is a coarse heuristic: higher ratio → higher prob.
    if carry_offset_ratio >= 1.2:
        break_even_prob = 0.90
    elif carry_offset_ratio >= 1.0:
        break_even_prob = 0.70
    elif carry_offset_ratio >= 0.85:
        break_even_prob = 0.45
    else:
        break_even_prob = 0.20

    reasoning = [
        f"Rent ${monthly_rent:,.0f} vs carry ${monthly_cost:,.0f}/mo → ratio {carry_offset_ratio}.",
    ]
    if carry_offset_ratio < 1.0:
        reasoning.append(
            f"Requires ~{required_occupancy*100:.0f}% occupancy to break even — thin margin."
        )

    return BridgeRecord(
        name=NAME,
        inputs_read=["carry_cost"] + ([rent_source] if rent_source else []),
        adjustments={
            "carry_offset_ratio": carry_offset_ratio,
            "monthly_gap": monthly_gap,
            "break_even_rent": break_even_rent,
            "required_occupancy": round(required_occupancy, 3),
            "break_even_probability": break_even_prob,
        },
        reasoning=reasoning,
        confidence=_confidence(carry) or 0.5,
        fired=True,
    )


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = ["NAME", "run"]

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NetOpportunityDeltaResult:
    value_anchor: float | None
    purchase_price: float | None
    capex_amount: float | None
    capex_source: str
    all_in_basis: float | None
    delta_value: float | None
    delta_pct: float | None


def infer_capex_amount(property_input: Any) -> tuple[float | None, str]:
    explicit_budget = getattr(property_input, "repair_capex_budget", None)
    if explicit_budget is not None:
        return float(explicit_budget), "user_budget"

    # User-declared renovation plan — "what if we renovate" — applies a real
    # capex dollar amount on top of the basis. Flat prototype heuristic;
    # scaling by sqft/beds is a follow-up.
    mode = (getattr(property_input, "renovation_mode", None) or "").strip().lower()
    if mode == "will_renovate":
        return 150_000.0, "user_renovation_plan"

    lane = (getattr(property_input, "capex_lane", None) or "").strip().lower()
    if lane == "light":
        return 25000.0, "inferred_lane"
    if lane == "moderate":
        return 75000.0, "inferred_lane"
    if lane == "heavy":
        return 150000.0, "inferred_lane"

    condition = (getattr(property_input, "condition_profile", None) or "").strip().lower()
    if condition in {"renovated", "updated", "turnkey"}:
        return 0.0, "inferred_condition"

    return None, "unknown"


def calculate_net_opportunity_delta(
    *,
    value_anchor: float | None,
    property_input: Any,
) -> NetOpportunityDeltaResult:
    purchase_price = getattr(property_input, "purchase_price", None)
    capex_amount, capex_source = infer_capex_amount(property_input)

    if purchase_price is None:
        return NetOpportunityDeltaResult(
            value_anchor=value_anchor,
            purchase_price=None,
            capex_amount=capex_amount,
            capex_source=capex_source,
            all_in_basis=None,
            delta_value=None,
            delta_pct=None,
        )

    all_in_basis = float(purchase_price)
    if capex_amount is not None:
        all_in_basis += capex_amount

    if value_anchor is None:
        return NetOpportunityDeltaResult(
            value_anchor=None,
            purchase_price=float(purchase_price),
            capex_amount=capex_amount,
            capex_source=capex_source,
            all_in_basis=all_in_basis,
            delta_value=None,
            delta_pct=None,
        )

    delta_value = float(value_anchor) - all_in_basis
    delta_pct = (delta_value / all_in_basis) if all_in_basis else None
    return NetOpportunityDeltaResult(
        value_anchor=float(value_anchor),
        purchase_price=float(purchase_price),
        capex_amount=capex_amount,
        capex_source=capex_source,
        all_in_basis=all_in_basis,
        delta_value=delta_value,
        delta_pct=delta_pct,
    )

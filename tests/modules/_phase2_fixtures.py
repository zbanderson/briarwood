"""Shared fixtures for Phase 2 module-isolation tests.

The Spec §7 audit template requires five canonical input cases per module:

- ``normal``           — complete, consistent inputs
- ``thin``             — minimal inputs; downstream modules should show confidence degradation
- ``contradictory``    — inputs that disagree (e.g., tiny sqft + huge price)
- ``unique``           — atypical property (back house, ADU, unusual zoning)
- ``fragile_financing``— high leverage / thin margin inputs

These are used across all Phase 2 module tests so failure modes are directly
comparable across modules.
"""

from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext


def _base(address: str) -> dict[str, Any]:
    return {
        "address": address,
        "town": "Avon By The Sea",
        "state": "NJ",
        "county": "Monmouth",
        "property_type": "single_family",
    }


def normal_property_data() -> dict[str, Any]:
    return {
        **_base("123 Main St"),
        "property_id": "test-normal",
        "beds": 3,
        "baths": 2.0,
        "sqft": 1800,
        "lot_size": 5000,
        "year_built": 1998,
        "purchase_price": 725_000,
        "taxes": 9_800,
        "insurance": 2_400,
        "monthly_hoa": 0,
        "estimated_monthly_rent": 3_800,
    }


def thin_property_data() -> dict[str, Any]:
    """Only the minimum PropertyInput fields. Everything downstream has to guess."""
    return {
        **_base("456 Sparse Ln"),
        "property_id": "test-thin",
        "beds": 2,
        "baths": 1.0,
        "sqft": 900,
    }


def contradictory_property_data() -> dict[str, Any]:
    """sqft / bed count / price do not tell a consistent story."""
    return {
        **_base("789 Mismatch Ave"),
        "property_id": "test-contradictory",
        "beds": 6,
        "baths": 1.0,      # 6 beds but only 1 bath
        "sqft": 700,       # tiny sqft for 6 beds
        "lot_size": 2_000,
        "year_built": 1900,
        "purchase_price": 2_400_000,  # absurd for 700 sqft
        "taxes": 3_200,
        "estimated_monthly_rent": 900,  # rent way below price
    }


def unique_property_data() -> dict[str, Any]:
    """Back house + ADU + extra signals. Exercises legal/rent logic."""
    return {
        **_base("22 Back House Rd"),
        "property_id": "test-unique",
        "beds": 4,
        "baths": 2.5,
        "sqft": 2_200,
        "lot_size": 9_000,
        "year_built": 1960,
        "purchase_price": 1_150_000,
        "taxes": 14_200,
        "has_back_house": True,
        "adu_type": "detached",
        "adu_sqft": 600,
        "additional_units": [{"beds": 1, "baths": 1.0, "sqft": 550}],
        "back_house_monthly_rent": 2_200,
        "estimated_monthly_rent": 4_500,
    }


def fragile_financing_property_data() -> dict[str, Any]:
    """Thin margin of safety. Should raise warnings in carry_cost/scenario paths."""
    return {
        **_base("5 Leverage Ct"),
        "property_id": "test-fragile",
        "beds": 3,
        "baths": 2.0,
        "sqft": 1_500,
        "lot_size": 3_500,
        "year_built": 2005,
        "purchase_price": 900_000,
        "taxes": 18_500,      # high taxes relative to rent
        "insurance": 4_800,
        "monthly_hoa": 350,
        "estimated_monthly_rent": 2_800,  # negative carry even with no mortgage
    }


# ─── ExecutionContext builders ────────────────────────────────────────────────

def _make_context(
    property_data: dict[str, Any],
    *,
    assumptions: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    comp_context: dict[str, Any] | None = None,
    prior_outputs: dict[str, Any] | None = None,
    macro_context: dict[str, Any] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        property_id=str(property_data.get("property_id") or "test-prop"),
        property_data=property_data,
        assumptions=dict(assumptions or {
            "down_payment_percent": 0.25,
            "interest_rate": 0.07,
            "loan_term_years": 30,
            "vacancy_rate": 0.06,
        }),
        market_context=dict(market_context or {}),
        comp_context=dict(comp_context or {}),
        prior_outputs=dict(prior_outputs or {}),
        macro_context=dict(macro_context or {}),
    )


def context_normal(**overrides: Any) -> ExecutionContext:
    return _make_context(normal_property_data(), **overrides)


def context_thin(**overrides: Any) -> ExecutionContext:
    # thin case → also thin assumptions
    return _make_context(
        thin_property_data(),
        assumptions=overrides.pop("assumptions", {}),
        **overrides,
    )


def context_contradictory(**overrides: Any) -> ExecutionContext:
    return _make_context(contradictory_property_data(), **overrides)


def context_unique(**overrides: Any) -> ExecutionContext:
    return _make_context(unique_property_data(), **overrides)


def context_fragile(**overrides: Any) -> ExecutionContext:
    return _make_context(
        fragile_financing_property_data(),
        assumptions=overrides.pop("assumptions", {
            "down_payment_percent": 0.05,   # 5% down
            "interest_rate": 0.085,         # elevated rate
            "loan_term_years": 30,
            "vacancy_rate": 0.15,
        }),
        **overrides,
    )


# ─── Contract assertions (shared by all Phase 2 tests) ────────────────────────

from briarwood.routing_schema import ModulePayload  # noqa: E402


def assert_payload_contract(payload_dict: dict[str, Any]) -> ModulePayload:
    """Validate the runner output shape and return a typed ModulePayload."""
    assert isinstance(payload_dict, dict), f"Runner must return a dict, got {type(payload_dict)!r}"
    payload = ModulePayload(**payload_dict)
    if payload.confidence is not None:
        assert 0.0 <= payload.confidence <= 1.0, f"confidence out of range: {payload.confidence}"
    assert isinstance(payload.warnings, list)
    assert isinstance(payload.assumptions_used, dict)
    return payload

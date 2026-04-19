from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NormalizedPropertyContext(BaseModel):
    """Typed result of Briarwood's pre-module normalization layer."""

    model_config = ConfigDict(extra="forbid")

    property_data: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    field_provenance: dict[str, str] = Field(default_factory=dict)
    missing_data_registry: dict[str, Any] = Field(default_factory=dict)
    normalized_fields: dict[str, Any] = Field(default_factory=dict)


def normalize_execution_inputs(
    *,
    property_data: dict[str, Any],
    property_summary: dict[str, Any] | None = None,
    assumptions: dict[str, Any] | None = None,
) -> NormalizedPropertyContext:
    """Normalize sparse property data into a safer execution-ready shape.

    This layer does not invent analytical answers; it only guarantees the
    module boundary receives stable, typed defaults and explicit provenance.
    """

    summary = dict(property_summary or {})
    raw_property = dict(property_data or {})
    raw_assumptions = dict(assumptions or {})

    facts = dict(raw_property.get("facts") or {})
    property_flat = dict(raw_property)
    property_flat.pop("facts", None)

    field_provenance: dict[str, str] = {}
    normalized_fields: dict[str, Any] = {}

    def _lookup(*sources: dict[str, Any], key: str) -> Any:
        for source in sources:
            if isinstance(source, dict) and key in source and source.get(key) not in (None, ""):
                return source.get(key)
        return None

    def _set_field(
        key: str,
        *,
        value: Any,
        status: str,
        target: str = "property",
        include_in_facts: bool = True,
    ) -> None:
        normalized_fields[key] = value
        field_provenance[key] = status
        if target == "assumption":
            raw_assumptions[key] = value
        else:
            property_flat[key] = value
            if include_in_facts:
                facts[key] = value

    for key in ("address", "town", "state", "county", "property_type", "beds", "baths", "sqft"):
        value = _lookup(property_flat, facts, summary, key=key)
        status = "provided" if value not in (None, "") else "missing"
        if key in {"beds", "sqft"} and value not in (None, ""):
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = None
                status = "missing"
        if key == "baths" and value not in (None, ""):
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = None
                status = "missing"
        if value in (None, "") and key in {"address", "town", "state"}:
            value = "Unknown"
            status = "defaulted"
        _set_field(key, value=value, status=status)

    ask_price = _coerce_number(_lookup(property_flat, facts, summary, key="ask_price"))
    purchase_price = _coerce_number(_lookup(property_flat, facts, key="purchase_price"))
    if purchase_price is None and ask_price is not None:
        purchase_price = ask_price
        purchase_status = "defaulted"
    else:
        purchase_status = "provided" if purchase_price is not None else "missing"
    if ask_price is None and purchase_price is not None:
        ask_price = purchase_price
        ask_status = "defaulted"
    else:
        ask_status = "provided" if ask_price is not None else "missing"
    _set_field("purchase_price", value=purchase_price, status=purchase_status)
    _set_field("ask_price", value=ask_price, status=ask_status, include_in_facts=False)

    taxes = _coerce_number(_lookup(property_flat, facts, raw_assumptions, key="taxes"))
    insurance = _coerce_number(_lookup(raw_assumptions, property_flat, facts, key="insurance"))
    monthly_hoa = _coerce_number(_lookup(property_flat, facts, key="monthly_hoa"))
    estimated_rent = _coerce_number(
        _lookup(raw_assumptions, property_flat, facts, key="estimated_monthly_rent")
    )
    _set_field("taxes", value=taxes, status="provided" if taxes is not None else "missing")
    _set_field("insurance", value=insurance, status="provided" if insurance is not None else "missing")
    _set_field(
        "monthly_hoa",
        value=monthly_hoa if monthly_hoa is not None else 0.0,
        status="provided" if monthly_hoa is not None else "defaulted",
    )
    raw_assumptions["insurance"] = insurance
    if "insurance" in facts:
        facts.pop("insurance", None)
    property_flat["insurance"] = insurance
    field_provenance["insurance"] = "provided" if insurance is not None else "missing"
    normalized_fields["insurance"] = insurance
    _set_field(
        "estimated_monthly_rent",
        value=estimated_rent,
        status="provided" if estimated_rent is not None else "missing",
        target="assumption",
    )

    assumption_defaults = {
        "down_payment_percent": 0.25,
        "interest_rate": 0.07,
        "loan_term_years": 30,
        "vacancy_rate": 0.06,
    }
    for key, default in assumption_defaults.items():
        value = _coerce_number(raw_assumptions.get(key))
        if value is None:
            value = default
            status = "defaulted"
        else:
            status = "provided"
        _set_field(key, value=value, status=status, target="assumption")

    manual_comp_inputs = raw_assumptions.get("manual_comp_inputs")
    if isinstance(manual_comp_inputs, list) and manual_comp_inputs:
        field_provenance["manual_comp_inputs"] = "provided"
    else:
        field_provenance["manual_comp_inputs"] = "missing"

    raw_property["facts"] = facts
    for key, value in property_flat.items():
        raw_property[key] = value

    registry = {
        "fields": {
            key: {
                "status": status,
                "value": normalized_fields.get(key),
            }
            for key, status in field_provenance.items()
        }
    }
    registry["provided"] = sorted([key for key, status in field_provenance.items() if status == "provided"])
    registry["estimated"] = sorted([key for key, status in field_provenance.items() if status == "estimated"])
    registry["defaulted"] = sorted([key for key, status in field_provenance.items() if status == "defaulted"])
    registry["missing"] = sorted([key for key, status in field_provenance.items() if status == "missing"])

    return NormalizedPropertyContext(
        property_data=raw_property,
        assumptions=raw_assumptions,
        field_provenance=field_provenance,
        missing_data_registry=registry,
        normalized_fields=normalized_fields,
    )


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = ["NormalizedPropertyContext", "normalize_execution_inputs"]

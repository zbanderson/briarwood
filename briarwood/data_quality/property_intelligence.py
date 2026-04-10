from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PropertyTaxQualityIntelligence:
    property_tax_confirmed_flag: bool
    municipality_tax_context_flag: bool
    reassessment_risk_score: float
    tax_burden_score: float
    structural_data_quality_score: float
    comp_eligibility_score: float
    notes: list[str] = field(default_factory=list)


def compute_property_tax_quality_intelligence(
    *,
    property_facts: dict[str, Any],
    attom_payload: dict[str, Any] | None = None,
    municipality_tax_context: dict[str, Any] | None = None,
    comp_quality_status: str | None = None,
) -> PropertyTaxQualityIntelligence:
    attom_payload = attom_payload or {}
    municipality_tax_context = municipality_tax_context or {}
    taxes = _as_float(attom_payload.get("tax_amount") or property_facts.get("taxes"))
    tax_year = attom_payload.get("tax_year")
    assessed_value = _as_float(attom_payload.get("assessed_total") or attom_payload.get("assessment_total"))
    purchase_price = _as_float(property_facts.get("purchase_price"))
    effective_tax_rate = _as_float(municipality_tax_context.get("effective_tax_rate"))
    equalization_ratio = _as_float(municipality_tax_context.get("equalization_ratio"))

    property_tax_confirmed_flag = taxes is not None and tax_year is not None
    municipality_tax_context_flag = effective_tax_rate is not None or equalization_ratio is not None

    tax_burden_score = _tax_burden_score(taxes=taxes, purchase_price=purchase_price, effective_tax_rate=effective_tax_rate)
    reassessment_risk_score = _reassessment_risk_score(
        assessed_value=assessed_value,
        purchase_price=purchase_price,
        equalization_ratio=equalization_ratio,
    )
    structural_data_quality_score = _structural_data_quality_score(property_facts)
    comp_eligibility_score = _comp_eligibility_score(
        structural_data_quality_score=structural_data_quality_score,
        property_tax_confirmed_flag=property_tax_confirmed_flag,
        comp_quality_status=comp_quality_status,
    )

    notes: list[str] = []
    if property_tax_confirmed_flag:
        notes.append("Taxes confirmed via ATTOM")
    if municipality_tax_context_flag:
        notes.append("Municipality tax burden sourced from NJ tax tables")
    if reassessment_risk_score >= 0.65:
        notes.append("Town equalization ratio suggests reassessment risk")
    if structural_data_quality_score < 0.7:
        notes.append("Structural profile incomplete; comp confidence reduced")

    return PropertyTaxQualityIntelligence(
        property_tax_confirmed_flag=property_tax_confirmed_flag,
        municipality_tax_context_flag=municipality_tax_context_flag,
        reassessment_risk_score=round(reassessment_risk_score, 3),
        tax_burden_score=round(tax_burden_score, 3),
        structural_data_quality_score=round(structural_data_quality_score, 3),
        comp_eligibility_score=round(comp_eligibility_score, 3),
        notes=notes,
    )


def _tax_burden_score(*, taxes: float | None, purchase_price: float | None, effective_tax_rate: float | None) -> float:
    if taxes is None or purchase_price in (None, 0):
        return 0.45
    implied_rate = taxes / purchase_price
    baseline = effective_tax_rate or 0.018
    if baseline <= 0:
        baseline = 0.018
    ratio = implied_rate / baseline
    if ratio <= 0.8:
        return 0.8
    if ratio <= 1.05:
        return 0.65
    if ratio <= 1.35:
        return 0.45
    return 0.25


def _reassessment_risk_score(
    *,
    assessed_value: float | None,
    purchase_price: float | None,
    equalization_ratio: float | None,
) -> float:
    if assessed_value in (None, 0) or purchase_price in (None, 0):
        return 0.35
    ratio = assessed_value / purchase_price
    equalization = equalization_ratio or 100.0
    equalization_factor = abs(equalization - 100.0) / 100.0
    return max(0.0, min(1.0, (1.0 - ratio) * 0.7 + equalization_factor * 0.6))


def _structural_data_quality_score(property_facts: dict[str, Any]) -> float:
    required = ["address", "town", "state", "beds", "baths", "sqft", "property_type"]
    present = sum(1 for field in required if property_facts.get(field) not in (None, "", []))
    return present / len(required)


def _comp_eligibility_score(
    *,
    structural_data_quality_score: float,
    property_tax_confirmed_flag: bool,
    comp_quality_status: str | None,
) -> float:
    score = structural_data_quality_score * 0.7 + (0.2 if property_tax_confirmed_flag else 0.0)
    if comp_quality_status == "accepted":
        score += 0.1
    elif comp_quality_status == "accepted_with_warnings":
        score += 0.04
    elif comp_quality_status == "rejected":
        score -= 0.25
    return max(0.0, min(1.0, score))


def _as_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

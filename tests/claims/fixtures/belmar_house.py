"""Fabricated Belmar house fixture for claim-pipeline tests.

Pure Python, no external data. Exercises all three comparison tiers
(subject config, renovated same, renovated +bath) and produces the
shape of module results + interaction trace that the synthesis
producer expects.
"""
from __future__ import annotations

from typing import Any

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    ComparableSalesOutput,
)


SUBJECT_PROPERTY_ID = "belmar-test-001"
SUBJECT_ADDRESS = "123 Belmar Ave, Belmar, NJ"
SUBJECT_BEDS = 3
SUBJECT_BATHS = 2.0
SUBJECT_SQFT = 1_800
SUBJECT_ASK = 650_000.0
SUBJECT_FMV = 700_000.0  # delta = (650-700)/700 = -7.14% → value_find
SUBJECT_CONFIDENCE = 0.82  # medium band

_COMMON_COMP_FIELDS: dict[str, Any] = {
    "comp_confidence_weight": 0.85,
    "similarity_score": 0.9,
    "fit_label": "strong",
    "time_adjustment_pct": 0.0,
    "subject_adjustment_pct": 0.0,
    "why_comp": ["same block", "same beds/baths"],
    "cautions": [],
    "adjustments_summary": ["no material adjustments"],
}


def _comp(
    *,
    address: str,
    adjusted_price: float,
    beds: int,
    baths: float,
    sqft: int,
    condition: str | None,
    sale_age_days: int = 60,
    distance_mi: float = 0.4,
) -> AdjustedComparable:
    return AdjustedComparable(
        address=address,
        sale_date="2026-01-15",
        sale_price=adjusted_price,
        time_adjusted_price=adjusted_price,
        adjusted_price=adjusted_price,
        bedrooms=beds,
        bathrooms=baths,
        sqft=sqft,
        condition_profile=condition,
        distance_to_subject_miles=distance_mi,
        sale_age_days=sale_age_days,
        **_COMMON_COMP_FIELDS,
    )


# Tier 1: subject config (3BR/2BA, any condition) — median ~350/sqft
_TIER_SUBJECT_COMPS = [
    _comp(
        address="11 Ocean Ave",
        adjusted_price=630_000,
        beds=3,
        baths=2.0,
        sqft=1_800,
        condition="maintained",
    ),
    _comp(
        address="22 8th Ave",
        adjusted_price=648_000,
        beds=3,
        baths=2.0,
        sqft=1_800,
        condition="dated",
    ),
    _comp(
        address="33 E Railroad",
        adjusted_price=612_000,
        beds=3,
        baths=2.0,
        sqft=1_800,
        condition="maintained",
    ),
]

# Tier 2: renovated same-config (3BR/2BA, renovated/updated) — median ~400/sqft
_TIER_RENOV_SAME_COMPS = [
    _comp(
        address="44 12th Ave",
        adjusted_price=720_000,
        beds=3,
        baths=2.0,
        sqft=1_800,
        condition="renovated",
    ),
    _comp(
        address="55 14th Ave",
        adjusted_price=738_000,
        beds=3,
        baths=2.0,
        sqft=1_800,
        condition="renovated",
    ),
    _comp(
        address="66 16th Ave",
        adjusted_price=702_000,
        beds=3,
        baths=2.0,
        sqft=1_800,
        condition="updated",
    ),
]

# Tier 3: renovated +bath (3BR/3BA, renovated/updated) — median ~510/sqft
_TIER_RENOV_PLUS_BATH_COMPS = [
    _comp(
        address="77 Main St",
        adjusted_price=900_000,
        beds=3,
        baths=3.0,
        sqft=1_800,
        condition="renovated",
        sale_age_days=120,
        distance_mi=0.8,
    ),
    _comp(
        address="88 C St",
        adjusted_price=918_000,
        beds=3,
        baths=3.0,
        sqft=1_800,
        condition="renovated",
        sale_age_days=90,
        distance_mi=0.6,
    ),
]

ALL_COMPS: list[AdjustedComparable] = [
    *_TIER_SUBJECT_COMPS,
    *_TIER_RENOV_SAME_COMPS,
    *_TIER_RENOV_PLUS_BATH_COMPS,
]


def property_summary() -> dict[str, Any]:
    return {
        "property_id": SUBJECT_PROPERTY_ID,
        "address": SUBJECT_ADDRESS,
        "beds": SUBJECT_BEDS,
        "baths": SUBJECT_BATHS,
        "sqft": SUBJECT_SQFT,
        "status": "active",
        "purchase_price": SUBJECT_ASK,
    }


def comparable_sales_output() -> ComparableSalesOutput:
    return ComparableSalesOutput(
        comparable_value=SUBJECT_FMV,
        comp_count=len(ALL_COMPS),
        confidence=0.85,
        comps_used=ALL_COMPS,
        assumptions=[],
        unsupported_claims=[],
        warnings=[],
        summary="Belmar test fixture",
        comp_confidence_score=0.85,
    )


def module_results() -> dict[str, Any]:
    return {
        "valuation": {
            "data": {
                "metrics": {
                    "briarwood_current_value": SUBJECT_FMV,
                    "listing_ask_price": SUBJECT_ASK,
                    "comp_count": len(ALL_COMPS),
                    "comp_confidence_score": 0.85,
                }
            }
        },
        "comparable_sales": {
            "payload": comparable_sales_output(),
        },
        "confidence": {
            "confidence": SUBJECT_CONFIDENCE,
        },
    }


def interaction_trace(*, include_bridge: bool = True) -> dict[str, Any]:
    if not include_bridge:
        return {"records": []}
    return {
        "records": [
            {
                "name": "comparable_sales_to_valuation",
                "fired": True,
                "reasoning": [
                    "Lifted comparable value to valuation for blending.",
                ],
                "adjustments": {
                    "conflicts": [],
                },
            }
        ]
    }


def parser_output() -> dict[str, Any]:
    return {"question_focus": ["price"]}

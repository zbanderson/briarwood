from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.reports.section_helpers import (
    get_comparable_sales,
    get_current_value,
    get_income_support,
    get_location_intelligence,
    get_rental_ease,
    get_town_county_outlook,
)
from briarwood.schemas import AnalysisReport


@dataclass(slots=True)
class ScoreCardItem:
    label: str
    score: float
    confidence: float
    source_modules: list[str] = field(default_factory=list)
    key_drivers: list[str] = field(default_factory=list)
    narrative: str = ""


@dataclass(slots=True)
class ScoreCard:
    value_support: ScoreCardItem
    income_support: ScoreCardItem
    location_quality: ScoreCardItem
    risk: ScoreCardItem
    confidence: ScoreCardItem
    overall: ScoreCardItem


def build_scorecard(report: AnalysisReport) -> ScoreCard:
    current_value_module = report.get_module("current_value")
    comparable_sales_module = report.get_module("comparable_sales")
    income_module = report.get_module("income_support")
    rental_module = report.get_module("rental_ease")
    town_module = report.get_module("town_county_outlook")
    scarcity_module = report.get_module("scarcity_support")
    risk_module = report.get_module("risk_constraints")
    location_module = report.module_results.get("location_intelligence")

    current_value = get_current_value(report)
    comps = get_comparable_sales(report)
    income = get_income_support(report)
    rental = get_rental_ease(report)
    town = get_town_county_outlook(report)
    location_payload = get_location_intelligence(report) if location_module is not None else None

    value_score = _weighted_average(
        [
            (current_value_module.score, 0.65),
            (comparable_sales_module.score, 0.35),
        ]
    )
    value_support = ScoreCardItem(
        label="Value Support",
        score=round(value_score, 1),
        confidence=round((current_value_module.confidence + comparable_sales_module.confidence) / 2, 2),
        source_modules=["current_value", "comparable_sales"],
        key_drivers=[
            f"BCV {current_value.pricing_view}",
            f"{comps.comp_count} active comps",
            f"comp confidence {comps.confidence:.0%}",
        ],
        narrative=(
            f"Value support is anchored by BCV and the current comp set. "
            f"Today it reads as {current_value.pricing_view} with {comps.comp_count} usable comps."
        ),
    )

    income_score = _weighted_average(
        [
            (income_module.score, 0.7),
            (rental_module.score, 0.3),
        ]
    )
    income_support = ScoreCardItem(
        label="Income Support",
        score=round(income_score, 1),
        confidence=round((income_module.confidence + rental_module.confidence) / 2, 2),
        source_modules=["income_support", "rental_ease"],
        key_drivers=[
            f"rent source {income.rent_source_type}",
            f"support ratio {income.income_support_ratio:.2f}x" if income.income_support_ratio is not None else "support ratio unavailable",
            rental.rental_ease_label,
        ],
        narrative=(
            "Income support blends fallback carry support and leasing ease. "
            "It is strongest when rent and financing are both supplied."
        ),
    )

    location_components = [
        (town.score.town_county_score, 0.45),
        (scarcity_module.score, 0.25),
    ]
    location_modules = ["town_county_outlook", "scarcity_support"]
    location_drivers = [
        town.score.location_thesis_label,
        town.score.liquidity_view,
        report.get_module("scarcity_support").metrics.get("scarcity_label", "Scarcity unavailable"),
    ]
    location_confidences = [town_module.confidence, scarcity_module.confidence]
    if location_module is not None and location_payload is not None:
        location_components.append((location_module.score, 0.30))
        location_modules.append("location_intelligence")
        location_drivers.append(
            f"geo bucket {location_payload.primary_category or 'proxy only'}"
        )
        location_confidences.append(location_module.confidence)
    location_quality = ScoreCardItem(
        label="Location Quality",
        score=round(_weighted_average(location_components), 1),
        confidence=round(sum(location_confidences) / len(location_confidences), 2),
        source_modules=location_modules,
        key_drivers=location_drivers,
        narrative=(
            "Location quality blends town/county context, scarcity support, and geo benchmarking when coordinates exist."
        ),
    )

    risk_score = ScoreCardItem(
        label="Risk",
        score=round(risk_module.score, 1),
        confidence=round(risk_module.confidence, 2),
        source_modules=["risk_constraints"],
        key_drivers=[str(risk_module.metrics.get("risk_flags") or "none")],
        narrative="Risk is a simple guardrail score: higher means fewer obvious structural flags.",
    )

    confidence_score_value = round(
        _weighted_average(
            [
                (current_value_module.confidence * 100, 0.30),
                (comparable_sales_module.confidence * 100, 0.20),
                (income_module.confidence * 100, 0.20),
                (town_module.confidence * 100, 0.15),
                (risk_module.confidence * 100, 0.15),
            ]
        ),
        1,
    )
    confidence_item = ScoreCardItem(
        label="Confidence",
        score=confidence_score_value,
        confidence=round(confidence_score_value / 100, 2),
        source_modules=["current_value", "comparable_sales", "income_support", "town_county_outlook", "risk_constraints"],
        key_drivers=[
            f"value {current_value_module.confidence:.0%}",
            f"comps {comparable_sales_module.confidence:.0%}",
            f"income {income_module.confidence:.0%}",
        ],
        narrative="Confidence is a blended evidence score, not a guarantee of accuracy.",
    )

    overall_score = ScoreCardItem(
        label="Overall Score",
        score=round(
            _weighted_average(
                [
                    (value_support.score, 0.30),
                    (income_support.score, 0.20),
                    (location_quality.score, 0.25),
                    (risk_score.score, 0.15),
                    (confidence_item.score, 0.10),
                ]
            ),
            1,
        ),
        confidence=round(confidence_item.confidence, 2),
        source_modules=[
            "current_value",
            "comparable_sales",
            "income_support",
            "rental_ease",
            "town_county_outlook",
            "scarcity_support",
            "risk_constraints",
        ],
        key_drivers=[
            value_support.label,
            income_support.label,
            location_quality.label,
            risk_score.label,
        ],
        narrative="Overall score is a simple synthesis of value, income, location, risk, and evidence confidence.",
    )

    return ScoreCard(
        value_support=value_support,
        income_support=income_support,
        location_quality=location_quality,
        risk=risk_score,
        confidence=confidence_item,
        overall=overall_score,
    )


def _weighted_average(items: list[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in items if weight > 0)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in items if weight > 0) / total_weight

from __future__ import annotations

from briarwood.reports.section_helpers import get_income_support, get_rental_ease
from briarwood.reports.schemas import CarrySupportSection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_carry_support_section(report: AnalysisReport) -> CarrySupportSection:
    income_module = report.get_module("income_support")
    income = get_income_support(report)
    rental_ease_module = report.get_module("rental_ease")
    rental_ease = get_rental_ease(report)

    market_absorption_label = rental_ease.rental_ease_label
    market_absorption_summary = _build_market_absorption_summary(rental_ease)
    rental_viability_label = _build_rental_viability_label(income)
    rental_viability_summary = _build_rental_viability_summary(income)
    assessment_summary = _build_assessment_summary(
        market_absorption_label=market_absorption_label,
        rental_viability_label=rental_viability_label,
    )

    estimated_days_to_rent_text = (
        f"{rental_ease.estimated_days_to_rent} days"
        if rental_ease.estimated_days_to_rent is not None
        else "Unavailable"
    )
    ratio_text = (
        f"{income.rent_coverage:.2f}x"
        if income.rent_coverage is not None
        else "Unverified"
    )
    cash_flow_text = (
        f"${income.monthly_cash_flow:,.0f}/mo"
        if income.monthly_cash_flow is not None
        else (
            f"Pre-debt ${income.operating_monthly_cash_flow:,.0f}/mo"
            if getattr(income, "operating_monthly_cash_flow", None) is not None
            else "Unverified"
        )
    )

    market_warnings = _dedupe(
        [
            *rental_ease.warnings,
            *_filter_market_unsupported_claims(rental_ease.unsupported_claims),
        ]
    )[:5]
    viability_warnings = _dedupe(
        [
            *income.warnings,
            *income.unsupported_claims,
        ]
    )[:5]
    assumptions = _dedupe([*rental_ease.assumptions, *income.assumptions])[:5]
    unsupported_claims = _dedupe(
        [
            *rental_ease.unsupported_claims,
            *income.unsupported_claims,
        ]
    )[:5]

    return CarrySupportSection(
        title="Fallback Rental Support",
        summary="Rental demand and rental economics are not the same thing.",
        market_absorption_label=market_absorption_label,
        market_absorption_summary=market_absorption_summary,
        market_absorption_confidence=rental_ease.confidence,
        rental_viability_label=rental_viability_label,
        rental_viability_summary=rental_viability_summary,
        rental_viability_confidence=income.confidence,
        rental_ease_score_text=f"{rental_ease.rental_ease_score:.0f}/100",
        estimated_days_to_rent_text=estimated_days_to_rent_text,
        estimated_days_to_rent_context=_build_days_to_rent_context(rental_ease),
        income_support_ratio_text=ratio_text,
        estimated_cash_flow_text=cash_flow_text,
        market_absorption_warnings=market_warnings,
        rental_viability_warnings=viability_warnings,
        assumptions=assumptions,
        unsupported_claims=unsupported_claims,
        assessment=SectionAssessment(
            score=round((income_module.score + rental_ease_module.score) / 2, 2),
            confidence=min(income.confidence, rental_ease.confidence),
            summary=assessment_summary,
        ),
    )


def _build_market_absorption_summary(rental_ease: object) -> str:
    label = str(rental_ease.rental_ease_label).lower()
    confidence = float(rental_ease.confidence)
    if "high absorption" in label or "stable rental profile" in label:
        summary = "Town-level rental demand looks stable."
    elif "seasonal / mixed" in label:
        summary = "Town-level rental demand looks mixed and somewhat seasonal."
    else:
        summary = "Town-level rental demand looks relatively fragile."

    if confidence < 0.75:
        summary += " This still leans partly on priors and indirect market context."
    else:
        summary += " This is market context, not proof the specific property rents easily."
    return summary


def _build_rental_viability_label(income: object) -> str:
    if (
        income.rent_coverage is None
        or income.effective_monthly_rent is None
        or not getattr(income, "carrying_cost_complete", False)
    ):
        return "Unverified Rental Fallback"
    if income.rent_coverage >= 1.1:
        return "Supported Rental Fallback"
    if income.rent_coverage >= 0.9:
        return "Borderline Rental Fallback"
    return "Weak Rental Fallback"


def _build_rental_viability_summary(income: object) -> str:
    if getattr(income, "rent_source_type", "missing") == "missing":
        return "Property-level rental support could not be verified because rent and carry inputs are incomplete."
    if income.rent_coverage is None or income.effective_monthly_rent is None or not getattr(income, "carrying_cost_complete", False):
        operating_cash_flow = getattr(income, "operating_monthly_cash_flow", None)
        if operating_cash_flow is not None:
            return (
                f"Full rental fallback is still unverified because financing inputs are incomplete, "
                f"but pre-debt operating cash flow looks to be about ${operating_cash_flow:,.0f}/mo."
            )
        return "Property-level rental support could not be verified because financing or carry inputs are incomplete."
    if income.rent_coverage >= 1.1:
        return f"This looks financially supportable at about {income.rent_coverage:.2f}x carry, with estimated cash flow near ${income.monthly_cash_flow:,.0f}/mo."
    if income.rent_coverage >= 0.9:
        return f"Rent looks close to break-even at about {income.rent_coverage:.2f}x carry, with cash flow near ${income.monthly_cash_flow:,.0f}/mo."
    downside_burden = income.downside_burden or abs(income.monthly_cash_flow or 0.0)
    return f"Rent only covers about {income.rent_coverage:.2f}x of carry and would require about ${downside_burden:,.0f}/mo in subsidy."


def _build_assessment_summary(*, market_absorption_label: str, rental_viability_label: str) -> str:
    market_supportive = market_absorption_label in {"High Absorption", "Stable Rental Profile"}
    viability_supported = rental_viability_label == "Supported Rental Fallback"
    viability_borderline = rental_viability_label == "Borderline Rental Fallback"
    viability_unverified = rental_viability_label == "Unverified Rental Fallback"

    if market_supportive and viability_supported:
        return "Easy enough to rent, and the fallback economics also hold up."
    if market_supportive and viability_borderline:
        return "Demand looks supportive, but the fallback economics are only borderline."
    if market_supportive and viability_unverified:
        return "Easy enough to rent, but property-level fallback support is unverified."
    if market_supportive:
        return "Demand looks supportive, but this asset does not carry well as a rental."
    if viability_supported:
        return "The property looks rentable on paper, but the local absorption backdrop is thinner."
    if viability_unverified:
        return "Demand looks mixed, and property-level fallback support could not be verified."
    return "Rental demand may be there, but fallback financial resilience is weak."


def _build_days_to_rent_context(rental_ease: object) -> str:
    if rental_ease.estimated_days_to_rent is None:
        return "No days-to-rent estimate is available because current rental absorption evidence is too thin."

    days = int(rental_ease.estimated_days_to_rent)
    if days <= 30:
        tone = "relatively fast absorption"
    elif days <= 45:
        tone = "moderate absorption"
    else:
        tone = "slower absorption"

    if float(rental_ease.confidence) < 0.75:
        return f"About {tone} versus current Monmouth priors. Treat this as heuristic, not lease-up precision."
    return f"About {tone} versus the current Monmouth rental backdrop. Still a heuristic guide."


def _filter_market_unsupported_claims(items: list[str]) -> list[str]:
    filtered: list[str] = []
    for item in items:
        lowered = item.lower()
        if "property-specific" in lowered or "direct rental comps" in lowered or "property level" in lowered:
            filtered.append(item)
    return filtered


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped

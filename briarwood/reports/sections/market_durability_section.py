from __future__ import annotations

from briarwood.reports.section_helpers import get_scarcity_support, get_town_county_outlook
from briarwood.reports.schemas import MarketDurabilitySection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_market_durability_section(report: AnalysisReport) -> MarketDurabilitySection:
    outlook = get_town_county_outlook(report)
    scarcity = get_scarcity_support(report)
    town_score = outlook.score

    buyer_takeaway = (
        f"{town_score.summary} {scarcity.buyer_takeaway}"
        if scarcity.buyer_takeaway
        else town_score.summary
    )
    supporting_points = list(
        dict.fromkeys(
            town_score.demand_drivers[:2]
            + scarcity.demand_drivers[:2]
            + scarcity.scarcity_notes[:1]
        )
    )
    caveats = list(
        dict.fromkeys(
            town_score.demand_risks[:2]
            + town_score.unsupported_claims[:2]
            + scarcity.unsupported_claims[:2]
        )
    )
    confidence_notes = list(
        dict.fromkeys(
            [f"Town/county confidence: {town_score.confidence:.2f}."]
            + [f"Scarcity confidence: {scarcity.confidence:.2f}."]
            + [f"Data as of: {outlook.normalized.inputs.data_as_of}."]
            if outlook.normalized.inputs.data_as_of
            else [f"Town/county confidence: {town_score.confidence:.2f}.", f"Scarcity confidence: {scarcity.confidence:.2f}."]
        )
    )

    if not supporting_points:
        supporting_points = ["Supporting location and scarcity evidence is still thin."]
    if not caveats:
        caveats = ["No major local durability caveat was surfaced by the current inputs."]

    summary = (
        "This section explains why buyers may still want the property in a few years, and whether "
        "that demand looks durable enough to support a cleaner exit."
    )
    return MarketDurabilitySection(
        title="Why Buyers Will Still Want This",
        summary=summary,
        buyer_takeaway=buyer_takeaway,
        supporting_points=supporting_points,
        caveats=caveats,
        confidence_notes=confidence_notes,
        assessment=SectionAssessment(
            score=round((town_score.town_county_score + scarcity.scarcity_support_score) / 2, 2),
            confidence=min(town_score.confidence, scarcity.confidence),
            summary=(
                f"Location demand reads {town_score.location_thesis_label}, while scarcity support reads "
                f"{scarcity.scarcity_label}."
            ),
        ),
    )

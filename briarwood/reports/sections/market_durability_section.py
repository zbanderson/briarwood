from __future__ import annotations

from briarwood.reports.section_helpers import get_scarcity_support, get_town_county_outlook
from briarwood.reports.schemas import MarketDurabilitySection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_market_durability_section(report: AnalysisReport) -> MarketDurabilitySection:
    outlook = get_town_county_outlook(report)
    scarcity = get_scarcity_support(report)
    town_score = outlook.score

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
    confidence_notes.extend(
        note
        for note in town_score.assumptions_used
        if "FRED-backed" in note or "refreshed about every" in note or "last reviewed on" in note
    )
    confidence_notes = list(dict.fromkeys(confidence_notes))

    if not supporting_points:
        supporting_points = ["Supporting location and scarcity evidence is still thin."]
    if not caveats:
        caveats = ["No major local durability caveat was surfaced by the current inputs."]

    summary = "Demand durability depends on local support, scarcity, and what still lacks proof."
    return MarketDurabilitySection(
        title="Demand Durability",
        summary=summary,
        confidence_line=f"Confidence: town/county {town_score.confidence:.0%} | scarcity {scarcity.confidence:.0%}.",
        supporting_points=supporting_points,
        caveats=caveats,
        confidence_notes=confidence_notes,
        assessment=SectionAssessment(
            score=round((town_score.town_county_score + scarcity.scarcity_support_score) / 2, 2),
            confidence=min(town_score.confidence, scarcity.confidence),
            summary=(
                f"Demand reads {town_score.location_thesis_label}; scarcity reads {scarcity.scarcity_label}."
            ),
        ),
    )

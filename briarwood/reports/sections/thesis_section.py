from __future__ import annotations

from briarwood.reports.section_helpers import get_valuation_output
from briarwood.reports.schemas import SectionAssessment, ThesisSection
from briarwood.schemas import AnalysisReport


def build_thesis_section(report: AnalysisReport) -> ThesisSection:
    valuation_module = report.get_module("cost_valuation")
    valuation = get_valuation_output(report)
    risk = report.get_module("risk_constraints")
    town = report.get_module("town_intelligence")
    snapshot = report.get_module("property_snapshot")

    cap_rate = valuation.cap_rate
    cash_flow = valuation.monthly_cash_flow
    school_rating = town.metrics.get("school_rating")
    property_age = snapshot.metrics.get("property_age")
    risk_flags = str(risk.metrics.get("risk_flags", "none"))

    bullets = [
        f"Income support is currently {_percent_or_na(cap_rate)} on cap rate.",
        f"Monthly cash flow screens at ${_number(cash_flow):,.0f} before reserves.",
        f"Town quality proxy is {school_rating if school_rating is not None else 'n/a'} with favorable price trend.",
        f"Physical profile is {int(property_age)} years old." if isinstance(property_age, (int, float)) else "Physical profile needs further diligence.",
        f"Primary flagged risks: {risk_flags}.",
    ]
    summary = (
        "The investment thesis combines current cash flow, scenario upside, "
        "town quality, and flagged constraints into one concise view."
    )
    return ThesisSection(
        title="Investment Thesis",
        bullets=bullets,
        assessment=SectionAssessment(
            score=valuation_module.score,
            confidence=min(valuation_module.confidence, risk.confidence, town.confidence),
            summary=summary,
        ),
    )


def _number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _percent_or_na(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1%}"
    return "n/a"

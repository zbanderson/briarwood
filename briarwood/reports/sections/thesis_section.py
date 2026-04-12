from __future__ import annotations

from briarwood.decision_engine import build_decision
from briarwood.reports.schemas import SectionAssessment, ThesisSection
from briarwood.schemas import AnalysisReport


def build_thesis_section(report: AnalysisReport) -> ThesisSection:
    decision = build_decision(report)
    current_value = report.get_module("current_value")

    must_go_right = list(decision.required_beliefs[:3])
    what_breaks = [decision.secondary_reason] if decision.secondary_reason else []
    if not what_breaks:
        what_breaks = ["The current decision depends on underwriting assumptions holding close to the base case."]

    return ThesisSection(
        title="Decision Conditions",
        deal_type=decision.recommendation,
        must_go_right=must_go_right,
        what_breaks=what_breaks,
        so_what=[
            decision.primary_reason,
            decision.secondary_reason,
        ],
        assessment=SectionAssessment(
            score=current_value.score,
            confidence=decision.conviction,
            summary="The top-line call is anchored to valuation gap, carry, and evidence quality.",
        ),
    )

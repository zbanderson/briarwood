from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.decision_engine import build_decision
from briarwood.risk_bar import RiskBarItem, build_risk_bar
from briarwood.schemas import AnalysisReport


@dataclass(slots=True)
class QuickReasonItem:
    text: str


@dataclass(slots=True)
class QuickUseCaseItem:
    label: str


@dataclass(slots=True)
class QuickDecisionViewModel:
    recommendation: str
    conviction: float
    confidence: str
    primary_reason: str
    secondary_reason: str
    risk_bar: list[RiskBarItem] = field(default_factory=list)
    key_reasons: list[QuickReasonItem] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    best_use_cases: list[QuickUseCaseItem] = field(default_factory=list)
    required_beliefs: list[str] = field(default_factory=list)
    full_analysis_available: bool = True


def build_quick_decision_view(report: AnalysisReport) -> QuickDecisionViewModel:
    decision = build_decision(report)
    risk_bar = build_risk_bar(report)
    confidence = _confidence_label(risk_bar)
    return QuickDecisionViewModel(
        recommendation=decision.recommendation,
        conviction=decision.conviction,
        confidence=confidence,
        primary_reason=decision.primary_reason,
        secondary_reason=decision.secondary_reason,
        risk_bar=risk_bar,
        key_reasons=[
            QuickReasonItem(text=item)
            for item in [decision.primary_reason, decision.secondary_reason]
            if item
        ],
        risks=[item.label for item in risk_bar if item.level == "High"][:3],
        best_use_cases=[QuickUseCaseItem(label=item) for item in _best_use_cases(decision.recommendation)],
        required_beliefs=list(decision.required_beliefs),
        full_analysis_available=True,
    )


def _confidence_label(risk_bar: list[RiskBarItem]) -> str:
    confidence_item = next((item for item in risk_bar if item.name == "Confidence"), None)
    if confidence_item is None:
        return "Medium"
    if confidence_item.level == "Low":
        return "High"
    if confidence_item.level == "Medium":
        return "Medium"
    return "Low"


def _best_use_cases(recommendation: str) -> list[str]:
    mapping = {
        "BUY": ["Move quickly if the thesis matches your plan", "Best when the purchase is conviction-led"],
        "LEAN BUY": ["Worth pursuing with price discipline", "Best when the plan is straightforward"],
        "NEUTRAL": ["Keep it on the list, but verify more first", "Best for selective follow-up"],
        "LEAN PASS": ["Only works if price or carry improves", "Best as a watchlist candidate"],
        "AVOID": ["Do not stretch to make this work", "Best only if the deal resets materially"],
    }
    return mapping.get(recommendation, ["Selective fit"])

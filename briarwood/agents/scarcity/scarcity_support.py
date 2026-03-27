from __future__ import annotations

from briarwood.agents.scarcity.demand_consistency import DemandConsistencyScorer
from briarwood.agents.scarcity.land_scarcity import LandScarcityScorer
from briarwood.agents.scarcity.location_scarcity import LocationScarcityScorer
from briarwood.agents.scarcity.schemas import ScarcitySupportInputs, ScarcitySupportScore


class ScarcitySupportScorer:
    """Combine early scarcity components into a report-ready scarcity support view."""

    _CONFIDENCE_WEIGHTS = {
        "demand": 0.50,
        "location": 0.30,
        "land": 0.20,
    }

    def __init__(
        self,
        *,
        demand_consistency_scorer: DemandConsistencyScorer | None = None,
        location_scorer: LocationScarcityScorer | None = None,
        land_scorer: LandScarcityScorer | None = None,
    ) -> None:
        self.demand_consistency_scorer = demand_consistency_scorer or DemandConsistencyScorer()
        self.location_scorer = location_scorer or LocationScarcityScorer()
        self.land_scorer = land_scorer or LandScarcityScorer()

    def score(self, payload: ScarcitySupportInputs | dict[str, object]) -> ScarcitySupportScore:
        inputs = payload if isinstance(payload, ScarcitySupportInputs) else ScarcitySupportInputs.model_validate(payload)

        demand = self.demand_consistency_scorer.score(inputs.demand_consistency)
        location = self.location_scorer.score(inputs.location_scarcity)
        land = self.land_scorer.score(inputs.land_scarcity)

        scarcity_score = (0.55 * location.location_scarcity_score) + (0.45 * land.land_scarcity_score)
        scarcity_support_score = (0.60 * scarcity_score) + (0.40 * demand.demand_consistency_score)
        confidence = self._confidence(
            demand_confidence=demand.confidence,
            location_confidence=location.confidence,
            land_confidence=land.confidence,
        )
        label = self._label(
            score=scarcity_support_score,
            confidence=confidence,
            location_confidence=location.confidence,
        )

        missing_inputs = sorted(
            set(demand.missing_inputs)
            | set(location.missing_inputs)
            | set(land.missing_inputs)
        )
        unsupported_claims = list(dict.fromkeys(
            demand.unsupported_claims + location.unsupported_claims + land.unsupported_claims
        ))

        return ScarcitySupportScore(
            demand_consistency_score=demand.demand_consistency_score,
            location_scarcity_score=location.location_scarcity_score,
            land_scarcity_score=land.land_scarcity_score,
            scarcity_score=round(scarcity_score, 2),
            scarcity_support_score=round(scarcity_support_score, 2),
            scarcity_label=label,
            confidence=round(confidence, 2),
            demand_drivers=list(dict.fromkeys(demand.demand_drivers + location.demand_drivers + land.demand_drivers)),
            scarcity_notes=list(dict.fromkeys(location.scarcity_notes + land.scarcity_notes)),
            missing_inputs=missing_inputs,
            unsupported_claims=unsupported_claims,
            summary=self._summary(
                town=inputs.demand_consistency.town,
                state=inputs.demand_consistency.state,
                label=label,
                confidence=confidence,
            ),
            buyer_takeaway=self._buyer_takeaway(
                town=inputs.demand_consistency.town,
                state=inputs.demand_consistency.state,
                label=label,
                confidence=confidence,
            ),
        )

    def _confidence(
        self,
        *,
        demand_confidence: float,
        location_confidence: float,
        land_confidence: float,
    ) -> float:
        return (
            (self._CONFIDENCE_WEIGHTS["demand"] * demand_confidence)
            + (self._CONFIDENCE_WEIGHTS["location"] * location_confidence)
            + (self._CONFIDENCE_WEIGHTS["land"] * land_confidence)
        )

    def _label(self, *, score: float, confidence: float, location_confidence: float) -> str:
        if confidence < 0.40:
            return "low-confidence"
        if score >= 75:
            if location_confidence < 0.60:
                return "limited scarcity support"
            return "high scarcity support"
        if score >= 60:
            if location_confidence < 0.35:
                return "limited scarcity support"
            return "meaningful scarcity support"
        if score >= 45:
            return "limited scarcity support"
        return "weak scarcity support"

    def _summary(self, *, town: str, state: str, label: str, confidence: float) -> str:
        if confidence < 0.40:
            return (
                f"{town}, {state} lacks enough evidence across demand and scarcity components for a reliable scarcity support view."
            )
        if label == "high scarcity support":
            return (
                f"{town}, {state} shows high scarcity support: the property appears difficult to replicate and the market looks capable of consistently rewarding those traits."
            )
        if label == "meaningful scarcity support":
            return (
                f"{town}, {state} shows meaningful scarcity support, suggesting scarcity may help both pricing durability and resale flexibility."
            )
        if label == "limited scarcity support":
            return (
                f"{town}, {state} shows only limited scarcity support; some scarce traits may exist, but the evidence is not yet strong enough to lean on heavily."
            )
        if label == "weak scarcity support":
            return (
                f"The current evidence does not show strong scarcity support in {town}, {state}."
            )
        return (
            f"{town}, {state} has insufficient evidence for a confident scarcity support view."
        )

    def _buyer_takeaway(self, *, town: str, state: str, label: str, confidence: float) -> str:
        if confidence < 0.40:
            return (
                "Briarwood cannot confidently say scarcity is protecting this property yet. "
                "Treat any scarcity story here as tentative until better local evidence is available."
            )
        if label == "high scarcity support":
            return (
                "This property appears to have real protection from both scarcity and demand. "
                "That does not eliminate risk, but it improves the odds that buyers will still care about it on resale."
            )
        if label == "meaningful scarcity support":
            return (
                "Scarcity is helping the story here in a meaningful way. "
                "The property looks harder to replicate than nearby substitutes, which may help support value and resale flexibility."
            )
        if label == "limited scarcity support":
            return (
                "There may be some scarce traits here, but Briarwood would not lean too heavily on scarcity alone as downside protection."
            )
        if label == "weak scarcity support":
            return (
                "Scarcity does not currently look like a major safety net here. "
                "The deal would need to work more on price discipline and broader market support."
            )
        return (
            f"Scarcity support in {town}, {state} is not yet strong enough to anchor a confident client narrative."
        )


def score_scarcity_support(payload: ScarcitySupportInputs | dict[str, object]) -> ScarcitySupportScore:
    """Convenience wrapper for one-shot scarcity support scoring."""

    return ScarcitySupportScorer().score(payload)

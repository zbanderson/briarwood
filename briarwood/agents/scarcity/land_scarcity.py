from __future__ import annotations

from briarwood.agents.scarcity.schemas import LandScarcityInputs, LandScarcityScore
from briarwood.scoring import clamp_score


class LandScarcityScorer:
    """Score how difficult it is to replicate a property's lot attributes and optionality."""

    _CONFIDENCE_WEIGHTS = {
        "lot_size_sqft": 0.35,
        "local_median_lot_size_sqft": 0.35,
        "lot_is_corner": 0.10,
        "adu_possible": 0.10,
        "redevelopment_optional": 0.10,
    }

    def score(self, payload: LandScarcityInputs | dict[str, object]) -> LandScarcityScore:
        inputs = payload if isinstance(payload, LandScarcityInputs) else LandScarcityInputs.model_validate(payload)

        score = 50.0
        missing_inputs = self._missing_inputs(inputs)
        unsupported_claims: list[str] = []

        lot_ratio: float | None = None
        if inputs.lot_size_sqft is not None and inputs.local_median_lot_size_sqft is not None:
            lot_ratio = inputs.lot_size_sqft / inputs.local_median_lot_size_sqft
            if lot_ratio >= 1.50:
                score += 15
            elif lot_ratio >= 1.25:
                score += 10
            elif lot_ratio <= 0.75:
                score -= 10

        if inputs.lot_is_corner is True:
            score += 5
        if inputs.adu_possible is True:
            score += 10
        if inputs.redevelopment_optional is True:
            score += 10

        confidence = self._confidence(inputs)
        final_score = clamp_score(score)
        label = self._label(final_score, confidence)

        if inputs.lot_size_sqft is None:
            unsupported_claims.append("Subject lot size is missing.")
        if inputs.local_median_lot_size_sqft is None:
            unsupported_claims.append("Local lot benchmark is missing.")
        if confidence < 0.60:
            unsupported_claims.append("Land scarcity is low confidence due to missing lot benchmark context.")

        return LandScarcityScore(
            land_scarcity_score=round(final_score, 2),
            land_scarcity_label=label,
            confidence=round(confidence, 2),
            demand_drivers=self._drivers(inputs, lot_ratio, final_score),
            scarcity_notes=self._notes(inputs, confidence),
            missing_inputs=missing_inputs,
            unsupported_claims=unsupported_claims,
            summary=self._summary(inputs, label, confidence, lot_ratio),
        )

    def _missing_inputs(self, inputs: LandScarcityInputs) -> list[str]:
        return [field_name for field_name in self._CONFIDENCE_WEIGHTS if getattr(inputs, field_name) is None]

    def _confidence(self, inputs: LandScarcityInputs) -> float:
        total_weight = sum(self._CONFIDENCE_WEIGHTS.values())
        populated_weight = sum(
            weight for field_name, weight in self._CONFIDENCE_WEIGHTS.items() if getattr(inputs, field_name) is not None
        )
        return populated_weight / total_weight

    def _label(self, score: float, confidence: float) -> str:
        if confidence < 0.40:
            return "low-confidence"
        if score >= 75:
            return "strong"
        if score >= 60:
            return "meaningful"
        if score >= 45:
            return "limited"
        return "weak"

    def _drivers(self, inputs: LandScarcityInputs, lot_ratio: float | None, score: float) -> list[str]:
        drivers: list[str] = []
        if lot_ratio is not None and lot_ratio >= 1.25:
            drivers.append(f"The lot is {lot_ratio:.2f}x the local median lot size.")
        if inputs.lot_is_corner is True:
            drivers.append("Corner-lot positioning adds frontage and flexibility.")
        if inputs.adu_possible is True:
            drivers.append("ADU potential adds future optionality.")
        if inputs.redevelopment_optional is True:
            drivers.append("Redevelopment optionality improves long-term scarcity support.")
        if not drivers and score >= 50:
            drivers.append("Available lot characteristics suggest some land-level scarcity support.")
        return drivers

    def _notes(self, inputs: LandScarcityInputs, confidence: float) -> list[str]:
        notes: list[str] = []
        if inputs.local_median_lot_size_sqft is not None:
            notes.append("Land scarcity is benchmarked against the local median lot size.")
        if confidence < 0.60:
            notes.append("Land scarcity should be treated cautiously because lot benchmark context is incomplete.")
        return notes

    def _summary(self, inputs: LandScarcityInputs, label: str, confidence: float, lot_ratio: float | None) -> str:
        if confidence < 0.40:
            return (
                f"{inputs.town}, {inputs.state} lacks enough lot benchmark context for a reliable land scarcity view."
            )
        if label == "strong":
            return (
                f"{inputs.town}, {inputs.state} shows strong land scarcity support, with a lot profile that appears difficult to replicate locally."
            )
        if label == "meaningful":
            return (
                f"{inputs.town}, {inputs.state} shows meaningful land scarcity support, suggesting the site's lot characteristics add real optionality or rarity."
            )
        if label == "limited":
            return (
                f"{inputs.town}, {inputs.state} shows only limited land scarcity support based on the available lot data."
            )
        if label == "weak":
            return (
                f"The current evidence does not show strong land scarcity support in {inputs.town}, {inputs.state}."
            )
        return (
            f"{inputs.town}, {inputs.state} has insufficient lot evidence for a confident land scarcity view."
        )

def score_land_scarcity(payload: LandScarcityInputs | dict[str, object]) -> LandScarcityScore:
    """Convenience wrapper for one-shot land scarcity scoring."""

    return LandScarcityScorer().score(payload)

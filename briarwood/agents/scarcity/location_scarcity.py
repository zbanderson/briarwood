from __future__ import annotations

from briarwood.agents.scarcity.schemas import LocationScarcityInputs, LocationScarcityScore


class LocationScarcityScorer:
    """Score how difficult it is to replicate a property's location advantages."""

    _CONFIDENCE_WEIGHTS = {
        "anchor_type": 0.25,
        "distance_to_anchor_miles": 0.35,
        "comparable_count_within_anchor_radius": 0.25,
        "anchor_radius_miles": 0.15,
    }

    def score(self, payload: LocationScarcityInputs | dict[str, object]) -> LocationScarcityScore:
        inputs = payload if isinstance(payload, LocationScarcityInputs) else LocationScarcityInputs.model_validate(payload)

        score = 50.0
        missing_inputs = self._missing_inputs(inputs)
        unsupported_claims: list[str] = []

        if inputs.distance_to_anchor_miles is not None:
            if inputs.distance_to_anchor_miles <= 0.20:
                score += 20
            elif inputs.distance_to_anchor_miles <= 0.50:
                score += 15
            elif inputs.distance_to_anchor_miles <= 1.00:
                score += 5
            elif inputs.distance_to_anchor_miles > 2.0:
                score -= 10

        if inputs.comparable_count_within_anchor_radius is not None:
            if inputs.comparable_count_within_anchor_radius <= 10:
                score += 15
            elif inputs.comparable_count_within_anchor_radius <= 20:
                score += 10
            elif inputs.comparable_count_within_anchor_radius <= 35:
                score += 5
            elif inputs.comparable_count_within_anchor_radius > 50:
                score -= 10

        if inputs.anchor_radius_miles is not None and inputs.distance_to_anchor_miles is not None:
            if inputs.distance_to_anchor_miles <= inputs.anchor_radius_miles * 0.25:
                score += 5

        confidence = self._confidence(inputs)
        final_score = self._clamp_score(score)
        label = self._label(final_score, confidence)

        if inputs.anchor_type is None:
            unsupported_claims.append("Anchor feature type is missing.")
        if inputs.distance_to_anchor_miles is None:
            unsupported_claims.append("Anchor proximity could not be confirmed.")
        if inputs.comparable_count_within_anchor_radius is None:
            unsupported_claims.append("Local substitute scarcity could not be confirmed.")
        if confidence < 0.60:
            unsupported_claims.append("Location scarcity is low confidence due to missing core anchor context.")

        return LocationScarcityScore(
            location_scarcity_score=round(final_score, 2),
            location_scarcity_label=label,
            confidence=round(confidence, 2),
            demand_drivers=self._drivers(inputs, final_score),
            scarcity_notes=self._notes(inputs, confidence),
            missing_inputs=missing_inputs,
            unsupported_claims=unsupported_claims,
            summary=self._summary(inputs, label, confidence),
        )

    def _missing_inputs(self, inputs: LocationScarcityInputs) -> list[str]:
        return [field_name for field_name in self._CONFIDENCE_WEIGHTS if getattr(inputs, field_name) is None]

    def _confidence(self, inputs: LocationScarcityInputs) -> float:
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

    def _drivers(self, inputs: LocationScarcityInputs, score: float) -> list[str]:
        drivers: list[str] = []
        if inputs.anchor_type and inputs.distance_to_anchor_miles is not None and inputs.distance_to_anchor_miles <= 0.50:
            drivers.append(
                f"The property is close to its anchor feature ({inputs.anchor_type}) at {inputs.distance_to_anchor_miles:.2f} miles."
            )
        if (
            inputs.comparable_count_within_anchor_radius is not None
            and inputs.comparable_count_within_anchor_radius <= 20
            and inputs.anchor_radius_miles is not None
        ):
            drivers.append(
                f"Only {inputs.comparable_count_within_anchor_radius} comparable properties were identified within {inputs.anchor_radius_miles:.2f} miles."
            )
        if not drivers and score >= 50:
            drivers.append("Available anchor and substitute data suggest some location scarcity support.")
        return drivers

    def _notes(self, inputs: LocationScarcityInputs, confidence: float) -> list[str]:
        notes: list[str] = []
        if inputs.anchor_type is not None:
            notes.append(f"Scarcity is being evaluated relative to the anchor type: {inputs.anchor_type}.")
        if confidence < 0.60:
            notes.append("Location scarcity should be treated cautiously because some anchor context is missing.")
        return notes

    def _summary(self, inputs: LocationScarcityInputs, label: str, confidence: float) -> str:
        if confidence < 0.40:
            return (
                f"{inputs.town}, {inputs.state} lacks enough anchor and substitute data for a reliable location scarcity view."
            )
        if label == "strong":
            return (
                f"{inputs.town}, {inputs.state} shows strong location scarcity, with a hard-to-replicate position relative to a meaningful demand anchor."
            )
        if label == "meaningful":
            return (
                f"{inputs.town}, {inputs.state} shows meaningful location scarcity, suggesting the property's positioning may be difficult to replace locally."
            )
        if label == "limited":
            return (
                f"{inputs.town}, {inputs.state} shows only limited location scarcity support based on the available anchor data."
            )
        if label == "weak":
            return (
                f"The current evidence does not show strong location scarcity support in {inputs.town}, {inputs.state}."
            )
        return (
            f"{inputs.town}, {inputs.state} has insufficient anchor evidence for a confident location scarcity view."
        )

    def _clamp_score(self, value: float) -> float:
        return max(0.0, min(value, 100.0))


def score_location_scarcity(payload: LocationScarcityInputs | dict[str, object]) -> LocationScarcityScore:
    """Convenience wrapper for one-shot location scarcity scoring."""

    return LocationScarcityScorer().score(payload)

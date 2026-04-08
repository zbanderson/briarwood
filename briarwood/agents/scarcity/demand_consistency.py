from __future__ import annotations

from briarwood.agents.scarcity.schemas import DemandConsistencyInputs, DemandConsistencyScore
from briarwood.scoring import clamp_score


class DemandConsistencyScorer:
    """Score how reliably a local market rewards scarce and desirable traits."""

    _CONFIDENCE_WEIGHTS = {
        "liquidity_signal": 0.25,
        "months_of_supply": 0.10,
        "days_on_market": 0.10,
        "town_price_trend": 0.20,
        "county_price_trend": 0.15,
        "school_signal": 0.20,
    }

    def score(self, payload: DemandConsistencyInputs | dict[str, object]) -> DemandConsistencyScore:
        inputs = payload if isinstance(payload, DemandConsistencyInputs) else DemandConsistencyInputs.model_validate(payload)

        missing_inputs = self._missing_inputs(inputs)
        unsupported_claims: list[str] = []

        score = 50.0

        if inputs.liquidity_signal == "strong":
            score += 15
        elif inputs.liquidity_signal == "normal":
            score += 10
        elif inputs.liquidity_signal == "fragile":
            score -= 15

        if inputs.months_of_supply is not None:
            if inputs.months_of_supply <= 3.0:
                score += 10
            elif inputs.months_of_supply <= 6.0:
                score += 5
            else:
                score -= 10

        if inputs.days_on_market is not None:
            if inputs.days_on_market < 21:
                score += 10
            elif inputs.days_on_market <= 45:
                score += 5
            elif inputs.days_on_market > 60:
                score -= 10

        if inputs.town_price_trend is not None:
            if inputs.town_price_trend > 0.03:
                score += 10
            elif inputs.town_price_trend <= 0:
                score -= 10

        if inputs.county_price_trend is not None:
            if inputs.county_price_trend > 0.03:
                score += 5
            elif inputs.county_price_trend <= 0:
                score -= 5

        if inputs.school_signal is not None:
            if inputs.school_signal >= 7:
                score += 10
            elif inputs.school_signal < 5:
                score -= 5

        confidence = self._confidence(inputs)
        final_score = clamp_score(score)
        label = self._label(final_score, confidence)

        if inputs.liquidity_signal is None and inputs.months_of_supply is None and inputs.days_on_market is None:
            unsupported_claims.append("Liquidity support could not be confirmed.")
        if inputs.town_price_trend is None and inputs.county_price_trend is None:
            unsupported_claims.append("Price-trend support could not be confirmed.")
        if inputs.school_signal is None:
            unsupported_claims.append("School-related demand support is missing.")
        if confidence < 0.60:
            unsupported_claims.append("Demand consistency is low confidence due to missing core support signals.")

        return DemandConsistencyScore(
            demand_consistency_score=round(final_score, 2),
            demand_consistency_label=label,
            confidence=round(confidence, 2),
            demand_drivers=self._drivers(inputs, final_score),
            demand_risks=self._risks(inputs, confidence),
            missing_inputs=missing_inputs,
            unsupported_claims=unsupported_claims,
            summary=self._summary(inputs, label, confidence),
        )

    def _missing_inputs(self, inputs: DemandConsistencyInputs) -> list[str]:
        return [field_name for field_name in self._CONFIDENCE_WEIGHTS if getattr(inputs, field_name) is None]

    def _confidence(self, inputs: DemandConsistencyInputs) -> float:
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
            return "supportive"
        if score >= 45:
            return "mixed"
        return "weak"

    def _drivers(self, inputs: DemandConsistencyInputs, score: float) -> list[str]:
        drivers: list[str] = []
        if inputs.liquidity_signal == "strong":
            drivers.append("Liquidity conditions are strong.")
        elif inputs.liquidity_signal == "normal":
            drivers.append("Liquidity conditions appear orderly.")
        if inputs.months_of_supply is not None and inputs.months_of_supply <= 3.0:
            drivers.append(f"Months of supply is tight at {inputs.months_of_supply:.1f}.")
        if inputs.town_price_trend is not None and inputs.town_price_trend > 0.03:
            drivers.append(f"Town price trend is supportive at {inputs.town_price_trend:.1%}.")
        if inputs.county_price_trend is not None and inputs.county_price_trend > 0.03:
            drivers.append(f"County trend reinforces demand at {inputs.county_price_trend:.1%}.")
        if inputs.school_signal is not None and inputs.school_signal >= 7:
            drivers.append(f"School signal supports durable buyer demand at {inputs.school_signal:.1f}/10.")
        if not drivers and score >= 50:
            drivers.append("Available signals suggest some continuing buyer demand, but not a standout pattern.")
        return drivers

    def _risks(self, inputs: DemandConsistencyInputs, confidence: float) -> list[str]:
        risks: list[str] = []
        if inputs.liquidity_signal == "fragile":
            risks.append("Liquidity looks fragile.")
        if inputs.months_of_supply is not None and inputs.months_of_supply > 6.0:
            risks.append(f"Months of supply is elevated at {inputs.months_of_supply:.1f}.")
        if inputs.days_on_market is not None and inputs.days_on_market > 60:
            risks.append("Properties appear to be taking longer to clear the market.")
        if inputs.town_price_trend is not None and inputs.town_price_trend <= 0:
            risks.append("Town price momentum is flat or negative.")
        if inputs.county_price_trend is not None and inputs.county_price_trend <= 0:
            risks.append("County price trend does not reinforce local demand.")
        if inputs.school_signal is not None and inputs.school_signal < 5:
            risks.append("School signal is not especially supportive.")
        if confidence < 0.60:
            risks.append("Core demand consistency inputs are incomplete.")
        return risks

    def _summary(self, inputs: DemandConsistencyInputs, label: str, confidence: float) -> str:
        if confidence < 0.40:
            return (
                f"{inputs.town}, {inputs.state} lacks enough core evidence to judge whether the market consistently "
                "rewards scarce traits; this should be treated as descriptive only."
            )
        if label == "strong":
            return (
                f"{inputs.town}, {inputs.state} shows strong signs that the market consistently rewards desirable and "
                "scarce housing traits."
            )
        if label == "supportive":
            return (
                f"{inputs.town}, {inputs.state} appears supportive, with enough evidence to believe the market usually "
                "absorbs desirable inventory reasonably well."
            )
        if label == "mixed":
            return (
                f"{inputs.town}, {inputs.state} shows mixed demand consistency; some support exists, but it is not strong "
                "enough to be relied on as a full safety net."
            )
        if label == "weak":
            return (
                f"The current evidence does not show strong demand consistency in {inputs.town}, {inputs.state}."
            )
        return (
            f"{inputs.town}, {inputs.state} has insufficient core data for a reliable demand consistency view."
        )

def score_demand_consistency(payload: DemandConsistencyInputs | dict[str, object]) -> DemandConsistencyScore:
    """Convenience wrapper for one-shot demand consistency scoring."""

    return DemandConsistencyScorer().score(payload)

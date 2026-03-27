from __future__ import annotations

from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.scoring import clamp_score


class TownIntelligenceModule:
    name = "town_intelligence"

    def run(self, property_input: PropertyInput) -> ModuleResult:
        price_trend = property_input.town_price_trend or 0
        population_trend = property_input.town_population_trend or 0
        school_rating = property_input.school_rating or 0

        score = 50 + (price_trend * 500) + (population_trend * 400) + (school_rating * 3)
        confidence = 0.85 if property_input.school_rating is not None else 0.55

        metrics = {
            "town": property_input.town,
            "state": property_input.state,
            "town_price_trend": price_trend,
            "town_population_trend": population_trend,
            "school_rating": school_rating,
            "flood_risk": property_input.flood_risk,
        }
        summary = (
            f"{property_input.town} shows price trend of {price_trend:.1%}, "
            f"population trend of {population_trend:.1%}, and school rating {school_rating:.1f}."
        )
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=clamp_score(score),
            confidence=confidence,
            summary=summary,
        )

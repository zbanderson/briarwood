from __future__ import annotations

from briarwood.agents.rental_ease.narrative import build_rental_ease_summary
from briarwood.agents.rental_ease.priors import RentalEasePrior, get_rental_ease_prior
from briarwood.agents.rental_ease.schemas import RentalEaseInput, RentalEaseOutput
from briarwood.agents.rental_ease.scoring import (
    clamp_score,
    label_for_score,
    liquidity_view_to_score,
    rent_support_to_score,
)


class RentalEaseAgent:
    """Score how easy and durable the rental thesis looks for a property."""

    _BASE_WEIGHTS = {
        "liquidity": 0.35,
        "demand_depth": 0.25,
        "rent_support": 0.25,
        "structural_support": 0.15,
    }

    def run(self, payload: RentalEaseInput | dict[str, object]) -> RentalEaseOutput:
        inputs = payload if isinstance(payload, RentalEaseInput) else RentalEaseInput.model_validate(payload)
        prior = get_rental_ease_prior(inputs.town, inputs.state)

        assumptions: list[str] = []
        unsupported_claims: list[str] = []
        warnings: list[str] = []

        if prior is None:
            assumptions.append(
                "No Monmouth County rental-ease prior was available for this town, so Briarwood relied on general fallback scoring."
            )
            unsupported_claims.append(
                "Town-specific rental ease priors are currently only defined for Briarwood's Monmouth County shore-town scope."
            )
        else:
            assumptions.append(
                f"Rental ease uses a Briarwood v1 rental prior for {prior.town}, which should be treated as structured market judgment rather than source truth."
            )
        if inputs.zillow_rent_index_current is not None and inputs.zillow_rent_index_prior_year is not None:
            assumptions.append(
                f"Zillow rental research is used as {inputs.zillow_context_scope or 'market'}-level context only, not as property-specific rental truth."
            )
        if inputs.rent_source_type == "estimated":
            assumptions.append("Property-level rent support uses an estimated rent input, not a provided rent figure.")
        elif inputs.rent_source_type == "missing":
            warnings.append("Rent not provided; rental viability remains market-informed rather than financially verified.")

        liquidity_score = self._liquidity_score(inputs, prior, assumptions)
        demand_depth_score = self._demand_depth_score(inputs, prior, assumptions)
        rent_support_score = self._rent_support_score(inputs, assumptions, unsupported_claims, warnings)
        structural_support_score = self._structural_support_score(inputs, prior, assumptions)
        estimated_days_to_rent = self._estimated_days_to_rent(inputs, prior, liquidity_score, assumptions, warnings)

        final_score = self._final_score(
            liquidity_score=liquidity_score,
            demand_depth_score=demand_depth_score,
            rent_support_score=rent_support_score,
            structural_support_score=structural_support_score,
            has_rent_support=inputs.income_support_ratio is not None or inputs.price_to_rent is not None,
        )
        label = label_for_score(final_score)

        confidence = self._confidence(inputs, prior)
        if inputs.rent_source_type == "missing" or inputs.estimated_monthly_rent is None:
            unsupported_claims.append("Property-specific rent evidence is missing, so rental ease leans more heavily on town and structural signals.")
        elif inputs.rent_source_type == "estimated":
            unsupported_claims.append("Property-specific rent support is estimated rather than directly provided.")
        if inputs.town_county_score is None:
            unsupported_claims.append("Town/county demand evidence is missing, so demand depth is only partly supported.")
        if inputs.scarcity_support_score is None:
            unsupported_claims.append("Structural support lacks a sourced scarcity signal.")
        if not inputs.financing_complete:
            warnings.append("Financing inputs are incomplete, so rental viability is only partly verified.")
        if confidence < 0.60:
            warnings.append("Rental ease confidence is low because the current view relies on partial evidence and priors.")

        drivers = self._drivers(inputs, prior, liquidity_score, demand_depth_score, rent_support_score, structural_support_score)
        risks = self._risks(inputs, prior, liquidity_score, demand_depth_score, rent_support_score, confidence)
        summary = build_rental_ease_summary(
            label=label,
            liquidity_score=liquidity_score,
            demand_depth_score=demand_depth_score,
            rent_support_score=rent_support_score,
            structural_support_score=structural_support_score,
            confidence=confidence,
            drivers=drivers,
            risks=risks,
        )

        return RentalEaseOutput(
            rental_ease_score=round(final_score, 2),
            rental_ease_label=label,
            liquidity_score=round(liquidity_score, 2),
            demand_depth_score=round(demand_depth_score, 2),
            rent_support_score=round(rent_support_score, 2),
            structural_support_score=round(structural_support_score, 2),
            estimated_days_to_rent=estimated_days_to_rent,
            summary=summary,
            drivers=drivers,
            risks=risks,
            confidence=round(confidence, 2),
            assumptions=assumptions,
            unsupported_claims=unsupported_claims,
            warnings=warnings,
            zillow_context_used=inputs.zillow_rent_index_current is not None,
        )

    def _liquidity_score(
        self,
        inputs: RentalEaseInput,
        prior: RentalEasePrior | None,
        assumptions: list[str],
    ) -> float:
        prior_score = prior.liquidity * 100 if prior else 55.0
        score = prior_score

        liquidity_view_score = liquidity_view_to_score(inputs.liquidity_view)
        if liquidity_view_score is not None:
            score = (0.65 * score) + (0.35 * liquidity_view_score)
        else:
            assumptions.append("Liquidity score leans more heavily on town prior because no live liquidity view was available.")

        if inputs.days_on_market is not None:
            if inputs.days_on_market <= 21:
                score += 4.0
            elif inputs.days_on_market > 60:
                score -= 8.0
        if inputs.zillow_renter_demand_index is not None:
            score = (0.75 * score) + (0.25 * inputs.zillow_renter_demand_index)

        if prior is not None:
            score -= prior.premium_fragility * 8.0
        return clamp_score(score)

    def _demand_depth_score(
        self,
        inputs: RentalEaseInput,
        prior: RentalEasePrior | None,
        assumptions: list[str],
    ) -> float:
        if prior is None:
            assumptions.append("Demand depth uses a generic fallback because no town prior was available.")
            prior_year_round = 0.55
            prior_seasonality = 0.45
        else:
            prior_year_round = prior.year_round_demand
            prior_seasonality = prior.seasonality

        market_score = inputs.town_county_score if inputs.town_county_score is not None else 55.0
        if inputs.town_county_score is None:
            assumptions.append("Demand depth uses a fallback market score because town/county outlook is missing.")

        zillow_demand_support = self._zillow_demand_support(inputs)

        score = (
            0.45 * (prior_year_round * 100)
            + 0.30 * market_score
            + 0.15 * ((1 - prior_seasonality) * 100)
            + 0.10 * zillow_demand_support
        )
        return clamp_score(score)

    def _rent_support_score(
        self,
        inputs: RentalEaseInput,
        assumptions: list[str],
        unsupported_claims: list[str],
        warnings: list[str],
    ) -> float:
        score = rent_support_to_score(
            income_support_ratio=inputs.income_support_ratio,
            price_to_rent=inputs.price_to_rent,
        )
        if score is not None:
            if inputs.zillow_rent_forecast_one_year is not None:
                if inputs.zillow_rent_forecast_one_year >= 0.03:
                    score += 4.0
                elif inputs.zillow_rent_forecast_one_year < 0:
                    score -= 5.0
            return score

        assumptions.append("Rent support score is provisional because property-specific rent support inputs are incomplete.")
        unsupported_claims.append("Rent support could not be measured directly from rent and carry economics.")
        warnings.append("Estimated days to rent and absorption quality should be treated cautiously without property-level rent support.")
        return 38.0

    def _structural_support_score(
        self,
        inputs: RentalEaseInput,
        prior: RentalEasePrior | None,
        assumptions: list[str],
    ) -> float:
        prior_score = prior.structural_desirability * 100 if prior else 52.0
        scarcity_score = inputs.scarcity_support_score
        if scarcity_score is None:
            assumptions.append("Structural support leans on town prior because scarcity support is incomplete.")
            scarcity_score = prior_score * 0.9

        score = (0.55 * scarcity_score) + (0.45 * prior_score)
        if inputs.flood_risk == "medium":
            score -= 6.0
        elif inputs.flood_risk == "high":
            score -= 12.0
        return clamp_score(score)

    def _estimated_days_to_rent(
        self,
        inputs: RentalEaseInput,
        prior: RentalEasePrior | None,
        liquidity_score: float,
        assumptions: list[str],
        warnings: list[str],
    ) -> int | None:
        if prior is None:
            warnings.append("Estimated days to rent is unavailable because no town prior exists for this market.")
            return None

        days = float(prior.default_days_to_rent)
        if liquidity_score >= 80:
            days -= 6
        elif liquidity_score < 55:
            days += 8

        days += prior.seasonality * 8
        days += prior.premium_fragility * 6

        if inputs.liquidity_view == "fragile":
            days += 6
        elif inputs.liquidity_view == "strong":
            days -= 3

        assumptions.append("Estimated days to rent is heuristic and primarily town-prior driven in v1.")
        return max(14, int(round(days)))

    def _final_score(
        self,
        *,
        liquidity_score: float,
        demand_depth_score: float,
        rent_support_score: float,
        structural_support_score: float,
        has_rent_support: bool,
    ) -> float:
        weights = dict(self._BASE_WEIGHTS)
        if not has_rent_support:
            weights["rent_support"] = 0.10
            weights["liquidity"] = 0.40
            weights["demand_depth"] = 0.30
            weights["structural_support"] = 0.20

        total_weight = sum(weights.values())
        normalized = {key: value / total_weight for key, value in weights.items()}
        return clamp_score(
            normalized["liquidity"] * liquidity_score
            + normalized["demand_depth"] * demand_depth_score
            + normalized["rent_support"] * rent_support_score
            + normalized["structural_support"] * structural_support_score
        )

    def _confidence(self, inputs: RentalEaseInput, prior: RentalEasePrior | None) -> float:
        confidence = 0.22
        if prior is not None:
            confidence += 0.12
        else:
            confidence -= 0.20
        if inputs.town_county_score is not None:
            confidence += 0.20
        if inputs.town_county_confidence is not None:
            confidence += 0.10 * inputs.town_county_confidence
        if inputs.scarcity_support_score is not None:
            confidence += 0.10
        if inputs.scarcity_confidence is not None:
            confidence += 0.08 * inputs.scarcity_confidence
        if inputs.income_support_ratio is not None or inputs.price_to_rent is not None:
            confidence += 0.16
        else:
            confidence -= 0.14
        if inputs.days_on_market is not None:
            confidence += 0.06
        if inputs.zillow_rent_index_current is not None and inputs.zillow_renter_demand_index is not None:
            confidence += 0.06
        if inputs.rent_source_type == "missing":
            confidence = min(confidence - 0.08, 0.6)
        elif inputs.rent_source_type == "estimated":
            confidence = min(confidence, 0.7)
        if not inputs.financing_complete:
            confidence = min(confidence - 0.08, 0.62)
        return max(0.15, min(confidence, 0.88))

    def _drivers(
        self,
        inputs: RentalEaseInput,
        prior: RentalEasePrior | None,
        liquidity_score: float,
        demand_depth_score: float,
        rent_support_score: float,
        structural_support_score: float,
    ) -> list[str]:
        drivers: list[str] = []
        if prior is not None and prior.liquidity >= 0.8:
            drivers.append(f"{prior.town} has a favorable rental liquidity prior within Briarwood's Monmouth scope.")
        if inputs.town_county_score is not None and inputs.town_county_score >= 65:
            drivers.append("Town/county demand context supports a durable renter base.")
        if inputs.zillow_renter_demand_index is not None and inputs.zillow_renter_demand_index >= 75:
            drivers.append("Zillow rental demand context points to healthy market-level renter interest.")
        if inputs.zillow_rent_forecast_one_year is not None and inputs.zillow_rent_forecast_one_year > 0:
            drivers.append("Zillow rent forecast remains positive, which supports the rental backdrop.")
        if inputs.income_support_ratio is not None and inputs.income_support_ratio >= 0.9:
            drivers.append("Rent support is reasonably aligned with carrying cost.")
        if inputs.scarcity_support_score is not None and inputs.scarcity_support_score >= 65:
            drivers.append("Structural scarcity and local desirability support rental durability.")
        if not drivers:
            strongest = max(
                (
                    ("liquidity", liquidity_score),
                    ("demand depth", demand_depth_score),
                    ("rent support", rent_support_score),
                    ("structural support", structural_support_score),
                ),
                key=lambda item: item[1],
            )[0]
            drivers.append(f"The strongest current rental-ease pillar is {strongest}.")
        return drivers

    def _risks(
        self,
        inputs: RentalEaseInput,
        prior: RentalEasePrior | None,
        liquidity_score: float,
        demand_depth_score: float,
        rent_support_score: float,
        confidence: float,
    ) -> list[str]:
        risks: list[str] = []
        if prior is not None and prior.seasonality >= 0.65:
            risks.append("Rental demand likely has some seasonal dependence, which can thin the off-season renter pool.")
        if prior is not None and prior.premium_fragility >= 0.55:
            risks.append("The renter pool may be thinner at this town's premium pricing tier.")
        if inputs.income_support_ratio is not None and inputs.income_support_ratio < 0.75:
            risks.append("Rent support looks weak relative to carrying cost.")
        if inputs.zillow_rent_forecast_one_year is not None and inputs.zillow_rent_forecast_one_year < 0:
            risks.append("Zillow rent forecast is soft, which weakens the rental backdrop.")
        if inputs.town_county_score is not None and inputs.town_county_score < 55:
            risks.append("Town/county demand support is only mixed, which weakens absorption durability.")
        if inputs.flood_risk in {"medium", "high"}:
            risks.append(f"Flood exposure is {inputs.flood_risk}, which can narrow the renter pool.")
        if confidence < 0.60:
            risks.append("Confidence is limited because this view relies partly on priors and partial evidence.")
        if not risks:
            risks.append("No major rental absorption risk was surfaced beyond normal pricing and seasonality sensitivity.")
        return risks

    def _zillow_demand_support(self, inputs: RentalEaseInput) -> float:
        if (
            inputs.zillow_rent_index_current is None
            or inputs.zillow_rent_index_prior_year is None
            or inputs.zillow_renter_demand_index is None
        ):
            return 55.0
        zori_growth = (inputs.zillow_rent_index_current / inputs.zillow_rent_index_prior_year) - 1
        growth_score = 55.0
        if zori_growth >= 0.05:
            growth_score = 82.0
        elif zori_growth >= 0.02:
            growth_score = 68.0
        elif zori_growth < 0:
            growth_score = 38.0
        return clamp_score((0.55 * inputs.zillow_renter_demand_index) + (0.45 * growth_score))


def analyze_rental_ease(payload: RentalEaseInput | dict[str, object]) -> RentalEaseOutput:
    """Convenience wrapper for one-shot rental ease analysis."""

    return RentalEaseAgent().run(payload)

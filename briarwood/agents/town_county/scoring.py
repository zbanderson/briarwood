from __future__ import annotations

from briarwood.agents.town_county.schemas import TownCountyInputs, TownCountyScore


class TownCountyScorer:
    """Score town/county investment support without filling gaps with fake data."""

    _CONFIDENCE_WEIGHTS = {
        "town_price_trend": 0.20,
        "town_population_trend": 0.15,
        "school_signal": 0.20,
        "county_price_trend": 0.15,
        "county_population_trend": 0.10,
        "liquidity_signal": 0.10,
        "scarcity_signal": 0.05,
        "flood_risk": 0.05,
    }

    def score(self, payload: TownCountyInputs | dict[str, object]) -> TownCountyScore:
        inputs = payload if isinstance(payload, TownCountyInputs) else TownCountyInputs.model_validate(payload)
        missing_inputs = self._missing_inputs(inputs)
        assumptions_used: list[str] = []
        unsupported_claims: list[str] = []

        normalized_town_price = self._normalize_price_trend(inputs.town_price_trend)
        normalized_town_population = self._normalize_population_trend(inputs.town_population_trend)
        normalized_school = self._normalize_school_signal(inputs.school_signal)
        normalized_scarcity = self._normalize_scarcity_signal(inputs.scarcity_signal)
        normalized_liquidity = self._normalize_liquidity_signal(inputs.liquidity_signal)
        flood_penalty = self._flood_penalty(inputs.flood_risk)

        town_demand_score = self._clamp_score(
            (35 * (normalized_town_price or 0.0))
            + (20 * (normalized_town_population or 0.0))
            + (25 * (normalized_school or 0.0))
            + (10 * (normalized_scarcity or 0.0))
            + (10 * (normalized_liquidity or 0.0))
            - flood_penalty
        )

        normalized_county_price = self._normalize_price_trend(inputs.county_price_trend)
        normalized_county_population = self._normalize_population_trend(inputs.county_population_trend)
        county_support_score: float | None = None
        if normalized_county_price is not None or normalized_county_population is not None:
            county_support_score = self._clamp_score(
                (60 * (normalized_county_price or 0.0))
                + (40 * (normalized_county_population or 0.0))
            )
        else:
            assumptions_used.append("County context unavailable; thesis relies more heavily on town-level signals.")

        market_alignment_score = self._market_alignment_score(
            days_on_market=inputs.days_on_market,
            price_position=inputs.price_position,
            has_core_property_context=all(value is not None for value in (inputs.days_on_market, inputs.price_position)),
        )

        if county_support_score is None:
            town_county_score = self._clamp_score((0.65 * town_demand_score) + (0.35 * market_alignment_score))
            unsupported_claims.append("County-level structural support could not be confirmed.")
        else:
            town_county_score = self._clamp_score(
                (0.50 * town_demand_score)
                + (0.25 * county_support_score)
                + (0.25 * market_alignment_score)
            )

        confidence = self._confidence(inputs)
        location_thesis_label = self._location_label(town_county_score, confidence)
        appreciation_support_view = self._appreciation_view(
            score=town_county_score,
            confidence=confidence,
            has_price_backbone=inputs.town_price_trend is not None and inputs.county_price_trend is not None,
        )
        liquidity_view = self._liquidity_view(
            market_alignment_score=market_alignment_score,
            liquidity_signal=inputs.liquidity_signal,
            confidence=confidence,
        )

        if inputs.town_price_trend is None and inputs.county_price_trend is None:
            unsupported_claims.append("Appreciation support lacks town and county price-trend data.")
        if inputs.school_signal is None:
            unsupported_claims.append("Demand durability lacks a school-quality signal.")
        if confidence < 0.60:
            unsupported_claims.append("Location thesis is low confidence due to missing core data.")

        demand_drivers = self._demand_drivers(inputs, town_county_score)
        demand_risks = self._demand_risks(inputs, confidence, unsupported_claims)

        return TownCountyScore(
            town_demand_score=round(town_demand_score, 2),
            county_support_score=round(county_support_score, 2) if county_support_score is not None else None,
            market_alignment_score=round(market_alignment_score, 2),
            town_county_score=round(town_county_score, 2),
            location_thesis_label=location_thesis_label,
            appreciation_support_view=appreciation_support_view,
            liquidity_view=liquidity_view,
            confidence=round(confidence, 2),
            demand_drivers=demand_drivers,
            demand_risks=demand_risks,
            missing_inputs=missing_inputs,
            assumptions_used=assumptions_used,
            unsupported_claims=unsupported_claims,
            summary=self._summary(
                inputs=inputs,
                label=location_thesis_label,
                confidence=confidence,
                unsupported_claims=unsupported_claims,
            ),
        )

    def _missing_inputs(self, inputs: TownCountyInputs) -> list[str]:
        missing: list[str] = []
        for field_name in self._CONFIDENCE_WEIGHTS:
            if getattr(inputs, field_name) is None:
                missing.append(field_name)
        return missing

    def _confidence(self, inputs: TownCountyInputs) -> float:
        total_weight = sum(self._CONFIDENCE_WEIGHTS.values())
        populated_weight = sum(
            weight for field_name, weight in self._CONFIDENCE_WEIGHTS.items() if getattr(inputs, field_name) is not None
        )
        return populated_weight / total_weight

    def _normalize_price_trend(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= -0.05:
            return 0.10
        if value <= 0.00:
            return 0.30
        if value <= 0.03:
            return 0.50
        if value <= 0.06:
            return 0.75
        return 0.95

    def _normalize_population_trend(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= -0.02:
            return 0.10
        if value <= 0.00:
            return 0.35
        if value <= 0.01:
            return 0.55
        if value <= 0.03:
            return 0.75
        return 0.90

    def _normalize_school_signal(self, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(value / 10.0, 1.0))

    def _normalize_liquidity_signal(self, value: str | None) -> float | None:
        if value is None:
            return None
        return {
            "strong": 0.90,
            "normal": 0.60,
            "fragile": 0.25,
        }[value]

    def _normalize_scarcity_signal(self, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(value, 1.0))

    def _flood_penalty(self, value: str | None) -> float:
        if value in {None, "none", "low"}:
            return 0.0
        if value == "medium":
            return 7.0
        return 15.0

    def _market_alignment_score(
        self,
        *,
        days_on_market: int | None,
        price_position: str | None,
        has_core_property_context: bool,
    ) -> float:
        score = 50.0
        if days_on_market is not None and days_on_market < 21:
            score += 10
        elif days_on_market is not None and days_on_market <= 45:
            score += 5
        elif days_on_market is not None and days_on_market > 60:
            score -= 10

        if price_position == "stretched":
            score -= 10
        elif price_position == "supported":
            score += 5

        if not has_core_property_context:
            score -= 10

        return self._clamp_score(score)

    def _location_label(self, score: float, confidence: float) -> str:
        if confidence < 0.40:
            return "low-confidence"
        if score >= 75:
            return "strong"
        if score >= 60:
            return "supportive"
        if score >= 45:
            return "mixed"
        return "weak"

    def _appreciation_view(self, *, score: float, confidence: float, has_price_backbone: bool) -> str:
        if confidence < 0.60 or not has_price_backbone:
            return "limited"
        if score >= 70:
            return "strong"
        if score >= 50:
            return "moderate"
        return "limited"

    def _liquidity_view(self, *, market_alignment_score: float, liquidity_signal: str | None, confidence: float) -> str:
        if confidence < 0.50 and liquidity_signal is None:
            return "fragile"
        if liquidity_signal == "strong" or market_alignment_score >= 65:
            return "strong"
        if liquidity_signal == "fragile" or market_alignment_score < 45:
            return "fragile"
        return "normal"

    def _demand_drivers(self, inputs: TownCountyInputs, score: float) -> list[str]:
        drivers: list[str] = []
        if inputs.town_price_trend is not None and inputs.town_price_trend > 0.03:
            drivers.append(f"Town home values are trending up at {inputs.town_price_trend:.1%}.")
        if inputs.county_price_trend is not None and inputs.county_price_trend > 0.03:
            drivers.append(f"County pricing also supports the hold thesis at {inputs.county_price_trend:.1%}.")
        if inputs.school_signal is not None and inputs.school_signal >= 7:
            drivers.append(f"School signal is supportive at {inputs.school_signal:.1f}/10.")
        if inputs.liquidity_signal == "strong":
            drivers.append("Local liquidity signals suggest exits should remain manageable.")
        if inputs.scarcity_signal is not None and inputs.scarcity_signal >= 0.75:
            drivers.append("Supply appears constrained enough to support scarcity value.")
        if not drivers and score >= 50:
            drivers.append("Available local signals are modestly supportive, but not especially strong.")
        return drivers

    def _demand_risks(self, inputs: TownCountyInputs, confidence: float, unsupported_claims: list[str]) -> list[str]:
        risks: list[str] = []
        if inputs.town_price_trend is not None and inputs.town_price_trend <= 0:
            risks.append("Town price momentum is flat or negative.")
        if inputs.county_population_trend is not None and inputs.county_population_trend < 0:
            risks.append("County population trend does not reinforce demand durability.")
        if inputs.flood_risk in {"medium", "high"}:
            risks.append(f"Flood exposure is flagged as {inputs.flood_risk}.")
        if inputs.liquidity_signal == "fragile":
            risks.append("Liquidity looks fragile, which could weaken exit flexibility.")
        if confidence < 0.60:
            risks.append("Core location inputs are incomplete, reducing confidence in the thesis.")
        if not risks and unsupported_claims:
            risks.append("Some location claims remain unsupported because core signals are missing.")
        return risks

    def _summary(
        self,
        *,
        inputs: TownCountyInputs,
        label: str,
        confidence: float,
        unsupported_claims: list[str],
    ) -> str:
        if confidence < 0.40:
            return (
                f"{inputs.town}, {inputs.state} has insufficient core location data for a reliable investment thesis; "
                "the current view should be treated as descriptive only."
            )
        if label == "strong":
            return (
                f"The town and county backdrop around {inputs.town}, {inputs.state} looks supportive for a medium-term hold, "
                "with durable demand signals and reasonable exit flexibility."
            )
        if label == "supportive":
            return (
                f"{inputs.town}, {inputs.state} appears supportive for a medium-term hold, though the thesis still depends on "
                "continued local demand and disciplined execution."
            )
        if label == "mixed":
            return (
                f"{inputs.town}, {inputs.state} offers a mixed location backdrop; some demand signals help, but the area alone "
                "should not be relied on to rescue a stretched purchase."
            )
        if label == "weak":
            return (
                f"The surrounding market does not currently provide strong support for the hold thesis in {inputs.town}, {inputs.state}."
            )
        return (
            f"{inputs.town}, {inputs.state} lacks enough core evidence for a confident location thesis. "
            f"Unsupported areas include: {'; '.join(unsupported_claims[:2])}."
        )

    def _clamp_score(self, value: float) -> float:
        return max(0.0, min(value, 100.0))


def score_town_county(payload: TownCountyInputs | dict[str, object]) -> TownCountyScore:
    """Convenience wrapper for one-shot town/county thesis scoring."""

    return TownCountyScorer().score(payload)

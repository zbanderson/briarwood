from __future__ import annotations

from math import pow

from briarwood.modules.current_value import CurrentValueModule, get_current_value_payload
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scarcity_support import ScarcitySupportModule, get_scarcity_support_payload
from briarwood.modules.town_county_outlook import TownCountyOutlookModule
from briarwood.schemas import ModuleResult, PropertyInput, ScenarioOutput
from briarwood.settings import BullBaseBearSettings, DEFAULT_BULL_BASE_BEAR_SETTINGS
from briarwood.scoring import clamp_score


class BullBaseBearModule:
    name = "bull_base_bear"

    def __init__(
        self,
        settings: BullBaseBearSettings | None = None,
        *,
        current_value_module: CurrentValueModule | None = None,
        market_value_history_module: MarketValueHistoryModule | None = None,
        town_county_outlook_module: TownCountyOutlookModule | None = None,
        risk_constraints_module: RiskConstraintsModule | None = None,
        scarcity_support_module: ScarcitySupportModule | None = None,
    ) -> None:
        self.settings = settings or DEFAULT_BULL_BASE_BEAR_SETTINGS
        self.current_value_module = current_value_module or CurrentValueModule()
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()
        self.town_county_outlook_module = town_county_outlook_module or TownCountyOutlookModule()
        self.risk_constraints_module = risk_constraints_module or RiskConstraintsModule()
        self.scarcity_support_module = scarcity_support_module or ScarcitySupportModule()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        price = float(property_input.purchase_price or 0.0)
        if price <= 0:
            scenario_output = ScenarioOutput(
                ask_price=0.0,
                bull_case_value=0.0,
                base_case_value=0.0,
                bear_case_value=0.0,
                spread=0.0,
            )
            return ModuleResult(
                module_name=self.name,
                metrics=scenario_output.to_metrics(),
                score=0.0,
                confidence=0.0,
                summary="Scenario range could not be calculated because purchase price is missing.",
                payload=scenario_output,
            )

        current_value_result = self.current_value_module.run(property_input)
        history_result = self.market_value_history_module.run(property_input)
        outlook_result = self.town_county_outlook_module.run(property_input)
        risk_result = self.risk_constraints_module.run(property_input)
        scarcity_result = self.scarcity_support_module.run(property_input)

        current_value = get_current_value_payload(current_value_result)
        scarcity = get_scarcity_support_payload(scarcity_result)
        bcv = current_value.briarwood_current_value

        one_year_change = self._as_float(history_result.metrics.get("one_year_change_pct"))
        three_year_change = self._as_float(history_result.metrics.get("three_year_change_pct"))
        location_score = float(outlook_result.score)
        risk_score = float(risk_result.score)
        optionality_score = float(scarcity.scarcity_support_score)
        optionality_confidence = float(scarcity.confidence)

        historical_growth = self._historical_growth_rate(
            one_year_change=one_year_change,
            three_year_change=three_year_change,
        )
        market_drift = self._market_drift(bcv, historical_growth)
        location_premium = self._location_premium(bcv, location_score)
        risk_discount = self._risk_discount(bcv, risk_score)
        optionality_premium = self._optionality_premium(
            bcv,
            optionality_score=optionality_score,
            optionality_confidence=optionality_confidence,
        )

        base_value = bcv + market_drift + location_premium - risk_discount + optionality_premium
        base_growth_rate = self._clamp_growth((base_value - price) / price)
        bull_growth_rate = self._clamp_growth(
            max(
                base_growth_rate + self.settings.min_spread_ratio / 2,
                base_growth_rate
                + self.settings.bull_upside_buffer
                + max(location_premium / bcv, 0.0) * 0.35
                + max(optionality_premium / bcv, 0.0) * 0.35,
            )
        )
        bear_growth_rate = self._clamp_growth(
            min(
                base_growth_rate - self.settings.min_spread_ratio / 2,
                base_growth_rate
                - self.settings.bear_downside_buffer
                - max(risk_discount / bcv, 0.0) * 0.5,
            )
        )

        bull_value = price * (1 + bull_growth_rate)
        bear_value = price * (1 + bear_growth_rate)

        spread = bull_value - bear_value
        score = self.settings.base_score
        spread_ratio = spread / price
        score += spread_ratio * self.settings.spread_weight

        scenario_output = ScenarioOutput(
            ask_price=float(price),
            bull_case_value=float(bull_value),
            base_case_value=float(base_value),
            bear_case_value=float(bear_value),
            spread=float(spread),
        )
        confidence = round(
            (
                current_value_result.confidence
                + history_result.confidence
                + outlook_result.confidence
                + risk_result.confidence
                + scarcity_result.confidence
            )
            / 5,
            2,
        )
        summary = (
            f"Base case points to roughly ${base_value:,.0f}, starting from BCV of ${bcv:,.0f} and then "
            f"adding market drift of ${market_drift:,.0f}, location premium of ${location_premium:,.0f}, "
            f"subtracting risk discount of ${risk_discount:,.0f}, and adding optionality of ${optionality_premium:,.0f}. "
        )
        summary = (
            f"{summary} This forward range is still heuristic and should be treated as an outlook, "
            "not a sourced current-value estimate."
        )
        return ModuleResult(
            module_name=self.name,
            metrics={
                **scenario_output.to_metrics(),
                "bcv_anchor": round(bcv, 2),
                "historical_growth_rate": round(historical_growth, 4),
                "market_drift": round(market_drift, 2),
                "location_premium": round(location_premium, 2),
                "risk_discount": round(risk_discount, 2),
                "optionality_premium": round(optionality_premium, 2),
                "base_growth_rate": round(base_growth_rate, 4),
                "bull_growth_rate": round(bull_growth_rate, 4),
                "bear_growth_rate": round(bear_growth_rate, 4),
                "location_score": round(location_score, 2),
                "risk_score": round(risk_score, 2),
                "optionality_score": round(optionality_score, 2),
                "market_history_confidence": history_result.confidence,
            },
            score=clamp_score(score),
            confidence=confidence,
            summary=summary,
            payload=scenario_output,
        )

    def _historical_growth_rate(
        self,
        *,
        one_year_change: float | None,
        three_year_change: float | None,
    ) -> float:
        weighted_growth = 0.0
        total_weight = 0.0

        if one_year_change is not None:
            weighted_growth += one_year_change * self.settings.one_year_history_weight
            total_weight += self.settings.one_year_history_weight

        annualized_three_year = self._annualize_change(three_year_change, years=3)
        if annualized_three_year is not None:
            weighted_growth += annualized_three_year * self.settings.three_year_history_weight
            total_weight += self.settings.three_year_history_weight

        if total_weight == 0:
            return 0.0
        return weighted_growth / total_weight

    def _market_drift(self, bcv: float, historical_growth: float) -> float:
        drift_rate = max(
            -self.settings.max_market_drift_adjustment,
            min(
                historical_growth * self.settings.trend_persistence_weight,
                self.settings.max_market_drift_adjustment,
            ),
        )
        return bcv * drift_rate

    def _location_premium(self, bcv: float, location_score: float) -> float:
        centered_score = max(min((location_score - 50.0) / 50.0, 1.0), -1.0)
        return bcv * centered_score * self.settings.max_location_premium

    def _risk_discount(self, bcv: float, risk_score: float) -> float:
        risk_gap = max(0.0, min((85.0 - risk_score) / 85.0, 1.0))
        return bcv * risk_gap * self.settings.max_risk_discount

    def _optionality_premium(
        self,
        bcv: float,
        *,
        optionality_score: float,
        optionality_confidence: float,
    ) -> float:
        centered_optionality = max(min((optionality_score - 50.0) / 50.0, 1.0), -1.0)
        confidence_scale = max(min(optionality_confidence, 1.0), 0.0)
        return bcv * centered_optionality * self.settings.max_optionality_premium * confidence_scale

    def _clamp_growth(self, value: float) -> float:
        return max(self.settings.min_growth_rate, min(self.settings.max_growth_rate, value))

    def _annualize_change(self, change: float | None, *, years: int) -> float | None:
        if change is None or change <= -1:
            return None
        return pow(1 + change, 1 / years) - 1

    def _as_float(self, value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

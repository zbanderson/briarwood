from __future__ import annotations

from math import pow

from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
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
        market_value_history_module: MarketValueHistoryModule | None = None,
        town_county_outlook_module: TownCountyOutlookModule | None = None,
        risk_constraints_module: RiskConstraintsModule | None = None,
        income_support_module: IncomeSupportModule | None = None,
    ) -> None:
        self.settings = settings or DEFAULT_BULL_BASE_BEAR_SETTINGS
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()
        self.town_county_outlook_module = town_county_outlook_module or TownCountyOutlookModule()
        self.risk_constraints_module = risk_constraints_module or RiskConstraintsModule()
        self.income_support_module = income_support_module or IncomeSupportModule()

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

        history_result = self.market_value_history_module.run(property_input)
        outlook_result = self.town_county_outlook_module.run(property_input)
        risk_result = self.risk_constraints_module.run(property_input)
        income_result = self.income_support_module.run(property_input)

        one_year_change = self._as_float(history_result.metrics.get("one_year_change_pct"))
        three_year_change = self._as_float(history_result.metrics.get("three_year_change_pct"))
        location_score = float(outlook_result.score)
        risk_score = float(risk_result.score)
        income_support_ratio = self._as_float(income_result.metrics.get("income_support_ratio"))

        historical_growth = self._historical_growth_rate(
            one_year_change=one_year_change,
            three_year_change=three_year_change,
        )
        location_adjustment = self._location_adjustment(location_score)
        income_adjustment = self._income_adjustment(income_support_ratio)
        risk_penalty = self._risk_penalty(risk_score)

        base_growth_rate = self._clamp_growth(
            historical_growth * self.settings.trend_persistence_weight
            + location_adjustment
            + income_adjustment
            - risk_penalty
        )
        bull_growth_rate = self._clamp_growth(
            max(
                base_growth_rate + self.settings.min_spread_ratio / 2,
                base_growth_rate
                + self.settings.bull_upside_buffer
                + max(location_adjustment, 0.0) * 0.5
                + max(income_adjustment, 0.0) * 0.5,
            )
        )
        bear_growth_rate = self._clamp_growth(
            min(
                base_growth_rate - self.settings.min_spread_ratio / 2,
                base_growth_rate
                - self.settings.bear_downside_buffer
                - risk_penalty * 0.5
                - max(-income_adjustment, 0.0) * 0.5,
            )
        )

        bull_value = price * (1 + bull_growth_rate)
        base_value = price * (1 + base_growth_rate)
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
                history_result.confidence
                + outlook_result.confidence
                + risk_result.confidence
                + income_result.confidence
            )
            / 4,
            2,
        )
        summary = (
            f"Base case points to roughly ${base_value:,.0f}, using historical market momentum of "
            f"{historical_growth:.1%}, location support of {location_score:.0f}/100, risk score of "
            f"{risk_score:.0f}/100, and fallback income support of "
            f"{income_support_ratio:.2f}x." if income_support_ratio is not None else
            f"Base case points to roughly ${base_value:,.0f}, using historical market momentum of "
            f"{historical_growth:.1%}, location support of {location_score:.0f}/100, and risk score of "
            f"{risk_score:.0f}/100."
        )
        summary = (
            f"{summary} This forward range is still heuristic and should be treated as an outlook, "
            "not a sourced current-value estimate."
        )
        return ModuleResult(
            module_name=self.name,
            metrics={
                **scenario_output.to_metrics(),
                "historical_growth_rate": round(historical_growth, 4),
                "base_growth_rate": round(base_growth_rate, 4),
                "bull_growth_rate": round(bull_growth_rate, 4),
                "bear_growth_rate": round(bear_growth_rate, 4),
                "location_score": round(location_score, 2),
                "risk_score": round(risk_score, 2),
                "income_support_ratio": round(income_support_ratio, 4)
                if income_support_ratio is not None
                else None,
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

    def _location_adjustment(self, location_score: float) -> float:
        centered_score = (location_score - 50.0) / 50.0
        return centered_score * self.settings.max_location_adjustment

    def _income_adjustment(self, income_support_ratio: float | None) -> float:
        if income_support_ratio is None:
            return 0.0
        centered_ratio = max(min((income_support_ratio - 0.75) / 0.75, 1.0), -1.0)
        return centered_ratio * self.settings.max_income_adjustment

    def _risk_penalty(self, risk_score: float) -> float:
        risk_gap = max(0.0, (80.0 - risk_score) / 80.0)
        return risk_gap * self.settings.max_risk_penalty

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

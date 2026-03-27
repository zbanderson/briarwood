from __future__ import annotations

from briarwood.schemas import ModuleResult, PropertyInput, ScenarioOutput
from briarwood.settings import BullBaseBearSettings, DEFAULT_BULL_BASE_BEAR_SETTINGS
from briarwood.scoring import clamp_score


class BullBaseBearModule:
    name = "bull_base_bear"

    def __init__(self, settings: BullBaseBearSettings | None = None) -> None:
        self.settings = settings or DEFAULT_BULL_BASE_BEAR_SETTINGS

    def run(self, property_input: PropertyInput) -> ModuleResult:
        price = property_input.purchase_price or 0
        rent = property_input.estimated_monthly_rent or 0

        bull_value = (
            price * self.settings.bull_price_multiplier
            + (rent * 12 * self.settings.bull_rent_multiple)
        )
        base_value = (
            price * self.settings.base_price_multiplier
            + (rent * 12 * self.settings.base_rent_multiple)
        )
        bear_value = (
            price * self.settings.bear_price_multiplier
            + (rent * 12 * self.settings.bear_rent_multiple)
        )

        spread = bull_value - bear_value
        score = self.settings.base_score
        if price:
            spread_ratio = spread / price
            score += spread_ratio * self.settings.spread_weight

        scenario_output = ScenarioOutput(
            ask_price=float(price),
            bull_case_value=float(bull_value),
            base_case_value=float(base_value),
            bear_case_value=float(bear_value),
            spread=float(spread),
        )
        summary = (
            f"Base case points to roughly ${base_value:,.0f}, with downside to "
            f"${bear_value:,.0f} and upside to ${bull_value:,.0f}."
        )
        return ModuleResult(
            module_name=self.name,
            metrics=scenario_output.to_metrics(),
            score=clamp_score(score),
            confidence=0.7,
            summary=summary,
            payload=scenario_output,
        )

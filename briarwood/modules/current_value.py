from __future__ import annotations

from briarwood.agents.current_value import CurrentValueAgent, CurrentValueInput, CurrentValueOutput
from briarwood.modules.income_support import IncomeSupportModule, get_income_support_payload
from briarwood.modules.market_value_history import (
    MarketValueHistoryModule,
    get_market_value_history_payload,
)
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.settings import CurrentValueSettings, DEFAULT_CURRENT_VALUE_SETTINGS


class CurrentValueModule:
    """Estimate today's Briarwood Current Value from market, listing, and income anchors."""

    name = "current_value"

    def __init__(
        self,
        *,
        agent: CurrentValueAgent | None = None,
        market_value_history_module: MarketValueHistoryModule | None = None,
        income_support_module: IncomeSupportModule | None = None,
        settings: CurrentValueSettings | None = None,
    ) -> None:
        self.agent = agent or CurrentValueAgent()
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()
        self.income_support_module = income_support_module or IncomeSupportModule()
        self.settings = settings or DEFAULT_CURRENT_VALUE_SETTINGS

    def run(self, property_input: PropertyInput) -> ModuleResult:
        if property_input.purchase_price is None or property_input.purchase_price <= 0:
            return ModuleResult(
                module_name=self.name,
                score=0.0,
                confidence=0.0,
                summary="Briarwood Current Value could not be estimated because ask price is missing.",
                metrics={
                    "briarwood_current_value": None,
                    "mispricing_pct": None,
                    "pricing_view": "unavailable",
                },
            )

        history_result = self.market_value_history_module.run(property_input)
        income_result = self.income_support_module.run(property_input)
        history = get_market_value_history_payload(history_result)
        income = get_income_support_payload(income_result)

        output = self.agent.run(
            CurrentValueInput(
                ask_price=property_input.purchase_price,
                market_value_today=history.current_value,
                market_history_points=history.points,
                beds=property_input.beds,
                baths=property_input.baths,
                lot_size=property_input.lot_size,
                property_type=property_input.property_type,
                year_built=property_input.year_built,
                listing_date=property_input.listing_date,
                price_history=property_input.price_history,
                days_on_market=property_input.days_on_market,
                effective_annual_rent=(
                    income.effective_monthly_rent * 12 if income.effective_monthly_rent is not None else None
                ),
                cap_rate_assumption=self.settings.income_cap_rate_assumption,
            )
        )

        summary = (
            f"Briarwood Current Value is about ${output.briarwood_current_value:,.0f}, "
            f"which {output.pricing_view} versus the ask by "
            f"{abs(output.mispricing_pct):.1%}. Confidence is {output.confidence:.0%}."
        )

        return ModuleResult(
            module_name=self.name,
            metrics={
                "briarwood_current_value": round(output.briarwood_current_value, 2),
                "value_low": round(output.value_low, 2),
                "value_high": round(output.value_high, 2),
                "mispricing_amount": round(output.mispricing_amount, 2),
                "mispricing_pct": round(output.mispricing_pct, 4),
                "pricing_view": output.pricing_view,
                "market_adjusted_value": output.components.market_adjusted_value,
                "backdated_listing_value": output.components.backdated_listing_value,
                "income_supported_value": output.components.income_supported_value,
                "market_adjusted_weight": round(output.weights.market_adjusted_weight, 4),
                "backdated_listing_weight": round(output.weights.backdated_listing_weight, 4),
                "income_weight": round(output.weights.income_weight, 4),
            },
            score=max(0.0, min(output.confidence * 100, 100.0)),
            confidence=output.confidence,
            summary=summary,
            payload=output,
        )


def get_current_value_payload(result: ModuleResult) -> CurrentValueOutput:
    """Extract the typed current-value payload from a module result."""

    if not isinstance(result.payload, CurrentValueOutput):
        raise TypeError("current_value module payload is not a CurrentValueOutput")
    return result.payload

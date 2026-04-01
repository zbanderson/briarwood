from __future__ import annotations

from pathlib import Path

from briarwood.agents.comparable_sales import (
    ComparableSalesAgent,
    ComparableSalesOutput,
    ComparableSalesRequest,
    FileBackedComparableSalesProvider,
)
from briarwood.evidence import build_section_evidence
from briarwood.modules.market_value_history import MarketValueHistoryModule, get_market_value_history_payload
from briarwood.schemas import ModuleResult, PropertyInput


class ComparableSalesModule:
    """Build a property-level value anchor from nearby sale comps."""

    name = "comparable_sales"

    def __init__(
        self,
        *,
        agent: ComparableSalesAgent | None = None,
        market_value_history_module: MarketValueHistoryModule | None = None,
    ) -> None:
        self.agent = agent or ComparableSalesAgent(
            FileBackedComparableSalesProvider(
                Path(__file__).resolve().parents[2] / "data" / "comps" / "sales_comps.json"
            )
        )
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        history_result = self.market_value_history_module.run(property_input)
        history = get_market_value_history_payload(history_result)
        output = self.agent.run(
            ComparableSalesRequest(
                town=property_input.town,
                state=property_input.state,
                property_type=property_input.property_type,
                architectural_style=property_input.architectural_style,
                condition_profile=property_input.condition_profile,
                capex_lane=property_input.capex_lane,
                beds=property_input.beds,
                baths=property_input.baths,
                sqft=property_input.sqft,
                lot_size=property_input.lot_size,
                year_built=property_input.year_built,
                stories=property_input.stories,
                garage_spaces=property_input.garage_spaces,
                listing_description=property_input.listing_description,
                market_value_today=history.current_value,
                market_history_points=[point.model_dump() for point in history.points],
                manual_sales=list(property_input.manual_comp_inputs),
                manual_comp_only=False,
            )
        )
        return ModuleResult(
            module_name=self.name,
            metrics={
                "comparable_value": output.comparable_value,
                "comp_count": output.comp_count,
                "comp_confidence": round(output.confidence, 2),
            },
            score=(output.comparable_value is not None) * min(output.confidence * 100, 100.0),
            confidence=output.confidence,
            summary=output.summary,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["comp_support", "sqft", "lot_size", "listing_history"],
                notes=["Comp support is only as strong as the current comp database and its verification tier."],
            ),
        )


def get_comparable_sales_payload(result: ModuleResult) -> ComparableSalesOutput:
    if not isinstance(result.payload, ComparableSalesOutput):
        raise TypeError("comparable_sales module payload is not a ComparableSalesOutput")
    return result.payload

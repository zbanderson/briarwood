from __future__ import annotations

from pathlib import Path

from briarwood.evidence import build_section_evidence
from briarwood.agents.market_history import (
    FileBackedZillowHistoryProvider,
    MarketValueHistoryAgent,
    MarketValueHistoryOutput,
    MarketValueHistoryRequest,
)
from briarwood.schemas import ModuleResult, PropertyInput


class MarketValueHistoryModule:
    """Source-backed historical market value context for charting and valuation framing."""

    name = "market_value_history"

    def __init__(self, *, agent: MarketValueHistoryAgent | None = None) -> None:
        self.agent = agent or MarketValueHistoryAgent(
            FileBackedZillowHistoryProvider(
                Path(__file__).resolve().parents[2] / "data" / "market_history" / "zillow_zhvi_history.json"
            )
        )

    def run(self, property_input: PropertyInput) -> ModuleResult:
        history = self.agent.run(
            MarketValueHistoryRequest(
                town=property_input.town,
                state=property_input.state,
                county=property_input.county,
            )
        )
        metrics = {
            "source_name": history.source_name,
            "geography_name": history.geography_name,
            "geography_type": history.geography_type,
            "current_value": history.current_value,
            "one_year_change_pct": history.one_year_change_pct,
            "three_year_change_pct": history.three_year_change_pct,
            "history_points": len(history.points),
        }
        score = 75.0 if history.points else 0.0
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=score,
            confidence=history.confidence,
            summary=history.summary,
            payload=history,
            section_evidence=build_section_evidence(
                property_input,
                categories=["market_history", "address"],
                notes=["Market history is a sourced market-level context layer, not property-specific listing evidence."],
            ),
        )


def get_market_value_history_payload(result: ModuleResult) -> MarketValueHistoryOutput:
    """Extract the typed market-value history payload from a module result."""

    if not isinstance(result.payload, MarketValueHistoryOutput):
        raise TypeError("market_value_history module payload is not a MarketValueHistoryOutput")
    return result.payload

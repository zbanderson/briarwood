from __future__ import annotations

from briarwood.agents.town_county.service import TownCountyDataService, TownCountyOutlookResult
from briarwood.modules.location_context import (
    build_default_town_county_service,
    build_town_county_request,
)
from briarwood.schemas import ModuleResult, PropertyInput


class TownCountyOutlookModule:
    """Source-backed location outlook for the report pipeline."""

    name = "town_county_outlook"

    def __init__(self, *, service: TownCountyDataService | None = None) -> None:
        self.service = service or build_default_town_county_service()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        outlook = self.service.build_outlook(build_town_county_request(property_input))
        score = outlook.score
        metrics = {
            "location_thesis_label": score.location_thesis_label,
            "town_county_score": score.town_county_score,
            "appreciation_support_view": score.appreciation_support_view,
            "liquidity_view": score.liquidity_view,
            "data_as_of": outlook.normalized.inputs.data_as_of,
            "missing_inputs": ", ".join(outlook.normalized.missing_inputs) if outlook.normalized.missing_inputs else "none",
        }
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=float(score.town_county_score),
            confidence=float(score.confidence),
            summary=score.summary,
            payload=outlook,
        )


def get_town_county_outlook_payload(result: ModuleResult) -> TownCountyOutlookResult:
    """Extract a typed town/county payload from a module result."""

    if not isinstance(result.payload, TownCountyOutlookResult):
        raise TypeError("town_county_outlook module payload is not a TownCountyOutlookResult")
    return result.payload

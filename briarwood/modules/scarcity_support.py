from __future__ import annotations

from briarwood.agents.scarcity.scarcity_support import ScarcitySupportScorer
from briarwood.agents.scarcity.schemas import ScarcitySupportScore
from briarwood.agents.town_county.service import TownCountyDataService
from briarwood.modules.location_context import (
    build_default_town_county_service,
    build_scarcity_inputs,
    build_town_county_request,
)
from briarwood.schemas import ModuleResult, PropertyInput


class ScarcitySupportModule:
    """Run the early scarcity framework inside the standard analysis pipeline."""

    name = "scarcity_support"

    def __init__(
        self,
        *,
        service: TownCountyDataService | None = None,
        scorer: ScarcitySupportScorer | None = None,
    ) -> None:
        self.service = service or build_default_town_county_service()
        self.scorer = scorer or ScarcitySupportScorer()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        outlook = self.service.build_outlook(build_town_county_request(property_input))
        scarcity = self.scorer.score(build_scarcity_inputs(property_input, outlook=outlook))
        metrics = {
            "scarcity_label": scarcity.scarcity_label,
            "scarcity_support_score": scarcity.scarcity_support_score,
            "buyer_takeaway": scarcity.buyer_takeaway,
            "missing_inputs": ", ".join(scarcity.missing_inputs) if scarcity.missing_inputs else "none",
        }
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=float(scarcity.scarcity_support_score),
            confidence=float(scarcity.confidence),
            summary=scarcity.summary,
            payload=scarcity,
        )


def get_scarcity_support_payload(result: ModuleResult) -> ScarcitySupportScore:
    """Extract a typed scarcity-support payload from a module result."""

    if not isinstance(result.payload, ScarcitySupportScore):
        raise TypeError("scarcity_support module payload is not a ScarcitySupportScore")
    return result.payload

from __future__ import annotations

from pathlib import Path

from briarwood.agents.income.schemas import IncomeAgentOutput
from briarwood.agents.rental_ease import RentalEaseAgent, RentalEaseInput, RentalEaseOutput
from briarwood.agents.rental_ease.context import FileBackedZillowRentContextProvider
from briarwood.evidence import build_section_evidence
from briarwood.modules.income_support import IncomeSupportModule, get_income_support_payload
from briarwood.modules.scarcity_support import ScarcitySupportModule, get_scarcity_support_payload
from briarwood.modules.town_county_outlook import TownCountyOutlookModule, get_town_county_outlook_payload
from briarwood.schemas import ModuleResult, PropertyInput


class RentalEaseModule:
    """Translate town priors and current Briarwood signals into rental absorption ease."""

    name = "rental_ease"

    def __init__(
        self,
        *,
        agent: RentalEaseAgent | None = None,
        income_support_module: IncomeSupportModule | None = None,
        town_county_outlook_module: TownCountyOutlookModule | None = None,
        scarcity_support_module: ScarcitySupportModule | None = None,
        zillow_context_provider: FileBackedZillowRentContextProvider | None = None,
    ) -> None:
        self.agent = agent or RentalEaseAgent()
        self.income_support_module = income_support_module or IncomeSupportModule()
        self.town_county_outlook_module = town_county_outlook_module or TownCountyOutlookModule()
        self.scarcity_support_module = scarcity_support_module or ScarcitySupportModule()
        self.zillow_context_provider = zillow_context_provider or FileBackedZillowRentContextProvider(
            Path(__file__).resolve().parents[2] / "data" / "town_county" / "zillow_rent_context.json"
        )

    def run(self, property_input: PropertyInput) -> ModuleResult:
        income_result = self.income_support_module.run(property_input)
        town_result = self.town_county_outlook_module.run(property_input)
        scarcity_result = self.scarcity_support_module.run(property_input)

        # Graceful degradation: when upstream income_support produced a
        # fallback (no IncomeAgentOutput payload) — e.g., thin inputs with no
        # purchase_price — return a low-confidence "unavailable" result
        # instead of raising. Phase 3 fix for the rent_stabilization crash.
        if not isinstance(income_result.payload, IncomeAgentOutput):
            return ModuleResult(
                module_name=self.name,
                metrics={"rental_ease_label": "unavailable"},
                score=0.0,
                confidence=0.0,
                summary="Rental ease unavailable: upstream income support could not run on the provided inputs.",
                payload=None,
                section_evidence=build_section_evidence(
                    property_input,
                    categories=["rent_estimate"],
                    extra_estimated_inputs=[],
                    notes=["Income support upstream produced no usable payload; rental ease cannot be computed."],
                ),
            )

        income = get_income_support_payload(income_result)
        town = get_town_county_outlook_payload(town_result).score
        scarcity = get_scarcity_support_payload(scarcity_result)
        zillow_context = self.zillow_context_provider.get_town_context(
            town=property_input.town,
            state=property_input.state,
        )
        if zillow_context is None and property_input.county:
            zillow_context = self.zillow_context_provider.get_county_context(
                county=property_input.county,
                state=property_input.state,
            )

        output = self.agent.run(
            RentalEaseInput(
                town=property_input.town,
                state=property_input.state,
                county=property_input.county,
                estimated_monthly_rent=income.effective_monthly_rent,
                rent_source_type=income.rent_source_type,
                gross_monthly_cost=income.gross_monthly_cost,
                carrying_cost_complete=income.carrying_cost_complete,
                financing_complete=income.financing_complete,
                income_support_ratio=income.income_support_ratio,
                price_to_rent=income.price_to_rent,
                rent_support_classification=income.rent_support_classification,
                monthly_cash_flow=income.monthly_cash_flow,
                downside_burden=income.downside_burden,
                town_county_score=town.town_county_score,
                town_county_confidence=town.confidence,
                liquidity_view=town.liquidity_view,
                scarcity_support_score=scarcity.scarcity_support_score,
                scarcity_confidence=scarcity.confidence,
                flood_risk=property_input.flood_risk,
                days_on_market=property_input.days_on_market,
                property_type=property_input.property_type,
                beds=property_input.beds,
                baths=property_input.baths,
                sqft=property_input.sqft,
                zillow_rent_index_current=zillow_context.zori_current if zillow_context else None,
                zillow_rent_index_prior_year=zillow_context.zori_prior_year if zillow_context else None,
                zillow_renter_demand_index=zillow_context.zordi_score if zillow_context else None,
                zillow_rent_forecast_one_year=zillow_context.zorf_one_year if zillow_context else None,
                zillow_context_scope=zillow_context.geography_type if zillow_context else None,
            )
        )

        metrics = {
            "rental_ease_score": output.rental_ease_score,
            "rental_ease_label": output.rental_ease_label,
            "liquidity_score": output.liquidity_score,
            "demand_depth_score": output.demand_depth_score,
            "rent_support_score": output.rent_support_score,
            "structural_support_score": output.structural_support_score,
            "estimated_days_to_rent": output.estimated_days_to_rent,
            "zillow_context_used": output.zillow_context_used,
            "zillow_context_scope": zillow_context.geography_type if zillow_context else "none",
        }
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=float(output.rental_ease_score),
            confidence=float(output.confidence),
            summary=output.summary,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["rent_estimate", "liquidity_signal", "scarcity_inputs", "flood_risk"],
                extra_estimated_inputs=(["rent_estimate"] if income.rent_source_type == "estimated" else []),
                notes=["Rental ease mixes town-level absorption signals with any property-level rent support that is available."],
            ),
        )


def get_rental_ease_payload(result: ModuleResult) -> RentalEaseOutput:
    if not isinstance(result.payload, RentalEaseOutput):
        raise TypeError("rental_ease module payload is not a RentalEaseOutput")
    return result.payload

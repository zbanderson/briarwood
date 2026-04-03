from __future__ import annotations

from briarwood.agents.rent_context import RentContextAgent, RentContextInput
from briarwood.agents.income import IncomeAgent, IncomeAgentOutput
from briarwood.agents.income.schemas import IncomeAgentInput
from briarwood.evidence import build_section_evidence
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.settings import CostValuationSettings, DEFAULT_COST_VALUATION_SETTINGS


class IncomeSupportModule:
    """Wrap the Income Agent for the main Briarwood analysis pipeline."""

    name = "income_support"

    def __init__(
        self,
        *,
        agent: IncomeAgent | None = None,
        rent_context_agent: RentContextAgent | None = None,
        settings: CostValuationSettings | None = None,
    ) -> None:
        self.agent = agent or IncomeAgent()
        self.rent_context_agent = rent_context_agent or RentContextAgent()
        self.settings = settings or DEFAULT_COST_VALUATION_SETTINGS

    def run(self, property_input: PropertyInput) -> ModuleResult:
        if property_input.purchase_price is None:
            return ModuleResult(
                module_name=self.name,
                score=0.0,
                confidence=0.0,
                summary="Fallback rental support could not be assessed because purchase price is missing.",
                metrics={
                    "income_support_ratio": None,
                    "estimated_monthly_cash_flow": None,
                    "support_label": "unavailable",
                },
                section_evidence=build_section_evidence(
                    property_input,
                    categories=["price_ask", "rent_estimate", "insurance_estimate", "financing_down_payment", "financing_interest_rate"],
                    extra_missing_inputs=["price_ask"],
                    notes=["Rental fallback cannot be underwritten without an ask price."],
                ),
            )

        wrapper_warnings: list[str] = []
        if property_input.down_payment_percent is None:
            wrapper_warnings.append("Down payment missing; rental carry excludes mortgage support verification.")
        if property_input.interest_rate is None:
            wrapper_warnings.append("Interest rate missing; rental carry excludes mortgage support verification.")
        loan_term_years = property_input.loan_term_years
        if loan_term_years is None:
            wrapper_warnings.append("Loan term missing; rental carry excludes mortgage support verification.")

        maintenance_pct = self.settings.default_maintenance_reserve_pct
        wrapper_warnings.append(
            f"Maintenance reserve not specified; assuming {maintenance_pct:.1%} annually."
        )
        manual_unit_rents = [rent for rent in property_input.unit_rents if rent > 0]
        if manual_unit_rents:
            rent_context_rent = sum(manual_unit_rents)
            rent_source_type = "manual_input"
            rent_context_assumptions = [
                f"Manual unit rent schedule supplied for {len(manual_unit_rents)} unit{'s' if len(manual_unit_rents) != 1 else ''}."
            ]
            rent_context_warnings: list[str] = []
        else:
            rent_context = self.rent_context_agent.run(
                RentContextInput(
                    town=property_input.town,
                    state=property_input.state,
                    sqft=property_input.sqft,
                    beds=property_input.beds,
                    baths=property_input.baths,
                    explicit_monthly_rent=property_input.estimated_monthly_rent,
                )
            )
            rent_context_rent = rent_context.rent_estimate
            rent_source_type = rent_context.rent_source_type
            rent_context_assumptions = rent_context.assumptions
            rent_context_warnings = rent_context.warnings
        wrapper_warnings.extend(rent_context_warnings)

        output = self.agent.run(
            IncomeAgentInput(
                price=property_input.purchase_price,
                down_payment_pct=property_input.down_payment_percent,
                interest_rate=property_input.interest_rate,
                loan_term_years=loan_term_years,
                annual_taxes=property_input.taxes,
                annual_insurance=property_input.insurance,
                monthly_hoa=property_input.monthly_hoa,
                estimated_monthly_rent=rent_context_rent,
                back_house_monthly_rent=property_input.back_house_monthly_rent,
                unit_rents=manual_unit_rents,
                rent_source_type=rent_source_type,
                vacancy_pct=property_input.vacancy_rate,
                maintenance_pct=maintenance_pct,
                market_price_to_rent_benchmark=property_input.market_price_to_rent_benchmark,
            )
        )
        warnings = wrapper_warnings + output.warnings
        support_label = output.rent_support_classification
        confidence = output.confidence
        summary = output.summary
        if warnings:
            summary = f"{summary} Key assumption gaps: {' '.join(warnings[:2])}"

        return ModuleResult(
            module_name=self.name,
            score=self._score(output),
            confidence=confidence,
            summary=summary,
            metrics={
                "gross_monthly_cost": output.gross_monthly_cost,
                "total_monthly_cost": output.total_monthly_cost,
                "operating_monthly_cost": output.operating_monthly_cost,
                "effective_monthly_rent": output.effective_monthly_rent,
                "monthly_rent_estimate": output.monthly_rent_estimate,
                "num_units": output.num_units,
                "avg_rent_per_unit": output.avg_rent_per_unit,
                "unit_breakdown": output.unit_breakdown,
                "income_support_ratio": output.income_support_ratio,
                "rent_coverage": output.rent_coverage,
                "price_to_rent": output.price_to_rent,
                "estimated_monthly_cash_flow": output.estimated_monthly_cash_flow,
                "monthly_cash_flow": output.monthly_cash_flow,
                "operating_monthly_cash_flow": output.operating_monthly_cash_flow,
                "downside_burden": output.downside_burden,
                "risk_view": output.risk_view,
                "support_label": support_label,
                "rent_source_type": output.rent_source_type,
                "financing_complete": output.financing_complete,
                "carrying_cost_complete": output.carrying_cost_complete,
                "rent_support_classification": output.rent_support_classification,
                "price_to_rent_classification": output.price_to_rent_classification,
                "warning_count": len(warnings),
            },
            payload=output.model_copy(
                update={
                    "warnings": warnings,
                    "assumptions": output.assumptions + rent_context_assumptions,
                }
            ),
            section_evidence=build_section_evidence(
                property_input,
                categories=["price_ask", "rent_estimate", "insurance_estimate", "financing_down_payment", "financing_interest_rate", "taxes", "hoa"],
                extra_estimated_inputs=(["rent_estimate"] if rent_source_type == "estimated" else []),
                notes=["Income support is strongest with sourced rent and complete financing assumptions."],
            ),
        )

    def _score(self, output: IncomeAgentOutput) -> float:
        ratio = output.income_support_ratio
        if ratio is None:
            return 0.0
        return max(0.0, min(ratio * 95, 100.0))


def get_income_support_payload(result: ModuleResult) -> IncomeAgentOutput:
    if not isinstance(result.payload, IncomeAgentOutput):
        raise TypeError("income_support module payload is not an IncomeAgentOutput")
    return result.payload

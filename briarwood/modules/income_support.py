from __future__ import annotations

from briarwood.agents.income import IncomeAgent, IncomeAgentOutput
from briarwood.agents.income.schemas import IncomeAgentInput
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.settings import CostValuationSettings, DEFAULT_COST_VALUATION_SETTINGS


class IncomeSupportModule:
    """Wrap the Income Agent for the main Briarwood analysis pipeline."""

    name = "income_support"

    def __init__(
        self,
        *,
        agent: IncomeAgent | None = None,
        settings: CostValuationSettings | None = None,
    ) -> None:
        self.agent = agent or IncomeAgent()
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
            )

        wrapper_warnings: list[str] = []
        down_payment_pct = property_input.down_payment_percent
        if down_payment_pct is None:
            down_payment_pct = 0.0
            wrapper_warnings.append("Down payment assumption missing; assuming 0.0%.")

        interest_rate = property_input.interest_rate
        if interest_rate is None:
            interest_rate = 0.0
            wrapper_warnings.append("Interest rate assumption missing; assuming 0.0%.")

        loan_term_years = property_input.loan_term_years
        if loan_term_years is None:
            loan_term_years = self.settings.loan_term_years
            wrapper_warnings.append(
                f"Loan term assumption missing; assuming {self.settings.loan_term_years} years."
            )

        maintenance_pct = self.settings.default_maintenance_reserve_pct
        wrapper_warnings.append(
            f"Maintenance reserve not specified; assuming {maintenance_pct:.1%} annually."
        )

        output = self.agent.run(
            IncomeAgentInput(
                price=property_input.purchase_price,
                down_payment_pct=down_payment_pct,
                interest_rate=interest_rate,
                loan_term_years=loan_term_years,
                annual_taxes=property_input.taxes,
                annual_insurance=property_input.insurance,
                monthly_hoa=property_input.monthly_hoa,
                estimated_monthly_rent=property_input.estimated_monthly_rent,
                vacancy_pct=property_input.vacancy_rate,
                maintenance_pct=maintenance_pct,
            )
        )
        warnings = wrapper_warnings + output.warnings
        support_label = self._support_label(output)
        confidence = self._confidence(property_input)
        summary = output.explanation
        if warnings:
            summary = f"{summary} Key assumption gaps: {' '.join(warnings[:2])}"

        return ModuleResult(
            module_name=self.name,
            score=self._score(output),
            confidence=confidence,
            summary=summary,
            metrics={
                "gross_monthly_cost": output.gross_monthly_cost,
                "effective_monthly_rent": output.effective_monthly_rent,
                "income_support_ratio": output.income_support_ratio,
                "estimated_monthly_cash_flow": output.estimated_monthly_cash_flow,
                "support_label": support_label,
                "warning_count": len(warnings),
            },
            payload=output.model_copy(update={"warnings": warnings}),
        )

    def _score(self, output: IncomeAgentOutput) -> float:
        ratio = output.income_support_ratio
        if ratio is None:
            return 0.0
        return max(0.0, min(ratio * 100, 100.0))

    def _confidence(self, property_input: PropertyInput) -> float:
        required_values = [
            property_input.purchase_price,
            property_input.down_payment_percent,
            property_input.interest_rate,
            property_input.taxes,
            property_input.insurance,
            property_input.estimated_monthly_rent,
        ]
        populated = sum(value is not None for value in required_values)
        return round(0.35 + (populated / len(required_values)) * 0.55, 2)

    def _support_label(self, output: IncomeAgentOutput) -> str:
        ratio = output.income_support_ratio
        if ratio is None:
            return "unavailable"
        if ratio >= 1.0:
            return "rent fully supports carry"
        if ratio >= 0.8:
            return "rent offsets much of carry"
        if ratio >= 0.5:
            return "rent offsets part of carry"
        return "weak fallback rental support"


def get_income_support_payload(result: ModuleResult) -> IncomeAgentOutput:
    """Extract the typed income-support payload from a module result."""

    if not isinstance(result.payload, IncomeAgentOutput):
        raise TypeError("income_support module payload is not an IncomeAgentOutput")
    return result.payload

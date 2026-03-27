from __future__ import annotations

from briarwood.agents.income.finance import (
    calculate_loan_amount,
    calculate_monthly_principal_interest,
)
from briarwood.agents.income.schemas import IncomeAgentInput, IncomeAgentOutput


class IncomeAgent:
    """Model carrying cost support from rental income."""

    def run(self, payload: IncomeAgentInput | dict[str, object]) -> IncomeAgentOutput:
        """Return a deterministic monthly ownership snapshot."""

        income_input = payload if isinstance(payload, IncomeAgentInput) else IncomeAgentInput.model_validate(payload)
        warnings: list[str] = []

        annual_taxes = self._optional_value(
            value=income_input.annual_taxes,
            default=0.0,
            warning="Annual taxes missing; treating taxes as $0.00/month.",
            warnings=warnings,
        )
        annual_insurance = self._optional_value(
            value=income_input.annual_insurance,
            default=0.0,
            warning="Annual insurance missing; treating insurance as $0.00/month.",
            warnings=warnings,
        )
        monthly_hoa = 0.0 if income_input.monthly_hoa is None else income_input.monthly_hoa
        vacancy_pct = self._optional_value(
            value=income_input.vacancy_pct,
            default=0.0,
            warning="Vacancy assumption missing; treating vacancy as 0.0%.",
            warnings=warnings,
        )
        maintenance_pct = self._optional_value(
            value=income_input.maintenance_pct,
            default=0.0,
            warning="Maintenance assumption missing; treating maintenance reserve as 0.0%.",
            warnings=warnings,
        )

        loan_amount = calculate_loan_amount(income_input.price, income_input.down_payment_pct)
        monthly_principal_interest = calculate_monthly_principal_interest(
            principal=loan_amount,
            annual_interest_rate=income_input.interest_rate,
            loan_term_years=income_input.loan_term_years,
        )
        monthly_taxes = annual_taxes / 12
        monthly_insurance = annual_insurance / 12
        monthly_maintenance_reserve = income_input.price * maintenance_pct / 12
        gross_monthly_cost = (
            monthly_principal_interest
            + monthly_taxes
            + monthly_insurance
            + monthly_hoa
            + monthly_maintenance_reserve
        )

        effective_monthly_rent: float | None = None
        income_support_ratio: float | None = None
        estimated_monthly_cash_flow: float | None = None

        if income_input.estimated_monthly_rent is None:
            warnings.append("Estimated monthly rent missing; income support metrics were not computed.")
        else:
            effective_monthly_rent = income_input.estimated_monthly_rent * (1 - vacancy_pct)
            if gross_monthly_cost > 0:
                income_support_ratio = effective_monthly_rent / gross_monthly_cost
            estimated_monthly_cash_flow = effective_monthly_rent - gross_monthly_cost

        score_inputs_complete = all(
            value is not None
            for value in (
                income_input.annual_taxes,
                income_input.annual_insurance,
                income_input.estimated_monthly_rent,
            )
        )

        return IncomeAgentOutput(
            loan_amount=round(loan_amount, 2),
            monthly_principal_interest=round(monthly_principal_interest, 2),
            monthly_taxes=round(monthly_taxes, 2),
            monthly_insurance=round(monthly_insurance, 2),
            monthly_hoa=round(monthly_hoa, 2),
            monthly_maintenance_reserve=round(monthly_maintenance_reserve, 2),
            gross_monthly_cost=round(gross_monthly_cost, 2),
            effective_monthly_rent=round(effective_monthly_rent, 2) if effective_monthly_rent is not None else None,
            income_support_ratio=round(income_support_ratio, 4) if income_support_ratio is not None else None,
            estimated_monthly_cash_flow=round(estimated_monthly_cash_flow, 2)
            if estimated_monthly_cash_flow is not None
            else None,
            score_inputs_complete=score_inputs_complete,
            warnings=warnings,
            explanation=self._build_explanation(
                gross_monthly_cost=gross_monthly_cost,
                monthly_principal_interest=monthly_principal_interest,
                monthly_taxes=monthly_taxes,
                monthly_insurance=monthly_insurance,
                monthly_hoa=monthly_hoa,
                monthly_maintenance_reserve=monthly_maintenance_reserve,
                effective_monthly_rent=effective_monthly_rent,
                income_support_ratio=income_support_ratio,
            ),
        )

    def __call__(self, payload: IncomeAgentInput | dict[str, object]) -> IncomeAgentOutput:
        return self.run(payload)

    def _optional_value(
        self,
        *,
        value: float | None,
        default: float,
        warning: str,
        warnings: list[str],
    ) -> float:
        if value is None:
            warnings.append(warning)
            return default
        return value

    def _build_explanation(
        self,
        *,
        gross_monthly_cost: float,
        monthly_principal_interest: float,
        monthly_taxes: float,
        monthly_insurance: float,
        monthly_hoa: float,
        monthly_maintenance_reserve: float,
        effective_monthly_rent: float | None,
        income_support_ratio: float | None,
    ) -> str:
        cost_stack = (
            f"Monthly cost is about ${gross_monthly_cost:,.0f}, made up of "
            f"${monthly_principal_interest:,.0f} principal and interest, "
            f"${monthly_taxes:,.0f} taxes, "
            f"${monthly_insurance:,.0f} insurance, "
            f"${monthly_hoa:,.0f} HOA, and "
            f"${monthly_maintenance_reserve:,.0f} maintenance reserve."
        )
        if effective_monthly_rent is None or income_support_ratio is None:
            return f"{cost_stack} Rent support could not be assessed because rent was not provided."

        support_text = "supports" if income_support_ratio >= 1 else "does not fully support"
        return (
            f"{cost_stack} Effective rent is about ${effective_monthly_rent:,.0f}, "
            f"which {support_text} the carrying cost with an income support ratio of {income_support_ratio:.2f}."
        )


def analyze_income(payload: IncomeAgentInput | dict[str, object]) -> IncomeAgentOutput:
    """Convenience function for one-shot income analysis."""

    return IncomeAgent().run(payload)

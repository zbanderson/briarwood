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
        assumptions: list[str] = []
        unsupported_claims: list[str] = []

        annual_taxes = self._optional_value(
            value=income_input.annual_taxes,
            default=0.0,
            warning="Annual taxes missing; treating taxes as $0.00/month.",
            warnings=warnings,
        )
        if income_input.annual_taxes is None:
            unsupported_claims.append("Rental downside analysis is missing sourced annual property taxes.")
        annual_insurance = self._optional_value(
            value=income_input.annual_insurance,
            default=0.0,
            warning="Annual insurance missing; treating insurance as $0.00/month.",
            warnings=warnings,
        )
        if income_input.annual_insurance is None:
            unsupported_claims.append("Rental downside analysis is missing sourced annual insurance.")
        monthly_hoa = 0.0 if income_input.monthly_hoa is None else income_input.monthly_hoa
        if income_input.monthly_hoa is None:
            assumptions.append("HOA was not provided and was treated as $0/month.")
        vacancy_pct = self._optional_value(
            value=income_input.vacancy_pct,
            default=0.0,
            warning="Vacancy assumption missing; treating vacancy as 0.0%.",
            warnings=warnings,
        )
        if income_input.vacancy_pct is None:
            assumptions.append("Vacancy was not provided and was treated as 0.0%.")
        maintenance_pct = self._optional_value(
            value=income_input.maintenance_pct,
            default=0.0,
            warning="Maintenance assumption missing; treating maintenance reserve as 0.0%.",
            warnings=warnings,
        )
        if income_input.maintenance_pct is None:
            assumptions.append("Maintenance reserve was not provided and was treated as 0.0%.")

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
        annual_rent: float | None = None
        income_support_ratio: float | None = None
        price_to_rent: float | None = None
        estimated_monthly_cash_flow: float | None = None
        downside_burden: float | None = None

        if income_input.estimated_monthly_rent is None:
            warnings.append("Estimated monthly rent missing; income support metrics were not computed.")
            unsupported_claims.append("Rental downside analysis could not assess rent support because rent is missing.")
        else:
            assumptions.append("Rent is an estimate and may differ from achieved lease income.")
            effective_monthly_rent = income_input.estimated_monthly_rent * (1 - vacancy_pct)
            annual_rent = effective_monthly_rent * 12
            if gross_monthly_cost > 0:
                income_support_ratio = effective_monthly_rent / gross_monthly_cost
            if annual_rent and annual_rent > 0:
                price_to_rent = income_input.price / annual_rent
            estimated_monthly_cash_flow = effective_monthly_rent - gross_monthly_cost
            if estimated_monthly_cash_flow < 0:
                downside_burden = abs(estimated_monthly_cash_flow)

        if income_input.market_price_to_rent_benchmark is None:
            assumptions.append("No market price-to-rent benchmark was available; heuristic price-to-rent thresholds were used.")
            if price_to_rent is not None:
                unsupported_claims.append("Price-to-rent classification is heuristic because no market benchmark was supplied.")

        rent_support_classification, risk_view = self._classify_rent_support(income_support_ratio)
        price_to_rent_classification = self._classify_price_to_rent(
            price_to_rent=price_to_rent,
            benchmark=income_input.market_price_to_rent_benchmark,
        )
        confidence = self._calculate_confidence(
            rent_present=income_input.estimated_monthly_rent is not None,
            taxes_present=income_input.annual_taxes is not None,
            insurance_present=income_input.annual_insurance is not None,
            benchmark_present=income_input.market_price_to_rent_benchmark is not None,
            vacancy_present=income_input.vacancy_pct is not None,
            maintenance_present=income_input.maintenance_pct is not None,
        )

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
            total_monthly_cost=round(gross_monthly_cost, 2),
            effective_monthly_rent=round(effective_monthly_rent, 2) if effective_monthly_rent is not None else None,
            annual_rent=round(annual_rent, 2) if annual_rent is not None else None,
            income_support_ratio=round(income_support_ratio, 4) if income_support_ratio is not None else None,
            rent_coverage=round(income_support_ratio, 4) if income_support_ratio is not None else None,
            price_to_rent=round(price_to_rent, 2) if price_to_rent is not None else None,
            estimated_monthly_cash_flow=round(estimated_monthly_cash_flow, 2)
            if estimated_monthly_cash_flow is not None
            else None,
            monthly_cash_flow=round(estimated_monthly_cash_flow, 2)
            if estimated_monthly_cash_flow is not None
            else None,
            rent_support_classification=rent_support_classification,
            price_to_rent_classification=price_to_rent_classification,
            downside_burden=round(downside_burden, 2) if downside_burden is not None else None,
            risk_view=risk_view,
            confidence=confidence,
            assumptions=assumptions,
            unsupported_claims=unsupported_claims,
            summary=self._build_summary(
                monthly_cash_flow=estimated_monthly_cash_flow,
                downside_burden=downside_burden,
                rent_coverage=income_support_ratio,
                price_to_rent=price_to_rent,
                price_to_rent_classification=price_to_rent_classification,
                risk_view=risk_view,
                confidence=confidence,
            ),
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

    def _classify_rent_support(self, ratio: float | None) -> tuple[str, str]:
        if ratio is None:
            return "Unavailable", "weak_support"
        if ratio >= 1.1:
            return "Strong Support", "strong_support"
        if ratio >= 0.9:
            return "Neutral Support", "neutral_support"
        return "Weak Support", "weak_support"

    def _classify_price_to_rent(self, *, price_to_rent: float | None, benchmark: float | None) -> str:
        if price_to_rent is None:
            return "Unavailable"
        if benchmark is not None:
            lower_bound = benchmark * 0.9
            upper_bound = benchmark * 1.1
            if price_to_rent < lower_bound:
                return "Cheap"
            if price_to_rent <= upper_bound:
                return "Fair"
            return "Expensive"
        if price_to_rent < 15:
            return "Strong Value"
        if price_to_rent <= 20:
            return "Moderate"
        return "Expensive"

    def _calculate_confidence(
        self,
        *,
        rent_present: bool,
        taxes_present: bool,
        insurance_present: bool,
        benchmark_present: bool,
        vacancy_present: bool,
        maintenance_present: bool,
    ) -> float:
        confidence = 0.82 if rent_present else 0.22
        if not taxes_present:
            confidence -= 0.14
        if not insurance_present:
            confidence -= 0.14
        if not benchmark_present:
            confidence -= 0.06
        if not vacancy_present:
            confidence -= 0.05
        if not maintenance_present:
            confidence -= 0.05
        return round(max(0.1, min(confidence, 0.9)), 2)

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

    def _build_summary(
        self,
        *,
        monthly_cash_flow: float | None,
        downside_burden: float | None,
        rent_coverage: float | None,
        price_to_rent: float | None,
        price_to_rent_classification: str,
        risk_view: str,
        confidence: float,
    ) -> str:
        if monthly_cash_flow is None or rent_coverage is None:
            return (
                f"Rental downside support could not be assessed because rent is missing. "
                f"Confidence is {confidence:.2f} due to limited support inputs."
            )

        if monthly_cash_flow >= 0:
            support_sentence = "The property is self-sustaining under a rental scenario."
        elif downside_burden is not None and downside_burden <= 300:
            support_sentence = (
                f"The property requires a modest owner subsidy of about ${downside_burden:,.0f}/month under a rental scenario."
            )
        else:
            support_sentence = (
                f"The property is not supported by rental economics and would require roughly ${downside_burden or 0:,.0f}/month in subsidy."
            )

        if price_to_rent is None:
            pricing_sentence = "Price-to-rent could not be assessed because rent support is unavailable."
        else:
            pricing_sentence = (
                f"The price-to-rent ratio is {price_to_rent:.1f}, which reads as {price_to_rent_classification.lower()} "
                f"for an income-support lens."
            )

        confidence_sentence = (
            f"Confidence is {confidence:.2f}; this is a conservative downside view, not a return projection."
            if confidence < 0.75 or risk_view == "weak_support"
            else f"Confidence is {confidence:.2f}, though rent support should still be treated as a downside lens rather than a return projection."
        )
        return f"{support_sentence} {pricing_sentence} {confidence_sentence}"


def analyze_income(payload: IncomeAgentInput | dict[str, object]) -> IncomeAgentOutput:
    """Convenience function for one-shot income analysis."""

    return IncomeAgent().run(payload)

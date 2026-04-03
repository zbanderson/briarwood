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
        manual_unit_rents = [rent for rent in income_input.unit_rents if rent > 0]
        rent_source_type = (
            "manual_input"
            if manual_unit_rents
            else "provided"
            if income_input.estimated_monthly_rent is not None and income_input.rent_source_type == "missing"
            else income_input.rent_source_type
        )
        warnings: list[str] = []
        assumptions: list[str] = []
        unsupported_claims: list[str] = []
        missing_inputs: list[str] = []

        annual_taxes = self._optional_value(
            value=income_input.annual_taxes,
            default=0.0,
            warning="Annual taxes missing; treating taxes as $0.00/month.",
            warnings=warnings,
        )
        if income_input.annual_taxes is None:
            missing_inputs.append("annual_taxes")
            unsupported_claims.append("Rental downside analysis is missing sourced annual property taxes.")
        annual_insurance = self._optional_value(
            value=income_input.annual_insurance,
            default=0.0,
            warning="Annual insurance missing; treating insurance as $0.00/month.",
            warnings=warnings,
        )
        if income_input.annual_insurance is None:
            missing_inputs.append("annual_insurance")
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

        financing_missing = []
        if income_input.down_payment_pct is None:
            financing_missing.append("down_payment_pct")
            warnings.append("Down payment was not provided; mortgage payment was not computed.")
        if income_input.interest_rate is None:
            financing_missing.append("interest_rate")
            warnings.append("Interest rate was not provided; mortgage payment was not computed.")
        if income_input.loan_term_years is None:
            financing_missing.append("loan_term_years")
            warnings.append("Loan term was not provided; mortgage payment was not computed.")

        missing_inputs.extend(financing_missing)
        financing_complete = len(financing_missing) == 0
        carrying_cost_complete = financing_complete

        loan_amount: float | None = None
        monthly_principal_interest: float | None = None
        if financing_complete:
            loan_amount = calculate_loan_amount(income_input.price, income_input.down_payment_pct or 0.0)
            monthly_principal_interest = calculate_monthly_principal_interest(
                principal=loan_amount,
                annual_interest_rate=income_input.interest_rate or 0.0,
                loan_term_years=income_input.loan_term_years or 30,
            )
        else:
            unsupported_claims.append("Rental downside analysis could not verify financing because key financing inputs are missing.")

        monthly_taxes = annual_taxes / 12
        monthly_insurance = annual_insurance / 12
        monthly_maintenance_reserve = income_input.price * maintenance_pct / 12
        operating_monthly_cost = monthly_taxes + monthly_insurance + monthly_hoa + monthly_maintenance_reserve
        gross_monthly_cost = (
            (monthly_principal_interest or 0.0)
            + monthly_taxes
            + monthly_insurance
            + monthly_hoa
            + monthly_maintenance_reserve
        )

        effective_monthly_rent: float | None = None
        gross_monthly_rent_before_vacancy: float | None = None
        monthly_rent_estimate: float | None = None
        num_units: int | None = None
        avg_rent_per_unit: float | None = None
        unit_breakdown: list[float] = list(manual_unit_rents)
        annual_rent: float | None = None
        income_support_ratio: float | None = None
        price_to_rent: float | None = None
        estimated_monthly_cash_flow: float | None = None
        operating_monthly_cash_flow: float | None = None
        downside_burden: float | None = None

        if rent_source_type == "missing" or (
            income_input.estimated_monthly_rent is None and not manual_unit_rents
        ):
            missing_inputs.append("estimated_monthly_rent")
            warnings.append("Estimated monthly rent missing; income support metrics were not computed.")
            unsupported_claims.append("Rental downside analysis could not assess rent support because rent is missing.")
        else:
            if rent_source_type == "estimated":
                assumptions.append("Monthly rent is estimated from town-level context and may differ from achieved lease income.")
                warnings.append("Rent support uses an estimated rent input rather than a provided rent figure.")
            elif rent_source_type == "manual_input":
                num_units = len(manual_unit_rents)
                avg_rent_per_unit = (sum(manual_unit_rents) / num_units) if num_units else None
                assumptions.append(
                    f"Manual rent schedule with {num_units} unit{'s' if num_units != 1 else ''} was used to override estimated rent."
                )
            else:
                assumptions.append("Rent is a provided estimate and may differ from achieved lease income.")
            gross_monthly_rent_before_vacancy = (
                sum(manual_unit_rents)
                if manual_unit_rents
                else income_input.estimated_monthly_rent
            )
            monthly_rent_estimate = gross_monthly_rent_before_vacancy
            if income_input.back_house_monthly_rent:
                gross_monthly_rent_before_vacancy += income_input.back_house_monthly_rent
                assumptions.append(
                    f"Back-house/ADU rent of ${income_input.back_house_monthly_rent:,.0f}/mo was included in support."
                )
            effective_monthly_rent = gross_monthly_rent_before_vacancy * (1 - vacancy_pct)
            annual_rent = effective_monthly_rent * 12
            if carrying_cost_complete and gross_monthly_cost > 0:
                income_support_ratio = effective_monthly_rent / gross_monthly_cost
            elif not carrying_cost_complete:
                warnings.append("Financing inputs are incomplete, so rental support ratio and cash flow were not computed.")
            if annual_rent and annual_rent > 0:
                price_to_rent = income_input.price / annual_rent
            operating_monthly_cash_flow = effective_monthly_rent - operating_monthly_cost
            if carrying_cost_complete:
                estimated_monthly_cash_flow = effective_monthly_rent - gross_monthly_cost
                if estimated_monthly_cash_flow < 0:
                    downside_burden = abs(estimated_monthly_cash_flow)
            elif operating_monthly_cash_flow is not None and operating_monthly_cash_flow < 0:
                downside_burden = abs(operating_monthly_cash_flow)

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
            rent_source_type=rent_source_type,
            taxes_present=income_input.annual_taxes is not None,
            insurance_present=income_input.annual_insurance is not None,
            benchmark_present=income_input.market_price_to_rent_benchmark is not None,
            vacancy_present=income_input.vacancy_pct is not None,
            maintenance_present=income_input.maintenance_pct is not None,
            financing_complete=financing_complete,
        )

        score_inputs_complete = all(
            value is not None
            for value in (
                income_input.annual_taxes,
                income_input.annual_insurance,
                income_input.estimated_monthly_rent,
                income_input.down_payment_pct,
                income_input.interest_rate,
                income_input.loan_term_years,
            )
        )

        return IncomeAgentOutput(
            loan_amount=round(loan_amount, 2) if loan_amount is not None else None,
            monthly_principal_interest=round(monthly_principal_interest, 2)
            if monthly_principal_interest is not None
            else None,
            monthly_taxes=round(monthly_taxes, 2),
            monthly_insurance=round(monthly_insurance, 2),
            monthly_hoa=round(monthly_hoa, 2),
            monthly_maintenance_reserve=round(monthly_maintenance_reserve, 2),
            gross_monthly_cost=round(gross_monthly_cost, 2),
            total_monthly_cost=round(gross_monthly_cost, 2),
            operating_monthly_cost=round(operating_monthly_cost, 2),
            carrying_cost_complete=carrying_cost_complete,
            financing_complete=financing_complete,
            effective_monthly_rent=round(effective_monthly_rent, 2) if effective_monthly_rent is not None else None,
            gross_monthly_rent_before_vacancy=(
                round(gross_monthly_rent_before_vacancy, 2)
                if gross_monthly_rent_before_vacancy is not None
                else None
            ),
            monthly_rent_estimate=round(monthly_rent_estimate, 2) if monthly_rent_estimate is not None else None,
            num_units=num_units,
            avg_rent_per_unit=round(avg_rent_per_unit, 2) if avg_rent_per_unit is not None else None,
            unit_breakdown=[round(rent, 2) for rent in unit_breakdown],
            annual_rent=round(annual_rent, 2) if annual_rent is not None else None,
            rent_source_type=rent_source_type,
            income_support_ratio=round(income_support_ratio, 4) if income_support_ratio is not None else None,
            rent_coverage=round(income_support_ratio, 4) if income_support_ratio is not None else None,
            price_to_rent=round(price_to_rent, 2) if price_to_rent is not None else None,
            estimated_monthly_cash_flow=round(estimated_monthly_cash_flow, 2)
            if estimated_monthly_cash_flow is not None
            else None,
            monthly_cash_flow=round(estimated_monthly_cash_flow, 2)
            if estimated_monthly_cash_flow is not None
            else None,
            operating_monthly_cash_flow=round(operating_monthly_cash_flow, 2)
            if operating_monthly_cash_flow is not None
            else None,
            rent_support_classification=rent_support_classification,
            price_to_rent_classification=price_to_rent_classification,
            downside_burden=round(downside_burden, 2) if downside_burden is not None else None,
            risk_view=risk_view,
            confidence=confidence,
            missing_inputs=sorted(set(missing_inputs)),
            assumptions=assumptions,
            unsupported_claims=unsupported_claims,
            summary=self._build_summary(
                monthly_cash_flow=estimated_monthly_cash_flow,
                operating_monthly_cash_flow=operating_monthly_cash_flow,
                downside_burden=downside_burden,
                rent_coverage=income_support_ratio,
                price_to_rent=price_to_rent,
                price_to_rent_classification=price_to_rent_classification,
                risk_view=risk_view,
                confidence=confidence,
                financing_complete=financing_complete,
                rent_source_type=rent_source_type,
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
        rent_source_type: str,
        taxes_present: bool,
        insurance_present: bool,
        benchmark_present: bool,
        vacancy_present: bool,
        maintenance_present: bool,
        financing_complete: bool,
    ) -> float:
        if rent_source_type == "provided":
            confidence = 0.82
        elif rent_source_type == "manual_input":
            confidence = 0.88
        elif rent_source_type == "estimated":
            confidence = 0.52
        else:
            confidence = 0.18
        if not taxes_present:
            confidence -= 0.14
        if not insurance_present:
            confidence -= 0.18
        if not benchmark_present:
            confidence -= 0.06
        if not vacancy_present:
            confidence -= 0.05
        if not maintenance_present:
            confidence -= 0.05
        if not financing_complete:
            confidence -= 0.24
        if rent_source_type == "missing":
            confidence = min(confidence, 0.45)
        if rent_source_type == "estimated":
            confidence = min(confidence, 0.68)
        if rent_source_type == "manual_input":
            confidence = max(confidence, 0.72)
        if not financing_complete:
            confidence = min(confidence, 0.6)
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
        monthly_principal_interest: float | None,
        monthly_taxes: float,
        monthly_insurance: float,
        monthly_hoa: float,
        monthly_maintenance_reserve: float,
        effective_monthly_rent: float | None,
        income_support_ratio: float | None,
    ) -> str:
        cost_stack = (
            f"Monthly cost is about ${gross_monthly_cost:,.0f}, made up of "
            f"${monthly_principal_interest or 0:,.0f} principal and interest, "
            f"${monthly_taxes:,.0f} taxes, "
            f"${monthly_insurance:,.0f} insurance, "
            f"${monthly_hoa:,.0f} HOA, and "
            f"${monthly_maintenance_reserve:,.0f} maintenance reserve."
        )
        if monthly_principal_interest is None:
            return f"{cost_stack} Financing inputs were incomplete, so this is only a partial carry view."
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
        operating_monthly_cash_flow: float | None,
        downside_burden: float | None,
        rent_coverage: float | None,
        price_to_rent: float | None,
        price_to_rent_classification: str,
        risk_view: str,
        confidence: float,
        financing_complete: bool,
        rent_source_type: str,
    ) -> str:
        if rent_source_type == "missing":
            return (
                f"Rental downside support could not be assessed because rent is missing. "
                f"Confidence is {confidence:.2f} due to limited support inputs."
            )
        if not financing_complete or monthly_cash_flow is None or rent_coverage is None:
            operating_text = (
                f"pre-debt operating cash flow is about ${operating_monthly_cash_flow:,.0f}/month"
                if operating_monthly_cash_flow is not None
                else "pre-debt operating cash flow could not be established"
            )
            return (
                "Rental support could not be verified with full financing inputs, "
                f"but {operating_text}. Confidence is {confidence:.2f} due to partial support inputs."
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

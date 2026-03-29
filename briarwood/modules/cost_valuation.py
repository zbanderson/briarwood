from __future__ import annotations

from briarwood.agents.income import IncomeAgent
from briarwood.agents.income.schemas import IncomeAgentInput
from briarwood.agents.rent_context import RentContextAgent, RentContextInput
from briarwood.evidence import build_section_evidence
from briarwood.schemas import ModuleResult, PropertyInput, ValuationOutput
from briarwood.scoring import clamp_score
from briarwood.settings import CostValuationSettings, DEFAULT_COST_VALUATION_SETTINGS
from briarwood.utils import safe_divide


class CostValuationModule:
    name = "cost_valuation"

    def __init__(
        self,
        settings: CostValuationSettings | None = None,
        *,
        income_agent: IncomeAgent | None = None,
        rent_context_agent: RentContextAgent | None = None,
    ) -> None:
        self.settings = settings or DEFAULT_COST_VALUATION_SETTINGS
        self.income_agent = income_agent or IncomeAgent()
        self.rent_context_agent = rent_context_agent or RentContextAgent()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        purchase_price = property_input.purchase_price or 0.0
        annual_taxes = property_input.taxes or 0.0
        annual_insurance = property_input.insurance or 0.0
        rent_context = self.rent_context_agent.run(
            RentContextInput(
                town=property_input.town,
                state=property_input.state,
                sqft=property_input.sqft,
                explicit_monthly_rent=property_input.estimated_monthly_rent,
            )
        )
        monthly_rent = rent_context.rent_estimate
        down_payment_percent = self._normalize_percent(property_input.down_payment_percent)
        interest_rate = self._normalize_percent(property_input.interest_rate)
        vacancy_rate = (
            property_input.vacancy_rate
            if property_input.vacancy_rate is not None
            else self.settings.default_vacancy_rate
        )
        loan_term_years = property_input.loan_term_years or self.settings.loan_term_years
        monthly_hoa = property_input.monthly_hoa if property_input.monthly_hoa is not None else 0.0

        income = self.income_agent.run(
            IncomeAgentInput(
                price=purchase_price or 1.0,
                down_payment_pct=down_payment_percent,
                interest_rate=interest_rate,
                loan_term_years=loan_term_years,
                annual_taxes=annual_taxes,
                annual_insurance=annual_insurance,
                monthly_hoa=monthly_hoa,
                estimated_monthly_rent=monthly_rent,
                rent_source_type=rent_context.rent_source_type,
                vacancy_pct=vacancy_rate,
                maintenance_pct=self.settings.default_maintenance_reserve_pct,
            )
        )

        down_payment_amount = (
            purchase_price * down_payment_percent if purchase_price > 0 and down_payment_percent is not None else None
        )
        loan_amount = income.loan_amount
        effective_monthly_rent = income.effective_monthly_rent
        monthly_taxes = income.monthly_taxes
        monthly_insurance = income.monthly_insurance
        monthly_hoa = income.monthly_hoa
        monthly_maintenance_reserve = income.monthly_maintenance_reserve
        monthly_mortgage = income.monthly_principal_interest
        monthly_total_cost = income.gross_monthly_cost

        annual_gross_rent = monthly_rent * 12 if monthly_rent is not None else None
        annual_effective_rent = effective_monthly_rent * 12 if effective_monthly_rent is not None else None
        annual_hoa = monthly_hoa * 12
        annual_maintenance = monthly_maintenance_reserve * 12
        annual_noi = (
            annual_effective_rent - annual_taxes - annual_insurance - annual_hoa - annual_maintenance
            if annual_effective_rent is not None
            else None
        )
        annual_debt_service = monthly_mortgage * 12 if monthly_mortgage is not None else None
        annual_cash_flow = (
            annual_noi - annual_debt_service
            if annual_noi is not None and annual_debt_service is not None
            else None
        )
        monthly_cash_flow = income.estimated_monthly_cash_flow

        price_per_sqft = safe_divide(purchase_price, property_input.sqft)
        cap_rate = safe_divide(annual_noi, purchase_price) if annual_noi is not None else None
        gross_yield = safe_divide(annual_gross_rent, purchase_price) if annual_gross_rent is not None else None
        dscr = safe_divide(annual_noi, annual_debt_service) if annual_noi is not None and annual_debt_service is not None else None
        cash_on_cash_return = (
            safe_divide(annual_cash_flow, down_payment_amount)
            if annual_cash_flow is not None and down_payment_amount is not None
            else None
        )

        score = self._score_valuation(
            cap_rate=cap_rate,
            dscr=dscr,
            cash_on_cash_return=cash_on_cash_return,
            monthly_cash_flow=monthly_cash_flow,
        )
        confidence = self._confidence(property_input, rent_source_type=rent_context.rent_source_type, financing_complete=income.financing_complete)

        valuation_output = ValuationOutput(
            purchase_price=purchase_price,
            price_per_sqft=price_per_sqft,
            monthly_rent=monthly_rent,
            rent_source_type=rent_context.rent_source_type,
            carrying_cost_complete=income.carrying_cost_complete,
            financing_complete=income.financing_complete,
            effective_monthly_rent=effective_monthly_rent,
            monthly_taxes=monthly_taxes,
            monthly_insurance=monthly_insurance,
            monthly_hoa=monthly_hoa,
            monthly_maintenance_reserve=monthly_maintenance_reserve,
            monthly_mortgage_payment=monthly_mortgage,
            monthly_total_cost=monthly_total_cost,
            monthly_cash_flow=monthly_cash_flow,
            annual_noi=annual_noi,
            cap_rate=cap_rate,
            gross_yield=gross_yield,
            dscr=dscr,
            cash_on_cash_return=cash_on_cash_return,
            loan_amount=loan_amount,
            down_payment_amount=down_payment_amount,
        )
        summary = self._build_summary(
            address=property_input.address,
            cap_rate=cap_rate,
            monthly_cash_flow=monthly_cash_flow,
            score=score,
        )
        return ModuleResult(
            module_name=self.name,
            metrics=valuation_output.to_metrics(),
            score=score,
            confidence=confidence,
            summary=summary,
            payload=valuation_output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["price_ask", "sqft", "taxes", "insurance_estimate", "rent_estimate", "financing_down_payment", "financing_interest_rate"],
                extra_estimated_inputs=(["rent_estimate"] if rent_context.rent_source_type == "estimated" else []),
                notes=["Cost valuation mixes sourced property facts with any user-supplied or estimated rent/financing assumptions."],
            ),
        )

    def _normalize_percent(self, value: float | None) -> float | None:
        if value is None:
            return None
        return value / 100 if value > 1 else value

    def _score_valuation(
        self,
        *,
        cap_rate: float | None,
        dscr: float | None,
        cash_on_cash_return: float | None,
        monthly_cash_flow: float | None,
    ) -> float:
        score = self.settings.base_score
        if cap_rate is not None:
            score += min(
                cap_rate * self.settings.cap_rate_weight,
                self.settings.cap_rate_score_cap,
            )
        if dscr is not None:
            score += min(
                max((dscr - self.settings.dscr_baseline) * self.settings.dscr_weight, 0),
                self.settings.dscr_score_cap,
            )
        if cash_on_cash_return is not None:
            score += min(
                max(cash_on_cash_return * self.settings.cash_on_cash_weight, 0),
                self.settings.cash_on_cash_score_cap,
            )
        if monthly_cash_flow is not None and monthly_cash_flow > 0:
            score += min(
                monthly_cash_flow / self.settings.positive_cash_flow_divisor,
                self.settings.positive_cash_flow_score_cap,
            )
        elif monthly_cash_flow is not None:
            score += max(
                monthly_cash_flow / self.settings.negative_cash_flow_divisor,
                self.settings.negative_cash_flow_score_floor,
            )
        return clamp_score(score)

    def _confidence(self, property_input: PropertyInput, *, rent_source_type: str, financing_complete: bool) -> float:
        required_values = [
            property_input.purchase_price,
            property_input.sqft,
            property_input.taxes,
            property_input.insurance,
        ]
        populated = sum(value is not None for value in required_values)
        confidence = round(
            self.settings.confidence_floor
            + (populated / len(required_values)) * self.settings.confidence_range,
            2,
        )
        if rent_source_type == "missing":
            confidence = min(confidence, 0.48)
        elif rent_source_type == "estimated":
            confidence = min(confidence, 0.64)
        if not financing_complete:
            confidence = min(confidence, 0.58)
        if property_input.insurance is None:
            confidence = min(confidence, 0.62)
        return confidence

    def _build_summary(
        self,
        *,
        address: str,
        cap_rate: float | None,
        monthly_cash_flow: float | None,
        score: float,
    ) -> str:
        cap_rate_text = f"{cap_rate:.1%}" if cap_rate is not None else "n/a"
        if monthly_cash_flow is None:
            return (
                f"{address} screens at a {cap_rate_text} cap rate, but rental carry is only partially underwritten "
                f"because rent or financing inputs are incomplete; valuation score is {score:.0f}/100."
            )
        cash_flow_text = "positive" if monthly_cash_flow >= 0 else "negative"
        return (
            f"{address} screens at a {cap_rate_text} cap rate with "
            f"{cash_flow_text} monthly cash flow of ${abs(monthly_cash_flow):,.0f}; "
            f"valuation score is {score:.0f}/100."
        )

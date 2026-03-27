from __future__ import annotations

from briarwood.schemas import ModuleResult, PropertyInput, ValuationOutput
from briarwood.settings import CostValuationSettings, DEFAULT_COST_VALUATION_SETTINGS
from briarwood.scoring import clamp_score
from briarwood.utils import safe_divide


class CostValuationModule:
    name = "cost_valuation"

    def __init__(self, settings: CostValuationSettings | None = None) -> None:
        self.settings = settings or DEFAULT_COST_VALUATION_SETTINGS

    def run(self, property_input: PropertyInput) -> ModuleResult:
        purchase_price = property_input.purchase_price or 0.0
        annual_taxes = property_input.taxes or 0.0
        annual_insurance = property_input.insurance or 0.0
        monthly_rent = property_input.estimated_monthly_rent or 0.0
        down_payment_percent = self._normalize_percent(property_input.down_payment_percent)
        interest_rate = self._normalize_percent(property_input.interest_rate)
        vacancy_rate = (
            property_input.vacancy_rate
            if property_input.vacancy_rate is not None
            else self.settings.default_vacancy_rate
        )

        down_payment_amount = purchase_price * down_payment_percent
        loan_amount = purchase_price - down_payment_amount
        monthly_taxes = annual_taxes / 12
        monthly_insurance = annual_insurance / 12
        monthly_mortgage = self._calculate_monthly_mortgage(
            loan_amount,
            interest_rate,
            years=self.settings.loan_term_years,
        )
        monthly_operating_cost = monthly_taxes + monthly_insurance
        monthly_total_cost = monthly_operating_cost + monthly_mortgage

        annual_gross_rent = monthly_rent * 12
        annual_effective_rent = annual_gross_rent * (1 - vacancy_rate)
        annual_noi = annual_effective_rent - annual_taxes - annual_insurance
        annual_debt_service = monthly_mortgage * 12
        annual_cash_flow = annual_noi - annual_debt_service
        monthly_cash_flow = annual_cash_flow / 12

        price_per_sqft = safe_divide(purchase_price, property_input.sqft)
        cap_rate = safe_divide(annual_noi, purchase_price)
        gross_yield = safe_divide(annual_gross_rent, purchase_price)
        dscr = safe_divide(annual_noi, annual_debt_service)
        cash_on_cash_return = safe_divide(annual_cash_flow, down_payment_amount)

        score = self._score_valuation(
            cap_rate=cap_rate,
            dscr=dscr,
            cash_on_cash_return=cash_on_cash_return,
            monthly_cash_flow=monthly_cash_flow,
        )
        confidence = self._confidence(property_input)

        valuation_output = ValuationOutput(
            purchase_price=purchase_price,
            price_per_sqft=price_per_sqft,
            monthly_rent=monthly_rent,
            monthly_taxes=monthly_taxes,
            monthly_insurance=monthly_insurance,
            monthly_mortgage_payment=monthly_mortgage,
            monthly_total_cost=monthly_total_cost,
            monthly_cash_flow=monthly_cash_flow,
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
        )

    def _normalize_percent(self, value: float | None) -> float:
        if value is None:
            return 0.0
        return value / 100 if value > 1 else value

    def _calculate_monthly_mortgage(self, principal: float, annual_rate: float, years: int = 30) -> float:
        if principal <= 0:
            return 0.0
        monthly_rate = annual_rate / 12
        periods = years * 12
        if monthly_rate == 0:
            return principal / periods
        growth = (1 + monthly_rate) ** periods
        return principal * (monthly_rate * growth) / (growth - 1)

    def _score_valuation(
        self,
        *,
        cap_rate: float | None,
        dscr: float | None,
        cash_on_cash_return: float | None,
        monthly_cash_flow: float,
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
        if monthly_cash_flow > 0:
            score += min(
                monthly_cash_flow / self.settings.positive_cash_flow_divisor,
                self.settings.positive_cash_flow_score_cap,
            )
        else:
            score += max(
                monthly_cash_flow / self.settings.negative_cash_flow_divisor,
                self.settings.negative_cash_flow_score_floor,
            )
        return clamp_score(score)

    def _confidence(self, property_input: PropertyInput) -> float:
        required_values = [
            property_input.purchase_price,
            property_input.sqft,
            property_input.taxes,
            property_input.insurance,
            property_input.estimated_monthly_rent,
            property_input.down_payment_percent,
            property_input.interest_rate,
        ]
        populated = sum(value is not None for value in required_values)
        return round(
            self.settings.confidence_floor
            + (populated / len(required_values)) * self.settings.confidence_range,
            2,
        )

    def _build_summary(
        self,
        *,
        address: str,
        cap_rate: float | None,
        monthly_cash_flow: float,
        score: float,
    ) -> str:
        cap_rate_text = f"{cap_rate:.1%}" if cap_rate is not None else "n/a"
        cash_flow_text = "positive" if monthly_cash_flow >= 0 else "negative"
        return (
            f"{address} screens at a {cap_rate_text} cap rate with "
            f"{cash_flow_text} monthly cash flow of ${abs(monthly_cash_flow):,.0f}; "
            f"valuation score is {score:.0f}/100."
        )

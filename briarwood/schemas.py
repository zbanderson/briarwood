from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


MetricValue = float | int | str | bool | None


@dataclass(slots=True)
class PropertyInput:
    property_id: str
    address: str
    town: str
    state: str
    beds: int
    baths: float
    sqft: int
    county: str | None = None
    property_type: str | None = None
    lot_size: float | None = None
    year_built: int | None = None
    purchase_price: float | None = None
    taxes: float | None = None
    insurance: float | None = None
    monthly_hoa: float | None = None
    estimated_monthly_rent: float | None = None
    down_payment_percent: float | None = None
    interest_rate: float | None = None
    loan_term_years: int | None = None
    days_on_market: int | None = None
    listing_date: str | None = None
    source_url: str | None = None
    price_history: list[dict[str, Any]] = field(default_factory=list)
    vacancy_rate: float | None = None
    town_population_trend: float | None = None
    town_price_trend: float | None = None
    school_rating: float | None = None
    flood_risk: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModuleResult:
    module_name: str
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    score: float = 0.0
    confidence: float = 0.0
    summary: str = ""
    payload: Any | None = None


@dataclass(slots=True)
class ValuationOutput:
    purchase_price: float
    price_per_sqft: float | None
    monthly_rent: float
    effective_monthly_rent: float
    monthly_taxes: float
    monthly_insurance: float
    monthly_hoa: float
    monthly_maintenance_reserve: float
    monthly_mortgage_payment: float
    monthly_total_cost: float
    monthly_cash_flow: float
    annual_noi: float
    cap_rate: float | None
    gross_yield: float | None
    dscr: float | None
    cash_on_cash_return: float | None
    loan_amount: float
    down_payment_amount: float

    def to_metrics(self) -> dict[str, MetricValue]:
        return {
            "purchase_price": round(self.purchase_price, 2),
            "price_per_sqft": round(self.price_per_sqft, 2) if self.price_per_sqft is not None else None,
            "monthly_rent": round(self.monthly_rent, 2),
            "effective_monthly_rent": round(self.effective_monthly_rent, 2),
            "monthly_taxes": round(self.monthly_taxes, 2),
            "monthly_insurance": round(self.monthly_insurance, 2),
            "monthly_hoa": round(self.monthly_hoa, 2),
            "monthly_maintenance_reserve": round(self.monthly_maintenance_reserve, 2),
            "monthly_mortgage_payment": round(self.monthly_mortgage_payment, 2),
            "monthly_total_cost": round(self.monthly_total_cost, 2),
            "monthly_cash_flow": round(self.monthly_cash_flow, 2),
            "annual_noi": round(self.annual_noi, 2),
            "cap_rate": round(self.cap_rate, 4) if self.cap_rate is not None else None,
            "gross_yield": round(self.gross_yield, 4) if self.gross_yield is not None else None,
            "dscr": round(self.dscr, 2) if self.dscr is not None else None,
            "cash_on_cash_return": round(self.cash_on_cash_return, 4)
            if self.cash_on_cash_return is not None
            else None,
            "loan_amount": round(self.loan_amount, 2),
            "down_payment_amount": round(self.down_payment_amount, 2),
        }


@dataclass(slots=True)
class ScenarioOutput:
    ask_price: float
    bull_case_value: float
    base_case_value: float
    bear_case_value: float
    spread: float

    def to_metrics(self) -> dict[str, MetricValue]:
        return {
            "ask_price": round(self.ask_price, 2),
            "bull_case_value": round(self.bull_case_value, 0),
            "base_case_value": round(self.base_case_value, 0),
            "bear_case_value": round(self.bear_case_value, 0),
            "spread": round(self.spread, 0),
        }


@dataclass(slots=True)
class AnalysisReport:
    property_id: str
    address: str
    module_results: dict[str, ModuleResult] = field(default_factory=dict)

    def get_module(self, module_name: str) -> ModuleResult:
        return self.module_results[module_name]


class AnalysisModule(Protocol):
    name: str

    def run(self, property_input: PropertyInput) -> ModuleResult:
        ...

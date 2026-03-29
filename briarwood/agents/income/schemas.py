from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncomeAgentInput(BaseModel):
    """Typed request model for monthly ownership economics."""

    model_config = ConfigDict(extra="forbid")

    price: float = Field(gt=0)
    down_payment_pct: float | None = Field(default=None, ge=0, le=1)
    interest_rate: float | None = Field(default=None, ge=0, le=1)
    loan_term_years: int | None = Field(default=None, gt=0)
    annual_taxes: float | None = Field(default=None, ge=0)
    annual_insurance: float | None = Field(default=None, ge=0)
    monthly_hoa: float | None = Field(default=None, ge=0)
    estimated_monthly_rent: float | None = Field(default=None, ge=0)
    rent_source_type: str = Field(default="missing", pattern="^(provided|estimated|missing)$")
    vacancy_pct: float | None = Field(default=None, ge=0, le=1)
    maintenance_pct: float | None = Field(default=None, ge=0, le=1)
    market_price_to_rent_benchmark: float | None = Field(default=None, gt=0)

    @field_validator("price", "loan_term_years")
    @classmethod
    def _reject_bool_values(cls, value: float | int) -> float | int:
        if isinstance(value, bool):
            raise TypeError("Boolean values are not valid numeric inputs.")
        return value


class IncomeAgentOutput(BaseModel):
    """Structured monthly ownership snapshot for downstream agents."""

    model_config = ConfigDict(extra="forbid")

    loan_amount: float | None
    monthly_principal_interest: float | None
    monthly_taxes: float
    monthly_insurance: float
    monthly_hoa: float
    monthly_maintenance_reserve: float
    gross_monthly_cost: float
    total_monthly_cost: float
    operating_monthly_cost: float | None = None
    carrying_cost_complete: bool
    financing_complete: bool
    effective_monthly_rent: float | None
    annual_rent: float | None
    rent_source_type: str = Field(pattern="^(provided|estimated|missing)$")
    income_support_ratio: float | None
    rent_coverage: float | None
    price_to_rent: float | None
    estimated_monthly_cash_flow: float | None
    monthly_cash_flow: float | None
    operating_monthly_cash_flow: float | None = None
    rent_support_classification: str
    price_to_rent_classification: str
    downside_burden: float | None
    risk_view: str
    confidence: float
    missing_inputs: list[str]
    assumptions: list[str]
    unsupported_claims: list[str]
    summary: str
    score_inputs_complete: bool
    warnings: list[str]
    explanation: str

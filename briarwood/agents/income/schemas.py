from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncomeAgentInput(BaseModel):
    """Typed request model for monthly ownership economics."""

    model_config = ConfigDict(extra="forbid")

    price: float = Field(gt=0)
    down_payment_pct: float = Field(ge=0, le=1)
    interest_rate: float = Field(ge=0, le=1)
    loan_term_years: int = Field(gt=0)
    annual_taxes: float | None = Field(default=None, ge=0)
    annual_insurance: float | None = Field(default=None, ge=0)
    monthly_hoa: float | None = Field(default=None, ge=0)
    estimated_monthly_rent: float | None = Field(default=None, ge=0)
    vacancy_pct: float | None = Field(default=None, ge=0, le=1)
    maintenance_pct: float | None = Field(default=None, ge=0, le=1)

    @field_validator("price", "loan_term_years")
    @classmethod
    def _reject_bool_values(cls, value: float | int) -> float | int:
        if isinstance(value, bool):
            raise TypeError("Boolean values are not valid numeric inputs.")
        return value


class IncomeAgentOutput(BaseModel):
    """Structured monthly ownership snapshot for downstream agents."""

    model_config = ConfigDict(extra="forbid")

    loan_amount: float
    monthly_principal_interest: float
    monthly_taxes: float
    monthly_insurance: float
    monthly_hoa: float
    monthly_maintenance_reserve: float
    gross_monthly_cost: float
    effective_monthly_rent: float | None
    income_support_ratio: float | None
    estimated_monthly_cash_flow: float | None
    score_inputs_complete: bool
    warnings: list[str]
    explanation: str

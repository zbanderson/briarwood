from __future__ import annotations


def calculate_loan_amount(price: float, down_payment_pct: float) -> float:
    """Return the financed principal after the down payment."""

    return price * (1 - down_payment_pct)


def calculate_monthly_principal_interest(
    principal: float,
    annual_interest_rate: float,
    loan_term_years: int,
) -> float:
    """Compute the standard fixed-rate mortgage payment."""

    if principal <= 0:
        return 0.0

    periods = loan_term_years * 12
    monthly_rate = annual_interest_rate / 12
    if monthly_rate == 0:
        return principal / periods

    growth = (1 + monthly_rate) ** periods
    return principal * (monthly_rate * growth) / (growth - 1)

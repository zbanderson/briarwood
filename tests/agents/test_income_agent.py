import unittest

from pydantic import ValidationError

from briarwood.agents.income.agent import IncomeAgent, analyze_income
from briarwood.agents.income.schemas import IncomeAgentInput, IncomeAgentOutput


def sample_payload() -> dict[str, float | int | None]:
    return {
        "price": 500000.0,
        "down_payment_pct": 0.2,
        "interest_rate": 0.06,
        "loan_term_years": 30,
        "annual_taxes": 7200.0,
        "annual_insurance": 1800.0,
        "monthly_hoa": 150.0,
        "estimated_monthly_rent": 3600.0,
        "vacancy_pct": 0.05,
        "maintenance_pct": 0.01,
    }


class IncomeAgentTests(unittest.TestCase):
    def test_full_input_case(self) -> None:
        result = IncomeAgent().run(sample_payload())

        self.assertIsInstance(result, IncomeAgentOutput)
        self.assertEqual(result.loan_amount, 400000.0)
        self.assertAlmostEqual(result.monthly_principal_interest, 2398.2, places=2)
        self.assertEqual(result.monthly_taxes, 600.0)
        self.assertEqual(result.monthly_insurance, 150.0)
        self.assertEqual(result.monthly_hoa, 150.0)
        self.assertAlmostEqual(result.monthly_maintenance_reserve, 416.67, places=2)
        self.assertAlmostEqual(result.gross_monthly_cost, 3714.87, places=2)
        self.assertEqual(result.effective_monthly_rent, 3420.0)
        self.assertAlmostEqual(result.income_support_ratio, 0.9206, places=4)
        self.assertAlmostEqual(result.estimated_monthly_cash_flow, -294.87, places=2)
        self.assertTrue(result.score_inputs_complete)
        self.assertEqual(result.warnings, [])
        self.assertIn("does not fully support", result.explanation)

    def test_missing_optional_values_returns_partial_with_warnings(self) -> None:
        payload = sample_payload()
        payload["annual_taxes"] = None
        payload["annual_insurance"] = None
        payload["monthly_hoa"] = None
        payload["vacancy_pct"] = None
        payload["maintenance_pct"] = None

        result = analyze_income(payload)

        self.assertEqual(result.monthly_taxes, 0.0)
        self.assertEqual(result.monthly_insurance, 0.0)
        self.assertEqual(result.monthly_hoa, 0.0)
        self.assertEqual(result.monthly_maintenance_reserve, 0.0)
        self.assertEqual(result.effective_monthly_rent, 3600.0)
        self.assertFalse(result.score_inputs_complete)
        self.assertEqual(len(result.warnings), 5)

    def test_zero_hoa_is_preserved_without_warning(self) -> None:
        payload = sample_payload()
        payload["monthly_hoa"] = 0.0

        result = IncomeAgent().run(payload)

        self.assertEqual(result.monthly_hoa, 0.0)
        self.assertNotIn("Monthly HOA missing; treating HOA as $0.00/month.", result.warnings)

    def test_missing_rent_keeps_support_metrics_unset(self) -> None:
        payload = sample_payload()
        payload["estimated_monthly_rent"] = None

        result = IncomeAgent().run(IncomeAgentInput.model_validate(payload))

        self.assertIsNone(result.effective_monthly_rent)
        self.assertIsNone(result.income_support_ratio)
        self.assertIsNone(result.estimated_monthly_cash_flow)
        self.assertFalse(result.score_inputs_complete)
        self.assertIn("Estimated monthly rent missing; income support metrics were not computed.", result.warnings)

    def test_invalid_values_raise_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            IncomeAgentInput.model_validate(
                {
                    "price": -1.0,
                    "down_payment_pct": 1.2,
                    "interest_rate": -0.01,
                    "loan_term_years": 0,
                }
            )


if __name__ == "__main__":
    unittest.main()

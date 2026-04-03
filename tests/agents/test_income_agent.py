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
        self.assertEqual(result.rent_source_type, "provided")
        self.assertEqual(result.monthly_taxes, 600.0)
        self.assertEqual(result.monthly_insurance, 150.0)
        self.assertEqual(result.monthly_hoa, 150.0)
        self.assertAlmostEqual(result.monthly_maintenance_reserve, 416.67, places=2)
        self.assertAlmostEqual(result.gross_monthly_cost, 3714.87, places=2)
        self.assertAlmostEqual(result.total_monthly_cost, 3714.87, places=2)
        self.assertAlmostEqual(result.operating_monthly_cost, 1316.67, places=2)
        self.assertEqual(result.effective_monthly_rent, 3420.0)
        self.assertEqual(result.annual_rent, 41040.0)
        self.assertAlmostEqual(result.income_support_ratio, 0.9206, places=4)
        self.assertAlmostEqual(result.rent_coverage, 0.9206, places=4)
        self.assertAlmostEqual(result.price_to_rent, 12.18, places=2)
        self.assertAlmostEqual(result.estimated_monthly_cash_flow, -294.87, places=2)
        self.assertAlmostEqual(result.monthly_cash_flow, -294.87, places=2)
        self.assertAlmostEqual(result.operating_monthly_cash_flow, 2103.33, places=2)
        self.assertAlmostEqual(result.downside_burden, 294.87, places=2)
        self.assertEqual(result.rent_support_classification, "Neutral Support")
        self.assertEqual(result.price_to_rent_classification, "Strong Value")
        self.assertEqual(result.risk_view, "neutral_support")
        self.assertTrue(result.financing_complete)
        self.assertTrue(result.carrying_cost_complete)
        self.assertLess(result.confidence, 0.9)
        self.assertTrue(result.assumptions)
        self.assertIn("price-to-rent ratio", result.summary.lower())
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
        self.assertTrue(result.financing_complete)
        self.assertEqual(len(result.warnings), 4)
        self.assertNotIn("Monthly HOA missing; treating HOA as $0.00/month.", result.warnings)
        self.assertGreaterEqual(len(result.assumptions), 3)
        self.assertGreaterEqual(len(result.unsupported_claims), 2)

    def test_zero_hoa_is_preserved_without_warning(self) -> None:
        payload = sample_payload()
        payload["monthly_hoa"] = 0.0

        result = IncomeAgent().run(payload)

        self.assertEqual(result.monthly_hoa, 0.0)
        self.assertNotIn("Monthly HOA missing; treating HOA as $0.00/month.", result.warnings)

    def test_missing_rent_keeps_support_metrics_unset(self) -> None:
        payload = sample_payload()
        payload["estimated_monthly_rent"] = None
        payload["rent_source_type"] = "missing"

        result = IncomeAgent().run(IncomeAgentInput.model_validate(payload))

        self.assertIsNone(result.effective_monthly_rent)
        self.assertIsNone(result.income_support_ratio)
        self.assertIsNone(result.estimated_monthly_cash_flow)
        self.assertIsNone(result.price_to_rent)
        self.assertEqual(result.rent_support_classification, "Unavailable")
        self.assertFalse(result.score_inputs_complete)
        self.assertIn("Estimated monthly rent missing; income support metrics were not computed.", result.warnings)
        self.assertIn("could not be assessed", result.summary)

    def test_missing_financing_disables_support_ratio(self) -> None:
        payload = sample_payload()
        payload["down_payment_pct"] = None
        payload["interest_rate"] = None
        payload["loan_term_years"] = None
        payload["rent_source_type"] = "provided"

        result = IncomeAgent().run(IncomeAgentInput.model_validate(payload))

        self.assertIsNone(result.loan_amount)
        self.assertIsNone(result.monthly_principal_interest)
        self.assertIsNone(result.income_support_ratio)
        self.assertIsNone(result.monthly_cash_flow)
        self.assertIsNotNone(result.operating_monthly_cash_flow)
        self.assertFalse(result.financing_complete)
        self.assertIn("interest_rate", result.missing_inputs)
        self.assertIn("pre-debt operating cash flow", result.summary.lower())

    def test_estimated_rent_lowers_confidence_and_flags_assumption(self) -> None:
        payload = sample_payload()
        payload["rent_source_type"] = "estimated"

        result = IncomeAgent().run(IncomeAgentInput.model_validate(payload))

        self.assertEqual(result.rent_source_type, "estimated")
        self.assertLess(result.confidence, 0.75)
        self.assertTrue(any("estimated" in item.lower() for item in result.assumptions))
        self.assertTrue(any("estimated rent input" in item.lower() for item in result.warnings))

    def test_back_house_rent_increases_effective_rent_support(self) -> None:
        payload = sample_payload()
        payload["back_house_monthly_rent"] = 900.0

        result = IncomeAgent().run(IncomeAgentInput.model_validate(payload))

        self.assertEqual(result.gross_monthly_rent_before_vacancy, 4500.0)
        self.assertAlmostEqual(result.effective_monthly_rent, 4275.0, places=2)
        self.assertGreater(result.income_support_ratio or 0.0, 1.0)
        self.assertTrue(any("back-house" in item.lower() or "adu" in item.lower() for item in result.assumptions))

    def test_manual_unit_rents_override_estimated_rent(self) -> None:
        payload = sample_payload()
        payload["estimated_monthly_rent"] = 3600.0
        payload["unit_rents"] = [1800.0, 1900.0]
        payload["rent_source_type"] = "manual_input"

        result = IncomeAgent().run(IncomeAgentInput.model_validate(payload))

        self.assertEqual(result.rent_source_type, "manual_input")
        self.assertEqual(result.monthly_rent_estimate, 3700.0)
        self.assertEqual(result.num_units, 2)
        self.assertEqual(result.avg_rent_per_unit, 1850.0)
        self.assertEqual(result.unit_breakdown, [1800.0, 1900.0])
        self.assertAlmostEqual(result.gross_monthly_rent_before_vacancy, 3700.0, places=2)
        self.assertTrue(any("manual rent schedule" in item.lower() for item in result.assumptions))

    def test_price_to_rent_uses_benchmark_when_available(self) -> None:
        payload = sample_payload()
        payload["market_price_to_rent_benchmark"] = 13.0

        result = IncomeAgent().run(payload)

        self.assertEqual(result.price_to_rent_classification, "Fair")

    def test_strong_negative_cash_flow_reads_as_weak_support(self) -> None:
        payload = sample_payload()
        payload["estimated_monthly_rent"] = 2400.0

        result = IncomeAgent().run(payload)

        self.assertEqual(result.risk_view, "weak_support")
        self.assertEqual(result.rent_support_classification, "Weak Support")
        self.assertGreater(result.downside_burden or 0.0, 1000.0)

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

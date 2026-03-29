import unittest

from briarwood.schemas import ModuleResult, PropertyInput, ScenarioOutput, ValuationOutput


class SchemaTests(unittest.TestCase):
    def test_property_input_to_dict_contains_expected_fields(self) -> None:
        property_input = PropertyInput(
            property_id="1",
            address="1 Main St",
            town="Testville",
            state="MA",
            beds=3,
            baths=2.0,
            sqft=1500,
        )

        data = property_input.to_dict()

        self.assertEqual(data["address"], "1 Main St")
        self.assertEqual(data["beds"], 3)

    def test_module_result_defaults_are_stable(self) -> None:
        result = ModuleResult(module_name="example")

        self.assertEqual(result.metrics, {})
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_typed_outputs_convert_to_metrics(self) -> None:
        valuation = ValuationOutput(
            purchase_price=100000.0,
            price_per_sqft=200.0,
            monthly_rent=1200.0,
            rent_source_type="provided",
            carrying_cost_complete=True,
            financing_complete=True,
            effective_monthly_rent=1140.0,
            monthly_taxes=100.0,
            monthly_insurance=50.0,
            monthly_hoa=0.0,
            monthly_maintenance_reserve=75.0,
            monthly_mortgage_payment=500.0,
            monthly_total_cost=650.0,
            monthly_cash_flow=550.0,
            annual_noi=10980.0,
            cap_rate=0.06,
            gross_yield=0.12,
            dscr=1.2,
            cash_on_cash_return=0.08,
            loan_amount=80000.0,
            down_payment_amount=20000.0,
        )
        scenario = ScenarioOutput(
            ask_price=100000.0,
            bull_case_value=120000.0,
            base_case_value=110000.0,
            bear_case_value=90000.0,
            spread=30000.0,
        )

        self.assertIn("cap_rate", valuation.to_metrics())
        self.assertIn("base_case_value", scenario.to_metrics())


if __name__ == "__main__":
    unittest.main()

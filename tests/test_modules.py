import unittest

from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.cost_valuation import CostValuationModule
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.town_intelligence import TownIntelligenceModule
from briarwood.schemas import PropertyInput, ScenarioOutput, ValuationOutput
from briarwood.settings import CostValuationSettings


def sample_property() -> PropertyInput:
    return PropertyInput(
        property_id="sample",
        address="17 Cedar Lane",
        town="Brookline",
        state="MA",
        beds=3,
        baths=2.0,
        sqft=1850,
        lot_size=0.11,
        year_built=1958,
        purchase_price=895000,
        taxes=10800,
        insurance=1800,
        estimated_monthly_rent=4200,
        down_payment_percent=0.2,
        interest_rate=0.0675,
        days_on_market=18,
        vacancy_rate=0.04,
        town_population_trend=0.01,
        town_price_trend=0.035,
        school_rating=8.0,
        flood_risk="low",
    )


class ModuleTests(unittest.TestCase):
    def test_all_modules_return_standard_shape(self) -> None:
        property_input = sample_property()
        modules = [
            PropertySnapshotModule(),
            CostValuationModule(),
            BullBaseBearModule(),
            RiskConstraintsModule(),
            TownIntelligenceModule(),
        ]

        for module in modules:
            result = module.run(property_input)
            self.assertIsInstance(result.metrics, dict)
            self.assertIsInstance(result.score, float)
            self.assertIsInstance(result.confidence, float)
            self.assertIsInstance(result.summary, str)

    def test_cost_valuation_returns_underwriting_metrics(self) -> None:
        result = CostValuationModule().run(sample_property())

        self.assertIn("cap_rate", result.metrics)
        self.assertIn("monthly_mortgage_payment", result.metrics)
        self.assertIn("cash_on_cash_return", result.metrics)
        self.assertIsInstance(result.payload, ValuationOutput)
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 100.0)

    def test_cost_valuation_accepts_configurable_settings(self) -> None:
        module = CostValuationModule(
            settings=CostValuationSettings(
                loan_term_years=15,
                default_vacancy_rate=0.08,
            )
        )

        result = module.run(sample_property())

        self.assertIn("monthly_total_cost", result.metrics)
        self.assertIsInstance(result.score, float)

    def test_bull_base_bear_returns_typed_payload(self) -> None:
        result = BullBaseBearModule().run(sample_property())

        self.assertIsInstance(result.payload, ScenarioOutput)
        self.assertIn("base_case_value", result.metrics)


if __name__ == "__main__":
    unittest.main()

import unittest

from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.cost_valuation import CostValuationModule
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.location_intelligence import LocationIntelligenceModule
from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.modules.rental_ease import RentalEaseModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scarcity_support import ScarcitySupportModule
from briarwood.modules.town_county_outlook import TownCountyOutlookModule
from briarwood.schemas import EvidenceMode, PropertyInput, ScenarioOutput, ValuationOutput
from briarwood.settings import CostValuationSettings


def sample_property() -> PropertyInput:
    return PropertyInput(
        property_id="sample",
        address="17 Cedar Lane",
        town="Brookline",
        state="MA",
        county="Norfolk",
        beds=3,
        baths=2.0,
        sqft=1850,
        lot_size=0.11,
        year_built=1958,
        purchase_price=895000,
        taxes=10800,
        insurance=1800,
        monthly_hoa=0.0,
        estimated_monthly_rent=4200,
        down_payment_percent=0.2,
        interest_rate=0.0675,
        loan_term_years=30,
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
            MarketValueHistoryModule(),
            ComparableSalesModule(),
            CurrentValueModule(),
            CostValuationModule(),
            IncomeSupportModule(),
            RentalEaseModule(),
            BullBaseBearModule(),
            RiskConstraintsModule(),
            TownCountyOutlookModule(),
            ScarcitySupportModule(),
            LocationIntelligenceModule(),
            LocalIntelligenceModule(),
        ]

        for module in modules:
            result = module.run(property_input)
            self.assertIsInstance(result.metrics, dict)
            self.assertIsInstance(result.score, float)
            self.assertIsInstance(result.confidence, float)
            self.assertIsInstance(result.summary, str)
            self.assertIsNotNone(result.section_evidence)
            self.assertIn(result.section_evidence.evidence_mode, {EvidenceMode.PUBLIC_RECORD, EvidenceMode.LISTING_ASSISTED, EvidenceMode.MLS_CONNECTED})

    def test_cost_valuation_returns_underwriting_metrics(self) -> None:
        result = CostValuationModule().run(sample_property())

        self.assertIn("cap_rate", result.metrics)
        self.assertIn("monthly_mortgage_payment", result.metrics)
        self.assertIn("effective_monthly_rent", result.metrics)
        self.assertIn("monthly_hoa", result.metrics)
        self.assertIn("monthly_maintenance_reserve", result.metrics)
        self.assertIn("annual_noi", result.metrics)
        self.assertIn("cash_on_cash_return", result.metrics)
        self.assertIsInstance(result.payload, ValuationOutput)
        self.assertIsNotNone(result.metrics["monthly_mortgage_payment"])
        self.assertGreater(result.metrics["monthly_total_cost"], result.metrics["monthly_mortgage_payment"])
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
        self.assertGreaterEqual(result.metrics["bull_case_value"], result.metrics["base_case_value"])
        self.assertGreaterEqual(result.metrics["base_case_value"], result.metrics["bear_case_value"])

    def test_location_modules_return_payloads(self) -> None:
        town_result = TownCountyOutlookModule().run(sample_property())
        scarcity_result = ScarcitySupportModule().run(sample_property())
        location_result = LocationIntelligenceModule().run(sample_property())
        local_result = LocalIntelligenceModule().run(sample_property())

        self.assertIn("town_county_score", town_result.metrics)
        self.assertGreaterEqual(town_result.confidence, 0.0)
        self.assertIn("scarcity_support_score", scarcity_result.metrics)
        self.assertIn("buyer_takeaway", scarcity_result.metrics)
        self.assertIn("location_score", location_result.metrics)
        self.assertIn("geo_peer_comp_count", location_result.metrics)
        self.assertIn("development_activity_score", local_result.metrics)

    def test_market_value_history_module_returns_payload(self) -> None:
        result = MarketValueHistoryModule().run(sample_property())

        self.assertIn("current_value", result.metrics)
        self.assertIn("history_points", result.metrics)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_current_value_module_returns_payload(self) -> None:
        result = CurrentValueModule().run(sample_property())

        self.assertIn("briarwood_current_value", result.metrics)
        self.assertIn("pricing_view", result.metrics)
        self.assertIn("comparable_sales_value", result.metrics)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_comparable_sales_module_returns_payload(self) -> None:
        result = ComparableSalesModule().run(sample_property())

        self.assertIn("comparable_value", result.metrics)
        self.assertIn("comp_count", result.metrics)
        self.assertGreater(result.metrics["comp_count"], 0)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_current_value_confidence_is_capped_when_rent_missing(self) -> None:
        property_input = sample_property()
        property_input.town = "Belmar"
        property_input.state = "NJ"
        property_input.county = "Monmouth"
        property_input.estimated_monthly_rent = None

        result = CurrentValueModule().run(property_input)

        self.assertLessEqual(result.confidence, 0.72)

    def test_income_support_module_returns_payload(self) -> None:
        result = IncomeSupportModule().run(sample_property())

        self.assertIn("income_support_ratio", result.metrics)
        self.assertIn("price_to_rent", result.metrics)
        self.assertIn("downside_burden", result.metrics)
        self.assertIn("support_label", result.metrics)
        self.assertIn("rent_source_type", result.metrics)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_income_support_missing_financing_marks_support_unverified(self) -> None:
        property_input = sample_property()
        property_input.down_payment_percent = None
        property_input.interest_rate = None
        property_input.loan_term_years = None

        result = IncomeSupportModule().run(property_input)

        self.assertFalse(result.metrics["financing_complete"])
        self.assertIsNone(result.metrics["income_support_ratio"])
        self.assertIn("could not be verified", result.summary.lower())

    def test_income_support_estimates_rent_when_supported_by_prior(self) -> None:
        property_input = sample_property()
        property_input.town = "Belmar"
        property_input.state = "NJ"
        property_input.county = "Monmouth"
        property_input.estimated_monthly_rent = None

        result = IncomeSupportModule().run(property_input)

        self.assertEqual(result.metrics["rent_source_type"], "estimated")
        self.assertIsNotNone(result.metrics["effective_monthly_rent"])
        self.assertLess(result.confidence, 0.7)

    def test_income_support_uses_back_house_rent_when_provided(self) -> None:
        baseline_input = sample_property()
        baseline_result = IncomeSupportModule().run(baseline_input)

        property_input = sample_property()
        property_input.back_house_monthly_rent = 1000
        result = IncomeSupportModule().run(property_input)

        self.assertGreater(result.metrics["effective_monthly_rent"], baseline_result.metrics["effective_monthly_rent"])
        self.assertGreater(result.metrics["income_support_ratio"], baseline_result.metrics["income_support_ratio"])

    def test_rental_ease_module_returns_payload(self) -> None:
        result = RentalEaseModule().run(sample_property())

        self.assertIn("rental_ease_score", result.metrics)
        self.assertIn("rental_ease_label", result.metrics)
        self.assertIn("estimated_days_to_rent", result.metrics)
        self.assertGreaterEqual(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()

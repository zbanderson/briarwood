import unittest

from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.cost_valuation import CostValuationModule
from briarwood.modules.current_value import CurrentValueModule
from briarwood.modules.hybrid_value import HybridValueModule
from briarwood.modules.income_support import IncomeSupportModule
from briarwood.modules.location_intelligence import LocationIntelligenceModule
from briarwood.modules.liquidity_signal import LiquiditySignalModule
from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.modules.market_momentum_signal import MarketMomentumSignalModule
from briarwood.modules.market_value_history import MarketValueHistoryModule
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.modules.renovation_scenario import RenovationScenarioModule
from briarwood.modules.rental_ease import RentalEaseModule
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scarcity_support import ScarcitySupportModule
from briarwood.modules.teardown_scenario import TeardownScenarioModule
from briarwood.modules.town_county_outlook import TownCountyOutlookModule
from briarwood.modules.value_drivers import ValueDriversModule
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
            HybridValueModule(),
            CurrentValueModule(),
            CostValuationModule(),
            IncomeSupportModule(),
            RentalEaseModule(),
            LiquiditySignalModule(),
            MarketMomentumSignalModule(),
            BullBaseBearModule(),
            RiskConstraintsModule(),
            TownCountyOutlookModule(),
            ScarcitySupportModule(),
            LocationIntelligenceModule(),
            LocalIntelligenceModule(),
            ValueDriversModule(),
        ]

        for module in modules:
            if module.name == "value_drivers":
                current_value_result = CurrentValueModule().run(property_input)
                income_result = IncomeSupportModule().run(property_input)
                location_result = LocationIntelligenceModule().run(property_input)
                town_result = TownCountyOutlookModule().run(property_input)
                result = module.run(
                    property_input,
                    prior_results={
                        "current_value": current_value_result,
                        "income_support": income_result,
                        "location_intelligence": location_result,
                        "town_county_outlook": town_result,
                    },
                )
            else:
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
        liquidity_result = LiquiditySignalModule().run(sample_property())
        momentum_result = MarketMomentumSignalModule().run(sample_property())
        location_result = LocationIntelligenceModule().run(sample_property())
        local_result = LocalIntelligenceModule().run(sample_property())

        self.assertIn("town_county_score", town_result.metrics)
        self.assertGreaterEqual(town_result.confidence, 0.0)
        self.assertIn("scarcity_support_score", scarcity_result.metrics)
        self.assertIn("buyer_takeaway", scarcity_result.metrics)
        self.assertIn("liquidity_score", liquidity_result.metrics)
        self.assertIn("liquidity_label", liquidity_result.metrics)
        self.assertIn("market_momentum_score", momentum_result.metrics)
        self.assertIn("market_momentum_label", momentum_result.metrics)
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
        self.assertIn("net_opportunity_delta_value", result.metrics)
        self.assertIn("net_opportunity_delta_pct", result.metrics)
        self.assertIn("all_in_basis", result.metrics)
        self.assertIn("blended_value_midpoint", result.metrics)
        self.assertIn("comp_confidence_score", result.metrics)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_hybrid_value_module_decomposes_front_house_and_rear_income(self) -> None:
        property_input = PropertyInput(
            property_id="hybrid-sample",
            address="304 14th Ave",
            town="Belmar",
            state="NJ",
            county="Monmouth",
            beds=5,
            baths=3.0,
            sqft=2250,
            lot_size=0.14,
            year_built=1948,
            property_type="Duplex",
            has_back_house=True,
            adu_type="detached_cottage",
            purchase_price=1_095_000,
            taxes=11_800,
            insurance=2_400,
            estimated_monthly_rent=5_750,
            back_house_monthly_rent=1_950,
            unit_rents=[3_800, 1_950],
            down_payment_percent=0.25,
            interest_rate=0.0675,
            loan_term_years=30,
            days_on_market=29,
            listing_description=(
                "Front house plus detached rear cottage two blocks from the beach. "
                "Flexible multigenerational or guest house setup with strong seasonal demand."
            ),
            vacancy_rate=0.06,
        )

        hybrid_result = HybridValueModule().run(property_input)
        hybrid_payload = hybrid_result.payload

        self.assertIsNotNone(hybrid_payload)
        self.assertTrue(hybrid_payload.is_hybrid)
        self.assertIsNotNone(hybrid_payload.primary_house_value)
        self.assertIsNotNone(hybrid_payload.rear_income_value)
        self.assertGreater(hybrid_payload.base_case_hybrid_value, hybrid_payload.primary_house_value)
        self.assertGreaterEqual(len(hybrid_payload.primary_house_comp_set), 1)
        self.assertIn(hybrid_payload.rear_income_method_used, {"noi_cap_rate", "gross_rent_multiplier", "comp_module_income_cap"})
        self.assertIn("hybrid valuation framework", hybrid_payload.narrative.lower())

        current_value_result = CurrentValueModule().run(property_input)
        self.assertEqual(current_value_result.metrics["valuation_method"], "hybrid")
        self.assertEqual(
            current_value_result.metrics["briarwood_current_value"],
            hybrid_result.metrics["base_case_hybrid_value"],
        )

    def test_comparable_sales_module_returns_payload(self) -> None:
        result = ComparableSalesModule().run(sample_property())

        self.assertIn("comparable_value", result.metrics)
        self.assertIn("comp_count", result.metrics)
        self.assertIn("comp_confidence_score", result.metrics)
        self.assertIn("blended_value_midpoint", result.metrics)
        self.assertGreaterEqual(result.confidence, 0.0)
        payload = result.payload
        self.assertIsNotNone(payload)
        self.assertGreaterEqual(float(payload.comp_confidence_score or 0.0), 0.0)
        if result.metrics["comp_count"] > 0:
            self.assertIsNotNone(payload.direct_value_range)
            self.assertIsNotNone(payload.blended_value_range)
            self.assertTrue(any(getattr(comp, "segmentation_bucket", None) for comp in payload.comps_used))
            self.assertIsNotNone(payload.base_comp_selection)
            assert payload.base_comp_selection is not None
            self.assertEqual(payload.base_comp_selection.support_summary.comp_count, payload.comp_count)
            self.assertGreaterEqual(len(payload.base_comp_selection.selected_comps), 1)
            self.assertIn(payload.base_comp_selection.support_summary.support_quality, {"strong", "moderate", "thin"})
            self.assertIsNotNone(payload.comp_analysis)
            assert payload.comp_analysis is not None
            self.assertIsNotNone(payload.comp_analysis.base_shell_value)
            self.assertIn("beach", payload.comp_analysis.location_adjustments)
            self.assertIn("cross_town_shell_transfer", payload.comp_analysis.town_transfer_adjustments)
            self.assertGreaterEqual(payload.comp_analysis.confidence, 0.0)

    def test_value_drivers_module_builds_bridge_from_base_to_adjusted_value(self) -> None:
        property_input = sample_property()
        current_value_result = CurrentValueModule().run(property_input)
        income_result = IncomeSupportModule().run(property_input)
        location_result = LocationIntelligenceModule().run(property_input)
        town_result = TownCountyOutlookModule().run(property_input)

        result = ValueDriversModule().run(
            property_input,
            prior_results={
                "current_value": current_value_result,
                "income_support": income_result,
                "location_intelligence": location_result,
                "town_county_outlook": town_result,
            },
        )

        self.assertIn("driver_count", result.metrics)
        self.assertGreaterEqual(result.metrics["driver_count"], 1)
        self.assertIsNotNone(result.payload)
        payload = result.payload
        self.assertAlmostEqual(
            payload.base_value + sum(driver.estimated_value_impact for driver in payload.drivers),
            payload.adjusted_value,
            places=2,
        )
        self.assertGreaterEqual(len(payload.bridge), 2)

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

    def test_income_support_respects_partial_owner_occupancy(self) -> None:
        property_input = sample_property()
        property_input.property_type = "Triplex"
        property_input.occupancy_strategy = "owner_occupy_partial"
        property_input.owner_occupied_unit_count = 1
        property_input.estimated_monthly_rent = None
        property_input.unit_rents = [2400, 2200]

        result = IncomeSupportModule().run(property_input)

        self.assertEqual(result.metrics["rent_source_type"], "manual_input")
        self.assertEqual(result.metrics["monthly_rent_estimate"], 4600)
        self.assertEqual(result.metrics["occupancy_strategy"], "owner_occupy_partial")
        self.assertEqual(result.metrics["owner_occupied_unit_count"], 1)
        self.assertIn("Partial owner-occupancy selected", " ".join(result.payload.assumptions))

    def test_renovation_scenario_returns_structured_blocked_payload_when_budget_missing(self) -> None:
        property_input = sample_property()
        property_input.renovation_scenario = {"enabled": True, "renovation_budget": 5_000}

        result = RenovationScenarioModule().run(property_input)

        self.assertFalse(result.metrics["enabled"])
        self.assertEqual(result.metrics["status"], "missing_inputs")
        self.assertIsInstance(result.payload, dict)
        assert isinstance(result.payload, dict)
        self.assertIn("renovation_budget", result.payload["missing_inputs"])

    def test_teardown_scenario_returns_structured_blocked_payload_when_build_inputs_missing(self) -> None:
        property_input = sample_property()
        property_input.teardown_scenario = {"enabled": True, "hold_years": 5}

        result = TeardownScenarioModule().run(property_input)

        self.assertFalse(result.metrics["enabled"])
        self.assertEqual(result.metrics["status"], "missing_inputs")
        self.assertIsInstance(result.payload, dict)
        assert isinstance(result.payload, dict)
        self.assertIn("new_construction_cost", result.payload["missing_inputs"])
        self.assertIn("new_construction_sqft", result.payload["missing_inputs"])

    def test_income_support_uses_manual_unit_rents_when_provided(self) -> None:
        baseline_input = sample_property()
        baseline_result = IncomeSupportModule().run(baseline_input)

        property_input = sample_property()
        property_input.property_type = "Duplex"
        property_input.unit_rents = [2400, 2200]
        property_input.estimated_monthly_rent = 3000

        result = IncomeSupportModule().run(property_input)

        self.assertEqual(result.metrics["rent_source_type"], "manual_input")
        self.assertEqual(result.metrics["monthly_rent_estimate"], 4600)
        self.assertEqual(result.metrics["num_units"], 2)
        self.assertEqual(result.metrics["unit_breakdown"], [2400, 2200])
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

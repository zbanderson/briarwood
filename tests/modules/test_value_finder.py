from __future__ import annotations

import unittest

from briarwood.modules.value_finder import analyze_property_value_finder, analyze_value_finder
from briarwood.modules.hybrid_value import HybridValueOutput
from briarwood.agents.town_county.schemas import SourceFieldStatus, TownCountyInputs, TownCountyNormalizedRecord, TownCountyScore
from briarwood.agents.town_county.service import TownCountyOutlookResult
from briarwood.schemas import AnalysisReport, ModuleResult, PropertyInput


class ValueFinderTests(unittest.TestCase):
    def test_possible_value_when_pricing_is_supported_and_friction_is_moderate(self) -> None:
        output = analyze_value_finder(
            asking_price=900000,
            briarwood_value=990000,
            comp_median=965000,
            comp_low=930000,
            comp_high=1000000,
            days_on_market=24,
            price_cut_count=0,
            total_price_cut_pct=None,
            town_dom_trend=-0.08,
            town_inventory_trend=-0.05,
            subject_price_per_sqft=600,
            cohort_price_per_sqft=655,
            confidence=0.76,
            similar_listing_dom=28,
            relist_count=0,
        )

        self.assertEqual(output.opportunity_signal, "Possible Value")
        self.assertEqual(output.pricing_posture, "Attractive vs Baseline")
        self.assertGreater(output.value_gap_pct or 0, 0)

    def test_watch_for_cut_when_market_friction_is_high_but_pricing_is_not_yet_cheap(self) -> None:
        output = analyze_value_finder(
            asking_price=1000000,
            briarwood_value=1015000,
            comp_median=995000,
            comp_low=950000,
            comp_high=1030000,
            days_on_market=92,
            price_cut_count=1,
            total_price_cut_pct=0.03,
            town_dom_trend=0.12,
            town_inventory_trend=0.10,
            subject_price_per_sqft=720,
            cohort_price_per_sqft=700,
            confidence=0.62,
            similar_listing_dom=45,
            relist_count=0,
        )

        self.assertEqual(output.opportunity_signal, "Watch for Cut")
        self.assertGreaterEqual(output.market_friction_score, 6.5)

    def test_needs_price_reset_when_listing_is_rich_and_market_is_resisting(self) -> None:
        output = analyze_value_finder(
            asking_price=1250000,
            briarwood_value=1080000,
            comp_median=1100000,
            comp_low=1040000,
            comp_high=1130000,
            days_on_market=118,
            price_cut_count=2,
            total_price_cut_pct=0.07,
            town_dom_trend=0.15,
            town_inventory_trend=0.14,
            subject_price_per_sqft=880,
            cohort_price_per_sqft=760,
            confidence=0.71,
            similar_listing_dom=52,
            relist_count=1,
        )

        self.assertEqual(output.opportunity_signal, "Needs Price Reset")
        self.assertEqual(output.pricing_posture, "Rich vs Baseline")
        self.assertGreaterEqual(output.cut_pressure_score, 6.0)

    def test_low_evidence_produces_caution_note(self) -> None:
        output = analyze_value_finder(
            asking_price=700000,
            briarwood_value=None,
            comp_median=None,
            comp_low=None,
            comp_high=None,
            days_on_market=67,
            confidence=0.35,
        )

        self.assertEqual(output.evidence_strength, "low")
        self.assertIn("watchlist signal", output.confidence_note.lower())

    def test_property_value_finder_returns_compact_supported_bullets(self) -> None:
        report = AnalysisReport(
            property_id="vf-test",
            address="304 14th Ave",
            property_input=PropertyInput(
                property_id="vf-test",
                address="304 14th Ave",
                town="Belmar",
                state="NJ",
                county="Monmouth",
                beds=5,
                baths=3.0,
                sqft=2250,
                lot_size=0.14,
                purchase_price=1_095_000,
                has_back_house=True,
                adu_type="detached_cottage",
                back_house_monthly_rent=1_950,
                garage_spaces=2,
                garage_type="detached",
                has_basement=True,
                basement_finished=False,
            ),
            module_results={
                "current_value": ModuleResult(
                    module_name="current_value",
                    metrics={"mispricing_pct": 0.09, "net_opportunity_delta_pct": 0.09},
                    confidence=0.72,
                ),
                "income_support": ModuleResult(
                    module_name="income_support",
                    metrics={"monthly_rent_estimate": 5_750, "num_units": 2},
                    confidence=0.78,
                ),
                "hybrid_value": ModuleResult(
                    module_name="hybrid_value",
                    metrics={"is_hybrid": True},
                    confidence=0.74,
                    payload=HybridValueOutput(
                        is_hybrid=True,
                        reason="rear cottage income matters",
                        detected_primary_structure_type="single_family",
                        detected_accessory_income_type="detached_cottage",
                        primary_house_value=900_000,
                        primary_house_comp_confidence=0.7,
                        rear_income_value=210_000,
                        rear_income_method_used="noi_cap_rate",
                        rear_income_confidence=0.72,
                        optionality_premium_value=15_000,
                        optionality_reason="garage / basement flexibility",
                        optionality_confidence=0.5,
                        base_case_hybrid_value=1_125_000,
                        confidence=0.74,
                    ),
                ),
                "town_county_outlook": ModuleResult(
                    module_name="town_county_outlook",
                    metrics={"town_county_score": 68.0},
                    confidence=0.66,
                    payload=TownCountyOutlookResult(
                        normalized=TownCountyNormalizedRecord(
                            inputs=TownCountyInputs(town="Belmar", state="NJ", county="Monmouth"),
                            field_status=[],
                            missing_inputs=[],
                            warnings=[],
                        ),
                        score=TownCountyScore(
                            town_demand_score=70.0,
                            county_support_score=66.0,
                            market_alignment_score=67.0,
                            town_county_score=68.0,
                            area_sentiment_score=64.0,
                            appreciation_support_view="supported",
                            location_thesis_label="supportive",
                            liquidity_view="normal",
                            confidence=0.66,
                            demand_drivers=["Buyer demand remains durable."],
                            demand_risks=[],
                            missing_inputs=[],
                            assumptions_used=[],
                            unsupported_claims=[],
                            summary="Supportive town backdrop.",
                        ),
                    ),
                ),
                "scarcity_support": ModuleResult(
                    module_name="scarcity_support",
                    metrics={"scarcity_support_score": 66.0, "scarcity_label": "supportive"},
                    confidence=0.58,
                ),
                "market_momentum_signal": ModuleResult(
                    module_name="market_momentum_signal",
                    metrics={"market_momentum_score": 64.0},
                    confidence=0.56,
                ),
            },
        )

        output = analyze_property_value_finder(report)

        self.assertLessEqual(len(output.bullets), 4)
        self.assertTrue(any(item.startswith("Detached cottage income (~$1.9k/mo)") for item in output.bullets))
        self.assertTrue(any("Expansion upside" in item for item in output.bullets))
        self.assertTrue(any("below fair value" in item for item in output.bullets))

    def test_property_value_finder_outputs_fewer_bullets_when_support_is_thin(self) -> None:
        report = AnalysisReport(
            property_id="vf-thin",
            address="1 Test St",
            property_input=PropertyInput(
                property_id="vf-thin",
                address="1 Test St",
                town="Asbury Park",
                state="NJ",
                county="Monmouth",
                beds=3,
                baths=2.0,
                sqft=1400,
                purchase_price=940_000,
            ),
            module_results={
                "current_value": ModuleResult(module_name="current_value", metrics={"mispricing_pct": -0.12}, confidence=0.34),
                "income_support": ModuleResult(module_name="income_support", metrics={}, confidence=0.3),
            },
        )

        output = analyze_property_value_finder(report)

        self.assertLessEqual(len(output.bullets), 1)


if __name__ == "__main__":
    unittest.main()

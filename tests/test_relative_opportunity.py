import unittest

from briarwood.modules.relative_opportunity import RelativeOpportunityModule
from briarwood.schemas import (
    AnalysisReport,
    LocalIntelligenceConfidence,
    LocalIntelligenceOutput,
    LocalIntelligenceScores,
    LocalIntelligenceSummary,
    ModuleResult,
    PropertyInput,
)


def report_for(
    *,
    property_id: str,
    address: str,
    ask: float,
    sqft: int,
    bcv: float,
    base_case: float,
    location_scarcity_score: float,
    local_dev_score: float,
    local_reg_score: float,
    local_supply_score: float,
    capex_lane: str | None = None,
    capex_budget: float | None = None,
) -> AnalysisReport:
    property_input = PropertyInput(
        property_id=property_id,
        address=address,
        town="Belmar",
        state="NJ",
        county="Monmouth",
        beds=3,
        baths=2.0,
        sqft=sqft,
        purchase_price=ask,
        capex_lane=capex_lane,
        repair_capex_budget=capex_budget,
    )
    return AnalysisReport(
        property_id=property_id,
        address=address,
        property_input=property_input,
        module_results={
            "current_value": ModuleResult(
                module_name="current_value",
                metrics={"briarwood_current_value": bcv},
                confidence=0.7,
            ),
            "bull_base_bear": ModuleResult(
                module_name="bull_base_bear",
                metrics={"base_case_value": base_case},
                confidence=0.65,
            ),
            "location_intelligence": ModuleResult(
                module_name="location_intelligence",
                metrics={"scarcity_score": location_scarcity_score},
                confidence=0.62,
            ),
            "local_intelligence": ModuleResult(
                module_name="local_intelligence",
                confidence=0.68,
                payload=LocalIntelligenceOutput(
                    summary=LocalIntelligenceSummary(total_projects=3, total_units=42, approved_projects=2, rejected_projects=1, pending_projects=0),
                    scores=LocalIntelligenceScores(
                        development_activity_score=local_dev_score,
                        supply_pipeline_score=local_supply_score,
                        regulatory_trend_score=local_reg_score,
                        sentiment_score=58.0,
                    ),
                    confidence=LocalIntelligenceConfidence(score=0.68, notes=["Based on 2 documents"]),
                ),
            ),
        },
    )


class RelativeOpportunityTests(unittest.TestCase):
    def test_relative_opportunity_compares_reports(self) -> None:
        report_a = report_for(
            property_id="a",
            address="10 Ocean Ave",
            ask=700000,
            sqft=1400,
            bcv=760000,
            base_case=810000,
            location_scarcity_score=68,
            local_dev_score=72,
            local_reg_score=70,
            local_supply_score=38,
            capex_lane="light",
        )
        report_b = report_for(
            property_id="b",
            address="20 Cedar Ave",
            ask=640000,
            sqft=1300,
            bcv=690000,
            base_case=745000,
            location_scarcity_score=55,
            local_dev_score=60,
            local_reg_score=58,
            local_supply_score=48,
            capex_lane="moderate",
        )

        output = RelativeOpportunityModule().compare([report_a, report_b])

        self.assertEqual(len(output.properties), 2)
        self.assertIsNotNone(output.winner)
        self.assertIsNotNone(output.comparison.best_forward_return)
        self.assertTrue(output.reasoning)
        self.assertGreater(output.confidence.score, 0.0)
        self.assertLessEqual(output.confidence.score, 1.0)


if __name__ == "__main__":
    unittest.main()

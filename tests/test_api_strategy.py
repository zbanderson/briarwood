from __future__ import annotations

import unittest

from briarwood.data_sources.api_strategy import AnalysisRequestContext, ApiStrategy


class ApiStrategyTests(unittest.TestCase):
    def test_endpoint_policy_only_triggers_needed_conditional_calls(self) -> None:
        strategy = ApiStrategy()
        plan = strategy.plan_endpoints(
            AnalysisRequestContext(
                analysis_id="analysis-1",
                missing_rent=True,
                redevelopment_case=False,
                tax_risk_review=True,
                multi_unit_ambiguity=False,
            )
        )
        self.assertEqual(plan["core"], ("property_detail", "assessment_detail", "sale_detail"))
        self.assertEqual(plan["batch"], ("sales_trend", "community_demographics"))
        self.assertEqual(plan["conditional"], ("rental_avm", "assessment_history"))


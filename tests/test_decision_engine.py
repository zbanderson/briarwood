from __future__ import annotations

import unittest

from briarwood.decision_engine import build_decision
from briarwood.schemas import AnalysisReport, ModuleResult, PropertyInput


def _report(*, ask: float, fair_value: float, monthly_carry: float, carry_ratio: float, comp_count: int = 5, current_confidence: float = 0.7) -> AnalysisReport:
    pi = PropertyInput(
        property_id="decision-test",
        address="1 Test St",
        town="Belmar",
        state="NJ",
        county="Monmouth",
        beds=3,
        baths=2.0,
        sqft=1400,
        purchase_price=ask,
    )
    gap = (fair_value - ask) / ask if ask else None
    return AnalysisReport(
        property_id="decision-test",
        address="1 Test St",
        property_input=pi,
        module_results={
            "current_value": ModuleResult(
                module_name="current_value",
                metrics={"mispricing_pct": gap, "briarwood_current_value": fair_value},
                score=60.0,
                confidence=current_confidence,
            ),
            "income_support": ModuleResult(
                module_name="income_support",
                metrics={"monthly_cash_flow": monthly_carry, "income_support_ratio": carry_ratio},
                score=55.0,
                confidence=0.65,
            ),
            "comparable_sales": ModuleResult(
                module_name="comparable_sales",
                metrics={"comp_count": comp_count, "comp_confidence": 0.7 if comp_count >= 5 else 0.2},
                score=50.0,
                confidence=0.7 if comp_count >= 5 else 0.2,
            ),
            "property_data_quality": ModuleResult(
                module_name="property_data_quality",
                metrics={},
                score=50.0,
                confidence=0.6,
            ),
            "town_county_outlook": ModuleResult(
                module_name="town_county_outlook",
                metrics={},
                score=40.0,
                confidence=0.5,
            ),
        },
    )


class DecisionEngineTests(unittest.TestCase):
    def test_buy_when_value_and_carry_are_constructive(self) -> None:
        decision = build_decision(
            _report(ask=750000.0, fair_value=850000.0, monthly_carry=-200.0, carry_ratio=0.93)
        )

        self.assertEqual(decision.recommendation, "BUY")
        self.assertIn("Fair value", decision.primary_reason)

    def test_avoid_when_value_and_carry_are_both_weak(self) -> None:
        decision = build_decision(
            _report(ask=950000.0, fair_value=760000.0, monthly_carry=-3900.0, carry_ratio=0.39)
        )

        self.assertEqual(decision.recommendation, "AVOID")
        self.assertGreaterEqual(len(decision.required_beliefs), 2)

    def test_low_evidence_caps_conviction(self) -> None:
        strong = build_decision(
            _report(ask=750000.0, fair_value=850000.0, monthly_carry=-200.0, carry_ratio=0.93, comp_count=6, current_confidence=0.72)
        )
        thin = build_decision(
            _report(ask=750000.0, fair_value=850000.0, monthly_carry=-200.0, carry_ratio=0.93, comp_count=0, current_confidence=0.32)
        )

        self.assertEqual(strong.recommendation, thin.recommendation)
        self.assertLess(thin.conviction, strong.conviction)


if __name__ == "__main__":
    unittest.main()

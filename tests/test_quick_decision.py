from __future__ import annotations

import unittest

from briarwood.dash_app.quick_decision import QuickDecisionViewModel, build_quick_decision_view
from briarwood.schemas import AnalysisReport, ModuleResult, PropertyInput


def _report(*, ask: float, fair_value: float, monthly_carry: float, carry_ratio: float, comp_count: int = 5, current_confidence: float = 0.7) -> AnalysisReport:
    pi = PropertyInput(
        property_id="test-property",
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
        property_id="test-property",
        address="1 Test St",
        property_input=pi,
        module_results={
            "current_value": ModuleResult(
                module_name="current_value",
                metrics={
                    "briarwood_current_value": fair_value,
                    "mispricing_pct": gap,
                },
                score=60.0,
                confidence=current_confidence,
            ),
            "income_support": ModuleResult(
                module_name="income_support",
                metrics={
                    "monthly_cash_flow": monthly_carry,
                    "income_support_ratio": carry_ratio,
                },
                score=50.0,
                confidence=0.65,
            ),
            "comparable_sales": ModuleResult(
                module_name="comparable_sales",
                metrics={
                    "comp_count": comp_count,
                    "comp_confidence": 0.7 if comp_count >= 5 else 0.2,
                },
                score=55.0,
                confidence=0.7 if comp_count >= 5 else 0.2,
            ),
            "property_data_quality": ModuleResult(
                module_name="property_data_quality",
                metrics={},
                score=55.0,
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


class QuickDecisionTests(unittest.TestCase):
    def test_build_returns_compact_contract(self) -> None:
        vm = build_quick_decision_view(
            _report(ask=750000.0, fair_value=840000.0, monthly_carry=-250.0, carry_ratio=0.92)
        )

        self.assertIsInstance(vm, QuickDecisionViewModel)
        self.assertEqual(vm.recommendation, "BUY")
        self.assertGreaterEqual(vm.conviction, 0.0)
        self.assertLessEqual(vm.conviction, 1.0)
        self.assertTrue(vm.primary_reason)
        self.assertTrue(vm.secondary_reason)
        self.assertEqual([item.name for item in vm.risk_bar], ["Price", "Carry", "Liquidity", "Execution", "Confidence"])
        self.assertGreaterEqual(len(vm.required_beliefs), 1)

    def test_weak_value_and_weak_carry_do_not_produce_positive_call(self) -> None:
        vm = build_quick_decision_view(
            _report(ask=900000.0, fair_value=720000.0, monthly_carry=-3200.0, carry_ratio=0.41)
        )

        self.assertIn(vm.recommendation, {"LEAN PASS", "AVOID"})

    def test_thin_evidence_reduces_conviction(self) -> None:
        strong = build_quick_decision_view(
            _report(ask=750000.0, fair_value=840000.0, monthly_carry=-250.0, carry_ratio=0.92, comp_count=6)
        )
        thin = build_quick_decision_view(
            _report(ask=750000.0, fair_value=840000.0, monthly_carry=-250.0, carry_ratio=0.92, comp_count=0, current_confidence=0.35)
        )

        self.assertEqual(strong.recommendation, thin.recommendation)
        self.assertLess(thin.conviction, strong.conviction)


if __name__ == "__main__":
    unittest.main()

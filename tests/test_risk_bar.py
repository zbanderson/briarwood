from __future__ import annotations

import unittest

from briarwood.risk_bar import build_risk_bar
from briarwood.schemas import AnalysisReport, ModuleResult, PropertyInput


def _report(
    *,
    ask: float,
    fair_value: float,
    monthly_carry: float,
    carry_ratio: float,
    liquidity_score: float,
    comp_count: int,
    overall_confidence: float,
    capex_lane: str = "light",
    capex_basis_source: str = "user_budget",
) -> AnalysisReport:
    property_input = PropertyInput(
        property_id="risk-test",
        address="1 Test St",
        town="Belmar",
        state="NJ",
        county="Monmouth",
        beds=3,
        baths=2.0,
        sqft=1400,
        purchase_price=ask,
        capex_lane=capex_lane,
        down_payment_percent=0.2,
        interest_rate=0.0675,
        loan_term_years=30,
        estimated_monthly_rent=max(monthly_carry + 5500.0, 1500.0),
        taxes=10_000,
        insurance=2_000,
        days_on_market=25,
    )
    gap = (fair_value - ask) / ask if ask else None
    return AnalysisReport(
        property_id="risk-test",
        address="1 Test St",
        property_input=property_input,
        module_results={
            "current_value": ModuleResult(
                module_name="current_value",
                metrics={
                    "briarwood_current_value": fair_value,
                    "mispricing_pct": gap,
                    "net_opportunity_delta_pct": gap,
                    "capex_basis_source": capex_basis_source,
                },
                score=overall_confidence * 100.0,
                confidence=overall_confidence,
            ),
            "income_support": ModuleResult(
                module_name="income_support",
                metrics={
                    "monthly_cash_flow": monthly_carry,
                    "income_support_ratio": carry_ratio,
                    "rent_source_type": "provided",
                    "monthly_rent_estimate": 5_500.0,
                },
                score=55.0,
                confidence=max(0.4, overall_confidence),
            ),
            "liquidity_signal": ModuleResult(
                module_name="liquidity_signal",
                metrics={
                    "liquidity_score": liquidity_score,
                    "comp_count": comp_count,
                    "days_on_market": 25,
                },
                score=liquidity_score,
                confidence=max(0.4, overall_confidence),
            ),
            "comparable_sales": ModuleResult(
                module_name="comparable_sales",
                metrics={
                    "comp_count": comp_count,
                    "comp_confidence": 0.75 if comp_count >= 5 else 0.2,
                },
                score=55.0,
                confidence=0.75 if comp_count >= 5 else 0.2,
            ),
            "property_data_quality": ModuleResult(
                module_name="property_data_quality",
                metrics={},
                score=55.0,
                confidence=overall_confidence,
            ),
            "town_county_outlook": ModuleResult(
                module_name="town_county_outlook",
                metrics={},
                score=45.0,
                confidence=overall_confidence,
            ),
        },
    )


class RiskBarTests(unittest.TestCase):
    def test_builds_fixed_category_contract(self) -> None:
        items = build_risk_bar(
            _report(
                ask=800_000.0,
                fair_value=760_000.0,
                monthly_carry=-1_200.0,
                carry_ratio=0.78,
                liquidity_score=58.0,
                comp_count=3,
                overall_confidence=0.62,
            )
        )

        self.assertEqual([item.name for item in items], ["Price", "Carry", "Liquidity", "Execution", "Confidence"])
        for item in items:
            self.assertGreaterEqual(item.score, 0)
            self.assertLessEqual(item.score, 100)
            self.assertIn(item.level, {"Low", "Medium", "High"})
            self.assertTrue(item.label)

    def test_weak_value_and_carry_push_price_and_carry_risk_high(self) -> None:
        items = build_risk_bar(
            _report(
                ask=950_000.0,
                fair_value=760_000.0,
                monthly_carry=-3_900.0,
                carry_ratio=0.39,
                liquidity_score=44.0,
                comp_count=1,
                overall_confidence=0.48,
                capex_lane="moderate",
                capex_basis_source="inferred_lane",
            )
        )
        mapping = {item.name: item for item in items}

        self.assertEqual(mapping["Price"].level, "High")
        self.assertEqual(mapping["Carry"].level, "High")
        self.assertIn(mapping["Price"].label, {"Premium to fair value", "Tight valuation cushion"})
        self.assertEqual(mapping["Execution"].level, "High")

    def test_thin_support_pushes_confidence_risk_higher(self) -> None:
        strong = {item.name: item for item in build_risk_bar(
            _report(
                ask=800_000.0,
                fair_value=860_000.0,
                monthly_carry=-200.0,
                carry_ratio=0.95,
                liquidity_score=72.0,
                comp_count=6,
                overall_confidence=0.78,
            )
        )}
        thin = {item.name: item for item in build_risk_bar(
            _report(
                ask=800_000.0,
                fair_value=860_000.0,
                monthly_carry=-200.0,
                carry_ratio=0.95,
                liquidity_score=72.0,
                comp_count=0,
                overall_confidence=0.34,
                capex_lane="",
            )
        )}

        self.assertLess(strong["Confidence"].score, thin["Confidence"].score)
        self.assertIn(thin["Confidence"].level, {"Medium", "High"})


if __name__ == "__main__":
    unittest.main()

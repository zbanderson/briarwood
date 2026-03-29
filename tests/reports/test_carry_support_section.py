import unittest

from briarwood.agents.income.schemas import IncomeAgentOutput
from briarwood.agents.rental_ease.schemas import RentalEaseOutput
from briarwood.reports.sections.carry_support_section import build_carry_support_section
from briarwood.schemas import AnalysisReport, ModuleResult


class CarrySupportSectionTests(unittest.TestCase):
    def test_market_absorption_present_but_property_viability_unverified(self) -> None:
        report = _build_report(
            income_output=_income_output_unverified(),
            rental_output=_rental_output_stable(),
            income_score=0.0,
            rental_score=67.8,
        )

        section = build_carry_support_section(report)

        self.assertEqual(section.market_absorption_label, "Stable Rental Profile")
        self.assertEqual(section.rental_viability_label, "Unverified Rental Fallback")
        self.assertIn("looks stable", section.market_absorption_summary.lower())
        self.assertIn("could not be verified", section.rental_viability_summary.lower())
        self.assertIn("is unverified", section.assessment.summary.lower())

    def test_supportive_absorption_and_supportive_viability(self) -> None:
        report = _build_report(
            income_output=_income_output_supported(),
            rental_output=_rental_output_high(),
            income_score=82.0,
            rental_score=84.0,
        )

        section = build_carry_support_section(report)

        self.assertEqual(section.rental_viability_label, "Supported Rental Fallback")
        self.assertIn("financially supportable", section.rental_viability_summary.lower())
        self.assertIn("hold up", section.assessment.summary.lower())

    def test_good_absorption_but_weak_viability_explains_mismatch(self) -> None:
        report = _build_report(
            income_output=_income_output_weak(),
            rental_output=_rental_output_stable(),
            income_score=22.0,
            rental_score=68.0,
        )

        section = build_carry_support_section(report)

        self.assertEqual(section.market_absorption_label, "Stable Rental Profile")
        self.assertEqual(section.rental_viability_label, "Weak Rental Fallback")
        self.assertIn("does not carry well as a rental", section.assessment.summary.lower())

    def test_sparse_inputs_remain_cautious_and_do_not_crash(self) -> None:
        report = _build_report(
            income_output=_income_output_unverified(),
            rental_output=_rental_output_sparse(),
            income_score=0.0,
            rental_score=48.0,
        )

        section = build_carry_support_section(report)

        self.assertEqual(section.estimated_days_to_rent_text, "Unavailable")
        self.assertGreaterEqual(len(section.market_absorption_warnings), 1)
        self.assertIn("too thin", section.estimated_days_to_rent_context.lower())

    def test_days_to_rent_is_contextualized_as_heuristic(self) -> None:
        report = _build_report(
            income_output=_income_output_unverified(),
            rental_output=_rental_output_stable(),
            income_score=0.0,
            rental_score=67.8,
        )

        section = build_carry_support_section(report)

        self.assertEqual(section.estimated_days_to_rent_text, "39 days")
        self.assertIn("heuristic", section.estimated_days_to_rent_context.lower())
        self.assertIn("monmouth priors", section.estimated_days_to_rent_context.lower())


def _build_report(
    *,
    income_output: IncomeAgentOutput,
    rental_output: RentalEaseOutput,
    income_score: float,
    rental_score: float,
) -> AnalysisReport:
    return AnalysisReport(
        property_id="test-property",
        address="1 Main St",
        module_results={
            "income_support": ModuleResult(
                module_name="income_support",
                score=income_score,
                confidence=income_output.confidence,
                summary=income_output.summary,
                payload=income_output,
            ),
            "rental_ease": ModuleResult(
                module_name="rental_ease",
                score=rental_score,
                confidence=rental_output.confidence,
                summary=rental_output.summary,
                payload=rental_output,
            ),
        },
    )


def _income_output_unverified() -> IncomeAgentOutput:
    return IncomeAgentOutput(
        loan_amount=None,
        monthly_principal_interest=None,
        monthly_taxes=523.17,
        monthly_insurance=0.0,
        monthly_hoa=0.0,
        monthly_maintenance_reserve=832.5,
        gross_monthly_cost=4130.67,
        total_monthly_cost=4130.67,
        carrying_cost_complete=False,
        financing_complete=False,
        effective_monthly_rent=None,
        annual_rent=None,
        rent_source_type="missing",
        income_support_ratio=None,
        rent_coverage=None,
        price_to_rent=None,
        estimated_monthly_cash_flow=None,
        monthly_cash_flow=None,
        rent_support_classification="Unavailable",
        price_to_rent_classification="Unavailable",
        downside_burden=None,
        risk_view="weak_support",
        confidence=0.10,
        missing_inputs=["estimated_monthly_rent", "interest_rate"],
        assumptions=["Down payment assumption missing; assuming 0.0%."],
        unsupported_claims=["Property-level rent support could not be measured directly."],
        summary="Rental downside support could not be assessed because rent is missing.",
        score_inputs_complete=False,
        warnings=["Estimated rent is missing."],
        explanation="Property-level fallback support remains incomplete.",
    )


def _income_output_supported() -> IncomeAgentOutput:
    return IncomeAgentOutput(
        loan_amount=650000.0,
        monthly_principal_interest=3900.0,
        monthly_taxes=700.0,
        monthly_insurance=180.0,
        monthly_hoa=0.0,
        monthly_maintenance_reserve=500.0,
        gross_monthly_cost=5280.0,
        total_monthly_cost=5280.0,
        carrying_cost_complete=True,
        financing_complete=True,
        effective_monthly_rent=6100.0,
        annual_rent=73200.0,
        rent_source_type="provided",
        income_support_ratio=1.16,
        rent_coverage=1.16,
        price_to_rent=14.8,
        estimated_monthly_cash_flow=820.0,
        monthly_cash_flow=820.0,
        rent_support_classification="Strong Support",
        price_to_rent_classification="Strong Value",
        downside_burden=None,
        risk_view="strong_support",
        confidence=0.84,
        missing_inputs=[],
        assumptions=["Maintenance reserve uses Briarwood default."],
        unsupported_claims=[],
        summary="Rental support appears strong.",
        score_inputs_complete=True,
        warnings=[],
        explanation="Rent appears to cover carrying cost.",
    )


def _income_output_weak() -> IncomeAgentOutput:
    return IncomeAgentOutput(
        loan_amount=850000.0,
        monthly_principal_interest=5100.0,
        monthly_taxes=900.0,
        monthly_insurance=220.0,
        monthly_hoa=0.0,
        monthly_maintenance_reserve=600.0,
        gross_monthly_cost=6820.0,
        total_monthly_cost=6820.0,
        carrying_cost_complete=True,
        financing_complete=True,
        effective_monthly_rent=4200.0,
        annual_rent=50400.0,
        rent_source_type="provided",
        income_support_ratio=0.62,
        rent_coverage=0.62,
        price_to_rent=21.5,
        estimated_monthly_cash_flow=-2620.0,
        monthly_cash_flow=-2620.0,
        rent_support_classification="Weak Support",
        price_to_rent_classification="Expensive",
        downside_burden=2620.0,
        risk_view="weak_support",
        confidence=0.80,
        missing_inputs=[],
        assumptions=[],
        unsupported_claims=[],
        summary="Property is not supported by rental economics.",
        score_inputs_complete=True,
        warnings=["Rental fallback requires owner subsidy."],
        explanation="Rent falls materially short of carrying cost.",
    )


def _rental_output_stable() -> RentalEaseOutput:
    return RentalEaseOutput(
        rental_ease_score=67.83,
        rental_ease_label="Stable Rental Profile",
        liquidity_score=77.73,
        demand_depth_score=61.74,
        rent_support_score=38.0,
        structural_support_score=72.1,
        estimated_days_to_rent=39,
        summary="Rental absorption appears fairly stable.",
        drivers=["Belmar has a favorable rental liquidity prior within Briarwood's Monmouth scope."],
        risks=["Rent support remains the main constraint."],
        confidence=0.73,
        assumptions=["Town prior informs absorption and seasonality in v1."],
        unsupported_claims=["Property-specific rental comps are not yet sourced."],
        warnings=["Estimated days to rent should be treated as heuristic."],
        zillow_context_used=True,
    )


def _rental_output_high() -> RentalEaseOutput:
    return RentalEaseOutput(
        rental_ease_score=84.0,
        rental_ease_label="High Absorption",
        liquidity_score=86.0,
        demand_depth_score=82.0,
        rent_support_score=79.0,
        structural_support_score=84.0,
        estimated_days_to_rent=24,
        summary="Rental absorption appears favorable.",
        drivers=["Town-level demand depth is healthy."],
        risks=[],
        confidence=0.82,
        assumptions=[],
        unsupported_claims=[],
        warnings=["Estimated days to rent remains a heuristic absorption guide."],
        zillow_context_used=True,
    )


def _rental_output_sparse() -> RentalEaseOutput:
    return RentalEaseOutput(
        rental_ease_score=48.0,
        rental_ease_label="Fragile Rental Profile",
        liquidity_score=45.0,
        demand_depth_score=46.0,
        rent_support_score=35.0,
        structural_support_score=52.0,
        estimated_days_to_rent=None,
        summary="Rental absorption evidence is thin.",
        drivers=[],
        risks=["Signals lean heavily on sparse priors."],
        confidence=0.41,
        assumptions=["Town-level prior used because direct evidence is sparse."],
        unsupported_claims=["Property-specific rental comps are not yet sourced."],
        warnings=["Rental absorption evidence is limited."],
        zillow_context_used=False,
    )


if __name__ == "__main__":
    unittest.main()

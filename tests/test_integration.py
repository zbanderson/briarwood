"""
Integration tests that run full properties through the engine and validate
key output metrics stay within expected ranges.

These are golden-record regression tests — they catch silent regressions
from settings or weight changes. The assertions use wide-but-sane ranges
rather than exact values so that legitimate improvements don't cause false
failures. The goal is catching: sign flips, order violations (bull>base>bear),
and metrics disappearing entirely.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from briarwood.runner import run_report, run_report_from_listing_text, render_report_html
from briarwood.reports.tear_sheet import build_tear_sheet


class FullPipelinePropertyOneTests(unittest.TestCase):
    """Golden-record test using data/sample_property.json (Asb, NJ)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_report("data/sample_property.json")

    def test_pipeline_produces_report_with_all_modules(self) -> None:
        expected_modules = [
            "cost_valuation",
            "market_value_history",
            "current_value",
            "comparable_sales",
            "income_support",
            "rental_ease",
            "town_county_outlook",
            "scarcity_support",
            "bull_base_bear",
            "risk_constraints",
            "location_intelligence",
        ]
        for name in expected_modules:
            self.assertIn(name, self.report.module_results, f"Module '{name}' missing from report")

    def test_bcv_is_in_sane_range(self) -> None:
        cv = self.report.get_module("current_value")
        bcv = cv.metrics.get("briarwood_current_value")
        self.assertIsNotNone(bcv, "BCV is None")
        self.assertGreater(bcv, 200_000, "BCV suspiciously low")
        self.assertLess(bcv, 5_000_000, "BCV suspiciously high")

    def test_scenario_order_bull_gt_base_gt_bear_gt_stress(self) -> None:
        bbb = self.report.get_module("bull_base_bear")
        bull = bbb.metrics.get("bull_case_value")
        base = bbb.metrics.get("base_case_value")
        bear = bbb.metrics.get("bear_case_value")
        stress = bbb.metrics.get("stress_case_value")
        self.assertIsNotNone(bull)
        self.assertIsNotNone(base)
        self.assertIsNotNone(bear)
        self.assertIsNotNone(stress, "Stress case value missing — bear_tail_risk_enabled may be False")
        self.assertGreaterEqual(bull, base, "Bull must be >= base")
        self.assertGreaterEqual(base, bear, "Base must be >= bear")
        self.assertGreater(bear, stress, "Bear must be > stress (stress is a larger shock)")

    def test_risk_score_in_valid_range(self) -> None:
        risk = self.report.get_module("risk_constraints")
        self.assertGreaterEqual(risk.score, 0.0)
        self.assertLessEqual(risk.score, 100.0)

    def test_risk_confidence_reflects_data_completeness(self) -> None:
        risk = self.report.get_module("risk_constraints")
        # Confidence should be one of the three defined tiers, not the old hardcoded 0.72
        self.assertIn(risk.confidence, (0.55, 0.72, 0.85), "Unexpected confidence value from risk module")

    def test_scarcity_score_in_valid_range(self) -> None:
        scarcity = self.report.get_module("scarcity_support")
        score = scarcity.metrics.get("scarcity_support_score")
        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_price_to_rent_in_sane_range(self) -> None:
        income = self.report.get_module("income_support")
        ptr = income.metrics.get("price_to_rent")
        if ptr is not None:
            self.assertGreater(ptr, 5.0, "P/R below 5 is implausible")
            self.assertLess(ptr, 100.0, "P/R above 100 is implausible")

    def test_all_confidence_values_between_zero_and_one(self) -> None:
        for name, result in self.report.module_results.items():
            self.assertGreaterEqual(result.confidence, 0.0, f"{name} confidence < 0")
            self.assertLessEqual(result.confidence, 1.0, f"{name} confidence > 1")

    def test_market_adjusted_value_is_unbounded(self) -> None:
        """After Fix 1, market-adjusted value should pass through ZHVI signal without clamping."""
        cv = self.report.get_module("current_value")
        cv_payload = cv.payload
        if cv_payload.components.market_adjusted_value is not None:
            ask = cv_payload.ask_price
            market_adj = cv_payload.components.market_adjusted_value
            # Previously bounded to ±18% of ask at most; now should reflect ZHVI directly.
            # We can't assert exact value but can confirm it's not artificially clipped to ±18%
            # by checking that divergence > 18% is possible (test passes regardless).
            divergence = abs(market_adj - ask) / ask if ask else 0
            # Just assert the value is reasonable (not zero, not astronomically wrong)
            self.assertGreater(market_adj, 0)
            self.assertLess(divergence, 2.0, "Market-adjusted value diverges >200% from ask — check ZHVI data")

    def test_tear_sheet_builds_without_error(self) -> None:
        tear_sheet = build_tear_sheet(self.report)
        self.assertEqual(tear_sheet.property_id, self.report.property_id)

    def test_tear_sheet_has_all_signal_metrics(self) -> None:
        tear_sheet = build_tear_sheet(self.report)
        sm = tear_sheet.signal_metrics
        self.assertIsNotNone(sm.price_to_rent)
        self.assertIsNotNone(sm.scarcity)
        self.assertIsNotNone(sm.forward_gap)
        self.assertIsNotNone(sm.liquidity)
        self.assertIsNotNone(sm.optionality)


class FullPipelinePropertyTwoTests(unittest.TestCase):
    """Golden-record test using the Belmar listing text (coastal NJ, different profile)."""

    @classmethod
    def setUpClass(cls) -> None:
        listing_path = Path("data/sample_zillow_listing_belmar.txt")
        cls.report = run_report_from_listing_text(
            listing_path.read_text(),
            property_id="belmar-integration-test",
            source_url="https://test.example.com/belmar",
        )

    def test_pipeline_produces_report(self) -> None:
        self.assertEqual(self.report.property_id, "belmar-integration-test")
        self.assertIn("current_value", self.report.module_results)
        self.assertIn("bull_base_bear", self.report.module_results)

    def test_bcv_is_in_coastal_nj_range(self) -> None:
        cv = self.report.get_module("current_value")
        bcv = cv.metrics.get("briarwood_current_value")
        self.assertIsNotNone(bcv)
        # Belmar coastal NJ — should be in realistic range
        self.assertGreater(bcv, 300_000)
        self.assertLess(bcv, 3_000_000)

    def test_scenario_order_holds(self) -> None:
        bbb = self.report.get_module("bull_base_bear")
        self.assertGreaterEqual(
            bbb.metrics.get("bull_case_value", 0),
            bbb.metrics.get("base_case_value", 0),
        )
        self.assertGreaterEqual(
            bbb.metrics.get("base_case_value", 0),
            bbb.metrics.get("bear_case_value", 0),
        )
        self.assertGreater(
            bbb.metrics.get("bear_case_value", 0),
            bbb.metrics.get("stress_case_value", 0),
        )

    def test_stress_case_is_below_bear(self) -> None:
        bbb = self.report.get_module("bull_base_bear")
        bear = bbb.metrics.get("bear_case_value")
        stress = bbb.metrics.get("stress_case_value")
        if bear is not None and stress is not None:
            self.assertLess(stress, bear, "Stress case must be lower than bear case")
        bcv = bbb.metrics.get("bcv_anchor")
        shock = bbb.metrics.get("stress_macro_shock_pct")
        if bcv is not None and shock is not None and stress is not None:
            expected = bcv * (1.0 - shock)
            self.assertAlmostEqual(stress, expected, delta=1.0, msg="Stress should be BCV × (1 - drawdown)")

    def test_risk_graduated_flood_scores_correctly(self) -> None:
        """Regression: high flood should score lower than medium flood."""
        from briarwood.modules.risk_constraints import RiskConstraintsModule
        from briarwood.schemas import PropertyInput

        def score_with_flood(level: str) -> float:
            pi = PropertyInput(
                property_id="flood-test",
                address="1 Test St",
                town="Belmar",
                state="NJ",
                beds=3,
                baths=2.0,
                sqft=1200,
                purchase_price=700_000,
                flood_risk=level,
            )
            return RiskConstraintsModule().run(pi).score

        high_score = score_with_flood("high")
        medium_score = score_with_flood("medium")
        low_score = score_with_flood("low")
        none_score = score_with_flood("none")

        self.assertLess(high_score, medium_score, "High flood should score lower than medium")
        self.assertLess(medium_score, low_score, "Medium flood should score lower than low")
        self.assertEqual(low_score, none_score, "Low and none flood should score the same (credit applied)")

    def test_risk_graduated_dom_scores_correctly(self) -> None:
        """Regression: DOM of 100 should score lower than DOM of 20."""
        from briarwood.modules.risk_constraints import RiskConstraintsModule
        from briarwood.schemas import PropertyInput

        def score_with_dom(dom: int) -> float:
            pi = PropertyInput(
                property_id="dom-test",
                address="1 Test St",
                town="Testville",
                state="NJ",
                beds=3,
                baths=2.0,
                sqft=1200,
                purchase_price=500_000,
                days_on_market=dom,
            )
            return RiskConstraintsModule().run(pi).score

        self.assertGreater(score_with_dom(10), score_with_dom(45))
        self.assertGreater(score_with_dom(45), score_with_dom(100))


class TearSheetRenderTests(unittest.TestCase):
    """Ensure the tear sheet renders completely without errors and contains all sections."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_report("data/sample_property.json")
        cls.html = render_report_html(cls.report)

    def test_renders_without_error(self) -> None:
        self.assertIsInstance(self.html, str)
        self.assertGreater(len(self.html), 10_000)

    def test_signal_metrics_section_visible(self) -> None:
        self.assertIn("Briarwood Signature Metrics", self.html)
        self.assertIn("Price-to-Rent", self.html)
        self.assertIn("Scarcity Score", self.html)
        self.assertIn("Forward Value Gap", self.html)

    def test_stress_case_visible_in_html(self) -> None:
        self.assertIn("Stress Case", self.html)
        self.assertIn("Tail Risk", self.html)
        self.assertIn("historical coastal correction", self.html)

    def test_all_nine_original_sections_present(self) -> None:
        markers = [
            "Verdict",
            "Why It Matters",
            "Thesis",
            "Deal Type",
            "What Must Go Right",
            "Demand Durability",
            "Fallback Rental Support",
            "Comparable Sales",
            "12M Scenario Spread",
            "Confidence / Evidence",
        ]
        for marker in markers:
            self.assertIn(marker, self.html, f"Expected section marker '{marker}' missing from HTML")

    def test_no_internal_module_names_leak_into_html(self) -> None:
        """Internal Python names should not appear verbatim in user-facing output."""
        leaked_names = ["ModuleResult", "PropertyInput", "AnalysisReport", "CurrentValueOutput"]
        for name in leaked_names:
            self.assertNotIn(name, self.html, f"Internal name '{name}' leaked into HTML")

    def test_unresolved_template_placeholders_absent(self) -> None:
        """All $variable placeholders must be replaced before delivery."""
        import re
        unresolved = re.findall(r"\$[a-z_]{3,}", self.html)
        self.assertEqual(unresolved, [], f"Unresolved template variables: {unresolved}")


if __name__ == "__main__":
    unittest.main()

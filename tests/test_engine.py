import unittest
from pathlib import Path

from briarwood.engine import AnalysisEngine
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.runner import format_intake_preview
from briarwood.runner import preview_intake_from_listing_text
from briarwood.runner import render_report_html
from briarwood.runner import run_report
from briarwood.runner import run_report_from_listing_text
from briarwood.runner import validate_property_input
from briarwood.runner import write_report_html
from briarwood.schemas import PropertyInput


class EngineTests(unittest.TestCase):
    def test_engine_runs_single_module(self) -> None:
        engine = AnalysisEngine(modules=[PropertySnapshotModule()])
        property_input = PropertyInput(
            property_id="1",
            address="1 Main St",
            town="Testville",
            state="MA",
            beds=2,
            baths=1.0,
            sqft=1000,
            purchase_price=300000,
        )

        result = engine.run_module("property_snapshot", property_input)

        self.assertEqual(result.module_name, "property_snapshot")
        self.assertIn("price_per_sqft", result.metrics)

    def test_engine_builds_report_for_all_modules(self) -> None:
        engine = AnalysisEngine(modules=[PropertySnapshotModule()])
        property_input = PropertyInput(
            property_id="1",
            address="1 Main St",
            town="Testville",
            state="MA",
            beds=2,
            baths=1.0,
            sqft=1000,
            purchase_price=300000,
        )

        report = engine.run_all(property_input)

        self.assertEqual(report.property_id, "1")
        self.assertEqual(report.address, "1 Main St")
        self.assertIn("property_snapshot", report.module_results)

    def test_engine_rejects_duplicate_module_names(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisEngine(modules=[PropertySnapshotModule(), PropertySnapshotModule()])

    def test_runner_can_build_report_from_property_file(self) -> None:
        report = run_report("data/sample_property.json")

        self.assertTrue(report.property_id)
        self.assertIn("cost_valuation", report.module_results)
        self.assertIn("market_value_history", report.module_results)
        self.assertIn("current_value", report.module_results)
        self.assertIn("comparable_sales", report.module_results)
        self.assertIn("income_support", report.module_results)
        self.assertIn("rental_ease", report.module_results)
        self.assertIn("liquidity_signal", report.module_results)
        self.assertIn("town_county_outlook", report.module_results)
        self.assertIn("scarcity_support", report.module_results)
        self.assertIn("location_intelligence", report.module_results)
        self.assertIn("local_intelligence", report.module_results)
        self.assertIn("market_momentum_signal", report.module_results)

    def test_runner_can_write_tear_sheet_html(self) -> None:
        report = run_report("data/sample_property.json")
        output_path = write_report_html(report, "outputs/test_tear_sheet.html")

        self.assertTrue(Path(output_path).exists())
        self.assertIn("tear_sheet", output_path.name)

    def test_rendered_tear_sheet_includes_forward_chart_and_interpretive_thesis(self) -> None:
        report = run_report("data/sample_property.json")

        html = render_report_html(report)

        self.assertIn("Verdict", html)
        self.assertIn("Why It Matters", html)
        self.assertIn("Should This Work For", html)
        self.assertIn("Thesis", html)
        self.assertIn("Deal Type", html)
        self.assertIn("What Must Go Right", html)
        self.assertIn("What Breaks", html)
        self.assertIn("Value Range", html)
        self.assertIn("12M Scenario Spread", html)
        self.assertIn("Historic Market Value", html)
        self.assertIn("Plotly.newPlot", html)
        self.assertGreaterEqual(html.count("Plotly.newPlot"), 2)
        self.assertIn("Demand Durability", html)
        self.assertIn("Demand Holds Because", html)
        self.assertIn("Demand Weakens If", html)
        self.assertIn("Fallback Rental Support", html)
        self.assertIn("physical", html.lower())
        self.assertIn("strategic", html.lower())
        self.assertIn("Comparable Sales", html)
        self.assertTrue(
            "Why This Is A Comp" in html or "No usable same-town sale comps were available" in html
        )
        self.assertTrue("manual local comp review" in html or "No usable same-town sale comps were available" in html)
        self.assertIn("Market Absorption", html)
        self.assertIn("Property-Level Rental Viability", html)
        self.assertIn("Support Ratio", html)
        self.assertIn("Rental Ease Score", html)
        self.assertIn("Est. Days to Rent", html)
        self.assertIn("Confidence / Evidence", html)
        self.assertIn("Evidence Mode", html)
        self.assertIn("Report Confidence", html)
        self.assertIn("Coverage Highlights", html)
        self.assertIn("Major Missing Inputs", html)
        self.assertIn("Fields Impacting Valuation", html)
        self.assertIn("Additional Descriptive Fields", html)
        self.assertIn("Strongest Evidence", html)
        self.assertIn("Heuristic Flags", html)

    def test_belmar_render_surfaces_location_freshness_and_source_notes(self) -> None:
        with open("data/sample_zillow_listing_belmar.txt") as file_handle:
            listing_text = file_handle.read()

        report = run_report_from_listing_text(
            listing_text,
            property_id="belmar-001",
            source_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?",
        )

        html = render_report_html(report)

        self.assertIn("County macro sentiment is sourced from FRED-backed county series", html)
        self.assertIn("refreshed about every 90 days", html)
        self.assertIn("Listing Assisted", html)

    def test_runner_can_build_report_from_listing_text(self) -> None:
        with open("data/sample_zillow_listing_belmar.txt") as file_handle:
            listing_text = file_handle.read()

        report = run_report_from_listing_text(
            listing_text,
            property_id="belmar-001",
            source_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?",
        )

        self.assertEqual(report.property_id, "belmar-001")
        self.assertIn("cost_valuation", report.module_results)

    def test_validate_property_input_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            validate_property_input(
                PropertyInput(
                    property_id="1",
                    address="1 Main St",
                    town="Testville",
                    state="MA",
                    beds=2,
                    baths=1.0,
                    sqft=1000,
                    purchase_price=-100.0,
                )
            )

    def test_runner_can_format_intake_preview(self) -> None:
        with open("data/sample_zillow_listing_belmar.txt") as file_handle:
            listing_text = file_handle.read()

        intake_result = preview_intake_from_listing_text(
            listing_text,
            source_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?",
        )
        preview_output = format_intake_preview(intake_result, include_raw=True)

        self.assertIn("Briarwood Intake Preview", preview_output)
        self.assertIn("text_intake", preview_output)
        self.assertIn("normalized_property_data", preview_output)
        self.assertIn("raw_extracted_data", preview_output)


if __name__ == "__main__":
    unittest.main()

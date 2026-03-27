import unittest
from pathlib import Path

from briarwood.engine import AnalysisEngine
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.runner import format_intake_preview
from briarwood.runner import preview_intake_from_listing_text
from briarwood.runner import render_report_html
from briarwood.runner import run_report
from briarwood.runner import run_report_from_listing_text
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

    def test_runner_can_build_report_from_property_file(self) -> None:
        report = run_report("data/sample_property.json")

        self.assertEqual(report.property_id, "brookline-001")
        self.assertIn("cost_valuation", report.module_results)
        self.assertIn("market_value_history", report.module_results)
        self.assertIn("town_county_outlook", report.module_results)
        self.assertIn("scarcity_support", report.module_results)

    def test_runner_can_write_tear_sheet_html(self) -> None:
        report = run_report("data/sample_property.json")
        output_path = write_report_html(report, "outputs/test_tear_sheet.html")

        self.assertTrue(Path(output_path).exists())
        self.assertIn("tear_sheet", output_path.name)

    def test_rendered_tear_sheet_includes_forward_chart_and_interpretive_thesis(self) -> None:
        report = run_report("data/sample_property.json")

        html = render_report_html(report)

        self.assertIn("Historic Market Context and Forward Value Range", html)
        self.assertIn("Historic Market Value", html)
        self.assertIn("Plotly.newPlot", html)
        self.assertIn("What this is:", html)
        self.assertIn("So what:", html)
        self.assertIn("Why Buyers Will Still Want This", html)
        self.assertIn("Buyer Takeaway", html)
        self.assertIn("Why Demand May Hold", html)
        self.assertIn("What Could Weaken It", html)

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

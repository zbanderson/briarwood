import unittest

from briarwood.inputs.property_loader import load_property_from_json
from briarwood.inputs.property_loader import (
    load_property_from_listing_intake_result,
    load_property_from_listing_source,
    load_property_from_listing_text,
)
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.runner import run_report_from_listing_text
from briarwood.schemas import EvidenceMode, InputCoverageStatus


class ListingIntakeTests(unittest.TestCase):
    def test_zillow_text_listing_is_normalized(self) -> None:
        service = ListingIntakeService()
        with open("data/sample_zillow_listing.txt") as file_handle:
            source = file_handle.read()

        result = service.intake(source)

        self.assertEqual(result.intake_mode, "text_intake")
        self.assertEqual(result.normalized_property_data.address, "17 Cedar Lane, Brookline, MA 02445")
        self.assertEqual(result.normalized_property_data.price, 895000.0)
        self.assertEqual(result.normalized_property_data.beds, 3)
        self.assertEqual(result.normalized_property_data.baths, 2.0)
        self.assertEqual(result.normalized_property_data.sqft, 1850)
        self.assertEqual(result.normalized_property_data.year_built, 1958)
        self.assertEqual(result.normalized_property_data.county, "Norfolk")
        self.assertEqual(result.normalized_property_data.taxes_annual, 10800.0)
        self.assertAlmostEqual(result.normalized_property_data.price_per_sqft, 483.78, places=2)
        self.assertEqual(len(result.normalized_property_data.tax_history), 2)
        self.assertEqual(len(result.normalized_property_data.price_history), 2)

    def test_listing_intake_result_can_be_loaded_into_property_input(self) -> None:
        service = ListingIntakeService()
        with open("data/sample_zillow_listing.txt") as file_handle:
            source = file_handle.read()

        result = service.intake(source)
        property_input = load_property_from_listing_intake_result(
            result,
            property_id="brookline-listing-001",
        )

        self.assertEqual(property_input.property_id, "brookline-listing-001")
        self.assertEqual(property_input.address, "17 Cedar Lane, Brookline, MA 02445")
        self.assertEqual(property_input.purchase_price, 895000.0)
        self.assertEqual(property_input.sqft, 1850)
        self.assertEqual(property_input.county, "Norfolk")
        self.assertEqual(property_input.taxes, 10800.0)
        self.assertIsNotNone(property_input.source_metadata)
        self.assertEqual(property_input.source_metadata.evidence_mode, EvidenceMode.LISTING_ASSISTED)
        self.assertEqual(property_input.coverage_for("price_ask").status, InputCoverageStatus.SOURCED)

    def test_listing_source_can_be_loaded_directly_into_property_input(self) -> None:
        with open("data/sample_zillow_listing.txt") as file_handle:
            source = file_handle.read()

        property_input = load_property_from_listing_source(
            source,
            property_id="brookline-direct-001",
        )

        self.assertEqual(property_input.property_id, "brookline-direct-001")
        self.assertEqual(property_input.address, "17 Cedar Lane, Brookline, MA 02445")
        self.assertEqual(property_input.purchase_price, 895000.0)
        self.assertEqual(property_input.source_metadata.evidence_mode, EvidenceMode.LISTING_ASSISTED)

    def test_belmar_text_intake_extracts_multiline_fields_and_enrichment(self) -> None:
        service = ListingIntakeService()
        with open("data/sample_zillow_listing_belmar.txt") as file_handle:
            source = file_handle.read()

        result = service.intake_text(
            source,
            source_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?",
        )

        self.assertEqual(result.intake_mode, "text_intake")
        self.assertEqual(result.normalized_property_data.address, "1600 L Street, Belmar, NJ 07719")
        self.assertEqual(result.normalized_property_data.price, 999000.0)
        self.assertEqual(result.normalized_property_data.beds, 3)
        self.assertEqual(result.normalized_property_data.baths, 2.0)
        self.assertEqual(result.normalized_property_data.sqft, None)
        self.assertEqual(result.normalized_property_data.lot_sqft, 5880)
        self.assertEqual(result.normalized_property_data.property_type, "Single Family Residence")
        self.assertEqual(result.normalized_property_data.architectural_style, "Ranch")
        self.assertEqual(result.normalized_property_data.condition_profile, "updated")
        self.assertEqual(result.normalized_property_data.capex_lane, "moderate")
        self.assertEqual(result.normalized_property_data.year_built, 1988)
        self.assertEqual(result.normalized_property_data.stories, 1.0)
        self.assertEqual(result.normalized_property_data.garage_spaces, 1)
        self.assertEqual(result.normalized_property_data.county, "Monmouth")
        self.assertEqual(result.normalized_property_data.days_on_market, 0)
        self.assertEqual(result.normalized_property_data.hoa_monthly, 0.0)
        self.assertEqual(result.normalized_property_data.taxes_annual, 6278.0)
        self.assertEqual(result.normalized_property_data.source_url, "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?")
        self.assertEqual(len(result.normalized_property_data.tax_history), 3)
        self.assertEqual(len(result.normalized_property_data.price_history), 5)
        self.assertIn("sqft", result.missing_fields)
        self.assertIn("price_per_sqft", result.missing_fields)

    def test_listing_text_can_run_through_report_pipeline(self) -> None:
        with open("data/sample_zillow_listing_belmar.txt") as file_handle:
            source = file_handle.read()

        property_input = load_property_from_listing_text(
            source,
            property_id="belmar-001",
            source_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?",
        )
        report = run_report_from_listing_text(
            source,
            property_id="belmar-001",
            source_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?",
        )

        self.assertEqual(property_input.purchase_price, 999000.0)
        self.assertEqual(property_input.county, "Monmouth")
        self.assertEqual(property_input.architectural_style, "Ranch")
        self.assertEqual(property_input.condition_profile, "updated")
        self.assertEqual(property_input.capex_lane, "moderate")
        self.assertEqual(property_input.garage_spaces, 1)
        self.assertTrue(property_input.listing_description)
        self.assertEqual(property_input.source_metadata.evidence_mode, EvidenceMode.LISTING_ASSISTED)
        self.assertEqual(property_input.coverage_for("listing_history").status, InputCoverageStatus.SOURCED)
        self.assertEqual(property_input.coverage_for("market_history").status, InputCoverageStatus.SOURCED)
        self.assertEqual(property_input.coverage_for("school_signal").status, InputCoverageStatus.SOURCED)
        self.assertEqual(property_input.coverage_for("rent_estimate").status, InputCoverageStatus.ESTIMATED)
        self.assertIn(property_input.coverage_for("comp_support").status, {InputCoverageStatus.ESTIMATED, InputCoverageStatus.SOURCED})
        self.assertEqual(report.property_id, "belmar-001")
        self.assertIn("cost_valuation", report.module_results)
        self.assertIn("town_county_outlook", report.module_results)
        self.assertEqual(report.property_input.source_metadata.evidence_mode, EvidenceMode.LISTING_ASSISTED)

    def test_json_loader_infers_listing_assisted_when_listing_fields_are_present(self) -> None:
        property_input = load_property_from_json("data/sample_property.json")

        self.assertEqual(property_input.town, "Asbury Park")
        self.assertEqual(property_input.source_metadata.evidence_mode, EvidenceMode.LISTING_ASSISTED)
        self.assertEqual(property_input.coverage_for("price_ask").status, InputCoverageStatus.SOURCED)
        self.assertEqual(property_input.coverage_for("rent_estimate").status, InputCoverageStatus.USER_SUPPLIED)
        self.assertEqual(property_input.coverage_for("insurance_estimate").status, InputCoverageStatus.USER_SUPPLIED)
        self.assertEqual(property_input.coverage_for("market_history").status, InputCoverageStatus.SOURCED)

    def test_zillow_url_listing_returns_partial_result_with_warning(self) -> None:
        service = ListingIntakeService()
        result = service.intake_url(
            "https://www.zillow.com/homedetails/17-Cedar-Ln-Brookline-MA-02445/123456_zpid/"
        )

        self.assertEqual(result.intake_mode, "url_intake")
        self.assertIsNotNone(result.normalized_property_data.address)
        self.assertIn("price", result.missing_fields)
        self.assertTrue(result.warnings)
        self.assertIn(
            "URL intake is metadata-only in v1; no live page fetching is performed.",
            result.warnings,
        )
        self.assertIn(
            "Provide pasted listing text to extract richer fields like description, HOA, tax history, and price history.",
            result.warnings,
        )


if __name__ == "__main__":
    unittest.main()

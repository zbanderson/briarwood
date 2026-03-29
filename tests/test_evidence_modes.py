import unittest

from briarwood.inputs.adapters import ListingTextAdapter, ManualInputAdapter, PublicRecordAdapter
from briarwood.schemas import EvidenceMode, InputCoverageStatus, PropertyInput


class EvidenceModeTests(unittest.TestCase):
    def test_public_record_adapter_builds_public_record_mode(self) -> None:
        canonical = PublicRecordAdapter().build(
            {
                "property_id": "pr-1",
                "address": "1 Main St",
                "town": "Belmar",
                "state": "NJ",
                "beds": 3,
                "baths": 2.0,
                "sqft": 1200,
                "purchase_price": 650000,
                "taxes": 5000,
            }
        )

        self.assertEqual(canonical.source_metadata.evidence_mode, EvidenceMode.PUBLIC_RECORD)
        self.assertEqual(canonical.source_metadata.source_coverage["price_ask"].status, InputCoverageStatus.SOURCED)
        self.assertEqual(canonical.source_metadata.source_coverage["rent_estimate"].status, InputCoverageStatus.MISSING)

    def test_manual_input_adapter_marks_user_supplied_assumptions(self) -> None:
        canonical = PublicRecordAdapter().build(
            {
                "property_id": "pr-2",
                "address": "1 Main St",
                "town": "Belmar",
                "state": "NJ",
            }
        )
        updated = ManualInputAdapter().apply(
            canonical,
            overrides={
                "estimated_monthly_rent": 2800,
                "insurance": 1400,
                "down_payment_percent": 0.2,
                "interest_rate": 0.0675,
            },
        )

        self.assertEqual(updated.source_metadata.source_coverage["rent_estimate"].status, InputCoverageStatus.USER_SUPPLIED)
        self.assertEqual(updated.source_metadata.source_coverage["insurance_estimate"].status, InputCoverageStatus.USER_SUPPLIED)
        self.assertEqual(updated.source_metadata.source_coverage["financing_interest_rate"].status, InputCoverageStatus.USER_SUPPLIED)

    def test_listing_text_adapter_builds_listing_assisted_mode(self) -> None:
        with open("data/sample_zillow_listing_briarwood_rd_belmar.txt") as file_handle:
            listing_text = file_handle.read()

        canonical = ListingTextAdapter().build(
            listing_text,
            property_id="listing-1",
            source_url="https://www.zillow.com/homedetails/1223-Briarwood-Rd-Belmar-NJ-07719/39225332_zpid/",
        )
        property_input = PropertyInput.from_canonical(canonical)

        self.assertEqual(canonical.source_metadata.evidence_mode, EvidenceMode.LISTING_ASSISTED)
        self.assertEqual(property_input.coverage_for("listing_history").status, InputCoverageStatus.SOURCED)
        self.assertEqual(property_input.coverage_for("insurance_estimate").status, InputCoverageStatus.MISSING)


if __name__ == "__main__":
    unittest.main()

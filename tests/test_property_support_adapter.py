import unittest

from briarwood.inputs.adapters import PublicRecordAdapter
from briarwood.inputs.property_support_adapter import PropertySupportAdapter
from briarwood.schemas import InputCoverageStatus


class PropertySupportAdapterTests(unittest.TestCase):
    def test_property_support_adapter_estimates_rent_and_marks_comp_support(self) -> None:
        canonical = PublicRecordAdapter().build(
            {
                "property_id": "belmar-support-1",
                "address": "1223 Briarwood Rd",
                "town": "Belmar",
                "state": "NJ",
                "county": "Monmouth",
                "beds": 3,
                "baths": 1.0,
                "sqft": 1196,
                "purchase_price": 674200,
            }
        )

        enriched = PropertySupportAdapter().enrich(canonical)

        self.assertIsNotNone(enriched.user_assumptions.estimated_monthly_rent)
        self.assertEqual(enriched.source_metadata.source_coverage["rent_estimate"].status, InputCoverageStatus.ESTIMATED)
        self.assertIn(
            enriched.source_metadata.source_coverage["comp_support"].status,
            {InputCoverageStatus.ESTIMATED, InputCoverageStatus.SOURCED},
        )
        self.assertIn("comp", (enriched.source_metadata.source_coverage["comp_support"].note or "").lower())


if __name__ == "__main__":
    unittest.main()

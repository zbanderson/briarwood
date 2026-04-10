from __future__ import annotations

import unittest

from briarwood.data_quality.property_intelligence import compute_property_tax_quality_intelligence


class PropertyTaxQualityIntelligenceTests(unittest.TestCase):
    def test_computes_flags_scores_and_notes(self) -> None:
        result = compute_property_tax_quality_intelligence(
            property_facts={
                "address": "1223 Briarwood Rd",
                "town": "Belmar",
                "state": "NJ",
                "beds": 4,
                "baths": 2.5,
                "sqft": 2180,
                "property_type": "single_family",
                "purchase_price": 910000,
                "taxes": 12850,
            },
            attom_payload={
                "tax_amount": 12850,
                "tax_year": 2025,
                "assessed_total": 585000,
            },
            municipality_tax_context={
                "effective_tax_rate": 0.01928,
                "equalization_ratio": 88.4,
            },
            comp_quality_status="accepted_with_warnings",
        )
        self.assertTrue(result.property_tax_confirmed_flag)
        self.assertTrue(result.municipality_tax_context_flag)
        self.assertGreaterEqual(result.comp_eligibility_score, 0.0)
        self.assertTrue(result.notes)


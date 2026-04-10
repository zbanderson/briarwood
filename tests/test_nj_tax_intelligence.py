from __future__ import annotations

import unittest
from pathlib import Path

from briarwood.data_sources.nj_tax_intelligence import NJTaxIntelligenceStore, town_tax_context


class NJTaxIntelligenceTests(unittest.TestCase):
    def test_loads_and_indexes_town_tax_rows(self) -> None:
        fixture = Path(__file__).resolve().parent / "fixtures" / "tax" / "nj_tax_sample.csv"
        store = NJTaxIntelligenceStore.load_csv(fixture)
        record = store.get(town="Belmar", county="Monmouth")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.tax_year, 2025)
        self.assertAlmostEqual(record.effective_tax_rate or 0.0, 1.928)
        context = town_tax_context(store, town="Belmar", county="Monmouth")
        self.assertEqual(context["town"], "Belmar")
        self.assertIn("equalization_ratio", context)


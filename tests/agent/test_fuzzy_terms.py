"""Deterministic fuzzy-term resolution.

These tests *intentionally avoid the LLM*. The dictionary + regex passes
must handle common search phrasing on their own.
"""

from __future__ import annotations

import unittest

from briarwood.agent.fuzzy_terms import translate


class FuzzyTermsTests(unittest.TestCase):
    def test_near_the_beach_resolves_to_distance(self) -> None:
        r = translate("close to the beach")
        self.assertIn("max_distance_to_beach_miles", r.filters)
        self.assertEqual(r.filters["max_distance_to_beach_miles"], 0.5)
        self.assertIn("close to the beach", r.matched_phrases)

    def test_walkable_resolves_to_downtown_distance(self) -> None:
        r = translate("walkable")
        self.assertIn("max_distance_to_downtown_miles", r.filters)

    def test_large_lot_resolves_to_lot_filter(self) -> None:
        r = translate("large lot")
        self.assertIn("lot_size_acres_min", r.filters)

    def test_three_beds_parses_exact(self) -> None:
        r = translate("3 bed")
        self.assertEqual(r.filters.get("beds"), 3)

    def test_three_plus_beds_parses_min(self) -> None:
        r = translate("3+ bedrooms")
        self.assertEqual(r.filters.get("beds_min"), 3)

    def test_under_1_5m_parses_price(self) -> None:
        r = translate("under $1.5M")
        self.assertEqual(r.filters.get("max_price"), 1_500_000)

    def test_under_bare_number_assumes_millions(self) -> None:
        r = translate("under 1.5")
        self.assertEqual(r.filters.get("max_price"), 1_500_000)

    def test_within_blocks_parses(self) -> None:
        r = translate("within 6 blocks of the beach")
        self.assertEqual(r.filters.get("within_blocks_of_beach"), 6)

    def test_compound_query(self) -> None:
        r = translate("find me 3-bed properties within 6 blocks of the beach under 1.5M")
        self.assertEqual(r.filters.get("beds"), 3)
        self.assertEqual(r.filters.get("within_blocks_of_beach"), 6)
        self.assertEqual(r.filters.get("max_price"), 1_500_000)

    def test_residual_returned_for_unmatched_text(self) -> None:
        r = translate("3 bed feels like a starter home")
        self.assertEqual(r.filters.get("beds"), 3)
        self.assertIn("starter", r.residual.lower())

    def test_empty_input_returns_no_filters(self) -> None:
        r = translate("")
        self.assertEqual(r.filters, {})

    def test_dictionary_only_produces_known_filter_keys(self) -> None:
        # Every dictionary entry must map to a key the index supports.
        # translate() raises if not; this smoke test walks each entry.
        from briarwood.agent.fuzzy_terms import FUZZY_TERMS
        for phrase in FUZZY_TERMS:
            translate(phrase)  # would raise if unsupported


if __name__ == "__main__":
    unittest.main()

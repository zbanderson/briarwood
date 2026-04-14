"""Listing index + search filter correctness."""

from __future__ import annotations

import unittest

from briarwood.agent.index import IndexedProperty, Index, search


def _sample_index() -> Index:
    return Index(
        properties=[
            IndexedProperty(
                property_id="a",
                address="1 A St",
                town="Avon by the Sea",
                state="NJ",
                latitude=40.19,
                longitude=-74.02,
                beds=3,
                baths=2.0,
                sqft=1800,
                lot_size_acres=0.11,
                year_built=1935,
                ask_price=1_499_000,
                confidence=0.63,
                distance_to_beach_miles=0.35,
                distance_to_downtown_miles=0.4,
                distance_to_train_miles=1.1,
                blocks_to_beach=5.8,
            ),
            IndexedProperty(
                property_id="b",
                address="2 B St",
                town="Belmar",
                state="NJ",
                latitude=40.18,
                longitude=-74.02,
                beds=4,
                baths=3.0,
                sqft=2400,
                lot_size_acres=0.09,
                year_built=1920,
                ask_price=1_900_000,
                confidence=0.72,
                distance_to_beach_miles=0.12,
                distance_to_downtown_miles=0.6,
                distance_to_train_miles=0.4,
                blocks_to_beach=2.0,
            ),
            IndexedProperty(
                property_id="c",
                address="3 C Dr",
                town="Belmar",
                state="NJ",
                latitude=40.17,
                longitude=-74.05,
                beds=3,
                baths=1.5,
                sqft=1400,
                lot_size_acres=0.30,
                year_built=1995,
                ask_price=850_000,
                confidence=0.55,
                distance_to_beach_miles=2.3,
                distance_to_downtown_miles=0.9,
                distance_to_train_miles=0.3,
                blocks_to_beach=38.3,
            ),
        ]
    )


class SearchTests(unittest.TestCase):
    def test_beds_exact_filters(self) -> None:
        idx = _sample_index()
        hits = search({"beds": 3}, idx=idx)
        self.assertEqual({h.property_id for h in hits}, {"a", "c"})

    def test_max_price_filters(self) -> None:
        idx = _sample_index()
        hits = search({"max_price": 1_500_000}, idx=idx)
        self.assertEqual({h.property_id for h in hits}, {"a", "c"})

    def test_within_blocks_of_beach(self) -> None:
        idx = _sample_index()
        hits = search({"within_blocks_of_beach": 6}, idx=idx)
        self.assertEqual({h.property_id for h in hits}, {"a", "b"})

    def test_compound_filter_matches_one(self) -> None:
        idx = _sample_index()
        hits = search(
            {"beds": 3, "within_blocks_of_beach": 6, "max_price": 1_500_000}, idx=idx
        )
        self.assertEqual([h.property_id for h in hits], ["a"])

    def test_lot_size_min_filters(self) -> None:
        idx = _sample_index()
        hits = search({"lot_size_acres_min": 0.25}, idx=idx)
        self.assertEqual({h.property_id for h in hits}, {"c"})

    def test_unknown_filter_raises(self) -> None:
        with self.assertRaises(ValueError):
            search({"bogus_filter": 3}, idx=_sample_index())

    def test_town_filter_is_case_insensitive(self) -> None:
        idx = _sample_index()
        hits = search({"town": "BELMAR", "state": "nj"}, idx=idx)
        self.assertEqual({h.property_id for h in hits}, {"b", "c"})


if __name__ == "__main__":
    unittest.main()

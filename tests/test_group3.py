"""Tests for Group 3: Comp Layer Robustness."""
from __future__ import annotations

import unittest
from pathlib import Path

from briarwood.utils import haversine_miles
from briarwood.agents.comparable_sales import (
    ComparableSalesAgent,
    ComparableSalesRequest,
    ComparableSale,
    FileBackedComparableSalesProvider,
)
from briarwood.decision_model.scoring_config import (
    ComparableSalesSettings,
    DEFAULT_COMPARABLE_SALES_SETTINGS,
)


class HaversineTests(unittest.TestCase):
    def test_same_point_is_zero(self) -> None:
        self.assertAlmostEqual(haversine_miles(40.0, -74.0, 40.0, -74.0), 0.0)

    def test_known_distance(self) -> None:
        # NYC (40.7128, -74.0060) to Philadelphia (39.9526, -75.1652) ≈ 80 miles
        d = haversine_miles(40.7128, -74.0060, 39.9526, -75.1652)
        self.assertAlmostEqual(d, 80.0, delta=5.0)

    def test_short_distance(self) -> None:
        # Two points ~1 mile apart in NJ
        d = haversine_miles(40.1800, -74.0700, 40.1800, -74.0530)
        self.assertGreater(d, 0.5)
        self.assertLess(d, 2.0)


class DistanceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ComparableSalesAgent(
            FileBackedComparableSalesProvider(Path("data/comps/sales_comps.json"))
        )

    def test_nearby_comp_passes_gate(self) -> None:
        request = ComparableSalesRequest(
            town="Belmar", state="NJ", latitude=40.18, longitude=-74.07,
        )
        sale = ComparableSale(
            address="1 Test St", town="Belmar", state="NJ",
            sale_price=500000, sale_date="2025-06-01",
            latitude=40.182, longitude=-74.072,
        )
        passes, reason = self.agent._passes_gate(request, sale)
        self.assertTrue(passes)

    def test_far_comp_rejected(self) -> None:
        request = ComparableSalesRequest(
            town="Belmar", state="NJ", latitude=40.18, longitude=-74.07,
        )
        sale = ComparableSale(
            address="1 Far St", town="Belmar", state="NJ",
            sale_price=500000, sale_date="2025-06-01",
            latitude=40.30, longitude=-74.20,  # ~10+ miles away
        )
        passes, reason = self.agent._passes_gate(request, sale)
        self.assertFalse(passes)
        self.assertEqual(reason, "distance_too_far")

    def test_no_coords_skips_distance_check(self) -> None:
        request = ComparableSalesRequest(town="Belmar", state="NJ")
        sale = ComparableSale(
            address="1 Test St", town="Belmar", state="NJ",
            sale_price=500000, sale_date="2025-06-01",
        )
        passes, _ = self.agent._passes_gate(request, sale)
        self.assertTrue(passes)


class DeduplicationTests(unittest.TestCase):
    def test_duplicate_address_keeps_latest(self) -> None:
        agent = ComparableSalesAgent(
            FileBackedComparableSalesProvider(Path("data/comps/sales_comps.json"))
        )
        request = ComparableSalesRequest(
            town="Belmar", state="NJ",
            sqft=1500, beds=3, baths=2.0,
            manual_sales=[
                {
                    "address": "100 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 400000,
                    "sale_date": "2024-01-15",
                    "sqft": 1500,
                    "beds": 3,
                    "baths": 2.0,
                },
                {
                    "address": "100 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 420000,
                    "sale_date": "2025-06-01",
                    "sqft": 1500,
                    "beds": 3,
                    "baths": 2.0,
                },
            ],
            manual_comp_only=True,
        )
        result = agent.run(request)
        # After dedup, only one comp should survive from the two identical addresses
        addresses = [c.address for c in result.comps_used]
        self.assertEqual(len(set(a.strip().lower() for a in addresses)), len(addresses))


class ComparableSalesSettingsTests(unittest.TestCase):
    def test_defaults_exist(self) -> None:
        s = DEFAULT_COMPARABLE_SALES_SETTINGS
        self.assertEqual(s.max_distance_miles, 5.0)
        self.assertEqual(s.total_adjustment_cap, 0.20)
        self.assertEqual(s.condition_per_rank_delta, 0.04)
        self.assertEqual(s.similarity_floor, 0.30)

    def test_custom_settings(self) -> None:
        s = ComparableSalesSettings(max_distance_miles=10.0, total_adjustment_cap=0.25)
        self.assertEqual(s.max_distance_miles, 10.0)
        self.assertEqual(s.total_adjustment_cap, 0.25)


if __name__ == "__main__":
    unittest.main()

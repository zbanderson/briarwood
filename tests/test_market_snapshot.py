from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from briarwood.data_sources.attom_client import AttomClient
from briarwood.data_sources.nj_tax_intelligence import NJTaxIntelligenceStore
from briarwood.modules.market_snapshot import MarketSnapshotBuilder


class MarketSnapshotTests(unittest.TestCase):
    def test_builds_town_snapshot_from_local_and_external_sources(self) -> None:
        fixture_dir = Path(__file__).resolve().parent / "fixtures"
        demographics = json.loads((fixture_dir / "attom" / "community_demographics.json").read_text())
        permits = json.loads((fixture_dir / "attom" / "building_permits.json").read_text())
        sales_trend = {"salestrend": {"salescounttrend": 0.08, "medsalepricetrend": 0.11}}

        def transport(url, params, headers, timeout):
            if "community" in url:
                return demographics
            if "sale/trend" in url:
                return sales_trend
            if "buildingpermit" in url:
                return permits
            return {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sales_path = root / "sales.json"
            active_path = root / "active.json"
            sales_path.write_text(json.dumps({
                "sales": [
                    {"address": "1 A St", "town": "Belmar", "state": "NJ", "sale_price": 800000},
                    {"address": "2 A St", "town": "Belmar", "state": "NJ", "sale_price": 1000000},
                ]
            }))
            active_path.write_text(json.dumps({
                "listings": [
                    {"address": "3 A St", "town": "Belmar", "state": "NJ", "list_price": 950000}
                ]
            }))
            tax_store = NJTaxIntelligenceStore.load_csv(fixture_dir / "tax" / "nj_tax_sample.csv")
            client = AttomClient(api_key="test", cache_dir=root / "attom-cache", transport=transport)
            builder = MarketSnapshotBuilder(
                attom_client=client,
                tax_store=tax_store,
                sales_path=sales_path,
                active_path=active_path,
                cache_dir=root / "snapshots",
            )
            snapshot = builder.build_snapshot(town="Belmar", county="Monmouth", use_cache=False)

        self.assertEqual(snapshot.town, "Belmar")
        self.assertEqual(snapshot.sale_count, 2)
        self.assertEqual(snapshot.median_sale_price, 900000.0)
        self.assertEqual(snapshot.median_rent, 3085.0)
        self.assertIsNotNone(snapshot.sale_count_trend)
        self.assertAlmostEqual(snapshot.effective_tax_rate or 0.0, 1.928)
        self.assertTrue(snapshot.tax_burden_context)
        self.assertTrue(snapshot.equalization_context)
        self.assertIn("permit", snapshot.permit_activity_summary.lower())

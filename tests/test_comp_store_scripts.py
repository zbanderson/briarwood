from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_comp_store import audit_store
from scripts.backfill_comp_store import backfill_store
from scripts.property_intel_audit_report import build_report
from briarwood.data_sources.attom_client import AttomClient


class CompStoreScriptsTests(unittest.TestCase):
    def test_audit_store_surfaces_auto_fixable_and_bucketed_records(self) -> None:
        payload = {
            "sales": [
                {
                    "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 910000,
                    "sale_date": "2025-03-11",
                },
                {
                    "address": "Beautiful beach opportunity with marina views",
                    "town": "Belmar",
                    "state": "NY",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sales_comps.json"
            path.write_text(json.dumps(payload))
            summary = audit_store(path)
        self.assertIn("auto_fixable_records", summary)
        self.assertIn("records_by_issue_type", summary)
        self.assertEqual(len(summary["rejected_records"]), 1)
        self.assertEqual(len(summary["needs_review_records"]), 1)

    def test_backfill_store_improves_fill_rate_in_dry_run(self) -> None:
        payload = {
            "sales": [
                {
                    "address": "1223 Briarwood Rd",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 910000,
                    "sale_date": "2025-03-11",
                }
            ]
        }
        property_detail = {"property": [{"building": {"rooms": {"beds": 4, "bathstotal": 2.5}, "size": {"universalsize": 2180}}, "summary": {"yearbuilt": 1952, "proptype": "single_family"}, "lot": {"lotsize1": 0.11}, "location": {"latitude": 40.18, "longitude": -74.02}}]}
        assessment_detail = {"property": [{"assessment": {"tax": {"taxamt": 12850}}}]}
        sale_detail = {"property": [{"sale": {"saleshistory": [{"saledate": "2025-03-11", "saleamt": 910000}]}}]}

        def transport(url, params, headers, timeout):
            if "assessment" in url:
                return assessment_detail
            if "/sale/" in url:
                return sale_detail
            return property_detail

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sales_comps.json"
            path.write_text(json.dumps(payload))
            client = AttomClient(api_key="test-key", cache_dir=Path(tmpdir) / "cache", transport=transport)
            summary = backfill_store(path, dry_run=True, max_calls=3, endpoint_selection=["property_detail", "assessment_detail", "sale_detail"], client=client)

        self.assertGreater(summary["fill_rate_improvement"]["beds"], 0.0)
        self.assertGreaterEqual(summary["records_targeted"], 1)
        self.assertIn("fill_counts_by_field", summary)
        self.assertIn("cache_hit_rate_by_endpoint", summary)

    def test_build_report_includes_supported_endpoints_and_next_actions(self) -> None:
        payload = {
            "sales": [
                {
                    "address": "1223 Briarwood Rd",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 910000,
                    "sale_date": "2025-03-11",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            comp_path = Path(tmpdir) / "sales_comps.json"
            comp_path.write_text(json.dumps(payload))
            tax_path = Path(__file__).resolve().parent / "fixtures" / "tax" / "nj_tax_sample.csv"
            report = build_report(comp_store_path=comp_path, tax_csv_path=tax_path, backfill_max_calls=1)
        self.assertIn("attom_supported_endpoints", report)
        self.assertIn("attom_capability_summary", report)
        self.assertIn("provenance_arbitration_status", report)
        self.assertTrue(report["top_next_actions"])

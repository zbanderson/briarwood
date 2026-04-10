from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from briarwood.data_quality.cleanup import cleanup_records


class DataQualityCleanupTests(unittest.TestCase):
    def test_cleanup_normalizes_address_and_labels(self) -> None:
        cleaned, actions = cleanup_records([
            {
                "address": "1223 briarwood rd, belmar, nj 07719",
                "town": "belmar",
                "state": "nj",
                "sale_price": 900000,
                "sale_date": "2025-01-01",
            }
        ])
        self.assertEqual(cleaned[0]["address"], "1223 Briarwood Rd")
        self.assertEqual(cleaned[0]["town"], "Belmar")
        self.assertEqual(cleaned[0]["state"], "NJ")
        self.assertTrue(actions)

    def test_audit_script_reports_issue_counts(self) -> None:
        from scripts.audit_comp_store import audit_store

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sales.json"
            path.write_text(json.dumps({
                "sales": [
                    {"address": "", "town": "Belmar", "state": "NJ", "sale_price": 500000, "sale_date": "2025-01-01"},
                    {"address": "1 Main St, Belmar, NJ 07719", "town": "belmar", "state": "nj", "sale_price": 525000, "sale_date": "2025-02-01"},
                ]
            }))
            summary = audit_store(path)
        self.assertIn("counts_by_issue_type", summary)
        self.assertIn("comp_eligibility_summary", summary)
        self.assertGreaterEqual(summary["record_count"], 2)


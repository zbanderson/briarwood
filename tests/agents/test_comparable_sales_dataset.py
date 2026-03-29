import json
import unittest
from collections import Counter
from pathlib import Path


class ComparableSalesDatasetTests(unittest.TestCase):
    def test_monmouth_seed_dataset_covers_priority_towns(self) -> None:
        payload = json.loads(Path("data/comps/sales_comps.json").read_text())

        self.assertEqual(payload["metadata"]["dataset_name"], "briarwood_monmouth_sales_seed_v2")
        sales = payload["sales"]
        counts = Counter(
            sale["town"]
            for sale in sales
            if sale["state"] == "NJ"
            and sale["town"] in {
                "Avon By The Sea",
                "Belmar",
                "Bradley Beach",
                "Manasquan",
                "Sea Girt",
                "Spring Lake",
            }
        )

        for town in (
            "Avon By The Sea",
            "Belmar",
            "Bradley Beach",
            "Manasquan",
            "Sea Girt",
            "Spring Lake",
        ):
            self.assertGreaterEqual(counts[town], 3, msg=f"{town} should have at least 3 seeded comps")

    def test_seed_rows_have_source_and_review_metadata(self) -> None:
        payload = json.loads(Path("data/comps/sales_comps.json").read_text())

        for sale in payload["sales"]:
            self.assertIn("source_name", sale)
            self.assertIn("source_quality", sale)
            self.assertIn("source_ref", sale)
            self.assertIn("reviewed_at", sale)
            self.assertIn("comp_status", sale)
            self.assertIn("address_verification_status", sale)
            self.assertIn("sale_verification_status", sale)
            self.assertIn("verification_source_type", sale)
            self.assertIn("verification_source_name", sale)
            self.assertIn("verification_source_id", sale)
            self.assertIn("last_verified_by", sale)
            self.assertIn("last_verified_at", sale)
            self.assertIn("verification_notes", sale)
            self.assertIn("location_tags", sale)
            self.assertIn("micro_location_notes", sale)
            self.assertIn("condition_profile", sale)


if __name__ == "__main__":
    unittest.main()

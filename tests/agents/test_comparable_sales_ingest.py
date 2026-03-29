import json
import tempfile
import unittest
from pathlib import Path

from briarwood.agents.comparable_sales.ingest_public_records import (
    load_public_record_rows,
    merge_public_record_verification,
)


class ComparableSalesIngestTests(unittest.TestCase):
    def test_merge_public_record_verification_marks_exact_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "records.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "property_address,municipality,state,sale_price,sale_date,instrument_number",
                        "1620 H Street,Belmar,NJ,905000,2025-08-15,MON-2025-0001",
                        "1208 16th Avenue,Belmar,NJ,880000,2025-06-30,MON-2025-0002",
                    ]
                )
                + "\n"
            )

            comp_dataset = {
                "metadata": {"dataset_name": "test"},
                "sales": [
                    {
                        "address": "1620 H Street",
                        "town": "Belmar",
                        "state": "NJ",
                        "sale_price": 905000,
                        "sale_date": "2025-08-15",
                        "source_name": "manual local comp review",
                        "source_ref": "BELMAR-SEED-001",
                    },
                    {
                        "address": "1406 D Street",
                        "town": "Belmar",
                        "state": "NJ",
                        "sale_price": 950000,
                        "sale_date": "2025-10-20",
                        "source_name": "manual local comp review",
                        "source_ref": "BELMAR-SEED-002",
                    },
                ],
            }

            records = load_public_record_rows(csv_path, default_source_name="Monmouth County public record")
            merged = merge_public_record_verification(
                comp_dataset=comp_dataset,
                public_records=records,
                as_of="2026-03-29",
            )

            matched = merged["sales"][0]
            unmatched = merged["sales"][1]
            self.assertEqual(matched["sale_verification_status"], "public_record_verified")
            self.assertEqual(matched["verification_source_type"], "public_record")
            self.assertEqual(matched["verification_source_name"], "Monmouth County public record")
            self.assertEqual(matched["verification_source_id"], "MON-2025-0001")
            self.assertEqual(matched["last_verified_at"], "2026-03-29")

            self.assertEqual(unmatched["sale_verification_status"], "seeded")
            self.assertEqual(unmatched["verification_source_type"], "manual_review")
            self.assertEqual(unmatched["verification_source_id"], "BELMAR-SEED-002")

            self.assertEqual(merged["metadata"]["public_record_matches"], 1)


if __name__ == "__main__":
    unittest.main()

import csv
import json
import tempfile
import unittest
from pathlib import Path

from briarwood.agents.comparable_sales.import_csv import (
    load_active_listing_rows,
    load_comp_rows,
    merge_active_rows,
    merge_rows,
)


class ImportCsvWorkflowTests(unittest.TestCase):
    def test_load_comp_rows_generates_stable_source_ref_without_explicit_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "comps.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "address",
                        "sale_price",
                        "sale_date",
                        "sqft",
                        "beds",
                        "baths",
                        "lot_size",
                        "year_built",
                        "verification_status",
                        "status",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "address": "304 8th Ave",
                        "sale_price": "810000",
                        "sale_date": "2026-03-15",
                        "sqft": "1400",
                        "beds": "3",
                        "baths": "2",
                        "lot_size": "0.11",
                        "year_built": "1950",
                        "verification_status": "manual",
                        "status": "sold",
                    }
                )

            rows = load_comp_rows(
                csv_path,
                town="Belmar",
                state="NJ",
                source_name="weekly update",
                as_of="2026-04-05",
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].source_ref, "BELMAR-SALE-304-8th-ave-2026-03-15")

    def test_merge_rows_updates_existing_sale_by_source_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            comps_path = Path(temp_dir) / "sales.json"
            comps_path.write_text(json.dumps({"metadata": {}, "sales": []}))

            first = load_comp_rows(
                _write_csv(
                    Path(temp_dir) / "first.csv",
                    [
                        {
                            "address": "304 8th Ave",
                            "sale_price": "810000",
                            "sale_date": "2026-03-15",
                            "sqft": "1400",
                            "beds": "3",
                            "baths": "2",
                            "lot_size": "0.11",
                            "year_built": "1950",
                            "verification_status": "manual",
                            "status": "sold",
                        }
                    ],
                ),
                town="Belmar",
                state="NJ",
                source_name="weekly update",
                as_of="2026-04-05",
            )
            created, updated = merge_rows(
                comps_path=comps_path,
                imported_rows=first,
                dataset_name="weekly_dataset",
                as_of="2026-04-05",
            )
            self.assertEqual((created, updated), (1, 0))

            second = load_comp_rows(
                _write_csv(
                    Path(temp_dir) / "second.csv",
                    [
                        {
                            "address": "304 8th Ave",
                            "sale_price": "825000",
                            "sale_date": "2026-03-15",
                            "sqft": "1400",
                            "beds": "3",
                            "baths": "2",
                            "lot_size": "0.11",
                            "year_built": "1950",
                            "verification_status": "manual",
                            "status": "sold",
                        }
                    ],
                ),
                town="Belmar",
                state="NJ",
                source_name="weekly update",
                as_of="2026-04-12",
            )
            created, updated = merge_rows(
                comps_path=comps_path,
                imported_rows=second,
                dataset_name="weekly_dataset",
                as_of="2026-04-12",
            )
            self.assertEqual((created, updated), (0, 1))

            payload = json.loads(comps_path.read_text())
            self.assertEqual(len(payload["sales"]), 1)
            self.assertEqual(payload["sales"][0]["sale_price"], 825000)
            self.assertEqual(payload["metadata"]["as_of"], "2026-04-12")

    def test_merge_active_rows_updates_existing_listing_by_stable_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            active_path = Path(temp_dir) / "active.json"
            active_path.write_text(json.dumps({"metadata": {}, "listings": []}))

            first = load_active_listing_rows(
                _write_csv(
                    Path(temp_dir) / "active_first.csv",
                    [
                        {
                            "address": "304 8th Ave",
                            "list_price": "899000",
                            "sqft": "1400",
                            "beds": "3",
                            "baths": "2",
                            "lot_size": "0.11",
                            "year_built": "1950",
                            "verification_status": "manual",
                            "status": "active",
                        }
                    ],
                ),
                town="Belmar",
                state="NJ",
                source_name="weekly active update",
            )
            created, updated = merge_active_rows(active_path=active_path, imported_rows=first, as_of="2026-04-05")
            self.assertEqual((created, updated), (1, 0))

            second = load_active_listing_rows(
                _write_csv(
                    Path(temp_dir) / "active_second.csv",
                    [
                        {
                            "address": "304 8th Ave",
                            "list_price": "875000",
                            "sqft": "1400",
                            "beds": "3",
                            "baths": "2",
                            "lot_size": "0.11",
                            "year_built": "1950",
                            "verification_status": "manual",
                            "status": "active",
                        }
                    ],
                ),
                town="Belmar",
                state="NJ",
                source_name="weekly active update",
            )
            created, updated = merge_active_rows(active_path=active_path, imported_rows=second, as_of="2026-04-12")
            self.assertEqual((created, updated), (0, 1))

            payload = json.loads(active_path.read_text())
            self.assertEqual(len(payload["listings"]), 1)
            self.assertEqual(payload["listings"][0]["list_price"], 875000)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    fieldnames = [
        "address",
        "list_price",
        "sale_price",
        "sale_date",
        "sqft",
        "beds",
        "baths",
        "lot_size",
        "year_built",
        "verification_status",
        "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


if __name__ == "__main__":
    unittest.main()

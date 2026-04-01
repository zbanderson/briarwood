import csv
import json
import tempfile
import unittest
from pathlib import Path

from briarwood.agents.comparable_sales.import_csv import (
    append_active_rows,
    append_rows,
    load_active_listing_rows,
    load_comp_rows,
)


class CompImportCsvTests(unittest.TestCase):
    def test_load_comp_rows_validates_strict_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "bad.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["address", "sale_price"])
                writer.writeheader()
                writer.writerow({"address": "1 Main St", "sale_price": "500000"})

            with self.assertRaises(ValueError):
                load_comp_rows(csv_path, town="Belmar", state="NJ", source_name="test import")

    def test_load_and_append_comp_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "comps.csv"
            with csv_path.open("w", newline="") as handle:
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
                        "lat",
                        "lon",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "address": "1 Main St",
                        "sale_price": "500000",
                        "sale_date": "2025-10-01",
                        "sqft": "1000",
                        "beds": "3",
                        "baths": "2",
                        "lot_size": "0.10",
                        "year_built": "1950",
                        "verification_status": "public_record",
                        "lat": "40.18",
                        "lon": "-74.03",
                    }
                )

            dataset_path = Path(temp_dir) / "sales.json"
            dataset_path.write_text(json.dumps({"metadata": {}, "sales": []}))

            rows = load_comp_rows(csv_path, town="Belmar", state="NJ", source_name="test import", as_of="2026-03-31")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].verification_status, "public_record")
            self.assertEqual(rows[0].sale_verification_status, "public_record_verified")

            append_rows(comps_path=dataset_path, imported_rows=rows, dataset_name="test_dataset", as_of="2026-03-31")
            payload = json.loads(dataset_path.read_text())
            self.assertEqual(len(payload["sales"]), 1)
            self.assertEqual(payload["sales"][0]["address"], "1 Main St")
            self.assertEqual(payload["metadata"]["dataset_name"], "test_dataset")

    def test_load_comp_rows_skips_for_sale_rows_and_accepts_blank_lat_lon(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "belmar.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "address",
                        "town",
                        "state",
                        "List Price",
                        "sale price",
                        "sale_date",
                        "sqft",
                        "beds",
                        "baths",
                        "lot_size",
                        "year_built",
                        "verification_status",
                        "status",
                        "lat",
                        "lon",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "address": "1600 L Street",
                        "town": "Belmar",
                        "state": "NJ",
                        "List Price": "999000",
                        "sale price": "N/A",
                        "sale_date": "N/A",
                        "sqft": "1600",
                        "beds": "3",
                        "baths": "2",
                        "lot_size": "0.13",
                        "year_built": "1988",
                        "verification_status": "Verified",
                        "status": "For Sale",
                        "lat": "",
                        "lon": "",
                    }
                )
                writer.writerow(
                    {
                        "address": "200 17th Ave",
                        "town": "Belmar",
                        "state": "NJ",
                        "List Price": "899900",
                        "sale price": "815000",
                        "sale_date": "3/13/26",
                        "sqft": "728",
                        "beds": "2",
                        "baths": "1",
                        "lot_size": "0.069",
                        "year_built": "1940",
                        "verification_status": "Verified",
                        "status": "Sold",
                        "lat": "",
                        "lon": "",
                    }
                )

            rows = load_comp_rows(csv_path, town="Belmar", state="NJ", source_name="draft sheet", as_of="2026-04-01")
            active_rows = load_active_listing_rows(csv_path, town="Belmar", state="NJ", source_name="draft sheet")

            self.assertEqual(len(rows), 1)
            self.assertEqual(len(active_rows), 1)
            self.assertEqual(rows[0].address, "200 17th Ave")
            self.assertEqual(rows[0].verification_status, "manual")
            self.assertIsNone(rows[0].latitude)
            self.assertIsNone(rows[0].longitude)
            self.assertEqual(active_rows[0].address, "1600 L Street")
            self.assertEqual(active_rows[0].listing_status, "for_sale")
            self.assertEqual(active_rows[0].list_price, 999000)

    def test_append_active_rows_persists_active_listing_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            active_path = Path(temp_dir) / "active.json"
            active_path.write_text(json.dumps({"metadata": {}, "listings": []}))

            csv_path = Path(temp_dir) / "active.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "address",
                        "town",
                        "state",
                        "List Price",
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
                        "address": "1200 H Street",
                        "town": "Belmar",
                        "state": "NJ",
                        "List Price": "1150000",
                        "sqft": "2174",
                        "beds": "2",
                        "baths": "2",
                        "lot_size": "0.169",
                        "year_built": "1940",
                        "verification_status": "Verified",
                        "status": "For Sale",
                    }
                )

            active_rows = load_active_listing_rows(csv_path, town="Belmar", state="NJ", source_name="draft sheet")
            count = append_active_rows(active_path=active_path, imported_rows=active_rows, dataset_name="test_active", as_of="2026-04-01")
            self.assertEqual(count, 1)
            payload = json.loads(active_path.read_text())
            self.assertEqual(len(payload["listings"]), 1)
            self.assertEqual(payload["listings"][0]["address"], "1200 H Street")
            self.assertEqual(payload["metadata"]["dataset_name"], "test_active")


if __name__ == "__main__":
    unittest.main()

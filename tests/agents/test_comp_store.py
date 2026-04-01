import json
import tempfile
import unittest
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ActiveListingRecord, ComparableSale
from briarwood.agents.comparable_sales.store import JsonActiveListingStore, JsonComparableSalesStore


class CompStoreTests(unittest.TestCase):
    def test_store_can_append_and_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sales.json"
            path.write_text(json.dumps({"metadata": {}, "sales": []}))
            store = JsonComparableSalesStore(path)

            sale = ComparableSale.model_validate(
                {
                    "address": "1 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 500000,
                    "sale_date": "2025-10-01",
                    "sqft": 1000,
                    "beds": 3,
                    "baths": 2.0,
                    "lot_size": 0.10,
                    "year_built": 1950,
                    "verification_status": "manual",
                    "lat": 40.18,
                    "lon": -74.03,
                    "source_ref": "BELMAR-MANUAL-001",
                }
            )
            store.append(sale)
            self.assertEqual(len(store.load().sales), 1)

            updated = sale.model_copy(update={"sale_price": 525000})
            store.upsert(updated, match_on="source_ref")
            self.assertEqual(len(store.load().sales), 1)
            self.assertEqual(store.load().sales[0].sale_price, 525000)

    def test_active_listing_store_can_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "active.json"
            path.write_text(json.dumps({"metadata": {}, "listings": []}))
            store = JsonActiveListingStore(path)

            listing = ActiveListingRecord.model_validate(
                {
                    "address": "1600 L Street",
                    "town": "Belmar",
                    "state": "NJ",
                    "list_price": 999000,
                    "listing_status": "for_sale",
                }
            )
            store.append(listing)
            self.assertEqual(len(store.load().listings), 1)


if __name__ == "__main__":
    unittest.main()

import unittest

from briarwood.modules.town_aggregation_diagnostics import (
    build_cross_town_comparison_table,
    build_town_calibration_table,
    build_feature_sensitivity_by_town,
    build_town_baseline_metrics,
    get_town_context,
    build_town_premium_index,
    build_town_qa_flags,
    load_normalized_market_records,
    normalize_town_name,
)


class TownAggregationDiagnosticsTests(unittest.TestCase):
    def test_town_aggregation_runs_on_sparse_data(self) -> None:
        records = load_normalized_market_records(
            sales_rows=[
                {
                    "address": "1 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 800000,
                    "sale_date": "2026-01-01",
                    "sqft": 1600,
                    "beds": 3,
                    "baths": 2,
                    "verification_status": "manual",
                }
            ],
            active_rows=[
                {
                    "address": "2 Main St",
                    "town": "Sea Girt",
                    "state": "NJ",
                    "list_price": 1500000,
                    "listing_status": "active",
                    "sqft": 2000,
                    "beds": 4,
                    "baths": 3,
                }
            ],
        )

        summary = build_town_baseline_metrics(records)
        comparison = build_cross_town_comparison_table(summary, records)
        premium = build_town_premium_index(summary, records)
        qa = build_town_qa_flags(summary, records)

        self.assertEqual(set(summary["town"]), {"Belmar", "Sea Girt"})
        self.assertEqual(len(comparison), 2)
        self.assertEqual(len(premium), 2)
        self.assertEqual(len(qa), 2)

    def test_missing_optional_columns_do_not_crash_feature_sensitivity(self) -> None:
        records = load_normalized_market_records(
            sales_rows=[
                {
                    "address": "1 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 800000,
                    "sale_date": "2026-01-01",
                    "sqft": 1600,
                    "beds": 3,
                    "baths": 2,
                    "verification_status": "manual",
                    "condition_profile": "updated",
                }
            ],
            active_rows=[],
        )
        feature_table = build_feature_sensitivity_by_town(records)
        self.assertFalse(feature_table.empty)
        self.assertIn("condition_profile", set(feature_table["feature_name"]))

    def test_region_indexes_are_computed_against_full_dataset_baseline(self) -> None:
        records = load_normalized_market_records(
            sales_rows=[
                {
                    "address": "1 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 800000,
                    "sale_date": "2026-01-01",
                    "sqft": 1600,
                    "beds": 3,
                    "baths": 2,
                    "lot_size": 0.10,
                    "year_built": 1950,
                    "verification_status": "manual",
                    "days_on_market": 30,
                    "list_price": 820000,
                },
                {
                    "address": "2 Main St",
                    "town": "Sea Girt",
                    "state": "NJ",
                    "sale_price": 1600000,
                    "sale_date": "2026-01-02",
                    "sqft": 2000,
                    "beds": 4,
                    "baths": 3,
                    "lot_size": 0.20,
                    "year_built": 1970,
                    "verification_status": "manual",
                    "days_on_market": 20,
                    "list_price": 1650000,
                },
            ],
            active_rows=[],
        )
        summary = build_town_baseline_metrics(records)
        comparison = build_cross_town_comparison_table(summary, records)
        premium = build_town_premium_index(summary, records)

        belmar_comp = comparison[comparison["town"] == "Belmar"].iloc[0]
        sea_girt_comp = comparison[comparison["town"] == "Sea Girt"].iloc[0]
        self.assertLess(belmar_comp["price_vs_region"], 1.0)
        self.assertGreater(sea_girt_comp["price_vs_region"], 1.0)

        belmar_premium = premium[premium["town"] == "Belmar"].iloc[0]
        sea_girt_premium = premium[premium["town"] == "Sea Girt"].iloc[0]
        self.assertLess(belmar_premium["town_price_index"], 100.0)
        self.assertGreater(sea_girt_premium["town_price_index"], 100.0)

    def test_town_name_normalization_collapses_avon_spellings(self) -> None:
        records = load_normalized_market_records(
            sales_rows=[
                {
                    "address": "1 Ocean Ave",
                    "town": "Avon By The Sea",
                    "state": "NJ",
                    "sale_price": 1000000,
                    "sale_date": "2026-01-01",
                    "sqft": 1800,
                    "beds": 3,
                    "baths": 2,
                    "verification_status": "manual",
                }
            ],
            active_rows=[
                {
                    "address": "2 Ocean Ave",
                    "town": "Avon-by-the-sea",
                    "state": "NJ",
                    "list_price": 1200000,
                    "listing_status": "active",
                    "sqft": 1900,
                    "beds": 4,
                    "baths": 3,
                }
            ],
        )
        summary = build_town_baseline_metrics(records)
        self.assertEqual(normalize_town_name("Avon-by-the-sea"), "Avon By The Sea")
        self.assertEqual(normalize_town_name("Avon By The Sea"), "Avon By The Sea")
        self.assertEqual(list(summary["town"]), ["Avon By The Sea"])
        self.assertEqual(int(summary.iloc[0]["listing_count"]), 1)
        self.assertEqual(int(summary.iloc[0]["sold_count"]), 1)

    def test_get_town_context_returns_indexes_and_flags(self) -> None:
        records = load_normalized_market_records(
            sales_rows=[
                {
                    "address": "1 Main St",
                    "town": "Belmar",
                    "sale_price": 800000,
                    "sqft": 1600,
                    "beds": 3,
                    "baths": 2,
                },
                {
                    "address": "2 Main St",
                    "town": "Belmar",
                    "sale_price": 820000,
                    "sqft": 1640,
                    "beds": 3,
                    "baths": 2,
                },
            ],
            active_rows=[
                {
                    "address": "3 Main St",
                    "town": "Belmar",
                    "list_price": 850000,
                    "sqft": 1700,
                    "beds": 3,
                    "baths": 2,
                }
            ],
        )
        summary = build_town_baseline_metrics(records)
        premium = build_town_premium_index(summary, records)
        qa = build_town_qa_flags(summary, records)
        self.assertFalse(premium.empty)
        self.assertFalse(qa.empty)

    def test_town_calibration_table_shows_town_context_reduces_ppsf_residual(self) -> None:
        records = load_normalized_market_records(
            sales_rows=[
                {"address": "1 A St", "town": "Belmar", "sale_price": 800000, "sqft": 1600, "beds": 3, "baths": 2},
                {"address": "2 A St", "town": "Belmar", "sale_price": 840000, "sqft": 1650, "beds": 3, "baths": 2},
                {"address": "1 B St", "town": "Sea Girt", "sale_price": 1600000, "sqft": 2000, "beds": 4, "baths": 3},
                {"address": "2 B St", "town": "Sea Girt", "sale_price": 1700000, "sqft": 2050, "beds": 4, "baths": 3},
            ],
            active_rows=[],
        )
        calibration = build_town_calibration_table(records)
        self.assertEqual(set(calibration["town"]), {"Belmar", "Sea Girt"})
        self.assertTrue((calibration["ppsf_residual_improvement"] >= 0).all())


if __name__ == "__main__":
    unittest.main()

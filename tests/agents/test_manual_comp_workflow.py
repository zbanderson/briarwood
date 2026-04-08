import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briarwood.agents.comparable_sales import ComparableSalesAgent, ComparableSalesRequest, FileBackedComparableSalesProvider
from briarwood.dash_app import data as dash_data


class ManualCompWorkflowTests(unittest.TestCase):
    def test_manual_comp_only_without_comps_returns_limited_support(self) -> None:
        agent = ComparableSalesAgent(FileBackedComparableSalesProvider(Path("does-not-exist.json")))
        result = agent.run(
            ComparableSalesRequest(
                town="Belmar",
                state="NJ",
                manual_comp_only=True,
                manual_sales=[],
            )
        )

        self.assertEqual(result.comp_count, 0)
        self.assertIn("not yet supported by manually entered comparable sales", result.unsupported_claims[0].lower())
        self.assertIn("no manual comps were entered", result.summary.lower())

    def test_manual_comp_only_with_comps_uses_manual_support(self) -> None:
        agent = ComparableSalesAgent(FileBackedComparableSalesProvider(Path("does-not-exist.json")))
        result = agent.run(
            ComparableSalesRequest(
                town="Belmar",
                state="NJ",
                property_type="Single Family Residence",
                beds=3,
                baths=2.0,
                sqft=1400,
                manual_comp_only=True,
                manual_sales=[
                    {
                        "address": "10 A St",
                        "town": "Belmar",
                        "state": "NJ",
                        "sale_price": 700000,
                        "sale_date": "2025-06-01",
                        "beds": 3,
                        "baths": 2.0,
                        "sqft": 1380,
                        "property_type": "Single Family Residence",
                        "address_verification_status": "verified",
                        "sale_verification_status": "seeded",
                        "verification_source_type": "manual_review",
                    },
                    {
                        "address": "12 A St",
                        "town": "Belmar",
                        "state": "NJ",
                        "sale_price": 715000,
                        "sale_date": "2025-07-01",
                        "beds": 3,
                        "baths": 2.0,
                        "sqft": 1420,
                        "property_type": "Single Family Residence",
                        "address_verification_status": "verified",
                        "sale_verification_status": "seeded",
                        "verification_source_type": "manual_review",
                    },
                    {
                        "address": "14 A St",
                        "town": "Belmar",
                        "state": "NJ",
                        "sale_price": 720000,
                        "sale_date": "2025-08-01",
                        "beds": 3,
                        "baths": 2.0,
                        "sqft": 1450,
                        "property_type": "Single Family Residence",
                        "address_verification_status": "verified",
                        "sale_verification_status": "seeded",
                        "verification_source_type": "manual_review",
                    },
                ],
            )
        )

        self.assertGreaterEqual(result.comp_count, 3)
        self.assertIsNotNone(result.comparable_value)
        self.assertIn("manually entered comparable sales", result.summary.lower())
        self.assertGreater(result.confidence, 0)

    def test_register_manual_analysis_persists_json_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_saved_dir = dash_data.SAVED_PROPERTY_DIR
            dash_data.SAVED_PROPERTY_DIR = Path(temp_dir)
            try:
                property_id, output_path = dash_data.register_manual_analysis(
                    {
                        "address": "1 Test Lane, Belmar, NJ 07719",
                        "town": "Belmar",
                        "state": "NJ",
                        "county": "Monmouth",
                        "purchase_price": 650000,
                        "beds": 3,
                    },
                    [
                        {
                            "address": "2 Test Lane",
                            "town": "Belmar",
                            "state": "NJ",
                            "sale_price": 640000,
                            "sale_date": "2025-05-01",
                            "address_verification_status": "verified",
                            "sale_verification_status": "seeded",
                            "verification_source_type": "manual_review",
                        }
                    ],
                )
                self.assertTrue(output_path.exists())
                self.assertTrue(property_id)
                saved_dir = dash_data.SAVED_PROPERTY_DIR / property_id
                self.assertTrue((saved_dir / "inputs.json").exists())
                # C1 (audit 2026-04-08): pickle-based report cache removed
                # to close an RCE vector. Reports now rehydrate from
                # inputs.json via run_report() instead.
                self.assertTrue((saved_dir / "summary.json").exists())
            finally:
                dash_data.SAVED_PROPERTY_DIR = original_saved_dir

    def test_load_reports_includes_registered_manual_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_saved_dir = dash_data.SAVED_PROPERTY_DIR
            dash_data.SAVED_PROPERTY_DIR = Path(temp_dir)
            try:
                property_id, _output_path = dash_data.register_manual_analysis(
                    {
                        "address": "1302 L Street, Belmar, NJ 07719",
                        "town": "Belmar",
                        "state": "NJ",
                        "county": "Monmouth",
                        "purchase_price": 625000,
                        "beds": 3,
                        "baths": 2.0,
                    },
                    [],
                )

                reports = dash_data.load_reports([property_id])

                self.assertIn(property_id, reports)
                self.assertEqual(reports[property_id].property_id, property_id)
                self.assertEqual(reports[property_id].address, "1302 L Street, Belmar, NJ 07719")
            finally:
                dash_data.SAVED_PROPERTY_DIR = original_saved_dir

    def test_register_manual_analysis_persists_unit_rents_and_uses_manual_income_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_saved_dir = dash_data.SAVED_PROPERTY_DIR
            dash_data.SAVED_PROPERTY_DIR = Path(temp_dir)
            try:
                property_id, _output_path = dash_data.register_manual_analysis(
                    {
                        "address": "88 12th Ave, Belmar, NJ 07719",
                        "town": "Belmar",
                        "state": "NJ",
                        "county": "Monmouth",
                        "property_type": "Duplex",
                        "purchase_price": 980000,
                        "beds": 5,
                        "baths": 3.0,
                        "unit_rents": [2600, 2400],
                        "insurance": 2400,
                        "taxes": 12000,
                    },
                    [],
                )

                reports = dash_data.load_reports([property_id])
                report = reports[property_id]
                income = report.get_module("income_support")

                self.assertEqual(income.metrics["rent_source_type"], "manual_input")
                self.assertEqual(income.metrics["monthly_rent_estimate"], 5000)
                saved_payload = (dash_data.SAVED_PROPERTY_DIR / property_id / "inputs.json").read_text()
                self.assertIn('"unit_rents": [', saved_payload)
            finally:
                dash_data.SAVED_PROPERTY_DIR = original_saved_dir

    def test_register_manual_analysis_persists_partial_owner_occupancy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_saved_dir = dash_data.SAVED_PROPERTY_DIR
            dash_data.SAVED_PROPERTY_DIR = Path(temp_dir)
            try:
                property_id, _output_path = dash_data.register_manual_analysis(
                    {
                        "address": "1214 Main St, Belmar, NJ 07719",
                        "town": "Belmar",
                        "state": "NJ",
                        "county": "Monmouth",
                        "property_type": "Triplex",
                        "purchase_price": 995000,
                        "beds": 5,
                        "baths": 3.0,
                        "occupancy_strategy": "owner_occupy_partial",
                        "owner_occupied_unit_count": 1,
                        "unit_rents": [2400, 2200],
                        "insurance": 2400,
                        "taxes": 12000,
                    },
                    [],
                )

                reports = dash_data.load_reports([property_id])
                report = reports[property_id]
                income = report.get_module("income_support")

                self.assertEqual(report.property_input.occupancy_strategy, "owner_occupy_partial")
                self.assertEqual(report.property_input.owner_occupied_unit_count, 1)
                self.assertEqual(income.metrics["occupancy_strategy"], "owner_occupy_partial")
                saved_payload = (dash_data.SAVED_PROPERTY_DIR / property_id / "inputs.json").read_text()
                self.assertIn('"occupancy_strategy": "owner_occupy_partial"', saved_payload)
            finally:
                dash_data.SAVED_PROPERTY_DIR = original_saved_dir

    def test_register_manual_analysis_persists_subject_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_saved_dir = dash_data.SAVED_PROPERTY_DIR
            dash_data.SAVED_PROPERTY_DIR = Path(temp_dir)
            try:
                property_id, _output_path = dash_data.register_manual_analysis(
                    {
                        "address": "99 Ocean Ave, Belmar, NJ 07719",
                        "town": "Belmar",
                        "state": "NJ",
                        "county": "Monmouth",
                        "purchase_price": 910000,
                        "beds": 3,
                        "baths": 2.0,
                        "latitude": 40.1781,
                        "longitude": -74.0214,
                    },
                    [],
                )

                reports = dash_data.load_reports([property_id])
                report = reports[property_id]

                self.assertEqual(report.property_input.latitude, 40.1781)
                self.assertEqual(report.property_input.longitude, -74.0214)
                saved_payload = (dash_data.SAVED_PROPERTY_DIR / property_id / "inputs.json").read_text()
                self.assertIn('"latitude": 40.1781', saved_payload)
                self.assertIn('"longitude": -74.0214', saved_payload)
            finally:
                dash_data.SAVED_PROPERTY_DIR = original_saved_dir

    def test_register_manual_analysis_geocodes_by_default_when_coordinates_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_saved_dir = dash_data.SAVED_PROPERTY_DIR
            dash_data.SAVED_PROPERTY_DIR = Path(temp_dir)
            try:
                with patch.object(dash_data, "geocode_address", return_value=(40.1781, -74.0214)) as mocked_geocode:
                    property_id, _output_path = dash_data.register_manual_analysis(
                        {
                            "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                            "town": "Belmar",
                            "state": "NJ",
                            "county": "Monmouth",
                            "purchase_price": 910000,
                            "beds": 3,
                            "baths": 2.0,
                        },
                        [],
                    )

                report = dash_data.load_reports([property_id])[property_id]
                mocked_geocode.assert_called_once()
                self.assertEqual(report.property_input.latitude, 40.1781)
                self.assertEqual(report.property_input.longitude, -74.0214)
            finally:
                dash_data.SAVED_PROPERTY_DIR = original_saved_dir

    def test_saved_property_summary_lists_recent_manual_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_saved_dir = dash_data.SAVED_PROPERTY_DIR
            dash_data.SAVED_PROPERTY_DIR = Path(temp_dir)
            try:
                property_id, _output_path = dash_data.register_manual_analysis(
                    {
                        "address": "9 Ocean Ave, Belmar, NJ 07719",
                        "town": "Belmar",
                        "state": "NJ",
                        "county": "Monmouth",
                        "purchase_price": 710000,
                        "beds": 3,
                        "garage_spaces": 1,
                        "has_pool": False,
                        "monthly_hoa": 150,
                    },
                    [],
                )

                summaries = dash_data.list_saved_properties()

                self.assertEqual(len(summaries), 1)
                self.assertEqual(summaries[0].property_id, property_id)
                self.assertIn("Ocean Ave", summaries[0].address)
                self.assertTrue(summaries[0].tear_sheet_path.exists())
            finally:
                dash_data.SAVED_PROPERTY_DIR = original_saved_dir


if __name__ == "__main__":
    unittest.main()

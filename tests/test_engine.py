import unittest

from briarwood.engine import AnalysisEngine
from briarwood.modules.property_snapshot import PropertySnapshotModule
from briarwood.runner_common import validate_property_input
from briarwood.schemas import PropertyInput


class EngineTests(unittest.TestCase):
    def test_engine_runs_single_module(self) -> None:
        engine = AnalysisEngine(modules=[PropertySnapshotModule()])
        property_input = PropertyInput(
            property_id="1",
            address="1 Main St",
            town="Testville",
            state="MA",
            beds=2,
            baths=1.0,
            sqft=1000,
            purchase_price=300000,
        )

        result = engine.run_module("property_snapshot", property_input)

        self.assertEqual(result.module_name, "property_snapshot")
        self.assertIn("price_per_sqft", result.metrics)

    def test_engine_builds_report_for_all_modules(self) -> None:
        engine = AnalysisEngine(modules=[PropertySnapshotModule()])
        property_input = PropertyInput(
            property_id="1",
            address="1 Main St",
            town="Testville",
            state="MA",
            beds=2,
            baths=1.0,
            sqft=1000,
            purchase_price=300000,
        )

        report = engine.run_all(property_input)

        self.assertEqual(report.property_id, "1")
        self.assertEqual(report.address, "1 Main St")
        self.assertIn("property_snapshot", report.module_results)

    def test_engine_rejects_duplicate_module_names(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisEngine(modules=[PropertySnapshotModule(), PropertySnapshotModule()])

    def test_validate_property_input_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            validate_property_input(
                PropertyInput(
                    property_id="1",
                    address="1 Main St",
                    town="Testville",
                    state="MA",
                    beds=2,
                    baths=1.0,
                    sqft=1000,
                    purchase_price=-100.0,
                )
            )


if __name__ == "__main__":
    unittest.main()

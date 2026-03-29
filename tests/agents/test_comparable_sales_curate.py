import json
import tempfile
import unittest
from pathlib import Path

from briarwood.agents.comparable_sales.curate import append_comp, write_template


class ComparableSalesCurateTests(unittest.TestCase):
    def test_write_template_and_append_comp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            template_path = temp_path / "comp.json"
            dataset_path = temp_path / "sales_comps.json"
            dataset_path.write_text(json.dumps({"metadata": {"dataset_name": "test"}, "sales": []}))

            write_template(template_path)
            payload = json.loads(template_path.read_text())
            payload["address"] = "10 Example Ave"
            payload["town"] = "Belmar"
            payload["state"] = "NJ"
            payload["source_ref"] = "BELMAR-MANUAL-123"
            template_path.write_text(json.dumps(payload))

            comp = append_comp(comps_path=dataset_path, input_path=template_path)
            self.assertEqual(comp.address, "10 Example Ave")
            merged = json.loads(dataset_path.read_text())
            self.assertEqual(len(merged["sales"]), 1)
            self.assertEqual(merged["sales"][0]["condition_profile"], "maintained")
            self.assertEqual(merged["sales"][0]["capex_lane"], "moderate")


if __name__ == "__main__":
    unittest.main()

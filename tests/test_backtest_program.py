from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from briarwood.eval.backtest_program import run_backtest_program


class BacktestProgramTests(unittest.TestCase):
    def test_backtest_program_emits_metrics_and_dataset_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = root / "saved_properties"
            saved.mkdir()
            case_dir = saved / "sample-property"
            case_dir.mkdir()
            (case_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "property_id": "sample-property",
                        "address": "1 Test St",
                        "ask_price": 500000,
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "inputs.json").write_text(
                json.dumps(
                    {
                        "facts": {
                            "purchase_price": 500000,
                            "sale_history": [{"sale_price": 490000}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            gold = root / "gold.json"
            gold.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "property_id": "sample-property",
                                "investor_grades": [
                                    {"investor": "a", "grade": "buy"},
                                    {"investor": "b", "grade": "buy"},
                                    {"investor": "c", "grade": "mixed"},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = run_backtest_program(
                saved_properties_dir=saved,
                feedback_path=root / "missing.jsonl",
                gold_standard_path=gold,
                property_ids=["sample-property"],
                analyze_fn=lambda _pid: {
                    "confidence": 0.72,
                    "decision": "buy",
                    "value_position": {"fair_value_base": 495000},
                },
            )

            self.assertIn("metrics", report)
            self.assertIn("dataset_health", report)
            self.assertEqual(report["dataset_health"]["cases_with_actual_sale_price"], 1)
            self.assertEqual(report["metrics"]["recommendation_hit_rate"], 1.0)
            self.assertIsNotNone(report["metrics"]["valuation_mae"])


if __name__ == "__main__":
    unittest.main()

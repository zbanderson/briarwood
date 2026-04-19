"""Tests for the opportunity_x_value bridge.

The bridge converts opportunity_cost's raw bps delta into a directional
signal (value_driver / risk / neutral) that the synthesizer consumes via
``_key_value_drivers`` and ``_key_risks``.
"""

from __future__ import annotations

import unittest

from briarwood.interactions import opportunity_x_value


def _opportunity_payload(
    *,
    dominant_excess_bps: float,
    dominant_benchmark: str = "sp500",
    hold_years: int = 5,
    property_cagr: float = 0.08,
    threshold: float = 150.0,
    confidence: float = 0.6,
) -> dict:
    return {
        "data": {
            "module_name": "opportunity_cost",
            "summary": "t",
            "metrics": {
                "dominant_excess_bps": dominant_excess_bps,
                "dominant_benchmark": dominant_benchmark,
                "dominant_delta_value": 12_345.0,
                "hold_years": hold_years,
                "property_cagr": property_cagr,
                "meaningful_excess_bps_threshold": threshold,
            },
        },
        "confidence": confidence,
        "assumptions_used": {},
        "warnings": [],
        "mode": "full",
    }


class OpportunityXValueBridgeTests(unittest.TestCase):
    def test_missing_module_does_not_fire(self) -> None:
        record = opportunity_x_value.run({})
        self.assertFalse(record.fired)
        self.assertIn("missing", record.reasoning[0].lower())

    def test_thin_metrics_does_not_fire(self) -> None:
        broken = {
            "opportunity_cost": {
                "data": {"metrics": {}},
                "confidence": 0.4,
            }
        }
        record = opportunity_x_value.run(broken)
        self.assertFalse(record.fired)

    def test_beats_benchmark_emits_value_driver(self) -> None:
        outputs = {
            "opportunity_cost": _opportunity_payload(dominant_excess_bps=250.0)
        }
        record = opportunity_x_value.run(outputs)
        self.assertTrue(record.fired)
        self.assertEqual(record.adjustments["signal"], "value_driver")
        self.assertEqual(record.adjustments["dominant_benchmark"], "sp500")
        self.assertTrue(
            any("beats" in r.lower() for r in record.reasoning),
            f"Expected 'beats' in reasoning, got {record.reasoning}",
        )

    def test_lags_benchmark_emits_risk(self) -> None:
        outputs = {
            "opportunity_cost": _opportunity_payload(
                dominant_excess_bps=-300.0, dominant_benchmark="tbill"
            )
        }
        record = opportunity_x_value.run(outputs)
        self.assertTrue(record.fired)
        self.assertEqual(record.adjustments["signal"], "risk")
        self.assertTrue(
            any("lags" in r.lower() for r in record.reasoning),
            f"Expected 'lags' in reasoning, got {record.reasoning}",
        )

    def test_thin_gap_emits_neutral(self) -> None:
        outputs = {
            "opportunity_cost": _opportunity_payload(
                dominant_excess_bps=50.0  # below 150 threshold
            )
        }
        record = opportunity_x_value.run(outputs)
        self.assertTrue(record.fired)
        self.assertEqual(record.adjustments["signal"], "neutral")
        self.assertTrue(
            any("in line" in r.lower() for r in record.reasoning),
            f"Expected 'in line' in reasoning, got {record.reasoning}",
        )

    def test_adjustments_include_raw_metrics(self) -> None:
        outputs = {
            "opportunity_cost": _opportunity_payload(dominant_excess_bps=200.0)
        }
        record = opportunity_x_value.run(outputs)
        adj = record.adjustments
        self.assertEqual(adj["dominant_excess_bps"], 200.0)
        self.assertEqual(adj["hold_years"], 5)
        self.assertEqual(adj["meaningful_excess_bps_threshold"], 150.0)
        self.assertAlmostEqual(adj["property_cagr"], 0.08, places=4)

    def test_confidence_propagates_from_module(self) -> None:
        outputs = {
            "opportunity_cost": _opportunity_payload(
                dominant_excess_bps=200.0, confidence=0.73
            )
        }
        record = opportunity_x_value.run(outputs)
        self.assertAlmostEqual(record.confidence, 0.73, places=4)


if __name__ == "__main__":
    unittest.main()

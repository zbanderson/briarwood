"""Isolation tests for the ``confidence`` scoped module.

Inventory audit flagged confidence as a placeholder that delegated wholly to
``PropertyDataQualityModule`` and never aggregated prior module confidences.
The module now blends a weighted mean of prior confidences with the
data-quality anchor. These tests lock that aggregation in.
"""
from __future__ import annotations

import unittest

from briarwood.modules.confidence import run_confidence

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
    context_thin,
)


def _prior(name: str, confidence: float) -> dict[str, object]:
    return {"data": {"module_name": name}, "confidence": confidence}


class ConfidenceIsolationTests(unittest.TestCase):
    def test_no_priors_falls_back_to_data_quality_anchor(self) -> None:
        payload = assert_payload_contract(run_confidence(context_normal()))
        self.assertIsNotNone(payload.confidence)
        self.assertEqual(
            payload.data.get("aggregated_prior_confidence"),
            None,
        )
        self.assertAlmostEqual(
            payload.confidence,
            payload.data.get("data_quality_confidence"),
            places=4,
        )
        self.assertTrue(payload.warnings, "should warn when anchoring on data quality alone")

    def test_aggregates_prior_confidences(self) -> None:
        priors = {
            "valuation": _prior("valuation", 0.80),
            "risk_model": _prior("risk_model", 0.60),
            "income_model": _prior("income_model", 0.70),
        }
        payload = assert_payload_contract(run_confidence(context_normal(prior_outputs=priors)))
        aggregated = payload.data.get("aggregated_prior_confidence")
        self.assertIsNotNone(aggregated)
        self.assertGreater(aggregated, 0.55)
        self.assertLess(aggregated, 0.85)
        anchor = payload.data.get("data_quality_confidence")
        self.assertAlmostEqual(
            payload.confidence,
            round(0.5 * aggregated + 0.5 * anchor, 4),
            places=3,
        )
        self.assertEqual(
            payload.assumptions_used.get("prior_confidence_modules"),
            sorted(priors.keys()),
        )

    def test_confidence_moves_with_prior_quality(self) -> None:
        high_priors = {
            "valuation": _prior("valuation", 0.90),
            "risk_model": _prior("risk_model", 0.85),
        }
        low_priors = {
            "valuation": _prior("valuation", 0.30),
            "risk_model": _prior("risk_model", 0.25),
        }
        high = run_confidence(context_normal(prior_outputs=high_priors)).get("confidence")
        low = run_confidence(context_normal(prior_outputs=low_priors)).get("confidence")
        self.assertGreater(high, low)

    def test_emits_confidence_on_thin_inputs(self) -> None:
        payload = assert_payload_contract(run_confidence(context_thin()))
        self.assertIsNotNone(payload.confidence)

    def test_non_numeric_prior_confidences_are_skipped(self) -> None:
        priors = {
            "valuation": _prior("valuation", 0.80),
            "bad_module": {"data": {}, "confidence": "high"},  # non-numeric
            "missing_conf": {"data": {}},  # no confidence at all
        }
        payload = assert_payload_contract(run_confidence(context_normal(prior_outputs=priors)))
        self.assertEqual(
            payload.assumptions_used.get("prior_confidence_modules"),
            ["valuation"],
        )


if __name__ == "__main__":
    unittest.main()

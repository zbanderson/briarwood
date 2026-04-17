"""Isolation tests for the ``risk_model`` scoped module.

The Phase 1 inventory flagged risk_model as a silo: it declared a dependency
on ``valuation`` but did not consume it. These tests now characterize the
bridged behavior — when valuation is present, risk_model consumes the fair
value; when absent, it falls back to legacy property-attribute logic.
"""
from __future__ import annotations

import unittest

from briarwood.modules.risk_model import run_risk_model

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_contradictory,
    context_fragile,
    context_normal,
    context_thin,
    context_unique,
)


def _valuation_output(fair_value: float) -> dict[str, object]:
    return {
        "data": {
            "module_name": "valuation",
            "metrics": {"briarwood_current_value": fair_value},
        },
        "confidence": 0.8,
    }


class RiskModelIsolationTests(unittest.TestCase):
    def test_normal_case_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_risk_model(context_normal()))
        self.assertIsNotNone(payload.confidence)

    def test_confidence_matches_legacy_when_valuation_absent(self) -> None:
        """Without a valuation prior_output the bridge no-ops and legacy
        confidence is returned unchanged across inputs of similar completeness.
        """
        normal = run_risk_model(context_normal()).get("confidence")
        contradictory = run_risk_model(context_contradictory()).get("confidence")
        fragile = run_risk_model(context_fragile()).get("confidence")
        self.assertEqual(normal, contradictory)
        self.assertEqual(normal, fragile)

    def test_thin_inputs_do_not_crash(self) -> None:
        payload = assert_payload_contract(run_risk_model(context_thin()))
        self.assertIsNotNone(payload.confidence)

    def test_unique_property_runs(self) -> None:
        payload = assert_payload_contract(run_risk_model(context_unique()))
        self.assertIsNotNone(payload.confidence)

    def test_assumptions_used_declares_silo_dependency(self) -> None:
        payload = assert_payload_contract(run_risk_model(context_normal()))
        self.assertTrue(payload.assumptions_used.get("valuation_dependency_declared"))
        self.assertFalse(payload.assumptions_used.get("valuation_dependency_used"))


class RiskModelValuationBridgeTests(unittest.TestCase):
    def test_overpriced_listing_lowers_confidence_and_flags(self) -> None:
        baseline = run_risk_model(context_normal())
        baseline_conf = baseline.get("confidence")
        fair = 600_000.0  # normal fixture lists at 725_000 → ~+20% premium
        context = context_normal(prior_outputs={"valuation": _valuation_output(fair)})
        payload = assert_payload_contract(run_risk_model(context))
        self.assertIsNotNone(payload.confidence)
        self.assertLess(payload.confidence, baseline_conf)
        bridge = payload.data.get("valuation_bridge") or {}
        self.assertEqual(bridge.get("flag"), "overpriced_vs_briarwood_fair_value")
        self.assertGreaterEqual(bridge.get("premium_pct"), 0.15)
        self.assertTrue(payload.assumptions_used.get("valuation_dependency_used"))
        self.assertTrue(payload.warnings, "overpriced listing should produce a warning")

    def test_underpriced_listing_raises_confidence(self) -> None:
        baseline_conf = run_risk_model(context_normal()).get("confidence")
        fair = 900_000.0  # normal lists at 725_000 → ~-19% below fair
        context = context_normal(prior_outputs={"valuation": _valuation_output(fair)})
        payload = assert_payload_contract(run_risk_model(context))
        self.assertGreater(payload.confidence, baseline_conf)
        bridge = payload.data.get("valuation_bridge") or {}
        self.assertEqual(bridge.get("flag"), "priced_below_briarwood_fair_value")

    def test_fairly_priced_listing_does_not_adjust_confidence(self) -> None:
        baseline_conf = run_risk_model(context_normal()).get("confidence")
        fair = 720_000.0  # normal lists at 725_000 → ~+0.7% premium
        context = context_normal(prior_outputs={"valuation": _valuation_output(fair)})
        payload = assert_payload_contract(run_risk_model(context))
        self.assertEqual(payload.confidence, baseline_conf)
        bridge = payload.data.get("valuation_bridge") or {}
        self.assertIsNone(bridge.get("flag"))
        self.assertTrue(payload.assumptions_used.get("valuation_dependency_used"))


if __name__ == "__main__":
    unittest.main()

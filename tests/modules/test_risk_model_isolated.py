"""Phase 2 isolation tests for the ``risk_model`` scoped module.

The Phase 1 inventory identified risk_model as the #1 silo: it declares a
dependency on ``valuation`` but does not consume it. These tests characterize
that silo behavior so Phase 4's ``valuation_x_risk`` bridge can measure the
difference after wiring.
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


class RiskModelIsolationTests(unittest.TestCase):
    def test_normal_case_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_risk_model(context_normal()))
        self.assertIsNotNone(payload.confidence)

    def test_confidence_is_insensitive_to_input_quality(self) -> None:
        """AUDIT: risk_model confidence is constant across wildly different inputs.

        This test *locks in* the silo. Phase 4 must break this: after wiring
        valuation_x_risk, confidence should differ materially between a clean
        normal case and a contradictory / fragile case.
        """
        normal = run_risk_model(context_normal()).get("confidence")
        contradictory = run_risk_model(context_contradictory()).get("confidence")
        fragile = run_risk_model(context_fragile()).get("confidence")
        # Today all three are ~0.72 — the silo signature. Assert equality so
        # the test goes red the moment someone wires real bridges (a good thing).
        self.assertEqual(normal, contradictory)
        self.assertEqual(normal, fragile)

    def test_thin_inputs_do_not_crash(self) -> None:
        payload = assert_payload_contract(run_risk_model(context_thin()))
        self.assertIsNotNone(payload.confidence)
        # AUDIT: thin inputs should degrade confidence. Today they do not.

    def test_unique_property_runs(self) -> None:
        payload = assert_payload_contract(run_risk_model(context_unique()))
        self.assertIsNotNone(payload.confidence)

    def test_assumptions_used_declares_silo_dependency(self) -> None:
        """The module self-documents that valuation dep is unused — lock that in."""
        payload = assert_payload_contract(run_risk_model(context_normal()))
        self.assertTrue(payload.assumptions_used.get("valuation_dependency_declared"))
        # AUDIT: once Phase 4 lands, this field should become:
        #   "valuation_dependency_declared": True, "valuation_dependency_used": True


if __name__ == "__main__":
    unittest.main()

"""Phase 2 isolation tests for the ``resale_scenario`` scoped module.

Phase 1 inventory flagged resale_scenario as a silo that ignores town regime
and execution risk. Phase 4's ``town_x_scenario`` and ``scenario_x_risk``
bridges must make its output sensitive to those inputs.
"""
from __future__ import annotations

import unittest

from briarwood.modules.resale_scenario_scoped import run_resale_scenario

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_contradictory,
    context_fragile,
    context_normal,
    context_thin,
    context_unique,
)


class ResaleScenarioIsolationTests(unittest.TestCase):
    def test_normal_case_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_resale_scenario(context_normal()))
        self.assertIsNotNone(payload.confidence)

    def test_thin_inputs_degrade_confidence(self) -> None:
        payload = assert_payload_contract(run_resale_scenario(context_thin()))
        # Missing purchase_price collapses scenario confidence. This is correct.
        conf = payload.confidence if payload.confidence is not None else 1.0
        self.assertLessEqual(conf, 0.3)

    def test_confidence_insensitive_to_fragile_financing(self) -> None:
        """AUDIT: execution fragility should modulate scenario confidence.

        Today resale_scenario produces identical confidence for normal and
        fragile inputs because it ignores financing state. Phase 4 must fix.
        """
        normal = run_resale_scenario(context_normal()).get("confidence")
        fragile = run_resale_scenario(context_fragile()).get("confidence")
        self.assertEqual(normal, fragile)

    def test_confidence_insensitive_to_contradictory_inputs(self) -> None:
        """AUDIT: contradictory (700 sqft @ $2.4M) produces same confidence."""
        normal = run_resale_scenario(context_normal()).get("confidence")
        contradictory = run_resale_scenario(context_contradictory()).get("confidence")
        self.assertEqual(normal, contradictory)

    def test_unique_property_runs(self) -> None:
        payload = assert_payload_contract(run_resale_scenario(context_unique()))
        self.assertIsNotNone(payload.confidence)

    def test_assumptions_used_populated(self) -> None:
        payload = assert_payload_contract(run_resale_scenario(context_normal()))
        self.assertEqual(
            payload.assumptions_used.get("legacy_module"),
            "BullBaseBearModule",
        )


if __name__ == "__main__":
    unittest.main()

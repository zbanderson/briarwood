"""Phase 2 isolation tests for the ``rent_stabilization`` scoped module.

The Phase 1 inventory flagged rent_stabilization as a silo whose confidence
never degrades (0.88 across most inputs) and which does not consume
``legal_confidence`` output even when accessory-unit signals exist.
"""
from __future__ import annotations

import unittest

from briarwood.modules.rent_stabilization import run_rent_stabilization

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_contradictory,
    context_fragile,
    context_normal,
    context_thin,
    context_unique,
)


class RentStabilizationIsolationTests(unittest.TestCase):
    def test_normal_case_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_rent_stabilization(context_normal()))
        self.assertIsNotNone(payload.confidence)

    def test_thin_inputs_degrade_gracefully(self) -> None:
        """Phase 3 fix: thin inputs (no purchase_price) used to crash with

        ``TypeError: income_support module payload is not an IncomeAgentOutput``.
        The module now degrades gracefully: low confidence + unavailable label
        instead of propagating the exception upward.
        """
        payload = assert_payload_contract(run_rent_stabilization(context_thin()))
        conf = payload.confidence if payload.confidence is not None else 1.0
        self.assertLessEqual(conf, 0.1)

    def test_confidence_is_flat_across_input_quality(self) -> None:
        """AUDIT: ~0.88 on every case that runs. Classic silo."""
        normal = run_rent_stabilization(context_normal()).get("confidence")
        contradictory = run_rent_stabilization(context_contradictory()).get("confidence")
        fragile = run_rent_stabilization(context_fragile()).get("confidence")
        self.assertEqual(normal, contradictory)
        self.assertEqual(normal, fragile)

    def test_unique_property_does_not_consume_legal_signals(self) -> None:
        """AUDIT: accessory-unit property does not get rent confidence downgrade.

        Phase 4 ``rent_x_risk`` bridge should make unique-case confidence
        *lower* than normal-case once legal_confidence is wired in.
        """
        normal = run_rent_stabilization(context_normal()).get("confidence")
        unique = run_rent_stabilization(context_unique()).get("confidence")
        self.assertEqual(normal, unique)

    def test_town_outlook_surfaces_in_extra_data(self) -> None:
        payload = assert_payload_contract(run_rent_stabilization(context_normal()))
        self.assertIn("town_county_outlook", payload.data)


if __name__ == "__main__":
    unittest.main()

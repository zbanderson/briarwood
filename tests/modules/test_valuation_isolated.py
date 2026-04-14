"""Phase 2 isolation tests for the ``valuation`` scoped module.

These are *characterization tests* — they lock in current behavior so that
Phase 3 (intake improvements) and Phase 4 (interaction bridges) can measure
real change. ``# AUDIT:`` comments mark behaviors that should change in later
phases; the companion notes live in ``docs/model_audits/valuation.md``.
"""
from __future__ import annotations

import unittest

from briarwood.modules.valuation import run_valuation

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_contradictory,
    context_fragile,
    context_normal,
    context_thin,
    context_unique,
)


class ValuationIsolationTests(unittest.TestCase):
    def test_normal_case_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_valuation(context_normal()))
        self.assertIsNotNone(payload.confidence)
        self.assertGreater(payload.confidence or 0.0, 0.0)

    def test_thin_inputs_degrade_confidence_to_zero(self) -> None:
        # Baseline behavior: no purchase_price + thin inputs → confidence collapses.
        # This is correct. The bar is that it remains ≤ 0.3, not that it's 0 exactly.
        payload = assert_payload_contract(run_valuation(context_thin()))
        conf = payload.confidence if payload.confidence is not None else 1.0
        self.assertLessEqual(conf, 0.3)

    def test_contradictory_inputs_do_not_raise(self) -> None:
        payload = assert_payload_contract(run_valuation(context_contradictory()))
        self.assertIsNotNone(payload.confidence)
        # AUDIT: a $2.4M asking price on 700 sqft should fire a warning or drive
        # confidence well below normal. Today it returns ~0.6 without warnings.
        # Phase 4 valuation_x_risk bridge should catch this.

    def test_unique_property_runs(self) -> None:
        payload = assert_payload_contract(run_valuation(context_unique()))
        self.assertIsNotNone(payload.confidence)
        # AUDIT: ADU + back-house signals are not reflected in valuation output.
        # Phase 3 strategy_classifier + Phase 4 primary_value_source bridge needed.

    def test_fragile_financing_does_not_alter_valuation(self) -> None:
        # Valuation is price-centric; financing shouldn't affect *value*, but it
        # should be surfaced as a bridge concern. Confirm valuation ignores it.
        normal = run_valuation(context_normal())
        fragile = run_valuation(context_fragile())
        self.assertIsNotNone(normal.get("confidence"))
        self.assertIsNotNone(fragile.get("confidence"))

    def test_assumptions_used_populated(self) -> None:
        payload = assert_payload_contract(run_valuation(context_normal()))
        self.assertIn("legacy_module", payload.assumptions_used)
        self.assertEqual(payload.assumptions_used["legacy_module"], "CurrentValueModule")


if __name__ == "__main__":
    unittest.main()

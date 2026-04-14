"""Phase 2 isolation tests for the ``legal_confidence`` scoped module.

Phase 1 inventory noted that legal_confidence output is "stranded" — nothing
downstream reads it. These tests lock in current behavior; Phase 4's
``rent_x_risk`` bridge must consume this output.
"""
from __future__ import annotations

import unittest

from briarwood.modules.legal_confidence import run_legal_confidence

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_contradictory,
    context_fragile,
    context_normal,
    context_thin,
    context_unique,
)


class LegalConfidenceIsolationTests(unittest.TestCase):
    def test_normal_case_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_legal_confidence(context_normal()))
        self.assertIsNotNone(payload.confidence)
        data = payload.data
        self.assertIn("legality_evidence", data)
        self.assertFalse(data["legality_evidence"]["has_accessory_signal"])

    def test_unique_property_detects_accessory_signal(self) -> None:
        payload = assert_payload_contract(run_legal_confidence(context_unique()))
        evidence = payload.data["legality_evidence"]
        self.assertTrue(evidence["has_accessory_signal"])
        self.assertEqual(evidence["adu_type"], "detached")
        self.assertTrue(evidence["has_back_house"])

    def test_unique_property_without_zoning_raises_warnings(self) -> None:
        """Accessory signals + no zone flags + no local docs → two warnings."""
        payload = assert_payload_contract(run_legal_confidence(context_unique()))
        self.assertEqual(len(payload.warnings), 2)
        self.assertTrue(any("zoning flags" in w for w in payload.warnings))
        self.assertTrue(any("local planning" in w for w in payload.warnings))

    def test_thin_inputs_do_not_crash(self) -> None:
        payload = assert_payload_contract(run_legal_confidence(context_thin()))
        self.assertIsNotNone(payload.confidence)

    def test_contradictory_and_fragile_run(self) -> None:
        assert_payload_contract(run_legal_confidence(context_contradictory()))
        assert_payload_contract(run_legal_confidence(context_fragile()))

    def test_confidence_caps_at_0_65_without_accessory_signal(self) -> None:
        """Module self-caps when there is no extra-unit question to answer."""
        payload = assert_payload_contract(run_legal_confidence(context_normal()))
        conf = payload.confidence if payload.confidence is not None else 1.0
        self.assertLessEqual(conf, 0.65)


if __name__ == "__main__":
    unittest.main()

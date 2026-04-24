"""Isolation tests for the location_intelligence scoped wrapper.

Pins:
- Standalone error contract (DECISIONS.md 2026-04-24): exceptions return
  ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).
- Missing-input semantics: the underlying module populates
  ``confidence_notes`` + ``missing_inputs`` when coords / landmarks / geo
  comps are absent. The scoped wrapper must surface those, not promote them
  to error mode.
- Registry integration.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import build_module_registry
from briarwood.modules.location_intelligence_scoped import run_location_intelligence

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
)


class LocationIntelligenceIsolationTests(unittest.TestCase):
    def test_normal_context_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_location_intelligence(context_normal()))
        self.assertEqual(payload.module_name, "location_intelligence")
        self.assertTrue(
            payload.assumptions_used.get("benchmarks_against_town_peer_comps")
        )

    def test_missing_inputs_does_not_raise(self) -> None:
        """Normal fixtures lack latitude/longitude; the legacy module populates
        confidence_notes + missing_inputs but must NOT raise. Low-confidence
        output legitimately infers mode="fallback" through _infer_payload_mode;
        that's semantically correct, not a wrapper bug. The hard contract: the
        wrapper never raises, and the fallback_reason attribution distinguishes
        low-confidence-legacy-output from caught-exception fallback.
        """
        payload = run_location_intelligence(context_normal())
        # Wrapper did not throw and produced a valid ModulePayload.
        self.assertEqual(payload["data"]["module_name"], "location_intelligence")
        # If mode landed on "fallback", assumptions_used must NOT carry the
        # caught-exception fallback_reason (that reason is reserved for the
        # try/except path; this fixture triggers the low-confidence path).
        self.assertNotEqual(
            payload["assumptions_used"].get("fallback_reason"),
            "provider_or_geocode_error",
        )
        # And never the composite-only error mode.
        self.assertNotEqual(payload["mode"], "error")


class LocationIntelligenceErrorContractTests(unittest.TestCase):
    def test_legacy_module_exception_returns_fallback(self) -> None:
        with patch(
            "briarwood.modules.location_intelligence_scoped.LocationIntelligenceModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("provider failed")
            payload = run_location_intelligence(context_normal())
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)
        self.assertTrue(
            any("Location-intelligence fallback" in w for w in payload["warnings"]),
            f"warnings={payload['warnings']!r}",
        )

    def test_empty_context_returns_fallback(self) -> None:
        empty_ctx = ExecutionContext(property_id="empty")
        payload = run_location_intelligence(empty_ctx)
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)


class LocationIntelligenceRegistryTests(unittest.TestCase):
    def test_location_intelligence_is_registered(self) -> None:
        registry = build_module_registry()
        self.assertIn("location_intelligence", registry)
        spec = registry["location_intelligence"]
        self.assertEqual(spec.depends_on, [])
        self.assertEqual(spec.runner, run_location_intelligence)

    def test_location_intelligence_resolves_in_plan(self) -> None:
        registry = build_module_registry()
        plan = build_execution_plan(["location_intelligence"], registry)
        self.assertIn("location_intelligence", plan.ordered_modules)
        self.assertEqual(plan.dependency_modules, [])


if __name__ == "__main__":
    unittest.main()

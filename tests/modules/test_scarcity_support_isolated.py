"""Isolation tests for the scarcity_support scoped wrapper.

Pins:
- Standalone error contract (DECISIONS.md 2026-04-24): exceptions return
  ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).
- Field-name stability: ``scarcity_support_score`` is read by multiple
  consumers (decision_model, interactions, rental_ease agent). The wrapper
  must not reshape it.
- Registry integration.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import build_module_registry
from briarwood.modules.scarcity_support_scoped import run_scarcity_support

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
)


class ScarcitySupportIsolationTests(unittest.TestCase):
    def test_normal_context_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_scarcity_support(context_normal()))
        self.assertEqual(payload.module_name, "scarcity_support")
        self.assertTrue(payload.assumptions_used.get("geography_driven"))

    def test_preserves_scarcity_support_score_key(self) -> None:
        """scarcity_support_score is read by key at ~10 callsites. The wrapper
        must pass it through unchanged."""
        payload = run_scarcity_support(context_normal())
        metrics = dict((payload["data"].get("metrics") or {}))
        self.assertIn(
            "scarcity_support_score", metrics,
            f"metrics missing 'scarcity_support_score'; keys={list(metrics)!r}",
        )
        self.assertIn("scarcity_label", metrics)


class ScarcitySupportErrorContractTests(unittest.TestCase):
    def test_legacy_module_exception_returns_fallback(self) -> None:
        with patch(
            "briarwood.modules.scarcity_support_scoped.ScarcitySupportModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("town lookup failed")
            payload = run_scarcity_support(context_normal())
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)
        self.assertTrue(
            any("Scarcity-support fallback" in w for w in payload["warnings"]),
            f"warnings={payload['warnings']!r}",
        )

    def test_empty_context_returns_fallback(self) -> None:
        empty_ctx = ExecutionContext(property_id="empty")
        payload = run_scarcity_support(empty_ctx)
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)


class ScarcitySupportRegistryTests(unittest.TestCase):
    def test_scarcity_support_is_registered(self) -> None:
        registry = build_module_registry()
        self.assertIn("scarcity_support", registry)
        spec = registry["scarcity_support"]
        self.assertEqual(spec.depends_on, [])
        self.assertEqual(spec.runner, run_scarcity_support)

    def test_scarcity_support_resolves_in_plan(self) -> None:
        registry = build_module_registry()
        plan = build_execution_plan(["scarcity_support"], registry)
        self.assertIn("scarcity_support", plan.ordered_modules)
        self.assertEqual(plan.dependency_modules, [])


if __name__ == "__main__":
    unittest.main()

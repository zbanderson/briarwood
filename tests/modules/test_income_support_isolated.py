"""Isolation tests for the income_support scoped wrapper.

Pins:
- Standalone error contract (DECISIONS.md 2026-04-24): exceptions return
  ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).
- Field-name stability: downstream callers (``risk_bar``, ``evidence``,
  ``comp_intelligence``, ``rental_ease``, ``hybrid_value``) read payload
  fields by name; the wrapper must not reshape them.
- Anti-recursion: income_support and rental_option are siblings that share
  an engine but neither depends on the other in the scoped registry.
- Registry integration.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import build_module_registry
from briarwood.modules.income_support_scoped import run_income_support

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
)


class IncomeSupportIsolationTests(unittest.TestCase):
    def test_normal_context_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_income_support(context_normal()))
        self.assertEqual(payload.module_name, "income_support")
        self.assertTrue(
            payload.assumptions_used.get("exposes_raw_underwriting_signal", False)
        )

    def test_preserves_legacy_payload_field_names(self) -> None:
        """Consumers read by key — the wrapper must not reshape."""
        payload = run_income_support(context_normal())
        legacy = dict(payload["data"].get("legacy_payload") or {})
        for key in (
            "income_support_ratio",
            "rent_coverage",
            "price_to_rent",
            "monthly_cash_flow",
            "rent_support_classification",
            "effective_monthly_rent",
            "gross_monthly_cost",
            "confidence",
        ):
            self.assertIn(
                key,
                legacy,
                f"legacy_payload missing '{key}'; keys={list(legacy)!r}",
            )


class IncomeSupportErrorContractTests(unittest.TestCase):
    def test_legacy_module_exception_returns_fallback(self) -> None:
        with patch(
            "briarwood.modules.income_support_scoped.IncomeSupportModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("engine blew up")
            payload = run_income_support(context_normal())
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)
        self.assertTrue(
            any("Income-support fallback" in w for w in payload["warnings"]),
            f"warnings={payload['warnings']!r}",
        )

    def test_empty_context_returns_fallback(self) -> None:
        empty_ctx = ExecutionContext(property_id="empty")
        payload = run_income_support(empty_ctx)
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)


class IncomeSupportRegistryTests(unittest.TestCase):
    def test_income_support_is_registered(self) -> None:
        registry = build_module_registry()
        self.assertIn("income_support", registry)
        spec = registry["income_support"]
        self.assertEqual(spec.depends_on, [])
        self.assertEqual(spec.runner, run_income_support)
        self.assertIn("property_data", spec.required_context_keys)

    def test_income_support_resolves_in_plan(self) -> None:
        registry = build_module_registry()
        plan = build_execution_plan(["income_support"], registry)
        self.assertIn("income_support", plan.ordered_modules)
        self.assertEqual(plan.dependency_modules, [])

    def test_income_support_and_rental_option_are_siblings_not_dependents(self) -> None:
        """Neither tool depends on the other. Anti-recursion: rental_option
        calls IncomeSupportModule in-process, and income_support does the
        same; neither reads the other's prior_outputs.
        """
        registry = build_module_registry()
        self.assertNotIn("income_support", registry["rental_option"].depends_on)
        self.assertNotIn("rental_option", registry["income_support"].depends_on)


if __name__ == "__main__":
    unittest.main()

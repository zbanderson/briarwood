"""Isolation tests for the comparable_sales scoped wrapper.

Pins:
- Standalone error contract (DECISIONS.md 2026-04-24): exceptions return
  ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).
- Field-name stability: hybrid_value (via prior_results) and unit_income_offset
  read the payload by key; the wrapper must not reshape.
- Registry integration.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import build_module_registry
from briarwood.modules.comparable_sales_scoped import run_comparable_sales

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
)


class ComparableSalesIsolationTests(unittest.TestCase):
    def test_normal_context_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_comparable_sales(context_normal()))
        self.assertEqual(payload.module_name, "comparable_sales")
        self.assertEqual(
            payload.assumptions_used.get("engine"),
            "Engine A (saved comps)",
        )

    def test_preserves_legacy_payload_field_names(self) -> None:
        """hybrid_value and unit_income_offset read these keys directly.
        The wrapper must pass them through unchanged."""
        payload = run_comparable_sales(context_normal())
        legacy = dict(payload["data"].get("legacy_payload") or {})
        for key in (
            "comparable_value",
            "comp_count",
            "confidence",
            "comps_used",
            "direct_value_range",
            "income_adjusted_value_range",
            "location_adjustment_range",
            "lot_adjustment_range",
            "blended_value_range",
            "comp_confidence_score",
            "is_hybrid_valuation",
        ):
            self.assertIn(
                key,
                legacy,
                f"legacy_payload missing '{key}'; keys={list(legacy)!r}",
            )


class ComparableSalesErrorContractTests(unittest.TestCase):
    def test_legacy_module_exception_returns_fallback(self) -> None:
        with patch(
            "briarwood.modules.comparable_sales_scoped.ComparableSalesModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("provider blew up")
            payload = run_comparable_sales(context_normal())
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)
        self.assertTrue(
            any("Comparable-sales fallback" in w for w in payload["warnings"]),
            f"warnings={payload['warnings']!r}",
        )

    def test_empty_context_returns_fallback(self) -> None:
        empty_ctx = ExecutionContext(property_id="empty")
        payload = run_comparable_sales(empty_ctx)
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)


class ComparableSalesRegistryTests(unittest.TestCase):
    def test_comparable_sales_is_registered(self) -> None:
        registry = build_module_registry()
        self.assertIn("comparable_sales", registry)
        spec = registry["comparable_sales"]
        self.assertEqual(spec.depends_on, [])
        self.assertEqual(spec.runner, run_comparable_sales)

    def test_comparable_sales_resolves_in_plan(self) -> None:
        registry = build_module_registry()
        plan = build_execution_plan(["comparable_sales"], registry)
        self.assertIn("comparable_sales", plan.ordered_modules)
        self.assertEqual(plan.dependency_modules, [])


if __name__ == "__main__":
    unittest.main()

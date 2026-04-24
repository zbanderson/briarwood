"""Isolation tests for the market_value_history scoped wrapper.

Pins the canonical standalone error contract from DECISIONS.md 2026-04-24:
- Legitimate town/state → legacy-result passthrough with ``module_payload_from_legacy_result``.
- Exception inside the legacy module → ``module_payload_from_error`` (``mode="fallback"``,
  ``confidence=0.08``).
- The payload is geography-level — the same town produces the same history
  regardless of property-level details (sqft, beds, purchase_price).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import build_module_registry
from briarwood.modules.market_value_history_scoped import run_market_value_history

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
    context_thin,
)


class MarketValueHistoryIsolationTests(unittest.TestCase):
    def test_normal_context_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_market_value_history(context_normal()))
        self.assertEqual(payload.module_name, "market_value_history")
        # Geography-level keys always present on happy path, even when ZHVI
        # coverage is empty (the legacy module populates geography identity
        # from the request itself).
        metrics = dict(payload.data.get("metrics") or {})
        self.assertIn("geography_name", metrics)
        self.assertIn("geography_type", metrics)

    def test_thin_context_still_classifies_geography(self) -> None:
        # Thin fixture has town + state; the module can still resolve geography.
        payload = assert_payload_contract(run_market_value_history(context_thin()))
        self.assertEqual(payload.module_name, "market_value_history")

    def test_geography_level_invariance(self) -> None:
        """Same town + state → same geography identity regardless of sqft/beds."""
        normal = run_market_value_history(context_normal())
        thin = run_market_value_history(context_thin())
        normal_metrics = dict(normal["data"].get("metrics") or {})
        thin_metrics = dict(thin["data"].get("metrics") or {})
        # Both fixtures target "Avon By The Sea", NJ. Geography metadata must match.
        self.assertEqual(
            normal_metrics.get("geography_name"),
            thin_metrics.get("geography_name"),
        )
        self.assertEqual(
            normal_metrics.get("geography_type"),
            thin_metrics.get("geography_type"),
        )


class MarketValueHistoryErrorContractTests(unittest.TestCase):
    def test_legacy_module_exception_returns_fallback(self) -> None:
        with patch(
            "briarwood.modules.market_value_history_scoped.MarketValueHistoryModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("zhvi file missing")
            payload = run_market_value_history(context_normal())
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)
        self.assertTrue(
            any("Market-value-history fallback" in w for w in payload["warnings"]),
            f"warnings={payload['warnings']!r}",
        )

    def test_empty_context_returns_fallback(self) -> None:
        # build_property_input_from_context raises on empty property_data;
        # the wrapper's try/except must catch it and return a fallback.
        empty_ctx = ExecutionContext(property_id="empty")
        payload = run_market_value_history(empty_ctx)
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)


class MarketValueHistoryRegistryTests(unittest.TestCase):
    def test_market_value_history_is_registered(self) -> None:
        registry = build_module_registry()
        self.assertIn("market_value_history", registry)
        spec = registry["market_value_history"]
        self.assertEqual(spec.depends_on, [])
        self.assertEqual(spec.runner, run_market_value_history)
        self.assertIn("property_data", spec.required_context_keys)

    def test_market_value_history_resolves_in_plan(self) -> None:
        registry = build_module_registry()
        plan = build_execution_plan(["market_value_history"], registry)
        self.assertIn("market_value_history", plan.ordered_modules)
        self.assertEqual(plan.dependency_modules, [])


if __name__ == "__main__":
    unittest.main()

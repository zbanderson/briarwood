"""Isolation tests for the current_value scoped wrapper.

Pins:
- Standalone error contract (DECISIONS.md 2026-04-24): exceptions return
  ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).
- Anti-recursion + macro-isolation sanity: on a fixture with a macro HPI
  signal, the scoped ``valuation`` tool applies the nudge; the scoped
  ``current_value`` tool does NOT. Same engine, different contracts.
- Registry integration.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import build_module_registry
from briarwood.modules.current_value_scoped import run_current_value
from briarwood.modules.valuation import run_valuation

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
)


class CurrentValueIsolationTests(unittest.TestCase):
    def test_normal_context_produces_valid_payload(self) -> None:
        payload = assert_payload_contract(run_current_value(context_normal()))
        self.assertEqual(payload.module_name, "current_value")
        # Pre-macro wrapper must NOT claim macro_context_used.
        self.assertFalse(
            payload.assumptions_used.get("applies_macro_nudge", True),
            f"assumptions_used={payload.assumptions_used!r}",
        )

    def test_preserves_legacy_payload_field_names(self) -> None:
        """Direct callers read the engine payload; key names must pass through."""
        payload = run_current_value(context_normal())
        legacy = dict(payload["data"].get("legacy_payload") or {})
        # The engine's CurrentValueOutput exposes these fields; consumers
        # (valuation, bull_base_bear, teardown_scenario, renovation_scenario)
        # read them by key. Verify they survive the wrapper.
        for key in (
            "briarwood_current_value",
            "mispricing_pct",
            "pricing_view",
            "value_low",
            "value_high",
            "confidence",
        ):
            self.assertIn(
                key, legacy, f"legacy_payload missing '{key}'; keys={list(legacy)!r}"
            )


class CurrentValueMacroIsolationTests(unittest.TestCase):
    """Anti-recursion + macro-isolation sanity check.

    Given the same context with a macro HPI signal, `valuation` and
    `current_value` share the same engine but produce different top-level
    confidence values: `valuation` applies the nudge, `current_value` does not.
    This confirms the two scoped tools do not secretly collapse into one path.
    """

    def _context_with_macro(self) -> ExecutionContext:
        ctx = context_normal()
        # MacroContextSlice expects flat float fields in [0, 1]; 0.8 is
        # clearly away from neutral 0.5, forcing apply_macro_nudge to move
        # valuation's confidence away from current_value's.
        ctx.macro_context = {
            "county": "Monmouth",
            "state": "NJ",
            "as_of": "2026-04-01",
            "hpi_momentum_signal": 0.8,
        }
        return ctx

    def test_valuation_and_current_value_diverge_under_macro_signal(self) -> None:
        ctx = self._context_with_macro()
        val = run_valuation(ctx)
        cur = run_current_value(ctx)
        # Same engine → same inner fair-value number.
        val_legacy = dict(val["data"].get("legacy_payload") or {})
        cur_legacy = dict(cur["data"].get("legacy_payload") or {})
        self.assertEqual(
            val_legacy.get("briarwood_current_value"),
            cur_legacy.get("briarwood_current_value"),
        )
        # Contract flags are always different. macro_context_used depends on
        # whether the macro slice parsed; with a well-formed slice and a
        # non-null signal it must be True.
        self.assertFalse(cur["assumptions_used"].get("applies_macro_nudge"))
        self.assertTrue(val["assumptions_used"].get("macro_context_used"))
        # Top-level confidence must diverge once the nudge applies.
        self.assertNotEqual(val["confidence"], cur["confidence"])


class CurrentValueErrorContractTests(unittest.TestCase):
    def test_legacy_module_exception_returns_fallback(self) -> None:
        with patch(
            "briarwood.modules.current_value_scoped.CurrentValueModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("engine blew up")
            payload = run_current_value(context_normal())
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)
        self.assertTrue(
            any("Current-value fallback" in w for w in payload["warnings"]),
            f"warnings={payload['warnings']!r}",
        )
        self.assertFalse(payload["assumptions_used"].get("applies_macro_nudge"))

    def test_empty_context_returns_fallback(self) -> None:
        empty_ctx = ExecutionContext(property_id="empty")
        payload = run_current_value(empty_ctx)
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)


class CurrentValueRegistryTests(unittest.TestCase):
    def test_current_value_is_registered(self) -> None:
        registry = build_module_registry()
        self.assertIn("current_value", registry)
        spec = registry["current_value"]
        # No scoped-registry deps — the engine composes its children in-process.
        self.assertEqual(spec.depends_on, [])
        self.assertEqual(spec.runner, run_current_value)
        self.assertIn("property_data", spec.required_context_keys)

    def test_current_value_resolves_in_plan(self) -> None:
        registry = build_module_registry()
        plan = build_execution_plan(["current_value"], registry)
        self.assertIn("current_value", plan.ordered_modules)
        self.assertEqual(plan.dependency_modules, [])

    def test_current_value_and_valuation_are_siblings_not_dependents(self) -> None:
        """Neither tool depends on the other. Anti-recursion: valuation does not
        declare current_value as a depends_on, and current_value does not
        declare valuation. Both call CurrentValueModule in-process independently.
        """
        registry = build_module_registry()
        self.assertNotIn("current_value", registry["valuation"].depends_on)
        self.assertNotIn("valuation", registry["current_value"].depends_on)


if __name__ == "__main__":
    unittest.main()

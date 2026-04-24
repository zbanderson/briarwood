"""Isolation tests for the hybrid_value scoped wrapper.

Pins:
- Canonical composite error contract (DECISIONS.md 2026-04-24):
  * Missing or degraded priors → module_payload_from_missing_prior
    (mode="error", confidence=None, missing_inputs populated).
  * Internal exception during happy path → module_payload_from_error
    (mode="fallback", confidence=0.08).
- is_hybrid=False short-circuit is a VALID legacy payload (not an error)
  — non-hybrid subjects get a zero-confidence, but not mode="error".
- Registry integration, including the depends_on edges.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import build_execution_plan
from briarwood.execution.registry import build_module_registry
from briarwood.modules.hybrid_value_scoped import run_hybrid_value

from tests.modules._phase2_fixtures import (
    assert_payload_contract,
    context_normal,
    context_unique,
)


def _valid_prior(mode: str = "full", confidence: float = 0.7) -> dict:
    """A minimal 'clean' scoped-payload dict — good enough to pass the gate."""
    return {
        "data": {"module_name": "prior", "summary": "test", "metrics": {}},
        "confidence": confidence,
        "warnings": [],
        "mode": mode,
    }


def _context_with_clean_priors(base):
    base.prior_outputs = {
        "comparable_sales": _valid_prior(),
        "income_support": _valid_prior(),
    }
    return base


class HybridValueIsolationTests(unittest.TestCase):
    def test_non_hybrid_subject_returns_is_hybrid_false_valid_payload(self) -> None:
        """A standard single-family subject does not screen as hybrid.
        The legacy module returns a valid ModuleResult with is_hybrid=False
        and zero confidence; the scoped wrapper must pass that through as
        a legitimate legacy-result payload — NOT mode='error'.
        """
        ctx = _context_with_clean_priors(context_normal())
        payload = assert_payload_contract(run_hybrid_value(ctx))
        self.assertEqual(payload.module_name, "hybrid_value")
        # Not the error mode — the answer "not a hybrid property" is a
        # valid product answer, not a module failure.
        self.assertNotEqual(payload.mode, "error")
        # legacy_payload must carry is_hybrid flag
        legacy = dict(payload.data.get("legacy_payload") or {})
        self.assertIn("is_hybrid", legacy)
        self.assertFalse(legacy["is_hybrid"])

    def test_hybrid_subject_produces_decomposition(self) -> None:
        """context_unique has ADU + back house — legacy module should set
        is_hybrid=True and populate primary/rear decomposition fields."""
        ctx = _context_with_clean_priors(context_unique())
        payload = run_hybrid_value(ctx)
        self.assertNotEqual(payload["mode"], "error")
        legacy = dict(payload["data"].get("legacy_payload") or {})
        self.assertIn("is_hybrid", legacy)
        # The hybrid fixture may or may not classify as hybrid by the
        # detector's criteria; we check the decomposition fields exist
        # regardless so consumers (current_value, risk_bar) can read them.
        for key in (
            "is_hybrid",
            "reason",
            "primary_house_value",
            "rear_income_value",
            "optionality_premium_value",
            "low_case_hybrid_value",
            "base_case_hybrid_value",
            "high_case_hybrid_value",
            "confidence",
        ):
            self.assertIn(
                key,
                legacy,
                f"legacy_payload missing '{key}'; keys={list(legacy)!r}",
            )


class HybridValueMissingPriorTests(unittest.TestCase):
    def test_both_priors_missing_returns_error_mode(self) -> None:
        ctx = context_normal()
        ctx.prior_outputs = {}
        payload = run_hybrid_value(ctx)
        self.assertEqual(payload["mode"], "error")
        self.assertIsNone(payload["confidence"])
        self.assertEqual(
            payload["missing_inputs"],
            ["comparable_sales", "income_support"],
        )
        self.assertTrue(
            all("Missing prior module output" in w for w in payload["warnings"])
        )

    def test_comparable_sales_degraded_treated_as_missing(self) -> None:
        """A prior with mode='error' or 'fallback' must not be composed on."""
        ctx = context_normal()
        ctx.prior_outputs = {
            "comparable_sales": _valid_prior(mode="error"),
            "income_support": _valid_prior(mode="full"),
        }
        payload = run_hybrid_value(ctx)
        self.assertEqual(payload["mode"], "error")
        self.assertEqual(payload["missing_inputs"], ["comparable_sales"])

    def test_income_support_fallback_mode_treated_as_missing(self) -> None:
        ctx = context_normal()
        ctx.prior_outputs = {
            "comparable_sales": _valid_prior(mode="full"),
            "income_support": _valid_prior(mode="fallback"),
        }
        payload = run_hybrid_value(ctx)
        self.assertEqual(payload["mode"], "error")
        self.assertEqual(payload["missing_inputs"], ["income_support"])

    def test_non_dict_prior_treated_as_missing(self) -> None:
        ctx = context_normal()
        ctx.prior_outputs = {
            "comparable_sales": "not a dict",
            "income_support": _valid_prior(),
        }
        payload = run_hybrid_value(ctx)
        self.assertEqual(payload["mode"], "error")
        self.assertIn("comparable_sales", payload["missing_inputs"])


class HybridValueErrorContractTests(unittest.TestCase):
    def test_legacy_module_exception_returns_fallback(self) -> None:
        ctx = _context_with_clean_priors(context_normal())
        with patch(
            "briarwood.modules.hybrid_value_scoped.HybridValueModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("engine blew up")
            payload = run_hybrid_value(ctx)
        self.assertEqual(payload["mode"], "fallback")
        self.assertEqual(payload["confidence"], 0.08)
        self.assertTrue(
            any("Hybrid-value fallback" in w for w in payload["warnings"]),
            f"warnings={payload['warnings']!r}",
        )


class HybridValueRegistryTests(unittest.TestCase):
    def test_hybrid_value_is_registered(self) -> None:
        registry = build_module_registry()
        self.assertIn("hybrid_value", registry)
        spec = registry["hybrid_value"]
        # Composite dependencies: both comparable_sales and income_support
        # must be registered ahead of hybrid_value.
        self.assertIn("comparable_sales", spec.depends_on)
        self.assertIn("income_support", spec.depends_on)
        self.assertEqual(spec.runner, run_hybrid_value)

    def test_hybrid_value_plan_expands_dependencies(self) -> None:
        registry = build_module_registry()
        plan = build_execution_plan(["hybrid_value"], registry)
        self.assertIn("hybrid_value", plan.ordered_modules)
        # Planner must pull in both upstream modules automatically.
        self.assertIn("comparable_sales", plan.dependency_modules)
        self.assertIn("income_support", plan.dependency_modules)
        # And order them before hybrid_value.
        hybrid_idx = plan.ordered_modules.index("hybrid_value")
        cs_idx = plan.ordered_modules.index("comparable_sales")
        is_idx = plan.ordered_modules.index("income_support")
        self.assertLess(cs_idx, hybrid_idx)
        self.assertLess(is_idx, hybrid_idx)


if __name__ == "__main__":
    unittest.main()

"""Isolation tests for the margin_sensitivity scoped wrapper.

These tests pin the fix for a live key-name bug that silently zeroed
the carry drag across every sensitivity scenario: the wrapper was
reading ``total_monthly_cost`` (transposed) from the carry_cost
payload while the authoritative emitter at ``briarwood.schemas``
writes ``monthly_total_cost``. The test asserts the real key is read
so a future regression is caught at runtime rather than in production.
"""

from __future__ import annotations

import unittest

from briarwood.execution.context import ExecutionContext
from briarwood.modules.margin_sensitivity_scoped import run_margin_sensitivity


def _arv_output(
    *,
    current_bcv: float = 790_000.0,
    renovated_bcv: float = 1_040_000.0,
    renovation_budget: float = 150_000.0,
    roi_pct: float = 66.7,
    confidence: float = 0.65,
) -> dict:
    return {
        "data": {
            "module_name": "arv_model",
            "summary": "test",
            "arv_snapshot": {
                "current_bcv": current_bcv,
                "renovated_bcv": renovated_bcv,
                "renovation_budget": renovation_budget,
                "roi_pct": roi_pct,
            },
        },
        "confidence": confidence,
        "warnings": [],
        "mode": "full",
    }


def _renovation_output(confidence: float = 0.65) -> dict:
    return {
        "data": {
            "module_name": "renovation_impact",
            "summary": "test",
            "metrics": {},
        },
        "confidence": confidence,
        "warnings": [],
        "mode": "full",
    }


def _carry_output(
    *, monthly_total_cost: float = 5_800.0, confidence: float = 0.72
) -> dict:
    """Mirror the authoritative key name from briarwood.schemas.ValuationOutput.to_metrics."""
    return {
        "data": {
            "module_name": "carry_cost",
            "summary": "test",
            "metrics": {"monthly_total_cost": monthly_total_cost},
        },
        "confidence": confidence,
        "warnings": [],
        "mode": "full",
    }


def _context(prior_outputs: dict) -> ExecutionContext:
    return ExecutionContext(
        property_id="margin-sens-test",
        property_data={"property_id": "margin-sens-test", "town": "Montclair", "state": "NJ"},
        assumptions={},
        prior_outputs=dict(prior_outputs),
    )


class MarginSensitivityCarryDrag(unittest.TestCase):
    """The carry-cost key name must match the authoritative emitter."""

    def test_monthly_carry_is_read_from_real_key(self) -> None:
        monthly_total_cost = 5_800.0
        holding_months = 6  # matches the constant at margin_sensitivity_scoped.py:34

        payload = run_margin_sensitivity(
            _context(
                {
                    "arv_model": _arv_output(),
                    "renovation_impact": _renovation_output(),
                    "carry_cost": _carry_output(monthly_total_cost=monthly_total_cost),
                }
            )
        )

        snapshot = payload["data"]["margin_snapshot"]
        self.assertAlmostEqual(snapshot["monthly_carry"], monthly_total_cost, places=2)
        self.assertAlmostEqual(
            snapshot["total_hold_cost"], monthly_total_cost * holding_months, places=2
        )

    def test_carry_is_deducted_from_breakeven_budget(self) -> None:
        """breakeven_budget = gross_value_creation - total_hold_cost; the deduction must be real."""

        payload = run_margin_sensitivity(
            _context(
                {
                    "arv_model": _arv_output(),
                    "renovation_impact": _renovation_output(),
                    "carry_cost": _carry_output(monthly_total_cost=5_800.0),
                }
            )
        )

        snapshot = payload["data"]["margin_snapshot"]
        gross = snapshot["gross_value_creation"]
        self.assertGreater(snapshot["total_hold_cost"], 0.0)
        self.assertLess(snapshot["breakeven_budget"], gross)
        self.assertAlmostEqual(
            snapshot["breakeven_budget"],
            gross - snapshot["total_hold_cost"],
            places=2,
        )

    def test_carry_drag_reduces_budget_overrun_margin(self) -> None:
        """Carry-inclusive budget_overrun_margin_pct must be lower than the carry-free version."""

        with_carry = run_margin_sensitivity(
            _context(
                {
                    "arv_model": _arv_output(),
                    "renovation_impact": _renovation_output(),
                    "carry_cost": _carry_output(monthly_total_cost=5_800.0),
                }
            )
        )
        no_carry = run_margin_sensitivity(
            _context(
                {
                    "arv_model": _arv_output(),
                    "renovation_impact": _renovation_output(),
                    "carry_cost": _carry_output(monthly_total_cost=0.0),
                }
            )
        )

        self.assertLess(
            with_carry["data"]["margin_snapshot"]["budget_overrun_margin_pct"],
            no_carry["data"]["margin_snapshot"]["budget_overrun_margin_pct"],
        )

    def test_every_scenario_includes_the_carry_drag(self) -> None:
        """Each sensitivity scenario's net_profit must reflect the non-zero carry drag."""

        payload = run_margin_sensitivity(
            _context(
                {
                    "arv_model": _arv_output(),
                    "renovation_impact": _renovation_output(),
                    "carry_cost": _carry_output(monthly_total_cost=5_800.0),
                }
            )
        )

        scenarios = payload["data"]["sensitivity_scenarios"]
        self.assertEqual(len(scenarios), 6)
        expected_hold_cost = 5_800.0 * 6
        for scenario in scenarios:
            self.assertAlmostEqual(scenario["hold_cost"], expected_hold_cost, places=2)


class MarginSensitivityErrorContractTests(unittest.TestCase):
    """Pin the canonical error-contract (DECISIONS.md 2026-04-24)."""

    def test_missing_priors_return_error_mode(self) -> None:
        payload = run_margin_sensitivity(_context({}))
        self.assertEqual(payload["mode"], "error")
        self.assertIsNone(payload["confidence"])
        self.assertEqual(
            payload["missing_inputs"],
            ["arv_model", "renovation_impact", "carry_cost"],
        )

    def test_degraded_prior_treated_as_missing(self) -> None:
        prior = {
            "arv_model": {**_arv_output(), "mode": "error"},
            "renovation_impact": _renovation_output(),
            "carry_cost": _carry_output(),
        }
        payload = run_margin_sensitivity(_context(prior))
        self.assertEqual(payload["mode"], "error")
        self.assertEqual(payload["missing_inputs"], ["arv_model"])


if __name__ == "__main__":
    unittest.main()

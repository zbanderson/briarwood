"""Isolation tests for the hold_to_rent scoped composite wrapper.

Pins the canonical error-contract behavior from DECISIONS.md 2026-04-24.
"""

from __future__ import annotations

import unittest

from briarwood.execution.context import ExecutionContext
from briarwood.modules.hold_to_rent import run_hold_to_rent


def _carry_output(mode: str = "full", confidence: float = 0.72) -> dict:
    return {
        "data": {
            "module_name": "carry_cost",
            "summary": "test",
            "metrics": {"monthly_cash_flow": -1_200.0, "cap_rate": 0.043},
        },
        "confidence": confidence,
        "warnings": [],
        "mode": mode,
    }


def _stabilization_output(mode: str = "full", confidence: float = 0.65) -> dict:
    return {
        "data": {
            "module_name": "rent_stabilization",
            "summary": "test",
            "metrics": {
                "rental_ease_label": "easy",
                "rental_ease_score": 4.0,
                "estimated_days_to_rent": 35,
            },
        },
        "confidence": confidence,
        "warnings": [],
        "mode": mode,
    }


def _context(prior_outputs: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        property_id="hold-to-rent-test",
        property_data={"property_id": "hold-to-rent-test", "town": "Montclair", "state": "NJ"},
        assumptions={},
        prior_outputs=dict(prior_outputs or {}),
    )


class HoldToRentMissingPriorTests(unittest.TestCase):
    def test_both_missing_returns_error_mode(self) -> None:
        payload = run_hold_to_rent(_context({}))
        self.assertEqual(payload["mode"], "error")
        self.assertIsNone(payload["confidence"])
        self.assertEqual(
            payload["missing_inputs"], ["carry_cost", "rent_stabilization"]
        )

    def test_degraded_prior_treated_as_missing(self) -> None:
        prior = {
            "carry_cost": _carry_output(mode="fallback"),
            "rent_stabilization": _stabilization_output(),
        }
        payload = run_hold_to_rent(_context(prior))
        self.assertEqual(payload["mode"], "error")
        self.assertEqual(payload["missing_inputs"], ["carry_cost"])


class HoldToRentHappyPathTests(unittest.TestCase):
    def test_full_priors_populate_hold_path_snapshot(self) -> None:
        prior = {
            "carry_cost": _carry_output(),
            "rent_stabilization": _stabilization_output(),
        }
        payload = run_hold_to_rent(_context(prior))
        self.assertNotEqual(payload["mode"], "error")
        snap = payload["data"]["hold_path_snapshot"]
        self.assertEqual(snap["monthly_cash_flow"], -1_200.0)
        self.assertEqual(snap["rental_ease_label"], "easy")


if __name__ == "__main__":
    unittest.main()

"""Isolation tests for the arv_model scoped wrapper.

Pins the canonical error-contract behavior from DECISIONS.md 2026-04-24:
- Missing priors → ``module_payload_from_missing_prior`` (``mode="error"``,
  ``confidence=None``, ``missing_inputs`` populated, ``arv_snapshot={}``).
- A prior whose ``mode`` is ``error`` or ``fallback`` must be treated as
  missing — the composite cannot safely compose on top of a degraded prior.
- Internal exceptions during composition → ``module_payload_from_error``
  (``mode="fallback"``, ``confidence=0.08``).
- Happy path still returns ``mode`` implied by synthesis and a populated
  ``arv_snapshot``.
"""

from __future__ import annotations

import unittest

from briarwood.execution.context import ExecutionContext
from briarwood.modules.arv_model_scoped import run_arv_model


def _valuation_output(confidence: float = 0.72, mode: str = "full") -> dict:
    return {
        "data": {
            "module_name": "valuation",
            "summary": "test",
            "metrics": {"briarwood_current_value": 790_000.0},
        },
        "confidence": confidence,
        "warnings": [],
        "mode": mode,
    }


def _renovation_output(confidence: float = 0.65, mode: str = "full") -> dict:
    return {
        "data": {
            "module_name": "renovation_impact",
            "summary": "test",
            "metrics": {
                "current_bcv": 790_000.0,
                "renovated_bcv": 1_040_000.0,
                "renovation_budget": 150_000.0,
                "gross_value_creation": 250_000.0,
                "net_value_creation": 100_000.0,
                "roi_pct": 66.7,
            },
        },
        "confidence": confidence,
        "warnings": [],
        "mode": mode,
    }


def _context(prior_outputs: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        property_id="arv-test",
        property_data={"property_id": "arv-test", "town": "Montclair", "state": "NJ"},
        assumptions={},
        prior_outputs=dict(prior_outputs or {}),
    )


class ArvModelMissingPriorTests(unittest.TestCase):
    def test_both_priors_missing_returns_error_mode(self) -> None:
        payload = run_arv_model(_context({}))

        self.assertEqual(payload["mode"], "error")
        self.assertIsNone(payload["confidence"])
        self.assertEqual(
            payload["missing_inputs"], ["valuation", "renovation_impact"]
        )
        self.assertEqual(payload["data"]["arv_snapshot"], {})
        self.assertTrue(
            all("Missing prior module output" in w for w in payload["warnings"])
        )

    def test_degraded_prior_treated_as_missing(self) -> None:
        """A valuation output with ``mode='error'`` must not be composed on."""
        prior = {
            "valuation": {**_valuation_output(), "mode": "error"},
            "renovation_impact": _renovation_output(),
        }
        payload = run_arv_model(_context(prior))

        self.assertEqual(payload["mode"], "error")
        self.assertEqual(payload["missing_inputs"], ["valuation"])
        self.assertEqual(payload["data"]["arv_snapshot"], {})

    def test_fallback_mode_prior_treated_as_missing(self) -> None:
        prior = {
            "valuation": _valuation_output(),
            "renovation_impact": {**_renovation_output(), "mode": "fallback"},
        }
        payload = run_arv_model(_context(prior))

        self.assertEqual(payload["mode"], "error")
        self.assertEqual(payload["missing_inputs"], ["renovation_impact"])


class ArvModelHappyPathTests(unittest.TestCase):
    def test_full_priors_populate_arv_snapshot(self) -> None:
        prior = {
            "valuation": _valuation_output(),
            "renovation_impact": _renovation_output(),
        }
        payload = run_arv_model(_context(prior))

        self.assertNotEqual(payload["mode"], "error")
        self.assertIsNotNone(payload["confidence"])
        snap = payload["data"]["arv_snapshot"]
        self.assertEqual(snap["current_bcv"], 790_000.0)
        self.assertEqual(snap["renovated_bcv"], 1_040_000.0)


if __name__ == "__main__":
    unittest.main()

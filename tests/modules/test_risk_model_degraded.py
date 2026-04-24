"""Pin the canonical error-contract for risk_model (DECISIONS.md 2026-04-24)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.modules.risk_model import run_risk_model


def _context() -> ExecutionContext:
    return ExecutionContext(
        property_id="risk-test",
        property_data={
            "property_id": "risk-test",
            "address": "1 Risk Ln",
            "town": "Montclair",
            "state": "NJ",
            "sqft": 2_100,
            "beds": 4,
            "baths": 2.5,
        },
        assumptions={},
    )


class RiskModelDegradedPathTests(unittest.TestCase):
    def test_internal_exception_returns_canonical_fallback(self) -> None:
        with patch(
            "briarwood.modules.risk_model.RiskConstraintsModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("boom")
            payload = run_risk_model(_context())

        self.assertEqual(payload["mode"], "fallback")
        self.assertAlmostEqual(payload["confidence"], 0.08)
        self.assertEqual(payload["data"]["module_name"], "risk_model")
        self.assertTrue(
            any("Risk-model fallback" in w for w in payload["warnings"])
        )


if __name__ == "__main__":
    unittest.main()

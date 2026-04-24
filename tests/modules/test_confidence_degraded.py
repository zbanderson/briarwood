"""Pin the canonical error-contract for the confidence rollup (DECISIONS.md 2026-04-24)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.modules.confidence import run_confidence


def _context() -> ExecutionContext:
    return ExecutionContext(
        property_id="confidence-test",
        property_data={
            "property_id": "confidence-test",
            "address": "1 Trust Ln",
            "town": "Montclair",
            "state": "NJ",
            "sqft": 2_100,
            "beds": 4,
            "baths": 2.5,
            "purchase_price": 790_000,
        },
        assumptions={},
    )


class ConfidenceDegradedPathTests(unittest.TestCase):
    def test_internal_exception_returns_canonical_fallback(self) -> None:
        with patch(
            "briarwood.modules.confidence.PropertyDataQualityModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("boom")
            payload = run_confidence(_context())

        self.assertEqual(payload["mode"], "fallback")
        self.assertAlmostEqual(payload["confidence"], 0.08)
        self.assertEqual(payload["data"]["module_name"], "confidence")
        self.assertTrue(
            any("Confidence fallback" in w for w in payload["warnings"])
        )


if __name__ == "__main__":
    unittest.main()

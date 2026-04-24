"""Pin the canonical error-contract for unit_income_offset (DECISIONS.md 2026-04-24)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.modules.unit_income_offset import run_unit_income_offset


def _context() -> ExecutionContext:
    return ExecutionContext(
        property_id="uio-test",
        property_data={
            "property_id": "uio-test",
            "address": "1 ADU Ln",
            "town": "Montclair",
            "state": "NJ",
            "sqft": 2_100,
            "beds": 4,
            "baths": 2.5,
        },
        assumptions={},
    )


class UnitIncomeOffsetDegradedPathTests(unittest.TestCase):
    def test_internal_exception_returns_canonical_fallback(self) -> None:
        with patch(
            "briarwood.modules.unit_income_offset.ComparableSalesModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("boom")
            payload = run_unit_income_offset(_context())

        self.assertEqual(payload["mode"], "fallback")
        self.assertAlmostEqual(payload["confidence"], 0.08)
        self.assertEqual(payload["data"]["module_name"], "unit_income_offset")
        self.assertTrue(
            any("Unit-income-offset fallback" in w for w in payload["warnings"])
        )


if __name__ == "__main__":
    unittest.main()

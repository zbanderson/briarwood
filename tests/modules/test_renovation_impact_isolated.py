"""Isolation tests for the renovation_impact scoped wrapper.

Pins the canonical error-contract behavior from DECISIONS.md 2026-04-24:
internal exceptions must degrade to a ``module_payload_from_error`` fallback
rather than propagating.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.modules.renovation_impact_scoped import run_renovation_impact


def _context() -> ExecutionContext:
    return ExecutionContext(
        property_id="reno-impact-test",
        property_data={
            "property_id": "reno-impact-test",
            "address": "1 Reno Ln",
            "town": "Montclair",
            "state": "NJ",
            "sqft": 2_100,
            "beds": 4,
            "baths": 2.5,
        },
        assumptions={},
    )


class RenovationImpactDegradedPathTests(unittest.TestCase):
    def test_internal_exception_returns_canonical_fallback(self) -> None:
        """When RenovationScenarioModule raises, the wrapper must not propagate."""

        with patch(
            "briarwood.modules.renovation_impact_scoped.RenovationScenarioModule"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("boom")
            payload = run_renovation_impact(_context())

        self.assertEqual(payload["mode"], "fallback")
        self.assertAlmostEqual(payload["confidence"], 0.08)
        self.assertEqual(payload["data"]["module_name"], "renovation_impact")
        self.assertEqual(payload["data"]["metrics"], {})
        self.assertTrue(
            any("Renovation-impact fallback" in w for w in payload["warnings"]),
            f"Expected canonical fallback prefix in warnings; got {payload['warnings']!r}",
        )


if __name__ == "__main__":
    unittest.main()

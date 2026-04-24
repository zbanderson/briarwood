"""Pin the canonical error-contract for town_development_index (DECISIONS.md 2026-04-24).

The ``_empty_payload`` branches for "no town/state" and "no feeds" remain the
primary degraded path; only unexpected internal exceptions go through the new
``module_payload_from_error`` fallback.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.modules.town_development_index import run_town_development_index


def _context() -> ExecutionContext:
    return ExecutionContext(
        property_id="tdi-test",
        property_data={
            "property_id": "tdi-test",
            "town": "Montclair",
            "state": "NJ",
        },
    )


class TownDevelopmentIndexDegradedPathTests(unittest.TestCase):
    def test_internal_exception_returns_canonical_fallback(self) -> None:
        with patch(
            "briarwood.modules.town_development_index.feeds_for_town"
        ) as mock_feeds:
            mock_feeds.side_effect = RuntimeError("boom")
            payload = run_town_development_index(_context())

        self.assertEqual(payload["mode"], "fallback")
        self.assertAlmostEqual(payload["confidence"], 0.08)
        self.assertEqual(payload["data"]["module_name"], "town_development_index")
        self.assertTrue(
            any("Town-development-index fallback" in w for w in payload["warnings"])
        )


if __name__ == "__main__":
    unittest.main()

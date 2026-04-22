"""Regression tests for the analysis cache-key components.

NEW-V-001 from VERIFICATION_REPORT.md: the scoped and legacy_fallback
execution paths produce materially different ``UnifiedIntelligenceOutput``
for the same property. Before this fix, ``build_cache_key`` did not include
``execution_mode``, so whichever path ran first won the shared cache entry
until TTL expiry.
"""

from __future__ import annotations

import unittest

from briarwood.orchestrator import build_cache_key
from briarwood.routing_schema import ParserOutput


def _parser_output() -> ParserOutput:
    return ParserOutput(
        intent_type="buy_decision",
        analysis_depth="snapshot",
        question_focus=["should_i_buy"],
        occupancy_type="unknown",
        exit_options=["unknown"],
        confidence=0.75,
        missing_inputs=[],
    )


class CacheKeyExecutionModeTests(unittest.TestCase):
    def test_scoped_and_legacy_fallback_produce_distinct_keys(self) -> None:
        """NEW-V-001: same property + same routing + same assumptions but
        different ``execution_mode`` must not collide in the synthesis cache."""
        parser_output = _parser_output()
        property_data = {
            "property_id": "prop-1",
            "beds": 3,
            "sqft": 1_800,
            "purchase_price": 750_000,
            "taxes": 12_500,
        }

        scoped_key = build_cache_key(property_data, parser_output, execution_mode="scoped")
        legacy_key = build_cache_key(property_data, parser_output, execution_mode="legacy_fallback")

        self.assertNotEqual(scoped_key, legacy_key)

    def test_same_execution_mode_is_stable(self) -> None:
        parser_output = _parser_output()
        property_data = {"property_id": "prop-1", "beds": 3}

        self.assertEqual(
            build_cache_key(property_data, parser_output, execution_mode="scoped"),
            build_cache_key(property_data, parser_output, execution_mode="scoped"),
        )

    def test_missing_execution_mode_raises(self) -> None:
        """No silent default — callers must pass ``execution_mode`` explicitly."""
        parser_output = _parser_output()
        with self.assertRaises(TypeError):
            build_cache_key({"property_id": "prop-1"}, parser_output)  # type: ignore[call-arg]

    def test_none_execution_mode_raises(self) -> None:
        """Explicit ``None`` must not silently succeed."""
        parser_output = _parser_output()
        with self.assertRaises(ValueError):
            build_cache_key(
                {"property_id": "prop-1"},
                parser_output,
                execution_mode=None,  # type: ignore[arg-type]
            )

    def test_unknown_execution_mode_raises(self) -> None:
        parser_output = _parser_output()
        with self.assertRaises(ValueError):
            build_cache_key(
                {"property_id": "prop-1"},
                parser_output,
                execution_mode="hybrid",
            )


if __name__ == "__main__":
    unittest.main()

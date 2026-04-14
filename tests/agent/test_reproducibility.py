"""Analysis mode is deterministic with warm caches.

Two consecutive decision-mode runs on the same property produce identical
decision_stance, primary_value_source, and value_position. This is the
Phase A reproducibility gate.
"""

from __future__ import annotations

import unittest

from briarwood.agent.tools import analyze_property


class AnalysisReproducibilityTests(unittest.TestCase):
    def test_decision_fields_are_byte_identical_on_warm_cache(self) -> None:
        a = analyze_property("526-west-end-ave")
        b = analyze_property("526-west-end-ave")
        for field in ("decision_stance", "primary_value_source", "value_position"):
            self.assertEqual(a[field], b[field], f"mismatch on {field}")


if __name__ == "__main__":
    unittest.main()

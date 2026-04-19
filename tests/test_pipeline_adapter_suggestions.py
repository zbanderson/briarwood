"""Slot-derived follow-up chips (Step 8).

Tests `_slot_derived_chips` and the three tier helpers that blend slot chips
over hardcoded tier defaults. The guarantees we pin:

1. A populated slot produces its expected chip.
2. Empty slots produce no slot-derived chips — tier defaults carry through.
3. Slot chips come first in the blended output (they're freshly relevant).
4. The blended list is dedup'd and capped at 4.
"""

from __future__ import annotations

import unittest

from api.pipeline_adapter import (
    _blend_chips,
    _slot_derived_chips,
    _suggestions_for_browse,
    _suggestions_for_decision,
    _suggestions_for_tier,
)
from briarwood.agent.router import AnswerType
from briarwood.agent.session import Session


def _session() -> Session:
    return Session()


class SlotDerivedChipsTests(unittest.TestCase):
    def test_empty_session_produces_no_chips(self) -> None:
        self.assertEqual(_slot_derived_chips(_session()), [])

    def test_risk_view_surfaces_top_risk_chip(self) -> None:
        s = _session()
        s.last_risk_view = {
            "key_risks": ["Flood-zone exposure", "Thin comp set"],
        }
        chips = _slot_derived_chips(s)
        self.assertIn("Tell me more about Flood-zone exposure", chips)

    def test_comps_preview_with_remainder_adds_show_remaining_chip(self) -> None:
        s = _session()
        s.last_comps_preview = {
            "count": 7,
            "comps": [{"property_id": f"p{i}"} for i in range(3)],
        }
        chips = _slot_derived_chips(s)
        self.assertIn("Show me the remaining 4 comps", chips)

    def test_comps_preview_with_all_displayed_omits_chip(self) -> None:
        s = _session()
        s.last_comps_preview = {
            "count": 3,
            "comps": [{"property_id": f"p{i}"} for i in range(3)],
        }
        chips = _slot_derived_chips(s)
        self.assertFalse(any("remaining" in c for c in chips))

    def test_projection_view_adds_price_cut_chip(self) -> None:
        s = _session()
        s.last_projection_view = {
            "bear_case_value": 780000,
            "base_case_value": 820000,
            "bull_case_value": 870000,
        }
        chips = _slot_derived_chips(s)
        self.assertIn("What would a 10% price cut do?", chips)

    def test_town_summary_with_docs_adds_chip(self) -> None:
        s = _session()
        s.last_town_summary = {"doc_count": 5, "town": "Belmar"}
        chips = _slot_derived_chips(s)
        self.assertIn("What's driving the town outlook?", chips)

    def test_town_summary_with_no_docs_omits_chip(self) -> None:
        s = _session()
        s.last_town_summary = {"doc_count": 0, "town": "Belmar"}
        chips = _slot_derived_chips(s)
        self.assertNotIn("What's driving the town outlook?", chips)

    def test_rent_outlook_with_monthly_rent_adds_chip(self) -> None:
        s = _session()
        s.last_rent_outlook_view = {"monthly_rent": 3200}
        chips = _slot_derived_chips(s)
        self.assertIn("What's the cash-on-cash if I rent it?", chips)

    def test_rent_outlook_with_break_even_adds_workability_chip(self) -> None:
        s = _session()
        s.last_rent_outlook_view = {"monthly_rent": 3200, "break_even_rent": 5900}
        chips = _slot_derived_chips(s)
        self.assertIn("What rent would make this work?", chips)

    def test_strategy_path_with_best_path_adds_chip(self) -> None:
        s = _session()
        s.last_strategy_view = {"best_path": "long_hold_rent"}
        chips = _slot_derived_chips(s)
        self.assertIn("Walk through the recommended path", chips)

    def test_value_thesis_with_drivers_adds_chip(self) -> None:
        s = _session()
        s.last_value_thesis_view = {"value_drivers": ["beach proximity"]}
        chips = _slot_derived_chips(s)
        self.assertIn("What are the key value drivers?", chips)

    def test_cma_rows_add_fair_value_chip(self) -> None:
        s = _session()
        s.last_cma_table = {"rows": [{"address": "1302 L Street"}]}
        chips = _slot_derived_chips(s)
        self.assertIn("Which comps actually fed fair value?", chips)

    def test_multiple_slots_produce_multiple_chips(self) -> None:
        s = _session()
        s.last_risk_view = {"key_risks": ["Flood zone"]}
        s.last_projection_view = {"base_case_value": 820000}
        s.last_town_summary = {"doc_count": 4}
        chips = _slot_derived_chips(s)
        self.assertGreaterEqual(len(chips), 3)


class BlendChipsTests(unittest.TestCase):
    def test_slot_chips_come_before_fallback(self) -> None:
        blended = _blend_chips(["slot-a", "slot-b"], ["fb-1", "fb-2"])
        self.assertEqual(blended[:2], ["slot-a", "slot-b"])

    def test_dedup_across_sources(self) -> None:
        blended = _blend_chips(["a", "b"], ["b", "c"])
        self.assertEqual(blended, ["a", "b", "c"])

    def test_caps_at_limit(self) -> None:
        blended = _blend_chips(["a", "b", "c", "d", "e"], ["f"])
        self.assertEqual(len(blended), 4)
        self.assertEqual(blended, ["a", "b", "c", "d"])

    def test_drops_empty_strings(self) -> None:
        blended = _blend_chips(["", "a"], ["", "b"])
        self.assertEqual(blended, ["a", "b"])


class TierHelperIntegrationTests(unittest.TestCase):
    """Spot-check each tier helper picks up slot chips through its fallback."""

    def test_browse_prefers_slot_chip(self) -> None:
        s = _session()
        s.last_risk_view = {"key_risks": ["Zoning change"]}
        chips = _suggestions_for_browse("", None, session=s)
        self.assertEqual(chips[0], "Tell me more about Zoning change")

    def test_browse_with_property_suggests_live_cma_first_when_not_already_run(self) -> None:
        s = _session()
        s.current_property_id = "1008-14th-ave"
        s.last_answer_contract = "property_brief"
        focal = {"address_line": "1008 14th Avenue", "price": 767000}
        chips = _suggestions_for_browse("", focal, session=s)
        self.assertEqual(chips[0], "Run a live CMA with market comps")

    def test_decision_without_focal_uses_slot_chip_first(self) -> None:
        s = _session()
        s.last_comps_preview = {"count": 6, "comps": [{}, {}]}
        chips = _suggestions_for_decision(None, session=s)
        self.assertEqual(chips[0], "Show me the remaining 4 comps")

    def test_tier_with_focal_blends_slot_over_tier_defaults(self) -> None:
        s = _session()
        s.last_projection_view = {"base_case_value": 820000}
        focal = {"address_line": "1 Main", "price": 820000}
        chips = _suggestions_for_tier(AnswerType.RISK, focal, session=s)
        # Slot chip leads; tier defaults trail.
        self.assertEqual(chips[0], "What would a 10% price cut do?")
        # Cap still applies.
        self.assertLessEqual(len(chips), 4)

    def test_no_session_returns_legacy_defaults(self) -> None:
        # Legacy code-path (no session passed) must still produce chips —
        # required because the error branches of stream impls used to call
        # suggestions_for_* without session access.
        chips = _suggestions_for_tier(AnswerType.RISK, None, session=None)
        self.assertGreater(len(chips), 0)


if __name__ == "__main__":
    unittest.main()

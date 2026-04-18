"""Architectural invariants for the unified property model.

These are regression pins for the three-bug sweep (architecture_sweep plan).
Each test asserts a property that future refactors must not silently break:

- ``ask_price`` is a LISTING fact — identical across every handler for a pid.
- ``all_in_basis`` is a DERIVED field — distinct from ``ask_price`` when
  capex is applied (heavy lane, renovation override, explicit budget).
- Renovation overrides visibly move the basis, not the listing ask.
- Browse narration never emits placeholder ``?`` for missing fields.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from briarwood.agent.dispatch import handle_browse
from briarwood.agent.property_view import PropertyView
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session
from briarwood.agent.tools import PropertyBrief
from briarwood.opportunity_metrics import (
    calculate_net_opportunity_delta,
    infer_capex_amount,
)


_LISTING_SUMMARY = {
    "property_id": "1223-briarwood-rd",
    "address": "1223 Briarwood Rd",
    "town": "Belmar",
    "state": "NJ",
    "beds": 4,
    "baths": 2.5,
    "ask_price": 1_000_000,
    "bcv": 1_050_000,
    "pricing_view": "at ask",
}


def _unified(ask: float, basis: float, fair: float = 1_080_000) -> dict:
    """Fake unified output — value_position fields the loader reads."""
    return {
        "decision_stance": "conditional",
        "primary_value_source": "current_value",
        "trust_flags": [],
        "what_must_be_true": [],
        "key_risks": [],
        "value_position": {
            "fair_value_base": fair,
            "ask_price": ask,
            "all_in_basis": basis,
            "ask_premium_pct": round((ask - fair) / fair, 4),
            "basis_premium_pct": round((basis - fair) / fair, 4),
            "premium_discount_pct": round((basis - fair) / fair, 4),
            "value_low": fair * 0.95,
            "value_high": fair * 1.05,
        },
    }


class AskPriceInvariants(unittest.TestCase):
    """Bug B: ask_price must not diverge between handlers for the same pid."""

    def test_ask_price_equal_in_browse_and_decision(self) -> None:
        unified = _unified(ask=1_000_000, basis=1_000_000)
        with patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value=_LISTING_SUMMARY,
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=unified
        ):
            browse = PropertyView.load("1223-briarwood-rd", depth="browse")
            decision = PropertyView.load("1223-briarwood-rd", depth="decision")
        self.assertEqual(browse.ask_price, decision.ask_price)
        self.assertEqual(browse.ask_price, 1_000_000.0)

    def test_ask_price_pinned_to_listing_even_if_analysis_disagrees(self) -> None:
        """Bug B root cause: synthesis used to alias ask_price := all_in_basis.
        The loader now refuses to let that alias leak back."""
        tampered = _unified(ask=1_150_000, basis=1_150_000)  # both aliased to basis
        with patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value=_LISTING_SUMMARY,
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=tampered
        ):
            view = PropertyView.load("1223-briarwood-rd", depth="decision")
        self.assertEqual(view.ask_price, 1_000_000.0)  # listing, not the alias


class BasisDistinctnessInvariants(unittest.TestCase):
    """all_in_basis must be a named, distinct field — not a shadow label."""

    def test_all_in_basis_distinct_from_ask_when_capex_present(self) -> None:
        """capex_lane='heavy' → basis = ask + $150k. They must not compare equal."""
        prop = SimpleNamespace(
            purchase_price=1_000_000,
            repair_capex_budget=None,
            renovation_mode=None,
            capex_lane="heavy",
            condition_profile=None,
        )
        result = calculate_net_opportunity_delta(
            value_anchor=1_100_000, property_input=prop
        )
        self.assertEqual(result.purchase_price, 1_000_000.0)
        self.assertEqual(result.all_in_basis, 1_150_000.0)
        self.assertNotEqual(result.purchase_price, result.all_in_basis)

    def test_all_in_basis_equals_purchase_when_no_capex(self) -> None:
        prop = SimpleNamespace(
            purchase_price=1_000_000,
            repair_capex_budget=None,
            renovation_mode=None,
            capex_lane=None,
            condition_profile=None,
        )
        result = calculate_net_opportunity_delta(
            value_anchor=1_100_000, property_input=prop
        )
        self.assertEqual(result.all_in_basis, 1_000_000.0)


class RenovationOverrideInvariants(unittest.TestCase):
    """Bug C: 'if we renovate' must move the basis, not the listing ask."""

    def test_renovation_override_moves_basis_not_ask(self) -> None:
        prop = SimpleNamespace(
            purchase_price=1_000_000,
            repair_capex_budget=None,
            renovation_mode="will_renovate",
            capex_lane=None,
            condition_profile=None,
        )
        amount, source = infer_capex_amount(prop)
        self.assertEqual(amount, 150_000.0)
        self.assertEqual(source, "user_renovation_plan")

        result = calculate_net_opportunity_delta(
            value_anchor=1_100_000, property_input=prop
        )
        self.assertEqual(result.purchase_price, 1_000_000.0)  # listing ask unchanged
        self.assertEqual(result.all_in_basis, 1_150_000.0)  # basis up by $150k
        self.assertEqual(result.capex_source, "user_renovation_plan")

    def test_renovation_override_beats_condition_profile(self) -> None:
        """User intent ('will_renovate') dominates listing condition ('turnkey')."""
        prop = SimpleNamespace(
            purchase_price=None,
            repair_capex_budget=None,
            renovation_mode="will_renovate",
            capex_lane="light",
            condition_profile="turnkey",
        )
        amount, source = infer_capex_amount(prop)
        self.assertEqual(amount, 150_000.0)
        self.assertEqual(source, "user_renovation_plan")


class BrowseNarrationInvariants(unittest.TestCase):
    """Bug A: browse must never narrate placeholder ``?`` for missing fields."""

    def test_browse_never_shows_question_marks_when_beds_missing(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE,
            confidence=0.9,
            target_refs=["1223-briarwood-rd"],
            reason="browse",
        )
        brief = PropertyBrief(
            property_id="1223-briarwood-rd",
            address="1223 Briarwood Rd",
            town="Belmar",
            state="NJ",
            beds=None,
            baths=None,
            ask_price=1_000_000,
            pricing_view="at ask",
            analysis_depth_used="snapshot",
            recommendation="Buy if the price improves.",
            decision="buy",
            decision_stance="buy_if_price_improves",
            best_path="Proceed carefully.",
            key_value_drivers=["Ask sits below the fair value anchor"],
            key_risks=["Thin carry inputs"],
            trust_flags=["weak_town_context"],
            recommended_next_run="decision",
            next_questions=["should I buy this at the current ask?"],
            primary_value_source="current_value",
            fair_value_base=1_080_000,
            ask_premium_pct=-0.074,
        )
        with patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=brief,
        ), patch("briarwood.agent.dispatch.search_listings", return_value=[]):
            response = handle_browse(
                "tell me about 1223 briarwood", decision, Session(), llm=None
            )
        # Bug A: "?bd/?ba" placeholder — the exact symptom from the CLI trace.
        self.assertNotIn("?bd", response)
        self.assertNotIn("?ba", response)
        self.assertNotIn("? bedroom", response.lower())
        self.assertNotIn("? bathroom", response.lower())


if __name__ == "__main__":
    unittest.main()

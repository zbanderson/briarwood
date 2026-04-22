"""PropertyView: unified loader seam used by every property handler."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.agent.property_view import PropertyView


_SUMMARY = {
    "address": "1223 Briarwood Rd",
    "town": "Belmar",
    "state": "NJ",
    "beds": 4,
    "baths": 2.5,
    "ask_price": 1_000_000,
    "bcv": 1_050_000,
    "pricing_view": "at ask",
}


_UNIFIED = {
    "decision_stance": "conditional",
    "primary_value_source": "comps",
    "trust_flags": ["weak_town_context"],
    "what_must_be_true": ["rents hold", "no structural issues"],
    "key_risks": ["thin comp set"],
    "value_position": {
        # Post-Wave-1: ask_price in unified == listing ask; PropertyView still
        # pins it from summary.json regardless, so the invariant is enforced
        # at the loader seam, not at the synthesis seam.
        "ask_price": 1_000_000,
        "all_in_basis": 1_150_000,
        "fair_value_base": 1_080_000,
        "ask_premium_pct": -0.074,
        "basis_premium_pct": 0.065,
        "value_low": 1_000_000,
        "value_high": 1_160_000,
    },
}


class BrowseDepthTests(unittest.TestCase):
    def test_populates_only_listing_fields(self) -> None:
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=_SUMMARY
        ), patch("briarwood.agent.property_view.analyze_property") as analyzer:
            view = PropertyView.load("1223-briarwood-rd", depth="browse")

        analyzer.assert_not_called()
        self.assertEqual(view.address, "1223 Briarwood Rd")
        self.assertEqual(view.beds, 4)
        self.assertEqual(view.ask_price, 1_000_000.0)
        self.assertEqual(view.bcv, 1_050_000.0)

        # Analysis fields are None at browse depth — browse must never read them.
        self.assertIsNone(view.all_in_basis)
        self.assertIsNone(view.fair_value_base)
        self.assertIsNone(view.decision_stance)
        self.assertEqual(view.trust_flags, ())


class DecisionDepthTests(unittest.TestCase):
    def test_populates_listing_plus_analysis_fields(self) -> None:
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=_SUMMARY
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=_UNIFIED
        ):
            view = PropertyView.load("1223-briarwood-rd", depth="decision")

        self.assertEqual(view.ask_price, 1_000_000.0)
        self.assertEqual(view.all_in_basis, 1_150_000.0)
        self.assertEqual(view.fair_value_base, 1_080_000.0)
        self.assertEqual(view.decision_stance, "conditional")
        self.assertEqual(view.trust_flags, ("weak_town_context",))
        self.assertEqual(view.key_risks, ("thin comp set",))
        self.assertIs(view.unified, _UNIFIED)

    def test_basis_premium_falls_back_to_legacy_alias(self) -> None:
        legacy = {
            **_UNIFIED,
            "value_position": {
                **_UNIFIED["value_position"],
                "basis_premium_pct": None,
                "premium_discount_pct": 0.065,
            },
        }
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=_SUMMARY
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=legacy
        ):
            view = PropertyView.load("pid", depth="decision")
        self.assertEqual(view.basis_premium_pct, 0.065)


class InvariantTests(unittest.TestCase):
    """Regression pins for the three-bug architectural fix."""

    def test_ask_price_identical_across_depths(self) -> None:
        """Core invariant: ask_price is the listing fact at every depth."""
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=_SUMMARY
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=_UNIFIED
        ):
            browse = PropertyView.load("pid", depth="browse")
            decision = PropertyView.load("pid", depth="decision")
        self.assertEqual(browse.ask_price, decision.ask_price)

    def test_ask_price_pinned_to_summary_even_when_unified_disagrees(self) -> None:
        """Loader refuses to let the analysis layer rename the listing fact."""
        tampered = {
            **_UNIFIED,
            "value_position": {
                **_UNIFIED["value_position"],
                "ask_price": 1_150_000,  # aliased to all_in_basis — old bug
            },
        }
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=_SUMMARY
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=tampered
        ):
            view = PropertyView.load("pid", depth="decision")
        self.assertEqual(view.ask_price, 1_000_000.0)  # listing, not basis
        self.assertEqual(view.all_in_basis, 1_150_000.0)
        self.assertNotEqual(view.ask_price, view.all_in_basis)

    def test_explicit_ask_override_becomes_working_ask(self) -> None:
        """Turn-level ask overrides should keep the UI and analysis on one price."""
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=_SUMMARY
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=_UNIFIED
        ):
            view = PropertyView.load(
                "pid",
                depth="decision",
                overrides={"ask_price": 699_000.0},
            )
        self.assertEqual(view.ask_price, 699_000.0)
        self.assertEqual(view.overrides_applied, {"ask_price": 699_000.0})

    def test_overrides_carried_through(self) -> None:
        with patch(
            "briarwood.agent.property_view.get_property_summary", return_value=_SUMMARY
        ), patch(
            "briarwood.agent.property_view.analyze_property", return_value=_UNIFIED
        ) as analyzer:
            view = PropertyView.load(
                "pid",
                depth="decision",
                overrides={"mode": "renovated"},
            )
        analyzer.assert_called_once_with("pid", overrides={"mode": "renovated"})
        self.assertEqual(view.overrides_applied, {"mode": "renovated"})


if __name__ == "__main__":
    unittest.main()

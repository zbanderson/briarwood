"""Capex inference: user budget > renovation_mode > capex_lane > condition."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from briarwood.opportunity_metrics import calculate_net_opportunity_delta, infer_capex_amount


def _input(**overrides) -> SimpleNamespace:
    defaults = dict(
        repair_capex_budget=None,
        renovation_mode=None,
        capex_lane=None,
        condition_profile=None,
        purchase_price=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class InferCapexTests(unittest.TestCase):
    def test_user_budget_wins(self) -> None:
        amount, source = infer_capex_amount(_input(repair_capex_budget=75_000))
        self.assertEqual((amount, source), (75_000.0, "user_budget"))

    def test_will_renovate_beats_lane_and_condition(self) -> None:
        """renovation_mode is the 'what if we renovate' override path."""
        amount, source = infer_capex_amount(
            _input(renovation_mode="will_renovate", capex_lane="light", condition_profile="turnkey")
        )
        self.assertEqual((amount, source), (150_000.0, "user_renovation_plan"))

    def test_capex_lane_heavy(self) -> None:
        amount, source = infer_capex_amount(_input(capex_lane="heavy"))
        self.assertEqual((amount, source), (150_000.0, "inferred_lane"))

    def test_renovated_condition_is_zero_capex(self) -> None:
        amount, source = infer_capex_amount(_input(condition_profile="renovated"))
        self.assertEqual((amount, source), (0.0, "inferred_condition"))

    def test_unknown_returns_none(self) -> None:
        amount, source = infer_capex_amount(_input())
        self.assertEqual((amount, source), (None, "unknown"))


class NetOpportunityDeltaTests(unittest.TestCase):
    def test_renovation_mode_raises_all_in_basis_above_purchase(self) -> None:
        """Bug C invariant: 'if we renovate' must move the basis."""
        prop = _input(purchase_price=1_000_000, renovation_mode="will_renovate")
        result = calculate_net_opportunity_delta(value_anchor=1_100_000, property_input=prop)
        self.assertEqual(result.all_in_basis, 1_150_000.0)  # 1_000_000 + 150_000 reno
        self.assertEqual(result.capex_source, "user_renovation_plan")


if __name__ == "__main__":
    unittest.main()

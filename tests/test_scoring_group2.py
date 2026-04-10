"""Tests for Group 2: Confidence Signal Integrity changes to scoring.py."""
from __future__ import annotations

import unittest

from briarwood.decision_model.scoring import (
    _aggregate_category,
    _critical_input_penalty,
    _score_price_vs_comps,
    _score_ppsf_positioning,
    _score_historical_pricing,
    _score_scarcity_premium,
    _score_downside_protection,
    _score_replacement_cost,
    _score_renovation_upside,
    _score_dom_signal,
    _score_buyer_seller_balance,
    _score_location_momentum,
    _score_liquidity_risk,
    SubFactorScore,
)
from briarwood.decision_model.scoring_config import (
    DEFAULT_DECISION_MODEL_SETTINGS,
    NEUTRAL_SCORE,
    SUB_FACTOR_WEIGHTS,
)


# ── Group 2a: comp_confidence_score penalty in _critical_input_penalty ────────


class CompConfidenceScorePenaltyTests(unittest.TestCase):
    """Verify graduated comp_confidence_score penalty."""

    def _base_metrics(self) -> dict:
        """Minimal metrics with no penalties except what we're testing."""
        return {
            "income_support_ratio": 0.9,
            "rent_source_type": "actual",
            "financing_complete": True,
            "carrying_cost_complete": True,
            "comp_count": 5,
            "comp_confidence": 0.80,
            "condition_profile": "maintained",
            "repair_capex_budget": 10000,
            "town_low_confidence_flag": False,
        }

    def test_high_confidence_no_penalty(self) -> None:
        m = self._base_metrics()
        m["comp_confidence_score"] = 0.70
        penalty = _critical_input_penalty(m)
        self.assertAlmostEqual(penalty, 0.0)

    def test_medium_confidence_small_penalty(self) -> None:
        s = DEFAULT_DECISION_MODEL_SETTINGS
        m = self._base_metrics()
        m["comp_confidence_score"] = 0.42  # between low and medium threshold
        penalty = _critical_input_penalty(m)
        self.assertAlmostEqual(penalty, s.comp_confidence_score_medium_penalty)

    def test_low_confidence_larger_penalty(self) -> None:
        s = DEFAULT_DECISION_MODEL_SETTINGS
        m = self._base_metrics()
        m["comp_confidence_score"] = 0.20
        penalty = _critical_input_penalty(m)
        self.assertAlmostEqual(penalty, s.comp_confidence_score_low_penalty)

    def test_missing_confidence_no_crash(self) -> None:
        m = self._base_metrics()
        # comp_confidence_score not present at all
        penalty = _critical_input_penalty(m)
        self.assertAlmostEqual(penalty, 0.0)

    def test_exactly_at_medium_threshold_no_penalty(self) -> None:
        m = self._base_metrics()
        m["comp_confidence_score"] = DEFAULT_DECISION_MODEL_SETTINGS.comp_confidence_score_medium_threshold
        penalty = _critical_input_penalty(m)
        self.assertAlmostEqual(penalty, 0.0)


# ── Group 2b: weight redistribution dampening in _aggregate_category ──────────


class WeightRedistributionDampeningTests(unittest.TestCase):
    """Verify category score is pulled toward NEUTRAL when heavy redistribution occurs."""

    def _make_subfactor(self, name: str, score: float, weight: float) -> SubFactorScore:
        return SubFactorScore(
            name=name, question="", score=score, weight=weight,
            contribution=round(score * weight, 4), evidence="test", data_source="test",
        )

    def test_no_redistribution_no_dampening(self) -> None:
        """All 4 sub-factors scored → no dampening."""
        scored = [
            self._make_subfactor("price_vs_comps", 5.0, 0.30),
            self._make_subfactor("ppsf_positioning", 5.0, 0.20),
            self._make_subfactor("historical_pricing", 5.0, 0.25),
            self._make_subfactor("scarcity_premium", 5.0, 0.25),
        ]
        cat = _aggregate_category("Price Context", "price_context", scored, [])
        self.assertAlmostEqual(cat.score, 5.0, places=1)

    def test_moderate_redistribution_dampens(self) -> None:
        """2 of 4 sub-factors unscorable (50% weight redistributed) → dampening applied."""
        # Only price_vs_comps (0.30) and ppsf_positioning (0.20) scored
        scored = [
            self._make_subfactor("price_vs_comps", 5.0, 0.30),
            self._make_subfactor("ppsf_positioning", 5.0, 0.20),
            None,
            None,
        ]
        unscorable = ["historical_pricing", "scarcity_premium"]
        cat = _aggregate_category("Price Context", "price_context", scored, unscorable)
        # Without dampening would be 5.0. With dampening, should be pulled toward 3.0.
        self.assertLess(cat.score, 5.0)
        self.assertGreater(cat.score, NEUTRAL_SCORE)

    def test_heavy_redistribution_dampens_more(self) -> None:
        """3 of 4 sub-factors unscorable (75% weight) → heavy dampening."""
        scored = [
            self._make_subfactor("price_vs_comps", 5.0, 0.30),
            None,
            None,
            None,
        ]
        unscorable = ["ppsf_positioning", "historical_pricing", "scarcity_premium"]
        cat = _aggregate_category("Price Context", "price_context", scored, unscorable)
        self.assertLess(cat.score, 5.0)
        # Heavy dampening should pull more toward neutral than moderate
        self.assertGreater(cat.score, NEUTRAL_SCORE)

    def test_low_score_dampened_upward_toward_neutral(self) -> None:
        """When remaining sub-factor scores low and redistribution is heavy, score pulls up toward neutral."""
        scored = [
            self._make_subfactor("price_vs_comps", 1.0, 0.30),
            None,
            None,
            None,
        ]
        unscorable = ["ppsf_positioning", "historical_pricing", "scarcity_premium"]
        cat = _aggregate_category("Price Context", "price_context", scored, unscorable)
        # Should be pulled up toward 3.0 from 1.0
        self.assertGreater(cat.score, 1.0)


# ── Group 2c: NEUTRAL_SCORE → None for no-data sub-factors ───────────────────


class NeutralScoreToNoneTests(unittest.TestCase):
    """Verify that sub-factor functions return None (not NEUTRAL_SCORE) when data is absent."""

    def test_price_vs_comps_no_data(self) -> None:
        score, _, _ = _score_price_vs_comps({})
        self.assertIsNone(score)

    def test_ppsf_no_sqft(self) -> None:
        score, _, _ = _score_ppsf_positioning({})
        self.assertIsNone(score)

    def test_historical_pricing_no_data(self) -> None:
        score, _, _ = _score_historical_pricing({})
        self.assertIsNone(score)

    def test_scarcity_no_data(self) -> None:
        score, _, _ = _score_scarcity_premium({})
        self.assertIsNone(score)

    def test_downside_protection_no_data(self) -> None:
        score, _, _ = _score_downside_protection({})
        self.assertIsNone(score)

    def test_replacement_cost_no_data(self) -> None:
        score, _, _ = _score_replacement_cost({})
        self.assertIsNone(score)

    def test_renovation_upside_unknown_condition(self) -> None:
        score, _, _ = _score_renovation_upside({})
        self.assertIsNone(score)

    def test_dom_signal_no_data(self) -> None:
        score, _, _ = _score_dom_signal({})
        self.assertIsNone(score)

    def test_buyer_seller_balance_no_data(self) -> None:
        score, _, _ = _score_buyer_seller_balance({})
        self.assertIsNone(score)

    def test_location_momentum_no_data(self) -> None:
        score, _, _ = _score_location_momentum({})
        self.assertIsNone(score)

    def test_liquidity_risk_no_data(self) -> None:
        score, _, _ = _score_liquidity_risk({})
        self.assertIsNone(score)

    def test_ppsf_partial_data_keeps_neutral(self) -> None:
        """When ask_ppsf exists but no benchmark, should keep NEUTRAL_SCORE (not None)."""
        score, _, _ = _score_ppsf_positioning({"purchase_price": 500000, "sqft": 1500})
        self.assertIsNotNone(score)
        self.assertAlmostEqual(score, NEUTRAL_SCORE)

    def test_dom_signal_with_data_returns_score(self) -> None:
        """When DOM data exists, should return a real score."""
        score, _, _ = _score_dom_signal({"days_on_market": 10})
        self.assertIsNotNone(score)
        self.assertGreater(score, 3.0)


if __name__ == "__main__":
    unittest.main()

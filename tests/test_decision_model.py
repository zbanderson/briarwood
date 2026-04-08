"""Unit tests for briarwood.decision_model scoring and lens scoring.

Covers the audit-flagged gap (C3, 2026-04-08): decision_model/scoring.py
and lens_scoring.py previously had zero dedicated unit tests. Tests exercise
pure sub-factor scorers, category builders, boundary/clamping behavior,
recommendation tiers, and the pure lens helpers that operate on metrics dicts
or CategoryScore dicts directly. This avoids wiring a full AnalysisReport
fixture tree while still hitting the core math.
"""
from __future__ import annotations

import unittest

from briarwood.decision_model import lens_scoring, scoring
from briarwood.decision_model.scoring import (
    CategoryScore,
    SubFactorScore,
    _aggregate_category,
    _calculate_economic_support,
    _calculate_market_position,
    _calculate_optionality,
    _calculate_price_context,
    _calculate_risk_layer,
    _clamp,
    _conviction_adjustment,
    _critical_input_penalty,
    _lerp_score,
    _score_historical_pricing,
    _score_ppsf_positioning,
    _score_price_vs_comps,
    _score_scarcity_premium,
    _sf,
    get_recommendation_tier,
)
from briarwood.decision_model.scoring_config import MAX_SCORE, MIN_SCORE, SUB_FACTOR_WEIGHTS


class ClampAndLerpTests(unittest.TestCase):
    """Boundary/utility math."""

    def test_clamp_respects_min_max(self) -> None:
        self.assertAlmostEqual(_clamp(10.0), MAX_SCORE, places=6)
        self.assertAlmostEqual(_clamp(-5.0), MIN_SCORE, places=6)
        self.assertAlmostEqual(_clamp(3.2), 3.2, places=6)

    def test_clamp_exact_bounds(self) -> None:
        self.assertAlmostEqual(_clamp(MIN_SCORE), MIN_SCORE, places=6)
        self.assertAlmostEqual(_clamp(MAX_SCORE), MAX_SCORE, places=6)

    def test_lerp_interpolates(self) -> None:
        # Midpoint of [0, 10] mapped onto [1, 5] → 3.0
        self.assertAlmostEqual(_lerp_score(5.0, 0.0, 10.0, 1.0, 5.0), 3.0, places=6)

    def test_lerp_clamps_outside_range(self) -> None:
        self.assertAlmostEqual(_lerp_score(-100.0, 0.0, 10.0, 1.0, 5.0), 1.0, places=6)
        self.assertAlmostEqual(_lerp_score(100.0, 0.0, 10.0, 1.0, 5.0), 5.0, places=6)

    def test_lerp_handles_degenerate_range(self) -> None:
        self.assertAlmostEqual(_lerp_score(5.0, 10.0, 10.0, 2.0, 4.0), 2.0, places=6)


class RecommendationTierTests(unittest.TestCase):
    """Threshold table should map scores into Buy/Neutral/Avoid."""

    def test_buy_tier_boundary(self) -> None:
        tier, _ = get_recommendation_tier(3.30)
        self.assertEqual(tier, "Buy")

    def test_neutral_tier_boundary(self) -> None:
        tier, _ = get_recommendation_tier(2.50)
        self.assertEqual(tier, "Neutral")

    def test_avoid_tier(self) -> None:
        tier, _ = get_recommendation_tier(1.80)
        self.assertEqual(tier, "Avoid")

    def test_high_score_returns_buy(self) -> None:
        tier, action = get_recommendation_tier(4.95)
        self.assertEqual(tier, "Buy")
        self.assertTrue(action)  # non-empty


class SubFactorScorerTests(unittest.TestCase):
    """Direct tests on pure sub-factor functions (metrics dict in, tuple out)."""

    def test_price_vs_comps_deep_discount_maxes_out(self) -> None:
        score, _, raw = _score_price_vs_comps({"net_opportunity_delta_pct": 0.25})
        self.assertAlmostEqual(score, 5.0, places=2)
        self.assertAlmostEqual(raw, 25.0, places=2)

    def test_price_vs_comps_deep_overprice_floors(self) -> None:
        score, _, _ = _score_price_vs_comps({"net_opportunity_delta_pct": -0.30})
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_price_vs_comps_neutral_when_no_data(self) -> None:
        score, _, raw = _score_price_vs_comps({})
        self.assertAlmostEqual(score, 3.0, places=2)  # NEUTRAL_SCORE
        self.assertIsNone(raw)

    def test_price_vs_comps_falls_back_to_mispricing_pct(self) -> None:
        score, _, raw = _score_price_vs_comps({"mispricing_pct": 0.20})
        self.assertAlmostEqual(score, 5.0, places=2)
        self.assertAlmostEqual(raw, 20.0, places=2)

    def test_historical_pricing_strong_appreciation(self) -> None:
        score, _, _ = _score_historical_pricing({"inputs_trailing_3yr_cagr": 0.09})
        self.assertAlmostEqual(score, 5.0, places=2)

    def test_historical_pricing_steep_decline(self) -> None:
        score, _, _ = _score_historical_pricing({"inputs_trailing_3yr_cagr": -0.10})
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_historical_pricing_prefers_three_year_over_one_year(self) -> None:
        score_3yr, _, _ = _score_historical_pricing(
            {"inputs_trailing_3yr_cagr": 0.05, "zhvi_1yr_change": -0.10}
        )
        # 3yr at +5% should place in the healthy-appreciation band (>3%)
        self.assertGreaterEqual(score_3yr, 4.0)

    def test_scarcity_premium_high_and_low(self) -> None:
        high, _, _ = _score_scarcity_premium({"scarcity_support_score": 80})
        low, _, _ = _score_scarcity_premium({"scarcity_support_score": 20})
        self.assertAlmostEqual(high, 5.0, places=2)
        self.assertAlmostEqual(low, 1.0, places=2)

    def test_scarcity_premium_neutral_when_missing(self) -> None:
        score, _, _ = _score_scarcity_premium({})
        self.assertAlmostEqual(score, 3.0, places=2)

    def test_ppsf_positioning_neutral_without_sqft(self) -> None:
        score, _, _ = _score_ppsf_positioning({"purchase_price": 500_000, "bcv": 500_000})
        self.assertAlmostEqual(score, 3.0, places=2)

    def test_ppsf_positioning_prefers_ask_below_model(self) -> None:
        # ask ppsf $400, bcv ppsf $500 → model benchmark ~20% below → high score
        metrics = {"purchase_price": 400_000, "bcv": 500_000, "sqft": 1000}
        score, _, _ = _score_ppsf_positioning(metrics)
        self.assertGreaterEqual(score, 4.5)


class SfWrapperTests(unittest.TestCase):
    def test_sf_none_score_returns_none(self) -> None:
        self.assertIsNone(_sf("price_vs_comps", None, "", "", None, 0.3))

    def test_sf_clamps_and_records_contribution(self) -> None:
        sf = _sf("price_vs_comps", 9.0, "ev", "src", 1.0, 0.30)
        self.assertIsNotNone(sf)
        assert sf is not None  # for type narrowing
        self.assertAlmostEqual(sf.score, MAX_SCORE, places=6)
        self.assertAlmostEqual(sf.contribution, round(MAX_SCORE * 0.30, 4), places=6)


class CategoryAggregationTests(unittest.TestCase):
    def test_weight_redistribution_when_sub_factor_unscorable(self) -> None:
        # Build a price_context category with one sub-factor missing.
        # The remaining three should absorb the missing weight proportionally
        # and the final category score should equal the unweighted average
        # of the scored sub-factors (since the originals all shared weights
        # that still sum to 1.0 after redistribution).
        weights = SUB_FACTOR_WEIGHTS["price_context"]
        scored: list[SubFactorScore | None] = [
            SubFactorScore(
                name="price_vs_comps",
                question="",
                score=5.0,
                weight=weights["price_vs_comps"],
                contribution=0.0,
                evidence="",
                data_source="",
            ),
            SubFactorScore(
                name="ppsf_positioning",
                question="",
                score=4.0,
                weight=weights["ppsf_positioning"],
                contribution=0.0,
                evidence="",
                data_source="",
            ),
            SubFactorScore(
                name="historical_pricing",
                question="",
                score=3.0,
                weight=weights["historical_pricing"],
                contribution=0.0,
                evidence="",
                data_source="",
            ),
            None,  # scarcity_premium unscorable
        ]
        cat = _aggregate_category(
            "Price Context", "price_context", scored, ["scarcity_premium"]
        )
        self.assertTrue(cat.weight_redistributed)
        self.assertEqual(cat.unscored_factors, ["scarcity_premium"])
        # All three present sub-factors' weights should now sum to 1.0.
        total = sum(sf.weight for sf in cat.sub_factors)
        self.assertAlmostEqual(total, 1.0, places=6)
        # Score should be within [1.0, 5.0] and reflect the three present.
        self.assertGreaterEqual(cat.score, MIN_SCORE)
        self.assertLessEqual(cat.score, MAX_SCORE)

    def test_category_score_clamped_to_range(self) -> None:
        # Every sub-factor at max → category score at MAX_SCORE.
        weights = SUB_FACTOR_WEIGHTS["price_context"]
        scored: list[SubFactorScore | None] = [
            SubFactorScore(
                name=name,
                question="",
                score=MAX_SCORE,
                weight=weights[name],
                contribution=0.0,
                evidence="",
                data_source="",
            )
            for name in weights
        ]
        cat = _aggregate_category("Price Context", "price_context", scored, [])
        self.assertAlmostEqual(cat.score, MAX_SCORE, places=6)


class CategoryBuilderTests(unittest.TestCase):
    """_calculate_* builders: thin smoke tests that the category plumbing works
    end-to-end from a metrics dict."""

    def _fully_strong_metrics(self) -> dict:
        return {
            # price_context
            "net_opportunity_delta_pct": 0.22,
            "purchase_price": 500_000,
            "bcv": 700_000,
            "sqft": 1500,
            "inputs_trailing_3yr_cagr": 0.10,
            "scarcity_support_score": 85,
            # economic_support
            "income_support_ratio": 1.25,
            "price_to_rent": 10.0,
            "monthly_cash_flow": 500.0,
            "downside_burden": 0.3,
            "bear_case_value": 480_000,
            "ask_price": 500_000,
            "base_case_value": 600_000,
            # optionality
            "has_back_house": True,
            "adu_type": "detached",
            "reno_enabled": True,
            "reno_roi_pct": 0.25,
            "reno_net_value_creation": 120_000,
            "strategy_intent": "flexible",
            "lot_size": 0.25,
            # market_position
            "days_on_market": 5,
            "comp_count": 8,
            "market_momentum_score": 80,
            "liquidity_score": 80,
            "zhvi_1yr_change": 0.07,
            "zhvi_3yr_change": 0.15,
            "location_score": 80,
            # risk_layer
            "risk_score": 90.0,
            "flood_risk": "low",
            "condition_profile": "turnkey",
            "capex_lane": "light",
            "rental_ease_score": 80,
            "rent_source_type": "manual_input",
            "vacancy_rate": 0.04,
        }

    def test_price_context_strong_metrics_produce_high_score(self) -> None:
        cat = _calculate_price_context(self._fully_strong_metrics())
        self.assertIsInstance(cat, CategoryScore)
        self.assertGreaterEqual(cat.score, 4.0)

    def test_price_context_empty_metrics_produces_neutral_band(self) -> None:
        cat = _calculate_price_context({})
        # With no data, sub-factors return NEUTRAL_SCORE (3.0) and the
        # aggregate lands in the neutral band.
        self.assertAlmostEqual(cat.score, 3.0, delta=0.2)

    def test_all_five_category_builders_return_valid_scores(self) -> None:
        m = self._fully_strong_metrics()
        builders = [
            _calculate_price_context,
            _calculate_economic_support,
            _calculate_optionality,
            _calculate_market_position,
            _calculate_risk_layer,
        ]
        for build in builders:
            cat = build(m)
            with self.subTest(category=cat.category_name):
                self.assertGreaterEqual(cat.score, MIN_SCORE)
                self.assertLessEqual(cat.score, MAX_SCORE)


class CriticalInputPenaltyTests(unittest.TestCase):
    def test_no_penalty_when_all_inputs_present(self) -> None:
        m = {
            "income_support_ratio": 1.1,
            "rent_source_type": "manual_input",
            "financing_complete": True,
            "carrying_cost_complete": True,
            "comp_count": 6,
            "comp_confidence": 0.8,
            "condition_profile": "turnkey",
        }
        self.assertAlmostEqual(_critical_input_penalty(m), 0.0, places=6)

    def test_penalty_capped_at_0_45(self) -> None:
        # Every critical input missing → penalty hits ceiling.
        m: dict = {}
        self.assertAlmostEqual(_critical_input_penalty(m), 0.45, places=6)

    def test_missing_rent_accumulates_both_ratio_and_source_penalties(self) -> None:
        m = {
            "financing_complete": True,
            "carrying_cost_complete": True,
            "comp_count": 6,
            "condition_profile": "turnkey",
        }
        # income_support_ratio missing (+0.14) + rent_source_type missing (+0.12)
        self.assertAlmostEqual(_critical_input_penalty(m), 0.26, places=6)


class ConvictionAdjustmentTests(unittest.TestCase):
    def _cats(self, values: dict[str, float]) -> dict[str, CategoryScore]:
        return {
            name: CategoryScore(
                category_name=name,
                score=score,
                weight=0.2,
                contribution=score * 0.2,
            )
            for name, score in values.items()
        }

    def test_empty_categories_zero_adjustment(self) -> None:
        self.assertAlmostEqual(_conviction_adjustment({}, {}), 0.0, places=6)

    def test_strong_price_and_economic_rewards(self) -> None:
        cats = self._cats(
            {
                "price_context": 4.5,
                "economic_support": 4.0,
                "optionality": 3.0,
                "market_position": 3.0,
                "risk_layer": 3.0,
            }
        )
        adj = _conviction_adjustment(cats, {"net_opportunity_delta_pct": 0.15})
        # Strong price + econ combo (+0.14) and deep discount (+0.12) and
        # one >=4.2 category (not enough for 2x strong bonus) — adjust upward.
        self.assertGreater(adj, 0.0)

    def test_adjustment_clamped_on_both_sides(self) -> None:
        cats_weak = self._cats(
            {
                "price_context": 1.5,
                "economic_support": 1.8,
                "optionality": 1.8,
                "market_position": 1.8,
                "risk_layer": 1.8,
            }
        )
        adj = _conviction_adjustment(cats_weak, {"net_opportunity_delta_pct": -0.25})
        self.assertGreaterEqual(adj, -0.45)
        self.assertLessEqual(adj, 0.40)


class LensScoringTests(unittest.TestCase):
    """Pure lens helpers that do not need a full AnalysisReport."""

    def _cats(self, risk: float, market: float, price: float) -> dict[str, CategoryScore]:
        return {
            "risk_layer": CategoryScore("Risk", risk, 0.2, risk * 0.2),
            "market_position": CategoryScore("Market", market, 0.15, market * 0.15),
            "price_context": CategoryScore("Price", price, 0.25, price * 0.25),
        }

    def test_risk_assessment_inverts_strong_fundamentals_to_low_risk(self) -> None:
        # All categories strong (5.0) → risk_val = 6-5 = 1 → clamped to 1.0.
        score, narr = lens_scoring._risk_assessment(self._cats(5.0, 5.0, 5.0))
        self.assertAlmostEqual(score, 1.0, places=2)
        self.assertIn("Very Low Risk", narr)

    def test_risk_assessment_high_risk_when_fundamentals_weak(self) -> None:
        score, narr = lens_scoring._risk_assessment(self._cats(1.0, 1.0, 1.0))
        self.assertAlmostEqual(score, 5.0, places=2)
        self.assertIn("High Risk", narr)

    def test_risk_assessment_neutral_mid_band(self) -> None:
        score, _ = lens_scoring._risk_assessment(self._cats(3.0, 3.0, 3.0))
        self.assertAlmostEqual(score, 3.0, places=2)

    def test_risk_assessment_handles_missing_categories(self) -> None:
        # Missing categories fall back to 3.0 → score should be mid-band.
        score, _ = lens_scoring._risk_assessment({})
        self.assertAlmostEqual(score, 3.0, places=2)

    def test_lens_clamp(self) -> None:
        self.assertAlmostEqual(lens_scoring._clamp(10.0), 5.0, places=6)
        self.assertAlmostEqual(lens_scoring._clamp(-5.0), 1.0, places=6)
        self.assertAlmostEqual(lens_scoring._clamp(3.4), 3.4, places=6)

    def test_lens_get_coerces_none_to_default(self) -> None:
        self.assertAlmostEqual(lens_scoring._get({"x": None}, "x", default=7.0), 7.0, places=6)
        self.assertAlmostEqual(lens_scoring._get({"x": 2.5}, "x"), 2.5, places=6)
        self.assertAlmostEqual(lens_scoring._get({}, "missing", default=1.1), 1.1, places=6)


if __name__ == "__main__":
    unittest.main()

import unittest

from briarwood.claims.base import Confidence, Provenance
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.claims.verdict_with_comparison import (
    Comparison,
    ComparisonScenario,
    Subject,
    Verdict,
    VerdictWithComparisonClaim,
)
from briarwood.value_scout.patterns import uplift_dominance
from tests.claims.fixtures import belmar_house


def _build_claim(scenarios: list[ComparisonScenario], sqft: int = 1800) -> VerdictWithComparisonClaim:
    return VerdictWithComparisonClaim(
        subject=Subject(
            property_id="x",
            address="1 Test St",
            beds=3,
            baths=2.0,
            sqft=sqft,
            ask_price=650_000.0,
            status="active",
        ),
        verdict=Verdict(
            label="fair",
            headline="headline",
            basis_fmv=650_000.0,
            ask_vs_fmv_delta_pct=0.0,
            method="comparable_sales_v1",
            comp_count=len(scenarios),
            comp_radius_mi=0.5,
            comp_window_months=6,
            confidence=Confidence.from_score(0.8),
        ),
        bridge_sentence="bridge",
        comparison=Comparison(
            metric="price_per_sqft",
            unit="$/sqft",
            scenarios=scenarios,
            chart_rule="horizontal_bar_with_ranges",
        ),
        provenance=Provenance(),
    )


def _scenario(
    id: str,
    median: float,
    *,
    is_subject: bool = False,
    label: str | None = None,
    sample_size: int = 3,
) -> ComparisonScenario:
    return ComparisonScenario(
        id=id,
        label=label or id,
        metric_range=(median - 5, median + 5),
        metric_median=median,
        is_subject=is_subject,
        sample_size=sample_size,
    )


class UpliftDominanceFiresTests(unittest.TestCase):
    def test_fires_on_belmar_fixture(self) -> None:
        claim = build_verdict_with_comparison_claim(
            property_summary=belmar_house.property_summary(),
            parser_output=belmar_house.parser_output(),
            module_results=belmar_house.module_results(),
            interaction_trace=belmar_house.interaction_trace(),
        )
        insight = uplift_dominance.detect(claim)
        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.scenario_id, "renovated_plus_bath")
        self.assertIn("Renovated +bath", insight.headline)
        self.assertIn("/sqft", insight.reason)
        self.assertIn("Renovated, same config", insight.reason)
        self.assertIn(
            "comparison.scenarios[renovated_plus_bath].metric_median",
            insight.supporting_fields,
        )
        self.assertIn(
            "comparison.scenarios[renovated_same].metric_median",
            insight.supporting_fields,
        )

    def test_fires_on_minimal_synthetic_claim(self) -> None:
        claim = _build_claim(
            [
                _scenario("subject", 375.0, is_subject=True, label="Subject config"),
                _scenario(
                    "renovated_same", 400.0, label="Renovated, same config"
                ),
                _scenario(
                    "renovated_plus_bath", 505.0, label="Renovated +bath"
                ),
            ]
        )
        insight = uplift_dominance.detect(claim)
        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.scenario_id, "renovated_plus_bath")


class UpliftDominanceDoesNotFireTests(unittest.TestCase):
    def test_no_fire_when_only_one_non_subject_scenario(self) -> None:
        claim = _build_claim(
            [
                _scenario("subject", 375.0, is_subject=True),
                _scenario("renovated_plus_bath", 600.0),
            ]
        )
        self.assertIsNone(uplift_dominance.detect(claim))

    def test_no_fire_when_no_subject_scenario(self) -> None:
        claim = _build_claim(
            [
                _scenario("renovated_same", 400.0),
                _scenario("renovated_plus_bath", 500.0),
            ]
        )
        self.assertIsNone(uplift_dominance.detect(claim))

    def test_no_fire_when_all_uplifts_non_positive(self) -> None:
        claim = _build_claim(
            [
                _scenario("subject", 400.0, is_subject=True),
                _scenario("renovated_same", 400.0),
                _scenario("renovated_plus_bath", 390.0),
            ]
        )
        self.assertIsNone(uplift_dominance.detect(claim))

    def test_no_fire_when_winner_below_ratio_threshold(self) -> None:
        # Tight uplifts across both paths — neither clears ratio=1.0.
        # same: uplift_total = 10 * 1800 = 18,000; investment = 100,000; ratio 0.18
        # plus_bath: uplift_total = 20 * 1800 = 36,000; investment = 175,000; ratio 0.21
        claim = _build_claim(
            [
                _scenario("subject", 375.0, is_subject=True),
                _scenario("renovated_same", 385.0),
                _scenario("renovated_plus_bath", 395.0),
            ]
        )
        self.assertIsNone(uplift_dominance.detect(claim))

    def test_no_fire_when_margin_too_narrow(self) -> None:
        # Both paths exceed investment but dominance margin < 1.5x.
        # same:      130/sqft * 1800 = 234,000; investment 100,000; ratio 2.34
        # plus_bath: 180/sqft * 1800 = 324,000; investment 175,000; ratio 1.85
        # winner / runner = 2.34 / 1.85 = 1.26 → below 1.5 threshold.
        claim = _build_claim(
            [
                _scenario("subject", 375.0, is_subject=True),
                _scenario("renovated_same", 505.0),
                _scenario("renovated_plus_bath", 555.0),
            ]
        )
        self.assertIsNone(uplift_dominance.detect(claim))


class BelmarRatioSanityTests(unittest.TestCase):
    """Documents the specific ratios the pattern sees on the Belmar fixture.
    If these shift, someone is changing either the fixture, the placeholders,
    or the arithmetic — worth catching explicitly.
    """

    def test_belmar_winner_is_plus_bath(self) -> None:
        claim = build_verdict_with_comparison_claim(
            property_summary=belmar_house.property_summary(),
            parser_output=belmar_house.parser_output(),
            module_results=belmar_house.module_results(),
            interaction_trace=belmar_house.interaction_trace(),
        )
        insight = uplift_dominance.detect(claim)
        self.assertIsNotNone(insight)
        assert insight is not None

        # median(subject tier) = 375; plus_bath median 505 → uplift 130/sqft
        self.assertIn("$130/sqft", insight.reason)


if __name__ == "__main__":
    unittest.main()

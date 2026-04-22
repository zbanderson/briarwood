import unittest

from briarwood.claims.base import Confidence, Provenance
from briarwood.claims.verdict_with_comparison import (
    Comparison,
    ComparisonScenario,
    Subject,
    Verdict,
    VerdictWithComparisonClaim,
)
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.value_scout import scout_claim
from tests.claims.fixtures import belmar_house


class ScoutEntrypointTests(unittest.TestCase):
    def test_returns_insight_when_a_pattern_fires(self) -> None:
        claim = build_verdict_with_comparison_claim(
            property_summary=belmar_house.property_summary(),
            parser_output=belmar_house.parser_output(),
            module_results=belmar_house.module_results(),
            interaction_trace=belmar_house.interaction_trace(),
        )
        insight = scout_claim(claim)
        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.scenario_id, "renovated_plus_bath")

    def test_returns_none_when_no_pattern_matches(self) -> None:
        # Subject-only comparison: nothing for the uplift pattern to compare.
        claim = VerdictWithComparisonClaim(
            subject=Subject(
                property_id="x",
                address="1 Test St",
                beds=3,
                baths=2.0,
                sqft=1800,
                ask_price=650_000.0,
                status="active",
            ),
            verdict=Verdict(
                label="fair",
                headline="headline",
                basis_fmv=650_000.0,
                ask_vs_fmv_delta_pct=0.0,
                method="comparable_sales_v1",
                comp_count=3,
                comp_radius_mi=0.5,
                comp_window_months=6,
                confidence=Confidence.from_score(0.8),
            ),
            bridge_sentence="bridge",
            comparison=Comparison(
                metric="price_per_sqft",
                unit="$/sqft",
                scenarios=[
                    ComparisonScenario(
                        id="subject",
                        label="Subject",
                        metric_range=(350.0, 360.0),
                        metric_median=355.0,
                        is_subject=True,
                        sample_size=3,
                    )
                ],
                chart_rule="horizontal_bar_with_ranges",
            ),
            provenance=Provenance(),
        )
        self.assertIsNone(scout_claim(claim))


if __name__ == "__main__":
    unittest.main()

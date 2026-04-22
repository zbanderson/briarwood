import unittest

from briarwood.claims.base import Confidence, Provenance, Caveat, SurfacedInsight
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.claims.verdict_with_comparison import (
    Comparison,
    ComparisonScenario,
    Subject,
    Verdict,
    VerdictWithComparisonClaim,
)
from briarwood.editor import edit_claim
from briarwood.editor import checks
from briarwood.value_scout import scout_claim
from tests.claims.fixtures import belmar_house


def _scenario(
    scenario_id: str,
    median: float,
    *,
    is_subject: bool = False,
    label: str | None = None,
    sample_size: int = 5,
) -> ComparisonScenario:
    return ComparisonScenario(
        id=scenario_id,
        label=label or scenario_id,
        metric_range=(median - 5, median + 5),
        metric_median=median,
        is_subject=is_subject,
        sample_size=sample_size,
    )


def _build_claim(
    scenarios: list[ComparisonScenario],
    *,
    delta_pct: float = 0.0,
    label: str = "fair",
    emphasis_scenario_id: str | None = None,
    surfaced_insight: SurfacedInsight | None = None,
    caveats: list[Caveat] | None = None,
) -> VerdictWithComparisonClaim:
    return VerdictWithComparisonClaim(
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
            label=label,
            headline="headline",
            basis_fmv=650_000.0,
            ask_vs_fmv_delta_pct=delta_pct,
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
            emphasis_scenario_id=emphasis_scenario_id,
        ),
        caveats=caveats or [],
        provenance=Provenance(),
        surfaced_insight=surfaced_insight,
    )


class BelmarHappyPathTests(unittest.TestCase):
    """Belmar fixture + synthesis + scout must pass the editor cleanly."""

    def test_synthesis_only_passes(self) -> None:
        claim = build_verdict_with_comparison_claim(
            property_summary=belmar_house.property_summary(),
            parser_output=belmar_house.parser_output(),
            module_results=belmar_house.module_results(),
            interaction_trace=belmar_house.interaction_trace(),
        )
        result = edit_claim(claim)
        self.assertTrue(result.passed, msg=f"failures: {result.failures}")
        self.assertEqual(result.failures, [])

    def test_synthesis_plus_scout_with_emphasis_passes(self) -> None:
        claim = build_verdict_with_comparison_claim(
            property_summary=belmar_house.property_summary(),
            parser_output=belmar_house.parser_output(),
            module_results=belmar_house.module_results(),
            interaction_trace=belmar_house.interaction_trace(),
        )
        insight = scout_claim(claim)
        self.assertIsNotNone(insight)
        assert insight is not None
        claim = claim.model_copy(
            update={
                "surfaced_insight": insight,
                "comparison": claim.comparison.model_copy(
                    update={"emphasis_scenario_id": insight.scenario_id}
                ),
            }
        )
        result = edit_claim(claim)
        self.assertTrue(result.passed, msg=f"failures: {result.failures}")


class ScenarioCompletenessTests(unittest.TestCase):
    def test_zero_sample_size_fails(self) -> None:
        scenarios = [
            _scenario("subject", 375.0, is_subject=True, sample_size=5),
            _scenario("renovated_same", 400.0, sample_size=0),
        ]
        claim = _build_claim(scenarios)
        result = edit_claim(claim)
        self.assertFalse(result.passed)
        self.assertTrue(
            any("renovated_same" in f and "sample_size" in f for f in result.failures)
        )


class VerdictDeltaCoherenceTests(unittest.TestCase):
    def test_label_must_match_delta_rule(self) -> None:
        # delta -10% → value_find; claim says "fair" → fails.
        scenarios = [_scenario("subject", 375.0, is_subject=True)]
        claim = _build_claim(scenarios, delta_pct=-10.0, label="fair")
        result = edit_claim(claim)
        self.assertFalse(result.passed)
        self.assertTrue(any("does not match delta" in f for f in result.failures))

    def test_value_find_at_minus_5_threshold(self) -> None:
        scenarios = [_scenario("subject", 375.0, is_subject=True)]
        claim = _build_claim(scenarios, delta_pct=-5.0, label="value_find")
        self.assertEqual(checks.check_verdict_delta_coherence(claim), [])

    def test_overpriced_at_plus_5_threshold(self) -> None:
        scenarios = [_scenario("subject", 375.0, is_subject=True)]
        claim = _build_claim(scenarios, delta_pct=5.0, label="overpriced")
        self.assertEqual(checks.check_verdict_delta_coherence(claim), [])

    def test_fair_within_band(self) -> None:
        scenarios = [_scenario("subject", 375.0, is_subject=True)]
        claim = _build_claim(scenarios, delta_pct=0.0, label="fair")
        self.assertEqual(checks.check_verdict_delta_coherence(claim), [])

    def test_insufficient_data_skips_coherence_check(self) -> None:
        # insufficient_data is an escape hatch; delta is meaningless here.
        scenarios = [_scenario("subject", 375.0, is_subject=True)]
        claim = _build_claim(scenarios, delta_pct=99.0, label="insufficient_data")
        self.assertEqual(checks.check_verdict_delta_coherence(claim), [])


class EmphasisCoherenceTests(unittest.TestCase):
    def test_emphasis_without_insight_fails(self) -> None:
        scenarios = [
            _scenario("subject", 375.0, is_subject=True),
            _scenario("renovated_same", 400.0),
        ]
        claim = _build_claim(scenarios, emphasis_scenario_id="renovated_same")
        result = edit_claim(claim)
        self.assertFalse(result.passed)
        self.assertTrue(
            any("no surfaced insight" in f for f in result.failures)
        )

    def test_emphasis_insight_mismatch_fails(self) -> None:
        scenarios = [
            _scenario("subject", 375.0, is_subject=True),
            _scenario("renovated_same", 400.0),
            _scenario("renovated_plus_bath", 500.0),
        ]
        insight = SurfacedInsight(
            headline="h",
            reason="r",
            supporting_fields=[],
            scenario_id="renovated_plus_bath",
        )
        claim = _build_claim(
            scenarios,
            emphasis_scenario_id="renovated_same",
            surfaced_insight=insight,
        )
        result = edit_claim(claim)
        self.assertFalse(result.passed)
        self.assertTrue(
            any("does not match surfaced" in f for f in result.failures)
        )

    def test_emphasis_matches_insight_passes(self) -> None:
        scenarios = [
            _scenario("subject", 375.0, is_subject=True),
            _scenario("renovated_plus_bath", 500.0),
        ]
        insight = SurfacedInsight(
            headline="h",
            reason="r",
            supporting_fields=[],
            scenario_id="renovated_plus_bath",
        )
        claim = _build_claim(
            scenarios,
            emphasis_scenario_id="renovated_plus_bath",
            surfaced_insight=insight,
        )
        self.assertEqual(checks.check_emphasis_coherence(claim), [])

    def test_no_emphasis_no_check(self) -> None:
        scenarios = [_scenario("subject", 375.0, is_subject=True)]
        claim = _build_claim(scenarios)
        self.assertEqual(checks.check_emphasis_coherence(claim), [])


class CaveatForGapTests(unittest.TestCase):
    def test_small_sample_without_caveat_fails(self) -> None:
        scenarios = [
            _scenario("subject", 375.0, is_subject=True, sample_size=5),
            _scenario("renovated_same", 400.0, sample_size=3),
        ]
        claim = _build_claim(scenarios)
        result = edit_claim(claim)
        self.assertFalse(result.passed)
        self.assertTrue(
            any("renovated_same" in f and "no caveat" in f for f in result.failures)
        )

    def test_small_sample_with_label_caveat_passes(self) -> None:
        scenarios = [
            _scenario("subject", 375.0, is_subject=True, sample_size=5),
            _scenario(
                "renovated_same", 400.0, label="Renovated, same config", sample_size=3
            ),
        ]
        caveats = [
            Caveat(
                text="Sample size for the 'Renovated, same config' scenario is below 5 (n=3).",
                severity="info",
                source="synthesis.verdict_with_comparison",
            )
        ]
        claim = _build_claim(scenarios, caveats=caveats)
        self.assertEqual(checks.check_caveat_for_gap(claim), [])

    def test_small_sample_with_id_caveat_passes(self) -> None:
        # Match on id if label isn't used in caveat text.
        scenarios = [
            _scenario("subject", 375.0, is_subject=True, sample_size=5),
            _scenario("renovated_same", 400.0, sample_size=3),
        ]
        caveats = [
            Caveat(
                text="renovated_same scenario relies on very few comps.",
                severity="info",
                source="synthesis.verdict_with_comparison",
            )
        ]
        claim = _build_claim(scenarios, caveats=caveats)
        self.assertEqual(checks.check_caveat_for_gap(claim), [])

    def test_large_sample_needs_no_caveat(self) -> None:
        scenarios = [
            _scenario("subject", 375.0, is_subject=True, sample_size=6),
            _scenario("renovated_same", 400.0, sample_size=8),
        ]
        claim = _build_claim(scenarios)
        self.assertEqual(checks.check_caveat_for_gap(claim), [])


class AggregationTests(unittest.TestCase):
    def test_multiple_failures_collected(self) -> None:
        # Two distinct problems: zero-sample scenario AND wrong label.
        scenarios = [
            _scenario("subject", 375.0, is_subject=True, sample_size=5),
            _scenario("renovated_same", 400.0, sample_size=0),
        ]
        claim = _build_claim(scenarios, delta_pct=-10.0, label="fair")
        result = edit_claim(claim)
        self.assertFalse(result.passed)
        self.assertGreaterEqual(len(result.failures), 2)

    def test_clean_claim_has_empty_failures_list(self) -> None:
        scenarios = [_scenario("subject", 375.0, is_subject=True, sample_size=5)]
        claim = _build_claim(scenarios)
        result = edit_claim(claim)
        self.assertTrue(result.passed)
        self.assertEqual(result.failures, [])


if __name__ == "__main__":
    unittest.main()

import unittest

from pydantic import ValidationError

from briarwood.claims import (
    Archetype,
    Caveat,
    Comparison,
    ComparisonScenario,
    Confidence,
    NextQuestion,
    Provenance,
    Subject,
    SurfacedInsight,
    Verdict,
    VerdictWithComparisonClaim,
)


def _subject() -> Subject:
    return Subject(
        property_id="p-1",
        address="1 Main St, Belmar NJ",
        beds=3,
        baths=2.0,
        sqft=1600,
        ask_price=900_000.0,
        status="active",
    )


def _verdict(label: str = "value_find", delta: float = -6.2) -> Verdict:
    return Verdict(
        label=label,
        headline="Priced $56,000 under fair market value (-6.2%).",
        basis_fmv=956_000.0,
        ask_vs_fmv_delta_pct=delta,
        method="comp_model_v3",
        comp_count=7,
        comp_radius_mi=0.5,
        comp_window_months=6,
        confidence=Confidence.from_score(0.78),
    )


def _scenarios() -> list[ComparisonScenario]:
    return [
        ComparisonScenario(
            id="subject",
            label="Subject config",
            metric_range=(520.0, 600.0),
            metric_median=560.0,
            is_subject=True,
            sample_size=7,
        ),
        ComparisonScenario(
            id="renovated_same",
            label="Renovated, same config",
            metric_range=(620.0, 700.0),
            metric_median=660.0,
            sample_size=6,
            flag="value_opportunity",
            flag_reason="20% median uplift over subject",
        ),
        ComparisonScenario(
            id="renovated_plus_bath",
            label="Renovated +bath",
            metric_range=(700.0, 820.0),
            metric_median=750.0,
            sample_size=4,
        ),
    ]


def _claim(**overrides) -> VerdictWithComparisonClaim:
    defaults = dict(
        subject=_subject(),
        verdict=_verdict(),
        bridge_sentence="Here's how this property compares against recent sales.",
        comparison=Comparison(
            metric="price_per_sqft",
            scenarios=_scenarios(),
            chart_rule="horizontal_bar_with_ranges",
            emphasis_scenario_id="renovated_same",
        ),
        provenance=Provenance(models_consulted=["current_value", "comparable_sales"]),
    )
    defaults.update(overrides)
    return VerdictWithComparisonClaim(**defaults)


class ArchetypeFieldTests(unittest.TestCase):
    def test_archetype_is_locked_to_verdict_with_comparison(self) -> None:
        claim = _claim()
        self.assertEqual(claim.archetype, Archetype.VERDICT_WITH_COMPARISON)

    def test_archetype_cannot_be_overridden_to_other_value(self) -> None:
        with self.assertRaises(ValidationError):
            _claim(archetype="option_comparison")  # type: ignore[arg-type]


class ComparisonValidatorTests(unittest.TestCase):
    def test_emphasis_scenario_must_exist(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            Comparison(
                metric="price_per_sqft",
                scenarios=_scenarios(),
                chart_rule="horizontal_bar_with_ranges",
                emphasis_scenario_id="does_not_exist",
            )
        self.assertIn("emphasis_scenario_id", str(ctx.exception))

    def test_emphasis_may_be_none(self) -> None:
        comp = Comparison(
            metric="price_per_sqft",
            scenarios=_scenarios(),
            chart_rule="horizontal_bar_with_ranges",
            emphasis_scenario_id=None,
        )
        self.assertIsNone(comp.emphasis_scenario_id)

    def test_chart_rule_is_fixed_to_horizontal_bar_with_ranges(self) -> None:
        with self.assertRaises(ValidationError):
            Comparison(
                metric="price_per_sqft",
                scenarios=_scenarios(),
                chart_rule="scatter",  # type: ignore[arg-type]
            )

    def test_metric_is_fixed_to_price_per_sqft(self) -> None:
        with self.assertRaises(ValidationError):
            Comparison(
                metric="price_per_bed",  # type: ignore[arg-type]
                scenarios=_scenarios(),
                chart_rule="horizontal_bar_with_ranges",
            )

    def test_empty_scenarios_allowed_at_type_level(self) -> None:
        # Editor enforces non-empty. Schema permits it so synthesis can build incrementally.
        comp = Comparison(
            metric="price_per_sqft",
            scenarios=[],
            chart_rule="horizontal_bar_with_ranges",
        )
        self.assertEqual(comp.scenarios, [])


class ComparisonScenarioValidatorTests(unittest.TestCase):
    def test_range_must_be_ordered_low_then_high(self) -> None:
        with self.assertRaises(ValidationError):
            ComparisonScenario(
                id="s",
                label="s",
                metric_range=(700.0, 600.0),
                metric_median=650.0,
                sample_size=3,
            )

    def test_flag_default_is_none(self) -> None:
        s = ComparisonScenario(
            id="s",
            label="s",
            metric_range=(100.0, 200.0),
            metric_median=150.0,
            sample_size=3,
        )
        self.assertEqual(s.flag, "none")
        self.assertIsNone(s.flag_reason)


class VerdictValidatorTests(unittest.TestCase):
    def test_label_must_be_known(self) -> None:
        with self.assertRaises(ValidationError):
            Verdict(
                label="great_buy",  # type: ignore[arg-type]
                headline="h",
                basis_fmv=1.0,
                ask_vs_fmv_delta_pct=0.0,
                method="m",
                comp_count=1,
                comp_radius_mi=0.0,
                comp_window_months=1,
                confidence=Confidence.from_score(0.5),
            )


class ClaimIntegrationTests(unittest.TestCase):
    def test_round_trip_via_model_dump_and_validate(self) -> None:
        claim = _claim()
        payload = claim.model_dump()
        restored = VerdictWithComparisonClaim.model_validate(payload)
        self.assertEqual(restored, claim)

    def test_optional_insight_and_extras_default_empty(self) -> None:
        claim = _claim()
        self.assertIsNone(claim.surfaced_insight)
        self.assertEqual(claim.caveats, [])
        self.assertEqual(claim.next_questions, [])

    def test_surfaced_insight_round_trips(self) -> None:
        insight = SurfacedInsight(
            headline="Renovated path shows strongest upside.",
            reason="$100/sqft uplift for ~$80k renovation.",
            supporting_fields=["comparison.scenarios[renovated_same].metric_median"],
        )
        claim = _claim(surfaced_insight=insight)
        self.assertEqual(claim.surfaced_insight, insight)

    def test_caveats_and_next_questions_round_trip(self) -> None:
        claim = _claim(
            caveats=[Caveat(text="Small +bath sample", severity="warning", source="synthesis")],
            next_questions=[NextQuestion(text="What if renovated?", routes_to="value_scout")],
        )
        self.assertEqual(len(claim.caveats), 1)
        self.assertEqual(len(claim.next_questions), 1)


if __name__ == "__main__":
    unittest.main()

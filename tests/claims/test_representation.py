import unittest
from typing import Any
from unittest.mock import MagicMock

from briarwood.claims.base import Confidence, Provenance, SurfacedInsight
from briarwood.claims.representation import RenderedClaim, render_claim
from briarwood.claims.representation.rubric import apply_rubric
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.claims.verdict_with_comparison import (
    Comparison,
    ComparisonScenario,
    Subject,
    Verdict,
    VerdictWithComparisonClaim,
)
from briarwood.value_scout import scout_claim
from tests.claims.fixtures import belmar_house


def _belmar_claim_with_scout() -> VerdictWithComparisonClaim:
    claim = build_verdict_with_comparison_claim(
        property_summary=belmar_house.property_summary(),
        parser_output=belmar_house.parser_output(),
        module_results=belmar_house.module_results(),
        interaction_trace=belmar_house.interaction_trace(),
    )
    insight = scout_claim(claim)
    if insight is None:
        return claim
    return claim.model_copy(
        update={
            "surfaced_insight": insight,
            "comparison": claim.comparison.model_copy(
                update={"emphasis_scenario_id": insight.scenario_id}
            ),
        }
    )


def _minimal_claim(
    *,
    label: str = "fair",
    headline: str = "Priced roughly at fair market value.",
    confidence: Confidence | None = None,
    scenarios: list[ComparisonScenario] | None = None,
    emphasis_scenario_id: str | None = None,
    surfaced_insight: SurfacedInsight | None = None,
) -> VerdictWithComparisonClaim:
    scenarios = scenarios or [
        ComparisonScenario(
            id="subject",
            label="Subject config",
            metric_range=(350.0, 400.0),
            metric_median=375.0,
            is_subject=True,
            sample_size=5,
        )
    ]
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
            headline=headline,
            basis_fmv=650_000.0,
            ask_vs_fmv_delta_pct=0.0,
            method="comparable_sales_v1",
            comp_count=len(scenarios),
            comp_radius_mi=0.5,
            comp_window_months=6,
            confidence=confidence or Confidence.from_score(0.95),
        ),
        bridge_sentence="Here's how this property compares.",
        comparison=Comparison(
            metric="price_per_sqft",
            unit="$/sqft",
            scenarios=scenarios,
            chart_rule="horizontal_bar_with_ranges",
            emphasis_scenario_id=emphasis_scenario_id,
        ),
        provenance=Provenance(),
        surfaced_insight=surfaced_insight,
    )


class RubricTests(unittest.TestCase):
    HEADLINE = "Priced $50,000 under fair market value (-7.1%)."

    def test_high_band_unchanged(self) -> None:
        out = apply_rubric(self.HEADLINE, Confidence.from_score(0.95), comp_count=8)
        self.assertEqual(out, self.HEADLINE)

    def test_medium_band_prepends_comp_count(self) -> None:
        out = apply_rubric(self.HEADLINE, Confidence.from_score(0.82), comp_count=8)
        self.assertTrue(out.startswith("Based on 8 comparable sales,"))
        # Rest of the sentence is preserved, only the first letter lowered.
        self.assertIn("priced $50,000 under fair market value", out)

    def test_low_band_prepends_best_estimate(self) -> None:
        out = apply_rubric(self.HEADLINE, Confidence.from_score(0.55), comp_count=5)
        self.assertTrue(out.startswith("Our best estimate is "))

    def test_very_low_band_prepends_hedge(self) -> None:
        out = apply_rubric(self.HEADLINE, Confidence.from_score(0.2), comp_count=3)
        self.assertTrue(out.startswith("We don't have high confidence here, but "))


class DeterministicFallbackTests(unittest.TestCase):
    """With llm=None the module must still produce a response."""

    def test_fallback_includes_headline_and_bridge_verbatim(self) -> None:
        claim = _minimal_claim()
        rendered = render_claim(claim, llm=None)
        self.assertIn(claim.verdict.headline, rendered.prose)
        self.assertIn(claim.bridge_sentence, rendered.prose)

    def test_fallback_mentions_surfaced_insight_reason(self) -> None:
        insight = SurfacedInsight(
            headline="Renovated +bath path shows the strongest upside.",
            reason="$130/sqft median uplift dominates the other path.",
            supporting_fields=[],
            scenario_id="renovated_plus_bath",
        )
        claim = _minimal_claim(surfaced_insight=insight)
        rendered = render_claim(claim, llm=None)
        self.assertIn("dominates the other path", rendered.prose)

    def test_fallback_applies_rubric_to_non_high_band(self) -> None:
        claim = _minimal_claim(confidence=Confidence.from_score(0.82))
        rendered = render_claim(claim, llm=None)
        # comp_count=1 by construction above
        self.assertIn("Based on 1 comparable sales,", rendered.prose)


class LLMRenderingTests(unittest.TestCase):
    def test_llm_prose_is_appended_after_headline_and_bridge(self) -> None:
        claim = _minimal_claim()
        prose_body = "The subject sits at $375/sqft with tight comp support."
        llm = _make_llm_returning(prose_body)
        rendered = render_claim(claim, llm=llm)
        self.assertIn(claim.verdict.headline, rendered.prose)
        self.assertIn(claim.bridge_sentence, rendered.prose)
        self.assertIn(prose_body, rendered.prose)
        idx_headline = rendered.prose.index(claim.verdict.headline)
        idx_body = rendered.prose.index(prose_body)
        self.assertLess(idx_headline, idx_body)


class ChartEventTests(unittest.TestCase):
    def test_chart_event_has_correct_kind_and_spec(self) -> None:
        claim = _belmar_claim_with_scout()
        rendered = render_claim(claim, llm=None)
        chart_evt = _find_chart(rendered.events)
        self.assertEqual(chart_evt["type"], "chart")
        self.assertEqual(chart_evt["kind"], "horizontal_bar_with_ranges")
        spec = chart_evt["spec"]
        self.assertEqual(spec["kind"], "horizontal_bar_with_ranges")
        self.assertEqual(spec["unit"], "$/sqft")

    def test_chart_spec_scenarios_mirror_claim(self) -> None:
        claim = _belmar_claim_with_scout()
        rendered = render_claim(claim, llm=None)
        spec = _find_chart(rendered.events)["spec"]
        ids = [s["id"] for s in spec["scenarios"]]
        self.assertEqual(ids, ["subject", "renovated_same", "renovated_plus_bath"])
        subject_row = spec["scenarios"][0]
        self.assertTrue(subject_row["is_subject"])
        low, high = claim.comparison.scenarios[0].metric_range
        self.assertEqual(subject_row["low"], float(low))
        self.assertEqual(subject_row["high"], float(high))

    def test_emphasis_scenario_id_flows_into_spec(self) -> None:
        claim = _belmar_claim_with_scout()
        rendered = render_claim(claim, llm=None)
        spec = _find_chart(rendered.events)["spec"]
        self.assertEqual(spec["emphasis_scenario_id"], "renovated_plus_bath")

    def test_emphasis_is_none_when_scout_did_not_fire(self) -> None:
        claim = _minimal_claim()
        rendered = render_claim(claim, llm=None)
        spec = _find_chart(rendered.events)["spec"]
        self.assertIsNone(spec["emphasis_scenario_id"])


class SuggestionsEventTests(unittest.TestCase):
    def test_suggestions_event_contains_next_question_texts(self) -> None:
        claim = _belmar_claim_with_scout()
        rendered = render_claim(claim, llm=None)
        suggestions_evt = _find_suggestions(rendered.events)
        self.assertEqual(suggestions_evt["type"], "suggestions")
        self.assertEqual(len(suggestions_evt["items"]), len(claim.next_questions))


class EndToEndBelmarTests(unittest.TestCase):
    def test_belmar_rendered_claim_has_prose_and_two_events(self) -> None:
        claim = _belmar_claim_with_scout()
        rendered = render_claim(claim, llm=None)
        self.assertIsInstance(rendered, RenderedClaim)
        self.assertTrue(rendered.prose)
        self.assertEqual(len(rendered.events), 2)
        kinds = {e["type"] for e in rendered.events}
        self.assertEqual(kinds, {"chart", "suggestions"})


# ─── Helpers ───────────────────────────────────────────────────────────


def _make_llm_returning(body: str) -> Any:
    """Build a minimal stub LLM that composer.complete_and_verify can use.

    complete_and_verify runs through _run_llm_with_verify → LLMClient.complete.
    Returning a MagicMock whose .complete() yields the body sidesteps the
    verifier machinery; structured_inputs is still required so the verifier
    report is present.
    """
    client = MagicMock()
    client.complete.return_value = body
    return client


def _find_chart(event_list: list[dict[str, Any]]) -> dict[str, Any]:
    for e in event_list:
        if e["type"] == "chart":
            return e
    raise AssertionError(f"no chart event in {event_list}")


def _find_suggestions(event_list: list[dict[str, Any]]) -> dict[str, Any]:
    for e in event_list:
        if e["type"] == "suggestions":
            return e
    raise AssertionError(f"no suggestions event in {event_list}")


if __name__ == "__main__":
    unittest.main()

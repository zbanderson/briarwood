import unittest

from briarwood.claims.archetypes import Archetype
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.claims.synthesis.templates import (
    BRIDGE_SENTENCE,
    DEFAULT_NEXT_QUESTIONS,
    VERDICT_HEADLINE,
)
from briarwood.claims.verdict_with_comparison import VerdictWithComparisonClaim
from tests.claims.fixtures import belmar_house


def _build(**overrides) -> VerdictWithComparisonClaim:
    kwargs = {
        "property_summary": belmar_house.property_summary(),
        "parser_output": belmar_house.parser_output(),
        "module_results": belmar_house.module_results(),
        "interaction_trace": belmar_house.interaction_trace(),
    }
    kwargs.update(overrides)
    return build_verdict_with_comparison_claim(**kwargs)


class SubjectMappingTests(unittest.TestCase):
    def test_subject_fields_flow_from_property_summary(self) -> None:
        claim = _build()
        self.assertEqual(claim.subject.property_id, belmar_house.SUBJECT_PROPERTY_ID)
        self.assertEqual(claim.subject.address, belmar_house.SUBJECT_ADDRESS)
        self.assertEqual(claim.subject.beds, belmar_house.SUBJECT_BEDS)
        self.assertEqual(claim.subject.baths, belmar_house.SUBJECT_BATHS)
        self.assertEqual(claim.subject.sqft, belmar_house.SUBJECT_SQFT)
        self.assertEqual(claim.subject.ask_price, belmar_house.SUBJECT_ASK)
        self.assertEqual(claim.subject.status, "active")

    def test_ask_price_falls_back_to_valuation_metric(self) -> None:
        summary = belmar_house.property_summary()
        summary.pop("purchase_price")
        claim = _build(property_summary=summary)
        # valuation.listing_ask_price carries the ask even without purchase_price
        self.assertEqual(claim.subject.ask_price, belmar_house.SUBJECT_ASK)


class VerdictTests(unittest.TestCase):
    def test_value_find_verdict_on_fixture(self) -> None:
        claim = _build()
        self.assertEqual(claim.verdict.label, "value_find")
        self.assertEqual(claim.verdict.basis_fmv, belmar_house.SUBJECT_FMV)
        # delta = (650 - 700) / 700 * 100 = -7.142857...
        self.assertAlmostEqual(
            claim.verdict.ask_vs_fmv_delta_pct, -7.142857, places=4
        )
        self.assertEqual(claim.verdict.method, "comparable_sales_v1")

    def test_headline_is_templated_from_delta(self) -> None:
        claim = _build()
        # Delta is ~$50,000 under FMV → "$50,000 under fair market value"
        self.assertIn("under fair market value", claim.verdict.headline)
        self.assertIn("$50,000", claim.verdict.headline)

    def test_fair_verdict_near_fmv(self) -> None:
        modules = belmar_house.module_results()
        modules["valuation"]["data"]["metrics"]["briarwood_current_value"] = (
            belmar_house.SUBJECT_ASK  # delta = 0%
        )
        claim = _build(module_results=modules)
        self.assertEqual(claim.verdict.label, "fair")
        self.assertEqual(
            claim.verdict.headline, VERDICT_HEADLINE["fair"]
        )

    def test_threshold_bands(self) -> None:
        # Pin the band edges on both sides of ±5% so a future refactor that
        # drifts the threshold gets caught.
        cases = [
            (-5.1, "value_find"),
            (-4.9, "fair"),
            (0.0, "fair"),
            (4.9, "fair"),
            (5.1, "overpriced"),
        ]
        for delta_pct, expected in cases:
            with self.subTest(delta_pct=delta_pct):
                modules = belmar_house.module_results()
                fmv = belmar_house.SUBJECT_ASK / (1.0 + delta_pct / 100.0)
                modules["valuation"]["data"]["metrics"][
                    "briarwood_current_value"
                ] = fmv
                claim = _build(module_results=modules)
                self.assertEqual(claim.verdict.label, expected)

    def test_insufficient_data_when_fmv_missing(self) -> None:
        modules = belmar_house.module_results()
        modules["valuation"]["data"]["metrics"].pop("briarwood_current_value")
        claim = _build(module_results=modules)
        self.assertEqual(claim.verdict.label, "insufficient_data")
        self.assertEqual(
            claim.verdict.headline, VERDICT_HEADLINE["insufficient_data"]
        )

    def test_confidence_band_derived_from_confidence_module(self) -> None:
        claim = _build()
        # 0.82 → medium band (>= 0.70, < 0.90)
        self.assertEqual(claim.verdict.confidence.band, "medium")
        self.assertAlmostEqual(claim.verdict.confidence.score, 0.82, places=4)


class ScenarioTests(unittest.TestCase):
    def test_three_tiers_assembled_from_comps(self) -> None:
        claim = _build()
        ids = [s.id for s in claim.comparison.scenarios]
        self.assertEqual(
            ids, ["subject", "renovated_same", "renovated_plus_bath"]
        )

    def test_subject_tier_is_marked_is_subject(self) -> None:
        claim = _build()
        by_id = {s.id: s for s in claim.comparison.scenarios}
        self.assertTrue(by_id["subject"].is_subject)
        self.assertFalse(by_id["renovated_same"].is_subject)
        self.assertFalse(by_id["renovated_plus_bath"].is_subject)

    def test_scenario_ranges_are_ordered_low_high(self) -> None:
        claim = _build()
        for scenario in claim.comparison.scenarios:
            low, high = scenario.metric_range
            self.assertLessEqual(low, high, msg=scenario.id)
            self.assertGreaterEqual(scenario.metric_median, low)
            self.assertLessEqual(scenario.metric_median, high)

    def test_sample_sizes_reflect_comp_counts(self) -> None:
        claim = _build()
        by_id = {s.id: s for s in claim.comparison.scenarios}
        # subject tier accepts any condition in the same layout — it overlaps
        # with renovated_same (both tiers contain the 3 renovated 3BR/2BA
        # comps) plus the 3 unrenovated 3BR/2BA comps.
        self.assertEqual(by_id["subject"].sample_size, 6)
        self.assertEqual(by_id["renovated_same"].sample_size, 3)
        self.assertEqual(by_id["renovated_plus_bath"].sample_size, 2)

    def test_missing_plus_bath_tier_drops_scenario_and_adds_caveat(self) -> None:
        # Strip out the +bath comps (3BR/3BA renovated) from the module output.
        modules = belmar_house.module_results()
        comps_output = modules["comparable_sales"]["payload"]
        filtered = [
            c
            for c in comps_output.comps_used
            if not (c.bathrooms == 3.0 and (c.condition_profile in {"renovated", "updated"}))
        ]
        modules["comparable_sales"]["payload"] = comps_output.model_copy(
            update={"comps_used": filtered, "comp_count": len(filtered)}
        )
        claim = _build(module_results=modules)
        ids = [s.id for s in claim.comparison.scenarios]
        self.assertNotIn("renovated_plus_bath", ids)
        caveat_texts = [c.text for c in claim.caveats]
        self.assertTrue(
            any("Renovated +bath" in t for t in caveat_texts),
            msg=f"expected +bath caveat in: {caveat_texts}",
        )

    def test_comparison_pins_metric_and_chart_rule(self) -> None:
        claim = _build()
        self.assertEqual(claim.comparison.metric, "price_per_sqft")
        self.assertEqual(claim.comparison.chart_rule, "horizontal_bar_with_ranges")
        self.assertEqual(claim.comparison.unit, "$/sqft")

    def test_emphasis_not_set_in_synthesis(self) -> None:
        # Value Scout owns emphasis; synthesis leaves it None.
        claim = _build()
        self.assertIsNone(claim.comparison.emphasis_scenario_id)


class CaveatTests(unittest.TestCase):
    def test_bridge_reasoning_flows_into_caveats(self) -> None:
        claim = _build()
        bridge_caveats = [
            c for c in claim.caveats if c.source == "comparable_sales_to_valuation"
        ]
        self.assertEqual(len(bridge_caveats), 1)
        self.assertEqual(bridge_caveats[0].severity, "info")

    def test_unfired_bridges_do_not_produce_caveats(self) -> None:
        claim = _build(interaction_trace=belmar_house.interaction_trace(include_bridge=False))
        bridge_caveats = [
            c for c in claim.caveats if c.source == "comparable_sales_to_valuation"
        ]
        self.assertEqual(bridge_caveats, [])


class ProvenanceTests(unittest.TestCase):
    def test_consulted_modules_listed(self) -> None:
        claim = _build()
        self.assertIn("valuation", claim.provenance.models_consulted)
        self.assertIn("comparable_sales", claim.provenance.models_consulted)
        self.assertIn("confidence", claim.provenance.models_consulted)

    def test_fired_bridges_listed(self) -> None:
        claim = _build()
        self.assertEqual(
            claim.provenance.bridges_fired, ["comparable_sales_to_valuation"]
        )


class ScaffoldingTests(unittest.TestCase):
    def test_archetype_pinned(self) -> None:
        claim = _build()
        self.assertEqual(claim.archetype, Archetype.VERDICT_WITH_COMPARISON)

    def test_bridge_sentence_is_the_template(self) -> None:
        claim = _build()
        self.assertEqual(claim.bridge_sentence, BRIDGE_SENTENCE)

    def test_next_questions_are_the_defaults(self) -> None:
        claim = _build()
        self.assertEqual(len(claim.next_questions), len(DEFAULT_NEXT_QUESTIONS))
        expected_routes = {q["routes_to"] for q in DEFAULT_NEXT_QUESTIONS}
        self.assertEqual(
            {q.routes_to for q in claim.next_questions}, expected_routes
        )

    def test_surfaced_insight_is_none_in_synthesis(self) -> None:
        # Scout fills this in later; synthesis alone leaves it unset.
        claim = _build()
        self.assertIsNone(claim.surfaced_insight)


if __name__ == "__main__":
    unittest.main()

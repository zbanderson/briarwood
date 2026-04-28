import unittest

from briarwood.agents.current_value import CurrentValueAgent
from briarwood.claims.synthesis import build_verdict_with_comparison_claim
from briarwood.decision_model.value_position import (
    PRICING_VIEW_BY_LABEL,
    classify_ask_vs_fmv_delta_pct,
    classify_bcv_vs_ask_delta_pct,
    classify_value_position,
)
from briarwood.editor.checks import check_verdict_delta_coherence
from tests.claims.fixtures import belmar_house


_LABEL_BY_PRICING_VIEW = {
    pricing_view: label
    for label, pricing_view in PRICING_VIEW_BY_LABEL.items()
    if label != "insufficient_data"
}


def _claim_for_ratio(ratio: float):
    modules = belmar_house.module_results()
    ask = belmar_house.SUBJECT_ASK
    modules["valuation"]["data"]["metrics"]["briarwood_current_value"] = ask * ratio
    return build_verdict_with_comparison_claim(
        property_summary=belmar_house.property_summary(),
        parser_output=belmar_house.parser_output(),
        module_results=modules,
        interaction_trace=belmar_house.interaction_trace(),
    )


class ValuePositionConsistencyTests(unittest.TestCase):
    def test_bcv_ask_ratio_sweep_agrees_across_value_paths(self) -> None:
        agent = CurrentValueAgent()
        ask = belmar_house.SUBJECT_ASK

        for ratio_i in range(80, 121):
            ratio = ratio_i / 100.0
            bcv = ask * ratio
            bcv_vs_ask_delta_pct = ((bcv - ask) / ask) * 100.0
            ask_vs_fmv_delta_pct = ((ask - bcv) / bcv) * 100.0

            canonical = classify_value_position(bcv=bcv, ask=ask)
            current_pricing_view = agent._pricing_view(bcv_vs_ask_delta_pct / 100.0)
            claim = _claim_for_ratio(ratio)

            with self.subTest(ratio=ratio):
                self.assertEqual(
                    classify_bcv_vs_ask_delta_pct(bcv_vs_ask_delta_pct),
                    canonical.label,
                )
                self.assertEqual(
                    classify_ask_vs_fmv_delta_pct(ask_vs_fmv_delta_pct),
                    canonical.label,
                )
                self.assertEqual(
                    _LABEL_BY_PRICING_VIEW[current_pricing_view],
                    canonical.label,
                )
                self.assertEqual(claim.verdict.label, canonical.label)
                self.assertEqual(check_verdict_delta_coherence(claim), [])

    def test_threshold_edges_use_single_canonical_rule(self) -> None:
        cases = [
            (-5.0, "value_find"),
            (-4.999, "fair"),
            (0.0, "fair"),
            (4.999, "fair"),
            (5.0, "overpriced"),
        ]
        for ask_vs_fmv_delta_pct, expected in cases:
            with self.subTest(delta=ask_vs_fmv_delta_pct):
                self.assertEqual(
                    classify_ask_vs_fmv_delta_pct(ask_vs_fmv_delta_pct),
                    expected,
                )

    def test_pricing_view_confidence_uses_weaker_available_signal(self) -> None:
        position = classify_value_position(
            bcv=700_000,
            ask=650_000,
            bcv_confidence=0.81,
            comp_confidence=0.55,
        )

        self.assertIsNotNone(position.confidence)
        assert position.confidence is not None
        self.assertEqual(position.confidence.score, 0.55)
        self.assertEqual(position.confidence.band, "low")


if __name__ == "__main__":
    unittest.main()

"""Advisory grounding verifier — per-violation-type unit tests.

Step 5 ships the verifier in advisory mode: `verify_response` walks a completed
LLM draft sentence-by-sentence and flags ungrounded numbers, forbidden hedges,
and sentinel phrases. The tests below exercise each violation type on synthetic
drafts paired with the `structured_inputs` that would have produced them. Real
LLM-drift fixtures collected from the dev environment can be added later; the
synthetic cases here pin the rules and guard against regressions from prompt
tweaks.
"""

from __future__ import annotations

import unittest

from api.guardrails import (
    Anchor,
    extract_anchors,
    extract_numbers,
    split_sentences,
    strip_violating_sentences,
    verify_response,
    verify_sentence,
)


class TokenExtractionTests(unittest.TestCase):
    def test_extracts_currency_short(self) -> None:
        found = extract_numbers("Ask $820k vs fair $870,000.")
        kinds = {kind for _raw, kind in found}
        self.assertIn("currency_short", kinds)
        self.assertIn("currency", kinds)

    def test_extracts_percent(self) -> None:
        found = extract_numbers("Premium of 10.5% vs ask.")
        self.assertTrue(any(kind == "percent" for _raw, kind in found))

    def test_extracts_multiplier(self) -> None:
        found = extract_numbers("Stress case is 1.5x the bear scenario.")
        self.assertTrue(any(kind == "multiplier" for _raw, kind in found))

    def test_bare_ints_require_three_digits(self) -> None:
        # 12 should NOT be caught (too short); 2024 should.
        found = extract_numbers("Built in 2024 with 12 rooms.")
        kinds_for = {raw: kind for raw, kind in found}
        self.assertIn("2024", kinds_for)
        self.assertNotIn("12", kinds_for)


class AnchorParsingTests(unittest.TestCase):
    def test_parses_triple_colon_anchor(self) -> None:
        anchors = extract_anchors("Fair value [[ValuationModel:fair_value_base:820000]] solid.")
        self.assertEqual(len(anchors), 1)
        a = anchors[0]
        self.assertEqual(a.module, "ValuationModel")
        self.assertEqual(a.field, "fair_value_base")
        self.assertEqual(a.value, "820000")

    def test_normalizes_k_suffix(self) -> None:
        a = Anchor(module="X", field="y", value="820k")
        self.assertEqual(a.normalized_value, "820000")


class SentenceSplitTests(unittest.TestCase):
    def test_preserves_decimal_numbers(self) -> None:
        pieces = split_sentences("Value is $1.2M. Premium +10%.")
        self.assertEqual(len(pieces), 2)
        self.assertIn("$1.2M", pieces[0])


class VerifyResponseTests(unittest.TestCase):
    """End-to-end verifier checks — each fixture is a (draft, structured_inputs)
    pair and asserts on the resulting VerifierReport."""

    def test_clean_draft_with_grounded_numbers(self) -> None:
        draft = "Fair value $820,000. Ask $870,000 — premium +6%."
        inputs = {"fair_value_base": 820000, "ask_price": 870000, "ask_premium_pct": 0.06}
        report = verify_response(draft, inputs, tier="decision_summary")
        self.assertEqual(report.sentences_with_violations, 0)
        self.assertEqual(report.violations, [])

    def test_flags_ungrounded_number(self) -> None:
        draft = "Fair value $820,000. Expected growth adds $700,000 upside."
        inputs = {"fair_value_base": 820000}
        report = verify_response(draft, inputs, tier="decision_summary")
        self.assertEqual(report.sentences_with_violations, 1)
        kinds = [v.kind for v in report.violations]
        self.assertIn("ungrounded_number", kinds)

    def test_anchor_grounds_number_not_in_inputs(self) -> None:
        draft = "Fair value [[ValuationModel:fair_value_base:820000]]$820,000 solid."
        inputs: dict = {}  # deliberately empty — anchor is the only evidence
        report = verify_response(draft, inputs, tier="decision_summary")
        self.assertEqual(report.sentences_with_violations, 0)
        self.assertEqual(report.anchor_count, 1)

    def test_flags_forbidden_hedge(self) -> None:
        draft = "Generally speaking, the market tends to appreciate."
        report = verify_response(draft, {}, tier="decision_summary")
        self.assertTrue(any(v.kind == "forbidden_hedge" for v in report.violations))

    def test_sentinel_phrase_sets_ungrounded_declaration(self) -> None:
        draft = "We don't have a model output for that school-district question."
        report = verify_response(draft, {}, tier="lookup")
        self.assertTrue(report.ungrounded_declaration)
        # sentinel is not itself a violation
        self.assertEqual(report.sentences_with_violations, 0)

    def test_empty_draft_yields_clean_report(self) -> None:
        report = verify_response("", {"ask_price": 820000}, tier="lookup")
        self.assertEqual(report.sentences_total, 0)
        self.assertEqual(report.sentences_with_violations, 0)
        self.assertEqual(report.violations, [])

    def test_rounding_tolerance_absorbs_small_diffs(self) -> None:
        # 820123 is within 0.5% of 820000 — should count as grounded.
        draft = "Fair value around $820,123."
        inputs = {"fair_value_base": 820000}
        report = verify_response(draft, inputs, tier="decision_summary")
        self.assertEqual(report.sentences_with_violations, 0)

    def test_percent_vs_fraction_variants(self) -> None:
        # Input stored as fraction 0.10; draft renders as 10%.
        draft = "Premium of 10%."
        inputs = {"ask_premium_pct": 0.10}
        report = verify_response(draft, inputs, tier="decision_summary")
        self.assertEqual(report.sentences_with_violations, 0)


class VerifySentenceTests(unittest.TestCase):
    def test_anchor_in_scope_grounds_value(self) -> None:
        anchors = [Anchor(module="ValuationModel", field="fair_value_base", value="820000")]
        violations = verify_sentence(
            "Fair value $820,000.",
            grounded_numbers=set(),
            grounded_strings=set(),
            anchors=anchors,
        )
        self.assertEqual(violations, [])

    def test_hedge_and_ungrounded_stack(self) -> None:
        violations = verify_sentence(
            "Generally speaking, upside is $700,000.",
            grounded_numbers=set(),
            grounded_strings=set(),
            anchors=[],
        )
        kinds = {v.kind for v in violations}
        self.assertEqual(kinds, {"ungrounded_number", "forbidden_hedge"})


class StripViolatingSentencesTests(unittest.TestCase):
    """The strict-regen flow (composer) relies on this helper to drop flagged
    sentences before flushing. Tests pin the equality semantics (marker-less
    comparison) and the kind-filter contract."""

    def test_drops_flagged_sentence_keeps_others(self) -> None:
        draft = "Fair value $820,000. Expected growth adds $700,000 upside."
        report = verify_response(
            draft, {"fair_value_base": 820000}, tier="decision_summary"
        )
        cleaned, n = strip_violating_sentences(draft, report)
        self.assertEqual(n, 1)
        self.assertIn("Fair value $820,000", cleaned)
        self.assertNotIn("$700,000", cleaned)

    def test_empty_draft_returns_empty(self) -> None:
        report = verify_response("", {}, tier="lookup")
        cleaned, n = strip_violating_sentences("", report)
        self.assertEqual((cleaned, n), ("", 0))

    def test_no_violations_returns_draft_unchanged(self) -> None:
        draft = "Fair value $820,000 — on the money."
        report = verify_response(
            draft, {"fair_value_base": 820000}, tier="decision_summary"
        )
        cleaned, n = strip_violating_sentences(draft, report)
        self.assertEqual((cleaned, n), (draft, 0))

    def test_forbidden_hedge_kind_not_stripped_by_default(self) -> None:
        # Only ungrounded_number / ungrounded_entity trigger strip by default.
        # A hedge should survive the default-kind call.
        draft = "Generally speaking, $820,000 is fair."
        report = verify_response(
            draft, {"fair_value_base": 820000}, tier="decision_summary"
        )
        cleaned, n = strip_violating_sentences(draft, report)
        self.assertEqual(n, 0)
        self.assertIn("$820,000", cleaned)

    def test_strips_markers_from_comparison(self) -> None:
        # Anchor-marked sentences should match the violation.sentence form
        # (verifier already strips markers before recording).
        draft = "Upside is [[Module:field:700000]]$700,000 on a good day."
        report = verify_response(draft, {}, tier="decision_summary")
        cleaned, n = strip_violating_sentences(draft, report)
        # The anchor grounds the 700000, so no violation and nothing stripped.
        self.assertEqual(n, 0)
        self.assertIn("$700,000", cleaned)


if __name__ == "__main__":
    unittest.main()

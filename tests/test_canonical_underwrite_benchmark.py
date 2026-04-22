from __future__ import annotations

import unittest

from briarwood.eval.canonical_underwrite_benchmark import evaluate_case, load_cases


class CanonicalUnderwriteBenchmarkTests(unittest.TestCase):
    def test_load_cases_returns_three_fixtures(self) -> None:
        cases = load_cases()
        self.assertEqual(len(cases), 3)
        self.assertEqual(cases[0].prompt, "Underwrite this property.")

    def test_evaluate_case_passes_when_surface_has_evidence_flip_hook_and_chart_claim(self) -> None:
        case = load_cases()[0]
        result = evaluate_case(
            case,
            events=[
                {
                    "type": "verdict",
                    "stance": case.expected_stance_band[0],
                    "lead_reason": "The all-in basis is above fair value.",
                    "evidence_items": ["Fair value is $720,644 against a working basis of $767,000."],
                    "fair_value_base": 720644,
                    "basis_premium_pct": 0.0604,
                    "what_changes_my_view": ["Price improves toward fair value."],
                    "next_step_teaser": "Open the value chart next to see how the ask sits against Briarwood's fair-value anchor.",
                },
                {
                    "type": "text_delta",
                    "content": "Buy only if price improves. The current basis is ahead of fair value.",
                },
                {
                    "type": "chart",
                    "kind": "value_opportunity",
                    "supports_claim": "price_position",
                    "why_this_chart": "This chart proves the verdict by showing where today's ask sits versus Briarwood's fair-value read.",
                },
            ],
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.first_chart_claim, "price_position")

    def test_evaluate_case_flags_generic_positive_language_without_surface_evidence(self) -> None:
        case = load_cases()[0]
        result = evaluate_case(
            case,
            events=[
                {"type": "verdict", "stance": case.expected_stance_band[0]},
                {"type": "text_delta", "content": "This looks like an interesting opportunity worth a closer look."},
                {"type": "chart", "kind": "value_opportunity", "supports_claim": "price_position"},
            ],
        )
        self.assertFalse(result.passed)
        self.assertIn(
            "generic positive language appeared without surfaced evidence",
            result.failures,
        )


if __name__ == "__main__":
    unittest.main()

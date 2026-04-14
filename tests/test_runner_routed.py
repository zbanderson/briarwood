from __future__ import annotations

import unittest

from briarwood.runner_routed import _scoped_synthesizer


class ScopedSynthesizerTests(unittest.TestCase):
    def test_future_income_focus_changes_recommendation_and_best_path(self) -> None:
        property_summary = {"property_id": "sample-property"}
        base_modules = {
            "outputs": {
                "valuation": {
                    "data": {
                        "summary": "Value looks roughly in line with the ask.",
                        "metrics": {"mispricing_pct": -0.01},
                    },
                    "confidence": 0.7,
                },
                "carry_cost": {
                    "data": {
                        "summary": "Monthly carry remains negative at current rent assumptions.",
                        "metrics": {"monthly_cash_flow": -1800},
                    },
                    "confidence": 0.8,
                },
                "rent_stabilization": {
                    "data": {"summary": "Rental absorption looks fragile under current evidence."},
                    "confidence": 0.6,
                },
                "hold_to_rent": {
                    "data": {"summary": "The hold-to-rent path only works if rents prove out."},
                    "confidence": 0.65,
                },
            }
        }

        buy_answer = _scoped_synthesizer(
            property_summary,
            {
                "intent_type": "buy_decision",
                "analysis_depth": "decision",
                "question_focus": ["should_i_buy"],
                "occupancy_type": "investor",
                "exit_options": ["rent"],
                "confidence": 0.7,
                "missing_inputs": [],
            },
            base_modules,
        )
        income_answer = _scoped_synthesizer(
            property_summary,
            {
                "intent_type": "owner_occupant_then_rent",
                "analysis_depth": "decision",
                "question_focus": ["future_income"],
                "occupancy_type": "investor",
                "exit_options": ["rent"],
                "confidence": 0.7,
                "missing_inputs": [],
            },
            base_modules,
        )

        self.assertNotEqual(buy_answer["recommendation"], income_answer["recommendation"])
        self.assertIn("rent path", income_answer["recommendation"].lower())
        self.assertIn("income durability", income_answer["best_path"].lower())
        self.assertNotEqual(buy_answer["best_path"], income_answer["best_path"])


if __name__ == "__main__":
    unittest.main()

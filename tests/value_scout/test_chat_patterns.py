import unittest

from briarwood.routing_schema import AnalysisDepth, DecisionType, UnifiedIntelligenceOutput
from briarwood.value_scout.patterns import adu_signal, rent_angle, town_trend_tailwind


def _unified(**supporting_facts: object) -> UnifiedIntelligenceOutput:
    return UnifiedIntelligenceOutput(
        recommendation="Buy if price improves.",
        decision=DecisionType.MIXED,
        best_path="Negotiate before committing.",
        key_value_drivers=[],
        key_risks=[],
        confidence=0.72,
        analysis_depth_used=AnalysisDepth.DECISION,
        supporting_facts=dict(supporting_facts),
    )


class RentAnglePatternTests(unittest.TestCase):
    def test_fires_on_comp_anchored_rent_yield(self) -> None:
        unified = _unified(
            cma={
                "comps": [
                    {"sale_price": 800_000, "rent_zestimate": 4_500},
                    {"sale_price": 820_000, "rent_zestimate": 4_700},
                    {"sale_price": 780_000, "rent_zestimate": 4_300},
                ],
            },
            carry_cost={"monthly_total_cost": 4_000},
        )

        insight = rent_angle.detect(unified)

        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.category, "rent_angle")
        self.assertGreaterEqual(insight.confidence or 0.0, 0.68)
        self.assertIn("supporting_facts.cma.comps.rent_zestimate", insight.supporting_fields)

    def test_secondary_fires_on_rent_support_and_cash_flow(self) -> None:
        unified = _unified(
            rental_option={"rent_support_score": 0.76},
            carry_cost={"monthly_cash_flow": -125},
            user_text="what do you think of this listing?",
        )

        insight = rent_angle.detect(unified)

        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.category, "rent_angle")
        self.assertIn("supporting_facts.rental_option.rent_support_score", insight.supporting_fields)

    def test_secondary_does_not_fire_when_user_already_asked_about_rent(self) -> None:
        unified = _unified(
            rental_option={"rent_support_score": 0.8},
            carry_cost={"monthly_cash_flow": 100},
            user_text="what rent can I get for this?",
        )

        self.assertIsNone(rent_angle.detect(unified))


class AduSignalPatternTests(unittest.TestCase):
    def test_fires_on_accessory_signal_with_credible_confidence(self) -> None:
        unified = _unified(
            legal_confidence={
                "confidence": 0.66,
                "legality_evidence": {
                    "has_accessory_signal": True,
                    "adu_type": "back_house",
                },
            },
        )

        insight = adu_signal.detect(unified)

        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.category, "adu_signal")
        self.assertGreaterEqual(insight.confidence or 0.0, 0.66)


class TownTrendTailwindPatternTests(unittest.TestCase):
    def test_fires_above_three_year_tailwind_threshold(self) -> None:
        unified = _unified(
            market_value_history={
                "geography_name": "Belmar",
                "three_year_change_pct": 0.123,
            },
        )

        insight = town_trend_tailwind.detect(unified)

        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.category, "town_trend_tailwind")
        self.assertIn(
            "supporting_facts.market_value_history.three_year_change_pct",
            insight.supporting_fields,
        )

    def test_does_not_fire_below_threshold(self) -> None:
        unified = _unified(
            market_value_history={
                "geography_name": "Belmar",
                "three_year_change_pct": 0.055,
            },
        )

        self.assertIsNone(town_trend_tailwind.detect(unified))


if __name__ == "__main__":
    unittest.main()

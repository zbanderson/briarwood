import unittest

from briarwood.agents.current_value import CurrentValueAgent, CurrentValueInput
from briarwood.agents.market_history.schemas import HistoricalValuePoint


def sample_history() -> list[HistoricalValuePoint]:
    return [
        HistoricalValuePoint(date="2024-02-28", value=900000),
        HistoricalValuePoint(date="2025-02-28", value=960000),
        HistoricalValuePoint(date="2026-02-28", value=1000000),
    ]


class CurrentValueAgentTests(unittest.TestCase):
    def test_full_input_case(self) -> None:
        result = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=950000,
                market_value_today=1000000,
                market_history_points=sample_history(),
                beds=4,
                baths=2.5,
                lot_size=0.14,
                property_type="Single Family",
                year_built=1995,
                listing_date="2025-12-01",
                effective_annual_rent=54000,
                cap_rate_assumption=0.05,
            )
        )

        self.assertGreater(result.briarwood_current_value, 0)
        self.assertIsNotNone(result.components.market_adjusted_value)
        self.assertIsNotNone(result.components.backdated_listing_value)
        self.assertIsNotNone(result.components.income_supported_value)
        self.assertAlmostEqual(
            result.weights.market_adjusted_weight
            + result.weights.backdated_listing_weight
            + result.weights.income_weight,
            1.0,
            places=4,
        )

    def test_missing_rent_zeroes_income_weight(self) -> None:
        result = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=950000,
                market_value_today=1000000,
                market_history_points=sample_history(),
                beds=3,
                baths=2.0,
                lot_size=0.11,
                year_built=1985,
                listing_date="2025-12-01",
                cap_rate_assumption=0.05,
            )
        )

        self.assertIsNone(result.components.income_supported_value)
        self.assertEqual(result.weights.income_weight, 0.0)

    def test_missing_listing_date_zeroes_backdated_weight(self) -> None:
        result = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=950000,
                market_value_today=1000000,
                market_history_points=sample_history(),
                beds=3,
                baths=2.0,
                lot_size=0.11,
                year_built=1985,
                effective_annual_rent=48000,
                cap_rate_assumption=0.05,
            )
        )

        self.assertIsNone(result.components.backdated_listing_value)
        self.assertEqual(result.weights.backdated_listing_weight, 0.0)

    def test_missing_market_history_degrades_confidence(self) -> None:
        result = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=950000,
                beds=3,
                baths=2.0,
                effective_annual_rent=48000,
                cap_rate_assumption=0.05,
            )
        )

        self.assertLess(result.confidence, 0.45)
        self.assertIn("Current value confidence is low", " ".join(result.warnings))

    def test_weight_normalization_ignores_missing_components(self) -> None:
        result = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=950000,
                market_value_today=1000000,
                market_history_points=sample_history(),
                cap_rate_assumption=0.05,
            )
        )

        self.assertEqual(result.weights.backdated_listing_weight, 0.0)
        self.assertEqual(result.weights.income_weight, 0.0)
        self.assertEqual(result.weights.market_adjusted_weight, 1.0)

    def test_mispricing_calculation(self) -> None:
        result = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=900000,
                market_value_today=1000000,
                market_history_points=sample_history(),
                beds=3,
                baths=2.0,
                cap_rate_assumption=0.05,
            )
        )

        self.assertGreater(result.mispricing_pct, 0)
        self.assertEqual(result.pricing_view, "appears undervalued")

    def test_range_widens_when_confidence_is_low(self) -> None:
        high_confidence = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=950000,
                market_value_today=1000000,
                market_history_points=sample_history(),
                beds=4,
                baths=3.0,
                lot_size=0.15,
                property_type="Single Family",
                year_built=2005,
                listing_date="2025-12-01",
                effective_annual_rent=54000,
                cap_rate_assumption=0.05,
            )
        )
        low_confidence = CurrentValueAgent().run(
            CurrentValueInput(
                ask_price=950000,
                market_value_today=1000000,
                market_history_points=[HistoricalValuePoint(date="2026-02-28", value=1000000)],
                cap_rate_assumption=0.05,
            )
        )

        high_band = high_confidence.value_high - high_confidence.value_low
        low_band = low_confidence.value_high - low_confidence.value_low
        self.assertGreater(low_band, high_band)


if __name__ == "__main__":
    unittest.main()

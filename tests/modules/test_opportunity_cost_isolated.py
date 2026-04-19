"""Isolation tests for the opportunity_cost Q5 producer.

The module compares a property's projected terminal value against two
passive benchmarks (T-bill, S&P). These tests pin down the three states:

- Missing prerequisite outputs → ``mode="error"`` payload.
- Thin metrics (no entry basis or no growth rate) → ``mode="partial"``.
- Full inputs → ``mode="full"`` with property CAGR / excess bps / dominant
  benchmark metrics populated.
"""

from __future__ import annotations

import unittest

from briarwood.execution.context import ExecutionContext
from briarwood.modules.opportunity_cost import run_opportunity_cost
from briarwood.routing_schema import ModulePayload
from briarwood.settings import DEFAULT_BENCHMARK_SETTINGS


def _context(
    *,
    purchase_price: float | None = 725_000,
    hold_years: int | None = 5,
    prior_outputs: dict | None = None,
) -> ExecutionContext:
    property_data: dict = {
        "property_id": "opp-cost-test",
        "address": "1 Benchmark Ln",
        "town": "Belmar",
        "state": "NJ",
    }
    if purchase_price is not None:
        property_data["purchase_price"] = purchase_price

    assumptions: dict = {}
    if hold_years is not None:
        assumptions["hold_period_years"] = hold_years

    return ExecutionContext(
        property_id="opp-cost-test",
        property_data=property_data,
        assumptions=assumptions,
        prior_outputs=dict(prior_outputs or {}),
    )


def _valuation_output(price: float = 725_000, confidence: float = 0.8) -> dict:
    return {
        "data": {
            "module_name": "valuation",
            "summary": "test",
            "metrics": {
                "ask_price": price,
                "briarwood_current_value": price * 0.98,
                "fair_value_base": price * 0.97,
            },
        },
        "confidence": confidence,
        "assumptions_used": {},
        "warnings": [],
        "mode": "full",
    }


def _resale_output(growth: float = 0.08, confidence: float = 0.7) -> dict:
    return {
        "data": {
            "module_name": "resale_scenario",
            "summary": "test",
            "metrics": {
                "base_growth_rate": growth,
            },
        },
        "confidence": confidence,
        "assumptions_used": {},
        "warnings": [],
        "mode": "full",
    }


class OpportunityCostModuleTests(unittest.TestCase):
    def test_missing_prerequisites_returns_error_payload(self) -> None:
        ctx = _context(prior_outputs={})
        raw = run_opportunity_cost(ctx)
        payload = ModulePayload(**raw)
        self.assertEqual(payload.mode, "error")
        self.assertIn("valuation", payload.missing_inputs)
        self.assertIn("resale_scenario", payload.missing_inputs)
        self.assertIsNone(payload.confidence)

    def test_missing_entry_basis_returns_partial(self) -> None:
        valuation_without_anchor = {
            "data": {"module_name": "valuation", "summary": "t", "metrics": {}},
            "confidence": 0.5,
            "assumptions_used": {},
            "warnings": [],
            "mode": "full",
        }
        ctx = _context(
            purchase_price=None,
            prior_outputs={
                "valuation": valuation_without_anchor,
                "resale_scenario": _resale_output(),
            },
        )
        raw = run_opportunity_cost(ctx)
        payload = ModulePayload(**raw)
        self.assertEqual(payload.mode, "partial")
        self.assertIn("entry_basis", payload.missing_inputs)
        self.assertLess(payload.confidence or 1.0, 0.5)

    def test_full_inputs_produce_meaningful_bps_delta(self) -> None:
        """8% growth handily beats a 7% S&P assumption."""
        ctx = _context(
            purchase_price=725_000,
            hold_years=5,
            prior_outputs={
                "valuation": _valuation_output(),
                "resale_scenario": _resale_output(growth=0.08),
            },
        )
        raw = run_opportunity_cost(ctx)
        payload = ModulePayload(**raw)
        self.assertEqual(payload.mode, "full")

        metrics = payload.data["metrics"]
        self.assertAlmostEqual(metrics["entry_basis"], 725_000.0, places=2)
        self.assertEqual(metrics["hold_years"], 5)
        self.assertAlmostEqual(metrics["property_cagr"], 0.08, places=4)
        # 8% growth over 5y → terminal > 725k × 1.07^5 (sp500 terminal)
        self.assertGreater(
            metrics["property_terminal_value"], metrics["sp500_terminal_value"]
        )
        self.assertGreater(metrics["excess_vs_sp500_bps"], 0)
        self.assertGreater(metrics["excess_vs_tbill_bps"], 0)
        # Property beats S&P more than T-bills, so dominant should be sp500.
        self.assertEqual(metrics["dominant_benchmark"], "sp500")
        self.assertEqual(
            metrics["meaningful_excess_bps_threshold"],
            DEFAULT_BENCHMARK_SETTINGS.meaningful_excess_bps,
        )

    def test_property_lags_benchmark_reports_negative_delta(self) -> None:
        ctx = _context(
            purchase_price=725_000,
            hold_years=5,
            prior_outputs={
                "valuation": _valuation_output(),
                "resale_scenario": _resale_output(growth=0.02),
            },
        )
        raw = run_opportunity_cost(ctx)
        payload = ModulePayload(**raw)
        metrics = payload.data["metrics"]
        # 2% vs 4.2% T-bill → negative
        self.assertLess(metrics["excess_vs_tbill_bps"], 0)
        self.assertLess(metrics["excess_vs_sp500_bps"], 0)
        # Lagging both, dominant = whichever it lags *less* (tbill, since
        # 2% is closer to 4.2% than to 7%).
        self.assertEqual(metrics["dominant_benchmark"], "tbill")
        self.assertLess(metrics["dominant_excess_bps"], 0)

    def test_purchase_price_takes_precedence_over_valuation_anchor(self) -> None:
        ctx = _context(
            purchase_price=800_000,
            prior_outputs={
                "valuation": _valuation_output(price=600_000),
                "resale_scenario": _resale_output(),
            },
        )
        raw = run_opportunity_cost(ctx)
        payload = ModulePayload(**raw)
        self.assertAlmostEqual(
            payload.data["metrics"]["entry_basis"], 800_000.0, places=2
        )

    def test_assumptions_surface_appreciation_only_flag(self) -> None:
        ctx = _context(
            prior_outputs={
                "valuation": _valuation_output(),
                "resale_scenario": _resale_output(),
            }
        )
        raw = run_opportunity_cost(ctx)
        payload = ModulePayload(**raw)
        self.assertEqual(
            payload.assumptions_used.get("comparison_mode"), "appreciation_only"
        )
        self.assertTrue(payload.assumptions_used.get("extrapolates_12mo_forward_rate"))
        self.assertTrue(payload.assumptions_used.get("gross_of_tax_and_liquidity"))


if __name__ == "__main__":
    unittest.main()

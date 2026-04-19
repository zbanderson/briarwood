"""Opportunity-cost module — Q5 producer (capital allocation vs. alternatives).

Given a property's base-case forward growth (from ``resale_scenario``) and its
entry basis (from ``valuation``), this module projects the property's terminal
value over the configured hold horizon and compares it to two passive
benchmarks (T-bill, S&P historical). The output is a set of raw metrics; the
``opportunity_x_value`` bridge converts the delta into human-readable
reasoning for the synthesizer.

Explicit limitations (surfaced in ``assumptions_used`` so they show up in the
trust surface rather than silently flattering the property):

- **Appreciation-only.** The comparison ignores net rental income, carry
  costs, tax impacts, and leverage. It answers "does the asset itself
  outgrow the benchmark?" not "does the levered-and-rented deal IRR clear
  the benchmark?" The rental / carry story lives in ``hold_to_rent`` and
  ``carry_cost``; this module deliberately does not double-count them.
- **Constant-growth extrapolation.** The property's forward return is
  assumed to compound at ``base_growth_rate`` over the hold horizon. That
  rate is itself a 12-month forward read from ``resale_scenario``; extending
  it to 5+ years is a rough first-pass and is flagged.
- **Gross of tax and liquidity.** Both sides of the comparison are reported
  pre-tax and assume no forced liquidation.

These limitations mean the signal is directional, not IRR-grade.
"""

from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.scoped_common import confidence_band
from briarwood.routing_schema import ModulePayload
from briarwood.settings import BenchmarkSettings, DEFAULT_BENCHMARK_SETTINGS


def run_opportunity_cost(
    context: ExecutionContext,
    *,
    settings: BenchmarkSettings | None = None,
) -> dict[str, object]:
    """Produce the property-vs-benchmark capital-allocation view.

    Requires ``valuation`` and ``resale_scenario`` to have already run; the
    executor guarantees this via the registry's ``depends_on`` edge.
    """

    s = settings or DEFAULT_BENCHMARK_SETTINGS

    valuation_output = context.get_module_output("valuation")
    resale_output = context.get_module_output("resale_scenario")

    missing: list[str] = []
    if not isinstance(valuation_output, dict):
        missing.append("valuation")
    if not isinstance(resale_output, dict):
        missing.append("resale_scenario")
    if missing:
        payload = ModulePayload(
            data={
                "module_name": "opportunity_cost",
                "summary": (
                    "Opportunity-cost comparison unavailable — required module outputs missing: "
                    + ", ".join(missing)
                ),
                "metrics": {},
            },
            confidence=None,
            assumptions_used={"required_prior_modules": ["valuation", "resale_scenario"]},
            warnings=[f"Missing prior module output: {name}" for name in missing],
            mode="error",
            missing_inputs=missing,
            confidence_band=confidence_band(None),
        )
        return payload.model_dump()

    entry_basis = _entry_basis(valuation_output, context)
    base_growth_rate = _base_growth_rate(resale_output)
    hold_years = _hold_years(context, default=s.default_hold_years)

    warnings: list[str] = []
    assumptions: dict[str, Any] = {
        "tbill_annual_return": s.tbill_annual_return,
        "sp500_annual_return": s.sp500_annual_return,
        "hold_years": hold_years,
        "comparison_mode": "appreciation_only",
        "extrapolates_12mo_forward_rate": True,
        "gross_of_tax_and_liquidity": True,
        "required_prior_modules": ["valuation", "resale_scenario"],
    }

    if entry_basis is None:
        warnings.append("Entry basis unavailable — cannot compute terminal values.")
    if base_growth_rate is None:
        warnings.append("Base-case growth rate unavailable from resale_scenario.")

    if entry_basis is None or base_growth_rate is None:
        payload = ModulePayload(
            data={
                "module_name": "opportunity_cost",
                "summary": (
                    "Opportunity-cost comparison requires entry basis and base-case growth rate."
                ),
                "metrics": {},
            },
            confidence=_confidence_from_prior(valuation_output, resale_output, hit=False),
            assumptions_used=assumptions,
            warnings=warnings,
            mode="partial",
            missing_inputs=[
                name
                for name, value in (("entry_basis", entry_basis), ("base_growth_rate", base_growth_rate))
                if value is None
            ],
            confidence_band=confidence_band(None),
        )
        return payload.model_dump()

    property_terminal = entry_basis * (1.0 + base_growth_rate) ** hold_years
    tbill_terminal = entry_basis * (1.0 + s.tbill_annual_return) ** hold_years
    sp500_terminal = entry_basis * (1.0 + s.sp500_annual_return) ** hold_years

    property_cagr = base_growth_rate  # by construction of constant-growth model
    excess_vs_tbill_bps = round((property_cagr - s.tbill_annual_return) * 10_000.0, 1)
    excess_vs_sp500_bps = round((property_cagr - s.sp500_annual_return) * 10_000.0, 1)
    delta_vs_tbill = round(property_terminal - tbill_terminal, 2)
    delta_vs_sp500 = round(property_terminal - sp500_terminal, 2)

    # "Dominant" is the benchmark most worth surfacing in a capital-allocation
    # narrative:
    # - Property beats S&P → surface S&P (strongest claim — clears the
    #   realistic passive alternative).
    # - Property lags S&P but beats T-bills → surface T-bills (honest "only
    #   beats the safe alt" story).
    # - Property lags T-bills too → surface T-bills (starkest red flag: worse
    #   than the risk-free rate).
    if excess_vs_sp500_bps >= 0:
        dominant = "sp500"
        dominant_excess_bps = excess_vs_sp500_bps
        dominant_delta_value = delta_vs_sp500
    else:
        dominant = "tbill"
        dominant_excess_bps = excess_vs_tbill_bps
        dominant_delta_value = delta_vs_tbill

    summary = _format_summary(
        property_cagr=property_cagr,
        hold_years=hold_years,
        dominant=dominant,
        dominant_excess_bps=dominant_excess_bps,
    )

    metrics = {
        "entry_basis": round(entry_basis, 2),
        "hold_years": hold_years,
        "property_cagr": round(property_cagr, 4),
        "property_terminal_value": round(property_terminal, 2),
        "tbill_annual_return": s.tbill_annual_return,
        "tbill_terminal_value": round(tbill_terminal, 2),
        "sp500_annual_return": s.sp500_annual_return,
        "sp500_terminal_value": round(sp500_terminal, 2),
        "excess_vs_tbill_bps": excess_vs_tbill_bps,
        "excess_vs_sp500_bps": excess_vs_sp500_bps,
        "delta_value_vs_tbill": delta_vs_tbill,
        "delta_value_vs_sp500": delta_vs_sp500,
        "dominant_benchmark": dominant,
        "dominant_excess_bps": dominant_excess_bps,
        "dominant_delta_value": dominant_delta_value,
        "meaningful_excess_bps_threshold": s.meaningful_excess_bps,
    }

    payload = ModulePayload(
        data={
            "module_name": "opportunity_cost",
            "summary": summary,
            "metrics": metrics,
        },
        confidence=_confidence_from_prior(valuation_output, resale_output, hit=True),
        assumptions_used=assumptions,
        warnings=warnings,
        mode="full",
        confidence_band=confidence_band(
            _confidence_from_prior(valuation_output, resale_output, hit=True)
        ),
    )
    return payload.model_dump()


def _entry_basis(
    valuation_output: dict[str, Any], context: ExecutionContext
) -> float | None:
    """Pull the entry basis — prefer the user's declared purchase price, fall
    back to the valuation module's anchor if absent. This is the denominator
    for both the property CAGR and the benchmark terminals."""

    property_data = context.property_data or {}
    purchase_price = property_data.get("purchase_price")
    if isinstance(purchase_price, (int, float)) and purchase_price > 0:
        return float(purchase_price)

    metrics = dict((valuation_output.get("data") or {}).get("metrics") or {})
    for key in ("ask_price", "briarwood_current_value", "fair_value_base"):
        candidate = metrics.get(key)
        if isinstance(candidate, (int, float)) and candidate > 0:
            return float(candidate)
    return None


def _base_growth_rate(resale_output: dict[str, Any]) -> float | None:
    metrics = dict((resale_output.get("data") or {}).get("metrics") or {})
    value = metrics.get("base_growth_rate")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _hold_years(context: ExecutionContext, *, default: int) -> int:
    """Resolve the user's declared hold horizon, defaulting when missing."""

    assumptions = context.assumptions or {}
    value = assumptions.get("hold_period_years")
    if isinstance(value, (int, float)) and value >= 1:
        return int(value)

    property_data = context.property_data or {}
    user_assumptions = property_data.get("user_assumptions")
    if isinstance(user_assumptions, dict):
        candidate = user_assumptions.get("hold_period_years")
        if isinstance(candidate, (int, float)) and candidate >= 1:
            return int(candidate)
    return default


def _confidence_from_prior(
    valuation_output: dict[str, Any],
    resale_output: dict[str, Any],
    *,
    hit: bool,
) -> float | None:
    """Opportunity_cost confidence is bounded by its inputs' confidence — it
    introduces no new information, it only recombines."""

    candidates: list[float] = []
    for source in (valuation_output, resale_output):
        value = source.get("confidence")
        if isinstance(value, (int, float)):
            candidates.append(float(value))
    if not candidates:
        return None
    base = min(candidates)
    # When the module can't actually compute a terminal comparison, drop
    # confidence further so downstream consumers (and the trust gate) see
    # the signal is degraded.
    return round(base if hit else base * 0.5, 4)


def _format_summary(
    *,
    property_cagr: float,
    hold_years: int,
    dominant: str,
    dominant_excess_bps: float,
) -> str:
    benchmark_label = "the S&P 500" if dominant == "sp500" else "T-bills"
    if dominant_excess_bps >= 0:
        direction = f"+{dominant_excess_bps:.0f} bps ahead of"
    else:
        direction = f"{dominant_excess_bps:.0f} bps behind"
    return (
        f"Property projects {property_cagr:.1%} CAGR over a {hold_years}-year hold — "
        f"{direction} {benchmark_label} on an appreciation-only basis."
    )


__all__ = ["run_opportunity_cost"]

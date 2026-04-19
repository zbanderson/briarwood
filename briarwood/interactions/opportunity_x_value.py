"""Bridge: opportunity × value.

Reads the ``opportunity_cost`` module's property-vs-benchmark comparison and
translates the raw bps delta into reasoning the synthesizer can surface as a
value driver (property beats the passive alternative decisively) or a risk
(property lags the passive alternative decisively). When the gap is thin —
|excess bps| < threshold — the bridge fires with a neutral "roughly in line"
read so the trace records that Q5 was considered, without promoting a
non-signal into the narrative.
"""

from __future__ import annotations

from briarwood.interactions.bridge import (
    BridgeRecord,
    ModuleOutputs,
    _confidence,
    _metrics,
    _payload,
)

NAME = "opportunity_x_value"


def run(outputs: ModuleOutputs) -> BridgeRecord:
    opp = _payload(outputs, "opportunity_cost")
    if opp is None:
        return BridgeRecord(
            name=NAME,
            fired=False,
            reasoning=["opportunity_cost output missing"],
        )

    metrics = _metrics(opp)
    dominant_excess_bps = _as_float(metrics.get("dominant_excess_bps"))
    dominant_benchmark = metrics.get("dominant_benchmark")
    dominant_delta_value = _as_float(metrics.get("dominant_delta_value"))
    hold_years = _as_float(metrics.get("hold_years"))
    property_cagr = _as_float(metrics.get("property_cagr"))
    threshold = _as_float(metrics.get("meaningful_excess_bps_threshold")) or 150.0

    if (
        dominant_excess_bps is None
        or dominant_benchmark not in ("tbill", "sp500")
        or hold_years is None
        or property_cagr is None
    ):
        return BridgeRecord(
            name=NAME,
            inputs_read=["opportunity_cost"],
            fired=False,
            reasoning=[
                "Missing required opportunity_cost metrics to compare property vs. benchmark."
            ],
        )

    benchmark_label = "the S&P 500" if dominant_benchmark == "sp500" else "T-bills"
    hold_years_int = int(hold_years)

    adjustments = {
        "dominant_benchmark": dominant_benchmark,
        "dominant_excess_bps": dominant_excess_bps,
        "dominant_delta_value": dominant_delta_value,
        "property_cagr": property_cagr,
        "hold_years": hold_years_int,
        "meaningful_excess_bps_threshold": threshold,
    }

    if dominant_excess_bps >= threshold:
        signal = "value_driver"
        reasoning = [
            f"Property projects {property_cagr:.1%} CAGR over {hold_years_int}y — "
            f"beats {benchmark_label} by {dominant_excess_bps:.0f} bps (appreciation-only). "
            "Capital-allocation edge vs. the passive alternative.",
        ]
    elif dominant_excess_bps <= -threshold:
        signal = "risk"
        reasoning = [
            f"Property projects {property_cagr:.1%} CAGR over {hold_years_int}y — "
            f"lags {benchmark_label} by {abs(dominant_excess_bps):.0f} bps (appreciation-only). "
            "Passive alternative looks better for the same capital.",
        ]
    else:
        signal = "neutral"
        reasoning = [
            f"Property CAGR is roughly in line with {benchmark_label} "
            f"({dominant_excess_bps:+.0f} bps over {hold_years_int}y, appreciation-only) — "
            "no meaningful capital-allocation edge either way.",
        ]

    adjustments["signal"] = signal

    return BridgeRecord(
        name=NAME,
        inputs_read=["opportunity_cost"],
        adjustments=adjustments,
        reasoning=reasoning,
        confidence=_confidence(opp) or 0.5,
        fired=True,
    )


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = ["NAME", "run"]

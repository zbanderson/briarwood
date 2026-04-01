from __future__ import annotations

from briarwood.reports.schemas import SignalMetric, SignalMetricsSection
from briarwood.schemas import AnalysisReport


def build_signal_metrics_section(report: AnalysisReport) -> SignalMetricsSection:
    return SignalMetricsSection(
        price_to_rent=_build_price_to_rent(report),
        scarcity=_build_scarcity(report),
        forward_gap=_build_forward_gap(report),
        liquidity=_build_liquidity(report),
        optionality=_build_optionality(report),
    )


def _build_price_to_rent(report: AnalysisReport) -> SignalMetric | None:
    income = report.get_module("income_support")
    ptr = income.metrics.get("price_to_rent")
    classification = str(income.metrics.get("price_to_rent_classification", "Unavailable"))
    if ptr is None:
        return SignalMetric(
            label="Price-to-Rent",
            value_text="n/a",
            classification="Unavailable",
            context="Price-to-rent could not be computed — rent support is missing.",
        )
    ptr_val = float(ptr)
    benchmark = report.property_input.market_price_to_rent_benchmark if report.property_input else None
    benchmark_text = f" (market ~{benchmark:.0f})" if benchmark else " (market avg ~18)"
    return SignalMetric(
        label="Price-to-Rent",
        value_text=f"{ptr_val:.1f}{benchmark_text}",
        classification=classification,
        context=(
            f"A P/R of {ptr_val:.1f} means the property costs {ptr_val:.1f}x annual rent. "
            f"Lower is better for investors; above 20 signals appreciation-dependent returns."
        ),
    )


def _build_scarcity(report: AnalysisReport) -> SignalMetric | None:
    scarcity = report.get_module("scarcity_support")
    score = scarcity.metrics.get("scarcity_support_score")
    label = str(scarcity.metrics.get("scarcity_label", "Unknown"))
    if score is None:
        return SignalMetric(
            label="Scarcity Score",
            value_text="n/a",
            classification="Unavailable",
            context="Scarcity score could not be computed.",
        )
    score_val = float(score)
    return SignalMetric(
        label="Scarcity Score",
        value_text=f"{score_val:.0f}/100",
        classification=label,
        context=(
            f"Scarcity of {score_val:.0f} ({label.lower()}) reflects how hard this property's "
            "location and land advantages are to replicate locally."
        ),
    )


def _build_forward_gap(report: AnalysisReport) -> SignalMetric | None:
    bbb = report.get_module("bull_base_bear")
    income = report.get_module("cost_valuation")
    base_value = bbb.metrics.get("base_case_value")
    ask_price = income.metrics.get("purchase_price")
    if base_value is None or ask_price is None or float(ask_price) == 0:
        return SignalMetric(
            label="Forward Value Gap",
            value_text="n/a",
            classification="Unavailable",
            context="Forward value gap requires a base case value and ask price.",
        )
    gap = float(base_value) - float(ask_price)
    gap_pct = gap / float(ask_price)
    direction = "+" if gap >= 0 else ""
    classification = "Positive" if gap >= 0 else "Negative"
    return SignalMetric(
        label="Forward Value Gap",
        value_text=f"{direction}${abs(gap):,.0f} ({direction}{gap_pct:.1%})",
        classification=classification,
        context=(
            f"Base case points to ${float(base_value):,.0f}, which is "
            f"{'above' if gap >= 0 else 'below'} the ask by {abs(gap_pct):.1%}. "
            "This is a heuristic forward estimate, not a sourced comp value."
        ),
    )


def _build_liquidity(report: AnalysisReport) -> SignalMetric | None:
    risk = report.get_module("risk_constraints")
    property_input = report.property_input
    dom = property_input.days_on_market if property_input else None
    flood_risk = risk.metrics.get("flood_risk")

    if dom is None:
        classification = "Unavailable"
        value_text = "n/a"
        context = "Days-on-market data is missing — liquidity signal cannot be computed."
    elif dom < 15:
        classification = "Fast"
        value_text = f"{dom} days DOM"
        context = f"Property sold in {dom} days — fast absorption suggests strong local demand."
    elif dom < 45:
        classification = "Normal"
        value_text = f"{dom} days DOM"
        context = f"{dom} days on market is within normal range for this market type."
    elif dom < 90:
        classification = "Slow"
        value_text = f"{dom} days DOM"
        context = f"{dom} days on market is above typical absorption — price or condition may be limiting demand."
    else:
        classification = "Stale"
        value_text = f"{dom} days DOM"
        context = f"{dom} days on market signals stale listing risk — exit flexibility may be constrained."

    return SignalMetric(
        label="Liquidity",
        value_text=value_text,
        classification=classification,
        context=context,
    )


def _build_optionality(report: AnalysisReport) -> SignalMetric | None:
    bbb = report.get_module("bull_base_bear")
    optionality_score = bbb.metrics.get("optionality_score")
    optionality_premium = bbb.metrics.get("optionality_premium")

    if optionality_score is None:
        return SignalMetric(
            label="Optionality",
            value_text="n/a",
            classification="Unavailable",
            context="Optionality score could not be computed.",
        )
    score_val = float(optionality_score)
    premium_val = float(optionality_premium) if optionality_premium is not None else 0.0

    if score_val >= 70:
        classification = "High"
    elif score_val >= 50:
        classification = "Moderate"
    elif score_val >= 30:
        classification = "Limited"
    else:
        classification = "Weak"

    premium_text = (
        f" (adds ~${premium_val:,.0f} to base)" if abs(premium_val) > 1000 else ""
    )
    return SignalMetric(
        label="Optionality",
        value_text=f"{score_val:.0f}/100{premium_text}",
        classification=classification,
        context=(
            f"Optionality of {score_val:.0f} ({classification.lower()}) reflects scarcity-driven "
            "upside potential from location advantages, land use, or renovation headroom."
        ),
    )

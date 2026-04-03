from __future__ import annotations

from briarwood.decision_model.scoring import calculate_final_score
from briarwood.reports.schemas import SignalMetric, SignalMetricsSection
from briarwood.schemas import AnalysisReport


def build_signal_metrics_section(report: AnalysisReport) -> SignalMetricsSection:
    return SignalMetricsSection(
        price_to_rent=_build_price_to_rent(report),
        net_opportunity_delta=_build_net_opportunity_delta(report),
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


def _build_net_opportunity_delta(report: AnalysisReport) -> SignalMetric | None:
    current_value = report.get_module("current_value")
    delta = current_value.metrics.get("net_opportunity_delta_value")
    delta_pct = current_value.metrics.get("net_opportunity_delta_pct")
    basis = current_value.metrics.get("all_in_basis")
    capex_source = str(current_value.metrics.get("capex_basis_source") or "unknown")

    if delta is None or delta_pct is None:
        return SignalMetric(
            label="Net Opportunity Delta",
            value_text="n/a",
            classification="Unavailable",
            context="Net opportunity delta requires a current value anchor and a usable purchase basis.",
        )

    delta_val = float(delta)
    delta_pct_val = float(delta_pct)
    basis_val = float(basis) if basis is not None else None

    if delta_pct_val >= 0.10:
        classification = "Positive"
    elif delta_pct_val >= 0.0:
        classification = "Moderate"
    elif delta_pct_val >= -0.10:
        classification = "Limited"
    else:
        classification = "Negative"

    source_text = {
        "user_budget": "explicit capex budget",
        "inferred_lane": "inferred capex lane",
        "inferred_condition": "condition-implied zero capex",
        "unknown": "incomplete capex basis",
    }.get(capex_source, "current capex basis")

    sign = "+" if delta_val >= 0 else "-"
    value_text = f"{sign}${abs(delta_val):,.0f} ({delta_pct_val:+.1%})"
    basis_context = f" against all-in basis of ${basis_val:,.0f}" if basis_val is not None else ""
    return SignalMetric(
        label="Net Opportunity Delta",
        value_text=value_text,
        classification=classification,
        context=(
            f"BCV minus all-in basis is {delta_pct_val:+.1%}{basis_context}, using {source_text}. "
            "This is the clearest current-value opportunity check after required work."
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
    liquidity = report.get_module("liquidity_signal")
    score = liquidity.metrics.get("liquidity_score")
    label = str(liquidity.metrics.get("liquidity_label") or "Unavailable")
    dom = liquidity.metrics.get("days_on_market")
    market_view = str(liquidity.metrics.get("market_liquidity_view") or "unknown").replace("_", " ")
    comp_count = int(liquidity.metrics.get("comp_count") or 0)

    if score is None:
        classification = "Unavailable"
        value_text = "n/a"
        context = "Exit liquidity could not be computed from the available property and market evidence."
    else:
        score_val = float(score)
        classification = label
        value_text = f"{score_val:.0f}/100"
        dom_text = f"{int(dom)} DOM" if dom is not None else "DOM unavailable"
        context = (
            f"Canonical exit liquidity scores {score_val:.0f}/100, combining {dom_text}, "
            f"a {market_view} market backdrop, and {comp_count} usable comp{'s' if comp_count != 1 else ''}. "
            "Higher means the asset should be easier to exit if you need to sell."
        )

    return SignalMetric(
        label="Liquidity",
        value_text=value_text,
        classification=classification,
        context=context,
    )


def _build_optionality(report: AnalysisReport) -> SignalMetric | None:
    try:
        final_score = calculate_final_score(report)
        optionality = final_score.category_scores.get("optionality")
    except Exception:
        optionality = None

    if optionality is None:
        return SignalMetric(
            label="Optionality",
            value_text="n/a",
            classification="Unavailable",
            context="Optionality score could not be computed.",
        )

    score_val = float(optionality.score)
    physical = optionality.component_scores.get("physical_optionality")
    strategic = optionality.component_scores.get("strategic_optionality")

    if score_val >= 4.0:
        classification = "High"
    elif score_val >= 3.0:
        classification = "Moderate"
    elif score_val >= 2.25:
        classification = "Limited"
    else:
        classification = "Weak"

    component_text = []
    if physical is not None:
        component_text.append(f"physical {physical:.1f}/5")
    if strategic is not None:
        component_text.append(f"strategic {strategic:.1f}/5")
    suffix = f" ({', '.join(component_text)})" if component_text else ""

    return SignalMetric(
        label="Optionality",
        value_text=f"{score_val:.1f}/5{suffix}",
        classification=classification,
        context=(
            "Optionality blends physical upside such as ADU / expansion / redevelopment headroom "
            "with strategic flexibility across hold, rent, renovate, or teardown paths."
        ),
    )

from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.dash_app.view_models import CompareMetricRow, PropertyAnalysisView


@dataclass(slots=True)
class ComparisonReasonItem:
    factor_name: str
    weighted_delta_pct: int
    explanation: str


@dataclass(slots=True)
class ComparisonSummaryViewModel:
    winner: str
    confidence: int
    reasons_for_winner: list[ComparisonReasonItem] = field(default_factory=list)
    strengths_of_loser: list[ComparisonReasonItem] = field(default_factory=list)
    flip_condition: str = ""


@dataclass(slots=True)
class CompareSummary:
    rows: list[CompareMetricRow] = field(default_factory=list)
    why_different: list[str] = field(default_factory=list)
    comparison_summary: ComparisonSummaryViewModel | None = None


def build_compare_summary(views: list[PropertyAnalysisView]) -> CompareSummary:
    if not views:
        return CompareSummary()
    rows = _build_rows(views)
    why_different = _build_difference_notes(views)
    comparison_summary = _build_comparison_summary(views)
    return CompareSummary(rows=rows, why_different=why_different, comparison_summary=comparison_summary)


# Metrics where lower values are better for the buyer
_LOWER_IS_BETTER = {"ask_price", "taxes", "dom", "price_to_rent"}
_COMPARISON_WEIGHTS: dict[str, float] = {
    "entry_basis": 0.25,
    "income_support": 0.20,
    "capex_load": 0.15,
    "liquidity_profile": 0.15,
    "optionality": 0.15,
    "risk_skew": 0.10,
}


def _build_rows(views: list[PropertyAnalysisView]) -> list[CompareMetricRow]:
    metric_order = [
        ("Ask", "ask_price"),
        ("Fair Value", "bcv"),
        ("FV Delta vs Ask", "bcv_delta"),
        ("FV Range", "bcv_range"),
        ("Forward Base", "forward_base_case"),
        ("Forward Gap", "forward_gap_pct"),
        ("Lot Size", "lot_size"),
        ("Sqft", "sqft"),
        ("Taxes", "taxes"),
        ("Days Listed", "dom"),
        ("Income Support", "income_support_ratio"),
        ("Price-to-Rent", "price_to_rent"),
        ("Risk Score", "risk_score"),
        ("Town/County", "town_county_score"),
        ("Scarcity", "scarcity_score"),
        ("Confidence", "confidence"),
    ]
    rows: list[CompareMetricRow] = []
    for label, key in metric_order:
        higher_is_better = key not in _LOWER_IS_BETTER
        raw_values: dict[str, float | None] = {}
        formatted_values: dict[str, str] = {}

        for view in views:
            raw = view.compare_metrics.get(key)
            raw_values[view.label] = float(raw) if isinstance(raw, (int, float)) else None
            formatted_values[view.label] = _format_compare_value(raw, key)

        # Determine winner
        scorable = {lbl: v for lbl, v in raw_values.items() if v is not None}
        winner = ""
        if len(scorable) >= 2:
            if higher_is_better:
                winner = max(scorable, key=scorable.get)  # type: ignore[arg-type]
            else:
                winner = min(scorable, key=scorable.get)  # type: ignore[arg-type]

        # Compute deltas (relative to the best/winner value)
        deltas: dict[str, str] = {}
        if winner and len(scorable) >= 2:
            best_val = scorable[winner]
            for lbl, val in scorable.items():
                if lbl == winner:
                    deltas[lbl] = "best"
                elif best_val != 0:
                    abs_delta = val - best_val
                    pct_delta = (abs_delta / abs(best_val)) * 100
                    deltas[lbl] = _format_delta(abs_delta, pct_delta, key)
                else:
                    deltas[lbl] = ""

        rows.append(CompareMetricRow(
            metric=label,
            values=formatted_values,
            raw_values=raw_values,
            deltas=deltas,
            winner=winner,
            higher_is_better=higher_is_better,
        ))
    return rows


def _format_delta(abs_delta: float, pct_delta: float, key: str) -> str:
    """Format the delta between a property's value and the best value."""
    sign = "+" if abs_delta >= 0 else ""
    if key in {"ask_price", "bcv", "bcv_delta", "forward_base_case", "taxes"}:
        return f"{sign}${abs_delta:,.0f} ({sign}{pct_delta:.1f}%)"
    if key in {"confidence", "forward_gap_pct"}:
        return f"{sign}{abs_delta:.1%}"
    if key in {"lot_size"}:
        return f"{sign}{abs_delta:.2f} ac ({sign}{pct_delta:.1f}%)"
    if key in {"income_support_ratio", "price_to_rent"}:
        return f"{sign}{abs_delta:.1f}x ({sign}{pct_delta:.1f}%)"
    return f"{sign}{abs_delta:.1f} ({sign}{pct_delta:.1f}%)"


def _format_compare_value(value: object, key: str) -> str:
    if value is None:
        return "Unavailable"
    if key in {"ask_price", "bcv", "bcv_delta", "forward_base_case", "taxes"} and isinstance(value, (int, float)):
        if key == "bcv_delta":
            sign = "+" if value >= 0 else "-"
            return f"{sign}${abs(value):,.0f}"
        return f"${value:,.0f}"
    if key in {"income_support_ratio", "price_to_rent"} and isinstance(value, (int, float)):
        return f"{value:.1f}x"
    if key in {"confidence", "forward_gap_pct"} and isinstance(value, (int, float)):
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.1%}"
    if key in {"lot_size"} and isinstance(value, (int, float)):
        return f"{value:.2f} ac"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _build_difference_notes(views: list[PropertyAnalysisView]) -> list[str]:
    if len(views) < 2:
        return ["Load at least two properties to compare driver differences."]
    anchor = views[0]
    notes: list[str] = []
    for other in views[1:]:
        input_note = _largest_numeric_difference(anchor, other, ["ask_price", "sqft", "lot_size", "taxes"])
        if input_note:
            notes.append(f"{anchor.label} vs {other.label}: biggest input gap is {input_note}.")
        score_note = _largest_numeric_difference(anchor, other, ["bcv", "forward_base_case", "risk_score", "town_county_score", "scarcity_score"])
        if score_note:
            notes.append(f"{anchor.label} vs {other.label}: biggest score/value gap is {score_note}.")
        confidence_gap = abs((anchor.compare_metrics.get("confidence") or 0) - (other.compare_metrics.get("confidence") or 0))
        if confidence_gap >= 0.1:
            notes.append(
                f"{anchor.label} vs {other.label}: confidence differs by {confidence_gap:.0%}, mostly driven by evidence depth."
            )
        missing_anchor = set(anchor.compare_metrics.get("missing_inputs", []))
        missing_other = set(other.compare_metrics.get("missing_inputs", []))
        only_anchor = sorted(missing_anchor - missing_other)
        only_other = sorted(missing_other - missing_anchor)
        if only_anchor:
            notes.append(f"{anchor.label} is missing {', '.join(only_anchor[:3])} that {other.label} has.")
        if only_other:
            notes.append(f"{other.label} is missing {', '.join(only_other[:3])} that {anchor.label} has.")
    return notes[:8]


def _largest_numeric_difference(anchor: PropertyAnalysisView, other: PropertyAnalysisView, keys: list[str]) -> str | None:
    best_key: str | None = None
    best_diff = -1.0
    for key in keys:
        left = anchor.compare_metrics.get(key)
        right = other.compare_metrics.get(key)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            continue
        diff = abs(float(left) - float(right))
        if diff > best_diff:
            best_diff = diff
            best_key = key
    if best_key is None:
        return None
    left = anchor.compare_metrics.get(best_key)
    right = other.compare_metrics.get(best_key)
    label = best_key.replace("_", " ")
    if best_key in {"ask_price", "bcv", "forward_base_case", "taxes"}:
        return f"{label} ({anchor.label} ${left:,.0f} vs {other.label} ${right:,.0f})"
    if best_key == "lot_size":
        return f"{label} ({anchor.label} {left:.2f} ac vs {other.label} {right:.2f} ac)"
    return f"{label} ({anchor.label} {left:,.0f} vs {other.label} {right:,.0f})"


def _comparison_explanation(factor_name: str, winner: PropertyAnalysisView, loser: PropertyAnalysisView) -> str:
    if factor_name == "entry_basis":
        return f"{winner.label} has the better pricing setup: {winner.entry_basis_label} versus {loser.entry_basis_label}."
    if factor_name == "income_support":
        return f"{winner.label} has the stronger rent-support profile: {winner.income_support_label} versus {loser.income_support_label}."
    if factor_name == "capex_load":
        return f"{winner.label} carries the lighter capex burden: {winner.capex_load_label} versus {loser.capex_load_label}."
    if factor_name == "liquidity_profile":
        return f"{winner.label} has the cleaner exit profile: {winner.liquidity_profile_label} versus {loser.liquidity_profile_label}."
    if factor_name == "optionality":
        return f"{winner.label} offers the better upside structure: {winner.optionality_label} versus {loser.optionality_label}."
    return f"{winner.label} has the more favorable downside profile: {winner.risk_skew_label} versus {loser.risk_skew_label}."


def _flip_condition_from_factor(factor_name: str, winner: PropertyAnalysisView, loser: PropertyAnalysisView) -> str:
    if factor_name == "income_support":
        return f"Rent support would need to compress enough to erase {winner.label}'s current income edge over {loser.label}."
    if factor_name == "capex_load":
        return f"Capex would need to come in materially worse for {winner.label}, or cleaner for {loser.label}, to reverse the ranking."
    if factor_name in {"liquidity_profile", "risk_skew"}:
        return f"Liquidity would need to tighten for {winner.label}, or improve for {loser.label}, to flip the ranking."
    return f"Pricing would need to move enough to erase {winner.label}'s current entry-basis edge over {loser.label}."


def _build_comparison_summary(views: list[PropertyAnalysisView]) -> ComparisonSummaryViewModel | None:
    if len(views) < 2:
        return None

    view_a, view_b = views[0], views[1]
    factors_a = view_a.report_card.factor_scores if view_a.report_card is not None else {}
    factors_b = view_b.report_card.factor_scores if view_b.report_card is not None else {}
    if not factors_a or not factors_b:
        return None

    weighted_deltas: dict[str, float] = {}
    for factor_name, weight in _COMPARISON_WEIGHTS.items():
        weighted_deltas[factor_name] = (float(factors_a.get(factor_name, 0.0)) - float(factors_b.get(factor_name, 0.0))) * weight

    total_delta = sum(weighted_deltas.values())
    winner = view_a if total_delta >= 0 else view_b
    loser = view_b if winner is view_a else view_a
    winner_sign = 1 if winner is view_a else -1

    winner_edges: list[tuple[float, ComparisonReasonItem]] = []
    loser_edges: list[tuple[float, ComparisonReasonItem]] = []
    for factor_name, weighted_delta in weighted_deltas.items():
        signed_for_winner = weighted_delta * winner_sign
        impact_pct = int(round(abs(weighted_delta) * 100))
        if impact_pct == 0:
            continue
        item = ComparisonReasonItem(
            factor_name=factor_name,
            weighted_delta_pct=impact_pct,
            explanation=_comparison_explanation(factor_name, winner if signed_for_winner > 0 else loser, loser if signed_for_winner > 0 else winner),
        )
        if signed_for_winner > 0:
            winner_edges.append((abs(weighted_delta), item))
        elif signed_for_winner < 0:
            loser_edges.append((abs(weighted_delta), item))

    winner_edges.sort(key=lambda item: item[0], reverse=True)
    loser_edges.sort(key=lambda item: item[0], reverse=True)

    conviction_a = view_a.decision.conviction_score if view_a.decision is not None else 50
    conviction_b = view_b.decision.conviction_score if view_b.decision is not None else 50
    avg_conviction = (conviction_a + conviction_b) / 2.0
    score_gap = abs(float(view_a.final_score or 0.0) - float(view_b.final_score or 0.0))
    confidence = avg_conviction
    if avg_conviction < 60:
        confidence -= 12
    elif avg_conviction < 70:
        confidence -= 6
    if score_gap < 0.20:
        confidence -= 18
    elif score_gap < 0.40:
        confidence -= 10
    elif score_gap < 0.60:
        confidence -= 5
    comparison_confidence = max(0, min(int(round(confidence)), 100))

    flip_factor_order = ["income_support", "capex_load", "entry_basis", "liquidity_profile", "risk_skew", "optionality"]
    flip_factor = next((name for name in flip_factor_order if abs(weighted_deltas.get(name, 0.0)) > 0), None)
    if flip_factor is None:
        flip_factor = max(weighted_deltas, key=lambda key: abs(weighted_deltas[key]))

    return ComparisonSummaryViewModel(
        winner=winner.label,
        confidence=comparison_confidence,
        reasons_for_winner=[item for _, item in winner_edges[:3]],
        strengths_of_loser=[item for _, item in loser_edges[:3]],
        flip_condition=_flip_condition_from_factor(flip_factor, winner, loser),
    )

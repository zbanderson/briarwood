from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.dash_app.view_models import CompareMetricRow, PropertyAnalysisView


@dataclass(slots=True)
class CompareSummary:
    rows: list[CompareMetricRow] = field(default_factory=list)
    why_different: list[str] = field(default_factory=list)


def build_compare_summary(views: list[PropertyAnalysisView]) -> CompareSummary:
    if not views:
        return CompareSummary()
    rows = _build_rows(views)
    why_different = _build_difference_notes(views)
    return CompareSummary(rows=rows, why_different=why_different)


# Metrics where lower values are better for the buyer
_LOWER_IS_BETTER = {"ask_price", "risk_score", "taxes", "dom", "price_to_rent"}


def _build_rows(views: list[PropertyAnalysisView]) -> list[CompareMetricRow]:
    metric_order = [
        ("Ask", "ask_price"),
        ("BCV", "bcv"),
        ("BCV Delta vs Ask", "bcv_delta"),
        ("BCV Range", "bcv_range"),
        ("Forward Base", "forward_base_case"),
        ("Forward Gap", "forward_gap_pct"),
        ("Lot Size", "lot_size"),
        ("Sqft", "sqft"),
        ("Taxes", "taxes"),
        ("DOM", "dom"),
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

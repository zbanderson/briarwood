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


def _build_rows(views: list[PropertyAnalysisView]) -> list[CompareMetricRow]:
    metric_order = [
        ("Ask", "ask_price"),
        ("BCV", "bcv"),
        ("BCV Delta vs Ask", "bcv_delta"),
        ("BCV Range", "bcv_range"),
        ("Forward Base", "forward_base_case"),
        ("Lot Size", "lot_size"),
        ("Sqft", "sqft"),
        ("Taxes", "taxes"),
        ("DOM", "dom"),
        ("Income Support", "income_support_ratio"),
        ("Risk Score", "risk_score"),
        ("Town/County", "town_county_score"),
        ("Scarcity", "scarcity_score"),
        ("Confidence", "confidence"),
    ]
    rows: list[CompareMetricRow] = []
    for label, key in metric_order:
        values = {view.label: _format_compare_value(view.compare_metrics.get(key), key) for view in views}
        rows.append(CompareMetricRow(metric=label, values=values))
    return rows


def _format_compare_value(value: object, key: str) -> str:
    if value is None:
        return "Unavailable"
    if key in {"ask_price", "bcv", "bcv_delta", "forward_base_case", "taxes"} and isinstance(value, (int, float)):
        if key == "bcv_delta":
            sign = "+" if value >= 0 else "-"
            return f"{sign}${abs(value):,.0f}"
        return f"${value:,.0f}"
    if key == "income_support_ratio" and isinstance(value, (int, float)):
        return f"{value:.2f}x"
    if key == "confidence" and isinstance(value, (int, float)):
        return f"{value:.0%}"
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


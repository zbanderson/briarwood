"""
UI components for the Briarwood research platform.

This module now primarily serves Briarwood's advanced evidence mode.
The main Property Analysis workflow should stay decision-first and lighter.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from dash import dash_table, dcc, html
import plotly.graph_objects as go

from briarwood.dash_app.compare import CompareSummary
from briarwood.dash_app.components_quick_decision import render_recommendation_hero
from briarwood.dash_app.quick_decision import build_quick_decision_view
from briarwood.dash_app.theme import (
    ACCENT_BLUE, ACCENT_CYAN, ACCENT_GREEN, ACCENT_NAVY, ACCENT_ORANGE, ACCENT_RED, ACCENT_TEAL, ACCENT_YELLOW,
    BG_BASE, BG_SECONDARY, BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3, BG_SURFACE_4,
    BODY_TEXT_STYLE, BORDER, BORDER_SUBTLE,
    BTN_PRIMARY, BTN_SECONDARY,
    CARD_STYLE, CARD_STYLE_ELEVATED, CHART_HEIGHT_COMPACT, CHART_HEIGHT_STANDARD,
    FONT_DISPLAY, FONT_FAMILY, GRID_2, GRID_3, GRID_4,
    HEADING_XL_STYLE, HEADING_L_STYLE,
    LABEL_STYLE, PAGE_STYLE,
    PLOTLY_LAYOUT, PLOTLY_LAYOUT_COMPACT,
    SECTION_HEADER_STYLE,
    TABLE_STYLE_CELL, TABLE_STYLE_DATA_EVEN, TABLE_STYLE_DATA_ODD,
    TABLE_STYLE_HEADER, TABLE_STYLE_TABLE,
    TEXT_INVERSE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TONE_NEGATIVE_BG, TONE_NEGATIVE_BORDER, TONE_NEGATIVE_TEXT,
    TONE_NEUTRAL_BG, TONE_NEUTRAL_BORDER, TONE_NEUTRAL_TEXT,
    TONE_POSITIVE_BG, TONE_POSITIVE_BORDER, TONE_POSITIVE_TEXT,
    TONE_WARNING_BG, TONE_WARNING_BORDER, TONE_WARNING_TEXT,
    VALUE_STYLE_LARGE, VALUE_STYLE_MEDIUM,
    score_color, score_label, tone_badge_style, tone_color, verdict_color,
)
from briarwood.decision_model.scoring_config import SUB_FACTOR_LABELS
from briarwood.dash_app.view_models import (
    PropertyAnalysisView,
    build_evidence_rows,
    build_section_evidence_rows,
)
from briarwood.schemas import AnalysisReport

# ── Market benchmarks (NJ coastal averages) ──────────────────────────────────

_BENCHMARKS: dict[str, float] = {
    "ptr": 15.0,           # Price-to-rent ratio
    "cash_flow": -800.0,   # Monthly cash flow (coastal NJ)
    "town_score": 70.0,    # Town/county score
    "scarcity": 65.0,      # Scarcity support score (0-100)
    "dom": 45.0,           # Days on market
    "risk_score": 50.0,    # Risk score (0-100)
    "momentum": 60.0,      # Market momentum (0-100)
    "liquidity": 65.0,     # Exit liquidity (0-100)
}

# Whether lower values are "better" for this metric
_BENCHMARK_LOWER_BETTER: set[str] = {"ptr", "dom"}


def _benchmark_context(value: float, key: str) -> str | None:
    """Return a short benchmark comparison string, or None if no benchmark."""
    bm = _BENCHMARKS.get(key)
    if bm is None or value is None:
        return None
    if bm == 0:
        return None
    delta_pct = ((value - bm) / abs(bm)) * 100
    if abs(delta_pct) < 3:
        return f"avg {bm:.0f}"
    sign = "+" if delta_pct > 0 else ""
    return f"avg {bm:.0f}, {sign}{delta_pct:.0f}%"


def _benchmark_sublabel(value: float, key: str, fmt: str = "{:.0f}") -> str | None:
    """Return a formatted sublabel with benchmark context for inline_metric_strip."""
    ctx = _benchmark_context(value, key)
    if ctx is None:
        return None
    return f"(mkt {ctx})"


# ── Backwards-compat aliases ───────────────────────────────────────────────────

SIDEBAR_STYLE: dict = {
    "width": "clamp(260px, 24vw, 320px)",
    "padding": "12px",
    "borderRight": f"1px solid {BORDER}",
    "backgroundColor": BG_SURFACE,
    "display": "flex",
    "flexDirection": "column",
    "gap": "8px",
    "flexShrink": "0",
    "overflowY": "auto",
}

LANE_HEADER_STYLE: dict = {
    "position": "sticky",
    "top": "0",
    "zIndex": "2",
    "backgroundColor": BG_BASE,
    "paddingBottom": "6px",
}


# ═══════════════════════════════════════════════════════════════════════════════
# ATOMIC COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════


def metric_card(label: str, value: str, *, subtitle: str = "", tone: str = "neutral") -> html.Div:
    """Compact metric card — used sparingly, prefer inline_metric_strip."""
    color = tone_color(tone) if tone != "neutral" else TEXT_PRIMARY
    return html.Div(
        [
            html.Div(label, style=LABEL_STYLE),
            html.Div(value, style={**VALUE_STYLE_MEDIUM, "color": color}),
            html.Div(subtitle, style={"fontSize": "11px", "color": TEXT_MUTED}) if subtitle else None,
        ],
        style=CARD_STYLE,
    )


def inline_metric_strip(metrics: list[tuple[str, str, str | None]]) -> html.Div:
    """Dense inline metric row: Ask $875K | Fair Value $920K +5.1% | Base $1.01M"""
    items = []
    for i, (label, value, sublabel) in enumerate(metrics):
        if i > 0:
            items.append(html.Span("•", style={"margin": "0 8px", "color": BORDER}))
        children = [
            html.Span(label, style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase", "letterSpacing": "0.06em", "marginRight": "5px"}),
            html.Span(value, style={"fontSize": "14px", "fontWeight": "700", "color": TEXT_PRIMARY}),
        ]
        if sublabel:
            is_positive = sublabel.startswith("+")
            is_negative = sublabel.startswith("-") or sublabel.startswith("−")
            sub_color = TONE_POSITIVE_TEXT if is_positive else TONE_NEGATIVE_TEXT if is_negative else TEXT_MUTED
            children.append(html.Span(f" {sublabel}", style={"fontSize": "10px", "color": sub_color}))
        items.append(html.Span(children, style={"display": "inline-flex", "alignItems": "baseline", "gap": "0"}))
    return html.Div(items, style={"padding": "6px 0", "lineHeight": "1.45", "flexWrap": "wrap"})


def confidence_badge(confidence: float) -> html.Span:
    tone = "positive" if confidence >= 0.75 else "warning" if confidence >= 0.55 else "negative"
    return html.Span(f"{confidence:.0%}", style=tone_badge_style(tone))


def _confidence_level_color(level: str) -> str:
    return {"High": TONE_POSITIVE_TEXT, "Medium": TONE_WARNING_TEXT, "Low": TONE_NEGATIVE_TEXT}.get(level, TEXT_MUTED)


def section_confidence_indicator(confidence: float, *, section_key: str = "") -> html.Span:
    """Enhanced per-section confidence badge: dot + label + optional reason."""
    if confidence >= 0.75:
        level, tone_color_val, reason = "High confidence", TONE_POSITIVE_TEXT, ""
    elif confidence >= 0.55:
        level, tone_color_val = "Medium", TONE_WARNING_TEXT
        reason = ""  # reason filled by caller if needed
    else:
        level, tone_color_val = "Low", TONE_NEGATIVE_TEXT
        reason = ""
    dot = html.Span(style={"width": "7px", "height": "7px", "borderRadius": "50%", "backgroundColor": tone_color_val, "display": "inline-block", "marginRight": "4px", "flexShrink": "0"})
    label_text = f"{confidence:.0%} {level}"
    return html.Span(
        [dot, html.Span(label_text, style={"fontSize": "10px", "fontWeight": "500", "color": tone_color_val})],
        style={"display": "inline-flex", "alignItems": "center", "padding": "3px 8px 3px 6px", "backgroundColor": f"{tone_color_val}10", "borderRadius": "999px", "border": f"1px solid {tone_color_val}22"},
    )


def compact_badge(label: str, value: str, *, tone: str = "neutral") -> html.Span:
    return html.Span(f"{label}: {value}", style=tone_badge_style(tone))


def _render_calibrated_narrative(narrative: str, confidence_level: str) -> list:
    """Split calibration prefix from narrative and style it distinctly."""
    if confidence_level == "High" or not narrative:
        return [narrative]
    # The calibration note starts with "Note:" or "Caution:" and ends before "Overall score"
    for prefix in ("Caution:", "Note:"):
        if narrative.startswith(prefix):
            idx = narrative.find("Overall score")
            if idx > 0:
                calibration = narrative[:idx].strip()
                rest = narrative[idx:]
                return [
                    html.Span(calibration + " ", style={"fontStyle": "italic", "color": TEXT_MUTED}),
                    rest,
                ]
    return [narrative]


def _fmt_value(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def _parse_currency_text(value: str | None) -> float | None:
    if not value or value in {"—", "Unavailable"}:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fmt_compact(value: float | None) -> str:
    """Format as compact: $875K or $1.2M."""
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value / 1_000:.0f}K"


def _fmt_signed_currency(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.0f}"


def _fmt_signed_pct(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.1f}%"


def _capex_basis_source_label(source: str | None) -> str:
    mapping = {
        "user_budget": "Explicit CapEx",
        "inferred_lane": "Inferred CapEx",
        "inferred_condition": "Condition Implied",
        "unknown": "CapEx Unknown",
    }
    return mapping.get(source or "unknown", "CapEx Basis")


def simple_table(rows: list[dict[str, str]], *, page_size: int = 10) -> dash_table.DataTable:
    if not rows:
        rows = [{"Metric": "—", "Value": "—"}]
    columns = [{"name": key, "id": key} for key in rows[0].keys()]
    return dash_table.DataTable(
        data=rows,
        columns=columns,
        page_size=page_size,
        style_table=TABLE_STYLE_TABLE,
        style_header=TABLE_STYLE_HEADER,
        style_cell=TABLE_STYLE_CELL,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, **TABLE_STYLE_DATA_ODD},
            {"if": {"row_index": "even"}, **TABLE_STYLE_DATA_EVEN},
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

_COMPARE_CATEGORY_ORDER: list[tuple[str, str]] = [
    ("price_context", "Price Context"),
    ("economic_support", "Economic Support"),
    ("optionality", "Optionality"),
    ("market_position", "Market Position"),
    ("risk_layer", "Risk Layer"),
]


def _compare_category_score(view: PropertyAnalysisView, key: str) -> float | None:
    if not view.category_scores:
        return None
    category = view.category_scores.get(key)
    return None if category is None else float(category.score)


def _all_compare_scores(view: PropertyAnalysisView) -> dict[str, float | None]:
    scores = {"final_score": view.final_score}
    for key, _label in _COMPARE_CATEGORY_ORDER:
        scores[key] = _compare_category_score(view, key)
    return scores


def _median_value(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _disabled_chart() -> html.Div:
    return html.Div(style={"display": "none"})



# ═══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ═══════════════════════════════════════════════════════════════════════════════


def build_comp_positioning_chart_data(view: PropertyAnalysisView, report: AnalysisReport) -> dict[str, object]:
    comp_module = report.module_results.get("comparable_sales")
    payload = getattr(comp_module, "payload", None)
    comps_used = getattr(payload, "comps_used", []) if payload is not None else []
    sold_prices = [
        float(comp.adjusted_price)
        for comp in comps_used[:8]
        if getattr(comp, "adjusted_price", None) is not None
    ]
    active_prices = [
        _parse_currency_text(row.list_price)
        for row in list(view.comps.active_listing_rows)
    ]
    active_prices = [price for price in active_prices if price is not None]

    return {
        "sold_prices": sold_prices,
        "active_prices": active_prices,
        "subject_value": view.bcv,
        "ask_price": view.ask_price,
        "comp_count": len(sold_prices),
        "support_quality": view.property_decision_view.price_support.metrics.support_quality,
        "median_value": _median_value(sold_prices),
    }


def render_comp_positioning_chart(data: dict[str, object]) -> dcc.Graph | html.Div:
    sold_prices = [float(value) for value in (data.get("sold_prices") or []) if isinstance(value, (int, float))]
    active_prices = [float(value) for value in (data.get("active_prices") or []) if isinstance(value, (int, float))]
    subject_value = data.get("subject_value")
    ask_price = data.get("ask_price")
    median_value = data.get("median_value")

    if not sold_prices and not active_prices:
        return html.Div(
            "Comp positioning is unavailable because Briarwood did not return usable direct pricing points.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    fig = go.Figure()
    y_levels: list[str] = []

    if sold_prices:
        y_levels.append("Sold comps")
        fig.add_trace(
            go.Scatter(
                x=[min(sold_prices), max(sold_prices)],
                y=["Sold comps", "Sold comps"],
                mode="lines",
                name="Comp range",
                line={"color": ACCENT_BLUE, "width": 10},
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sold_prices,
                y=["Sold comps"] * len(sold_prices),
                mode="markers",
                name="Sold comps",
                marker={"size": 10, "color": BG_SURFACE, "line": {"color": ACCENT_BLUE, "width": 2}},
                hovertemplate="Adjusted comp: %{x:$,.0f}<extra></extra>",
            )
        )

    if active_prices:
        y_levels.append("Active listings")
        fig.add_trace(
            go.Scatter(
                x=[min(active_prices), max(active_prices)],
                y=["Active listings", "Active listings"],
                mode="lines",
                name="Active range",
                line={"color": ACCENT_ORANGE, "width": 6, "dash": "dot"},
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=active_prices,
                y=["Active listings"] * len(active_prices),
                mode="markers",
                name="Active listings",
                marker={"size": 10, "symbol": "square-open", "color": ACCENT_ORANGE, "line": {"color": ACCENT_ORANGE, "width": 2}},
                hovertemplate="Active listing: %{x:$,.0f}<extra></extra>",
            )
        )

    if isinstance(subject_value, (int, float)):
        subject_row = y_levels[0] if y_levels else "Sold comps"
        fig.add_trace(
            go.Scatter(
                x=[float(subject_value)],
                y=[subject_row],
                mode="markers",
                name="Fair value",
                marker={"size": 16, "symbol": "diamond", "color": ACCENT_TEAL, "line": {"color": BORDER, "width": 1.5}},
                hovertemplate="Fair value: %{x:$,.0f}<extra></extra>",
            )
        )

    if isinstance(ask_price, (int, float)):
        ask_row = y_levels[-1] if y_levels else "Sold comps"
        fig.add_trace(
            go.Scatter(
                x=[float(ask_price)],
                y=[ask_row],
                mode="markers",
                name="Ask",
                marker={"size": 14, "symbol": "diamond-open", "color": ACCENT_RED, "line": {"color": ACCENT_RED, "width": 2}},
                hovertemplate="Ask: %{x:$,.0f}<extra></extra>",
            )
        )

    if isinstance(median_value, (int, float)):
        fig.add_vline(
            x=float(median_value),
            line_dash="dash",
            line_color=TEXT_MUTED,
            annotation_text="Comp median",
            annotation_font_size=10,
            annotation_font_color=TEXT_MUTED,
            annotation_position="top",
        )

    layout = dict(PLOTLY_LAYOUT_COMPACT)
    layout["height"] = 220
    layout["showlegend"] = True
    layout["legend"] = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXT_SECONDARY, "size": 11},
    }
    layout["xaxis"] = {**layout.get("xaxis", {}), "tickformat": "$,.0f", "title": ""}
    layout["yaxis"] = {**layout.get("yaxis", {}), "title": "", "showgrid": False, "categoryorder": "array", "categoryarray": y_levels}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def build_financial_chart_data(view: PropertyAnalysisView, report: AnalysisReport) -> dict[str, object]:
    metrics = _economics_inputs(report, view)
    return {
        "months": ["Now", "6M", "12M"],
        "monthly_cost": metrics.get("gross_monthly_cost"),
        "rent_offset": metrics.get("monthly_rent"),
        "net_monthly": metrics.get("net_monthly_cost"),
    }


def render_financial_chart(data: dict[str, object]) -> dcc.Graph | html.Div:
    months = list(data.get("months") or ["Now", "6M", "12M"])
    monthly_cost = data.get("monthly_cost")
    rent_offset = data.get("rent_offset")
    net_monthly = data.get("net_monthly")

    numeric_series = [
        value
        for value in [monthly_cost, rent_offset, net_monthly]
        if isinstance(value, (int, float))
    ]
    if not numeric_series:
        return html.Div(
            "Financial chart is unavailable because Briarwood did not return usable monthly ownership inputs.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    fig = go.Figure()
    if isinstance(monthly_cost, (int, float)):
        fig.add_trace(
            go.Scatter(
                x=months,
                y=[float(monthly_cost)] * len(months),
                mode="lines+markers",
                name="Monthly cost",
                line={"color": ACCENT_RED, "width": 3},
                marker={"size": 7, "color": ACCENT_RED},
                hovertemplate="%{x}<br>Monthly cost: %{y:$,.0f}<extra></extra>",
            )
        )
    if isinstance(rent_offset, (int, float)):
        fig.add_trace(
            go.Scatter(
                x=months,
                y=[float(rent_offset)] * len(months),
                mode="lines+markers",
                name="Rent offset",
                line={"color": ACCENT_GREEN, "width": 3},
                marker={"size": 7, "color": ACCENT_GREEN},
                hovertemplate="%{x}<br>Rent offset: %{y:$,.0f}<extra></extra>",
            )
        )
    if isinstance(net_monthly, (int, float)):
        fig.add_trace(
            go.Scatter(
                x=months,
                y=[float(net_monthly)] * len(months),
                mode="lines+markers",
                name="Net monthly",
                line={"color": ACCENT_BLUE, "width": 3, "dash": "dot"},
                marker={"size": 7, "color": ACCENT_BLUE},
                hovertemplate="%{x}<br>Net monthly: %{y:$,.0f}<extra></extra>",
            )
        )

    layout = dict(PLOTLY_LAYOUT_COMPACT)
    layout["height"] = 240
    layout["showlegend"] = True
    layout["legend"] = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXT_SECONDARY, "size": 11},
    }
    layout["xaxis"] = {**layout.get("xaxis", {}), "title": "", "showgrid": False}
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f", "title": "", "gridcolor": BG_SURFACE_4}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def forward_waterfall_chart(report: AnalysisReport) -> dcc.Graph | html.Div:
    del report
    return _disabled_chart()
    """Readable bridge summary from BCV to Base Case."""
    bbb = report.module_results.get("bull_base_bear")
    if not bbb:
        return html.Div("No scenario data", style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"})

    m = bbb.metrics
    bcv = m.get("bcv_anchor")
    if not bcv:
        return html.Div("No BCV anchor", style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"})

    components = [
        ("Market", (m.get("base_market_drift_pct") or 0) * bcv),
        ("Location", (m.get("base_location_pct") or 0) * bcv),
        ("Risk", (m.get("base_risk_pct") or 0) * bcv),
        ("Optionality", (m.get("base_optionality_pct") or 0) * bcv),
    ]
    base_case = bcv + sum(delta for _, delta in components)
    rows = []
    for label, delta in components:
        tone = ACCENT_GREEN if delta >= 0 else ACCENT_RED
        width_pct = max(min(abs(delta) / max(abs(base_case - bcv), abs(delta), 1.0), 1.0) * 100, 12)
        rows.append(
            html.Div(
                [
                    html.Div(label, style={"fontSize": "11px", "fontWeight": "600", "color": TEXT_PRIMARY, "minWidth": "88px"}),
                    html.Div(
                        html.Div(style={"width": f"{width_pct:.0f}%", "height": "100%", "backgroundColor": tone, "borderRadius": "999px"}),
                        style={"height": "8px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "999px", "overflow": "hidden", "flex": "1"},
                    ),
                    html.Div(_fmt_signed_currency(delta), style={"fontSize": "11px", "fontWeight": "700", "color": tone, "minWidth": "72px", "textAlign": "right"}),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "10px"},
            )
        )

    return html.Div(
        [
            html.Div("Base Case Bridge", style=SECTION_HEADER_STYLE),
            html.Div(
                "This shows how Briarwood moves from current value support to the base-case outcome.",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "10px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Fair Value", style={**LABEL_STYLE, "marginBottom": "4px"}),
                            html.Div(_fmt_compact(bcv), style={"fontSize": "22px", "fontWeight": "700", "color": ACCENT_BLUE}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px"},
                    ),
                    html.Div(rows, style={**CARD_STYLE, "padding": "12px 14px", "display": "grid", "gap": "10px"}),
                    html.Div(
                        [
                            html.Div("Base Case", style={**LABEL_STYLE, "marginBottom": "4px"}),
                            html.Div(_fmt_compact(base_case), style={"fontSize": "22px", "fontWeight": "700", "color": ACCENT_BLUE}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px"},
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "160px 1fr 170px", "gap": "12px", "alignItems": "stretch"},
            ),
        ],
    )


def forward_range_chart(view: PropertyAnalysisView, *, compact: bool = False) -> dcc.Graph:
    del view, compact
    return _disabled_chart()
    """Scenario range: Downside → Base → Upside with ask reference line."""
    layout = dict(PLOTLY_LAYOUT_COMPACT if compact else PLOTLY_LAYOUT)
    layout["height"] = CHART_HEIGHT_COMPACT if compact else CHART_HEIGHT_STANDARD
    layout["showlegend"] = False
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f"}

    x_labels = ["Downside", "Base", "Upside"]
    y_values = [view.bear_case or 0, view.base_case or 0, view.bull_case or 0]
    texts = [view.forward.bear_value_text, view.forward.base_value_text, view.forward.bull_value_text]
    colors = [ACCENT_RED, ACCENT_BLUE, ACCENT_GREEN]

    if view.stress_case is not None:
        x_labels = ["Stress", "Downside", "Base", "Upside"]
        y_values = [view.stress_case, view.bear_case or 0, view.base_case or 0, view.bull_case or 0]
        texts = [view.forward.stress_case_value_text, view.forward.bear_value_text, view.forward.base_value_text, view.forward.bull_value_text]
        colors = [ACCENT_RED, ACCENT_RED, ACCENT_BLUE, ACCENT_GREEN]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_labels, y=y_values, mode="lines+markers+text",
        line={"color": ACCENT_BLUE, "width": 2},
        marker={"size": 8, "color": colors, "line": {"color": BORDER, "width": 1}},
        text=texts, textposition="top center",
        textfont={"color": TEXT_SECONDARY, "size": 10},
    ))
    fig.add_hline(y=view.ask_price or 0, line_dash="dot", line_color=TEXT_MUTED, annotation_text="Ask", annotation_font_color=TEXT_MUTED, annotation_font_size=10, annotation_position="right")
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def forward_fan_chart(
    view: PropertyAnalysisView,
    *,
    compact: bool = False,
    years: int = 1,
    horizon_label: str | None = None,
    chart_height: int | None = None,
) -> dcc.Graph | html.Div:
    del view, compact, years, horizon_label, chart_height
    return _disabled_chart()
    anchor_value = view.bcv or view.base_case
    if anchor_value is None:
        return html.Div(
            "Forward fan chart is unavailable because no BCV or base-case anchor was returned.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    fig = go.Figure()
    x_anchor = "Today"
    x_horizon = horizon_label or ("12M" if years <= 1 else f"{years}Y")

    def _project_terminal(anchor: float, one_year_terminal: float, total_years: int) -> float:
        if total_years <= 1:
            return one_year_terminal
        if anchor > 0 and one_year_terminal > 0:
            return anchor * ((one_year_terminal / anchor) ** total_years)
        return anchor + ((one_year_terminal - anchor) * total_years)

    fig.add_trace(
        go.Scatter(
            x=[x_anchor],
            y=[anchor_value],
            mode="markers",
            name="Today / BCV",
            marker={"size": 10 if compact else 11, "color": ACCENT_BLUE, "line": {"color": BORDER, "width": 1.5}},
            hovertemplate="Today / BCV<br>%{y:$,.0f}<extra></extra>",
        )
    )

    if view.bull_case is not None and view.bear_case is not None:
        bull_terminal = _project_terminal(anchor_value, view.bull_case, years)
        bear_terminal = _project_terminal(anchor_value, view.bear_case, years)
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon, x_horizon, x_anchor],
                y=[anchor_value, bull_terminal, bear_terminal, anchor_value],
                fill="toself",
                fillcolor="rgba(88, 166, 255, 0.14)",
                line={"color": "rgba(0,0,0,0)"},
                hoverinfo="skip",
                name="Bull / Bear Fan",
                showlegend=True,
            )
        )

    if view.bull_case is not None:
        bull_terminal = _project_terminal(anchor_value, view.bull_case, years)
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[anchor_value, bull_terminal],
                mode="lines",
                name="Upside",
                line={"color": ACCENT_GREEN, "width": 2, "dash": "dash"},
                hovertemplate="%{x}<br>Upside: %{y:$,.0f}<extra></extra>",
            )
        )

    if view.bear_case is not None:
        bear_terminal = _project_terminal(anchor_value, view.bear_case, years)
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[anchor_value, bear_terminal],
                mode="lines",
                name="Downside",
                line={"color": ACCENT_RED, "width": 2, "dash": "dash"},
                hovertemplate="%{x}<br>Downside: %{y:$,.0f}<extra></extra>",
            )
        )

    if view.base_case is not None:
        base_terminal = _project_terminal(anchor_value, view.base_case, years)
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[anchor_value, base_terminal],
                mode="lines+markers",
                name="Base",
                line={"color": ACCENT_BLUE, "width": 4},
                marker={"size": 7, "color": ACCENT_BLUE},
                hovertemplate="%{x}<br>Base: %{y:$,.0f}<extra></extra>",
            )
        )

    if view.stress_case is not None:
        stress_terminal = _project_terminal(anchor_value, view.stress_case, years)
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[anchor_value, stress_terminal],
                mode="lines",
                name="Stress",
                line={"color": ACCENT_RED, "width": 1.5, "dash": "dot"},
                hovertemplate="%{x}<br>Stress: %{y:$,.0f}<extra></extra>",
            )
        )

    if view.ask_price is not None:
        fig.add_hline(
            y=view.ask_price,
            line_dash="dot",
            line_color=TEXT_MUTED,
            annotation_text="Ask",
            annotation_font_color=TEXT_MUTED,
            annotation_font_size=10,
            annotation_position="right",
        )

    fig.add_shape(
        type="line",
        x0=x_anchor,
        x1=x_anchor,
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line={"dash": "dot", "color": ACCENT_ORANGE, "width": 1.5},
    )
    fig.add_annotation(
        x=x_anchor,
        y=1.02,
        xref="x",
        yref="paper",
        text="Today",
        showarrow=False,
        font={"color": ACCENT_ORANGE, "size": 11},
        xanchor="left",
    )

    layout = dict(PLOTLY_LAYOUT_COMPACT if compact else PLOTLY_LAYOUT)
    layout["height"] = chart_height or (CHART_HEIGHT_COMPACT if compact else CHART_HEIGHT_STANDARD)
    layout["legend"] = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": -0.28 if compact else -0.2,
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXT_SECONDARY, "size": 11},
    }
    layout["xaxis"] = {**layout.get("xaxis", {}), "title": "", "showgrid": False}
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f", "gridcolor": BG_SURFACE_4}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def forward_fan_chart_from_ask(
    view: PropertyAnalysisView,
    *,
    compact: bool = False,
    chart_height: int | None = None,
) -> dcc.Graph | html.Div:
    del view, compact, chart_height
    return _disabled_chart()
    """Forward fan anchored at ask_price instead of BCV.

    Shows the bull/base/bear terminal values at 12M, drawn from the ask price
    on day 0. When BCV > ask, the gap on day 0 is rendered as a green cushion
    marker so the user can see the value already being found before any
    forward growth.

    The bull/base/bear endpoint values are taken directly from the engine —
    they are NOT shifted upward by the cushion (Option A: honest to model).
    """
    ask = view.ask_price
    if ask is None:
        return html.Div(
            "Ask-anchored forward fan is unavailable because the ask price is missing.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    bcv = view.bcv
    cushion = (bcv - ask) if isinstance(bcv, (int, float)) else None

    fig = go.Figure()
    x_anchor = "Today"
    x_horizon = "12M"

    # Ask marker on day 0
    fig.add_trace(
        go.Scatter(
            x=[x_anchor],
            y=[ask],
            mode="markers",
            name=f"Ask {_fmt_compact(ask)}",
            marker={"size": 11 if not compact else 10, "color": ACCENT_ORANGE, "line": {"color": BORDER, "width": 1.5}},
            hovertemplate="Ask price<br>%{y:$,.0f}<extra></extra>",
        )
    )

    # Cushion marker (BCV on day 0) — only if we have a positive gap
    if cushion is not None and abs(cushion) > 1:
        cushion_color = ACCENT_GREEN if cushion > 0 else ACCENT_RED
        cushion_label = (
            f"+{_fmt_compact(cushion)} cushion"
            if cushion > 0
            else f"{_fmt_compact(cushion)} gap"
        )
        fig.add_trace(
            go.Scatter(
                x=[x_anchor],
                y=[bcv],
                mode="markers",
                name=f"Fair Value {_fmt_compact(bcv)}",
                marker={"size": 11, "color": cushion_color, "line": {"color": BORDER, "width": 1.5}, "symbol": "diamond"},
                hovertemplate=f"Briarwood fair value<br>%{{y:$,.0f}}<br>{cushion_label}<extra></extra>",
            )
        )
        # Vertical cushion band on day 0
        fig.add_shape(
            type="line",
            x0=x_anchor, x1=x_anchor,
            y0=ask, y1=bcv,
            line={"color": cushion_color, "width": 6},
        )

    # Bull / bear fan fill from ASK on day 0 to bull/bear on 12M
    if view.bull_case is not None and view.bear_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon, x_horizon, x_anchor],
                y=[ask, view.bull_case, view.bear_case, ask],
                fill="toself",
                fillcolor="rgba(88, 166, 255, 0.14)",
                line={"color": "rgba(0,0,0,0)"},
                hoverinfo="skip",
                name="Bull / Bear Range",
                showlegend=True,
            )
        )

    if view.bull_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[ask, view.bull_case],
                mode="lines",
                name="Upside",
                line={"color": ACCENT_GREEN, "width": 2, "dash": "dash"},
                hovertemplate="%{x}<br>Upside: %{y:$,.0f}<extra></extra>",
            )
        )
    if view.bear_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[ask, view.bear_case],
                mode="lines",
                name="Downside",
                line={"color": ACCENT_RED, "width": 2, "dash": "dash"},
                hovertemplate="%{x}<br>Downside: %{y:$,.0f}<extra></extra>",
            )
        )
    if view.base_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[ask, view.base_case],
                mode="lines+markers",
                name="Base",
                line={"color": ACCENT_BLUE, "width": 4},
                marker={"size": 7, "color": ACCENT_BLUE},
                hovertemplate="%{x}<br>Base: %{y:$,.0f}<extra></extra>",
            )
        )
    if view.stress_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[ask, view.stress_case],
                mode="lines",
                name="Stress",
                line={"color": ACCENT_RED, "width": 1.5, "dash": "dot"},
                hovertemplate="%{x}<br>Stress: %{y:$,.0f}<extra></extra>",
            )
        )

    layout = dict(PLOTLY_LAYOUT_COMPACT if compact else PLOTLY_LAYOUT)
    layout["height"] = chart_height or (CHART_HEIGHT_COMPACT if compact else CHART_HEIGHT_STANDARD)
    layout["legend"] = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": -0.28 if compact else -0.2,
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXT_SECONDARY, "size": 11},
    }
    layout["xaxis"] = {**layout.get("xaxis", {}), "title": "", "showgrid": False}
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f", "gridcolor": BG_SURFACE_4}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def renovation_justification_chart(view: PropertyAnalysisView, report: AnalysisReport | None = None, *, compact: bool = False) -> dcc.Graph | html.Div | None:
    del view, report, compact
    return None
    current_anchor = view.bcv or view.ask_price
    if current_anchor is None or view.base_case is None or view.bull_case is None or view.bear_case is None:
        return None

    # Use comp-derived renovation estimate when available, fall back to bull_case
    renovated_anchor = None
    if report is not None:
        reno_result = report.module_results.get("renovation_scenario")
        reno_payload = reno_result.payload if reno_result is not None and isinstance(reno_result.payload, dict) else None
        if reno_payload and reno_payload.get("enabled"):
            renovated_anchor = reno_payload.get("renovated_bcv")
        else:
            from briarwood.decision_model.scoring import estimate_comp_renovation_premium
            premium_data = estimate_comp_renovation_premium(report)
            renovated_anchor = premium_data.get("estimated_renovated_value")
    if renovated_anchor is None:
        renovated_anchor = view.bull_case if view.bull_case is not None else view.base_case
    x_anchor = "Today / Needs Work"
    x_future = "Value-Add Case"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[x_anchor],
            y=[current_anchor],
            mode="markers",
            name="Today / Fair Value",
            marker={"size": 12, "color": ACCENT_BLUE, "line": {"color": BORDER, "width": 1.5}},
            hovertemplate="Today / current fair value<br>%{y:$,.0f}<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[x_anchor, x_future, x_future, x_anchor],
            y=[current_anchor, view.bull_case, view.bear_case, current_anchor],
            fill="toself",
            fillcolor="rgba(88, 166, 255, 0.14)",
            line={"color": "rgba(0,0,0,0)"},
            hoverinfo="skip",
            name="Renovation Fan",
            showlegend=True,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[x_anchor, x_future],
            y=[current_anchor, view.bull_case],
            mode="lines",
            name="Upside",
            line={"color": ACCENT_GREEN, "width": 2, "dash": "dash"},
            hovertemplate="Upside value-add case<br>%{y:$,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[x_anchor, x_future],
            y=[current_anchor, view.bear_case],
            mode="lines",
            name="Downside",
            line={"color": ACCENT_RED, "width": 2, "dash": "dash"},
            hovertemplate="Downside value-add case<br>%{y:$,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[x_anchor, x_future],
            y=[current_anchor, view.base_case],
            mode="lines+markers",
            name="Base",
            line={"color": ACCENT_BLUE, "width": 4},
            marker={"size": 7, "color": ACCENT_BLUE},
            hovertemplate="Base value-add case<br>%{y:$,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[x_future],
            y=[renovated_anchor],
            mode="markers",
            name="Renovated Anchor",
            marker={"size": 11, "symbol": "diamond", "color": ACCENT_ORANGE, "line": {"color": BORDER, "width": 1.5}},
            hovertemplate="Renovated fair value<br>%{y:$,.0f}<extra></extra>",
        )
    )

    fig.add_annotation(
        x=x_anchor,
        y=current_anchor,
        text="Today",
        showarrow=False,
        yshift=18,
        font={"color": ACCENT_ORANGE, "size": 11},
    )
    fig.add_annotation(
        x=x_future,
        y=renovated_anchor,
        text="Value-Add",
        showarrow=False,
        yshift=18,
        font={"color": ACCENT_ORANGE, "size": 11},
    )

    layout = dict(PLOTLY_LAYOUT_COMPACT if compact else PLOTLY_LAYOUT)
    layout["height"] = CHART_HEIGHT_COMPACT if compact else CHART_HEIGHT_STANDARD
    layout["legend"] = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": -0.28 if compact else -0.2,
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXT_SECONDARY, "size": 11},
    }
    layout["xaxis"] = {**layout.get("xaxis", {}), "title": "", "showgrid": False}
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f", "gridcolor": BG_SURFACE_4}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def comp_positioning_dot_plot(view: PropertyAnalysisView, report: AnalysisReport) -> dcc.Graph | html.Div:
    del view, report
    return _disabled_chart()
    comp_module = report.module_results.get("comparable_sales")
    payload = getattr(comp_module, "payload", None)
    comps_used = getattr(payload, "comps_used", []) if payload is not None else []
    active_rows = list(view.comps.active_listing_rows)
    if not comps_used and not active_rows:
        return html.Div(
            "Comparable-sale positioning is unavailable because neither adjusted comps nor active listings were found.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    comps = list(comps_used[:5])
    adjusted_prices = [float(comp.adjusted_price) for comp in comps if getattr(comp, "adjusted_price", None) is not None]
    active_prices = [_parse_currency_text(row.list_price) for row in active_rows]
    active_prices = [price for price in active_prices if price is not None]
    if not adjusted_prices and not active_prices:
        return html.Div(
            "Comparable-sale positioning is unavailable because no comparable pricing points were returned.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    def _verification_color(value: str | None) -> str:
        normalized = (value or "").lower()
        if normalized == "mls_verified":
            return ACCENT_GREEN
        if normalized == "public_record_verified":
            return ACCENT_BLUE
        if normalized == "public_record_matched":
            return ACCENT_ORANGE
        if normalized == "questioned":
            return ACCENT_RED
        return TEXT_MUTED

    avg_adjusted = (sum(adjusted_prices) / len(adjusted_prices)) if adjusted_prices else None

    # Use similarity score as the Y axis for semantic meaning
    comp_similarities = [getattr(comp, "similarity_score", 0.5) for comp in comps]
    marker_sizes = [10 + (sim * 12) for sim in comp_similarities]

    fig = go.Figure()
    if adjusted_prices:
        fig.add_trace(
            go.Scatter(
                x=adjusted_prices,
                y=comp_similarities,
                mode="markers",
                name="Sold Comps",
                marker={
                    "size": marker_sizes,
                    "color": [_verification_color(getattr(comp, "sale_verification_status", None)) for comp in comps],
                    "line": {"color": BORDER, "width": 1},
                    "opacity": 0.9,
                },
                customdata=[
                    [
                        comp.address,
                        getattr(comp, "fit_label", "usable").title(),
                        getattr(comp, "sale_verification_status", "unverified").replace("_", " ").title(),
                        f"{getattr(comp, 'similarity_score', 0.0):.2f}",
                    ]
                    for comp in comps
                ],
                hovertemplate="%{customdata[0]}<br>Adjusted: %{x:$,.0f}<br>Fit: %{customdata[1]}<br>Verification: %{customdata[2]}<br>Similarity: %{customdata[3]}<extra></extra>",
            )
        )

    if active_prices:
        # Active listings don't have similarity scores — place them at a mid-range
        active_y = [0.4 + (i * 0.03) for i in range(len(active_prices))]
        fig.add_trace(
            go.Scatter(
                x=active_prices,
                y=active_y,
                mode="markers",
                name="Active Listings",
                marker={
                    "size": 11,
                    "symbol": "square-open",
                    "color": ACCENT_YELLOW,
                    "line": {"color": ACCENT_YELLOW, "width": 2},
                },
                customdata=[
                    [row.address, row.status, row.dom, row.condition]
                    for row in active_rows
                ],
                hovertemplate="%{customdata[0]}<br>List: %{x:$,.0f}<br>Status: %{customdata[1]}<br>DOM: %{customdata[2]}<br>Condition: %{customdata[3]}<extra></extra>",
            )
        )

    subject_x = view.ask_price if view.ask_price is not None else view.bcv
    if subject_x is not None:
        fig.add_trace(
            go.Scatter(
                x=[subject_x],
                y=[1.0],
                mode="markers",
                name="Subject Ask" if view.ask_price is not None else "Subject FV",
                marker={"size": 15, "symbol": "diamond", "color": ACCENT_TEAL, "line": {"color": BORDER, "width": 1.5}},
                hovertemplate=f"{view.address}<br>{'Ask' if view.ask_price is not None else 'Fair Value'}: %{{x:$,.0f}}<extra></extra>",
            )
        )
        fig.add_vline(
            x=subject_x,
            line_dash="dot",
            line_color=ACCENT_TEAL,
            annotation_text="Subject",
            annotation_font_size=10,
            annotation_font_color=ACCENT_TEAL,
            annotation_position="top",
        )

    if avg_adjusted is not None:
        fig.add_vline(
            x=avg_adjusted,
            line_dash="dash",
            line_color=TEXT_MUTED,
            annotation_text="Comp Avg",
            annotation_font_size=10,
            annotation_font_color=TEXT_MUTED,
            annotation_position="bottom right",
        )

    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = CHART_HEIGHT_STANDARD
    layout["showlegend"] = True
    layout["legend"] = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXT_SECONDARY, "size": 11},
    }
    layout["xaxis"] = {**layout.get("xaxis", {}), "tickformat": "$,.0f", "title": ""}
    layout["yaxis"] = {
        **layout.get("yaxis", {}),
        "title": {"text": "Similarity", "font": {"size": 10, "color": TEXT_MUTED}},
        "showticklabels": True,
        "tickformat": ".0%",
        "showgrid": True,
        "gridcolor": BG_SURFACE_4,
        "zeroline": False,
        "range": [0, 1.08],
    }
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def location_metrics_bars(view: PropertyAnalysisView, report: AnalysisReport) -> dcc.Graph | html.Div:
    del view, report
    return _disabled_chart()
    local_module = report.module_results.get("local_intelligence")
    location_module = report.module_results.get("location_intelligence")

    metrics: list[tuple[str, float, float]] = []
    neutral_benchmark = 50.0  # v1 fallback because current live contract does not expose county-level benchmark bars.

    if local_module is not None:
        local_metrics = local_module.metrics
        for label, key in [
            ("Momentum", "market_momentum_score"),
            ("Development", "development_activity_score"),
            ("Regulatory", "regulatory_trend_score"),
            ("Supply Pipeline", "supply_pipeline_score"),
            ("Sentiment", "sentiment_score"),
        ]:
            value = local_metrics.get(key)
            if isinstance(value, (int, float)):
                metrics.append((label, float(value), neutral_benchmark))

    momentum_module = report.module_results.get("market_momentum_signal")
    if momentum_module is not None:
        momentum_value = momentum_module.metrics.get("market_momentum_score")
        if isinstance(momentum_value, (int, float)):
            metrics.insert(0, ("Momentum", float(momentum_value), neutral_benchmark))

    if location_module is not None and len(metrics) < 5:
        location_metrics = location_module.metrics
        for label, key in [
            ("Geo Position", "location_score"),
            ("Geo Scarcity", "scarcity_score"),
        ]:
            value = location_metrics.get(key)
            if isinstance(value, (int, float)):
                metrics.append((label, float(value), neutral_benchmark))

    if not metrics:
        metrics = [
            ("Town / County", float(view.risk_location.town_score), neutral_benchmark),
            ("Scarcity", float(view.risk_location.scarcity_score), neutral_benchmark),
            ("Risk Resilience", float(view.risk_location.risk_score), neutral_benchmark),
        ]

    labels = [item[0] for item in metrics[:5]]
    values = [item[1] for item in metrics[:5]]
    benchmarks = [item[2] for item in metrics[:5]]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=benchmarks,
            y=labels,
            orientation="h",
            name="Benchmark",
            marker={"color": BG_SURFACE_4, "line": {"color": BORDER_SUBTLE, "width": 1}},
            hovertemplate="Neutral benchmark: %{x:.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            name="Town / Property",
            marker={"color": ACCENT_BLUE, "line": {"color": BORDER, "width": 1}},
            text=[f"{value:.0f}" for value in values],
            textposition="outside",
            hovertemplate="%{y}: %{x:.0f}<extra></extra>",
        )
    )

    layout = dict(PLOTLY_LAYOUT_COMPACT)
    layout["height"] = max(CHART_HEIGHT_STANDARD, 60 + (len(labels) * 34))
    layout["barmode"] = "overlay"
    layout["showlegend"] = False
    layout["xaxis"] = {**layout.get("xaxis", {}), "range": [0, 100], "title": "", "showgrid": True}
    layout["yaxis"] = {**layout.get("yaxis", {}), "autorange": "reversed", "showgrid": False}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def income_carry_waterfall(view: PropertyAnalysisView, report: AnalysisReport) -> dcc.Graph | html.Div:
    del view, report
    return _disabled_chart()
    income_module = report.module_results.get("income_support")
    payload = getattr(income_module, "payload", None)
    metrics = getattr(income_module, "metrics", {}) if income_module is not None else {}

    monthly_rent = metrics.get("monthly_rent_estimate")
    if monthly_rent is None and payload is not None:
        monthly_rent = getattr(payload, "monthly_rent_estimate", None) or getattr(payload, "gross_monthly_rent_before_vacancy", None)
    if monthly_rent is None:
        monthly_rent = _parse_currency_text(view.income_support.total_rent_text)
    if monthly_rent is None:
        return html.Div(
            "Income waterfall is unavailable because monthly rent support was not returned.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    monthly_principal_interest = getattr(payload, "monthly_principal_interest", None) if payload is not None else None
    monthly_taxes = getattr(payload, "monthly_taxes", None) if payload is not None else None
    monthly_insurance = getattr(payload, "monthly_insurance", None) if payload is not None else None
    monthly_maintenance = getattr(payload, "monthly_maintenance_reserve", None) if payload is not None else None
    monthly_hoa = getattr(payload, "monthly_hoa", None) if payload is not None else None
    net_cash_flow = metrics.get("monthly_cash_flow")

    steps: list[tuple[str, float, str]] = [("Rent", float(monthly_rent), "absolute")]
    for label, value in [
        ("Mortgage", monthly_principal_interest),
        ("Taxes", monthly_taxes),
        ("Insurance", monthly_insurance),
        ("Maintenance", monthly_maintenance),
        ("HOA", monthly_hoa),
    ]:
        if isinstance(value, (int, float)) and abs(value) > 0.01:
            steps.append((label, -float(value), "relative"))
    steps.append(("Net Cash Flow", float(net_cash_flow or 0.0), "total"))

    fig = go.Figure(
        go.Waterfall(
            x=[label for label, _, _ in steps],
            y=[value for _, value, _ in steps],
            measure=[measure for _, _, measure in steps],
            text=[_fmt_value(value) if measure == "absolute" or measure == "total" else f"-{_fmt_value(abs(value))}" for _, value, measure in steps],
            textposition="outside",
            connector={"line": {"color": BORDER, "width": 1}},
            increasing={"marker": {"color": ACCENT_GREEN}},
            decreasing={"marker": {"color": ACCENT_RED}},
            totals={"marker": {"color": ACCENT_BLUE}},
        )
    )

    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = CHART_HEIGHT_STANDARD
    layout["showlegend"] = False
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f", "title": ""}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def risk_breakdown_bars(view: PropertyAnalysisView) -> html.Div:
    """CSS-based horizontal bars for risk sub-factors (no Plotly overhead)."""
    if not view.category_scores or "risk_layer" not in view.category_scores:
        return html.Div()
    subs = view.category_scores["risk_layer"].sub_factors
    bars = []
    for sf in subs:
        sc = score_color(sf.score)
        pct = (sf.score / 5.0) * 100
        bars.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(sf.name.replace("_", " ").title(), style={"fontSize": "11px", "color": TEXT_MUTED}),
                            html.Span(f"{sf.score:.1f}", style={"fontSize": "11px", "fontWeight": "600", "color": sc}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "2px"},
                    ),
                    html.Div(
                        html.Div(style={"width": f"{pct}%", "height": "100%", "backgroundColor": sc, "borderRadius": "1px", "transition": "width 0.3s"}),
                        style={"height": "4px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden"},
                    ),
                ],
                style={"marginBottom": "5px"},
            )
        )
    return html.Div(bars)


def confidence_progress_bars(view: PropertyAnalysisView) -> html.Div:
    """Confidence per section as thin progress bars."""
    sections = view.evidence.section_confidences if view.evidence else []
    if not sections:
        return html.Div()
    bars = []
    for item in sections:
        pct = item.confidence * 100
        if pct >= 75:
            color = ACCENT_GREEN
        elif pct >= 50:
            color = ACCENT_YELLOW
        else:
            color = ACCENT_RED
        bars.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(item.label, style={"fontSize": "11px", "color": TEXT_MUTED}),
                            html.Span(f"{pct:.0f}%", style={"fontSize": "11px", "fontWeight": "600"}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "2px"},
                    ),
                    html.Div(
                        html.Div(style={"width": f"{pct}%", "height": "100%", "backgroundColor": color, "borderRadius": "1px"}),
                        style={"height": "3px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden"},
                    ),
                ],
                style={"marginBottom": "5px"},
            )
        )
    return html.Div(bars)


def confidence_component_bars(view: PropertyAnalysisView) -> html.Div:
    """Evidence-quality confidence split by underwriting dimension."""
    components = view.evidence.confidence_components if view.evidence else []
    if not components:
        return html.Div()
    bars = []
    for item in components:
        pct = item.confidence * 100
        weight_pct = round(item.weight * 100)
        if pct >= 75:
            color = ACCENT_GREEN
        elif pct >= 50:
            color = ACCENT_YELLOW
        else:
            color = ACCENT_RED
        bars.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(item.label, style={"fontSize": "11px", "color": TEXT_MUTED}),
                            html.Span(f"{pct:.0f}%  ·  wt {weight_pct}%", style={"fontSize": "11px", "fontWeight": "600"}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "2px"},
                    ),
                    html.Div(
                        html.Div(style={"width": f"{pct}%", "height": "100%", "backgroundColor": color, "borderRadius": "1px"}),
                        style={"height": "4px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden"},
                    ),
                    html.Div(item.reason, style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "3px", "lineHeight": "1.4"}),
                ],
                style={"marginBottom": "8px"},
            )
        )
    return html.Div(bars)


def _assumption_status_tone(status: str) -> tuple[str, str]:
    if status == "confirmed":
        return "positive", "Confirmed"
    if status == "estimated":
        return "warning", "Estimated"
    return "negative", "Missing"


def compact_assumption_summary_block(view: PropertyAnalysisView) -> html.Div | None:
    items = view.evidence.assumption_statuses if view.evidence else []
    if not items:
        return None

    grouped_keys = [
        ("Rent", ["rent"]),
        ("Financing", ["financing"]),
        ("Taxes", ["taxes"]),
        ("Insurance", ["insurance"]),
        ("Condition", ["condition_profile"]),
        ("CapEx", ["capex"]),
    ]
    lookup = {item.key: item for item in items}
    cards = []
    for label, keys in grouped_keys:
        item = next((lookup.get(key) for key in keys if lookup.get(key) is not None), None)
        if item is None:
            continue
        tone, status_label = _assumption_status_tone(item.status)
        tone_color = {
            "positive": TONE_POSITIVE_TEXT,
            "warning": TONE_WARNING_TEXT,
            "negative": TONE_NEGATIVE_TEXT,
        }[tone]
        cards.append(
            html.Div(
                [
                    html.Div(label, style={**LABEL_STYLE, "marginBottom": "6px"}),
                    html.Div(status_label, style={"fontSize": "14px", "fontWeight": "700", "color": tone_color, "marginBottom": "4px"}),
                    html.Div(item.value, style={"fontSize": "12px", "lineHeight": "1.45", "color": TEXT_SECONDARY}),
                ],
                style={**CARD_STYLE, "padding": "12px 14px"},
            )
        )

    return html.Div(
        [
            html.Div("ASSUMPTION SUMMARY", style={**SECTION_HEADER_STYLE, "fontSize": "12px", "letterSpacing": "0.12em", "marginBottom": "12px"}),
            html.Div(
                "This is the fast trust read for the underwriting inputs driving carry, value, and risk.",
                style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_MUTED, "marginBottom": "10px"},
            ),
            html.Div(cards, style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "10px"}),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "18px 20px", "marginBottom": "16px"},
    )


def _assumption_quality_snapshot(view: PropertyAnalysisView) -> tuple[str, str, str, list[html.Span]]:
    items = view.evidence.assumption_statuses if view.evidence else []
    if not items:
        return ("No assumption read", TEXT_MUTED, "No critical underwriting assumptions were classified.", [])

    confirmed = sum(1 for item in items if item.status == "confirmed")
    estimated = sum(1 for item in items if item.status == "estimated")
    missing = sum(1 for item in items if item.status == "missing")

    if missing:
        summary = f"{missing} missing"
        color = TONE_NEGATIVE_TEXT
        detail = "Critical inputs still missing"
    elif estimated:
        summary = f"{estimated} estimated"
        color = TONE_WARNING_TEXT
        detail = "Core underwriting still leans on estimates"
    else:
        summary = "Mostly confirmed"
        color = TONE_POSITIVE_TEXT
        detail = "Critical underwriting inputs are mostly confirmed"

    chips = []
    priority_keys = ["rent", "financing", "condition_profile", "capex", "insurance", "taxes"]
    lookup = {item.key: item for item in items}
    for key in priority_keys:
        item = lookup.get(key)
        if item is None:
            continue
        tone, status_label = _assumption_status_tone(item.status)
        chip_color = {
            "positive": TONE_POSITIVE_TEXT,
            "warning": TONE_WARNING_TEXT,
            "negative": TONE_NEGATIVE_TEXT,
        }[tone]
        chips.append(
            html.Span(
                f"{item.label}: {status_label}",
                style={
                    "padding": "4px 8px",
                    "borderRadius": "999px",
                    "fontSize": "11px",
                    "fontWeight": "600",
                    "letterSpacing": "0.02em",
                    "backgroundColor": f"{chip_color}18",
                    "border": f"1px solid {chip_color}33",
                    "color": chip_color,
                },
            )
        )
    return (summary, color, f"{confirmed} confirmed · {estimated} estimated · {missing} missing", chips)


def _header_pricing_snapshot(view: PropertyAnalysisView) -> list[tuple[str, str, str | None]]:
    metrics = [("Ask", _fmt_compact(view.ask_price), None)]
    if view.bcv is not None:
        delta_hint = gap_pct_text(view) if view.mispricing_pct is not None else None
        metrics.append(("Fair Value", _fmt_compact(view.bcv), delta_hint))
    if view.base_case is not None:
        metrics.append(("Base", _fmt_compact(view.base_case), None))
    return metrics


def improve_analysis_block(view: PropertyAnalysisView) -> html.Div | None:
    """Top-3 missing inputs that would most improve analysis confidence."""
    impacts = view.top_input_impacts
    if not impacts:
        return None
    rows = []
    for item in impacts:
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(item.field_label, style={"fontSize": "13px", "fontWeight": "600", "color": TEXT_PRIMARY}),
                            html.Span(f" → {item.impact_description}", style={"fontSize": "12px", "color": TONE_POSITIVE_TEXT}),
                        ],
                        style={"lineHeight": "1.5"},
                    ),
                ],
                style={"padding": "6px 0", "borderBottom": f"1px solid {BORDER_SUBTLE}"},
            )
        )
    return html.Div(
        [
            html.Div("Improve This Analysis", style={**SECTION_HEADER_STYLE, "color": ACCENT_BLUE}),
            html.Div(
                "Adding these inputs would most improve confidence:",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "6px"},
            ),
            html.Div(rows, style={"display": "grid", "gap": "0"}),
        ],
        style={**CARD_STYLE, "padding": "10px 12px", "borderLeft": f"3px solid {ACCENT_BLUE}"},
    )


def assumptions_transparency_block(view: PropertyAnalysisView) -> html.Div:
    """Compact distinction between model assumptions and user inputs."""
    items = view.evidence.transparency_items if view.evidence else []
    if not items:
        return html.Div()

    def _source_badge(item) -> html.Span:
        tone = "positive" if item.source_kind == "confirmed" else "warning" if item.source_kind == "inferred" else "neutral"
        return html.Span(item.source_label, style=tone_badge_style(tone))

    rows = []
    for item in items:
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(item.label, style={"fontSize": "11px", "color": TEXT_MUTED, "textTransform": "uppercase"}),
                            html.Div(item.value, style={"fontSize": "13px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginTop": "2px"}),
                        ],
                        style={"minWidth": "140px"},
                    ),
                    html.Div(
                        [
                            _source_badge(item),
                            html.Div(item.note, style={"fontSize": "11px", "color": TEXT_MUTED, "lineHeight": "1.4", "marginTop": "4px"}),
                        ],
                        style={"flex": "1"},
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "150px 1fr",
                    "gap": "12px",
                    "padding": "8px 0",
                    "borderBottom": f"1px solid {BORDER_SUBTLE}",
                },
            )
        )

    return html.Div(
        [
            html.Div("Model Assumptions vs User Inputs", style=SECTION_HEADER_STYLE),
            html.Div(
                "This block distinguishes what Briarwood inferred, what the user confirmed, and which entries are preferences rather than factual inputs.",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "6px"},
            ),
            html.Div(rows, style={"display": "grid", "gap": "0"}),
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def metric_input_status_block(view: PropertyAnalysisView) -> html.Div:
    """Audit trail for whether top-line metrics are fact-based, estimated, or unresolved."""
    items = view.evidence.metric_statuses if view.evidence else []
    if not items:
        return html.Div()

    tone_map = {
        "fact_based": ("positive", "Fact Based"),
        "user_confirmed": ("positive", "User Confirmed"),
        "estimated": ("warning", "Estimated"),
        "unresolved": ("negative", "Unresolved"),
    }
    rows = []
    for item in items:
        tone, label = tone_map.get(item.status, ("neutral", item.status.replace("_", " ").title()))
        detail_parts = []
        if item.facts_used:
            detail_parts.append(f"facts: {', '.join(item.facts_used[:3])}")
        if item.user_inputs_used:
            detail_parts.append(f"user: {', '.join(item.user_inputs_used[:3])}")
        if item.assumptions_used:
            detail_parts.append(f"assumptions: {', '.join(item.assumptions_used[:3])}")
        if item.missing_inputs:
            detail_parts.append(f"missing: {', '.join(item.missing_inputs[:3])}")
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(item.label, style={"fontSize": "11px", "color": TEXT_MUTED, "textTransform": "uppercase"}),
                            html.Div(item.confidence_impact, style={"fontSize": "11px", "color": TEXT_SECONDARY, "lineHeight": "1.4", "marginTop": "3px"}),
                            html.Div(" | ".join(detail_parts), style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "4px", "lineHeight": "1.4"}) if detail_parts else None,
                        ]
                    ),
                    html.Div(compact_badge("Status", label, tone=tone), style={"justifySelf": "end"}),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "1fr auto",
                    "gap": "12px",
                    "padding": "8px 0",
                    "borderBottom": f"1px solid {BORDER_SUBTLE}",
                },
            )
        )

    gap_block = None
    if view.evidence.gap_prompt_fields:
        gap_block = html.Div(
            [
                html.Div("To Strengthen This Analysis", style=SECTION_HEADER_STYLE),
                html.Div(
                    ", ".join(field.replace("_", " ") for field in view.evidence.gap_prompt_fields[:8]),
                    style={"fontSize": "11px", "color": TEXT_SECONDARY, "lineHeight": "1.5"},
                ),
            ],
            style={**CARD_STYLE, "padding": "8px 10px", "marginTop": "8px"},
        )

    return html.Div(
        [
            html.Div("Metric Basis & Gaps", style=SECTION_HEADER_STYLE),
            html.Div(
                "Each core metric is labeled as fact-based, user-confirmed, estimated, or unresolved based on the actual inputs used.",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "6px"},
            ),
            html.Div(rows, style={"display": "grid", "gap": "0"}),
            gap_block,
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# V2 COMPONENTS — Decision-first tear sheet layout
# ═══════════════════════════════════════════════════════════════════════════════


def _sub_factor_display_name(name: str) -> str:
    """Human-readable sub-factor label from the scoring config map."""
    return SUB_FACTOR_LABELS.get(name, name.replace("_", " ").title())


def _extract_diverse_items(view: PropertyAnalysisView, *, best: bool, count: int = 3) -> list[str]:
    """Pick top strengths or risks ensuring diversity across categories."""
    if not view.category_scores:
        return []
    all_sfs: list[tuple[float, str, str, str]] = []
    for cat_name, cat in view.category_scores.items():
        for sf in cat.sub_factors:
            all_sfs.append((sf.score, sf.name, sf.evidence, cat_name))
    all_sfs.sort(key=lambda x: x[0], reverse=best)
    items: list[str] = []
    seen_cats: set[str] = set()
    threshold = 3.5 if best else 3.0
    for score, _name, evidence, cat in all_sfs:
        if len(items) >= count:
            break
        passes = (score >= threshold) if best else (score <= threshold)
        if cat not in seen_cats and passes:
            items.append(evidence)
            seen_cats.add(cat)
    # Fill remaining from any category
    for score, _name, evidence, _cat in all_sfs:
        if len(items) >= count:
            break
        if evidence not in items:
            passes = (score >= 3.0) if best else (score < 3.5)
            if passes:
                items.append(evidence)
    return items[:count]


_LENS_DISPLAY = {
    "owner": ("Primary Residence", "🏠"),
    "investor": ("Rental Investment", "💰"),
    "developer": ("Value-Add / Renovation", "🔧"),
}



def _compact_lens_badge(label: str, score: float | None, *, inverted: bool = False) -> html.Div | None:
    """Compact lens badge for non-primary lenses."""
    if score is None:
        return None
    display = (6.0 - score) if inverted else score
    sc = score_color(display)
    return html.Div(
        [
            html.Span(label, style={"color": TEXT_MUTED, "fontSize": "11px"}),
            html.Span(f"{score:.1f}", style={"fontWeight": "700", "color": sc, "fontSize": "13px"}),
            html.Span(score_label(display), style={"fontSize": "11px", "color": sc}),
        ],
        style={
            "display": "inline-flex", "alignItems": "center", "gap": "6px",
            "padding": "6px 12px", "backgroundColor": BG_SURFACE_2,
            "border": f"1px solid {BORDER}", "borderRadius": "4px",
        },
    )


def _render_v2_category_bars(view: PropertyAnalysisView) -> html.Div:
    """Compact horizontal bars for each category with score labels."""
    if not view.category_scores:
        return html.Div()
    cats = [
        ("Price Context", "price_context"),
        ("Economic Support", "economic_support"),
        ("Optionality", "optionality"),
        ("Market Position", "market_position"),
        ("Risk Layer", "risk_layer"),
    ]
    rows = []
    for name, key in cats:
        cat = view.category_scores.get(key)
        if cat is None:
            continue
        sc = score_color(cat.score)
        pct = (cat.score / 5.0) * 100
        sl = score_label(cat.score)
        rows.append(
            html.Div(
                [
                    html.Div(name, style={"width": "130px", "fontSize": "11px", "color": TEXT_MUTED}),
                    html.Div(
                        html.Div(style={"width": f"{pct}%", "height": "100%", "backgroundColor": sc, "borderRadius": "2px", "transition": "width 0.3s ease"}),
                        style={"flex": "1", "height": "8px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "2px", "overflow": "hidden"},
                    ),
                    html.Div(
                        [
                            html.Span(f"{cat.score:.1f}", style={"fontSize": "13px", "fontWeight": "700", "color": sc}),
                            html.Span(f" {sl}", style={"fontSize": "11px", "color": sc, "marginLeft": "4px"}),
                        ],
                        style={"width": "100px", "textAlign": "right"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "6px"},
            )
        )
    return html.Div(rows)


def _sub_factor_icon(score: float) -> tuple[str, str]:
    """Return icon and color for a sub-factor score."""
    if score >= 4.0:
        return "●", ACCENT_GREEN
    if score >= 3.0:
        return "●", ACCENT_BLUE
    if score >= 2.5:
        return "○", ACCENT_YELLOW
    return "○", ACCENT_ORANGE


def render_sub_factor_row_v2(sf: object) -> html.Div:
    """V2 sub-factor row: human-readable question, no dots, no weight, color-coded badge."""
    question = _sub_factor_display_name(sf.name)
    sc = score_color(sf.score)
    sl = score_label(sf.score)
    icon, icon_color = _sub_factor_icon(sf.score)

    return html.Div(
        [
            html.Span(icon, style={"color": icon_color, "fontSize": "14px", "marginRight": "12px", "marginTop": "2px", "flexShrink": "0"}),
            html.Div(
                [
                    html.Div(question, style={"fontSize": "13px", "fontWeight": "600", "marginBottom": "2px", "color": TEXT_PRIMARY}),
                    html.Div(sf.evidence, style={"fontSize": "11px", "color": TEXT_MUTED, "lineHeight": "1.5"}),
                ],
                style={"flex": "1"},
            ),
            html.Div(
                [
                    html.Span(f"{sf.score:.1f}", style={"fontWeight": "700", "color": sc}),
                    html.Span(f" {sl}", style={"fontSize": "11px", "color": sc, "marginLeft": "4px"}),
                ],
                style={
                    "padding": "4px 8px", "backgroundColor": BG_SURFACE_2,
                    "borderRadius": "4px", "fontSize": "11px", "whiteSpace": "nowrap", "flexShrink": "0",
                },
            ),
        ],
        style={"display": "flex", "alignItems": "flex-start", "padding": "8px 0", "borderBottom": f"1px solid {BORDER_SUBTLE}"},
    )


def render_category_section_v2(
    title: str,
    category_key: str,
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    metrics_strip: html.Div | None = None,
    chart: html.Div | dcc.Graph | None = None,
    extra_content: html.Div | None = None,
    default_open: bool = False,
) -> html.Div:
    """V2 category section: no weights, human-readable sub-factors, top 2 drivers by default."""
    cat = view.category_scores.get(category_key) if view.category_scores else None
    if cat is None:
        return html.Div()
    sc = score_color(cat.score)
    sl = score_label(cat.score)

    # Sort sub-factors: best first when section is strong, worst first when weak
    sorted_sfs = sorted(cat.sub_factors, key=lambda sf: sf.score, reverse=True) if cat.sub_factors else []
    top_drivers = sorted_sfs[:2]
    remaining_sfs = sorted_sfs[2:]

    summary_el = html.Summary(
        html.Div(
            [
                html.Span(title, style={**SECTION_HEADER_STYLE, "marginBottom": "0", "display": "inline", "fontSize": "13px", "letterSpacing": "0.5px"}),
                html.Span(
                    f"  {cat.score:.1f} / 5",
                    style={"fontSize": "15px", "fontWeight": "600", "color": sc, "marginLeft": "10px"},
                ),
                html.Span(
                    sl,
                    style={"fontSize": "11px", "fontWeight": "600", "color": sc, "marginLeft": "6px",
                           "padding": "2px 8px", "backgroundColor": BG_SURFACE_2, "borderRadius": "3px",
                           "border": f"1px solid {sc}40"},
                ),
                html.Div(
                    html.Div(style={"width": f"{(cat.score / 5.0) * 100:.0f}%", "height": "100%", "backgroundColor": sc, "borderRadius": "1px"}),
                    style={"height": "4px", "width": "60px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden", "marginLeft": "12px", "display": "inline-block", "verticalAlign": "middle"},
                ),
            ],
            style={"display": "flex", "alignItems": "baseline"},
        ),
        style={
            "cursor": "pointer", "padding": "12px 16px",
            "borderBottom": f"2px solid {BORDER}", "listStyle": "none",
            "outline": "none", "userSelect": "none",
        },
    )

    body_children = []
    if metrics_strip:
        body_children.append(metrics_strip)
    if chart:
        body_children.append(html.Div(chart, style={"marginTop": "6px"}))

    # Key Drivers section (always visible when expanded)
    if top_drivers:
        body_children.append(
            html.Div(
                [
                    html.Div("KEY DRIVERS", style={**SECTION_HEADER_STYLE, "marginBottom": "8px", "marginTop": "12px"}),
                    html.Div([render_sub_factor_row_v2(sf) for sf in top_drivers]),
                ],
            )
        )

    # "Show all N sub-factors" toggle for remaining
    if remaining_sfs:
        body_children.append(
            html.Details(
                [
                    html.Summary(
                        f"Show all {len(cat.sub_factors)} sub-factors",
                        style={"fontSize": "11px", "color": ACCENT_BLUE, "cursor": "pointer", "padding": "6px 0", "listStyle": "none", "outline": "none"},
                    ),
                    html.Div([render_sub_factor_row_v2(sf) for sf in sorted_sfs], style={"marginTop": "4px"}),
                ],
                open=False,
                style={"marginTop": "8px"},
            )
        )

    if extra_content:
        body_children.append(extra_content)

    return html.Details(
        [summary_el, html.Div(body_children, style={"padding": "8px 16px 16px"})],
        open=default_open,
        style={"marginBottom": "8px", "backgroundColor": BG_SURFACE, "border": f"1px solid {BORDER}", "borderRadius": "4px"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY STRIP (property header in tear sheet)
# ═══════════════════════════════════════════════════════════════════════════════


def summary_strip(view: PropertyAnalysisView) -> html.Div:
    gap_pct = view.mispricing_pct
    if gap_pct is not None:
        sign = "+" if gap_pct >= 0 else ""
        gap_text = f"{sign}{gap_pct * 100:.1f}%"
    else:
        gap_text = "—"

    return html.Div(
        [
            # Verdict + narrative
            html.Div(
                [
                    html.Div(_summary_verdict(view), style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginBottom": "3px"}),
                    html.Div(view.memo_summary, style={"fontSize": "11px", "color": TEXT_SECONDARY, "lineHeight": "1.5"}),
                ],
                style={"flex": "1"},
            ),
            # Inline metrics
            html.Div(
                [confidence_badge(view.overall_confidence), html.Span(view.evidence_mode, style=tone_badge_style("neutral"))],
                style={"display": "flex", "gap": "6px", "alignItems": "center", "flexShrink": "0"},
            ),
        ],
        style={"display": "flex", "justifyContent": "space-between", "alignItems": "start", "gap": "16px", "paddingBottom": "12px", "borderBottom": f"1px solid {BORDER_SUBTLE}", "marginBottom": "12px"},
    )


def _summary_verdict(view: PropertyAnalysisView) -> str:
    if view.decision is not None and view.decision.recommendation:
        return view.decision.recommendation.replace("_", " ")
    return view.pricing_view.replace("_", " ").title() if view.pricing_view else "Decision pending"


def _primary_risk_text(view: PropertyAnalysisView) -> str:
    if view.decision is not None and view.decision.primary_risk:
        return view.decision.primary_risk
    if view.top_risks:
        return view.top_risks[0]
    return "No primary risk surfaced yet."


def _supporting_reasons(view: PropertyAnalysisView) -> list[str]:
    if view.decision is not None and view.decision.supporting_factors:
        return list(view.decision.supporting_factors)
    reasons = [
        item
        for item in [
            view.decision.primary_reason if view.decision is not None else "",
            view.decision.secondary_reason if view.decision is not None else "",
        ]
        if item
    ]
    return reasons[:3]


def _decision_dependencies(view: PropertyAnalysisView) -> list[str]:
    if view.decision is not None and view.decision.dependencies:
        return list(view.decision.dependencies)
    if view.decision is not None and view.decision.required_beliefs:
        return list(view.decision.required_beliefs[:3])
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# TEAR SHEET DECISION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _section_confidence_lookup(view: PropertyAnalysisView) -> dict[str, float]:
    return {
        item.label.lower(): item.confidence
        for item in view.evidence.section_confidences
    }


def _avg_confidence(values: list[float | None], fallback: float) -> float:
    usable = [value for value in values if value is not None]
    if not usable:
        return fallback
    return sum(usable) / len(usable)


def _section_confidence(view: PropertyAnalysisView, section_key: str) -> float:
    lookup = _section_confidence_lookup(view)
    component_lookup = {item.key: item.confidence for item in view.evidence.confidence_components}
    mapping = {
        "price": _avg_confidence([lookup.get("value"), lookup.get("comps")], view.overall_confidence),
        "economics": _avg_confidence([lookup.get("income"), lookup.get("rental")], view.overall_confidence),
        "forward": lookup.get("forward", view.overall_confidence),
        "risk": _avg_confidence(
            [
                component_lookup.get("capex"),
                component_lookup.get("liquidity"),
                component_lookup.get("market"),
                component_lookup.get("rent"),
            ],
            view.overall_confidence,
        ),
        "optionality": _avg_confidence(
            [component_lookup.get("capex"), lookup.get("location"), lookup.get("forward")],
            view.overall_confidence,
        ),
        "evidence": view.overall_confidence,
    }
    return mapping.get(section_key, view.overall_confidence)


def _metric_status_map(view: PropertyAnalysisView) -> dict[str, object]:
    return {item.key: item for item in view.evidence.metric_statuses}


def _metric_status_label(status: str) -> str:
    labels = {
        "fact_based": "Fact-Based",
        "user_confirmed": "User Confirmed",
        "estimated": "Estimated",
        "unresolved": "Unresolved",
    }
    return labels.get(status, status.replace("_", " ").title())


def _status_tone(status: str) -> str:
    return {
        "fact_based": "positive",
        "user_confirmed": "positive",
        "estimated": "warning",
        "unresolved": "negative",
    }.get(status, "neutral")


def _section_status_chips(view: PropertyAnalysisView, metric_keys: list[str]) -> html.Div | None:
    status_map = _metric_status_map(view)
    chips = []
    for key in metric_keys:
        item = status_map.get(key)
        if item is None:
            continue
        chips.append(compact_badge(item.label, _metric_status_label(item.status), tone=_status_tone(item.status)))
    if not chips:
        return None
    return html.Div(chips, style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "marginTop": "8px"})


def _section_missing_note(view: PropertyAnalysisView, metric_keys: list[str]) -> html.Div | None:
    status_map = _metric_status_map(view)
    missing = []
    for key in metric_keys:
        item = status_map.get(key)
        if item is None:
            continue
        for label in item.missing_inputs[:2]:
            if label not in missing:
                missing.append(label)
    if not missing:
        return None
    return html.Div(
        [
            html.Span("Missing facts: ", style={"fontWeight": "600", "color": TONE_WARNING_TEXT}),
            html.Span(", ".join(missing[:4]), style={"color": TEXT_MUTED}),
        ],
        style={"fontSize": "11px", "marginTop": "8px"},
    )


def _question_section(
    question: str,
    answer: str,
    *,
    section_id: str | None = None,
    confidence: float,
    summary: str | None = None,
    insight_callout: html.Div | None = None,
    metrics_strip: html.Div | None = None,
    chart: html.Div | dcc.Graph | None = None,
    extra_content: html.Div | None = None,
    basis_chips: html.Div | None = None,
    missing_note: html.Div | None = None,
    default_open: bool = False,
) -> html.Div:
    """Collapsible question section. Answer visible in collapsed header."""
    # Header line: question + enhanced confidence indicator (always visible)
    header = html.Summary(
        html.Div(
            [
                html.Div(
                    [
                        html.Span(question, style={**SECTION_HEADER_STYLE, "marginBottom": "0", "display": "inline", "fontSize": "12px", "letterSpacing": "0.08em"}),
                        section_confidence_indicator(confidence),
                    ],
                    style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "6px"},
                ),
                # Answer text — visible even when collapsed
                html.Div(answer, style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_PRIMARY, "lineHeight": "1.4"}),
            ],
        ),
        style={"cursor": "pointer", "padding": "14px 18px", "listStyle": "none", "outline": "none", "userSelect": "none"},
    )

    # Expandable body
    body_children: list[object] = []
    if insight_callout:
        body_children.append(insight_callout)
    if summary:
        body_children.append(html.Div(summary, style={"fontSize": "13px", "lineHeight": "1.6", "color": TEXT_SECONDARY, "marginBottom": "10px"}))
    if metrics_strip:
        body_children.append(metrics_strip)
    if basis_chips:
        body_children.append(basis_chips)
    if missing_note:
        body_children.append(missing_note)
    if chart:
        body_children.append(html.Div(chart, style={"marginTop": "12px"}))
    if extra_content:
        body_children.append(html.Div(extra_content, style={"marginTop": "12px"}))

    # Low-confidence visual treatment
    section_style = {**CARD_STYLE, "padding": "0", "marginBottom": "12px", "scrollMarginTop": "96px"}
    section_class = ""
    if confidence < 0.55:
        section_class = "section-low-confidence"

    return html.Details(
        [header, html.Div(body_children, style={"padding": "0 18px 18px"})],
        id=section_id,
        open=default_open,
        style=section_style,
        className=section_class,
    )


def _summary_anchor(label: str, href: str) -> html.A:
    return html.A(
        label,
        href=href,
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "padding": "8px 12px",
            "borderRadius": "999px",
            "border": f"1px solid {BORDER}",
            "backgroundColor": BG_SURFACE,
            "fontSize": "12px",
            "fontWeight": "600",
            "color": TEXT_PRIMARY,
            "textDecoration": "none",
        },
    )


def _view_mode_toggle(toggle_id: str, *, default_value: str = "chart") -> dcc.RadioItems:
    return dcc.RadioItems(
        id=toggle_id,
        options=[
            {"label": "Chart", "value": "chart"},
            {"label": "Table", "value": "table"},
        ],
        value=default_value,
        inline=True,
        labelStyle={"marginRight": "12px", "fontSize": "12px", "color": TEXT_SECONDARY},
        inputStyle={"marginRight": "4px"},
        style={"fontSize": "12px"},
    )


def _summary_list_block(title: str, items: list[str], *, tone: str = "neutral") -> html.Div:
    color = {
        "neutral": TEXT_SECONDARY,
        "positive": TONE_POSITIVE_TEXT,
        "warning": TONE_WARNING_TEXT,
        "negative": TONE_NEGATIVE_TEXT,
    }.get(tone, TEXT_SECONDARY)
    rows = items or ["No standout signals were surfaced yet."]
    return html.Div(
        [
            html.Div(title, style=SECTION_HEADER_STYLE),
            html.Ul(
                [
                    html.Li(
                        item,
                        style={"fontSize": "12px", "lineHeight": "1.55", "color": color},
                    )
                    for item in rows[:4]
                ],
                style={"margin": "6px 0 0 0", "paddingLeft": "16px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "14px 16px", "boxShadow": "none"},
    )


def render_property_decision_summary(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    show_jump_links: bool = True,
) -> html.Div:
    """Layer-1 decision summary — recommendation hero + quick reality strip only."""
    quick_vm = build_quick_decision_view(report)

    reality_strip = inline_metric_strip([
        ("Ask", _fmt_compact(view.ask_price), None),
        ("Fair Value", _fmt_compact(view.bcv), gap_pct_text(view) or None),
        ("12M Base", _fmt_compact(view.base_case), None),
        ("Monthly Reality", view.income_support.monthly_cash_flow_text, view.income_support.rent_source_label or None),
    ])

    return html.Div(
        [
            render_recommendation_hero(quick_vm),
            html.Div(
                [
                    reality_strip,
                    html.Div(
                        [
                            html.Button(
                                "Compare To Town / Market",
                                id="compare-to-market-button",
                                n_clicks=0,
                                style={
                                    "display": "inline-flex",
                                    "alignItems": "center",
                                    "padding": "8px 12px",
                                    "borderRadius": "999px",
                                    "border": f"1px solid {BORDER}",
                                    "backgroundColor": BG_SURFACE,
                                    "fontSize": "12px",
                                    "fontWeight": "600",
                                    "color": TEXT_PRIMARY,
                                    "cursor": "pointer",
                                },
                            ),
                        ],
                        style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginTop": "10px"},
                    ) if show_jump_links else None,
                ],
                style={**CARD_STYLE, "padding": "14px 18px", "boxShadow": "none"},
            ),
        ],
        style={"display": "grid", "gap": "12px", "marginBottom": "16px"},
    )


def _fit_label(view: PropertyAnalysisView) -> str:
    if view.lens_scores is None:
        if view.buyer_fit:
            return view.buyer_fit[0]
        return "Selective fit"
    key = view.lens_scores.recommended_lens
    mapping = {
        "owner": "Best suited for primary residence",
        "investor": "Most compelling as a rental investment",
        "developer": "Most compelling as a value-add / renovation strategy",
    }
    return mapping.get(key, "Selective fit across buyer types")


def _price_answer(view: PropertyAnalysisView) -> tuple[str, str, str]:
    pct = view.net_opportunity_delta_pct if view.net_opportunity_delta_pct is not None else view.mispricing_pct
    if pct is None:
        return (
            "Not enough data to call the price.",
            "",
            "Unresolved",
        )
    if pct >= 0.10:
        label = "Discount"
        answer = f"Priced {pct * 100:.0f}% below fair value — there's room built in."
    elif pct >= 0.04:
        label = "Modest Discount"
        answer = f"Priced {pct * 100:.0f}% below fair value — a modest discount."
    elif pct <= -0.10:
        label = "Premium"
        answer = f"Priced {abs(pct) * 100:.0f}% above fair value — this needs a reason."
    elif pct <= -0.04:
        label = "Slight Premium"
        answer = f"Priced {abs(pct) * 100:.0f}% above fair value — you're paying up."
    else:
        label = "In Line"
        answer = "Priced in line with fair value."
    if view.capex_basis_source == "inferred_lane":
        answer += " Capex basis is still inferred — treat the gap as provisional."
    return answer, view.value.pricing_view or "", label


def _economics_inputs(report: AnalysisReport, view: PropertyAnalysisView) -> dict[str, float | None]:
    module = report.module_results.get("income_support")
    payload = None if module is None else module.payload

    def _num(name: str) -> float | None:
        value = getattr(payload, name, None) if payload is not None else None
        return float(value) if isinstance(value, (int, float)) else None

    monthly_rent = _num("monthly_rent_estimate") or _num("gross_monthly_rent_before_vacancy")
    principal_interest = _num("monthly_principal_interest")
    taxes = _num("monthly_taxes")
    insurance = _num("monthly_insurance")
    maintenance = _num("monthly_maintenance_reserve")
    hoa = _num("monthly_hoa")
    expense_values = [value for value in [principal_interest, taxes, insurance, maintenance, hoa] if value is not None]
    gross_monthly_cost = sum(expense_values) if expense_values else None
    monthly_cash_flow = _parse_currency_text(view.income_support.monthly_cash_flow_text)
    net_monthly_cost = None
    if gross_monthly_cost is not None and monthly_rent is not None:
        net_monthly_cost = gross_monthly_cost - monthly_rent
    return {
        "monthly_rent": monthly_rent,
        "principal_interest": principal_interest,
        "taxes": taxes,
        "insurance": insurance,
        "maintenance": maintenance,
        "hoa": hoa,
        "gross_monthly_cost": gross_monthly_cost,
        "net_monthly_cost": net_monthly_cost,
        "monthly_cash_flow": monthly_cash_flow,
    }


def _economics_answer(view: PropertyAnalysisView, report: AnalysisReport) -> tuple[str, str]:
    metrics = _economics_inputs(report, view)
    cash_flow = metrics["monthly_cash_flow"]
    ptr_raw = view.compare_metrics.get("price_to_rent")
    rent_source = view.income_support.rent_source_type.lower()
    if cash_flow is not None and cash_flow >= 250:
        answer = f"The property carries itself — rent covers the hold with ~${cash_flow:,.0f}/mo cushion."
        summary = "Modeled income covers operating costs and leaves room. The hold is self-supporting under current assumptions."
    elif cash_flow is not None and cash_flow >= -250:
        answer = "Close to break-even — the carry is manageable but not comfortable."
        summary = "Rent nearly offsets the monthly nut. A modest rent increase or basis reduction would tip this positive."
    elif cash_flow is not None:
        answer = f"The carry is real — plan on ~${abs(cash_flow):,.0f}/mo out of pocket."
        summary = "Current rent support doesn't cover the monthly obligation. This is a capital play, not a cash-flow one."
    elif isinstance(ptr_raw, (int, float)) and ptr_raw <= 15:
        answer = "The price-to-rent ratio looks reasonable, but the full carry picture is still incomplete."
        summary = "Directionally the economics aren't extreme, but a complete hold view needs financing and expense inputs."
    else:
        answer = "Can't fully price the carry yet — key inputs are still missing."
        summary = "Not enough data to model the monthly cost of ownership. Rent, financing, and expense assumptions still need to be filled in."
    summary = f"{summary} This section uses financing, tax, insurance, and rent support to estimate what ownership costs month to month."
    if "estimated" in rent_source or "missing" in rent_source:
        summary += " Rent support is still estimated — treat the carry view as provisional."
    return answer, summary


def _forward_answer(view: PropertyAnalysisView) -> tuple[str, str]:
    if view.ask_price and view.base_case:
        base_gap = (view.base_case - view.ask_price) / view.ask_price
    else:
        base_gap = None
    if view.ask_price and view.bear_case:
        downside = (view.bear_case - view.ask_price) / view.ask_price
    else:
        downside = None
    if view.ask_price and view.bull_case:
        upside = (view.bull_case - view.ask_price) / view.ask_price
    else:
        upside = None
    if upside is not None and downside is not None and upside > abs(downside) * 1.5:
        ratio = upside / abs(downside) if abs(downside) > 0 else 0
        answer = f"The upside outweighs the downside by more than {ratio:.0f}:1 — forward skew is favorable."
    elif base_gap is not None and base_gap <= 0:
        answer = "The base case is flat or down from here — upside depends on the property improving or the market helping."
    elif upside is not None and downside is not None:
        answer = "The forward range is balanced — upside exists but the cone is wide enough to require discipline."
    else:
        answer = "The forward picture is partially visible, but the scenario range is thinner than ideal."
    summary = view.forward.summary or "Upside, base, and downside scenarios show how value could move from today's anchor."
    return answer, summary


def _risk_answer(view: PropertyAnalysisView) -> tuple[str, list[str]]:
    risk_bits = []
    if "thin" in view.risk_location.liquidity_label.lower() or "mixed" in view.risk_location.liquidity_label.lower():
        risk_bits.append("liquidity")
    if view.capex_lane.lower() in {"moderate", "heavy"}:
        risk_bits.append("capex certainty")
    if view.income_support.risk_view.lower() not in {"good", "supported"}:
        risk_bits.append("income support")
    primary_risk = _primary_risk_text(view)
    if not risk_bits and primary_risk and primary_risk != "No primary risk surfaced yet.":
        risk_bits.append(primary_risk.lower())
    top_risks = view.top_risks[:3] or ([primary_risk] if primary_risk and primary_risk != "No primary risk surfaced yet." else [])
    if len(risk_bits) == 1:
        answer = f"The thesis depends on {risk_bits[0]}. If that breaks, the hold gets harder to justify."
    elif risk_bits:
        answer = f"The thesis depends on {risk_bits[0]} and {risk_bits[1]}. If either breaks, the hold gets harder to justify."
    else:
        answer = "No single kill shot, but watch the margins — the risk profile is moderate, not absent."
    return answer, top_risks


def _optionality_answer(view: PropertyAnalysisView) -> tuple[str, str]:
    category = view.category_scores.get("optionality") if view.category_scores else None
    component_scores = getattr(category, "component_scores", {}) if category is not None else {}
    physical = component_scores.get("physical_optionality")
    strategic = component_scores.get("strategic_optionality")
    if physical is not None and physical >= 4.0:
        answer = "The property can physically become more than it is today — there's real upside not yet priced in."
    elif strategic is not None and strategic >= 4.0:
        answer = "Multiple strategies work here — the property offers execution flexibility even if physical upside is modest."
    elif category is not None and category.score <= 2.8:
        answer = "This is a narrow-path asset — limited room to pivot if the primary thesis doesn't hold."
    else:
        answer = "Some optionality exists, but it's selective rather than broad — one or two paths, not many."
    summary = "Optionality captures what the property can still become and how many realistic strategies remain open to you."
    return answer, summary


def _compact_verdict_strip(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Single compact strip replacing the 6-card decision grid + perspective block.

    Shows: score + tier, best lens, one-line conclusion, category mini-bars.
    Reduces above-fold from ~32 data points to ~8.
    """
    sc = score_color(view.final_score) if view.final_score else TEXT_MUTED
    sl = score_label(view.final_score) if view.final_score else "—"
    tier = (view.recommendation_tier or "Neutral").upper()
    vc = verdict_color(view.recommendation_tier or "")
    fit = _fit_label(view)
    conclusion = _decision_conclusion(view, report)

    # Lens badges
    ls = view.lens_scores
    lens_badges = []
    if ls:
        if ls.owner_score is not None:
            lens_badges.append(_compact_lens_badge("🏠 Owner", ls.owner_score))
        if ls.investor_score is not None:
            lens_badges.append(_compact_lens_badge("💰 Investor", ls.investor_score))
        if ls.developer_score is not None:
            lens_badges.append(_compact_lens_badge("🔧 Developer", ls.developer_score))
        lens_badges.append(_compact_lens_badge("🛡 Risk", ls.risk_score, inverted=True))

    # Category bars
    cat_bars = _render_v2_category_bars(view)

    return html.Div(
        [
            # Row 1: Score + Tier + Fit
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f"{view.final_score:.1f}" if view.final_score else "—", style={"fontSize": "28px", "fontWeight": "700", "color": sc}),
                            html.Span(" / 5", style={"fontSize": "14px", "color": TEXT_MUTED}),
                            html.Span(f"  {sl}", style={"fontSize": "14px", "fontWeight": "600", "color": sc, "marginLeft": "4px"}),
                        ],
                        style={"display": "flex", "alignItems": "baseline"},
                    ),
                    html.Div(
                        [
                            html.Span(tier, style={"fontSize": "14px", "fontWeight": "700", "color": vc, "marginRight": "10px"}),
                            html.Span(f"· {fit}", style={"fontSize": "13px", "color": TEXT_SECONDARY}),
                        ],
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "10px"},
            ),
            # Row 2: Conclusion narrative
            html.Div(conclusion, style={"fontSize": "13px", "lineHeight": "1.6", "color": TEXT_PRIMARY, "marginBottom": "12px"}),
            # Row 3: Lens badges
            html.Div(
                [b for b in lens_badges if b is not None],
                style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "12px"},
            ) if lens_badges else None,
            # Row 4: Category bars
            cat_bars,
        ],
        style={**CARD_STYLE, "border": f"2px solid {vc}40", "padding": "18px 20px", "marginBottom": "16px"},
    )


def get_smart_defaults(view: PropertyAnalysisView) -> list[str]:
    """Determine which sections to auto-expand based on property characteristics.

    Returns a list of section IDs that should start open.  The property's
    analysis results drive the defaults — no user role selection needed.
    """
    expanded: list[str] = []
    scores: dict[str, float] = {}

    # Check category scores for the weakest area
    if view.category_scores:
        mapping = {
            "price_context": "tear-price",
            "economic_support": "tear-economics",
            "risk_layer": "tear-risk",
        }
        for cat_key, section_id in mapping.items():
            cat = view.category_scores.get(cat_key)
            if cat:
                scores[section_id] = cat.score

    # Strong rental property → show income analysis
    cf_raw = _parse_currency_text(view.income_support.monthly_cash_flow_text)
    ptr_raw = view.compare_metrics.get("price_to_rent")
    if isinstance(cf_raw, (int, float)) and cf_raw > 0 and isinstance(ptr_raw, (int, float)) and ptr_raw < 15:
        expanded.append("tear-economics")

    # Large BCV gap → highlight pricing
    if view.mispricing_pct is not None and abs(view.mispricing_pct) > 0.10:
        expanded.append("tear-price")

    # High risk → surface warnings
    if view.risk_location.risk_score < 45:
        expanded.append("tear-risk")

    # Net opportunity delta is big → show optionality/value-add
    if view.net_opportunity_delta_pct is not None and abs(view.net_opportunity_delta_pct) > 0.15:
        expanded.append("tear-optionality")

    # If nothing triggered, open the weakest category
    if not expanded and scores:
        weakest = min(scores, key=scores.get)
        expanded.append(weakest)

    # Fallback: always show price
    if not expanded:
        expanded.append("tear-price")

    return list(dict.fromkeys(expanded))  # dedupe, preserve order


def _decision_conclusion(view: PropertyAnalysisView, report: AnalysisReport) -> str:
    price_answer, _, _ = _price_answer(view)
    economics_answer, _ = _economics_answer(view, report)
    forward_answer, _ = _forward_answer(view)
    risk_answer, _ = _risk_answer(view)
    fit = _fit_label(view)
    return (
        f"{fit}. {price_answer} {economics_answer} {forward_answer} "
        f"The main watch items are {risk_answer.replace('Risk is currently driven by ', '').replace('.', '')}."
    )


def _decision_engine_block(view: PropertyAnalysisView) -> html.Div:
    decision = view.decision
    if decision is None:
        return html.Div()

    tone = (
        "positive" if decision.recommendation in {"BUY", "LEAN BUY"} else
        "warning" if decision.recommendation in {"NEUTRAL", "LEAN PASS"} else
        "negative"
    )
    tone_color_map = {
        "positive": TONE_POSITIVE_TEXT,
        "warning": TONE_WARNING_TEXT,
        "negative": TONE_NEGATIVE_TEXT,
    }
    badge_color = tone_color_map[tone]
    assumption_summary, assumption_color, assumption_detail, assumption_chips = _assumption_quality_snapshot(view)

    supporting = decision.supporting_factors or _supporting_reasons(view)[:3]
    dependencies = decision.dependencies or _decision_dependencies(view)[:2]
    risks = decision.disqualifiers or decision.risks or view.top_risks[:2]

    def _bullet_block(title: str, items: list[str], color: str = TEXT_SECONDARY) -> html.Div | None:
        if not items:
            return None
        return html.Div(
            [
                html.Div(title, style=SECTION_HEADER_STYLE),
                html.Ul(
                    [html.Li(item, style={"fontSize": "12px", "lineHeight": "1.55", "color": color}) for item in items],
                    style={"margin": "4px 0 0 0", "paddingLeft": "16px"},
                ),
            ],
            style={**CARD_STYLE, "padding": "10px 12px"},
        )

    memo_metric_cards = [
        ("Conviction", f"{decision.conviction_score}/100", TEXT_PRIMARY),
        ("Confidence", decision.confidence_level, badge_color),
        ("Trust", assumption_summary, assumption_color),
    ]

    return html.Div(
        [
            html.Div("DECISION MEMO", style={**SECTION_HEADER_STYLE, "fontSize": "12px", "letterSpacing": "0.12em", "marginBottom": "12px"}),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(decision.recommendation, style={"fontSize": "32px", "fontWeight": "800", "letterSpacing": "-0.03em", "color": badge_color}),
                                    html.Span(f" · {decision.best_fit}", style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_SECONDARY, "marginLeft": "8px"}),
                                ],
                                style={"display": "flex", "alignItems": "baseline", "flexWrap": "wrap"},
                            ),
                            html.Div(
                                "Top-line call anchored to Briarwood's current score, risk, and trust read.",
                                style={"fontSize": "12px", "lineHeight": "1.45", "color": TEXT_MUTED, "marginTop": "6px"},
                            ),
                        ],
                        style={"display": "flex", "flexDirection": "column", "gap": "0"},
                    ),
                    html.Div(
                        [
                            html.Span(decision.confidence_level.upper(), style=tone_badge_style(tone)),
                        ],
                        style={"display": "flex", "flexDirection": "column", "alignItems": "flex-end", "justifyContent": "flex-start"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "marginBottom": "12px", "gap": "16px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(label, style={**LABEL_STYLE, "marginBottom": "4px"}),
                            html.Div(value, style={"fontSize": "15px", "fontWeight": "700", "lineHeight": "1.2", "color": color}),
                        ],
                        style={
                            **CARD_STYLE,
                            "padding": "10px 12px",
                            "backgroundColor": BG_SURFACE_2,
                            "border": f"1px solid {BORDER}",
                        },
                    )
                    for label, value, color in memo_metric_cards
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "10px", "marginBottom": "12px"},
            ),
            html.Div(decision.thesis, style={"fontSize": "15px", "lineHeight": "1.58", "color": TEXT_PRIMARY, "marginBottom": "8px", "maxWidth": "88ch"}),
            html.Div(
                decision.fit_context,
                style={"fontSize": "13px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ) if decision.fit_context else None,
            html.Div(
                assumption_detail,
                style={"fontSize": "12px", "lineHeight": "1.45", "color": TEXT_MUTED, "marginBottom": "10px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Why This Works", style={**LABEL_STYLE, "marginBottom": "4px"}),
                            html.Div(decision.decisive_driver, style={"fontSize": "13px", "lineHeight": "1.55", "color": TEXT_PRIMARY}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px"},
                    ),
                    html.Div(
                        [
                            html.Div("What Breaks It", style={**LABEL_STYLE, "marginBottom": "4px"}),
                            html.Div(decision.break_condition, style={"fontSize": "13px", "lineHeight": "1.55", "color": TONE_WARNING_TEXT}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px"},
                    ),
                    html.Div(
                        [
                            html.Div("What Must Be True", style={**LABEL_STYLE, "marginBottom": "4px"}),
                            html.Div(decision.required_belief, style={"fontSize": "13px", "lineHeight": "1.55", "color": TEXT_SECONDARY}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px"},
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "10px", "marginBottom": "12px"},
            ),
            inline_metric_strip(_header_pricing_snapshot(view)),
            html.Div(
                assumption_chips,
                style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginTop": "10px", "marginBottom": "2px"},
            ) if assumption_chips else None,
            html.Div(
                [block for block in [
                    _bullet_block("Supporting Factors", supporting),
                    _bullet_block("Risks", risks, TONE_WARNING_TEXT if tone != "negative" else TONE_NEGATIVE_TEXT),
                    _bullet_block("Dependencies", dependencies),
                ] if block is not None],
                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "10px", "marginTop": "12px"},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "18px 20px", "marginBottom": "16px", "border": f"1px solid {badge_color}55"},
    )


# ── Archived 2026-04-08 ────────────────────────────────────────────────────
# `_decision_summary_block` rendered a 6-card grid (Price, Hold Economics,
# Forward, Risk, Optionality, Fit) that duplicated the main tab navigation,
# plus a conclusion paragraph at the bottom. The card grid was retired from
# the Overview tab; the conclusion copy is now extracted via
# `_decision_conclusion(...)` and rendered as a ribbon at the top of Overview.
# Function body is preserved in case the grid is useful in a future layout.
# ───────────────────────────────────────────────────────────────────────────
def _decision_summary_block(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    price_answer, _, price_label = _price_answer(view)
    economics_answer, economics_summary = _economics_answer(view, report)
    forward_answer, forward_summary = _forward_answer(view)
    risk_answer, top_risks = _risk_answer(view)
    optionality_answer, optionality_summary = _optionality_answer(view)
    fit_answer = _fit_label(view)
    cards = []
    normalized_rows = [
        ("Price", price_answer, f"Signal: {price_label}. BCV and net opportunity delta are the main anchors here.", "tear-price"),
        ("Hold Economics", economics_answer, economics_summary, "tear-economics"),
        ("Forward Outlook", forward_answer, forward_summary, "tear-forward"),
        ("Risk", risk_answer, "Main watch items: " + ", ".join(top_risks[:2]) if top_risks else "Risk combines valuation, carry, liquidity, and execution burden.", "tear-risk"),
        ("Optionality", optionality_answer, optionality_summary, "tear-optionality"),
        ("Fit", fit_answer, "This comes from Briarwood's live investment lenses: owner, investor, developer, and risk.", "tear-evidence"),
    ]
    for label, answer, detail, section_id in normalized_rows:
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(label, style={**LABEL_STYLE, "marginBottom": "0"}),
                            html.A(
                                "View details",
                                href=f"#{section_id}",
                                style={"fontSize": "11px", "fontWeight": "600", "color": ACCENT_BLUE, "textDecoration": "none"},
                            ) if section_id else None,
                        ],
                        style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "8px"},
                    ),
                    html.Div(answer, style={"fontSize": "13px", "lineHeight": "1.55", "color": TEXT_PRIMARY}),
                ],
                style={**CARD_STYLE, "padding": "12px 14px"},
            )
        )
    return html.Div(
        [
            html.Div("DECISION SUMMARY", style={**SECTION_HEADER_STYLE, "fontSize": "12px", "letterSpacing": "0.12em", "marginBottom": "12px"}),
            html.Div(cards, style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px", "marginBottom": "12px"}),
            html.Div(
                _decision_conclusion(view, report),
                style={
                    "fontSize": "14px",
                    "lineHeight": "1.65",
                    "color": TEXT_PRIMARY,
                    "padding": "12px 14px",
                    "backgroundColor": BG_SURFACE_2,
                    "borderLeft": f"3px solid {ACCENT_BLUE}",
                    "borderRadius": "0 4px 4px 0",
                },
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "18px 20px", "marginBottom": "16px"},
    )


def _property_header_identity(report: AnalysisReport) -> tuple[str, str]:
    address = getattr(report, "address", "") or ""
    parts = [part.strip() for part in str(address).split(",") if part.strip()]
    street = parts[0] if parts else "Unknown Address"
    property_input = getattr(report, "property_input", None)
    town = getattr(property_input, "town", None)
    state = getattr(property_input, "state", None)
    locality = ", ".join(part for part in [town, state] if part) or ", ".join(parts[1:3]).strip() or "Unknown Location"
    return locality, street


def _property_header_basics(report: AnalysisReport) -> str:
    property_input = getattr(report, "property_input", None)
    if property_input is None:
        return ""
    items: list[str] = []
    beds = getattr(property_input, "beds", None)
    baths = getattr(property_input, "baths", None)
    sqft = getattr(property_input, "sqft", None)
    property_type = getattr(property_input, "property_type", None)
    if beds:
        items.append(f"{beds} bd")
    if baths:
        items.append(f"{baths:g} ba" if isinstance(baths, (int, float)) else f"{baths} ba")
    if sqft:
        items.append(f"{int(sqft):,} sf")
    if property_type:
        items.append(str(property_type).replace("_", " ").title())
    return " · ".join(items)


def _subject_location_block(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div | None:
    property_input = getattr(report, "property_input", None)
    if property_input is None:
        return None

    lat = getattr(property_input, "latitude", None)
    lon = getattr(property_input, "longitude", None)
    location_module = report.module_results.get("location_intelligence")
    payload = getattr(location_module, "payload", None) if location_module is not None else None
    category_results = getattr(payload, "category_results", None) or []

    if lat is None and lon is None and not category_results:
        return None

    address_parts = [
        getattr(property_input, "address", None),
        getattr(property_input, "town", None),
        getattr(property_input, "state", None),
    ]
    maps_query = ", ".join(str(part).strip() for part in address_parts if part)
    maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(maps_query)}" if maps_query else None

    status = "Geocoded" if view.geocoded else "Coordinates Attached" if lat is not None and lon is not None else "Address Only"
    tone = "positive" if view.geocoded or (lat is not None and lon is not None) else "warning"
    anchor_summary = " • ".join(
        f"{str(getattr(item, 'category', '')).replace('_', ' ').title()} {float(getattr(item, 'subject_distance_miles')):.2f} mi"
        for item in category_results[:3]
        if getattr(item, "category", None) and getattr(item, "subject_distance_miles", None) is not None
    )

    chips = [
        compact_badge("Status", status, tone=tone),
        compact_badge("Location Support", view.risk_location.location_support_label, tone="positive" if view.risk_location.location_support_label == "Geo-Benchmarked" else "warning" if "Missing" in view.risk_location.location_support_label else "neutral"),
    ]
    if lat is not None and lon is not None:
        chips.append(compact_badge("Lat / Lon", f"{float(lat):.5f}, {float(lon):.5f}", tone="neutral"))

    links: list[object] = []
    if maps_url:
        links.append(html.A("Open in Google Maps", href=maps_url, target="_blank", rel="noreferrer", style={"fontSize": "12px", "fontWeight": "600", "color": ACCENT_BLUE, "textDecoration": "none"}))

    return html.Div(
        [
            html.Div("Subject Location", style={**SECTION_HEADER_STYLE, "fontSize": "10px", "marginBottom": "4px"}),
            html.Div(chips, style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "alignItems": "center"}),
            html.Div(view.risk_location.location_support_detail, style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_MUTED}) if view.risk_location.location_support_detail else None,
            html.Div(f"Nearest anchors: {anchor_summary}", style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_SECONDARY}) if anchor_summary else None,
            html.Div(links, style={"display": "flex", "gap": "10px", "alignItems": "center"}) if links else None,
        ],
        style={**CARD_STYLE, "padding": "12px 14px", "marginTop": "12px", "boxShadow": "none", "borderColor": BORDER_SUBTLE},
    )


def _premium_property_header(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    locality, street = _property_header_identity(report)
    basics = _property_header_basics(report)
    pricing_panel = html.Div(
        [
            html.Div("Asking Price", style={**LABEL_STYLE, "color": ACCENT_BLUE, "marginBottom": "6px"}),
            html.Div(_fmt_compact(view.ask_price), style={"fontSize": "34px", "fontWeight": "800", "lineHeight": "1.0", "color": ACCENT_NAVY}),
            html.Div(
                "Current listing basis",
                style={"fontSize": "12px", "color": TEXT_MUTED, "marginTop": "4px"},
            ),
            html.Div(
                inline_metric_strip([
                    ("Fair Value", _fmt_compact(view.bcv), gap_pct_text(view) if view.mispricing_pct is not None else None),
                    ("12M Base", _fmt_compact(view.base_case), None),
                ]),
                style={"marginTop": "10px"},
            ),
        ],
        style={
            **CARD_STYLE,
            "padding": "18px 18px",
            "backgroundColor": BG_SURFACE_3,
            "border": f"1px solid {BG_SURFACE_4}",
            "boxShadow": "none",
        },
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(locality, style={**SECTION_HEADER_STYLE, "fontSize": "12px", "marginBottom": "6px", "color": ACCENT_BLUE}),
                    html.Div(street, style={"fontSize": "34px", "fontWeight": "800", "letterSpacing": "-0.03em", "lineHeight": "1.05", "color": ACCENT_NAVY}),
                    html.Div(
                        "High-conviction investment read anchored in current value, path to upside, town backdrop, and evidence quality.",
                        style={"fontSize": "14px", "lineHeight": "1.6", "color": TEXT_SECONDARY, "marginTop": "8px", "maxWidth": "72ch"},
                    ),
                    html.Div(basics, style={"fontSize": "13px", "color": TEXT_MUTED, "marginTop": "8px"}) if basics else None,
                    _subject_location_block(view, report),
                ],
                style={"display": "grid", "gap": "0"},
            ),
            pricing_panel,
        ],
        style={
            **CARD_STYLE_ELEVATED,
            "padding": "22px 24px",
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(280px, 1fr))",
            "gap": "18px",
            "alignItems": "start",
            "background": f"linear-gradient(180deg, rgba(59,130,246,0.08) 0%, {BG_SECONDARY} 42%)",
            "border": f"1px solid {BG_SURFACE_4}",
        },
    )


def _premium_decision_strip(view: PropertyAnalysisView) -> html.Div:
    decision = view.decision
    recommendation = decision.recommendation if decision is not None else (view.recommendation_tier or "—")
    confidence = decision.confidence_level if decision is not None else view.confidence_level
    fit = decision.best_fit if decision is not None else _fit_label(view)
    confidence_tone = (
        "positive" if confidence == "High" else
        "warning" if confidence == "Medium" else
        "negative"
    )
    summary_line = decision.decisive_driver if decision is not None and decision.decisive_driver else (decision.thesis if decision is not None else "Briarwood's current underwriting view.")
    lead_card = html.Div(
        [
            html.Div("Decision Read", style={**LABEL_STYLE, "color": "rgba(255,255,255,0.78)"}),
            html.Div(recommendation, style={"fontSize": "34px", "fontWeight": "800", "lineHeight": "1.0", "color": TEXT_PRIMARY}),
            html.Div(summary_line, style={"fontSize": "14px", "lineHeight": "1.55", "color": "rgba(255,255,255,0.82)", "marginTop": "10px", "maxWidth": "58ch"}),
        ],
        style={
            "padding": "18px 20px",
            "borderRadius": "18px",
            "background": f"linear-gradient(135deg, {ACCENT_NAVY} 0%, {ACCENT_BLUE} 100%)",
            "boxShadow": "0 18px 34px rgba(2, 62, 138, 0.24)",
            "gridColumn": "span 2",
        },
    )
    return html.Div(
        [
            lead_card,
            html.Div(
                [
                    html.Div("Score", style=LABEL_STYLE),
                    html.Div(f"{view.final_score:.1f}/5" if view.final_score is not None else "—", style={"fontSize": "30px", "fontWeight": "800", "lineHeight": "1.05", "color": score_color(view.final_score)}),
                ],
                style={**CARD_STYLE, "padding": "18px 18px", "boxShadow": "none", "borderColor": BORDER_SUBTLE, "minHeight": "118px"},
            ),
            html.Div(
                [
                    html.Div("Confidence", style=LABEL_STYLE),
                    html.Div(
                        [
                            html.Span(confidence, style={"fontSize": "20px", "fontWeight": "700", "color": _confidence_level_color(confidence)}),
                            html.Span(confidence.upper(), style=tone_badge_style(confidence_tone)),
                        ],
                        style={"display": "flex", "gap": "8px", "alignItems": "center", "flexWrap": "wrap"},
                    ),
                ],
                style={**CARD_STYLE, "padding": "18px 18px", "boxShadow": "none", "borderColor": BORDER_SUBTLE, "minHeight": "118px"},
            ),
            html.Div(
                [
                    html.Div("Best Fit", style=LABEL_STYLE),
                    html.Div(fit, style={"fontSize": "18px", "fontWeight": "700", "lineHeight": "1.25", "color": TEXT_PRIMARY}),
                ],
                style={**CARD_STYLE, "padding": "18px 18px", "boxShadow": "none", "borderColor": BORDER_SUBTLE, "minHeight": "118px"},
            ),
        ],
        style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "12px"},
    )


def _key_metric_context_lines(view: PropertyAnalysisView, report: AnalysisReport) -> list[tuple[str, str, str]]:
    metrics = _economics_inputs(report, view)
    monthly_cash_flow = metrics.get("monthly_cash_flow")
    rent = metrics.get("monthly_rent")
    gross_cost = metrics.get("gross_monthly_cost")
    rent_coverage = None
    if isinstance(rent, (int, float)) and isinstance(gross_cost, (int, float)) and gross_cost > 0:
        rent_coverage = rent / gross_cost

    net_monthly_cost_value = _fmt_value(metrics.get("net_monthly_cost")) or view.income_support.monthly_cash_flow_text
    net_monthly_cost_context = _benchmark_sublabel(monthly_cash_flow, "cash_flow") if isinstance(monthly_cash_flow, (int, float)) else None
    if rent_coverage is not None:
        coverage_text = f"rent covers {rent_coverage:.0%} of carrying cost"
        net_monthly_cost_context = f"{net_monthly_cost_context} • {coverage_text}" if net_monthly_cost_context else coverage_text

    ptr_raw = view.compare_metrics.get("price_to_rent")
    ptr_context = _benchmark_sublabel(float(ptr_raw), "ptr") if isinstance(ptr_raw, (int, float)) else view.income_support.ptr_classification
    town_ppsf = view.compare_metrics.get("town_baseline_median_ppsf")
    if town_ppsf is not None:
        ptr_context = f"{ptr_context or ''} • town median PPSF {_fmt_compact(town_ppsf)}".strip(" •")

    capex_context_parts = [view.condition_profile]
    capex_source = _capex_basis_source_label(view.capex_basis_source)
    if capex_source:
        capex_context_parts.append(capex_source)
    if view.compare_metrics.get("town_baseline_median_price") is not None:
        capex_context_parts.append(f"town prior {_fmt_compact(view.compare_metrics.get('town_baseline_median_price'))}")

    liquidity_context = _benchmark_sublabel(view.risk_location.liquidity_score, "liquidity") or view.risk_location.liquidity_label
    town_dom = view.town_context.get("town_dom_median") if isinstance(view.town_context, dict) else None
    if town_dom is not None:
        liquidity_context = f"{liquidity_context or ''} • town DOM {float(town_dom):.0f}".strip(" •")

    optionality_context_parts: list[str] = []
    town_opportunity = view.town_context.get("town_relative_opportunity_score") if isinstance(view.town_context, dict) else None
    if town_opportunity is not None:
        optionality_context_parts.append(f"town opportunity {float(town_opportunity):.2f}/5")
    if view.decision is not None and view.decision.best_fit:
        optionality_context_parts.append(view.decision.best_fit)

    return [
        ("Net Monthly Cost", net_monthly_cost_value, net_monthly_cost_context or "context unavailable"),
        ("Price-to-Rent", view.income_support.price_to_rent_text, ptr_context or "context unavailable"),
        ("CapEx Load", view.capex_lane, " • ".join(part for part in capex_context_parts if part) or "context unavailable"),
        ("Liquidity", f"{view.risk_location.liquidity_score:.0f}/100", liquidity_context or "context unavailable"),
        ("Optionality", view.optionality_label, " • ".join(optionality_context_parts) or "context unavailable"),
    ]


def _premium_key_metrics_row(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    key_cards = _key_metric_context_lines(view, report)
    return html.Div(
        [
            html.Div("Key Metrics", style=SECTION_HEADER_STYLE),
            html.Div(
                "Each metric includes its comparison context so the number is not floating on its own.",
                style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginBottom": "2px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(label, style=LABEL_STYLE),
                            html.Div(value, style={"fontSize": "20px", "fontWeight": "800", "lineHeight": "1.1", "color": TEXT_PRIMARY}),
                            html.Div("Context", style={**LABEL_STYLE, "fontSize": "10px", "marginTop": "10px", "marginBottom": "3px"}),
                            html.Div(subtitle, style={"fontSize": "11px", "lineHeight": "1.45", "color": TEXT_SECONDARY}),
                        ],
                        style={**CARD_STYLE, "padding": "16px 16px", "boxShadow": "none", "borderColor": BORDER_SUBTLE},
                    )
                    for label, value, subtitle in key_cards
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(170px, 1fr))", "gap": "10px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "18px 20px", "boxShadow": "none"},
    )


def _premium_scenario_workspace(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    town_pulse_filter: str = "all",
) -> html.Div:
    return html.Div(
        [
            html.Div("Scenario View", style=SECTION_HEADER_STYLE),
            html.Div(
                "Use this section to move from current value to strategic path, then to forward value and break-even timing. The goal is to see whether the deal works today, through execution, and over time.",
                style={"fontSize": "13px", "lineHeight": "1.6", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ),
            _property_analysis_top_stack(view, report, include_market_position=False),
            _premium_town_pulse_section(view, report, town_pulse_filter=town_pulse_filter),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "20px 22px", "display": "grid", "gap": "14px"},
    )


def _premium_risk_constraints_section(
    view: PropertyAnalysisView,
    risk_section: html.Div,
    optionality_section: html.Div,
) -> html.Div:
    decision = view.decision
    required_belief = decision.required_belief if decision is not None else "The current assumptions need to hold close to the base case."
    break_condition = decision.break_condition if decision is not None else (view.top_risks[0] if view.top_risks else "No primary break condition available.")
    dependencies = (decision.dependencies if decision is not None and decision.dependencies else _decision_dependencies(view)[:3]) or []
    return html.Div(
        [
            html.Div("Risk & Constraints", style=SECTION_HEADER_STYLE),
            html.Div(
                "This is the fast read on what can break the thesis, what still has to be believed, and which constraints deserve attention before acting.",
                style={"fontSize": "13px", "lineHeight": "1.6", "color": TEXT_SECONDARY},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Key Risk", style=LABEL_STYLE),
                            html.Div(break_condition, style={"fontSize": "14px", "fontWeight": "700", "lineHeight": "1.45", "color": TONE_WARNING_TEXT}),
                        ],
                        style={**CARD_STYLE, "padding": "14px 16px"},
                    ),
                    html.Div(
                        [
                            html.Div("Required Belief", style=LABEL_STYLE),
                            html.Div(required_belief, style={"fontSize": "14px", "fontWeight": "700", "lineHeight": "1.45", "color": TEXT_PRIMARY}),
                        ],
                        style={**CARD_STYLE, "padding": "14px 16px"},
                    ),
                    html.Div(
                        [
                            html.Div("Dependencies", style=LABEL_STYLE),
                            html.Ul(
                                [html.Li(item, style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_SECONDARY}) for item in dependencies[:3]],
                                style={"margin": "0", "paddingLeft": "16px"},
                            ) if dependencies else html.Div("No explicit dependency list available.", style={"fontSize": "12px", "color": TEXT_MUTED}),
                        ],
                        style={**CARD_STYLE, "padding": "14px 16px"},
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(240px, 1fr))", "gap": "10px"},
            ),
            html.Div(
                [
                    risk_section,
                    optionality_section,
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(280px, 1fr))", "gap": "12px", "alignItems": "start"},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "20px 22px", "display": "grid", "gap": "14px"},
    )


def _premium_town_pulse_section(view: PropertyAnalysisView, report: AnalysisReport, *, town_pulse_filter: str = "all") -> html.Div:
    metrics = inline_metric_strip([
        ("Town", f"{view.risk_location.town_score:.0f}", _benchmark_sublabel(view.risk_location.town_score, "town_score") or view.risk_location.town_label.replace("_", " ").title()),
        ("Momentum", f"{view.risk_location.market_momentum_score:.0f}/100", _benchmark_sublabel(view.risk_location.market_momentum_score, "momentum") or view.risk_location.market_momentum_label),
        ("Scarcity", f"{view.risk_location.scarcity_score:.0f}", _benchmark_sublabel(view.risk_location.scarcity_score, "scarcity")),
        ("Liquidity", f"{view.risk_location.liquidity_score:.0f}/100", _benchmark_sublabel(view.risk_location.liquidity_score, "liquidity") or view.risk_location.liquidity_label),
    ])
    pulse_block = _town_pulse_block(view, signal_filter=town_pulse_filter)
    content: list[object] = [
        html.Div("Section D - Town Pulse", style=SECTION_HEADER_STYLE),
        html.Div(
            "This is the local intelligence layer: what may be changing in the town before comps and listing data fully catch up.",
            style={"fontSize": "13px", "lineHeight": "1.6", "color": TEXT_SECONDARY},
        ),
        metrics,
    ]
    if pulse_block is not None:
        content.append(pulse_block)
    else:
        content.append(
            html.Div(
                "No local intelligence is currently available for this town.",
                style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_MUTED},
            )
        )
    return html.Div(
        content,
        style={
            **CARD_STYLE_ELEVATED,
            "padding": "20px 22px",
            "display": "grid",
            "gap": "12px",
            "background": f"linear-gradient(180deg, rgba(59,130,246,0.08) 0%, {BG_SECONDARY} 40%)",
            "border": f"1px solid {BG_SURFACE_4}",
        },
    )


def _premium_risk_bar(view: PropertyAnalysisView) -> html.Div:
    """Compact risk bar — key risk, required belief, and top dependencies."""
    decision = view.decision
    break_condition = decision.break_condition if decision is not None else (view.top_risks[0] if view.top_risks else "No primary break condition identified.")
    required_belief = decision.required_belief if decision is not None else "Current assumptions need to hold close to the base case."
    dependencies = (decision.dependencies if decision is not None and decision.dependencies else _decision_dependencies(view)[:3]) or []

    dep_el = (
        html.Ul(
            [html.Li(item, style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_SECONDARY}) for item in dependencies[:3]],
            style={"margin": "0", "paddingLeft": "16px"},
        ) if dependencies else html.Div("No explicit dependencies.", style={"fontSize": "12px", "color": TEXT_MUTED})
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Key Risk", style=LABEL_STYLE),
                            html.Div(break_condition, style={"fontSize": "14px", "fontWeight": "700", "lineHeight": "1.45", "color": TONE_WARNING_TEXT}),
                        ],
                        style={**CARD_STYLE, "padding": "14px 16px"},
                    ),
                    html.Div(
                        [
                            html.Div("Required Belief", style=LABEL_STYLE),
                            html.Div(required_belief, style={"fontSize": "14px", "fontWeight": "700", "lineHeight": "1.45", "color": TEXT_PRIMARY}),
                        ],
                        style={**CARD_STYLE, "padding": "14px 16px"},
                    ),
                    html.Div(
                        [
                            html.Div("Dependencies", style=LABEL_STYLE),
                            dep_el,
                        ],
                        style={**CARD_STYLE, "padding": "14px 16px"},
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(240px, 1fr))", "gap": "10px"},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "16px 18px", "display": "grid", "gap": "10px"},
    )


def _premium_supporting_details(children: list[object]) -> html.Details:
    visible_children = [child for child in children if child is not None]
    return html.Details(
        [
            html.Summary(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("See More", style=SECTION_HEADER_STYLE),
                                html.Div(
                                    "Scenarios, pricing detail, evidence, and full section analysis.",
                                    style={"fontSize": "13px", "lineHeight": "1.5", "color": TEXT_SECONDARY},
                                ),
                            ],
                            style={"display": "grid", "gap": "4px"},
                        ),
                        html.Span("Drill Down", style=tone_badge_style("neutral")),
                    ],
                    style={"display": "flex", "justifyContent": "space-between", "gap": "12px", "alignItems": "center"},
                ),
                style={"cursor": "pointer", "listStyle": "none", "padding": "16px 18px"},
            ),
            html.Div(visible_children, style={"display": "grid", "gap": "12px", "padding": "0 18px 18px"}),
        ],
        style={
            **CARD_STYLE,
            "padding": "0",
            "backgroundColor": BG_SURFACE_2,
            "borderStyle": "dashed",
            "boxShadow": "none",
            "opacity": "0.94",
        },
    )


def _premium_owner_page(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    town_pulse_filter: str = "all",
    risk_section: html.Div,
    optionality_section: html.Div,
    evidence_section: html.Div,
    report_card_block: html.Div | None,
    price_section: html.Div,
    economics_section: html.Div,
    forward_section: html.Div,
    market_section: html.Div,
) -> html.Div:
    # Core visible elements: decision (in summary_layer above), risk bar, value finder
    risk_bar = _premium_risk_bar(view)
    value_finder = _value_finder_block(view)

    core_children: list[object] = [
        _premium_property_header(view, report),
        risk_bar,
    ]
    if value_finder is not None:
        core_children.append(value_finder)

    # Everything else lives behind a single "See More" drill-down
    core_children.append(
        _premium_supporting_details(
            [
                _premium_scenario_workspace(view, report, town_pulse_filter=town_pulse_filter),
                price_section,
                economics_section,
                forward_section,
                risk_section,
                optionality_section,
                market_section,
                evidence_section,
                report_card_block,
            ]
        ),
    )

    return html.Div(
        core_children,
        style={"display": "grid", "gap": "14px"},
    )


def _list_block(title: str, items: list[str], *, tone: str = "neutral") -> html.Div | None:
    filtered = [item for item in items if item]
    if not filtered:
        return None
    color = {
        "neutral": TEXT_SECONDARY,
        "warning": TONE_WARNING_TEXT,
        "negative": TONE_NEGATIVE_TEXT,
        "positive": TONE_POSITIVE_TEXT,
    }.get(tone, TEXT_SECONDARY)
    return html.Div(
        [
            html.Div(title, style=SECTION_HEADER_STYLE),
            html.Ul(
                [html.Li(item, style={"fontSize": "12px", "lineHeight": "1.55", "color": color}) for item in filtered],
                style={"margin": "4px 0 0 0", "paddingLeft": "16px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def _soft_recommendation_label(recommendation: str) -> str:
    mapping = {
        "BUY": "Well Positioned",
        "LEAN BUY": "Constructive, Price Sensitive",
        "NEUTRAL": "Needs More Signal",
        "LEAN PASS": "Needs Better Basis",
        "AVOID": "Does Not Meet Criteria",
    }
    return mapping.get(recommendation, recommendation)


def _reframe_risk_for_realtor(text: str) -> str:
    if not text:
        return text
    replacements = [
        ("Liquidity risk is elevated", "Resale may take longer than more liquid inventory"),
        ("High capex uncertainty", "Renovation scope should be confirmed early"),
        ("Weak liquidity", "Resale may be slower than more standard inventory"),
        ("Rent confidence is low", "Income assumptions should be validated before leaning on them"),
        ("carry is heavy", "the economics work best with additional support or a more flexible use case"),
        ("Carry is heavy", "The economics work best with additional support or a more flexible use case"),
        ("Risk is currently driven by ", ""),
        ("capex certainty", "capex scope that still needs confirmation"),
        ("income support", "income support that still needs validation"),
    ]
    rewritten = text
    for old, new in replacements:
        rewritten = rewritten.replace(old, new)
    return rewritten


def _realtor_talking_points(view: PropertyAnalysisView, report: AnalysisReport) -> list[str]:
    price_answer, _, _ = _price_answer(view)
    forward_answer, _ = _forward_answer(view)
    optionality_answer, _ = _optionality_answer(view)
    points: list[str] = []
    for item in [price_answer, forward_answer, optionality_answer]:
        if item and "limited" not in item.lower() and item not in points:
            points.append(item)
    for reason in _supporting_reasons(view):
        if reason not in points:
            points.append(reason)
        if len(points) >= 3:
            break
    for driver in (view.risk_location.drivers or []):
        if driver not in points:
            points.append(driver)
        if len(points) >= 3:
            break
    return points[:3]


def _realtor_watchouts(view: PropertyAnalysisView) -> list[str]:
    items: list[str] = []
    for risk in (view.top_risks or [])[:2]:
        items.append(_reframe_risk_for_realtor(risk))
    for dep in _decision_dependencies(view)[:2]:
        reframed = dep.replace("Confirm ", "Confirming ").replace("confirm ", "confirming ")
        if reframed not in items:
            items.append(reframed)
        if len(items) >= 2:
            break
    return items[:2]


def _realtor_positioning_header(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    decision = view.decision
    if decision is None:
        return html.Div()
    talking_points = _realtor_talking_points(view, report)
    watchouts = _realtor_watchouts(view)
    assumption_summary, assumption_color, assumption_detail, assumption_chips = _assumption_quality_snapshot(view)
    positioning_cards = [
        ("Best for", decision.best_fit, TEXT_PRIMARY),
        ("Positioning", _soft_recommendation_label(decision.recommendation), TEXT_PRIMARY),
        ("Trust", assumption_summary, assumption_color),
    ]
    return html.Div(
        [
            html.Div("POSITIONING HEADER", style={**SECTION_HEADER_STYLE, "fontSize": "12px", "letterSpacing": "0.12em", "marginBottom": "12px"}),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(decision.best_fit, style={"fontSize": "28px", "fontWeight": "800", "letterSpacing": "-0.03em", "color": TEXT_PRIMARY}),
                            html.Span(f" · {_soft_recommendation_label(decision.recommendation)}", style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_SECONDARY, "marginLeft": "8px"}),
                        ],
                        style={"display": "flex", "alignItems": "baseline", "flexWrap": "wrap"},
                    ),
                    html.Div(
                        "Buyer-fit framing backed by the same underwriting and trust signals as Owner View.",
                        style={"fontSize": "12px", "lineHeight": "1.45", "color": TEXT_MUTED, "marginTop": "6px"},
                    ),
                    html.Div(
                        [
                            html.Span(decision.confidence_level.upper(), style=tone_badge_style("neutral")),
                        ],
                        style={"display": "flex", "flexDirection": "column", "alignItems": "flex-end", "justifyContent": "flex-start"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "gap": "12px", "marginBottom": "12px"},
            ),
            html.Div(
                decision.thesis,
                style={"fontSize": "15px", "lineHeight": "1.58", "color": TEXT_PRIMARY, "marginBottom": "10px", "maxWidth": "88ch"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(label, style={**LABEL_STYLE, "marginBottom": "4px"}),
                            html.Div(value, style={"fontSize": "14px", "fontWeight": "700", "lineHeight": "1.25", "color": color}),
                        ],
                        style={
                            **CARD_STYLE,
                            "padding": "10px 12px",
                            "backgroundColor": BG_SURFACE_2,
                            "border": f"1px solid {BORDER}",
                        },
                    )
                    for label, value, color in positioning_cards
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "10px", "marginBottom": "10px"},
            ),
            html.Div(
                assumption_detail,
                style={"fontSize": "12px", "lineHeight": "1.45", "color": TEXT_MUTED, "marginBottom": "10px"},
            ),
            html.Div(
                assumption_chips,
                style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginBottom": "10px"},
            ) if assumption_chips else None,
            html.Div(
                [block for block in [
                    _list_block("Talking Points", talking_points, tone="positive"),
                    _list_block("Watch-Outs", watchouts, tone="warning"),
                ] if block is not None],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px"},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "18px 20px", "marginBottom": "16px"},
    )


def _owner_decision_close(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    decision = view.decision
    conclusion = _decision_conclusion(view, report)
    if decision is None:
        return html.Div()
    return html.Div(
        [
            html.Div("FINAL DECISION CLOSE", style={**SECTION_HEADER_STYLE, "fontSize": "12px", "letterSpacing": "0.12em", "marginBottom": "10px"}),
            html.Div(conclusion, style={"fontSize": "14px", "lineHeight": "1.65", "color": TEXT_PRIMARY, "marginBottom": "8px"}),
            html.Div(
                f"{decision.recommendation}: {decision.required_belief}",
                style={"fontSize": "12px", "lineHeight": "1.6", "color": TEXT_SECONDARY},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "16px 18px", "marginTop": "16px"},
    )


def _realtor_positioning_close(view: PropertyAnalysisView) -> html.Div:
    decision = view.decision
    if decision is None:
        return html.Div()
    return html.Div(
        [
            html.Div("RECOMMENDED POSITIONING", style={**SECTION_HEADER_STYLE, "fontSize": "12px", "letterSpacing": "0.12em", "marginBottom": "10px"}),
            html.Div(
                f"Lead with {decision.best_fit.lower()} fit, keep the strongest talking points grounded in the actual economics and optionality, and flag early where diligence still matters.",
                style={"fontSize": "14px", "lineHeight": "1.65", "color": TEXT_PRIMARY, "marginBottom": "8px"},
            ),
            html.Div(
                _reframe_risk_for_realtor(decision.required_belief),
                style={"fontSize": "12px", "lineHeight": "1.6", "color": TEXT_SECONDARY},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "16px 18px", "marginTop": "16px"},
    )


def _economics_summary_box(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    metrics = _economics_inputs(report, view)
    rows = [
        ("Monthly carry", _fmt_value(metrics["gross_monthly_cost"])),
        ("Rent support", _fmt_value(metrics["monthly_rent"])),
        ("Net monthly cost", _fmt_value(metrics["net_monthly_cost"])),
        ("Monthly cash flow", view.income_support.monthly_cash_flow_text),
    ]
    return html.Div(
        [
            html.Div("Monthly Economics", style=SECTION_HEADER_STYLE),
            html.Table(
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(label, style={"padding": "4px 12px 4px 0", "fontSize": "11px", "color": TEXT_MUTED}),
                                html.Td(value, style={"padding": "4px 0", "fontSize": "11px", "fontWeight": "600", "textAlign": "right"}),
                            ]
                        )
                        for label, value in rows
                    ]
                ),
                style={"width": "100%", "borderCollapse": "collapse"},
            ),
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def _scenario_table(view: PropertyAnalysisView) -> html.Div:
    metric_rows = [
        {"Scenario": "Downside", "Value": view.forward.bear_value_text, "Vs Ask": view.forward.downside_pct_text},
        {"Scenario": "Base", "Value": view.forward.base_value_text, "Vs Ask": "—"},
        {"Scenario": "Upside", "Value": view.forward.bull_value_text, "Vs Ask": view.forward.upside_pct_text},
    ]
    if view.stress_case is not None:
        metric_rows.insert(0, {"Scenario": "Stress", "Value": view.forward.stress_case_value_text, "Vs Ask": "Tail risk"})
    return html.Div(simple_table(metric_rows, page_size=6), style={"flex": "0 0 280px"})


def _scenario_skew_summary(view: PropertyAnalysisView) -> html.Div:
    return html.Div(
        [
            html.Div("Scenario Interpretation", style=SECTION_HEADER_STYLE),
            html.Div(
                f"Base case {view.forward.base_value_text}, with bull at {view.forward.bull_value_text} and bear at {view.forward.bear_value_text}. "
                f"Drivers: drift {view.forward.market_drift_text}, location {view.forward.location_premium_text}, "
                f"risk {view.forward.risk_discount_text}, optionality {view.forward.optionality_premium_text}.",
                style={"fontSize": "12px", "lineHeight": "1.6", "color": TEXT_SECONDARY},
            ),
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def _risk_list_block(view: PropertyAnalysisView) -> html.Div | None:
    top_risks = view.top_risks[:3]
    if not top_risks:
        return None
    return html.Div(
        [
            html.Div("Biggest Risks", style=SECTION_HEADER_STYLE),
            html.Ul(
                [html.Li(risk, style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY}) for risk in top_risks],
                style={"margin": "4px 0 0 0", "paddingLeft": "16px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def _scarcity_breakdown_strip(view: PropertyAnalysisView) -> html.Div | None:
    """Show land scarcity vs location scarcity as a split metric strip."""
    rl = view.risk_location
    land = getattr(rl, "land_scarcity_score", None)
    loc = getattr(rl, "location_scarcity_score", None)
    if land is None and loc is None:
        return None
    items = []
    if land is not None:
        items.append(("Land Scarcity", f"{land:.0f}", None))
    if loc is not None:
        items.append(("Location Scarcity", f"{loc:.0f}", None))
    items.append(("Composite", f"{rl.scarcity_score:.0f}", None))
    return html.Div(
        [
            html.Div("Scarcity Breakdown", style=SECTION_HEADER_STYLE),
            inline_metric_strip(items),
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def _optionality_fact_block(view: PropertyAnalysisView) -> html.Div:
    facts = []
    if view.compare_metrics.get("lot_size") is not None:
        facts.append(("Lot Size", f"{view.compare_metrics['lot_size']:.2f} ac" if isinstance(view.compare_metrics["lot_size"], float) else str(view.compare_metrics["lot_size"])))
    facts.append(("Condition", view.condition_profile))
    facts.append(("CapEx Lane", view.capex_lane))
    if view.buyer_fit:
        facts.append(("Best Fits", ", ".join(view.buyer_fit[:2])))
    return html.Div(
        [
            html.Div("Supporting Facts", style=SECTION_HEADER_STYLE),
            html.Div(
                [html.Div([html.Span(f"{label}: ", style={"fontWeight": "600"}), html.Span(value, style={"color": TEXT_SECONDARY})], style={"fontSize": "11px"}) for label, value in facts],
                style={"display": "grid", "gap": "4px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def _renovation_path_summary(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    reno_result = report.module_results.get("renovation_scenario")
    reno_payload = reno_result.payload if reno_result is not None and isinstance(reno_result.payload, dict) else None
    explicit_renovation = bool(reno_payload and reno_payload.get("enabled"))

    option_one_rows = [
        html.Div("Option 1", style={**LABEL_STYLE, "marginBottom": "4px"}),
        html.Div("Buy As-Is", style={"fontSize": "16px", "fontWeight": "700", "color": TEXT_PRIMARY, "marginBottom": "6px"}),
        html.Div(
            f"Forward base case: {_fmt_compact(view.base_case)}",
            style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_PRIMARY},
        ),
        html.Div(
            f"Range: {_fmt_compact(view.bear_case)} downside to {_fmt_compact(view.bull_case)} upside.",
            style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY},
        ),
    ]

    if explicit_renovation:
        renovated_bcv = reno_payload.get("renovated_bcv")
        budget = reno_payload.get("renovation_budget")
        option_two_note = (
            f"As renovated, Briarwood estimates value around {_fmt_compact(renovated_bcv)}"
            + (f" on a budget of {_fmt_compact(budget)}." if budget else ".")
        )
    else:
        from briarwood.decision_model.scoring import estimate_comp_renovation_premium
        premium_data = estimate_comp_renovation_premium(report)
        renovated_bcv = premium_data.get("estimated_renovated_value") or view.bull_case
        if premium_data.get("estimated_renovated_value"):
            option_two_note = (
                f"Estimated renovated value: {_fmt_compact(renovated_bcv)}, "
                "based on the renovation premium observed in area comps."
            )
        else:
            option_two_note = (
                f"Estimated value-add anchor: {_fmt_compact(renovated_bcv)}. "
                "This is a renovation/value-add upside case, not a fully budgeted construction scenario."
            )

    option_two_rows = [
        html.Div("Option 2", style={**LABEL_STYLE, "marginBottom": "4px"}),
        html.Div("Buy + Renovate", style={"fontSize": "16px", "fontWeight": "700", "color": TEXT_PRIMARY, "marginBottom": "6px"}),
        html.Div(option_two_note, style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_PRIMARY}),
    ]

    return html.Div(
        [
            html.Div(option_one_rows, style={**CARD_STYLE, "padding": "12px 14px"}),
            html.Div(option_two_rows, style={**CARD_STYLE, "padding": "12px 14px"}),
        ],
        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px"},
    )


def _renovation_justification_block(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div | None:
    if view.decision is None or view.decision.best_fit != "Value-Add / Renovation":
        return None
    chart = renovation_justification_chart(view, report)
    if chart is None:
        return None

    reno_result = report.module_results.get("renovation_scenario")
    reno_payload = reno_result.payload if reno_result is not None and isinstance(reno_result.payload, dict) else None
    explicit_renovation = bool(reno_payload and reno_payload.get("enabled"))
    anchor_text = (
        "Briarwood is separating the as-is forward case from the buy-and-renovate case below."
        if explicit_renovation else
        "Briarwood is separating the as-is forward case from an estimated renovation/value-add case below."
    )
    return html.Div(
        [
            html.Div("Renovation Justification", style=SECTION_HEADER_STYLE),
            html.Div(
                anchor_text,
                style={"fontSize": "12px", "lineHeight": "1.6", "color": TEXT_SECONDARY, "marginBottom": "8px"},
            ),
            _renovation_path_summary(view, report),
            chart,
        ],
        style={**CARD_STYLE, "padding": "10px 12px"},
    )


def _evidence_summary_strip(view: PropertyAnalysisView) -> html.Div:
    sourced = len(view.evidence.sourced_inputs)
    user_supplied = len(view.evidence.user_supplied_inputs)
    estimated = len(view.evidence.estimated_inputs)
    missing = len(view.evidence.missing_inputs)
    return html.Div(
        [
            compact_badge("Overall Confidence", f"{view.overall_confidence:.0%}", tone="neutral"),
            compact_badge("Sourced", str(sourced), tone="positive" if sourced else "neutral"),
            compact_badge("User Confirmed", str(user_supplied), tone="positive" if user_supplied else "neutral"),
            compact_badge("Estimated", str(estimated), tone="warning" if estimated else "neutral"),
            compact_badge("Missing", str(missing), tone="negative" if missing else "neutral"),
        ],
        style={"display": "flex", "gap": "6px", "flexWrap": "wrap"},
    )


# ── Archived 2026-04-08 ────────────────────────────────────────────────────
# `_value_snapshot_block` used to live at the bottom of the Overview tab as a
# compact "Current Value Snapshot" bar. Its metrics (Ask, Fair Value, All-In
# Basis, Town Prior, subject-vs-town PPSF, town opportunity, town context
# confidence) have been absorbed into `_value_snapshot_top_section` so the
# value story lives in a single section. Function body is preserved.
# ───────────────────────────────────────────────────────────────────────────
def _value_snapshot_block(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    town_context = view.town_context or {}
    metric_rows = [
        ("Ask", _fmt_compact(view.ask_price), None),
        ("Fair Value", _fmt_compact(view.bcv), gap_pct_text(view) if view.mispricing_pct is not None else None),
        ("All-In Basis", _fmt_compact(view.all_in_basis), _capex_basis_source_label(view.capex_basis_source)),
        ("Town Prior", _fmt_compact(view.compare_metrics.get("town_baseline_median_price")), f"Idx {float(view.compare_metrics.get('town_price_index')):.0f}" if view.compare_metrics.get("town_price_index") is not None else None),
    ]
    secondary_rows = []
    if town_context.get("subject_ppsf_vs_town") is not None:
        secondary_rows.append(
            ("Subject vs Town PPSF", f"{float(town_context['subject_ppsf_vs_town']):.2f}x", None)
        )
    if town_context.get("town_relative_opportunity_score") is not None:
        secondary_rows.append(
            ("Town Opportunity", f"{float(town_context['town_relative_opportunity_score']):.2f}/5", None)
        )
    if town_context.get("town_context_confidence") is not None:
        secondary_rows.append(
            ("Town Context", f"{float(town_context['town_context_confidence']):.0%}", None)
        )

    return html.Div(
        [
            html.Div("Current Value Snapshot", style=SECTION_HEADER_STYLE),
            inline_metric_strip(metric_rows),
            inline_metric_strip(secondary_rows) if secondary_rows else None,
        ],
        style={**CARD_STYLE, "padding": "12px 14px"},
    )


def _property_analysis_section(title: str, subtitle: str, children: list) -> html.Div:
    return html.Div(
        [
            html.Div(title, style=SECTION_HEADER_STYLE),
            html.Div(
                subtitle,
                style={"fontSize": "13px", "lineHeight": "1.6", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ),
            *children,
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "16px 18px"},
    )


def _value_snapshot_top_section(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    ask = view.ask_price
    bcv = view.bcv
    base = view.base_case
    gap = (bcv - ask) if isinstance(bcv, (int, float)) and isinstance(ask, (int, float)) else None
    if gap is None:
        framing = "Briarwood has not returned a full value gap yet, so this section falls back to the best available fair-value anchor."
        tone = "neutral"
    elif gap >= 0:
        framing = f"Briarwood values the property around {_fmt_compact(bcv)}, or about {_fmt_compact(gap)} above ask today."
        tone = "positive" if gap > 0 else "neutral"
    else:
        framing = f"Briarwood values the property around {_fmt_compact(bcv)}, or about {_fmt_compact(abs(gap))} below the current ask."
        tone = "warning"

    range_text = "12-month range unavailable."
    if view.bear_case is not None and view.bull_case is not None:
        range_text = f"12-month range runs from {_fmt_compact(view.bear_case)} to {_fmt_compact(view.bull_case)}."
    if isinstance(base, (int, float)) and isinstance(ask, (int, float)):
        if base < ask:
            shortfall = ask - base
            range_text = f"{range_text} Even the 12-month base case stays about {_fmt_compact(shortfall)} below today's ask."
        elif base > ask:
            cushion_12m = base - ask
            range_text = f"{range_text} The 12-month base case sits about {_fmt_compact(cushion_12m)} above today's ask."

    town_context = view.town_context or {}
    subject_vs_town = town_context.get("subject_ppsf_vs_town")
    town_prior = view.compare_metrics.get("town_baseline_median_price")
    value_cards: list[tuple[str, str, str | None]] = [
        ("Ask Price", _fmt_compact(ask), "current asking price"),
        (
            "Briarwood Fair Value",
            _fmt_compact(bcv),
            f"{gap_pct_text(view)} vs ask" if view.mispricing_pct is not None else "today's fair value anchor",
        ),
        (
            "12M Base Case",
            _fmt_compact(base),
            (
                f"{_fmt_signed_pct(((base - ask) / ask))} vs ask in 12 months"
                if isinstance(base, (int, float)) and isinstance(ask, (int, float)) and ask != 0
                else "base-case value in 12 months"
            ),
        ),
        (
            "All-In Basis",
            _fmt_compact(view.all_in_basis),
            _capex_basis_source_label(view.capex_basis_source),
        ),
    ]
    if town_prior is not None:
        value_cards.append(
            (
                "Town Median Price",
                _fmt_compact(town_prior),
                f"town price index {float(view.compare_metrics.get('town_price_index')):.0f}" if view.compare_metrics.get("town_price_index") is not None else "local reference point",
            )
        )
    if subject_vs_town is not None:
        ratio = float(subject_vs_town)
        if ratio < 1:
            town_compare = f"pricing is {((1 - ratio) * 100):.0f}% below town PPSF"
        elif ratio > 1:
            town_compare = f"pricing is {((ratio - 1) * 100):.0f}% above town PPSF"
        else:
            town_compare = "priced in line with town PPSF"
        value_cards.append(
            (
                "Compared with Town",
                f"{ratio:.2f}x",
                town_compare,
            )
        )

    value_box = html.Div(
        [
            html.Div("What We Think It Is Worth Now", style={**LABEL_STYLE, "marginBottom": "6px"}),
            html.Div(_fmt_compact(bcv or base), style={**VALUE_STYLE_LARGE, "color": tone_color(tone) if tone != "neutral" else TEXT_PRIMARY}),
            html.Div(
                framing,
                style={"fontSize": "14px", "lineHeight": "1.6", "color": TEXT_PRIMARY, "marginTop": "6px"},
            ),
            html.Div(
                range_text,
                style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "6px"},
            ),
            html.Div(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(label, style=LABEL_STYLE),
                                html.Div(value, style={"fontSize": "18px", "fontWeight": "800", "lineHeight": "1.1", "color": TEXT_PRIMARY}),
                                html.Div(detail, style={"fontSize": "11px", "lineHeight": "1.45", "color": TEXT_SECONDARY, "marginTop": "6px"}) if detail else None,
                            ],
                            style={**CARD_STYLE, "padding": "12px 14px", "boxShadow": "none", "borderColor": BORDER_SUBTLE, "minWidth": "0"},
                        )
                        for label, value, detail in value_cards
                    ],
                    style={
                        "display": "grid",
                        "gridTemplateColumns": f"repeat({len(value_cards)}, minmax(0, 1fr))",
                        "gap": "10px",
                        "marginTop": "12px",
                    },
                ),
                style={"overflowX": "auto"},
            ),
        ],
        style={**CARD_STYLE, "padding": "14px 16px"},
    )

    market_anchors_block = html.Div(
        [
            html.Div("Market Anchors", style={**LABEL_STYLE, "marginBottom": "6px"}),
            html.Div(
                "Segmented comp ranges show how direct comps, income-style comps, location, and lot context are shaping the valuation rather than hiding everything inside one number.",
                style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(item.label, style=LABEL_STYLE),
                            html.Div(item.range_text, style={"fontSize": "18px", "fontWeight": "800", "lineHeight": "1.15", "color": TEXT_PRIMARY}),
                            html.Div(f"Confidence {item.confidence_text}", style={"fontSize": "11px", "lineHeight": "1.45", "color": TEXT_SECONDARY, "marginTop": "4px"}),
                            html.Div(item.detail, style={"fontSize": "11px", "lineHeight": "1.45", "color": TEXT_SECONDARY, "marginTop": "6px"}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px", "boxShadow": "none", "borderColor": BORDER_SUBTLE},
                    )
                    for item in view.value.market_anchors
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))", "gap": "10px"},
            ) if view.value.market_anchors else html.Div("Segmented market anchors are not yet available for this property.", style={"fontSize": "12px", "color": TEXT_MUTED}),
        ],
        style={**CARD_STYLE, "padding": "14px 16px"},
    )

    value_drivers_block = html.Div(
        [
            html.Div("What's Driving Value?", style={**LABEL_STYLE, "marginBottom": "6px"}),
            html.Div(
                "These are the property-specific factors Briarwood sees as most responsible for the gap between the direct market anchor and the adjusted value.",
                style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(item.label, style=LABEL_STYLE),
                            html.Div(item.impact_text, style={"fontSize": "20px", "fontWeight": "800", "lineHeight": "1.1", "color": TONE_POSITIVE_TEXT if item.impact_text.startswith("+") else TONE_WARNING_TEXT if item.impact_text.startswith("-") else TEXT_PRIMARY}),
                            html.Div(f"Confidence {item.confidence_text}", style={"fontSize": "11px", "lineHeight": "1.45", "color": TEXT_SECONDARY, "marginTop": "4px"}),
                            html.Div(item.description, style={"fontSize": "11px", "lineHeight": "1.45", "color": TEXT_SECONDARY, "marginTop": "6px"}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px", "boxShadow": "none", "borderColor": BORDER_SUBTLE},
                    )
                    for item in view.value.value_drivers[:5]
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))", "gap": "10px"},
            ) if view.value.value_drivers else html.Div("Property-specific value drivers are not yet available for this property.", style={"fontSize": "12px", "color": TEXT_MUTED}),
        ],
        style={**CARD_STYLE, "padding": "14px 16px"},
    )

    value_bridge_block = html.Div(
        [
            html.Div("Value Bridge", style={**LABEL_STYLE, "marginBottom": "6px"}),
            html.Div(
                "Start from the direct market anchor, then step through the main property-specific adjustments until you reach Briarwood's adjusted value.",
                style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(step.label, style=LABEL_STYLE),
                            html.Div(step.value_text, style={"fontSize": "18px", "fontWeight": "800", "lineHeight": "1.1", "color": TEXT_PRIMARY}),
                            html.Div(f"Confidence {step.confidence_text}", style={"fontSize": "11px", "lineHeight": "1.45", "color": TEXT_SECONDARY, "marginTop": "4px"}),
                        ],
                        style={**CARD_STYLE, "padding": "12px 14px", "boxShadow": "none", "borderColor": BORDER_SUBTLE},
                    )
                    for step in view.value.value_bridge
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "10px"},
            ) if view.value.value_bridge else html.Div("Value bridge is not yet available for this property.", style={"fontSize": "12px", "color": TEXT_MUTED}),
        ],
        style={**CARD_STYLE, "padding": "14px 16px"},
    )

    return _property_analysis_section(
        "Section A - Value Snapshot",
        "Answer the value question once: what we think it is worth today, how that compares to ask, and what the 12-month range looks like from here.",
        [
            value_box,
            market_anchors_block,
            value_drivers_block,
            value_bridge_block,
        ],
    )


def renovation_value_trajectory_chart(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    show_renovated: bool = False,
    years: int = 1,
    chart_height: int | None = None,
) -> go.Figure:
    """Base-case value trajectory anchored at ask price.

    Both trajectories start at ``ask_price`` on month 0 and project out from
    Briarwood's current 12-month anchors. The as-is terminal is the engine's
    base-case value (BCV or base). The renovated overlay uses the modeled
    renovated BCV when available; otherwise it falls back to the comp-derived
    renovation premium.
    """
    ask = view.ask_price
    base = view.base_case
    bcv = view.bcv
    terminal_as_is = bcv or base

    fig = go.Figure()

    if ask is None or terminal_as_is is None:
        fig.add_annotation(
            text="Trajectory unavailable — ask price or fair value missing.",
            showarrow=False,
            font={"color": TEXT_MUTED, "size": 12},
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        layout = dict(PLOTLY_LAYOUT_COMPACT)
        layout["height"] = chart_height or CHART_HEIGHT_STANDARD
        fig.update_layout(**layout)
        return fig

    months = list(range(0, max(1, years * 12) + 1))

    def _project_path(start: float, one_year_terminal: float, total_years: int) -> list[float]:
        if len(months) <= 1:
            return [start]
        if start > 0 and one_year_terminal > 0:
            annual_ratio = one_year_terminal / start
            return [start * (annual_ratio ** (month / 12.0)) for month in months]
        projected_terminal = start + ((one_year_terminal - start) * total_years)
        step = (projected_terminal - start) / (len(months) - 1)
        return [start + step * i for i in range(len(months))]

    # As-is base trajectory
    as_is_path = _project_path(ask, terminal_as_is, years)
    fig.add_trace(
        go.Scatter(
            x=months,
            y=as_is_path,
            mode="lines+markers",
            name="As-Is (base)",
            line={"color": ACCENT_BLUE, "width": 3},
            marker={"size": 6, "color": ACCENT_BLUE},
            hovertemplate="Month %{x}<br>As-Is: %{y:$,.0f}<extra></extra>",
        )
    )

    # Renovated overlay — fall back to comp-derived premium when reno scenario
    # is not modeled so the toggle always produces a visible second line.
    if show_renovated:
        renovated_terminal: float | None = None
        overlay_label = "Renovated (base)"
        reno = _get_reno_data(report)
        if reno and reno.get("renovated_bcv") is not None:
            renovated_terminal = float(reno["renovated_bcv"])
        else:
            try:
                from briarwood.decision_model.scoring import estimate_comp_renovation_premium
                premium_data = estimate_comp_renovation_premium(report)
                candidate = premium_data.get("estimated_renovated_value")
                if candidate is not None:
                    renovated_terminal = float(candidate)
                    overlay_label = "Renovated (comp-derived)"
            except Exception:
                renovated_terminal = None
            if renovated_terminal is None and view.bull_case is not None:
                renovated_terminal = float(view.bull_case)
                overlay_label = "Renovated (bull fallback)"

        if renovated_terminal is not None:
            reno_path = _project_path(ask, renovated_terminal, years)
            lower_path = [min(a, b) for a, b in zip(as_is_path, reno_path)]
            upper_path = [max(a, b) for a, b in zip(as_is_path, reno_path)]
            fig.add_trace(
                go.Scatter(
                    x=months,
                    y=lower_path,
                    mode="lines",
                    line={"color": "rgba(0,0,0,0)", "width": 0},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=months,
                    y=upper_path,
                    mode="lines",
                    line={"color": "rgba(0,0,0,0)", "width": 0},
                    fill="tonexty",
                    fillcolor="rgba(107, 114, 128, 0.14)",
                    hoverinfo="skip",
                    showlegend=False,
                    name="Renovation gap",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=months,
                    y=reno_path,
                    mode="lines+markers",
                    name=overlay_label,
                    line={"color": ACCENT_GREEN, "width": 3, "dash": "dash"},
                    marker={"size": 6, "color": ACCENT_GREEN},
                    hovertemplate="Month %{x}<br>Renovated: %{y:$,.0f}<extra></extra>",
                )
            )
            if as_is_path[-1]:
                gap_pct = ((reno_path[-1] - as_is_path[-1]) / abs(as_is_path[-1])) * 100
                fig.add_annotation(
                    x=months[-1],
                    y=max(as_is_path[-1], reno_path[-1]),
                    text=f"{gap_pct:+.0f}% gap",
                    showarrow=False,
                    yshift=16,
                    font={"color": TEXT_SECONDARY, "size": 11},
                    bgcolor=BG_SURFACE,
                    bordercolor=BORDER,
                    borderwidth=1,
                )
        else:
            fig.add_annotation(
                text="Renovation scenario not modeled and no comp premium available.",
                showarrow=False,
                font={"color": TEXT_MUTED, "size": 10},
                xref="paper", yref="paper", x=0.98, y=0.02, xanchor="right", yanchor="bottom",
            )

    # Ask reference line
    fig.add_hline(
        y=ask,
        line_dash="dot",
        line_color=TEXT_MUTED,
        annotation_text=f"Ask {_fmt_compact(ask)}",
        annotation_font_color=TEXT_MUTED,
        annotation_font_size=10,
        annotation_position="bottom right",
    )

    layout = dict(PLOTLY_LAYOUT_COMPACT)
    layout["height"] = chart_height or CHART_HEIGHT_STANDARD
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f", "title": "Value"}
    layout["xaxis"] = {**layout.get("xaxis", {}), "title": "Months from today", "tickmode": "linear", "dtick": 6 if years > 1 else 2}
    layout["showlegend"] = True
    layout["legend"] = {**layout.get("legend", {}), "orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1.0}
    fig.update_layout(**layout)
    return fig


def _strategic_path_card(
    title: str,
    subtitle: str,
    metrics: list[tuple[str, str, str | None]],
    tone: str = "neutral",
    *,
    accent: str | None = None,
) -> html.Div:
    accent = accent or (tone_color(tone) if tone != "neutral" else ACCENT_BLUE)
    return html.Div(
        [
            html.Div(title, style={"fontSize": "17px", "fontWeight": "700", "color": TEXT_PRIMARY, "marginBottom": "6px"}),
            html.Div(subtitle, style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginBottom": "10px"}),
            inline_metric_strip(metrics),
        ],
        style={**CARD_STYLE, "padding": "14px 16px", "borderTop": f"3px solid {accent}"},
    )


def _strategic_paths_top_section(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    reno_payload = _get_reno_data(report)
    has_reno = reno_payload is not None

    as_is_card = _strategic_path_card(
        "Buy As-Is",
        "Read this as the current basis and forward hold case without leaning on construction execution.",
        [
            ("Fair Value", _fmt_compact(view.bcv), gap_pct_text(view) if view.mispricing_pct is not None else None),
            ("12M Base", _fmt_compact(view.base_case), None),
            ("Monthly Carry", view.income_support.monthly_cash_flow_text, _cash_flow_benchmark_label(view)),
            ("Recommendation", view.decision.recommendation if view.decision is not None else "—", None),
        ],
        tone="neutral",
        accent=ACCENT_BLUE,
    )

    if has_reno:
        renovated_bcv = reno_payload.get("renovated_bcv")
        budget = reno_payload.get("renovation_budget")
        net_creation = reno_payload.get("net_value_creation")
        reno_subtitle = "Renovation scenario is fully modeled in the engine and shows how value changes if execution goes right."
        reno_metrics = [
            ("Renovated Value", _fmt_compact(renovated_bcv), None),
            ("Budget", _fmt_compact(budget), None),
            ("Value Creation", _fmt_signed_currency(net_creation), None),
            ("ROI", f"{float(reno_payload.get('roi_pct')):.0f}%" if reno_payload.get("roi_pct") is not None else "—", None),
        ]
    else:
        from briarwood.decision_model.scoring import estimate_comp_renovation_premium

        premium_data = estimate_comp_renovation_premium(report)
        estimated_renovated = premium_data.get("estimated_renovated_value") or view.bull_case
        reno_subtitle = (
            "A dedicated renovation scenario is not available, so Briarwood falls back to a comp-derived value-add estimate."
        )
        reno_metrics = [
            ("Estimated Value-Add", _fmt_compact(estimated_renovated), None),
            ("Anchor", "Comp premium" if premium_data.get("estimated_renovated_value") else "Bull case fallback", None),
            ("Budget", "Needed for full model", None),
            ("Execution", "Not fully underwritten", None),
        ]

    path_summary_block = html.Div(
        [
            html.Div("Path Read", style={**LABEL_STYLE, "marginBottom": "6px"}),
            html.Div(
                "Strategic paths stay text-first here. Scenario and renovation visuals were removed so this section only frames the as-is path versus the value-add path.",
                style={"fontSize": "12px", "lineHeight": "1.6", "color": TEXT_PRIMARY},
            ),
            html.Div(
                simple_table(
                    [
                        {"Path": "Buy As-Is", "Value": _fmt_compact(view.bcv), "12M Base": _fmt_compact(view.base_case), "Carry": view.income_support.monthly_cash_flow_text},
                        {"Path": "Buy + Renovate", "Value": reno_metrics[0][1], "12M Base": reno_metrics[0][1], "Carry": reno_metrics[3][1]},
                    ],
                    page_size=2,
                ),
                style={"marginTop": "10px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "14px 16px", "marginTop": "10px"},
    )

    return _property_analysis_section(
        "Section B - Strategic Paths",
        "Compare the clean as-is path against the renovation path without forcing the user into the deeper scenario tabs first.",
        [
            html.Div(
                [
                    as_is_card,
                    _strategic_path_card("Buy + Renovate", reno_subtitle, reno_metrics, tone="positive" if has_reno else "warning", accent=ACCENT_GREEN),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(280px, 1fr))", "gap": "12px"},
            ),
            path_summary_block,
        ],
    )


def _forward_scenarios_top_section(view: PropertyAnalysisView) -> html.Div:
    ask = view.ask_price
    bcv = view.bcv
    cushion = (bcv - ask) if isinstance(bcv, (int, float)) and isinstance(ask, (int, float)) else None

    if cushion is None:
        cushion_ribbon = None
    elif cushion > 0:
        cushion_ribbon = html.Div(
            [
                html.Span(
                    f"Starting from an ask of {_fmt_compact(ask)}. ",
                    style={"color": TEXT_PRIMARY, "fontWeight": "600"},
                ),
                html.Span(
                    f"Briarwood sees fair value at {_fmt_compact(bcv)} — that's {_fmt_compact(cushion)} of cushion already captured on day one.",
                    style={"color": TONE_POSITIVE_TEXT},
                ),
            ],
            style={
                "fontSize": "13px",
                "lineHeight": "1.55",
                "padding": "10px 14px",
                "backgroundColor": TONE_POSITIVE_BG,
                "borderLeft": f"3px solid {TONE_POSITIVE_BORDER}",
                "borderRadius": "0 6px 6px 0",
                "marginBottom": "10px",
            },
        )
    elif cushion < 0:
        cushion_ribbon = html.Div(
            [
                html.Span(
                    f"Starting from an ask of {_fmt_compact(ask)}. ",
                    style={"color": TEXT_PRIMARY, "fontWeight": "600"},
                ),
                html.Span(
                    f"Briarwood sees fair value at {_fmt_compact(bcv)}, which is {_fmt_compact(abs(cushion))} below ask — you would need forward growth to absorb that gap.",
                    style={"color": TONE_WARNING_TEXT},
                ),
            ],
            style={
                "fontSize": "13px",
                "lineHeight": "1.55",
                "padding": "10px 14px",
                "backgroundColor": TONE_WARNING_BG,
                "borderLeft": f"3px solid {TONE_WARNING_BORDER}",
                "borderRadius": "0 6px 6px 0",
                "marginBottom": "10px",
            },
        )
    else:
        cushion_ribbon = None

    metric_rows = [
        ("Bear", view.forward.bear_value_text, view.forward.downside_pct_text),
        ("Base", view.forward.base_value_text, None),
        ("Bull", view.forward.bull_value_text, view.forward.upside_pct_text),
    ]
    if view.stress_case is not None:
        metric_rows.insert(0, ("Stress", view.forward.stress_case_value_text, "tail case"))

    return _property_analysis_section(
        "Section C - Forward Value / Scenario View",
        "All three cases are drawn from your ask price, so any value Briarwood already sees above ask shows up as a day-0 cushion before forward growth kicks in.",
        [
            cushion_ribbon,
            inline_metric_strip(metric_rows),
            html.Div(_scenario_table(view), style={"marginTop": "10px"}),
            html.Div(_scenario_skew_summary(view), style={"marginTop": "10px"}),
        ],
    )


def _rent_ramp_break_even_section(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    metrics = _economics_inputs(report, view)
    monthly_rent = metrics.get("monthly_rent")
    gross_cost = metrics.get("gross_monthly_cost")
    monthly_cash_flow = metrics.get("monthly_cash_flow")

    if not isinstance(monthly_rent, (int, float)):
        return _property_analysis_section(
            "Section C - Financial Path / Rent Ramp",
            "Show when the hold can work financially, or explain what data is still missing.",
            [
                html.Div(
                    "Rent ramp is unavailable because the current analysis does not include a usable monthly rent estimate.",
                    style={**CARD_STYLE, "padding": "14px 16px", "fontSize": "13px", "lineHeight": "1.6", "color": TEXT_SECONDARY},
                )
            ],
        )

    if not isinstance(gross_cost, (int, float)):
        if isinstance(monthly_cash_flow, (int, float)):
            gross_cost = monthly_rent - monthly_cash_flow
        else:
            gross_cost = None

    if not isinstance(gross_cost, (int, float)) or gross_cost <= 0:
        return _property_analysis_section(
            "Section C - Financial Path / Rent Ramp",
            "Show when the hold can work financially, or explain what data is still missing.",
            [
                html.Div(
                    "Rent ramp is unavailable because carrying-cost assumptions are incomplete.",
                    style={**CARD_STYLE, "padding": "14px 16px", "fontSize": "13px", "lineHeight": "1.6", "color": TEXT_SECONDARY},
                )
            ],
        )

    growth_rates = [0.00, 0.03, 0.05]
    horizon = list(range(0, 11))
    fig = go.Figure()
    break_even_labels: list[tuple[str, str, str | None]] = []

    for rate, color in zip(growth_rates, [TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN]):
        net_path = [(monthly_rent * ((1 + rate) ** year)) - gross_cost for year in horizon]
        fig.add_trace(
            go.Scatter(
                x=horizon,
                y=net_path,
                mode="lines+markers",
                name=f"{rate * 100:.0f}% rent growth",
                line={"color": color, "width": 3 if rate == 0.03 else 2},
                marker={"size": 7},
                hovertemplate=f"{rate * 100:.0f}% growth" + "<br>Year %{x}: %{y:$,.0f}/mo<extra></extra>",
            )
        )
        break_even_year = next((year for year, value in zip(horizon, net_path) if value >= 0), None)
        if break_even_year is None:
            label = "No break-even in 10y"
            sublabel = None
        elif break_even_year == 0:
            label = "Works today"
            sublabel = None
        else:
            label = f"Year {break_even_year}"
            sublabel = f"@ {rate * 100:.0f}% growth"
        break_even_labels.append((f"Break-Even {rate * 100:.0f}%", label, sublabel))

    fig.add_hline(y=0, line_dash="dot", line_color=TEXT_MUTED, annotation_text="Break-even", annotation_font_color=TEXT_MUTED, annotation_position="right")
    layout = dict(PLOTLY_LAYOUT_COMPACT)
    layout["height"] = 300
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f", "title": "Monthly cash flow"}
    layout["xaxis"] = {**layout.get("xaxis", {}), "title": "Years from today", "tickmode": "linear", "dtick": 1}
    fig.update_layout(**layout)

    if isinstance(monthly_cash_flow, (int, float)) and monthly_cash_flow >= 0:
        summary = f"The hold already works today with about ${monthly_cash_flow:,.0f}/mo of positive cash flow."
    else:
        base_break_even = next((label for metric, label, sub in break_even_labels if metric == "Break-Even 3%"), None)
        if base_break_even == "No break-even in 10y":
            summary = "Even with a moderate rent-growth path, this does not break even inside a 10-year hold under today's cost assumptions."
        else:
            summary = f"Under a 3% annual rent-growth path, break-even lands around {base_break_even.lower()}."

    return _property_analysis_section(
        "Section C - Financial Path / Rent Ramp",
        "Translate today's carry into a simple time path so the user can see whether the property works now or only after rent growth catches up.",
        [
            html.Div(
                [
                    html.Div("Break-Even Read", style={**LABEL_STYLE, "marginBottom": "8px"}),
                    html.Div(summary, style={"fontSize": "13px", "lineHeight": "1.6", "color": TEXT_PRIMARY, "marginBottom": "10px"}),
                    inline_metric_strip([
                        ("Current Rent", _fmt_compact(monthly_rent), None),
                        ("Monthly Cost", _fmt_compact(gross_cost), None),
                        ("Today Cash Flow", _fmt_signed_currency(monthly_cash_flow), None),
                    ]),
                    html.Div(style={"height": "8px"}),
                    inline_metric_strip(break_even_labels),
                ],
                style={**CARD_STYLE, "padding": "14px 16px"},
            ),
            html.Div(
                "v1 holds carrying costs flat and only moves rent — a decision aid, not a full operating pro forma.",
                style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_MUTED, "marginTop": "8px", "fontStyle": "italic"},
            ),
        ],
    )


def _property_analysis_top_stack(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    town_pulse_filter: str = "all",
    include_market_position: bool = True,
) -> html.Div:
    sections = [
        _value_snapshot_top_section(view, report),
        _strategic_paths_top_section(view, report),
        _rent_ramp_break_even_section(view, report),
    ]
    if include_market_position:
        sections.append(_market_position_top_section(view, report, town_pulse_filter=town_pulse_filter))
    return html.Div(
        sections,
        style={"display": "grid", "gap": "12px"},
    )


def _market_position_top_section(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    town_pulse_filter: str = "all",
) -> html.Div:
    rl = view.risk_location
    summary = (
        "This answers whether the town backdrop is helping, neutral, or fighting the property thesis, using current momentum plus local intelligence signals."
    )
    metrics = inline_metric_strip([
        ("Town", f"{rl.town_score:.0f}", _benchmark_sublabel(rl.town_score, "town_score") or rl.town_label.replace("_", " ").title()),
        ("Momentum", f"{rl.market_momentum_score:.0f}/100", _benchmark_sublabel(rl.market_momentum_score, "momentum") or rl.market_momentum_label),
        ("Scarcity", f"{rl.scarcity_score:.0f}", _benchmark_sublabel(rl.scarcity_score, "scarcity")),
        ("Liquidity", f"{rl.liquidity_score:.0f}/100", _benchmark_sublabel(rl.liquidity_score, "liquidity") or rl.liquidity_label),
    ])
    content_blocks = [
        html.Div(
            [
                html.Div("Backdrop Read", style={**LABEL_STYLE, "marginBottom": "6px"}),
                html.Div(
                    [
                        html.Span("Location Support", style={**SECTION_HEADER_STYLE, "fontSize": "10px"}),
                        html.Span(rl.location_support_label, style=tone_badge_style("positive" if rl.location_support_label == "Geo-Benchmarked" else "warning" if "Missing" in rl.location_support_label else "neutral")),
                    ],
                    style={"display": "flex", "gap": "8px", "alignItems": "center", "flexWrap": "wrap", "marginBottom": "6px"},
                ),
                metrics,
                html.Div(
                    "Town-level positioning blends valuation support, momentum, scarcity, liquidity, and Town Pulse catalysts into a quick market read.",
                    style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginTop": "6px"},
                ),
                html.Div(
                    rl.location_support_detail,
                    style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_MUTED, "marginTop": "4px"},
                ) if rl.location_support_detail else None,
                html.Div(
                    f"Benchmarked anchors: {rl.location_anchor_summary}",
                    style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "4px"},
                ) if rl.location_anchor_summary else None,
                html.Div(
                    "Catalysts are confirmed positive local signals. Risks are confirmed negative local signals. Watch items are early-stage, mixed, or lower-confidence signals.",
                    style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_MUTED, "marginTop": "6px"},
                ),
            ],
            style={**CARD_STYLE, "padding": "14px 16px"},
        ),
    ]
    pulse_block = _town_pulse_block(view, signal_filter=town_pulse_filter)
    if pulse_block is not None:
        content_blocks.append(pulse_block)
    else:
        content_blocks.append(
            html.Div(
                [
                    html.Div("Town Pulse", style=SECTION_HEADER_STYLE),
                    html.Div(
                        "No local intelligence is currently available for this town.",
                        style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_MUTED},
                    ),
                ],
                style={**CARD_STYLE, "padding": "14px 16px"},
            )
        )
    return _property_analysis_section(
        "Section E - Market Position",
        summary,
        [
            html.Div(
                content_blocks,
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(320px, 1fr))", "gap": "12px", "alignItems": "start"},
            ),
        ],
    )


def _market_position_sentiment_chart(view: PropertyAnalysisView, *, signal_filter: str = "all") -> dcc.Graph:
    del view, signal_filter
    return _disabled_chart()
    rl = view.risk_location
    pulse = rl.town_pulse
    bullish_count = len(pulse.bullish_signals) if pulse is not None else 0
    bearish_count = len(pulse.bearish_signals) if pulse is not None else 0
    watch_count = len(pulse.watch_items) if pulse is not None else 0
    confidence_bonus = {"High": 10.0, "Medium": 4.0, "Low": 0.0}.get(getattr(pulse, "confidence_label", "Low"), 0.0)

    catalysts_score = min(100.0, bullish_count * 28.0 + confidence_bonus + max(0.0, (rl.market_momentum_score - 50.0) * 0.25))
    risk_score = min(100.0, bearish_count * 28.0 + max(0.0, (50.0 - rl.risk_score) * 0.45))
    watch_score = min(100.0, watch_count * 24.0 + (8.0 if watch_count else 0.0))
    backdrop_score = max(0.0, min(100.0, (rl.town_score * 0.35) + (rl.market_momentum_score * 0.35) + (rl.scarcity_score * 0.15) + (rl.liquidity_score * 0.15)))

    labels = ["Catalysts", "Risks", "Watch", "Backdrop"]
    values = [round(catalysts_score, 1), round(risk_score, 1), round(watch_score, 1), round(backdrop_score, 1)]
    base_colors = [ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW, ACCENT_BLUE]
    filter_to_label = {"bullish": "Catalysts", "bearish": "Risks", "watch": "Watch"}
    active_label = filter_to_label.get(signal_filter)
    colors = [color if active_label in {None, label} else BG_SURFACE_4 for label, color in zip(labels, base_colors)]
    line_widths = [2 if active_label == label else 1 for label in labels]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker={"color": colors, "line": {"color": BORDER_SUBTLE, "width": line_widths}},
            text=[f"{value:.0f}" for value in values],
            textposition="outside",
            hovertemplate="%{y}: %{x:.0f}<extra></extra>",
        )
    )
    layout = dict(PLOTLY_LAYOUT_COMPACT)
    layout["height"] = 230
    layout["margin"] = {"l": 88, "r": 20, "t": 8, "b": 16}
    layout["xaxis"] = {
        **layout.get("xaxis", {}),
        "range": [0, 100],
        "showgrid": True,
        "gridcolor": BG_SURFACE_4,
        "title": "",
    }
    layout["yaxis"] = {
        **layout.get("yaxis", {}),
        "title": "",
        "categoryorder": "array",
        "categoryarray": labels[::-1],
    }
    layout["showlegend"] = False
    layout["clickmode"] = "event"
    layout["paper_bgcolor"] = BG_SURFACE
    layout["plot_bgcolor"] = BG_SURFACE_2
    fig.update_layout(**layout)
    return dcc.Graph(
        id="market-position-sentiment-chart",
        figure=fig,
        config={"displayModeBar": False, "responsive": True},
        clear_on_unhover=False,
    )


def _town_context_block(view: PropertyAnalysisView) -> html.Div | None:
    town_context = view.town_context or {}
    if not town_context:
        return None

    summary_lines: list[str] = []
    if town_context.get("subject_ppsf_vs_town") is not None:
        ratio = float(town_context["subject_ppsf_vs_town"])
        if ratio <= 0.92:
            summary_lines.append(f"Subject screens cheap relative to the town's median PPSF at {ratio:.2f}x.")
        elif ratio >= 1.08:
            summary_lines.append(f"Subject screens rich relative to the town's median PPSF at {ratio:.2f}x.")
        else:
            summary_lines.append(f"Subject sits near the town's median PPSF at {ratio:.2f}x.")
    if town_context.get("subject_price_vs_town") is not None:
        summary_lines.append(f"Ask is {float(town_context['subject_price_vs_town']):.2f}x the town median price anchor.")
    if town_context.get("subject_lot_vs_town") is not None:
        summary_lines.append(f"Lot size is {float(town_context['subject_lot_vs_town']):.2f}x the town median lot profile.")
    if town_context.get("qa_summary"):
        summary_lines.append(str(town_context["qa_summary"]))

    return html.Div(
        [
            html.Div("Town-Aware Context", style=SECTION_HEADER_STYLE),
            inline_metric_strip([
                ("Town", str(town_context.get("town") or "—"), None),
                ("Town Median PPSF", _fmt_compact(town_context.get("baseline_median_ppsf")), None),
                ("Price Index", f"{float(town_context['town_price_index']):.0f}" if town_context.get("town_price_index") is not None else "—", None),
                ("Liquidity Index", f"{float(town_context['town_liquidity_index']):.0f}" if town_context.get("town_liquidity_index") is not None else "—", None),
            ]),
            html.Div(
                [html.Div(line, style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY}) for line in summary_lines],
                style={"display": "grid", "gap": "4px", "marginTop": "8px"},
            ),
            html.Div(
                f"QA flags: {', '.join(town_context.get('qa_flags', [])) or 'none'}",
                style={"fontSize": "11px", "color": TONE_WARNING_TEXT if town_context.get('qa_flags') else TEXT_MUTED, "marginTop": "8px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "12px 14px"},
    )


# ── Archived 2026-04-08 ────────────────────────────────────────────────────
# `_strategy_fit_block` was the thin lens-positioning card at the top of the
# Strategy tab. Replaced by `_decision_engine_block` (the full investment
# memo), which covers best_fit + thesis + drivers + break conditions in a
# single more informative card. Function body preserved for re-use.
# ───────────────────────────────────────────────────────────────────────────
def _strategy_fit_block(view: PropertyAnalysisView) -> html.Div:
    decision = view.decision
    best_fit = decision.best_fit if decision is not None else _fit_label(view)
    recommendation = decision.recommendation if decision is not None else "—"
    return html.Div(
        [
            html.Div("Strategy Fit", style=SECTION_HEADER_STYLE),
            inline_metric_strip([
                ("Best Fit", best_fit, None),
                ("Recommendation", recommendation, None),
                ("Decision", _summary_verdict(view), None),
                ("Confidence", f"{view.overall_confidence:.0%}", None),
            ]),
            html.Div(
                [
                    _list_block("Why It Fits", view.buyer_fit[:3], tone="positive"),
                    _list_block("What Changes the Call", _decision_dependencies(view)[:3], tone="warning"),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px", "marginTop": "10px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "12px 14px"},
    )


def _report_card_block(view: PropertyAnalysisView) -> html.Div | None:
    report_card = view.report_card
    if report_card is None:
        return None

    def _contribution_list(title: str, items: list, tone_color: str) -> html.Div:
        if not items:
            return html.Div(
                [
                    html.Div(title, style=SECTION_HEADER_STYLE),
                    html.Div("No material contribution in this direction.", style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_MUTED}),
                ],
                style={**CARD_STYLE, "padding": "10px 12px"},
            )
        return html.Div(
            [
                html.Div(title, style=SECTION_HEADER_STYLE),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span(item.factor_name.replace("_", " ").title(), style={"fontSize": "12px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                                        html.Span(f"{item.percentage_impact}%", style={"fontSize": "12px", "fontWeight": "700", "color": tone_color}),
                                    ],
                                    style={"display": "flex", "justifyContent": "space-between", "gap": "8px"},
                                ),
                                html.Div(item.explanation, style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "4px"}),
                            ],
                            style={"paddingBottom": "8px", "borderBottom": f"1px solid {BORDER_SUBTLE}"} if idx < len(items) - 1 else {},
                        )
                        for idx, item in enumerate(items)
                    ],
                    style={"display": "grid", "gap": "8px"},
                ),
            ],
            style={**CARD_STYLE, "padding": "10px 12px"},
        )

    contribution_pairs = [
        (factor.replace("_", " ").title(), value)
        for factor, value in sorted(report_card.factor_contributions.items(), key=lambda item: abs(item[1]), reverse=True)
    ]

    return html.Div(
        [
            html.Div("Score Report Card", style=SECTION_HEADER_STYLE),
            html.Div(
                "This is the deterministic score breakdown behind Briarwood's investment read.",
                style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_MUTED, "marginBottom": "10px"},
            ),
            inline_metric_strip([(label, f"{value:+d}%", None) for label, value in contribution_pairs[:4]]),
            html.Div(
                [
                    _contribution_list("Positive Contributions", report_card.positive, TONE_POSITIVE_TEXT),
                    _contribution_list("Negative Contributions", report_card.negative, TONE_NEGATIVE_TEXT),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px", "marginTop": "10px"},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "16px 18px"},
    )


def _tear_sheet_subtabs(tabs: list[tuple[str, str, list]], *, default_value: str = "overview") -> dcc.Tabs:
    tab_style = {
        "backgroundColor": BG_SURFACE,
        "border": f"1px solid {BORDER}",
        "borderBottom": "none",
        "color": TEXT_SECONDARY,
        "fontSize": "12px",
        "fontWeight": "600",
        "padding": "10px 14px",
    }
    selected_style = {
        **tab_style,
        "backgroundColor": BG_SURFACE_2,
        "color": TEXT_PRIMARY,
        "borderTop": f"2px solid {ACCENT_BLUE}",
    }
    return dcc.Tabs(
        value=default_value,
        children=[
            dcc.Tab(
                label=label,
                value=value,
                style=tab_style,
                selected_style=selected_style,
                children=[
                    html.Div(
                        [child for child in children if child is not None],
                        style={"display": "grid", "gap": "14px", "paddingTop": "14px"},
                    )
                ],
            )
            for value, label, children in tabs
        ],
        style={"marginTop": "4px"},
        colors={"border": "transparent", "primary": ACCENT_BLUE, "background": BG_SURFACE},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# "SO WHAT?" INSIGHT LAYER
# ═══════════════════════════════════════════════════════════════════════════════


def _section_insight_callout(text: str, tone: str = "neutral") -> html.Div:
    """Small interpretive callout block for the top of each section body."""
    tone_borders = {
        "positive": TONE_POSITIVE_BORDER,
        "warning": TONE_WARNING_BORDER,
        "negative": TONE_NEGATIVE_BORDER,
        "neutral": TONE_NEUTRAL_BORDER,
    }
    tone_bgs = {
        "positive": TONE_POSITIVE_BG,
        "warning": TONE_WARNING_BG,
        "negative": TONE_NEGATIVE_BG,
        "neutral": TONE_NEUTRAL_BG,
    }
    return html.Div(
        text,
        style={
            "fontSize": "13px",
            "lineHeight": "1.55",
            "color": TEXT_PRIMARY,
            "padding": "10px 14px",
            "backgroundColor": tone_bgs.get(tone, TONE_NEUTRAL_BG),
            "borderLeft": f"3px solid {tone_borders.get(tone, TONE_NEUTRAL_BORDER)}",
            "borderRadius": "0 4px 4px 0",
            "marginBottom": "10px",
        },
    )


def _get_reno_data(report: AnalysisReport) -> dict | None:
    """Extract renovation scenario data from report, returns None if unavailable."""
    reno_result = report.module_results.get("renovation_scenario")
    if reno_result is None:
        return None
    payload = reno_result.payload if isinstance(reno_result.payload, dict) else None
    if payload and payload.get("enabled"):
        return payload
    return None


def _insight_hero_text(view: PropertyAnalysisView, report: AnalysisReport) -> tuple[str, str, str]:
    """Select the most noteworthy insight. Returns (primary, detail, tone)."""
    ask = view.ask_price
    bcv = view.bcv
    mispricing = view.mispricing_pct
    isr_raw = view.compare_metrics.get("income_support_ratio")
    isr = float(isr_raw) if isinstance(isr_raw, (int, float)) else None
    cash_flow = _parse_currency_text(view.income_support.monthly_cash_flow_text)
    reno = _get_reno_data(report)
    risk_score = view.risk_location.risk_score
    final_score = view.final_score

    # 1. Massive mispricing (>15%)
    if mispricing is not None and ask and bcv:
        gap = abs(bcv - ask)
        if mispricing > 0.15:
            return (
                f"Listed at {_fmt_compact(ask)}, this property appears undervalued. "
                f"Our comp-anchored model puts fair value at {_fmt_compact(bcv)} — {mispricing * 100:.0f}% higher.",
                f"That's ${gap:,.0f} of embedded value before you do anything.",
                "positive",
            )
        if mispricing < -0.15:
            return (
                f"This property is listed at {_fmt_compact(ask)}, but our analysis values it at {_fmt_compact(bcv)} — "
                f"that's {abs(mispricing) * 100:.0f}% above fair value.",
                f"At this price, you're paying a ${gap:,.0f} premium over what the market supports.",
                "negative",
            )

    # 2. Strong renovation opportunity
    if reno:
        roi = reno.get("roi_pct", 0)
        net_creation = reno.get("net_value_creation", 0)
        budget = reno.get("renovation_budget")
        renovated_bcv = reno.get("renovated_bcv")
        if roi > 50 and net_creation > 50_000 and ask and budget and renovated_bcv:
            return (
                f"This property is listed at {_fmt_compact(ask)}. Spend {_fmt_compact(budget)} on renovation "
                f"and it could be worth {_fmt_compact(renovated_bcv)}.",
                f"That's ${net_creation:,.0f} in created equity, a {roi:.0f}% return on the renovation investment.",
                "positive",
            )

    # 3. High score but elevated risk
    if final_score is not None and final_score >= 3.5 and risk_score <= 40:
        stress_val = view.stress_case
        if stress_val and ask:
            drawdown = (ask - stress_val) / ask * 100
            return (
                f"The numbers look good — score of {final_score:.1f}/5 — but the risk profile deserves attention.",
                f"{_primary_risk_text(view) or 'Risk'} is elevated, and in a stress scenario "
                f"this property could drop to {_fmt_compact(stress_val)} ({drawdown:.0f}% below ask).",
                "warning",
            )

    # 4. Strong income property
    if isr is not None and isr >= 1.0:
        rent_text = view.income_support.total_rent_text
        if isr >= 1.1 and cash_flow and cash_flow > 0:
            gross_yield = view.income_support.gross_yield_text
            return (
                f"This property generates positive cash flow. After all carrying costs, you net ${cash_flow:,.0f}/mo.",
                f"The {gross_yield} gross yield makes this a legitimate income play.",
                "positive",
            )
        if cash_flow is not None:
            return (
                f"At {_fmt_compact(ask)} with rental income of {rent_text}/mo, this property pays for itself.",
                f"Your net monthly cost is ${abs(cash_flow):,.0f}/mo — effectively break-even. That's rare at this price point.",
                "positive",
            )

    # 5. Negative cash flow warning
    if cash_flow is not None and cash_flow < -3000 and (isr is None or isr < 0.3):
        annual_burn = abs(cash_flow) * 12
        return (
            f"Carrying this property costs ${abs(cash_flow):,.0f}/mo all-in — "
            f"that's ${annual_burn:,.0f}/yr out of pocket with limited income offset.",
            "Before renovations or improvements, make sure you can sustain this burn through the hold period.",
            "warning",
        )

    # 6. Default insight
    if ask and bcv and mispricing is not None:
        direction = "undervalued" if mispricing > 0 else "overvalued"
        base_text = ""
        if view.base_case:
            base_text = f" The base case projects {_fmt_compact(view.base_case)} over the hold period."
        tone = "positive" if mispricing > 0.04 else "warning" if mispricing < -0.04 else "neutral"
        return (
            f"Listed at {_fmt_compact(ask)}, our model values this at {_fmt_compact(bcv)} "
            f"({direction} by {abs(mispricing) * 100:.0f}%).{base_text}",
            _summary_verdict(view)[:120],
            tone,
        )

    return ("Analysis in progress.", "", "neutral")


def _mini_scenario_bar(view: PropertyAnalysisView) -> html.Div | None:
    """Compact horizontal range bar showing bear–base–bull with ask marked."""
    bear = view.bear_case
    base = view.base_case
    bull = view.bull_case
    ask = view.ask_price
    if bear is None or base is None or bull is None:
        return None
    lo = min(bear, ask or bear) * 0.97
    hi = max(bull, ask or bull) * 1.03
    span = hi - lo
    if span <= 0:
        return None

    def _pct(val: float) -> str:
        return f"{((val - lo) / span) * 100:.1f}%"

    markers: list = []
    # Bear–Bull range band
    markers.append(html.Div(style={
        "position": "absolute",
        "left": _pct(bear), "width": f"{((bull - bear) / span) * 100:.1f}%",
        "top": "18px", "height": "12px",
        "backgroundColor": "rgba(88, 166, 255, 0.18)",
        "borderRadius": "3px",
    }))
    # Bear marker
    markers.append(html.Div(
        [html.Div(f"{_fmt_compact(bear)}", style={"fontSize": "9px", "color": ACCENT_RED, "whiteSpace": "nowrap"})],
        style={"position": "absolute", "left": _pct(bear), "top": "0", "transform": "translateX(-50%)"},
    ))
    # Bull marker
    markers.append(html.Div(
        [html.Div(f"{_fmt_compact(bull)}", style={"fontSize": "9px", "color": ACCENT_GREEN, "whiteSpace": "nowrap"})],
        style={"position": "absolute", "left": _pct(bull), "top": "0", "transform": "translateX(-50%)"},
    ))
    # Base marker (larger)
    markers.append(html.Div(style={
        "position": "absolute",
        "left": _pct(base), "top": "16px",
        "width": "8px", "height": "16px",
        "backgroundColor": ACCENT_BLUE,
        "borderRadius": "2px",
        "transform": "translateX(-50%)",
    }))
    markers.append(html.Div(
        [html.Div(f"Base {_fmt_compact(base)}", style={"fontSize": "9px", "color": ACCENT_BLUE, "fontWeight": "600", "whiteSpace": "nowrap"})],
        style={"position": "absolute", "left": _pct(base), "top": "34px", "transform": "translateX(-50%)"},
    ))
    # Ask marker
    if ask:
        markers.append(html.Div(style={
            "position": "absolute",
            "left": _pct(ask), "top": "14px",
            "width": "1px", "height": "20px",
            "borderLeft": f"2px dashed {TEXT_MUTED}",
        }))
        markers.append(html.Div(
            [html.Div(f"Ask {_fmt_compact(ask)}", style={"fontSize": "9px", "color": TEXT_MUTED, "whiteSpace": "nowrap"})],
            style={"position": "absolute", "left": _pct(ask), "bottom": "0", "transform": "translateX(-50%)"},
        ))
    # Renovation overlay if available
    reno_bcv = view.compare_metrics.get("renovated_bcv")
    if isinstance(reno_bcv, (int, float)) and reno_bcv > 0:
        markers.append(html.Div(style={
            "position": "absolute",
            "left": _pct(reno_bcv), "top": "16px",
            "width": "8px", "height": "16px",
            "backgroundColor": ACCENT_TEAL,
            "borderRadius": "2px",
            "transform": "translateX(-50%)",
        }))
        markers.append(html.Div(
            [html.Div(f"Reno {_fmt_compact(reno_bcv)}", style={"fontSize": "9px", "color": ACCENT_TEAL, "fontWeight": "600", "whiteSpace": "nowrap"})],
            style={"position": "absolute", "left": _pct(reno_bcv), "top": "34px", "transform": "translateX(-50%)"},
        ))

    return html.Div(
        markers,
        style={
            "position": "relative",
            "width": "100%",
            "height": "56px",
            "marginTop": "12px",
        },
    )


def render_insight_hero(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Insight hero card — the single most prominent 'so what?' on the page."""
    primary, detail, tone = _insight_hero_text(view, report)
    accent = tone_color(tone)
    mini_chart = _mini_scenario_bar(view)

    children: list = [
        html.Div(primary, style={"fontSize": "15px", "lineHeight": "1.55", "color": TEXT_PRIMARY, "fontWeight": "500"}),
    ]
    if detail:
        children.append(html.Div(detail, style={"fontSize": "13px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "6px"}))
    if mini_chart:
        children.append(mini_chart)

    return html.Div(
        children,
        style={
            **CARD_STYLE,
            "padding": "16px 18px",
            "marginBottom": "16px",
            "borderLeft": f"4px solid {accent}",
            "backgroundColor": BG_SURFACE_2,
        },
    )


# ── Per-section insight generators ────────────────────────────────────────────


def _price_insight(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div | None:
    """Interpretive callout for 'Is This a Good Price?'"""
    pct = view.net_opportunity_delta_pct if view.net_opportunity_delta_pct is not None else view.mispricing_pct
    if pct is None:
        return None

    # Town ppsf context
    subject_ppsf = view.compare_metrics.get("subject_ppsf")
    town_ppsf = view.compare_metrics.get("town_baseline_median_ppsf")
    ppsf_ctx = ""
    if isinstance(subject_ppsf, (int, float)) and isinstance(town_ppsf, (int, float)) and town_ppsf > 0:
        ppsf_ctx = f" At this price, you're paying ${subject_ppsf:,.0f}/sqft vs the town median of ${town_ppsf:,.0f}/sqft."

    direction = "discount" if pct > 0 else "premium"
    text = f"You're buying at a {abs(pct) * 100:.0f}% {direction} to our comp-anchored value.{ppsf_ctx}"
    if view.comps.is_hybrid_valuation:
        text += (
            f" (Hybrid valuation: primary dwelling {view.comps.primary_dwelling_value_text}"
            f" + {view.comps.additional_unit_count} rental unit(s)"
            f" {view.comps.additional_unit_income_value_text} via income cap.)"
        )
    tone = "positive" if pct > 0.04 else "warning" if pct < -0.04 else "neutral"
    return _section_insight_callout(text, tone)


def _economics_insight(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div | None:
    """Interpretive callout for 'Can I Afford to Hold It?'"""
    cash_flow = _parse_currency_text(view.income_support.monthly_cash_flow_text)
    isr_raw = view.compare_metrics.get("income_support_ratio")
    isr = float(isr_raw) if isinstance(isr_raw, (int, float)) else None

    if cash_flow is None:
        return None

    if cash_flow >= 0:
        text = (
            f"Your true monthly cost is effectively zero after rental income. "
            f"Cash flow is ${cash_flow:,.0f}/mo positive."
        )
        tone = "positive"
    else:
        abs_cf = abs(cash_flow)
        if isr is not None and isr > 0:
            coverage_pct = isr * 100
            text = (
                f"Your true monthly cost is ${abs_cf:,.0f}/mo after rental income. "
                f"The rental income covers {coverage_pct:.0f}% of your carry."
            )
        else:
            text = f"Your true monthly cost is ${abs_cf:,.0f}/mo all-in with no meaningful income offset."
        tone = "warning" if abs_cf > 2000 else "neutral"
    return _section_insight_callout(text, tone)


def _forward_insight(view: PropertyAnalysisView) -> html.Div | None:
    """Interpretive callout for 'What Happens If I Buy It?'"""
    bear = view.bear_case
    base = view.base_case
    bull = view.bull_case
    ask = view.ask_price
    if bear is None or bull is None or ask is None:
        return None

    spread_pct = (bull - bear) / ask * 100
    bear_vs_ask = (bear - ask) / ask * 100
    base_vs_ask = ((base - ask) / ask * 100) if base else None

    parts = [f"The range of outcomes spans {_fmt_compact(bear)} to {_fmt_compact(bull)} — a {spread_pct:.0f}% spread."]
    if bear_vs_ask >= 0:
        parts.append(f"Even in the bear case, you're above your purchase price.")
        tone = "positive"
    elif base_vs_ask is not None and base_vs_ask > 0:
        parts.append(f"The base case shows {base_vs_ask:.0f}% gain — the market supports your price.")
        tone = "neutral"
    else:
        parts.append(f"In the bear case, you'd be {abs(bear_vs_ask):.0f}% below your purchase price.")
        tone = "warning"
    return _section_insight_callout(" ".join(parts), tone)


def _risk_insight(view: PropertyAnalysisView) -> html.Div | None:
    """Interpretive callout for 'What Could Go Wrong?'"""
    risk_bits: list[str] = []
    primary_risk = _primary_risk_text(view)
    if primary_risk and primary_risk != "No primary risk surfaced yet.":
        risk_bits.append(primary_risk)
    elif view.top_risks:
        risk_bits.append(view.top_risks[0])
    if not risk_bits:
        return None

    top_risk = risk_bits[0]
    liq = view.risk_location.liquidity_label.lower()
    liq_ctx = ""
    if "thin" in liq or "low" in liq or "very low" in liq:
        dom_raw = view.compare_metrics.get("dom")
        if isinstance(dom_raw, (int, float)):
            liq_ctx = f" This is a thin market — if you need to sell quickly, expect {dom_raw:.0f}+ days on market."

    text = f"The biggest risk here is {top_risk.lower()}.{liq_ctx}"
    tone = "warning" if view.risk_location.risk_score <= 55 else "neutral"
    return _section_insight_callout(text, tone)


def _optionality_insight(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div | None:
    """Interpretive callout for 'Where's the Upside?'"""
    reno = _get_reno_data(report)
    if reno:
        roi = reno.get("roi_pct", 0)
        if roi > 0:
            text = f"Renovation ROI of {roi:.0f}% suggests this is a value-add play, not a hold-and-pray."
            tone = "positive" if roi > 30 else "neutral"
            return _section_insight_callout(text, tone)

    # Try comp-derived renovation premium
    from briarwood.decision_model.scoring import estimate_comp_renovation_premium
    premium_data = estimate_comp_renovation_premium(report)
    premium_pct = premium_data.get("renovation_premium_pct")
    est_creation = premium_data.get("estimated_value_creation")
    if premium_pct is not None and premium_pct > 0.05 and est_creation and est_creation > 0:
        text = (
            f"Renovated comps in this market trade at a {premium_pct * 100:.0f}% premium. "
            f"Estimated value creation from renovation: {_fmt_compact(est_creation)}."
        )
        tone = "positive" if premium_pct > 0.15 else "neutral"
        return _section_insight_callout(text, tone)

    category = view.category_scores.get("optionality") if view.category_scores else None
    if category is not None and category.score >= 3.5:
        text = "Multiple viable execution paths exist — the property has flexibility beyond its current use."
        return _section_insight_callout(text, "positive")
    if category is not None and category.score <= 2.5:
        text = "Optionality is limited. The upside case depends on a narrow set of conditions being met."
        return _section_insight_callout(text, "warning")
    return None


def _renovation_value_overlay(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div | None:
    """Renovation premium section — comp-driven or explicit renovation scenario.

    Shows a bar chart comparing renovated vs dated comp $/sqft, with estimated
    value creation.  Falls back to explicit renovation data if available, or
    shows a data-insufficient message for properties that need work.
    """
    from briarwood.decision_model.scoring import estimate_comp_renovation_premium

    condition = view.condition_profile.lower().replace(" ", "_")
    # Only show for properties where renovation is relevant
    if condition in ("renovated", "updated"):
        return None

    bcv = view.bcv

    # Try explicit renovation scenario first
    reno = _get_reno_data(report)
    if reno and bcv:
        renovated_bcv = reno.get("renovated_bcv")
        budget = reno.get("renovation_budget")
        net_creation = reno.get("net_value_creation")
        roi = reno.get("roi_pct", 0)
        if all([renovated_bcv, budget]):
            return html.Div(
                [
                    html.Div("RENOVATION VALUE", style={**SECTION_HEADER_STYLE, "marginBottom": "6px"}),
                    html.Div(
                        [
                            _reno_metric_cell("Current Fair Value", f"${bcv:,.0f}", TEXT_PRIMARY),
                            html.Div(
                                [
                                    html.Div(f"+ {_fmt_compact(budget)} reno", style={"fontSize": "10px", "color": ACCENT_TEAL}),
                                    html.Div("→", style={"fontSize": "20px", "color": ACCENT_TEAL, "fontWeight": "700"}),
                                ],
                                style={"textAlign": "center", "display": "flex", "flexDirection": "column", "alignItems": "center", "justifyContent": "center"},
                            ),
                            _reno_metric_cell("Renovated Fair Value", f"${renovated_bcv:,.0f}", ACCENT_TEAL),
                            _reno_metric_cell(
                                "Net Equity Created",
                                f"+${net_creation:,.0f}" if net_creation and net_creation > 0 else f"-${abs(net_creation or 0):,.0f}",
                                TONE_POSITIVE_TEXT if (net_creation or 0) > 0 else TONE_NEGATIVE_TEXT,
                            ),
                        ],
                        style={"display": "grid", "gridTemplateColumns": "1fr auto 1fr 1fr", "gap": "12px", "alignItems": "center"},
                    ),
                ],
                style={**CARD_STYLE, "padding": "10px 14px", "marginTop": "8px"},
            )

    # Comp-derived renovation premium
    premium_data = estimate_comp_renovation_premium(report)
    premium_pct = premium_data.get("renovation_premium_pct")
    reno_ppsf = premium_data.get("median_renovated_ppsf")
    dated_ppsf = premium_data.get("median_dated_ppsf")
    reno_count = premium_data.get("renovated_comp_count", 0)
    dated_count = premium_data.get("dated_comp_count", 0)
    est_value = premium_data.get("estimated_renovated_value")
    est_creation = premium_data.get("estimated_value_creation")

    children: list = [
        html.Div("RENOVATION PREMIUM FROM COMPS", style={**SECTION_HEADER_STYLE, "marginBottom": "6px"}),
    ]

    if premium_pct is not None and reno_ppsf and dated_ppsf:
        # Build the comparison bar chart
        bar_chart = _renovation_premium_bar_chart(
            reno_ppsf, dated_ppsf, premium_pct, reno_count, dated_count,
        )
        children.append(bar_chart)

        # Value estimate strip
        if bcv and est_value and est_creation:
            children.append(html.Div(
                [
                    _reno_metric_cell("Current Fair Value", _fmt_compact(bcv), TEXT_PRIMARY),
                    html.Div("→", style={"fontSize": "18px", "color": ACCENT_TEAL, "fontWeight": "700", "textAlign": "center", "alignSelf": "center"}),
                    _reno_metric_cell("Est. Renovated Value", _fmt_compact(est_value), ACCENT_TEAL),
                    _reno_metric_cell(
                        "Est. Value Creation",
                        f"+{_fmt_compact(est_creation)}" if est_creation > 0 else _fmt_compact(est_creation),
                        TONE_POSITIVE_TEXT if est_creation > 0 else TONE_WARNING_TEXT,
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr auto 1fr 1fr", "gap": "12px", "alignItems": "center", "marginTop": "10px"},
            ))
        children.append(html.Div(
            f"Based on {reno_count} renovated/updated and {dated_count} dated/needs-work comps in the area. "
            "Add an explicit renovation budget for a more precise estimate.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "8px", "lineHeight": "1.5"},
        ))
    else:
        # Insufficient data
        children.append(html.Div(
            [
                html.Div(
                    "Insufficient comp data to estimate renovation premium",
                    style={"fontSize": "13px", "color": TEXT_MUTED, "fontWeight": "500"},
                ),
                html.Div(
                    f"Need comps in both renovated/updated and dated/needs-work condition. "
                    f"Currently: {reno_count} renovated, {dated_count} dated in this market. "
                    "Add condition profiles to comps or provide an explicit renovation budget to unlock this analysis.",
                    style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "6px", "lineHeight": "1.5"},
                ),
            ],
            style={
                "padding": "16px",
                "textAlign": "center",
                "border": f"1px dashed {BORDER}",
                "borderRadius": "4px",
                "marginTop": "4px",
            },
        ))

    return html.Div(children, style={**CARD_STYLE, "padding": "10px 14px", "marginTop": "8px"})


def _reno_metric_cell(label: str, value: str, color: str) -> html.Div:
    """Small metric cell for renovation overlays."""
    return html.Div(
        [
            html.Div(label, style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase", "letterSpacing": "0.08em"}),
            html.Div(value, style={"fontSize": "16px", "fontWeight": "700", "color": color}),
        ],
        style={"textAlign": "center"},
    )


def _renovation_premium_bar_chart(
    reno_ppsf: float,
    dated_ppsf: float,
    premium_pct: float,
    reno_count: int,
    dated_count: int,
) -> dcc.Graph:
    del reno_ppsf, dated_ppsf, premium_pct, reno_count, dated_count
    return _disabled_chart()
    """Horizontal bar chart comparing renovated vs dated comp $/sqft."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=["Dated / Needs Work"],
        x=[dated_ppsf],
        orientation="h",
        name=f"Dated ({dated_count} comps)",
        marker_color=ACCENT_ORANGE,
        text=[f"${dated_ppsf:,.0f}/sqft"],
        textposition="inside",
        textfont={"color": "#fff", "size": 12},
        hovertemplate="Dated/Needs Work<br>$%{x:,.0f}/sqft<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=["Renovated / Updated"],
        x=[reno_ppsf],
        orientation="h",
        name=f"Renovated ({reno_count} comps)",
        marker_color=ACCENT_TEAL,
        text=[f"${reno_ppsf:,.0f}/sqft"],
        textposition="inside",
        textfont={"color": "#fff", "size": 12},
        hovertemplate="Renovated/Updated<br>$%{x:,.0f}/sqft<extra></extra>",
    ))
    # Add premium annotation
    fig.add_annotation(
        x=reno_ppsf,
        y="Renovated / Updated",
        text=f"+{premium_pct * 100:.0f}% premium",
        showarrow=False,
        xanchor="left",
        xshift=8,
        font={"size": 11, "color": ACCENT_TEAL},
    )
    layout = {**PLOTLY_LAYOUT_COMPACT}
    layout.update(
        height=100,
        margin={"l": 0, "r": 60, "t": 8, "b": 8},
        xaxis={"visible": False},
        yaxis={"tickfont": {"size": 11}},
        barmode="group",
        showlegend=False,
    )
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True}, style={"height": "100px"})


# ═══════════════════════════════════════════════════════════════════════════════
# TEAR SHEET SECTION RENDERERS (scoring-driven)
# ═══════════════════════════════════════════════════════════════════════════════

def render_tear_sheet_body(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    town_pulse_filter: str = "all",
) -> html.Div:
    """Simplified property analysis page — four core elements + drill-down."""
    summary_layer = render_property_decision_summary(view, report)
    economics_metrics = _economics_inputs(report, view)
    price_answer, price_summary, _price_label = _price_answer(view)
    economics_answer, economics_summary = _economics_answer(view, report)
    forward_answer, forward_summary = _forward_answer(view)
    risk_answer, _ = _risk_answer(view)
    optionality_answer, optionality_summary = _optionality_answer(view)

    auto_open = get_smart_defaults(view)

    # ── Detail sections (all live behind "See More") ──────────────────────
    price_section = _question_section(
        "Is the Price Right?",
        price_answer,
        section_id="tear-price",
        confidence=_section_confidence(view, "price"),
        default_open="tear-price" in auto_open,
        insight_callout=_price_insight(view, report),
        summary=price_summary or "Briarwood compares the ask against current value support, comp positioning, basis, and net opportunity delta.",
        metrics_strip=inline_metric_strip([
            ("Ask", _fmt_compact(view.ask_price), None),
            ("Fair Value", _fmt_compact(view.bcv), gap_pct_text(view) if view.mispricing_pct is not None else None),
            ("Base", _fmt_compact(view.base_case), None),
            ("Basis", _fmt_compact(view.all_in_basis), _capex_basis_source_label(view.capex_basis_source)),
        ]),
        chart=render_comp_positioning_chart(build_comp_positioning_chart_data(view, report)),
        extra_content=html.Div(
            [block for block in [
                _net_opportunity_delta_block(view),
                _active_listing_block(view),
                _town_context_block(view),
            ] if block is not None],
            style={"display": "grid", "gap": "8px"},
        ),
    )
    _investor_metrics = [
        m for m in [
            ("Debt Coverage", view.income_support.dscr_text, _dscr_tone_label(view.income_support.dscr)) if view.income_support.dscr is not None else None,
            ("Cash Return", view.income_support.cash_on_cash_return_text, None) if view.income_support.cash_on_cash_return is not None else None,
            ("Rental Yield", view.income_support.gross_yield_text, None) if view.income_support.gross_yield is not None else None,
        ] if m is not None
    ]
    _investor_strip = inline_metric_strip(_investor_metrics) if _investor_metrics else None
    _rent_sublabel = view.income_support.rent_source_label or view.income_support.rent_source_type
    economics_extra_blocks = [
        _economics_summary_box(view, report),
        _investor_strip,
        _unit_breakdown_block(view),
    ]
    economics_section = _question_section(
        "What Does It Cost to Own?",
        economics_answer,
        section_id="tear-economics",
        confidence=_section_confidence(view, "economics"),
        default_open="tear-economics" in auto_open,
        insight_callout=_economics_insight(view, report),
        summary=economics_summary,
        metrics_strip=inline_metric_strip([
            ("Rent", view.income_support.total_rent_text, _rent_sublabel),
            ("Price to Rent", view.income_support.price_to_rent_text, None),
            ("Cash Flow", view.income_support.monthly_cash_flow_text, None),
            ("Rental Ease", view.income_support.rental_ease_label, None),
        ]),
        chart=render_financial_chart(build_financial_chart_data(view, report)),
        extra_content=html.Div(
            [block for block in economics_extra_blocks if block is not None],
            style={"display": "grid", "gap": "8px"},
        ),
    )
    forward_section = _question_section(
        "What Does the Forward Look Like?",
        forward_answer,
        section_id="tear-forward",
        confidence=_section_confidence(view, "forward"),
        default_open="tear-forward" in auto_open,
        insight_callout=_forward_insight(view),
        summary=forward_summary,
        metrics_strip=inline_metric_strip([
            ("Downside", view.forward.bear_value_text, view.forward.downside_pct_text),
            ("Base", view.forward.base_value_text, None),
            ("Upside", view.forward.bull_value_text, view.forward.upside_pct_text),
            ("Stress", view.forward.stress_case_value_text, "optional") if view.stress_case is not None else ("Confidence", f"{_section_confidence(view, 'forward'):.0%}", None),
        ]),
        chart=None,
        extra_content=_scenario_skew_summary(view),
    )
    risk_section = _question_section(
        "What Could Break the Thesis?",
        risk_answer,
        section_id="tear-risk",
        confidence=_section_confidence(view, "risk"),
        default_open="tear-risk" in auto_open,
        insight_callout=_risk_insight(view),
        summary="Risk combines valuation cushion, execution burden, exit liquidity, income support, and market backdrop.",
        metrics_strip=inline_metric_strip([m for m in [
            ("Risk Score", f"{view.risk_location.risk_score:.0f}", None),
            ("Liquidity", f"{view.risk_location.liquidity_score:.0f}/100", view.risk_location.liquidity_label),
            ("Momentum", f"{view.risk_location.market_momentum_score:.0f}/100", _momentum_direction_label(view.risk_location)),
            ("Flood", view.risk_location.flood_risk.title(), None),
            ("Stress Case", view.risk_location.stress_case_text, f"-{view.risk_location.stress_drawdown_pct:.0%} drawdown" if view.risk_location.stress_drawdown_pct else None) if view.risk_location.stress_case_value is not None else None,
        ] if m is not None]),
        chart=None,
        extra_content=html.Div(
            [block for block in [
                _risk_list_block(view),
            ] if block is not None],
            style={"display": "grid", "gap": "8px"},
        ),
    )
    optionality_section = _question_section(
        "Where's the Upside?",
        optionality_answer,
        section_id="tear-optionality",
        confidence=_section_confidence(view, "optionality"),
        default_open="tear-optionality" in auto_open,
        insight_callout=_optionality_insight(view, report),
        summary=optionality_summary,
        metrics_strip=inline_metric_strip([
            ("Condition", view.condition_profile, None),
            ("CapEx Lane", view.capex_lane, None),
            ("Net Delta", _fmt_signed_currency(view.net_opportunity_delta_value), _fmt_signed_pct(view.net_opportunity_delta_pct)),
            ("Fit", _fit_label(view).replace("Best suited for ", "").replace("Most compelling as ", ""), None),
        ]),
        extra_content=html.Div(
            [
                _optionality_fact_block(view),
                _scarcity_breakdown_strip(view),
            ],
            style={"display": "grid", "gap": "8px"},
        ),
    )
    market_section = render_category_section_v2(
        "MARKET POSITION", "market_position", view, report,
        metrics_strip=inline_metric_strip([
            ("Town", f"{view.risk_location.town_score:.0f}", view.risk_location.town_label.replace("_", " ").title()),
            ("Momentum", f"{view.risk_location.market_momentum_score:.0f}/100", view.risk_location.market_momentum_label),
            ("Scarcity", f"{view.risk_location.scarcity_score:.0f}", None),
            ("Liquidity", f"{view.risk_location.liquidity_score:.0f}/100", view.risk_location.liquidity_label),
        ]),
        chart=None,
        extra_content=html.Div(
            [
                _town_pulse_block(view, signal_filter=town_pulse_filter),
                html.Div([html.Span("Demand Drivers", style=SECTION_HEADER_STYLE), html.Ul([html.Li(d, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for d in view.risk_location.drivers[:4]], style={"margin": "4px 0", "paddingLeft": "16px"})], style={"flex": "1"}),
                html.Div([html.Span("Location Risks", style=SECTION_HEADER_STYLE), html.Ul([html.Li(r, style={"fontSize": "11px", "color": TONE_WARNING_TEXT}) for r in view.risk_location.risks[:4]], style={"margin": "4px 0", "paddingLeft": "16px"})], style={"flex": "1"}),
            ],
            style={"display": "flex", "gap": "16px", "marginTop": "8px"},
        ) if (view.risk_location.town_pulse is not None or view.risk_location.drivers or view.risk_location.risks) else None,
        default_open=False,
    )
    # Evidence section — comp tables and diagnostics relocated here
    evidence_section = _question_section(
        "How Strong Is the Evidence?",
        f"Overall confidence is {view.overall_confidence:.0%}.",
        section_id="tear-evidence",
        confidence=_section_confidence(view, "evidence"),
        default_open=False,
        summary="Sourced facts, user-confirmed inputs, estimated assumptions, and unresolved gaps.",
        metrics_strip=_evidence_summary_strip(view),
        extra_content=html.Div(
            [block for block in [
                improve_analysis_block(view),
                compact_assumption_summary_block(view),
                _comp_review_block(view),
                assumptions_transparency_block(view),
                metric_input_status_block(view),
            ] if block is not None],
            style={"display": "grid", "gap": "8px"},
        ),
    )

    owner_page = _premium_owner_page(
        view,
        report,
        town_pulse_filter=town_pulse_filter,
        risk_section=risk_section,
        optionality_section=optionality_section,
        evidence_section=evidence_section,
        report_card_block=_report_card_block(view),
        price_section=price_section,
        economics_section=economics_section,
        forward_section=forward_section,
        market_section=market_section,
    )
    return html.Div(
        [
            summary_layer,
            owner_page,
        ],
        style={"padding": "16px 20px", "maxWidth": "1100px"},
    )


def gap_pct_text(view: PropertyAnalysisView) -> str:
    if view.mispricing_pct is None:
        return ""
    sign = "+" if view.mispricing_pct >= 0 else ""
    return f"{sign}{view.mispricing_pct * 100:.1f}%"


def _dscr_tone_label(dscr: float | None) -> str | None:
    """DSCR color-coded sublabel: green ≥1.25, yellow 1.0–1.25, red <1.0."""
    if dscr is None:
        return None
    if dscr >= 1.25:
        return "+covers debt"
    if dscr >= 1.0:
        return "borderline"
    return "-below debt service"


def _momentum_direction_label(rl: object) -> str:
    """Combine momentum label with directional arrow from momentum_direction."""
    label = getattr(rl, "market_momentum_label", "Unknown")
    direction = getattr(rl, "momentum_direction", "")
    arrow = {"accelerating": "↑", "steady": "→", "decelerating": "↓"}.get(direction, "")
    return f"{arrow} {label}" if arrow else label


def _location_context_chips(view: PropertyAnalysisView) -> html.Div | None:
    """School signal badge + coastal profile tag — only shown when data exists."""
    chips: list[html.Span] = []
    rl = view.risk_location
    if rl.location_support_label:
        tone = "positive" if rl.location_support_label == "Geo-Benchmarked" else "warning" if "Missing" in rl.location_support_label else "neutral"
        chips.append(compact_badge("Location Support", rl.location_support_label, tone=tone))
    if rl.school_signal is not None and rl.school_signal_text:
        tone = "positive" if rl.school_signal >= 7 else "warning" if rl.school_signal >= 5 else "negative"
        chips.append(compact_badge("School Quality", rl.school_signal_text, tone=tone))
    if rl.coastal_profile_label:
        chips.append(compact_badge("Location", rl.coastal_profile_label, tone="positive"))
    if not chips and not rl.location_anchor_summary:
        return None
    children: list[object] = [
        html.Span("LOCATION CONTEXT", style={**SECTION_HEADER_STYLE, "fontSize": "10px", "marginBottom": "4px"})
    ] + chips
    if rl.location_anchor_summary:
        children.append(
            html.Div(
                rl.location_anchor_summary,
                style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "width": "100%"},
            )
        )
    return html.Div(
        children,
        style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "alignItems": "center"},
    )


def _ptr_benchmark_label(view: PropertyAnalysisView) -> str | None:
    """PTR benchmark sublabel: 'Good (avg 15x)' or 'High (avg 15x, +35%)'."""
    ptr_raw = view.compare_metrics.get("price_to_rent")
    if not isinstance(ptr_raw, (int, float)) or ptr_raw <= 0:
        return view.income_support.ptr_classification
    ctx = _benchmark_context(ptr_raw, "ptr")
    if ctx is None:
        return view.income_support.ptr_classification
    classification = view.income_support.ptr_classification or ""
    return f"{classification} (mkt {ctx})" if classification else f"mkt {ctx}"


def _cash_flow_benchmark_label(view: PropertyAnalysisView) -> str | None:
    """Cash flow benchmark sublabel."""
    cf_raw = _parse_currency_text(view.income_support.monthly_cash_flow_text)
    if cf_raw is None:
        return None
    ctx = _benchmark_context(cf_raw, "cash_flow")
    return f"mkt {ctx}" if ctx else None


def _render_forward_scenarios(view: PropertyAnalysisView) -> html.Div:
    """Compact scenario range section."""
    metric_rows = [
        {"Metric": "Downside", "Value": view.forward.bear_value_text, "vs Ask": view.forward.downside_pct_text},
        {"Metric": "Base", "Value": view.forward.base_value_text, "vs Ask": "—"},
        {"Metric": "Upside", "Value": view.forward.bull_value_text, "vs Ask": view.forward.upside_pct_text},
    ]
    if view.stress_case is not None:
        metric_rows.insert(0, {"Metric": "Stress", "Value": view.forward.stress_case_value_text, "vs Ask": "Tail risk"})

    return html.Div(
        [
            html.Div("SCENARIO RANGE", style=SECTION_HEADER_STYLE),
            simple_table(metric_rows, page_size=6),
            html.Div(
                [
                    html.Span("Drivers: ", style={"fontWeight": "500", "fontSize": "11px"}),
                    html.Span(
                        f"Drift {view.forward.market_drift_text} | Loc {view.forward.location_premium_text} | Risk {view.forward.risk_discount_text} | Opt {view.forward.optionality_premium_text}",
                        style={"fontSize": "11px", "color": TEXT_MUTED},
                    ),
                ],
                style={"marginTop": "6px"},
            ),
        ],
        style={"marginBottom": "20px"},
    )


def _render_evidence_footer(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Compact evidence/confidence footer."""
    sourced = len(view.evidence.sourced_inputs)
    estimated = len(view.evidence.estimated_inputs)
    missing = len(view.evidence.missing_inputs)

    return html.Div(
        [
            html.Div(
                [
                    html.Span("EVIDENCE & CONFIDENCE", style=SECTION_HEADER_STYLE),
                    html.Div(
                        [
                            compact_badge("Mode", view.evidence.evidence_mode),
                            compact_badge("Sourced", str(sourced), tone="positive" if sourced > 5 else "neutral"),
                            compact_badge("Estimated", str(estimated), tone="warning" if estimated > 0 else "neutral"),
                            compact_badge("Missing", str(missing), tone="negative" if missing > 0 else "neutral"),
                        ],
                        style={"display": "flex", "gap": "6px", "flexWrap": "wrap"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "8px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Confidence Drivers", style=SECTION_HEADER_STYLE),
                            html.Div(
                                "Overall confidence is a weighted blend of Rent 30%, CapEx 25%, Market 25%, and Liquidity 20%.",
                                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "8px"},
                            ),
                            confidence_component_bars(view),
                        ],
                        style={"flex": "1"},
                    ),
                    html.Div(
                        [
                            html.Div("Section Confidence", style=SECTION_HEADER_STYLE),
                            confidence_progress_bars(view),
                        ],
                        style={"flex": "1"},
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "alignItems": "start"},
            ),
            assumptions_transparency_block(view),
            metric_input_status_block(view),
            html.Div(
                [
                    html.Div("Where Confidence Is Thin", style=SECTION_HEADER_STYLE),
                    html.Ul(
                        [html.Li(note, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for note in view.evidence.confidence_notes],
                        style={"margin": "4px 0 0 0", "paddingLeft": "16px"},
                    ),
                ],
                style={**CARD_STYLE, "padding": "8px 10px", "marginTop": "8px"},
            ) if view.evidence.confidence_notes else None,
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Missing Inputs", style={**LABEL_STYLE, "color": TONE_NEGATIVE_TEXT}),
                            html.Div(", ".join(view.evidence.missing_inputs[:6]) or "None", style={"fontSize": "11px", "color": TEXT_MUTED}),
                        ],
                        style={"flex": "1"},
                    ) if missing > 0 else None,
                    html.Div(
                        [
                            html.Div("Estimated Inputs", style={**LABEL_STYLE, "color": TONE_WARNING_TEXT}),
                            html.Div(", ".join(view.evidence.estimated_inputs[:6]) or "None", style={"fontSize": "11px", "color": TEXT_MUTED}),
                        ],
                        style={"flex": "1"},
                    ) if estimated > 0 else None,
                ],
                style={"display": "flex", "gap": "12px", "marginTop": "6px"},
            ) if (missing > 0 or estimated > 0) else None,
            # Defaults transparency
            _render_defaults_applied(view),
        ],
        style={"marginTop": "24px", "paddingTop": "12px", "borderTop": f"1px solid {BORDER}"},
    )


def _render_defaults_applied(view: PropertyAnalysisView) -> html.Div | None:
    """Show which smart defaults were applied to this property."""
    if not view.defaults_applied:
        return None

    rows = []
    for field_name, description in view.defaults_applied.items():
        label = field_name.replace("_", " ").title()
        rows.append(
            html.Div(
                [
                    html.Span(f"{label}: ", style={"fontWeight": "500", "color": TEXT_SECONDARY, "fontSize": "11px"}),
                    html.Span(description, style={"color": TEXT_MUTED, "fontSize": "11px"}),
                ],
                style={"marginBottom": "2px"},
            )
        )

    geocode_note = None
    if view.geocoded:
        geocode_note = html.Div(
            [
                html.Span("Geocoded: ", style={"fontWeight": "500", "color": TEXT_SECONDARY, "fontSize": "11px"}),
                html.Span("lat/lon populated from address via Nominatim", style={"color": TEXT_MUTED, "fontSize": "11px"}),
            ],
            style={"marginBottom": "2px"},
        )

    return html.Div(
        [
            html.Div(
                [
                    html.Div("SMART DEFAULTS APPLIED", style={**SECTION_HEADER_STYLE, "color": TONE_WARNING_TEXT}),
                    html.Div(
                        f"{len(view.defaults_applied)} fields auto-filled. Override in Add Property form if you have actual values.",
                        style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "6px"},
                    ),
                ],
            ),
            *rows,
            geocode_note,
        ],
        style={**CARD_STYLE, "padding": "8px 10px", "marginTop": "8px", "borderColor": TONE_WARNING_BG},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WHAT-IF ASK PRICE SLIDER
# ═══════════════════════════════════════════════════════════════════════════════


def render_what_if_metrics(view: PropertyAnalysisView, adjusted_ask: float, rate: float = 7.0, vacancy: float = 0.05) -> html.Div:
    """Render recalculated metrics for a given adjusted ask price, rate, and vacancy."""
    original_ask = view.ask_price or adjusted_ask
    bcv = view.bcv or original_ask
    default_rate = 7.0
    default_vacancy = 0.15 if view.risk_location.coastal_profile_label else 0.05

    # BCV gap
    gap_orig = ((bcv - original_ask) / original_ask * 100) if original_ask > 0 else 0
    gap_adj = ((bcv - adjusted_ask) / adjusted_ask * 100) if adjusted_ask > 0 else 0

    # PTR (uses effective rent after vacancy)
    rent_raw = _parse_currency_text(view.income_support.total_rent_text)
    eff_rent = (rent_raw or 0) * (1 - vacancy)
    eff_rent_orig = (rent_raw or 0) * (1 - default_vacancy)
    annual_rent = eff_rent * 12
    annual_rent_orig = eff_rent_orig * 12
    ptr_orig = (original_ask / annual_rent_orig) if annual_rent_orig > 0 else 0
    ptr_adj = (adjusted_ask / annual_rent) if annual_rent > 0 else 0

    # Monthly mortgage at adjusted rate
    loan = adjusted_ask * 0.80
    r_adj = rate / 100 / 12
    n = 360
    pmt_adj = (loan * r_adj * (1 + r_adj) ** n / ((1 + r_adj) ** n - 1)) if r_adj > 0 else loan / n

    # Monthly mortgage at default rate (for comparison)
    loan_orig = original_ask * 0.80
    r_def = default_rate / 100 / 12
    pmt_orig = (loan_orig * r_def * (1 + r_def) ** n / ((1 + r_def) ** n - 1)) if r_def > 0 else loan_orig / n

    # Cash flow
    cf_adj = eff_rent - pmt_adj
    cf_orig = eff_rent_orig - pmt_orig

    # Price delta from original
    delta = adjusted_ask - original_ask
    delta_pct = (delta / original_ask * 100) if original_ask > 0 else 0

    # Rate delta
    rate_delta = rate - default_rate

    def _card(label: str, value: str, *, tone: str = "neutral", sublabel: str = "") -> html.Div:
        color = TONE_POSITIVE_TEXT if tone == "positive" else TONE_NEGATIVE_TEXT if tone == "negative" else TEXT_PRIMARY
        children = [
            html.Div(label, style={"fontSize": "11px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "2px"}),
            html.Div(value, style={"fontSize": "16px", "fontWeight": "700", "color": color}),
        ]
        if sublabel:
            children.append(html.Div(sublabel, style={"fontSize": "10px", "color": TEXT_MUTED, "marginTop": "2px"}))
        return html.Div(
            children,
            style={"padding": "10px", "backgroundColor": BG_SURFACE_2, "borderRadius": "4px", "border": f"1px solid {BORDER}"},
        )

    gap_tone = "positive" if gap_adj > gap_orig else "negative" if gap_adj < gap_orig else "neutral"
    ptr_tone = "positive" if ptr_adj < ptr_orig else "negative" if ptr_adj > ptr_orig else "neutral"
    cf_tone = "positive" if cf_adj > 0 else "negative"
    pmt_tone = "positive" if pmt_adj < pmt_orig else "negative" if pmt_adj > pmt_orig else "neutral"

    # Summary line
    summary_parts = [f"${adjusted_ask:,.0f}"]
    if abs(delta_pct) > 0.1:
        summary_parts.append(f"({delta_pct:+.1f}% vs ask)")
    summary_parts.append(f"@ {rate:.2f}%")
    if abs(rate_delta) > 0.01:
        summary_parts.append(f"({rate_delta:+.2f}%)")

    return html.Div(
        [
            html.Div(
                "  ".join(summary_parts),
                style={"fontSize": "18px", "fontWeight": "700", "textAlign": "center", "marginBottom": "12px", "color": TEXT_PRIMARY},
            ),
            html.Div(
                [
                    _card("BCV Gap", f"{gap_adj:+.1f}%", tone=gap_tone, sublabel=f"was {gap_orig:+.1f}%" if abs(gap_adj - gap_orig) > 0.1 else ""),
                    _card("Price to Rent", f"{ptr_adj:.1f}x", tone=ptr_tone, sublabel=f"was {ptr_orig:.1f}x" if abs(ptr_adj - ptr_orig) > 0.1 else ""),
                    _card("Est. Mortgage", f"${pmt_adj:,.0f}/mo", tone=pmt_tone, sublabel=f"was ${pmt_orig:,.0f}/mo" if abs(pmt_adj - pmt_orig) > 10 else ""),
                    _card("Est. Cash Flow", f"${cf_adj:,.0f}/mo", tone=cf_tone, sublabel=f"was ${cf_orig:,.0f}/mo" if abs(cf_adj - cf_orig) > 10 else ""),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(2, 1fr)", "gap": "8px"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════


def render_portfolio_dashboard(views: list[PropertyAnalysisView]) -> html.Div:
    """Portfolio-level aggregate dashboard across all analyzed properties."""
    if not views:
        return html.Div("No properties loaded. Add or select properties to view portfolio summary.", style={"padding": "40px", "color": TEXT_MUTED})

    scored = [v for v in views if v.final_score is not None]
    total = len(views)
    avg_score = sum(v.final_score for v in scored) / len(scored) if scored else 0
    total_value = sum(v.ask_price or 0 for v in views)
    buys = sum(1 for v in scored if (v.final_score or 0) >= 3.30)

    # Summary cards
    def _stat(icon: str, value: str, label: str) -> html.Div:
        return html.Div(
            [
                html.Div(icon, style={"fontSize": "22px", "marginBottom": "6px"}),
                html.Div(value, style={"fontSize": "24px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                html.Div(label, style={"fontSize": "12px", "color": TEXT_MUTED}),
            ],
            style={**CARD_STYLE, "padding": "16px 20px", "textAlign": "center"},
        )

    summary_row = html.Div(
        [
            _stat("📊", str(total), "Properties"),
            _stat("⭐", f"{avg_score:.2f}/5", "Avg Score"),
            _stat("💰", f"${total_value / 1_000_000:.1f}M", "Total Value"),
            _stat("●", str(buys), "Buys"),
        ],
        style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "12px", "marginBottom": "24px"},
    )

    # Rankings table
    ranked = sorted(scored, key=lambda v: v.final_score or 0, reverse=True)
    rank_rows = []
    for i, v in enumerate(ranked):
        sc = score_color(v.final_score)
        sl = score_label(v.final_score)
        ls = v.lens_scores
        best = ls.recommended_lens if ls else ""
        lens_name, _icon = _LENS_DISPLAY.get(best, (best.replace("_", " ").title(), ""))
        vc = verdict_color(v.recommendation_tier or "")
        rank_rows.append(
            html.Tr(
                [
                    html.Td(f"#{i + 1}", style={"padding": "10px 8px", "fontSize": "13px", "color": TEXT_MUTED}),
                    html.Td(v.address, style={"padding": "10px 8px", "fontSize": "13px", "fontWeight": "600"}),
                    html.Td(_fmt_compact(v.ask_price), style={"padding": "10px 8px", "fontSize": "13px"}),
                    html.Td(
                        [html.Span(f"{v.final_score:.2f}", style={"fontWeight": "700", "color": sc}), html.Span(f" {sl}", style={"fontSize": "11px", "color": sc, "marginLeft": "4px"})],
                        style={"padding": "10px 8px"},
                    ),
                    html.Td(lens_name, style={"padding": "10px 8px", "fontSize": "13px"}),
                    html.Td(v.recommendation_tier or "—", style={"padding": "10px 8px", "fontSize": "13px", "fontWeight": "600", "color": vc}),
                ],
                style={"borderBottom": f"1px solid {BORDER_SUBTLE}", "backgroundColor": BG_SURFACE if i % 2 == 0 else BG_BASE},
            )
        )

    rankings = html.Div(
        [
            html.Div("PROPERTY RANKINGS", style=SECTION_HEADER_STYLE),
            html.Table(
                [
                    html.Thead(html.Tr([
                        html.Th(col, style={"padding": "10px 8px", "fontSize": "11px", "fontWeight": "600", "color": TEXT_MUTED, "textTransform": "uppercase", "textAlign": "left", "borderBottom": f"2px solid {BORDER}"})
                        for col in ["Rank", "Property", "Ask", "Score", "Best For", "Verdict"]
                    ])),
                    html.Tbody(rank_rows),
                ],
                style={"width": "100%", "borderCollapse": "collapse"},
            ),
        ],
        style={**CARD_STYLE, "padding": "16px 20px", "marginBottom": "24px"},
    )

    return html.Div(
        [
            html.Div("PORTFOLIO DASHBOARD", style={"fontSize": "20px", "fontWeight": "700", "color": TEXT_PRIMARY, "marginBottom": "20px"}),
            summary_row,
            rankings,
        ],
        style={"padding": "20px 24px", "maxWidth": "1200px"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY SECTION RENDERERS (for compare view backwards compat)
# ═══════════════════════════════════════════════════════════════════════════════


def render_overview_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            html.Div(_summary_verdict(view), style={"fontSize": "14px" if compact else "16px", "fontWeight": "600", "marginBottom": "4px"}),
            html.Div(view.memo_summary, style=BODY_TEXT_STYLE),
            inline_metric_strip([
                ("Ask", _fmt_compact(view.ask_price), None),
                ("Fair Value", _fmt_compact(view.bcv), gap_pct_text(view) or None),
                ("Base", _fmt_compact(view.base_case), None),
                ("Risk", _primary_risk_text(view), None),
            ]),
        ],
        style=CARD_STYLE,
    )


def render_value_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    comps_sublabel = "hybrid" if view.comps.is_hybrid_valuation else None
    return html.Div(
        [
            inline_metric_strip([
                ("Pricing", view.pricing_view.title(), None),
                ("Net Delta", _fmt_signed_currency(view.net_opportunity_delta_value), _fmt_signed_pct(view.net_opportunity_delta_pct) if view.net_opportunity_delta_pct is not None else None),
                ("Basis", _fmt_compact(view.all_in_basis), _capex_basis_source_label(view.capex_basis_source)),
                ("Confidence", f"{view.value.confidence:.0%}", None),
                ("Comps", view.comps.comparable_value_text, comps_sublabel),
            ]),
            _net_opportunity_delta_block(view),
            _comp_review_block(view),
        ],
        style={"display": "grid", "gap": "8px"},
    )


def render_forward_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    del compact
    return html.Div(
        [
            inline_metric_strip([
                ("Downside", view.forward.bear_value_text, view.forward.downside_pct_text),
                ("Base", view.forward.base_value_text, None),
                ("Upside", view.forward.bull_value_text, view.forward.upside_pct_text),
            ]),
            html.Div(_scenario_skew_summary(view), style={"fontSize": "12px", "color": TEXT_SECONDARY}),
        ],
        style={"display": "grid", "gap": "8px"},
    )


def render_risk_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            inline_metric_strip([("Risk Score", f"{view.risk_location.risk_score:.0f}", None), ("Flood", view.risk_location.flood_risk.title(), None), ("Liquidity", view.risk_location.liquidity_view.title(), None)]),
            inline_metric_strip([("Exit Liquidity", f"{view.risk_location.liquidity_score:.0f}/100", view.risk_location.liquidity_label)]),
            html.Div(view.risk_location.risk_summary, style=BODY_TEXT_STYLE),
            risk_breakdown_bars(view),
        ],
        style={"display": "grid", "gap": "8px"},
    )


def render_location_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            inline_metric_strip([("Town", f"{view.risk_location.town_score:.0f}", view.risk_location.town_label.replace("_", " ").title()), ("Momentum", f"{view.risk_location.market_momentum_score:.0f}/100", view.risk_location.market_momentum_label), ("Scarcity", f"{view.risk_location.scarcity_score:.0f}", None), ("Liquidity", f"{view.risk_location.liquidity_score:.0f}/100", view.risk_location.liquidity_label)]),
            _town_pulse_block(view),
            html.Div(
                [
                    html.Ul([html.Li(d, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for d in view.risk_location.drivers[:4]], style={"margin": "0", "paddingLeft": "16px"}),
                ],
            ) if view.risk_location.drivers else None,
        ],
        style={"display": "grid", "gap": "8px"},
    )


def _town_pulse_block(view: PropertyAnalysisView, signal_filter: str = "all") -> html.Div | None:
    pulse = view.risk_location.town_pulse
    if pulse is None or not pulse.key_signals:
        return None
    signal_groups = {
        "all": pulse.key_signals[:4],
        "bullish": pulse.bullish_signals[:4],
        "bearish": pulse.bearish_signals[:4],
        "watch": pulse.watch_items[:4],
    }
    active_signals = signal_groups.get(signal_filter, pulse.key_signals[:4])
    rows = [_town_pulse_signal_row(item) for item in active_signals]
    filter_label = {
        "all": "All signals",
        "bullish": "Catalysts",
        "bearish": "Risks",
        "watch": "Watch items",
    }.get(signal_filter, "All signals")
    return html.Div(
        [
            html.Div(
                [
                    html.Div(pulse.section_title, style=SECTION_HEADER_STYLE),
                    html.Div(
                        [
                            html.Span(filter_label, style=tone_badge_style("neutral")),
                            html.Span(
                                pulse.confidence_label,
                                style=tone_badge_style(
                                    "positive" if pulse.confidence_label == "High" else
                                    "warning" if pulse.confidence_label == "Medium" else
                                    "negative"
                                ),
                            ),
                        ],
                        style={"display": "flex", "gap": "6px", "alignItems": "center"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "gap": "12px", "alignItems": "start"},
            ),
            html.Div(
                "What is changing in this town that comps and listing data may not fully reflect yet.",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "-2px"},
            ),
            html.Div(
                [
                    html.Span("Click the sentiment chart to filter these rows.", style={"fontSize": "11px", "color": TEXT_MUTED}),
                    html.Button(
                        "Clear",
                        id="town-pulse-clear-filter",
                        n_clicks=0,
                        style={
                            "border": f"1px solid {BORDER_SUBTLE}",
                            "backgroundColor": BG_SURFACE_2,
                            "color": TEXT_SECONDARY,
                            "fontSize": "11px",
                            "padding": "4px 8px",
                            "borderRadius": "999px",
                            "cursor": "pointer",
                        },
                    ) if signal_filter != "all" else None,
                ],
                style={"display": "flex", "gap": "8px", "alignItems": "center", "marginTop": "2px"},
            ),
            html.Div(pulse.narrative_summary, style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY}),
            html.Div(
                rows if rows else [
                    html.Div(
                        f"No {filter_label.lower()} are currently available for this town.",
                        style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_MUTED},
                    )
                ],
                style={"display": "grid", "gap": "8px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "12px 14px"},
    )


def _town_pulse_signal_row(item: object) -> html.Details:
    tone = getattr(item, "tone", "warning")
    tag_style = tone_badge_style(tone)
    evidence = getattr(item, "evidence_excerpt", "")
    source_type = getattr(item, "source_type", "")
    source_date_text = getattr(item, "source_date_text", "")
    source_url = getattr(item, "source_url", None)
    reconciliation_tag = getattr(item, "reconciliation_tag", None)
    return html.Details(
        [
            html.Summary(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(getattr(item, "title", "Town signal"), style={"fontSize": "13px", "fontWeight": "700", "color": TEXT_PRIMARY, "lineHeight": "1.35"}),
                                html.Div(getattr(item, "description", ""), style={"fontSize": "11px", "color": TEXT_SECONDARY, "lineHeight": "1.5", "marginTop": "3px"}),
                            ],
                            style={"minWidth": "0"},
                        ),
                        html.Div(
                            [
                                html.Span(getattr(item, "status_tag", "Watch"), style=tag_style),
                                html.Span(getattr(item, "confidence_tag", "Low"), style=tone_badge_style("neutral")),
                                html.Span(reconciliation_tag, style=tone_badge_style("warning")) if reconciliation_tag else None,
                            ],
                            style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "justifyContent": "end"},
                        ),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "minmax(0, 1fr) auto", "gap": "10px", "alignItems": "start"},
                ),
                style={"cursor": "pointer", "listStyle": "none"},
            ),
            html.Div(
                [
                    html.Div("Evidence", style={"fontSize": "10px", "fontWeight": "700", "letterSpacing": "0.08em", "textTransform": "uppercase", "color": TEXT_MUTED}),
                    html.Div(evidence, style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "4px"}),
                    html.Div(
                        [
                            html.Span(f"Source: {source_type}", style={"fontSize": "10px", "color": TEXT_MUTED}),
                            html.Span(f" | {source_date_text}", style={"fontSize": "10px", "color": TEXT_MUTED}) if source_date_text else None,
                            html.A(" | Open source", href=source_url, target="_blank", rel="noreferrer", style={"fontSize": "10px", "color": ACCENT_BLUE, "textDecoration": "none"}) if source_url else None,
                        ],
                        style={"marginTop": "6px"},
                    ) if source_type or source_date_text or source_url else None,
                ],
                style={"paddingTop": "8px"},
            ) if evidence else None,
        ],
        style={"border": f"1px solid {BORDER_SUBTLE}", "borderRadius": "10px", "padding": "10px 12px", "backgroundColor": BG_SURFACE_2},
    )


def render_income_support_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            inline_metric_strip([
                ("Total Rent", view.income_support.total_rent_text, view.income_support.rent_source_type),
                ("Price to Rent", view.income_support.price_to_rent_text, view.income_support.ptr_classification),
                ("Rental Ease", view.income_support.rental_ease_label, None),
                ("Rent Coverage", view.income_support.income_support_ratio_text, None),
                ("Cash Flow", view.income_support.monthly_cash_flow_text, None),
            ]),
            html.Div(view.income_support.summary, style=BODY_TEXT_STYLE),
            _unit_breakdown_block(view),
        ],
        style={"display": "grid", "gap": "8px"},
    )


def _unit_breakdown_block(view: PropertyAnalysisView) -> html.Div | None:
    if not view.income_support.unit_breakdown:
        return None
    rows = [
        html.Div(
            [
                html.Span(label, style={"fontSize": "11px", "color": TEXT_MUTED}),
                html.Span(value, style={"fontSize": "11px", "fontWeight": "600", "color": TEXT_PRIMARY}),
            ],
            style={"display": "flex", "justifyContent": "space-between", "padding": "4px 0", "borderBottom": f"1px solid {BORDER_SUBTLE}"},
        )
        for label, value in view.income_support.unit_breakdown
    ]
    header = inline_metric_strip(
        [
            ("Units", view.income_support.num_units_text, None),
            ("Avg / Unit", view.income_support.avg_rent_per_unit_text, None),
        ]
    )
    return html.Div(
        [
            html.Div("Unit Rent Breakdown", style=SECTION_HEADER_STYLE),
            header,
            html.Div(rows, style={"display": "grid", "gap": "0"}),
        ],
        style={**CARD_STYLE, "padding": "8px 10px"},
    )


def _net_opportunity_delta_block(view: PropertyAnalysisView) -> html.Div | None:
    if view.net_opportunity_delta_value is None:
        return None
    explanation = (
        f"Net Opportunity Delta = BCV {_fmt_compact(view.bcv)} minus all-in basis {_fmt_compact(view.all_in_basis)}."
    )
    capex_note = (
        f"CapEx basis used: {_fmt_compact(view.capex_basis_used)} ({_capex_basis_source_label(view.capex_basis_source)})."
        if view.capex_basis_used is not None
        else "CapEx basis could not be established cleanly, so delta should be treated cautiously."
    )
    return html.Div(
        [
            html.Div("Net Opportunity Delta", style=SECTION_HEADER_STYLE),
            inline_metric_strip(
                [
                    ("Delta", _fmt_signed_currency(view.net_opportunity_delta_value), _fmt_signed_pct(view.net_opportunity_delta_pct) if view.net_opportunity_delta_pct is not None else None),
                    ("Fair Value", _fmt_compact(view.bcv), None),
                    ("All-In Basis", _fmt_compact(view.all_in_basis), _capex_basis_source_label(view.capex_basis_source)),
                ]
            ),
            html.Div(explanation, style={"fontSize": "11px", "color": TEXT_SECONDARY, "marginTop": "2px"}),
            html.Div(capex_note, style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "4px"}),
        ],
        style={**CARD_STYLE, "marginTop": "8px"},
    )


def _value_finder_block(view: PropertyAnalysisView) -> html.Div | None:
    if view.value_finder is None:
        return None
    finder = view.value_finder
    if not finder.bullets:
        return None
    return html.Div(
        [
            html.Div("Value Finder", style=SECTION_HEADER_STYLE),
            html.Div(
                finder.supporting_signal,
                style={"fontSize": "11px", "fontWeight": "700", "letterSpacing": "0.06em", "textTransform": "uppercase", "color": TEXT_MUTED, "marginBottom": "8px"},
            ) if finder.supporting_signal else None,
            html.Ul(
                [
                    html.Li(
                        bullet,
                        style={"fontSize": "13px", "lineHeight": "1.55", "color": TEXT_PRIMARY, "marginBottom": "6px"},
                    )
                    for bullet in finder.bullets[:4]
                ],
                style={"margin": "0", "paddingLeft": "18px"},
            ),
            html.Div(
                finder.confidence_note,
                style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_MUTED, "marginTop": "8px"},
            ) if finder.confidence_note else None,
        ],
        style={**CARD_STYLE, "marginTop": "8px"},
    )


def _comp_thumb_slot(title: str, thumbnail_url: str | None, locality: str) -> html.Div:
    if thumbnail_url:
        return html.Div(
            html.Img(
                src=thumbnail_url,
                alt=title,
                style={"width": "100%", "height": "100%", "objectFit": "cover", "display": "block"},
            ),
            style={"width": "88px", "minWidth": "88px", "height": "72px", "borderRadius": "8px", "overflow": "hidden", "backgroundColor": BG_SURFACE_3, "border": f"1px solid {BORDER_SUBTLE}"},
        )
    return html.Div(
        [
            html.Div("Preview", style={"fontSize": "10px", "fontWeight": "700", "letterSpacing": "0.08em", "textTransform": "uppercase", "color": TEXT_MUTED}),
            html.Div(locality, style={"fontSize": "12px", "fontWeight": "600", "color": TEXT_SECONDARY, "lineHeight": "1.4", "marginTop": "6px"}),
        ],
        style={
            "width": "88px",
            "minWidth": "88px",
            "height": "72px",
            "borderRadius": "8px",
            "padding": "10px 8px",
            "background": f"linear-gradient(180deg, {BG_SURFACE_3} 0%, {BG_SURFACE_2} 100%)",
            "border": f"1px solid {BORDER_SUBTLE}",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "space-between",
        },
    )


def _comp_actions(google_maps_url: str, apple_maps_url: str, external_url: str | None, external_label: str) -> html.Div:
    links = [
        html.A("Google Maps", href=google_maps_url, target="_blank", rel="noreferrer", style={"fontSize": "11px", "fontWeight": "600", "color": ACCENT_BLUE, "textDecoration": "none"}),
        html.A("Apple Maps", href=apple_maps_url, target="_blank", rel="noreferrer", style={"fontSize": "11px", "color": TEXT_SECONDARY, "textDecoration": "none"}),
    ]
    if external_url:
        links.append(html.A(external_label, href=external_url, target="_blank", rel="noreferrer", style={"fontSize": "11px", "color": TEXT_SECONDARY, "textDecoration": "none"}))
    return html.Div(links, style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginTop": "8px"})


def _comp_card(row: object, *, listing: bool = False) -> html.Div:
    title = getattr(row, "street", None) or getattr(row, "address", "Unknown Address")
    locality = getattr(row, "locality", "Unknown Location")
    if listing:
        metrics = [
            ("List", getattr(row, "list_price", None) or "—", None),
            ("Status", getattr(row, "status", "—"), None),
            ("Condition", getattr(row, "condition", "—"), None),
            ("Days Listed", getattr(row, "dom", "—"), None),
            ("Layout", " / ".join(part for part in [getattr(row, "beds", ""), getattr(row, "baths", ""), getattr(row, "sqft", "")] if part and part != "Unavailable") or "—", None),
        ]
    else:
        metrics = [
            ("Sale", getattr(row, "sale_price", None) or "—", None),
            ("Adjusted", getattr(row, "adjusted_price", "—"), None),
            ("Fit", getattr(row, "fit", "—"), getattr(row, "verification", None)),
            ("Condition", getattr(row, "condition", "—"), getattr(row, "capex_lane", None)),
            ("Status", getattr(row, "status", "—"), None),
        ]

    detail = getattr(row, "why_comp", "") if not listing else f"Source ref: {getattr(row, 'source_ref', 'Unavailable')}"
    caution = getattr(row, "cautions", "") if not listing else ""

    return html.Div(
        [
            _comp_thumb_slot(title, getattr(row, "thumbnail_url", None), locality),
            html.Div(
                [
                    html.Div(locality, style={"fontSize": "11px", "fontWeight": "700", "letterSpacing": "0.08em", "textTransform": "uppercase", "color": ACCENT_BLUE}),
                    html.Div(title, style={"fontSize": "16px", "fontWeight": "700", "lineHeight": "1.35", "color": TEXT_PRIMARY, "marginTop": "2px"}),
                    inline_metric_strip(metrics),
                    html.Div(detail, style={"fontSize": "12px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginTop": "8px"}) if detail else None,
                    html.Div(caution, style={"fontSize": "11px", "lineHeight": "1.5", "color": TONE_WARNING_TEXT, "marginTop": "6px"}) if caution else None,
                    _comp_actions(
                        getattr(row, "google_maps_url", ""),
                        getattr(row, "apple_maps_url", ""),
                        getattr(row, "external_url", None),
                        "Open source" if listing else "Listing / source",
                    ),
                ],
                style={"minWidth": "0"},
            ),
        ],
        style={**CARD_STYLE, "padding": "12px 14px", "display": "grid", "gridTemplateColumns": "88px minmax(0, 1fr)", "gap": "12px", "alignItems": "start"},
    )


def _comp_review_block(view: PropertyAnalysisView) -> html.Div:
    rows = view.comps.rows
    if not rows:
        return html.Div("No comparable sales available.", style={"fontSize": "12px", "color": TEXT_MUTED})

    children: list = []

    # Hybrid valuation banner for multi-unit properties
    if view.comps.is_hybrid_valuation:
        unit_label = "unit" if view.comps.additional_unit_count == 1 else "units"
        children.append(
            html.Div("Hybrid Valuation — Multi-Unit Property", style=SECTION_HEADER_STYLE),
        )
        children.append(
            html.Div(
                "Briarwood comps the primary dwelling against single-family sales, then values additional rental units via income capitalization.",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "4px"},
            ),
        )
        children.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Primary Dwelling", style={"fontSize": "11px", "fontWeight": "600", "color": TEXT_SECONDARY}),
                            html.Div(view.comps.primary_dwelling_value_text, style={"fontSize": "16px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                            html.Div(f"Comped against {view.comps.comp_count_text} SFR sales", style={"fontSize": "10px", "color": TEXT_MUTED}),
                        ],
                        style={"flex": "1", "textAlign": "center", "padding": "8px"},
                    ),
                    html.Div("+", style={"fontSize": "20px", "fontWeight": "700", "color": TEXT_MUTED, "alignSelf": "center"}),
                    html.Div(
                        [
                            html.Div(f"{view.comps.additional_unit_count} Rental {unit_label.title()}", style={"fontSize": "11px", "fontWeight": "600", "color": TEXT_SECONDARY}),
                            html.Div(view.comps.additional_unit_income_value_text, style={"fontSize": "16px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                            html.Div(f"{view.comps.additional_unit_annual_income_text}/yr @ {view.comps.additional_unit_cap_rate_text} cap", style={"fontSize": "10px", "color": TEXT_MUTED}),
                        ],
                        style={"flex": "1", "textAlign": "center", "padding": "8px"},
                    ),
                    html.Div("=", style={"fontSize": "20px", "fontWeight": "700", "color": TEXT_MUTED, "alignSelf": "center"}),
                    html.Div(
                        [
                            html.Div("Combined Value", style={"fontSize": "11px", "fontWeight": "600", "color": TEXT_SECONDARY}),
                            html.Div(view.comps.comparable_value_text, style={"fontSize": "16px", "fontWeight": "700", "color": ACCENT_BLUE}),
                        ],
                        style={"flex": "1", "textAlign": "center", "padding": "8px"},
                    ),
                ],
                style={
                    "display": "flex",
                    "gap": "4px",
                    "alignItems": "center",
                    "backgroundColor": BG_SURFACE_2,
                    "borderRadius": "6px",
                    "padding": "6px 10px",
                    "marginBottom": "8px",
                },
            ),
        )
        children.append(
            html.Div("Primary Dwelling Comps", style=SECTION_HEADER_STYLE),
        )
    else:
        children.append(
            html.Div("Comparable Sales", style=SECTION_HEADER_STYLE),
        )

    children.append(
        html.Div(
            "Scan locality first, then sale and adjusted pricing, with direct map links for quick orientation.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "8px"},
        ),
    )
    children.append(
        html.Div([_comp_card(row) for row in rows], style={"display": "grid", "gap": "8px"}),
    )

    return html.Div(children, style={"display": "grid", "gap": "8px"})


def _active_listing_block(view: PropertyAnalysisView) -> html.Div | None:
    if not view.comps.active_listing_rows:
        return None
    return html.Div(
        [
            html.Div("Current Competition", style=SECTION_HEADER_STYLE),
            html.Div(
                f"{view.comps.active_listing_count_text} active listing(s) currently loaded for this market.",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "6px"},
            ),
            html.Div([_comp_card(row, listing=True) for row in view.comps.active_listing_rows], style={"display": "grid", "gap": "8px"}),
        ],
        style={**CARD_STYLE, "marginTop": "8px"},
    )


def render_evidence_section(report: AnalysisReport, view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    evidence_rows = build_evidence_rows(report)
    return html.Div(
        [
            inline_metric_strip([
                ("Mode", view.evidence.evidence_mode, None),
                ("Sourced", str(len(view.evidence.sourced_inputs)), None),
                ("Estimated", str(len(view.evidence.estimated_inputs)), None),
                ("Missing", str(len(view.evidence.missing_inputs)), None),
            ]),
            assumptions_transparency_block(view),
            metric_input_status_block(view),
            confidence_component_bars(view),
            confidence_progress_bars(view),
            simple_table(evidence_rows, page_size=10) if not compact else html.Div(),
        ],
        style={"display": "grid", "gap": "8px"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH (used by app.py for tear sheet and compare)
# ═══════════════════════════════════════════════════════════════════════════════


_SECTION_RENDERERS = {
    "overview": render_overview_section,
    "value": render_value_section,
    "forward": render_forward_section,
    "risk": render_risk_section,
    "location": render_location_section,
    "income": render_income_support_section,
}


def _render_section_content(section: str, view: PropertyAnalysisView, report: AnalysisReport, *, compact: bool):
    if section == "evidence":
        return render_evidence_section(report, view, compact=compact)
    if section == "data_quality":
        from briarwood.dash_app.data_quality import render_data_quality_section
        return render_data_quality_section(report)
    if section == "scenarios":
        from briarwood.dash_app.scenarios import render_scenarios_section
        return render_scenarios_section(report)
    return _SECTION_RENDERERS.get(section, render_overview_section)(view, compact=compact)


_COMPARE_SECTION_METRICS: dict[str, set[str]] = {
    "overview": {"Ask", "Fair Value", "FV Delta vs Ask", "Forward Base", "Confidence"},
    "value": {"Ask", "Fair Value", "FV Delta vs Ask", "FV Range", "Lot Size", "Sqft", "Taxes", "Confidence"},
    "forward": {"Forward Base", "FV Delta vs Ask", "Forward Gap", "Confidence"},
    "risk": {"Risk Score", "Days Listed", "Taxes"},
    "location": {"Town/County", "Scarcity"},
    "income": {"Income Support", "Price-to-Rent"},
    "evidence": {"Confidence"},
}


def render_compare_summary(section: str, summary: CompareSummary) -> html.Div | None:
    if not summary.rows:
        return None
    metric_filter = _COMPARE_SECTION_METRICS.get(section, set())
    filtered_rows = [row for row in summary.rows if row.metric in metric_filter]
    if not filtered_rows:
        return None
    comparison_block = _comparison_summary_block(summary)
    return html.Div(
        [
            comparison_block,
            html.Div([html.Div("Key Differences", style=SECTION_HEADER_STYLE), html.Ul([html.Li(item, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for item in summary.why_different[:4]])], style=CARD_STYLE),
            html.Div([html.Div("Compare", style=SECTION_HEADER_STYLE), _render_compare_table(filtered_rows)], style=CARD_STYLE),
        ],
        style={"display": "grid", "gap": "12px", "marginBottom": "12px"},
    )


def _comparison_summary_block(summary: CompareSummary) -> html.Div | None:
    if summary.comparison_summary is None:
        return None
    cs = summary.comparison_summary

    def _reason_list(title: str, items: list, tone_color: str) -> html.Div:
        return html.Div(
            [
                html.Div(title, style=SECTION_HEADER_STYLE),
                html.Ul(
                    [
                        html.Li(
                            f"{item.factor_name.replace('_', ' ').title()} ({item.weighted_delta_pct}%): {item.explanation}",
                            style={"fontSize": "11px", "lineHeight": "1.55", "color": tone_color},
                        )
                        for item in items
                    ] or [html.Li("No material edge identified.", style={"fontSize": "11px", "lineHeight": "1.55", "color": TEXT_MUTED})],
                    style={"margin": "4px 0 0 0", "paddingLeft": "16px"},
                ),
            ],
            style={**CARD_STYLE, "padding": "10px 12px"},
        )

    return html.Div(
        [
            html.Div("Why One Property Wins", style=SECTION_HEADER_STYLE),
            inline_metric_strip([
                ("Winner", cs.winner, None),
                ("Compare Confidence", f"{cs.confidence}/100", None),
                ("Flip Condition", cs.flip_condition, None),
            ]),
            html.Div(
                [
                    _reason_list("Reasons For Winner", cs.reasons_for_winner, TONE_POSITIVE_TEXT),
                    _reason_list("Strengths Of Loser", cs.strengths_of_loser, TONE_WARNING_TEXT),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px", "marginTop": "10px"},
            ),
        ],
        style={**CARD_STYLE_ELEVATED, "padding": "14px 16px"},
    )


def _render_compare_table(rows: list) -> html.Div:
    """Rich comparison table with relative deltas and winner-per-metric indicators."""
    if not rows:
        return html.Div("No metrics to compare.", style={"color": TEXT_MUTED, "fontSize": "13px"})

    # Get all property labels from the first row
    property_labels = list(rows[0].values.keys())

    # Build header
    header_cells = [html.Th("Metric", style={**TABLE_STYLE_HEADER, "textAlign": "left", "minWidth": "110px"})]
    for label in property_labels:
        header_cells.append(html.Th(label, style={**TABLE_STYLE_HEADER, "textAlign": "right", "minWidth": "120px"}))

    # Build data rows
    table_rows = []
    for row in rows:
        cells = [html.Td(row.metric, style={**TABLE_STYLE_CELL, "fontWeight": "600", "fontSize": "11px", "textTransform": "uppercase", "color": TEXT_MUTED})]
        for label in property_labels:
            value_text = row.values.get(label, "—")
            delta_text = row.deltas.get(label, "")
            is_winner = label == row.winner

            # Value styling
            val_style: dict = {"fontSize": "13px", "fontWeight": "600", "color": TEXT_PRIMARY}
            if is_winner and len(property_labels) >= 2:
                val_style["color"] = ACCENT_GREEN

            # Build cell content
            cell_children: list = [html.Div(value_text, style=val_style)]
            if delta_text and delta_text != "best":
                # Show delta as sublabel — red if worse, muted if neutral
                delta_color = TONE_NEGATIVE_TEXT if not row.higher_is_better and delta_text.startswith("+") else (
                    TONE_NEGATIVE_TEXT if row.higher_is_better and delta_text.startswith("-") else TEXT_MUTED
                )
                # For lower-is-better metrics, positive delta means worse
                if not row.higher_is_better and delta_text.startswith("+"):
                    delta_color = TONE_NEGATIVE_TEXT
                elif not row.higher_is_better and delta_text.startswith("-"):
                    delta_color = TONE_POSITIVE_TEXT
                elif row.higher_is_better and delta_text.startswith("+"):
                    delta_color = TONE_POSITIVE_TEXT
                elif row.higher_is_better and delta_text.startswith("-"):
                    delta_color = TONE_NEGATIVE_TEXT
                cell_children.append(html.Div(delta_text, style={"fontSize": "10px", "color": delta_color, "marginTop": "1px"}))
            elif is_winner and len(property_labels) >= 2:
                cell_children.append(html.Div("★ best", style={"fontSize": "9px", "color": ACCENT_GREEN, "marginTop": "1px", "fontWeight": "600"}))

            cell_style = {**TABLE_STYLE_CELL, "textAlign": "right", "verticalAlign": "top", "padding": "6px 10px"}
            if is_winner and len(property_labels) >= 2:
                cell_style["backgroundColor"] = "rgba(34, 197, 94, 0.15)"  # subtle green tint
                cell_style["borderLeft"] = f"2px solid {ACCENT_GREEN}40"

            cells.append(html.Td(cell_children, style=cell_style))

        bg = BG_SURFACE if len(table_rows) % 2 == 0 else BG_SURFACE_2
        table_rows.append(html.Tr(cells, style={"backgroundColor": bg}))

    return html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(table_rows)],
        style={"width": "100%", "borderCollapse": "collapse", "border": f"1px solid {BORDER}", "borderRadius": "4px"},
    )


def score_comparison_heatmap(views: list[PropertyAnalysisView]) -> dcc.Graph | html.Div:
    del views
    return _disabled_chart()
    scored_views = [view for view in views if view.final_score is not None and view.category_scores]
    if not scored_views:
        return html.Div(
            "Score comparison is unavailable because scored properties were not loaded.",
            style={"fontSize": "13px", "color": TEXT_MUTED, "padding": "12px"},
        )

    x_labels = ["Final Score"] + [label for _, label in _COMPARE_CATEGORY_ORDER]
    y_labels = [view.label for view in scored_views]
    z_values: list[list[float]] = []
    text_values: list[list[str]] = []
    for view in scored_views:
        row_scores = [float(view.final_score or 0.0)]
        row_text = [f"{float(view.final_score or 0.0):.1f}"]
        for key, _label in _COMPARE_CATEGORY_ORDER:
            score = _compare_category_score(view, key)
            row_scores.append(float(score or 0.0))
            row_text.append("—" if score is None else f"{score:.1f}")
        z_values.append(row_scores)
        text_values.append(row_text)

    fig = go.Figure(
        data=go.Heatmap(
            z=z_values,
            x=x_labels,
            y=y_labels,
            zmin=1,
            zmax=5,
            colorscale=[
                [0.00, "#EF4444"],
                [0.20, "#F97316"],
                [0.40, "#F59E0B"],
                [0.55, "#64748B"],
                [0.75, "#3B82F6"],
                [1.00, "#22C55E"],
            ],
            text=text_values,
            texttemplate="%{text}",
            textfont={"color": TEXT_PRIMARY, "size": 11},
            hovertemplate="%{y}<br>%{x}: %{z:.1f} / 5.0<extra></extra>",
            colorbar={"title": "Score", "tickvals": [1, 2, 3, 4, 5]},
        )
    )
    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = max(240, 130 + (len(scored_views) * 46))
    layout["margin"] = {"l": 110, "r": 30, "t": 12, "b": 80}
    layout["xaxis"] = {**layout.get("xaxis", {}), "side": "bottom", "tickangle": -20}
    layout["yaxis"] = {**layout.get("yaxis", {}), "autorange": "reversed"}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def category_comparison_radar(view_a: PropertyAnalysisView, view_b: PropertyAnalysisView) -> dcc.Graph | html.Div:
    del view_a, view_b
    return _disabled_chart()
    if not view_a.category_scores or not view_b.category_scores:
        return html.Div(
            "Radar comparison is unavailable because category scoring is missing for one or both properties.",
            style={"fontSize": "13px", "color": TEXT_MUTED, "padding": "12px"},
        )

    labels = [label for _, label in _COMPARE_CATEGORY_ORDER]
    theta = labels + [labels[0]]

    def _scores(view: PropertyAnalysisView) -> list[float]:
        values = [float(_compare_category_score(view, key) or 0.0) for key, _ in _COMPARE_CATEGORY_ORDER]
        return values + [values[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=_scores(view_a),
            theta=theta,
            fill="toself",
            name=view_a.label,
            line={"color": ACCENT_BLUE, "width": 2},
            fillcolor="rgba(59,130,246,0.18)",
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=_scores(view_b),
            theta=theta,
            fill="toself",
            name=view_b.label,
            line={"color": ACCENT_GREEN, "width": 2},
            fillcolor="rgba(22,163,74,0.16)",
        )
    )
    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = 360
    layout["polar"] = {
        "bgcolor": BG_SURFACE,
        "radialaxis": {"visible": True, "range": [0, 5], "gridcolor": BORDER_SUBTLE, "tickfont": {"color": TEXT_MUTED, "size": 10}},
        "angularaxis": {"gridcolor": BORDER_SUBTLE, "tickfont": {"color": TEXT_SECONDARY, "size": 11}},
    }
    layout["legend"] = {"orientation": "h", "y": 1.08, "x": 0, "font": {"color": TEXT_SECONDARY, "size": 11}}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def comparison_explainer(view_a: PropertyAnalysisView, view_b: PropertyAnalysisView) -> html.Div:
    if view_a.final_score is None or view_b.final_score is None:
        return html.Div(
            "Comparison explainer is unavailable because one or both properties are missing a final score.",
            style={"fontSize": "13px", "color": TEXT_MUTED, "padding": "12px"},
        )

    winner = view_a if view_a.final_score >= view_b.final_score else view_b
    loser = view_b if winner is view_a else view_a
    score_gap = abs((view_a.final_score or 0.0) - (view_b.final_score or 0.0))

    category_notes: list[str] = []
    for key, label in _COMPARE_CATEGORY_ORDER:
        left = _compare_category_score(view_a, key)
        right = _compare_category_score(view_b, key)
        if left is None or right is None:
            continue
        diff = left - right
        if abs(diff) > 0.3:
            stronger = view_a if diff > 0 else view_b
            category_notes.append(f"{stronger.label} is stronger in {label} by {abs(diff):.1f} points.")

    metric_notes: list[str] = []
    for label, left, right, formatter in [
        ("Ask", view_a.ask_price, view_b.ask_price, lambda x: f"${x:,.0f}"),
        ("BCV gap vs ask", view_a.mispricing_pct, view_b.mispricing_pct, lambda x: f"{x:+.1%}"),
        ("Monthly cash flow", _parse_currency_text(view_a.income_support.monthly_cash_flow_text), _parse_currency_text(view_b.income_support.monthly_cash_flow_text), lambda x: f"${x:,.0f}"),
    ]:
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            continue
        if abs(float(left) - float(right)) < 0.01:
            continue
        better = view_a if left > right else view_b
        metric_notes.append(
            f"{label} favors {better.label} ({formatter(float(left))} vs {formatter(float(right))})."
        )

    return html.Div(
        [
            html.Div("Decision Read", style=SECTION_HEADER_STYLE),
            html.Div(
                f"{winner.label} ranks ahead of {loser.label} by {score_gap:.2f} score points.",
                style={"fontSize": "15px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginBottom": "8px"},
            ),
            html.Ul(
                [html.Li(note, style={"fontSize": "11px", "color": TEXT_SECONDARY, "marginBottom": "4px"}) for note in (category_notes[:4] + metric_notes[:3])]
                or [html.Li("The two properties score similarly, so the choice likely comes down to fit and diligence.", style={"fontSize": "11px", "color": TEXT_SECONDARY})],
                style={"margin": "0", "paddingLeft": "16px"},
            ),
        ],
        style=CARD_STYLE,
    )


def _top_ranked_views(views: list[PropertyAnalysisView]) -> list[PropertyAnalysisView]:
    return sorted(
        [view for view in views if view.final_score is not None],
        key=lambda view: float(view.final_score or 0.0),
        reverse=True,
    )


def _best_category_edge(winner: PropertyAnalysisView, runner_up: PropertyAnalysisView) -> tuple[str | None, float]:
    best_label: str | None = None
    best_gap = 0.0
    for key, label in _COMPARE_CATEGORY_ORDER:
        winner_score = _compare_category_score(winner, key)
        runner_score = _compare_category_score(runner_up, key)
        if winner_score is None or runner_score is None:
            continue
        gap = float(winner_score) - float(runner_score)
        if gap > best_gap:
            best_gap = gap
            best_label = label
    return best_label, best_gap


def compare_winner_banner(views: list[PropertyAnalysisView]) -> html.Div | None:
    ranked = _top_ranked_views(views)
    if not ranked:
        return None

    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    score_text = f"{float(winner.final_score or 0.0):.2f} / 5.0"

    main_reason = "Highest overall Briarwood score across the selected set."
    runner_text = "No runner-up yet — add another property to compare tradeoffs."
    margin_text = "Only one scored property loaded."

    if runner_up is not None:
        score_gap = float(winner.final_score or 0.0) - float(runner_up.final_score or 0.0)
        best_label, best_gap = _best_category_edge(winner, runner_up)
        runner_text = f"{runner_up.label} ranks second at {float(runner_up.final_score or 0.0):.2f} / 5.0."
        margin_text = f"Lead over runner-up: {score_gap:.2f} points."
        if best_label and best_gap > 0.0:
            main_reason = f"Main edge: {winner.label} leads most clearly in {best_label} (+{best_gap:.1f})."
        elif winner.mispricing_pct is not None and runner_up.mispricing_pct is not None:
            main_reason = (
                f"Main edge: better valuation cushion ({winner.mispricing_pct:+.1%} vs {runner_up.mispricing_pct:+.1%} BCV gap)."
            )

    return html.Div(
        [
            html.Div("Compare Decision Read", style=SECTION_HEADER_STYLE),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Top Ranked", style={"fontSize": "11px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "4px"}),
                            html.Div(winner.label, style={"fontSize": "18px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                            html.Div(score_text, style={"fontSize": "13px", "fontWeight": "600", "color": ACCENT_BLUE, "marginTop": "4px"}),
                        ],
                        style={"flex": "1"},
                    ),
                    html.Div(
                        [
                            html.Div("Runner Up", style={"fontSize": "11px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "4px"}),
                            html.Div(runner_text, style={"fontSize": "13px", "color": TEXT_SECONDARY, "lineHeight": "1.5"}),
                        ],
                        style={"flex": "1"},
                    ),
                    html.Div(
                        [
                            html.Div("Main Reason", style={"fontSize": "11px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "4px"}),
                            html.Div(main_reason, style={"fontSize": "13px", "color": TEXT_SECONDARY, "lineHeight": "1.5"}),
                            html.Div(margin_text, style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "6px"}),
                        ],
                        style={"flex": "1.2"},
                    ),
                ],
                style={"display": "flex", "gap": "18px", "alignItems": "start", "flexWrap": "wrap"},
            ),
        ],
        style={**CARD_STYLE, "border": f"1px solid {BORDER_SUBTLE}", "padding": "14px 16px"},
    )


def property_ranking_table(views: list[PropertyAnalysisView]) -> dash_table.DataTable | html.Div:
    scored_views = _top_ranked_views(views)
    if not scored_views:
        return html.Div(
            "Ranking table is unavailable because no scored properties were loaded.",
            style={"fontSize": "13px", "color": TEXT_MUTED, "padding": "12px"},
        )

    rows: list[dict[str, object]] = []
    for index, view in enumerate(scored_views, start=1):
        rows.append(
            {
                "Rank": index,
                "Address": view.address,
                "Final": round(float(view.final_score or 0.0), 2),
                "Price": round(float(_compare_category_score(view, 'price_context') or 0.0), 1),
                "Income": round(float(_compare_category_score(view, 'economic_support') or 0.0), 1),
                "Optionality": round(float(_compare_category_score(view, 'optionality') or 0.0), 1),
                "Market": round(float(_compare_category_score(view, 'market_position') or 0.0), 1),
                "Risk": round(float(_compare_category_score(view, 'risk_layer') or 0.0), 1),
                "Ask": _fmt_compact(view.ask_price),
                "BCV Gap": gap_pct_text(view) or "—",
            }
        )

    return dash_table.DataTable(
        data=rows,
        columns=[{"name": key, "id": key} for key in rows[0].keys()],
        sort_action="native",
        style_table=TABLE_STYLE_TABLE,
        style_header=TABLE_STYLE_HEADER,
        style_cell=TABLE_STYLE_CELL,
        style_data_conditional=[
            {"if": {"row_index": 0}, "backgroundColor": BG_SURFACE_3, "fontWeight": "700"},
            {"if": {"row_index": "odd"}, **TABLE_STYLE_DATA_ODD},
            {"if": {"row_index": "even"}, **TABLE_STYLE_DATA_EVEN},
            {"if": {"column_id": "Final"}, "color": ACCENT_BLUE, "fontWeight": "600"},
        ],
    )


def render_compare_decision_mode(mode: str, views: list[PropertyAnalysisView], reports: list[AnalysisReport], summary: CompareSummary, section: str) -> html.Div:
    if mode == "detail":
        banner = compare_winner_banner(views)
        body = render_compare_section(section, views, reports, summary)
        return html.Div(([banner] if banner is not None else []) + [body], style={"display": "grid", "gap": "12px"})

    blocks: list = []
    banner = compare_winner_banner(views)
    if banner is not None:
        blocks.append(banner)
    comparison_summary_block = _comparison_summary_block(summary)
    if comparison_summary_block is not None:
        blocks.append(comparison_summary_block)
    blocks.append(
        html.Div(
            [
                html.Div("Score Summary", style=SECTION_HEADER_STYLE),
                property_ranking_table(views),
            ],
            style=CARD_STYLE,
        )
    )
    if len(views) >= 2 and summary.rows:
        blocks.append(html.Div([html.Div("Key Metric Comparison", style=SECTION_HEADER_STYLE), _render_compare_table(summary.rows)], style=CARD_STYLE))
    blocks.append(html.Div([html.Div("Shortlist Ranking", style=SECTION_HEADER_STYLE), property_ranking_table(views)], style=CARD_STYLE))
    if len(views) >= 2:
        blocks.append(html.Div([html.Div("Why Different", style=SECTION_HEADER_STYLE), html.Ul([html.Li(item, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for item in summary.why_different[:6]])], style=CARD_STYLE))

    return html.Div(blocks, style={"display": "grid", "gap": "12px"})


def _lane_header(view: PropertyAnalysisView, *, show_export_button: bool = False) -> html.Div:
    from briarwood.dash_app.theme import BTN_SECONDARY
    return html.Div(
        [
            html.Div(
                [
                    html.Div(view.address, style={"fontSize": "13px", "fontWeight": "600", "color": TEXT_PRIMARY}),
                    html.Div(
                        [confidence_badge(view.overall_confidence), compact_badge("Mode", view.evidence_mode)],
                        style={"display": "flex", "gap": "4px", "marginTop": "4px"},
                    ),
                ],
            ),
            html.Button("Export", id={"type": "lane-export-button", "property_id": view.property_id}, n_clicks=0, style=BTN_SECONDARY) if show_export_button else None,
        ],
        style={**CARD_STYLE, **LANE_HEADER_STYLE, "display": "flex", "justifyContent": "space-between", "alignItems": "start"},
    )


def render_compare_section(section: str, views: list[PropertyAnalysisView], reports: list[AnalysisReport], summary: CompareSummary) -> html.Div:
    summary_block = render_compare_summary(section, summary)
    lanes: list[html.Div] = []
    for view, report in zip(views, reports):
        body = _render_section_content(section, view, report, compact=True)
        lanes.append(html.Div([_lane_header(view, show_export_button=True), body], style={"display": "grid", "gap": "8px"}))
    col_count = min(len(lanes), 2)
    return html.Div(
        [summary_block] + ([html.Div(lanes, style={"display": "grid", "gridTemplateColumns": f"repeat({col_count}, 1fr)", "gap": "12px", "alignItems": "start"})] if lanes else []),
        style={"display": "grid", "gap": "8px"},
    )

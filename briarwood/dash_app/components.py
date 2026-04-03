"""
UI components for the Briarwood research platform.

Dense, analytical layout. Charts are primary. Inline metrics replace cards.
Sub-factor scoring drives the tear sheet structure.
"""
from __future__ import annotations

from dash import dash_table, dcc, html
import plotly.graph_objects as go

from briarwood.dash_app.compare import CompareSummary
from briarwood.dash_app.theme import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED, ACCENT_YELLOW,
    BG_BASE, BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3,
    BODY_TEXT_STYLE, BORDER, BORDER_SUBTLE,
    CARD_STYLE, CARD_STYLE_ELEVATED, CHART_HEIGHT_COMPACT, CHART_HEIGHT_STANDARD,
    FONT_FAMILY, GRID_2, GRID_3, GRID_4,
    LABEL_STYLE, PAGE_STYLE,
    PLOTLY_LAYOUT, PLOTLY_LAYOUT_COMPACT,
    SECTION_HEADER_STYLE,
    TABLE_STYLE_CELL, TABLE_STYLE_DATA_EVEN, TABLE_STYLE_DATA_ODD,
    TABLE_STYLE_HEADER, TABLE_STYLE_TABLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TONE_NEGATIVE_TEXT, TONE_POSITIVE_TEXT, TONE_WARNING_TEXT,
    VALUE_STYLE_LARGE, VALUE_STYLE_MEDIUM,
    score_color, tone_badge_style, tone_color,
)
from briarwood.dash_app.view_models import (
    PropertyAnalysisView,
    build_evidence_rows,
    build_section_evidence_rows,
)
from briarwood.schemas import AnalysisReport

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

RESPONSIVE_GRID_2 = GRID_2
RESPONSIVE_GRID_3 = GRID_3
RESPONSIVE_GRID_4 = GRID_4

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
            html.Div(subtitle, style={"fontSize": "10px", "color": TEXT_MUTED}) if subtitle else None,
        ],
        style=CARD_STYLE,
    )


def inline_metric_strip(metrics: list[tuple[str, str, str | None]]) -> html.Div:
    """Dense inline metric row: Ask $875K | BCV $920K +5.1% | Base $1.01M"""
    items = []
    for i, (label, value, sublabel) in enumerate(metrics):
        if i > 0:
            items.append(html.Span(" | ", style={"margin": "0 10px", "color": BORDER}))
        children = [
            html.Span(label, style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginRight": "5px"}),
            html.Span(value, style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_PRIMARY}),
        ]
        if sublabel:
            is_positive = sublabel.startswith("+")
            is_negative = sublabel.startswith("-") or sublabel.startswith("−")
            sub_color = TONE_POSITIVE_TEXT if is_positive else TONE_NEGATIVE_TEXT if is_negative else TEXT_MUTED
            children.append(html.Span(f" {sublabel}", style={"fontSize": "11px", "color": sub_color}))
        items.append(html.Span(children, style={"display": "inline-flex", "alignItems": "baseline", "gap": "0"}))
    return html.Div(items, style={"padding": "8px 0", "lineHeight": "1.4"})


def confidence_badge(confidence: float) -> html.Span:
    tone = "positive" if confidence >= 0.75 else "warning" if confidence >= 0.55 else "negative"
    return html.Span(f"{confidence:.0%}", style=tone_badge_style(tone))


def compact_badge(label: str, value: str, *, tone: str = "neutral") -> html.Span:
    return html.Span(f"{label}: {value}", style=tone_badge_style(tone))


def _fmt_value(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def _fmt_compact(value: float | None) -> str:
    """Format as compact: $875K or $1.2M."""
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value / 1_000:.0f}K"


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


def render_score_header(view: PropertyAnalysisView) -> html.Div:
    """Top-of-page investment recommendation with overall score and category breakdown."""
    if view.final_score is None:
        return html.Div(
            "Scoring not available",
            style={"padding": "12px", "textAlign": "center", "color": TEXT_MUTED, "fontSize": "11px"},
        )

    sc = score_color(view.final_score)
    filled = int(round(view.final_score))
    dots = "●" * filled + "○" * (5 - filled)

    return html.Div(
        [
            # Top row: score + dots + tier
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f"{view.final_score:.2f}", style={"fontSize": "28px", "fontWeight": "700", "color": sc, "letterSpacing": "-0.03em"}),
                            html.Span(" / 5", style={"fontSize": "14px", "color": TEXT_MUTED}),
                            html.Span(f"  {dots}", style={"fontSize": "16px", "color": sc, "letterSpacing": "3px", "marginLeft": "8px"}),
                        ],
                        style={"display": "flex", "alignItems": "baseline"},
                    ),
                    html.Div(
                        [
                            html.Div((view.recommendation_tier or "").upper(), style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_PRIMARY}),
                            html.Div(view.recommendation_action or "", style={"fontSize": "11px", "color": TEXT_MUTED}),
                        ],
                        style={"textAlign": "right"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "10px"},
            ),
            # Narrative
            html.Div(
                view.score_narrative or "",
                style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_PRIMARY, "marginBottom": "12px"},
            ) if view.score_narrative else None,
            # Category mini-bars in 2-column grid
            html.Div(
                _render_category_mini_bars(view),
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px 16px"},
            ),
        ],
        style={
            **CARD_STYLE,
            "border": f"2px solid {sc}40",
            "marginBottom": "16px",
            "padding": "14px 16px",
        },
    )


def _render_category_mini_bars(view: PropertyAnalysisView) -> list:
    """Compact horizontal bars for each category score."""
    if not view.category_scores:
        return []
    rows = []
    for cat_name, cat in view.category_scores.items():
        sc = score_color(cat.score)
        pct = (cat.score / 5.0) * 100
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(cat.category_name, style={"fontSize": "10px", "color": TEXT_MUTED, "minWidth": "100px", "display": "inline-block"}),
                            html.Span(f"{cat.score:.1f}", style={"fontSize": "11px", "fontWeight": "600", "color": sc, "minWidth": "28px", "display": "inline-block", "textAlign": "right"}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "2px"},
                    ),
                    html.Div(
                        html.Div(style={"width": f"{pct}%", "height": "100%", "backgroundColor": sc, "borderRadius": "1px"}),
                        style={"height": "3px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden"},
                    ),
                ],
                style={"marginBottom": "4px"},
            )
        )
    return rows


def render_sub_factors(sub_factors: list) -> html.Div:
    """Compact sub-factor score rows with dot indicators."""
    rows = []
    for sf in sub_factors:
        filled = int(round(sf.score))
        dots = "●" * filled + "○" * (5 - filled)
        sc = score_color(sf.score)
        rows.append(
            html.Div(
                [
                    html.Span(sf.name.replace("_", " ").title(), style={"fontSize": "11px", "fontWeight": "500", "color": TEXT_PRIMARY, "minWidth": "130px", "display": "inline-block"}),
                    html.Span(dots, style={"fontSize": "11px", "color": sc, "letterSpacing": "1px", "minWidth": "60px", "display": "inline-block"}),
                    html.Span(f"{sf.score:.1f}", style={"fontSize": "11px", "fontWeight": "600", "color": sc, "minWidth": "28px", "display": "inline-block"}),
                    html.Span(f"({sf.weight:.0%})", style={"fontSize": "10px", "color": TEXT_MUTED, "minWidth": "35px", "display": "inline-block"}),
                    html.Span(sf.evidence, style={"fontSize": "10px", "color": TEXT_MUTED, "flex": "1"}),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "6px", "padding": "4px 0", "borderBottom": f"1px solid {BORDER_SUBTLE}"},
            )
        )
    return html.Div(rows, style={"marginTop": "8px"})


def render_executive_summary(view: PropertyAnalysisView) -> html.Div:
    """Executive summary: TL;DR with top strengths/risks and key metrics."""
    # Collect all sub-factors, rank by score
    all_sfs: list[tuple[float, str, str]] = []
    if view.category_scores:
        for cat in view.category_scores.values():
            for sf in cat.sub_factors:
                all_sfs.append((sf.score, sf.name.replace("_", " ").title(), sf.evidence))
    all_sfs.sort(key=lambda x: x[0], reverse=True)
    top_strengths = all_sfs[:3]
    top_risks = all_sfs[-3:][::-1]

    # Key metrics table rows
    metric_rows = [
        ("Ask Price", _fmt_value(view.ask_price), gap_pct_text(view) or None),
        ("BCV", _fmt_value(view.bcv), None),
        ("Base Case", _fmt_value(view.base_case), None),
        ("PTR", view.income_support.price_to_rent_text, view.income_support.ptr_classification),
        ("Cash Flow", view.income_support.monthly_cash_flow_text, None),
        ("Risk Score", f"{view.risk_location.risk_score:.0f}/100", None),
    ]

    return html.Div(
        [
            html.Div("EXECUTIVE SUMMARY", style=SECTION_HEADER_STYLE),
            # Thesis narrative
            html.Div(
                view.score_narrative or view.memo_summary or "",
                style={"fontSize": "12px", "lineHeight": "1.6", "color": TEXT_PRIMARY, "marginBottom": "12px"},
            ),
            # Strengths vs Risks
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Top Strengths", style={"fontSize": "10px", "fontWeight": "600", "color": TONE_POSITIVE_TEXT, "marginBottom": "4px", "textTransform": "uppercase"}),
                            html.Ul(
                                [html.Li([html.Span(f"{name}: ", style={"fontWeight": "500"}), html.Span(ev, style={"color": TEXT_MUTED})], style={"fontSize": "11px", "marginBottom": "3px"}) for _, name, ev in top_strengths],
                                style={"margin": "0", "paddingLeft": "14px"},
                            ),
                        ],
                        style={"flex": "1"},
                    ),
                    html.Div(
                        [
                            html.Div("Top Risks", style={"fontSize": "10px", "fontWeight": "600", "color": TONE_NEGATIVE_TEXT, "marginBottom": "4px", "textTransform": "uppercase"}),
                            html.Ul(
                                [html.Li([html.Span(f"{name}: ", style={"fontWeight": "500"}), html.Span(ev, style={"color": TEXT_MUTED})], style={"fontSize": "11px", "marginBottom": "3px"}) for _, name, ev in top_risks],
                                style={"margin": "0", "paddingLeft": "14px"},
                            ),
                        ],
                        style={"flex": "1"},
                    ),
                ],
                style={"display": "flex", "gap": "16px", "marginBottom": "12px"},
            ) if all_sfs else None,
            # Key metrics as compact table
            html.Div(
                [
                    html.Div("Key Metrics", style={"fontSize": "10px", "fontWeight": "600", "color": TEXT_MUTED, "marginBottom": "4px", "textTransform": "uppercase"}),
                    html.Table(
                        html.Tbody(
                            [
                                html.Tr(
                                    [
                                        html.Td(label, style={"padding": "3px 8px 3px 0", "color": TEXT_MUTED, "fontSize": "11px", "borderBottom": f"1px solid {BORDER_SUBTLE}"}),
                                        html.Td(value, style={"padding": "3px 8px", "fontWeight": "600", "fontSize": "11px", "textAlign": "right", "borderBottom": f"1px solid {BORDER_SUBTLE}"}),
                                        html.Td(
                                            change or "",
                                            style={"padding": "3px 0 3px 6px", "fontSize": "10px", "textAlign": "right", "borderBottom": f"1px solid {BORDER_SUBTLE}",
                                                   "color": TONE_POSITIVE_TEXT if change and "+" in change else TEXT_MUTED},
                                        ),
                                    ]
                                )
                                for label, value, change in metric_rows
                            ]
                        ),
                        style={"width": "100%", "borderCollapse": "collapse"},
                    ),
                ],
            ),
        ],
        style={**CARD_STYLE, "marginBottom": "16px"},
    )


def render_category_section(
    title: str,
    category_key: str,
    view: PropertyAnalysisView,
    *,
    metrics_strip: html.Div | None = None,
    chart: html.Div | dcc.Graph | None = None,
    narrative: str | None = None,
    extra_content: html.Div | None = None,
    default_open: bool = False,
) -> html.Div:
    """Collapsible category section using native HTML <details>/<summary>."""
    cat = view.category_scores.get(category_key) if view.category_scores else None
    sc = score_color(cat.score) if cat else TEXT_MUTED

    # Summary line (always visible, acts as the toggle)
    summary_el = html.Summary(
        html.Div(
            [
                html.Span(title, style={**SECTION_HEADER_STYLE, "marginBottom": "0", "display": "inline", "fontSize": "11px"}),
                html.Span(
                    f"  {cat.score:.1f} / 5.0" if cat else "  N/A",
                    style={"fontSize": "15px", "fontWeight": "600", "color": sc, "marginLeft": "8px"},
                ),
                html.Span(
                    f"({cat.weight:.0%})" if cat else "",
                    style={"fontSize": "10px", "color": TEXT_MUTED, "marginLeft": "6px"},
                ),
                # Mini score bar inline in header
                html.Div(
                    html.Div(style={"width": f"{(cat.score / 5.0) * 100:.0f}%", "height": "100%", "backgroundColor": sc, "borderRadius": "1px"}),
                    style={"height": "3px", "width": "60px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden", "marginLeft": "10px", "display": "inline-block", "verticalAlign": "middle"},
                ) if cat else None,
            ],
            style={"display": "flex", "alignItems": "baseline"},
        ),
        style={
            "cursor": "pointer",
            "padding": "8px 12px",
            "borderBottom": f"2px solid {BORDER}",
            "listStyle": "none",
            "outline": "none",
            "userSelect": "none",
        },
    )

    # Expandable body
    body_children = []
    if metrics_strip:
        body_children.append(metrics_strip)
    if chart:
        body_children.append(html.Div(chart, style={"marginTop": "6px"}))
    if cat:
        # Sub-factors also collapsible
        body_children.append(
            html.Details(
                [
                    html.Summary(
                        html.Span("Sub-Factor Breakdown", style={"fontSize": "10px", "fontWeight": "600", "color": TEXT_MUTED, "textTransform": "uppercase", "cursor": "pointer"}),
                        style={"listStyle": "none", "padding": "6px 0", "outline": "none"},
                    ),
                    render_sub_factors(cat.sub_factors),
                ],
                open=default_open,
                style={"marginTop": "8px"},
            )
        )
    if narrative:
        body_children.append(html.P(narrative, style={**BODY_TEXT_STYLE, "marginTop": "6px"}))
    if extra_content:
        body_children.append(extra_content)

    return html.Details(
        [summary_el, html.Div(body_children, style={"padding": "8px 12px 12px"})],
        open=default_open,
        style={"marginBottom": "4px", "backgroundColor": BG_SURFACE, "border": f"1px solid {BORDER}", "borderRadius": "4px"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ═══════════════════════════════════════════════════════════════════════════════


def forward_waterfall_chart(report: AnalysisReport) -> dcc.Graph | html.Div:
    """Waterfall: BCV → market drift → location → risk → optionality → Base."""
    bbb = report.module_results.get("bull_base_bear")
    if not bbb:
        return html.Div("No scenario data", style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"})

    m = bbb.metrics
    bcv = m.get("bcv_anchor")
    if not bcv:
        return html.Div("No BCV anchor", style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"})

    components = [
        ("Market Drift", (m.get("base_market_drift_pct") or 0) * bcv),
        ("Location", (m.get("base_location_pct") or 0) * bcv),
        ("Risk Adj", (m.get("base_risk_pct") or 0) * bcv),
        ("Optionality", (m.get("base_optionality_pct") or 0) * bcv),
    ]

    labels = ["BCV"]
    values = [bcv]
    measure = ["absolute"]
    for label, val in components:
        labels.append(label)
        values.append(val)
        measure.append("relative")
    labels.append("Base Case")
    values.append(0)
    measure.append("total")

    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=measure,
        text=[f"${v / 1000:+.0f}K" if meas == "relative" else f"${v / 1000:.0f}K" for v, meas in zip(values, measure)],
        textposition="outside",
        textfont={"color": TEXT_SECONDARY, "size": 10},
        connector={"line": {"color": BORDER, "width": 1}},
        increasing={"marker": {"color": ACCENT_GREEN}},
        decreasing={"marker": {"color": ACCENT_RED}},
        totals={"marker": {"color": ACCENT_BLUE}},
    ))
    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = CHART_HEIGHT_STANDARD
    layout["showlegend"] = False
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f"}
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def forward_range_chart(view: PropertyAnalysisView, *, compact: bool = False) -> dcc.Graph:
    """Scenario range: Bear → Base → Bull with ask reference line."""
    layout = dict(PLOTLY_LAYOUT_COMPACT if compact else PLOTLY_LAYOUT)
    layout["height"] = CHART_HEIGHT_COMPACT if compact else CHART_HEIGHT_STANDARD
    layout["showlegend"] = False
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f"}

    x_labels = ["Bear", "Base", "Bull"]
    y_values = [view.bear_case or 0, view.base_case or 0, view.bull_case or 0]
    texts = [view.forward.bear_value_text, view.forward.base_value_text, view.forward.bull_value_text]
    colors = [ACCENT_RED, ACCENT_BLUE, ACCENT_GREEN]

    if view.stress_case is not None:
        x_labels = ["Stress", "Bear", "Base", "Bull"]
        y_values = [view.stress_case, view.bear_case or 0, view.base_case or 0, view.bull_case or 0]
        texts = [view.forward.stress_case_value_text, view.forward.bear_value_text, view.forward.base_value_text, view.forward.bull_value_text]
        colors = ["#7c1f1f", ACCENT_RED, ACCENT_BLUE, ACCENT_GREEN]

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
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


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
                            html.Span(sf.name.replace("_", " ").title(), style={"fontSize": "10px", "color": TEXT_MUTED}),
                            html.Span(f"{sf.score:.1f}", style={"fontSize": "10px", "fontWeight": "600", "color": sc}),
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
                            html.Span(item.label, style={"fontSize": "10px", "color": TEXT_MUTED}),
                            html.Span(f"{pct:.0f}%", style={"fontSize": "10px", "fontWeight": "600"}),
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
                    html.Div(view.memo_verdict, style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginBottom": "3px"}),
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


# ═══════════════════════════════════════════════════════════════════════════════
# TEAR SHEET SECTION RENDERERS (scoring-driven)
# ═══════════════════════════════════════════════════════════════════════════════


def render_tear_sheet_body(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Full tear sheet: summary-first with collapsible drill-downs."""
    return html.Div(
        [
            summary_strip(view),
            render_score_header(view),
            # Executive summary (always visible)
            render_executive_summary(view),
            # Detailed analysis header
            html.Div("DETAILED ANALYSIS", style={**SECTION_HEADER_STYLE, "marginTop": "8px", "marginBottom": "8px", "fontSize": "10px", "letterSpacing": "0.12em"}),
            # Price Context (collapsed by default)
            render_category_section(
                "PRICE CONTEXT", "price_context", view,
                metrics_strip=inline_metric_strip([
                    ("Ask", _fmt_compact(view.ask_price), None),
                    ("BCV", _fmt_compact(view.bcv), gap_pct_text(view) if view.mispricing_pct is not None else None),
                    ("Comps", view.comps.comparable_value_text, f"{view.comps.comp_count_text} used"),
                    ("Base", _fmt_compact(view.base_case), None),
                ]),
                chart=forward_waterfall_chart(report),
                narrative=view.forward.summary if view.forward else None,
                default_open=False,
            ),
            # Economic Support (open by default as example)
            render_category_section(
                "ECONOMIC SUPPORT", "economic_support", view,
                metrics_strip=inline_metric_strip([
                    ("PTR", view.income_support.price_to_rent_text, view.income_support.ptr_classification),
                    ("ISR", view.income_support.income_support_ratio_text, None),
                    ("Cash Flow", view.income_support.monthly_cash_flow_text, None),
                    ("Rental Ease", view.income_support.rental_ease_label, None),
                ]),
                narrative=view.income_support.summary,
                default_open=True,
            ),
            # Optionality (collapsed)
            render_category_section(
                "OPTIONALITY", "optionality", view,
                metrics_strip=inline_metric_strip([
                    ("Condition", view.condition_profile, None),
                    ("CapEx Lane", view.capex_lane, None),
                    ("Pricing View", view.pricing_view.title(), None),
                ]),
                default_open=False,
            ),
            # Market Position (collapsed)
            render_category_section(
                "MARKET POSITION", "market_position", view,
                metrics_strip=inline_metric_strip([
                    ("Town Score", f"{view.risk_location.town_score:.0f}", view.risk_location.town_label.replace("_", " ").title()),
                    ("Scarcity", f"{view.risk_location.scarcity_score:.0f}", None),
                    ("Liquidity", view.risk_location.liquidity_view.title(), None),
                ]),
                extra_content=html.Div(
                    [
                        html.Div([html.Span("Demand Drivers", style=SECTION_HEADER_STYLE), html.Ul([html.Li(d, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for d in view.risk_location.drivers[:4]], style={"margin": "4px 0", "paddingLeft": "16px"})], style={"flex": "1"}),
                        html.Div([html.Span("Location Risks", style=SECTION_HEADER_STYLE), html.Ul([html.Li(r, style={"fontSize": "11px", "color": TONE_WARNING_TEXT}) for r in view.risk_location.risks[:4]], style={"margin": "4px 0", "paddingLeft": "16px"})], style={"flex": "1"}),
                    ],
                    style={"display": "flex", "gap": "16px", "marginTop": "8px"},
                ) if (view.risk_location.drivers or view.risk_location.risks) else None,
                default_open=False,
            ),
            # Risk Layer (collapsed)
            render_category_section(
                "RISK LAYER", "risk_layer", view,
                metrics_strip=inline_metric_strip([
                    ("Risk Score", f"{view.risk_location.risk_score:.0f}", None),
                    ("Flood", view.risk_location.flood_risk.title(), None),
                    ("Constraints", view.risk_location.risk_summary[:60] if view.risk_location.risk_summary else "—", None),
                ]),
                chart=risk_breakdown_bars(view),
                default_open=False,
            ),
            # Scenario range
            _render_forward_scenarios(view),
            # Evidence footer
            _render_evidence_footer(view, report),
        ],
        style={"padding": "16px 20px", "maxWidth": "1100px"},
    )


def gap_pct_text(view: PropertyAnalysisView) -> str:
    if view.mispricing_pct is None:
        return ""
    sign = "+" if view.mispricing_pct >= 0 else ""
    return f"{sign}{view.mispricing_pct * 100:.1f}%"


def _render_forward_scenarios(view: PropertyAnalysisView) -> html.Div:
    """Compact scenario range section."""
    metric_rows = [
        {"Metric": "Bear", "Value": view.forward.bear_value_text, "vs Ask": view.forward.downside_pct_text},
        {"Metric": "Base", "Value": view.forward.base_value_text, "vs Ask": "—"},
        {"Metric": "Bull", "Value": view.forward.bull_value_text, "vs Ask": view.forward.upside_pct_text},
    ]
    if view.stress_case is not None:
        metric_rows.insert(0, {"Metric": "Stress ⚠", "Value": view.forward.stress_case_value_text, "vs Ask": "Tail risk"})

    return html.Div(
        [
            html.Div("SCENARIO RANGE", style=SECTION_HEADER_STYLE),
            html.Div(
                [
                    html.Div(forward_range_chart(view, compact=True), style={"flex": "1"}),
                    html.Div(simple_table(metric_rows, page_size=6), style={"flex": "0 0 280px"}),
                ],
                style={"display": "flex", "gap": "12px", "alignItems": "start"},
            ),
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
            confidence_progress_bars(view),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Missing Inputs", style={**LABEL_STYLE, "color": TONE_NEGATIVE_TEXT}),
                            html.Div(", ".join(view.evidence.missing_inputs[:6]) or "None", style={"fontSize": "10px", "color": TEXT_MUTED}),
                        ],
                        style={"flex": "1"},
                    ) if missing > 0 else None,
                    html.Div(
                        [
                            html.Div("Estimated Inputs", style={**LABEL_STYLE, "color": TONE_WARNING_TEXT}),
                            html.Div(", ".join(view.evidence.estimated_inputs[:6]) or "None", style={"fontSize": "10px", "color": TEXT_MUTED}),
                        ],
                        style={"flex": "1"},
                    ) if estimated > 0 else None,
                ],
                style={"display": "flex", "gap": "12px", "marginTop": "6px"},
            ) if (missing > 0 or estimated > 0) else None,
        ],
        style={"marginTop": "24px", "paddingTop": "12px", "borderTop": f"1px solid {BORDER}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY SECTION RENDERERS (for compare view backwards compat)
# ═══════════════════════════════════════════════════════════════════════════════


def render_overview_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            html.Div(view.memo_verdict, style={"fontSize": "14px" if compact else "16px", "fontWeight": "600", "marginBottom": "4px"}),
            html.Div(view.memo_summary, style=BODY_TEXT_STYLE),
            inline_metric_strip([
                ("Ask", _fmt_compact(view.ask_price), None),
                ("BCV", _fmt_compact(view.bcv), gap_pct_text(view) or None),
                ("Base", _fmt_compact(view.base_case), None),
                ("Risk", view.biggest_risk, None),
            ]),
        ],
        style=CARD_STYLE,
    )


def render_value_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    comp_rows = [{"Address": r.address, "Adjusted": r.adjusted_price, "Fit": r.fit, "Verification": r.verification} for r in view.comps.rows]
    return html.Div(
        [
            inline_metric_strip([("Pricing", view.pricing_view.title(), None), ("Confidence", f"{view.value.confidence:.0%}", None), ("Comps", view.comps.comparable_value_text, None)]),
            simple_table(comp_rows or [{"Address": "No comps", "Adjusted": "—", "Fit": "—", "Verification": "—"}], page_size=5),
        ],
        style={"display": "grid", "gap": "8px"},
    )


def render_forward_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            inline_metric_strip([
                ("Bear", view.forward.bear_value_text, view.forward.downside_pct_text),
                ("Base", view.forward.base_value_text, None),
                ("Bull", view.forward.bull_value_text, view.forward.upside_pct_text),
            ]),
            forward_range_chart(view, compact=compact),
        ],
        style={"display": "grid", "gap": "8px"},
    )


def render_risk_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            inline_metric_strip([("Risk Score", f"{view.risk_location.risk_score:.0f}", None), ("Flood", view.risk_location.flood_risk.title(), None), ("Liquidity", view.risk_location.liquidity_view.title(), None)]),
            html.Div(view.risk_location.risk_summary, style=BODY_TEXT_STYLE),
            risk_breakdown_bars(view),
        ],
        style={"display": "grid", "gap": "8px"},
    )


def render_location_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            inline_metric_strip([("Town", f"{view.risk_location.town_score:.0f}", view.risk_location.town_label.replace("_", " ").title()), ("Scarcity", f"{view.risk_location.scarcity_score:.0f}", None)]),
            html.Div(
                [
                    html.Ul([html.Li(d, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for d in view.risk_location.drivers[:4]], style={"margin": "0", "paddingLeft": "16px"}),
                ],
            ) if view.risk_location.drivers else None,
        ],
        style={"display": "grid", "gap": "8px"},
    )


def render_income_support_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    return html.Div(
        [
            inline_metric_strip([
                ("PTR", view.income_support.price_to_rent_text, view.income_support.ptr_classification),
                ("Rental Ease", view.income_support.rental_ease_label, None),
                ("ISR", view.income_support.income_support_ratio_text, None),
                ("Cash Flow", view.income_support.monthly_cash_flow_text, None),
            ]),
            html.Div(view.income_support.summary, style=BODY_TEXT_STYLE),
        ],
        style={"display": "grid", "gap": "8px"},
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
            confidence_progress_bars(view),
            simple_table(evidence_rows, page_size=10) if not compact else html.Div(),
        ],
        style={"display": "grid", "gap": "8px"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH (used by app.py for tear sheet and compare)
# ═══════════════════════════════════════════════════════════════════════════════


def render_single_section(section: str, view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Legacy dispatcher — used by compare view. Tear sheet uses render_tear_sheet_body directly."""
    mapping = {
        "overview": render_overview_section,
        "value": render_value_section,
        "forward": render_forward_section,
        "risk": render_risk_section,
        "location": render_location_section,
        "income": render_income_support_section,
    }
    if section == "evidence":
        return render_evidence_section(report, view, compact=False)
    if section == "data_quality":
        from briarwood.dash_app.data_quality import render_data_quality_section
        return render_data_quality_section(report)
    if section == "scenarios":
        from briarwood.dash_app.scenarios import render_scenarios_section
        return render_scenarios_section(report)
    return mapping.get(section, render_overview_section)(view, compact=False)


_COMPARE_SECTION_METRICS: dict[str, set[str]] = {
    "overview": {"Ask", "BCV", "BCV Delta vs Ask", "Forward Base", "Confidence"},
    "value": {"Ask", "BCV", "BCV Delta vs Ask", "BCV Range", "Lot Size", "Sqft", "Taxes", "Confidence"},
    "forward": {"Forward Base", "BCV Delta vs Ask", "Forward Gap", "Confidence"},
    "risk": {"Risk Score", "DOM", "Taxes"},
    "location": {"Town/County", "Scarcity"},
    "income": {"Income Support", "Price-to-Rent"},
    "evidence": {"Confidence"},
}


def render_compare_summary(section: str, summary: CompareSummary) -> html.Div | None:
    if not summary.rows:
        return None
    metric_filter = _COMPARE_SECTION_METRICS.get(section, set())
    rows = [{"Metric": row.metric, **row.values} for row in summary.rows if row.metric in metric_filter]
    if not rows:
        return None
    return html.Div(
        [
            html.Div([html.Div("Key Differences", style=SECTION_HEADER_STYLE), html.Ul([html.Li(item, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for item in summary.why_different[:4]])], style=CARD_STYLE),
            html.Div([html.Div("Compare", style=SECTION_HEADER_STYLE), simple_table(rows, page_size=8)], style=CARD_STYLE),
        ],
        style={**GRID_2, "marginBottom": "12px"},
    )


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
    lane_renderer = {
        "overview": render_overview_section,
        "value": render_value_section,
        "forward": render_forward_section,
        "risk": render_risk_section,
        "location": render_location_section,
        "income": render_income_support_section,
    }
    lanes: list[html.Div] = []
    for view, report in zip(views, reports):
        if section == "evidence":
            body = render_evidence_section(report, view, compact=True)
        elif section == "data_quality":
            from briarwood.dash_app.data_quality import render_data_quality_section
            body = render_data_quality_section(report)
        elif section == "scenarios":
            from briarwood.dash_app.scenarios import render_scenarios_section
            body = render_scenarios_section(report)
        else:
            body = lane_renderer.get(section, render_overview_section)(view, compact=True)
        lanes.append(html.Div([_lane_header(view, show_export_button=True), body], style={"display": "grid", "gap": "8px"}))
    col_count = min(len(lanes), 2)
    return html.Div(
        [summary_block] + ([html.Div(lanes, style={"display": "grid", "gridTemplateColumns": f"repeat({col_count}, 1fr)", "gap": "12px", "alignItems": "start"})] if lanes else []),
        style={"display": "grid", "gap": "8px"},
    )

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
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED, ACCENT_TEAL, ACCENT_YELLOW,
    BG_BASE, BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3, BG_SURFACE_4,
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
        strongest = max(cat.sub_factors, key=lambda sf: sf.score) if cat.sub_factors else None
        weakest = min(cat.sub_factors, key=lambda sf: sf.score) if cat.sub_factors else None
        rows.append(
            html.Details(
                [
                    html.Summary(
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
                        style={"listStyle": "none", "cursor": "pointer", "padding": "0", "outline": "none"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("What this means", style={"fontSize": "10px", "fontWeight": "600", "color": TEXT_MUTED, "textTransform": "uppercase"}),
                                    html.Div(
                                        _category_drill_in_summary(cat.category_name, strongest.evidence if strongest else None, weakest.evidence if weakest else None),
                                        style={"fontSize": "11px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "4px"},
                                    ),
                                ]
                            ),
                            _render_category_components(cat),
                            render_sub_factors(cat.sub_factors) if cat.sub_factors else None,
                        ],
                        style={"paddingTop": "6px"},
                    ),
                ],
                open=False,
                style={"marginBottom": "4px", "paddingBottom": "2px", "borderBottom": f"1px solid {BORDER_SUBTLE}"},
            )
        )
    return rows


def _category_drill_in_summary(category_name: str, strongest: str | None, weakest: str | None) -> str:
    parts = []
    if strongest:
        parts.append(f"Best support: {strongest}")
    if weakest:
        parts.append(f"Main drag: {weakest}")
    if not parts:
        parts.append(f"{category_name} is being scored from the currently available Briarwood evidence and heuristics.")
    return " ".join(parts)


def _render_category_components(cat: object) -> html.Div | None:
    component_scores = getattr(cat, "component_scores", None) or {}
    if not component_scores:
        return None
    component_notes = getattr(cat, "component_notes", None) or {}
    label_map = {
        "physical_optionality": "Physical Optionality",
        "strategic_optionality": "Strategic Optionality",
    }
    rows = []
    for key, value in component_scores.items():
        if value is None:
            continue
        sc = score_color(value)
        pct = (value / 5.0) * 100
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(label_map.get(key, key.replace("_", " ").title()), style={"fontSize": "10px", "color": TEXT_MUTED}),
                            html.Span(f"{value:.1f}/5", style={"fontSize": "10px", "fontWeight": "600", "color": sc}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "2px"},
                    ),
                    html.Div(
                        html.Div(style={"width": f"{pct}%", "height": "100%", "backgroundColor": sc, "borderRadius": "1px"}),
                        style={"height": "3px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden", "marginBottom": "4px"},
                    ),
                    html.Div(component_notes.get(key, ""), style={"fontSize": "10px", "lineHeight": "1.4", "color": TEXT_MUTED}),
                ],
                style={"padding": "4px 0", "borderBottom": f"1px solid {BORDER_SUBTLE}"},
            )
        )
    if not rows:
        return None
    return html.Div(
        [
            html.Div("Sub-Components", style={"fontSize": "10px", "fontWeight": "600", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "4px"}),
            html.Div(rows, style={"display": "grid", "gap": "2px"}),
        ],
        style={"marginTop": "8px"},
    )


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
                    _render_category_components(cat),
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


def forward_fan_chart(view: PropertyAnalysisView, *, compact: bool = False) -> dcc.Graph | html.Div:
    anchor_value = view.bcv or view.base_case
    if anchor_value is None:
        return html.Div(
            "Forward fan chart is unavailable because no BCV or base-case anchor was returned.",
            style={"fontSize": "11px", "color": TEXT_MUTED, "padding": "12px"},
        )

    fig = go.Figure()
    x_anchor = "Today"
    x_horizon = "12M"

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
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon, x_horizon, x_anchor],
                y=[anchor_value, view.bull_case, view.bear_case, anchor_value],
                fill="toself",
                fillcolor="rgba(88, 166, 255, 0.14)",
                line={"color": "rgba(0,0,0,0)"},
                hoverinfo="skip",
                name="Bull / Bear Fan",
                showlegend=True,
            )
        )

    if view.bull_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[anchor_value, view.bull_case],
                mode="lines",
                name="Bull",
                line={"color": ACCENT_GREEN, "width": 2, "dash": "dash"},
                hovertemplate="%{x}<br>Bull: %{y:$,.0f}<extra></extra>",
            )
        )

    if view.bear_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[anchor_value, view.bear_case],
                mode="lines",
                name="Bear",
                line={"color": ACCENT_RED, "width": 2, "dash": "dash"},
                hovertemplate="%{x}<br>Bear: %{y:$,.0f}<extra></extra>",
            )
        )

    if view.base_case is not None:
        fig.add_trace(
            go.Scatter(
                x=[x_anchor, x_horizon],
                y=[anchor_value, view.base_case],
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
                y=[anchor_value, view.stress_case],
                mode="lines",
                name="Stress",
                line={"color": "#7c1f1f", "width": 1.5, "dash": "dot"},
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
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def comp_positioning_dot_plot(view: PropertyAnalysisView, report: AnalysisReport) -> dcc.Graph | html.Div:
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
    marker_sizes = [10 + (getattr(comp, "similarity_score", 0.5) * 12) for comp in comps]

    fig = go.Figure()
    if adjusted_prices:
        fig.add_trace(
            go.Scatter(
                x=adjusted_prices,
                y=list(range(len(comps), 0, -1)),
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
        start_y = len(comps) + len(active_rows)
        fig.add_trace(
            go.Scatter(
                x=active_prices,
                y=list(range(start_y, len(comps), -1)),
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
                y=[len(comps) + len(active_rows) + 0.8],
                mode="markers",
                name="Subject Ask" if view.ask_price is not None else "Subject BCV",
                marker={"size": 15, "symbol": "diamond", "color": ACCENT_TEAL, "line": {"color": BORDER, "width": 1.5}},
                hovertemplate=f"{view.address}<br>{'Ask' if view.ask_price is not None else 'BCV'}: %{{x:$,.0f}}<extra></extra>",
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
        "showticklabels": False,
        "showgrid": False,
        "zeroline": False,
        "range": [0.5, max(len(comps) + len(active_rows) + 1.4, 2.5)],
    }
    fig.update_layout(**layout)
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def location_metrics_bars(view: PropertyAnalysisView, report: AnalysisReport) -> dcc.Graph | html.Div:
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
            ("Risk Adjusted", max(0.0, 100.0 - float(view.risk_location.risk_score)), neutral_benchmark),
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
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def income_carry_waterfall(view: PropertyAnalysisView, report: AnalysisReport) -> dcc.Graph | html.Div:
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
                            html.Span(item.label, style={"fontSize": "10px", "color": TEXT_MUTED}),
                            html.Span(f"{pct:.0f}%  ·  wt {weight_pct}%", style={"fontSize": "10px", "fontWeight": "600"}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "2px"},
                    ),
                    html.Div(
                        html.Div(style={"width": f"{pct}%", "height": "100%", "backgroundColor": color, "borderRadius": "1px"}),
                        style={"height": "4px", "backgroundColor": BORDER_SUBTLE, "borderRadius": "1px", "overflow": "hidden"},
                    ),
                    html.Div(item.reason, style={"fontSize": "10px", "color": TEXT_MUTED, "marginTop": "3px", "lineHeight": "1.4"}),
                ],
                style={"marginBottom": "8px"},
            )
        )
    return html.Div(bars)


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
                            html.Div(item.label, style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase"}),
                            html.Div(item.value, style={"fontSize": "13px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginTop": "2px"}),
                        ],
                        style={"minWidth": "140px"},
                    ),
                    html.Div(
                        [
                            _source_badge(item),
                            html.Div(item.note, style={"fontSize": "10px", "color": TEXT_MUTED, "lineHeight": "1.4", "marginTop": "4px"}),
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
                            html.Div(item.label, style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase"}),
                            html.Div(item.confidence_impact, style={"fontSize": "11px", "color": TEXT_SECONDARY, "lineHeight": "1.4", "marginTop": "3px"}),
                            html.Div(" | ".join(detail_parts), style={"fontSize": "10px", "color": TEXT_MUTED, "marginTop": "4px", "lineHeight": "1.4"}) if detail_parts else None,
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
            # Executive summary (always visible)
            render_executive_summary(view),
            render_score_header(view),
            # Detailed analysis header
            html.Div("DETAILED ANALYSIS", style={**SECTION_HEADER_STYLE, "marginTop": "8px", "marginBottom": "8px", "fontSize": "10px", "letterSpacing": "0.12em"}),
            # Price Context (collapsed by default)
            render_category_section(
                "PRICE CONTEXT", "price_context", view,
                metrics_strip=inline_metric_strip([
                    ("Ask", _fmt_compact(view.ask_price), None),
                    ("BCV", _fmt_compact(view.bcv), gap_pct_text(view) if view.mispricing_pct is not None else None),
                    ("Net Delta", _fmt_signed_currency(view.net_opportunity_delta_value), _fmt_signed_pct(view.net_opportunity_delta_pct) if view.net_opportunity_delta_pct is not None else None),
                    ("Comps", view.comps.comparable_value_text, f"{view.comps.comp_count_text} used"),
                    ("Actives", view.comps.active_listing_count_text, None),
                    ("Basis", _fmt_compact(view.all_in_basis), _capex_basis_source_label(view.capex_basis_source)),
                ]),
                chart=html.Div(
                    [
                        comp_positioning_dot_plot(view, report),
                        html.Div(forward_waterfall_chart(report), style={"marginTop": "8px"}),
                    ],
                    style={"display": "grid", "gap": "8px"},
                ),
                narrative=view.forward.summary if view.forward else None,
                extra_content=html.Div(
                    [block for block in [_net_opportunity_delta_block(view), _active_listing_block(view)] if block is not None],
                    style={"display": "grid", "gap": "8px"},
                ),
                default_open=False,
            ),
            # Economic Support (open by default as example)
            render_category_section(
                "ECONOMIC SUPPORT", "economic_support", view,
                metrics_strip=inline_metric_strip([
                    ("Total Rent", view.income_support.total_rent_text, view.income_support.rent_source_type),
                    ("PTR", view.income_support.price_to_rent_text, view.income_support.ptr_classification),
                    ("ISR", view.income_support.income_support_ratio_text, None),
                    ("Cash Flow", view.income_support.monthly_cash_flow_text, None),
                    ("Rental Ease", view.income_support.rental_ease_label, None),
                ]),
                chart=income_carry_waterfall(view, report),
                narrative=view.income_support.summary,
                extra_content=_unit_breakdown_block(view),
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
                    ("Momentum", f"{view.risk_location.market_momentum_score:.0f}/100", view.risk_location.market_momentum_label),
                    ("Scarcity", f"{view.risk_location.scarcity_score:.0f}", None),
                    ("Liquidity", f"{view.risk_location.liquidity_score:.0f}/100", view.risk_location.liquidity_label),
                ]),
                chart=location_metrics_bars(view, report),
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
            inline_metric_strip([
                ("Pricing", view.pricing_view.title(), None),
                ("Net Delta", _fmt_signed_currency(view.net_opportunity_delta_value), _fmt_signed_pct(view.net_opportunity_delta_pct) if view.net_opportunity_delta_pct is not None else None),
                ("Basis", _fmt_compact(view.all_in_basis), _capex_basis_source_label(view.capex_basis_source)),
                ("Confidence", f"{view.value.confidence:.0%}", None),
                ("Comps", view.comps.comparable_value_text, None),
            ]),
            _net_opportunity_delta_block(view),
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
            forward_fan_chart(view, compact=compact),
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
                ("Total Rent", view.income_support.total_rent_text, view.income_support.rent_source_type),
                ("PTR", view.income_support.price_to_rent_text, view.income_support.ptr_classification),
                ("Rental Ease", view.income_support.rental_ease_label, None),
                ("ISR", view.income_support.income_support_ratio_text, None),
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
                    ("BCV", _fmt_compact(view.bcv), None),
                    ("All-In Basis", _fmt_compact(view.all_in_basis), _capex_basis_source_label(view.capex_basis_source)),
                ]
            ),
            html.Div(explanation, style={"fontSize": "11px", "color": TEXT_SECONDARY, "marginTop": "2px"}),
            html.Div(capex_note, style={"fontSize": "11px", "color": TEXT_MUTED, "marginTop": "4px"}),
        ],
        style={**CARD_STYLE, "marginTop": "8px"},
    )


def _active_listing_block(view: PropertyAnalysisView) -> html.Div | None:
    if not view.comps.active_listing_rows:
        return None
    rows = [
        {
            "Address": row.address,
            "List": row.list_price,
            "Status": row.status,
            "Beds": row.beds,
            "Baths": row.baths,
            "Sqft": row.sqft,
            "DOM": row.dom,
            "Condition": row.condition,
        }
        for row in view.comps.active_listing_rows
    ]
    return html.Div(
        [
            html.Div("Current Competition", style=SECTION_HEADER_STYLE),
            html.Div(
                f"{view.comps.active_listing_count_text} active listing(s) currently loaded for this market.",
                style={"fontSize": "11px", "color": TEXT_MUTED, "marginBottom": "6px"},
            ),
            simple_table(rows, page_size=min(max(len(rows), 1), 10)),
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


def render_single_section(section: str, view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Legacy dispatcher — used by compare view. Tear sheet uses render_tear_sheet_body directly."""
    return _render_section_content(section, view, report, compact=False)


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


def score_comparison_heatmap(views: list[PropertyAnalysisView]) -> dcc.Graph | html.Div:
    scored_views = [view for view in views if view.final_score is not None and view.category_scores]
    if not scored_views:
        return html.Div(
            "Score comparison is unavailable because scored properties were not loaded.",
            style={"fontSize": "12px", "color": TEXT_MUTED, "padding": "12px"},
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
                [0.00, "#b42318"],
                [0.20, "#f97316"],
                [0.40, "#facc15"],
                [0.55, "#6e7681"],
                [0.75, "#3b82f6"],
                [1.00, "#16a34a"],
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
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def category_comparison_radar(view_a: PropertyAnalysisView, view_b: PropertyAnalysisView) -> dcc.Graph | html.Div:
    if not view_a.category_scores or not view_b.category_scores:
        return html.Div(
            "Radar comparison is unavailable because category scoring is missing for one or both properties.",
            style={"fontSize": "12px", "color": TEXT_MUTED, "padding": "12px"},
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
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def comparison_explainer(view_a: PropertyAnalysisView, view_b: PropertyAnalysisView) -> html.Div:
    if view_a.final_score is None or view_b.final_score is None:
        return html.Div(
            "Comparison explainer is unavailable because one or both properties are missing a final score.",
            style={"fontSize": "12px", "color": TEXT_MUTED, "padding": "12px"},
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
                            html.Div("Top Ranked", style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "4px"}),
                            html.Div(winner.label, style={"fontSize": "18px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                            html.Div(score_text, style={"fontSize": "12px", "fontWeight": "600", "color": ACCENT_BLUE, "marginTop": "4px"}),
                        ],
                        style={"flex": "1"},
                    ),
                    html.Div(
                        [
                            html.Div("Runner Up", style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "4px"}),
                            html.Div(runner_text, style={"fontSize": "12px", "color": TEXT_SECONDARY, "lineHeight": "1.5"}),
                        ],
                        style={"flex": "1"},
                    ),
                    html.Div(
                        [
                            html.Div("Main Reason", style={"fontSize": "10px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginBottom": "4px"}),
                            html.Div(main_reason, style={"fontSize": "12px", "color": TEXT_SECONDARY, "lineHeight": "1.5"}),
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
            style={"fontSize": "12px", "color": TEXT_MUTED, "padding": "12px"},
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
    if mode == "heatmap":
        blocks.append(html.Div([html.Div("Score Heatmap", style=SECTION_HEADER_STYLE), score_comparison_heatmap(views)], style=CARD_STYLE))
        blocks.append(html.Div([html.Div("Property Ranking", style=SECTION_HEADER_STYLE), property_ranking_table(views)], style=CARD_STYLE))
        if len(views) >= 2:
            blocks.append(html.Div([html.Div("Why Different", style=SECTION_HEADER_STYLE), html.Ul([html.Li(item, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for item in summary.why_different[:6]])], style=CARD_STYLE))
    elif mode == "radar":
        if len(views) < 2:
            return html.Div("Select exactly 2 properties to use radar comparison.", style={"color": TEXT_MUTED, "fontSize": "14px"})
        blocks.append(html.Div([html.Div("Category Radar", style=SECTION_HEADER_STYLE), category_comparison_radar(views[0], views[1])], style=CARD_STYLE))
        blocks.append(comparison_explainer(views[0], views[1]))
    elif mode == "table":
        blocks.append(html.Div([html.Div("Ranked Comparison", style=SECTION_HEADER_STYLE), property_ranking_table(views)], style=CARD_STYLE))
        if len(views) >= 2:
            blocks.append(html.Div([html.Div("Decision Notes", style=SECTION_HEADER_STYLE), html.Ul([html.Li(item, style={"fontSize": "11px", "color": TEXT_SECONDARY}) for item in summary.why_different[:6]])], style=CARD_STYLE))

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

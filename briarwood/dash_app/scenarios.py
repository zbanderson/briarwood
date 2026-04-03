"""
Investment Scenarios tab — dark-theme renderer.

Renders Renovation Scenario and Rent-to-Teardown Strategy.
Only shown when at least one scenario is enabled on the property.
"""
from __future__ import annotations

from dash import dcc, html
import plotly.graph_objects as go

from briarwood.dash_app.components import (
    confidence_badge,
    metric_card,
    simple_table,
)
from briarwood.dash_app.theme import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED,
    BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3, BORDER,
    BODY_TEXT_STYLE, CARD_STYLE, FONT_FAMILY, GRID_2, GRID_3, GRID_4,
    PLOTLY_LAYOUT, SECTION_HEADER_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TONE_NEGATIVE_TEXT, TONE_WARNING_TEXT, TONE_WARNING_BG,
    VALUE_STYLE_LARGE, tone_color,
)
from briarwood.schemas import AnalysisReport


def render_scenarios_section(report: AnalysisReport) -> html.Div:
    blocks: list = []

    reno_result = report.module_results.get("renovation_scenario")
    if reno_result and isinstance(reno_result.payload, dict) and reno_result.payload.get("enabled"):
        blocks.append(_render_renovation(reno_result.payload, reno_result.confidence))

    td_result = report.module_results.get("teardown_scenario")
    if td_result and isinstance(td_result.payload, dict) and td_result.payload.get("enabled"):
        blocks.append(_render_teardown(td_result.payload, td_result.confidence))

    if not blocks:
        return html.Div(
            html.Div(
                [
                    html.Div("No Investment Scenarios Configured", style={**VALUE_STYLE_LARGE, "fontSize": "18px", "marginBottom": "8px"}),
                    html.P(
                        "Add renovation_scenario or teardown_scenario to the property input to activate scenario analysis.",
                        style=BODY_TEXT_STYLE,
                    ),
                ],
                style={**CARD_STYLE, "padding": "32px"},
            )
        )

    return html.Div(blocks, style={"display": "grid", "gap": "32px"})


# ── Renovation Scenario ────────────────────────────────────────────────────────


def _render_renovation(payload: dict, confidence: float) -> html.Div:
    budget = payload.get("renovation_budget") or 0
    current_bcv = payload.get("current_bcv") or 0
    renovated_bcv = payload.get("renovated_bcv") or 0
    gross_vc = payload.get("gross_value_creation") or 0
    net_vc = payload.get("net_value_creation") or 0
    roi_pct = payload.get("roi_pct") or 0
    cpd = payload.get("cost_per_dollar_of_value")
    condition_change = payload.get("condition_change") or ""
    sqft_change = payload.get("sqft_change")
    summary = payload.get("summary") or ""
    warnings = payload.get("warnings") or []

    roi_tone = "positive" if roi_pct > 0 else "negative"
    cpd_text = f"${cpd:.2f} per $1 of value" if cpd is not None else "—"

    # Before / after chart
    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = 260
    layout["showlegend"] = False
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickformat": "$,.0f"}
    layout["margin"] = {"l": 48, "r": 20, "t": 20, "b": 40}

    fig = go.Figure(data=[
        go.Bar(
            x=["Current BCV", "Renovation Cost", "Renovated BCV"],
            y=[current_bcv, budget, renovated_bcv],
            marker_color=[BG_SURFACE_3, ACCENT_ORANGE, ACCENT_GREEN],
            marker_line_color=BORDER,
            marker_line_width=1,
            text=[f"${current_bcv:,.0f}", f"${budget:,.0f}", f"${renovated_bcv:,.0f}"],
            textposition="outside",
            textfont={"color": TEXT_SECONDARY, "size": 11},
        )
    ])
    fig.update_layout(**layout)

    return html.Div(
        [
            # Header card
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Renovation Scenario", style=SECTION_HEADER_STYLE),
                            html.Div(
                                f"${budget:,.0f} investment  →  est. ${renovated_bcv:,.0f} post-renovation value",
                                style={"fontSize": "18px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginBottom": "8px"},
                            ),
                            html.Div(
                                [
                                    html.Span(condition_change, style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginRight": "10px"}),
                                    confidence_badge(confidence),
                                ],
                                style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"},
                            ),
                        ]
                    ),
                ],
                style=CARD_STYLE,
            ),
            # Metric row
            html.Div(
                [
                    metric_card("Current BCV", f"${current_bcv:,.0f}"),
                    metric_card("Renovation Cost", f"${budget:,.0f}"),
                    metric_card("Renovated BCV", f"${renovated_bcv:,.0f}", tone="positive"),
                    metric_card("Net Value Creation", f"${net_vc:,.0f}", tone=roi_tone),
                    metric_card("ROI", f"{roi_pct:.1f}%", tone=roi_tone),
                    metric_card("Cost Efficiency", cpd_text, tone=roi_tone),
                ],
                style=GRID_3,
            ),
            # Chart + analysis
            html.Div(
                [
                    html.Div(
                        [html.Div("Before / After", style=SECTION_HEADER_STYLE), dcc.Graph(figure=fig, config={"displayModeBar": False})],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div("Analysis", style=SECTION_HEADER_STYLE),
                            html.P(summary, style=BODY_TEXT_STYLE),
                            *(
                                [html.Div([html.Span("Sqft Change: ", style={"fontWeight": "600", "color": TEXT_SECONDARY}), html.Span(sqft_change, style={"color": TEXT_PRIMARY})], style={"marginTop": "10px"})]
                                if sqft_change else []
                            ),
                            *(
                                [_warning_block(warnings)]
                                if warnings else []
                            ),
                        ],
                        style=CARD_STYLE,
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 2fr", "gap": "12px"},
            ),
        ],
        style={"display": "grid", "gap": "12px"},
    )


# ── Rent-to-Teardown Strategy ──────────────────────────────────────────────────


def _render_teardown(payload: dict, confidence: float) -> html.Div:
    hold_years = payload.get("hold_years") or 0
    timeline = payload.get("total_project_timeline_years") or 0
    p1 = payload.get("phase1") or {}
    p2 = payload.get("phase2") or {}
    pt = payload.get("project_totals") or {}
    warnings = payload.get("warnings") or []
    phase1_narrative = payload.get("phase1_narrative") or ""
    phase2_narrative = payload.get("phase2_narrative") or ""
    project_narrative = payload.get("project_narrative") or ""

    burn_down_pct = p1.get("burn_down_pct") or 0
    new_build_value = p2.get("estimated_new_construction_value") or 0
    total_profit = pt.get("total_profit") or 0
    ann_roi = pt.get("annualized_roi_pct") or 0
    total_invested = pt.get("total_cash_invested") or 0
    roi_tone = "positive" if ann_roi >= 5.0 else "warning" if ann_roi >= 2.0 else "negative"

    year_by_year = p1.get("year_by_year") or []
    burn_chart = _build_burndown_chart(year_by_year)

    return html.Div(
        [
            # Header card
            html.Div(
                [
                    html.Div("Rent-to-Teardown Strategy", style=SECTION_HEADER_STYLE),
                    html.Div(
                        f"{hold_years}-year hold + new construction  →  est. ${new_build_value:,.0f}",
                        style={"fontSize": "18px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginBottom": "8px"},
                    ),
                    confidence_badge(confidence),
                ],
                style=CARD_STYLE,
            ),
            # Key metrics
            html.Div(
                [
                    metric_card("Hold Period", f"{hold_years} yrs"),
                    metric_card("Burn Down", f"{burn_down_pct:.0f}%", subtitle="rent offset vs initial investment"),
                    metric_card("New Build Value", f"${new_build_value:,.0f}", tone="positive"),
                    metric_card("Total Profit", f"${total_profit:,.0f}", tone=roi_tone),
                    metric_card("Ann. ROI", f"{ann_roi:.1f}%", tone=roi_tone),
                    metric_card("Timeline", f"{timeline:.1f} yrs"),
                ],
                style=GRID_3,
            ),
            # Burn-down chart
            html.Div(
                [html.Div("Cash Flow & Equity Over Hold Period", style=SECTION_HEADER_STYLE), burn_chart],
                style=CARD_STYLE,
            ),
            # Phase narratives
            html.Div(
                [
                    html.Div(
                        [html.Div("Phase 1 — Hold & Rent", style=SECTION_HEADER_STYLE), html.P(phase1_narrative, style=BODY_TEXT_STYLE)],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [html.Div("Phase 2 — Tear Down & Build", style=SECTION_HEADER_STYLE), html.P(phase2_narrative, style=BODY_TEXT_STYLE)],
                        style=CARD_STYLE,
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px"},
            ),
            # Project totals
            html.Div(
                [
                    html.Div("Full Project Economics", style=SECTION_HEADER_STYLE),
                    html.P(project_narrative, style=BODY_TEXT_STYLE),
                    html.Div(
                        [
                            metric_card("Total Invested", f"${total_invested:,.0f}"),
                            metric_card("Final Value", f"${new_build_value:,.0f}", tone="positive"),
                            metric_card("Net Profit", f"${total_profit:,.0f}", tone=roi_tone),
                            metric_card("Ann. ROI", f"{ann_roi:.1f}%", tone=roi_tone),
                        ],
                        style={**GRID_4, "marginTop": "12px"},
                    ),
                    *([_warning_block(warnings)] if warnings else []),
                ],
                style=CARD_STYLE,
            ),
        ],
        style={"display": "grid", "gap": "12px"},
    )


def _build_burndown_chart(year_by_year: list[dict]) -> dcc.Graph:
    if not year_by_year:
        layout = dict(PLOTLY_LAYOUT)
        layout["height"] = 300
        layout["annotations"] = [{"text": "No data", "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False, "font": {"color": TEXT_MUTED}}]
        return dcc.Graph(figure=go.Figure().update_layout(**layout), config={"displayModeBar": False})

    years = [y["year"] for y in year_by_year]
    cum_cf = [y["cumulative_cash_flow"] for y in year_by_year]
    equity = [y["equity"] for y in year_by_year]
    prop_values = [y["property_value"] for y in year_by_year]

    breakeven_year = next((y["year"] for y in year_by_year if y["cumulative_cash_flow"] >= 0), None)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=years, y=prop_values,
        mode="lines",
        name="Property Value",
        line={"color": ACCENT_BLUE, "width": 2, "dash": "dot"},
    ))
    fig.add_trace(go.Scatter(
        x=years, y=equity,
        mode="lines+markers",
        name="Equity Position",
        line={"color": ACCENT_GREEN, "width": 3},
        marker={"size": 7, "color": ACCENT_GREEN, "line": {"color": BORDER, "width": 1}},
    ))
    cf_colors = [ACCENT_RED if v < 0 else ACCENT_GREEN for v in cum_cf]
    fig.add_trace(go.Scatter(
        x=years, y=cum_cf,
        mode="lines+markers",
        name="Cumulative Cash Flow",
        line={"color": ACCENT_ORANGE, "width": 2.5},
        marker={"size": 7, "color": cf_colors, "line": {"color": BORDER, "width": 1}},
    ))

    fig.add_hline(y=0, line_dash="dash", line_color=TEXT_MUTED, line_width=1)

    if breakeven_year is not None:
        fig.add_vline(
            x=breakeven_year,
            line_dash="dot",
            line_color=ACCENT_GREEN,
            line_width=1.5,
            annotation_text=f"Break-even yr {breakeven_year}",
            annotation_position="top right",
            annotation_font_color=ACCENT_GREEN,
            annotation_font_size=11,
        )

    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = 380
    layout["yaxis"] = {**layout.get("yaxis", {}), "tickprefix": "$", "separatethousands": True}
    layout["xaxis"] = {**layout.get("xaxis", {}), "title": "Year", "dtick": 1}
    layout["legend"] = {"orientation": "h", "yanchor": "bottom", "y": -0.28, "x": 0, "bgcolor": "rgba(0,0,0,0)", "font": {"color": TEXT_SECONDARY, "size": 11}}
    fig.update_layout(**layout)

    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _warning_block(warnings: list[str]) -> html.Div:
    return html.Div(
        [
            html.Div("Warnings", style={**SECTION_HEADER_STYLE, "color": TONE_WARNING_TEXT, "marginTop": "14px"}),
            html.Ul(
                [html.Li(w, style={"color": TONE_WARNING_TEXT, "fontSize": "13px"}) for w in warnings],
                style={"margin": "4px 0 0", "paddingLeft": "20px"},
            ),
        ],
    )

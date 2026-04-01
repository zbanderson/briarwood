"""
Investment Scenarios Dash renderer.

Renders the Renovation Scenario and Rent-to-Teardown Strategy sections
in the Briarwood Workspace. Only shown when at least one scenario is enabled.
"""
from __future__ import annotations

from dash import dcc, html
import plotly.graph_objects as go

from briarwood.dash_app.components import (
    CARD_STYLE,
    RESPONSIVE_GRID_3,
    RESPONSIVE_GRID_4,
    confidence_badge,
    metric_card,
)
from briarwood.schemas import AnalysisReport


def render_scenarios_section(report: AnalysisReport) -> html.Div:
    """Render the Investment Scenarios tab content."""
    blocks: list[html.Div] = []

    reno_result = report.module_results.get("renovation_scenario")
    if reno_result and isinstance(reno_result.payload, dict) and reno_result.payload.get("enabled"):
        blocks.append(_render_renovation(reno_result.payload, reno_result.confidence))

    td_result = report.module_results.get("teardown_scenario")
    if td_result and isinstance(td_result.payload, dict) and td_result.payload.get("enabled"):
        blocks.append(_render_teardown(td_result.payload, td_result.confidence))

    if not blocks:
        return html.Div(
            html.P(
                "No investment scenarios are enabled for this property. "
                "Add renovation_scenario or teardown_scenario to the property input to activate.",
                style={"color": "#6b7b8d", "padding": "24px"},
            )
        )

    return html.Div(blocks, style={"display": "grid", "gap": "24px"})


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

    # Before/after bar chart
    fig = go.Figure(data=[
        go.Bar(
            x=["Current BCV", "Renovation Cost", "Renovated BCV"],
            y=[current_bcv, budget, renovated_bcv],
            marker_color=["#8fa7bf", "#e08a3a", "#3aaf85"],
            text=[f"${current_bcv:,.0f}", f"${budget:,.0f}", f"${renovated_bcv:,.0f}"],
            textposition="outside",
        )
    ])
    fig.update_layout(
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=260,
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
    )

    return html.Div(
        [
            html.Div(
                [
                    html.H2("Renovation Scenario", style={"margin": "0 0 4px 0"}),
                    html.Div(
                        f"${budget:,.0f} investment → estimated ${renovated_bcv:,.0f} post-renovation value",
                        style={"color": "#5f7286", "marginBottom": "8px"},
                    ),
                    html.Div([html.Span(condition_change, style={"marginRight": "12px"}), confidence_badge(confidence)]),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    metric_card("Current BCV", f"${current_bcv:,.0f}"),
                    metric_card("Renovation Cost", f"${budget:,.0f}"),
                    metric_card("Renovated BCV", f"${renovated_bcv:,.0f}", tone="positive"),
                    metric_card("Net Value Creation", f"${net_vc:,.0f}", tone=roi_tone),
                    metric_card("ROI", f"{roi_pct:.1f}%", tone=roi_tone),
                    metric_card("Cost Efficiency", cpd_text, tone=roi_tone),
                ],
                style=RESPONSIVE_GRID_3,
            ),
            html.Div(
                [
                    html.Div(
                        [html.H3("Before / After"), dcc.Graph(figure=fig, config={"displayModeBar": False})],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.H3("Analysis"),
                            html.P(summary),
                            *(
                                [html.Div(
                                    [html.Strong("Sqft Change: "), html.Span(sqft_change)],
                                    style={"marginBottom": "8px"},
                                )]
                                if sqft_change else []
                            ),
                            *(
                                [html.Div([html.Strong("Warnings:"), html.Ul([html.Li(w) for w in warnings])])]
                                if warnings else []
                            ),
                        ],
                        style=CARD_STYLE,
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 2fr", "gap": "14px"},
            ),
        ],
        style={"display": "grid", "gap": "14px"},
    )


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

    # Burn-down chart
    year_by_year = p1.get("year_by_year") or []
    burn_chart = _build_burndown_chart(year_by_year)

    return html.Div(
        [
            html.Div(
                [
                    html.H2("Rent-to-Teardown Strategy", style={"margin": "0 0 4px 0"}),
                    html.Div(
                        f"{hold_years}-year hold + new construction → estimated ${new_build_value:,.0f}",
                        style={"color": "#5f7286", "marginBottom": "8px"},
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
                style=RESPONSIVE_GRID_3,
            ),
            # Burn-down chart (signature visual)
            html.Div(
                [html.H3("Cash Flow & Equity Over Hold Period"), burn_chart],
                style=CARD_STYLE,
            ),
            # Phase narratives
            html.Div(
                [
                    html.Div(
                        [html.H3("Phase 1 — Hold & Rent"), html.P(phase1_narrative)],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [html.H3("Phase 2 — Tear Down & Build"), html.P(phase2_narrative)],
                        style=CARD_STYLE,
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"},
            ),
            # Project totals
            html.Div(
                [
                    html.H3("Full Project Economics"),
                    html.P(project_narrative),
                    html.Div(
                        [
                            metric_card("Total Invested", f"${total_invested:,.0f}"),
                            metric_card("Final Value", f"${new_build_value:,.0f}", tone="positive"),
                            metric_card("Net Profit", f"${total_profit:,.0f}", tone=roi_tone),
                            metric_card("Ann. ROI", f"{ann_roi:.1f}%", tone=roi_tone),
                        ],
                        style=RESPONSIVE_GRID_4,
                    ),
                    *(
                        [html.Div([html.Strong("Warnings:"), html.Ul([html.Li(w) for w in warnings])])]
                        if warnings else []
                    ),
                ],
                style=CARD_STYLE,
            ),
        ],
        style={"display": "grid", "gap": "14px"},
    )


def _build_burndown_chart(year_by_year: list[dict]) -> dcc.Graph:
    if not year_by_year:
        return dcc.Graph(
            figure=go.Figure().update_layout(title="No data", height=300),
            config={"displayModeBar": False},
        )

    years = [y["year"] for y in year_by_year]
    cum_cf = [y["cumulative_cash_flow"] for y in year_by_year]
    equity = [y["equity"] for y in year_by_year]
    prop_values = [y["property_value"] for y in year_by_year]

    # Find break-even year (cumulative cash flow turns positive)
    breakeven_year = None
    for y in year_by_year:
        if y["cumulative_cash_flow"] >= 0:
            breakeven_year = y["year"]
            break

    fig = go.Figure()

    # Property value (blue background line)
    fig.add_trace(go.Scatter(
        x=years, y=prop_values,
        mode="lines",
        name="Property Value",
        line={"color": "#4a90d9", "width": 2, "dash": "dot"},
    ))

    # Equity position (green solid)
    fig.add_trace(go.Scatter(
        x=years, y=equity,
        mode="lines+markers",
        name="Equity Position",
        line={"color": "#0b7a5d", "width": 3},
        marker={"size": 7},
    ))

    # Cumulative cash flow (can be negative)
    cf_color = ["#d9534f" if v < 0 else "#3aaf85" for v in cum_cf]
    fig.add_trace(go.Scatter(
        x=years, y=cum_cf,
        mode="lines+markers",
        name="Cumulative Cash Flow",
        line={"color": "#e08a3a", "width": 2.5},
        marker={"size": 7, "color": cf_color},
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="#9ca3af", line_width=1)

    # Break-even annotation
    if breakeven_year is not None:
        fig.add_vline(
            x=breakeven_year,
            line_dash="dash",
            line_color="#0b7a5d",
            line_width=1.5,
            annotation_text=f"Break-even yr {breakeven_year}",
            annotation_position="top right",
        )

    fig.update_layout(
        template="plotly_white",
        height=380,
        margin={"l": 20, "r": 20, "t": 20, "b": 40},
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.25, "x": 0},
        yaxis={"tickprefix": "$", "separatethousands": True, "gridcolor": "#e4dbc9"},
        xaxis={"title": "Year", "dtick": 1},
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False})

"""
Investment Scenarios tab — dark-theme renderer.

Renders Renovation Scenario and Rent-to-Teardown Strategy.
Only shown when at least one scenario is enabled on the property.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from dash import dcc, html
import plotly.graph_objects as go

from briarwood.dash_app.components import (
    confidence_badge,
    metric_card,
    simple_table,
)
from briarwood.dash_app.theme import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED, ACCENT_TEAL,
    BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3, BG_SURFACE_4, BORDER,
    BODY_TEXT_STYLE, CARD_STYLE, FONT_FAMILY, GRID_2, GRID_3, GRID_4,
    PLOTLY_LAYOUT, SECTION_HEADER_STYLE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TONE_NEGATIVE_TEXT, TONE_WARNING_TEXT, TONE_WARNING_BG,
    VALUE_STYLE_LARGE, tone_color,
)
from briarwood.reports.section_helpers import get_current_value, get_market_value_history, get_scenario_output
from briarwood.schemas import AnalysisReport


def render_scenarios_section(report: AnalysisReport) -> html.Div:
    blocks: list = [_render_historic_forward_outlook(report)]

    reno_result = report.module_results.get("renovation_scenario")
    if reno_result and isinstance(reno_result.payload, dict) and reno_result.payload.get("enabled"):
        blocks.append(_render_renovation(reno_result.payload, reno_result.confidence))

    td_result = report.module_results.get("teardown_scenario")
    if td_result and isinstance(td_result.payload, dict) and td_result.payload.get("enabled"):
        blocks.append(_render_teardown(td_result.payload, td_result.confidence))

    if len(blocks) == 1:
        blocks.append(
            html.Div(
                [
                    html.Div("Optional Investment Scenarios", style=SECTION_HEADER_STYLE),
                    html.P(
                        "Forward outlook is available below. Add renovation_scenario or teardown_scenario inputs to activate project-specific strategy analysis.",
                        style=BODY_TEXT_STYLE,
                    ),
                ],
                style=CARD_STYLE,
            )
        )

    return html.Div(blocks, style={"display": "grid", "gap": "32px"})


def _stress_value(scenario: object) -> float | None:
    return getattr(scenario, "stress_case_value", None)


# ── Historic + forward outlook ────────────────────────────────────────────────


def _render_historic_forward_outlook(report: AnalysisReport) -> html.Div:
    chart_bundle = _build_historic_forward_chart(report)
    scenario_module = report.module_results.get("bull_base_bear")
    current_value = get_current_value(report)
    scenario = get_scenario_output(report)

    low = scenario.bear_case_value
    high = scenario.bull_case_value
    spread_text = "—"
    if low is not None and high is not None:
        spread_text = f"${low:,.0f} to ${high:,.0f}"

    metrics = [
        metric_card("BCV Anchor", _currency(current_value.briarwood_current_value), tone="positive"),
        metric_card("12M Base", _currency(scenario.base_case_value)),
        metric_card("12M Range", spread_text),
        metric_card("Stress Case", _currency(_stress_value(scenario)), tone="negative" if _stress_value(scenario) is not None else "neutral"),
    ]

    driver_metrics = scenario_module.metrics if scenario_module is not None else {}
    drivers_table = simple_table(
        [
            {"Driver": "Market Drift", "Impact": _currency(driver_metrics.get("market_drift"))},
            {"Driver": "Location Premium", "Impact": _currency(driver_metrics.get("location_premium"))},
            {"Driver": "Risk Discount", "Impact": _currency(driver_metrics.get("risk_discount"))},
            {"Driver": "Optionality", "Impact": _currency(driver_metrics.get("optionality_premium"))},
        ]
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div("Historic + Forward Outlook", style=SECTION_HEADER_STYLE),
                    html.Div(
                        "Here’s where the property or market has been, and where Briarwood thinks it could go next.",
                        style={"fontSize": "18px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginBottom": "8px"},
                    ),
                    html.Div(
                        [
                            confidence_badge(scenario_module.confidence if scenario_module is not None else 0.0),
                            html.Span("12-month forward framing", style={"fontSize": "13px", "color": TEXT_SECONDARY}),
                        ],
                        style={"display": "flex", "gap": "10px", "alignItems": "center", "flexWrap": "wrap"},
                    ),
                ],
                style=CARD_STYLE,
            ),
            html.Div(metrics, style=GRID_4),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Research Chart", style=SECTION_HEADER_STYLE),
                            dcc.Graph(figure=chart_bundle["figure"], config={"displayModeBar": False}),
                            html.Div(chart_bundle["diagnostic_note"], style={"fontSize": "13px", "color": TEXT_MUTED, "marginTop": "6px"}),
                            html.Div(chart_bundle["fallback_note"], style={"fontSize": "13px", "color": TONE_WARNING_TEXT, "marginTop": "4px"}) if chart_bundle["fallback_note"] else None,
                        ],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div("Forward Framing", style=SECTION_HEADER_STYLE),
                            html.P((scenario_module.summary if scenario_module is not None else "Forward scenario output unavailable."), style=BODY_TEXT_STYLE),
                            html.Div("Driver Breakdown", style={**SECTION_HEADER_STYLE, "marginTop": "14px"}),
                            drivers_table,
                        ],
                        style=CARD_STYLE,
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1.8fr 1fr", "gap": "12px"},
            ),
        ],
        style={"display": "grid", "gap": "12px"},
    )


def _build_historic_forward_chart(report: AnalysisReport) -> dict[str, object]:
    """
    Diagnostic note for this chart:
    - Historic property series comes from property_input.price_history and facts.sale_history when present.
    - Historic market context comes from market_value_history.points.
    - The forward bridge uses current_value.briarwood_current_value as the primary anchor, falling back to base case if needed.
    """
    current_value = get_current_value(report)
    scenario = get_scenario_output(report)
    market_history = get_market_value_history(report)

    property_points = _extract_property_history_points(report)
    market_points = _extract_market_history_points(report)

    last_historic_date = max(
        [point["date"] for point in property_points + market_points],
        default=date.today(),
    )
    cutoff = last_historic_date - timedelta(days=365 * 10)
    property_points = [point for point in property_points if point["date"] >= cutoff]
    market_points = [point for point in market_points if point["date"] >= cutoff]

    anchor_date = max([point["date"] for point in property_points + market_points], default=date.today())
    horizon_date = anchor_date + timedelta(days=365)
    anchor_value = current_value.briarwood_current_value or scenario.base_case_value

    history_sources: list[str] = []
    if property_points:
        history_sources.append(f"property history ({len(property_points)} pts)")
    if market_points:
        history_sources.append(f"market history ({len(market_points)} pts)")
    if not history_sources:
        history_sources.append("forward projection only")

    fallback_note = ""
    if not property_points and not market_points:
        fallback_note = "Historic pricing data not available. Showing forward projection only."
    elif not property_points:
        fallback_note = "No property transaction history found. Historic context uses market-level pricing only."
    elif not market_points:
        fallback_note = "Market history series not available. Historic context uses property-specific pricing only."

    diagnostic_note = (
        f"Historic series used: {', '.join(history_sources)}. "
        f"Forward anchor: {_currency(anchor_value)} from {'BCV' if current_value.briarwood_current_value is not None else 'base case fallback'}."
    )

    fig = go.Figure()

    anchor_x = anchor_date.isoformat()
    horizon_x = horizon_date.isoformat()

    if market_points:
        fig.add_trace(
            go.Scatter(
                x=[point["date"].isoformat() for point in market_points],
                y=[point["value"] for point in market_points],
                mode="lines",
                name="Market Context",
                line={"color": TEXT_MUTED, "width": 2},
                hovertemplate="%{x|%b %Y}<br>Market: %{y:$,.0f}<extra></extra>",
            )
        )

    if property_points:
        fig.add_trace(
            go.Scatter(
                x=[point["date"].isoformat() for point in property_points],
                y=[point["value"] for point in property_points],
                mode="lines+markers",
                name="Property History",
                line={"color": ACCENT_TEAL, "width": 2.5},
                marker={
                    "size": 8,
                    "color": ACCENT_TEAL,
                    "line": {"color": BORDER, "width": 1},
                    "symbol": [point["symbol"] for point in property_points],
                },
                customdata=[[point["label"], point["event"]] for point in property_points],
                hovertemplate="%{x|%b %Y}<br>%{customdata[0]}: %{y:$,.0f}<br>%{customdata[1]}<extra></extra>",
            )
        )

    if anchor_value is not None:
        fig.add_trace(
            go.Scatter(
                x=[anchor_x],
                y=[anchor_value],
                mode="markers",
                name="Today / BCV",
                marker={"size": 10, "color": ACCENT_BLUE, "line": {"color": BORDER, "width": 1.5}},
                hovertemplate="%{x|%b %Y}<br>BCV anchor: %{y:$,.0f}<extra></extra>",
            )
        )

        if scenario.bull_case_value is not None and scenario.bear_case_value is not None:
            fig.add_trace(
                go.Scatter(
                    x=[anchor_x, horizon_x, horizon_x, anchor_x],
                    y=[anchor_value, scenario.bull_case_value, scenario.bear_case_value, anchor_value],
                    fill="toself",
                    fillcolor="rgba(88, 166, 255, 0.14)",
                    line={"color": "rgba(0,0,0,0)"},
                    hoverinfo="skip",
                    name="Bull / Bear Fan",
                    showlegend=True,
                )
            )

        if scenario.bull_case_value is not None:
            fig.add_trace(
                go.Scatter(
                    x=[anchor_x, horizon_x],
                    y=[anchor_value, scenario.bull_case_value],
                    mode="lines",
                    name="Bull",
                    line={"color": ACCENT_GREEN, "width": 2, "dash": "dash"},
                    hovertemplate="%{x|%b %Y}<br>Bull: %{y:$,.0f}<extra></extra>",
                )
            )
        if scenario.bear_case_value is not None:
            fig.add_trace(
                go.Scatter(
                    x=[anchor_x, horizon_x],
                    y=[anchor_value, scenario.bear_case_value],
                    mode="lines",
                    name="Bear",
                    line={"color": ACCENT_RED, "width": 2, "dash": "dash"},
                    hovertemplate="%{x|%b %Y}<br>Bear: %{y:$,.0f}<extra></extra>",
                )
            )
        if scenario.base_case_value is not None:
            fig.add_trace(
                go.Scatter(
                    x=[anchor_x, horizon_x],
                    y=[anchor_value, scenario.base_case_value],
                    mode="lines+markers",
                    name="Base",
                    line={"color": ACCENT_BLUE, "width": 4},
                    marker={"size": 7, "color": ACCENT_BLUE},
                    hovertemplate="%{x|%b %Y}<br>Base: %{y:$,.0f}<extra></extra>",
                )
            )
        if _stress_value(scenario) is not None:
            fig.add_trace(
                go.Scatter(
                    x=[anchor_x, horizon_x],
                    y=[anchor_value, _stress_value(scenario)],
                    mode="lines",
                    name="Stress",
                    line={"color": "#7c1f1f", "width": 1.5, "dash": "dot"},
                    hovertemplate="%{x|%b %Y}<br>Stress: %{y:$,.0f}<extra></extra>",
                )
            )

    fig.add_shape(
        type="line",
        x0=anchor_x,
        x1=anchor_x,
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line={"dash": "dot", "color": ACCENT_ORANGE, "width": 1.5},
    )
    fig.add_annotation(
        x=anchor_x,
        y=1.02,
        xref="x",
        yref="paper",
        text="Today",
        showarrow=False,
        font={"color": ACCENT_ORANGE, "size": 11},
        xanchor="left",
    )

    layout = dict(PLOTLY_LAYOUT)
    layout["height"] = 360
    layout["margin"] = {"l": 48, "r": 20, "t": 20, "b": 48}
    layout["legend"] = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": -0.24,
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXT_SECONDARY, "size": 11},
    }
    layout["xaxis"] = {
        **layout.get("xaxis", {}),
        "title": "",
        "showgrid": False,
        "tickformat": "%Y",
    }
    layout["yaxis"] = {
        **layout.get("yaxis", {}),
        "tickformat": "$,.0f",
        "gridcolor": BG_SURFACE_4,
    }
    fig.update_layout(**layout)

    return {
        "figure": fig,
        "diagnostic_note": diagnostic_note,
        "fallback_note": fallback_note,
    }


def _extract_market_history_points(report: AnalysisReport) -> list[dict[str, object]]:
    history = get_market_value_history(report)
    points: list[dict[str, object]] = []
    for point in history.points:
        parsed_date = _parse_date(point.date)
        if parsed_date is None:
            continue
        points.append({"date": parsed_date, "value": float(point.value)})
    return points


def _extract_property_history_points(report: AnalysisReport) -> list[dict[str, object]]:
    property_input = report.property_input
    if property_input is None:
        return []

    raw_entries: list[dict[str, object]] = []
    raw_entries.extend(list(property_input.price_history or []))
    if property_input.facts is not None:
        raw_entries.extend(list(property_input.facts.sale_history or []))

    points: list[dict[str, object]] = []
    seen: set[tuple[date, float, str]] = set()
    for entry in raw_entries:
        parsed_date = _parse_date(entry.get("date") or entry.get("sale_date"))
        value = _coerce_float(entry.get("price") or entry.get("sale_price") or entry.get("list_price"))
        if parsed_date is None or value is None:
            continue
        event = str(entry.get("event") or entry.get("status") or "Price event")
        label = "Sale" if "sold" in event.lower() or "sale" in event.lower() else "List"
        key = (parsed_date, value, label)
        if key in seen:
            continue
        seen.add(key)
        points.append(
            {
                "date": parsed_date,
                "value": value,
                "event": event,
                "label": label,
                "symbol": "diamond" if label == "Sale" else "circle",
            }
        )

    return sorted(points, key=lambda point: point["date"])


def _parse_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _coerce_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _currency(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


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

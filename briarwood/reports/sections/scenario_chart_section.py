from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

from briarwood.reports.section_helpers import (
    get_current_value,
    get_market_value_history,
    get_scenario_output,
    get_valuation_output,
)
from briarwood.reports.schemas import ScenarioChartSection, ScenarioFanBand, ScenarioPoint
from briarwood.schemas import AnalysisReport


def build_scenario_chart_section(report: AnalysisReport) -> ScenarioChartSection:
    valuation = get_valuation_output(report)
    current_value = get_current_value(report)
    scenario = get_scenario_output(report)
    history = get_market_value_history(report)

    ask_price = valuation.purchase_price
    briarwood_current_value = current_value.briarwood_current_value
    market_reference_value = history.current_value or ask_price
    market_reference_label = (
        f"Current Zillow Market ({history.geography_name})"
        if history.current_value is not None
        else "Current Market Marker"
    )

    bear_value = scenario.bear_case_value
    base_value = scenario.base_case_value
    bull_value = scenario.bull_case_value
    plot_html = _build_plotly_chart(
        history=history,
        current_ask=ask_price,
        current_value=briarwood_current_value,
        market_reference_value=market_reference_value,
        bear_value=bear_value,
        base_value=base_value,
        bull_value=bull_value,
    )
    secondary_plot_html = _build_plotly_scenario_zoom_chart(
        current_ask=ask_price,
        current_value=briarwood_current_value,
        market_reference_value=market_reference_value,
        bear_value=bear_value,
        base_value=base_value,
        bull_value=bull_value,
        stress_value=scenario.stress_case_value,
    )

    history_years = len(history.points)
    return ScenarioChartSection(
        chart_title="Historic Market Context and Forward Value Range",
        secondary_chart_title="12M Scenario Spread",
        current_ask=ask_price,
        current_value_label="Briarwood Current Value",
        current_value=briarwood_current_value,
        market_reference_label=market_reference_label,
        market_reference_value=market_reference_value,
        forward_year_label="12M outlook",
        forward_base_value=base_value,
        fan_bands=[
            ScenarioFanBand(label="Bull", value=bull_value),
            ScenarioFanBand(label="Base", value=base_value),
            ScenarioFanBand(label="Bear", value=bear_value),
        ],
        points=[
            ScenarioPoint(label="Ask", value=ask_price),
            ScenarioPoint(label="BCV", value=briarwood_current_value),
            ScenarioPoint(label="Market Reference", value=market_reference_value),
            ScenarioPoint(label="Bear", value=bear_value),
            ScenarioPoint(label="Base", value=base_value),
            ScenarioPoint(label="Bull", value=bull_value),
        ],
        plot_html=plot_html,
        secondary_plot_html=secondary_plot_html,
        caption=(
            f"BCV anchors today; the fan shows the 12-month range."
        ),
    )


def _build_plotly_chart(
    *,
    history: object,
    current_ask: float,
    current_value: float,
    market_reference_value: float,
    bear_value: float,
    base_value: float,
    bull_value: float,
) -> str:
    historical_dates = [point.date for point in history.points]
    historical_values = [point.value for point in history.points]

    if historical_dates:
        last_date = date.fromisoformat(historical_dates[-1])
    else:
        last_date = date.today()
        historical_dates = [last_date.isoformat()]
        historical_values = [market_reference_value]
    forward_date = date(last_date.year + 1, last_date.month, min(last_date.day, 28)).isoformat()
    base_pct_vs_bcv = _pct_change(base_value, current_value)
    bull_pct_vs_bcv = _pct_change(bull_value, current_value)
    bear_pct_vs_bcv = _pct_change(bear_value, current_value)
    history_fill = _history_fill_values(historical_values)
    chart_values = historical_values + [
        current_ask,
        current_value,
        market_reference_value,
        bear_value,
        base_value,
        bull_value,
    ]
    y_min = min(chart_values) * 0.82
    y_max = max(chart_values) * 1.18
    divider_label_y = y_max * 0.985
    target_annotations = _target_probability_annotations(
        current_value=current_value,
        bear_value=bear_value,
        base_value=base_value,
        bull_value=bull_value,
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=historical_dates,
            y=history_fill,
            mode="lines",
            name="Historic Market Context",
            line={"color": "rgba(191,197,205,0.0)", "width": 0},
            fill="tozeroy",
            fillcolor="rgba(191,197,205,0.24)",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=historical_dates,
            y=historical_values,
            mode="lines",
            name="Historic Market Value",
            line={"color": "#2a9fe8", "width": 4},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1], forward_date, forward_date, historical_dates[-1]],
            y=[current_value, bull_value, bear_value, current_value],
            mode="lines",
            line={"color": "rgba(110,173,224,0.0)", "width": 0},
            fill="toself",
            fillcolor="rgba(137,191,244,0.40)",
            hoverinfo="skip",
            showlegend=False,
            name="Forward Fan",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1], forward_date],
            y=[current_value, base_value],
            mode="lines",
            name="Base Case",
            line={"color": "#2b2b2b", "width": 2.5},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[forward_date, forward_date],
            y=[bull_value, bear_value],
            mode="lines",
            line={"color": "rgba(67,82,95,0.45)", "width": 2, "dash": "dash"},
            hoverinfo="skip",
            showlegend=False,
            name="Target Range",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[forward_date],
            y=[bull_value],
            mode="markers",
            name="Bull Case",
            marker={"size": 10, "symbol": "diamond", "color": "#1f2937"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[forward_date],
            y=[base_value],
            mode="markers",
            name="Base Target",
            marker={"size": 10, "symbol": "diamond", "color": "#1f2937"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[forward_date],
            y=[bear_value],
            mode="markers",
            name="Bear Case",
            marker={"size": 10, "symbol": "diamond", "color": "#1f2937"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1]],
            y=[current_value],
            mode="markers",
            name="Current BCV",
            marker={"size": 12, "symbol": "circle", "color": "#ff5a3c", "line": {"width": 3, "color": "#fffdf8"}},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1]],
            y=[current_ask],
            mode="markers",
            name="Current Ask",
            marker={"size": 10, "symbol": "diamond", "color": "#17212b"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1]],
            y=[market_reference_value],
            mode="markers",
            name="Current Market",
            marker={"size": 9, "symbol": "circle", "color": "#8b7c67"},
        )
    )
    fig.add_vline(x=historical_dates[-1], line_color="#ff5a3c", line_width=2)
    fig.update_layout(
        template="plotly_white",
        margin={"l": 18, "r": 50, "t": 18, "b": 22},
        height=430,
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.20, "x": 0},
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",
        xaxis={
            "title": "",
            "showgrid": False,
        },
        yaxis={
            "title": "",
            "tickprefix": "$",
            "separatethousands": True,
            "gridcolor": "#e4dbc9",
            "zeroline": False,
            "range": [y_min, y_max],
        },
        annotations=[
            {
                "x": historical_dates[-1],
                "y": divider_label_y,
                "text": "Today",
                "font": {"color": "#ff5a3c", "size": 12},
                "showarrow": False,
                "xanchor": "right",
                "yanchor": "top",
                "xshift": -8,
            },
            {
                "x": historical_dates[-1],
                "y": current_value,
                "text": f"${current_value:,.0f}",
                "font": {"color": "#ff5a3c", "size": 15},
                "showarrow": False,
                "xanchor": "right",
                "yanchor": "bottom",
                "xshift": -10,
            },
            {
                "x": forward_date,
                "y": bull_value,
                "text": f"${bull_value:,.0f} ({bull_pct_vs_bcv:+.1%})",
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "middle",
                "xshift": 12,
                "font": {"size": 13, "color": "#57534e"},
            },
            {
                "x": forward_date,
                "y": base_value,
                "text": f"${base_value:,.0f} ({base_pct_vs_bcv:+.1%})",
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "middle",
                "xshift": 12,
                "font": {"size": 13, "color": "#111827"},
            },
            {
                "x": forward_date,
                "y": bear_value,
                "text": f"${bear_value:,.0f} ({bear_pct_vs_bcv:+.1%})",
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "middle",
                "xshift": 12,
                "font": {"size": 13, "color": "#6b7280"},
            },
            {
                "x": forward_date,
                "y": bull_value,
                "text": target_annotations["bull"],
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "middle",
                "xshift": 152,
                "font": {"size": 12, "color": "#4b5563"},
            },
            {
                "x": forward_date,
                "y": base_value,
                "text": target_annotations["base"],
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "middle",
                "xshift": 152,
                "font": {"size": 12, "color": "#374151"},
            },
            {
                "x": forward_date,
                "y": bear_value,
                "text": target_annotations["bear"],
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "middle",
                "xshift": 152,
                "font": {"size": 12, "color": "#6b7280"},
            },
        ],
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})


def _build_plotly_scenario_zoom_chart(
    *,
    current_ask: float,
    current_value: float,
    market_reference_value: float,
    bear_value: float,
    base_value: float,
    bull_value: float,
    stress_value: float | None = None,
) -> str:
    current_label = "Today"
    future_label = "12M"
    bull_pct_vs_bcv = _pct_change(bull_value, current_value)
    base_pct_vs_bcv = _pct_change(base_value, current_value)
    bear_pct_vs_bcv = _pct_change(bear_value, current_value)
    values = [current_ask, current_value, market_reference_value, bear_value, base_value, bull_value]
    if stress_value:
        values.append(stress_value)
    y_min = min(values) * 0.82
    y_max = max(values) * 1.18
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[current_label, future_label, future_label, current_label],
            y=[current_value, bull_value, bear_value, current_value],
            mode="lines",
            line={"color": "rgba(137,191,244,0.0)", "width": 0},
            fill="toself",
            fillcolor="rgba(137,191,244,0.50)",
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[current_label, future_label],
            y=[current_value, base_value],
            mode="lines",
            line={"color": "#2b2b2b", "width": 2.5},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[future_label, future_label],
            y=[bull_value, bear_value],
            mode="lines",
            line={"color": "rgba(67,82,95,0.50)", "width": 2, "dash": "dash"},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[current_label],
            y=[current_value],
            mode="markers",
            marker={"size": 12, "symbol": "circle", "color": "#ff5a3c", "line": {"width": 3, "color": "#fffdf8"}},
            name="Current BCV",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[future_label, future_label, future_label],
            y=[bull_value, base_value, bear_value],
            mode="markers",
            marker={"size": 10, "symbol": "diamond", "color": "#1f2937"},
            name="Price Target",
            showlegend=False,
        )
    )
    if stress_value is not None:
        stress_pct = _pct_change(stress_value, current_value)
        fig.add_trace(
            go.Scatter(
                x=[future_label],
                y=[stress_value],
                mode="markers",
                marker={"size": 10, "symbol": "x", "color": "#dc2626"},
                name="Stress",
                showlegend=False,
            )
        )
    zoom_annotations = [
        {
            "x": current_label,
            "y": current_value,
            "text": f"${current_value:,.0f}",
            "showarrow": False,
            "font": {"color": "#ff5a3c", "size": 15},
            "xanchor": "left",
            "xshift": 6,
        },
        {
            "x": current_label,
            "y": y_max * 0.985,
            "text": "Today",
            "showarrow": False,
            "font": {"color": "#ff5a3c", "size": 12},
            "xanchor": "center",
            "yanchor": "top",
        },
        {
            "x": future_label,
            "y": bull_value,
            "text": f"Bull ${bull_value:,.0f} ({bull_pct_vs_bcv:+.1%})",
            "showarrow": False,
            "xanchor": "left",
            "xshift": 10,
            "font": {"size": 13, "color": "#57534e"},
        },
        {
            "x": future_label,
            "y": base_value,
            "text": f"Base ${base_value:,.0f} ({base_pct_vs_bcv:+.1%})",
            "showarrow": False,
            "xanchor": "left",
            "xshift": 10,
            "font": {"size": 13, "color": "#111827"},
        },
        {
            "x": future_label,
            "y": bear_value,
            "text": f"Bear ${bear_value:,.0f} ({bear_pct_vs_bcv:+.1%})",
            "showarrow": False,
            "xanchor": "left",
            "xshift": 10,
            "font": {"size": 13, "color": "#6b7280"},
        },
        {
            "x": current_label,
            "y": current_ask,
            "text": f"Ask ${current_ask:,.0f}",
            "showarrow": False,
            "xanchor": "right",
            "xshift": -10,
            "font": {"size": 12, "color": "#111827"},
        },
        {
            "x": current_label,
            "y": market_reference_value,
            "text": f"Market ${market_reference_value:,.0f}",
            "showarrow": False,
            "xanchor": "right",
            "xshift": -10,
            "font": {"size": 12, "color": "#8b7c67"},
        },
    ]
    if stress_value is not None:
        zoom_annotations.append(
            {
                "x": future_label,
                "y": stress_value,
                "text": f"Stress ${stress_value:,.0f} ({stress_pct:+.1%})",
                "showarrow": False,
                "xanchor": "left",
                "xshift": 10,
                "font": {"size": 12, "color": "#dc2626"},
            }
        )
    fig.update_layout(
        template="plotly_white",
        margin={"l": 18, "r": 34, "t": 18, "b": 22},
        height=430,
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",
        xaxis={"title": "", "showgrid": False},
        yaxis={
            "title": "",
            "tickprefix": "$",
            "separatethousands": True,
            "gridcolor": "#e4dbc9",
            "zeroline": False,
            "range": [y_min, y_max],
        },
        annotations=zoom_annotations,
        shapes=[
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": current_label,
                "x1": current_label,
                "y0": 0,
                "y1": 1,
                "line": {"color": "#ff5a3c", "width": 2},
            }
        ],
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def _pct_change(target_value: float, base_value: float) -> float:
    if base_value == 0:
        return 0.0
    return (target_value / base_value) - 1


def _history_fill_values(historical_values: list[float]) -> list[float]:
    if not historical_values:
        return []
    min_value = min(historical_values)
    return [max(min_value * 0.58, value * 0.62) for value in historical_values]


def _target_probability_annotations(
    *,
    current_value: float,
    bear_value: float,
    base_value: float,
    bull_value: float,
) -> dict[str, str]:
    bull_gap = max(bull_value - current_value, 0.0)
    base_gap = abs(base_value - current_value)
    bear_gap = max(current_value - bear_value, 0.0)
    gap_scale = max(current_value * 0.22, 1.0)

    bull_prob = max(0.08, 0.62 - (bull_gap / gap_scale) * 0.12)
    base_prob = max(0.20, 0.82 - (base_gap / gap_scale) * 0.08)
    bear_prob = max(0.10, 0.58 - (bear_gap / gap_scale) * 0.11)

    return {
        "bull": f"Prob (>{bull_value:,.0f}) ~{bull_prob:.0%}",
        "base": f"Prob (~{base_value:,.0f}) ~{base_prob:.0%}",
        "bear": f"Prob (<{bear_value:,.0f}) ~{bear_prob:.0%}",
    }

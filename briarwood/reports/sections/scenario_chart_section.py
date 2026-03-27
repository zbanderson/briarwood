from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

from briarwood.reports.section_helpers import (
    get_market_value_history,
    get_scenario_output,
    get_valuation_output,
)
from briarwood.reports.schemas import ScenarioChartSection, ScenarioFanBand, ScenarioPoint
from briarwood.schemas import AnalysisReport


def build_scenario_chart_section(report: AnalysisReport) -> ScenarioChartSection:
    valuation = get_valuation_output(report)
    scenario = get_scenario_output(report)
    history = get_market_value_history(report)

    ask_price = valuation.purchase_price
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
        market_reference_value=market_reference_value,
        bear_value=bear_value,
        base_value=base_value,
        bull_value=bull_value,
    )

    history_years = len(history.points)
    return ScenarioChartSection(
        chart_title="Historic Market Context and Forward Value Range",
        current_ask=ask_price,
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
            ScenarioPoint(label="Market Reference", value=market_reference_value),
            ScenarioPoint(label="Bear", value=bear_value),
            ScenarioPoint(label="Base", value=base_value),
            ScenarioPoint(label="Bull", value=bull_value),
        ],
        plot_html=plot_html,
        caption=(
            f"This chart uses {history_years} historical Zillow-style market value points to anchor the left side, "
            "then extends into a 12-month forward fan for the bull, base, and bear view. "
            "The historical series is market-level context, not a property-specific Zestimate history."
        ),
    )


def _build_plotly_chart(
    *,
    history: object,
    current_ask: float,
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

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=historical_dates,
            y=historical_values,
            mode="lines+markers",
            name="Historic Market Value",
            line={"color": "#8b7c67", "width": 3},
            marker={"size": 6},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1], forward_date],
            y=[market_reference_value, bull_value],
            mode="lines",
            line={"color": "rgba(59,127,95,0.0)", "width": 0},
            hoverinfo="skip",
            showlegend=False,
            name="Bull Ceiling",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1], forward_date],
            y=[market_reference_value, bear_value],
            mode="lines",
            line={"color": "rgba(177,77,59,0.0)", "width": 0},
            fill="tonexty",
            fillcolor="rgba(47,97,115,0.14)",
            hoverinfo="skip",
            showlegend=False,
            name="Forward Range",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1], forward_date],
            y=[market_reference_value, base_value],
            mode="lines+markers",
            name="Base Case",
            line={"color": "#2f6173", "width": 4},
            marker={"size": 7},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1], forward_date],
            y=[market_reference_value, bull_value],
            mode="lines+markers",
            name="Bull Case",
            line={"color": "#3b7f5f", "width": 3, "dash": "dash"},
            marker={"size": 7},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1], forward_date],
            y=[market_reference_value, bear_value],
            mode="lines+markers",
            name="Bear Case",
            line={"color": "#b14d3b", "width": 3, "dash": "dash"},
            marker={"size": 7},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[historical_dates[-1]],
            y=[current_ask],
            mode="markers",
            name="Current Ask",
            marker={"size": 11, "symbol": "diamond", "color": "#17212b"},
        )
    )
    fig.update_layout(
        template="plotly_white",
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=380,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#fffdf8",
        xaxis={
            "title": "",
            "showgrid": False,
        },
        yaxis={
            "title": "Value",
            "tickprefix": "$",
            "separatethousands": True,
            "gridcolor": "#e4dbc9",
            "zeroline": False,
        },
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})

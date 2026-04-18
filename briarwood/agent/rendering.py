"""Chart-on-demand rendering for the CLI agent.

Builds lightweight Plotly figures from a ``UnifiedIntelligenceOutput`` dict
and writes standalone HTML (always) or PNG (if ``kaleido`` is installed) to
``data/agent_artifacts/{session_id}/``. Returns the absolute path.

Scope: rebuild the handful of charts the decision flow actually needs.
Pixel-parity with the legacy Dash dashboard is not a goal — these are
answer-shaped visuals meant to be opened in a browser from the CLI.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

try:  # pragma: no cover - environment-specific optional dependency
    import plotly.graph_objects as go
except ModuleNotFoundError:  # pragma: no cover - exercised via import-only tests
    go = None

ARTIFACTS_ROOT = Path("data/agent_artifacts")

SUPPORTED_KINDS = {
    # Legacy answer-shaped kinds — kept for existing callers.
    "verdict_gauge",
    "value_opportunity",
    "scenario_fan",
    "risk_bar",
    "rent_burn",
    # Architecture-diagram visualization-shaped kinds (Layer 05 chart router).
    "line_area",
    "bar_compare",
    "geo_map",
    "radar_score",
}


class ChartUnavailable(Exception):
    """Raised when the requested chart cannot be produced from the given payload."""


def render_chart(
    kind: str,
    unified_output: dict[str, Any],
    *,
    session_id: str = "default",
    fmt: str = "html",
) -> Path:
    """Render a chart and return the artifact path.

    ``fmt`` may be ``"html"`` (always works) or ``"png"`` (requires kaleido).
    """
    if go is None:
        raise ChartUnavailable("plotly is not installed")
    if kind not in SUPPORTED_KINDS:
        raise ChartUnavailable(f"Unsupported chart kind '{kind}'. Supported: {sorted(SUPPORTED_KINDS)}")
    if fmt not in {"html", "png"}:
        raise ChartUnavailable(f"Unsupported format '{fmt}'. Use 'html' or 'png'.")

    fig = _build_figure(kind, unified_output)
    out_dir = ARTIFACTS_ROOT / session_id
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"{timestamp}-{kind}.{fmt}"

    if fmt == "html":
        fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True)
    else:
        try:
            fig.write_image(str(out_path))
        except Exception as exc:
            raise ChartUnavailable(
                f"PNG export failed (install kaleido with `pip install kaleido`): {exc}"
            ) from exc
    return out_path


def _build_figure(kind: str, unified: dict[str, Any]) -> go.Figure:
    if kind == "verdict_gauge":
        return _verdict_gauge(unified)
    if kind == "value_opportunity":
        return _value_opportunity(unified)
    if kind == "scenario_fan":
        return _scenario_fan(unified)
    if kind == "risk_bar":
        return _risk_bar(unified)
    if kind == "rent_burn":
        return _rent_burn(unified)
    if kind == "line_area":
        return _line_area(unified)
    if kind == "bar_compare":
        return _bar_compare(unified)
    if kind == "geo_map":
        return _geo_map(unified)
    if kind == "radar_score":
        return _radar_score(unified)
    raise ChartUnavailable(f"No builder for kind '{kind}'")  # pragma: no cover


def _line_area(payload: dict[str, Any]) -> go.Figure:
    """Generic time series / projection chart (Layer 05 chart kind)."""
    series = payload.get("series") or []
    ask = payload.get("ask_price")
    bull = payload.get("bull_case_value")
    bear = payload.get("bear_case_value")
    if not series and isinstance(ask, (int, float)) and isinstance(bull, (int, float)):
        years = list(range(6))
        base_path = [ask + (bull - ask) * (y / 5) for y in years]
        bear_path = [ask + ((bear or ask) - ask) * (y / 5) for y in years]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=years, y=base_path, mode="lines", name="Base"))
        fig.add_trace(go.Scatter(x=years, y=bear_path, mode="lines", name="Bear",
                                 fill="tonexty", fillcolor="rgba(25,118,210,0.08)"))
        fig.update_layout(title="Projected value", xaxis_title="Years",
                          yaxis_title="Value ($)", height=320)
        return fig
    if not series:
        raise ChartUnavailable("line_area requires `series` or projection values.")
    fig = go.Figure()
    for name, values in (series.items() if isinstance(series, dict) else []):
        fig.add_trace(go.Scatter(y=list(values), mode="lines", name=str(name), fill="tozeroy"))
    fig.update_layout(title="Trend", height=320)
    return fig


def _bar_compare(payload: dict[str, Any]) -> go.Figure:
    """Side-by-side comparison chart (Layer 05 chart kind)."""
    items = payload.get("items")
    if isinstance(items, dict):
        labels = list(items.keys())
        values = [float(v) if isinstance(v, (int, float)) else 0.0 for v in items.values()]
    elif isinstance(items, list):
        labels = [str(i.get("label")) for i in items if isinstance(i, dict)]
        values = [float(i.get("value") or 0) for i in items if isinstance(i, dict)]
    else:
        raise ChartUnavailable("bar_compare requires `items` as dict or list of {label, value}.")
    if not labels:
        raise ChartUnavailable("bar_compare has no items to plot.")
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color="#1976d2"))
    fig.update_layout(title=payload.get("title") or "Comparison", height=340)
    return fig


def _geo_map(payload: dict[str, Any]) -> go.Figure:
    """Scatter-geo / map visualization (Layer 05 chart kind).

    Expects a `points` list of {lat, lon, label?, score?}. Falls back to a
    placeholder figure when coordinates are not available.
    """
    points = payload.get("points") or []
    if not points:
        fig = go.Figure()
        fig.add_annotation(text="No geocoded points available",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(title="Location", height=320)
        return fig
    lats = [p.get("lat") for p in points if isinstance(p, dict)]
    lons = [p.get("lon") for p in points if isinstance(p, dict)]
    labels = [str(p.get("label") or "") for p in points if isinstance(p, dict)]
    fig = go.Figure(go.Scattergeo(lat=lats, lon=lons, text=labels, mode="markers"))
    fig.update_geos(fitbounds="locations")
    fig.update_layout(title=payload.get("title") or "Location", height=360)
    return fig


def _radar_score(payload: dict[str, Any]) -> go.Figure:
    """Radar / polar multi-factor score chart (Layer 05 chart kind)."""
    factors = payload.get("factors")
    if isinstance(factors, dict):
        labels = list(factors.keys())
        values = [float(v) if isinstance(v, (int, float)) else 0.0 for v in factors.values()]
    else:
        raise ChartUnavailable("radar_score requires `factors` dict of name→score.")
    if not labels:
        raise ChartUnavailable("radar_score has no factors.")
    # Close the polygon
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]
    fig = go.Figure(go.Scatterpolar(r=values_closed, theta=labels_closed, fill="toself"))
    fig.update_layout(title=payload.get("title") or "Fit index",
                      polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                      height=360)
    return fig


_RISK_FLAG_LABELS = {
    "older_housing_stock": "Older housing stock",
    "long_marketing_period": "Long marketing period",
    "flood_zone": "Flood exposure",
    "high_vacancy": "High vacancy",
    "weak_town_context": "Weak town context",
    "valuation_anchor_divergence": "Valuation anchors diverge",
    "incomplete_carry_inputs": "Incomplete carry inputs",
    "zoning_unverified": "Zoning unverified",
    "thin_comp_set": "Thin comp set",
}


def _risk_bar(payload: dict[str, Any]) -> go.Figure:
    """Horizontal bar of risk drivers. Input: dict from get_risk_profile."""
    risk_flags = payload.get("risk_flags") or []
    trust_flags = payload.get("trust_flags") or []
    total_penalty = payload.get("total_penalty") or 0
    ask = payload.get("ask_price")
    bear = payload.get("bear_case_value")
    stress = payload.get("stress_case_value")

    rows: list[tuple[str, float, str]] = []
    # Risk-model flags get proportional slice of total_penalty
    if risk_flags and total_penalty:
        per = float(total_penalty) / max(len(risk_flags), 1)
        for flag in risk_flags:
            rows.append((_RISK_FLAG_LABELS.get(flag, flag.replace("_", " ").title()), per, "#c62828"))
    # Trust flags at a fixed smaller weight
    for tf in trust_flags:
        rows.append((_RISK_FLAG_LABELS.get(tf, tf.replace("_", " ").title()), 8.0, "#f57f17"))
    if not rows:
        raise ChartUnavailable("no risk drivers to plot.")

    rows.sort(key=lambda r: r[1])  # ascending so largest sits at top of h-bar
    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]
    colors = [r[2] for r in rows]

    subtitle_parts = []
    if isinstance(ask, (int, float)) and isinstance(bear, (int, float)):
        subtitle_parts.append(f"bear ${bear:,.0f} vs ask ${ask:,.0f}")
    if isinstance(stress, (int, float)):
        subtitle_parts.append(f"stress ${stress:,.0f}")
    subtitle = " · ".join(subtitle_parts) or "risk drivers ranked by penalty weight"

    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h",
            marker=dict(color=colors),
            text=[f"{v:.1f}" for v in values],
            textposition="outside",
            hovertemplate="%{y}: %{x:.1f} penalty<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"Risk drivers<br><sub>{subtitle}</sub>", x=0, xanchor="left"),
        xaxis=dict(title="Penalty weight"),
        yaxis=dict(automargin=True),
        height=max(320, 60 + 40 * len(rows)),
        margin=dict(t=70, b=50, l=40, r=60),
        showlegend=False,
    )
    return fig


def _scenario_fan(projection: dict[str, Any]) -> go.Figure:
    """Fan chart: bull / base / bear paths projected from ask over 5 years.

    Input is the dict returned by ``get_projection`` (or any dict with
    ask_price, bull_case_value, base_case_value, bear_case_value).
    """
    ask = projection.get("ask_price")
    bull = projection.get("bull_case_value")
    base = projection.get("base_case_value")
    bear = projection.get("bear_case_value")
    stress = projection.get("stress_case_value")
    if not isinstance(ask, (int, float)) or not any(isinstance(v, (int, float)) for v in (bull, base, bear)):
        raise ChartUnavailable("projection requires ask_price and at least one scenario value.")

    years = [0, 1, 2, 3, 4, 5]
    def _path(target):
        t = target if isinstance(target, (int, float)) else ask
        return [ask + (t - ask) * (y / 5) for y in years]

    fig = go.Figure()
    # Uncertainty band between bull and bear
    if isinstance(bull, (int, float)) and isinstance(bear, (int, float)):
        fig.add_trace(go.Scatter(x=years, y=_path(bull), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=years, y=_path(bear), mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor="rgba(25, 118, 210, 0.08)",
            showlegend=False, hoverinfo="skip",
        ))
    if isinstance(bull, (int, float)):
        fig.add_trace(go.Scatter(x=years, y=_path(bull), mode="lines+markers", name=f"Bull ${bull:,.0f}",
                                 line=dict(color="#2e7d32", width=2, dash="dot"), marker=dict(size=5)))
    if isinstance(base, (int, float)):
        fig.add_trace(go.Scatter(x=years, y=_path(base), mode="lines+markers", name=f"Base ${base:,.0f}",
                                 line=dict(color="#1976d2", width=2.5), marker=dict(size=6)))
    if isinstance(bear, (int, float)):
        fig.add_trace(go.Scatter(x=years, y=_path(bear), mode="lines+markers", name=f"Bear ${bear:,.0f}",
                                 line=dict(color="#c62828", width=2, dash="dot"), marker=dict(size=5)))
    if isinstance(stress, (int, float)):
        fig.add_trace(go.Scatter(x=years, y=_path(stress), mode="lines", name=f"Stress ${stress:,.0f}",
                                 line=dict(color="#6d4c41", width=1.5, dash="dashdot")))

    fig.add_hline(y=ask, line=dict(color="#9e9e9e", width=1, dash="dash"),
                  annotation_text=f"Ask ${ask:,.0f}", annotation_position="bottom left",
                  annotation_font=dict(color="#616161", size=10))

    fig.update_layout(
        title=dict(text="5-year projection — bull / base / bear", x=0, xanchor="left"),
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(title="Value", tickformat="$,.0f"),
        height=380, margin=dict(t=60, b=50, l=70, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _rent_burn(payload: dict[str, Any]) -> go.Figure:
    """Rent burn chart from a rent outlook burn payload."""
    points = list(payload.get("series") or [])
    if not points:
        raise ChartUnavailable("rent_burn requires `series` points.")
    years = [point.get("year") for point in points]
    base = [point.get("rent_base") for point in points]
    bull = [point.get("rent_bull") for point in points]
    bear = [point.get("rent_bear") for point in points]
    obligation = [point.get("monthly_obligation") for point in points]
    if not any(isinstance(value, (int, float)) for value in base):
        raise ChartUnavailable("rent_burn requires at least one rent series.")

    fig = go.Figure()
    if any(isinstance(v, (int, float)) for v in bull) and any(isinstance(v, (int, float)) for v in bear):
        fig.add_trace(go.Scatter(x=years, y=bull, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(
            go.Scatter(
                x=years,
                y=bear,
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(25, 118, 210, 0.08)",
                showlegend=False,
                hoverinfo="skip",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=base,
            mode="lines+markers",
            name="Rent base",
            line=dict(color="#1976d2", width=2.5),
            marker=dict(size=6),
        )
    )
    if any(isinstance(v, (int, float)) for v in obligation):
        fig.add_trace(
            go.Scatter(
                x=years,
                y=obligation,
                mode="lines",
                name="Monthly obligation",
                line=dict(color="#c62828", width=2, dash="dash"),
            )
        )
    fig.update_layout(
        title=dict(text=payload.get("title") or "Rent burn chart", x=0, xanchor="left"),
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(title="Monthly dollars", tickformat="$,.0f"),
        height=360,
        margin=dict(t=60, b=50, l=70, r=40),
    )
    return fig


def _verdict_gauge(unified: dict[str, Any]) -> go.Figure:
    vp = unified.get("value_position") or {}
    premium = vp.get("premium_discount_pct")
    if not isinstance(premium, (int, float)):
        raise ChartUnavailable("value_position.premium_discount_pct is missing — can't build verdict gauge.")

    pct = premium * 100  # positive = above fair, negative = below
    # Color: red when premium > 5%, green when discount > 5%, amber in between.
    color = "#2e7d32" if pct <= -5 else "#c62828" if pct >= 5 else "#f57f17"
    stance = unified.get("decision_stance")
    if hasattr(stance, "value"):
        stance = stance.value

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=pct,
            number={"suffix": "%", "valueformat": ".1f"},
            delta={"reference": 0, "increasing": {"color": "#c62828"}, "decreasing": {"color": "#2e7d32"}},
            title={"text": f"Premium vs. fair value<br><sub>stance: {stance or 'n/a'}</sub>"},
            gauge={
                "axis": {"range": [-25, 25], "ticksuffix": "%"},
                "bar": {"color": color},
                "steps": [
                    {"range": [-25, -5], "color": "#e8f5e9"},
                    {"range": [-5, 5], "color": "#fff8e1"},
                    {"range": [5, 25], "color": "#ffebee"},
                ],
                "threshold": {"line": {"color": "black", "width": 3}, "thickness": 0.75, "value": 0},
            },
        )
    )
    fig.update_layout(margin=dict(t=60, b=20, l=20, r=20), height=360)
    return fig


def _value_opportunity(unified: dict[str, Any]) -> go.Figure:
    vp = unified.get("value_position") or {}
    ask = vp.get("ask_price")
    fair = vp.get("fair_value_base")
    low = vp.get("value_low")
    high = vp.get("value_high")
    if not isinstance(ask, (int, float)) or not isinstance(fair, (int, float)):
        raise ChartUnavailable("value_position requires ask_price and fair_value_base.")

    fig = go.Figure()
    # Range band (if we have low/high)
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        fig.add_shape(
            type="rect",
            x0=low, x1=high, y0=0.6, y1=1.4,
            fillcolor="#e3f2fd", line=dict(width=0), layer="below",
        )
        fig.add_annotation(
            x=(low + high) / 2, y=1.45, showarrow=False,
            text=f"Fair range ${low:,.0f}–${high:,.0f}",
            font=dict(size=11, color="#555"),
        )

    fig.add_trace(go.Scatter(
        x=[fair], y=[1], mode="markers+text",
        marker=dict(size=22, color="#1976d2", symbol="diamond"),
        text=[f"Fair ${fair:,.0f}"], textposition="top center",
        name="Fair value",
    ))
    fig.add_trace(go.Scatter(
        x=[ask], y=[1], mode="markers+text",
        marker=dict(size=22, color="#c62828", symbol="triangle-down"),
        text=[f"Ask ${ask:,.0f}"], textposition="bottom center",
        name="Ask price",
    ))

    stance = unified.get("decision_stance")
    if hasattr(stance, "value"):
        stance = stance.value
    flags = unified.get("trust_flags") or []

    fig.update_layout(
        title=dict(
            text=f"Value picture — stance: {stance}<br><sub>flags: {', '.join(flags) or 'none'}</sub>",
            x=0, xanchor="left",
        ),
        xaxis=dict(title="Price ($)", tickformat="$,.0f"),
        yaxis=dict(visible=False, range=[0.3, 1.7]),
        showlegend=False,
        height=320,
        margin=dict(t=70, b=50, l=60, r=40),
    )
    return fig

"""Visual-first components — Tufte-inspired, data-ink maximising.

Every component renders a *visual element* (gauge, bar, strip, chart)
rather than a text label with a number next to it.  Metric values appear
in large type; labels in small muted type.  Color is semantic:
green = favorable, amber = mixed, red = unfavorable.

No raw tables in the default view.  Tables are evidence — they live
behind expand/collapse.
"""
from __future__ import annotations

from typing import Any, Sequence

import plotly.graph_objects as go
from dash import dcc, html

from briarwood.dash_app.theme import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_RED,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_SURFACE,
    BORDER,
    BORDER_SUBTLE,
    CARD_STYLE,
    CARD_STYLE_ELEVATED,
    CHART_HEIGHT_COMPACT,
    CHART_HEIGHT_STANDARD,
    FONT_FAMILY,
    FONT_MONO,
    LABEL_STYLE,
    PLOTLY_LAYOUT,
    PLOTLY_LAYOUT_COMPACT,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    SECTION_HEADER_STYLE,
    SHADOW_SOFT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    verdict_color,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _semantic_color(value: float, *, invert: bool = False) -> str:
    """Map a normalised 0-1 value to green/amber/red.

    *invert=True* means higher = worse (e.g. risk scores).
    """
    if invert:
        value = 1.0 - value
    if value >= 0.65:
        return ACCENT_GREEN
    if value >= 0.35:
        return ACCENT_AMBER
    return ACCENT_RED


def _pct(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    if signed:
        return f"{value:+.1%}"
    return f"{value:.0%}"


def _money(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    if signed:
        sign = "+" if value >= 0 else "-"
        return f"{sign}${abs(value):,.0f}"
    return f"${value:,.0f}"


# ═══════════════════════════════════════════════════════════════════════════════
#  1. Metric Spark — tiny inline visual indicator
# ═══════════════════════════════════════════════════════════════════════════════


def metric_spark(
    label: str,
    value_text: str,
    fill_pct: float,
    *,
    color: str | None = None,
    subtitle: str = "",
) -> html.Div:
    """A compact metric with a thin fill-bar underneath.

    fill_pct: 0.0-1.0 — how much of the bar to fill.
    """
    bar_color = color or _semantic_color(fill_pct)
    return html.Div(
        [
            html.Div(label, style={
                "fontSize": "10px", "fontWeight": "600", "color": TEXT_TERTIARY,
                "textTransform": "uppercase", "letterSpacing": "0.06em",
                "marginBottom": "2px",
            }),
            html.Div(value_text, style={
                "fontSize": "18px", "fontWeight": "800", "fontFamily": FONT_MONO,
                "color": bar_color, "lineHeight": "1.2",
            }),
            # Thin fill bar
            html.Div(
                html.Div(style={
                    "width": f"{max(2, min(100, fill_pct * 100)):.0f}%",
                    "height": "100%",
                    "backgroundColor": bar_color,
                    "borderRadius": "2px",
                    "transition": "width 0.4s ease",
                }),
                style={
                    "height": "3px",
                    "backgroundColor": BORDER_SUBTLE,
                    "borderRadius": "2px",
                    "marginTop": "6px",
                    "overflow": "hidden",
                },
            ),
            html.Div(subtitle, style={
                "fontSize": "11px", "color": TEXT_TERTIARY, "marginTop": "3px",
            }) if subtitle else None,
        ],
        style={"minWidth": "100px", "padding": "4px 0"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  2. Verdict Gauge — the hero signal for Section 1
# ═══════════════════════════════════════════════════════════════════════════════


def verdict_gauge(
    recommendation: str,
    conviction: float,
    *,
    fv_gap_pct: float | None = None,
    monthly_carry: float | None = None,
    stabilized_cf: float | None = None,
    confidence: float = 0.0,
    question: str = "Should I buy this?",
    primary_reason: str = "",
    secondary_reason: str = "",
    required_beliefs: list[str] | None = None,
) -> html.Div:
    """Composite verdict signal — readable in under 2 seconds.

    Large verdict + conviction arc, with four supporting metric sparks:
    FV gap, carry, stabilized CF, confidence.
    """
    accent = verdict_color(recommendation)
    conviction_pct = conviction * 100

    # ── Signal interpretation ───────────────────────────────────────────
    # Determine signal class for the ring
    if recommendation in ("BUY", "LEAN BUY"):
        ring_class = "positive"
    elif recommendation in ("LEAN PASS", "AVOID"):
        ring_class = "negative"
    else:
        ring_class = "neutral"

    # ── Conviction ring (CSS conic-gradient arc) ────────────────────────
    ring_bg = {
        "positive": f"conic-gradient({ACCENT_GREEN} {conviction_pct * 3.6}deg, {BORDER_SUBTLE} 0deg)",
        "negative": f"conic-gradient({ACCENT_RED} {conviction_pct * 3.6}deg, {BORDER_SUBTLE} 0deg)",
        "neutral": f"conic-gradient({ACCENT_AMBER} {conviction_pct * 3.6}deg, {BORDER_SUBTLE} 0deg)",
    }[ring_class]

    conviction_ring = html.Div(
        html.Div(
            [
                html.Div(f"{int(conviction_pct)}", style={
                    "fontSize": "32px", "fontWeight": "800", "color": accent,
                    "lineHeight": "1",
                }),
                html.Div("conviction", style={
                    "fontSize": "9px", "fontWeight": "600", "color": TEXT_TERTIARY,
                    "textTransform": "uppercase", "letterSpacing": "0.08em",
                }),
            ],
            style={
                "width": "76px", "height": "76px", "borderRadius": "50%",
                "backgroundColor": BG_SECONDARY,
                "display": "flex", "flexDirection": "column",
                "alignItems": "center", "justifyContent": "center",
            },
        ),
        style={
            "width": "88px", "height": "88px", "borderRadius": "50%",
            "background": ring_bg,
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "flexShrink": "0",
        },
    )

    # ── Four metric sparks ──────────────────────────────────────────────
    sparks: list[html.Div] = []

    # FV vs Ask
    if fv_gap_pct is not None:
        fv_fill = min(1.0, max(0.0, (fv_gap_pct + 0.20) / 0.40))  # -20% to +20% → 0-1
        fv_color = ACCENT_GREEN if fv_gap_pct >= 0.05 else ACCENT_RED if fv_gap_pct < -0.05 else ACCENT_AMBER
        sparks.append(metric_spark(
            "FV vs Ask",
            _pct(fv_gap_pct, signed=True),
            fv_fill,
            color=fv_color,
            subtitle="discount" if fv_gap_pct >= 0 else "premium",
        ))

    # Monthly carry
    if monthly_carry is not None:
        carry_fill = min(1.0, max(0.0, (monthly_carry + 2000) / 4000))  # -2k to +2k → 0-1
        carry_color = ACCENT_GREEN if monthly_carry >= 0 else ACCENT_RED if monthly_carry < -500 else ACCENT_AMBER
        sparks.append(metric_spark(
            "Monthly carry",
            _money(monthly_carry, signed=True),
            carry_fill,
            color=carry_color,
            subtitle="cash flow" if monthly_carry >= 0 else "out of pocket",
        ))

    # Stabilized CF
    if stabilized_cf is not None:
        cf_fill = min(1.0, max(0.0, (stabilized_cf + 1000) / 3000))
        cf_color = ACCENT_GREEN if stabilized_cf >= 0 else ACCENT_RED if stabilized_cf < -300 else ACCENT_AMBER
        sparks.append(metric_spark(
            "Stabilized CF",
            _money(stabilized_cf, signed=True),
            cf_fill,
            color=cf_color,
            subtitle="at full utilization",
        ))

    # Confidence
    if confidence > 0:
        conf_color = ACCENT_GREEN if confidence >= 0.70 else ACCENT_AMBER if confidence >= 0.40 else ACCENT_RED
        sparks.append(metric_spark(
            "Confidence",
            f"{confidence:.0%}",
            confidence,
            color=conf_color,
            subtitle="data quality",
        ))

    # ── Reasons (compact, below sparks) ─────────────────────────────────
    reason_block: list = []
    if primary_reason:
        reason_block.append(html.Div(
            f"\u201c{primary_reason}\u201d",
            style={
                "fontSize": "14px", "fontWeight": "500", "lineHeight": "1.5",
                "color": TEXT_PRIMARY, "fontStyle": "italic",
            },
        ))
    if secondary_reason:
        reason_block.append(html.Div(
            secondary_reason,
            style={"fontSize": "13px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "4px"},
        ))
    if required_beliefs:
        reason_block.append(html.Div(
            [
                html.Div("What must be true", style={**LABEL_STYLE, "marginTop": "12px", "marginBottom": "4px"}),
                html.Ul(
                    [html.Li(b, style={"fontSize": "13px", "lineHeight": "1.5", "color": TEXT_SECONDARY})
                     for b in required_beliefs[:3]],
                    style={"margin": "0", "paddingLeft": "18px"},
                ),
            ],
        ))

    return html.Div(
        className="card briarwood-fade-in",
        children=[
            html.Div(
                [html.Span("VERDICT", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                 html.Span(question, style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                style={"marginBottom": "20px"},
            ),
            # Hero row: verdict text + conviction ring
            html.Div(
                [
                    html.Div(
                        recommendation,
                        style={
                            "fontSize": "48px", "fontWeight": "800",
                            "letterSpacing": "-0.04em", "lineHeight": "1.0",
                            "color": accent,
                        },
                    ),
                    conviction_ring,
                ],
                style={
                    "display": "flex", "justifyContent": "space-between",
                    "alignItems": "center", "gap": "16px", "marginBottom": "20px",
                },
            ),
            # Metric sparks row
            html.Div(
                sparks,
                style={
                    "display": "grid",
                    "gridTemplateColumns": f"repeat(auto-fit, minmax(110px, 1fr))",
                    "gap": "20px",
                    "padding": "16px 0",
                    "borderTop": f"1px solid {BORDER}",
                    "borderBottom": f"1px solid {BORDER}" if reason_block else "none",
                    "marginBottom": "16px" if reason_block else "0",
                },
            ) if sparks else None,
            # Reasons
            html.Div(reason_block) if reason_block else None,
        ],
        style={
            **CARD_STYLE_ELEVATED,
            "borderLeft": f"4px solid {accent}",
            "padding": "24px 28px",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  3. Risk Heat Strip — Section 2
# ═══════════════════════════════════════════════════════════════════════════════


def _risk_segment_color(score: int) -> str:
    """Map 0-100 risk score to color."""
    if score <= 33:
        return ACCENT_GREEN
    if score <= 66:
        return ACCENT_AMBER
    return ACCENT_RED


def _risk_level_label(score: int) -> str:
    if score <= 25:
        return "Low"
    if score <= 50:
        return "Moderate"
    if score <= 75:
        return "Elevated"
    return "High"


def risk_heat_strip(
    items: Sequence[Any],
    *,
    top_risks: list[str] | None = None,
) -> html.Div:
    """Horizontal risk profile — 5 color-coded segments in a single strip.

    Each item must have .name, .score (0-100), .level, .label attributes.
    Bloomberg-terminal dense but instantly scannable.
    """
    if not items:
        return html.Div("Risk data unavailable.", style={"color": TEXT_SECONDARY, "fontSize": "13px"})

    # Category name mapping for clarity
    _DISPLAY_NAMES = {
        "Price": "Overpayment",
        "Carry": "Monthly Burn",
        "Liquidity": "Liquidity",
        "Execution": "Execution",
        "Confidence": "Data Quality",
    }

    total_score = sum(it.score for it in items)
    max_total = len(items) * 100

    # ── Composite strip ─────────────────────────────────────────────────
    strip_segments: list[html.Div] = []
    segment_labels: list[html.Div] = []

    for item in items:
        color = _risk_segment_color(item.score)
        width_pct = 100 / len(items)
        display_name = _DISPLAY_NAMES.get(item.name, item.name)

        strip_segments.append(html.Div(
            # Score number centered in segment
            html.Div(f"{item.score}", style={
                "fontSize": "13px", "fontWeight": "700", "fontFamily": FONT_MONO,
                "color": TEXT_PRIMARY, "textAlign": "center", "lineHeight": "28px",
            }),
            style={
                "width": f"{width_pct}%",
                "height": "28px",
                "backgroundColor": color,
                "opacity": "0.85",
                "position": "relative",
            },
        ))

        segment_labels.append(html.Div(
            [
                html.Div(display_name, style={
                    "fontSize": "10px", "fontWeight": "600", "color": TEXT_SECONDARY,
                    "textTransform": "uppercase", "letterSpacing": "0.04em",
                    "textAlign": "center", "whiteSpace": "nowrap",
                }),
                html.Div(item.label, style={
                    "fontSize": "11px", "color": TEXT_TERTIARY, "textAlign": "center",
                    "marginTop": "2px", "lineHeight": "1.3",
                    "overflow": "hidden", "textOverflow": "ellipsis",
                    "display": "-webkit-box", "WebkitLineClamp": "2",
                    "WebkitBoxOrient": "vertical",
                }),
            ],
            style={"width": f"{width_pct}%", "padding": "0 4px", "boxSizing": "border-box"},
        ))

    # Overall risk indicator
    composite = int(total_score / len(items)) if items else 0
    composite_color = _risk_segment_color(composite)
    composite_label = _risk_level_label(composite)

    # ── Top risks as compact pills ──────────────────────────────────────
    risk_pills: list[html.Span] = []
    if top_risks:
        for risk_text in top_risks[:3]:
            risk_pills.append(html.Span(
                risk_text,
                style={
                    "fontSize": "12px", "color": TEXT_SECONDARY,
                    "padding": "4px 10px", "borderRadius": RADIUS_SM,
                    "backgroundColor": BG_SURFACE, "border": f"1px solid {BORDER}",
                    "display": "inline-block", "marginRight": "6px", "marginBottom": "4px",
                },
            ))

    return html.Div(
        [
            # Header with composite score
            html.Div(
                [
                    html.Div(
                        [html.Span("RISK PROFILE", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                         html.Span("What could go wrong?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                    ),
                    html.Div(
                        [
                            html.Span(f"{composite}", style={
                                "fontSize": "24px", "fontWeight": "800",
                                "fontFamily": FONT_MONO, "color": composite_color,
                            }),
                            html.Span(f"/100 {composite_label}", style={
                                "fontSize": "12px", "fontWeight": "600",
                                "color": composite_color, "marginLeft": "4px",
                            }),
                        ],
                        style={"textAlign": "right"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "16px"},
            ),
            # Heat strip
            html.Div(
                strip_segments,
                style={
                    "display": "flex", "borderRadius": RADIUS_SM,
                    "overflow": "hidden", "marginBottom": "8px",
                },
            ),
            # Labels below strip
            html.Div(
                segment_labels,
                style={"display": "flex", "marginBottom": "16px"},
            ),
            # Top risks
            html.Div(risk_pills, style={"marginTop": "4px"}) if risk_pills else None,
        ],
        style=CARD_STYLE,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  4. Value Opportunity Chart — Section 3 (Plotly horizontal bar)
# ═══════════════════════════════════════════════════════════════════════════════


def value_opportunity_chart(
    drivers: list[dict[str, Any]],
    *,
    bullets: list[str] | None = None,
    supporting_signal: str = "",
) -> html.Div:
    """Stacked horizontal value waterfall showing where value comes from.

    Each driver: {"label": str, "impact": float ($/mo or $), "confidence": str}
    If no drivers, the emptiness IS the signal.
    """
    if not drivers and not bullets:
        return html.Div(
            [
                html.Div(
                    [html.Span("VALUE DRIVERS", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                     html.Span("Where is the value?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                    style={"marginBottom": "16px"},
                ),
                html.Div(
                    "No clear value edge identified.",
                    style={
                        "fontSize": "16px", "fontWeight": "600", "color": TEXT_TERTIARY,
                        "textAlign": "center", "padding": "40px 0",
                    },
                ),
            ],
            style=CARD_STYLE,
        )

    # ── Build Plotly horizontal bar if we have drivers ───────────────────
    chart = None
    if drivers:
        labels = [d["label"] for d in drivers]
        values = [d.get("impact", 0) for d in drivers]
        colors = [ACCENT_GREEN if v >= 0 else ACCENT_RED for v in values]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=labels,
            x=values,
            orientation="h",
            marker=dict(color=colors, cornerradius=4),
            text=[_money(v, signed=True) if abs(v) >= 100 else _pct(v, signed=True) for v in values],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY, family=FONT_MONO, size=12),
            hovertemplate="%{y}: %{x:$,.0f}<extra></extra>",
        ))

        layout = {**PLOTLY_LAYOUT_COMPACT}
        layout["height"] = max(100, len(drivers) * 40 + 40)
        layout["showlegend"] = False
        layout["yaxis"] = dict(
            autorange="reversed",
            gridcolor="rgba(0,0,0,0)",
            tickfont=dict(color=TEXT_PRIMARY, family=FONT_FAMILY, size=12),
        )
        layout["xaxis"] = dict(
            gridcolor=BORDER_SUBTLE,
            tickfont=dict(color=TEXT_TERTIARY, family=FONT_MONO, size=10),
            tickprefix="$",
        )
        fig.update_layout(**layout)

        chart = dcc.Graph(
            figure=fig,
            config={"displayModeBar": False},
            style={"marginBottom": "12px"},
        )

    # ── Bullet signals ──────────────────────────────────────────────────
    bullet_items: list = []
    if bullets:
        for b in bullets[:4]:
            bullet_items.append(html.Div(
                [
                    html.Span("\u25B8 ", style={"color": ACCENT_GREEN, "fontSize": "14px"}),
                    html.Span(b, style={"fontSize": "14px", "lineHeight": "1.6", "color": TEXT_PRIMARY}),
                ],
                style={"marginBottom": "6px"},
            ))

    return html.Div(
        [
            html.Div(
                [html.Span("VALUE DRIVERS", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                 html.Span("Where is the value?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                style={"marginBottom": "16px"},
            ),
            chart,
            html.Div(bullet_items) if bullet_items else None,
            html.Div(supporting_signal, style={
                "fontSize": "12px", "color": TEXT_TERTIARY, "marginTop": "8px",
            }) if supporting_signal else None,
        ],
        style=CARD_STYLE,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  5. Scenario Fan Chart — Section 4 (Plotly area)
# ═══════════════════════════════════════════════════════════════════════════════


def scenario_fan_chart(
    ask_price: float,
    *,
    base_value: float | None = None,
    bull_value: float | None = None,
    bear_value: float | None = None,
    stress_value: float | None = None,
    upside_pct: str = "",
    downside_pct: str = "",
    equity_year5: float | None = None,
) -> html.Div:
    """Fan/cone chart showing three scenario paths diverging from today.

    The spread between bull and bear IS the uncertainty.
    Includes small equity buildup annotation.
    """
    has_data = any(v is not None for v in [base_value, bull_value, bear_value])
    if not has_data:
        return html.Div(
            [
                html.Div(
                    [html.Span("PROJECTION", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                     html.Span("What does this become?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                    style={"marginBottom": "16px"},
                ),
                html.Div("Forward projections unavailable.", style={
                    "fontSize": "14px", "color": TEXT_TERTIARY, "textAlign": "center", "padding": "32px 0",
                }),
            ],
            style=CARD_STYLE,
        )

    # Build linear interpolation paths from ask → scenario value
    years = [0, 1, 2, 3, 4, 5]
    base = base_value or ask_price
    bull = bull_value or base
    bear = bear_value or base
    stress = stress_value or bear

    def _path(target: float) -> list[float]:
        return [ask_price + (target - ask_price) * (y / 5) for y in years]

    base_path = _path(base)
    bull_path = _path(bull)
    bear_path = _path(bear)

    fig = go.Figure()

    # Uncertainty band (bull-bear fill)
    fig.add_trace(go.Scatter(
        x=years, y=bull_path,
        mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=years, y=bear_path,
        mode="lines", line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(59, 130, 246, 0.08)",
        showlegend=False, hoverinfo="skip",
    ))

    # Scenario lines
    fig.add_trace(go.Scatter(
        x=years, y=bull_path,
        mode="lines+markers",
        name="Bull",
        line=dict(color=ACCENT_GREEN, width=2, dash="dot"),
        marker=dict(size=4, color=ACCENT_GREEN),
        hovertemplate="Year %{x}: $%{y:,.0f}<extra>Bull</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=years, y=base_path,
        mode="lines+markers",
        name="Base",
        line=dict(color=ACCENT_BLUE, width=2.5),
        marker=dict(size=5, color=ACCENT_BLUE),
        hovertemplate="Year %{x}: $%{y:,.0f}<extra>Base</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=years, y=bear_path,
        mode="lines+markers",
        name="Bear",
        line=dict(color=ACCENT_RED, width=2, dash="dot"),
        marker=dict(size=4, color=ACCENT_RED),
        hovertemplate="Year %{x}: $%{y:,.0f}<extra>Bear</extra>",
    ))

    # Ask price reference line
    fig.add_hline(
        y=ask_price,
        line=dict(color=TEXT_TERTIARY, width=1, dash="dash"),
        annotation_text="Ask",
        annotation_position="bottom left",
        annotation_font=dict(color=TEXT_TERTIARY, size=10),
    )

    fan_layout = {**PLOTLY_LAYOUT_COMPACT}
    fan_layout.update(
        height=CHART_HEIGHT_STANDARD,
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=11, color=TEXT_SECONDARY),
            bgcolor="rgba(0,0,0,0)",
        ),
        yaxis=dict(
            gridcolor=BORDER_SUBTLE,
            tickfont=dict(color=TEXT_TERTIARY, family=FONT_MONO, size=10),
            tickprefix="$",
            tickformat=",",
        ),
        xaxis=dict(
            gridcolor="rgba(0,0,0,0)",
            tickfont=dict(color=TEXT_TERTIARY, family=FONT_MONO, size=10),
            dtick=1,
            title=dict(text="Year", font=dict(size=10, color=TEXT_TERTIARY)),
        ),
    )
    fig.update_layout(**fan_layout)

    # ── Summary sparks below the chart ──────────────────────────────────
    sparks: list[html.Div] = []
    if bull_value is not None:
        bull_delta = (bull_value - ask_price) / ask_price
        sparks.append(metric_spark("Bull case", _money(bull_value), min(1.0, max(0, bull_delta + 0.5)),
                                   color=ACCENT_GREEN, subtitle=upside_pct or f"{bull_delta:+.1%}"))
    if base_value is not None:
        base_delta = (base_value - ask_price) / ask_price
        sparks.append(metric_spark("Base case", _money(base_value), min(1.0, max(0, base_delta + 0.5)),
                                   color=ACCENT_BLUE, subtitle=f"{base_delta:+.1%}"))
    if bear_value is not None:
        bear_delta = (bear_value - ask_price) / ask_price
        sparks.append(metric_spark("Bear case", _money(bear_value), min(1.0, max(0, bear_delta + 0.5)),
                                   color=ACCENT_RED, subtitle=downside_pct or f"{bear_delta:+.1%}"))
    if equity_year5 is not None:
        sparks.append(metric_spark("5yr equity", _money(equity_year5), 0.6,
                                   color=ACCENT_BLUE, subtitle="appreciation + paydown"))

    return html.Div(
        [
            html.Div(
                [html.Span("PROJECTION", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                 html.Span("What does this become?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                style={"marginBottom": "12px"},
            ),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
            html.Div(
                sparks,
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(120px, 1fr))",
                    "gap": "20px",
                    "borderTop": f"1px solid {BORDER}",
                    "paddingTop": "14px",
                    "marginTop": "4px",
                },
            ) if sparks else None,
        ],
        style=CARD_STYLE,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  6. Strategy Radar Chart — Section 5 (Plotly scatterpolar)
# ═══════════════════════════════════════════════════════════════════════════════


_FIT_DIMENSION_LABELS = {
    "entry_basis": "Entry Price",
    "income_support": "Cash Flow",
    "capex_load": "Capex Load",
    "liquidity_profile": "Liquidity",
    "optionality": "Upside",
    "risk_skew": "Risk Profile",
}


def strategy_radar_chart(
    factor_scores: dict[str, float],
    *,
    capital_required: float | None = None,
    time_to_stabilize: str = "",
    complexity: str = "",
    positive_factors: list[Any] | None = None,
    negative_factors: list[Any] | None = None,
) -> html.Div:
    """Radar/spider chart showing strategy fit across 6 dimensions.

    factor_scores: dict mapping dimension key → score (-1.0 to 1.0)
    """
    if not factor_scores:
        return html.Div(
            [
                html.Div(
                    [html.Span("STRATEGY FIT", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                     html.Span("Does this fit my strategy?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                    style={"marginBottom": "16px"},
                ),
                html.Div("Fit analysis unavailable.", style={
                    "fontSize": "14px", "color": TEXT_TERTIARY, "textAlign": "center", "padding": "32px 0",
                }),
            ],
            style=CARD_STYLE,
        )

    # Normalize -1..1 → 0..1 for radar
    categories = []
    values = []
    for key in ["entry_basis", "income_support", "capex_load", "liquidity_profile", "optionality", "risk_skew"]:
        if key in factor_scores:
            categories.append(_FIT_DIMENSION_LABELS.get(key, key))
            values.append((factor_scores[key] + 1.0) / 2.0)  # -1..1 → 0..1

    if not categories:
        return html.Div()

    # Close the polygon
    categories.append(categories[0])
    values.append(values[0])

    # Color based on average score
    avg_score = sum(values[:-1]) / len(values[:-1])
    fill_color = ACCENT_GREEN if avg_score >= 0.6 else ACCENT_AMBER if avg_score >= 0.4 else ACCENT_RED
    fill_rgba = fill_color.replace("#", "")
    r, g, b = int(fill_rgba[:2], 16), int(fill_rgba[2:4], 16), int(fill_rgba[4:6], 16)

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill="toself",
        fillcolor=f"rgba({r},{g},{b},0.15)",
        line=dict(color=fill_color, width=2),
        marker=dict(size=6, color=fill_color),
        name="Property",
        hovertemplate="%{theta}: %{r:.0%}<extra></extra>",
    ))

    radar_layout = {**PLOTLY_LAYOUT_COMPACT}
    radar_layout.update(
        height=CHART_HEIGHT_STANDARD,
        showlegend=False,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                showticklabels=False,
                gridcolor=BORDER_SUBTLE,
            ),
            angularaxis=dict(
                tickfont=dict(color=TEXT_SECONDARY, family=FONT_FAMILY, size=11),
                gridcolor=BORDER,
            ),
        ),
    )
    fig.update_layout(**radar_layout)

    # ── Annotations: capital, timeline, complexity ──────────────────────
    annotations: list[html.Div] = []
    if capital_required is not None:
        annotations.append(metric_spark("Capital required", _money(capital_required), 0.5,
                                        color=TEXT_PRIMARY, subtitle="down payment + reserves"))
    if time_to_stabilize:
        annotations.append(metric_spark("Time to stabilize", time_to_stabilize, 0.5,
                                        color=ACCENT_BLUE, subtitle="to full cash flow"))
    if complexity:
        comp_color = ACCENT_GREEN if complexity == "Low" else ACCENT_AMBER if complexity in ("Medium", "Med") else ACCENT_RED
        comp_fill = {"Low": 0.8, "Medium": 0.5, "Med": 0.5, "High": 0.2}.get(complexity, 0.5)
        annotations.append(metric_spark("Complexity", complexity, comp_fill,
                                        color=comp_color, subtitle="operational burden"))

    # ── Factor pills (positive/negative) ────────────────────────────────
    factor_pills: list = []
    if positive_factors:
        for f in positive_factors[:3]:
            text = f.explanation if hasattr(f, "explanation") else str(f)
            factor_pills.append(html.Span(
                f"+ {text}",
                style={
                    "fontSize": "12px", "color": ACCENT_GREEN,
                    "padding": "3px 8px", "borderRadius": RADIUS_SM,
                    "backgroundColor": "rgba(34, 197, 94, 0.1)",
                    "border": "1px solid rgba(34, 197, 94, 0.2)",
                    "display": "inline-block", "marginRight": "6px", "marginBottom": "4px",
                },
            ))
    if negative_factors:
        for f in negative_factors[:3]:
            text = f.explanation if hasattr(f, "explanation") else str(f)
            factor_pills.append(html.Span(
                f"- {text}",
                style={
                    "fontSize": "12px", "color": ACCENT_RED,
                    "padding": "3px 8px", "borderRadius": RADIUS_SM,
                    "backgroundColor": "rgba(239, 68, 68, 0.1)",
                    "border": "1px solid rgba(239, 68, 68, 0.2)",
                    "display": "inline-block", "marginRight": "6px", "marginBottom": "4px",
                },
            ))

    return html.Div(
        [
            html.Div(
                [html.Span("STRATEGY FIT", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                 html.Span("Does this fit my strategy?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                style={"marginBottom": "8px"},
            ),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
            html.Div(
                annotations,
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(130px, 1fr))",
                    "gap": "20px",
                    "borderTop": f"1px solid {BORDER}",
                    "paddingTop": "14px",
                },
            ) if annotations else None,
            html.Div(factor_pills, style={"marginTop": "12px"}) if factor_pills else None,
        ],
        style=CARD_STYLE,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  7. Quick Reality Gauge — compact strip with visual indicators
# ═══════════════════════════════════════════════════════════════════════════════


def quick_metric_gauge(
    label: str,
    value_text: str,
    fill_pct: float,
    *,
    color: str | None = None,
    subtitle: str = "",
) -> html.Div:
    """A slightly larger metric gauge for the Quick Reality strip."""
    bar_color = color or _semantic_color(fill_pct)
    return html.Div(
        [
            html.Div(label, style={
                "fontSize": "10px", "fontWeight": "600", "color": TEXT_TERTIARY,
                "textTransform": "uppercase", "letterSpacing": "0.06em",
                "marginBottom": "4px",
            }),
            html.Div(value_text, style={
                "fontSize": "22px", "fontWeight": "800", "fontFamily": FONT_MONO,
                "color": bar_color, "lineHeight": "1.2",
            }),
            # Thicker fill bar
            html.Div(
                html.Div(style={
                    "width": f"{max(2, min(100, fill_pct * 100)):.0f}%",
                    "height": "100%",
                    "backgroundColor": bar_color,
                    "borderRadius": "3px",
                    "transition": "width 0.4s ease",
                }),
                style={
                    "height": "4px",
                    "backgroundColor": BORDER_SUBTLE,
                    "borderRadius": "3px",
                    "marginTop": "8px",
                    "overflow": "hidden",
                },
            ),
            html.Div(subtitle, style={
                "fontSize": "11px", "color": TEXT_TERTIARY, "marginTop": "4px",
            }) if subtitle else None,
        ],
        style={"minWidth": "120px"},
    )

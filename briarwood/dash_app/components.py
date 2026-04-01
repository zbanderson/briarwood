from __future__ import annotations

from dash import dash_table, dcc, html
import plotly.graph_objects as go

from briarwood.dash_app.compare import CompareSummary
from briarwood.dash_app.view_models import (
    PropertyAnalysisView,
    build_evidence_rows,
    build_section_evidence_rows,
)
from briarwood.schemas import AnalysisReport


SIDEBAR_STYLE = {
    "width": "clamp(280px, 28vw, 360px)",
    "padding": "clamp(16px, 2vw, 24px)",
    "borderRight": "1px solid #d9e1ea",
    "backgroundColor": "#f7f9fb",
    "display": "flex",
    "flexDirection": "column",
    "gap": "16px",
    "flexShrink": "0",
}

PAGE_STYLE = {
    "fontFamily": "Avenir Next, Helvetica Neue, sans-serif",
    "color": "#17324d",
    "backgroundColor": "#fbfcfe",
    "minHeight": "100vh",
}

CARD_STYLE = {
    "backgroundColor": "white",
    "border": "1px solid #dde4ec",
    "borderRadius": "12px",
    "padding": "16px",
    "boxShadow": "0 8px 24px rgba(23, 50, 77, 0.06)",
}

LANE_HEADER_STYLE = {
    "position": "sticky",
    "top": "0",
    "zIndex": "2",
    "backgroundColor": "#fbfcfe",
    "paddingBottom": "8px",
}

RESPONSIVE_GRID_2 = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))", "gap": "14px"}
RESPONSIVE_GRID_3 = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))", "gap": "14px"}
RESPONSIVE_GRID_4 = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "14px"}


def metric_card(label: str, value: str, *, subtitle: str = "", tone: str = "neutral") -> html.Div:
    accent = {"positive": "#0b7a5d", "negative": "#a23d3d"}.get(tone, "#17324d")
    return html.Div(
        [
            html.Div(label, style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
            html.Div(value, style={"fontSize": "28px", "fontWeight": "700", "color": accent}),
            html.Div(subtitle, style={"fontSize": "12px", "color": "#6b7b8d"}) if subtitle else None,
        ],
        style=CARD_STYLE,
    )


def _fmt_value(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"${value:,.0f}"


def confidence_badge(confidence: float) -> html.Span:
    tone = "#0b7a5d" if confidence >= 0.75 else "#a36a00" if confidence >= 0.55 else "#a23d3d"
    return html.Span(
        f"{confidence:.0%} confidence",
        style={
            "padding": "4px 10px",
            "borderRadius": "999px",
            "backgroundColor": "#eef3f8",
            "color": tone,
            "fontSize": "12px",
            "fontWeight": "600",
        },
    )


def compact_badge(label: str, value: str, *, tone: str = "neutral") -> html.Span:
    colors = {
        "positive": ("#e8f5ef", "#0b7a5d"),
        "warning": ("#fff4df", "#a36a00"),
        "negative": ("#fdecec", "#a23d3d"),
        "neutral": ("#eef3f8", "#4f6275"),
    }
    background, color = colors.get(tone, colors["neutral"])
    return html.Span(
        f"{label}: {value}",
        style={
            "padding": "4px 8px",
            "borderRadius": "999px",
            "backgroundColor": background,
            "color": color,
            "fontSize": "11px",
            "fontWeight": "600",
            "display": "inline-block",
        },
    )


def simple_table(rows: list[dict[str, str]], *, page_size: int = 12) -> dash_table.DataTable:
    columns = [{"name": key, "id": key} for key in (rows[0].keys() if rows else ["Metric", "Value"])]
    return dash_table.DataTable(
        data=rows,
        columns=columns,
        page_size=page_size,
        style_table={"overflowX": "auto"},
        style_header={"backgroundColor": "#edf3f8", "fontWeight": "700"},
        style_cell={"padding": "10px", "textAlign": "left", "fontFamily": "Avenir Next, Helvetica Neue, sans-serif"},
    )


def ask_bcv_base_chart(view: PropertyAnalysisView, *, compact: bool = False) -> dcc.Graph:
    figure = go.Figure(
        data=[
            go.Bar(
                x=["Ask", "BCV", "Base"],
                y=[view.ask_price or 0, view.bcv or 0, view.base_case or 0],
                marker_color=["#8fa7bf", "#1f77b4", "#3aaf85"],
                text=[f"${(view.ask_price or 0):,.0f}", f"${(view.bcv or 0):,.0f}", f"${(view.base_case or 0):,.0f}"],
                textposition="outside",
            )
        ]
    )
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=220 if compact else 260,
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis_title="Value",
        showlegend=False,
    )
    return dcc.Graph(figure=figure, config={"displayModeBar": False})


def forward_chart(view: PropertyAnalysisView, *, compact: bool = False) -> dcc.Graph:
    x_labels = ["Bear Case", "Base Case", "Bull Case"]
    y_values = [view.bear_case or 0, view.base_case or 0, view.bull_case or 0]
    texts = [view.forward.bear_value_text, view.forward.base_value_text, view.forward.bull_value_text]
    colors = ["#d97b7b", "#8fa7bf", "#3aaf85"]
    if view.stress_case is not None:
        x_labels = ["Stress", "Bear Case", "Base Case", "Bull Case"]
        y_values = [view.stress_case, view.bear_case or 0, view.base_case or 0, view.bull_case or 0]
        texts = [view.forward.stress_case_value_text, view.forward.bear_value_text, view.forward.base_value_text, view.forward.bull_value_text]
        colors = ["#8b2020", "#d97b7b", "#8fa7bf", "#3aaf85"]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=x_labels,
            y=y_values,
            mode="lines+markers+text",
            line={"color": "#1f4e79", "width": 3},
            marker={"size": 10, "color": colors},
            text=texts,
            textposition="top center",
            name="Scenario Range",
        )
    )
    figure.add_hline(y=view.ask_price or 0, line_dash="dash", line_color="#17324d", annotation_text="Ask", annotation_position="right")
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=220 if compact else 260,
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis_title="12M Value",
        showlegend=False,
    )
    return dcc.Graph(figure=figure, config={"displayModeBar": False})


def summary_strip(view: PropertyAnalysisView) -> html.Div:
    gap_tone = "positive" if (view.mispricing_pct or 0) >= 0 else "negative"
    risk_tone = "neutral" if view.risk_location.risk_score >= 70 else "warning" if view.risk_location.risk_score >= 50 else "negative"
    gap_text = _fmt_value(view.ask_price)
    if view.mispricing_pct is not None:
        pct = view.mispricing_pct * 100
        sign = "+" if pct >= 0 else ""
        gap_text = f"{sign}{pct:.1f}%"
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Investment Memo", style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
                            html.H1(view.memo_verdict, style={"margin": "6px 0"}),
                            html.Div(view.address, style={"color": "#5f7286", "fontSize": "14px"}),
                            html.Div(
                                [html.Span(view.evidence_mode), html.Span(" | "), confidence_badge(view.overall_confidence)],
                                style={"display": "flex", "gap": "8px", "alignItems": "center"},
                            ),
                        ],
                        style={**CARD_STYLE, "gridColumn": "span 2"},
                    ),
                    metric_card("Ask", _fmt_value(view.ask_price)),
                    metric_card("BCV", _fmt_value(view.bcv)),
                    metric_card("Gap vs BCV", gap_text, subtitle=view.pricing_view.title(), tone=gap_tone),
                    metric_card("Biggest Risk", view.biggest_risk, tone=risk_tone),
                    metric_card("Base Case", _fmt_value(view.base_case)),
                ],
                style=RESPONSIVE_GRID_3,
            ),
        ]
    )


def render_overview_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    if compact:
        return html.Div(
            [
                html.Div(
                    [
                        html.H3(view.memo_verdict, style={"margin": "0 0 6px 0"}),
                        html.P(view.memo_summary, style={"margin": "0 0 10px 0", "color": "#30485f"}),
                        html.Div(
                            [
                                compact_badge("Ask", _fmt_value(view.ask_price)),
                                compact_badge("BCV", _fmt_value(view.bcv)),
                                compact_badge("Base", _fmt_value(view.base_case)),
                                compact_badge("Risk", view.biggest_risk, tone="negative"),
                            ],
                            style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginBottom": "10px"},
                        ),
                        html.Div([html.H3("Top Reasons"), html.Ul([html.Li(item) for item in view.top_reasons[:3]])], style={"marginBottom": "10px"}),
                        html.Div([html.H3("Buyer Fit"), html.Ul([html.Li(item) for item in view.buyer_fit[:3]])], style={"marginBottom": "10px"}),
                        html.Div([html.H3("What Changes The Call"), html.Ul([html.Li(item) for item in view.what_changes_call[:3]])]),
                    ],
                    style=CARD_STYLE,
                )
            ],
            style={"display": "grid", "gap": "14px"},
        )

    intro = html.Div(
        [
            html.H2(view.memo_verdict if not compact else view.memo_verdict, style={"margin": "0 0 6px 0", "fontSize": "26px" if not compact else "20px"}),
            html.Div(view.address, style={"color": "#5f7286", "marginBottom": "6px"}),
            html.Div(
                [html.Span(view.evidence_mode), html.Span(" | "), confidence_badge(view.overall_confidence)],
                style={"display": "flex", "gap": "8px", "alignItems": "center", "flexWrap": "wrap"},
            ),
            html.P(view.memo_summary, style={"margin": "12px 0 0 0", "color": "#30485f"}),
        ],
        style=CARD_STYLE,
    )
    cards = html.Div(
        [
            metric_card("Decision", view.pricing_view.title()),
            metric_card("Ask", _fmt_value(view.ask_price)),
            metric_card("BCV", _fmt_value(view.bcv)),
            metric_card("Base Case", _fmt_value(view.base_case)),
        ],
        style=RESPONSIVE_GRID_3,
    )
    bullets = html.Div(
        [
            html.Div([html.H3("Top Reasons"), html.Ul([html.Li(item) for item in view.top_reasons])], style=CARD_STYLE),
            html.Div([html.H3("Buyer Fit"), html.Ul([html.Li(item) for item in view.buyer_fit])], style=CARD_STYLE),
            html.Div([html.H3("Biggest Risk"), html.P(view.biggest_risk)], style=CARD_STYLE),
            html.Div([html.H3("What Changes The Call"), html.Ul([html.Li(item) for item in view.what_changes_call])], style=CARD_STYLE),
        ],
        style=RESPONSIVE_GRID_2,
    )
    chart = html.Div([html.H3("Ask vs BCV vs Base"), ask_bcv_base_chart(view, compact=compact)], style=CARD_STYLE)
    return html.Div([intro, cards, bullets, chart], style={"display": "grid", "gap": "14px"})


def render_value_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    component_rows = [{"Component": label, "Value": value, "Weight": weight} for label, value, weight in view.value.component_rows]
    comp_rows = [
        {
            "Address": row.address,
            "Adjusted": row.adjusted_price,
            "Fit": row.fit,
            "Verification": row.verification,
            "Condition": row.condition,
        }
        for row in view.comps.rows
    ]
    blocks: list[html.Div] = [
        html.Div(
            [
                metric_card("Pricing View", view.pricing_view.title()),
                metric_card("BCV Confidence", f"{view.value.confidence:.0%}"),
                metric_card("Comparable Value", view.comps.comparable_value_text),
            ],
            style=RESPONSIVE_GRID_3,
        ),
        html.Div([html.H3("BCV Components"), simple_table(component_rows, page_size=8)], style=CARD_STYLE),
        html.Div(
            [
                html.Div([html.H3("Comp Verification"), html.P(view.comps.verification_summary), html.P(view.comps.curation_summary)], style=CARD_STYLE),
                html.Div([html.H3("Comp Screening"), html.P(view.comps.screening_summary), html.P(f"Dataset: {view.comps.dataset_name}")], style=CARD_STYLE),
            ],
            style=RESPONSIVE_GRID_2,
        ),
        html.Div([html.H3("Active Comps"), simple_table(comp_rows or [{"Address": "No active comps", "Adjusted": "", "Fit": "", "Verification": "", "Condition": ""}], page_size=6)], style=CARD_STYLE),
    ]
    if not compact:
        blocks.append(
            html.Div(
                [
                    html.Div([html.H3("Assumptions"), html.Ul([html.Li(item) for item in view.value.assumptions[:8]])], style=CARD_STYLE),
                    html.Div([html.H3("Warnings"), html.Ul([html.Li(item) for item in view.value.warnings[:8]])], style=CARD_STYLE),
                    html.Div([html.H3("Unsupported Claims"), html.Ul([html.Li(item) for item in view.value.unsupported_claims[:8]])], style=CARD_STYLE),
                ],
                style=RESPONSIVE_GRID_3,
            )
        )
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_forward_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    metric_rows = [
        {"Metric": "Bear Case", "Value": view.forward.bear_value_text, "vs Ask": view.forward.downside_pct_text},
        {"Metric": "Base Case", "Value": view.forward.base_value_text, "vs Ask": "—"},
        {"Metric": "Bull Case", "Value": view.forward.bull_value_text, "vs Ask": view.forward.upside_pct_text},
        {"Metric": "Market Drift", "Value": view.forward.market_drift_text, "vs Ask": ""},
        {"Metric": "Location Premium", "Value": view.forward.location_premium_text, "vs Ask": ""},
        {"Metric": "Risk Discount", "Value": view.forward.risk_discount_text, "vs Ask": ""},
        {"Metric": "Optionality Premium", "Value": view.forward.optionality_premium_text, "vs Ask": ""},
    ]
    if view.stress_case is not None:
        metric_rows.insert(0, {"Metric": "Stress Case ⚠", "Value": view.forward.stress_case_value_text, "vs Ask": "Tail risk — not a forecast"})
    scenario_cards = [
        metric_card("Bear", view.forward.bear_value_text, subtitle=view.forward.downside_pct_text + " vs ask"),
        metric_card("Base", view.forward.base_value_text),
        metric_card("Bull", view.forward.bull_value_text, subtitle=view.forward.upside_pct_text + " vs ask"),
    ]
    if view.stress_case is not None:
        scenario_cards.append(metric_card("Stress ⚠", view.forward.stress_case_value_text, subtitle="Tail risk scenario"))
    blocks = [
        html.Div(
            [metric_card("Forward Confidence", f"{view.forward.confidence:.0%}")] + scenario_cards,
            style=RESPONSIVE_GRID_4,
        ),
        html.Div(
            [
                html.H3("12-Month Scenario Range"),
                forward_chart(view, compact=compact),
                html.P(
                    "Scenarios represent a 12-month range of outcomes, not a forecast. "
                    + ("Stress case models a historical coastal correction (NJ 2008–2011 analog). " if view.stress_case is not None else "")
                    + "Bear and Bull reflect market and location risk/upside.",
                    style={"fontSize": "12px", "color": "#6b7b8d", "marginTop": "8px"},
                ),
            ],
            style=CARD_STYLE,
        ),
        html.Div([html.H3("Scenario Drivers"), simple_table(metric_rows, page_size=10)], style=CARD_STYLE),
    ]
    if not compact:
        blocks.append(html.Div([html.H3("Forward Summary"), html.P(view.forward.summary)], style=CARD_STYLE))
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_risk_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    metric_rows = [
        {"Metric": "Risk Score", "Value": f"{view.risk_location.risk_score:.1f}"},
        {"Metric": "Flood", "Value": view.risk_location.flood_risk.title()},
        {"Metric": "Liquidity", "Value": view.risk_location.liquidity_view.title()},
    ]
    blocks = [
        html.Div([html.H3("Risk Snapshot"), simple_table(metric_rows, page_size=8)], style=CARD_STYLE),
        html.Div([html.H3("Primary Constraints"), html.P(view.risk_location.risk_summary)], style=CARD_STYLE),
        html.Div([html.H3("Key Risks"), html.Ul([html.Li(item) for item in view.risk_location.risks[:8]])], style=CARD_STYLE),
    ]
    if not compact and view.risk_location.unsupported_claims:
        blocks.append(html.Div([html.H3("Unsupported Claims"), html.Ul([html.Li(item) for item in view.risk_location.unsupported_claims[:8]])], style=CARD_STYLE))
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_location_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    metric_rows = [
        {"Metric": "Town / County Score", "Value": f"{view.risk_location.town_score:.1f}"},
        {"Metric": "Location Thesis", "Value": view.risk_location.town_label.replace("_", " ").title()},
        {"Metric": "Scarcity Score", "Value": f"{view.risk_location.scarcity_score:.1f}"},
    ]
    blocks = [
        html.Div([html.H3("Location Snapshot"), simple_table(metric_rows, page_size=8)], style=CARD_STYLE),
        html.Div(
            [
                html.Div([html.H3("Demand Drivers"), html.Ul([html.Li(item) for item in view.risk_location.drivers[:8]])], style=CARD_STYLE),
                html.Div([html.H3("Location Risks"), html.Ul([html.Li(item) for item in view.risk_location.risks[:8]])], style=CARD_STYLE),
            ],
            style=RESPONSIVE_GRID_2,
        ),
    ]
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_income_support_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    metric_rows = [
        {"Metric": "Price-to-Rent", "Value": view.income_support.price_to_rent_text, "Read": view.income_support.ptr_classification},
        {"Metric": "Rental Ease", "Value": view.income_support.rental_ease_label, "Read": ""},
        {"Metric": "Days to Rent", "Value": view.income_support.estimated_days_to_rent_text, "Read": ""},
        {"Metric": "Income Support", "Value": view.income_support.income_support_ratio_text, "Read": ""},
        {"Metric": "All-in Cash Flow", "Value": view.income_support.monthly_cash_flow_text, "Read": ""},
        {"Metric": "Operating Cash Flow", "Value": view.income_support.operating_cash_flow_text, "Read": ""},
        {"Metric": "Rent Source", "Value": view.income_support.rent_source_type, "Read": ""},
        {"Metric": "Risk View", "Value": view.income_support.risk_view, "Read": ""},
    ]
    blocks = [
        html.Div(
            [
                metric_card("Income Confidence", f"{view.income_support.confidence:.0%}"),
                metric_card("Price-to-Rent", view.income_support.price_to_rent_text, subtitle=view.income_support.ptr_classification),
                metric_card("Rental Ease", view.income_support.rental_ease_label),
                metric_card("Income Support", view.income_support.income_support_ratio_text),
            ],
            style=RESPONSIVE_GRID_4,
        ),
        html.Div([html.H3("Carry and Rent Support"), simple_table(metric_rows, page_size=10)], style=CARD_STYLE),
        html.Div([html.H3("Summary"), html.P(view.income_support.summary)], style=CARD_STYLE),
    ]
    if not compact:
        blocks.append(
            html.Div(
                [
                    html.Div([html.H3("Warnings"), html.Ul([html.Li(item) for item in view.income_support.warnings[:8]])], style=CARD_STYLE),
                    html.Div([html.H3("Assumptions"), html.Ul([html.Li(item) for item in view.income_support.assumptions[:8]])], style=CARD_STYLE),
                    html.Div([html.H3("Unsupported Claims"), html.Ul([html.Li(item) for item in view.income_support.unsupported_claims[:8]])], style=CARD_STYLE),
                ],
                style=RESPONSIVE_GRID_3,
            )
        )
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_evidence_section(report: AnalysisReport, view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    evidence_rows = build_evidence_rows(report)
    section_rows = build_section_evidence_rows(report)
    blocks = [
        html.Div(
            [
                metric_card("Mode", view.evidence.evidence_mode),
                metric_card("Sourced Inputs", str(len(view.evidence.sourced_inputs))),
                metric_card("Estimated Inputs", str(len(view.evidence.estimated_inputs)), tone="negative" if view.evidence.estimated_inputs else "neutral"),
                metric_card("Missing Inputs", str(len(view.evidence.missing_inputs)), tone="negative" if view.evidence.missing_inputs else "neutral"),
            ],
            style=RESPONSIVE_GRID_4,
        ),
        html.Div([html.H3("Source Coverage"), simple_table(evidence_rows, page_size=12)], style=CARD_STYLE),
        html.Div([html.H3("Section Confidence"), simple_table(section_rows, page_size=12)], style=CARD_STYLE),
    ]
    if not compact:
        blocks.append(
            html.Div(
                [
                    html.Div([html.H3("Estimated Inputs"), html.Ul([html.Li(item) for item in view.evidence.estimated_inputs[:10]])], style=CARD_STYLE),
                    html.Div([html.H3("Missing Inputs"), html.Ul([html.Li(item) for item in view.evidence.missing_inputs[:10]])], style=CARD_STYLE),
                    html.Div([html.H3("Unsupported Claims"), html.Ul([html.Li(item) for item in view.evidence.unsupported_claims[:10]])], style=CARD_STYLE),
                ],
                style=RESPONSIVE_GRID_3,
            )
        )
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_single_section(section: str, view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
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
        from briarwood.dash_app.data_quality import render_data_quality_section  # lazy to avoid circular import
        return render_data_quality_section(report)
    return mapping[section](view, compact=False)


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
    if len(summary.rows) == 0:
        return None
    metric_filter = _COMPARE_SECTION_METRICS.get(section, set())
    rows = [{"Metric": row.metric, **row.values} for row in summary.rows if row.metric in metric_filter]
    if not rows:
        return None
    title = {"value": "Value Compare", "forward": "Forward Compare", "risk": "Risk Compare",
             "location": "Location Compare", "income": "Income Compare", "overview": "Summary Compare", "evidence": "Evidence Compare"}.get(section, "Compare")
    return html.Div(
        [
            html.Div([html.H3("Key Differences"), html.Ul([html.Li(item) for item in summary.why_different[:6]])], style=CARD_STYLE),
            html.Div([html.H3(title), simple_table(rows, page_size=8)], style=CARD_STYLE),
        ],
        style={**RESPONSIVE_GRID_2, "marginBottom": "16px"},
    )


def _lane_header(view: PropertyAnalysisView, *, show_export_button: bool = False) -> html.Div:
    comp_trust_value, comp_trust_tone = _comp_trust_badge(view)
    missing_count = len(view.evidence.missing_inputs)
    missing_tone = "negative" if missing_count >= 4 else "warning" if missing_count >= 1 else "positive"
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(view.label, style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
                            html.H3(view.address, style={"margin": "4px 0"}),
                        ]
                    ),
                    html.Button(
                        "Export Tear Sheet",
                        id={"type": "lane-export-button", "property_id": view.property_id},
                        n_clicks=0,
                        style={
                            "border": "1px solid #d0dbe7",
                            "backgroundColor": "white",
                            "borderRadius": "8px",
                            "padding": "8px 12px",
                            "fontSize": "12px",
                            "fontWeight": "600",
                            "cursor": "pointer",
                        },
                    )
                    if show_export_button
                    else None,
                ],
                style={"display": "flex", "justifyContent": "space-between", "gap": "12px", "alignItems": "start", "flexWrap": "wrap"},
            ),
            html.Div([confidence_badge(view.overall_confidence)], style={"marginTop": "6px"}),
            html.Div(
                [
                    compact_badge("Mode", view.evidence_mode),
                    compact_badge("Comp Trust", comp_trust_value, tone=comp_trust_tone),
                    compact_badge("Condition", view.condition_profile, tone=_condition_badge_tone(view.condition_profile)),
                    compact_badge("CapEx", view.capex_lane, tone=_capex_badge_tone(view.capex_lane)),
                    compact_badge("Rent Source", view.income_support.rent_source_type, tone="warning" if view.income_support.rent_source_type != "Provided" else "positive"),
                    compact_badge("Missing Inputs", str(missing_count), tone=missing_tone),
                ],
                style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginTop": "10px"},
            ),
        ],
        style={**CARD_STYLE, **LANE_HEADER_STYLE},
    )


def _comp_trust_badge(view: PropertyAnalysisView) -> tuple[str, str]:
    verification_values = {row.verification for row in view.comps.rows}
    if "Mls Verified" in verification_values:
        return "MLS Verified", "positive"
    if "Public Record Verified" in verification_values:
        return "Public Record Verified", "positive"
    if "Public Record Matched" in verification_values:
        return "Public Record Matched", "warning"
    if view.comps.rows:
        return "Seed / Review Only", "warning"
    return "No Active Comps", "negative"


def _condition_badge_tone(condition_profile: str) -> str:
    normalized = condition_profile.strip().lower()
    if normalized in {"renovated", "updated"}:
        return "positive"
    if normalized in {"maintained", "dated"}:
        return "warning"
    if normalized == "needs work":
        return "negative"
    return "neutral"


def _capex_badge_tone(capex_lane: str) -> str:
    normalized = capex_lane.strip().lower()
    if normalized == "light":
        return "positive"
    if normalized == "moderate":
        return "warning"
    if normalized == "heavy":
        return "negative"
    return "neutral"


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
            from briarwood.dash_app.data_quality import render_data_quality_section  # lazy to avoid circular import
            body = render_data_quality_section(report)
        else:
            body = lane_renderer[section](view, compact=True)
        lanes.append(
            html.Div(
                [_lane_header(view, show_export_button=True), body],
                style={"display": "grid", "gap": "12px"},
            )
        )
    grid = html.Div(
        lanes,
        style={
            "display": "grid",
            "gridTemplateColumns": f"repeat({max(len(lanes),1)}, minmax(280px, 1fr))",
            "gap": "16px",
            "alignItems": "start",
            "overflowX": "auto",
        },
        className="compare-lanes-grid",
    )
    return html.Div(([summary_block] if summary_block else []) + [grid])

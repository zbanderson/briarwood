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
    "width": "300px",
    "padding": "20px",
    "borderRight": "1px solid #d9e1ea",
    "backgroundColor": "#f7f9fb",
    "display": "flex",
    "flexDirection": "column",
    "gap": "16px",
}

PAGE_STYLE = {
    "fontFamily": "Avenir Next, Helvetica Neue, sans-serif",
    "color": "#17324d",
    "backgroundColor": "#fbfcfe",
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
    figure = go.Figure(
        data=[
            go.Bar(
                x=["Bear", "Base", "Bull"],
                y=[view.bear_case or 0, view.base_case or 0, view.bull_case or 0],
                marker_color=["#d97b7b", "#8fa7bf", "#3aaf85"],
                text=[view.forward.bear_value_text, view.forward.base_value_text, view.forward.bull_value_text],
                textposition="outside",
            )
        ]
    )
    figure.add_hline(y=view.ask_price or 0, line_dash="dash", line_color="#17324d")
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
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Focus Property", style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
                            html.H1(view.address, style={"margin": "6px 0"}),
                            html.Div(
                                [html.Span(view.evidence_mode), html.Span(" | "), confidence_badge(view.overall_confidence)],
                                style={"display": "flex", "gap": "8px", "alignItems": "center"},
                            ),
                        ],
                        style={**CARD_STYLE, "gridColumn": "span 2"},
                    ),
                    *[metric_card(chip.label, chip.value, tone=chip.tone) for chip in view.metric_chips[:4]],
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "14px"},
            ),
        ]
    )


def render_overview_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    intro = html.Div(
        [
            html.H2(view.address if not compact else view.label, style={"margin": "0 0 6px 0", "fontSize": "26px" if not compact else "20px"}),
            html.Div(
                [html.Span(view.evidence_mode), html.Span(" | "), confidence_badge(view.overall_confidence)],
                style={"display": "flex", "gap": "8px", "alignItems": "center", "flexWrap": "wrap"},
            ),
        ],
        style=CARD_STYLE,
    )
    cards = html.Div(
        [metric_card(chip.label, chip.value, subtitle=chip.subtitle, tone=chip.tone) for chip in view.metric_chips],
        style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "14px"},
    )
    bullets = html.Div(
        [
            html.Div([html.H3("Top Positives"), html.Ul([html.Li(item) for item in view.top_positives])], style=CARD_STYLE),
            html.Div([html.H3("Top Risks"), html.Ul([html.Li(item) for item in view.top_risks])], style=CARD_STYLE),
        ],
        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"},
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
            style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "14px"},
        ),
        html.Div([html.H3("BCV Components"), simple_table(component_rows, page_size=8)], style=CARD_STYLE),
        html.Div(
            [
                html.Div([html.H3("Comp Verification"), html.P(view.comps.verification_summary), html.P(view.comps.curation_summary)], style=CARD_STYLE),
                html.Div([html.H3("Comp Screening"), html.P(view.comps.screening_summary), html.P(f"Dataset: {view.comps.dataset_name}")], style=CARD_STYLE),
            ],
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"},
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
                style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "14px"},
            )
        )
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_forward_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    metric_rows = [
        {"Metric": "Bear", "Value": view.forward.bear_value_text},
        {"Metric": "Base", "Value": view.forward.base_value_text},
        {"Metric": "Bull", "Value": view.forward.bull_value_text},
        {"Metric": "Market Drift", "Value": view.forward.market_drift_text},
        {"Metric": "Location Premium", "Value": view.forward.location_premium_text},
        {"Metric": "Risk Discount", "Value": view.forward.risk_discount_text},
        {"Metric": "Optionality Premium", "Value": view.forward.optionality_premium_text},
    ]
    blocks = [
        html.Div(
            [
                metric_card("Forward Confidence", f"{view.forward.confidence:.0%}"),
                metric_card("Bear", view.forward.bear_value_text),
                metric_card("Base", view.forward.base_value_text),
                metric_card("Bull", view.forward.bull_value_text),
            ],
            style={"display": "grid", "gridTemplateColumns": "repeat(4, minmax(0, 1fr))", "gap": "14px"},
        ),
        html.Div([html.H3("12-Month Scenario Range"), forward_chart(view, compact=compact)], style=CARD_STYLE),
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
        {"Metric": "Town / County", "Value": f"{view.risk_location.town_score:.1f} ({view.risk_location.town_label})"},
        {"Metric": "Scarcity", "Value": f"{view.risk_location.scarcity_score:.1f}"},
        {"Metric": "Flood", "Value": view.risk_location.flood_risk.title()},
        {"Metric": "Liquidity", "Value": view.risk_location.liquidity_view.title()},
    ]
    blocks = [
        html.Div([html.H3("Location Snapshot"), simple_table(metric_rows, page_size=8)], style=CARD_STYLE),
        html.Div(
            [
                html.Div([html.H3("Demand Drivers"), html.Ul([html.Li(item) for item in view.risk_location.drivers[:8]])], style=CARD_STYLE),
                html.Div([html.H3("Location Risks"), html.Ul([html.Li(item) for item in view.risk_location.risks[:8]])], style=CARD_STYLE),
            ],
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"},
        ),
    ]
    return html.Div(blocks, style={"display": "grid", "gap": "14px"})


def render_income_support_section(view: PropertyAnalysisView, *, compact: bool = False) -> html.Div:
    metric_rows = [
        {"Metric": "Rental Ease", "Value": view.income_support.rental_ease_label},
        {"Metric": "Days to Rent", "Value": view.income_support.estimated_days_to_rent_text},
        {"Metric": "Income Support", "Value": view.income_support.income_support_ratio_text},
        {"Metric": "All-in Cash Flow", "Value": view.income_support.monthly_cash_flow_text},
        {"Metric": "Operating Cash Flow", "Value": view.income_support.operating_cash_flow_text},
        {"Metric": "Rent Source", "Value": view.income_support.rent_source_type},
        {"Metric": "Risk View", "Value": view.income_support.risk_view},
    ]
    blocks = [
        html.Div(
            [
                metric_card("Income Confidence", f"{view.income_support.confidence:.0%}"),
                metric_card("Rental Ease", view.income_support.rental_ease_label),
                metric_card("Income Support", view.income_support.income_support_ratio_text),
            ],
            style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "14px"},
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
                style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "14px"},
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
            style={"display": "grid", "gridTemplateColumns": "repeat(4, minmax(0, 1fr))", "gap": "14px"},
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
                style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "14px"},
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
    return mapping[section](view, compact=False)


def render_compare_summary(section: str, summary: CompareSummary) -> html.Div | None:
    if section != "value":
        return None
    rows = [{"Metric": row.metric, **row.values} for row in summary.rows if row.metric in {"Ask", "BCV", "BCV Delta vs Ask", "Lot Size", "Taxes", "Confidence"}]
    return html.Div(
        [
            html.Div([html.H3("Key Differences"), html.Ul([html.Li(item) for item in summary.why_different[:6]])], style=CARD_STYLE),
            html.Div([html.H3("Value Compare Snapshot"), simple_table(rows, page_size=8)], style=CARD_STYLE),
        ],
        style={"display": "grid", "gridTemplateColumns": "1.2fr 1fr", "gap": "14px", "marginBottom": "16px"},
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
                style={"display": "flex", "justifyContent": "space-between", "gap": "12px", "alignItems": "start"},
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
        style={"display": "grid", "gridTemplateColumns": f"repeat({max(len(lanes),1)}, minmax(0, 1fr))", "gap": "16px", "alignItems": "start"},
    )
    return html.Div(([summary_block] if summary_block else []) + [grid])

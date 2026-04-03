"""
Data Quality scorecard — dark-theme renderer.

Developer / analyst view: comp database health, per-property comp matching,
value driver attribution, and input impact signals.
Not intended for end-user delivery.
"""
from __future__ import annotations

import json
from pathlib import Path

from dash import dash_table, html

from briarwood.agents.comparable_sales.schemas import AdjustedComparable, ComparableSalesOutput
from briarwood.dash_app.components import metric_card, simple_table
from briarwood.dash_app.theme import (
    BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3, BORDER,
    BODY_TEXT_STYLE, CARD_STYLE, GRID_3, GRID_4,
    SECTION_HEADER_STYLE, TABLE_STYLE_CELL, TABLE_STYLE_DATA_EVEN,
    TABLE_STYLE_DATA_ODD, TABLE_STYLE_HEADER, TABLE_STYLE_TABLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TONE_NEGATIVE_TEXT, TONE_POSITIVE_TEXT, TONE_WARNING_TEXT,
    TONE_WARNING_BG,
)
from briarwood.modules.comparable_sales import get_comparable_sales_payload
from briarwood.schemas import AnalysisReport

_SALES_COMPS_PATH = Path(__file__).resolve().parents[2] / "data" / "comps" / "sales_comps.json"


# ── helpers ────────────────────────────────────────────────────────────────────


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1%}"


def _dollar(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def _load_comp_db() -> list[dict]:
    if not _SALES_COMPS_PATH.exists():
        return []
    with _SALES_COMPS_PATH.open() as fh:
        raw = json.load(fh)
    rows = raw.get("sales", raw) if isinstance(raw, dict) else raw
    return rows if isinstance(rows, list) else []


def _dark_table(
    columns: list[str],
    data: list[dict],
    *,
    page_size: int = 15,
    conditional_styles: list[dict] | None = None,
) -> dash_table.DataTable:
    base_conditional = [
        {"if": {"row_index": "odd"}, **TABLE_STYLE_DATA_ODD},
        {"if": {"row_index": "even"}, **TABLE_STYLE_DATA_EVEN},
    ]
    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in columns],
        data=data,
        page_size=page_size,
        style_table=TABLE_STYLE_TABLE,
        style_header=TABLE_STYLE_HEADER,
        style_cell={**TABLE_STYLE_CELL, "whiteSpace": "normal", "height": "auto"},
        style_data_conditional=base_conditional + (conditional_styles or []),
    )


# ── comp database health ────────────────────────────────────────────────────────


def _render_db_health() -> html.Div:
    rows = _load_comp_db()
    if not rows:
        return html.Div(
            html.P("Comp database not found.", style={**BODY_TEXT_STYLE, "color": TONE_NEGATIVE_TEXT}),
            style=CARD_STYLE,
        )

    total = len(rows)

    town_counts: dict[str, int] = {}
    for r in rows:
        town = r.get("town", "Unknown")
        town_counts[town] = town_counts.get(town, 0) + 1

    ver_counts: dict[str, int] = {}
    for r in rows:
        v = r.get("sale_verification_status") or "unknown"
        ver_counts[v] = ver_counts.get(v, 0) + 1

    estimated_dates = sum(1 for r in rows if r.get("verification_notes", "").startswith("sale_date_estimated"))
    real_dates = total - estimated_dates

    fields = ["lot_size", "year_built", "sqft", "beds", "baths", "stories", "garage_spaces"]
    completeness = {f: sum(1 for r in rows if r.get(f) not in (None, "", 0)) / total for f in fields}

    town_table_rows = [{"Town": t, "Count": c, "Coverage": "OK" if c >= 5 else "Low"} for t, c in sorted(town_counts.items(), key=lambda x: -x[1])]
    ver_table_rows = [{"Verification Status": k, "Count": v} for k, v in sorted(ver_counts.items(), key=lambda x: -x[1])]
    completeness_rows = [{"Field": f, "Complete": f"{completeness[f]:.0%}", "Count": f"{int(completeness[f]*total)}/{total}"} for f in fields]

    return html.Div(
        [
            html.Div("Comp Database Health", style=SECTION_HEADER_STYLE),
            html.Div(
                [
                    metric_card("Total Comps", str(total)),
                    metric_card("Towns Covered", str(len(town_counts))),
                    metric_card("Real Sale Dates", str(real_dates), tone="positive" if real_dates > total * 0.5 else "negative"),
                    metric_card("Estimated Dates", str(estimated_dates), tone="negative" if estimated_dates > 0 else "neutral"),
                ],
                style=GRID_4,
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Coverage by Town", style=SECTION_HEADER_STYLE),
                            _dark_table(
                                ["Town", "Count", "Coverage"],
                                town_table_rows,
                                conditional_styles=[
                                    {"if": {"filter_query": '{Coverage} = "Low"', "column_id": "Coverage"}, "color": TONE_NEGATIVE_TEXT, "fontWeight": "600"},
                                    {"if": {"filter_query": '{Coverage} = "OK"', "column_id": "Coverage"}, "color": TONE_POSITIVE_TEXT, "fontWeight": "600"},
                                ],
                            ),
                        ],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div("Verification Tiers", style=SECTION_HEADER_STYLE),
                            _dark_table(["Verification Status", "Count"], ver_table_rows, page_size=10),
                        ],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div("Field Completeness", style=SECTION_HEADER_STYLE),
                            _dark_table(["Field", "Complete", "Count"], completeness_rows, page_size=10),
                        ],
                        style=CARD_STYLE,
                    ),
                ],
                style=GRID_3,
            ),
        ],
        style={"display": "grid", "gap": "12px"},
    )


# ── per-property comp matching ─────────────────────────────────────────────────


def _render_comp_matching(comp_output: ComparableSalesOutput) -> html.Div:
    comps = comp_output.comps_used
    rejected = comp_output.rejected_count
    rejection_reasons = comp_output.rejection_reasons

    if not comps:
        return html.Div(
            [
                html.Div("Comp Matching — This Property", style=SECTION_HEADER_STYLE),
                html.Div(
                    f"No comps used. Rejected: {rejected}. Reasons: {rejection_reasons}",
                    style={"color": TONE_NEGATIVE_TEXT, "fontSize": "13px"},
                ),
            ],
            style=CARD_STYLE,
        )

    avg_similarity = sum(c.similarity_score for c in comps) / len(comps)
    avg_time_adj = sum(c.time_adjustment_pct for c in comps) / len(comps)
    avg_subject_adj = sum(c.subject_adjustment_pct for c in comps) / len(comps)

    comp_rows = [
        {
            "Address": c.address,
            "Sale Price": _dollar(c.sale_price),
            "Time Adj": _pct(c.time_adjustment_pct),
            "Subject Adj": _pct(c.subject_adjustment_pct),
            "Adj Price": _dollar(c.adjusted_price),
            "Similarity": f"{c.similarity_score:.2f}",
            "Fit": c.fit_label,
            "Cautions": "; ".join(c.cautions) if c.cautions else "—",
        }
        for c in comps
    ]
    rejection_rows = [{"Reason": k.replace("_", " "), "Count": v} for k, v in sorted(rejection_reasons.items(), key=lambda x: -x[1])]

    return html.Div(
        [
            html.Div("Comp Matching — This Property", style=SECTION_HEADER_STYLE),
            html.Div(
                [
                    metric_card("Comps Used", str(len(comps))),
                    metric_card("Rejected", str(rejected), tone="negative" if rejected > 10 else "neutral"),
                    metric_card("Avg Similarity", f"{avg_similarity:.2f}"),
                    metric_card("Avg Time Adj", _pct(avg_time_adj)),
                    metric_card("Avg Subject Adj", _pct(avg_subject_adj), tone="positive" if avg_subject_adj >= 0 else "negative"),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(140px, 1fr))", "gap": "12px"},
            ),
            html.Div(
                [
                    html.Div("Comps Used", style=SECTION_HEADER_STYLE),
                    _dark_table(
                        ["Address", "Sale Price", "Time Adj", "Subject Adj", "Adj Price", "Similarity", "Fit", "Cautions"],
                        comp_rows,
                        conditional_styles=[
                            {"if": {"filter_query": '{Fit} = "strong"', "column_id": "Fit"}, "color": TONE_POSITIVE_TEXT, "fontWeight": "600"},
                            {"if": {"filter_query": '{Fit} = "stretch"', "column_id": "Fit"}, "color": TONE_NEGATIVE_TEXT, "fontWeight": "600"},
                        ],
                    ),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Rejection Reasons", style=SECTION_HEADER_STYLE),
                            _dark_table(["Reason", "Count"], rejection_rows or [{"Reason": "No rejections", "Count": 0}], page_size=10),
                        ],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div("Adjustments Detail", style=SECTION_HEADER_STYLE),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(c.address, style={"fontWeight": "600", "fontSize": "12px", "color": TEXT_PRIMARY, "marginBottom": "4px"}),
                                            html.Ul(
                                                [html.Li(note, style={"fontSize": "12px", "color": TEXT_SECONDARY}) for note in c.adjustments_summary],
                                                style={"margin": "0", "paddingLeft": "16px"},
                                            ),
                                        ],
                                        style={"marginBottom": "12px"},
                                    )
                                    for c in comps
                                ]
                            ),
                        ],
                        style=CARD_STYLE,
                    ),
                ],
                style=GRID_3,
            ),
        ],
        style={"display": "grid", "gap": "12px"},
    )


# ── value driver attribution ───────────────────────────────────────────────────


def _render_value_attribution(report: AnalysisReport, comp_output: ComparableSalesOutput | None) -> html.Div:
    cv_result = report.module_results.get("current_value")
    if cv_result is None:
        return html.Div(html.P("Current value module not available.", style=BODY_TEXT_STYLE), style=CARD_STYLE)

    payload = cv_result.payload
    components = getattr(payload, "components", None)

    blend_rows: list[dict] = []
    if components is not None:
        blend_map = [
            ("Comparable Sales (45%)", getattr(components, "comparable_value", None)),
            ("Market Adjusted / ZHVI (30%)", getattr(components, "market_adjusted_value", None)),
            ("Backdated Listing (15%)", getattr(components, "backdated_listing_value", None)),
            ("Income Supported (10%)", getattr(components, "income_supported_value", None)),
        ]
        ask = getattr(payload, "ask_price", None)
        for label, val in blend_map:
            delta_pct = None
            if val is not None and ask and ask > 0:
                delta_pct = (val - ask) / ask
            flag = ""
            if delta_pct is not None and abs(delta_pct) > 0.20:
                flag = "HIGH DELTA"
            elif delta_pct is not None and abs(delta_pct) > 0.10:
                flag = "mod delta"
            blend_rows.append({
                "Component": label,
                "Value": _dollar(val),
                "vs Ask": _pct(delta_pct) if delta_pct is not None else "—",
                "Flag": flag,
            })

    location_signals: list[dict] = []
    if comp_output and comp_output.comps_used:
        tag_counter: dict[str, list[float]] = {}
        for comp in comp_output.comps_used:
            for tag in comp.location_tags:
                tag_counter.setdefault(tag, []).append(comp.similarity_score)
        for tag, scores in sorted(tag_counter.items()):
            avg_score = sum(scores) / len(scores)
            location_signals.append({
                "Tag": tag,
                "Comps": len(scores),
                "Avg Similarity": f"{avg_score:.2f}",
                "Note": "Shared tag — confirms match" if avg_score >= 0.70 else "Low similarity despite shared tag",
            })

    adj_analysis: list[dict] = []
    if comp_output and comp_output.comps_used:
        net_pushes: dict[str, list[float]] = {}
        for comp in comp_output.comps_used:
            for note in comp.adjustments_summary:
                note_lower = note.lower()
                pct_push = comp.subject_adjustment_pct
                if "bed" in note_lower:
                    net_pushes.setdefault("beds", []).append(pct_push)
                elif "bath" in note_lower:
                    net_pushes.setdefault("baths", []).append(pct_push)
                elif "sqft" in note_lower or "square" in note_lower:
                    net_pushes.setdefault("sqft", []).append(pct_push)
                elif "lot" in note_lower:
                    net_pushes.setdefault("lot_size", []).append(pct_push)
                elif "capex" in note_lower:
                    net_pushes.setdefault("capex_lane", []).append(pct_push)
                elif "beach" in note_lower or "ocean" in note_lower or "water" in note_lower:
                    net_pushes.setdefault("water_proximity", []).append(pct_push)
        for factor, pushes in sorted(net_pushes.items()):
            avg = sum(pushes) / len(pushes)
            direction = "UP" if avg > 0.005 else ("DOWN" if avg < -0.005 else "neutral")
            alert = ""
            if factor == "water_proximity" and direction == "DOWN":
                alert = "UNEXPECTED — beach proximity reducing value"
            adj_analysis.append({
                "Input Factor": factor,
                "Avg Push": _pct(avg),
                "Direction": direction,
                "Alert": alert,
            })

    return html.Div(
        [
            html.Div("Value Driver Attribution", style=SECTION_HEADER_STYLE),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("BCV Blend Components", style=SECTION_HEADER_STYLE),
                            html.P("Each component vs. ask. HIGH DELTA = diverges >20% from ask.", style={**BODY_TEXT_STYLE, "marginBottom": "8px"}),
                            _dark_table(
                                ["Component", "Value", "vs Ask", "Flag"],
                                blend_rows,
                                page_size=6,
                                conditional_styles=[
                                    {"if": {"filter_query": '{Flag} = "HIGH DELTA"', "column_id": "Flag"}, "color": TONE_NEGATIVE_TEXT, "fontWeight": "700"},
                                    {"if": {"filter_query": '{Flag} = "mod delta"', "column_id": "Flag"}, "color": TONE_WARNING_TEXT, "fontWeight": "600"},
                                ],
                            ),
                        ],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div("Input Factor Push Direction", style=SECTION_HEADER_STYLE),
                            html.P("Avg subject adjustment per factor across used comps.", style={**BODY_TEXT_STYLE, "marginBottom": "8px"}),
                            _dark_table(
                                ["Input Factor", "Avg Push", "Direction", "Alert"],
                                adj_analysis or [{"Input Factor": "No adjustment data", "Avg Push": "—", "Direction": "—", "Alert": ""}],
                                page_size=10,
                                conditional_styles=[
                                    {"if": {"filter_query": '{Direction} = "UP"', "column_id": "Direction"}, "color": TONE_POSITIVE_TEXT, "fontWeight": "600"},
                                    {"if": {"filter_query": '{Direction} = "DOWN"', "column_id": "Direction"}, "color": TONE_NEGATIVE_TEXT, "fontWeight": "600"},
                                    {"if": {"filter_query": '{Alert} != ""', "column_id": "Alert"}, "color": TONE_NEGATIVE_TEXT, "fontWeight": "700"},
                                ],
                            ),
                        ],
                        style=CARD_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div("Location Tags in Used Comps", style=SECTION_HEADER_STYLE),
                            _dark_table(
                                ["Tag", "Comps", "Avg Similarity", "Note"],
                                location_signals or [{"Tag": "No location tags found", "Comps": 0, "Avg Similarity": "—", "Note": ""}],
                                page_size=10,
                            ),
                        ],
                        style=CARD_STYLE,
                    ),
                ],
                style=GRID_3,
            ),
        ],
        style={"display": "grid", "gap": "12px"},
    )


# ── public entry point ─────────────────────────────────────────────────────────


def render_data_quality_section(report: AnalysisReport) -> html.Div:
    comp_output: ComparableSalesOutput | None = None
    comp_result = report.module_results.get("comparable_sales")
    if comp_result is not None:
        try:
            comp_output = get_comparable_sales_payload(comp_result)
        except TypeError:
            pass

    banner = html.Div(
        "Developer view — comp database health, matching detail, and value driver signals. Not for client delivery.",
        style={
            "backgroundColor": TONE_WARNING_BG,
            "border": f"1px solid #6a4f0e",
            "borderRadius": "6px",
            "padding": "10px 14px",
            "fontSize": "13px",
            "color": TONE_WARNING_TEXT,
        },
    )

    blocks = [
        banner,
        _render_db_health(),
        _render_comp_matching(comp_output) if comp_output is not None else html.Div(
            html.P("No comp output available for this property.", style=BODY_TEXT_STYLE),
            style=CARD_STYLE,
        ),
        _render_value_attribution(report, comp_output),
    ]
    return html.Div(blocks, style={"display": "grid", "gap": "20px"})

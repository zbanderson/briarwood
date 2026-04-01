from __future__ import annotations

import os

from dash import ALL, Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update

from briarwood.dash_app.compare import build_compare_summary
from briarwood.dash_app.components import (
    PAGE_STYLE,
    SIDEBAR_STYLE,
    render_compare_section,
    render_single_section,
    summary_strip,
)
from briarwood.dash_app.data import (
    DEFAULT_PRESET_IDS,
    export_preset_tear_sheet,
    list_presets,
    list_saved_properties,
    load_report_for_preset,
    load_reports,
    register_manual_analysis,
)
from briarwood.dash_app.view_models import build_property_analysis_view


app = Dash(
    __name__,
    title="Briarwood Workspace",
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

SECTION_TABS = [
    ("overview", "Overview"),
    ("value", "Value"),
    ("forward", "Forward"),
    ("risk", "Risk"),
    ("location", "Location"),
    ("income", "Income Support"),
    ("evidence", "Evidence"),
    ("data_quality", "Data Quality"),
]

CONDITION_OPTIONS = [
    {"label": "Unavailable", "value": ""},
    {"label": "Renovated", "value": "renovated"},
    {"label": "Updated", "value": "updated"},
    {"label": "Maintained", "value": "maintained"},
    {"label": "Dated", "value": "dated"},
    {"label": "Needs Work", "value": "needs_work"},
]

CAPEX_OPTIONS = [
    {"label": "Unavailable", "value": ""},
    {"label": "Light", "value": "light"},
    {"label": "Moderate", "value": "moderate"},
    {"label": "Heavy", "value": "heavy"},
]

YES_NO_OPTIONS = [
    {"label": "Unknown", "value": ""},
    {"label": "Yes", "value": "true"},
    {"label": "No", "value": "false"},
]

GARAGE_TYPE_OPTIONS = [
    {"label": "Unavailable", "value": ""},
    {"label": "Attached", "value": "attached"},
    {"label": "Detached", "value": "detached"},
    {"label": "Built-In", "value": "built_in"},
]

ADU_TYPE_OPTIONS = [
    {"label": "Unavailable", "value": ""},
    {"label": "Studio Over Garage", "value": "studio_over_garage"},
    {"label": "Detached Cottage", "value": "detached_cottage"},
    {"label": "Basement Unit", "value": "basement_unit"},
    {"label": "Guest Suite", "value": "guest_suite"},
]


def _property_options() -> list[dict[str, str]]:
    saved_by_id = {item.property_id: item for item in list_saved_properties()}
    options: list[dict[str, str]] = []
    for preset in list_presets():
        saved = saved_by_id.get(preset.preset_id)
        if saved is not None:
            label = f"{saved.label} | {_fmt_currency(saved.ask_price)} | saved"
        else:
            label = preset.label
        options.append({"label": label, "value": preset.preset_id})
    return options


def _saved_property_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in list_saved_properties():
        rows.append(
            {
                "property_id": item.property_id,
                "Address": item.address,
                "Ask": _fmt_currency(item.ask_price),
                "BCV": _fmt_currency(item.bcv),
                "Pricing View": item.pricing_view.replace("_", " ").title(),
                "Confidence": f"{item.confidence:.0%}",
                "Comp Trust": item.comp_trust,
                "Missing Inputs": str(item.missing_input_count),
                "Saved": item.timestamp[:16].replace("T", " "),
            }
        )
    return rows


def _fmt_currency(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"${value:,.0f}"


def _text_input(input_id: str, placeholder: str, *, value: str | None = None) -> dcc.Input:
    return dcc.Input(id=input_id, placeholder=placeholder, type="text", value=value)


def _number_input(input_id: str, placeholder: str) -> dcc.Input:
    return dcc.Input(id=input_id, placeholder=placeholder, type="number")


def _dropdown(input_id: str, options: list[dict[str, str]], placeholder: str) -> dcc.Dropdown:
    return dcc.Dropdown(id=input_id, options=options, value="", placeholder=placeholder, clearable=False)


def _build_layout():
    return html.Div(
        [
            dcc.Store(id="loaded-preset-ids", data=DEFAULT_PRESET_IDS),
            dcc.Store(id="manual-comps-store", data=[]),
            dcc.Store(id="property-catalog-version", data=0),
            dcc.Store(id="add-property-open", data=False),
            dcc.Store(id="last-analysis-summary", data=None),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Briarwood Workspace", style={"margin": 0}),
                                    html.Div("Interactive decision layer for value, risk, income support, and evidence.", style={"color": "#5f7286"}),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Button("Add Property", id="add-property-button", n_clicks=0),
                                    html.Div(
                                        [
                                            html.Label("Select Property"),
                                            dcc.Dropdown(id="property-selector-dropdown", clearable=False, persistence=True),
                                        ],
                                        style={"minWidth": "280px", "flex": "1"},
                                    ),
                                    html.Div(
                                        [
                                            html.Label("Compare Properties"),
                                            dcc.Dropdown(id="compare-selector-dropdown", multi=True, persistence=True),
                                        ],
                                        style={"minWidth": "320px", "flex": "1.2"},
                                    ),
                                    html.Div(
                                        [
                                            html.Label("Mode"),
                                            dcc.RadioItems(
                                                id="workspace-mode",
                                                options=[
                                                    {"label": "Single Property", "value": "single"},
                                                    {"label": "Compare", "value": "compare"},
                                                ],
                                                value="single",
                                                inline=True,
                                            ),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            html.Button("Export Tear Sheet", id="export-tear-sheet-button", n_clicks=0),
                                            html.Div(id="export-status", style={"fontSize": "13px", "color": "#5f7286"}),
                                        ],
                                        style={"display": "grid", "gap": "6px"},
                                    ),
                                ],
                                style={"display": "flex", "gap": "14px", "alignItems": "end", "flexWrap": "wrap"},
                            ),
                            html.Div(id="analysis-feedback-banner"),
                            html.Div(id="active-property-status", style={"fontSize": "13px", "color": "#5f7286"}),
                        ],
                        style={
                            "backgroundColor": "white",
                            "borderBottom": "1px solid #d9e1ea",
                            "padding": "16px clamp(16px, 2.5vw, 28px)",
                            "display": "grid",
                            "gap": "14px",
                        },
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H3("Saved Properties", style={"margin": "0 0 8px 0"}),
                                            dash_table.DataTable(
                                                id="saved-properties-table",
                                                columns=[
                                                    {"name": "Address", "id": "Address"},
                                                    {"name": "Ask", "id": "Ask"},
                                                    {"name": "BCV", "id": "BCV"},
                                                    {"name": "Pricing View", "id": "Pricing View"},
                                                    {"name": "Confidence", "id": "Confidence"},
                                                    {"name": "Comp Trust", "id": "Comp Trust"},
                                                    {"name": "Missing Inputs", "id": "Missing Inputs"},
                                                ],
                                                data=[],
                                                row_selectable="multi",
                                                selected_rows=[],
                                                page_size=8,
                                                style_table={"overflowX": "auto", "maxWidth": "100%", "width": "100%"},
                                                style_cell={
                                                    "padding": "8px",
                                                    "textAlign": "left",
                                                    "fontFamily": "Avenir Next, Helvetica Neue, sans-serif",
                                                    "fontSize": "12px",
                                                    "whiteSpace": "normal",
                                                    "height": "auto",
                                                    "minWidth": "72px",
                                                    "maxWidth": "150px",
                                                },
                                                style_header={"backgroundColor": "#edf3f8", "fontWeight": "700"},
                                            ),
                                            html.Button("Compare Selected", id="compare-selected-button", n_clicks=0),
                                        ],
                                        style={"display": "grid", "gap": "10px"},
                                    ),
                                    html.Hr(),
                                    html.Div(
                                        [
                                            html.H3("Add Property", style={"margin": "0 0 8px 0"}),
                                            html.Div("Core facts", style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
                                            _text_input("manual-property-id", "Property id (optional)"),
                                            _text_input("manual-address", "Address"),
                                            html.Div(
                                                [
                                                    _text_input("manual-town", "Town", value="Belmar"),
                                                    _text_input("manual-state", "State", value="NJ"),
                                                    _text_input("manual-county", "County", value="Monmouth"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "1fr 90px 1fr", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _number_input("manual-price", "Ask price"),
                                                    _number_input("manual-beds", "Beds"),
                                                    _number_input("manual-baths", "Baths"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _number_input("manual-sqft", "Sqft"),
                                                    _number_input("manual-lot-size", "Lot size (acres)"),
                                                    _number_input("manual-year-built", "Year built"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _number_input("manual-taxes", "Taxes"),
                                                    _number_input("manual-hoa", "HOA / month"),
                                                    _number_input("manual-dom", "Days on market"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            _text_input("manual-property-type", "Property type", value="Single Family Residence"),
                                            html.Div("Physical differentiators", style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
                                            html.Div(
                                                [
                                                    _number_input("manual-garage-spaces", "Garage spaces"),
                                                    _dropdown("manual-garage-type", GARAGE_TYPE_OPTIONS, "Garage type"),
                                                    _dropdown("manual-has-detached-garage", YES_NO_OPTIONS, "Detached garage"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _dropdown("manual-has-back-house", YES_NO_OPTIONS, "Back house / ADU"),
                                                    _dropdown("manual-adu-type", ADU_TYPE_OPTIONS, "ADU type"),
                                                    _number_input("manual-adu-sqft", "ADU sqft"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _dropdown("manual-has-basement", YES_NO_OPTIONS, "Has basement"),
                                                    _dropdown("manual-basement-finished", YES_NO_OPTIONS, "Basement finished"),
                                                    _dropdown("manual-has-pool", YES_NO_OPTIONS, "Has pool"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _number_input("manual-parking-spaces", "Parking spaces"),
                                                    _dropdown("manual-corner-lot", YES_NO_OPTIONS, "Corner lot"),
                                                    _dropdown("manual-driveway-off-street", YES_NO_OPTIONS, "Driveway / off-street"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Dropdown(id="manual-condition-profile", options=CONDITION_OPTIONS, value="", placeholder="Condition", clearable=False),
                                                    dcc.Dropdown(id="manual-capex-lane", options=CAPEX_OPTIONS, value="", placeholder="CapEx lane", clearable=False),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                            ),
                                            html.Div("Income / support inputs", style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
                                            html.Div(
                                                [
                                                    _number_input("manual-estimated-rent", "Estimated market rent"),
                                                    _number_input("manual-back-house-rent", "Back house rent"),
                                                    _number_input("manual-seasonal-rent", "Seasonal rent"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _number_input("manual-insurance", "Insurance estimate"),
                                                    _number_input("manual-maintenance-reserve", "Maintenance reserve / month"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                            ),
                                            dcc.Textarea(id="manual-notes", placeholder="Notes", style={"width": "100%", "height": "70px"}),
                                            html.Div("Optional manual comps", style={"fontSize": "12px", "textTransform": "uppercase", "color": "#6b7b8d"}),
                                            _text_input("manual-comp-address", "Comp address"),
                                            html.Div(
                                                [
                                                    _number_input("manual-comp-sale-price", "Sale price"),
                                                    _text_input("manual-comp-sale-date", "Sale date YYYY-MM-DD"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _number_input("manual-comp-beds", "Beds"),
                                                    _number_input("manual-comp-baths", "Baths"),
                                                    _number_input("manual-comp-sqft", "Sqft"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _number_input("manual-comp-lot-size", "Lot size (acres)"),
                                                    _number_input("manual-comp-year-built", "Year built"),
                                                    _number_input("manual-comp-distance", "Distance miles"),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "8px"},
                                            ),
                                            html.Div(
                                                [
                                                    _text_input("manual-comp-property-type", "Property type", value="Single Family Residence"),
                                                    dcc.Dropdown(id="manual-comp-condition-profile", options=CONDITION_OPTIONS, value="", placeholder="Comp condition", clearable=False),
                                                ],
                                                style={"display": "grid", "gridTemplateColumns": "1.3fr 1fr", "gap": "8px"},
                                            ),
                                            dcc.Textarea(id="manual-comp-notes", placeholder="Comp notes", style={"width": "100%", "height": "60px"}),
                                            html.Button("Add Comp", id="manual-add-comp-button", n_clicks=0),
                                            html.Div(id="manual-comps-preview", style={"fontSize": "12px", "color": "#5f7286"}),
                                            html.Button("Analyze Property", id="manual-run-analysis-button", n_clicks=0),
                                            html.Div(id="manual-entry-status", style={"fontSize": "13px", "color": "#5f7286"}),
                                        ],
                                        id="add-property-form",
                                        style={"display": "grid", "gap": "8px"},
                                    ),
                                ],
                                style=SIDEBAR_STYLE,
                                className="workspace-sidebar",
                            ),
                            html.Div(
                                [
                                    html.Div(id="top-summary"),
                                    dcc.Tabs(
                                        id="section-tabs",
                                        value="overview",
                                        children=[dcc.Tab(label=label, value=value) for value, label in SECTION_TABS],
                                        style={"marginTop": "12px"},
                                    ),
                                    html.Div(id="workspace-tab-content", style={"marginTop": "16px"}),
                                ],
                                style={"flex": "1", "padding": "clamp(16px, 2.5vw, 28px)", "minWidth": 0},
                                className="workspace-main",
                            ),
                        ],
                        style={"display": "flex", "minHeight": "calc(100vh - 120px)", "alignItems": "stretch"},
                        className="workspace-shell",
                    ),
                ]
            ),
        ],
        style=PAGE_STYLE,
    )


app.layout = _build_layout()


@app.callback(
    Output("property-selector-dropdown", "options"),
    Output("property-selector-dropdown", "value"),
    Output("compare-selector-dropdown", "options"),
    Output("compare-selector-dropdown", "value"),
    Output("saved-properties-table", "data"),
    Input("property-catalog-version", "data"),
    Input("loaded-preset-ids", "data"),
    State("property-selector-dropdown", "value"),
    State("compare-selector-dropdown", "value"),
)
def refresh_property_controls(
    _catalog_version: int,
    loaded_ids: list[str] | None,
    current_property_id: str | None,
    current_compare_ids: list[str] | None,
):
    options = _property_options()
    allowed = {option["value"] for option in options}
    loaded_ids = [property_id for property_id in (loaded_ids or []) if property_id in allowed]
    property_value = current_property_id if current_property_id in allowed else (loaded_ids[0] if loaded_ids else None)
    compare_values = [property_id for property_id in (current_compare_ids or loaded_ids) if property_id in allowed][:4]
    return options, property_value, options, compare_values, _saved_property_rows()


@app.callback(
    Output("active-property-status", "children"),
    Input("property-selector-dropdown", "value"),
)
def render_active_property_status(property_id: str | None):
    if not property_id:
        return "No active property selected."
    try:
        report = load_report_for_preset(property_id)
    except KeyError:
        return "Selected property is unavailable."
    view = build_property_analysis_view(report)
    return (
        f"Active property: {view.address} | Ask: {_fmt_currency(view.ask_price)} | "
        f"BCV: {_fmt_currency(view.bcv)} | Confidence: {view.overall_confidence:.0%}"
    )


@app.callback(
    Output("analysis-feedback-banner", "children"),
    Input("last-analysis-summary", "data"),
)
def render_analysis_feedback(summary: dict[str, str] | None):
    if not summary:
        return html.Div(
            "Saved analyses reopen from persisted results. Add a property to create a new saved analysis.",
            className="analysis-feedback-banner analysis-feedback-banner--neutral",
        )
    return html.Div(
        [
            html.Div("Analysis Saved And Loaded", style={"fontWeight": "700"}),
            html.Div(
                f"{summary.get('address', 'Property')} | Ask: {summary.get('ask_price', 'Unavailable')} | "
                f"Comps: {summary.get('comp_count', '0')} | Evidence: {summary.get('mode', 'Unknown')}"
            ),
            html.Div(
                [
                    "Saved id: ",
                    html.Code(summary.get("property_id", "")),
                    html.Span(" | "),
                    "Tear sheet: ",
                    html.Code(summary.get("tear_sheet_path", "")),
                ],
                style={"fontSize": "12px"},
            ),
        ],
        className="analysis-feedback-banner analysis-feedback-banner--positive",
    )


@app.callback(
    Output("loaded-preset-ids", "data", allow_duplicate=True),
    Output("workspace-mode", "value", allow_duplicate=True),
    Input("property-selector-dropdown", "value"),
    prevent_initial_call=True,
)
def select_property(property_id: str | None):
    if not property_id:
        return no_update, no_update
    load_reports([property_id])
    return [property_id], "single"


@app.callback(
    Output("loaded-preset-ids", "data", allow_duplicate=True),
    Output("workspace-mode", "value", allow_duplicate=True),
    Input("compare-selector-dropdown", "value"),
    prevent_initial_call=True,
)
def select_compare_properties(property_ids: list[str] | None):
    property_ids = [property_id for property_id in (property_ids or [])][:4]
    if not property_ids:
        return no_update, no_update
    load_reports(property_ids)
    return property_ids, ("compare" if len(property_ids) > 1 else "single")


@app.callback(
    Output("loaded-preset-ids", "data", allow_duplicate=True),
    Output("compare-selector-dropdown", "value", allow_duplicate=True),
    Output("property-selector-dropdown", "value", allow_duplicate=True),
    Output("workspace-mode", "value", allow_duplicate=True),
    Input("compare-selected-button", "n_clicks"),
    State("saved-properties-table", "data"),
    State("saved-properties-table", "selected_rows"),
    prevent_initial_call=True,
)
def compare_selected_saved_properties(
    _n_clicks: int,
    rows: list[dict[str, str]] | None,
    selected_rows: list[int] | None,
):
    if not rows or not selected_rows:
        return no_update, no_update, no_update, no_update
    property_ids = [rows[index]["property_id"] for index in selected_rows if 0 <= index < len(rows)][:4]
    if not property_ids:
        return no_update, no_update, no_update, no_update
    load_reports(property_ids)
    return property_ids, property_ids, no_update, ("compare" if len(property_ids) > 1 else "single")


@app.callback(
    Output("top-summary", "children"),
    Output("workspace-tab-content", "children"),
    Input("workspace-mode", "value"),
    Input("section-tabs", "value"),
    Input("loaded-preset-ids", "data"),
    Input("property-selector-dropdown", "value"),
)
def render_workspace(mode: str, section_value: str, loaded_ids: list[str] | None, focus_id: str | None):
    loaded_ids = loaded_ids or []
    if not loaded_ids:
        empty = html.Div("Add or select a property to start the workspace.")
        return empty, empty
    reports = load_reports(loaded_ids)
    if not reports:
        empty = html.Div("Selected properties are unavailable.")
        return empty, empty
    focus_id = focus_id if focus_id in reports else next(iter(reports.keys()))
    focus_report = reports[focus_id]
    focus_view = build_property_analysis_view(focus_report)
    report_list = list(reports.values())
    compare_views = [build_property_analysis_view(report) for report in report_list]

    if mode == "single":
        summary = summary_strip(focus_view)
        content = render_single_section(section_value, focus_view, focus_report)
    else:
        summary = html.Div(
            [
                html.Div(
                    [
                        html.H1("Compare View", style={"margin": "0 0 6px 0"}),
                        html.Div(
                            f"{len(compare_views)} properties loaded. Each lane shows the same Briarwood section side by side.",
                            style={"color": "#5f7286"},
                        ),
                    ],
                    style={"backgroundColor": "white", "border": "1px solid #dde4ec", "borderRadius": "12px", "padding": "16px"},
                )
            ]
        )
        content = render_compare_section(section_value, compare_views, report_list, build_compare_summary(compare_views))
    return summary, content


@app.callback(
    Output("export-status", "children"),
    Input("export-tear-sheet-button", "n_clicks"),
    State("property-selector-dropdown", "value"),
    prevent_initial_call=True,
)
def export_tear_sheet(_n_clicks: int, property_id: str | None):
    if not property_id:
        return "Choose a property before exporting."
    output_path = export_preset_tear_sheet(property_id)
    return html.Div(["Tear sheet ready: ", html.Code(str(output_path))])


@app.callback(
    Output("export-status", "children", allow_duplicate=True),
    Input({"type": "lane-export-button", "property_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def export_lane_tear_sheet(_clicks: list[int]):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return "Choose a property before exporting."
    property_id = triggered.get("property_id")
    if not isinstance(property_id, str):
        return "Choose a property before exporting."
    output_path = export_preset_tear_sheet(property_id)
    return html.Div(["Tear sheet ready: ", html.Code(str(output_path))])


@app.callback(
    Output("add-property-open", "data"),
    Input("add-property-button", "n_clicks"),
    State("add-property-open", "data"),
    prevent_initial_call=True,
)
def toggle_add_property_form(_n_clicks: int, is_open: bool | None):
    return not bool(is_open)


@app.callback(
    Output("add-property-form", "style"),
    Input("add-property-open", "data"),
)
def set_add_property_form_style(is_open: bool | None):
    return {"display": "grid", "gap": "8px"} if is_open else {"display": "none"}


@app.callback(
    Output("manual-comps-store", "data"),
    Output("manual-entry-status", "children", allow_duplicate=True),
    Input("manual-add-comp-button", "n_clicks"),
    State("manual-comps-store", "data"),
    State("manual-town", "value"),
    State("manual-state", "value"),
    State("manual-comp-address", "value"),
    State("manual-comp-sale-price", "value"),
    State("manual-comp-sale-date", "value"),
    State("manual-comp-beds", "value"),
    State("manual-comp-baths", "value"),
    State("manual-comp-sqft", "value"),
    State("manual-comp-lot-size", "value"),
    State("manual-comp-year-built", "value"),
    State("manual-comp-property-type", "value"),
    State("manual-comp-distance", "value"),
    State("manual-comp-condition-profile", "value"),
    State("manual-comp-notes", "value"),
    prevent_initial_call=True,
)
def add_manual_comp(
    _n_clicks: int,
    current_comps: list[dict[str, object]] | None,
    town: str | None,
    state: str | None,
    address: str | None,
    sale_price: float | None,
    sale_date: str | None,
    beds: float | None,
    baths: float | None,
    sqft: float | None,
    lot_size: float | None,
    year_built: float | None,
    property_type: str | None,
    distance: float | None,
    condition_profile: str | None,
    notes: str | None,
):
    comps = list(current_comps or [])
    if not address or sale_price in (None, "") or not sale_date:
        return no_update, "Comp needs at least address, sale price, and sale date."
    if len(comps) >= 10:
        return no_update, "Comp limit reached for v1 manual entry (10 comps)."
    comp = {
        "address": address,
        "town": town or "Unknown",
        "state": state or "NJ",
        "sale_price": sale_price,
        "sale_date": sale_date,
        "beds": int(beds) if beds not in (None, "") else None,
        "baths": float(baths) if baths not in (None, "") else None,
        "sqft": int(sqft) if sqft not in (None, "") else None,
        "lot_size": float(lot_size) if lot_size not in (None, "") else None,
        "year_built": int(year_built) if year_built not in (None, "") else None,
        "property_type": property_type or None,
        "distance_to_subject_miles": float(distance) if distance not in (None, "") else None,
        "condition_profile": condition_profile or None,
        "capex_lane": _capex_from_condition(condition_profile),
        "source_name": "manual comp entry",
        "source_quality": "manual",
        "source_ref": f"manual-{len(comps) + 1}",
        "source_notes": notes or None,
        "comp_status": "seeded",
        "address_verification_status": "verified",
        "sale_verification_status": "seeded",
        "verification_source_type": "manual_review",
        "verification_source_name": "manual comp entry",
        "verification_source_id": f"manual-{len(comps) + 1}",
        "micro_location_notes": [notes] if notes else [],
    }
    comps.append(comp)
    return comps, f"Added comp {len(comps)}: {address}"


@app.callback(
    Output("manual-comps-preview", "children"),
    Input("manual-comps-store", "data"),
)
def render_manual_comp_preview(comps: list[dict[str, object]] | None):
    comps = comps or []
    if not comps:
        return "No manual comps added yet."
    cards = []
    for index, comp in enumerate(comps):
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(f"{index + 1}. {comp.get('address')}", style={"fontWeight": "600"}),
                            html.Div(f"${float(comp.get('sale_price', 0)):,.0f} | {comp.get('sale_date')}", style={"fontSize": "12px"}),
                        ]
                    ),
                    html.Div(
                        [
                            html.Button("Edit", id={"type": "manual-edit-comp-button", "index": index}, n_clicks=0),
                            html.Button("Remove", id={"type": "manual-remove-comp-button", "index": index}, n_clicks=0),
                        ],
                        style={"display": "flex", "gap": "6px"},
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "border": "1px solid #d9e1ea",
                    "borderRadius": "8px",
                    "padding": "8px",
                    "backgroundColor": "white",
                    "gap": "8px",
                },
            )
        )
    return html.Div(cards, style={"display": "grid", "gap": "8px"})


@app.callback(
    Output("manual-comps-store", "data", allow_duplicate=True),
    Output("manual-comp-address", "value"),
    Output("manual-comp-sale-price", "value"),
    Output("manual-comp-sale-date", "value"),
    Output("manual-comp-beds", "value"),
    Output("manual-comp-baths", "value"),
    Output("manual-comp-sqft", "value"),
    Output("manual-comp-lot-size", "value"),
    Output("manual-comp-year-built", "value"),
    Output("manual-comp-property-type", "value"),
    Output("manual-comp-distance", "value"),
    Output("manual-comp-condition-profile", "value"),
    Output("manual-comp-notes", "value"),
    Output("manual-entry-status", "children", allow_duplicate=True),
    Input({"type": "manual-edit-comp-button", "index": ALL}, "n_clicks"),
    Input({"type": "manual-remove-comp-button", "index": ALL}, "n_clicks"),
    State("manual-comps-store", "data"),
    prevent_initial_call=True,
)
def manage_manual_comps(
    _edit_clicks: list[int],
    _remove_clicks: list[int],
    current_comps: list[dict[str, object]] | None,
):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return (no_update,) * 14
    comps = list(current_comps or [])
    index = triggered.get("index")
    if not isinstance(index, int) or index < 0 or index >= len(comps):
        return (no_update,) * 14
    comp = comps.pop(index)
    if triggered.get("type") == "manual-remove-comp-button":
        return comps, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, f"Removed comp {index + 1}: {comp.get('address')}"
    return (
        comps,
        comp.get("address"),
        comp.get("sale_price"),
        comp.get("sale_date"),
        comp.get("beds"),
        comp.get("baths"),
        comp.get("sqft"),
        comp.get("lot_size"),
        comp.get("year_built"),
        comp.get("property_type") or "Single Family Residence",
        comp.get("distance_to_subject_miles"),
        comp.get("condition_profile") or "",
        comp.get("source_notes") or "",
        f"Editing comp {index + 1}: {comp.get('address')}",
    )


@app.callback(
    Output("loaded-preset-ids", "data", allow_duplicate=True),
    Output("manual-entry-status", "children", allow_duplicate=True),
    Output("property-catalog-version", "data", allow_duplicate=True),
    Output("property-selector-dropdown", "value", allow_duplicate=True),
    Output("compare-selector-dropdown", "value", allow_duplicate=True),
    Output("workspace-mode", "value", allow_duplicate=True),
    Output("add-property-open", "data", allow_duplicate=True),
    Output("last-analysis-summary", "data", allow_duplicate=True),
    Input("manual-run-analysis-button", "n_clicks"),
    State("property-catalog-version", "data"),
    State("manual-comps-store", "data"),
    State("manual-property-id", "value"),
    State("manual-address", "value"),
    State("manual-town", "value"),
    State("manual-state", "value"),
    State("manual-county", "value"),
    State("manual-price", "value"),
    State("manual-beds", "value"),
    State("manual-baths", "value"),
    State("manual-sqft", "value"),
    State("manual-lot-size", "value"),
    State("manual-year-built", "value"),
    State("manual-property-type", "value"),
    State("manual-taxes", "value"),
    State("manual-hoa", "value"),
    State("manual-dom", "value"),
    State("manual-garage-spaces", "value"),
    State("manual-garage-type", "value"),
    State("manual-has-detached-garage", "value"),
    State("manual-has-back-house", "value"),
    State("manual-adu-type", "value"),
    State("manual-adu-sqft", "value"),
    State("manual-has-basement", "value"),
    State("manual-basement-finished", "value"),
    State("manual-has-pool", "value"),
    State("manual-parking-spaces", "value"),
    State("manual-corner-lot", "value"),
    State("manual-driveway-off-street", "value"),
    State("manual-estimated-rent", "value"),
    State("manual-back-house-rent", "value"),
    State("manual-seasonal-rent", "value"),
    State("manual-insurance", "value"),
    State("manual-maintenance-reserve", "value"),
    State("manual-condition-profile", "value"),
    State("manual-capex-lane", "value"),
    State("manual-notes", "value"),
    prevent_initial_call=True,
)
def run_manual_analysis(
    _n_clicks: int,
    catalog_version: int | None,
    comps: list[dict[str, object]] | None,
    property_id: str | None,
    address: str | None,
    town: str | None,
    state: str | None,
    county: str | None,
    price: float | None,
    beds: float | None,
    baths: float | None,
    sqft: float | None,
    lot_size: float | None,
    year_built: float | None,
    property_type: str | None,
    taxes: float | None,
    monthly_hoa: float | None,
    days_on_market: float | None,
    garage_spaces: float | None,
    garage_type: str | None,
    has_detached_garage: str | None,
    has_back_house: str | None,
    adu_type: str | None,
    adu_sqft: float | None,
    has_basement: str | None,
    basement_finished: str | None,
    has_pool: str | None,
    parking_spaces: float | None,
    corner_lot: str | None,
    driveway_off_street: str | None,
    estimated_rent: float | None,
    back_house_rent: float | None,
    seasonal_rent: float | None,
    insurance: float | None,
    maintenance_reserve: float | None,
    condition_profile: str | None,
    capex_lane: str | None,
    notes: str | None,
):
    if not address or price in (None, ""):
        return no_update, "Subject property needs at least address and asking price.", no_update, no_update, no_update, no_update, no_update, no_update
    subject = {
        "property_id": property_id,
        "address": address,
        "town": town or "Unknown",
        "state": state or "NJ",
        "county": county or None,
        "purchase_price": price,
        "beds": beds,
        "baths": baths,
        "sqft": sqft,
        "lot_size": lot_size,
        "year_built": year_built,
        "property_type": property_type,
        "taxes": taxes,
        "monthly_hoa": monthly_hoa,
        "days_on_market": days_on_market,
        "garage_spaces": garage_spaces,
        "garage_type": garage_type or None,
        "has_detached_garage": _bool_from_form(has_detached_garage),
        "has_back_house": _bool_from_form(has_back_house),
        "adu_type": adu_type or None,
        "adu_sqft": adu_sqft,
        "has_basement": _bool_from_form(has_basement),
        "basement_finished": _bool_from_form(basement_finished),
        "has_pool": _bool_from_form(has_pool),
        "parking_spaces": parking_spaces,
        "corner_lot": _bool_from_form(corner_lot),
        "driveway_off_street": _bool_from_form(driveway_off_street),
        "estimated_monthly_rent": estimated_rent,
        "back_house_monthly_rent": back_house_rent,
        "seasonal_monthly_rent": seasonal_rent,
        "insurance": insurance,
        "monthly_maintenance_reserve_override": maintenance_reserve,
        "condition_profile": condition_profile or None,
        "capex_lane": capex_lane or _capex_from_condition(condition_profile),
        "notes": notes or None,
    }
    manual_id, output_path = register_manual_analysis(subject, list(comps or []))
    load_reports([manual_id])
    summary = {
        "property_id": manual_id,
        "address": address,
        "ask_price": _fmt_currency(price),
        "comp_count": str(len(comps or [])),
        "mode": "Public Record",
        "tear_sheet_path": str(output_path),
    }
    return (
        [manual_id],
        html.Div(
            [
                html.Div(f"Saved and analyzed {address}.", style={"fontWeight": "700"}),
                html.Div(f"Loaded as active property: {manual_id}"),
                html.Div(["Tear sheet: ", html.Code(str(output_path))], style={"fontSize": "12px"}),
            ]
        ),
        int(catalog_version or 0) + 1,
        manual_id,
        [manual_id],
        "single",
        False,
        summary,
    )


def main() -> None:
    load_reports(DEFAULT_PRESET_IDS)
    debug = os.getenv("BRIARWOOD_DASH_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug)


def _capex_from_condition(condition_profile: str | None) -> str | None:
    if condition_profile == "renovated":
        return "light"
    if condition_profile in {"updated", "maintained", "dated"}:
        return "moderate"
    if condition_profile == "needs_work":
        return "heavy"
    return None


def _bool_from_form(value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


if __name__ == "__main__":
    main()

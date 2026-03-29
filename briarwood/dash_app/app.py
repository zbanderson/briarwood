from __future__ import annotations

import os

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html

from briarwood.dash_app.compare import build_compare_summary
from briarwood.dash_app.components import (
    PAGE_STYLE,
    SIDEBAR_STYLE,
    render_compare_section,
    render_single_section,
    summary_strip,
)
from briarwood.dash_app.data import DEFAULT_PRESET_IDS, export_preset_tear_sheet, list_presets, load_reports
from briarwood.dash_app.view_models import build_property_analysis_view


app = Dash(__name__, title="Briarwood Workspace", suppress_callback_exceptions=True)
server = app.server

SECTION_TABS = [
    ("overview", "Overview"),
    ("value", "Value"),
    ("forward", "Forward"),
    ("risk", "Risk"),
    ("location", "Location"),
    ("income", "Income Support"),
    ("evidence", "Evidence"),
]


def _preset_options() -> list[dict[str, str]]:
    return [{"label": preset.label, "value": preset.preset_id} for preset in list_presets()]


def _build_layout():
    return html.Div(
        [
            dcc.Store(id="loaded-preset-ids", data=DEFAULT_PRESET_IDS),
            html.Div(
                [
                    html.Div(
                        [
                            html.H2("Briarwood Workspace", style={"margin": 0}),
                            html.Div("Interactive analysis layer for BCV, risk, and evidence.", style={"color": "#5f7286"}),
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
                                    html.Label("Properties"),
                                    dcc.Dropdown(
                                        id="preset-selector",
                                        options=_preset_options(),
                                        value=DEFAULT_PRESET_IDS,
                                        multi=True,
                                        clearable=False,
                                    ),
                                ]
                            ),
                            html.Button("Load Analysis", id="load-analysis-button", n_clicks=0),
                            html.Div(
                                [
                                    html.Label("Focus Property"),
                                    dcc.Dropdown(id="focus-property-dropdown", clearable=False),
                                ]
                            ),
                            html.Button("Export Tear Sheet", id="export-tear-sheet-button", n_clicks=0),
                            html.Div(id="export-status", style={"fontSize": "13px", "color": "#5f7286"}),
                            html.Div(
                                "The Dash app stays lightweight. Export uses the existing tear-sheet pipeline.",
                                style={"fontSize": "12px", "color": "#6b7b8d"},
                            ),
                        ],
                        style=SIDEBAR_STYLE,
                    ),
                    html.Div(
                        [
                            html.Div(id="top-summary"),
                            dcc.Tabs(
                                id="section-tabs",
                                value="overview",
                                children=[
                                    dcc.Tab(label=label, value=value) for value, label in SECTION_TABS
                                ],
                                style={"marginTop": "12px"},
                            ),
                            html.Div(id="workspace-tab-content", style={"marginTop": "16px"}),
                        ],
                        style={"flex": "1", "padding": "24px"},
                    ),
                ],
                style={"display": "flex", "minHeight": "100vh"},
            ),
        ],
        style=PAGE_STYLE,
    )


app.layout = _build_layout()


@app.callback(
    Output("loaded-preset-ids", "data"),
    Input("load-analysis-button", "n_clicks"),
    State("preset-selector", "value"),
    prevent_initial_call=False,
)
def load_selected_reports(_n_clicks: int, selected_ids: list[str] | None):
    selected_ids = [preset_id for preset_id in (selected_ids or [])][:4]
    if not selected_ids:
        return DEFAULT_PRESET_IDS
    load_reports(selected_ids)
    return selected_ids


@app.callback(
    Output("focus-property-dropdown", "options"),
    Output("focus-property-dropdown", "value"),
    Input("loaded-preset-ids", "data"),
    State("focus-property-dropdown", "value"),
)
def update_focus_property_options(loaded_ids: list[str] | None, current_value: str | None):
    loaded_ids = loaded_ids or []
    reports = load_reports(loaded_ids)
    options = [{"label": build_property_analysis_view(report).label, "value": preset_id} for preset_id, report in reports.items()]
    if current_value in reports:
        return options, current_value
    fallback = loaded_ids[0] if loaded_ids else None
    return options, fallback


@app.callback(
    Output("top-summary", "children"),
    Output("workspace-tab-content", "children"),
    Input("workspace-mode", "value"),
    Input("section-tabs", "value"),
    Input("loaded-preset-ids", "data"),
    Input("focus-property-dropdown", "value"),
)
def render_workspace(mode: str, section_value: str, loaded_ids: list[str] | None, focus_id: str | None):
    loaded_ids = loaded_ids or []
    if not loaded_ids:
        empty = html.Div("Load one or more property presets to start the workspace.")
        return empty, empty
    reports = load_reports(loaded_ids)
    focus_id = focus_id or loaded_ids[0]
    if focus_id not in reports:
        focus_id = loaded_ids[0]
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
    State("focus-property-dropdown", "value"),
    prevent_initial_call=True,
)
def export_tear_sheet(_n_clicks: int, focus_id: str | None):
    if not focus_id:
        return "Choose a focus property before exporting."
    output_path = export_preset_tear_sheet(focus_id)
    return html.Div(
        [
            "Tear sheet exported: ",
            html.Code(str(output_path)),
        ]
    )


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
    return html.Div(
        [
            "Tear sheet exported: ",
            html.Code(str(output_path)),
        ]
    )


def main() -> None:
    load_reports(DEFAULT_PRESET_IDS)
    debug = os.getenv("BRIARWOOD_DASH_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug)


if __name__ == "__main__":
    main()

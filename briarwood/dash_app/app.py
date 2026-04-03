"""
Briarwood — Investment Research Platform
Dark-theme, 4-tab layout: Tear Sheet | Scenarios | Compare | Data Quality
"""
from __future__ import annotations

import os
import traceback

from dash import ALL, Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update
try:
    import dash_bootstrap_components as dbc
except ImportError:  # pragma: no cover - lightweight fallback for local v1 usage
    class _DBCShim:
        @staticmethod
        def Button(children=None, **kwargs):
            return html.Button(children, **kwargs)

        @staticmethod
        def Spinner(children=None, **kwargs):
            return html.Span("●", style={"fontSize": "11px", "lineHeight": "1", "display": "inline-block"})

    dbc = _DBCShim()

from briarwood.dash_app.compare import build_compare_summary
from briarwood.dash_app.components import (
    render_compare_decision_mode,
    render_portfolio_dashboard,
    render_tear_sheet_body,
    render_tour_overlay,
    render_tour_trigger_button,
    render_what_if_metrics,
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
from briarwood.dash_app.theme import (
    ACCENT_BLUE, ACCENT_GREEN, BG_BASE, BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3, BG_SURFACE_4,
    BORDER, BORDER_SUBTLE, BTN_GHOST, BTN_PRIMARY, BTN_SECONDARY,
    CARD_STYLE, CARD_STYLE_ELEVATED, FONT_FAMILY, FONT_MONO,
    INPUT_STYLE, LABEL_STYLE, PAGE_STYLE, SECTION_HEADER_STYLE,
    TABLE_STYLE_CELL, TABLE_STYLE_DATA_EVEN, TABLE_STYLE_DATA_ODD,
    TABLE_STYLE_HEADER, TABLE_STYLE_TABLE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TONE_NEGATIVE_TEXT, TONE_POSITIVE_TEXT, TONE_WARNING_TEXT,
    TOPBAR_HEIGHT, TOPBAR_STYLE, PROPERTY_HEADER_STYLE,
    tone_badge_style, score_color,
)
from briarwood.dash_app.view_models import build_property_analysis_view


app = Dash(
    __name__,
    title="Briarwood",
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

# ── Constants ──────────────────────────────────────────────────────────────────

MAIN_TABS = [
    ("tear_sheet", "Tear Sheet"),
    ("scenarios", "Scenarios"),
    ("compare", "Compare"),
    ("portfolio", "Portfolio"),
    ("data_quality", "Diagnostics"),
]

# Compare view still uses section-based rendering
COMPARE_SECTIONS = [
    ("overview", "Overview"),
    ("value", "Value"),
    ("forward", "Forward"),
    ("risk", "Risk"),
    ("location", "Location"),
    ("income", "Income"),
    ("evidence", "Evidence"),
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

PROPERTY_TYPE_OPTIONS = [
    {"label": "Single Family", "value": "single_family"},
    {"label": "Duplex", "value": "duplex"},
    {"label": "Triplex", "value": "triplex"},
    {"label": "Fourplex", "value": "fourplex"},
    {"label": "Multi Family", "value": "multi_family"},
]

# ── Style helpers ──────────────────────────────────────────────────────────────

_TAB_STYLE = {
    "padding": "10px 18px",
    "fontSize": "13px",
    "fontWeight": "500",
    "fontFamily": FONT_FAMILY,
    "color": TEXT_MUTED,
    "backgroundColor": "transparent",
    "borderBottom": "2px solid transparent",
    "cursor": "pointer",
    "border": "none",
    "borderTop": "none",
    "borderLeft": "none",
    "borderRight": "none",
}

_TAB_SELECTED_STYLE = {
    **_TAB_STYLE,
    "color": TEXT_PRIMARY,
    "borderBottom": f"2px solid {ACCENT_BLUE}",
    "fontWeight": "600",
}

_TAB_BAR_STYLE = {
    "backgroundColor": BG_SURFACE,
    "borderBottom": f"1px solid {BORDER}",
    "display": "flex",
    "padding": "0 24px",
}

    # Section-level sub-tabs removed — tear sheet is now one scrollable page.

_DROPDOWN_STYLE = {
    "backgroundColor": BG_SURFACE_3,
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": "6px",
    "fontSize": "13px",
    "fontFamily": FONT_FAMILY,
}

# ── Helpers ────────────────────────────────────────────────────────────────────


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
                "Missing": str(item.missing_input_count),
            }
        )
    return rows


def _fmt_currency(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def _labeled(label: str, child) -> html.Div:
    """Wrap a form input with a label above it."""
    return html.Div(
        [
            html.Div(label, style={**LABEL_STYLE, "marginBottom": "3px"}),
            child,
        ],
    )


def _text_input(input_id: str, label: str, *, value: str | None = None) -> html.Div:
    return _labeled(
        label,
        dcc.Input(
            id=input_id, placeholder=label, type="text", value=value,
            style=INPUT_STYLE,
            debounce=False,
        ),
    )


def _number_input(input_id: str, label: str) -> html.Div:
    return _labeled(
        label,
        dcc.Input(
            id=input_id, placeholder=label, type="number",
            style=INPUT_STYLE,
        ),
    )


def _dropdown(input_id: str, options: list[dict[str, str]], label: str) -> html.Div:
    return _labeled(
        label,
        dcc.Dropdown(
            id=input_id, options=options, value="", placeholder=label, clearable=False,
            className="briarwood-dropdown",
            style={"fontSize": "13px"},
        ),
    )


def _section_label(text: str) -> html.Div:
    return html.Div(text, style={**SECTION_HEADER_STYLE, "marginTop": "12px"})


def _capex_from_condition(condition_profile: str | None) -> str | None:
    if not condition_profile:
        return None
    normalized = condition_profile.strip().lower()
    if normalized in {"renovated", "updated"}:
        return "light"
    if normalized in {"maintained"}:
        return "moderate"
    if normalized in {"dated", "needs_work"}:
        return "heavy"
    return None


def _unit_count_for_property_type(property_type: str | None) -> int:
    mapping = {
        "duplex": 2,
        "triplex": 3,
        "fourplex": 4,
        "multi_family": 4,
    }
    return mapping.get((property_type or "").strip().lower(), 0)


def _engine_property_type(property_type: str | None) -> str | None:
    mapping = {
        "single_family": "Single Family Residence",
        "duplex": "Duplex",
        "triplex": "Triplex",
        "fourplex": "Fourplex",
        "multi_family": "Multi-Family",
    }
    normalized = (property_type or "").strip().lower()
    return mapping.get(normalized)


def _normalize_property_label(property_type: str | None) -> str:
    return (_engine_property_type(property_type) or "Property").replace("-", " ")


# ── Layout builders ────────────────────────────────────────────────────────────


def _topbar() -> html.Div:
    return html.Div(
        [
            # Logo / wordmark
            html.Div(
                [
                    html.Span("Briarwood", style={"fontWeight": "700", "fontSize": "16px", "color": TEXT_PRIMARY, "letterSpacing": "-0.02em"}),
                    html.Span("Research Platform", style={"fontSize": "13px", "color": TEXT_MUTED, "marginLeft": "8px"}),
                ],
                style={"display": "flex", "alignItems": "baseline", "gap": "0", "flexShrink": "0"},
            ),
            # Separator
            html.Div(style={"width": "1px", "height": "24px", "backgroundColor": BORDER, "flexShrink": "0"}),
            # Property selector
            html.Div(
                [
                    dcc.Dropdown(
                        id="property-selector-dropdown",
                        clearable=False,
                        persistence=True,
                        placeholder="Select property…",
                        style={"minWidth": "280px", "fontSize": "13px"},
                    ),
                ],
                style={"flex": "1", "maxWidth": "360px"},
            ),
            # Add Property toggle
            html.Button("+ Add Property", id="add-property-button", n_clicks=0, style=BTN_SECONDARY),
            # Export button
            html.Div(
                [
                    html.Button("Export Tear Sheet", id="export-tear-sheet-button", n_clicks=0, style=BTN_GHOST),
                    html.Div(id="export-status", style={"fontSize": "13px", "color": TEXT_MUTED}),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "8px"},
            ),
            # Spacer
            html.Div(style={"flex": "1"}),
            # Active property status
            html.Div(id="active-property-status", style={"fontSize": "13px", "color": TEXT_MUTED, "flexShrink": "0"}),
        ],
        style=TOPBAR_STYLE,
    )


def _feedback_banner() -> html.Div:
    return html.Div(id="analysis-feedback-banner", style={"flexShrink": "0"})


def _main_tab_bar() -> dcc.Tabs:
    return dcc.Tabs(
        id="main-tabs",
        value="tear_sheet",
        children=[
            dcc.Tab(
                label=label,
                value=value,
                style=_TAB_STYLE,
                selected_style=_TAB_SELECTED_STYLE,
            )
            for value, label in MAIN_TABS
        ],
        style=_TAB_BAR_STYLE,
        colors={"border": "transparent", "primary": ACCENT_BLUE, "background": BG_SURFACE},
    )


    # _tear_sheet_section_tabs removed — section tabs are now built inline
    # inside _tear_sheet_shell() to avoid dynamic component ID issues.


_DRAWER_CARD: dict = {
    **CARD_STYLE_ELEVATED,
    "padding": "14px 16px",
    "display": "grid",
    "gap": "8px",
}

_DRAWER_WIDTH = "400px"

_BTN_ANALYZE_ENABLED: dict = {
    **BTN_PRIMARY,
    "width": "100%",
    "padding": "12px 16px",
    "fontSize": "14px",
    "fontWeight": "700",
    "letterSpacing": "0.02em",
}

_BTN_ANALYZE_DISABLED: dict = {
    **_BTN_ANALYZE_ENABLED,
    "backgroundColor": BG_SURFACE_3,
    "color": TEXT_MUTED,
    "cursor": "not-allowed",
    "opacity": "0.6",
}


def _field_label(text: str) -> html.Div:
    return html.Div(text, style={**LABEL_STYLE, "marginBottom": "0"})


def _required_dot() -> html.Span:
    return html.Span(" *", style={"color": ACCENT_GREEN, "fontWeight": "700"})


def _add_property_drawer() -> html.Div:
    """Slide-in drawer with two modes: Browse saved properties, or add new."""
    return html.Div(
        html.Div(
            [
                # ── Header ──
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("Property Manager", style={"fontWeight": "700", "fontSize": "15px", "color": TEXT_PRIMARY, "letterSpacing": "-0.01em"}),
                                html.Div("Browse saved or add a new analysis", style={"fontSize": "13px", "color": TEXT_MUTED}),
                            ]
                        ),
                        html.Button("✕", id="add-property-close-button", n_clicks=0, style={**BTN_GHOST, "fontSize": "16px", "padding": "4px 8px"}),
                    ],
                    style={"display": "flex", "justifyContent": "space-between", "alignItems": "start", "marginBottom": "16px"},
                ),
                # ── Saved properties card ──
                html.Div(
                    [
                        html.Div("Saved Properties", style=SECTION_HEADER_STYLE),
                        dash_table.DataTable(
                            id="saved-properties-table",
                            columns=[
                                {"name": "Address", "id": "Address"},
                                {"name": "Ask", "id": "Ask"},
                                {"name": "BCV", "id": "BCV"},
                                {"name": "Pricing View", "id": "Pricing View"},
                                {"name": "Confidence", "id": "Confidence"},
                                {"name": "Missing", "id": "Missing"},
                            ],
                            data=[],
                            row_selectable="multi",
                            selected_rows=[],
                            page_size=5,
                            style_table={**TABLE_STYLE_TABLE, "maxWidth": "100%"},
                            style_header=TABLE_STYLE_HEADER,
                            style_cell={**TABLE_STYLE_CELL, "minWidth": "55px", "maxWidth": "110px", "whiteSpace": "normal", "fontSize": "13px", "padding": "6px 8px"},
                            style_data_conditional=[
                                {"if": {"row_index": "odd"}, **TABLE_STYLE_DATA_ODD},
                                {"if": {"row_index": "even"}, **TABLE_STYLE_DATA_EVEN},
                            ],
                        ),
                        html.Button("Compare Selected", id="compare-selected-button", n_clicks=0, style={**BTN_SECONDARY, "marginTop": "4px"}),
                    ],
                    style=_DRAWER_CARD,
                ),
                # ── Divider ──
                html.Div(
                    html.Div("New Property Analysis", style={**SECTION_HEADER_STYLE, "margin": "0", "fontSize": "13px", "letterSpacing": "0.10em"}),
                    style={"textAlign": "center", "padding": "10px 0 4px"},
                ),
                # ── Form ──
                html.Div(id="add-property-form", style={"display": "grid", "gap": "10px"}, children=_add_property_form_body()),
            ],
            style={
                "backgroundColor": BG_BASE,
                "borderLeft": f"1px solid {BORDER}",
                "padding": "20px",
                "width": _DRAWER_WIDTH,
                "overflowY": "auto",
                "height": f"calc(100vh - {TOPBAR_HEIGHT})",
                "position": "fixed",
                "top": TOPBAR_HEIGHT,
                "right": "0",
                "zIndex": "150",
                "boxShadow": "-12px 0 40px rgba(0,0,0,0.5)",
            },
        ),
        id="add-property-drawer",
        style={"display": "none"},
    )


def _add_property_form_body() -> list:
    """Form fields grouped into themed cards."""
    return [
        # ── Required: Subject Property ──
        html.Div(
            [
                html.Div(
                    [html.Span("Subject Property", style={**SECTION_HEADER_STYLE, "marginBottom": "0", "display": "inline"}), _required_dot()],
                ),
                _text_input("manual-address", "Street address"),
                html.Div(
                    [_number_input("manual-price", "Asking price ($)")],
                ),
                html.Div(
                    [
                        _text_input("manual-town", "Town", value="Belmar"),
                        _text_input("manual-state", "State", value="NJ"),
                        _text_input("manual-county", "County", value="Monmouth"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "1fr 70px 1fr", "gap": "6px"},
                ),
                html.Div(
                    [_number_input("manual-beds", "Beds"), _number_input("manual-baths", "Baths"), _number_input("manual-sqft", "Sqft")],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                _text_input("manual-property-id", "Property ID (optional)"),
                # Validation hint
                html.Div(
                    id="form-validation-hint",
                    style={"fontSize": "13px", "color": TEXT_MUTED, "marginTop": "2px"},
                ),
            ],
            style=_DRAWER_CARD,
        ),
        # ── Property Details (optional) ──
        html.Div(
            [
                html.Div("Property Details", style=SECTION_HEADER_STYLE),
                html.Div(
                    [_number_input("manual-lot-size", "Lot (acres)"), _number_input("manual-year-built", "Year built"), _number_input("manual-dom", "Days on market")],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                html.Div(
                    [_number_input("manual-taxes", "Annual Taxes ($)"), _number_input("manual-hoa", "Monthly HOA ($)")],
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"},
                ),
                _dropdown("manual-property-type", PROPERTY_TYPE_OPTIONS, "Property Type"),
                html.Div(
                    [
                        _dropdown("manual-condition-profile", CONDITION_OPTIONS, "Condition"),
                        _dropdown("manual-capex-lane", CAPEX_OPTIONS, "CapEx Lane"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"},
                ),
            ],
            style=_DRAWER_CARD,
        ),
        # ── Physical Features (optional, collapsed feel) ──
        html.Div(
            [
                html.Div("Physical Features", style=SECTION_HEADER_STYLE),
                html.Div(
                    [
                        _number_input("manual-garage-spaces", "Garage spaces"),
                        _dropdown("manual-garage-type", GARAGE_TYPE_OPTIONS, "Garage type"),
                        _dropdown("manual-has-detached-garage", YES_NO_OPTIONS, "Detached"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                html.Div(
                    [
                        _dropdown("manual-has-back-house", YES_NO_OPTIONS, "Back house / ADU"),
                        _dropdown("manual-adu-type", ADU_TYPE_OPTIONS, "ADU type"),
                        _number_input("manual-adu-sqft", "ADU sqft"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                html.Div(
                    [
                        _dropdown("manual-has-basement", YES_NO_OPTIONS, "Basement"),
                        _dropdown("manual-basement-finished", YES_NO_OPTIONS, "Finished"),
                        _dropdown("manual-has-pool", YES_NO_OPTIONS, "Pool"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                html.Div(
                    [
                        _number_input("manual-parking-spaces", "Parking spaces"),
                        _dropdown("manual-corner-lot", YES_NO_OPTIONS, "Corner lot"),
                        _dropdown("manual-driveway-off-street", YES_NO_OPTIONS, "Off-street"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
            ],
            style=_DRAWER_CARD,
        ),
        # ── Income & Carry (optional) ──
        html.Div(
            [
                html.Div("Income & Carry", style=SECTION_HEADER_STYLE),
                html.Div(
                    [
                        _number_input("manual-estimated-rent", "Market rent ($/mo)"),
                        _number_input("manual-back-house-rent", "Back house rent"),
                        _number_input("manual-seasonal-rent", "Seasonal rent"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                html.Div(
                    id="manual-unit-rents-container",
                    children=[
                        html.Div("Unit Rent Schedule", style=SECTION_HEADER_STYLE),
                        html.Div(
                            [
                                _number_input("manual-rent-1", "Unit 1 rent ($/mo)"),
                                _number_input("manual-rent-2", "Unit 2 rent ($/mo)"),
                                _number_input("manual-rent-3", "Unit 3 rent ($/mo)"),
                                _number_input("manual-rent-4", "Unit 4 rent ($/mo)"),
                            ],
                            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"},
                        ),
                        html.Div(
                            id="manual-unit-rent-note",
                            style={"fontSize": "13px", "color": TEXT_MUTED},
                        ),
                    ],
                    style={"display": "none"},
                ),
                html.Div(
                    [_number_input("manual-insurance", "Insurance ($/yr)"), _number_input("manual-maintenance-reserve", "Maint reserve ($/mo)")],
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"},
                ),
            ],
            style=_DRAWER_CARD,
        ),
        # ── Notes ──
        dcc.Textarea(
            id="manual-notes", placeholder="Notes or listing description (optional)",
            style={**INPUT_STYLE, "height": "60px", "resize": "vertical"},
        ),
        # ── Manual Comps (collapsible card) ──
        html.Div(
            [
                html.Div("Manual Comps (optional)", style=SECTION_HEADER_STYLE),
                _text_input("manual-comp-address", "Comp address"),
                html.Div(
                    [_number_input("manual-comp-sale-price", "Sale price"), _text_input("manual-comp-sale-date", "Date YYYY-MM-DD")],
                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"},
                ),
                html.Div(
                    [_number_input("manual-comp-beds", "Beds"), _number_input("manual-comp-baths", "Baths"), _number_input("manual-comp-sqft", "Sqft")],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                html.Div(
                    [_number_input("manual-comp-lot-size", "Lot (acres)"), _number_input("manual-comp-year-built", "Year built"), _number_input("manual-comp-distance", "Distance mi")],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px"},
                ),
                html.Div(
                    [
                        _text_input("manual-comp-property-type", "Type", value="Single Family Residence"),
                        _dropdown("manual-comp-condition-profile", CONDITION_OPTIONS, "Comp condition"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "1.3fr 1fr", "gap": "6px"},
                ),
                dcc.Textarea(
                    id="manual-comp-notes", placeholder="Comp notes",
                    style={**INPUT_STYLE, "height": "50px", "resize": "vertical"},
                ),
                html.Button("Add Comp", id="manual-add-comp-button", n_clicks=0, style={**BTN_SECONDARY, "width": "100%"}),
                html.Div(id="manual-comps-preview", style={"fontSize": "13px", "color": TEXT_MUTED}),
            ],
            style=_DRAWER_CARD,
        ),
        # ── Submit area ──
        html.Div(
            [
                dbc.Button(
                    "Start Analysis",
                    id="manual-run-analysis-button",
                    n_clicks=0,
                    disabled=True,
                    style=_BTN_ANALYZE_DISABLED,
                ),
                dcc.Loading(
                    id="analysis-loading",
                    type="circle",
                    color=ACCENT_GREEN,
                    children=html.Div(id="analysis-loading-target"),
                    style={"marginTop": "4px"},
                ),
                html.Div(id="manual-entry-status", style={"fontSize": "13px", "marginTop": "6px"}),
            ],
            style={
                "position": "sticky",
                "bottom": "0",
                "backgroundColor": BG_BASE,
                "padding": "12px 0 4px",
                "borderTop": f"1px solid {BORDER}",
                "zIndex": "10",
            },
        ),
    ]


def _compare_controls() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Compare Properties", style=SECTION_HEADER_STYLE),
                    dcc.Dropdown(
                        id="compare-selector-dropdown",
                        multi=True,
                        persistence=True,
                        placeholder="Select 2–4 properties to compare…",
                        style={"fontSize": "13px"},
                    ),
                    html.Div(
                        [
                            html.Button("Go", id="compare-go-button", n_clicks=0, style=BTN_PRIMARY),
                        ],
                        style={"display": "flex", "gap": "8px", "marginTop": "8px"},
                    ),
                    html.Div(id="compare-selection-status", style={"fontSize": "13px", "color": TEXT_MUTED, "marginTop": "6px"}),
                ],
                style={"flex": "1"},
            ),
            html.Div(
                [
                    html.Div("Mode", style=SECTION_HEADER_STYLE),
                    dcc.RadioItems(
                        id="compare-mode-toggle",
                        options=[
                            {"label": "Heatmap", "value": "heatmap"},
                            {"label": "Radar", "value": "radar"},
                            {"label": "Table", "value": "table"},
                            {"label": "Detail", "value": "detail"},
                        ],
                        value="heatmap",
                        inline=True,
                        labelStyle={"marginRight": "12px", "fontSize": "13px", "color": TEXT_SECONDARY},
                        inputStyle={"marginRight": "4px"},
                    ),
                ],
            ),
            html.Div(
                [
                    html.Div("Detail Section", style=SECTION_HEADER_STYLE),
                    dcc.Dropdown(
                        id="compare-section-dropdown",
                        options=[{"label": label, "value": value} for value, label in COMPARE_SECTIONS],
                        value="overview",
                        clearable=False,
                        style={"fontSize": "13px", "minWidth": "160px"},
                    ),
                ],
            ),
        ],
        style={"display": "flex", "gap": "16px", "alignItems": "end", "padding": "16px 24px", "borderBottom": f"1px solid {BORDER}", "backgroundColor": BG_SURFACE},
    )


def _build_layout():
    return html.Div(
        [
            # Stores
            dcc.Store(id="loaded-preset-ids", data=DEFAULT_PRESET_IDS),
            dcc.Store(id="manual-comps-store", data=[]),
            dcc.Store(id="property-catalog-version", data=0),
            dcc.Store(id="add-property-open", data=False),
            dcc.Store(id="last-analysis-summary", data=None),
            dcc.Store(id="compare-confirmed-ids", data=[]),
            dcc.Store(id="compare-go-token", data=0),
            # Tour state (persists in browser localStorage)
            dcc.Store(id="tour-state", storage_type="local", data={"completed": False, "step": 0}),
            # PDF download target
            dcc.Download(id="pdf-download"),

            # Top bar
            _topbar(),

            # Sticky property header (populated by callback)
            html.Div(id="property-header-bar", style={"display": "none"}),

            # Feedback banner (only shown after analysis)
            _feedback_banner(),

            # Main tab bar
            _main_tab_bar(),

            # Main content area
            html.Div(
                id="main-tab-content",
                style={"flex": "1", "minHeight": "0"},
            ),

            # Floating add-property drawer
            _add_property_drawer(),

            # Tour: step store drives the overlay content
            dcc.Store(id="tour-step", data=-1),
            html.Div(id="tour-overlay-container"),

            # Tour trigger button (always visible)
            render_tour_trigger_button(),
        ],
        style={**PAGE_STYLE, "display": "flex", "flexDirection": "column"},
    )


app.layout = _build_layout()


# ── Callbacks ──────────────────────────────────────────────────────────────────


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
    loaded_ids = [pid for pid in (loaded_ids or []) if pid in allowed]
    property_value = current_property_id if current_property_id in allowed else (loaded_ids[0] if loaded_ids else None)
    compare_values = [pid for pid in (current_compare_ids or []) if pid in allowed][:4]
    return options, property_value, options, compare_values, _saved_property_rows()


@app.callback(
    Output("active-property-status", "children"),
    Output("property-header-bar", "children"),
    Output("property-header-bar", "style"),
    Input("property-selector-dropdown", "value"),
    Input("loaded-preset-ids", "data"),
)
def render_active_property_status(property_id: str | None, loaded_ids: list[str] | None):
    hidden = {"display": "none"}
    if not property_id and loaded_ids:
        property_id = loaded_ids[0]
    if not property_id:
        return "No property selected", None, hidden
    try:
        report = load_report_for_preset(property_id)
    except KeyError:
        return "Unavailable", None, hidden
    view = build_property_analysis_view(report)

    # Top bar status (compact)
    status = f"{view.address}  ·  {_fmt_currency(view.ask_price)}  ·  {view.overall_confidence:.0%}"

    # Sticky property header
    pi = report.property_input
    basics_parts = []
    if pi:
        if pi.beds:
            basics_parts.append(f"{pi.beds}bd")
        if pi.baths:
            basics_parts.append(f"{pi.baths}ba")
        if pi.sqft:
            basics_parts.append(f"{pi.sqft:,}sf")
        if pi.town:
            basics_parts.append(f"{pi.town}")
    basics_text = " · ".join(basics_parts)

    gap_text = ""
    if view.mispricing_pct is not None:
        sign = "+" if view.mispricing_pct >= 0 else ""
        gap_text = f"{sign}{view.mispricing_pct * 100:.1f}%"

    score_text = ""
    sc = TEXT_MUTED
    if view.final_score is not None:
        score_text = f"{view.final_score:.1f}/5"
        sc = score_color(view.final_score)

    header_children = html.Div(
        [
            # Left: address + basics
            html.Div(
                [
                    html.Span(view.address, style={"fontSize": "13px", "fontWeight": "600", "color": TEXT_PRIMARY, "marginRight": "12px"}),
                    html.Span(basics_text, style={"fontSize": "13px", "color": TEXT_MUTED}),
                ],
                style={"display": "flex", "alignItems": "baseline", "gap": "0"},
            ),
            # Right: key metrics inline
            html.Div(
                [
                    _header_metric("Ask", _fmt_currency(view.ask_price)),
                    _header_metric("BCV", _fmt_currency(view.bcv)),
                    _header_metric("Gap", gap_text or "—"),
                    _header_metric("Base", _fmt_currency(view.base_case)),
                    _header_metric("Score", score_text or "—", color=sc),
                    html.Span(
                        view.recommendation_tier,
                        style=tone_badge_style("positive" if (view.final_score or 0) >= 3.75 else "warning" if (view.final_score or 0) >= 3.0 else "negative"),
                    ) if view.recommendation_tier else None,
                ],
                style={"display": "flex", "gap": "12px", "alignItems": "center"},
            ),
        ],
        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "width": "100%"},
    )

    return status, header_children, PROPERTY_HEADER_STYLE


def _header_metric(label: str, value: str, *, color: str = TEXT_PRIMARY) -> html.Span:
    return html.Span(
        [
            html.Span(label, style={"fontSize": "9px", "color": TEXT_MUTED, "textTransform": "uppercase", "marginRight": "3px"}),
            html.Span(value, style={"fontSize": "13px", "fontWeight": "600", "color": color}),
        ],
        style={"display": "inline-flex", "alignItems": "baseline"},
    )


@app.callback(
    Output("analysis-feedback-banner", "children"),
    Input("last-analysis-summary", "data"),
)
def render_analysis_feedback(summary: dict[str, str] | None):
    if not summary:
        return None
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Analysis saved", style={"fontWeight": "700", "color": TONE_POSITIVE_TEXT}),
                    html.Span(" — ", style={"color": TEXT_MUTED}),
                    html.Span(
                        f"{summary.get('address', 'Property')}  ·  Ask: {summary.get('ask_price', '—')}  ·  "
                        f"Comps: {summary.get('comp_count', '0')}  ·  Evidence: {summary.get('mode', '—')}",
                        style={"color": TEXT_SECONDARY},
                    ),
                ],
                style={"fontSize": "13px"},
            ),
        ],
        style={
            "backgroundColor": "#1a3a1f",
            "borderBottom": "1px solid #2d6a35",
            "padding": "10px 24px",
            "flexShrink": "0",
        },
    )


@app.callback(
    Output("loaded-preset-ids", "data", allow_duplicate=True),
    Input("property-selector-dropdown", "value"),
    prevent_initial_call=True,
)
def select_property(property_id: str | None):
    if not property_id:
        return no_update
    load_reports([property_id])
    return [property_id]


@app.callback(
    Output("compare-confirmed-ids", "data"),
    Output("compare-go-token", "data"),
    Output("compare-selection-status", "children"),
    Input("compare-go-button", "n_clicks"),
    State("compare-selector-dropdown", "value"),
    State("compare-go-token", "data"),
    prevent_initial_call=True,
)
def trigger_compare_go(_n_clicks: int, property_ids: list[str] | None, token: int | None):
    property_ids = [pid for pid in (property_ids or [])][:4]
    if len(property_ids) < 2:
        return no_update, no_update, html.Span("Select at least 2 properties, then click Go.", style={"color": TONE_WARNING_TEXT})
    load_reports(property_ids)
    return property_ids, int(token or 0) + 1, html.Span(f"Comparing {len(property_ids)} selected properties.", style={"color": TONE_POSITIVE_TEXT})


@app.callback(
    Output("loaded-preset-ids", "data", allow_duplicate=True),
    Output("compare-selector-dropdown", "value", allow_duplicate=True),
    Output("compare-confirmed-ids", "data", allow_duplicate=True),
    Output("compare-go-token", "data", allow_duplicate=True),
    Output("compare-selection-status", "children", allow_duplicate=True),
    Output("property-selector-dropdown", "value", allow_duplicate=True),
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
        return no_update, no_update, no_update, no_update, no_update, no_update
    property_ids = [rows[i]["property_id"] for i in selected_rows if 0 <= i < len(rows)][:4]
    if not property_ids:
        return no_update, no_update, no_update, no_update, no_update, no_update
    load_reports(property_ids)
    return (
        property_ids,
        property_ids,
        property_ids,
        1,
        html.Span(f"Comparing {len(property_ids)} properties selected from saved analyses.", style={"color": TONE_POSITIVE_TEXT}),
        no_update,
    )


# ── Main tab content ───────────────────────────────────────────────────────────


@app.callback(
    Output("main-tab-content", "children"),
    Input("main-tabs", "value"),
    Input("loaded-preset-ids", "data"),
    Input("property-selector-dropdown", "value"),
)
def render_main_tab(tab: str, loaded_ids: list[str] | None, focus_id: str | None):
    if tab == "tear_sheet":
        report = _focused_report(loaded_ids, focus_id)
        if report is None:
            return _empty_state("Add or select a property to begin.")
        view = build_property_analysis_view(report)
        return _centered_main_panel(render_tear_sheet_body(view, report), padding="0 20px 24px", max_width="1140px")

    if tab == "scenarios":
        report = _focused_report(loaded_ids, focus_id)
        if report is None:
            return _empty_state("Select a property to view investment scenarios.")
        from briarwood.dash_app.scenarios import render_scenarios_section
        return _centered_main_panel(render_scenarios_section(report))

    if tab == "compare":
        return html.Div(
            [
                _compare_controls(),
                html.Div(
                    id="compare-content",
                    style={"width": "100%", "maxWidth": "1180px", "padding": "16px 20px 24px", "margin": "0 auto"},
                ),
            ]
        )

    if tab == "portfolio":
        loaded_ids = loaded_ids or []
        if not loaded_ids:
            return _empty_state("Load properties to view portfolio dashboard.")
        reports = load_reports(loaded_ids)
        views = [build_property_analysis_view(r) for r in reports.values()]
        return _centered_main_panel(render_portfolio_dashboard(views), max_width="1200px")

    if tab == "data_quality":
        report = _focused_report(loaded_ids, focus_id)
        if report is None:
            return _empty_state("Select a property to view diagnostics.")
        from briarwood.dash_app.data_quality import render_data_quality_section
        return _centered_main_panel(render_data_quality_section(report))

    return _empty_state("Select a tab.")


def _empty_state(message: str) -> html.Div:
    return html.Div(
        html.P(message, style={"color": TEXT_MUTED, "fontSize": "13px"}),
        style={"padding": "40px 20px"},
    )


def _centered_main_panel(content, *, padding: str = "16px 20px 24px", max_width: str = "1180px") -> html.Div:
    return html.Div(
        html.Div(content, style={"width": "100%", "maxWidth": max_width}),
        style={"width": "100%", "display": "flex", "justifyContent": "center", "padding": padding},
    )


def _focused_report(loaded_ids: list[str] | None, focus_id: str | None) -> AnalysisReport | None:
    property_ids = loaded_ids or []
    if not property_ids:
        return None
    reports = load_reports(property_ids)
    if not reports:
        return None
    resolved_focus_id = focus_id if focus_id in reports else next(iter(reports.keys()))
    return reports[resolved_focus_id]


@app.callback(
    Output("compare-content", "children"),
    Input("compare-go-token", "data"),
    Input("compare-confirmed-ids", "data"),
    Input("compare-mode-toggle", "value"),
    Input("compare-section-dropdown", "value"),
)
def render_compare(_go_token: int | None, property_ids: list[str] | None, mode: str | None, section: str | None):
    property_ids = [pid for pid in (property_ids or [])][:4]
    if len(property_ids) < 2:
        return html.Div(
            "Select 2 or more properties, click OK to confirm them, then click Go.",
            style={"color": TEXT_MUTED, "fontSize": "14px"},
        )
    reports_dict = load_reports(property_ids)
    report_list = [reports_dict[pid] for pid in property_ids if pid in reports_dict]
    if len(report_list) < 2:
        return html.Div("Some selected properties are unavailable.", style={"color": TEXT_MUTED})
    views = [build_property_analysis_view(r) for r in report_list]
    summary = build_compare_summary(views)
    return render_compare_decision_mode(mode or "heatmap", views, report_list, summary, section or "overview")


@app.callback(
    Output("compare-mode-toggle", "value", allow_duplicate=True),
    Input("compare-section-dropdown", "value"),
    State("compare-mode-toggle", "value"),
    prevent_initial_call=True,
)
def focus_detail_mode_for_section(_section: str | None, current_mode: str | None):
    if current_mode == "detail":
        return no_update
    return "detail"


# ── Form validation callback ───────────────────────────────────────────────────


@app.callback(
    Output("manual-run-analysis-button", "disabled"),
    Output("manual-run-analysis-button", "style"),
    Output("form-validation-hint", "children"),
    Input("manual-address", "value"),
    Input("manual-price", "value"),
    Input("manual-beds", "value"),
    Input("manual-baths", "value"),
    Input("manual-sqft", "value"),
)
def validate_form(
    address: str | None,
    price: float | None,
    beds: float | None,
    baths: float | None,
    sqft: float | None,
):
    missing: list[str] = []
    if not address or not str(address).strip():
        missing.append("address")
    if price in (None, "", 0):
        missing.append("asking price")

    # Beds/baths/sqft are strongly recommended but not blocking
    warnings: list[str] = []
    if beds in (None, ""):
        warnings.append("beds")
    if baths in (None, ""):
        warnings.append("baths")
    if sqft in (None, "", 0):
        warnings.append("sqft")

    if missing:
        hint = html.Span(
            f"Required: {', '.join(missing)}",
            style={"color": TONE_NEGATIVE_TEXT},
        )
        return True, _BTN_ANALYZE_DISABLED, hint

    if warnings:
        hint = html.Span(
            [
                html.Span("Ready to analyze", style={"color": TONE_POSITIVE_TEXT}),
                html.Span(f"  ·  recommended: {', '.join(warnings)}", style={"color": TONE_WARNING_TEXT}),
            ]
        )
        return False, _BTN_ANALYZE_ENABLED, hint

    return False, _BTN_ANALYZE_ENABLED, html.Span("Ready to analyze", style={"color": TONE_POSITIVE_TEXT})


@app.callback(
    Output("manual-unit-rents-container", "style"),
    Output("manual-unit-rent-note", "children"),
    Input("manual-property-type", "value"),
)
def toggle_rent_inputs(property_type: str | None):
    unit_count = _unit_count_for_property_type(property_type)
    if unit_count <= 1:
        return {"display": "none"}, ""
    property_label = _normalize_property_label(property_type)
    return (
        {"display": "grid", "gap": "6px"},
        html.Span(
            f"{property_label} selected — unit rents will override the single market-rent input when provided.",
            style={"color": TONE_POSITIVE_TEXT},
        ),
    )


# ── Drawer callbacks ───────────────────────────────────────────────────────────


@app.callback(
    Output("add-property-open", "data"),
    Input("add-property-button", "n_clicks"),
    Input("add-property-close-button", "n_clicks"),
    State("add-property-open", "data"),
    prevent_initial_call=True,
)
def toggle_add_property_drawer(_open_clicks: int, _close_clicks: int, is_open: bool | None):
    triggered = ctx.triggered_id
    if triggered == "add-property-close-button":
        return False
    return not bool(is_open)


@app.callback(
    Output("add-property-drawer", "style"),
    Input("add-property-open", "data"),
)
def set_drawer_visibility(is_open: bool | None):
    if is_open:
        return {"display": "block"}
    return {"display": "none"}


# ── Export callbacks ───────────────────────────────────────────────────────────


@app.callback(
    Output("export-status", "children"),
    Input("export-tear-sheet-button", "n_clicks"),
    State("property-selector-dropdown", "value"),
    prevent_initial_call=True,
)
def export_tear_sheet(_n_clicks: int, property_id: str | None):
    if not property_id:
        return "Choose a property first."
    output_path = export_preset_tear_sheet(property_id)
    return html.Span(str(output_path), style={**{"fontFamily": FONT_MONO, "fontSize": "13px"}})


@app.callback(
    Output("export-status", "children", allow_duplicate=True),
    Input({"type": "lane-export-button", "property_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def export_lane_tear_sheet(_clicks: list[int]):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return "Choose a property first."
    property_id = triggered.get("property_id")
    if not isinstance(property_id, str):
        return "Choose a property first."
    output_path = export_preset_tear_sheet(property_id)
    return html.Span(str(output_path), style={"fontFamily": FONT_MONO, "fontSize": "13px"})


# ── Manual comp callbacks ──────────────────────────────────────────────────────


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
        return no_update, "Comp needs at least address, sale price, and date."
    if len(comps) >= 10:
        return no_update, "Comp limit reached (10 comps max)."
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
        return html.Div("No manual comps added yet.", style={"color": TEXT_MUTED, "fontSize": "13px"})
    cards = []
    for index, comp in enumerate(comps):
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(f"{index + 1}. {comp.get('address')}", style={"fontWeight": "600", "fontSize": "13px", "color": TEXT_PRIMARY}),
                            html.Div(f"${float(comp.get('sale_price', 0)):,.0f} | {comp.get('sale_date')}", style={"fontSize": "13px", "color": TEXT_MUTED}),
                        ]
                    ),
                    html.Div(
                        [
                            html.Button("Edit", id={"type": "manual-edit-comp-button", "index": index}, n_clicks=0, style={**BTN_GHOST, "fontSize": "13px", "padding": "3px 8px"}),
                            html.Button("Remove", id={"type": "manual-remove-comp-button", "index": index}, n_clicks=0, style={**BTN_GHOST, "fontSize": "13px", "padding": "3px 8px", "color": TONE_NEGATIVE_TEXT}),
                        ],
                        style={"display": "flex", "gap": "4px"},
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "border": f"1px solid {BORDER}",
                    "borderRadius": "6px",
                    "padding": "8px 10px",
                    "backgroundColor": BG_SURFACE_3,
                },
            )
        )
    return html.Div(cards, style={"display": "grid", "gap": "6px"})


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


# ── Manual analysis callback ───────────────────────────────────────────────────


@app.callback(
    Output("loaded-preset-ids", "data", allow_duplicate=True),
    Output("manual-entry-status", "children", allow_duplicate=True),
    Output("property-catalog-version", "data", allow_duplicate=True),
    Output("property-selector-dropdown", "options", allow_duplicate=True),
    Output("property-selector-dropdown", "value", allow_duplicate=True),
    Output("compare-selector-dropdown", "options", allow_duplicate=True),
    Output("compare-selector-dropdown", "value", allow_duplicate=True),
    Output("add-property-open", "data", allow_duplicate=True),
    Output("last-analysis-summary", "data", allow_duplicate=True),
    Output("main-tabs", "value"),
    Output("manual-run-analysis-button", "children", allow_duplicate=True),
    Output("manual-run-analysis-button", "disabled", allow_duplicate=True),
    Output("analysis-loading-target", "children"),
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
    State("manual-rent-1", "value"),
    State("manual-rent-2", "value"),
    State("manual-rent-3", "value"),
    State("manual-rent-4", "value"),
    State("manual-back-house-rent", "value"),
    State("manual-seasonal-rent", "value"),
    State("manual-insurance", "value"),
    State("manual-maintenance-reserve", "value"),
    State("manual-condition-profile", "value"),
    State("manual-capex-lane", "value"),
    State("manual-notes", "value"),
    prevent_initial_call=True,
    running=[
        (
            Output("manual-run-analysis-button", "children"),
            html.Span(
                [
                    dbc.Spinner(size="sm", color="light"),
                    html.Span("Analyzing...", style={"marginLeft": "8px"}),
                ],
                style={"display": "inline-flex", "alignItems": "center"},
            ),
            "Start Analysis",
        ),
        (Output("manual-run-analysis-button", "disabled"), True, False),
    ],
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
    rent_1: float | None,
    rent_2: float | None,
    rent_3: float | None,
    rent_4: float | None,
    back_house_rent: float | None,
    seasonal_rent: float | None,
    insurance: float | None,
    maintenance_reserve: float | None,
    condition_profile: str | None,
    capex_lane: str | None,
    notes: str | None,
):
    options = _property_options()
    unit_count = _unit_count_for_property_type(property_type)
    unit_rents = [rent for rent in (rent_1, rent_2, rent_3, rent_4) if rent not in (None, "", 0)]
    if not address or price in (None, ""):
        error_msg = html.Div(
            [
                html.Div("Analysis not started", style={"color": TONE_NEGATIVE_TEXT, "fontWeight": "600"}),
                html.Div("Address and asking price are required.", style={"color": TEXT_SECONDARY, "marginTop": "4px"}),
            ]
        )
        return no_update, error_msg, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, "Start Analysis", False, ""

    def _bool(v: str | None) -> bool | None:
        if v == "true":
            return True
        if v == "false":
            return False
        return None

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
        "property_type": _engine_property_type(property_type),
        "taxes": taxes,
        "monthly_hoa": monthly_hoa,
        "days_on_market": days_on_market,
        "garage_spaces": garage_spaces,
        "garage_type": garage_type or None,
        "has_detached_garage": _bool(has_detached_garage),
        "has_back_house": _bool(has_back_house),
        "adu_type": adu_type or None,
        "adu_sqft": adu_sqft,
        "has_basement": _bool(has_basement),
        "basement_finished": _bool(basement_finished),
        "has_pool": _bool(has_pool),
        "parking_spaces": parking_spaces,
        "corner_lot": _bool(corner_lot),
        "driveway_off_street": _bool(driveway_off_street),
        "estimated_monthly_rent": estimated_rent,
        "unit_rents": unit_rents if unit_count > 1 else [],
        "back_house_monthly_rent": back_house_rent,
        "seasonal_monthly_rent": seasonal_rent,
        "insurance": insurance,
        "monthly_maintenance_reserve_override": maintenance_reserve,
        "condition_profile": condition_profile or None,
        "capex_lane": capex_lane or None,
        "notes": notes or None,
    }

    try:
        new_id, tear_sheet_path = register_manual_analysis(subject, comps or [])
        options = _property_options()
        inline_notes: list[str] = []
        if unit_count > 1 and not unit_rents:
            inline_notes.append("Multi-unit selected without unit rents; income support fell back to the single rent field or market prior.")
        if unit_count > 1 and unit_rents:
            inline_notes.append(f"Manual rents for {len(unit_rents)} unit{'s' if len(unit_rents) != 1 else ''} were used in income support.")
        summary = {
            "property_id": new_id,
            "address": address,
            "ask_price": f"${price:,.0f}",
            "comp_count": str(len(comps or [])),
            "mode": "manual",
            "tear_sheet_path": str(tear_sheet_path),
            "unit_rents": len(unit_rents),
        }
        new_version = (catalog_version or 0) + 1
        success_msg = html.Div(
            [
                html.Div("Analysis complete", style={"color": TONE_POSITIVE_TEXT, "fontWeight": "600"}),
                html.Div(f"{address} saved and loaded as the active property.", style={"color": TEXT_SECONDARY, "marginTop": "4px"}),
                html.Div(f"Tear sheet: {tear_sheet_path}", style={"color": TEXT_MUTED, "fontSize": "13px", "marginTop": "4px"}),
                html.Ul(
                    [html.Li(note, style={"color": TONE_WARNING_TEXT if "fell back" in note else TEXT_SECONDARY, "fontSize": "13px"}) for note in inline_notes],
                    style={"margin": "6px 0 0", "paddingLeft": "18px"},
                ) if inline_notes else None,
            ]
        )
        return [new_id], success_msg, new_version, options, new_id, options, [new_id], False, summary, "tear_sheet", "Start Analysis", False, ""
    except Exception as exc:
        tb = traceback.format_exc(limit=6)
        error_msg = html.Div(
            [
                html.Div("Analysis failed", style={"color": TONE_NEGATIVE_TEXT, "fontWeight": "600"}),
                html.Div(str(exc), style={"color": TEXT_SECONDARY, "marginTop": "4px"}),
                html.Details(
                    [
                        html.Summary("Show traceback", style={"cursor": "pointer", "color": TEXT_MUTED, "marginTop": "6px"}),
                        html.Pre(tb, style={"whiteSpace": "pre-wrap", "fontSize": "13px", "color": TEXT_MUTED, "marginTop": "6px"}),
                    ]
                ),
            ]
        )
        return no_update, error_msg, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, "Start Analysis", False, ""


# ── Tour callbacks ────────────────────────────────────────────────────────────

# Callback 1: ANY button press updates the step store.
# tour-trigger-btn is always in the DOM.
# tour-next-btn / tour-prev-btn are inside the overlay (dynamic), so
# suppress_callback_exceptions=True handles them.


@app.callback(
    Output("tour-step", "data"),
    Output("tour-state", "data"),
    Input("tour-trigger-btn", "n_clicks"),
    Input("tour-next-btn", "n_clicks"),
    Input("tour-prev-btn", "n_clicks"),
    State("tour-step", "data"),
    State("tour-state", "data"),
    prevent_initial_call=True,
)
def tour_navigate(_trig: int, _nxt: int, _prv: int, step: int, tour_state: dict | None):
    triggered = ctx.triggered_id
    tour_state = tour_state or {"completed": False, "step": 0}
    step = step if isinstance(step, int) else -1

    if triggered == "tour-trigger-btn":
        return 0, {"completed": False, "step": 0}

    if triggered == "tour-next-btn":
        if step >= 5:
            return -1, {"completed": True, "step": 0}
        return step + 1, {"completed": False, "step": step + 1}

    if triggered == "tour-prev-btn":
        if step <= 0:
            return -1, {"completed": True, "step": 0}
        return step - 1, {"completed": False, "step": step - 1}

    return no_update, no_update


# Callback 2: Render the overlay whenever tour-step changes.
# step == -1 means hidden.  step >= 0 means show that step.


@app.callback(
    Output("tour-overlay-container", "children"),
    Input("tour-step", "data"),
)
def tour_render(step: int):
    if not isinstance(step, int) or step < 0:
        return None
    return render_tour_overlay(step)


# Callback 3: On initial page load, check localStorage and auto-show tour.


@app.callback(
    Output("tour-step", "data", allow_duplicate=True),
    Input("tour-state", "data"),
    prevent_initial_call="initial_duplicate",
)
def tour_auto_show(tour_state: dict | None):
    tour_state = tour_state or {"completed": False, "step": 0}
    if not tour_state.get("completed", False):
        return tour_state.get("step", 0)
    return -1


# ── What-if slider callback ───────────────────────────────────────────────────


@app.callback(
    Output("what-if-metrics", "children"),
    Input("what-if-ask-slider", "value"),
    State("property-selector-dropdown", "value"),
    State("loaded-preset-ids", "data"),
    prevent_initial_call=True,
)
def update_what_if(adjusted_ask: float | None, focus_id: str | None, loaded_ids: list[str] | None):
    if adjusted_ask is None:
        return no_update
    report = _focused_report(loaded_ids, focus_id)
    if report is None:
        return no_update
    view = build_property_analysis_view(report)
    return render_what_if_metrics(view, adjusted_ask)


# ── PDF/text export callback ─────────────────────────────────────────────────


@app.callback(
    Output("pdf-download", "data"),
    Input("export-tear-sheet-button", "n_clicks"),
    State("property-selector-dropdown", "value"),
    State("loaded-preset-ids", "data"),
    prevent_initial_call=True,
)
def export_analysis_report(_n: int, focus_id: str | None, loaded_ids: list[str] | None):
    report = _focused_report(loaded_ids, focus_id)
    if report is None:
        return no_update
    view = build_property_analysis_view(report)
    from briarwood.dash_app.theme import score_label as _sl
    from briarwood.dash_app.components import _extract_diverse_items
    lines = [
        "BRIARWOOD PROPERTY ANALYSIS",
        "=" * 50,
        "",
        f"Property: {view.address}",
        f"Ask: ${(view.ask_price or 0):,.0f}",
        "",
        f"VERDICT: {(view.recommendation_tier or 'N/A').upper()}",
        f"Score: {(view.final_score or 0):.2f}/5 ({_sl(view.final_score or 0)})",
        "",
    ]
    if view.lens_scores:
        best = view.lens_scores.recommended_lens
        lines.append(f"Best For: {best.replace('_', ' ').title()}")
        lines.append(f"  Reason: {view.lens_scores.recommendation_reason}")
        lines.append("")
        lines.append("LENS SCORES")
        lines.append(f"  Risk:      {view.lens_scores.risk_score:.1f}/5")
        if view.lens_scores.investor_score is not None:
            lines.append(f"  Investor:  {view.lens_scores.investor_score:.1f}/5")
        if view.lens_scores.owner_score is not None:
            lines.append(f"  Owner:     {view.lens_scores.owner_score:.1f}/5")
        if view.lens_scores.developer_score is not None:
            lines.append(f"  Developer: {view.lens_scores.developer_score:.1f}/5")
        lines.append("")
    if view.category_scores:
        lines.append("CATEGORY SCORES")
        for _key, cat in view.category_scores.items():
            lines.append(f"  {cat.category_name:20s} {cat.score:.1f}/5  ({_sl(cat.score)})")
        lines.append("")
    strengths = _extract_diverse_items(view, best=True, count=3)
    risks = _extract_diverse_items(view, best=False, count=3)
    if strengths:
        lines.append("TOP STRENGTHS")
        for s in strengths:
            lines.append(f"  + {s}")
        lines.append("")
    if risks:
        lines.append("TOP RISKS")
        for r in risks:
            lines.append(f"  - {r}")
        lines.append("")
    lines.append("KEY METRICS")
    lines.append(f"  BCV:       ${(view.bcv or 0):,.0f}")
    lines.append(f"  Base Case: ${(view.base_case or 0):,.0f}")
    if view.mispricing_pct is not None:
        lines.append(f"  BCV Gap:   {view.mispricing_pct * 100:+.1f}%")
    lines.append(f"  PTR:       {view.income_support.price_to_rent_text}")
    lines.append(f"  Cash Flow: {view.income_support.monthly_cash_flow_text}")
    lines.append(f"  Risk:      {view.risk_location.risk_score:.0f}/100")
    lines.append("")
    lines.append("Generated by Briarwood Research Platform")
    content = "\n".join(lines)
    safe_name = view.address.replace(" ", "_").replace(",", "")[:40]
    return dict(content=content, filename=f"{safe_name}_analysis.txt")

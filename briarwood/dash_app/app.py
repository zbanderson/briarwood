"""
Briarwood — Investment Research Platform
Dark-theme, 4-tab layout: Tear Sheet | Scenarios | Compare | Data Quality
"""
from __future__ import annotations

import os
import traceback
from datetime import datetime

import dash
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
    export_preset_tear_sheet_pdf,
    list_comp_database_rows,
    list_presets,
    list_saved_properties,
    load_comp_form_defaults,
    load_property_form_defaults,
    load_report_for_preset,
    load_reports,
    register_manual_analysis,
)
from briarwood.dash_app.theme import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED, ACCENT_YELLOW,
    BG_BASE, BG_SURFACE, BG_SURFACE_2, BG_SURFACE_3, BG_SURFACE_4,
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


def _form_property_type(property_type: str | None) -> str:
    mapping = {
        "single family residence": "single_family",
        "single family": "single_family",
        "duplex": "duplex",
        "triplex": "triplex",
        "fourplex": "fourplex",
        "multi-family": "multi_family",
        "multi family": "multi_family",
    }
    normalized = (property_type or "").strip().lower()
    return mapping.get(normalized, "")


def _bool_dropdown_value(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def _highlight_input_style(is_missing: bool) -> dict:
    style = dict(INPUT_STYLE)
    if is_missing:
        style.update(
            {
                "border": f"1px solid {TONE_WARNING_TEXT}",
                "boxShadow": f"0 0 0 1px {TONE_WARNING_TEXT}33 inset",
                "backgroundColor": BG_SURFACE_2,
            }
        )
    return style


def _highlight_dropdown_style(is_missing: bool) -> dict:
    style = {"fontSize": "13px"}
    if is_missing:
        style.update(
            {
                "border": f"1px solid {TONE_WARNING_TEXT}",
                "borderRadius": "6px",
                "boxShadow": f"0 0 0 1px {TONE_WARNING_TEXT}33 inset",
                "backgroundColor": BG_SURFACE_2,
            }
        )
    return style


def _locked_input_style() -> dict:
    style = dict(INPUT_STYLE)
    style.update(
        {
            "backgroundColor": BG_SURFACE_2,
            "color": TEXT_MUTED,
            "cursor": "not-allowed",
            "opacity": "0.85",
        }
    )
    return style


def _normalize_compare_value(value: object) -> object:
    if value in ("", [], {}):
        return None
    return value


def _changed_property_fields(source_subject: dict[str, object], new_subject: dict[str, object]) -> list[str]:
    labels = {
        "address": "Address",
        "town": "Town",
        "state": "State",
        "county": "County",
        "purchase_price": "Ask Price",
        "beds": "Beds",
        "baths": "Baths",
        "sqft": "Sqft",
        "lot_size": "Lot Size",
        "year_built": "Year Built",
        "property_type": "Property Type",
        "taxes": "Taxes",
        "monthly_hoa": "HOA",
        "days_on_market": "Days on Market",
        "garage_spaces": "Garage Spaces",
        "garage_type": "Garage Type",
        "has_detached_garage": "Detached Garage",
        "has_back_house": "Back House / ADU",
        "adu_type": "ADU Type",
        "adu_sqft": "ADU Sqft",
        "has_basement": "Basement",
        "basement_finished": "Finished Basement",
        "has_pool": "Pool",
        "parking_spaces": "Parking",
        "corner_lot": "Corner Lot",
        "driveway_off_street": "Off-Street Parking",
        "estimated_monthly_rent": "Market Rent",
        "unit_rents": "Unit Rents",
        "back_house_monthly_rent": "Back House Rent",
        "seasonal_monthly_rent": "Seasonal Rent",
        "insurance": "Insurance",
        "monthly_maintenance_reserve_override": "Maintenance Reserve",
        "condition_profile": "Condition",
        "capex_lane": "CapEx Lane",
        "notes": "Notes",
    }
    changed: list[str] = []
    for key, label in labels.items():
        before = _normalize_compare_value(source_subject.get(key))
        after = _normalize_compare_value(new_subject.get(key))
        if before != after:
            changed.append(label)
    return changed


# ── Layout builders ────────────────────────────────────────────────────────────


def _topbar() -> html.Div:
    options = _property_options()
    initial_value = DEFAULT_PRESET_IDS[0] if DEFAULT_PRESET_IDS else (options[0]["value"] if options else None)
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
                        options=options,
                        value=initial_value,
                        clearable=False,
                        searchable=True,
                        persistence=True,
                        placeholder="Search property…",
                        style={"minWidth": "280px", "fontSize": "13px"},
                    ),
                ],
                style={"flex": "1", "maxWidth": "360px"},
            ),
            # Add Property toggle
            html.Button("+ Add Property", id="add-property-button", n_clicks=0, style=BTN_SECONDARY),
            html.Div(
                [
                    html.Button("Export PDF", id="export-tear-sheet-button", n_clicks=0, style=BTN_GHOST),
                    html.Button("Export TXT", id="export-txt-button", n_clicks=0, style={**BTN_GHOST, "opacity": "0.7"}),
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
    """Modal property manager with browse + edit/create flows."""
    return html.Div(
        html.Div(
            [
                # ── Header ──
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("Property Manager", style={"fontWeight": "700", "fontSize": "15px", "color": TEXT_PRIMARY, "letterSpacing": "-0.01em"}),
                                html.Div("Browse saved properties, pull from the comp database, or create a new working record.", style={"fontSize": "13px", "color": TEXT_MUTED}),
                                html.Div(id="manual-editing-status", style={"fontSize": "12px", "color": ACCENT_BLUE, "marginTop": "4px"}),
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
                        html.Div(
                            [
                                html.Button("Edit Selected Record", id="edit-selected-property-button", n_clicks=0, style=BTN_PRIMARY),
                                html.Button("Compare Selected", id="compare-selected-button", n_clicks=0, style=BTN_SECONDARY),
                            ],
                            style={"display": "flex", "gap": "8px", "marginTop": "4px", "flexWrap": "wrap"},
                        ),
                    ],
                    style=_DRAWER_CARD,
                ),
                html.Div(
                    [
                        html.Div("Comp Database", style=SECTION_HEADER_STYLE),
                        dash_table.DataTable(
                            id="comp-database-table",
                            columns=[
                                {"name": "Address", "id": "Address"},
                                {"name": "Town", "id": "Town"},
                                {"name": "Price", "id": "Price"},
                                {"name": "Status", "id": "Status"},
                                {"name": "Type", "id": "Type"},
                            ],
                            data=[],
                            row_selectable="single",
                            selected_rows=[],
                            page_size=6,
                            style_table={**TABLE_STYLE_TABLE, "maxWidth": "100%"},
                            style_header=TABLE_STYLE_HEADER,
                            style_cell={**TABLE_STYLE_CELL, "minWidth": "55px", "maxWidth": "120px", "whiteSpace": "normal", "fontSize": "13px", "padding": "6px 8px"},
                            style_data_conditional=[
                                {"if": {"row_index": "odd"}, **TABLE_STYLE_DATA_ODD},
                                {"if": {"row_index": "even"}, **TABLE_STYLE_DATA_EVEN},
                            ],
                        ),
                        html.Button("Analyze Selected Comp", id="analyze-selected-comp-button", n_clicks=0, style={**BTN_SECONDARY, "marginTop": "4px"}),
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
                "border": f"1px solid {BORDER}",
                "borderRadius": "10px",
                "padding": "20px",
                "width": "min(920px, calc(100vw - 48px))",
                "maxHeight": f"calc(100vh - {TOPBAR_HEIGHT} - 56px)",
                "overflowY": "auto",
                "boxShadow": "0 24px 72px rgba(0,0,0,0.55)",
                "margin": "0 auto",
            },
        ),
        id="add-property-drawer",
        style={"display": "none"},
    )


def _form_tier_label(text: str, tier: str) -> html.Div:
    """Section header with tier badge: REQUIRED / RECOMMENDED / OPTIONAL."""
    tier_colors = {
        "required": {"bg": "#1a3a1f", "border": "#2d6a35", "text": ACCENT_GREEN},
        "recommended": {"bg": "#3a2f0d", "border": "#6a4f0e", "text": TONE_WARNING_TEXT},
        "optional": {"bg": BG_SURFACE_3, "border": BORDER, "text": TEXT_MUTED},
    }
    c = tier_colors.get(tier, tier_colors["optional"])
    return html.Div(
        [
            html.Span(text, style={**SECTION_HEADER_STYLE, "marginBottom": "0", "display": "inline"}),
            html.Span(tier.upper(), style={
                "fontSize": "9px", "fontWeight": "600", "letterSpacing": "0.08em",
                "color": c["text"], "backgroundColor": c["bg"], "border": f"1px solid {c['border']}",
                "padding": "1px 5px", "borderRadius": "3px", "marginLeft": "8px", "verticalAlign": "middle",
            }),
        ],
    )


def _impact_hint(text: str) -> html.Div:
    """Small hint showing what impact adding this data has."""
    return html.Div(text, style={"fontSize": "10px", "color": TEXT_MUTED, "fontStyle": "italic", "marginTop": "2px"})


def _add_property_form_body() -> list:
    """Form fields grouped into themed cards with progressive disclosure."""
    return [
        # ── Required: Subject Property ──
        html.Div(
            [
                _form_tier_label("Subject Property", "required"),
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
                html.Div(
                    id="form-validation-hint",
                    style={"fontSize": "13px", "color": TEXT_MUTED, "marginTop": "2px"},
                ),
            ],
            style=_DRAWER_CARD,
        ),
        # ── Property Details (recommended — improves scoring) ──
        html.Div(
            [
                _form_tier_label("Property Details", "recommended"),
                _impact_hint("Adding taxes and condition improves risk scoring by ~15%"),
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
        # ── Income & Carry (recommended — enables income analysis) ──
        html.Div(
            [
                _form_tier_label("Income & Carry", "recommended"),
                _impact_hint("Adding rent estimate improves income confidence by ~12%"),
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
        # ── Physical Features (optional — collapsed by default) ──
        html.Details(
            [
                html.Summary(
                    _form_tier_label("Physical Features", "optional"),
                    style={"cursor": "pointer", "listStyle": "none", "outline": "none"},
                ),
                html.Div(
                    [
                        _impact_hint("ADU and lot features improve optionality scoring"),
                        html.Div(
                            [
                                _number_input("manual-garage-spaces", "Garage spaces"),
                                _dropdown("manual-garage-type", GARAGE_TYPE_OPTIONS, "Garage type"),
                            ],
                            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"},
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
                    style={"paddingTop": "8px", "display": "grid", "gap": "8px"},
                ),
            ],
            open=False,
            style={**_DRAWER_CARD, "padding": "12px 16px"},
        ),
        # ── Notes ──
        dcc.Textarea(
            id="manual-notes", placeholder="Notes or listing description (optional)",
            style={**INPUT_STYLE, "height": "60px", "resize": "vertical"},
        ),
        # ── Manual Comps (optional — collapsed by default) ──
        html.Details(
            [
                html.Summary(
                    _form_tier_label("Manual Comps", "optional"),
                    style={"cursor": "pointer", "listStyle": "none", "outline": "none"},
                ),
                html.Div(
                    [
                        _impact_hint("Adding comps improves valuation confidence significantly"),
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
                    style={"paddingTop": "8px", "display": "grid", "gap": "8px"},
                ),
            ],
            open=False,
            style={**_DRAWER_CARD, "padding": "12px 16px"},
        ),
        # ── Submit area ──
        html.Div(
            [
                html.Button(
                    "Start Analysis",
                    id="manual-run-analysis-trigger",
                    n_clicks=0,
                    type="button",
                    style=_BTN_ANALYZE_ENABLED,
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
                "backgroundColor": BG_BASE,
                "padding": "12px 0 4px",
                "borderTop": f"1px solid {BORDER}",
                "marginTop": "8px",
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
                        searchable=True,
                        persistence=True,
                        placeholder="Search 2–4 properties to compare…",
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
            dcc.Store(id="tear-sheet-view-mode", storage_type="local", data="owner"),
            dcc.Store(id="tear-sheet-lens", storage_type="local", data="auto"),
            dcc.Store(id="manual-form-target-property-id", data=None),
            dcc.Store(id="manual-form-comp-ref", data=None),
            dcc.Store(id="analysis-form-snapshot", data=None),
            # Tour state (persists in browser localStorage)
            dcc.Store(id="tour-state", storage_type="local", data={"completed": False, "step": 0}),
            # User preferences (persists in browser localStorage)
            dcc.Store(id="user-preferences", storage_type="local", data={
                "role": None,  # "investor", "owner", "developer", or None (show all)
                "expanded_sections": None,  # list of section keys, or None for defaults
                "hidden_sections": [],  # sections the user has explicitly hidden
            }),
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

            # Main content area (wrapped in Loading for property-switch feedback)
            dcc.Loading(
                id="main-content-loading",
                type="default",
                color=ACCENT_BLUE,
                children=html.Div(
                    id="main-tab-content",
                    style={"flex": "1", "minHeight": "0"},
                ),
                style={"flex": "1", "minHeight": "0"},
            ),

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
    Output("comp-database-table", "data"),
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
    default_value = loaded_ids[0] if loaded_ids else (options[0]["value"] if options else None)
    property_value = current_property_id if current_property_id in allowed else default_value
    compare_values = [pid for pid in (current_compare_ids or []) if pid in allowed][:4]
    return options, property_value, options, compare_values, _saved_property_rows(), list_comp_database_rows()


@app.callback(
    Output("active-property-status", "children"),
    Output("property-header-bar", "children"),
    Output("property-header-bar", "style"),
    Input("property-catalog-version", "data"),
    Input("property-selector-dropdown", "value"),
    Input("loaded-preset-ids", "data"),
)
def render_active_property_status(_catalog_version: int | None, property_id: str | None, loaded_ids: list[str] | None):
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

    # Risk indicator
    risk_val = view.risk_location.risk_score
    risk_color = ACCENT_GREEN if risk_val < 35 else ACCENT_YELLOW if risk_val < 55 else ACCENT_ORANGE if risk_val < 70 else ACCENT_RED

    # Monthly net burn/cash flow
    monthly_cf = view.compare_metrics.get("monthly_cash_flow")
    if isinstance(monthly_cf, (int, float)):
        cf_sign = "+" if monthly_cf >= 0 else ""
        monthly_text = f"{cf_sign}${monthly_cf:,.0f}"
        monthly_color = TONE_POSITIVE_TEXT if monthly_cf >= 0 else TONE_WARNING_TEXT if monthly_cf >= -500 else TONE_NEGATIVE_TEXT
    else:
        monthly_text = "—"
        monthly_color = TEXT_MUTED

    # Confidence level indicator
    conf_level = view.confidence_level
    conf_color = ACCENT_GREEN if conf_level == "High" else ACCENT_YELLOW if conf_level == "Medium" else ACCENT_RED

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
                    _header_metric("Net/Mo", monthly_text, color=monthly_color),
                    _header_metric("Risk", f"{risk_val:.0f}", color=risk_color),
                    # Compact separator
                    html.Span(style={"width": "1px", "height": "14px", "backgroundColor": BORDER, "flexShrink": "0"}),
                    _header_metric("Score", score_text or "—", color=sc),
                    html.Span(
                        view.recommendation_tier,
                        style=tone_badge_style("positive" if (view.final_score or 0) >= 3.75 else "warning" if (view.final_score or 0) >= 3.0 else "negative"),
                    ) if view.recommendation_tier else None,
                    # Confidence dot
                    html.Span(
                        [
                            html.Span("●", style={"color": conf_color, "fontSize": "8px", "marginRight": "3px"}),
                            html.Span(conf_level, style={"fontSize": "9px", "color": conf_color, "textTransform": "uppercase", "fontWeight": "600"}),
                        ],
                        style={"display": "inline-flex", "alignItems": "center"},
                    ),
                ],
                style={"display": "flex", "gap": "10px", "alignItems": "center"},
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
    Input("property-catalog-version", "data"),
    Input("property-selector-dropdown", "value"),
    Input("loaded-preset-ids", "data"),
    Input("last-analysis-summary", "data"),
)
def render_analysis_feedback(
    _catalog_version: int | None,
    property_id: str | None,
    loaded_ids: list[str] | None,
    summary: dict[str, str] | None,
):
    report = _focused_report(loaded_ids, property_id)
    focused_property_id = report.property_id if report is not None else (property_id or ((loaded_ids or [None])[0]))
    if summary and summary.get("property_id") == focused_property_id:
        missing = _core_missing_fields(report) if report is not None else []
        updated_suffix = f"  ·  Updated {summary.get('updated_at')}" if summary.get("updated_at") else ""
        summary_line = html.Div(
            [
                html.Span(
                    "Property updated" if summary.get("mode") == "updated" else "Analysis saved",
                    style={"fontWeight": "700", "color": TONE_POSITIVE_TEXT},
                ),
                html.Span(" — ", style={"color": TEXT_MUTED}),
                html.Span(
                    f"{summary.get('address', 'Property')}  ·  Ask: {summary.get('ask_price', '—')}  ·  "
                    f"Comps: {summary.get('comp_count', '0')}  ·  "
                    f"{'saved back to database' if summary.get('mode') == 'updated' else 'saved as active analysis'}"
                    f"{updated_suffix}",
                    style={"color": TEXT_SECONDARY},
                ),
            ],
            style={"fontSize": "13px"},
        )
        if missing:
            return html.Div(
                [
                    summary_line,
                    html.Div(
                        [
                            html.Span("Still missing core values", style={"fontWeight": "600", "color": TONE_WARNING_TEXT}),
                            html.Span(" — ", style={"color": TEXT_MUTED}),
                            html.Span(", ".join(missing[:5]) + ("…" if len(missing) > 5 else ""), style={"color": TEXT_SECONDARY}),
                            html.Button("Review & Update", id="fix-missing-values-button", n_clicks=0, style={**BTN_SECONDARY, "padding": "6px 10px", "marginLeft": "12px"}),
                        ],
                        style={"display": "flex", "alignItems": "center", "gap": "0", "marginTop": "8px", "fontSize": "13px"},
                    ),
                ],
                style={
                    "backgroundColor": BG_SURFACE_2,
                    "borderBottom": f"1px solid {BORDER}",
                    "padding": "10px 24px",
                    "flexShrink": "0",
                },
            )
        return html.Div(
            [summary_line],
            style={
                "backgroundColor": "#1a3a1f",
                "borderBottom": "1px solid #2d6a35",
                "padding": "10px 24px",
                "flexShrink": "0",
            },
        )

    if report is not None:
        missing = _core_missing_fields(report)
        if missing:
            return html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Property is missing core values", style={"fontWeight": "700", "color": TONE_WARNING_TEXT}),
                                    html.Span(" — ", style={"color": TEXT_MUTED}),
                                    html.Span(
                                        ", ".join(missing[:5]) + ("…" if len(missing) > 5 else ""),
                                        style={"color": TEXT_SECONDARY},
                                    ),
                                ],
                                style={"fontSize": "13px"},
                            ),
                            html.Button("Review & Update", id="fix-missing-values-button", n_clicks=0, style={**BTN_SECONDARY, "padding": "6px 10px"}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "gap": "12px", "alignItems": "center"},
                    ),
                ],
                style={
                    "backgroundColor": BG_SURFACE_2,
                    "borderBottom": f"1px solid {BORDER}",
                    "padding": "10px 24px",
                    "flexShrink": "0",
                },
            )
    return None


@app.callback(
    Output("manual-entry-status", "children", allow_duplicate=True),
    Output("add-property-open", "data", allow_duplicate=True),
    Output("manual-form-target-property-id", "data"),
    Output("manual-form-comp-ref", "data"),
    Input("add-property-button", "n_clicks"),
    Input("add-property-close-button", "n_clicks"),
    Input("fix-missing-values-button", "n_clicks"),
    State("property-selector-dropdown", "value"),
    State("loaded-preset-ids", "data"),
    State("add-property-open", "data"),
    prevent_initial_call=True,
)
def route_property_drawer(
    _open_clicks: int,
    _close_clicks: int,
    _fix_clicks: int,
    property_id: str | None,
    loaded_ids: list[str] | None,
    is_open: bool | None,
):
    triggered = ctx.triggered_id
    if triggered == "add-property-close-button":
        return "", False, None, None
    if triggered == "fix-missing-values-button":
        if not _fix_clicks:
            return no_update, no_update, no_update, no_update
        target_property_id = property_id or ((loaded_ids or [None])[0])
        return "", True, target_property_id, None
    if triggered == "add-property-button" and not _open_clicks:
        return no_update, no_update, no_update, no_update
    return "", True, None, None


@app.callback(
    Output("manual-property-id", "disabled"),
    Output("manual-property-id", "style"),
    Input("manual-form-target-property-id", "data"),
    Input("manual-form-comp-ref", "data"),
)
def configure_property_id_field(target_property_id: str | None, comp_ref: str | None):
    if target_property_id and not comp_ref:
        return True, _locked_input_style()
    return False, INPUT_STYLE


@app.callback(
    Output("manual-entry-status", "children", allow_duplicate=True),
    Output("add-property-open", "data", allow_duplicate=True),
    Output("manual-form-target-property-id", "data", allow_duplicate=True),
    Output("manual-form-comp-ref", "data", allow_duplicate=True),
    Input("analyze-selected-comp-button", "n_clicks"),
    State("comp-database-table", "data"),
    State("comp-database-table", "selected_rows"),
    prevent_initial_call=True,
)
def analyze_selected_comp(_n_clicks: int, rows: list[dict[str, str]] | None, selected_rows: list[int] | None):
    if not rows or not selected_rows:
        return html.Span("Select one comp from the database first.", style={"color": TONE_WARNING_TEXT}), no_update, no_update, no_update
    index = selected_rows[0]
    if not isinstance(index, int) or index < 0 or index >= len(rows):
        return html.Span("Select one comp from the database first.", style={"color": TONE_WARNING_TEXT}), no_update, no_update, no_update
    source_ref = rows[index].get("source_ref")
    if not source_ref:
        return html.Span("Selected comp is missing a database reference.", style={"color": TONE_WARNING_TEXT}), no_update, no_update, no_update
    return (
        html.Span(f"Loaded {rows[index].get('Address')} from the comp database into the analysis form.", style={"color": TONE_POSITIVE_TEXT}),
        True,
        None,
        source_ref,
    )


@app.callback(
    Output("manual-entry-status", "children", allow_duplicate=True),
    Output("add-property-open", "data", allow_duplicate=True),
    Output("manual-form-target-property-id", "data", allow_duplicate=True),
    Output("manual-form-comp-ref", "data", allow_duplicate=True),
    Input("edit-selected-property-button", "n_clicks"),
    State("saved-properties-table", "data"),
    State("saved-properties-table", "selected_rows"),
    prevent_initial_call=True,
)
def edit_selected_saved_property(_n_clicks: int, rows: list[dict[str, str]] | None, selected_rows: list[int] | None):
    if not rows or not selected_rows:
        return html.Span("Select one saved property first.", style={"color": TONE_WARNING_TEXT}), no_update, no_update, no_update
    if len(selected_rows) != 1:
        return html.Span("Select exactly one saved property to edit.", style={"color": TONE_WARNING_TEXT}), no_update, no_update, no_update
    index = selected_rows[0]
    if not isinstance(index, int) or index < 0 or index >= len(rows):
        return html.Span("Select one saved property first.", style={"color": TONE_WARNING_TEXT}), no_update, no_update, no_update
    property_id = rows[index].get("property_id")
    address = rows[index].get("Address") or property_id
    if not property_id:
        return html.Span("Selected record is missing a property id.", style={"color": TONE_WARNING_TEXT}), no_update, no_update, no_update
    return (
        html.Span(f"Loaded saved record {address} into the editor.", style={"color": TONE_POSITIVE_TEXT}),
        True,
        property_id,
        None,
    )


def _core_missing_fields(report) -> list[str]:
    property_input = report.property_input
    if property_input is None:
        return []
    fields: list[tuple[str, object]] = [
        ("Square footage", property_input.sqft),
        ("Lot size", property_input.lot_size),
        ("Condition", property_input.condition_profile),
        ("CapEx lane", property_input.capex_lane),
        ("Taxes", property_input.taxes),
        ("Insurance", property_input.insurance),
        ("Garage details", property_input.garage_spaces or property_input.garage_type),
        ("ADU / back house", property_input.has_back_house or property_input.adu_type or property_input.adu_sqft),
    ]
    missing = [label for label, value in fields if value in (None, "", [])]
    status_map = {item.key: item for item in build_property_analysis_view(report).evidence.metric_statuses}
    for key, label in [
        ("price_to_rent", "Rent support"),
        ("net_monthly_cost", "Carry inputs"),
        ("capex_load", "CapEx budget / condition"),
    ]:
        item = status_map.get(key)
        if item is not None and item.status in {"estimated", "unresolved"} and label not in missing:
            missing.append(label)
    return missing


def _core_missing_field_flags(report) -> dict[str, bool]:
    property_input = report.property_input
    if property_input is None:
        return {}
    return {
        "manual-sqft": property_input.sqft in (None, ""),
        "manual-lot-size": property_input.lot_size in (None, ""),
        "manual-condition-profile": property_input.condition_profile in (None, ""),
        "manual-capex-lane": property_input.capex_lane in (None, ""),
        "manual-garage-spaces": property_input.garage_spaces in (None, "") and property_input.garage_type in (None, ""),
        "manual-has-back-house": property_input.has_back_house in (None, "") and property_input.adu_type in (None, ""),
        "manual-estimated-rent": property_input.estimated_monthly_rent in (None, "") and not list(property_input.unit_rents or []),
        "manual-insurance": property_input.insurance in (None, ""),
    }


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
    Input("property-catalog-version", "data"),
    Input("loaded-preset-ids", "data"),
    Input("property-selector-dropdown", "value"),
    Input("tear-sheet-view-mode", "data"),
    Input("tear-sheet-lens", "data"),
)
def render_main_tab(
    tab: str,
    _catalog_version: int | None,
    loaded_ids: list[str] | None,
    focus_id: str | None,
    tear_sheet_view_mode: str | None,
    tear_sheet_lens: str | None,
):
    if tab == "tear_sheet":
        report = _focused_report(loaded_ids, focus_id)
        if report is None:
            return _empty_state("Add or select a property to begin.")
        view = build_property_analysis_view(report)
        return _centered_main_panel(
            render_tear_sheet_body(view, report, tear_sheet_view_mode or "owner", tear_sheet_lens or "auto"),
            padding="0 20px 24px",
            max_width="1140px",
        )

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


@app.callback(
    Output("tear-sheet-view-mode", "data"),
    Input("tear-sheet-view-toggle", "value"),
    State("tear-sheet-view-mode", "data"),
    prevent_initial_call=True,
)
def update_tear_sheet_view_mode(selected_mode: str | None, current_mode: str | None) -> str:
    if selected_mode in {"owner", "realtor"}:
        return selected_mode
    return current_mode or "owner"


@app.callback(
    Output("tear-sheet-lens", "data"),
    Input("tear-sheet-lens-selector", "value"),
    State("tear-sheet-lens", "data"),
    prevent_initial_call=True,
)
def update_tear_sheet_lens(selected_lens: str | None, current_lens: str | None) -> str:
    if selected_lens in {"auto", "risk", "investor", "owner", "developer"}:
        return selected_lens
    return current_lens or "auto"


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
    Output("manual-run-analysis-trigger", "children"),
    Input("manual-form-target-property-id", "data"),
    Input("manual-form-comp-ref", "data"),
)
def update_manual_action_label(target_property_id: str | None, comp_ref: str | None):
    if target_property_id and not comp_ref:
        return "Save & Re-Run Analysis"
    if comp_ref:
        return "Create Analysis from Comp"
    return "Save & Run Analysis"


@app.callback(
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

    warnings: list[str] = []
    if beds in (None, ""):
        warnings.append("beds")
    if baths in (None, ""):
        warnings.append("baths")
    if sqft in (None, "", 0):
        warnings.append("sqft")

    if missing:
        return html.Span(f"Required: {', '.join(missing)}", style={"color": TONE_NEGATIVE_TEXT})
    if warnings:
        return html.Span(
            [
                html.Span("Ready to analyze", style={"color": TONE_POSITIVE_TEXT}),
                html.Span(f"  ·  recommended: {', '.join(warnings)}", style={"color": TONE_WARNING_TEXT}),
            ]
        )
    return html.Span("Ready to analyze", style={"color": TONE_POSITIVE_TEXT})


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
    Output("add-property-drawer", "style"),
    Input("add-property-open", "data"),
)
def set_drawer_visibility(is_open: bool | None):
    if is_open:
        return {
            "display": "flex",
            "position": "fixed",
            "top": TOPBAR_HEIGHT,
            "left": "0",
            "right": "0",
            "bottom": "0",
            "padding": "24px",
            "alignItems": "flex-start",
            "justifyContent": "center",
            "backgroundColor": "rgba(10, 14, 24, 0.58)",
            "backdropFilter": "blur(4px)",
            "zIndex": "150",
            "overflowY": "auto",
        }
    return {"display": "none"}


@app.callback(
    Output("manual-property-id", "value"),
    Output("manual-address", "value"),
    Output("manual-town", "value"),
    Output("manual-state", "value"),
    Output("manual-county", "value"),
    Output("manual-price", "value"),
    Output("manual-beds", "value"),
    Output("manual-baths", "value"),
    Output("manual-sqft", "value"),
    Output("manual-lot-size", "value"),
    Output("manual-year-built", "value"),
    Output("manual-property-type", "value"),
    Output("manual-taxes", "value"),
    Output("manual-hoa", "value"),
    Output("manual-dom", "value"),
    Output("manual-garage-spaces", "value"),
    Output("manual-garage-type", "value"),
    Output("manual-has-back-house", "value"),
    Output("manual-adu-type", "value"),
    Output("manual-adu-sqft", "value"),
    Output("manual-has-basement", "value"),
    Output("manual-basement-finished", "value"),
    Output("manual-has-pool", "value"),
    Output("manual-parking-spaces", "value"),
    Output("manual-corner-lot", "value"),
    Output("manual-driveway-off-street", "value"),
    Output("manual-estimated-rent", "value"),
    Output("manual-rent-1", "value"),
    Output("manual-rent-2", "value"),
    Output("manual-rent-3", "value"),
    Output("manual-rent-4", "value"),
    Output("manual-back-house-rent", "value"),
    Output("manual-seasonal-rent", "value"),
    Output("manual-insurance", "value"),
    Output("manual-maintenance-reserve", "value"),
    Output("manual-condition-profile", "value"),
    Output("manual-capex-lane", "value"),
    Output("manual-notes", "value"),
    Output("manual-comps-store", "data", allow_duplicate=True),
    Output("manual-editing-status", "children"),
    Input("add-property-open", "data"),
    Input("manual-form-target-property-id", "data"),
    Input("manual-form-comp-ref", "data"),
    prevent_initial_call=True,
)
def populate_manual_form(is_open: bool | None, target_property_id: str | None, comp_ref: str | None):
    if not is_open:
        return (no_update,) * 40

    if comp_ref:
        subject, comps = load_comp_form_defaults(comp_ref)
        unit_rents = list(subject.get("unit_rents") or [])
        return (
            subject.get("property_id") or "",
            subject.get("address"),
            subject.get("town") or "Belmar",
            subject.get("state") or "NJ",
            subject.get("county") or "Monmouth",
            subject.get("purchase_price"),
            subject.get("beds"),
            subject.get("baths"),
            subject.get("sqft"),
            subject.get("lot_size"),
            subject.get("year_built"),
            _form_property_type(subject.get("property_type")),
            subject.get("taxes"),
            subject.get("monthly_hoa"),
            subject.get("days_on_market"),
            subject.get("garage_spaces"),
            subject.get("garage_type") or "",
            _bool_dropdown_value(subject.get("has_back_house")),
            subject.get("adu_type") or "",
            subject.get("adu_sqft"),
            _bool_dropdown_value(subject.get("has_basement")),
            _bool_dropdown_value(subject.get("basement_finished")),
            _bool_dropdown_value(subject.get("has_pool")),
            subject.get("parking_spaces"),
            _bool_dropdown_value(subject.get("corner_lot")),
            _bool_dropdown_value(subject.get("driveway_off_street")),
            subject.get("estimated_monthly_rent"),
            unit_rents[0] if len(unit_rents) > 0 else None,
            unit_rents[1] if len(unit_rents) > 1 else None,
            unit_rents[2] if len(unit_rents) > 2 else None,
            unit_rents[3] if len(unit_rents) > 3 else None,
            subject.get("back_house_monthly_rent"),
            subject.get("seasonal_monthly_rent"),
            subject.get("insurance"),
            subject.get("monthly_maintenance_reserve_override"),
            subject.get("condition_profile") or "",
            subject.get("capex_lane") or "",
            subject.get("notes") or "",
            comps,
            f"Creating a new analysis seeded from comp database row {comp_ref}",
        )

    if not target_property_id:
        return (
            "",
            None,
            "Belmar",
            "NJ",
            "Monmouth",
            None,
            None,
            None,
            None,
            None,
            None,
            "",
            None,
            None,
            None,
            None,
            "",
            "",
            "",
            "",
            None,
            "",
            "",
            "",
            None,
            "",
            "",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "",
            "",
            "",
            [],
            "Creating a new property analysis record",
        )

    subject, comps = load_property_form_defaults(target_property_id)
    unit_rents = list(subject.get("unit_rents") or [])
    return (
        subject.get("property_id") or target_property_id,
        subject.get("address"),
        subject.get("town") or "Belmar",
        subject.get("state") or "NJ",
        subject.get("county") or "Monmouth",
        subject.get("purchase_price"),
        subject.get("beds"),
        subject.get("baths"),
        subject.get("sqft"),
        subject.get("lot_size"),
        subject.get("year_built"),
        _form_property_type(subject.get("property_type")),
        subject.get("taxes"),
        subject.get("monthly_hoa"),
        subject.get("days_on_market"),
        subject.get("garage_spaces"),
        subject.get("garage_type") or "",
        _bool_dropdown_value(subject.get("has_back_house")),
        subject.get("adu_type") or "",
        subject.get("adu_sqft"),
        _bool_dropdown_value(subject.get("has_basement")),
        _bool_dropdown_value(subject.get("basement_finished")),
        _bool_dropdown_value(subject.get("has_pool")),
        subject.get("parking_spaces"),
        _bool_dropdown_value(subject.get("corner_lot")),
        _bool_dropdown_value(subject.get("driveway_off_street")),
        subject.get("estimated_monthly_rent"),
        unit_rents[0] if len(unit_rents) > 0 else None,
        unit_rents[1] if len(unit_rents) > 1 else None,
        unit_rents[2] if len(unit_rents) > 2 else None,
        unit_rents[3] if len(unit_rents) > 3 else None,
        subject.get("back_house_monthly_rent"),
        subject.get("seasonal_monthly_rent"),
        subject.get("insurance"),
        subject.get("monthly_maintenance_reserve_override"),
        subject.get("condition_profile") or "",
        subject.get("capex_lane") or "",
        subject.get("notes") or "",
        comps,
        f"Editing saved record: {target_property_id} · {subject.get('address') or target_property_id}",
    )


@app.callback(
    Output("manual-sqft", "style"),
    Output("manual-lot-size", "style"),
    Output("manual-condition-profile", "style"),
    Output("manual-capex-lane", "style"),
    Output("manual-garage-spaces", "style"),
    Output("manual-has-back-house", "style"),
    Output("manual-estimated-rent", "style"),
    Output("manual-insurance", "style"),
    Output("form-validation-hint", "children", allow_duplicate=True),
    Input("add-property-open", "data"),
    State("manual-form-target-property-id", "data"),
    State("manual-form-comp-ref", "data"),
    prevent_initial_call=True,
)
def highlight_missing_manual_fields(is_open: bool | None, target_property_id: str | None, comp_ref: str | None):
    if not is_open or (not target_property_id and not comp_ref):
        neutral_input = _highlight_input_style(False)
        neutral_dropdown = _highlight_dropdown_style(False)
        return (
            neutral_input,
            neutral_input,
            neutral_dropdown,
            neutral_dropdown,
            neutral_input,
            neutral_dropdown,
            neutral_input,
            neutral_input,
            "Address and asking price are required. Highlighted fields would materially improve the analysis.",
        )

    if comp_ref:
        subject, _ = load_comp_form_defaults(comp_ref)
        missing = [label for label, value in {
            "Square footage": subject.get("sqft"),
            "Lot size": subject.get("lot_size"),
            "Condition": subject.get("condition_profile"),
            "CapEx lane": subject.get("capex_lane"),
            "Insurance": subject.get("insurance"),
            "Rent support": subject.get("estimated_monthly_rent"),
        }.items() if value in (None, "", [])]
        flags = {
            "manual-sqft": subject.get("sqft") in (None, ""),
            "manual-lot-size": subject.get("lot_size") in (None, ""),
            "manual-condition-profile": subject.get("condition_profile") in (None, ""),
            "manual-capex-lane": subject.get("capex_lane") in (None, ""),
            "manual-garage-spaces": subject.get("garage_spaces") in (None, ""),
            "manual-has-back-house": subject.get("has_back_house") in (None, ""),
            "manual-estimated-rent": subject.get("estimated_monthly_rent") in (None, ""),
            "manual-insurance": subject.get("insurance") in (None, ""),
        }
    else:
        report = load_report_for_preset(target_property_id)
        flags = _core_missing_field_flags(report)
        missing = _core_missing_fields(report)

    hint = (
        html.Span(
            f"Highlighted fields are currently missing or inferred: {', '.join(missing[:5])}. Update them and save to rerun the analysis on this record.",
            style={"color": TONE_WARNING_TEXT},
        )
        if missing
        else html.Span("Ready to analyze — update any fields and save to rerun the analysis.", style={"color": TONE_POSITIVE_TEXT})
    )
    return (
        _highlight_input_style(flags.get("manual-sqft", False)),
        _highlight_input_style(flags.get("manual-lot-size", False)),
        _highlight_dropdown_style(flags.get("manual-condition-profile", False)),
        _highlight_dropdown_style(flags.get("manual-capex-lane", False)),
        _highlight_input_style(flags.get("manual-garage-spaces", False)),
        _highlight_dropdown_style(flags.get("manual-has-back-house", False)),
        _highlight_input_style(flags.get("manual-estimated-rent", False)),
        _highlight_input_style(flags.get("manual-insurance", False)),
        hint,
    )


# ── Export callbacks ───────────────────────────────────────────────────────────


@app.callback(
    Output("export-status", "children"),
    Input("export-tear-sheet-button", "n_clicks"),
    State("property-selector-dropdown", "value"),
    prevent_initial_call=True,
)
def export_tear_sheet_pdf(_n_clicks: int, property_id: str | None):
    if not property_id:
        return "Choose a property first."
    output_path = export_preset_tear_sheet_pdf(property_id)
    return html.Span(
        [html.Span("Exported! ", style={"color": ACCENT_GREEN, "fontWeight": "600"}), str(output_path)],
        style={"fontFamily": FONT_MONO, "fontSize": "13px"},
    )


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
    output_path = export_preset_tear_sheet_pdf(property_id)
    return html.Span(
        [html.Span("Exported! ", style={"color": ACCENT_GREEN, "fontWeight": "600"}), str(output_path)],
        style={"fontFamily": FONT_MONO, "fontSize": "13px"},
    )


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
    Output("add-property-open", "data", allow_duplicate=True),
    Output("last-analysis-summary", "data", allow_duplicate=True),
    Output("main-tabs", "value"),
    Output("analysis-loading-target", "children"),
    Input("manual-run-analysis-trigger", "n_clicks"),
    State("manual-comps-store", "data"),
    State("manual-form-target-property-id", "data"),
    State("manual-form-comp-ref", "data"),
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
)
def run_manual_analysis(
    _n_clicks: int,
    comps: list[dict[str, object]] | None,
    target_property_id: str | None,
    comp_ref: str | None,
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
    if not _n_clicks:
        raise dash.exceptions.PreventUpdate
    print(
        f"[ANALYSIS] Submit clicked: n={_n_clicks}, target_property_id={target_property_id}, comp_ref={comp_ref}, address={address!r}",
        flush=True,
    )
    catalog_version = 0  # will be bumped
    options = _property_options()
    is_edit_mode = bool(target_property_id and not comp_ref)
    original_subject: dict[str, object] = {}
    if is_edit_mode and target_property_id:
        try:
            original_subject, _existing_comps = load_property_form_defaults(target_property_id)
        except Exception:
            original_subject = {}
    unit_count = _unit_count_for_property_type(property_type)
    unit_rents = [rent for rent in (rent_1, rent_2, rent_3, rent_4) if rent not in (None, "", 0)]
    if not address:
        error_msg = html.Div(
            [
                html.Div("Save not started", style={"color": TONE_NEGATIVE_TEXT, "fontWeight": "600"}),
                html.Div("The current form is missing an address. Reload the saved record into the editor and try again.", style={"color": TEXT_SECONDARY, "marginTop": "4px"}),
                html.Div(
                    f"Edit target: {target_property_id or 'none'}",
                    style={"color": TEXT_MUTED, "fontSize": "12px", "marginTop": "4px"},
                ),
            ]
        )
        return no_update, error_msg, no_update, no_update, no_update, no_update, ""
    if price in (None, ""):
        error_msg = html.Div(
            [
                html.Div("Analysis not started", style={"color": TONE_NEGATIVE_TEXT, "fontWeight": "600"}),
                html.Div("Address and asking price are required.", style={"color": TEXT_SECONDARY, "marginTop": "4px"}),
            ]
        )
        return no_update, error_msg, no_update, no_update, no_update, no_update, ""

    def _bool(v: str | None) -> bool | None:
        if v == "true":
            return True
        if v == "false":
            return False
        return None

    subject = {
        "property_id": target_property_id or property_id,
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
        "has_detached_garage": True if (garage_type or "").strip().lower() == "detached" else False if garage_spaces not in (None, "", 0) else None,
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
    changed_fields = _changed_property_fields(original_subject, subject) if is_edit_mode and original_subject else []

    try:
        print(f"[ANALYSIS] Calling register_manual_analysis for {subject.get('address')}, edit_mode={is_edit_mode}", flush=True)
        new_id, tear_sheet_path = register_manual_analysis(subject, comps or [])
        print(f"[ANALYSIS] SUCCESS: new_id={new_id}, path={tear_sheet_path}", flush=True)
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
            "mode": "updated" if is_edit_mode else "manual",
            "tear_sheet_path": str(tear_sheet_path),
            "unit_rents": len(unit_rents),
            "updated_at": datetime.now().strftime("%I:%M:%S %p").lstrip("0"),
        }
        new_version = (catalog_version or 0) + 1
        success_msg = html.Div(
            [
                html.Div("Update complete" if is_edit_mode else "Analysis complete", style={"color": TONE_POSITIVE_TEXT, "fontWeight": "600"}),
                html.Div(
                    f"{address} updated in the saved property database and reloaded."
                    if is_edit_mode else
                    f"{address} saved and loaded as the active property.",
                    style={"color": TEXT_SECONDARY, "marginTop": "4px"},
                ),
                html.Div(
                    f"Record id: {new_id}",
                    style={"color": TEXT_MUTED, "fontSize": "12px", "marginTop": "4px"},
                ),
                html.Div(
                    "Changed fields: " + (", ".join(changed_fields[:8]) if changed_fields else "no material field changes detected; analysis was re-run on the current record."),
                    style={"color": TEXT_SECONDARY, "fontSize": "12px", "marginTop": "4px"},
                ) if is_edit_mode else None,
                html.Div(f"Tear sheet: {tear_sheet_path}", style={"color": TEXT_MUTED, "fontSize": "13px", "marginTop": "4px"}),
                html.Ul(
                    [html.Li(note, style={"color": TONE_WARNING_TEXT if "fell back" in note else TEXT_SECONDARY, "fontSize": "13px"}) for note in inline_notes],
                    style={"margin": "6px 0 0", "paddingLeft": "18px"},
                ) if inline_notes else None,
            ]
        )
        return [new_id], success_msg, new_version, False, summary, "tear_sheet", ""
    except Exception as exc:
        print(f"[ANALYSIS] EXCEPTION: {type(exc).__name__}: {exc}", flush=True)
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
        return no_update, error_msg, no_update, no_update, no_update, no_update, ""




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
    Input("what-if-rate-slider", "value"),
    Input("what-if-vacancy-toggle", "value"),
    State("property-selector-dropdown", "value"),
    State("loaded-preset-ids", "data"),
    prevent_initial_call=True,
)
def update_what_if(adjusted_ask: float | None, rate: float | None, vacancy: float | None, focus_id: str | None, loaded_ids: list[str] | None):
    if adjusted_ask is None:
        return no_update
    report = _focused_report(loaded_ids, focus_id)
    if report is None:
        return no_update
    view = build_property_analysis_view(report)
    vacancy = vacancy if vacancy is not None else 0.05
    return render_what_if_metrics(view, adjusted_ask, rate, vacancy)


# ── TXT export callback ──────────────────────────────────────────────────────


@app.callback(
    Output("pdf-download", "data"),
    Input("export-txt-button", "n_clicks"),
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

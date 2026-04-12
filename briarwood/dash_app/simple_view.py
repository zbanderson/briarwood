"""Simple View — the product.

Answers three questions in under 10 seconds:
1. Should I do this? → Decision hero
2. What could go wrong? → Risk Check
3. Why might this still be interesting? → Value Finder

Then 3 action buttons for Layer 2 progressive disclosure.
"""
from __future__ import annotations

from dash import dcc, html

from briarwood.dash_app.quick_decision import (
    QuickDecisionViewModel,
    build_quick_decision_view,
)
from briarwood.dash_app.theme import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_RED,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_SURFACE,
    BORDER,
    BTN_SECONDARY,
    CARD_STYLE,
    CARD_STYLE_ELEVATED,
    FONT_FAMILY,
    FONT_MONO,
    LABEL_STYLE,
    RADIUS_LG,
    RADIUS_MD,
    SECTION_HEADER_STYLE,
    SHADOW_SOFT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    dejargon,
    risk_dot,
    tone_badge_style,
    verdict_color,
)
from briarwood.dash_app.view_models import PropertyAnalysisView
from briarwood.schemas import AnalysisReport


# ── Risk category mapping ─────────────────────────────────────────────────────

_RISK_CATEGORY_MAP: dict[str, str] = {
    "Price Confidence": "Price Risk",
    "Confidence": "Data Quality",
    "Price Risk": "Price Risk",
    "Income Risk": "Carry Risk",
    "Carry Risk": "Carry Risk",
    "Market Risk": "Exit Risk",
    "Exit Risk": "Exit Risk",
    "Execution Risk": "Execution Risk",
    "Condition Risk": "Execution Risk",
    "Flood Risk": "Exit Risk",
    "Liquidity Risk": "Exit Risk",
    "Data Quality": "Data Quality",
}


def _standardize_risk_name(name: str) -> str:
    return _RISK_CATEGORY_MAP.get(name, name)


def _risk_color(level: str) -> str:
    if level == "Low":
        return ACCENT_GREEN
    if level == "Medium":
        return ACCENT_AMBER
    return ACCENT_RED


# ── Public entry point ────────────────────────────────────────────────────────


def render_simple_view(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Render the default property view — 5 cards + 3 action buttons.

    This IS the product. 90% of users never go deeper.
    """
    quick_vm = build_quick_decision_view(report)

    return html.Div(
        [
            _render_toggle(user_role),
            _render_property_header(view),
            _render_decision_hero(quick_vm, user_role=user_role),
            _render_risk_check(view, quick_vm),
            _render_value_card(view),
            _render_monthly_reality(view, report, user_role=user_role),
            _render_action_buttons(),
        ],
        className="briarwood-fade-in",
        style={
            "display": "grid",
            "gap": "16px",
            "maxWidth": "720px",
            "margin": "0 auto",
            "padding": "24px 16px 48px",
        },
    )


# ── Retail / Investor toggle ─────────────────────────────────────────────────


def _render_toggle(user_role: str) -> html.Div:
    return html.Div(
        [
            html.Button(
                "Homebuyer",
                id={"type": "role-toggle", "role": "homebuyer"},
                className=f"toggle-option {'active' if user_role == 'homebuyer' else ''}",
                n_clicks=0,
            ),
            html.Button(
                "Investor",
                id={"type": "role-toggle", "role": "investor"},
                className=f"toggle-option {'active' if user_role == 'investor' else ''}",
                n_clicks=0,
            ),
        ],
        className="toggle-group",
        style={"display": "flex", "justifyContent": "center"},
    )


# ── Card 1: Property Header ──────────────────────────────────────────────────


def _render_property_header(view: PropertyAnalysisView) -> html.Div:
    pi = view
    bed_bath = f"{pi.evidence.user_supplied_inputs[0] if pi.evidence.user_supplied_inputs else ''}"
    # Build the spec line from available data
    specs: list[str] = []
    # Extract from compare_metrics or label
    for label_key in ["beds", "baths", "sqft", "lot_size"]:
        val = view.compare_metrics.get(label_key)
        if val is not None:
            if label_key == "beds":
                specs.append(f"{int(val)} bed")
            elif label_key == "baths":
                specs.append(f"{val:g} bath")
            elif label_key == "sqft":
                specs.append(f"{int(val):,} sqft")
            elif label_key == "lot_size" and val > 0:
                specs.append(f"{val:.2f} acres")

    spec_line = " \u00b7 ".join(specs) if specs else ""
    ask_text = f"Asking: ${view.ask_price:,.0f}" if view.ask_price else ""

    return html.Div(
        [
            html.Div(
                view.address,
                style={"fontSize": "22px", "fontWeight": "700", "color": TEXT_PRIMARY, "lineHeight": "1.3"},
            ),
            html.Div(
                spec_line,
                style={"fontSize": "14px", "color": TEXT_SECONDARY, "marginTop": "4px"},
            ) if spec_line else None,
            html.Div(
                ask_text,
                style={"fontSize": "16px", "fontWeight": "600", "fontFamily": FONT_MONO, "color": TEXT_PRIMARY, "marginTop": "6px"},
            ) if ask_text else None,
        ],
        style={**CARD_STYLE, "padding": "24px 28px"},
    )


# ── Card 2: Decision Hero ────────────────────────────────────────────────────


def _render_decision_hero(vm: QuickDecisionViewModel, *, user_role: str = "homebuyer") -> html.Div:
    accent = verdict_color(vm.recommendation)

    question = "Should I buy this?" if user_role == "homebuyer" else "Does this pencil?"

    return html.Div(
        className="card briarwood-fade-in",
        children=[
            html.Div("DECISION", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em", "marginBottom": "16px"}),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                vm.recommendation,
                                style={
                                    "fontSize": "48px",
                                    "fontWeight": "800",
                                    "letterSpacing": "-0.04em",
                                    "lineHeight": "1.0",
                                    "color": accent,
                                },
                            ),
                            html.Div(question, style={**LABEL_STYLE, "marginTop": "8px"}),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div(
                                f"Score: {vm.conviction * 5:.1f}",
                                style={"fontSize": "14px", "fontWeight": "600", "color": TEXT_SECONDARY},
                            ),
                            html.Div(
                                f"Confidence: {vm.confidence}",
                                style={"fontSize": "13px", "color": TEXT_TERTIARY, "marginTop": "2px"},
                            ),
                        ],
                        style={"textAlign": "right"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "gap": "16px", "marginBottom": "20px"},
            ),
            html.Div(
                [
                    html.Div(
                        f"\u201c{vm.primary_reason}\u201d",
                        style={"fontSize": "16px", "fontWeight": "500", "lineHeight": "1.5", "color": TEXT_PRIMARY, "fontStyle": "italic"},
                    ),
                ],
                style={"marginBottom": "0"},
            ),
        ],
        style={
            **CARD_STYLE_ELEVATED,
            "borderLeft": f"4px solid {accent}",
            "padding": "28px 32px",
        },
    )


# ── Card 3: Risk Check ───────────────────────────────────────────────────────


def _render_risk_check(view: PropertyAnalysisView, vm: QuickDecisionViewModel) -> html.Div:
    # Map risk bar items to standardized categories
    seen: set[str] = set()
    risk_rows: list[html.Div] = []
    for item in vm.risk_bar[:6]:
        std_name = _standardize_risk_name(item.name)
        if std_name in seen:
            continue
        seen.add(std_name)
        color = _risk_color(item.level)
        dots = risk_dot(item.level)
        risk_rows.append(
            html.Div(
                [
                    html.Span(
                        std_name,
                        style={"fontSize": "14px", "fontWeight": "500", "color": TEXT_PRIMARY, "minWidth": "120px"},
                    ),
                    html.Span(
                        dots,
                        style={"fontSize": "14px", "color": color, "minWidth": "48px", "textAlign": "center", "letterSpacing": "2px"},
                    ),
                    html.Span(
                        f"{item.level}",
                        style={"fontSize": "12px", "fontWeight": "600", "color": color, "minWidth": "60px"},
                    ),
                    html.Span(
                        item.label,
                        style={"fontSize": "13px", "color": TEXT_SECONDARY, "flex": "1"},
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "16px",
                    "padding": "10px 0",
                    "borderBottom": f"1px solid {BORDER}",
                },
            )
        )
        if len(risk_rows) >= 5:
            break

    return html.Div(
        [
            html.Div("RISK CHECK", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
            html.Div(risk_rows),
        ],
        style=CARD_STYLE,
    )


# ── Card 4: Where's the Value ────────────────────────────────────────────────


def _render_value_card(view: PropertyAnalysisView) -> html.Div:
    bullets: list[str] = []
    if view.value_finder is not None and view.value_finder.bullets:
        bullets = list(view.value_finder.bullets[:4])

    # Fallback: build from top_reasons
    if not bullets and view.top_reasons:
        bullets = list(view.top_reasons[:3])

    # Final fallback
    if not bullets:
        bullets = ["Analysis in progress — check back after data loads."]

    return html.Div(
        [
            html.Div("WHERE'S THE VALUE", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
            html.Ul(
                [
                    html.Li(
                        bullet,
                        style={
                            "fontSize": "14px",
                            "lineHeight": "1.6",
                            "color": TEXT_PRIMARY,
                            "marginBottom": "8px",
                        },
                    )
                    for bullet in bullets
                ],
                style={"margin": "0", "paddingLeft": "20px"},
            ),
        ],
        style=CARD_STYLE,
    )


# ── Card 5: Monthly Reality ──────────────────────────────────────────────────


def _render_monthly_reality(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    income = view.income_support
    title = "MONTHLY REALITY" if user_role == "homebuyer" else "MONTHLY CARRY"

    # Extract economics
    from briarwood.dash_app.components import _economics_inputs
    metrics = _economics_inputs(report, view)

    cost = metrics.get("gross_monthly_cost")
    rent = metrics.get("monthly_rent")
    net = metrics.get("net_monthly_cost")

    cost_text = f"${cost:,.0f}/mo" if cost else "N/A"
    rent_text = f"${rent:,.0f}" if rent else "N/A"

    # Net position — color-coded
    if net is not None:
        net_sign = "+" if net <= 0 else "-"
        net_abs = abs(net)
        net_text = f"${net_abs:,.0f} net"
        net_positive = net <= 0  # cost < rent = good
    else:
        net_text = "N/A"
        net_positive = False

    net_color = ACCENT_GREEN if net_positive else ACCENT_RED

    return html.Div(
        [
            html.Div(title, style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
            html.Div(
                [
                    html.Span(
                        f"{cost_text} cost",
                        style={"fontSize": "16px", "fontWeight": "600", "fontFamily": FONT_MONO, "color": TEXT_PRIMARY},
                    ),
                    html.Span(" \u00b7 ", style={"color": TEXT_TERTIARY, "margin": "0 8px"}),
                    html.Span(
                        f"{rent_text} rent",
                        style={"fontSize": "16px", "fontWeight": "600", "fontFamily": FONT_MONO, "color": TEXT_PRIMARY},
                    ),
                    html.Span(" \u00b7 ", style={"color": TEXT_TERTIARY, "margin": "0 8px"}),
                    html.Span(
                        f"{'+' if net_positive else '-'}{net_text}",
                        style={"fontSize": "16px", "fontWeight": "700", "fontFamily": FONT_MONO, "color": net_color},
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "4px"},
            ),
        ],
        style=CARD_STYLE,
    )


# ── Action buttons ────────────────────────────────────────────────────────────


def _render_action_buttons() -> html.Div:
    button_style = {
        "flex": "1",
        "minWidth": "180px",
    }
    return html.Div(
        [
            html.Button(
                "See Price Support",
                id={"type": "simple-view-action", "screen": "price_support"},
                className="action-button",
                n_clicks=0,
                style=button_style,
            ),
            html.Button(
                "See Financials",
                id={"type": "simple-view-action", "screen": "financials"},
                className="action-button",
                n_clicks=0,
                style=button_style,
            ),
            html.Button(
                "See Scenarios",
                id={"type": "simple-view-action", "screen": "scenarios"},
                className="action-button",
                n_clicks=0,
                style=button_style,
            ),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 SCREENS (progressive disclosure — user clicked deeper)
# ═══════════════════════════════════════════════════════════════════════════════


def render_price_support(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Layer 2: How we got to the number + comp charts."""
    from briarwood.dash_app.components import (
        comp_positioning_dot_plot,
        forward_fan_chart,
        forward_waterfall_chart,
    )

    # Build value waterfall from comp analysis
    waterfall_rows = _build_value_waterfall(view, report)

    return html.Div(
        [
            _back_button(),
            html.Div(
                [
                    html.Div("HOW WE GOT TO THE NUMBER", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                    html.Div(waterfall_rows),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    html.Div("COMP POSITIONING", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                    comp_positioning_dot_plot(view, report),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    html.Div("FORWARD VALUE", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                    forward_fan_chart(report),
                ],
                style=CARD_STYLE,
            ),
        ],
        className="briarwood-fade-in",
        style={
            "display": "grid",
            "gap": "16px",
            "maxWidth": "720px",
            "margin": "0 auto",
            "padding": "24px 16px 48px",
        },
    )


def render_financials(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Layer 2: What it costs to own + income waterfall."""
    from briarwood.dash_app.components import _economics_inputs, income_carry_waterfall

    metrics = _economics_inputs(report, view)

    line_items = [
        ("Mortgage", metrics.get("principal_interest")),
        ("Taxes", metrics.get("taxes")),
        ("Insurance", metrics.get("insurance")),
        ("Maintenance", metrics.get("maintenance")),
        ("HOA", metrics.get("hoa")),
    ]
    total_cost = metrics.get("gross_monthly_cost")
    rent = metrics.get("monthly_rent")
    net = metrics.get("net_monthly_cost")

    rows: list[html.Div] = []
    for label, amount in line_items:
        if amount is None or amount == 0:
            continue
        rows.append(
            html.Div(
                [
                    html.Span(label, style={"fontSize": "14px", "color": TEXT_PRIMARY}),
                    html.Span(
                        f"${amount:,.0f}/mo",
                        style={"fontSize": "14px", "fontFamily": FONT_MONO, "fontWeight": "500", "color": TEXT_PRIMARY},
                    ),
                ],
                className="value-waterfall-row",
            )
        )

    # Total
    if total_cost is not None:
        rows.append(
            html.Div(
                [
                    html.Span("Total carry", style={"fontSize": "15px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                    html.Span(
                        f"${total_cost:,.0f}/mo",
                        style={"fontSize": "15px", "fontFamily": FONT_MONO, "fontWeight": "700", "color": TEXT_PRIMARY},
                    ),
                ],
                className="value-waterfall-row value-waterfall-total",
            )
        )

    # Rent and net
    if rent is not None:
        rows.append(
            html.Div(
                [
                    html.Span("Rental income", style={"fontSize": "14px", "color": ACCENT_GREEN}),
                    html.Span(
                        f"${rent:,.0f}/mo",
                        style={"fontSize": "14px", "fontFamily": FONT_MONO, "fontWeight": "500", "color": ACCENT_GREEN},
                    ),
                ],
                className="value-waterfall-row",
            )
        )

    if net is not None:
        net_color = ACCENT_GREEN if net <= 0 else ACCENT_RED
        sign = "+" if net <= 0 else "-"
        rows.append(
            html.Div(
                [
                    html.Span("Net position", style={"fontSize": "15px", "fontWeight": "700", "color": net_color}),
                    html.Span(
                        f"{sign}${abs(net):,.0f}/mo",
                        style={"fontSize": "15px", "fontFamily": FONT_MONO, "fontWeight": "700", "color": net_color},
                    ),
                ],
                className="value-waterfall-row value-waterfall-total",
            )
        )

    return html.Div(
        [
            _back_button(),
            html.Div(
                [
                    html.Div("WHAT IT COSTS TO OWN", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                    html.Div(rows),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    html.Div("INCOME WATERFALL", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                    income_carry_waterfall(report),
                ],
                style=CARD_STYLE,
            ),
        ],
        className="briarwood-fade-in",
        style={
            "display": "grid",
            "gap": "16px",
            "maxWidth": "720px",
            "margin": "0 auto",
            "padding": "24px 16px 48px",
        },
    )


def render_scenarios(view: PropertyAnalysisView, report: AnalysisReport) -> html.Div:
    """Layer 2: Three scenario cards + forward chart."""
    from briarwood.dash_app.components import forward_fan_chart, _economics_inputs

    metrics = _economics_inputs(report, view)
    rent = metrics.get("monthly_rent")
    cost = metrics.get("gross_monthly_cost")
    net = metrics.get("net_monthly_cost")

    scenario_cards = html.Div(
        [
            _scenario_card(
                "LIVE IN IT",
                [
                    ("Monthly cost", f"${cost:,.0f}" if cost else "N/A"),
                    ("5yr equity", f"${view.base_case:,.0f}" if view.base_case else "N/A"),
                    ("Upside", view.forward.upside_pct_text if view.forward else "N/A"),
                ],
            ),
            _scenario_card(
                "RENT IT OUT",
                [
                    ("Net monthly", f"${abs(net):,.0f}" if net else "N/A"),
                    ("Rental yield", view.income_support.gross_yield_text if view.income_support.gross_yield else "N/A"),
                    ("Rental ease", view.income_support.rental_ease_label),
                ],
            ),
            _scenario_card(
                "RENOVATE",
                [
                    ("CapEx lane", dejargon(view.capex_lane) if view.capex_lane else "N/A"),
                    ("Condition", view.condition_profile or "N/A"),
                    ("Upside potential", view.optionality_label or "N/A"),
                ],
            ),
        ],
        style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))", "gap": "12px"},
    )

    return html.Div(
        [
            _back_button(),
            scenario_cards,
            html.Div(
                [
                    html.Div("FORWARD OUTLOOK", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                    forward_fan_chart(report),
                ],
                style=CARD_STYLE,
            ),
        ],
        className="briarwood-fade-in",
        style={
            "display": "grid",
            "gap": "16px",
            "maxWidth": "720px",
            "margin": "0 auto",
            "padding": "24px 16px 48px",
        },
    )


def _scenario_card(title: str, metrics: list[tuple[str, str]]) -> html.Div:
    return html.Div(
        [
            html.Div(title, style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.12em", "marginBottom": "16px"}),
        ] + [
            html.Div(
                [
                    html.Div(label, style={"fontSize": "12px", "color": TEXT_TERTIARY}),
                    html.Div(value, style={"fontSize": "15px", "fontWeight": "600", "fontFamily": FONT_MONO, "color": TEXT_PRIMARY, "marginTop": "2px"}),
                ],
                style={"marginBottom": "12px"},
            )
            for label, value in metrics
        ],
        style=CARD_STYLE,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _back_button() -> html.Div:
    return html.Div(
        html.Button(
            "\u2190 Back to Summary",
            id={"type": "simple-view-action", "screen": "simple"},
            className="action-button",
            n_clicks=0,
            style={"padding": "8px 16px", "fontSize": "13px"},
        ),
    )


def _build_value_waterfall(view: PropertyAnalysisView, report: AnalysisReport) -> list[html.Div]:
    """Build a value bridge from comp analysis or value_bridge data."""
    rows: list[html.Div] = []

    # Try to get the value bridge from view model
    if view.value and view.value.value_bridge:
        for step in view.value.value_bridge:
            is_total = step.label.lower() in ("estimated value", "total", "briarwood value", "fair value")
            amount_text = step.value
            rows.append(
                html.Div(
                    [
                        html.Span(
                            step.label,
                            style={
                                "fontSize": "14px" if not is_total else "15px",
                                "fontWeight": "500" if not is_total else "700",
                                "color": TEXT_PRIMARY,
                            },
                        ),
                        html.Span(
                            amount_text,
                            style={
                                "fontSize": "14px" if not is_total else "16px",
                                "fontFamily": FONT_MONO,
                                "fontWeight": "500" if not is_total else "700",
                                "color": TEXT_PRIMARY,
                            },
                        ),
                    ],
                    className=f"value-waterfall-row{' value-waterfall-total' if is_total else ''}",
                )
            )
    else:
        # Fallback: show BCV with ask comparison
        if view.bcv is not None:
            rows.append(
                html.Div(
                    [
                        html.Span("Estimated fair value", style={"fontSize": "15px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                        html.Span(
                            f"${view.bcv:,.0f}",
                            style={"fontSize": "16px", "fontFamily": FONT_MONO, "fontWeight": "700", "color": TEXT_PRIMARY},
                        ),
                    ],
                    className="value-waterfall-row value-waterfall-total",
                )
            )
        if view.ask_price is not None and view.bcv is not None:
            gap = view.bcv - view.ask_price
            gap_color = ACCENT_GREEN if gap >= 0 else ACCENT_RED
            rows.append(
                html.Div(
                    [
                        html.Span("vs. asking price", style={"fontSize": "14px", "color": TEXT_SECONDARY}),
                        html.Span(
                            f"{'+'if gap >= 0 else ''}{gap/view.ask_price*100:.1f}%",
                            style={"fontSize": "14px", "fontFamily": FONT_MONO, "fontWeight": "600", "color": gap_color},
                        ),
                    ],
                    className="value-waterfall-row",
                )
            )

    if not rows:
        rows.append(
            html.Div("Value analysis not yet available.", style={"fontSize": "14px", "color": TEXT_SECONDARY, "padding": "12px 0"})
        )

    return rows

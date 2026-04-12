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
            "maxWidth": "860px",
            "margin": "0 auto",
            "padding": "24px 24px 48px",
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


def render_price_support(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Layer 2: How we got to the number + comp charts."""
    from briarwood.dash_app.components import (
        comp_positioning_dot_plot,
        forward_fan_chart,
    )

    waterfall_rows = _build_value_waterfall(view, report)

    # Narrative block — differs by role
    if user_role == "investor":
        narrative = _price_support_investor_narrative(view)
    else:
        narrative = _price_support_homebuyer_narrative(view)

    return html.Div(
        [
            _back_button(),
            html.Div(
                [
                    html.Div("HOW WE GOT TO THE NUMBER", style=_LAYER2_HEADER),
                    narrative,
                    html.Div(waterfall_rows, style={"marginTop": "16px"}),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    html.Div("COMP POSITIONING", style=_LAYER2_HEADER),
                    html.Div(
                        _comp_context_line(view),
                        style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "8px"},
                    ),
                    comp_positioning_dot_plot(view, report),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    html.Div("FORWARD VALUE", style=_LAYER2_HEADER),
                    html.Div(
                        _forward_context_line(view),
                        style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "8px"},
                    ),
                    forward_fan_chart(view, chart_height=320),
                ],
                style=CARD_STYLE,
            ),
        ],
        className="briarwood-fade-in",
        style=_LAYER2_GRID,
    )


def render_financials(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
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
        rows.append(_kv_row(label, f"${amount:,.0f}/mo"))

    if total_cost is not None:
        rows.append(_kv_row("Total carry", f"${total_cost:,.0f}/mo", bold=True))

    if rent is not None:
        rows.append(_kv_row("Rental income", f"${rent:,.0f}/mo", color=ACCENT_GREEN))

    if net is not None:
        net_color = ACCENT_GREEN if net <= 0 else ACCENT_RED
        sign = "+" if net <= 0 else "-"
        rows.append(_kv_row("Net position", f"{sign}${abs(net):,.0f}/mo", bold=True, color=net_color))

    # Investor metrics card
    investor_card = None
    if user_role == "investor":
        investor_card = _financials_investor_metrics(view)

    # Homebuyer context line
    if user_role == "homebuyer":
        context = _financials_homebuyer_context(total_cost, rent, net)
    else:
        context = html.Div(
            view.income_support.summary if view.income_support.summary else "Income and carry analysis based on current market rents.",
            style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "4px"},
        )

    return html.Div(
        [
            _back_button(),
            html.Div(
                [
                    html.Div("WHAT IT COSTS TO OWN", style=_LAYER2_HEADER),
                    context,
                    html.Div(rows, style={"marginTop": "12px"}),
                ],
                style=CARD_STYLE,
            ),
            investor_card,
            html.Div(
                [
                    html.Div("INCOME WATERFALL", style=_LAYER2_HEADER),
                    income_carry_waterfall(view, report),
                ],
                style=CARD_STYLE,
            ),
        ],
        className="briarwood-fade-in",
        style=_LAYER2_GRID,
    )


def render_scenarios(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Layer 2: Three scenario cards + forward chart."""
    from briarwood.dash_app.components import forward_fan_chart, _economics_inputs

    metrics = _economics_inputs(report, view)
    rent = metrics.get("monthly_rent")
    cost = metrics.get("gross_monthly_cost")
    net = metrics.get("net_monthly_cost")

    # Scenario cards — investor gets extra stats
    live_metrics = [
        ("Monthly cost", f"${cost:,.0f}" if cost else "N/A"),
        ("5yr equity", f"${view.base_case:,.0f}" if view.base_case else "N/A"),
        ("Upside", view.forward.upside_pct_text if view.forward else "N/A"),
    ]
    rent_metrics = [
        ("Net monthly", f"${abs(net):,.0f}" if net else "N/A"),
        ("Rental yield", view.income_support.gross_yield_text if view.income_support.gross_yield else "N/A"),
        ("Rental ease", view.income_support.rental_ease_label),
    ]
    reno_metrics = [
        ("Capital lane", dejargon(view.capex_lane) if view.capex_lane else "N/A"),
        ("Condition", view.condition_profile or "N/A"),
        ("Upside potential", view.optionality_label or "N/A"),
    ]

    if user_role == "investor":
        rent_metrics.extend([
            ("Debt coverage", view.income_support.dscr_text),
            ("Cash return", view.income_support.cash_on_cash_return_text),
            ("Price to rent", view.income_support.price_to_rent_text),
        ])
        if view.forward:
            live_metrics.append(("Downside", view.forward.downside_pct_text))

    scenario_cards = html.Div(
        [
            _scenario_card("LIVE IN IT", live_metrics),
            _scenario_card("RENT IT OUT", rent_metrics),
            _scenario_card("RENOVATE", reno_metrics),
        ],
        style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))", "gap": "12px"},
    )

    return html.Div(
        [
            _back_button(),
            scenario_cards,
            html.Div(
                [
                    html.Div("FORWARD OUTLOOK", style=_LAYER2_HEADER),
                    html.Div(
                        _forward_context_line(view),
                        style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "8px"},
                    ),
                    forward_fan_chart(view, chart_height=320),
                ],
                style=CARD_STYLE,
            ),
        ],
        className="briarwood-fade-in",
        style=_LAYER2_GRID,
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


# ── Shared Layer 2 styles and helpers ────────────────────────────────────────

_LAYER2_HEADER: dict = {**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}

_LAYER2_GRID: dict = {
    "display": "grid",
    "gap": "16px",
    "maxWidth": "860px",
    "margin": "0 auto",
    "padding": "24px 24px 48px",
}


def _kv_row(label: str, value: str, *, bold: bool = False, color: str | None = None) -> html.Div:
    c = color or TEXT_PRIMARY
    fw = "700" if bold else "500"
    fs = "15px" if bold else "14px"
    return html.Div(
        [
            html.Span(label, style={"fontSize": fs, "fontWeight": fw, "color": c}),
            html.Span(value, style={"fontSize": fs, "fontFamily": FONT_MONO, "fontWeight": fw, "color": c}),
        ],
        className=f"value-waterfall-row{' value-waterfall-total' if bold else ''}",
    )


def _stat_row(label: str, value: str) -> html.Div:
    """A compact stat row for investor metrics tables."""
    return html.Div(
        [
            html.Span(label, style={"fontSize": "13px", "color": TEXT_SECONDARY}),
            html.Span(value, style={"fontSize": "14px", "fontFamily": FONT_MONO, "fontWeight": "600", "color": TEXT_PRIMARY}),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "padding": "8px 0",
            "borderBottom": f"1px solid {BORDER}",
        },
    )


# ── Price Support narratives ─────────────────────────────────────────────────


def _price_support_homebuyer_narrative(view: PropertyAnalysisView) -> html.Div:
    """Plain English explanation of the valuation for homebuyers."""
    bcv = view.bcv
    ask = view.ask_price
    lines: list[str] = []

    if bcv is not None and ask is not None:
        diff_pct = (bcv - ask) / ask * 100
        if diff_pct > 5:
            lines.append(f"We estimate this property is worth about ${bcv:,.0f}, which is {abs(diff_pct):.0f}% above the asking price. That suggests room to negotiate or a solid entry point.")
        elif diff_pct < -5:
            lines.append(f"We estimate this property is worth about ${bcv:,.0f}, which is {abs(diff_pct):.0f}% below the asking price. You may want to negotiate down or wait for a price reduction.")
        else:
            lines.append(f"We estimate this property is worth about ${bcv:,.0f}, which is close to the asking price. The price looks fair at current market levels.")
    elif bcv is not None:
        lines.append(f"We estimate this property is worth about ${bcv:,.0f} based on comparable sales and market conditions.")

    lines.append("The table below shows how we built up to that number.")

    return html.Div(
        [html.Div(line, style={"fontSize": "14px", "lineHeight": "1.6", "color": TEXT_SECONDARY, "marginBottom": "6px"}) for line in lines],
    )


def _price_support_investor_narrative(view: PropertyAnalysisView) -> html.Div:
    """Statistical context for investors."""
    comps = view.comps
    value_vm = view.value

    stats: list[html.Div] = []
    stats.append(_stat_row("Comparable value", comps.comparable_value_text))
    stats.append(_stat_row("Comp count", comps.comp_count_text))
    stats.append(_stat_row("Confidence", comps.confidence_text))
    stats.append(_stat_row("Verification", comps.verification_summary))
    stats.append(_stat_row("Dataset", comps.dataset_name))

    if value_vm.confidence > 0:
        stats.append(_stat_row("Value confidence", f"{value_vm.confidence:.0%}"))
    if view.value_low is not None and view.value_high is not None:
        stats.append(_stat_row("Value range", f"${view.value_low:,.0f} – ${view.value_high:,.0f}"))

    return html.Div(stats, style={"marginTop": "8px"})


def _comp_context_line(view: PropertyAnalysisView) -> str:
    """One-liner about comp positioning."""
    comps = view.comps
    parts: list[str] = []
    if comps.comp_count_text and comps.comp_count_text != "0":
        parts.append(f"{comps.comp_count_text} sold comps")
    if comps.active_listing_count_text and comps.active_listing_count_text != "0":
        parts.append(f"{comps.active_listing_count_text} active listings")
    if parts:
        return f"Showing {' and '.join(parts)} by price vs. similarity."
    return "Comparable sales positioning relative to the subject property."


def _forward_context_line(view: PropertyAnalysisView) -> str:
    """One-liner about forward outlook."""
    if view.forward:
        return f"Bull case {view.forward.upside_pct_text} upside, bear case {view.forward.downside_pct_text} downside over 12 months."
    return "Projected value range based on market conditions and property characteristics."


# ── Financials helpers ───────────────────────────────────────────────────────


def _financials_homebuyer_context(
    total_cost: float | None,
    rent: float | None,
    net: float | None,
) -> html.Div:
    """Plain English summary for homebuyers."""
    lines: list[str] = []
    if total_cost is not None and rent is not None and net is not None:
        if net <= 0:
            lines.append(f"If you rent this property out, the rental income covers your monthly costs with ${abs(net):,.0f} left over each month.")
        else:
            lines.append(f"If you rent this property out, you'd still need to cover ${abs(net):,.0f}/mo out of pocket after rental income.")
    elif total_cost is not None:
        lines.append(f"Your estimated total monthly cost to own this property is ${total_cost:,.0f}.")

    lines.append("Here's how the costs break down.")

    return html.Div(
        [html.Div(line, style={"fontSize": "14px", "lineHeight": "1.6", "color": TEXT_SECONDARY, "marginBottom": "6px"}) for line in lines],
    )


def _financials_investor_metrics(view: PropertyAnalysisView) -> html.Div:
    """Investor-only card with return metrics."""
    inc = view.income_support
    stats: list[html.Div] = []
    stats.append(_stat_row("Gross yield", inc.gross_yield_text))
    stats.append(_stat_row("Cash return", inc.cash_on_cash_return_text))
    stats.append(_stat_row("Debt coverage (DSCR)", inc.dscr_text))
    stats.append(_stat_row("Price to rent", inc.price_to_rent_text))
    stats.append(_stat_row("Income coverage", inc.income_support_ratio_text))
    stats.append(_stat_row("Rental ease", inc.rental_ease_label))
    stats.append(_stat_row("Rent source", inc.rent_source_label or inc.rent_source_type))
    if inc.operating_cash_flow_text:
        stats.append(_stat_row("Operating cash flow", inc.operating_cash_flow_text))

    return html.Div(
        [
            html.Div("INVESTOR METRICS", style=_LAYER2_HEADER),
            html.Div(stats, style={"marginTop": "8px"}),
        ],
        style=CARD_STYLE,
    )


def _build_value_waterfall(view: PropertyAnalysisView, report: AnalysisReport) -> list[html.Div]:
    """Build a value bridge from comp analysis or value_bridge data."""
    rows: list[html.Div] = []

    # Try to get the value bridge from view model
    if view.value and view.value.value_bridge:
        for step in view.value.value_bridge:
            is_total = step.label.lower() in ("estimated value", "total", "briarwood value", "fair value")
            amount_text = step.value_text
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

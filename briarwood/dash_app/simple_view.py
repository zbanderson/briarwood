"""Property View — visual-first, decision-first single-page layout.

Five questions, in order.  Each gets its own visual section:
  1. "Should I buy this?"     — Verdict gauge (above the fold)
  2. "What could go wrong?"   — Risk heat strip (above the fold)
  3. "Where is the value?"    — Value opportunity chart (below the fold)
  4. "What does this become?" — Scenario fan chart (below the fold)
  5. "Does this fit?"         — Strategy radar (collapsed by default)

Evidence, tables, and detailed breakdowns live behind expand/collapse.
Every metric is a visual element — no raw tables in the default view.
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
from briarwood.dash_app.viz import (
    metric_spark,
    quick_metric_gauge,
    risk_heat_strip,
    scenario_fan_chart,
    strategy_radar_chart,
    value_opportunity_chart,
    verdict_gauge,
)
from briarwood.schemas import AnalysisReport


# ── Section boundary enforcement ─────────────────────────────────────────────


class SectionBoundaryError(RuntimeError):
    """Raised when a section renderer accesses a field outside its allowlist."""


# Each key maps a section name → the set of top-level attribute paths that
# section is permitted to read from a PropertyAnalysisView (or sub-model).
# Paths use dot notation relative to PropertyAnalysisView.property_decision_view.
#
# The five question-based sections:
#   verdict     — "Should I buy this?"
#   risk        — "What could go wrong?"
#   value       — "Where is the value?"
#   projection  — "What does this become?"
#   fit         — "Does this fit my strategy?"
SECTION_FIELD_ALLOWLIST: dict[str, frozenset[str]] = {
    # Section 1: Verdict — synthesises decision + price gap + carry + confidence
    "verdict": frozenset({
        "recommendation", "conviction", "confidence",
        "primary_reason", "secondary_reason", "required_beliefs",
        "risk_bar",       # for confidence score extraction
    }),
    # Legacy alias
    "decision": frozenset({
        "recommendation", "conviction", "confidence",
        "primary_reason", "secondary_reason", "required_beliefs",
    }),
    # Section 2: Risk — risk bar items only
    "risk": frozenset({
        "risk",           # RiskQuestionViewModel (metrics, risk_bar, summary, top_risks)
        "risk_bar",       # on QuickDecisionViewModel
    }),
    # Section 3: Value — value drivers and opportunity signals
    "value": frozenset({
        "value",          # ValueQuestionViewModel (metrics, value_finder, hybrid_value)
    }),
    # Section 4: Projection — forward scenarios + deal curve
    "projection": frozenset({
        "financials",     # FinancialsQuestionViewModel (forward, scenarios)
        "deal_curve",
        "deal_curve_thresholds",
    }),
    # Section 5: Fit — positioning, report card, buyer fit
    "fit": frozenset({
        "positioning_summary",
        "report_card",
        "category_scores",
    }),
    # ── Legacy section boundaries (kept for backward compat) ────────────
    "price_support": frozenset({
        "price_support",  # PriceSupportQuestionViewModel
    }),
    "financials": frozenset({
        "financials",     # FinancialsQuestionViewModel (metrics, income_support, forward)
        "income_support", # top-level convenience alias on PropertyAnalysisView
    }),
    "quick_reality": frozenset({
        "price_support",
        "financials",
    }),
    "deal_curve": frozenset({
        "deal_curve",
        "deal_curve_thresholds",
    }),
}


class SectionDataProxy:
    """Thin wrapper that restricts attribute access to the section's allowlist.

    Wraps either a PropertyAnalysisView.property_decision_view (for view-
    backed sections) or a QuickDecisionViewModel (for the decision section).
    Any attribute access outside the declared allowlist raises
    ``SectionBoundaryError`` so cross-contamination is caught at render time.
    """

    __slots__ = ("_wrapped", "_allowed", "_section")

    def __init__(self, wrapped: object, section: str) -> None:
        allowed = SECTION_FIELD_ALLOWLIST.get(section)
        if allowed is None:
            raise ValueError(f"Unknown section {section!r}; valid: {sorted(SECTION_FIELD_ALLOWLIST)}")
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "_allowed", allowed)
        object.__setattr__(self, "_section", section)

    def __getattr__(self, name: str) -> object:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        if name not in self._allowed:
            raise SectionBoundaryError(
                f"Section '{self._section}' attempted to access '{name}' — "
                f"allowed fields: {sorted(self._allowed)}"
            )
        return getattr(self._wrapped, name)


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


# ── Tab bar styles ───────────────────────────────────────────────────────────

_PROPERTY_TAB_BAR_STYLE: dict = {
    "display": "flex",
    "justifyContent": "flex-end",
    "marginBottom": "16px",
    "padding": "0 4px",
}


def _tab_button_style(active: bool) -> dict:
    return {
        "padding": "12px 20px",
        "fontSize": "13px",
        "fontWeight": "600",
        "color": TEXT_PRIMARY if active else TEXT_SECONDARY,
        "borderBottom": f"2px solid {ACCENT_BLUE}" if active else "2px solid transparent",
        "backgroundColor": "transparent",
        "border-top": "none",
        "border-left": "none",
        "border-right": "none",
        "cursor": "pointer",
        "transition": "color 0.15s, border-color 0.15s",
        "whiteSpace": "nowrap",
    }


# ── Public section renderers (validated) ─────────────────────────────────────
#
# Each renderer enforces its section boundary via SectionDataProxy.  The proxy
# gates attribute access so that, e.g., the risk renderer cannot accidentally
# read price_support or financials fields.  Any cross-contamination is caught
# at render time with a clear SectionBoundaryError.


def render_verdict_section(
    view: PropertyAnalysisView,
    vm: QuickDecisionViewModel,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Section 1: 'Should I buy this?' — visual verdict gauge with 4 metric sparks."""
    proxy = SectionDataProxy(vm, "verdict")

    # Extract the four supporting metrics from view model
    price_support = view.property_decision_view.price_support
    financials = view.property_decision_view.financials

    fv_gap_pct = view.mispricing_pct
    monthly_carry = financials.metrics.net_monthly
    # Stabilized CF: use operating cash flow if available, else net monthly
    stabilized_cf = None
    if financials.income_support and financials.income_support.operating_cash_flow_text:
        try:
            stabilized_cf = float(financials.income_support.operating_cash_flow_text.replace("$", "").replace(",", "").replace("/mo", "").strip())
        except (ValueError, AttributeError):
            pass
    if stabilized_cf is None:
        stabilized_cf = monthly_carry

    question = "Should I buy this?" if user_role == "homebuyer" else "Does this pencil?"

    return verdict_gauge(
        proxy.recommendation,
        proxy.conviction,
        fv_gap_pct=fv_gap_pct,
        monthly_carry=monthly_carry,
        stabilized_cf=stabilized_cf,
        confidence=view.overall_confidence,
        question=question,
        primary_reason=proxy.primary_reason,
        secondary_reason=proxy.secondary_reason,
        required_beliefs=list(proxy.required_beliefs) if proxy.required_beliefs else None,
    )


def render_risk_section(
    view: PropertyAnalysisView,
    vm: QuickDecisionViewModel,
) -> html.Div:
    """Section 2: 'What could go wrong?' — risk heat strip."""
    pdv_proxy = SectionDataProxy(view.property_decision_view, "risk")
    vm_proxy = SectionDataProxy(vm, "risk")
    risk_qvm = pdv_proxy.risk
    risk_bar = vm_proxy.risk_bar
    return risk_heat_strip(risk_bar, top_risks=list(risk_qvm.top_risks) if risk_qvm.top_risks else None)


def render_value_section(view: PropertyAnalysisView) -> html.Div:
    """Section 3: 'Where is the value?' — value opportunity chart."""
    proxy = SectionDataProxy(view.property_decision_view, "value")
    value_qvm = proxy.value
    value_metrics = value_qvm.metrics
    value_finder = value_qvm.value_finder

    # Build driver list from value_drivers and metrics
    drivers: list[dict] = []
    if value_metrics.adu_income is not None and value_metrics.adu_income > 0:
        drivers.append({"label": "ADU / Rental Income", "impact": value_metrics.adu_income * 12})
    if value_metrics.mispricing_pct is not None and abs(value_metrics.mispricing_pct) > 0.01:
        # Express mispricing as dollar amount using ask price
        ask = view.ask_price or 0
        drivers.append({"label": "Price Dislocation", "impact": value_metrics.mispricing_pct * ask})
    if value_metrics.expansion_score is not None and value_metrics.expansion_score > 0:
        drivers.append({"label": "Expansion Upside", "impact": value_metrics.expansion_score * 100_000})
    if value_metrics.market_tailwind is not None and value_metrics.market_tailwind > 50:
        drivers.append({"label": "Market Tailwind", "impact": value_metrics.market_tailwind * 500})

    bullets = list(value_finder.bullets[:4]) if value_finder and value_finder.bullets else []
    signal = value_finder.supporting_signal if value_finder else ""

    return value_opportunity_chart(drivers, bullets=bullets, supporting_signal=signal)


def render_projection_section(
    view: PropertyAnalysisView,
    report: AnalysisReport,
) -> html.Div:
    """Section 4: 'What does this become?' — scenario fan chart."""
    financials = view.property_decision_view.financials
    forward = financials.forward
    ask = view.ask_price or 0

    return scenario_fan_chart(
        ask,
        base_value=financials.base_case,
        bull_value=financials.bull_case,
        bear_value=financials.bear_case,
        stress_value=financials.stress_case,
        upside_pct=forward.upside_pct_text if forward else "",
        downside_pct=forward.downside_pct_text if forward else "",
    )


def render_fit_section(view: PropertyAnalysisView) -> html.Div:
    """Section 5: 'Does this fit my strategy?' — radar chart."""
    rc = view.report_card
    factor_scores = rc.factor_scores if rc else {}

    # Capital required = down payment
    capital = None
    if view.ask_price and view.compare_metrics.get("down_payment_percent"):
        capital = view.ask_price * view.compare_metrics["down_payment_percent"]
    elif view.ask_price:
        capital = view.ask_price * 0.20  # default 20%

    # Complexity from capex lane
    complexity = "Low"
    if view.capex_lane and "heavy" in view.capex_lane.lower():
        complexity = "High"
    elif view.capex_lane and ("moderate" in view.capex_lane.lower() or "medium" in view.capex_lane.lower()):
        complexity = "Medium"

    return strategy_radar_chart(
        factor_scores,
        capital_required=capital,
        complexity=complexity,
        positive_factors=list(rc.positive[:3]) if rc else None,
        negative_factors=list(rc.negative[:3]) if rc else None,
    )


def render_town_pulse_compact(view: PropertyAnalysisView) -> html.Div | None:
    """Compact Town Pulse block — surfaces market signals between Risk and Value.

    Returns None when no town pulse data is available.
    """
    rl = view.risk_location
    if rl is None:
        return None
    pulse = rl.town_pulse
    if pulse is None or not pulse.key_signals:
        return None

    # Build compact signal pills grouped by tone
    signal_pills: list[html.Div] = []
    _TONE_COLORS = {"bullish": ACCENT_GREEN, "bearish": ACCENT_RED, "watch": ACCENT_AMBER}
    _TONE_BG = {
        "bullish": "rgba(34, 197, 94, 0.10)",
        "bearish": "rgba(239, 68, 68, 0.10)",
        "watch": "rgba(245, 158, 11, 0.10)",
    }

    for signal in pulse.key_signals[:4]:
        tone = getattr(signal, "tone", "watch")
        color = _TONE_COLORS.get(tone, ACCENT_AMBER)
        bg = _TONE_BG.get(tone, "rgba(245, 158, 11, 0.10)")
        title = getattr(signal, "title", "")
        confidence_tag = getattr(signal, "confidence_tag", "")

        signal_pills.append(html.Div(
            [
                html.Div(
                    [
                        html.Span(
                            tone.upper(),
                            style={
                                "fontSize": "9px", "fontWeight": "700", "color": color,
                                "letterSpacing": "0.08em",
                            },
                        ),
                        html.Span(
                            confidence_tag,
                            style={"fontSize": "9px", "color": TEXT_TERTIARY, "marginLeft": "6px"},
                        ) if confidence_tag else None,
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": "3px"},
                ),
                html.Div(title, style={
                    "fontSize": "12px", "fontWeight": "500", "color": TEXT_PRIMARY,
                    "lineHeight": "1.4",
                }),
            ],
            style={
                "padding": "8px 12px", "borderRadius": RADIUS_MD,
                "backgroundColor": bg, "border": f"1px solid {color}20",
            },
        ))

    # Location context sparks
    sparks: list[html.Div] = []
    sparks.append(metric_spark(
        "Town Score", f"{rl.town_score:.0f}/100",
        rl.town_score / 100,
        subtitle=rl.town_label.replace("_", " ").title() if rl.town_label else "",
    ))
    sparks.append(metric_spark(
        "Momentum", f"{rl.market_momentum_score:.0f}/100",
        rl.market_momentum_score / 100,
        subtitle=rl.momentum_direction or rl.market_momentum_label,
    ))
    sparks.append(metric_spark(
        "Scarcity", f"{rl.scarcity_score:.0f}/100",
        rl.scarcity_score / 100,
    ))
    sparks.append(metric_spark(
        "Liquidity", f"{rl.liquidity_score:.0f}/100",
        rl.liquidity_score / 100,
        subtitle=rl.liquidity_label,
    ))

    return html.Div(
        [
            html.Div(
                [html.Span("TOWN PULSE", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
                 html.Span("What's changing in this market?", style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginLeft": "12px"})],
                style={"marginBottom": "12px"},
            ),
            # Narrative summary
            html.Div(pulse.narrative_summary, style={
                "fontSize": "13px", "lineHeight": "1.55", "color": TEXT_SECONDARY,
                "marginBottom": "14px",
            }) if pulse.narrative_summary else None,
            # Signal pills grid
            html.Div(
                signal_pills,
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))",
                    "gap": "8px",
                    "marginBottom": "16px",
                },
            ),
            # Location metrics sparks
            html.Div(
                sparks,
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(110px, 1fr))",
                    "gap": "20px",
                    "borderTop": f"1px solid {BORDER}",
                    "paddingTop": "14px",
                },
            ),
        ],
        style=CARD_STYLE,
    )


# ── Legacy public section renderers (delegate to new visual sections) ───────


def render_decision_section(
    vm: QuickDecisionViewModel,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Legacy decision section — kept for backward compat."""
    proxy = SectionDataProxy(vm, "decision")
    return _render_decision_hero(proxy, user_role=user_role)


def render_price_support_section(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Price support section — consumes price_support sub-model only."""
    proxy = SectionDataProxy(view.property_decision_view, "price_support")
    return _render_price_support_section_validated(proxy, view, report, user_role=user_role)


def render_financial_section(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Financials section — consumes financials sub-model only."""
    proxy = SectionDataProxy(view.property_decision_view, "financials")
    return _render_financials_section_validated(proxy, view, report, user_role=user_role)


def render_quick_reality_section(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Quick reality strip — declared composite of price_support + financials."""
    proxy = SectionDataProxy(view.property_decision_view, "quick_reality")
    return _render_quick_reality_strip_validated(proxy, view, report, user_role=user_role)


# ── Validated render internals ───────────────────────────────────────────────
#
# These thin wrappers extract sub-models through the proxy (validating
# access), then delegate to the existing render functions with the real data.


def _render_risk_check_validated(pdv_proxy: SectionDataProxy, vm_proxy: SectionDataProxy) -> html.Div:
    risk = pdv_proxy.risk      # validates "risk" is allowed
    risk_bar = vm_proxy.risk_bar  # validates "risk_bar" is allowed
    # Build a minimal namespace the existing renderer expects
    class _RiskView:
        __slots__ = ("property_decision_view",)
        def __init__(self, risk_qvm):
            self.property_decision_view = type("_", (), {"risk": risk_qvm})()
    class _RiskVM:
        __slots__ = ("risk_bar",)
        def __init__(self, rb):
            self.risk_bar = rb
    return _render_risk_check(_RiskView(risk), _RiskVM(risk_bar))


def _render_value_card_validated(proxy: SectionDataProxy) -> html.Div:
    value = proxy.value  # validates "value" is allowed
    class _ValueView:
        __slots__ = ("property_decision_view",)
        def __init__(self, value_qvm):
            self.property_decision_view = type("_", (), {"value": value_qvm})()
    return _render_value_card(_ValueView(value))


def _render_price_support_section_validated(
    proxy: SectionDataProxy,
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    _ = proxy.price_support  # validates access
    return _render_price_support_section(view, report, user_role=user_role)


def _render_financials_section_validated(
    proxy: SectionDataProxy,
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    _ = proxy.financials  # validates access
    return _render_financials_section(view, report, user_role=user_role)


def _render_quick_reality_strip_validated(
    proxy: SectionDataProxy,
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    _ = proxy.price_support  # validates access — would raise if not in allowlist
    _ = proxy.financials     # validates access — would raise if not in allowlist
    # The real view is passed through because _economics_inputs needs
    # view.income_support (a financials-adjacent read).  The proxy above
    # proves that this section only *declares* price_support + financials.
    return _render_quick_reality_strip(view, report, user_role=user_role)


# ── Public entry point ────────────────────────────────────────────────────────


def render_property_view(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    active_tab: str = "summary",
    user_role: str = "homebuyer",
) -> html.Div:
    """Visual-first property analysis — five questions, five visual sections.

    Visual hierarchy:
      Above the fold:  1. Verdict gauge  |  2. Risk heat strip
      Below the fold:  3. Value opportunity  |  4. Scenario fan chart
      Collapsed:       5. Strategy fit  |  Deal Curve  |  Evidence

    Every metric is a visual element.  No raw tables in the default view.
    Tables are evidence — they live behind expand/collapse.
    """
    del active_tab  # single-page now
    quick_vm = build_quick_decision_view(report)

    # ── Build optional sections ───────────────────────────────────────
    town_pulse_block = render_town_pulse_compact(view)

    # ── Above the fold ──────────────────────────────────────────────
    above_fold = [
        render_verdict_section(view, quick_vm, report, user_role=user_role),
        render_risk_section(view, quick_vm),
    ]

    # ── Below the fold (visible, secondary) ─────────────────────────
    below_fold: list[html.Div] = []
    if town_pulse_block is not None:
        below_fold.append(town_pulse_block)
    below_fold.extend([
        render_value_section(view),
        render_projection_section(view, report),
    ])

    # ── Collapsed by default ────────────────────────────────────────
    collapsed = [
        _render_collapsed_section(
            "Strategy Fit",
            "Does this fit my strategy?",
            render_fit_section(view),
        ),
        _render_deal_curve_collapsed(view),
        _render_collapsed_section(
            "Price & Financials Detail",
            "Comp positioning, cost breakdown, and investor metrics.",
            html.Div([
                render_price_support_section(view, report, user_role=user_role),
                render_financial_section(view, report, user_role=user_role),
            ], style={"display": "grid", "gap": "12px"}),
        ),
        _render_collapsed_section(
            "Scenarios",
            "Stress-test renovation, knockdown, and forward cases.",
            _render_scenarios_content(view, report),
        ),
        _render_collapsed_section(
            "Evidence",
            "Comp tables, diagnostics, assumptions, and evidence quality.",
            _render_evidence_content(view, report),
        ),
    ]

    # ── Fold separator ──────────────────────────────────────────────
    fold_divider = html.Div(style={
        "height": "1px",
        "backgroundColor": BORDER,
        "margin": "8px 0",
    })

    return html.Div(
        [
            _render_mode_toggle(user_role),
            _render_property_header(view),
            html.Div(
                [
                    # Above the fold
                    html.Div(above_fold, style={"display": "grid", "gap": "16px"}),
                    fold_divider,
                    # Below the fold
                    html.Div(below_fold, style={"display": "grid", "gap": "16px"}),
                    fold_divider,
                    # Collapsed
                    html.Div(collapsed, style={"display": "grid", "gap": "12px"}),
                ],
                className="briarwood-fade-in",
                style={"display": "grid", "gap": "12px", "padding": "0 4px"},
            ),
        ],
        style={
            "maxWidth": "900px",
            "margin": "0 auto",
            "padding": "20px 24px 48px",
        },
    )


# Keep backward compat alias
def render_simple_view(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    return render_property_view(view, report, user_role=user_role)


# ── Top controls ─────────────────────────────────────────────────────────────


def _render_mode_toggle(user_role: str) -> html.Div:
    detail_toggle = html.Div(
        [
            html.Button(
                "Retail",
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
        style={"display": "flex", "marginLeft": "auto"},
    )

    return html.Div([detail_toggle], style=_PROPERTY_TAB_BAR_STYLE)


# ── Collapsed section wrapper ─────────────────────────────────────────────────


def _render_collapsed_section(title: str, subtitle: str, content: html.Div) -> html.Details:
    """Expand/collapse wrapper — content is NOT visible on page load."""
    return html.Details(
        [
            html.Summary(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(title.upper(), style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em", "marginBottom": "0"}),
                                html.Div(subtitle, style={"fontSize": "13px", "color": TEXT_SECONDARY}),
                            ],
                            style={"display": "grid", "gap": "4px"},
                        ),
                        html.Span(
                            "Expand",
                            style={
                                "fontSize": "11px",
                                "fontWeight": "600",
                                "color": ACCENT_BLUE,
                                "padding": "4px 10px",
                                "borderRadius": RADIUS_MD,
                                "border": f"1px solid {BORDER}",
                                "backgroundColor": BG_SURFACE,
                            },
                        ),
                    ],
                    style={"display": "flex", "justifyContent": "space-between", "gap": "12px", "alignItems": "center"},
                ),
                style={"cursor": "pointer", "listStyle": "none", "padding": "16px 20px"},
            ),
            html.Div(content, style={"padding": "0 20px 20px"}),
        ],
        open=False,
        style={**CARD_STYLE, "padding": "0"},
    )


def _render_deal_curve_collapsed(view: PropertyAnalysisView) -> html.Div:
    """Deal Curve as a collapsed section — returns empty div if no data."""
    content = render_deal_curve_summary(view)
    if content is None:
        return html.Div()
    return _render_collapsed_section(
        "Deal Curve",
        "How the verdict shifts at lower entry prices.",
        content,
    )


# ── Below-fold inline sections ───────────────────────────────────────────────


def _render_price_support_section(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Price Support — visible below the fold, not collapsed."""
    from briarwood.dash_app.components import (
        build_comp_positioning_chart_data,
        render_comp_positioning_chart,
    )

    waterfall_rows = _build_value_waterfall(view, report)
    comp_chart = render_comp_positioning_chart(build_comp_positioning_chart_data(view, report))

    if user_role == "investor":
        narrative = _price_support_investor_narrative(view)
    else:
        narrative = _price_support_homebuyer_narrative(view)

    return html.Div(
        [
            _render_price_support_summary(view),
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
                        "Direct comp pricing first: where adjusted same-market support sits, where actives sit, and where Briarwood's fair value lands.",
                        style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "10px"},
                    ),
                    comp_chart,
                ],
                style=CARD_STYLE,
            ),
            _render_comp_support_card(view),
        ],
        style={"display": "grid", "gap": "12px"},
    )


def _render_financials_section(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Financials — visible below the fold, not collapsed."""
    from briarwood.dash_app.components import (
        _economics_inputs,
        build_financial_chart_data,
        render_financial_chart,
    )

    metrics = _economics_inputs(report, view)
    financial_chart = render_financial_chart(build_financial_chart_data(view, report))
    cost = metrics.get("gross_monthly_cost")
    rent = metrics.get("monthly_rent")
    net = metrics.get("net_monthly_cost")

    # Cost breakdown rows
    line_items = [
        ("Mortgage", metrics.get("principal_interest")),
        ("Taxes", metrics.get("taxes")),
        ("Insurance", metrics.get("insurance")),
        ("Maintenance", metrics.get("maintenance")),
        ("HOA", metrics.get("hoa")),
    ]
    rows: list[html.Div] = []
    for label, amount in line_items:
        if amount is None or amount == 0:
            continue
        rows.append(_kv_row(label, f"${amount:,.0f}/mo"))
    if cost is not None:
        rows.append(_kv_row("Total carry", f"${cost:,.0f}/mo", bold=True))
    if rent is not None:
        rows.append(_kv_row("Rental income", f"${rent:,.0f}/mo", color=ACCENT_GREEN))
    if net is not None:
        net_color = ACCENT_GREEN if net <= 0 else ACCENT_RED
        sign = "+" if net <= 0 else "-"
        rows.append(_kv_row("Net position", f"{sign}${abs(net):,.0f}/mo", bold=True, color=net_color))

    # Context line
    if user_role == "homebuyer":
        context = _financials_homebuyer_context(cost, rent, net)
    else:
        context = html.Div(
            view.income_support.summary if view.income_support.summary else "Income and carry analysis based on current market rents.",
            style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "4px"},
        )

    # Investor metrics
    investor_card = _financials_investor_metrics(view) if user_role == "investor" else None

    return html.Div(
        [
            html.Div(
                [
                    html.Div("WHAT IT COSTS TO OWN", style=_LAYER2_HEADER),
                    context,
                    html.Div(rows, style={"marginTop": "12px"}),
                ],
                style=CARD_STYLE,
            ),
            html.Div(
                [
                    html.Div("FINANCIAL REALITY", style=_LAYER2_HEADER),
                    html.Div(
                        "A simple ownership read: monthly cost, monthly rent offset, and the resulting monthly position.",
                        style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "10px"},
                    ),
                    financial_chart,
                ],
                style=CARD_STYLE,
            ),
            _render_financial_support_card(view, metrics),
            investor_card,
        ],
        style={"display": "grid", "gap": "12px"},
    )


def _render_scenarios_content(
    view: PropertyAnalysisView,
    report: AnalysisReport,
) -> html.Div:
    """Scenarios content — rendered inside a collapsed section."""
    del view
    from briarwood.dash_app.scenarios import render_scenarios_section

    return html.Div(
        [render_scenarios_section(report)],
        style={"display": "grid", "gap": "12px"},
    )


def _render_evidence_content(
    view: PropertyAnalysisView,
    report: AnalysisReport,
) -> html.Div:
    """Evidence content — rendered inside a collapsed section."""
    from briarwood.dash_app.components import render_tear_sheet_body

    return html.Div(
        [render_tear_sheet_body(view, report)],
        style={"display": "grid", "gap": "12px"},
    )


def _render_price_support_summary(view: PropertyAnalysisView) -> html.Div:
    price = view.property_decision_view.price_support
    gap_text = "N/A"
    gap_color = TEXT_PRIMARY
    if price.ask_price is not None and price.fair_value is not None and price.ask_price:
        gap = price.fair_value - price.ask_price
        gap_pct = (gap / price.ask_price) * 100
        gap_text = f"{'+' if gap >= 0 else '-'}${abs(gap):,.0f} ({'+' if gap_pct >= 0 else '-'}{abs(gap_pct):.1f}%)"
        gap_color = ACCENT_GREEN if gap >= 0 else ACCENT_RED

    return html.Div(
        [
            html.Div("PRICE SUPPORT", style=_LAYER2_HEADER),
            html.Div(
                [
                    _quick_fact("Fair Value", f"${price.fair_value:,.0f}" if price.fair_value is not None else "N/A", f"Ask {f'${price.ask_price:,.0f}' if price.ask_price is not None else 'N/A'}"),
                    _quick_fact("Gap vs Ask", gap_text, price.pricing_view.replace("_", " ").title() if price.pricing_view else "", value_color=gap_color),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))", "gap": "12px"},
            ),
        ],
        style=CARD_STYLE,
    )


def _render_comp_support_card(view: PropertyAnalysisView) -> html.Div:
    comps = view.property_decision_view.price_support.comps
    rows = [
        _stat_row("Comparable value", comps.comparable_value_text),
        _stat_row("Comp count", comps.comp_count_text),
        _stat_row("Comp confidence", comps.confidence_text),
        _stat_row("Verification", comps.verification_summary),
    ]
    if comps.active_listing_count_text not in {"", "0"}:
        rows.append(_stat_row("Active listings", comps.active_listing_count_text))
    return html.Div(
        [
            html.Div("COMP SUPPORT", style=_LAYER2_HEADER),
            html.Div(
                _comp_context_line(view),
                style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ),
            html.Div(rows),
        ],
        style=CARD_STYLE,
    )


def _render_scenario_cards(
    view: PropertyAnalysisView,
    metrics: dict,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    """Three scenario cards for the Financials tab."""
    cost = metrics.get("gross_monthly_cost")
    net = metrics.get("net_monthly_cost")

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

    return html.Div(
        [
            _scenario_card("LIVE IN IT", live_metrics),
            _scenario_card("RENT IT OUT", rent_metrics),
            _scenario_card("RENOVATE", reno_metrics),
        ],
        style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(240px, 1fr))", "gap": "12px"},
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

    # Town from the address for market link
    town = view.town_context.get("town_name") or (view.address.split(",")[1].strip() if "," in view.address else "")

    return html.Div(
        [
            html.Button(
                f"\u2190 Markets{(' \u00b7 ' + town) if town else ''}",
                id={"type": "shell-nav-button", "tab": "opportunities"},
                n_clicks=0,
                style={
                    "fontSize": "12px",
                    "color": ACCENT_BLUE,
                    "backgroundColor": "transparent",
                    "border": "none",
                    "cursor": "pointer",
                    "padding": "0",
                    "marginBottom": "8px",
                },
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                view.address,
                                style={"fontSize": "22px", "fontWeight": "700", "color": TEXT_PRIMARY, "lineHeight": "1.3"},
                            ),
                            html.Div(
                                spec_line,
                                style={"fontSize": "14px", "color": TEXT_SECONDARY, "marginTop": "4px"},
                            ) if spec_line else None,
                        ],
                    ),
                    html.Div(
                        ask_text,
                        style={"fontSize": "18px", "fontWeight": "700", "fontFamily": FONT_MONO, "color": TEXT_PRIMARY},
                    ) if ask_text else None,
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "gap": "16px"},
            ),
        ],
        style={**CARD_STYLE, "padding": "20px 28px"},
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
                                "Conviction",
                                style={"fontSize": "12px", "fontWeight": "600", "color": TEXT_SECONDARY, "textTransform": "uppercase", "letterSpacing": "0.08em"},
                            ),
                            html.Div(
                                f"{int(round(vm.conviction * 100))}%",
                                style={"fontSize": "28px", "fontWeight": "800", "color": accent, "marginTop": "2px"},
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
                    html.Div(
                        vm.secondary_reason,
                        style={"fontSize": "14px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginTop": "8px"},
                    ) if vm.secondary_reason else None,
                    html.Div(
                        [
                            html.Div("What must be true", style={**LABEL_STYLE, "marginTop": "16px", "marginBottom": "6px"}),
                            html.Ul(
                                [html.Li(item, style={"fontSize": "13px", "lineHeight": "1.5", "color": TEXT_SECONDARY}) for item in vm.required_beliefs[:3]],
                                style={"margin": "0", "paddingLeft": "18px"},
                            ),
                        ]
                    ) if vm.required_beliefs else None,
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
    risk_metrics = view.property_decision_view.risk.metrics
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
            html.Div("RISK BAR", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
            html.Div(
                f"Price gap {risk_metrics.price_gap_pct:.1%} • Liquidity {risk_metrics.liquidity_score:.0f}/100 • Execution {risk_metrics.execution_risk}"
                if risk_metrics.price_gap_pct is not None and risk_metrics.liquidity_score is not None
                else f"Execution {risk_metrics.execution_risk} • Confidence {risk_metrics.confidence:.0%}",
                style={"fontSize": "12px", "color": TEXT_SECONDARY, "marginBottom": "8px"},
            ),
            html.Div(risk_rows),
        ],
        style=CARD_STYLE,
    )


# ── Card 4: Where's the Value ────────────────────────────────────────────────


def _render_value_card(view: PropertyAnalysisView) -> html.Div:
    bullets: list[str] = []
    value_vm = view.property_decision_view.value.value_finder
    value_metrics = view.property_decision_view.value.metrics
    if value_vm is not None and value_vm.bullets:
        bullets = list(value_vm.bullets[:4])

    # Final fallback
    if not bullets:
        bullets = ["No clear value edge is supported yet."]

    return html.Div(
        [
            html.Div("WHERE'S THE VALUE", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
            html.Div(
                " | ".join(
                    part
                    for part in [
                        f"ADU income {_fmt_money_inline(value_metrics.adu_income)}" if value_metrics.adu_income is not None else "",
                        f"Expansion {value_metrics.expansion_score:.2f}" if value_metrics.expansion_score is not None else "",
                        f"Tailwind {value_metrics.market_tailwind:.0f}/100" if value_metrics.market_tailwind is not None else "",
                    ]
                    if part
                ),
                style={"fontSize": "12px", "color": TEXT_SECONDARY, "marginBottom": "8px"},
            ) if any(v is not None for v in [value_metrics.adu_income, value_metrics.expansion_score, value_metrics.market_tailwind]) else None,
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


# ── Quick Reality Strip ──────────────────────────────────────────────────────


def _render_quick_reality_strip(
    view: PropertyAnalysisView,
    report: AnalysisReport,
    *,
    user_role: str = "homebuyer",
) -> html.Div:
    from briarwood.dash_app.components import _economics_inputs
    metrics = _economics_inputs(report, view)

    cost = metrics.get("gross_monthly_cost")
    rent = metrics.get("monthly_rent")
    net = metrics.get("net_monthly_cost")
    del user_role

    price = view.property_decision_view.price_support
    financials = view.property_decision_view.financials.metrics
    fair_value = f"${price.fair_value:,.0f}" if price.fair_value is not None else "N/A"
    ask = f"${price.ask_price:,.0f}" if price.ask_price is not None else "N/A"
    monthly_reality = "N/A"
    monthly_color = TEXT_PRIMARY
    net_metric = financials.net_monthly if financials.net_monthly is not None else net
    if net_metric is not None:
        monthly_reality = f"+${abs(net_metric):,.0f}/mo" if net_metric >= 0 else f"-${abs(net_metric):,.0f}/mo"
        monthly_color = ACCENT_GREEN if net_metric >= 0 else ACCENT_RED

    return html.Div(
        [
            html.Div("QUICK REALITY", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}),
            html.Div(
                [
                    _quick_fact("Fair Value", fair_value, f"Ask {ask}" if ask != "N/A" else ""),
                    _quick_fact(
                        "Monthly Reality",
                        monthly_reality,
                        f"Carry {f'${financials.monthly_cost:,.0f}/mo' if financials.monthly_cost else 'N/A'} • Rent {f'${financials.rent_offset:,.0f}/mo' if financials.rent_offset else 'N/A'}",
                        value_color=monthly_color,
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))", "gap": "12px"},
            ),
        ],
        style=CARD_STYLE,
    )


def _quick_fact(label: str, value: str, subtitle: str, *, value_color: str = TEXT_PRIMARY) -> html.Div:
    return html.Div(
        [
            html.Div(label, style={**LABEL_STYLE, "marginBottom": "4px"}),
            html.Div(value, style={"fontSize": "22px", "fontWeight": "800", "fontFamily": FONT_MONO, "color": value_color}),
            html.Div(subtitle, style={"fontSize": "12px", "lineHeight": "1.5", "color": TEXT_SECONDARY, "marginTop": "4px"}) if subtitle else None,
        ],
        style={"padding": "4px 0"},
    )


def _fmt_money_inline(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.0f}"


def _render_financial_support_card(view: PropertyAnalysisView, metrics: dict) -> html.Div:
    financial_metrics = view.property_decision_view.financials.metrics
    net = financial_metrics.net_monthly if financial_metrics.net_monthly is not None else metrics.get("net_monthly_cost")
    net_text = "N/A"
    net_color = TEXT_PRIMARY
    if net is not None:
        net_text = f"+${abs(net):,.0f}/mo" if net >= 0 else f"-${abs(net):,.0f}/mo"
        net_color = ACCENT_GREEN if net >= 0 else ACCENT_RED

    inc = view.property_decision_view.financials.income_support
    return html.Div(
        [
            html.Div("SUPPORT SNAPSHOT", style=_LAYER2_HEADER),
            html.Div(
                [
                    _quick_fact("Net Monthly", net_text, inc.rent_source_label or inc.rent_source_type, value_color=net_color),
                    _quick_fact("Income Coverage", inc.income_support_ratio_text, inc.risk_view),
                    _quick_fact("Price to Rent", inc.price_to_rent_text, getattr(inc, "ptr_classification", "") or ""),
                    _quick_fact("Break Even", "Yes" if financial_metrics.break_even else "No", _forward_context_line(view)),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "12px"},
            ),
        ],
        style=CARD_STYLE,
    )


# ── Deal Curve (Price Sensitivity) ──────────────────────────────────────────


def render_deal_curve_summary(view: PropertyAnalysisView) -> html.Div | None:
    """Compact price-sensitivity block showing action thresholds and the curve.

    Returns None when no deal curve data is available.
    """
    curve = view.deal_curve
    thresholds = view.deal_curve_thresholds
    if not curve or thresholds is None:
        return None

    # ── Threshold cards ──────────────────────────────────────────────────
    threshold_cards: list[html.Div] = []
    if thresholds.get("buy_below") is not None:
        threshold_cards.append(
            _threshold_card("Buy Below", thresholds["buy_below"], ACCENT_GREEN, "Strong entry at this price or lower."),
        )
    if thresholds.get("interesting") is not None:
        threshold_cards.append(
            _threshold_card("Gets Interesting", thresholds["interesting"], ACCENT_AMBER, "Verdict turns NEUTRAL — worth watching."),
        )
    if thresholds.get("pass_above") is not None:
        threshold_cards.append(
            _threshold_card("Pass Above", thresholds["pass_above"], ACCENT_RED, "The deal doesn't work at this price."),
        )

    # Edge case: if all verdicts are identical, show one summary card
    if not threshold_cards:
        verdict = curve[0]["verdict"]
        color = verdict_color(verdict)
        threshold_cards.append(
            _threshold_card(
                verdict,
                curve[0]["price"],
                color,
                f"Verdict holds at every tested price ({curve[-1]['pct_of_ask']:.0%}–{curve[0]['pct_of_ask']:.0%} of ask).",
            ),
        )

    # ── Curve table ──────────────────────────────────────────────────────
    header = html.Div(
        [
            html.Span("Entry", style=_CURVE_CELL_HEADER),
            html.Span("Verdict", style=_CURVE_CELL_HEADER),
            html.Span("Carry", style=_CURVE_CELL_HEADER),
            html.Span("FV Gap", style=_CURVE_CELL_HEADER),
            html.Span("Risk", style=_CURVE_CELL_HEADER),
        ],
        style=_CURVE_ROW_STYLE,
    )
    rows = [header] + [_deal_curve_row(pt) for pt in curve]

    return html.Div(
        [
            html.Div(
                threshold_cards,
                style={
                    "display": "grid",
                    "gridTemplateColumns": f"repeat({len(threshold_cards)}, 1fr)",
                    "gap": "12px",
                    "marginBottom": "16px",
                },
            ),
            html.Div("PRICE SENSITIVITY", style=_LAYER2_HEADER),
            html.Div(
                "How the verdict, carry, and risk shift as entry price drops from ask.",
                style={"fontSize": "13px", "color": TEXT_SECONDARY, "marginBottom": "10px"},
            ),
            html.Div(rows),
        ],
        style=CARD_STYLE,
    )


def _threshold_card(title: str, price: float, color: str, subtitle: str) -> html.Div:
    return html.Div(
        [
            html.Div(title.upper(), style={**LABEL_STYLE, "color": color, "marginBottom": "4px"}),
            html.Div(f"${price:,.0f}", style={"fontSize": "20px", "fontWeight": "800", "fontFamily": FONT_MONO, "color": TEXT_PRIMARY}),
            html.Div(subtitle, style={"fontSize": "12px", "color": TEXT_SECONDARY, "marginTop": "4px"}),
        ],
        style={
            **CARD_STYLE,
            "borderTop": f"3px solid {color}",
            "padding": "16px 20px",
            "textAlign": "center",
        },
    )


_CURVE_CELL_HEADER: dict = {
    "fontSize": "11px",
    "fontWeight": "600",
    "color": TEXT_TERTIARY,
    "textTransform": "uppercase",
    "letterSpacing": "0.08em",
}

_CURVE_ROW_STYLE: dict = {
    "display": "grid",
    "gridTemplateColumns": "1.3fr 1fr 1fr 1fr 0.7fr",
    "gap": "8px",
    "padding": "8px 0",
    "borderBottom": f"1px solid {BORDER}",
    "alignItems": "center",
}


def _deal_curve_row(pt: dict) -> html.Div:
    pct = pt.get("pct_of_ask", 1.0)
    price = pt.get("price", 0)
    verdict = pt.get("verdict", "")
    carry = pt.get("carry")
    fv_gap = pt.get("fv_gap")
    risk = pt.get("risk", 50)

    carry_text = f"${carry:+,.0f}/mo" if carry is not None else "N/A"
    carry_color = ACCENT_GREEN if carry is not None and carry >= 0 else ACCENT_RED if carry is not None else TEXT_SECONDARY
    fv_text = f"{fv_gap:+.1%}" if fv_gap is not None else "N/A"
    fv_color = ACCENT_GREEN if fv_gap is not None and fv_gap >= 0 else ACCENT_RED if fv_gap is not None else TEXT_SECONDARY

    return html.Div(
        [
            html.Span(
                [
                    html.Span(f"${price:,.0f}", style={"fontWeight": "600", "fontFamily": FONT_MONO}),
                    html.Span(f" ({pct:.0%})", style={"fontSize": "11px", "color": TEXT_SECONDARY, "marginLeft": "4px"}),
                ],
                style={"fontSize": "14px", "color": TEXT_PRIMARY},
            ),
            html.Span(
                verdict,
                style={
                    "fontSize": "13px",
                    "fontWeight": "700",
                    "color": verdict_color(verdict),
                },
            ),
            html.Span(carry_text, style={"fontSize": "13px", "fontFamily": FONT_MONO, "color": carry_color}),
            html.Span(fv_text, style={"fontSize": "13px", "fontFamily": FONT_MONO, "color": fv_color}),
            html.Span(
                f"{risk}",
                style={
                    "fontSize": "13px",
                    "fontFamily": FONT_MONO,
                    "fontWeight": "600",
                    "color": ACCENT_GREEN if risk < 34 else ACCENT_AMBER if risk < 67 else ACCENT_RED,
                },
            ),
        ],
        style=_CURVE_ROW_STYLE,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Backward compat wrappers — old standalone screen functions
# ═══════════════════════════════════════════════════════════════════════════════


def render_price_support(view, report, *, user_role="homebuyer"):
    return render_property_view(view, report, user_role=user_role)


def render_financials(view, report, *, user_role="homebuyer"):
    return render_property_view(view, report, user_role=user_role)


def render_scenarios(view, report, *, user_role="homebuyer"):
    return render_property_view(view, report, user_role=user_role)


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


# ── Shared styles and helpers ────────────────────────────────────────────────

_LAYER2_HEADER: dict = {**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em"}

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
    price = view.property_decision_view.price_support
    bcv = price.fair_value
    ask = price.ask_price
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
    comps = view.property_decision_view.price_support.comps
    value_vm = view.property_decision_view.price_support.value

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
    comps = view.property_decision_view.price_support.comps
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
    forward = view.property_decision_view.financials.forward
    if forward:
        return f"Bull case {forward.upside_pct_text} upside, bear case {forward.downside_pct_text} downside over 12 months."
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
    inc = view.property_decision_view.financials.income_support
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
    price = view.property_decision_view.price_support
    if price.value and price.value.value_bridge:
        for step in price.value.value_bridge:
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
        if price.fair_value is not None:
            rows.append(
                html.Div(
                    [
                        html.Span("Estimated fair value", style={"fontSize": "15px", "fontWeight": "700", "color": TEXT_PRIMARY}),
                        html.Span(
                            f"${price.fair_value:,.0f}",
                            style={"fontSize": "16px", "fontFamily": FONT_MONO, "fontWeight": "700", "color": TEXT_PRIMARY},
                        ),
                    ],
                    className="value-waterfall-row value-waterfall-total",
                )
            )
        if price.ask_price is not None and price.fair_value is not None:
            gap = price.fair_value - price.ask_price
            gap_color = ACCENT_GREEN if gap >= 0 else ACCENT_RED
            rows.append(
                html.Div(
                    [
                        html.Span("vs. asking price", style={"fontSize": "14px", "color": TEXT_SECONDARY}),
                        html.Span(
                            f"{'+'if gap >= 0 else ''}{gap/price.ask_price*100:.1f}%",
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

from __future__ import annotations

from dash import html

from briarwood.dash_app.quick_decision import QuickDecisionViewModel
from briarwood.dash_app.theme import (
    ACCENT_AMBER,
    ACCENT_GREEN,
    ACCENT_RED,
    CARD_STYLE_ELEVATED,
    FONT_MONO,
    LABEL_STYLE,
    SECTION_HEADER_STYLE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    TONE_NEGATIVE_BG,
    TONE_NEGATIVE_BORDER,
    TONE_NEGATIVE_TEXT,
    TONE_NEUTRAL_BG,
    TONE_NEUTRAL_BORDER,
    TONE_POSITIVE_BG,
    TONE_POSITIVE_BORDER,
    TONE_POSITIVE_TEXT,
    TONE_WARNING_BG,
    TONE_WARNING_BORDER,
    TONE_WARNING_TEXT,
    risk_dot,
    tone_badge_style,
    verdict_color,
)


def _hero_tone(recommendation: str) -> tuple[str, str, str]:
    if recommendation == "BUY":
        return TONE_POSITIVE_BG, TONE_POSITIVE_BORDER, ACCENT_GREEN
    if recommendation == "LEAN BUY":
        return TONE_POSITIVE_BG, TONE_POSITIVE_BORDER, ACCENT_GREEN
    if recommendation == "NEUTRAL":
        return TONE_NEUTRAL_BG, TONE_NEUTRAL_BORDER, ACCENT_AMBER
    if recommendation == "LEAN PASS":
        return TONE_WARNING_BG, TONE_WARNING_BORDER, ACCENT_AMBER
    return TONE_NEGATIVE_BG, TONE_NEGATIVE_BORDER, ACCENT_RED


def render_recommendation_hero(vm: QuickDecisionViewModel) -> html.Div:
    hero_bg, hero_border, accent = _hero_tone(vm.recommendation)
    beliefs = vm.required_beliefs[:3]
    risk_bar = vm.risk_bar[:5]
    return html.Div(
        className="card briarwood-fade-in",
        children=[
            html.Div("DECISION ENGINE", style={**SECTION_HEADER_STYLE, "fontSize": "11px", "letterSpacing": "0.14em", "marginBottom": "16px"}),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(vm.recommendation, style={"fontSize": "48px", "fontWeight": "800", "letterSpacing": "-0.04em", "lineHeight": "1.0", "color": accent}),
                            html.Div("Should I move forward?", style={**LABEL_STYLE, "marginTop": "8px"}),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div("Conviction", style=LABEL_STYLE),
                            html.Div(f"{int(round(vm.conviction * 100))}%", style={"fontSize": "32px", "fontWeight": "800", "fontFamily": FONT_MONO, "lineHeight": "1.0", "color": accent}),
                        ],
                        style={"textAlign": "right"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "gap": "16px", "marginBottom": "20px"},
            ),
            html.Div(
                [
                    html.Div("Why", style={**LABEL_STYLE, "marginBottom": "4px"}),
                    html.Div(vm.primary_reason, style={"fontSize": "16px", "fontWeight": "600", "lineHeight": "1.5", "color": TEXT_PRIMARY}),
                    html.Div(vm.secondary_reason, style={"fontSize": "14px", "lineHeight": "1.55", "color": TEXT_SECONDARY, "marginTop": "6px"}) if vm.secondary_reason else None,
                ],
                style={"marginBottom": "16px"},
            ),
            html.Div(
                [
                    html.Div("Risk Bar", style={**LABEL_STYLE, "marginBottom": "10px"}),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span(item.name, style={"fontSize": "12px", "fontWeight": "600", "color": TEXT_PRIMARY}),
                                            html.Span(item.level.upper(), style=tone_badge_style(_risk_tone(item.level))),
                                        ],
                                        style={"display": "flex", "justifyContent": "space-between", "gap": "8px", "alignItems": "center"},
                                    ),
                                    html.Div(f"{item.score}/100", style={"fontSize": "20px", "fontWeight": "800", "fontFamily": FONT_MONO, "lineHeight": "1.1", "color": _risk_color(item.level)}),
                                    html.Div(item.label, style={"fontSize": "12px", "lineHeight": "1.45", "color": TEXT_SECONDARY, "marginTop": "4px"}),
                                ],
                                style={
                                    "padding": "12px",
                                    "borderRadius": "8px",
                                    "border": f"1px solid {hero_border}",
                                    "backgroundColor": "rgba(0,0,0,0.15)",
                                },
                            )
                            for item in risk_bar
                        ],
                        style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(140px, 1fr))", "gap": "10px"},
                    ),
                ],
                style={"marginBottom": "16px"},
            ) if risk_bar else None,
            html.Div(
                [
                    html.Div("What Must Be True", style={**LABEL_STYLE, "marginBottom": "6px"}),
                    html.Ul(
                        [html.Li(item, style={"fontSize": "14px", "lineHeight": "1.55", "color": TEXT_SECONDARY}) for item in beliefs],
                        style={"margin": "0", "paddingLeft": "18px"},
                    ) if beliefs else html.Div("No open belief conditions surfaced.", style={"fontSize": "14px", "color": TEXT_TERTIARY}),
                ]
            ),
        ],
        style={
            **CARD_STYLE_ELEVATED,
            "backgroundColor": hero_bg,
            "borderColor": hero_border,
            "borderLeft": f"4px solid {accent}",
            "padding": "28px 32px",
            "marginBottom": "20px",
        },
    )


def _risk_tone(level: str) -> str:
    if level == "Low":
        return "positive"
    if level == "Medium":
        return "warning"
    return "negative"


def _risk_color(level: str) -> str:
    if level == "Low":
        return ACCENT_GREEN
    if level == "Medium":
        return ACCENT_AMBER
    return ACCENT_RED


def render_full_analysis_button() -> html.Div:
    return html.Div(
        html.Button(
            "View Full Analysis",
            id={"type": "shell-nav-button", "tab": "tear_sheet"},
            className="btn-primary",
        ),
        className="briarwood-fade-in",
        style={"textAlign": "center", "padding": "8px 0 24px"},
    )


def render_quick_decision(vm: QuickDecisionViewModel) -> html.Div:
    return html.Div(
        [
            render_recommendation_hero(vm),
            render_full_analysis_button() if vm.full_analysis_available else None,
        ]
    )

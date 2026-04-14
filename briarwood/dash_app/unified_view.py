"""Compact decision card renderer for UnifiedIntelligenceOutput.

Morningstar-style summary: clear, opinionated, backed by evidence.
Six sections: recommendation hero, key drivers, risk flags, confidence gauge,
next questions (clickable), Go Deeper action, and analysis depth indicator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dash import html

from briarwood.dash_app.theme import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, BG_SURFACE, BORDER,
    BTN_PRIMARY, BTN_GHOST,
    CARD_STYLE, FONT_MONO, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
)

_AMBER = "#F59E0B"
_DECISION_COLORS = {"buy": ACCENT_GREEN, "pass": ACCENT_RED, "mixed": _AMBER}
_SIGNAL_ICON = {"positive": "+", "negative": "-", "neutral": "~"}
_SIGNAL_COLOR = {"positive": ACCENT_GREEN, "negative": ACCENT_RED, "neutral": TEXT_MUTED}
_SEV_COLOR = {"high": ACCENT_RED, "medium": _AMBER, "low": TEXT_MUTED}
_SECTION = {"padding": "16px 24px", "borderTop": f"1px solid {BORDER}"}
_ROW = {"display": "flex", "gap": "10px", "alignItems": "start"}
_GRID = {"display": "grid"}
_KICKER = {"fontSize": "10px", "fontWeight": "700", "color": TEXT_TERTIARY, "letterSpacing": "0.08em", "marginBottom": "10px"}
_BODY = {"fontSize": "13px", "color": TEXT_PRIMARY, "lineHeight": "1.4"}
_PILL_BASE = {"fontSize": "10px", "fontWeight": "500", "color": TEXT_TERTIARY, "backgroundColor": BG_SURFACE,
              "padding": "2px 8px", "borderRadius": "10px", "border": f"1px solid {BORDER}", "whiteSpace": "nowrap"}


def _dot(char: str, color: str, size: int = 18) -> html.Span:
    return html.Span(char, style={
        "width": f"{size}px", "height": f"{size}px", "borderRadius": "50%",
        "backgroundColor": color + "18", "color": color, "display": "flex",
        "alignItems": "center", "justifyContent": "center",
        "fontSize": f"{size - 6}px", "fontWeight": "700", "flexShrink": "0",
    })


# ── View model ───────────────────────────────────────────────────────────────

@dataclass(slots=True)
class DriverItem:
    text: str
    signal: str

@dataclass(slots=True)
class RiskFlag:
    text: str
    severity: str

@dataclass(slots=True)
class DecisionCardViewModel:
    decision: str; decision_label: str; recommendation: str; best_path: str
    drivers: list[DriverItem] = field(default_factory=list)
    risk_flags: list[RiskFlag] = field(default_factory=list)
    confidence: float = 0.0; confidence_label: str = ""; confidence_detail: str = ""
    next_questions: list[str] = field(default_factory=list)
    recommended_next_run: str | None = None
    intent_type: str = ""; analysis_depth: str = ""
    modules_ran: list[str] = field(default_factory=list); execution_mode: str = ""


def build_decision_card_view(routed_result: dict[str, Any]) -> DecisionCardViewModel | None:
    if not routed_result:
        return None
    unified = routed_result.get("unified_output")
    if not unified:
        return None
    routing = routed_result.get("routing_decision") or {}
    decision_raw = str(unified.get("decision") or "mixed")

    drivers: list[DriverItem] = [DriverItem(t, "positive") for t in list(unified.get("key_value_drivers") or [])[:5]]
    for t in list(unified.get("key_risks") or [])[:5 - len(drivers)]:
        drivers.append(DriverItem(t, "negative"))

    risk_flags = [RiskFlag(t, "high" if i == 0 else "medium" if i <= 2 else "low")
                  for i, t in enumerate(list(unified.get("key_risks") or [])[:5])]

    confidence = float(unified.get("confidence") or 0.0)
    c_label, c_detail = _confidence_description(confidence)
    modules = [str(m).replace("_", " ").title() for m in list(routing.get("selected_modules") or [])]

    return DecisionCardViewModel(
        decision=decision_raw,
        decision_label={"buy": "BUY", "pass": "PASS", "mixed": "INVESTIGATE"}.get(decision_raw, decision_raw.upper()),
        recommendation=str(unified.get("recommendation") or ""),
        best_path=str(unified.get("best_path") or ""),
        drivers=drivers, risk_flags=risk_flags,
        confidence=confidence, confidence_label=c_label, confidence_detail=c_detail,
        next_questions=list(unified.get("next_questions") or [])[:5],
        recommended_next_run=unified.get("recommended_next_run"),
        intent_type=str(routing.get("intent_type") or "").replace("_", " ").title(),
        analysis_depth=str(unified.get("analysis_depth_used") or "").replace("_", " ").title(),
        modules_ran=modules,
        execution_mode=str(routed_result.get("execution_mode") or ""),
    )


# ── Renderer ─────────────────────────────────────────────────────────────────

def render_decision_card(vm: DecisionCardViewModel) -> html.Div:
    return html.Div([
        _hero(vm), _drivers(vm.drivers), _risks(vm.risk_flags),
        _confidence(vm), _questions(vm), _feedback_prompt(), _depth(vm),
    ], style={**CARD_STYLE, "maxWidth": "720px", "margin": "0 auto", "display": "grid", "gap": "0", "overflow": "hidden"})


def _hero(vm: DecisionCardViewModel) -> html.Div:
    c = _DECISION_COLORS.get(vm.decision, TEXT_MUTED)
    return html.Div([
        html.Div([
            html.Span(vm.decision_label, style={"fontSize": "28px", "fontWeight": "800", "color": c, "letterSpacing": "-0.02em", "lineHeight": "1"}),
            html.Div(vm.confidence_label, style={"fontSize": "11px", "fontWeight": "600", "color": TEXT_TERTIARY, "letterSpacing": "0.06em", "textTransform": "uppercase", "marginTop": "4px"}),
        ], style={**_GRID, "gap": "2px"}),
        html.Div([
            html.Div(vm.recommendation, style={"fontSize": "14px", "fontWeight": "500", "color": TEXT_PRIMARY, "lineHeight": "1.5"}),
            html.Div(vm.best_path, style={"fontSize": "13px", "color": TEXT_SECONDARY, "lineHeight": "1.5", "marginTop": "6px"}),
        ], style={"flex": "1", "minWidth": "0"}),
    ], style={"display": "flex", "gap": "20px", "alignItems": "start", "padding": "24px 24px 20px"})


def _drivers(items: list[DriverItem]) -> html.Div:
    if not items:
        return html.Div()
    rows = [html.Div([_dot(_SIGNAL_ICON.get(d.signal, "~"), _SIGNAL_COLOR.get(d.signal, TEXT_MUTED)),
                       html.Span(d.text, style=_BODY)], style=_ROW) for d in items]
    return html.Div([html.Div("KEY DRIVERS", style=_KICKER), html.Div(rows, style={**_GRID, "gap": "8px"})], style=_SECTION)


def _risks(flags: list[RiskFlag]) -> html.Div:
    if not flags:
        return html.Div()
    rows = [html.Div([
        html.Span(f.severity.upper(), style={"fontSize": "9px", "fontWeight": "700", "color": _SEV_COLOR.get(f.severity, TEXT_MUTED), "letterSpacing": "0.08em", "width": "52px", "flexShrink": "0"}),
        html.Span(f.text, style=_BODY),
    ], style={**_ROW, "alignItems": "baseline"}) for f in flags]
    return html.Div([html.Div("RISK FLAGS", style=_KICKER), html.Div(rows, style={**_GRID, "gap": "6px"})], style=_SECTION)


def _confidence(vm: DecisionCardViewModel) -> html.Div:
    pct = max(0.0, min(1.0, vm.confidence))
    c = ACCENT_GREEN if pct >= 0.7 else _AMBER if pct >= 0.4 else ACCENT_RED
    bar = html.Div(html.Div(style={"width": f"{pct * 100:.0f}%", "height": "100%", "backgroundColor": c, "borderRadius": "3px", "transition": "width 0.3s ease"}),
                   style={"height": "6px", "backgroundColor": BORDER, "borderRadius": "3px", "flex": "1"})
    label = html.Span(f"{pct:.0%}", style={"fontSize": "13px", "fontWeight": "600", "fontFamily": FONT_MONO, "color": c, "minWidth": "38px", "textAlign": "right"})
    detail = html.Div(vm.confidence_detail, style={"fontSize": "12px", "color": TEXT_TERTIARY, "marginTop": "4px"}) if vm.confidence_detail else None
    return html.Div([html.Div("CONFIDENCE", style=_KICKER), html.Div([bar, label], style={"display": "flex", "gap": "12px", "alignItems": "center"}), detail], style=_SECTION)


def _questions(vm: DecisionCardViewModel) -> html.Div:
    if not vm.next_questions and not vm.recommended_next_run:
        return html.Div()
    children: list = []
    if vm.next_questions:
        rows = [
            html.Button(
                [_dot("?", ACCENT_BLUE, 16), html.Span(q, style={**_BODY, "color": TEXT_SECONDARY})],
                id={"type": "next-question-btn", "index": i},
                n_clicks=0,
                style={
                    **_ROW,
                    "background": "none", "border": "none", "cursor": "pointer",
                    "padding": "4px 0", "width": "100%", "textAlign": "left",
                },
                title="Ask this question",
            )
            for i, q in enumerate(vm.next_questions)
        ]
        children.append(html.Div("WHAT'S MISSING", style=_KICKER))
        children.append(html.Div(rows, style={**_GRID, "gap": "6px"}))
    if vm.recommended_next_run:
        _DEPTH_LABELS = {"decision": "Decision", "scenario": "Scenario", "deep_dive": "Deep Dive"}
        depth_label = _DEPTH_LABELS.get(vm.recommended_next_run, vm.recommended_next_run.replace("_", " ").title())
        children.append(
            html.Button(
                f"Go Deeper \u2192 {depth_label}",
                id="go-deeper-btn",
                n_clicks=0,
                style={
                    **BTN_PRIMARY,
                    "width": "100%", "marginTop": "12px",
                    "padding": "10px 16px", "fontSize": "13px",
                },
            )
        )
    return html.Div(children, style=_SECTION)


def _feedback_prompt() -> html.Div:
    """Inline 'Was this helpful?' prompt with Yes / Partially / No buttons."""
    _FB_BTN = {
        "background": "none", "border": f"1px solid {BORDER}", "borderRadius": "6px",
        "padding": "5px 14px", "fontSize": "12px", "fontWeight": "500",
        "cursor": "pointer", "color": TEXT_SECONDARY,
    }
    return html.Div([
        html.Div("Was this helpful?", style={**_KICKER, "marginBottom": "8px"}),
        html.Div([
            html.Button("Yes", id={"type": "user-feedback-btn", "rating": "yes"}, n_clicks=0, style=_FB_BTN),
            html.Button("Partially", id={"type": "user-feedback-btn", "rating": "partially"}, n_clicks=0, style=_FB_BTN),
            html.Button("No", id={"type": "user-feedback-btn", "rating": "no"}, n_clicks=0, style=_FB_BTN),
        ], style={"display": "flex", "gap": "8px"}),
        html.Div(id="user-feedback-confirmation", style={"fontSize": "12px", "color": TEXT_MUTED, "marginTop": "6px"}),
    ], style=_SECTION)


def _depth(vm: DecisionCardViewModel) -> html.Div:
    pills = [html.Span(n, style=_PILL_BASE) for n in vm.modules_ran]
    meta = " \u00b7 ".join(p for p in [vm.intent_type, vm.analysis_depth, vm.execution_mode.replace("_", " ").title() if vm.execution_mode else ""] if p)
    return html.Div([
        html.Div([
            html.Span("Analysis Scope", style={**_KICKER, "marginBottom": "0"}),
            html.Span(meta, style={"fontSize": "12px", "color": TEXT_SECONDARY}) if meta else None,
        ], style={"display": "flex", "gap": "10px", "alignItems": "center"}),
        html.Div(pills, style={"display": "flex", "flexWrap": "wrap", "gap": "4px", "marginTop": "6px"}) if pills else None,
    ], style={"padding": "14px 24px 18px", "borderTop": f"1px solid {BORDER}", "backgroundColor": BG_SURFACE})


def _confidence_description(c: float) -> tuple[str, str]:
    if c >= 0.80: return "High Confidence", ""
    if c >= 0.60: return "Moderate Confidence", "Some assumptions are estimated or unverified."
    if c >= 0.40: return "Low-Moderate Confidence", "Key inputs like rent or condition are estimated."
    return "Low Confidence", "Multiple critical inputs are missing or estimated."


def render_conversation_history(entries: list[dict[str, Any]]) -> html.Div:
    """Render a compact stack of prior question/answer pairs above the current card."""
    if not entries:
        return html.Div()
    items: list = []
    for i, entry in enumerate(entries):
        q = str(entry.get("question") or "")
        decision = str(entry.get("decision") or "")
        depth = str(entry.get("analysis_depth") or "").replace("_", " ").title()
        confidence = entry.get("confidence")
        conf_text = f" \u00b7 {confidence:.0%}" if isinstance(confidence, (int, float)) else ""
        c = _DECISION_COLORS.get(decision, TEXT_MUTED)
        items.append(html.Div([
            html.Div(f"Q{i + 1}: {q}", style={"fontSize": "12px", "fontWeight": "500", "color": TEXT_PRIMARY}),
            html.Div([
                html.Span(decision.upper(), style={"fontSize": "11px", "fontWeight": "700", "color": c}),
                html.Span(f" \u00b7 {depth}{conf_text}", style={"fontSize": "11px", "color": TEXT_TERTIARY}),
            ]),
        ], style={"padding": "8px 12px", "borderLeft": f"3px solid {c}", "marginBottom": "6px"}))
    return html.Div([
        html.Div("CONVERSATION HISTORY", style={**_KICKER, "padding": "0 24px"}),
        html.Div(items, style={"padding": "0 24px 12px"}),
    ], style={"borderBottom": f"1px solid {BORDER}"})


__all__ = ["DecisionCardViewModel", "build_decision_card_view", "render_decision_card", "render_conversation_history"]

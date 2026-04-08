"""
Design tokens for the Briarwood investment research platform.

Analytical and premium, with a lighter, more welcoming retail-facing shell.
"""
from __future__ import annotations

from briarwood.recommendations import normalize_recommendation_label

# ── Color palette ──────────────────────────────────────────────────────────────

BG_BASE = "#f5f1e8"
BG_SURFACE = "#fffdf8"
BG_SURFACE_2 = "#f8f4ec"
BG_SURFACE_3 = "#efe8dc"
BG_SURFACE_4 = "#e4d8c7"

BORDER = "#d8ccbc"
BORDER_SUBTLE = "#e8dfd2"

TEXT_PRIMARY = "#1f2a37"
TEXT_SECONDARY = "#526071"
TEXT_MUTED = "#7a8795"
TEXT_LINK = "#285ea8"

ACCENT_BLUE = "#2f6fb2"
ACCENT_GREEN = "#1f8a56"
ACCENT_YELLOW = "#b78818"
ACCENT_RED = "#c44a3d"
ACCENT_ORANGE = "#cc7a29"
ACCENT_TEAL = "#0f8b8d"

TONE_POSITIVE_TEXT = "#1f8a56"
TONE_POSITIVE_BG = "#e9f5ee"
TONE_POSITIVE_BORDER = "#b7dec8"

TONE_WARNING_TEXT = "#9a6a00"
TONE_WARNING_BG = "#fff6df"
TONE_WARNING_BORDER = "#e9d39a"

TONE_NEGATIVE_TEXT = "#b53f34"
TONE_NEGATIVE_BG = "#faece9"
TONE_NEGATIVE_BORDER = "#e6b7b1"

TONE_NEUTRAL_TEXT = "#617181"
TONE_NEUTRAL_BG = "#f1ece3"
TONE_NEUTRAL_BORDER = "#d7cab8"

# ── Typography ─────────────────────────────────────────────────────────────────

FONT_FAMILY = "Inter, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif"
FONT_MONO = "'JetBrains Mono', 'SF Mono', 'Fira Code', Consolas, monospace"

# ── Layout ─────────────────────────────────────────────────────────────────────

TOPBAR_HEIGHT = "48px"
PROPERTY_HEADER_HEIGHT = "40px"

# ── Chart heights ──────────────────────────────────────────────────────────────

CHART_HEIGHT_COMPACT = 160
CHART_HEIGHT_STANDARD = 200
CHART_HEIGHT_TALL = 280

# ── Component base styles ──────────────────────────────────────────────────────

PAGE_STYLE: dict = {
    "fontFamily": FONT_FAMILY,
    "backgroundColor": BG_BASE,
    "color": TEXT_PRIMARY,
    "minHeight": "100vh",
    "lineHeight": "1.45",
    "fontSize": "13px",
    "backgroundImage": "linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(245,241,232,0.95) 30%, rgba(245,241,232,1) 100%)",
}

TOPBAR_STYLE: dict = {
    "backgroundColor": "rgba(255,253,248,0.92)",
    "borderBottom": f"1px solid {BORDER}",
    "padding": "0 20px",
    "height": TOPBAR_HEIGHT,
    "display": "flex",
    "alignItems": "center",
    "gap": "12px",
    "position": "sticky",
    "top": "0",
    "zIndex": "200",
    "flexShrink": "0",
    "backdropFilter": "blur(12px)",
    "boxShadow": "0 8px 24px rgba(77, 60, 32, 0.05)",
}

PROPERTY_HEADER_STYLE: dict = {
    "backgroundColor": "rgba(248,244,236,0.94)",
    "borderBottom": f"1px solid {BORDER_SUBTLE}",
    "padding": "6px 20px",
    "height": PROPERTY_HEADER_HEIGHT,
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "space-between",
    "position": "sticky",
    "top": TOPBAR_HEIGHT,
    "zIndex": "190",
    "flexShrink": "0",
    "backdropFilter": "blur(10px)",
}

CARD_STYLE: dict = {
    "backgroundColor": BG_SURFACE,
    "border": f"1px solid {BORDER}",
    "borderRadius": "12px",
    "padding": "10px 12px",
    "boxShadow": "0 8px 24px rgba(76, 57, 30, 0.05)",
}

CARD_STYLE_ELEVATED: dict = {
    "backgroundColor": BG_SURFACE_2,
    "border": f"1px solid {BORDER}",
    "borderRadius": "14px",
    "padding": "10px 12px",
    "boxShadow": "0 12px 32px rgba(76, 57, 30, 0.07)",
}

SECTION_HEADER_STYLE: dict = {
    "fontSize": "11px",
    "fontWeight": "600",
    "letterSpacing": "0.10em",
    "textTransform": "uppercase",
    "color": TEXT_MUTED,
    "marginBottom": "8px",
}

LABEL_STYLE: dict = {
    "fontSize": "11px",
    "fontWeight": "500",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
    "color": TEXT_MUTED,
    "marginBottom": "3px",
}

VALUE_STYLE_LARGE: dict = {
    "fontSize": "18px",
    "fontWeight": "600",
    "letterSpacing": "-0.02em",
    "lineHeight": "1.2",
}

VALUE_STYLE_MEDIUM: dict = {
    "fontSize": "15px",
    "fontWeight": "600",
    "letterSpacing": "-0.01em",
}

BODY_TEXT_STYLE: dict = {
    "fontSize": "13px",
    "color": TEXT_SECONDARY,
    "lineHeight": "1.6",
}

MONO_STYLE: dict = {
    "fontFamily": FONT_MONO,
    "fontSize": "12px",
    "color": TEXT_SECONDARY,
}

# ── Button styles ──────────────────────────────────────────────────────────────

BTN_PRIMARY: dict = {
    "backgroundColor": ACCENT_BLUE,
    "color": "#fffdf8",
    "border": "none",
    "borderRadius": "10px",
    "padding": "8px 14px",
    "fontSize": "13px",
    "fontWeight": "600",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
    "whiteSpace": "nowrap",
    "boxShadow": "0 6px 16px rgba(47, 111, 178, 0.18)",
}

BTN_SECONDARY: dict = {
    "backgroundColor": BG_SURFACE,
    "color": TEXT_SECONDARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": "10px",
    "padding": "7px 12px",
    "fontSize": "13px",
    "fontWeight": "500",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
    "whiteSpace": "nowrap",
}

BTN_GHOST: dict = {
    "backgroundColor": "transparent",
    "color": TEXT_MUTED,
    "border": "none",
    "borderRadius": "8px",
    "padding": "4px 10px",
    "fontSize": "12px",
    "fontWeight": "500",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
}

# ── Input styles ───────────────────────────────────────────────────────────────

INPUT_STYLE: dict = {
    "backgroundColor": BG_SURFACE,
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": "10px",
    "padding": "8px 10px",
    "fontSize": "13px",
    "fontFamily": FONT_FAMILY,
    "width": "100%",
    "boxSizing": "border-box",
    "outline": "none",
    "boxShadow": "inset 0 1px 2px rgba(76, 57, 30, 0.04)",
}

# ── Responsive grid helpers ────────────────────────────────────────────────────

GRID_2: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))", "gap": "8px"}
GRID_3: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "8px"}
GRID_4: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(160px, 1fr))", "gap": "8px"}
GRID_5: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(140px, 1fr))", "gap": "8px"}

# ── Plotly light theme base ────────────────────────────────────────────────────

PLOTLY_LAYOUT: dict = {
    "paper_bgcolor": BG_SURFACE,
    "plot_bgcolor": BG_SURFACE_2,
    "font": {"color": TEXT_PRIMARY, "family": FONT_FAMILY, "size": 12},
    "margin": {"l": 44, "r": 16, "t": 24, "b": 36},
    "xaxis": {
        "gridcolor": BORDER_SUBTLE,
        "linecolor": BORDER,
        "tickcolor": TEXT_MUTED,
        "tickfont": {"color": TEXT_MUTED, "size": 11},
        "showgrid": True,
        "zeroline": False,
    },
    "yaxis": {
        "gridcolor": BORDER_SUBTLE,
        "linecolor": BORDER,
        "tickcolor": TEXT_MUTED,
        "tickfont": {"color": TEXT_MUTED, "size": 11},
        "showgrid": True,
        "zeroline": False,
    },
    "legend": {
        "bgcolor": "rgba(0,0,0,0)",
        "bordercolor": BORDER,
        "font": {"color": TEXT_SECONDARY, "size": 11},
    },
    "hoverlabel": {
        "bgcolor": BG_SURFACE,
        "bordercolor": BORDER,
        "font": {"color": TEXT_PRIMARY, "family": FONT_FAMILY, "size": 12},
    },
}

PLOTLY_LAYOUT_COMPACT: dict = {
    **PLOTLY_LAYOUT,
    "margin": {"l": 32, "r": 8, "t": 12, "b": 28},
}

# ── DataTable light theme ──────────────────────────────────────────────────────

TABLE_STYLE_CELL: dict = {
    "backgroundColor": BG_SURFACE,
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER_SUBTLE}",
    "padding": "6px 10px",
    "fontFamily": FONT_FAMILY,
    "fontSize": "13px",
    "textAlign": "left",
}

TABLE_STYLE_HEADER: dict = {
    "backgroundColor": BG_SURFACE_3,
    "color": TEXT_SECONDARY,
    "fontWeight": "600",
    "fontSize": "11px",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
    "border": f"1px solid {BORDER}",
    "padding": "6px 10px",
}

TABLE_STYLE_DATA_ODD: dict = {
    "backgroundColor": BG_SURFACE,
}

TABLE_STYLE_DATA_EVEN: dict = {
    "backgroundColor": BG_SURFACE_2,
}

TABLE_STYLE_TABLE: dict = {
    "overflowX": "auto",
    "borderRadius": "12px",
    "border": f"1px solid {BORDER}",
    "overflowY": "hidden",
}

# ── Tone helpers ───────────────────────────────────────────────────────────────


def tone_color(tone: str) -> str:
    """Return text color for a given tone."""
    return {
        "positive": TONE_POSITIVE_TEXT,
        "warning": TONE_WARNING_TEXT,
        "negative": TONE_NEGATIVE_TEXT,
    }.get(tone, TEXT_PRIMARY)


def score_color(score: float) -> str:
    """Return color for a 1-5 score value."""
    if score >= 4.0:
        return ACCENT_GREEN
    if score >= 3.0:
        return ACCENT_YELLOW
    if score >= 2.0:
        return ACCENT_ORANGE
    return ACCENT_RED


def score_label(score: float) -> str:
    """Return human-readable label for a 1-5 score value."""
    if score >= 4.5:
        return "Clear"
    if score >= 4.0:
        return "Supported"
    if score >= 3.0:
        return "Mixed"
    if score >= 2.0:
        return "Thin"
    return "Unsupported"


def verdict_color(verdict: str) -> str:
    """Return accent color for a recommendation tier string."""
    v = normalize_recommendation_label(verdict)
    if v == "Buy":
        return ACCENT_GREEN
    if v == "Neutral":
        return ACCENT_ORANGE
    return ACCENT_RED


def tone_badge_style(tone: str) -> dict:
    """Return inline style for a pill/badge for a given tone."""
    styles = {
        "positive": {"backgroundColor": TONE_POSITIVE_BG, "color": TONE_POSITIVE_TEXT, "border": f"1px solid {TONE_POSITIVE_BORDER}"},
        "warning": {"backgroundColor": TONE_WARNING_BG, "color": TONE_WARNING_TEXT, "border": f"1px solid {TONE_WARNING_BORDER}"},
        "negative": {"backgroundColor": TONE_NEGATIVE_BG, "color": TONE_NEGATIVE_TEXT, "border": f"1px solid {TONE_NEGATIVE_BORDER}"},
        "neutral": {"backgroundColor": TONE_NEUTRAL_BG, "color": TONE_NEUTRAL_TEXT, "border": f"1px solid {TONE_NEUTRAL_BORDER}"},
    }
    base = {
        "padding": "3px 8px",
        "borderRadius": "999px",
        "fontSize": "11px",
        "fontWeight": "600",
        "display": "inline-block",
        "whiteSpace": "nowrap",
    }
    return {**base, **styles.get(tone, styles["neutral"])}

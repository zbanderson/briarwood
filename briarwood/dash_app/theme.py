"""
Design tokens for the Briarwood investment research platform.

Dense, analytical, data-forward. Every pixel earns its space.
"""
from __future__ import annotations

# ── Color palette ──────────────────────────────────────────────────────────────

BG_BASE = "#0d1117"
BG_SURFACE = "#161b22"
BG_SURFACE_2 = "#1c2333"
BG_SURFACE_3 = "#21262d"
BG_SURFACE_4 = "#2d333b"

BORDER = "#30363d"
BORDER_SUBTLE = "#21262d"

TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED = "#848d97"  # 5.5:1 contrast on BG_BASE (WCAG AA)
TEXT_LINK = "#58a6ff"

ACCENT_BLUE = "#58a6ff"
ACCENT_GREEN = "#3fb950"
ACCENT_YELLOW = "#d29922"
ACCENT_RED = "#f85149"
ACCENT_ORANGE = "#f0883e"
ACCENT_TEAL = "#39d353"

TONE_POSITIVE_TEXT = "#3fb950"
TONE_POSITIVE_BG = "#1a3a1f"
TONE_POSITIVE_BORDER = "#2d6a35"

TONE_WARNING_TEXT = "#d29922"
TONE_WARNING_BG = "#3a2f0d"
TONE_WARNING_BORDER = "#6a4f0e"

TONE_NEGATIVE_TEXT = "#f85149"
TONE_NEGATIVE_BG = "#3a1414"
TONE_NEGATIVE_BORDER = "#6a2020"

TONE_NEUTRAL_TEXT = "#8b949e"
TONE_NEUTRAL_BG = "#1c2333"
TONE_NEUTRAL_BORDER = "#30363d"

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
}

TOPBAR_STYLE: dict = {
    "backgroundColor": BG_SURFACE,
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
}

PROPERTY_HEADER_STYLE: dict = {
    "backgroundColor": BG_SURFACE,
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
}

CARD_STYLE: dict = {
    "backgroundColor": BG_SURFACE,
    "border": f"1px solid {BORDER}",
    "borderRadius": "4px",
    "padding": "10px 12px",
}

CARD_STYLE_ELEVATED: dict = {
    "backgroundColor": BG_SURFACE_2,
    "border": f"1px solid {BORDER}",
    "borderRadius": "4px",
    "padding": "10px 12px",
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
    "color": "#0d1117",
    "border": "none",
    "borderRadius": "4px",
    "padding": "6px 14px",
    "fontSize": "13px",
    "fontWeight": "600",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
    "whiteSpace": "nowrap",
}

BTN_SECONDARY: dict = {
    "backgroundColor": "transparent",
    "color": TEXT_SECONDARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": "4px",
    "padding": "5px 12px",
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
    "borderRadius": "4px",
    "padding": "4px 10px",
    "fontSize": "12px",
    "fontWeight": "500",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
}

# ── Input styles ───────────────────────────────────────────────────────────────

INPUT_STYLE: dict = {
    "backgroundColor": BG_SURFACE_3,
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": "4px",
    "padding": "6px 8px",
    "fontSize": "13px",
    "fontFamily": FONT_FAMILY,
    "width": "100%",
    "boxSizing": "border-box",
    "outline": "none",
}

# ── Responsive grid helpers ────────────────────────────────────────────────────

GRID_2: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))", "gap": "8px"}
GRID_3: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "8px"}
GRID_4: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(160px, 1fr))", "gap": "8px"}
GRID_5: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(140px, 1fr))", "gap": "8px"}

# ── Plotly dark theme base ─────────────────────────────────────────────────────

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
        "bgcolor": BG_SURFACE_2,
        "bordercolor": BORDER,
        "font": {"color": TEXT_PRIMARY, "family": FONT_FAMILY, "size": 12},
    },
}

PLOTLY_LAYOUT_COMPACT: dict = {
    **PLOTLY_LAYOUT,
    "margin": {"l": 32, "r": 8, "t": 12, "b": 28},
}

# ── DataTable dark theme ───────────────────────────────────────────────────────

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
    "borderRadius": "4px",
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
        return "Excellent"
    if score >= 4.0:
        return "Strong"
    if score >= 3.0:
        return "Fair"
    if score >= 2.0:
        return "Weak"
    return "Poor"


def verdict_color(verdict: str) -> str:
    """Return accent color for a recommendation tier string."""
    v = (verdict or "").upper()
    if "HIGH CONVICTION" in v or "ATTRACTIVE" in v:
        return ACCENT_GREEN
    if "NEUTRAL" in v:
        return ACCENT_BLUE
    if "CAUTION" in v:
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
        "padding": "2px 6px",
        "borderRadius": "3px",
        "fontSize": "11px",
        "fontWeight": "600",
        "display": "inline-block",
        "whiteSpace": "nowrap",
    }
    return {**base, **styles.get(tone, styles["neutral"])}

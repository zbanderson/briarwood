"""
Design tokens for the Briarwood investment research platform.

Analytical and premium, with a lighter, more welcoming retail-facing shell.
"""
from __future__ import annotations

from briarwood.recommendations import normalize_recommendation_label

# ── Color palette ──────────────────────────────────────────────────────────────

BRAND_NAVY = "#023E8A"
BRAND_OCEAN = "#0077B6"
BRAND_CYAN = "#90E0EF"
BRAND_PALE = "#CAF0F8"
WHITE = "#FFFFFF"
LIGHT_GRAY = "#F5F7FA"
MEDIUM_GRAY = "#6B7280"
DARK_GRAY = "#1F2937"

BG_BASE = LIGHT_GRAY
BG_SURFACE = WHITE
BG_SURFACE_2 = "#F8FBFE"
BG_SURFACE_3 = "#EEF6FB"
BG_SURFACE_4 = "#DCEEF6"

BORDER = "#D6E2EE"
BORDER_SUBTLE = "#E8EFF6"

TEXT_PRIMARY = DARK_GRAY
TEXT_SECONDARY = "#334155"
TEXT_MUTED = MEDIUM_GRAY
TEXT_LINK = BRAND_OCEAN
TEXT_INVERSE = WHITE

ACCENT_NAVY = BRAND_NAVY
ACCENT_BLUE = BRAND_OCEAN
ACCENT_CYAN = BRAND_CYAN
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

TONE_NEUTRAL_TEXT = BRAND_NAVY
TONE_NEUTRAL_BG = BRAND_PALE
TONE_NEUTRAL_BORDER = "#A9DCE9"

# ── Typography ─────────────────────────────────────────────────────────────────

FONT_FAMILY = "Inter, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif"
FONT_MONO = "'JetBrains Mono', 'SF Mono', 'Fira Code', Consolas, monospace"
FONT_DISPLAY = "'Source Serif 4', Georgia, serif"

# ── Layout ─────────────────────────────────────────────────────────────────────

TOPBAR_HEIGHT = "48px"
PROPERTY_HEADER_HEIGHT = "40px"
RADIUS_SM = "12px"
RADIUS_MD = "16px"
RADIUS_LG = "18px"
SPACE_1 = "4px"
SPACE_2 = "8px"
SPACE_3 = "12px"
SPACE_4 = "16px"
SPACE_5 = "20px"
SHADOW_SOFT = "0 10px 24px rgba(15, 23, 42, 0.05)"
SHADOW_ELEVATED = "0 16px 36px rgba(2, 62, 138, 0.08)"

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
    "backgroundImage": "linear-gradient(180deg, rgba(202,240,248,0.30) 0%, rgba(245,247,250,0.96) 18%, rgba(245,247,250,1) 100%)",
}

TOPBAR_STYLE: dict = {
    "backgroundColor": BRAND_NAVY,
    "borderBottom": f"1px solid rgba(255,255,255,0.12)",
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
    "boxShadow": "0 12px 32px rgba(2, 62, 138, 0.22)",
}

PROPERTY_HEADER_STYLE: dict = {
    "backgroundColor": "rgba(255,255,255,0.96)",
    "borderBottom": f"1px solid {BORDER}",
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
    "boxShadow": "0 8px 22px rgba(15, 23, 42, 0.05)",
}

CARD_STYLE: dict = {
    "backgroundColor": BG_SURFACE,
    "border": f"1px solid {BORDER}",
    "borderRadius": RADIUS_MD,
    "padding": "12px 14px",
    "boxShadow": SHADOW_SOFT,
}

CARD_STYLE_ELEVATED: dict = {
    "backgroundColor": BG_SURFACE,
    "border": f"1px solid {BORDER}",
    "borderRadius": RADIUS_LG,
    "padding": "14px 16px",
    "boxShadow": SHADOW_ELEVATED,
}

SECTION_HEADER_STYLE: dict = {
    "fontSize": "11px",
    "fontWeight": "700",
    "letterSpacing": "0.10em",
    "textTransform": "uppercase",
    "color": BRAND_NAVY,
    "marginBottom": "8px",
}

LABEL_STYLE: dict = {
    "fontSize": "11px",
    "fontWeight": "600",
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

# ── Display headings (editorial serif) ─────────────────────────────────────────

HEADING_XL_STYLE: dict = {
    "fontFamily": FONT_DISPLAY,
    "fontSize": "28px",
    "fontWeight": "700",
    "letterSpacing": "-0.02em",
    "lineHeight": "1.15",
    "color": BRAND_NAVY,
    "margin": "0",
}

HEADING_L_STYLE: dict = {
    "fontFamily": FONT_DISPLAY,
    "fontSize": "22px",
    "fontWeight": "600",
    "letterSpacing": "-0.01em",
    "lineHeight": "1.2",
    "color": BRAND_NAVY,
    "margin": "0",
}

HEADING_M_STYLE: dict = {
    "fontFamily": FONT_DISPLAY,
    "fontSize": "20px",
    "fontWeight": "600",
    "lineHeight": "1.25",
    "color": BRAND_NAVY,
    "margin": "0",
}

BODY_TEXT_STYLE: dict = {
    "fontSize": "13px",
    "color": TEXT_SECONDARY,
    "lineHeight": "1.65",
}

MONO_STYLE: dict = {
    "fontFamily": FONT_MONO,
    "fontSize": "12px",
    "color": TEXT_SECONDARY,
}

# ── Button styles ──────────────────────────────────────────────────────────────

BTN_PRIMARY: dict = {
    "backgroundColor": ACCENT_BLUE,
    "color": WHITE,
    "border": "none",
    "borderRadius": RADIUS_SM,
    "padding": "8px 14px",
    "fontSize": "13px",
    "fontWeight": "600",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
    "whiteSpace": "nowrap",
    "boxShadow": "0 10px 20px rgba(0, 119, 182, 0.24)",
}

BTN_SECONDARY: dict = {
    "backgroundColor": BG_SURFACE,
    "color": TEXT_SECONDARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": RADIUS_SM,
    "padding": "7px 12px",
    "fontSize": "13px",
    "fontWeight": "500",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
    "whiteSpace": "nowrap",
}

BTN_GHOST: dict = {
    "backgroundColor": "transparent",
    "color": BRAND_PALE,
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
    "borderRadius": RADIUS_SM,
    "padding": "8px 10px",
    "fontSize": "13px",
    "fontFamily": FONT_FAMILY,
    "width": "100%",
    "boxSizing": "border-box",
    "outline": "none",
    "boxShadow": "inset 0 1px 2px rgba(2, 62, 138, 0.04)",
}

# ── Responsive grid helpers ────────────────────────────────────────────────────

GRID_2: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))", "gap": "8px"}
GRID_3: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "8px"}
GRID_4: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(160px, 1fr))", "gap": "8px"}
GRID_5: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(140px, 1fr))", "gap": "8px"}

# ── Plotly light theme base ────────────────────────────────────────────────────

PLOTLY_LAYOUT: dict = {
    "paper_bgcolor": BG_SURFACE,
    "plot_bgcolor": LIGHT_GRAY,
    "font": {"color": TEXT_PRIMARY, "family": FONT_FAMILY, "size": 12},
    "title": {"font": {"color": TEXT_PRIMARY, "family": FONT_DISPLAY, "size": 16}},
    "margin": {"l": 44, "r": 16, "t": 22, "b": 32},
    "xaxis": {
        "gridcolor": "#E6EEF6",
        "linecolor": BORDER,
        "tickcolor": TEXT_MUTED,
        "tickfont": {"color": TEXT_MUTED, "size": 11},
        "showgrid": True,
        "zeroline": False,
    },
    "yaxis": {
        "gridcolor": "#E6EEF6",
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
    "padding": "8px 10px",
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
    "padding": "8px 10px",
}

TABLE_STYLE_DATA_ODD: dict = {
    "backgroundColor": BG_SURFACE,
}

TABLE_STYLE_DATA_EVEN: dict = {
    "backgroundColor": BG_SURFACE_2,
}

TABLE_STYLE_TABLE: dict = {
    "overflowX": "auto",
    "borderRadius": RADIUS_MD,
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
        return ACCENT_BLUE
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
        return ACCENT_BLUE
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
        "padding": "4px 9px",
        "borderRadius": "999px",
        "fontSize": "10px",
        "fontWeight": "600",
        "display": "inline-block",
        "whiteSpace": "nowrap",
        "letterSpacing": "0.01em",
    }
    return {**base, **styles.get(tone, styles["neutral"])}

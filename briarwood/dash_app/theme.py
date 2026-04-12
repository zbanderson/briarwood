"""
Design tokens for the Briarwood investment research platform.

Modern, confident, Brookfield-inspired aesthetic.
Dark slate background with warm accent palette.
"""
from __future__ import annotations

from briarwood.recommendations import normalize_recommendation_label

# ── Color palette ──────────────────────────────────────────────────────────────

# Primary backgrounds
BG_PRIMARY = "#1B2A3D"      # deep slate blue — main background
BG_SECONDARY = "#243447"    # slightly lighter slate for cards/sections
BG_SURFACE = "#2C3E50"      # elevated surfaces
BG_LIGHT = "#F5F6F8"        # for light-mode cards if needed

# Text colors
TEXT_PRIMARY = "#FFFFFF"     # bold headlines on dark
TEXT_SECONDARY = "#94A3B8"   # muted labels, supporting text
TEXT_TERTIARY = "#64748B"    # least important text
TEXT_INVERSE = "#1B2A3D"     # dark text on light backgrounds

# Accent colors — color means something, not decoration
ACCENT_GREEN = "#22C55E"    # positive signals, Buy, bullish
ACCENT_AMBER = "#F59E0B"    # Watch, caution, medium risk
ACCENT_RED = "#EF4444"      # Avoid/Pass, high risk, bearish
ACCENT_BLUE = "#3B82F6"     # neutral highlights, links, interactive

# Borders & dividers
BORDER = "#334155"           # subtle, doesn't scream
BORDER_SUBTLE = "#1E293B"   # very subtle dividers

# Shadows
SHADOW_SOFT = "0 1px 3px rgba(0,0,0,0.2)"
SHADOW_ELEVATED = "0 4px 12px rgba(0,0,0,0.3)"

# Tone system — semantic meaning through color
TONE_POSITIVE_TEXT = ACCENT_GREEN
TONE_POSITIVE_BG = "rgba(34, 197, 94, 0.12)"
TONE_POSITIVE_BORDER = "rgba(34, 197, 94, 0.25)"

TONE_WARNING_TEXT = ACCENT_AMBER
TONE_WARNING_BG = "rgba(245, 158, 11, 0.12)"
TONE_WARNING_BORDER = "rgba(245, 158, 11, 0.25)"

TONE_NEGATIVE_TEXT = ACCENT_RED
TONE_NEGATIVE_BG = "rgba(239, 68, 68, 0.12)"
TONE_NEGATIVE_BORDER = "rgba(239, 68, 68, 0.25)"

TONE_NEUTRAL_TEXT = ACCENT_BLUE
TONE_NEUTRAL_BG = "rgba(59, 130, 246, 0.12)"
TONE_NEUTRAL_BORDER = "rgba(59, 130, 246, 0.25)"

# ── Backwards compat aliases (old names → new values) ─────────────────────────

BRAND_NAVY = BG_PRIMARY
BRAND_OCEAN = ACCENT_BLUE
BRAND_CYAN = "#90E0EF"
BRAND_PALE = "rgba(59, 130, 246, 0.08)"
WHITE = "#FFFFFF"
LIGHT_GRAY = BG_PRIMARY
MEDIUM_GRAY = TEXT_TERTIARY
DARK_GRAY = TEXT_PRIMARY

BG_BASE = BG_PRIMARY
BG_SURFACE_2 = BG_SECONDARY
BG_SURFACE_3 = BG_SURFACE
BG_SURFACE_4 = "#354B63"

ACCENT_NAVY = BG_PRIMARY
ACCENT_CYAN = ACCENT_BLUE
ACCENT_YELLOW = ACCENT_AMBER
ACCENT_ORANGE = "#F97316"
ACCENT_TEAL = "#14B8A6"

TEXT_LINK = ACCENT_BLUE
TEXT_MUTED = TEXT_TERTIARY

# ── Typography ─────────────────────────────────────────────────────────────────

FONT_FAMILY = "'Plus Jakarta Sans', 'DM Sans', Inter, -apple-system, BlinkMacSystemFont, sans-serif"
FONT_DISPLAY = "'Plus Jakarta Sans', 'DM Sans', Inter, sans-serif"
FONT_MONO = "'JetBrains Mono', 'SF Mono', 'Fira Code', Consolas, monospace"

# ── Spacing ────────────────────────────────────────────────────────────────────

SPACE_XS = "4px"
SPACE_SM = "8px"
SPACE_MD = "16px"
SPACE_LG = "24px"
SPACE_XL = "32px"
SPACE_XXL = "48px"

# Compat aliases
SPACE_1 = SPACE_XS
SPACE_2 = SPACE_SM
SPACE_3 = "12px"
SPACE_4 = SPACE_MD
SPACE_5 = "20px"

# ── Radii ──────────────────────────────────────────────────────────────────────

RADIUS_SM = "6px"
RADIUS_MD = "8px"
RADIUS_LG = "12px"
RADIUS_XL = "16px"

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
    "backgroundColor": BG_PRIMARY,
    "color": TEXT_PRIMARY,
    "minHeight": "100vh",
    "lineHeight": "1.5",
    "fontSize": "14px",
}

TOPBAR_STYLE: dict = {
    "backgroundColor": BG_PRIMARY,
    "borderBottom": f"1px solid {BORDER}",
    "padding": "0 24px",
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
    "backgroundColor": BG_SECONDARY,
    "borderBottom": f"1px solid {BORDER}",
    "padding": "8px 24px",
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
    "backgroundColor": BG_SECONDARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": RADIUS_LG,
    "padding": "24px",
    "boxShadow": SHADOW_SOFT,
}

CARD_STYLE_ELEVATED: dict = {
    "backgroundColor": BG_SECONDARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": RADIUS_LG,
    "padding": "28px 32px",
    "boxShadow": SHADOW_ELEVATED,
}

SECTION_HEADER_STYLE: dict = {
    "fontSize": "11px",
    "fontWeight": "700",
    "letterSpacing": "0.10em",
    "textTransform": "uppercase",
    "color": TEXT_SECONDARY,
    "marginBottom": "12px",
}

LABEL_STYLE: dict = {
    "fontSize": "11px",
    "fontWeight": "600",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
    "color": TEXT_TERTIARY,
    "marginBottom": "4px",
}

VALUE_STYLE_LARGE: dict = {
    "fontSize": "20px",
    "fontWeight": "700",
    "fontFamily": FONT_MONO,
    "letterSpacing": "-0.02em",
    "lineHeight": "1.2",
}

VALUE_STYLE_MEDIUM: dict = {
    "fontSize": "16px",
    "fontWeight": "600",
    "fontFamily": FONT_MONO,
    "letterSpacing": "-0.01em",
}

# ── Display headings ──────────────────────────────────────────────────────────

HEADING_XL_STYLE: dict = {
    "fontFamily": FONT_DISPLAY,
    "fontSize": "32px",
    "fontWeight": "800",
    "letterSpacing": "-0.02em",
    "lineHeight": "1.15",
    "color": TEXT_PRIMARY,
    "margin": "0",
}

HEADING_L_STYLE: dict = {
    "fontFamily": FONT_DISPLAY,
    "fontSize": "24px",
    "fontWeight": "700",
    "letterSpacing": "-0.01em",
    "lineHeight": "1.2",
    "color": TEXT_PRIMARY,
    "margin": "0",
}

HEADING_M_STYLE: dict = {
    "fontFamily": FONT_DISPLAY,
    "fontSize": "20px",
    "fontWeight": "600",
    "lineHeight": "1.25",
    "color": TEXT_PRIMARY,
    "margin": "0",
}

BODY_TEXT_STYLE: dict = {
    "fontSize": "14px",
    "color": TEXT_SECONDARY,
    "lineHeight": "1.6",
}

MONO_STYLE: dict = {
    "fontFamily": FONT_MONO,
    "fontSize": "13px",
    "color": TEXT_SECONDARY,
}

# ── Button styles ──────────────────────────────────────────────────────────────

BTN_PRIMARY: dict = {
    "backgroundColor": ACCENT_BLUE,
    "color": WHITE,
    "border": "none",
    "borderRadius": RADIUS_MD,
    "padding": "10px 20px",
    "fontSize": "14px",
    "fontWeight": "600",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
    "whiteSpace": "nowrap",
    "boxShadow": "0 2px 8px rgba(59, 130, 246, 0.3)",
}

BTN_SECONDARY: dict = {
    "backgroundColor": BG_SURFACE,
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": RADIUS_MD,
    "padding": "10px 20px",
    "fontSize": "14px",
    "fontWeight": "500",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
    "whiteSpace": "nowrap",
}

BTN_GHOST: dict = {
    "backgroundColor": "transparent",
    "color": TEXT_SECONDARY,
    "border": "none",
    "borderRadius": RADIUS_MD,
    "padding": "8px 14px",
    "fontSize": "13px",
    "fontWeight": "500",
    "cursor": "pointer",
    "fontFamily": FONT_FAMILY,
}

# ── Input styles ───────────────────────────────────────────────────────────────

INPUT_STYLE: dict = {
    "backgroundColor": BG_SURFACE,
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER}",
    "borderRadius": RADIUS_MD,
    "padding": "10px 12px",
    "fontSize": "14px",
    "fontFamily": FONT_FAMILY,
    "width": "100%",
    "boxSizing": "border-box",
    "outline": "none",
}

# ── Responsive grid helpers ────────────────────────────────────────────────────

GRID_2: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(240px, 1fr))", "gap": "16px"}
GRID_3: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))", "gap": "16px"}
GRID_4: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "16px"}
GRID_5: dict = {"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(160px, 1fr))", "gap": "16px"}

# ── Plotly dark theme base ────────────────────────────────────────────────────

PLOTLY_LAYOUT: dict = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": TEXT_SECONDARY, "family": FONT_FAMILY, "size": 12},
    "title": {"font": {"color": TEXT_PRIMARY, "family": FONT_DISPLAY, "size": 16}},
    "margin": {"l": 48, "r": 16, "t": 24, "b": 36},
    "xaxis": {
        "gridcolor": BORDER,
        "linecolor": BORDER,
        "tickcolor": TEXT_TERTIARY,
        "tickfont": {"color": TEXT_TERTIARY, "family": FONT_MONO, "size": 11},
        "showgrid": True,
        "zeroline": False,
    },
    "yaxis": {
        "gridcolor": BORDER,
        "linecolor": BORDER,
        "tickcolor": TEXT_TERTIARY,
        "tickfont": {"color": TEXT_TERTIARY, "family": FONT_MONO, "size": 11},
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
    "margin": {"l": 36, "r": 8, "t": 12, "b": 28},
}

# ── DataTable dark theme ──────────────────────────────────────────────────────

TABLE_STYLE_CELL: dict = {
    "backgroundColor": BG_SECONDARY,
    "color": TEXT_PRIMARY,
    "border": f"1px solid {BORDER}",
    "padding": "10px 12px",
    "fontFamily": FONT_FAMILY,
    "fontSize": "14px",
    "textAlign": "left",
}

TABLE_STYLE_HEADER: dict = {
    "backgroundColor": BG_SURFACE,
    "color": TEXT_SECONDARY,
    "fontWeight": "600",
    "fontSize": "11px",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
    "border": f"1px solid {BORDER}",
    "padding": "10px 12px",
}

TABLE_STYLE_DATA_ODD: dict = {
    "backgroundColor": BG_SECONDARY,
}

TABLE_STYLE_DATA_EVEN: dict = {
    "backgroundColor": BG_PRIMARY,
}

TABLE_STYLE_TABLE: dict = {
    "overflowX": "auto",
    "borderRadius": RADIUS_LG,
    "border": f"1px solid {BORDER}",
    "overflowY": "hidden",
}

# ── Jargon → plain English mapping ───────────────────────────────────────────

JARGON_MAP: dict[str, str] = {
    "ISR": "Income coverage",
    "PPSF": "Price per sqft",
    "DSCR": "Debt coverage",
    "PTR": "Price to rent",
    "BCV": "Fair value",
    "DOM": "Days on market",
    "NOI": "Net income",
    "Cap Rate": "Return rate",
    "Cash-on-Cash": "Cash return",
    "Gross Yield": "Rental yield",
    "Rental Ease": "How easy to rent",
    "Optionality": "Upside potential",
    "Risk Skew": "Risk profile",
    "Liquidity Profile": "How easy to sell",
    "Entry Basis": "How it's priced",
    "CapEx Load": "Renovation cost",
    "Income Support": "Can rent cover the cost?",
}


def dejargon(label: str) -> str:
    """Replace jargon with plain English. Returns original if no match."""
    return JARGON_MAP.get(label, label)


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
        return ACCENT_AMBER
    return ACCENT_RED


def score_label(score: float) -> str:
    """Return human-readable label for a 1-5 score value."""
    if score >= 4.5:
        return "Strong"
    if score >= 4.0:
        return "Supported"
    if score >= 3.0:
        return "Mixed"
    if score >= 2.0:
        return "Thin"
    return "Weak"


def verdict_color(verdict: str) -> str:
    """Return accent color for a recommendation tier string."""
    v = normalize_recommendation_label(verdict)
    if v == "Buy":
        return ACCENT_GREEN
    if v == "Neutral":
        return ACCENT_AMBER
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
        "padding": "4px 10px",
        "borderRadius": "999px",
        "fontSize": "11px",
        "fontWeight": "600",
        "display": "inline-block",
        "whiteSpace": "nowrap",
        "letterSpacing": "0.02em",
    }
    return {**base, **styles.get(tone, styles["neutral"])}


def risk_dot(level: str, *, count: int | None = None) -> str:
    """Return styled dot indicator for risk level. Replaces emoji."""
    if count is None:
        count = {"Low": 1, "Medium": 2, "High": 3}.get(level, 2)
    return "●" * count

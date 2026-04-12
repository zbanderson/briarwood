# UI Refactor Log

## Design System

| Element | Before | After |
|---------|--------|-------|
| Background | White (#FFFFFF) | Deep Slate (#1B2A3D) |
| Cards | Light gray borders | Elevated dark surface (#2C3E50) |
| Heading font | Inter | Plus Jakarta Sans |
| Mono font | Source Serif 4 | JetBrains Mono |
| Risk indicators | Emoji (✓ ⚠ 🎯) | Colored dots (risk_dot()) |
| Accent positive | Various greens | #22C55E |
| Accent warning | Various ambers | #F59E0B |
| Accent negative | Hardcoded #7c1f1f | #EF4444 |
| Accent interactive | Mixed | #3B82F6 |

## Sections Killed / Merged

| Section | Action | Reason |
|---------|--------|--------|
| Default tear sheet as landing | Replaced | Simple view (5 cards) is now default |
| Metric strips on simple view | Hidden | Progressive disclosure — only in full analysis |
| Jump links on simple view | Removed | Not needed with card-based layout |
| Category scoring breakdowns | Hidden | Only in full analysis via "View Full Analysis" |
| Evidence chips on simple view | Hidden | Noise for quick decisions |
| Essay-length text blocks | Truncated | Simple view shows primary_reason + secondary_reason only |

## Jargon Terms Replaced

| Old Term | New Term | Files |
|----------|----------|-------|
| BCV | Fair Value | components.py, theme.py |
| DSCR | Debt Coverage | components.py, theme.py |
| PTR | Price to Rent | components.py, theme.py |
| DOM | Days Listed | components.py, theme.py |
| Cash-on-Cash | Cash Return | components.py, theme.py |
| Gross Yield | Rental Yield | components.py, theme.py |
| ISR | Income Coverage | theme.py |
| PPSF | Price per sqft | theme.py |
| NOI | Net Operating Income | theme.py |
| GRM | Gross Rent Multiple | theme.py |
| LTV | Loan to Value | theme.py |
| CoC | Cash Return | theme.py |
| CapEx | Capital Expense | theme.py |
| Absorption | Market Speed | theme.py |
| Basis | Total Cost | theme.py |
| Imputed | Estimated | theme.py |
| Amortization | Loan Paydown | theme.py |

## New Components Created

| Component | File | Purpose |
|-----------|------|---------|
| render_simple_view() | simple_view.py | Main 5-card decision view |
| _render_toggle() | simple_view.py | Homebuyer/Investor role toggle |
| _render_property_header() | simple_view.py | Address + specs + asking price |
| _render_decision_hero() | simple_view.py | Recommendation + conviction + reason |
| _render_risk_check() | simple_view.py | 5-category risk rows with colored dots |
| _render_value_card() | simple_view.py | Value finder bullets |
| _render_monthly_reality() | simple_view.py | Cost/rent/net monthly summary |
| _render_action_buttons() | simple_view.py | 3 Layer 2 navigation buttons |
| render_price_support() | simple_view.py | Layer 2: waterfall + comps + forward chart |
| render_financials() | simple_view.py | Layer 2: cost table + income waterfall |
| render_scenarios() | simple_view.py | Layer 2: scenario cards + outlook chart |
| _build_value_waterfall() | simple_view.py | Value bridge row builder |
| _back_button() | simple_view.py | Return to simple view |

## Charts Restyled

| Chart | Change |
|-------|--------|
| Heatmap colorscale | Updated to new accent palette (#EF4444 through #22C55E) |
| Stress scenario line | #7c1f1f -> #EF4444 |
| All Plotly charts | PLOTLY_LAYOUT updated: transparent bg, dark gridlines (#334155), JetBrains Mono axis text |

## Before / After Component Count (Property View)

| Metric | Before | After |
|--------|--------|-------|
| Default view cards | ~15+ sections | 5 cards + 3 action buttons |
| Layer 2 screens | 0 | 3 (price support, financials, scenarios) |
| Full analysis | Still available | Via "View Full Analysis" button |

## Callbacks Added

| Callback | Purpose |
|----------|---------|
| handle_simple_view_action | Routes action button clicks -> property-view-screen store |
| handle_role_toggle | Switches user-role store (homebuyer/investor) |
| render_main_tab (updated) | Screen-based routing for tear_sheet tab |

## dcc.Store Added

| Store ID | Type | Purpose |
|----------|------|---------|
| property-view-screen | memory | Tracks current screen (simple/price_support/financials/scenarios/full) |
| user-role | localStorage | Persists homebuyer/investor toggle |

## Issues Found and Fixed

1. `ValueBridgeStepViewModel.value` -> `.value_text` (field name mismatch in _build_value_waterfall)
2. `forward_fan_chart(report)` -> `forward_fan_chart(view)` (wrong argument type, expects PropertyAnalysisView)
3. `income_carry_waterfall(report)` -> `income_carry_waterfall(view, report)` (missing first argument)

## Validation

- All 5 test properties render all 4 views without errors
- 13 existing UI tests pass
- App initializes successfully

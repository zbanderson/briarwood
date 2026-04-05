# Briarwood UX Assessment

**Date:** April 5, 2026
**Scope:** Full UI/UX audit of the Briarwood Investment Research Platform
**Files reviewed:** app.py, components.py, compare.py, view_models.py, theme.py, lens_scoring.py, scoring.py, workspace.css, pdf_renderer.py, tear_sheet.html template, saved property data

---

## 1. What's Working Well (Preserve These)

### Design System & Visual Language
The dark theme is **well-executed and consistent**. The design token system in `theme.py` is clean and comprehensive — 5 surface levels (`BG_BASE` through `BG_SURFACE_4`), semantic tone colors (positive/warning/negative/neutral), and a proper typographic scale. The Bloomberg-terminal aesthetic is authentic without being austere. This is one of the strongest aspects of the platform.

### Question-Based Tear Sheet Structure
The 5 question headers ("Is This a Good Price?", "Can I Afford to Hold It?", etc.) are **excellent framing** for the decision narrative. They turn analytical sections into answers the user actually wants. The collapsible `<details>` pattern with answer text visible in the collapsed state is a smart density optimization — users can scan all 5 answers without expanding anything.

### Score Header Card
The score header (`render_score_header`) is well-composed: score with dots, recommendation tier badge, confidence level badge, calibrated narrative, and expandable category mini-bars. The expandable category drill-down (added recently) addresses Gap 4 from the audit — users can now click category bars to see sub-factors, "What this means" summaries, and component breakdowns. This is working.

### Metric Strip Pattern
The `inline_metric_strip()` pattern used across all sections is excellent — compact, scannable, consistent. Each metric has a label, value, and optional sublabel. This is the right level of density for the target user.

### Evidence & Confidence Layer
The recently-added confidence system is solid:
- Global `confidence_level_badge()` with hover tooltip showing 4 data quality factors
- Per-section `section_confidence_indicator()` with colored dots and percentage
- Low-confidence sections get a visual red left border (`section-low-confidence`)
- "Improve This Analysis" block with actionable missing input suggestions
- Calibrated narrative prefixes for Medium/Low confidence

### Perspective Block
The `render_perspective_block()` is a good first pass at surfacing lens scores — hero card for best lens, compact badges for others, category breakdown bars. The data model (`LensScores`, `LensDetail`) is rich enough to support a full lens selector redesign.

### What-If Slider
The `render_what_if_slider()` for ask price sensitivity is a good interactive element — it adjusts BCV gap, PTR, estimated mortgage, and cash flow in real-time. This is the kind of interactivity the platform needs more of.

### Owner/Realtor Toggle
The dual-mode tear sheet (owner vs. realtor) is a unique and valuable feature. The realtor mode reframes risks as "buyer talking points" and objection handlers. This is a genuine product differentiator.

### Feedback Banner System
The post-analysis feedback banner with "missing core values" warnings and "Review & Update" button is well-designed — it catches data gaps immediately after analysis without being intrusive.

---

## 2. Information Hierarchy Issues

### Issue H1: Sticky Header Is Missing Critical Decision Context
**Severity: High | Location: `app.py:1046-1073`**

The sticky property header shows: Address, Basics (bd/ba/sf/town), Ask, BCV, Gap%, Base, Score, and Recommendation Tier.

**Missing from the header:**
- **Risk level** — The audit's top finding. A user can see "4.2 / Strong Buy" without knowing risk is elevated. Risk is what differentiates Briarwood from every other tool, yet it has no persistent presence.
- **Net monthly burn** — The #2 question after "Should I buy this?" is "What does this cost me monthly?" This number is buried in section 2 behind a collapsible section.
- **Confidence level** — The global confidence badge exists in the score header card but NOT in the sticky property header. A user scrolling past the score header loses all confidence context.

**Current header height:** 40px. There is room for 2-3 more compact metrics without increasing height, using the existing `_header_metric()` pattern.

### Issue H2: Risk Is a Mid-Tier Section, Not a First-Class Signal
**Severity: High | Location: `components.py:3260-3285`**

Risk is the 4th of 5 question sections. In the owner view, it's positioned after Price, Economics, and Forward sections. For many properties — especially those where Briarwood would flag caution — risk should be the first thing the user sees after the score header.

The risk section itself is well-built (risk bars chart, stress case metrics, liquidity/momentum signals). The problem is purely positional: it doesn't have persistent visibility.

### Issue H3: Monthly Net Burn Requires Scrolling to Section 2
**Severity: Medium | Location: `components.py:3209-3235`**

The economics section contains the monthly cash flow number but it's inside a collapsible section. For buyers and owner-occupants, this number is as fundamental as the price. It should be surfaceable without any scrolling.

### Issue H4: Decision Summary Placement
**Severity: Medium | Location: `components.py:3398-3413`**

The tear sheet flow in owner mode is:
1. View toggle (owner/realtor)
2. Decision engine block (score header)
3. Decision summary block
4. "YOUR QUESTIONS" header
5. Five question sections
6. "MORE CONTEXT" header
7. Optionality, Market, Perspective, What-If, Evidence sections
8. Decision close

The decision answer (score + recommendation) appears at the top — good. But the decision *summary* block with thesis, risks, and supporting factors is just below the score, competing for attention with the question sections that follow. Consider whether a condensed "verdict strip" at the top plus full summary at the bottom (after evidence) would create better flow.

### Issue H5: Investor Metrics (DSCR, Cash-on-Cash, Gross Yield) Are Correctly Placed but Not Lens-Aware
**Severity: Low | Location: `components.py:3199-3206`**

The investor metrics strip in the economics section is well-implemented — it only renders when data exists, it uses the `inline_metric_strip` pattern, and DSCR has a tone sublabel. However, these metrics are always visible regardless of whether the user cares about rental income. When a lens selector is added, these should be promoted/demoted based on the selected lens.

---

## 3. Interaction Model Gaps

### Gap G1: No Rate Sensitivity Control
**Severity: High | Effort: Medium**

The what-if slider adjusts ask price, but there's no way to adjust mortgage rate. The `render_what_if_metrics()` function hardcodes `0.07` (7%) and `0.80` (80% LTV). For buyers, the difference between 6.5% and 7.5% can change monthly cost by hundreds of dollars and flip a "manageable carry" into "negative cash flow."

**Recommendation:** Add a rate slider (5.0%–9.0%, step 0.25%) alongside the existing ask price slider in the what-if section. Both should update the same output panel. The view model already carries the financing inputs; the recalculation is simple mortgage math.

### Gap G2: No Vacancy Rate Toggle
**Severity: Medium | Effort: Low**

For seasonal/coastal properties (which Belmar, the primary market, IS), vacancy dramatically affects true cost. The `coastal_profile_label` field exists in the view model but there's no way to adjust vacancy assumptions. A simple dropdown (5%/10%/15%/Seasonal 40%) in the economics section would let users see the impact.

### Gap G3: Comps Are Not Interactive
**Severity: Medium | Effort: Medium**

The `comp_positioning_dot_plot()` renders SVG dots on a chart, but they're static. Users can see where their property sits relative to comps but can't click a dot to see which comp it represents, its address, sale price, or adjustments. The comp data exists in `CompsViewModel.rows` — it just needs to be connected to click events.

**Note:** This is harder in Plotly Dash than in React. The best approach is likely `dcc.Graph` click events with a callback that updates a comp detail panel below the chart.

### Gap G4: Category Scores Now Expand (Fixed)
This was flagged in the audit but has been resolved. The `_render_category_mini_bars` function now uses `html.Details` with sub-factor breakdowns, component bars, and "What this means" summaries. ✅

### Gap G5: No Hold Period Selector
**Severity: Medium | Effort: Medium**

The forward section shows bull/base/bear values but there's no way to adjust the hold period. The tear sheet assumes a default hold horizon. Adding a 3/5/7/10 year selector that adjusts the forward projections would be the second most impactful interactive element after the rate slider.

### Gap G6: Compare Tab Lacks Winner Signal (Partially Fixed)
**Severity: High | Effort: Medium**

A `compare_winner_banner()` now exists and shows Top Ranked, Runner Up, and Main Reason. This is a good start. But the banner is thin — it shows the score leader and one reason, without addressing the specific trade-offs that make comparison useful. See Section 4 below.

---

## 4. Compare View Assessment

The compare view is the **weakest area of the platform**. It has 4 display modes (heatmap, radar, table, detail) but the experience is shallow.

### What Exists
- **Winner banner:** Shows top-ranked property by score, runner-up, and a single "main reason" (`compare_winner_banner`)
- **Score heatmap:** Category-by-property color grid (`score_comparison_heatmap`)
- **Ranking table:** DataTable with Final/Price/Income/Optionality/Market/Risk columns (`property_ranking_table`)
- **Radar chart:** 2-property category radar (`category_comparison_radar`)
- **Detail mode:** Side-by-side lanes showing same section for each property (`render_compare_section`)
- **"Why Different" notes:** Up to 8 difference bullets from `_build_difference_notes`

### What's Missing

**4a. No Relative Framing**
Every metric shows absolute values only. When comparing Ask $850K vs $750K, the user has to mentally compute "+$100K (13.3%)". The `_format_compare_value` function in `compare.py` formats values but never shows deltas. Every row in the comparison should show the absolute value AND the relative difference from the best/worst/anchor.

**4b. No Winner-Per-Metric Indicators**
The ranking table highlights the top-ranked row but doesn't indicate which property "wins" each individual metric. Users should be able to scan vertically and see patterns: "Property A wins on value and risk, Property B wins on income and momentum."

**4c. No Trade-Off Narrative**
The "Why Different" notes are mechanical: "biggest input gap is X" and "confidence differs by Y%." There's no synthesized narrative like: "Property A costs more but offers lower risk and higher forward return. Property B is the value play with more renovation upside." This is the single most valuable thing the compare view could add.

**4d. No Scenario Overlay**
Each property's bull/base/bear is shown independently in detail mode. There's no way to see all properties' scenario ranges on a single chart — "in the bull case, A ends up at $1.2M and B at $950K; in the bear case, they converge at $700K."

**4e. Compare Controls Are Fragmented**
The compare flow requires: select properties in dropdown → click "Go" → pick a mode → optionally pick a section. The "OK to confirm" step (`compare-confirmed-ids`) adds friction. And the section dropdown only applies to "Detail" mode but is always visible.

---

## 5. Property Manager Assessment

**Location: `app.py:534-840`**

### Current State
The property manager is a **right-side drawer** with:
1. **Saved Properties table** — browse/select/edit existing properties
2. **Comp Database table** — pull properties from the comp database
3. **New Property Analysis form** — 40+ fields across 6 groups:
   - Subject Property (address, price, town/state/county, beds/baths/sqft, property ID)
   - Property Details (lot, year built, DOM, taxes, HOA, type, condition, capex)
   - Physical Features (garage, ADU, basement, pool, parking, lot features)
   - Income & Carry (rents, insurance, maintenance)
   - Notes (textarea)
   - Manual Comps (address, price, date, beds/baths/sqft, lot, year, distance, type, condition, notes)

### Issues
- **All fields are visible at once.** There's no progressive disclosure. A first-time user sees 40+ fields and has to figure out which matter.
- **The minimum viable analysis requires ~8 fields** (address, price, town, state, beds, baths, sqft, property type), but this isn't communicated visually. There's a "required dot" on the Subject Property group but optional groups look identical.
- **Physical Features is rarely impactful.** Garage spaces, pool, and driveway don't meaningfully change the analysis for most properties. These could be hidden behind a "More details" expander.
- **Manual Comps are complex.** Each comp has 10 fields. This is a power-user feature that should be collapsed by default.
- **The form doesn't pre-fill intelligently.** Town/State/County default to Belmar/NJ/Monmouth (hardcoded), which helps for the current user but isn't scalable.
- **No "quick add" path.** The fastest way to get an analysis should be: paste an address + price, click analyze. Everything else should be progressive.

---

## 6. Lens System Assessment

### Current UI State
**Location: `components.py:2730, 3163`**

The tear sheet has a **view mode toggle** between "Owner" and "Realtor" (`_tear_sheet_view_toggle`). This is stored in `tear-sheet-view-mode` (localStorage) and defaults to "owner."

The `render_perspective_block()` shows all 4 lens scores (Owner, Investor, Developer, Risk) with a "BEST FOR" hero card and compact badges for the other lenses. But this block is **informational only** — selecting a different lens doesn't change anything else on the page.

### Data Model
The `LensScores` dataclass is well-designed:
- `risk_score` + `risk_narrative` (universal)
- `investor_score` + `investor_narrative` + `investor_detail` (LensDetail with components, verdicts)
- `owner_score` + `owner_narrative` + `owner_detail`
- `developer_score` + `developer_narrative` + `developer_detail`
- `recommended_lens` + `recommendation_reason`

Each `LensDetail` contains component-level scores, verdicts, and a recommendation. This is rich enough to drive a full lens-aware UI.

### Mismatch
The Owner/Realtor toggle and the 4-lens system are **two different concepts** that overlap confusingly:
- "Owner" view mode is about **presentation framing** (direct questions vs. client-facing reframes)
- "Owner" lens is about **scoring weights** (location + appreciation + scarcity)

A user who is an investor would select the "Owner" view (because they want direct analysis, not realtor talk) but the "Investor" lens (because they care about cash flow). These should be decoupled:
1. **Lens selector** → changes which metrics are promoted, how sections are ordered, and which lens recommendation is shown
2. **Presentation mode** → changes language framing (owner: "What could go wrong?" vs. realtor: "Risks / Things To Be Aware Of")

---

## 7. Visual Design Observations

### Typography
- **Primary font:** Inter / SF Pro Display (sans-serif) — excellent choice for data-dense UI
- **Monospace:** JetBrains Mono — used for `MONO_STYLE` but rarely applied
- **Base size:** 13px — appropriate for desktop data density
- **Label size:** 11px uppercase with letter-spacing — clean, consistent
- **Section headers:** 11-12px, 600 weight, uppercase, 0.08-0.12em tracking — Bloomberg-appropriate
- **Score values:** 28px for main score, 18px for large values, 15px for medium — good hierarchy

### Color Usage
- **Score coloring** (`score_color`): Green ≥4.0, Yellow ≥3.0, Orange ≥2.0, Red <2.0 — standard and clear
- **Tone system:** Well-structured with text, background, and border for each tone — consistent across badges, cards, and charts
- **Link/accent:** `#58a6ff` (blue) — used for active tab borders, buttons, and interactive elements
- **Low-confidence treatment:** Red left border at 50% opacity (`#f8514999`) + 0.92 opacity — subtle but noticeable

### Spacing
- **Card padding:** 10-12px — tight, appropriate for density
- **Section gaps:** 8-12px between cards — consistent
- **Page padding:** 16px vertical, 20px horizontal — reasonable
- **Grid gaps:** 6-8px for metric grids, 12-16px for section grids — consistent

### Consistency Issues
- **Border radius:** Cards use 4px, drawer modal uses 10px, badges use 3px, recommendation pill uses 999px. The 10px on the drawer feels out of place.
- **Font size proliferation:** 9px (header metric labels), 10px (some sublabels), 11px (labels/headers), 12px (what-if note), 13px (body), 14px (section answers), 15px (medium values), 16px (dots), 18px (large values), 24px (lens score), 28px (main score). This is 10 distinct sizes — could be tightened to 6-7.
- **Padding inconsistency:** Cards use `10px 12px`, question sections use `14px 18px` for header and `0 18px 18px` for body, drawer cards use `14px 16px`. These should be standardized.

---

## 8. Tear Sheet Flow Assessment

### Current Order (Owner Mode)
1. View toggle (owner/realtor)
2. Decision engine block (score header with recommendation)
3. Decision summary (thesis, risks, supporting factors)
4. **"YOUR QUESTIONS"**
5. "Is This a Good Price?" — value, comps, positioning
6. "Can I Afford to Hold It?" — income, carry, cash flow
7. "What Happens If I Buy It?" — bull/base/bear scenarios
8. "What Could Go Wrong?" — risk, liquidity, stress case
9. **"MORE CONTEXT"**
10. "What Is the Hidden Upside or Constraint?" — optionality, renovation, scarcity
11. Market Position (category section)
12. Perspective block (lens scores)
13. What-If slider
14. Evidence section
15. Decision close

### Assessment
- **Score + recommendation at the top is correct.** Answer first, evidence second.
- **The 5-question ordering is logical** but could be debated. The current flow is: Value → Affordability → Forward → Risk → Upside. An alternative would be: Value → Risk → Affordability → Forward → Upside (risk-first after value). For cautious investors, knowing risk early matters.
- **"What Is the Hidden Upside or Constraint?" is unclear as a header.** "Constraint" dilutes the upside focus. Recommendation: rename to "Where's the Upside?" — shorter, clearer, more action-oriented.
- **The "MORE CONTEXT" section break creates an odd hierarchy.** Optionality is a core section but it's pushed below the fold under a secondary header. If it's important enough to be one of the 5 questions, it should be with the other 4.
- **Market Position, Perspective, and What-If are orphaned.** They sit between the question sections and the evidence section without clear framing. Consider grouping them under "DEEPER ANALYSIS" or integrating them into the question sections they support.
- **The decision close at the bottom mirrors the score header at the top.** This is a good bookend pattern — start with the answer, end with the answer. Keep this.

---

## 9. PDF Assessment

### Current Implementation
The PDF renderer (`pdf_renderer.py`) injects print-specific CSS into the existing HTML tear sheet and converts via WeasyPrint. This is architecturally sound — no separate template to maintain.

### Strengths
- Letter portrait with 0.75in margins — standard professional format
- Page footer with "Generated by Briarwood · [date] · Confidential" — adds credibility
- Page numbering ("Page X of Y") — essential for multi-page documents
- `page-break-before: always` on major sections — prevents awkward splits
- `page-break-inside: avoid` on cards — prevents orphaned content
- SVG charts render natively — no JavaScript dependency issues
- Cream/tan background (#f5f1e8) with serif typography (Georgia) — warm, professional feel distinct from the dark Dash UI

### Issues
- **Without viewing the actual PDF output**, I can note architectural concerns:
  - The print CSS forces `page-break-before: always` on 7 different sections (signal metrics, chart card, durability card, carry card, comp card section, scenario cases, evidence card). This likely creates excessive blank space on pages.
  - Interactive elements are hidden (`display: none !important`), but the space they occupied may not collapse properly.
  - The comp grid is forced to 2 columns for print, which may be too wide for some comp cards.
- **No cover page.** A professional document for distribution should have a title page with property address, date, and Briarwood branding.
- **No table of contents.** For a multi-page document, a TOC helps navigation.

---

## 10. Accessibility Observations

- **Color contrast:** `TEXT_MUTED` (#848d97) on `BG_BASE` (#0d1117) is noted as "5.5:1 contrast on BG_BASE (WCAG AA)" — good.
- **Interactive elements:** The `<details>/<summary>` pattern is natively accessible. Good choice.
- **Score dots (●/○):** Purely visual, no `aria-label`. Score is also shown as text ("4.2 / 5"), so this is acceptable but could be improved.
- **Color-only indicators:** Score colors (green/yellow/orange/red) are used alongside text labels (Excellent/Strong/Fair/Weak/Poor). Good practice.
- **Hover-only tooltips:** The confidence level tooltip requires hover, which doesn't work on touch devices. The CSS-only approach (`.confidence-level-wrap:hover .confidence-tooltip`) is not keyboard-accessible. Consider making the tooltip clickable/tappable.
- **Small text:** 9px labels in the sticky header are below WCAG minimum recommended size (12px). These are supplementary labels alongside 13px values, but worth noting.

---

## 11. Mobile/Responsive State

The `workspace.css` has responsive breakpoints at 1024px, 768px, and 480px:
- **1024px:** Portfolio summary grid goes to 2 columns
- **768px:** Verdict grid stacks, what-if metrics stack, drawer goes full-width, add-property button hides, metric strips wrap
- **480px:** Reduced padding, smaller score text, stacked lens badges, single-column portfolio, horizontal scroll for tables, smaller tour button

**Assessment:** The responsive approach is reasonable for a desktop-first tool. The 768px breakpoint makes the most critical adjustments. However:
- The sticky header (`40px` height, flex layout) will likely overflow on screens under 600px where "Ask | BCV | Gap | Base | Score | Tier" won't fit.
- The comparison view (side-by-side lanes) is fundamentally a desktop layout. It should probably switch to stacked/tabbed lanes on mobile.
- The property manager drawer at 920px wide with 48px margin is fine on desktop but the 768px breakpoint forcing full-width is appropriate.

---

## 12. Prioritized Recommendations

### P0 — Sticky Header Improvements
1. Add **Risk** indicator (risk score with color)
2. Add **Net Monthly** (monthly burn/cash flow number)
3. Add **Confidence** level badge (already exists as component, just needs placement)
4. Design challenge: fit 3 new metrics without clutter — consider a two-row header or a condensed format

### P1 — Compare View Redesign
1. Add relative deltas to all metric rows ("+$100K / +13%")
2. Add winner-per-metric color indicators
3. Generate trade-off narrative (synthesized text, not just bullet differences)
4. Add scenario overlay chart
5. Simplify the compare flow (remove the "confirm" step)

### P1 — Property Input Simplification
1. Collapse Physical Features and Manual Comps by default
2. Add visual hierarchy: "Required" vs "Recommended" vs "Optional" grouping
3. Show field impact hints: "Adding rent improves income confidence by ~12%"

### P2 — Interactive Controls
1. Rate sensitivity slider in what-if section
2. Vacancy toggle for coastal properties
3. Hold period selector (3/5/7/10 years)

### P2 — Lens Selector Redesign
1. Replace Owner/Realtor toggle with 4-lens selector + presentation mode
2. Lens selection re-emphasizes relevant metrics
3. Show lens-specific recommendation

### P3 — Section Ordering Refinement
1. Consider promoting Risk to position 3 (after Value and Economics)
2. Rename "What Is the Hidden Upside or Constraint?" → "Where's the Upside?"
3. Move optionality back into the main question group (remove "MORE CONTEXT" break)

### P3 — PDF Polish
1. Add cover page
2. Review page break strategy (reduce excessive `page-break-before: always`)
3. Test with multiple properties and verify pagination

---

## Summary

Briarwood's UI is significantly stronger than most real estate analysis tools. The design system is consistent, the question-based framing is excellent, and the recent engineering work (confidence layer, investor metrics, PDF export, category drill-down) has filled major gaps.

The highest-impact improvements are:
1. **Sticky header enrichment** — surface risk, monthly cost, and confidence where they can't be missed
2. **Compare view depth** — add relative framing, winner indicators, and trade-off narrative
3. **Rate sensitivity** — let users adjust the variable that most affects their decision
4. **Lens system** — decouple presentation mode from scoring perspective, give users control

The platform's core strength — dense, analytical, decision-first — should be preserved. Every change should add clarity without reducing density.

---

## Implementation Log

The following improvements were implemented during the Phase 3 pass:

### P0 — Sticky Header Enrichment (completed)
- Added **risk score** (color-coded dot), **net monthly cash flow** (tone-colored), and **confidence level** (dot indicator) to the persistent sticky header
- Replaced the "Base" metric to make room; added a 1px separator before the score/recommendation cluster
- Files: `app.py` (callback `render_active_property_status`)

### P1 — Compare View Depth (completed)
- Extended `CompareMetricRow` with `raw_values`, `deltas`, `winner`, `higher_is_better` fields
- Rewrote `compare.py` with `_LOWER_IS_BETTER` set for proper min/max winner determination
- Added `_render_compare_table` in `components.py` with green winner highlighting, delta sublabels, and "best" badges
- Formatted deltas contextually: currency, percentages, ratios, acreage
- Files: `view_models.py`, `compare.py`, `components.py`

### P1 — Property Input Simplification (completed)
- Restructured `_add_property_form_body` with progressive disclosure using `<details>` elements
- Added tier badges (REQUIRED / RECOMMENDED / OPTIONAL) with color-coded labels and impact hints
- Subject Property and Property Details always visible; Physical Features and Manual Comps collapsed by default
- Files: `app.py`

### P2 — Rate Sensitivity Slider (completed)
- Added mortgage rate slider (5.0%–9.0%, step 0.25%) alongside existing ask price slider
- `render_what_if_metrics` now computes mortgage at both adjusted and default rates, shows "was" sublabels
- Wired up `what-if-rate-slider` as Input in the `update_what_if` callback
- Files: `components.py`, `app.py`

### P2 — Vacancy Toggle for Coastal Properties (completed)
- Added RadioItems toggle (Standard 5% / Seasonal 15%) that appears only for properties with a coastal profile
- Vacancy rate feeds into PTR and cash flow calculations in what-if metrics
- Default value auto-selects based on `coastal_profile_label`
- Files: `components.py`, `app.py`

### P2 — Lens Selector Redesign (completed)
- Replaced Owner/Realtor toggle with combined control: 4-lens selector (Auto / Investor / Owner / Developer / Risk) + presentation mode toggle (Owner / Realtor)
- Lens selector stored in `tear-sheet-lens` (localStorage), passed through to `render_tear_sheet_body` and `render_perspective_block`
- Perspective block hero card shows "VIEWING AS" when user-selected vs "BEST FOR" in auto mode
- Risk lens properly uses inverted color scale
- Files: `components.py`, `app.py`

### P3 — Section Ordering (completed)
- Renamed "What Is the Hidden Upside or Constraint?" to "Where's the Upside?"
- Removed "MORE CONTEXT" divider between main and secondary sections
- Promoted Risk section to position 3 (after Price and Economics, before Forward Look)
- Files: `components.py`

### P3 — PDF Cover Page (completed)
- Added `_build_cover_page` to `pdf_renderer.py` generating a centered cover page with property name, subtitle, stance, Ask/BCV metrics, verdict, and generation date
- Cover page uses `page-break-after: always` to separate from main content
- No TOC per user instruction
- Files: `pdf_renderer.py`

### Not Implemented (deferred)
- **Compare trade-off narrative** — may need backend support; deferred per user instruction
- **PDF table of contents** — skipped per user instruction
- **Lens-aware metric promotion/demotion** — lens selector is wired but does not yet reorder or hide sections based on selected lens (follow-up work)

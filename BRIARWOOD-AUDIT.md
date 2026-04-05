# BRIARWOOD PLATFORM AUDIT
**Date:** 2026-04-05
**Scope:** Model & Logic Audit + UX Designer Handoff Prep

---

# PHASE 1: MODEL & LOGIC AUDIT

## Architecture Overview

Briarwood runs 17 modules sequentially via `AnalysisEngine` (engine.py). Each module wraps one or more agents that score/transform domain-specific inputs. Data flows:

```
PropertyInput → Modules (calling Agents) → AnalysisReport → Decision Model → Tear Sheet
```

**Key files:**
- `briarwood/engine.py` — orchestrator, runs all 17 modules in sequence
- `briarwood/schemas.py` — PropertyInput, AnalysisReport, ModuleResult dataclasses
- `briarwood/settings.py` — all configuration constants
- `briarwood/decision_model/scoring.py` — 20 sub-factors → 5 categories → final 1–5 score
- `briarwood/decision_model/lens_scoring.py` — 4 perspective lenses (Risk, Investor, Owner, Developer)
- `briarwood/dash_app/app.py` — main Dash application (2,508 lines)
- `briarwood/dash_app/components.py` — UI rendering (4,454 lines)

---

## UC1: Single Property Decision Engine (PRIMARY)

**Coverage: ✅ FULLY COVERED**

This is the heart of the platform and the most complete use case.

### What Exists

| Question | Implementation | Files |
|----------|---------------|-------|
| Is this overpriced/underpriced? | BCV vs ask price comparison with mispricing_pct; comp-anchored valuation via 5-component CurrentValue model (40% comps, 24% market-adjusted, 16% town prior, 12% backdated listing, 8% income) | `agents/current_value/agent.py`, `modules/current_value.py` |
| What's my real cost to own? | Full monthly cost model: mortgage P&I + taxes + insurance + HOA + maintenance (1% default) + vacancy (5% default); income offset via IncomeAgent | `modules/cost_valuation.py`, `agents/income/agent.py` |
| What happens if I renovate? | RenovationScenarioModule: budget estimation, post-reno BCV using upgraded comp set, ROI calculation, equity creation analysis | `modules/renovation_scenario.py` |
| What's the upside vs downside? | Bull/Base/Bear scenarios with 4 adjustment components (market drift, location, risk, optionality) + stress scenario (25–35% drawdown) | `modules/bull_base_bear.py` |
| Should I buy this? | 20 sub-factor decision model → 5 categories → 1–5 final score → 5 recommendation tiers (High Conviction Buy / Attractive / Neutral / Caution / Avoid) + narrative generation | `decision_model/scoring.py`, `decision_model/scoring_config.py` |

**Required Outputs:**

| Output | Status | Notes |
|--------|--------|-------|
| Value vs baseline | ✅ | BCV vs ask, mispricing_pct, comp positioning chart |
| Cost profile | ✅ | Monthly carrying cost breakdown, income offset, net monthly burn |
| Bull/Base/Bear scenarios | ✅ | Full scenario projections with market drift, location, risk, optionality adjustments |
| Risk bars | ✅ | 5-dimension risk scoring (flood, age, taxes, DOM, vacancy) + 4 risk sub-factors in decision model (liquidity, capex, income stability, macro/regulatory) |
| Narrative recommendation | ✅ | Auto-generated via `_generate_narrative()` identifying strongest/weakest dimensions |

### What's Missing

- **Opportunity cost calculation**: No explicit "what if I invested this down payment in S&P 500 instead?" comparison. Monthly cost exists but opportunity cost of capital is not modeled.
- **Mortgage rate sensitivity**: No toggle to see how rate changes affect cost-to-own and decision score.

### What's Broken or Wrong

1. **Cost valuation base score too generous** (`modules/cost_valuation.py`): Base score starts at 45/100 even with ZERO rent and ZERO cap rate support. A property that can't support itself financially should score much lower.

2. **Cap rate scoring may be inverted** (`modules/cost_valuation.py`): `cap_rate × 500` means a 5% cap rate → 25 pts (capped at 20). This rewards higher cap rates, which is correct for income investors, but the weight (500) creates a ceiling quickly — anything above 4% cap rate maxes out at 20 pts with no differentiation.

3. **Negative cash flow asymmetry** (`modules/cost_valuation.py`): Positive CF divisor is $100/pt, negative is $200/pt. Negative carry is treated as half as damaging as positive carry is beneficial. In a rising rate environment, this could mask real downside.

4. **Replacement cost heuristic is NJ-specific** (`decision_model/scoring.py`): Hardcoded $400/sqft replacement cost. No adjustment for property type, age, or geography.

---

## UC2: Property Comparison Engine

**Coverage: ⚠️ PARTIALLY COVERED**

### What Exists

| Feature | Implementation | Files |
|---------|---------------|-------|
| Side-by-side metrics | 16 metrics compared: Ask, BCV, Forward Base, Lot, Sqft, Taxes, DOM, ISR, PTR, Risk, Town Score, Scarcity, Confidence | `dash_app/compare.py` |
| 4 comparison modes | Heatmap (color-coded grid), Radar (polar chart), Table (raw metrics), Detail (section deep-dive) | `dash_app/components.py` (render_compare_*) |
| Difference notes | Highlights largest input gaps between properties | `dash_app/compare.py` → `build_compare_summary()` |
| Multi-property ranking | Portfolio tab with sortable rankings by score, recommendation tier, best lens | `dash_app/components.py` → `render_portfolio_dashboard()` |

### What's Missing

- ❌ **Price attribution diff**: No "Why is Property A $X more than Property B?" breakdown. Compare shows raw metrics side-by-side but does NOT decompose the price delta into feature-level contributions (e.g., "$30K from extra bedroom, $50K from newer build, -$20K from flood risk").
- ❌ **Forward return comparison**: No scenario projection overlay across properties. Each property has its own bull/base/bear but there's no comparative view of "which has better forward return."
- ❌ **Optionality comparison**: No structured view of "which property has more upside" beyond raw optionality category scores. No renovation scenario comparison across properties.
- ⚠️ **Relative value**: Partially addressed via BCV delta and heatmap coloring, but no explicit "Property A is X% cheaper on an all-in basis when adjusted for features" calculation.

### What's Broken or Wrong

- `compare.py` is only 118 lines — the comparison logic is thin. It builds summary rows but doesn't compute any relative metrics (e.g., delta per sqft, delta per bedroom).
- Heatmap color coding uses absolute thresholds rather than relative percentile positioning within the comparison set.

---

## UC3: Value Creation / Renovation Underwriting

**Coverage: ⚠️ PARTIALLY COVERED**

### What Exists

| Feature | Implementation | Files |
|---------|---------------|-------|
| Post-reno valuation | Builds synthetic "renovated" PropertyInput, runs ComparableSales + CurrentValue to get renovated BCV | `modules/renovation_scenario.py` |
| ROI calculation | `roi_pct = (net_value_creation / budget) × 100` | `modules/renovation_scenario.py` |
| Equity creation analysis | `net_value_creation = renovated_BCV - current_BCV - budget`; `cost_per_dollar = budget / gross_value_creation` | `modules/renovation_scenario.py` |
| Teardown scenario | Full two-phase model: hold & rent → demolish & build, with year-by-year cash flow projection | `modules/teardown_scenario.py` |
| Scoring | Renovation: `score = 50 + roi_pct × 0.5`; Teardown: `score = 50 + annualized_roi × 3` | Both modules |

### What's Missing

- ❌ **ROIC calculation**: No explicit Return on Invested Capital metric that accounts for total capital deployed (purchase + capex + carry costs during renovation). The ROI calculation uses only budget as denominator, ignoring carry costs and closing costs.
- ❌ **Renovation timeline modeling**: No construction duration estimation. The renovation module assumes instantaneous value creation — no "what do I pay in carry during 6 months of renovation?"
- ❌ **Capex budget builder**: Budget comes from property condition/capex_lane inputs, not from a detailed room-by-room or system-by-system estimate. No kitchen/bath/roof/HVAC breakdown.
- ⚠️ **Comp quality for renovated properties**: Renovated BCV depends on finding comps with `condition_profile = "renovated"`. If the comp database is thin on renovated comps in the target town, confidence degrades but may still produce misleading values.

### What's Broken or Wrong

- **Minimum budget threshold of $10K** (`modules/renovation_scenario.py`): Properties with light cosmetic renovation needs ($5–10K) are excluded from analysis entirely.
- **Teardown scenario default construction duration is 14 months** — no way to adjust this per-property. Coastal NJ permitting can add 6–12 months.

---

## UC4: Income / Rental Optimization Engine

**Coverage: ✅ FULLY COVERED (with minor gaps)**

### What Exists

| Feature | Implementation | Files |
|---------|---------------|-------|
| Income offset modeling | ISR (Income Support Ratio) = effective_rent / gross_monthly_cost; net monthly burn after income | `agents/income/agent.py`, `modules/income_support.py` |
| True monthly burn | Full carrying cost: P&I + taxes + insurance + HOA + maintenance - effective rent | `modules/cost_valuation.py` |
| Income-adjusted affordability | ISR classification (Strong ≥ 1.1, Neutral 0.9–1.1, Weak < 0.9); downside burden metric | `agents/rental_ease/scoring.py` |
| Rental ease scoring | 4-component scoring: liquidity (35%), demand depth (25%), rent support (25%), structural (15%) | `agents/rental_ease/agent.py` |
| ADU/back house income | `back_house_monthly_rent` field in PropertyInput; `unit_rents` for multi-unit | `schemas.py`, `agents/income/agent.py` |
| Stabilized yield | Cap rate = NOI / purchase_price; gross yield = annual_rent / purchase_price | `modules/cost_valuation.py` |

### What's Missing

- ❌ **Seasonal income modeling**: No seasonal rent adjustment despite coastal NJ having significant summer premium. `seasonal_premium_rent` exists in schema but not processed in scoring.
- ⚠️ **Rent growth projection**: Teardown module projects rent growth (3% default) but the income module only shows current state. No 5-year income projection for standard hold.

### What's Broken or Wrong

- **Maintenance reserve is flat 1%** regardless of property age or condition. A 1920s home needing a new roof should have higher maintenance reserve than a 2020 build.
- **Vacancy rate default 5%** is reasonable for year-round rentals but too low for seasonal coastal properties where 15–25% vacancy is normal.

---

## UC5: Risk & Constraint Engine (DIFFERENTIATOR)

**Coverage: ✅ FULLY COVERED**

### What Exists

| Feature | Implementation | Files |
|---------|---------------|-------|
| Multi-factor risk scoring | 5-dimension graduated penalty/credit model: flood, property age, taxes, DOM, vacancy | `modules/risk_constraints.py` |
| Liquidity risk | LiquiditySignalModule: comp freshness, rental absorption, town liquidity → strong/normal/fragile label | `modules/liquidity_signal.py` |
| Market depth | Scarcity framework: land scarcity (55%) + location scarcity (45%) blended with demand consistency (60/40) | `agents/scarcity/` |
| Decision model risk layer | 4 risk sub-factors: liquidity_risk, capex_risk, income_stability, macro_regulatory (20% category weight) | `decision_model/scoring.py` |
| Risk lens | Dedicated Risk Assessment lens inverting category scores: risk (40%) + market (30%) + price (30%) | `decision_model/lens_scoring.py` |

**Required Outputs:**

| Output | Status | Notes |
|--------|--------|-------|
| Risk bars (liquidity) | ✅ | DOM-based + town liquidity index + comp absorption |
| Risk bars (capex) | ✅ | Condition-based or explicit repair budget scoring |
| Risk bars (income stability) | ✅ | Rental ease score + downside burden + risk view |
| Risk bars (market risk) | ✅ | Bull/base/bear spread + stress scenario |
| Risk bars (valuation risk) | ✅ | BCV confidence + mispricing + comp quality |

### What's Missing

- ❌ **Insurance risk**: No insurance availability/cost risk scoring. NJ coastal properties face escalating insurance costs and potential non-renewal risk not captured.
- ❌ **Environmental risk beyond flood**: No storm surge, erosion, or sea-level rise modeling.

### What's Broken or Wrong

- **DOM penalty cliff at 30 days** (`modules/risk_constraints.py`): 29 days = 0 penalty, 30 days = starts accumulating. Should be a smooth function.
- **Vacancy threshold is binary** (`modules/risk_constraints.py`): Above 6% = -10 pts, below = no penalty. Should be graduated like taxes and DOM.
- **Risk attenuation in bull scenario is questionable** (`modules/bull_base_bear.py`): Risk penalty is only 30% effective in bull case. Structural risks (flood, age) don't disappear in bull markets.

---

## UC6: Town / Market Intelligence Layer

**Coverage: ✅ FULLY COVERED**

### What Exists

| Feature | Implementation | Files |
|---------|---------------|-------|
| Market momentum | MarketMomentumSignalModule: ZHVI trend + town score direction + local project signals → accelerating/steady/decelerating | `modules/market_momentum_signal.py` |
| Cycle positioning | Town/County scoring: 3-component composite (50% town demand + 25% county support + 25% market alignment) | `agents/town_county/scoring.py` |
| Capital flow signals | Inventory levels, sell-through (months of supply), DOM trends, local development activity | `agents/town_county/service.py`, `modules/local_intelligence.py` |
| Location thesis | Labels: strong (≥75) / supportive (60–75) / mixed (45–60) / weak (<45) | `agents/town_county/scoring.py` |
| School signal | 5-component weighted scoring (achievement 30%, growth 25%, readiness 15%, absenteeism 15%, student-teacher ratio 15%) | `agents/school_signal/agent.py` |
| Coastal profile | Beach/downtown premium flags for Monmouth County towns | Data: `data/town_county/monmouth_coastal_profiles.json` |

**Required Outputs:**

| Output | Status | Notes |
|--------|--------|-------|
| Inventory levels | ✅ | Via liquidity.json: months_of_supply, active inventory |
| Sell-through rate | ✅ | Months of supply + absorption rate from scarcity framework |
| Market momentum | ✅ | ZHVI 1yr/3yr/5yr CAGRs + momentum direction label |
| Development/sentiment | ✅ | LocalIntelligenceModule parses town planning docs for project signals |

### What's Missing

- ⚠️ **Limited geography**: Town data only seeded for ~6 Monmouth County shore towns. Other NJ towns or out-of-state properties hit fallback logic.
- ❌ **Real-time data feeds**: All data is file-backed JSON. No Zillow API, MLS API, or Census API integration for live updates.

### What's Broken or Wrong

- **County support score uses macro sentiment with no recent data check** — if FRED data is stale, it still gets 10% weight in the town score without warning.

---

## UC7: Portfolio Layer

**Coverage: ❌ NOT IMPLEMENTED (audit scaffolding only)**

### What Exists

- `audit_scripts/01_portfolio_summary.py` — Read-only audit that loads all presets and reports aggregate stats (mean/min/max scores, tier distribution, category averages)
- Dash app Portfolio tab — Simple ranking table + category heatmap. Shows property count, average score, total value, "Strong Buy" count.
- Properties stored independently in `data/saved_properties/`

### What's Missing

- ❌ **Portfolio-level impact modeling**: No "how does this deal affect my portfolio?" analysis. Each property analyzed in isolation.
- ❌ **Geographic concentration**: No exposure breakdown by town/county/region.
- ❌ **Leverage aggregation**: No total leverage, LTV, or debt service across portfolio.
- ❌ **Portfolio NAV**: No mark-to-market portfolio valuation.
- ❌ **Risk aggregation**: No portfolio-level risk metrics (correlation, diversification benefit).
- ❌ **Position sizing**: No optimal allocation or weighting.

### Foundations That Exist

- Multiple properties can be loaded simultaneously (`load_reports()` in `dash_app/data.py`)
- Each property has full AnalysisReport with BCV, scores, scenarios
- Portfolio tab infrastructure exists in the UI
- The data model supports aggregation — it just hasn't been built

---

## UC8: Price Attribution / Explainability

**Coverage: ⚠️ PARTIALLY COVERED**

### What Exists

| Feature | Implementation | Files |
|---------|---------------|-------|
| Sub-factor evidence | Each of 20 sub-factors returns `evidence` string explaining the score basis (e.g., "Net opportunity delta 12.5% (+$50K)") | `decision_model/scoring.py` |
| Category contribution | Sub-factor weights × scores tracked via `SubFactorScore.contribution` field | `decision_model/scoring.py` |
| Narrative generation | `_generate_narrative()` identifies strongest/weakest dimensions for interpretability | `decision_model/scoring.py` |
| Multi-lens explanation | Each lens provides reasoning for its score and recommendation | `decision_model/lens_scoring.py` |
| Comp adjustment details | Comparable sales agent shows per-comp adjustments (sqft, beds, baths, lot, vintage) | `agents/comparable_sales/agent.py` |
| Value driver attribution | Diagnostics tab shows contribution of each input to final value via sensitivity analysis | `dash_app/data_quality.py` |

### What's Missing

- ❌ **Feature-level price impact**: No "this garage adds $25K, the back house adds $40K, the flood zone costs $15K" decomposition. The comp adjustment model adjusts for differences but doesn't produce standalone feature valuations.
- ❌ **Statistical significance / confidence on attributions**: No standard errors, confidence intervals, or p-values on feature impacts. All scoring is deterministic rule-based.
- ❌ **SHAP / permutation importance**: No ML-based explainability. System is rule-based with hardcoded thresholds.

### What's Broken or Wrong

- The diagnostics tab's "value driver attribution" is a sensitivity analysis (vary each input, see score change) — not a true attribution of what drives the *price*. It shows which *inputs* matter most to the *score*, not which *features* drive the *market price*.

---

## UC9: Tear Sheet as Product (Distribution)

**Coverage: ⚠️ PARTIALLY COVERED**

### What Exists

| Feature | Implementation | Files |
|---------|---------------|-------|
| HTML tear sheet generation | `render_tear_sheet_html()` → self-contained HTML file with professional styling (serif typography, beige background, print-ready) | `briarwood/reports/renderer.py`, `briarwood/reports/templates/tear_sheet.html` |
| Tear sheet export from UI | "Export Tear Sheet" button in topbar → generates HTML file in `outputs/` directory | `dash_app/data.py` → `export_preset_tear_sheet()` |
| Static output files | Generated in `outputs/{preset_id}_tear_sheet.html` (~57KB each) | `outputs/` directory |
| Text summary export | `format_tear_sheet_summary()` produces structured text with header, conclusion, thesis, scenarios | `briarwood/runner.py` |

### What's Missing

- ❌ **PDF export**: No PDF generation. Despite a "download" button in the UI, it produces TXT, not PDF. No weasyprint, reportlab, or pdfkit dependency.
- ❌ **Shareable link generation**: No URL-based sharing. All output is local file generation.
- ❌ **Embed support**: No iframe or widget embedding capability.
- ❌ **Email/distribution**: No send-to-email or CRM integration.
- ⚠️ **Mobile responsiveness**: Dash app has responsive breakpoints defined in CSS but the static HTML tear sheet is desktop-optimized with no mobile stylesheet.

### What's Broken or Wrong

- The UI's export button label suggests PDF but actually generates TXT. This is misleading for users expecting a polished document.
- Static HTML tear sheets are self-contained but ~57KB each — acceptable but could be optimized.

---

## SUMMARY: Coverage Against 3 Core Jobs

### Job 1: Evaluate a Property — "Should I buy this?"

**Implementation: ~85%**

| Component | Status | Coverage |
|-----------|--------|----------|
| Property valuation (BCV) | ✅ | 5-component model, comp-anchored |
| Cost to own | ✅ | Full monthly breakdown |
| Risk assessment | ✅ | 5-dimension + 4 sub-factor model |
| Decision score & recommendation | ✅ | 20 sub-factors → 1–5 score → 5 tiers |
| Multi-lens evaluation | ✅ | 4 perspective lenses |
| Renovation upside | ✅ | Post-reno BCV + ROI |
| Tear sheet output | ⚠️ | HTML only, no PDF |
| Opportunity cost | ❌ | Not modeled |
| Rate sensitivity | ❌ | Not modeled |

**Critical gaps**: PDF export for professional distribution; opportunity cost of capital calculation.

**Priority**: PDF export is the #1 blocker for UC9 and distribution.

### Job 2: Compare Opportunities — "Is this better than alternatives?"

**Implementation: ~40%**

| Component | Status | Coverage |
|-----------|--------|----------|
| Side-by-side metrics | ✅ | 16 metrics, 4 display modes |
| Portfolio ranking | ✅ | Sortable table with heatmap |
| Price attribution diff | ❌ | No feature-level delta decomposition |
| Forward return comparison | ❌ | No scenario overlay across properties |
| Optionality comparison | ❌ | No structured comparison view |
| Relative value (all-in adjusted) | ❌ | No normalized comparison |
| Portfolio-level impact | ❌ | No portfolio modeling |

**Critical gaps**: The comparison view shows numbers side-by-side but doesn't answer *why* one is better than another. No relative value engine exists.

**Priority**: Price attribution diff engine — this is the most impactful gap because it serves both UC2 and UC8.

### Job 3: Project Outcomes — "What happens if I act?"

**Implementation: ~65%**

| Component | Status | Coverage |
|-----------|--------|----------|
| Bull/Base/Bear scenarios | ✅ | Full 4-component adjustment model |
| Stress scenario | ✅ | Historical drawdown modeling |
| Renovation scenario | ⚠️ | ROI exists but no ROIC, no timeline |
| Teardown scenario | ✅ | Full 2-phase model with year-by-year cash flow |
| Income projection | ⚠️ | Current snapshot only, no multi-year forward |
| Hold period analysis | ⚠️ | Only in teardown module, not general |
| Rate sensitivity | ❌ | No "what if rates go to 8%?" modeling |
| Market cycle scenarios | ❌ | No "what if we enter recession?" overlay |

**Critical gaps**: ROIC for renovation; multi-year income projection for standard hold; rate/macro scenario overlays.

**Priority**: ROIC calculation and general hold-period cash flow projection (extend teardown module's year-by-year model to standard hold).

---

# PHASE 2: UX DESIGNER HANDOFF PREP

## A. Data Inventory

### Screen 1: Tear Sheet (Primary View)

| Section | Data Points | Source | Format |
|---------|------------|--------|--------|
| **Header** | Address, beds/baths/sqft, town | PropertyInput | Text labels |
| **Sticky sub-header** | Ask price, BCV, gap %, Base case, Score, Tier | CurrentValue, BullBaseBear, DecisionModel | Formatted currency, %, score badge |
| **"Is This a Good Price?"** | Ask vs BCV, mispricing %, comp positioning, PPSF vs town median, replacement cost ratio | CurrentValue, ComparableSales, DecisionModel | Metric cards, dot plot chart, status chips |
| **"Can I Afford to Hold It?"** | Monthly P&I, taxes, insurance, HOA, maintenance, rent, net cash flow, ISR, PTR, downside burden | CostValuation, IncomeSupport | Metric cards, income waterfall chart |
| **"What Happens If I Buy It?"** | Bull/Base/Bear values, spread, market drift, location adjustment, risk adjustment, optionality premium | BullBaseBear | Fan chart, waterfall chart, metric cards |
| **"What Could Go Wrong?"** | Risk score (0–100), flood risk, tax burden, DOM signal, vacancy, liquidity view, market momentum | RiskConstraints, LiquiditySignal, MarketMomentum | Risk breakdown bars, metric cards, tone badges |
| **"Hidden Upside or Constraint?"** | Condition profile, capex lane, ADU potential, lot signals, zoning, renovation ROI | RenovationScenario, Scarcity, DecisionModel optionality | Metric cards, signal list, score bars |
| **Decision Summary** | Final score (1–5), recommendation tier, narrative, 4 lens scores + best lens, category breakdown | DecisionModel, LensScoring | Star rating, colored badge, category mini-bars, narrative text |
| **Assumption Transparency** | All inputs with source labels (user_supplied/system_estimated/missing), confidence per section | All modules | Collapsible block, color-coded status chips |

### Screen 2: Scenarios Tab

| Section | Data Points | Source | Format |
|---------|------------|--------|--------|
| **Historic + Forward Outlook** | 10-year price history, 12M projection, BCV anchor, driver breakdown (drift, location, risk, optionality) | MarketValueHistory, BullBaseBear | Line chart, metric cards, driver table |
| **Renovation Scenario** | Budget, current BCV, renovated BCV, gross value creation, net value creation, ROI, cost per dollar, comp range | RenovationScenario | Metric cards, narrative text |
| **Teardown Scenario** | Hold years, year-by-year cash flow, construction cost, new build BCV, total ROI, annualized ROI | TeardownScenario | Metric cards, cash flow table, narrative text |

### Screen 3: Compare Tab

| Section | Data Points | Source | Format |
|---------|------------|--------|--------|
| **Controls** | Property multi-select, mode toggle, section selector | User input | Dropdowns, radio buttons |
| **Heatmap mode** | 16 metrics × N properties, color-coded | All modules | Color grid |
| **Radar mode** | 6 category scores per property | DecisionModel | Polar chart |
| **Table mode** | 16 raw metric values side-by-side | All modules | Data table |
| **Detail mode** | Full section analysis for selected properties | All modules | Expandable sections |
| **Difference notes** | Largest input gaps, missing inputs, confidence variance | Compare logic | Text annotations |

### Screen 4: Portfolio Tab

| Section | Data Points | Source | Format |
|---------|------------|--------|--------|
| **Summary cards** | Property count, avg score, total portfolio value, strong buy count | Aggregated from all reports | 4 metric cards |
| **Rankings table** | Rank, address, ask price, score, best lens, recommendation tier | DecisionModel, LensScoring | Sortable data table |
| **Category heatmap** | Properties × 6 categories, color-coded scores | DecisionModel | Color grid |

### Screen 5: Diagnostics Tab

| Section | Data Points | Source | Format |
|---------|------------|--------|--------|
| **Comp database health** | Total comps, towns covered, real vs estimated sale dates, coverage by town, verification tiers, field completeness | ComparableSales data | Tables, status badges |
| **Per-property comp matching** | Comps used/rejected, rejection reasons, match quality distribution | ComparableSales agent | Tables, quality indicators |
| **Value driver attribution** | Input contribution to score (sensitivity analysis), sensitivity ranking | All modules | Tables, bar charts |
| **Input impact signals** | Missing inputs + potential impact, confidence variance | All modules | Warning lists, conditional styling |

### Screen 6: Property Manager Modal

| Section | Data Points | Source | Format |
|---------|------------|--------|--------|
| **Saved properties table** | Address, ask, BCV, pricing view, confidence, missing input count | Saved reports | Multi-select table |
| **Comp database table** | Address, town, price, status, type | sales_comps.json | Single-select table |
| **New property form** | 40+ fields across 5 groups (subject, details, physical, income, manual comps) | User input | Form cards with validation |

---

## B. Information Hierarchy Assessment

### Tear Sheet View

| Element | Current Prominence | Should Be | Mismatch? |
|---------|-------------------|-----------|-----------|
| Final score (1–5) | ⬆️ Highest — large colored display | ✅ Correct — this is the answer | No |
| Recommendation tier badge | ⬆️ High — colored badge in header | ✅ Correct — immediate decision signal | No |
| BCV vs Ask gap | ⬆️ High — sticky sub-header | ✅ Correct — primary value signal | No |
| Risk score | ⬆️ Medium-high — section header metric | ⚠️ Should be higher — risk is differentiator | **Yes — promote** |
| Monthly cash flow / net burn | ➡️ Medium — metric card in affordability section | ⚠️ Should be higher — "can I afford this?" is question #2 | **Yes — promote** |
| Comp positioning chart | ➡️ Medium — within "Good Price" section | ✅ Correct — supporting evidence | No |
| Confidence levels | ⬇️ Low — small badges per section | ⚠️ Should be more visible — users need to know what to trust | **Yes — promote** |
| Assumption transparency | ⬇️ Lowest — collapsed by default | ✅ Correct — detail for power users | No |
| Lens scores | ➡️ Medium — in decision summary | ⚠️ Could be higher — different buyer types need different signals | **Mild mismatch** |
| Scarcity/optionality | ⬇️ Low — buried in "Hidden Upside" section | ⚠️ For developer lens, this should be more prominent | **Context-dependent** |

**Key mismatches:**
1. **Risk score needs more prominence** — it's the UC5 differentiator but sits at medium prominence. Consider risk as a persistent indicator alongside the overall score.
2. **Monthly cash flow / net burn should appear in the sticky header** — "Can I afford this?" is the #2 question after "Should I buy this?"
3. **Confidence should be more visible** — when confidence is low, the entire tear sheet's reliability is questionable. Consider a global confidence indicator.

### Compare View

| Element | Current Prominence | Should Be | Mismatch? |
|---------|-------------------|-----------|-----------|
| Heatmap/radar/table toggle | ⬆️ High — prominent controls | ✅ Correct | No |
| Raw metric values | ⬆️ High — the main content | ⚠️ Should show relative differences, not just absolutes | **Yes — transform** |
| Difference notes | ⬇️ Low — text below comparison | ⚠️ Should be more prominent — this is the "why" | **Yes — promote** |
| Winner/recommendation | ❌ Missing | ⚠️ Should exist — "which should I buy?" is the whole point | **Yes — add** |

### Portfolio View

| Element | Current Prominence | Should Be | Mismatch? |
|---------|-------------------|-----------|-----------|
| Summary stats | ⬆️ High — 4 cards at top | ✅ Correct | No |
| Rankings table | ⬆️ High — main content | ✅ Correct | No |
| Category heatmap | ➡️ Medium | ⚠️ Could be higher for pattern recognition | **Mild** |
| Portfolio-level risk | ❌ Missing | ⚠️ Should exist — concentration, leverage | **Yes — add** |

---

## C. Missing Displays (Backend Exists, Not Surfaced)

These are calculations that exist in the backend but are NOT shown in any UI component:

| Calculation | Where It Lives | Why It Matters | Quick Win? |
|-------------|---------------|----------------|------------|
| **DSCR (Debt Service Coverage Ratio)** | `modules/cost_valuation.py` — calculated but not in UI | Critical for investor lens — shows if income covers debt | ✅ Yes |
| **Cash-on-cash return** | `modules/cost_valuation.py` — calculated but not displayed | Key investor metric absent from tear sheet | ✅ Yes |
| **Gross yield** | `modules/cost_valuation.py` — calculated but not displayed | Quick rental return indicator | ✅ Yes |
| **School signal (0–10)** | `agents/school_signal/agent.py` — scored but not surfaced | Affects location thesis but invisible to user | ✅ Yes |
| **Coastal profile flags** | `data/town_county/monmouth_coastal_profiles.json` — loaded but not displayed | Beach/downtown premium context | ✅ Yes |
| **Comp rejection reasons** | `agents/comparable_sales/agent.py` — tracked but only in diagnostics | Explains why BCV uses certain comps | ⚠️ Medium |
| **Market momentum direction** | `modules/market_momentum_signal.py` — scored | accelerating/steady/decelerating label exists | ✅ Yes |
| **Scarcity component breakdown** | `agents/scarcity/` — land + location + demand scored separately | Only composite shown; components add nuance | ⚠️ Medium |
| **Stress scenario value** | `modules/bull_base_bear.py` — calculated | Worst-case drawdown value exists but not in main UI | ✅ Yes |
| **Teardown year-by-year cash flow** | `modules/teardown_scenario.py` — full annual projection | Only summary shown; detail table would be valuable | ⚠️ Medium |
| **Lens reasoning text** | `decision_model/lens_scoring.py` — generated per lens | Natural language explaining each lens recommendation | ✅ Yes |
| **Sub-factor raw values + evidence** | `decision_model/scoring.py` — tracked per sub-factor | 20 evidence strings exist but aren't shown individually | ⚠️ Medium |
| **Rent source type** | `agents/income/agent.py` — tracked | Whether rent is manual, provided, estimated, or missing | ✅ Yes |

---

## D. Interaction Gaps

### Input Mechanisms Missing

| Need | Current State | Recommendation |
|------|--------------|----------------|
| **Adjust mortgage rate** | Fixed at input time; no slider | Add rate sensitivity slider to affordability section |
| **Toggle vacancy rate** | Fixed 5% default | Add vacancy toggle (5% / 10% / 15% / seasonal) |
| **Renovation budget input** | From condition/capex_lane only | Add inline budget input with room-by-room estimator |
| **Hold period selection** | Only in teardown scenario | Add general hold period selector for cash flow projection |
| **Risk tolerance input** | `risk_tolerance` field exists in schema but unused in UI | Add risk tolerance slider to adjust scoring weights |

### View Toggles Missing

| Need | Current State | Recommendation |
|------|--------------|----------------|
| **Owner vs Investor view** | "Owner vs Realtor" toggle exists | Rename/expand to Owner / Investor / Developer (matches lens model) |
| **Monthly vs Annual view** | Cash flow shown monthly only | Add toggle for monthly/annual/cumulative views |
| **Nominal vs Real dollars** | All values nominal | Add inflation-adjusted toggle for scenario projections |
| **Scenario overlay** | Bull/Base/Bear shown as range | Add slider to blend between scenarios |

### Drill-Down Missing

| Need | Current State | Recommendation |
|------|--------------|----------------|
| **Click comp → see details** | Comp positioning chart is static | Make comps clickable to show address, sale details, adjustments |
| **Click category → see sub-factors** | Category bars shown in summary | Add expandable sub-factor breakdown on click |
| **Click risk factor → see detail** | Risk bars are static | Add drill-down to show graduated penalty calculation |
| **Click town score → see components** | Composite score only | Add expandable town demand / county support / alignment breakdown |

### Comparison Mode Missing

| Need | Current State | Recommendation |
|------|--------------|----------------|
| **"Why is A more expensive?"** | Raw numbers side-by-side | Add feature-level price delta decomposition |
| **Scenario comparison** | Each property has own scenarios | Add overlay of bull/base/bear across properties |
| **Quick add to comparison** | Must go to Compare tab, select | Add "Compare" button on each property card in Portfolio |

---

## E. Export & Distribution Readiness

### PDF / Tear Sheet Generation

| Aspect | Status | Notes |
|--------|--------|-------|
| HTML tear sheet | ✅ Working | Self-contained ~57KB HTML files, professional styling |
| PDF export | ❌ Not implemented | No PDF library in dependencies. UI button generates TXT. |
| Print styling | ⚠️ Partial | HTML tear sheet has print-ready styling; Dash app does not |
| Batch generation | ✅ Working | `app.py` CLI generates for all presets |

### Shareability

| Aspect | Status | Notes |
|--------|--------|-------|
| Shareable URLs | ❌ Not implemented | All output is local files |
| Email integration | ❌ Not implemented | No email/SMTP functionality |
| CRM integration | ❌ Not implemented | No external service connections |
| Embed / iframe | ❌ Not implemented | No widget or embed mode |

### Print Readiness

| View | Print Ready? | Notes |
|------|-------------|-------|
| HTML tear sheet | ✅ Yes | Serif typography, beige background, professional layout |
| Dash tear sheet tab | ❌ No | Dark theme, interactive elements don't translate to print |
| Compare view | ❌ No | Requires interactivity (mode toggle) |
| Portfolio view | ⚠️ Partial | Table is printable; heatmap may not render well |
| Diagnostics | ❌ No | Developer-facing, not meant for print |

### Mobile Responsiveness

| View | Mobile Ready? | Notes |
|------|-------------|-------|
| Dash app (all tabs) | ⚠️ Partial | Breakpoints defined in CSS for 1024/768/480px; layout stacks but readability degrades |
| HTML tear sheet | ❌ No | Desktop-optimized, no mobile stylesheet |
| Property manager modal | ⚠️ Partial | Goes full-width on mobile but form is complex |
| Charts/visualizations | ⚠️ Partial | Plotly charts resize but labels may overlap on small screens |

---

## F. Designer Handoff Document

### Sitemap / Screen Inventory

```
Briarwood Platform
├── Topbar (persistent)
│   ├── Logo/Wordmark
│   ├── Property Selector (dropdown)
│   ├── + Add Property (opens modal)
│   ├── Export Tear Sheet (button)
│   └── Active Property Status
│
├── Property Header (sticky, persistent)
│   └── Address · Facts · Ask · BCV · Gap · Base · Score · Tier
│
├── Tab: Tear Sheet ─────────────────────
│   ├── Section 1: "Is This a Good Price?"
│   │   ├── Metric strip (4 inline metrics)
│   │   ├── Comp positioning dot plot
│   │   └── Value support detail
│   ├── Section 2: "Can I Afford to Hold It?"
│   │   ├── Metric strip
│   │   ├── Income waterfall chart
│   │   └── Rent/carry detail
│   ├── Section 3: "What Happens If I Buy It?"
│   │   ├── Metric strip
│   │   ├── Forward fan chart
│   │   ├── Forward waterfall chart
│   │   └── Driver breakdown
│   ├── Section 4: "What Could Go Wrong?"
│   │   ├── Metric strip
│   │   ├── Risk breakdown bars
│   │   └── Risk factor details
│   ├── Section 5: "Hidden Upside or Constraint?"
│   │   ├── Metric strip
│   │   └── Optionality signals
│   ├── Decision Summary
│   │   ├── Score display (1–5)
│   │   ├── Recommendation tier badge
│   │   ├── Narrative text
│   │   ├── Category breakdown bars
│   │   └── Lens scores + best lens
│   └── Assumption Transparency (collapsed)
│
├── Tab: Scenarios ──────────────────────
│   ├── Historic + Forward Outlook
│   │   ├── Price history line chart
│   │   ├── 12M projection metrics
│   │   └── Driver breakdown table
│   ├── Renovation Scenario (conditional)
│   │   ├── Economics metrics
│   │   └── Narrative
│   └── Teardown Scenario (conditional)
│       ├── Phase 1 (hold) metrics
│       ├── Phase 2 (build) metrics
│       └── Full project economics
│
├── Tab: Compare ────────────────────────
│   ├── Controls (property select, mode toggle)
│   ├── Heatmap mode (grid)
│   ├── Radar mode (polar chart)
│   ├── Table mode (data table)
│   └── Detail mode (expandable sections)
│
├── Tab: Portfolio ──────────────────────
│   ├── Summary cards (4)
│   ├── Rankings table
│   └── Category heatmap
│
├── Tab: Diagnostics ────────────────────
│   ├── Comp database health
│   ├── Per-property comp matching
│   ├── Value driver attribution
│   └── Input impact signals
│
└── Modal: Property Manager ─────────────
    ├── Saved Properties table
    ├── Comp Database table
    └── New Property Analysis form
        ├── Subject Property (required)
        ├── Property Details (optional)
        ├── Physical Features (optional)
        ├── Income & Carry (optional)
        └── Manual Comps (optional)
```

### Per-Screen Details

#### Tear Sheet
- **Purpose**: Answer "Should I buy this property?"
- **Primary user**: Buyer, investor, or their advisor
- **Key decisions it supports**: Buy/pass, negotiate price, assess risk
- **Current state**: Most complete screen. 5 question-based sections with charts, metrics, and narrative. Dark theme, professional layout. What-if slider for price sensitivity. Owner/Realtor view toggle.
- **Data available**: BCV, mispricing, comp positioning, full cost breakdown, income support, bull/base/bear scenarios, 5-dimension risk scoring, 20 sub-factor decision model, 4 lens scores, narrative recommendation
- **Recommended focus areas**:
  1. Promote risk score and monthly net burn to sticky header
  2. Add global confidence indicator
  3. Surface DSCR, cash-on-cash, gross yield (exist in backend)
  4. Make comp positioning chart interactive (clickable comps)
  5. Add rate sensitivity slider

#### Scenarios
- **Purpose**: Project future outcomes under different strategies
- **Primary user**: Active investor evaluating renovation or development
- **Key decisions it supports**: Renovate or hold as-is, teardown viability, hold period selection
- **Current state**: Conditional tab (only shows if scenarios enabled). Historic chart + forward projection + renovation/teardown economics.
- **Data available**: Full year-by-year cash flow (teardown), renovation ROI/equity creation, market drift projections
- **Recommended focus areas**:
  1. Add standard hold-period projection (not just teardown)
  2. Surface year-by-year cash flow table for teardown
  3. Add renovation budget builder / input mechanism
  4. Add ROIC metric alongside ROI

#### Compare
- **Purpose**: Choose between competing properties
- **Primary user**: Buyer with multiple options
- **Key decisions it supports**: Relative value, which to pursue first
- **Current state**: 4 display modes but thin underlying logic. Shows raw numbers without relative analysis.
- **Data available**: 16 comparison metrics, category scores for radar
- **Recommended focus areas**:
  1. Add "winner" recommendation per metric
  2. Add relative value calculation (price-per-feature adjusted)
  3. Surface difference notes more prominently
  4. Add scenario overlay view across properties
  5. Add "Why is A more expensive than B?" feature-level breakdown

#### Portfolio
- **Purpose**: Manage and rank all analyzed properties
- **Primary user**: Active buyer/investor tracking multiple markets
- **Key decisions it supports**: Prioritization, portfolio-level risk awareness
- **Current state**: Basic ranking table + category heatmap. No portfolio-level analytics.
- **Data available**: Individual scores, recommendations, category breakdowns
- **Recommended focus areas**:
  1. Add geographic concentration visualization
  2. Add portfolio-level risk aggregation
  3. Add "Quick Compare" action from portfolio to compare tab
  4. Add portfolio-level statistics beyond averages (spread, diversification)

#### Diagnostics
- **Purpose**: Evaluate data quality and model confidence
- **Primary user**: Developer, analyst, or power user
- **Key decisions it supports**: Trust calibration, data improvement prioritization
- **Current state**: Comprehensive comp database health and matching quality views.
- **Data available**: Comp counts, rejection reasons, verification tiers, field completeness, sensitivity analysis
- **Recommended focus areas**:
  1. Consider whether to expose to end users or keep as developer tool
  2. If exposing: simplify to "Data Quality Score" summary + drill-down
  3. Add actionable suggestions ("Add 2 more comps in Belmar to improve confidence")

#### Property Manager Modal
- **Purpose**: Add and manage properties for analysis
- **Primary user**: Any user adding a new property
- **Key decisions it supports**: Data entry accuracy, property setup
- **Current state**: Complex form with 40+ fields across 5 collapsible groups. Saved property list.
- **Data available**: Full PropertyInput schema, saved reports
- **Recommended focus areas**:
  1. Simplify initial entry to 5–8 required fields
  2. Progressive disclosure: show optional fields only after analysis completes
  3. Add "import from listing URL" capability (even if manual parsing)
  4. Improve feedback on which optional fields most improve confidence

### Prioritized UX Issues

Ranked by impact on the 3 core jobs:

| Priority | Issue | Impact | Core Job Affected |
|----------|-------|--------|-------------------|
| **P0** | No PDF export — can't distribute tear sheets professionally | Blocks UC9 entirely | All 3 |
| **P0** | Compare view lacks relative value analysis | Users can't answer "which is better?" | Job 2: Compare |
| **P1** | Monthly burn / net cash flow not in sticky header | Key affordability signal buried | Job 1: Evaluate |
| **P1** | No rate sensitivity control | Can't model different financing scenarios | Job 3: Project |
| **P1** | Risk score underemphasized vs overall score | Differentiator (UC5) not prominent enough | Job 1: Evaluate |
| **P1** | Investor metrics (DSCR, cash-on-cash, yield) exist but not shown | Missing quick signals for investor lens | Job 1: Evaluate |
| **P2** | No standard hold-period cash flow projection | Only teardown has multi-year projection | Job 3: Project |
| **P2** | Comps are not clickable / interactive | Can't inspect evidence behind BCV | Job 1: Evaluate |
| **P2** | Property manager form too complex for onboarding | 40+ fields overwhelming for new users | All 3 |
| **P2** | No global confidence indicator | Users may trust low-confidence analyses | Job 1: Evaluate |
| **P2** | Portfolio tab lacks risk aggregation | No portfolio-level risk awareness | Job 2: Compare |
| **P3** | Static HTML tear sheet not mobile responsive | Limits distribution reach | Job 1: Evaluate |
| **P3** | Owner/Realtor toggle should match 4 lens model | UI offers 2 views but model supports 4 | Job 1: Evaluate |
| **P3** | Diagnostics tab ambiguously positioned | Power tool or end-user feature? Unclear | N/A |
| **P3** | No shareable links or embed support | Limits organic distribution | Job 1: Evaluate |

---

*End of audit. All findings reference actual files, functions, and components in the current codebase as of 2026-04-05.*

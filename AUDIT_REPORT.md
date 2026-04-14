# Archived / Historical Context Only

This document is preserved for audit history. It is not the current implementation source of truth.

# Briarwood Comprehensive Audit Report

**Date:** 2026-04-12
**Scope:** Code architecture, UI, data pipeline, analytical accuracy, confidence gaps

---

## 1. File-by-File Code Inventory

### Core Engine (briarwood/)

| File | Purpose | Status | Issues |
|------|---------|--------|--------|
| `engine.py` | Module orchestrator — runs 20 modules sequentially, passes `prior_results` | Clean | None |
| `runner.py` | High-level workflow: load JSON, validate, apply defaults, run engine | Clean | None |
| `schemas.py` | Pydantic models + core enums (PropertyInput, AnalysisReport, ModuleResult) | Clean | Large (~500 lines) |
| `defaults.py` | Smart defaults for missing fields with transparent tracking | Clean | Hardcoded NJ tax rate (1.89%), insurance (0.35%), vacancy (5%) |
| `settings.py` | Configuration dataclasses for valuation modules | Needs cleanup | Contains "Bug 1-8" calibration comments mixed with settings |
| `decision_engine.py` | Build recommendation from report (BUY/LEAN BUY/NEUTRAL/LEAN PASS/AVOID) | Clean | Arbitrary thresholds (12%, -15%) with no backtest |
| `risk_bar.py` | 5-category risk scoring (Price, Carry, Liquidity, Execution, Confidence) | Clean | Multipliers (340, 120) appear arbitrary |
| `deal_curve.py` | Price sensitivity: recompute verdict at 100/95/90/85% of ask | Clean | Hardcoded price fractions |
| `base_comp_selector.py` | Tier-based comp selection (tight/loose/broad) | Clean | TODO: cross-town comp support |
| `comp_intelligence.py` | Orchestrates comp stack: selection, features, location, transfer, confidence | Clean | None |
| `feature_adjustment_engine.py` | Feature adjustments (garage, basement, pool, ADU) | Clean | Hardcoded fallbacks ($18k/garage, $35/sqft basement) |
| `micro_location_engine.py` | Beach/downtown/train proximity adjustments | Clean | Hardcoded distance thresholds |
| `town_transfer_engine.py` | Cross-town comp borrowing when <3 same-town comps | Clean | MAX_TRANSFERRED_CONFIDENCE = 0.45 (hardcoded) |
| `comp_confidence_engine.py` | Composite confidence across comp layers | Clean | None |
| `opportunity_metrics.py` | Net opportunity delta (value anchor vs all-in basis) | Clean | None |
| `valuation_constraints.py` | Market friction + nonstandard product detection | Clean | None |
| `scoring.py` | clamp_score() utility | Clean | Trivial |
| `recommendations.py` | Recommendation labels, normalization, ranking | Clean | Score thresholds (3.30/2.50) hardcoded |
| `truth.py` | Confidence classification (Low/Medium/High) | Clean | None |
| `evidence.py` | Evidence aggregation + confidence tracking | Clean | None |
| `scorecard.py` | Build scorecard from analysis results | Clean | None |
| `geocoder.py` | OSM Nominatim geocoding with rate limiting + thread safety | Clean | None |
| `field_audit.py` | Reference: modeled vs descriptive field lists | Clean | None |
| `utils.py` | safe_divide, haversine_miles, current_year | Clean | None |

### Agents (briarwood/agents/)

| File | Purpose | Status | Issues |
|------|---------|--------|--------|
| `comparable_sales/agent.py` | Main comp valuation agent — loads, screens, builds analysis | Clean | TODO: feed measured renovation premium |
| `comparable_sales/store.py` | JSON-backed comp storage | Clean | None |
| `comparable_sales/schemas.py` | Pydantic models for comp structures | Clean | None |
| `comparable_sales/attom_enricher.py` | ATTOM API enrichment for comps | Clean | Hardcoded town-zip mappings |
| `comparable_sales/sr1a_parser.py` | NJ SR1A fixed-width sales file parser | Clean | Position-based parsing is brittle |
| `comparable_sales/modiv_enricher.py` | MOD-IV NJ tax list enrichment | Clean | None |
| `comparable_sales/import_csv.py` | CSV comp import | Clean | None |
| `comparable_sales/ingest_public_bulk.py` | Bulk ingestion (SR1A + MOD-IV) | Clean | None |
| `comparable_sales/curate.py` | Manual comp curation | Clean | None |
| `comparable_sales/geocode.py` | Comp geocoding support | Clean | None |
| `current_value/agent.py` | BCV estimation: weighted blend of 5 anchors | Clean | Anchor weights (40-24-12-8-16) lack empirical basis |
| `current_value/schemas.py` | Input/output schemas for BCV | Clean | None |
| `income/agent.py` | Carrying cost + rental income modeling | Clean | Large (~400 lines) |
| `income/finance.py` | Loan amount + mortgage payment math | Clean | None |
| `rent_context/agent.py` | Rent resolution: provided vs estimated vs missing | Clean | None |
| `rent_context/listing_parser.py` | Extract per-unit rent from listing descriptions | Clean | Regex-based; brittle |
| `rent_context/unit_rent_estimator.py` | Estimate market rent per unit | Clean | Condition multipliers hardcoded |
| `rental_ease/agent.py` | Rental thesis scoring (liquidity/demand/rent/structural) | Clean | Weights (35-25-25-15) lack empirical basis |
| `scarcity/land_scarcity.py` | Land replicability scoring | Clean | Base 50 + arbitrary adjustments |
| `scarcity/location_scarcity.py` | Location advantage scoring | Clean | Same pattern |
| `scarcity/demand_consistency.py` | Market demand consistency scoring | Clean | Same pattern |
| `school_signal/agent.py` | School quality signal | Clean | Weights (30-25-15-15-15) hardcoded |
| `town_county/service.py` | Town/county data service orchestrator | Clean | None |
| `market_history/agent.py` | Zillow ZHVI historical context | Clean | None |

### Modules (briarwood/modules/)

| File | Purpose | Status | Issues |
|------|---------|--------|--------|
| `comparable_sales.py` | Wraps ComparableSalesAgent for pipeline | Clean | Default ADU cap rate 8% hardcoded |
| `current_value.py` | BCV module: blends anchors + confidence caps | Clean | Confidence caps (0.60/0.72/0.65) lack validation |
| `hybrid_value.py` | Multi-unit decomposition (primary + income) | Clean | Cap rate / expense ratios hardcoded |
| `income_support.py` | Income agent wrapper | Clean | None |
| `cost_valuation.py` | Rental viability scoring | Clean | Many hardcoded scoring weights |
| `bull_base_bear.py` | Scenario analysis (bull/base/bear/stress) | Clean | Drift logic asymmetric; stress = historical not forward |
| `liquidity_signal.py` | Exit liquidity composite (DOM/market/comps/rental) | Clean | Weights (35-30-20-15) not validated |
| `market_momentum_signal.py` | Market momentum composite | Clean | Weights (35-25-20-20) not validated |
| `risk_constraints.py` | Risk flag scoring (flood/age/tax/vacancy/DOM) | Clean | Base score 85 + graduated penalties |
| `scarcity_support.py` | Scarcity framework wrapper | Clean | None |
| `rental_ease.py` | Rental ease wrapper | Clean | None |
| `location_intelligence.py` | Geo peer bucket benchmarking | Clean | Distance bucket thresholds hardcoded |
| `market_value_history.py` | ZHVI history wrapper | Clean | None |
| `town_county_outlook.py` | Location outlook wrapper | Clean | None |
| `property_snapshot.py` | Basic property metrics (age, price/sqft) | Clean | None |
| `renovation_scenario.py` | Renovation value-add modeling | Clean | None |
| `teardown_scenario.py` | Demolition/replacement modeling | Clean | None |
| `value_drivers.py` | Value bridge construction | Clean | None |
| `property_data_quality.py` | Input completeness assessment | Clean | None |

### Dash App (briarwood/dash_app/)

| File | Purpose | Status | Issues |
|------|---------|--------|--------|
| `app.py` | Main Dash app with callbacks | Clean | Large (~3500+ lines); render_portfolio_dashboard imported but never called |
| `simple_view.py` | Property analysis page — 5-question visual layout | Clean | render_quick_reality_section() is dead code |
| `viz.py` | Visual components (gauges, strips, charts) | Clean | quick_metric_gauge() unused |
| `components.py` | Reusable UI components + tear sheet body | Needs cleanup | ~7000 lines; 10+ dead chart functions |
| `view_models.py` | ViewModel construction (30+ dataclasses) | Clean | Large but well-organized |
| `data.py` | Data loading, pickle caching, staleness detection | Clean | None |
| `compare.py` | Comparison data model | Clean | None |
| `scenarios.py` | Scenario section renderer | Clean | None |
| `quick_decision.py` | QuickDecisionViewModel builder | Clean | None |
| `theme.py` | Design tokens + semantic colors | Clean | None |
| `data_quality.py` | Diagnostics page (separate from property view) | Clean | None |

### Other

| File | Purpose | Status | Issues |
|------|---------|--------|--------|
| `data_quality/pipeline.py` | DQ pipeline: ingest, normalize, validate, arbitrate | Clean | None |
| `data_quality/eligibility.py` | Comp eligibility classifier | Clean | None |
| `data_quality/normalizers.py` | Field normalization (state, town, date, sqft) | Clean | None |
| `data_quality/provenance.py` | Field provenance tracking | Clean | None |
| `data_sources/attom_client.py` | ATTOM property API client with caching | Clean | None |
| `inputs/property_loader.py` | JSON property loading | Clean | None |
| `inputs/adapters.py` | Input format adapters | Clean | None |
| `listing_intake/service.py` | Listing intake orchestrator | Clean | None |
| `local_intelligence/service.py` | Local intelligence analysis | Clean | None |
| `reports/tear_sheet.py` | Report builder | Clean | None |

**Total files audited: ~150+**
**Dead code found: 4 TODOs, ~12 unused functions (concentrated in components.py), 0 stubs**
**Code quality: HIGH — mature error handling, comprehensive None checks, no bare excepts**

---

## 2. Component Inventory

### Property Analysis Page Components

| Component | Question | Placement | Visual? | Action |
|-----------|----------|-----------|---------|--------|
| Mode Toggle (Retail/Investor) | Navigation | Top | Yes (buttons) | **Keep** |
| Property Header (address, specs, ask) | Context | Top | Yes (layout) | **Keep** |
| **Verdict Gauge** (recommendation + conviction ring + 4 metric sparks) | 1: Should I buy? | Above fold | Yes | **Keep** |
| **Risk Heat Strip** (5 color-coded segments + top risks) | 2: What could go wrong? | Above fold | Yes | **Keep** |
| **Town Pulse Compact** (signal pills + 4 location sparks) | Market context | Below fold | Yes | **Keep** |
| **Value Opportunity Chart** (Plotly horizontal bar + bullet signals) | 3: Where is the value? | Below fold | Yes | **Keep** — needs better driver data |
| **Scenario Fan Chart** (Plotly fan with bull/base/bear paths) | 4: What does this become? | Below fold | Yes | **Keep** |
| **Strategy Radar** (Plotly scatterpolar + factor pills) | 5: Does this fit? | Collapsed | Yes | **Keep** |
| **Deal Curve** (threshold cards + sensitivity table) | Price sensitivity | Collapsed | Mixed | **Keep** |
| Price Support Detail (narrative + waterfall + comp chart) | Evidence: Price | Collapsed | Mixed | **Keep** |
| Financial Detail (cost breakdown + chart + investor metrics) | Evidence: Economics | Collapsed | Mixed | **Keep** |
| Scenarios (historic/forward chart + renovation + teardown) | Evidence: Forward | Collapsed | Mixed | **Keep** |
| Evidence (tear sheet body: comp tables, diagnostics, assumptions) | Evidence: Data | Collapsed | No (tables) | **Keep** — tables appropriate behind collapse |

### Dead / Orphaned Components

| Component | File | Action |
|-----------|------|--------|
| `render_quick_reality_section()` | simple_view.py | **Remove** — superseded by verdict gauge metric sparks |
| `render_decision_section()` (legacy) | simple_view.py | **Remove** — superseded by render_verdict_section |
| `render_price_support()`, `render_financials()`, `render_scenarios()` | simple_view.py | **Remove** — backward compat wrappers, all delegate to render_property_view |
| `forward_waterfall_chart()` | components.py | **Remove** — never called |
| `forward_range_chart()` | components.py | **Remove** — never called |
| `forward_fan_chart()` / `forward_fan_chart_from_ask()` | components.py | **Remove** — replaced by viz.scenario_fan_chart |
| `comp_positioning_dot_plot()` | components.py | **Remove** — never called |
| `location_metrics_bars()` | components.py | **Remove** — never called |
| `income_carry_waterfall()` | components.py | **Remove** — never called |
| `render_compare_section()` | components.py | **Remove** — superseded by render_compare_decision_mode |
| `render_portfolio_dashboard()` | components.py | **Remove** — imported in app.py but never called |
| `quick_metric_gauge()` | viz.py | **Remove** — never called |

**Raw tables in default (non-collapsed) view: NONE confirmed.**

---

## 3. Data Flow

```
INPUT SOURCES
  |
  |- inputs.json (saved properties)
  |- listing text (via ListingIntakeService)  
  |- URL scraping (via ListingIntakeService)
  |
  v
PROPERTY INPUT (PropertyInput dataclass)
  |
  |- Validation (PropertyInputValidationModel)
  |- Smart defaults (defaults.py: down_payment 20%, rate 7%, vacancy 5%, etc.)
  |- Geocoding (geocoder.py: OSM Nominatim)
  |
  v
ANALYSIS ENGINE (engine.py: 20 modules in sequence)
  |
  |- PropertySnapshot ──> raw property facts
  |- PropertyDataQuality ──> input completeness assessment
  |- MarketValueHistory ──> ZHVI trailing 1yr/3yr/5yr changes
  |- ComparableSales ──> comp-derived valuation (3-5 comps, tiered selection)
  |     |- BaseCompSelector (tight/loose/broad tiers)
  |     |- FeatureAdjustmentEngine (garage, basement, pool, ADU)
  |     |- MicroLocationEngine (beach, downtown, train proximity)
  |     |- TownTransferEngine (cross-town borrowing if <3 same-town)
  |     |- CompConfidenceEngine (layered confidence)
  |     |- MarketFriction + MarketFeedback (split-structure, stale listing)
  |
  |- HybridValue ──> multi-unit decomposition (primary + ADU income cap)
  |- CurrentValue ──> BCV blended anchor (comps 40% + market 24% + listing 12% + income 8% + town 16%)
  |- CostValuation ──> rental viability score (cap rate, DSCR, cash flow)
  |- IncomeSupport ──> carry metrics (rent, cost, net, ISR)
  |- RentalEase ──> rental absorption scoring
  |- LiquiditySignal ──> exit liquidity (DOM 35% + market 30% + comps 20% + rental 15%)
  |- BullBaseBear ──> scenario values (market drift + location + risk + optionality)
  |- RiskConstraints ──> risk flag scoring (flood, age, tax, vacancy, DOM)
  |- TownCountyOutlook ──> location strength + appreciation support
  |- ScarcitySupport ──> scarcity/optionality scoring
  |- LocationIntelligence ──> landmark proximity + location premium
  |- LocalIntelligence ──> development activity, regulatory signals
  |- MarketMomentumSignal ──> market momentum composite
  |- RenovationScenario ──> renovation value-add (if enabled)
  |- TeardownScenario ──> demolition/replacement (if enabled)
  |- ValueDrivers ──> value bridge from comps to BCV
  |
  v
ANALYSIS REPORT (AnalysisReport: module_results dict)
  |
  |- DecisionEngine ──> recommendation + conviction + evidence_quality
  |- RiskBar ──> 5 risk items (Price, Carry, Liquidity, Execution, Confidence)
  |- DealCurve ──> price sensitivity at 4 entry points
  |
  v
VIEW MODELS (view_models.py: PropertyAnalysisView)
  |
  |- build_property_analysis_view() ──> 30+ nested view model dataclasses
  |- build_quick_decision_view() ──> QuickDecisionViewModel
  |- build_market_view_model() ──> market comparison data
  |
  v
RENDERED PAGE (simple_view.py → viz.py)
  |
  |- Verdict gauge (fv_gap, carry, stabilized CF, confidence)
  |- Risk heat strip (5 categories)
  |- Town pulse (market signals + location metrics)
  |- Value opportunity chart (drivers + bullets)
  |- Scenario fan chart (bull/base/bear paths)
  |- Strategy radar (6-dimension factor scores)
  |- [Collapsed: deal curve, price/financials, scenarios, evidence]
```

### Gaps in Flow

| Gap | Description |
|-----|-------------|
| **Computed but never displayed** | PropertyDataQuality metrics, RentalEase detail (only liquidity integration shown), TownCountyOutlook detail (only score shown), MarketValueHistory 5yr+ points, ValueDrivers detail breakdown |
| **Displayed but thinly computed** | Scarcity score (heuristic keyword matching), optionality premium (keyword triggers ±2%), execution risk (capex lane lookup + flat penalties) |
| **Hardcoded assumptions not surfaced** | User never sees: BCV anchor weights, comp similarity weights, risk multipliers, scenario drift logic, confidence cap reasons |

---

## 4. Per-Question Accuracy Assessment

### Question 1: "Should I buy this?" — Verdict

| Metric | Computation | Reliability | What would improve it |
|--------|-------------|-------------|----------------------|
| **Fair Value (BCV)** | Weighted blend: comps 40% + market-adjusted 24% + listing 12% + income 8% + town 16%. Uses 3-5 comps via tiered selection | **MEDIUM** | Backtest anchor weights against repeat-sale prediction accuracy |
| **Mispricing %** | `(BCV - ask) / ask` | **HIGH** (math is simple; accuracy depends on BCV) | Improve BCV accuracy |
| **Conviction** | `anchor(0.24-0.82) × 0.65 + evidence_quality × 0.25 + band_strength × 0.10` | **MEDIUM** | Validate that 0.72 conviction actually predicts 72% positive outcomes |
| **Evidence quality** | `cv×0.32 + inc×0.23 + comp×0.23 + pdq×0.12 + town×0.10` | **MEDIUM** | Empirically derive weights from prediction error analysis |
| **Confidence (overall)** | Weighted blend of rent, capex, market, liquidity confidences (view_models.py) | **MEDIUM** | Backtest: do 70% confidence reports actually land within ±15% of realized values? |

**Current values observed:**
- Briarwood Rd: evidence_quality=0.69, conviction=0.51 (NEUTRAL), overall_confidence=70%
- L Street: evidence_quality=0.69, conviction=0.36 (AVOID), overall_confidence=67%

**Key drags on confidence:** Property data quality (0.48) and comp confidence (0.61-0.62) are the weakest components. Both properties have PDQ at 48% — this is the single biggest confidence drag.

### Question 2: "What could go wrong?" — Risk

| Metric | Computation | Reliability | What would improve it |
|--------|-------------|-------------|----------------------|
| **Price Risk** | `premium_gap × 340 - discount_gap × 120`, clamped 0-100 | **LOW** | Multipliers (340, 120) have no stated empirical basis |
| **Carry Risk** | `ratio_score × 0.65 + shortfall_score × 0.35`, piecewise linear | **MEDIUM** | Validate carry thresholds ($250, $1500, $3000) against default rates |
| **Liquidity Risk** | `100 - liquidity_score + penalties` (comp count, DOM) | **MEDIUM** | Backtest against actual days-to-sale |
| **Execution Risk** | Capex lane lookup (light=22, moderate=48, heavy=78) + condition/capex penalties | **MEDIUM** | Rules-based and transparent; penalties for missing data reasonable |
| **Confidence Risk** | `100 - (overall_confidence × 100) + penalties` | **MEDIUM** | Reasonable inverse-confidence model |

**Critical issue:** Risk categories are scored independently — no correlation adjustment. High price risk + high execution risk should compound, not average.

### Question 3: "Where is the value?" — Value

| Metric | Computation | Reliability | What would improve it |
|--------|-------------|-------------|----------------------|
| **ADU income** | From income agent: market rent × 12 × (1 - vacancy) | **MEDIUM** | Use property-specific comp rents, not town-level estimates |
| **Price dislocation** | BCV mispricing % × ask price | **MEDIUM** (derived from BCV) | Improve BCV accuracy |
| **Expansion upside** | Scarcity score × $100K (in viz rendering) | **LOW** | Arbitrary multiplier; needs empirical basis |
| **Market tailwind** | Market momentum score × $500 (in viz rendering) | **LOW** | Arbitrary multiplier; no evidence $500/point is meaningful |
| **Scarcity score** | `(location_scarcity × 0.55 + land_scarcity × 0.45) × 0.60 + demand_consistency × 0.40` | **LOW** | Heavily heuristic; keyword-driven optionality is brittle |

**Critical issue:** Value driver dollar amounts in the opportunity chart use arbitrary scaling. Expansion score × $100K and tailwind × $500 are rendering artifacts, not analytical outputs.

### Question 4: "What does this become?" — Projection

| Metric | Computation | Reliability | What would improve it |
|--------|-------------|-------------|----------------------|
| **Market drift** | From ZHVI trailing rates: bull=max(1yr, 3yr CAGR) capped 15%, bear=min(1yr, 5yr) × 0.5 floored -20% | **MEDIUM** | Asymmetric logic lacks stated rationale; validate against forward returns |
| **Location premium** | `(town_score - 50)/50 × scale_factor`, capped ±8% | **MEDIUM** | Validate town_score differential against realized appreciation spreads |
| **Risk adjustment** | Tiered penalty: score≥85 → 0%, 70-85 → 0-5%, 50-70 → 5-12%, <50 → 12-20% | **MEDIUM** | Thresholds (85/70/50) appear arbitrary |
| **Optionality premium** | `(scarcity_score / 100) × 8%` in bull case only | **LOW** | 8% max is arbitrary; scarcity relationship not validated |
| **Stress scenario** | -25% default, -30% medium flood, -35% high flood (2007-2011 NJ coastal correction) | **MEDIUM** | Historical, not probability-weighted forward; geographically specific |
| **Scenario spread** | Bull/base/bear are additive compositions, not Monte Carlo | **MEDIUM** | Deterministic scenarios; spread width IS the uncertainty |

**Critical issue:** Scenarios compound from BCV, so BCV error propagates and amplifies through all three paths.

### Question 5: "Does this fit my strategy?" — Fit

| Metric | Computation | Reliability | What would improve it |
|--------|-------------|-------------|----------------------|
| **Factor scores** (6 dimensions) | From report_card: entry_basis, income_support, capex_load, liquidity_profile, optionality, risk_skew. Each -1.0 to +1.0 | **MEDIUM** | Scoring is derived from real analysis; weights in the radar are equal (not personalized) |
| **Capital required** | `ask_price × down_payment_pct` (default 20%) | **HIGH** | Simple math |
| **Complexity** | Derived from capex_lane label (light/moderate/heavy) | **MEDIUM** | Transparent mapping |
| **Positive/negative factors** | From ReportCardViewModel: top 3 contribution items | **MEDIUM** | Real analysis output |

**Critical issue:** Fit is NOT personalized. There is no user strategy profile. The radar shows property characteristics, not fit against a target. The section title ("Does this fit my strategy?") overpromises — it should be "Property Profile" until personalization exists.

---

## 5. Confidence Improvement Roadmap

Current observed confidence: **67-70%** across saved properties.

### Confidence Formula (view_models.py)
```
overall = rent_conf × 0.30 + capex_conf × 0.25 + market_conf × 0.25 + liquidity_conf × 0.20
```

### Factor-by-Factor Breakdown

| Factor | Current | Weight | Gap Contribution | What Drags It Down | Fix | Estimated Lift |
|--------|---------|--------|------------------|--------------------|----|----------------|
| **Rent** | 68-72% | 0.30 | 8.4-9.6% gap | Estimated rent (not actuals); confidence capped at 72% when rent is estimated | Add comp-derived rent validation; connect to actual rental listings data | +3-5% overall |
| **Capex** | 62-72% | 0.25 | 7.0-9.5% gap | Renovation burden estimated not measured; capex basis often "inferred_condition" | Add actual renovation cost estimates; inspection-based condition grading | +2-4% overall |
| **Market** | 70% | 0.25 | 7.5% gap | ZHVI coverage sufficient; town confidence decent (0.90) but some uncertainty | More granular sub-market data (neighborhood vs town level) | +1-2% overall |
| **Liquidity** | 66% | 0.20 | 6.8% gap | Comp depth moderate (4-5 comps); DOM data available but limited exit velocity history | More comps; actual absorption rate data; listing agent feedback | +2-3% overall |

### Evidence Quality (Decision Engine) — Separate Formula
```
evidence_quality = cv×0.32 + inc×0.23 + comp×0.23 + pdq×0.12 + town×0.10
```

| Factor | Current | Weight | Drag | Fix | Lift |
|--------|---------|--------|------|-----|------|
| **Property Data Quality** | 0.48 | 0.12 | **Highest drag per weight** | Fill missing structural fields (lot_size, basement, garage); add ATTOM enrichment | +2-3% evidence quality |
| **Comp Confidence** | 0.61-0.62 | 0.23 | **Largest absolute drag** | More comps (≥6 same-town); tighter similarity matches; adjust for recency | +3-5% evidence quality |
| **Current Value** | 0.71 | 0.32 | Moderate | Improve comp quality (feeds into BCV); validate with multiple anchor methods | +1-2% evidence quality |
| **Income** | 0.76 | 0.23 | Low | Already decent; would improve with actual lease data | +1% evidence quality |
| **Town** | 0.90 | 0.10 | Negligible | Already strong | Negligible |

### Priority-Ranked Improvement Actions

| Priority | Action | Effort | Confidence Lift | Evidence Quality Lift |
|----------|--------|--------|-----------------|----------------------|
| **1** | Add more comps (target ≥6 same-town via SR1A/ATTOM bulk ingest) | Medium | +3-4% | +3-5% |
| **2** | Fill missing structural fields via ATTOM enrichment (lot_size, garage, basement) | Low | +1-2% | +2-3% |
| **3** | Connect actual rental listing data for rent validation | Medium | +3-5% | +1% |
| **4** | Add inspection-based condition grading or renovation cost estimates | High | +2-4% | +1% |
| **5** | Validate BCV with repeat-sale backtesting | High | Indirect | +2-3% |
| **6** | Sub-market (neighborhood) data instead of town-level | High | +1-2% | +1% |

**Projected confidence after top 3 fixes: 74-79% (from current 67-70%)**

---

## 6. Prioritized Punch List

### Tier 1: Blocks Next Phase (Must Fix)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 1.1 | **Value driver dollar amounts are rendering artifacts.** `expansion_score × $100K` and `tailwind × $500` are arbitrary multipliers baked into `render_value_section()`, not analytical outputs. The opportunity chart shows fake magnitudes. | simple_view.py:289-297 | Value chart is misleading |
| 1.2 | **Strategy Fit section is not personalized.** No user strategy profile exists. Radar shows property characteristics, not fit against target. Section title overpromises. | simple_view.py:325-350, viz.py | Section answers wrong question |
| 1.3 | **Decision thresholds (12%, -15%, $250, $3000) are hardcoded with no backtest.** These determine BUY vs AVOID verdicts for every property. If they're wrong, every recommendation is wrong. | decision_engine.py:121-198 | Core recommendation accuracy |
| 1.4 | **Risk multipliers (340, 120) have no empirical basis.** Price risk formula uses arbitrary scaling that determines "High" vs "Low" risk labels. | risk_bar.py:45-65 | Risk assessment accuracy |
| 1.5 | **Comp similarity weights (30-25-30-15) and BCV anchor weights (40-24-12-8-16) are not validated.** These are the most consequential numbers in the system — they determine fair value. | comparable_sales.py:190-195, current_value/agent.py | Fair value accuracy |

### Tier 2: Degrades Quality (Should Fix)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 2.1 | **~12 dead chart functions in components.py.** forward_waterfall_chart, forward_range_chart, forward_fan_chart, comp_positioning_dot_plot, location_metrics_bars, income_carry_waterfall, render_compare_section, render_portfolio_dashboard. ~500 lines of dead code. | components.py | Code bloat, maintenance burden |
| 2.2 | **Dead functions in simple_view.py.** render_quick_reality_section, legacy render_decision_section, backward-compat wrappers (render_price_support, render_financials, render_scenarios). | simple_view.py | Code bloat |
| 2.3 | **Scenario drift logic is asymmetric with no rationale.** Bull uses max(1yr, 3yr); bear uses min(1yr, 5yr) × 0.5. Why the asymmetry? | bull_base_bear.py:281-306 | Scenario accuracy |
| 2.4 | **Stress scenario is historical, not forward.** 25-35% drawdown based on 2007-2011 NJ coastal correction. Not probability-weighted; not geography-adjusted beyond flood. | bull_base_bear.py:149-159 | Stress test relevance |
| 2.5 | **PropertyDataQuality confidence at 0.48 is the biggest drag** on evidence quality, but the view model doesn't surface why or what inputs would fix it. | modules/property_data_quality.py, view_models.py | User can't improve their analysis |
| 2.6 | **Risk categories scored independently — no correlation.** Price risk + execution risk should compound in renovation scenarios. | risk_bar.py | Risk assessment accuracy |
| 2.7 | **Scarcity optionality premium triggered by keyword matching.** "cottage" → +1.5%, "ADU" → +2.0%. Brittle and arbitrary. | hybrid_value.py | Optionality valuation accuracy |
| 2.8 | **settings.py mixes calibration notes ("Bug 1-8") with production config.** | settings.py | Maintainability |
| 2.9 | **Confidence caps (0.60, 0.65, 0.72) are not validated.** When rent is missing, confidence is capped at 0.60 — but is the BCV actually ±25% less accurate without rent? | settings.py:48-54 | Confidence calibration |
| 2.10 | **4 known TODOs remain unaddressed.** Cross-town comp support, geography-aware PPSF ($400/sqft hardcoded), renovation premium feed. | base_comp_selector.py:377, scoring.py:802, scoring_config.py:250, agent.py:768 | Analytical completeness |

### Tier 3: Nice to Have (Fix When Possible)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 3.1 | **components.py is ~7000 lines.** Should be split into logical sub-modules (charts.py, evidence.py, comparison.py, premium_page.py). | components.py | Maintainability |
| 3.2 | **SR1A parser uses position-based fixed-width parsing.** Brittle if NJ changes the record format. | sr1a_parser.py | Data ingestion robustness |
| 3.3 | **Feature adjustment fallbacks are hardcoded.** $18k/garage, $35/sqft basement, $15k pool. These are reasonable but should be market-sourced. | feature_adjustment_engine.py | Valuation precision |
| 3.4 | **Town-zip mappings in ATTOM enricher are hardcoded to Monmouth County.** Will need expansion for multi-county support. | attom_enricher.py | Geographic expansion |
| 3.5 | **No model governance dashboard.** Can't track whether recommendation accuracy is improving or degrading over time. | N/A (not built) | Long-term accuracy |
| 3.6 | **Computed metrics never displayed:** PropertyDataQuality detail, RentalEase detail, full ValueDrivers breakdown, ZHVI 5yr+ historical points. | Various modules | Information density |
| 3.7 | **Listing parser uses regex for unit extraction.** Works but brittle for unusual listing formats. | rent_context/listing_parser.py | Rent estimation robustness |
| 3.8 | **Rent source confidence can be overridden by user.** User can force "high" confidence on estimated rent, bypassing data quality. No audit trail. | income/agent.py | Data integrity |
| 3.9 | **All distance/lot/location adjustment factors lack published empirical basis.** 0.015 per mile, ±8% cap, ±12% lot. | micro_location_engine.py, base_comp_selector.py | Adjustment precision |
| 3.10 | **quick_metric_gauge() in viz.py is dead code.** | viz.py | Code hygiene |

---

## Summary

**Architecture:** Clean, well-organized, mature. Agent-module-engine hierarchy works. ~150 files, all with clear responsibility. No stubs, no placeholders, comprehensive error handling.

**UI:** Visual-first refactoring is complete. No raw tables in default view. All 5 questions have dedicated visual sections. ~12 dead chart functions in components.py need cleanup.

**Data Pipeline:** End-to-end traceable. 20 modules in defined sequence. Confidence flows through every layer. Main gaps: computed-but-not-displayed metrics and hardcoded assumptions not surfaced to user.

**Analytical Accuracy:** MEDIUM overall. Comp selection methodology is solid (HIGH). BCV blending, risk scoring, and scenario modeling are reasonable but rely on unvalidated weights and thresholds (MEDIUM). Scarcity, optionality, and value driver scaling are heuristic (LOW).

**Confidence:** 67-70% across properties. Biggest drags: property data quality (0.48) and comp confidence (0.61). Adding more comps + filling structural fields could push confidence to 74-79%.

**Highest-impact next actions:**
1. Fix value chart scaling (rendering artifacts masquerading as analysis)
2. Rename/redesign "Strategy Fit" to honest "Property Profile" until personalization exists
3. Backtest decision thresholds against actual outcomes
4. Bulk-ingest more comps to improve comp confidence
5. Remove ~500 lines of dead code from components.py

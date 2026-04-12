# Briarwood Codebase Inventory

Generated: 2026-04-11

Briarwood is a Dash (Plotly) real estate investment analysis platform focused on NJ coastal/Monmouth County properties. It ingests listing data, runs a multi-module analysis engine, scores properties on a 1-5 scale, and produces interactive dashboards and PDF/HTML tear sheets.

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Python source files (excl. venv, __pycache__, .cache) | ~160 |
| Test files | ~60 |
| Non-test source files | ~100 |
| Estimated total lines of Python | ~64,800 |
| CSS files | 2 |
| HTML templates | 1 |
| JSON data/config files | ~180+ |

---

## 1. Root Files

### app.py (123 lines)
- **Purpose:** CLI entry point for running property reports from JSON files or pasted listing text. Supports preview-intake mode and various overrides (loan term, interest rate, etc.).
- **Dependencies:** `briarwood.runner`, `briarwood.settings`
- **Status:** Active -- primary CLI interface
- **UI/Feature:** N/A (CLI only)

### run_dash.py (6 lines)
- **Purpose:** Launches the Dash web application on port 8050.
- **Dependencies:** `briarwood.dash_app.app`
- **Status:** Active -- web app launcher
- **UI/Feature:** Powers the entire Dash UI

---

## 2. briarwood/ Core Modules

### __init__.py (11 lines)
- **Purpose:** Package init; loads `.env` via `python-dotenv` if available.
- **Dependencies:** `dotenv` (optional)
- **Status:** Active

### schemas.py (685 lines)
- **Purpose:** Central data model file. Defines `PropertyInput`, `AnalysisReport`, `ModuleResult`, `AnalysisModule` protocol, `UnitDetail`, `CanonicalPropertyData`, `PropertyFacts`, `UserAssumptions`, `SourceMetadata`, `MarketLocationSignals`, evidence/coverage enums, and all output dataclasses (`ValuationOutput`, `ScenarioOutput`, `LocationIntelligenceOutput`, `LiquiditySignalOutput`, `MarketMomentumOutput`, `LocalIntelligenceOutput`, `RelativeOpportunityOutput`, etc.).
- **Dependencies:** pydantic, dataclasses, enum
- **Status:** Active -- imported by virtually every module
- **UI/Feature:** Foundation for all analysis data flow

### engine.py (39 lines)
- **Purpose:** `AnalysisEngine` -- orchestrates running all registered `AnalysisModule` instances in order, threading `prior_results` to modules that accept them.
- **Dependencies:** `briarwood.schemas`
- **Status:** Active -- central pipeline orchestrator

### runner.py (423 lines)
- **Purpose:** High-level report pipeline. `build_engine()` constructs the full module graph; `run_report()` loads a property and runs the engine; `format_report()` prints results; `write_report_html()` generates tear sheets. Also handles listing-text and URL intake flows.
- **Dependencies:** All module classes, `briarwood.engine`, `briarwood.inputs.property_loader`, `briarwood.listing_intake`, `briarwood.reports`, `briarwood.decision_model.scoring_config`
- **Status:** Active -- used by both CLI (`app.py`) and Dash (`data.py`)
- **UI/Feature:** Powers report generation for all surfaces

### evidence.py (1,153 lines)
- **Purpose:** Evidence and confidence computation. `build_section_evidence()` creates coverage assessments. `compute_confidence_breakdown()`, `compute_critical_assumption_statuses()`, `compute_metric_input_statuses()` provide input-aware confidence analysis for the dashboard.
- **Dependencies:** `briarwood.schemas`
- **Status:** Active -- used by every module for section evidence, and by `view_models.py` for confidence dashboards
- **UI/Feature:** Powers the Evidence & Confidence panel in the Dash UI

### scorecard.py (207 lines)
- **Purpose:** Builds a 6-dimension `ScoreCard` (value_support, income_support, location_quality, risk, confidence, overall) from an `AnalysisReport` for dashboard summary display.
- **Dependencies:** `briarwood.reports.section_helpers`, `briarwood.schemas`
- **Status:** Active -- used by `dashboard_contract.py`
- **UI/Feature:** Powers portfolio-level summary cards

### dashboard_contract.py (154 lines)
- **Purpose:** Defines `DashboardAnalysisSummary` and `DashboardSectionSummary` dataclasses; `build_dashboard_analysis_summary()` converts a report into a dashboard-ready summary. Also defines `MODULE_DEPENDENCIES` graph.
- **Dependencies:** `briarwood.scorecard`, `briarwood.reports.section_helpers`, `briarwood.schemas`
- **Status:** Active -- used by Dash data layer
- **UI/Feature:** Dashboard section summaries

### defaults.py (122 lines)
- **Purpose:** Smart defaults for missing property data. `apply_smart_defaults()` populates None fields with reasonable NJ coastal market estimates (interest rate, vacancy, insurance, etc.) and records what was applied.
- **Dependencies:** `briarwood.schemas`
- **Status:** Active -- called during property loading
- **UI/Feature:** Ensures analysis works with minimal input

### entry_prep.py (68 lines)
- **Purpose:** Defines the `EntryPrepContract` -- documentation of required fields for property and comp entry, plus `save_manual_property()` and `save_manual_comp()` functions for the manual entry workflow.
- **Dependencies:** `briarwood.agents.comparable_sales`, `briarwood.dash_app.data`
- **Status:** Active -- used by the "Add Property" and "Add Comp" flows in the Dash UI
- **UI/Feature:** Manual property/comp entry

### field_audit.py (85 lines)
- **Purpose:** `audit_property_fields()` inspects a `PropertyInput` and classifies each modeled field as present, missing, or estimated. Used by `current_value` module to report data completeness.
- **Dependencies:** `briarwood.schemas`
- **Status:** Active -- called by `modules/current_value.py`

### geocoder.py (90 lines)
- **Purpose:** Free geocoding via OpenStreetMap Nominatim. Rate-limited (1 req/sec), thread-safe, results cached via `lru_cache`.
- **Dependencies:** `requests` (delayed import), `briarwood.schemas`
- **Status:** Active -- used by `dash_app/data.py` for geocoding saved properties
- **External:** OpenStreetMap Nominatim API

### opportunity_metrics.py (82 lines)
- **Purpose:** `calculate_net_opportunity_delta()` computes the gap between value anchor and all-in basis (purchase + capex). `infer_capex_amount()` estimates capex from lane/condition if not explicitly provided.
- **Dependencies:** None (standalone)
- **Status:** Active -- used by `modules/current_value.py`, `modules/relative_opportunity.py`

### recommendations.py (49 lines)
- **Purpose:** Recommendation label logic: maps scores to Buy/Neutral/Avoid, normalizes variant labels, provides ranking and downgrade/cap functions.
- **Dependencies:** None (standalone)
- **Status:** Active -- used by `decision_model/scoring.py`, `dash_app/view_models.py`, `dash_app/theme.py`

### scoring.py (4 lines)
- **Purpose:** Single utility: `clamp_score()` -- clamps a float between floor and ceiling.
- **Dependencies:** None
- **Status:** Active -- used by many scoring modules

### settings.py (100 lines)
- **Purpose:** Runtime configuration dataclasses: `CostValuationSettings` (vacancy rates, maintenance reserves, confidence caps), `CurrentValueSettings`, `RenovationScenarioSettings`, `TeardownScenarioSettings`, `RelativeOpportunitySettings`. Each has calibrated defaults.
- **Dependencies:** None (standalone)
- **Status:** Active -- imported by modules and runner

### truth.py (46 lines)
- **Purpose:** `classify_confidence()` -- shared confidence taxonomy (Low/Medium/High bands with narrative levels Provisional/Estimated/Grounded) based on overall confidence, comp count, rent source, and town confidence.
- **Dependencies:** None
- **Status:** Active -- used by `decision_model/scoring.py`, `dash_app/view_models.py`

### utils.py (24 lines)
- **Purpose:** Small utilities: `current_year()`, `safe_divide()`, `haversine_miles()`.
- **Dependencies:** None
- **Status:** Active -- used by modules and agents

---

## 3. briarwood/agents/ -- Domain-Specific Scoring Agents

Each agent is a focused scoring/analysis unit with typed input/output schemas.

### agents/__init__.py (1 line)
- Empty package marker.

### agents/comparable_sales/ (3,833 lines total)

#### __init__.py (51 lines)
- Re-exports all public symbols from the sub-package.

#### agent.py (913 lines)
- **Purpose:** `ComparableSalesAgent` -- the core comp analysis engine. Loads comp data via `FileBackedComparableSalesProvider`, filters by town/distance/recency, applies property-specific adjustments (time, size, condition, location), produces `ComparableSalesOutput` with value range, adjusted comps, and confidence metrics.
- **Dependencies:** `schemas`, `data_quality.eligibility`, `data_quality.pipeline`, `market_history.schemas`, `briarwood.utils`
- **Status:** Active -- central to valuation
- **UI/Feature:** Powers comp analysis across all views

#### attom_enricher.py (390 lines)
- **Purpose:** Enriches comp records with ATTOM property detail API data (beds, baths, sqft, year_built, lot_size, lat/lon). CLI-runnable.
- **Dependencies:** `requests`, `agents.comparable_sales.schemas`
- **Status:** Active -- used by enrichment scripts
- **External:** ATTOM API

#### curate.py (82 lines)
- **Purpose:** CLI tool to generate a blank manual comp template JSON and save it to the comp store. Used for seeding the comp database with manually researched sales.
- **Dependencies:** `agents.comparable_sales.schemas`, `agents.comparable_sales.store`
- **Status:** Active -- manual comp entry workflow

#### geocode.py (37 lines)
- **Purpose:** Protocol and helpers for geocoding comp addresses. `enrich_sale_with_geocode()` and `enrich_listing_with_geocode()` add lat/lon to records.
- **Dependencies:** `agents.comparable_sales.schemas`
- **Status:** Active

#### import_csv.py (501 lines)
- **Purpose:** CSV import for comp data. Parses CSV/Excel rows into `ComparableSale` or `ActiveListingRecord` objects with field aliasing, normalization, and merge/append logic.
- **Dependencies:** `agents.comparable_sales.schemas`, `agents.comparable_sales.store`
- **Status:** Active -- used by scripts and audit_scripts
- **UI/Feature:** Bulk comp import pipeline

#### ingest_public_bulk.py (279 lines)
- **Purpose:** Orchestrates bulk ingestion: SR1A + MOD-IV data into the comp store. CLI-runnable.
- **Dependencies:** `modiv_enricher`, `sr1a_parser`, `store`
- **Status:** Active -- public records pipeline

#### ingest_public_records.py (521 lines)
- **Purpose:** Lower-level public record ingestion. Loads CSV/TSV public record rows, applies MOD-IV enrichment, merges SR1A verification status.
- **Dependencies:** `agents.comparable_sales.schemas`
- **Status:** Active -- used by `ingest_public_bulk.py`

#### modiv_enricher.py (321 lines)
- **Purpose:** Enriches comps with NJ MOD-IV property tax list data (year_built, assessed values, lot acreage, lat/lon from parcel centroids). Joins by block/lot/qualifier.
- **Dependencies:** `agents.comparable_sales.schemas`, `briarwood.utils`
- **Status:** Active

#### schemas.py (224 lines)
- **Purpose:** Pydantic models for comp data: `ComparableSale`, `ActiveListingRecord`, `AdjustedComparable`, `ComparableSalesOutput`, `ComparableSalesRequest`, `ComparableValueRange`.
- **Dependencies:** pydantic
- **Status:** Active -- used everywhere comps are referenced

#### sr1a_parser.py (381 lines)
- **Purpose:** Parses NJ SR1A fixed-width (662-char) deed transfer files into `ComparableSale` records. Contains Monmouth County district code mappings.
- **Dependencies:** `agents.comparable_sales.schemas`, `briarwood.utils`
- **Status:** Active -- NJ public records ingestion

#### store.py (132 lines)
- **Purpose:** `JsonComparableSalesStore` and `JsonActiveListingStore` -- lightweight JSON-backed persistence for comp data with load/save/upsert.
- **Dependencies:** pydantic, `agents.comparable_sales.schemas`
- **Status:** Active -- central comp persistence layer

### agents/current_value/ (692 lines total)

#### __init__.py (15 lines)
- Re-exports agent and schema classes.

#### agent.py (456 lines)
- **Purpose:** `CurrentValueAgent` -- estimates Briarwood Current Value (BCV) by blending 5 components: comparable sales value, market-adjusted value, backdated listing value, income-supported value, and town prior. Applies dynamic weighting based on data availability.
- **Dependencies:** `current_value.schemas`, `market_history.schemas`
- **Status:** Active -- core valuation agent

#### inspect_data.py (116 lines)
- **Purpose:** One-off data inspection script for parsing Monmouth County public record text files. Extracts town, zip, year_built, assessed values.
- **Dependencies:** csv, re (stdlib only)
- **Status:** Likely dead code / historical utility -- not imported by any other file

#### schemas.py (105 lines)
- **Purpose:** Pydantic models: `CurrentValueInput`, `CurrentValueOutput`, `CurrentValueComponents`, `CurrentValueWeights`, `CurrentValueTraceItem`.
- **Dependencies:** pydantic, `market_history.schemas`, `comparable_sales.schemas`
- **Status:** Active

### agents/income/ (574 lines total)

#### __init__.py (11 lines)
- Re-exports `IncomeAgent`, `IncomeAgentInput`, `IncomeAgentOutput`.

#### agent.py (461 lines)
- **Purpose:** `IncomeAgent` -- models monthly ownership economics: mortgage P&I, taxes, insurance, HOA, vacancy, maintenance vs. rental income. Produces DSCR, cap rate, cash-on-cash return, income support ratio.
- **Dependencies:** `income.finance`, `income.schemas`
- **Status:** Active -- core income analysis

#### finance.py (26 lines)
- **Purpose:** `calculate_loan_amount()` and `calculate_monthly_principal_interest()` -- standard mortgage math.
- **Dependencies:** None
- **Status:** Active

#### schemas.py (76 lines)
- **Purpose:** Pydantic models: `IncomeAgentInput`, `IncomeAgentOutput` with all monthly ownership snapshot fields.
- **Dependencies:** pydantic
- **Status:** Active

### agents/market_history/ (233 lines total)

#### __init__.py (17 lines)
- Re-exports agent, provider, and schema classes.

#### agent.py (143 lines)
- **Purpose:** `MarketValueHistoryAgent` -- builds market-level historical value context from Zillow ZHVI-style data. Computes 1/3/5-year change percentages.
- **Dependencies:** `market_history.schemas`
- **Status:** Active

#### provider.py (33 lines)
- **Purpose:** `FileBackedZillowHistoryProvider` -- loads Zillow-style historical home value data from a JSON fixture file.
- **Dependencies:** None (stdlib json)
- **Status:** Active

#### schemas.py (40 lines)
- **Purpose:** Pydantic models: `HistoricalValuePoint`, `MarketValueHistoryRequest`, `MarketValueHistoryOutput`.
- **Dependencies:** pydantic
- **Status:** Active

### agents/rent_context/ (382 lines total)

#### __init__.py (9 lines)
- Re-exports agent and schema classes.

#### agent.py (75 lines)
- **Purpose:** `RentContextAgent` -- resolves whether rent is user-provided, estimable from town priors, or missing. Critical for determining evidence mode.
- **Dependencies:** `rent_context.priors`, `rent_context.schemas`
- **Status:** Active

#### listing_parser.py (104 lines)
- **Purpose:** `parse_units_from_listing()` -- extracts per-unit details (beds, baths, sqft, condition) from listing description text using regex patterns.
- **Dependencies:** `briarwood.schemas` (UnitDetail)
- **Status:** Active -- used by `modules/comparable_sales.py`

#### priors.py (69 lines)
- **Purpose:** Town-level rent priors for Monmouth County shore towns (Belmar, Bradley Beach, Avon, Spring Lake, etc.). Provides `monthly_rent_per_sqft` and `base_monthly_rent_by_bed`.
- **Dependencies:** None (standalone)
- **Status:** Active

#### schemas.py (28 lines)
- **Purpose:** Pydantic models: `RentContextInput`, `RentContextOutput`.
- **Dependencies:** pydantic
- **Status:** Active

#### unit_rent_estimator.py (97 lines)
- **Purpose:** `estimate_unit_market_rent()` and `estimate_units_market_rent()` -- estimates market rent for individual rental units using town priors with condition multipliers.
- **Dependencies:** `rent_context.priors`, `briarwood.schemas`
- **Status:** Active -- used by `modules/comparable_sales.py`

### agents/rental_ease/ (721 lines total)

#### __init__.py (15 lines)
- Re-exports agent and schema classes.

#### agent.py (391 lines)
- **Purpose:** `RentalEaseAgent` -- scores how easy and durable the rental thesis is for a property. Blends liquidity, demand depth, rent support, and structural support with town-specific priors.
- **Dependencies:** `rental_ease.narrative`, `rental_ease.priors`, `rental_ease.schemas`, `rental_ease.scoring`
- **Status:** Active

#### context.py (56 lines)
- **Purpose:** `ZillowRentContext` model and `FileBackedZillowRentContextProvider` -- loads market-level Zillow rental research data (ZORI, ZORDI).
- **Dependencies:** pydantic
- **Status:** Active

#### narrative.py (49 lines)
- **Purpose:** `build_rental_ease_summary()` -- generates a human-readable rental ease narrative from component scores.
- **Dependencies:** None
- **Status:** Active

#### priors.py (92 lines)
- **Purpose:** `RentalEasePrior` dataclass and `MONMOUTH_RENTAL_EASE_PRIORS` dict -- town-level rental absorption priors (liquidity, seasonality, demand, desirability, fragility, days-to-rent).
- **Dependencies:** None
- **Status:** Active

#### schemas.py (61 lines)
- **Purpose:** Pydantic models: `RentalEaseInput`, `RentalEaseOutput`.
- **Dependencies:** pydantic
- **Status:** Active

#### scoring.py (57 lines)
- **Purpose:** Scoring helper functions: `liquidity_view_to_score()`, `rent_support_to_score()`, `label_for_score()`.
- **Dependencies:** `briarwood.scoring`
- **Status:** Active

### agents/scarcity/ (789 lines total)

#### __init__.py (35 lines)
- Re-exports all scarcity-related classes and functions.

#### demand_consistency.py (181 lines)
- **Purpose:** `DemandConsistencyScorer` -- scores how reliably a market rewards scarce/desirable traits, using liquidity signal, supply months, DOM, price trends, school signal.
- **Dependencies:** `scarcity.schemas`, `briarwood.scoring`
- **Status:** Active

#### land_scarcity.py (135 lines)
- **Purpose:** `LandScarcityScorer` -- scores how difficult it is to replicate a property's lot attributes (lot size ratio, corner lot, ADU possibility, redevelopment option).
- **Dependencies:** `scarcity.schemas`, `briarwood.scoring`
- **Status:** Active

#### location_scarcity.py (147 lines)
- **Purpose:** `LocationScarcityScorer` -- scores how difficult it is to replicate a property's location advantages (distance to anchor, comparable count within radius).
- **Dependencies:** `scarcity.schemas`, `briarwood.scoring`
- **Status:** Active

#### scarcity_support.py (170 lines)
- **Purpose:** `ScarcitySupportScorer` -- combines demand consistency, location scarcity, and land scarcity into a composite scarcity support score.
- **Dependencies:** `demand_consistency`, `land_scarcity`, `location_scarcity`, `scarcity.schemas`
- **Status:** Active

#### schemas.py (121 lines)
- **Purpose:** Pydantic input/output models for all three scarcity sub-scorers plus the composite `ScarcitySupportInputs`/`ScarcitySupportScore`.
- **Dependencies:** pydantic
- **Status:** Active

### agents/school_signal/ (657 lines total)

#### __init__.py (4 lines)
- Re-exports `SchoolSignalAgent`.

#### agent.py (119 lines)
- **Purpose:** `SchoolSignalAgent` -- builds a school quality signal (0-10) from NJ School Performance Report metrics (achievement, growth, readiness indices, absenteeism, student-teacher ratio).
- **Dependencies:** `school_signal.schemas`
- **Status:** Active

#### ingest.py (500 lines)
- **Purpose:** Ingests NJ School Performance Report data from Excel/XLSX files. Parses the OpenXML workbook format, extracts district-level metrics, and produces structured output for the school signal agent.
- **Dependencies:** xml, zipfile, csv (stdlib)
- **Status:** Active -- data ingestion pipeline

#### schemas.py (34 lines)
- **Purpose:** Pydantic models: `SchoolSignalInput`, `SchoolSignalOutput`.
- **Dependencies:** pydantic
- **Status:** Active

### agents/town_county/ (2,002 lines total)

#### __init__.py (70 lines)
- Re-exports all town/county classes and functions.

#### bridge.py (184 lines)
- **Purpose:** `TownCountySourceBridge` -- normalizes raw source records (price trends, population, flood, macro) into scorer-ready `TownCountyNormalizedRecord` inputs.
- **Dependencies:** `town_county.schemas`
- **Status:** Active

#### cli.py (120 lines)
- **Purpose:** CLI for building a town/county outlook from file-backed data. Supports `--town`, `--state`, `--county`, `--school-signal`, etc.
- **Dependencies:** `town_county.providers`, `town_county.service`, `town_county.sources`
- **Status:** Active -- standalone CLI tool

#### providers.py (173 lines)
- **Purpose:** File-backed data providers: `FileBackedPriceTrendProvider`, `FileBackedPopulationProvider`, `FileBackedFloodRiskProvider`, `FileBackedLiquidityProvider`, `FileBackedFredMacroProvider`, `FileBackedTownProfileProvider`, `FileBackedSchoolSignalProvider`, `FileBackedTownLandmarkProvider`.
- **Dependencies:** stdlib json
- **Status:** Active -- data access layer for town/county

#### schemas.py (100 lines)
- **Purpose:** Pydantic models: `TownCountyInputs`, `TownCountyScore`, `TownCountySourceRecord`, `TownCountyNormalizedRecord`, `SourceFieldStatus`.
- **Dependencies:** pydantic
- **Status:** Active

#### scoring.py (344 lines)
- **Purpose:** `TownCountyScorer` -- scores town/county investment support using price trends, population trends, school signal, macro sentiment, coastal profile, flood risk, liquidity, scarcity.
- **Dependencies:** `town_county.schemas`, `briarwood.scoring`
- **Status:** Active

#### service.py (399 lines)
- **Purpose:** `TownCountyDataService` -- orchestrates data acquisition from multiple providers, builds source records, normalizes via bridge, and scores via scorer. The main entry point for location analysis.
- **Dependencies:** `town_county.bridge`, `town_county.scoring`, `town_county.schemas`, `town_county.sources`
- **Status:** Active

#### sources.py (612 lines)
- **Purpose:** Source adapter layer. Defines adapter classes (`ZillowTrendAdapter`, `CensusPopulationAdapter`, `FemaFloodAdapter`, `FredMacroAdapter`, `LiquidityAdapter`, `SchoolSignalAdapter`, `TownProfileAdapter`) that normalize raw data into typed slices. `TownCountyOutlookBuilder` assembles a `TownCountySourceRecord` from all adapters.
- **Dependencies:** `school_signal.SchoolSignalAgent`, `town_county.schemas`
- **Status:** Active

---

## 4. briarwood/dash_app/ -- UI Layer (20,186 lines total)

### __init__.py (2 lines)
- Empty marker with docstring.

### app.py (5,320 lines)
- **Purpose:** The Dash application. Defines all layouts, callbacks, and routing. Features include: property selector dropdown, analysis tabs (Overview, Tear Sheet, Scenarios, Data Quality, Compare, Quick Decision, Town Pulse), manual property/comp entry forms, portfolio dashboard, Zillow URL intake, what-if scenario adjustments, tear sheet PDF/HTML export, guided tour overlay.
- **Dependencies:** dash, dash_bootstrap_components, `briarwood.dash_app.components`, `briarwood.dash_app.data`, `briarwood.dash_app.view_models`, `briarwood.dash_app.scenarios`, `briarwood.dash_app.data_quality`, `briarwood.dash_app.quick_decision`, `briarwood.dash_app.compare`, `briarwood.listing_intake`, `briarwood.evidence`, `briarwood.entry_prep`, `briarwood.decision_model.scoring`
- **Status:** Active -- the main web application
- **UI/Feature:** All UI screens and interactions

### components.py (7,992 lines)
- **Purpose:** Dash HTML component rendering functions. Renders tear sheet body, property decision summary, portfolio dashboard, compare view, metric cards, charts (radar, bar, scenario trajectory, value waterfall, value bridge, location heatmap), tables, evidence panels, tour overlay, benchmark comparisons.
- **Dependencies:** dash, plotly, `briarwood.dash_app.theme`, `briarwood.dash_app.view_models`, `briarwood.dash_app.compare`, `briarwood.dash_app.quick_decision`, `briarwood.decision_model.scoring_config`
- **Status:** Active -- all UI rendering
- **UI/Feature:** Every visual element

### components_quick_decision.py (510 lines)
- **Purpose:** Rendering components for the Quick Decision view -- a simplified, decision-first layout for non-expert users. Renders recommendation hero, key reasons, use cases, scenario snapshots, value finder summary.
- **Dependencies:** `briarwood.dash_app.quick_decision`, `briarwood.dash_app.theme`
- **Status:** Active (new feature, untracked in git)
- **UI/Feature:** Quick Decision tab

### view_models.py (2,893 lines)
- **Purpose:** `PropertyAnalysisView` -- the main view model that transforms an `AnalysisReport` into display-ready data. `build_property_analysis_view()` computes all formatted metrics, market analysis, value finder, town pulse, evidence rows, and comparison metrics. Includes caching layer for expensive computations.
- **Dependencies:** `briarwood.agents.comparable_sales.store`, `briarwood.evidence`, `briarwood.recommendations`, `briarwood.modules.town_aggregation_diagnostics`, `briarwood.modules.market_analyzer`, `briarwood.modules.hybrid_value`, `briarwood.modules.value_finder`, `briarwood.local_intelligence`, `briarwood.truth`, `briarwood.reports.section_helpers`, `briarwood.reports.sections.conclusion_section`, `briarwood.reports.sections.thesis_section`
- **Status:** Active -- core presentation logic
- **UI/Feature:** Powers all dashboard views

### data.py (764 lines)
- **Purpose:** Data access layer for the Dash app. Lists presets, saved properties, and comp database rows. Loads reports (with caching). Handles property saving, comp saving, tear sheet export (HTML/PDF). `register_manual_analysis()` persists new property analyses.
- **Dependencies:** `briarwood.runner`, `briarwood.reports.pdf_renderer`, `briarwood.geocoder`, `briarwood.dash_app.view_models`
- **Status:** Active
- **UI/Feature:** Data loading for all views

### data_quality.py (677 lines)
- **Purpose:** Data Quality scorecard renderer -- developer/analyst view showing comp database health, per-property comp matching, value driver attribution, input impact signals, town aggregation diagnostics.
- **Dependencies:** `briarwood.agents.comparable_sales.schemas`, `briarwood.dash_app.components`, `briarwood.modules.comparable_sales`, `briarwood.modules.town_aggregation_diagnostics`
- **Status:** Active
- **UI/Feature:** Data Quality tab

### compare.py (293 lines)
- **Purpose:** `build_compare_summary()` -- builds a side-by-side comparison of multiple properties with weighted delta analysis and winner determination.
- **Dependencies:** `briarwood.dash_app.view_models`
- **Status:** Active
- **UI/Feature:** Compare tab

### quick_decision.py (532 lines)
- **Purpose:** `build_quick_decision_view()` -- distills a full `AnalysisReport` into a simplified `QuickDecisionViewModel` for non-expert users. Includes jargon rewriting, key reasons extraction, use case suggestions, scenario snapshots, value finder integration.
- **Dependencies:** `briarwood.recommendations`, `briarwood.schemas`
- **Status:** Active (new feature, untracked in git)
- **UI/Feature:** Quick Decision tab

### scenarios.py (775 lines)
- **Purpose:** Investment Scenarios tab renderer. Renders renovation scenario, rent-to-teardown strategy, historic-forward outlook chart, scenario economics tables.
- **Dependencies:** plotly, `briarwood.dash_app.components`, `briarwood.dash_app.theme`, `briarwood.reports.section_helpers`
- **Status:** Active
- **UI/Feature:** Scenarios tab

### theme.py (428 lines)
- **Purpose:** Design tokens for the platform. Defines color palette (light/professional theme), typography (Source Serif 4 / Inter), spacing, card styles, chart layouts, tone colors, helper functions (`score_color()`, `score_label()`, `tone_badge_style()`, `verdict_color()`).
- **Dependencies:** `briarwood.recommendations`
- **Status:** Active -- imported by all component files

---

## 5. briarwood/modules/ -- Analysis Pipeline Modules (7,624 lines total)

Each module implements the `AnalysisModule` protocol (`name` attribute + `run()` method returning `ModuleResult`).

### __init__.py (1 line)
- Empty marker.

### bull_base_bear.py (411 lines)
- **Purpose:** `BullBaseBearModule` -- generates bull/base/bear 12-month scenario projections combining current value, market history, town outlook, risk constraints, and scarcity support. Produces `ScenarioOutput` with case values, spread, and confidence.
- **Dependencies:** `modules.current_value`, `modules.market_value_history`, `modules.risk_constraints`, `modules.scarcity_support`, `modules.town_county_outlook`, `briarwood.decision_model.scoring_config`
- **Status:** Active
- **UI/Feature:** Scenario projections on tear sheet and dashboard

### comparable_sales.py (614 lines)
- **Purpose:** `ComparableSalesModule` -- wraps `ComparableSalesAgent` for the pipeline. Loads comp data from file, runs the agent, also parses listing descriptions for rental units and estimates their market rent for optionality/hybrid value detection.
- **Dependencies:** `agents.comparable_sales`, `agents.rent_context`, `modules.market_value_history`
- **Status:** Active
- **UI/Feature:** Comp analysis across all views

### cost_valuation.py (286 lines)
- **Purpose:** `CostValuationModule` -- wraps `IncomeAgent` and `RentContextAgent` to produce a cost-of-ownership score with cap rate, DSCR, cash-on-cash return, monthly cash flow, and vacancy-adjusted income metrics.
- **Dependencies:** `agents.income`, `agents.rent_context`, `briarwood.settings`
- **Status:** Active
- **UI/Feature:** Income/cost metrics on tear sheet

### current_value.py (306 lines)
- **Purpose:** `CurrentValueModule` -- wraps `CurrentValueAgent` and orchestrates comp, market history, income, and hybrid value modules to produce the Briarwood Current Value (BCV) with confidence and pricing view (supported/neutral/stretched).
- **Dependencies:** `agents.current_value`, `modules.comparable_sales`, `modules.hybrid_value`, `modules.income_support`, `modules.market_value_history`, `briarwood.field_audit`, `briarwood.opportunity_metrics`
- **Status:** Active
- **UI/Feature:** BCV is the central valuation metric

### hybrid_value.py (546 lines)
- **Purpose:** `HybridValueModule` -- detects multi-use/hybrid properties (e.g., house + rear rental units) and values them as primary structure + accessory income + optionality premium. Separates comp-based house value from income-capitalized rental value.
- **Dependencies:** `agents.comparable_sales.schemas`, `modules.comparable_sales`, `modules.income_support`
- **Status:** Active
- **UI/Feature:** Hybrid value analysis for multi-unit properties

### income_support.py (230 lines)
- **Purpose:** `IncomeSupportModule` -- wraps `IncomeAgent` for the pipeline, adding rent context resolution and section evidence.
- **Dependencies:** `agents.rent_context`, `agents.income`
- **Status:** Active

### liquidity_signal.py (235 lines)
- **Purpose:** `LiquiditySignalModule` -- canonical exit-liquidity signal combining DOM score, market liquidity view, rental liquidity, and comp depth.
- **Dependencies:** `modules.comparable_sales`, `modules.rental_ease`, `modules.town_county_outlook`
- **Status:** Active
- **UI/Feature:** Liquidity metric on dashboard

### local_intelligence.py (223 lines)
- **Purpose:** `LocalIntelligenceModule` -- bridge from the local intelligence subsystem into the `ModuleResult` format. Runs town-level document analysis and produces structured signals.
- **Dependencies:** `briarwood.local_intelligence.service`
- **Status:** Active
- **UI/Feature:** Town Pulse on dashboard

### location_context.py (93 lines)
- **Purpose:** Factory functions: `build_default_town_county_service()` (cached), `build_town_county_request()`, `build_scarcity_inputs()`. Wires up file-backed data providers for the town/county service.
- **Dependencies:** `agents.town_county.providers`, `agents.town_county.service`, `agents.scarcity.schemas`
- **Status:** Active -- used by multiple modules

### location_intelligence.py (619 lines)
- **Purpose:** `LocationIntelligenceModule` -- location-based comp bucket analysis. Groups comps by distance to landmarks (beach, downtown, ski), computes per-bucket PPSF benchmarks and position relative to similar properties.
- **Dependencies:** `agents.comparable_sales`, `briarwood.schemas`
- **Status:** Active
- **UI/Feature:** Location intelligence section on tear sheet

### market_analyzer.py (604 lines)
- **Purpose:** `analyze_markets()` -- cross-town market comparison engine. Aggregates comp data, active listings, rental context, and local intelligence signals to score towns on market health, structure, valuation, catalysts, and investability.
- **Dependencies:** `agents.comparable_sales.store`, `local_intelligence.models`, `local_intelligence.storage`, `modules.town_aggregation_diagnostics`
- **Status:** Active
- **UI/Feature:** Market Analysis panel in dashboard

### market_momentum_signal.py (273 lines)
- **Purpose:** `MarketMomentumSignalModule` -- canonical market momentum signal combining market history trends, town outlook score, local intelligence catalyst score, and scenario spread.
- **Dependencies:** `modules.bull_base_bear`, `modules.local_intelligence`, `modules.market_value_history`, `modules.town_county_outlook`
- **Status:** Active
- **UI/Feature:** Momentum metric on dashboard

### market_snapshot.py (190 lines)
- **Purpose:** `TownMarketSnapshot` -- town-level market snapshot combining comp data, ATTOM API data, and NJ tax intelligence (tax rates, equalization ratios, vacancy rates, permit activity).
- **Dependencies:** `data_quality.normalizers`, `data_sources.attom_client`, `data_sources.nj_tax_intelligence`
- **Status:** Active
- **UI/Feature:** Market snapshot data

### market_value_history.py (65 lines)
- **Purpose:** `MarketValueHistoryModule` -- wraps `MarketValueHistoryAgent` for the pipeline. Loads Zillow ZHVI history from a JSON fixture.
- **Dependencies:** `agents.market_history`
- **Status:** Active

### property_data_quality.py (76 lines)
- **Purpose:** `PropertyDataQualityModule` -- computes property-level tax quality intelligence (tax confirmation, reassessment risk, structural data quality) using ATTOM data and NJ tax context.
- **Dependencies:** `data_quality.property_intelligence`, `data_sources.nj_tax_intelligence`
- **Status:** Active
- **UI/Feature:** Data Quality tab

### property_snapshot.py (76 lines)
- **Purpose:** `PropertySnapshotModule` -- basic property-level scoring based on age, PPSF, and lot size.
- **Dependencies:** `briarwood.schemas`, `briarwood.scoring`, `briarwood.utils`
- **Status:** Active

### relative_opportunity.py (271 lines)
- **Purpose:** `RelativeOpportunityModule` -- compares multiple analyzed properties for directional forward opportunity. Computes best value creation, best location, lowest risk, etc.
- **Dependencies:** `briarwood.opportunity_metrics`, `briarwood.schemas`, `briarwood.settings`
- **Status:** Active
- **UI/Feature:** Compare tab winner analysis

### renovation_scenario.py (272 lines)
- **Purpose:** `RenovationScenarioModule` -- estimates value creation from a planned renovation. Creates hypothetical post-reno property, runs it through comp/value infrastructure, computes renovation economics. No-op if renovation_scenario is absent.
- **Dependencies:** `modules.comparable_sales`, `modules.current_value`, `briarwood.settings`
- **Status:** Active
- **UI/Feature:** Scenarios tab - Renovation

### rental_ease.py (118 lines)
- **Purpose:** `RentalEaseModule` -- wraps `RentalEaseAgent` with income support, town outlook, and scarcity modules for pipeline integration.
- **Dependencies:** `agents.rental_ease`, `modules.income_support`, `modules.scarcity_support`, `modules.town_county_outlook`
- **Status:** Active

### risk_constraints.py (158 lines)
- **Purpose:** `RiskConstraintsModule` -- evaluates risk factors: flood risk, building age, condition, financing leverage, data completeness. Applies graduated penalties/credits.
- **Dependencies:** `briarwood.decision_model.scoring_config`, `briarwood.scoring`, `briarwood.utils`
- **Status:** Active
- **UI/Feature:** Risk assessment on dashboard

### scarcity_support.py (58 lines)
- **Purpose:** `ScarcitySupportModule` -- wraps `ScarcitySupportScorer` with town/county data service for pipeline integration.
- **Dependencies:** `agents.scarcity`, `agents.town_county.service`, `modules.location_context`
- **Status:** Active

### teardown_scenario.py (485 lines)
- **Purpose:** `TeardownScenarioModule` -- models a rent-to-teardown investment strategy (Phase 1: rent for N years; Phase 2: demolish and build new construction). Computes year-by-year cash flows, equity buildup, and terminal value. No-op if teardown_scenario is absent.
- **Dependencies:** `modules.comparable_sales`, `modules.current_value`, `modules.income_support`, `briarwood.settings`
- **Status:** Active
- **UI/Feature:** Scenarios tab - Teardown

### town_aggregation_diagnostics.py (792 lines)
- **Purpose:** Comp database diagnostics aggregated by town. Uses pandas for statistical analysis (median, dispersion, missingness, outlier detection). Provides `get_town_context()` for enriching per-property analysis with town-level comp statistics.
- **Dependencies:** pandas, `agents.comparable_sales.store`
- **Status:** Active
- **UI/Feature:** Data Quality tab, enriches view models

### town_county_outlook.py (51 lines)
- **Purpose:** `TownCountyOutlookModule` -- wraps `TownCountyDataService` for the pipeline.
- **Dependencies:** `agents.town_county.service`, `modules.location_context`
- **Status:** Active

### value_drivers.py (286 lines)
- **Purpose:** `ValueDriversModule` -- attribution analysis showing which property features drive value. Builds a value bridge from base comp value through adjustments (lot premium, condition, location, age, beds/baths surplus).
- **Dependencies:** `briarwood.schemas`
- **Status:** Active
- **UI/Feature:** Value drivers / waterfall chart

### value_finder.py (285 lines)
- **Purpose:** `analyze_value_finder()` -- identifies negotiation opportunities by analyzing value gap (asking vs. BCV), comp gap, days on market, price cuts, and market friction. Produces opportunity signal (strong/moderate/low/watch) and pricing posture.
- **Dependencies:** None (standalone)
- **Status:** Active (new feature, untracked in git)
- **UI/Feature:** Quick Decision view, Value Finder panel

---

## 6. briarwood/reports/ -- Tear Sheet & Report Generation (2,963 lines total)

### __init__.py (1 line)
- Empty marker.

### tear_sheet.py (32 lines)
- **Purpose:** `build_tear_sheet()` -- assembles a `TearSheet` from an `AnalysisReport` by calling all section builders.
- **Dependencies:** All `reports.sections.*` builders, `reports.schemas`
- **Status:** Active

### renderer.py (346 lines)
- **Purpose:** `render_tear_sheet_html()` -- renders a `TearSheet` into a standalone HTML page using template substitution. Generates charts as inline base64 images.
- **Dependencies:** `reports.schemas`
- **Status:** Active
- **UI/Feature:** HTML tear sheet export

### pdf_renderer.py (237 lines)
- **Purpose:** `write_tear_sheet_pdf()` -- converts tear sheet HTML to a print-optimized PDF using WeasyPrint. Adds page headers, footers, and print-specific CSS.
- **Dependencies:** weasyprint (optional)
- **Status:** Active
- **UI/Feature:** PDF tear sheet export

### schemas.py (302 lines)
- **Purpose:** Dataclasses for tear sheet structure: `TearSheet`, `HeaderSection`, `ConclusionSection`, `CarrySupportSection`, `ThesisSection`, `MarketDurabilitySection`, `ScenarioChartSection`, `SignalMetricsSection`, etc.
- **Dependencies:** dataclasses
- **Status:** Active

### section_helpers.py (69 lines)
- **Purpose:** Convenience functions to extract typed payloads from module results: `get_current_value()`, `get_comparable_sales()`, `get_income_support()`, `get_rental_ease()`, `get_town_county_outlook()`, etc.
- **Dependencies:** All agent output types, all module payload extractors
- **Status:** Active -- widely imported

### sections/__init__.py (1 line)
- Empty marker.

### sections/header_section.py (29 lines)
- **Purpose:** Builds the tear sheet header (property name, subtitle, investment stance).
- **Status:** Active

### sections/conclusion_section.py (268 lines)
- **Purpose:** Builds the conclusion section with verdict, key line, pricing analysis, scenario range, risk summary, and decision-fit recommendations.
- **Status:** Active

### sections/carry_support_section.py (195 lines)
- **Purpose:** Builds the carry support section analyzing rental viability and market absorption.
- **Status:** Active

### sections/case_columns_section.py (181 lines)
- **Purpose:** Builds the bull/base/bear case columns section with driver narratives.
- **Status:** Active

### sections/comparable_sales_section.py (94 lines)
- **Purpose:** Builds the comparable sales section showing comp table and value range.
- **Status:** Active

### sections/evidence_strip_section.py (124 lines)
- **Purpose:** Builds the evidence strip showing data source coverage and confidence.
- **Status:** Active

### sections/investment_scenarios_section.py (93 lines)
- **Purpose:** Builds the investment scenarios section (renovation, teardown) for the tear sheet.
- **Status:** Active

### sections/market_durability_section.py (63 lines)
- **Purpose:** Builds the market durability section analyzing town/county outlook strength.
- **Status:** Active

### sections/scenario_chart_section.py (569 lines)
- **Purpose:** Builds the scenario chart data (fan bands, labeled points) and generates the Plotly chart as inline SVG for the tear sheet.
- **Dependencies:** plotly
- **Status:** Active

### sections/signal_metrics_section.py (218 lines)
- **Purpose:** Builds the signal metrics section with key financial/market indicators.
- **Status:** Active

### sections/thesis_section.py (141 lines)
- **Purpose:** Builds the investment thesis section with bull/bear narrative and confidence assessment.
- **Status:** Active

---

## 7. briarwood/inputs/ -- Property Data Loading (1,274 lines total)

### __init__.py (1 line)
- Empty marker.

### adapters.py (470 lines)
- **Purpose:** Canonical input adapters: `PublicRecordAdapter`, `ListingTextAdapter`, `normalized_listing_to_canonical()`. Converts raw input sources into `CanonicalPropertyData` with full provenance tracking.
- **Dependencies:** `briarwood.listing_intake`, `briarwood.schemas`
- **Status:** Active

### market_location_adapter.py (193 lines)
- **Purpose:** `MarketLocationAdapter` -- enriches canonical property data with market location signals (town/county outlook, market history, landmark proximity).
- **Dependencies:** `agents.market_history`, `agents.town_county.providers`, `modules.location_context`
- **Status:** Active

### property_loader.py (484 lines)
- **Purpose:** `load_property_from_json()` and `load_property_from_listing_text()` -- main entry points for creating `PropertyInput` from JSON files or listing text. Applies smart defaults, evidence arbitration, market location enrichment, and property support enrichment. Includes pydantic boundary validation.
- **Dependencies:** `briarwood.inputs.adapters`, `briarwood.data_quality.arbitration`, `briarwood.inputs.market_location_adapter`, `briarwood.inputs.property_support_adapter`, `briarwood.listing_intake`
- **Status:** Active -- used by `runner.py` and `dash_app/data.py`

### property_support_adapter.py (126 lines)
- **Purpose:** `PropertySupportAdapter` -- enriches canonical property data with rent context estimates and comp availability signals.
- **Dependencies:** `agents.rent_context`, `agents.comparable_sales`
- **Status:** Active

---

## 8. briarwood/data_quality/ -- Data Validation & Arbitration (1,585 lines total)

### __init__.py (2 lines)
- Empty marker.

### pipeline.py (400 lines)
- **Purpose:** `DataQualityPipeline` -- validates and normalizes comp/listing records. Produces `PipelineRecord` with validation issues, field evidence, and quality status (accepted/needs_review/rejected).
- **Dependencies:** `data_quality.arbitration`, `data_quality.eligibility`, `data_quality.normalizers`, `data_quality.provenance`, `data_quality.source_policy`
- **Status:** Active

### arbitration.py (496 lines)
- **Purpose:** Multi-source field arbitration: `choose_field_value()` picks the best value for each field from multiple candidates based on source tier, recency, and policy. `build_property_evidence_profile()` constructs a full evidence profile. `apply_evidence_profile()` maps evidence onto `CanonicalPropertyData`.
- **Dependencies:** `data_quality.normalizers`, `data_quality.eligibility`, `data_quality.provenance`, `data_quality.source_policy`
- **Status:** Active

### cleanup.py (125 lines)
- **Purpose:** `delete_junk_records()` and `cleanup_records()` -- batch operations to remove/fix problematic records in the comp store (normalize addresses, strip suffixes, delete rejected records).
- **Dependencies:** `data_quality.pipeline`, `data_quality.normalizers`
- **Status:** Active

### eligibility.py (107 lines)
- **Purpose:** `classify_comp_eligibility()` -- determines whether a record meets minimum identity and structural requirements to be used as a comp.
- **Dependencies:** `data_quality.provenance`
- **Status:** Active

### normalizers.py (157 lines)
- **Purpose:** Field normalization functions: `normalize_town()`, `normalize_address_string()`, `normalize_date()`, `normalize_numeric()`, `normalize_sqft()`, `normalize_lot_size()`, `normalize_state()`, `treat_missing()`, `is_malformed_address()`, `is_listing_description_as_address()`.
- **Dependencies:** None (stdlib only)
- **Status:** Active

### property_intelligence.py (130 lines)
- **Purpose:** `compute_property_tax_quality_intelligence()` -- assesses property tax data quality, reassessment risk, tax burden, and structural data completeness.
- **Dependencies:** None (standalone)
- **Status:** Active

### provenance.py (49 lines)
- **Purpose:** Core data structures: `FieldCandidate`, `FieldEvidence`, `PropertyEvidenceProfile` -- used throughout the arbitration system.
- **Dependencies:** dataclasses
- **Status:** Active

### source_policy.py (119 lines)
- **Purpose:** Field group definitions and source ranking policies. Defines which fields are identity, structural, sale, tax, or rent fields, and their priority ordering for multi-source arbitration.
- **Dependencies:** dataclasses
- **Status:** Active

---

## 9. briarwood/data_sources/ -- External Data Integrations (711 lines total)

### __init__.py (2 lines)
- Empty marker.

### api_strategy.py (94 lines)
- **Purpose:** API budget tracking and conditional endpoint selection. `ApiStrategy` determines which ATTOM endpoints to call based on analysis context (missing rent, redevelopment case, tax risk review). `ApiBudgetTracker` tracks call counts, cache hits, and field fills.
- **Dependencies:** dataclasses
- **Status:** Active

### attom_client.py (426 lines)
- **Purpose:** `AttomClient` -- HTTP client for the ATTOM property data API. Supports 15+ endpoints (property detail, assessment, sale, building permits, rental AVM, school snapshot, etc.). Includes local file caching, rate limiting, and field mapping.
- **Dependencies:** urllib (stdlib), `data_sources.api_strategy`
- **Status:** Active
- **External:** ATTOM API (requires API key)

### nj_tax_intelligence.py (189 lines)
- **Purpose:** `NJTaxIntelligenceStore` -- loads NJ municipal tax rate data from CSV. `town_tax_context()` provides tax rates, equalization ratios, and assessment context for a given town.
- **Dependencies:** csv (stdlib), `data_quality.normalizers`
- **Status:** Active

---

## 10. briarwood/decision_model/ -- Investment Scoring Framework (2,197 lines total)

### __init__.py (0 lines)
- Empty marker.

### scoring.py (1,525 lines)
- **Purpose:** The investment scoring engine. `calculate_final_score()` converts raw `AnalysisReport` metrics into a 1-5 investment score with 5 category scores (price_context, economic_support, optionality, market_position, risk_layer), 20 sub-factor scores, and a Buy/Neutral/Avoid recommendation. Contains all metric extraction and sub-factor scoring logic.
- **Dependencies:** `briarwood.decision_model.scoring_config`, `briarwood.modules.town_aggregation_diagnostics`, `briarwood.schemas`, `briarwood.truth`, `briarwood.recommendations`
- **Status:** Active
- **UI/Feature:** Powers the decision score on all views

### scoring_config.py (302 lines)
- **Purpose:** Scoring configuration: category weights, sub-factor weights, sub-factor questions/labels, recommendation tiers, and settings dataclasses (`BullBaseBearSettings`, `RiskSettings`, `DecisionModelSettings`).
- **Dependencies:** dataclasses
- **Status:** Active

### lens_scoring.py (370 lines)
- **Purpose:** Multi-lens scoring: evaluates properties from Investor, Owner-Occupant, and Developer perspectives. Re-weights the same underlying data for each buyer persona. Produces `LensScores` with per-lens scores, narratives, and recommendations.
- **Dependencies:** `briarwood.decision_model.scoring`, `briarwood.schemas`
- **Status:** Active
- **UI/Feature:** Lens scores on dashboard (if enabled)

---

## 11. briarwood/listing_intake/ -- Listing Data Ingestion (865 lines total)

### __init__.py (1 line)
- Empty marker.

### service.py (36 lines)
- **Purpose:** `ListingIntakeService` -- orchestrates listing parsing and normalization. Routes Zillow URLs, pasted listing text, and generic text through the appropriate parser.
- **Dependencies:** `listing_intake.normalizer`, `listing_intake.parsers`
- **Status:** Active

### parsers.py (414 lines)
- **Purpose:** Listing parsers: `ZillowUrlParser` (extracts metadata from Zillow URLs), `ZillowTextParser` (parses pasted Zillow listing text using regex for price, beds, baths, sqft, lot size, year built, address, description, price/tax history). `get_default_parsers()` returns the parser chain.
- **Dependencies:** `listing_intake.schemas`
- **Status:** Active

### normalizer.py (108 lines)
- **Purpose:** `normalize_listing()` -- converts raw listing data into normalized property data. Infers county from zip/town, computes price per sqft, populates evidence mode.
- **Dependencies:** `listing_intake.schemas`
- **Status:** Active

### schemas.py (253 lines)
- **Purpose:** Data structures for listing intake: `ListingRawData`, `NormalizedPropertyData`, `ListingIntakeResult`, `PriceHistoryEntry`, `TaxHistoryEntry`.
- **Dependencies:** `briarwood.schemas`
- **Status:** Active

### cli.py (53 lines)
- **Purpose:** CLI for listing intake: `python -m briarwood.listing_intake.cli <url_or_text_file>`.
- **Dependencies:** `listing_intake.service`
- **Status:** Active

---

## 12. briarwood/local_intelligence/ -- Town-Level Document Analysis (1,711 lines total)

### __init__.py (65 lines)
- Re-exports all public symbols from the subsystem.

### service.py (102 lines)
- **Purpose:** `LocalIntelligenceService` -- orchestrates document ingestion, signal extraction, reconciliation with persisted history, and town summary generation.
- **Dependencies:** `local_intelligence.adapters`, `local_intelligence.collector`, `local_intelligence.models`, `local_intelligence.normalize`, `local_intelligence.reconcile`, `local_intelligence.storage`, `local_intelligence.summarize`
- **Status:** Active
- **UI/Feature:** Town Pulse tab

### models.py (185 lines)
- **Purpose:** Pydantic models for the local intelligence subsystem: `SourceDocument`, `TownSignal`, `TownSignalDraft`, `TownSignalDraftBatch`, `TownSummary`, `TownPulseView`, `LocalIntelligenceRun`. Enums: `SourceType`, `SignalType`, `SignalStatus`, `ImpactDirection`, `TimeHorizon`, `ReconciliationStatus`.
- **Dependencies:** pydantic
- **Status:** Active

### adapters.py (411 lines)
- **Purpose:** Signal extraction backends: `RuleBasedLocalIntelligenceExtractor` (deterministic regex-based), `OpenAILocalIntelligenceExtractor` (LLM-backed via OpenAI API). Both implement `LocalIntelligenceExtractor` protocol.
- **Dependencies:** `local_intelligence.config`, `local_intelligence.models`, `local_intelligence.prompts`, `local_intelligence.validation`
- **Status:** Active
- **External:** OpenAI API (optional, for LLM extraction)

### classification.py (98 lines)
- **Purpose:** Town signal classification: `classify_town_signal()` buckets signals as bullish/bearish/watch based on impact direction, status, and confidence. `bucket_town_signals()` and `rank_town_signals()` sort for display.
- **Dependencies:** `local_intelligence.models`
- **Status:** Active

### collector.py (213 lines)
- **Purpose:** `MunicipalDocumentCollector` -- fetches municipal documents from URLs (planning board minutes, ordinances, etc.) and converts to `SourceDocument` models. Supports PDF parsing via PyMuPDF.
- **Dependencies:** `local_intelligence.models`
- **Status:** Active (new feature, untracked in git)
- **External:** PyMuPDF/fitz (optional, for PDF parsing)

### config.py (43 lines)
- **Purpose:** `OpenAILocalIntelligenceConfig` -- centralized provider configuration for OpenAI-backed extraction (model, reasoning effort, timeout).
- **Dependencies:** os (stdlib)
- **Status:** Active

### normalize.py (123 lines)
- **Purpose:** `normalize_source_documents()` -- converts loose dict payloads into validated `SourceDocument` models. Handles ID generation, source type inference, and field normalization.
- **Dependencies:** `local_intelligence.models`
- **Status:** Active

### prompts.py (42 lines)
- **Purpose:** System prompt and extraction prompt templates for the OpenAI-backed signal extractor.
- **Dependencies:** `local_intelligence.models`
- **Status:** Active

### reconcile.py (161 lines)
- **Purpose:** `reconcile_signals()` -- merges fresh signals into persisted signal history with deterministic duplicate detection (title similarity + date proximity). Tracks reconciliation status (new, updated, unchanged).
- **Dependencies:** `local_intelligence.models`
- **Status:** Active

### storage.py (52 lines)
- **Purpose:** `JsonLocalSignalStore` -- file-backed persistence for town-level signal history. Stores JSON files per town in `data/local_intelligence/signals/`.
- **Dependencies:** `local_intelligence.models`
- **Status:** Active

### summarize.py (68 lines)
- **Purpose:** `build_town_summary()` -- produces a compact, decision-first Town Pulse narrative from reconciled signals.
- **Dependencies:** `local_intelligence.classification`, `local_intelligence.models`
- **Status:** Active

### ui.py (16 lines)
- **Purpose:** `build_town_pulse_view()` -- creates a lightweight UI view-model for town surfaces.
- **Dependencies:** `local_intelligence.models`
- **Status:** Active

### validation.py (132 lines)
- **Purpose:** `validate_signal_drafts()` -- converts draft signal records into canonical `TownSignal` objects with validation, ID generation, and canonical key computation.
- **Dependencies:** `local_intelligence.models`
- **Status:** Active

---

## 13. scripts/ -- Data Pipeline & Maintenance Scripts (2,241 lines total)

### audit_comp_store.py (150 lines)
- **Purpose:** Audits the comp store for data quality issues: runs cleanup, validation pipeline, eligibility classification, and generates an issue summary report.
- **Dependencies:** `briarwood.data_quality`
- **Status:** Active

### backfill_comp_store.py (235 lines)
- **Purpose:** Backfills missing comp fields using ATTOM API lookups. Identifies records with missing priority fields and enriches them.
- **Dependencies:** `briarwood.data_quality.pipeline`, `briarwood.data_sources.api_strategy`, `briarwood.data_sources.attom_client`
- **Status:** Active

### enrich_comps.py (294 lines)
- **Purpose:** Enriches comp store records by looking up each address in ATTOM property detail API. Confirms/fills structural fields and optionally fetches AVM estimates.
- **Dependencies:** `briarwood.agents.comparable_sales`, `briarwood.data_sources.attom_client`
- **Status:** Active

### fetch_attom_sales.py (327 lines)
- **Purpose:** Fetches recent residential sales from ATTOM's sale/snapshot endpoint and merges into the comp store. Targets Monmouth County towns.
- **Dependencies:** `briarwood.agents.comparable_sales`
- **Status:** Active

### fetch_sr1a_sales.py (280 lines)
- **Purpose:** Downloads NJ SR1A deed transfer files from NJ Treasury, parses them via `sr1a_parser`, and merges residential sales into the comp store.
- **Dependencies:** `briarwood.agents.comparable_sales`
- **Status:** Active

### ingest_excel_comps.py (746 lines)
- **Purpose:** Ingests comp Excel files (sold structured, active comp template) into the comp database. Handles sale_date estimation, lot size conversion, deduplication, and data quality reporting.
- **Dependencies:** openpyxl, `briarwood.agents.comparable_sales`
- **Status:** Active

### property_intel_audit_report.py (159 lines)
- **Purpose:** Generates a combined property intelligence audit report covering comp store quality, ATTOM API coverage, and NJ tax intelligence.
- **Dependencies:** `briarwood.data_sources`, scripts.audit_comp_store, scripts.backfill_comp_store
- **Status:** Active

### run_town_pulse.py (50 lines)
- **Purpose:** CLI to run Briarwood Town Pulse for a given town/state. Outputs signals, narrative, and confidence.
- **Dependencies:** `briarwood.local_intelligence`
- **Status:** Active (new feature, untracked in git)

---

## 14. audit_scripts/ -- Analysis & Diagnostic Scripts (697 lines total)

### 01_portfolio_summary.py (100 lines)
- **Purpose:** Portfolio-level audit: runs all presets through the scoring engine and reports score distribution, data quality, and module health.
- **Dependencies:** `briarwood.dash_app.data`, `briarwood.dash_app.view_models`, `briarwood.decision_model.scoring`
- **Status:** Active

### 02_property_deep_dive.py (109 lines)
- **Purpose:** Single property deep dive: complete scoring breakdown, module confidence analysis, and data completeness report.
- **Dependencies:** `briarwood.dash_app.data`, `briarwood.dash_app.view_models`, `briarwood.decision_model.scoring`
- **Status:** Active

### 03_correlation_and_modules.py (139 lines)
- **Purpose:** Correlation analysis across all properties: sub-factor score distributions and module performance metrics.
- **Dependencies:** `briarwood.dash_app.data`, `briarwood.decision_model.scoring`
- **Status:** Active

### pickup_comp_drop_folder.py (349 lines)
- **Purpose:** Watches a "drop folder" (iCloud) for new comp Excel/CSV files, ingests them into the comp store, and archives processed files. Supports sold and active listing file patterns.
- **Dependencies:** openpyxl, `briarwood.agents.comparable_sales.import_csv`
- **Status:** Active

---

## 15. tests/ -- Test Suite (~9,371 lines total)

### tests/agents/ (4,126 lines, 28 files)

| File | Lines | Tests |
|------|-------|-------|
| test_comp_drop_folder.py | 187 | Comp drop folder ingestion |
| test_comp_import_csv.py | 205 | CSV comp import |
| test_comp_store.py | 63 | JsonComparableSalesStore |
| test_comparable_sales_agent.py | 203 | ComparableSalesAgent |
| test_comparable_sales_curate.py | 34 | Curate template generation |
| test_comparable_sales_dataset.py | 60 | CompDataset operations |
| test_comparable_sales_ingest.py | 74 | Public record ingest |
| test_current_value_agent.py | 232 | CurrentValueAgent |
| test_demand_consistency.py | 93 | DemandConsistencyScorer |
| test_import_csv.py | 215 | CSV import edge cases |
| test_income_agent.py | 216 | IncomeAgent |
| test_land_scarcity.py | 86 | LandScarcityScorer |
| test_location_scarcity.py | 84 | LocationScarcityScorer |
| test_manual_comp_workflow.py | 310 | Manual comp entry workflow |
| test_market_value_history.py | 44 | MarketValueHistoryAgent |
| test_public_record_ingest.py | 765 | Public record ingestion (largest test file) |
| test_rent_context_agent.py | 48 | RentContextAgent |
| test_rental_ease_agent.py | 112 | RentalEaseAgent |
| test_scarcity_support.py | 78 | ScarcitySupportScorer |
| test_school_signal_agent.py | 49 | SchoolSignalAgent |
| test_school_signal_ingest.py | 139 | School signal ingestion |
| test_town_county_bridge.py | 84 | TownCountySourceBridge |
| test_town_county_cli.py | 31 | Town/county CLI |
| test_town_county_providers.py | 82 | File-backed providers |
| test_town_county_scoring.py | 105 | TownCountyScorer |
| test_town_county_service.py | 211 | TownCountyDataService |
| test_town_county_service_file_backed.py | 52 | File-backed service integration |
| test_town_county_sources.py | 264 | Source adapters |

### tests/modules/ (469 lines, 3 files)

| File | Lines | Tests |
|------|-------|-------|
| test_market_analyzer.py | 160 | Market analyzer |
| test_town_aggregation_diagnostics.py | 216 | Town aggregation diagnostics |
| test_value_finder.py | 93 | Value finder |

### tests/reports/ (278 lines, 1 file)

| File | Lines | Tests |
|------|-------|-------|
| test_carry_support_section.py | 278 | Carry support section builder |

### tests/ root (4,498 lines, 29 files)

| File | Lines | Tests |
|------|-------|-------|
| test_api_strategy.py | 23 | API strategy |
| test_attom_client.py | 75 | AttomClient |
| test_comp_eligibility.py | 72 | Comp eligibility |
| test_comp_store_scripts.py | 95 | Comp store scripts |
| test_dash_view_models.py | 317 | Dashboard view models |
| test_data_quality_cleanup.py | 42 | Data quality cleanup |
| test_data_quality_pipeline.py | 131 | Data quality pipeline |
| test_decision_model.py | 412 | Decision model scoring |
| test_engine.py | 186 | AnalysisEngine |
| test_evidence_modes.py | 108 | Evidence mode handling |
| test_group3.py | 130 | Mixed module tests |
| test_group4.py | 54 | Mixed module tests |
| test_integration.py | 279 | End-to-end integration |
| test_listing_intake.py | 166 | Listing intake |
| test_local_intelligence.py | 594 | Local intelligence subsystem |
| test_location_intelligence.py | 122 | Location intelligence |
| test_market_location_adapter.py | 59 | Market location adapter |
| test_market_snapshot.py | 63 | Market snapshot |
| test_modules.py | 400 | Module-level tests |
| test_nj_tax_intelligence.py | 32 | NJ tax intelligence |
| test_property_support_adapter.py | 36 | Property support adapter |
| test_property_tax_quality_intelligence.py | 37 | Property tax quality |
| test_quick_decision.py | 507 | Quick decision view |
| test_recommendation_and_refresh.py | 102 | Recommendations |
| test_relative_opportunity.py | 121 | Relative opportunity |
| test_schemas.py | 73 | Schema validation |
| test_scorecard.py | 31 | Scorecard |
| test_scoring_calibration.py | 19 | Scoring calibration |
| test_scoring_group2.py | 212 | Decision model scoring group 2 |

---

## 16. Non-Python Files

### CSS

| File | Lines | Purpose |
|------|-------|---------|
| briarwood/dash_app/assets/workspace.css | 341 | Dash app styles -- scrollbar, table, font loading (Source Serif 4, Inter), layout overrides |
| briarwood/reports/assets/tear_sheet.css | 538 | Tear sheet styles -- print-optimized typography, section layouts, chart containers |

### HTML Templates

| File | Lines | Purpose |
|------|-------|---------|
| briarwood/reports/templates/tear_sheet.html | 324 | Tear sheet HTML template with placeholder tokens ($variable) for Jinja-style substitution |

### Configuration Files

| File | Purpose |
|------|---------|
| .env.example | Template for ATTOM_API_KEY |
| .env | Actual environment variables (not tracked) |
| .vscode/launch.json | VS Code debug configurations |
| .vscode/settings.json | VS Code workspace settings |

### Data Files (data/)

| Directory | Contents |
|-----------|----------|
| data/comps/ | sales_comps.json (~270+ sale comps), active_listings.json, manual_comp_template.json, import_manifest.json, monmouth_public_record_template.csv |
| data/town_county/ | 10 JSON fixture files: price_trends.json, population_trends.json, flood_risk.json, liquidity.json, fred_macro.json, monmouth_coastal_profiles.json, monmouth_landmark_points.json, monmouth_school_signal.json, monmouth_school_targets.json, zillow_rent_context.json |
| data/market_history/ | zillow_zhvi_history.json (Zillow ZHVI time series) |
| data/saved_properties/ | 9 saved property directories, each containing: inputs.json, report.pkl, summary.json, tear_sheet.html |
| data/local_intelligence/signals/ | Per-town JSON signal files (e.g., belmar-nj.json) |
| data/local_intelligence/documents/ | Ingested municipal documents |
| data/cache/attom/ | ~170+ cached ATTOM API response JSON files |
| data/sample_property.json | Sample property input for testing |
| data/sample_zillow_listing*.txt | 3 sample Zillow listing text files |
| outputs/ | Generated tear sheets (test_tear_sheet.html) |

---

## 17. Potentially Dead Code

| File | Lines | Reason |
|------|-------|--------|
| briarwood/agents/current_value/inspect_data.py | 116 | One-off data inspection script; not imported by any other file; uses raw CSV parsing unrelated to the agent system |

All other files appear actively imported and used within the codebase.

---

## 18. Key External Dependencies

| Package | Usage |
|---------|-------|
| dash, dash-bootstrap-components | Web UI framework |
| plotly | Charts and visualizations |
| pydantic | Schema validation for agents and data models |
| pandas | Town aggregation diagnostics, market analysis |
| requests | Geocoding (Nominatim), ATTOM enricher |
| openpyxl | Excel comp ingestion |
| weasyprint | PDF tear sheet generation (optional) |
| python-dotenv | Environment variable loading (optional) |
| openai | LLM-backed local intelligence extraction (optional) |
| PyMuPDF/fitz | PDF document parsing for municipal documents (optional) |

---

## 19. Architecture Summary

```
CLI (app.py)  or  Dash UI (run_dash.py / app.py)
       |                    |
       v                    v
   runner.py ---- dash_app/data.py
       |                    |
       v                    v
  inputs/property_loader.py
       |
       v
  AnalysisEngine (engine.py)
       |
       +-- PropertySnapshotModule
       +-- MarketValueHistoryModule
       +-- ComparableSalesModule (+ HybridValueModule)
       +-- IncomeSupportModule (CostValuationModule)
       +-- CurrentValueModule
       +-- TownCountyOutlookModule
       +-- ScarcitySupportModule
       +-- RiskConstraintsModule
       +-- RentalEaseModule
       +-- BullBaseBearModule (scenarios)
       +-- LocationIntelligenceModule
       +-- LocalIntelligenceModule
       +-- LiquiditySignalModule
       +-- MarketMomentumSignalModule
       +-- ValueDriversModule
       +-- PropertyDataQualityModule
       +-- RenovationScenarioModule
       +-- TeardownScenarioModule
       |
       v
  AnalysisReport
       |
       +---> decision_model/scoring.py  --> FinalScore (1-5, Buy/Neutral/Avoid)
       +---> reports/tear_sheet.py      --> TearSheet --> HTML/PDF
       +---> dash_app/view_models.py    --> PropertyAnalysisView --> UI
```

The engine runs 18 modules in dependency order. Each module wraps one or more domain agents and produces a standardized `ModuleResult`. Results are assembled into an `AnalysisReport`, which feeds into scoring, reporting, and UI presentation layers.

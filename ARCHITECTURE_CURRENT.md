# Briarwood — Current Architecture

Factual snapshot of what exists in the codebase as of 2026-04-28. No gap analysis, no recommendations. For those, see [GAP_ANALYSIS.md](GAP_ANALYSIS.md).

## Overview

Briarwood is a conversational real-estate decision prototype. A Next.js chat UI talks to a FastAPI bridge, which routes each user turn to one of 14 `AnswerType` handlers. Each handler executes a subset of specialty models (15 in a scoped registry, 25+ legacy models reachable through them) and synthesizes the results either through a deterministic legacy composer path or, behind the `BRIARWOOD_CLAIMS_ENABLED` feature flag, through a structured claim-object pipeline. The response is streamed back as SSE events (22+ typed events covering text deltas, structured verdicts, charts, maps, and scout insights).

## Directory Map

Top-level layout:

| Path | Role |
|------|------|
| [api/](api/) | FastAPI bridge between Next.js and the Briarwood agent. Owns SSE protocol and dispatch entry. |
| [briarwood/](briarwood/) | Core decision-intelligence engine. Python. All specialty models, agents, orchestration, and synthesis live here. |
| [web/](web/) | Next.js 16.2 + React 19 chat UI. |
| [scripts/](scripts/) | 18 dev/utility scripts. `dev_chat.py` boots API + web together. |
| [tests/](tests/) | 66 test modules mirroring `briarwood/` structure. |
| [data/](data/) | Fixtures, caches, saved properties, comps, market histories. |
| [docs/](docs/) | 24 model audit documents (historical per [AGENTS.md](AGENTS.md)). |
| [analysis/](analysis/), [outputs/](outputs/), [audit_scripts/](audit_scripts/) | Historical analysis artifacts and tooling. |

Inside [briarwood/](briarwood/), the directories that matter for the decision pipeline:

| Path | Role |
|------|------|
| [briarwood/agent/](briarwood/agent/) | Routing, dispatch, LLM clients, composer, session state, property resolver. |
| [briarwood/modules/](briarwood/modules/) | 43 deterministic specialty models. See Specialty Models Inventory below. |
| [briarwood/agents/](briarwood/agents/) | Sub-agents that back specific modules (comparable_sales, income, rental_ease, town_county, current_value). |
| [briarwood/execution/](briarwood/execution/) | Scoped-execution registry + planner + executor. |
| [briarwood/pipeline/](briarwood/pipeline/) | V2 orchestration (registry wiring, triage, macro nudges). |
| [briarwood/claims/](briarwood/claims/) | Phase 3 claim-object pipeline (archetypes, synthesis, representation, feature-flagged). |
| [briarwood/editor/](briarwood/editor/) | Claim-object validator (5 checks). |
| [briarwood/value_scout/](briarwood/value_scout/) | Shared Scout dispatcher for claim-wedge and chat-tier non-obvious insights. |
| [briarwood/synthesis/](briarwood/synthesis/) | Legacy structured-output synthesis (runs when claims pipeline disabled). |
| [briarwood/representation/](briarwood/representation/) | Representation Agent + chart registry. |
| [briarwood/interactions/](briarwood/interactions/) | Session state, persona inference, primary-value-source bridge. |
| [briarwood/local_intelligence/](briarwood/local_intelligence/) | Town-level document and news signal extraction. |
| [briarwood/decision_model/](briarwood/decision_model/) | Post–Handoff-4, contains only metric-extraction helpers used by `components.py` (`estimate_comp_renovation_premium` + `extract_scoring_metrics`) plus `scoring_config` constants. The former `calculate_final_score` aggregator and `lens_scoring.py` were dead code and were deleted 2026-04-24. |
| [briarwood/data_sources/](briarwood/data_sources/) | External API clients (Attom, SR1A, Google Maps, Zillow context). |
| [briarwood/data_quality/](briarwood/data_quality/) | Input completeness and contradiction detection. |
| [briarwood/feature_flags.py](briarwood/feature_flags.py) | Process-level feature flags, read once at import. |

## Data Flow

The "Run analysis" flow for a saved property, end-to-end:

1. Browser renders [web/src/app/page.tsx](web/src/app/page.tsx); user sends a message via the `useChat` hook at [web/src/lib/chat/use-chat.ts](web/src/lib/chat/use-chat.ts).
2. Next.js proxies the request at [web/src/app/api/chat/route.ts](web/src/app/api/chat/route.ts) to FastAPI `POST /api/chat` at [api/main.py](api/main.py).
3. FastAPI calls into [api/pipeline_adapter.py](api/pipeline_adapter.py), which classifies the turn via `classify_turn()` → `briarwood.agent.router.classify()` at [briarwood/agent/router.py:105](briarwood/agent/router.py#L105). Router produces a `RouterDecision` with an `AnswerType` (one of 14 values).
4. The adapter dispatches to a tier-specific stream: `search_stream`, `browse_stream`, `decision_stream`, or the generic `dispatch_stream`. For DECISION, control enters `handle_decision()` at [briarwood/agent/dispatch.py:1887](briarwood/agent/dispatch.py#L1887).
5. Inside the decision handler, a feature-flag check at [briarwood/agent/dispatch.py:1809-1883](briarwood/agent/dispatch.py#L1809-L1883) uses `claims_enabled_for(property_id)` from [briarwood/feature_flags.py:22](briarwood/feature_flags.py#L22). Branching:
   - **Flag on**: `build_claim_for_property()` at [briarwood/claims/pipeline.py:28](briarwood/claims/pipeline.py#L28) runs `run_briarwood_analysis_with_artifacts()`, grafts a `comparable_sales` entry via the canonical scoped runner `run_comparable_sales(context)` at [briarwood/claims/pipeline.py:62-114](briarwood/claims/pipeline.py#L62-L114), and calls `build_verdict_with_comparison_claim()`. The claim goes through `scout_claim()` at [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) (`uplift_dominance`), then `edit_claim()` at [briarwood/editor/validator.py](briarwood/editor/validator.py) (5 checks). On pass, `render_claim()` at [briarwood/claims/representation/verdict_with_comparison.py:52](briarwood/claims/representation/verdict_with_comparison.py#L52) emits prose + chart + suggestions events. On editor failure, the handler emits `EVENT_CLAIM_REJECTED` and falls back to the legacy path. Chat-tier BROWSE / DECISION fall-through / EDGE calls use the shared `scout(...)` dispatcher over `UnifiedIntelligenceOutput` before `synthesize_with_llm`.
   - **Flag off**: handler runs the scoped-execution registry via `briarwood.orchestrator.run_briarwood_analysis_with_artifacts()`, synthesizes through [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py), and emits events directly.
6. Responses stream back as SSE events defined in [api/events.py](api/events.py) (22 event types).
7. The `useChat` hook in [web/src/lib/chat/use-chat.ts](web/src/lib/chat/use-chat.ts) deserializes events and assembles `ChatMessage` objects with structured payloads.
8. React components in [web/src/components/chat/](web/src/components/chat/) render verdict cards, comp previews, risk profiles, scenario tables, maps, and charts. **Phase 4c Cycle 1 (2026-04-28)** added tier-aware rendering: when `ChatMessage.answerType === "browse"` (sourced from the `message` SSE event's `answer_type` field, persisted on `messages.answer_type`), `AssistantMessage` renders a three-section newspaper-hierarchy layout — `BrowseRead` ([browse-read.tsx](web/src/components/chat/browse-read.tsx)) + `BrowseScout` ([browse-scout.tsx](web/src/components/chat/browse-scout.tsx)) + `BrowseDeeperRead` ([browse-deeper-read.tsx](web/src/components/chat/browse-deeper-read.tsx)) — instead of the legacy card stack. Sections share a single primitive at [browse-section.tsx](web/src/components/chat/browse-section.tsx) (small-caps section label + 1px top rule + 2rem padding; no nested boxed cards). Section A (`BrowseRead`) is fully filled in Cycle 1 with stance pill + ask/fair-value headline + masthead `market_trend` chart + flowed synthesizer prose; Sections B and C are stubs that fill in Cycles 2–4 of [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md). All other tiers (DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP) continue to render the legacy card stack unchanged.

## Specialty Models Inventory

Briarwood has two tiers of specialty models: a **scoped execution registry** (23 models, the active production runners) and a **legacy module layer** (25+ models that existed before the scoped pattern and remain reachable only through the scoped wrappers or post-hoc grafts).

### Scoped execution registry (23 models)

All defined in [briarwood/execution/registry.py](briarwood/execution/registry.py). Each exposes `run_<name>(context: ExecutionContext) -> dict[str, object]`.

| Model | File | Inputs | Outputs (key fields) | Deps | Purpose |
|-------|------|--------|----------------------|------|---------|
| `valuation` | [briarwood/modules/valuation.py](briarwood/modules/valuation.py) | `property_data` | `briarwood_current_value`, `mispricing_pct`, `confidence` | — (internally: comparable_sales, market_value_history, income_support, hybrid_value) | Fair-value estimate with macro-nudge on `hpi_momentum` (max 3%). |
| `carry_cost` | [briarwood/modules/carry_cost.py](briarwood/modules/carry_cost.py) | `property_data`, financing `assumptions` | `monthly_payment`, `annual_property_tax`, `total_annual_cost`, `cash_flow_impact` | — | Ownership cost per month. |
| `risk_model` | [briarwood/modules/risk_model.py](briarwood/modules/risk_model.py) | `property_data`, prior `valuation` + `legal_confidence` | `confidence`, `valuation_bridge`, `legal_confidence_signal`, warnings | `valuation`, `legal_confidence` | Adjusts confidence for overpricing and legal uncertainty; macro-nudge on `liquidity`. |
| `confidence` | [briarwood/modules/confidence.py](briarwood/modules/confidence.py) | `property_data`, all prior outputs | `confidence` (top-level ModulePayload), `confidence_band`; components in `extra_data` (`field_completeness`, `comp_quality`, `model_agreement`, `scenario_fragility`, `legal_certainty`, `estimated_reliance`, `contradiction_count`, `aggregated_prior_confidence`, `combined_confidence`, `prior_module_confidences`) | — | Weighted ensemble across completeness, agreement, fragility. |
| `resale_scenario` | [briarwood/modules/resale_scenario_scoped.py](briarwood/modules/resale_scenario_scoped.py) | `property_data`, `hold_period_years` | `ask_price`, `bull_case_value`, `base_case_value`, `bear_case_value`, `spread` | `valuation`, `carry_cost`, `town_development_index` (internally runs `bull_base_bear`) | Forward resale projection. |
| `rental_option` | [briarwood/modules/rental_option_scoped.py](briarwood/modules/rental_option_scoped.py) | `property_data` | `rental_ease_label`, `liquidity_score`, `demand_depth_score`, `rent_support_score`, `structural_support_score`, `estimated_days_to_rent`, `scarcity_support_score`, `zillow_context_used`; plus `extra_data.income_support`, `extra_data.macro_nudge` | — | Rent-to-own viability via `RentalEaseModule` + `IncomeSupportModule` + employment-macro nudge. |
| `rent_stabilization` | [briarwood/modules/rent_stabilization.py](briarwood/modules/rent_stabilization.py) | `property_data` | `rental_ease_label`, `rent_support_score`, `confidence` | — (internally: `rental_ease`, `town_county_outlook`, `scarcity_support`) | Rent durability and market signal. |
| `hold_to_rent` | [briarwood/modules/hold_to_rent.py](briarwood/modules/hold_to_rent.py) | `property_data`, `assumptions` | `hold_path_snapshot` (`monthly_cash_flow`, `cap_rate`, `rental_ease_label`, `rental_ease_score`, `estimated_days_to_rent`); plus nested `carry_cost` and `rent_stabilization` sub-dicts | `carry_cost`, `rent_stabilization` | Composite wrapper packaging carry + stabilization into a hold-path view. |
| `renovation_impact` | [briarwood/modules/renovation_impact_scoped.py](briarwood/modules/renovation_impact_scoped.py) | `property_data`, `repair_capex_budget` | `enabled`, `renovation_budget`, `current_bcv`, `renovated_bcv`, `gross_value_creation`, `net_value_creation`, `roi_pct`, `cost_per_dollar_of_value`, `condition_change`, `sqft_change`, `comp_range_text`, `confidence`, `warnings`, `summary` | — | BCV-delta + ROI calculator for an already-specified renovation scenario (not scope/cost-range estimator). |
| `arv_model` | [briarwood/modules/arv_model_scoped.py](briarwood/modules/arv_model_scoped.py) | `property_data`, `assumptions` | `arv_snapshot` (`current_bcv`, `renovated_bcv`, `renovation_budget`, `gross_value_creation`, `net_value_creation`, `roi_pct`, `condition_change`, `sqft_change`, `comp_range_text`); plus nested `valuation` and `renovation_impact` sub-dicts | `valuation`, `renovation_impact` | Pure composite wrapper — does NOT call `comparable_sales` directly; that call happens transitively inside `renovation_impact`. |
| `margin_sensitivity` | [briarwood/modules/margin_sensitivity_scoped.py](briarwood/modules/margin_sensitivity_scoped.py) | `property_data`, `assumptions` | `margin_at_base_case`, `margin_at_90pct_arv`, `margin_at_110pct_cost` | `arv_model`, `renovation_impact`, `carry_cost` | Renovation margin stress test. |
| `unit_income_offset` | [briarwood/modules/unit_income_offset.py](briarwood/modules/unit_income_offset.py) | `property_data`, `assumptions` | `offset_snapshot` (`additional_unit_income_value`, `additional_unit_count`, `back_house_monthly_rent`, `unit_rents`, `monthly_total_cost`, `monthly_cash_flow`, `has_accessory_unit_signal`); plus `comparable_sales` sub-dict; outer `confidence` | `carry_cost` (internally: `comparable_sales`) | ADU/accessory unit offset income. ADU cap rate (0.08) and expense ratio (0.30) live in [briarwood/modules/comparable_sales.py](briarwood/modules/comparable_sales.py) (`_DEFAULT_ADU_CAP_RATE`, `_ADU_EXPENSE_RATIO`). |
| `legal_confidence` | [briarwood/modules/legal_confidence.py](briarwood/modules/legal_confidence.py) | `property_data` (zoning, deed restrictions, local documents) | `legality_evidence` (dict: `has_accessory_signal`, `adu_type`, `has_back_house`, `additional_unit_count`, `zone_flags`, `local_document_count`, `multi_unit_allowed`), `data_quality`, `local_intelligence` (optional), `summary`, outer `confidence` | — | Zoning / ADU evidence coverage (NOT a legal classifier — no `permission_flags` / `restriction_flags` fields). |
| `opportunity_cost` | [briarwood/modules/opportunity_cost.py](briarwood/modules/opportunity_cost.py) | `property_data`, `hold_period_years` | `property_terminal_value`, `passive_benchmark_return`, `outperformance_vs_tbill`, `outperformance_vs_sp500` | `valuation`, `resale_scenario` | Capital allocation vs. T-bill 5Y and S&P 500. |
| `town_development_index` | [briarwood/modules/town_development_index.py](briarwood/modules/town_development_index.py) | `property_data` (town, state) | `approval_rate`, `activity_volume`, `contention`, `development_velocity`, `explanation` | — | 12-month rolling window over planning-board minutes (`JsonMinutesStore`); 6-month half-life decay. |
| `strategy_classifier` | [briarwood/modules/strategy_classifier.py](briarwood/modules/strategy_classifier.py) | `property_data` | `strategy` (enum: `owner_occ_sfh` / `owner_occ_duplex` / `owner_occ_with_adu` / `pure_rental` / `value_add_sfh` / `redevelopment_play` / `scarcity_hold` / `unknown`), `rationale`, `rule_fired`, `candidates`, `confidence` | — | Deterministic rule-based property-strategy classifier; no LLM. Promoted to scoped registry in Handoff 3 (2026-04-24). |
| `market_value_history` | [briarwood/modules/market_value_history_scoped.py](briarwood/modules/market_value_history_scoped.py) | `property_data` (town, state) | `geography_name`, `geography_type`, `current_value`, `one_year_change_pct`, `three_year_change_pct`, `history_points`; full `points` time-series in `legacy_payload` | — | Town/county Zillow ZHVI trend lookup. Geography-level — not property-specific. Promoted to scoped registry in Handoff 3 (2026-04-24). |
| `current_value` | [briarwood/modules/current_value_scoped.py](briarwood/modules/current_value_scoped.py) | `property_data` | `briarwood_current_value`, `mispricing_pct`, `pricing_view`, `value_low`/`value_high`, `all_in_basis`, `confidence` (pre-macro) | — (internally: comparable_sales, market_value_history, income_support, hybrid_value) | Pre-macro fair-value anchor. Same engine as `valuation` but does NOT apply the HPI-momentum nudge. Sibling tool with disambiguation contract — see READMEs. Promoted to scoped registry in Handoff 3 (2026-04-24). |
| `income_support` | [briarwood/modules/income_support_scoped.py](briarwood/modules/income_support_scoped.py) | `property_data` (purchase_price, rent, financing assumptions) | `income_support_ratio`, `rent_coverage`, `price_to_rent`, `monthly_cash_flow`, `rent_support_classification`, `effective_monthly_rent`, `gross_monthly_cost`, `rent_source_type`, `confidence` | — | Raw rental-underwriting ratios for LOOKUP intents. Same engine as `rental_option` but does NOT apply the employment-macro nudge or layer rental-ease context. Sibling tool with disambiguation contract — see READMEs. Promoted to scoped registry in Handoff 3 (2026-04-24). |
| `scarcity_support` | [briarwood/modules/scarcity_support_scoped.py](briarwood/modules/scarcity_support_scoped.py) | `property_data` (town, state) | `scarcity_support_score` (0–100), `scarcity_label`, `buyer_takeaway`, sub-component scores (`demand_consistency_score`, `location_scarcity_score`, `land_scarcity_score`), `confidence` | — | Town/segment supply and optionality signal. Field-name stability on `scarcity_support_score` load-bearing — read by decision_model / interactions / rental_ease. Promoted to scoped registry in Handoff 3 (2026-04-24). |
| `location_intelligence` | [briarwood/modules/location_intelligence_scoped.py](briarwood/modules/location_intelligence_scoped.py) | `property_data` (town, state, lat/long, landmark_points, zone_flags) | `location_score`, `scarcity_score`, `primary_category`, `location_premium_pct`, `subject_relative_premium_pct`, `category_results`, `narratives`, `confidence_notes`, `missing_inputs`, `confidence` | — | Landmark-proximity benchmarking against same-town peer comp buckets. First scoped tool covering the MICRO_LOCATION intent family. Missing-input semantics preserved verbatim. Promoted to scoped registry in Handoff 3 (2026-04-24). |
| `comparable_sales` | [briarwood/modules/comparable_sales_scoped.py](briarwood/modules/comparable_sales_scoped.py) | `property_data` (sqft, beds, baths, town, state, + optional lot/year/condition/accessory fields) | `comparable_value`, `comp_count`, `comp_confidence_score`, `comps_used`, `direct_value_range` / `income_adjusted_value_range` / `location_adjustment_range` / `lot_adjustment_range` / `blended_value_range`, `is_hybrid_valuation`, `primary_dwelling_value`, `additional_unit_income_value`, `additional_unit_cap_rate`, `hybrid_valuation_note`, `confidence` | — (internally: market_value_history) | Comp-based fair-value anchor (Engine A, saved comps). Field-name stability load-bearing — read by `hybrid_value` (via prior_results) and `unit_income_offset`. As of CMA Phase 4a Cycles 3a-3c (2026-04-26), Engine A's scoring math lives in [briarwood/modules/comp_scoring.py](briarwood/modules/comp_scoring.py) and is shared with Engine B (`get_cma`); legacy function names in `comparable_sales.py` are thin delegators. Promoted to scoped registry in Handoff 3 (2026-04-24). |
| `hybrid_value` | [briarwood/modules/hybrid_value_scoped.py](briarwood/modules/hybrid_value_scoped.py) | `property_data`, `prior_outputs.comparable_sales`, `prior_outputs.income_support` | `is_hybrid`, `reason`, `primary_house_value`, `rear_income_value`, `rear_income_method_used`, `optionality_premium_value`, `low_case_hybrid_value`, `base_case_hybrid_value`, `high_case_hybrid_value`, `market_friction_discount`, `market_feedback_adjustment`, `confidence` | `comparable_sales`, `income_support` | Decomposed valuation for primary+accessory properties. **Composite wrapper with canonical missing-priors contract** — requires both upstreams to run cleanly; treats `mode in {"error","fallback"}` priors as missing. `is_hybrid=False` short-circuit preserved as a valid zero-confidence answer, NOT an error. Promoted to scoped registry in Handoff 3 (2026-04-24). |

### Legacy modules (not in scoped registry)

These predate the scoped pattern and are callable only from within other modules (or via the post-hoc graft at [briarwood/claims/pipeline.py:62-114](briarwood/claims/pipeline.py#L62-L114), which as of CMA Phase 4a Cycle 6 routes through the canonical scoped runner `run_comparable_sales` and reads the `ComparableSalesOutput` pydantic shape only to repackage `data.legacy_payload`). Each exposes a class with a `run(property_input)` method returning a `ModuleResult`.

| Model | File | Role |
|-------|------|------|
| `BullBaseBearModule` | [briarwood/modules/bull_base_bear.py](briarwood/modules/bull_base_bear.py) | Bull/base/bear scenario range engine. KEEP-as-internal-helper: wrapped by scoped `resale_scenario` ([briarwood/modules/resale_scenario_scoped.py:30](briarwood/modules/resale_scenario_scoped.py#L30)); also consumed by `teardown_scenario` via `prior_results`. Same pattern as `RentalEaseModule`, `RiskConstraintsModule`, `PropertyDataQualityModule`. Reclassified from DEPRECATE during Handoff 4 — see DECISIONS.md 2026-04-24 "PROMOTION_PLAN.md entry 6 decision corrected." |
| `RentalEaseModule` | [briarwood/modules/rental_ease.py](briarwood/modules/rental_ease.py) | Rental-absorption difficulty. Uses Zillow ZORI/ZORDI/ZORF. |
| `TownCountyOutlookModule` | [briarwood/modules/town_county_outlook.py](briarwood/modules/town_county_outlook.py) | Town/county sentiment. Backed by `TownCountyAgent`. |
| `RiskConstraintsModule` | [briarwood/modules/risk_constraints.py](briarwood/modules/risk_constraints.py) | Risk flag catalog (condition, title, flood, zoning). Feeds `bull_base_bear`. |
| `OwnershipEconomicsModule` | [briarwood/modules/ownership_economics.py](briarwood/modules/ownership_economics.py) | Ownership-carry economics: PITI, HOA, maintenance reserve, NOI, DSCR, cap rate. Consumed by the scoped `carry_cost` wrapper. Renamed from `CostValuationModule` in Handoff 2a Piece 5A (2026-04-24). |
| `LocalIntelligenceModule` | [briarwood/modules/local_intelligence.py](briarwood/modules/local_intelligence.py) | News, planning, deed-restriction signal surfaces. |
| `PropertyDataQualityModule` | [briarwood/modules/property_data_quality.py](briarwood/modules/property_data_quality.py) | Completeness score, contradiction flags. Anchors `confidence`. |
| `RenovationScenarioModule` | [briarwood/modules/renovation_scenario.py](briarwood/modules/renovation_scenario.py) | Legacy reno path (superseded by scoped `renovation_impact`). |
| `TeardownScenarioModule` | [briarwood/modules/teardown_scenario.py](briarwood/modules/teardown_scenario.py) | Land-value + redevelopment scenario. |

### Sub-agents

The modules above are often thin wrappers around agents in [briarwood/agents/](briarwood/agents/):

| Agent | Directory | Backs |
|-------|-----------|-------|
| `ComparableSalesAgent` | [briarwood/agents/comparable_sales/](briarwood/agents/comparable_sales/) | `ComparableSalesModule` |
| `IncomeAgent` | [briarwood/agents/income/](briarwood/agents/income/) | `IncomeSupportModule` |
| `RentalEaseAgent` | [briarwood/agents/rental_ease/](briarwood/agents/rental_ease/) | `RentalEaseModule` |
| `TownCountyAgent` | [briarwood/agents/town_county/](briarwood/agents/town_county/) | `TownCountyOutlookModule` |
| `CurrentValueAgent` | [briarwood/agents/current_value/](briarwood/agents/current_value/) | `CurrentValueModule` |

## LLM Integrations

Active call sites across the codebase. All are non-streaming; the streaming the user sees is applied after LLM response at the SSE layer.

### Core clients

- **OpenAI client** at [briarwood/agent/llm.py:84-193](briarwood/agent/llm.py#L84-L193). Methods: `complete()` (Responses API, free text) and `complete_structured()` (JSON schema mode, Pydantic-validated). Default model `gpt-4o-mini`.
- **Anthropic client** at [briarwood/agent/llm.py:195-348](briarwood/agent/llm.py#L195-L348). Same methods; structured output via tool-use JSON mode. Default model `claude-sonnet-4-6`.
- Provider selection at [briarwood/agent/llm.py:350-371](briarwood/agent/llm.py#L350-L371) via `BRIARWOOD_AGENT_PROVIDER` (default `openai`).

### Call sites

| Site | Purpose | Provider / model | Schema | Prompt source |
|------|---------|------------------|--------|---------------|
| [briarwood/agent/router.py:210-237](briarwood/agent/router.py#L210-L237) | Intent classification into 14 `AnswerType` values | OpenAI (injected) / `gpt-4o-mini` | `RouterClassification` | Inline at [briarwood/agent/router.py:138-177](briarwood/agent/router.py#L138-L177) |
| [briarwood/agent/composer.py](briarwood/agent/composer.py) `complete_and_verify()` | Prose composition with grounding verifier | Auto-routed (Anthropic for decision_summary/edge/risk; OpenAI otherwise) | Free text | YAML files in `api/prompts/` |
| [briarwood/agent/composer.py:249-270](briarwood/agent/composer.py#L249-L270) | Decision critic (optional, off by default) | Anthropic / `claude-opus-4-7` | `DecisionCriticReview` | Inline |
| [briarwood/representation/agent.py:128-187](briarwood/representation/agent.py#L128-L187) | Chart selection | OpenAI / `gpt-4o-mini` | `RepresentationPlan` | Inline at [briarwood/representation/agent.py:108-125](briarwood/representation/agent.py#L108-L125) |
| [briarwood/local_intelligence/adapters.py:130-193](briarwood/local_intelligence/adapters.py#L130-L193) | Town signal extraction from documents | OpenAI / `gpt-5-mini` | `TownSignalDraftBatch` | `LOCAL_INTELLIGENCE_SYSTEM_PROMPT` |
| [briarwood/claims/representation/verdict_with_comparison.py:87-106](briarwood/claims/representation/verdict_with_comparison.py#L87-L106) | Claim prose (2–4 sentences around verdict + insight) | OpenAI (injected) / default | Free text | `api/prompts/claim_verdict_with_comparison.yaml` |
| [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) `synthesize_with_llm()` | Chat-tier prose from `UnifiedIntelligenceOutput` | Injected LLM / default | Free text | Inline newspaper/plain prompts; ledger surface `synthesis.llm` |
| [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) `scout_unified()` | Non-obvious chat-tier Scout Finds | Injected LLM / default structured model | `_ScoutScanResult` | Inline `_SYSTEM_PROMPT`; ledger surface `value_scout.scan` |

### Grounding and verification

[briarwood/agent/composer.py](briarwood/agent/composer.py) wraps every composed prose through a grounding verifier that checks numeric tokens, entities, and hedges against a `[[Module:field:value]]` anchor format. Violations above a threshold trigger strict regen (default on via `BRIARWOOD_STRICT_REGEN`). The verifier's numeric extraction lives in [api/guardrails.py:168-207](api/guardrails.py#L168-L207).

### Env vars

| Var | Default | Role |
|-----|---------|------|
| `BRIARWOOD_AGENT_PROVIDER` | `openai` | Global LLM provider |
| `BRIARWOOD_NARRATIVE_PROVIDER` | `auto` | Route decision_summary/edge/risk to Anthropic |
| `BRIARWOOD_DECISION_CRITIC` | `off` | Enable critic (`off`/`shadow`/`on`) |
| `BRIARWOOD_STRICT_REGEN` | `on` | Strip + retry on ≥2 grounding violations |
| `BRIARWOOD_CLAIMS_ENABLED` | `false` | Enable Phase 3 claim-object pipeline |
| `BRIARWOOD_CLAIMS_PROPERTY_IDS` | `""` | Whitelist property IDs for claims (empty = all) |
| `BRIARWOOD_AGENT_MODEL` | `gpt-4o-mini` | OpenAI prose model |
| `BRIARWOOD_STRUCTURED_MODEL` | `gpt-4o-mini` | OpenAI structured-output model |
| `BRIARWOOD_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic default |
| `BRIARWOOD_CRITIC_MODEL` | `claude-opus-4-7` | Critic model |
| `BRIARWOOD_REPRESENTATION_MODEL` | `gpt-4o-mini` | Chart-selection model |
| `BRIARWOOD_LOCAL_INTELLIGENCE_MODEL` | `gpt-5-mini` | Town signal extraction |
| `BRIARWOOD_LOCAL_INTELLIGENCE_REASONING` | `low` | Reasoning effort for town extraction |
| `BRIARWOOD_BUDGET_OPENAI_USD` | `1.00` | OpenAI spend cap |
| `BRIARWOOD_BUDGET_ANTHROPIC_USD` | `1.00` | Anthropic spend cap |

Cost enforcement at [briarwood/cost_guard.py](briarwood/cost_guard.py) — checked pre-call, usage recorded post-response.

## Orchestration Layer

The orchestration layer today is a **handler registry**, not an LLM-driven tool-use loop.

- **Router** at [briarwood/agent/router.py:105](briarwood/agent/router.py#L105) classifies the turn into an `AnswerType` (14 values: LOOKUP, DECISION, COMPARISON, SEARCH, RESEARCH, VISUALIZE, RENT_LOOKUP, MICRO_LOCATION, PROJECTION, RISK, EDGE, STRATEGY, BROWSE, CHITCHAT). Two regex cache rules (stand-alone greeting → CHITCHAT; explicit compare/vs → COMPARISON) plus a what-if-price-override short-circuit at `classify` lines 267-296 (price-override parser hit → DECISION / RENT_LOOKUP / PROJECTION based on text hints); everything else goes to the LLM.
- **Dispatch** at [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) (4538 LOC) holds 14 per-`AnswerType` handler functions: `handle_lookup`, `handle_decision`, `handle_search`, `handle_comparison`, `handle_research`, `handle_visualize`, `handle_rent_lookup`, `handle_projection`, `handle_micro_location`, `handle_risk`, `handle_edge`, `handle_strategy`, `handle_browse`, `handle_chitchat`. Each handler hardcodes which specialty models run and in what order for its tier.
- **Scoped execution** at [briarwood/execution/](briarwood/execution/) implements the registry + planner + executor pattern AGENTS.md prescribes: modules declare dependencies, the planner resolves the DAG, the executor fires runners in order and caches outputs by `build_cache_key(property_data, assumptions, execution_mode)`.
- **Orchestrator** at [briarwood/orchestrator.py](briarwood/orchestrator.py) exposes two entry points today, with different call topologies:
  - `run_briarwood_analysis_with_artifacts(property_data, user_input, synthesizer=_scoped_synthesizer)` — runs the intent-contract router (`briarwood/router.py`), then the scoped pipeline, then an injected synthesizer. Production callers are [briarwood/runner_routed.py:228](briarwood/runner_routed.py#L228) (batch / pre-computation) and [briarwood/claims/pipeline.py:42](briarwood/claims/pipeline.py#L42) (claims wedge). Chat-tier handlers do NOT call this directly — see DECISIONS.md 2026-04-25 "README_dispatch.md overstates orchestrator coupling".
  - `run_chat_tier_analysis(property_data, answer_type, user_input, *, parser_output=None, parallel=False)` (added 2026-04-25, Cycle 2 of OUTPUT_QUALITY_HANDOFF_PLAN.md) — skips the intent-contract router (the chat-tier router has already produced an `AnswerType`), picks a module set from [`briarwood/execution/module_sets.py::ANSWER_TYPE_MODULE_SETS`](briarwood/execution/module_sets.py), runs a single consolidated execution plan, and calls the deterministic `briarwood.synthesis.structured.build_unified_output` directly. LOOKUP and the non-property tiers short-circuit. **Wired into `handle_browse` 2026-04-25 (Cycle 3, commit `ca94d2f`)** via the helper `_browse_chat_tier_artifact` — for saved properties the BROWSE handler now runs ONE consolidated execution plan with all 23 scoped modules instead of the per-tool fragmentation pattern from §9.3. Other chat-tier handlers (`handle_decision`, `handle_risk`, `handle_edge`, `handle_strategy`, `handle_projection`, `handle_rent_lookup`) still use the per-tool pattern — Cycle 5 will roll the same rewire out.
- **Layer 3 LLM synthesizer** at [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) (added 2026-04-25, Cycle 4 of OUTPUT_QUALITY_HANDOFF_PLAN.md, commit `fb23152`). `synthesize_with_llm(*, unified, intent, llm, max_tokens=360) -> tuple[str, dict]` reads a fully-populated `UnifiedIntelligenceOutput` and the user's `IntentContract` and writes 3-7 sentences of intent-aware prose. Single LLM call wrapped in `complete_text_observed(surface="synthesis.llm", ...)` for distinct ledger telemetry. Numeric guardrail via `api.guardrails.verify_response` over the full unified output; one regen attempt (`synthesis.llm.regen` surface) on threshold-level ungrounded numbers, kept only when violations strictly decrease. **Wired into all six chat-tier handlers as of 2026-04-25 (Cycle 5):** `handle_browse` (Cycle 4, `fb23152`), `handle_projection` (`1f8ab6a`), `handle_risk` (`6b861e9`), `handle_edge` (`d3293a1`), `handle_strategy` (`3811dbf`), `handle_rent_lookup` (`c589635`), `handle_decision` final summary (`a429d88`). On empty synthesizer output the tier-specific composer fires as fallback so user-visible prose is never empty. Section-followup composers (`compose_section_followup` for trust, downside, comp_set, entry_point, value_change, rent_workability) keep their narrow-payload composer calls — those follow-ups are surgical section-specific generations, not full intent-aware prose.
- **Value Scout** at [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) exposes `scout(input_obj, *, llm=None, intent=None, max_insights=2)`. Claim-wedge inputs run deterministic `uplift_dominance`; chat-tier `UnifiedIntelligenceOutput` inputs run deterministic rails (`rent_angle`, `adu_signal`, `town_trend_tailwind`) plus the LLM scout when `llm` is provided. Results are sorted by `SurfacedInsight.confidence`, cached on `session.last_scout_insights`, threaded into `synthesize_with_llm`, and emitted as the `scout_insights` SSE event for the `ScoutFinds` React surface.
- **Macro nudges** at [briarwood/pipeline/triage.py](briarwood/pipeline/triage.py) apply small confidence/value adjustments per module based on signed macro signals (HPI momentum, liquidity) with per-dimension caps.

There is no LLM layer that reads a tool registry and picks which specialty models to invoke. Model selection is encoded in handler code.

## UI Layer

Next.js 16.2.4 App Router + React 19.2.4 + Tailwind 4.

- [web/src/app/page.tsx](web/src/app/page.tsx) — home page, loads conversations and renders chat.
- [web/src/app/layout.tsx](web/src/app/layout.tsx) — root layout.
- [web/src/app/api/chat/route.ts](web/src/app/api/chat/route.ts) — reverse proxy to FastAPI (keeps API URL server-side).
- [web/src/lib/chat/use-chat.ts](web/src/lib/chat/use-chat.ts) — custom SSE hook (doesn't use Vercel AI SDK because Briarwood's wire format is structured).
- [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — TypeScript event types, mirrors [api/events.py](api/events.py).

Chat components in [web/src/components/chat/](web/src/components/chat/):

| Component | Renders |
|-----------|---------|
| `chat-view.tsx` | Main chat container |
| `sidebar.tsx` | Conversation history |
| `property-card.tsx` | Listing card |
| `verdict-card.tsx` | Structured verdict + comparison |
| `scenario-chart-section.tsx` | Bull/base/bear chart |
| `comps-preview-card.tsx` | Top comps |
| `risk-profile-card.tsx` | Risk breakdown |
| `rent-outlook-card.tsx` | Rental projection |
| `strategy-path-card.tsx` | Investment-path recommendation |
| `research-update-card.tsx` | Town research findings |
| `cma-table-card.tsx` | Comparative-market-analysis table |
| `inline-map.tsx` | Map with pins |
| `chart-frame.tsx` | iframe for Plotly HTML artifacts |
| `property-carousel.tsx` | Property carousel |
| `empty-state.tsx` | Initial empty UI |

The SSE protocol in [api/events.py](api/events.py) defines 22 event types: `text_delta`, `tool_call`, `tool_result`, `listings`, `map`, `suggestions`, `verdict`, `chart`, `scenario_table`, `comparison_table`, `town_summary`, `comps_preview`, `risk_profile`, `value_thesis`, `valuation_comps`, `market_support_comps`, `strategy_path`, `rent_outlook`, `research_update`, `trust_summary`, `modules_ran`, `grounding_annotations`, `verifier_report`, `partial_data_warning`, `claim_rejected`, `conversation`, `message`, `done`, `error`.

## Persistence

The chat-tier observability layer writes three durable artifacts (added
2026-04-28 as AI-Native Foundation Stage 1; see
[PERSISTENCE_HANDOFF_PLAN.md](PERSISTENCE_HANDOFF_PLAN.md) and
[ROADMAP.md](ROADMAP.md) §3.1). All three are populated by default — no
env-var gating — and all three are exception-safe (a write failure logs
with a `[turn_traces]` / `[llm_calls.jsonl]` / `[messages.metrics]`
prefix and never breaks a turn).

- **`turn_traces` table** in [`data/web/conversations.db`](api/store.py).
  One row per chat turn, finalized in the `event_source` finally block
  at [api/main.py:269-288](api/main.py) from the `TurnManifest` returned
  by `end_turn()` ([briarwood/agent/turn_manifest.py:185](briarwood/agent/turn_manifest.py#L185)).
  Schema declared in `_init_schema` at [api/store.py:48-91](api/store.py#L48-L91);
  insert path at `insert_turn_trace` ([api/store.py:155](api/store.py)).
  JSON columns (`modules_run`, `modules_skipped`, `llm_calls_summary`,
  `tool_calls`, `notes`, `wedge`) carry the full
  `TurnManifest.to_jsonable()` shape. Indexes on `(conversation_id,
  started_at)` and `started_at`. `conversation_id` declared `ON DELETE
  SET NULL` and `delete_conversation` applies it explicitly so traces
  survive conversation deletion (deliberate divergence from the
  `messages.ON DELETE CASCADE` semantic).
- **`data/llm_calls.jsonl`** — one JSON line per LLM call. Sink lives
  in `LLMCallLedger.append` at
  [briarwood/agent/llm_observability.py:80-103](briarwood/agent/llm_observability.py#L80-L103),
  mirroring every record the ledger receives. Excludes `debug_payload`
  unless `BRIARWOOD_LLM_DEBUG_PAYLOADS=1`. Adds an ISO-8601
  `recorded_at` at write time (the dataclass carries no absolute
  timestamp). Path overridable via `BRIARWOOD_LLM_JSONL_PATH`. Test
  runs are isolated by [tests/conftest.py](tests/conftest.py), which
  redirects the env var to a per-session tmp file so the production
  artifact isn't polluted.
- **Scout yield telemetry** — chat-tier `scout(...)` calls append a
  `value_scout_yield insights_generated=... insights_surfaced=...
  top_confidence=...` note to the active `TurnManifest`. The LLM Scout
  path also appears in `data/llm_calls.jsonl` under surface
  `value_scout.scan` (and `value_scout.scan.regen` when numeric
  grounding triggers a rewrite), so `/admin/turn/[turn_id]` can compare
  Scout output yield against LLM cost and duration.
- **Metric columns on `messages`** — `latency_ms`, `answer_type`,
  `success_flag`, `turn_trace_id` (FK → `turn_traces.turn_id`,
  `ON DELETE SET NULL`). Added via idempotent `ALTER TABLE ADD COLUMN`
  migrations ([api/store.py:93-104](api/store.py#L93-L104)) so
  re-running `_init_schema` is a no-op. Backfilled forward only; null
  on rows from before Stage 1 landed. Populated on the assistant
  message row in the same `event_source` finally block via
  `ConversationStore.attach_turn_metrics` ([api/store.py:117-152](api/store.py#L117-L152)).
  `success_flag=True` semantically means "the manifest reached
  `end_turn` without exception" (v1; revisited when Stage 2 — the
  feedback loop — lands).

The owner-visible payoff: any `sqlite3 data/web/conversations.db`
query can now answer "what was the slowest turn this week" or "which
`answer_type` is the most expensive on average" without grepping logs.
The single concrete success-criteria query from the plan
(`SELECT answer_type, AVG(duration_ms_total) FROM turn_traces GROUP BY 1`)
returns real numbers as soon as the API has served any traffic. Stage 3
(admin dashboard, [ROADMAP.md](ROADMAP.md) §3.1) is the read-side UI
that consumes these artifacts.

**Stage 2 — User feedback loop (added 2026-04-28).** A fourth durable
artifact joined the persistence layer with the
[`FEEDBACK_LOOP_HANDOFF_PLAN.md`](FEEDBACK_LOOP_HANDOFF_PLAN.md) Cycles
1-4 landing:

- **`feedback` table** in [`data/web/conversations.db`](api/store.py).
  One row per rated assistant message. PK on `message_id`; FKs declared
  to `messages` (`ON DELETE CASCADE`) and `turn_traces` (`ON DELETE SET
  NULL`). Schema in `_init_schema` at
  [api/store.py:68-83](api/store.py#L68-L83); upsert path at
  `ConversationStore.upsert_feedback` ([api/store.py:155](api/store.py)).
  `INSERT OR REPLACE` semantics on revision (last-write-wins per
  `message_id`); `created_at` preserved across revisions, `updated_at`
  advanced. Indexes on `(conversation_id, created_at)` and
  `(rating, created_at)`. `delete_conversation` applies the CASCADE
  explicitly (FK enforcement is off project-wide).
- **JSONL mirror** — every successful POST also appends to
  `data/learning/intelligence_feedback.jsonl` via the existing
  `build_user_feedback_record` → `append_intelligence_capture` chain,
  so the analyzer at
  [`briarwood/feedback/analyzer.py`](briarwood/feedback/analyzer.py)
  picks up ratings without a code change. The wire vocabulary
  (`"up"|"down"`) is translated at the API boundary to the helper's
  vocabulary (`"yes"|"no"`) so the analyzer's
  threshold-recommendation logic at
  [briarwood/feedback/analyzer.py:306-353](briarwood/feedback/analyzer.py#L306-L353)
  keeps working unchanged. Path overridable via
  `BRIARWOOD_INTEL_FEEDBACK_PATH`; [tests/conftest.py](tests/conftest.py)
  redirects per session so test runs don't pollute the analyzer hopper.
- **Read-back consumer** — when the same conversation has a recent
  thumbs-down, the next turn's synthesizer system prompt gains a
  "vary your framing" directive. Implemented via a `ContextVar` in
  [`briarwood/synthesis/feedback_hint.py`](briarwood/synthesis/feedback_hint.py),
  set by `apply_feedback_hint` in
  [api/pipeline_adapter.py](api/pipeline_adapter.py) entry points
  (browse / decision / search / dispatch streams) and read by
  `synthesize_with_llm`. Manifest carries the
  `feedback:recent-thumbs-down-influenced-synthesis` tag so the loop
  closure surfaces in `turn_traces.notes` for SQL audit. Numeric and
  citation rules from the base synthesis prompt are unchanged; the
  hint only affects framing.

**Stage 3 — Read-side admin surface (added 2026-04-28).** The
substrate above (Stages 1+2) gained a read-side UI with
[`DASHBOARD_HANDOFF_PLAN.md`](DASHBOARD_HANDOFF_PLAN.md) Cycles 1-4:

- **Three FastAPI admin endpoints** under `/api/admin/*` in
  [api/main.py](api/main.py), all gated behind
  `BRIARWOOD_ADMIN_ENABLED=1` (404 when unset, not 403, so a probe
  doesn't reveal the surface exists). `GET /api/admin/metrics?days=N`
  returns latency-by-answer_type + cost-by-surface + thumbs ratio.
  `GET /api/admin/turns/recent?days=N&limit=M` returns top-N slowest
  + top-N highest-cost. `GET /api/admin/turns/{turn_id}` returns the
  full per-turn manifest plus any feedback rows that joined to its
  messages.
- **SQL aggregators** on `ConversationStore` in
  [api/store.py](api/store.py):
  `latency_durations_by_answer_type`, `thumbs_ratio_since`,
  `top_slowest_turns`, `get_turn_trace` (deserializes JSON columns
  defensively — leaves raw string in place on corrupt JSON rather
  than raising), `feedback_for_turn` (LEFT JOIN via
  `messages.turn_trace_id`).
- **JSONL aggregators** in the new
  [api/admin_metrics.py](api/admin_metrics.py) module:
  `cost_by_surface`, `top_costliest_turns`. Read-and-aggregate-on-request
  pattern; today's JSONL is a few thousand lines, parse is sub-100ms.
  v2 path (SQLite cost table) deferred until file grows past a few
  hundred MB.
- **`turn_id` linkage on JSONL writes** added during Cycle 1 — small
  scope addition over the original Stage 1 plan. The
  `LLMCallLedger._write_jsonl` path now looks up
  `current_manifest().turn_id` at write time and stamps it on the
  payload; failure-safe via the same try/except pattern as the
  manifest-mirror lookup. New JSONL records carry `turn_id`;
  pre-Stage-3 records do not, and are excluded from the top-N cost
  ranking (the dashboard's empty-state notice explains this so the
  empty table doesn't read as broken).
- **Next server-component routes** at
  `web/src/app/admin/page.tsx` (top-line metrics; 1d/7d/30d window
  switch; plain HTML/CSS bar-width visualizations — chart-library
  evaluation deferred to Phase 4c UI reconstruction per ROADMAP
  §3.4.7) and `web/src/app/admin/turn/[turn_id]/page.tsx` (full
  manifest drill-down; the `feedback:recent-thumbs-down-influenced-synthesis`
  note tag renders highlighted as the closure-loop audit affordance
  from Stage 2). Unlinked from the main UI by design.

**Stage 4 — Model-accuracy loop substrate (added 2026-04-28).** The
model-accuracy loop now has a manual outcome-ingestion path and a durable
alignment store. Real outcome data still has to be supplied and backfilled
before the loop has live rows to review.

- **Outcome loader** in [briarwood/eval/outcomes.py](briarwood/eval/outcomes.py).
  Loads manual CSV/JSONL files under the Stage 4 outcome contract:
  `property_id`, `address`, `outcome_type="sale_price"`, `outcome_value`,
  `outcome_date`, `source`, `source_ref`, `confidence`, `notes`. Matching is
  strict: exact `property_id` first, normalized address second; ambiguous
  rows are reported rather than guessed.
- **Outcome CLIs** in [scripts/ingest_outcomes.py](scripts/ingest_outcomes.py)
  and [scripts/backfill_outcomes.py](scripts/backfill_outcomes.py). The
  ingest script validates rows and reports errors/duplicates. The backfill
  script attaches outcome objects to matching
  `data/learning/intelligence_feedback.jsonl` rows, preserves a `.bak`, and
  refuses to overwrite non-null outcomes unless explicitly requested.
- **Alignment backfill** in
  [briarwood/eval/model_alignment_backfill.py](briarwood/eval/model_alignment_backfill.py)
  and [scripts/backfill_model_alignment.py](scripts/backfill_model_alignment.py).
  It resolves outcome rows to saved properties by strict `property_id` first
  and normalized address second, builds an `ExecutionContext` from
  `data/saved_properties/<id>/inputs.json`, runs `current_value`,
  `valuation`, and `comparable_sales`, and records `model_alignment` rows.
  It supports `--dry-run` and skips duplicate rows by default.
- **`model_alignment` table** in [`data/web/conversations.db`](api/store.py).
  Declared in `ConversationStore._init_schema`; insert/read helpers are
  `insert_model_alignment` and `model_alignment_rows`. Rows carry
  `module_name`, prediction, confidence, sale outcome, absolute error,
  absolute percentage error, alignment score, high-confidence flag,
  underperformance flag, and JSON evidence.
- **Record-only receiver hooks** on
  [briarwood/modules/current_value_scoped.py](briarwood/modules/current_value_scoped.py),
  [briarwood/modules/valuation.py](briarwood/modules/valuation.py), and
  [briarwood/modules/comparable_sales_scoped.py](briarwood/modules/comparable_sales_scoped.py).
  Each exposes `receive_feedback(session_id, signal)` and writes alignment
  evidence when given a module payload and sale-price outcome. These hooks do
  not change weights, thresholds, prompts, or module behavior.
- **Alignment analyzer** at
  [briarwood/feedback/model_alignment_analyzer.py](briarwood/feedback/model_alignment_analyzer.py).
  Reports rows scored by module, mean absolute percentage error,
  high-confidence underperformance rates, top examples, and human-review
  tuning candidates. There is no auto-tuning path.

**Deferred follow-ons:**
- (Stage 1) JSONL rotation/compaction policy (file under operational
  backlog when size becomes an issue); top-level analytic query
  sketches to seed Stage 3's dashboard.
- (Stage 2) Asset-quality rating (different signal from
  response-quality thumbs; feeds Stage 4 — Loop 1 Model Accuracy —
  rather than Loop 2). Tier label `mixed` reserved for the middle
  option when built. Comment column reserved on the `feedback`
  table; v2 client can ship without an API change.
- (Stage 3) JSONL → SQLite cost table when file grows past a few
  hundred MB; real auth on the admin surface (currently env-gate
  only); chart-library swap (bound to Phase 4c UI reconstruction
  per §3.4.7).
- (Stage 4) Run against real outcome data; optional `/admin` panel for
  alignment summaries; public-record outcome automation after the manual
  loop proves useful.

## Known Rough Edges

File-path-cited, no editorial framing.

### Structural

- **`comparable_sales` is in the scoped registry as of Handoff 3 (2026-04-24).** Registered at [briarwood/execution/registry.py:270-284](briarwood/execution/registry.py#L270-L284) with runner [briarwood/modules/comparable_sales_scoped.py](briarwood/modules/comparable_sales_scoped.py). The post-hoc graft at [briarwood/claims/pipeline.py:62-114](briarwood/claims/pipeline.py#L62-L114) routes through the canonical scoped runner `run_comparable_sales(context)` as of CMA Phase 4a Cycle 6 (2026-04-28). The graft repackages the scoped wrapper's `data.legacy_payload` as a `ComparableSalesOutput` pydantic instance under `outputs["comparable_sales"]["payload"]` so [briarwood/claims/synthesis/verdict_with_comparison.py:413-425](briarwood/claims/synthesis/verdict_with_comparison.py#L413-L425) `_iter_comps` can keep using its `payload.comps_used` access path. The graft itself is still required because the orchestrator's routed run does not surface `comparable_sales` as a top-level entry in `module_results["outputs"]` (it runs only as an internal dependency of `valuation`); full removal is gated on top-level surfacing — see ROADMAP §4 High *Consolidate chat-tier execution*.
- **`decision_model/scoring.py`'s `calculate_final_score` was deleted 2026-04-24** (Handoff 4). It and its supporting chain (`FinalScore`/`CategoryScore`/`SubFactorScore` dataclasses, all `_calculate_*` category builders, all `_score_*` helpers, the entire `lens_scoring.py` file) had zero production callers and were removed. Production synthesis at [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) was never coupled to this path. The `estimate_comp_renovation_premium` function + its utility helpers were preserved — they are called 7× from `briarwood/components.py`. See DECISIONS.md 2026-04-24 "PROMOTION_PLAN.md entry 15 scope-limit paragraph corrected."
- **`security_model.py` is a stub.** [briarwood/modules/security_model.py](briarwood/modules/security_model.py) has minimal implementation; no downstream consumers.
- **Resolver has no state-aware disambiguation.** For ambiguous queries like "526 West End Ave" the saved-properties directory contains three colliding slugs (`526-w-end-ave-avon-by-the-sea-nj`, `526-w-end-ave-statesville-nc-28677`, `526-west-end-ave`). The token-overlap scorer at [briarwood/agent/resolver.py:92-160](briarwood/agent/resolver.py#L92-L160) correctly returns ambiguity (None + ranked candidates); the risk is that downstream callers consume `ranked[0]` instead of presenting the disambiguation prompt.

### Hardcoded values / TODOs

- `$400/sqft` default replacement cost in [briarwood/decision_model/scoring_config.py](briarwood/decision_model/scoring_config.py) — explicit `# TODO: make geography/property-type aware in a future iteration.`
- ADU cap rate `_DEFAULT_ADU_CAP_RATE = 0.08` and expense ratio `_ADU_EXPENSE_RATIO = 0.30` hardcoded in [briarwood/modules/comparable_sales.py](briarwood/modules/comparable_sales.py) (lines 28 and 32). They feed the `additional_unit_income_value` decomposition `ComparableSalesModule` performs; `unit_income_offset` and `hybrid_value` consume that decomposition transitively but do not define the constants themselves.
- Risk thresholds hardcoded in [briarwood/modules/risk_model.py](briarwood/modules/risk_model.py): `OVERPRICED_THRESHOLD = 0.15`, `UNDERPRICED_THRESHOLD = -0.10`.
- Claim-object thresholds hardcoded in [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py): `VALUE_FIND` at delta ≤ -5%, `OVERPRICED` at delta ≥ +5%, sample-size-caveat threshold at 5 properties.
- Cross-town comp expansion landed in CMA Phase 4a Cycle 4 (2026-04-26). Engine B's `get_cma` queries each neighbor in [briarwood/modules/cma_invariants.py](briarwood/modules/cma_invariants.py)'s `TOWN_ADJACENCY` map for SOLD listings when same-town SOLD count is below `MIN_SOLD_COUNT`; rows tag `is_cross_town=True`. Engine A (saved comps) is still strictly same-town — its provider filters at [briarwood/modules/comparable_sales.py:76-86](briarwood/modules/comparable_sales.py#L76-L86) by normalized town. There is no `base_comp_selector.py` file in the repo; the same-town filter has no TODO comment.
- Sqft matching uses a sliding score penalty at [briarwood/agents/comparable_sales/agent.py:429-444](briarwood/agents/comparable_sales/agent.py#L429-L444) — `score -= min(sqft_gap * 0.45, 0.28)` with rationale thresholds at 10% and 20% gap. There is no hard 15% tolerance band; weak-sqft matches degrade their score and flow downstream as cautions on the comp.
- Renovation-premium pass-through to live (Engine B) comps deferred — `estimate_comp_renovation_premium` is internal to Engine A. See ROADMAP §4 Medium *Renovation premium pass-through to live comps*.

### Historical audit cross-references (still live)

Four findings from the historical audit markdowns remain applicable to current code. Citations here are by document name; the docs themselves live at the repo root and are marked historical per [AGENTS.md](AGENTS.md). One further finding (`VERIFICATION_REPORT.md` NEW-V-003) was flagged during historical skim but is **no longer live** — the fix is visible in the commentary at [api/guardrails.py:173-182](api/guardrails.py#L173-L182) which documents the NEW-V-003 fix inline and the corresponding `elif isinstance(node, str)` branch that extracts embedded numeric tokens from prose fields.

1. **No fallback on scoped-registry failure** (`AUDIT_REPORT.md` F-004, elevated in `VERIFICATION_REPORT.md`). [briarwood/orchestrator.py:505-514](briarwood/orchestrator.py#L505-L514) raises `RoutingError` if scoped execution cannot cover the selected module set. The legacy `AnalysisEngine` fallback is deleted. The whole analysis pipeline now depends on scoped-registry completeness; a router/registry mismatch fails hard.
2. **Mock-listings fallback has no demo-mode gate** (`AUDIT_REPORT.md` F-001). [api/main.py:334-335](api/main.py#L334-L335) falls through to `_echo_stream()` when the router returns `None`; `_echo_stream` then calls `mock_listings_for()` at [api/main.py:162](api/main.py#L162) when the query looks like a listing query. No `BRIARWOOD_DEMO_MODE` guard — fabricated listings can serve silently on provider failure. The surrounding comments (lines 291, 305) show the team has narrowed the fall-through envelope, but the gate itself is not in place.
3. **`all_in_basis` computed but not consumed by the UI** (`AUDIT_REPORT.md` F-003, `VERIFICATION_REPORT.md` confirmed-partial). Synthesizer at [briarwood/synthesis/structured.py:252-265](briarwood/synthesis/structured.py#L252-L265) computes `all_in_basis`; it's declared on the verdict event at [api/pipeline_adapter.py:615](api/pipeline_adapter.py#L615) and projected at [api/pipeline_adapter.py:658](api/pipeline_adapter.py#L658); it appears in the TypeScript type at [web/src/lib/chat/events.ts:152](web/src/lib/chat/events.ts#L152). No card in [web/src/components/chat/](web/src/components/chat/) reads it — `grep -rn all_in_basis web/src/components/` returns zero hits. The true-cost-to-own anchor is wired through the whole data path but the last rendering step is missing.
4. **`primary_value_source` bridge tends to return `"unknown"`** (`VERIFICATION_REPORT.md` NEW-V-005; recent commit `56e0d53 fix(interactions): log primary_value_source bridge decisions` added logging but did not change the core classification logic). [briarwood/interactions/primary_value_source.py](briarwood/interactions/primary_value_source.py) checks four signal paths (strategy → mispricing → carry offset → scenario) and falls back to `"unknown"` at line 134 when none fire. The UI consumes the value at [web/src/components/chat/value-thesis-card.tsx:33-35](web/src/components/chat/value-thesis-card.tsx#L33-L35) and [web/src/components/chat/comparison-table.tsx:124](web/src/components/chat/comparison-table.tsx#L124), both gated on `!== "unknown"`. Whether the bridge fires is fixture-dependent; historical verification against typical fixtures found it returning `"unknown"` on all of them.

Two historical docs are wholly superseded: `BRIARWOOD-AUDIT.md` and `UX-ASSESSMENT.md`. Both describe the deleted Dash UI and legacy `AnalysisEngine` architecture.

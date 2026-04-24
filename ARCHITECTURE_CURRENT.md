# Briarwood — Current Architecture

Factual snapshot of what exists in the codebase as of 2026-04-24. No gap analysis, no recommendations. For those, see [GAP_ANALYSIS.md](GAP_ANALYSIS.md).

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
| [briarwood/value_scout/](briarwood/value_scout/) | Pattern-based insight surfacing on claim objects. |
| [briarwood/synthesis/](briarwood/synthesis/) | Legacy structured-output synthesis (runs when claims pipeline disabled). |
| [briarwood/representation/](briarwood/representation/) | Representation Agent + chart registry. |
| [briarwood/interactions/](briarwood/interactions/) | Session state, persona inference, primary-value-source bridge. |
| [briarwood/local_intelligence/](briarwood/local_intelligence/) | Town-level document and news signal extraction. |
| [briarwood/decision_model/](briarwood/decision_model/) | Decision scoring config and `FinalScore` calculation. |
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
   - **Flag on**: `build_claim_for_property()` at [briarwood/claims/pipeline.py:28](briarwood/claims/pipeline.py#L28) runs `run_briarwood_analysis_with_artifacts()`, grafts a `ComparableSalesModule` run post-hoc at [briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88), and calls `build_verdict_with_comparison_claim()`. The claim goes through `scout_claim()` at [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) (one pattern registered: `uplift_dominance`), then `edit_claim()` at [briarwood/editor/validator.py](briarwood/editor/validator.py) (5 checks). On pass, `render_claim()` at [briarwood/claims/representation/verdict_with_comparison.py:52](briarwood/claims/representation/verdict_with_comparison.py#L52) emits prose + chart + suggestions events. On editor failure, the handler emits `EVENT_CLAIM_REJECTED` and falls back to the legacy path.
   - **Flag off**: handler runs the scoped-execution registry via `briarwood.orchestrator.run_briarwood_analysis_with_artifacts()`, synthesizes through [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py), and emits events directly.
6. Responses stream back as SSE events defined in [api/events.py](api/events.py) (22 event types).
7. The `useChat` hook in [web/src/lib/chat/use-chat.ts](web/src/lib/chat/use-chat.ts) deserializes events and assembles `ChatMessage` objects with structured payloads.
8. React components in [web/src/components/chat/](web/src/components/chat/) render verdict cards, comp previews, risk profiles, scenario tables, maps, and charts.

## Specialty Models Inventory

Briarwood has two tiers of specialty models: a **scoped execution registry** (15 models, the active production runners) and a **legacy module layer** (25+ models that existed before the scoped pattern and remain reachable only through the scoped wrappers or post-hoc grafts).

### Scoped execution registry (15 models)

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

### Legacy modules (not in scoped registry)

These predate the scoped pattern and are callable only from within other modules (or via post-hoc grafts like [briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88)). Each exposes a class with a `run(property_input)` method returning a `ModuleResult`.

| Model | File | Role |
|-------|------|------|
| `CurrentValueModule` | [briarwood/modules/current_value.py](briarwood/modules/current_value.py) | Valuation anchor; composes comps + history + income + hybrid. Consumed by scoped `valuation`. |
| `ComparableSalesModule` | [briarwood/modules/comparable_sales.py](briarwood/modules/comparable_sales.py) | Comp-based anchor. Data source: `data/comps/sales_comps.json`. Hybrid detection + income premium. |
| `BullBaseBearModule` | [briarwood/modules/bull_base_bear.py](briarwood/modules/bull_base_bear.py) | Bull/base/bear scenario range. Runs inside scoped `resale_scenario`. |
| `HybridValueModule` | [briarwood/modules/hybrid_value.py](briarwood/modules/hybrid_value.py) | Decomposes value into primary structure + accessory income for multi-unit. |
| `IncomeSupportModule` | [briarwood/modules/income_support.py](briarwood/modules/income_support.py) | Rent estimation and carry-cost income ratio. Backed by `IncomeAgent`. |
| `MarketValueHistoryModule` | [briarwood/modules/market_value_history.py](briarwood/modules/market_value_history.py) | Historical price trend. |
| `RentalEaseModule` | [briarwood/modules/rental_ease.py](briarwood/modules/rental_ease.py) | Rental-absorption difficulty. Uses Zillow ZORI/ZORDI/ZORF. |
| `TownCountyOutlookModule` | [briarwood/modules/town_county_outlook.py](briarwood/modules/town_county_outlook.py) | Town/county sentiment. Backed by `TownCountyAgent`. |
| `ScarcitySupportModule` | [briarwood/modules/scarcity_support.py](briarwood/modules/scarcity_support.py) | Supply/optionality signal. |
| `RiskConstraintsModule` | [briarwood/modules/risk_constraints.py](briarwood/modules/risk_constraints.py) | Risk flag catalog (condition, title, flood, zoning). Feeds `bull_base_bear`. |
| `OwnershipEconomicsModule` | [briarwood/modules/ownership_economics.py](briarwood/modules/ownership_economics.py) | Ownership-carry economics: PITI, HOA, maintenance reserve, NOI, DSCR, cap rate. Consumed by the scoped `carry_cost` wrapper. Renamed from `CostValuationModule` in Handoff 2a Piece 5A (2026-04-24). |
| `LocationIntelligenceModule` | [briarwood/modules/location_intelligence.py](briarwood/modules/location_intelligence.py) | Micro-location scoring (walkability, transit, amenities). |
| `LocalIntelligenceModule` | [briarwood/modules/local_intelligence.py](briarwood/modules/local_intelligence.py) | News, planning, deed-restriction signal surfaces. |
| `PropertyDataQualityModule` | [briarwood/modules/property_data_quality.py](briarwood/modules/property_data_quality.py) | Completeness score, contradiction flags. Anchors `confidence`. |
| `StrategyClassifier` | [briarwood/modules/strategy_classifier.py](briarwood/modules/strategy_classifier.py) | Rule-based property-strategy classifier (`owner_occ_sfh`, `pure_rental`, `value_add_sfh`, etc.). Runs at Layer 2 (post-intake, pre-domain). |
| `value_finder` | [briarwood/modules/value_finder.py](briarwood/modules/value_finder.py) | Deterministic value-gap analysis: `value_gap_pct`, `pricing_posture`, `opportunity_signal`. Distinct from `value_scout`. |
| `RenovationScenarioModule` | [briarwood/modules/renovation_scenario.py](briarwood/modules/renovation_scenario.py) | Legacy reno path (superseded by scoped `renovation_impact`). |
| `TeardownScenarioModule` | [briarwood/modules/teardown_scenario.py](briarwood/modules/teardown_scenario.py) | Land-value + redevelopment scenario. |
| `FinalScore` / `calculate_final_score` | [briarwood/decision_model/scoring.py](briarwood/decision_model/scoring.py) | Weighted 5-category scoring (`price_context` 15%, `economic_support` 30%, `optionality` 20%, `market_position` 20%, `risk_layer` 15%). **Defined but not invoked in current production synthesis.** |

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

Nine call sites across the codebase. All are non-streaming; the streaming the user sees is applied after LLM response at the SSE layer.

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
- **Orchestrator** at [briarwood/orchestrator.py](briarwood/orchestrator.py) is the single entry point handlers call: `run_briarwood_analysis_with_artifacts(property_data, user_input, synthesizer=_scoped_synthesizer)`. It routes the analysis, runs the scoped pipeline, and returns a unified artifact bundle.
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

## Known Rough Edges

File-path-cited, no editorial framing.

### Structural

- **`ComparableSalesModule` is not in the scoped registry.** It's invoked only inside `CurrentValueModule`, `HybridValueModule`, `ArvModule`, `UnitIncomeOffsetModule`, and (since the claims wedge) via a post-hoc graft at [briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88). The comment at that graft is explicit: `"The scoped execution registry doesn't surface comparable_sales as a top-level module ... Running the module directly here fills that gap without editing briarwood/modules/."`
- **`decision_model/scoring.py`'s `calculate_final_score` is defined but not invoked in production synthesis.** Current synthesis ([briarwood/synthesis/structured.py](briarwood/synthesis/structured.py)) uses different scoring logic. The 5-category weighted scorer and its tier mapping (Buy ≥3.30, Neutral ≥2.50, Avoid <2.50) are live code but dead paths.
- **`security_model.py` is a stub.** [briarwood/modules/security_model.py](briarwood/modules/security_model.py) has minimal implementation; no downstream consumers.
- **Resolver has no state-aware disambiguation.** For ambiguous queries like "526 West End Ave" the saved-properties directory contains three colliding slugs (`526-w-end-ave-avon-by-the-sea-nj`, `526-w-end-ave-statesville-nc-28677`, `526-west-end-ave`). The token-overlap scorer at [briarwood/agent/resolver.py:92-160](briarwood/agent/resolver.py#L92-L160) correctly returns ambiguity (None + ranked candidates); the risk is that downstream callers consume `ranked[0]` instead of presenting the disambiguation prompt.

### Hardcoded values / TODOs

- `$400/sqft` default replacement cost in [briarwood/decision_model/scoring_config.py](briarwood/decision_model/scoring_config.py) — explicit `# TODO: make geography/property-type aware in a future iteration.`
- ADU cap rate `_DEFAULT_ADU_CAP_RATE = 0.08` and expense ratio `_ADU_EXPENSE_RATIO = 0.30` hardcoded in [briarwood/modules/comparable_sales.py](briarwood/modules/comparable_sales.py) (lines 28 and 32). They feed the `additional_unit_income_value` decomposition `ComparableSalesModule` performs; `unit_income_offset` and `hybrid_value` consume that decomposition transitively but do not define the constants themselves.
- Risk thresholds hardcoded in [briarwood/modules/risk_model.py](briarwood/modules/risk_model.py): `OVERPRICED_THRESHOLD = 0.15`, `UNDERPRICED_THRESHOLD = -0.10`.
- Claim-object thresholds hardcoded in [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py): `VALUE_FIND` at delta ≤ -5%, `OVERPRICED` at delta ≥ +5%, sample-size-caveat threshold at 5 properties.
- Cross-town comp TODO in `base_comp_selector.py`.
- Renovation-premium TODO in comparable_sales agent (`estimate_comp_renovation_premium` not yet fed through).

### Historical audit cross-references (still live)

Four findings from the historical audit markdowns remain applicable to current code. Citations here are by document name; the docs themselves live at the repo root and are marked historical per [AGENTS.md](AGENTS.md). One further finding (`VERIFICATION_REPORT.md` NEW-V-003) was flagged during historical skim but is **no longer live** — the fix is visible in the commentary at [api/guardrails.py:173-182](api/guardrails.py#L173-L182) which documents the NEW-V-003 fix inline and the corresponding `elif isinstance(node, str)` branch that extracts embedded numeric tokens from prose fields.

1. **No fallback on scoped-registry failure** (`AUDIT_REPORT.md` F-004, elevated in `VERIFICATION_REPORT.md`). [briarwood/orchestrator.py:505-514](briarwood/orchestrator.py#L505-L514) raises `RoutingError` if scoped execution cannot cover the selected module set. The legacy `AnalysisEngine` fallback is deleted. The whole analysis pipeline now depends on scoped-registry completeness; a router/registry mismatch fails hard.
2. **Mock-listings fallback has no demo-mode gate** (`AUDIT_REPORT.md` F-001). [api/main.py:334-335](api/main.py#L334-L335) falls through to `_echo_stream()` when the router returns `None`; `_echo_stream` then calls `mock_listings_for()` at [api/main.py:162](api/main.py#L162) when the query looks like a listing query. No `BRIARWOOD_DEMO_MODE` guard — fabricated listings can serve silently on provider failure. The surrounding comments (lines 291, 305) show the team has narrowed the fall-through envelope, but the gate itself is not in place.
3. **`all_in_basis` computed but not consumed by the UI** (`AUDIT_REPORT.md` F-003, `VERIFICATION_REPORT.md` confirmed-partial). Synthesizer at [briarwood/synthesis/structured.py:252-265](briarwood/synthesis/structured.py#L252-L265) computes `all_in_basis`; it's declared on the verdict event at [api/pipeline_adapter.py:615](api/pipeline_adapter.py#L615) and projected at [api/pipeline_adapter.py:658](api/pipeline_adapter.py#L658); it appears in the TypeScript type at [web/src/lib/chat/events.ts:152](web/src/lib/chat/events.ts#L152). No card in [web/src/components/chat/](web/src/components/chat/) reads it — `grep -rn all_in_basis web/src/components/` returns zero hits. The true-cost-to-own anchor is wired through the whole data path but the last rendering step is missing.
4. **`primary_value_source` bridge tends to return `"unknown"`** (`VERIFICATION_REPORT.md` NEW-V-005; recent commit `56e0d53 fix(interactions): log primary_value_source bridge decisions` added logging but did not change the core classification logic). [briarwood/interactions/primary_value_source.py](briarwood/interactions/primary_value_source.py) checks four signal paths (strategy → mispricing → carry offset → scenario) and falls back to `"unknown"` at line 134 when none fire. The UI consumes the value at [web/src/components/chat/value-thesis-card.tsx:33-35](web/src/components/chat/value-thesis-card.tsx#L33-L35) and [web/src/components/chat/comparison-table.tsx:124](web/src/components/chat/comparison-table.tsx#L124), both gated on `!== "unknown"`. Whether the bridge fires is fixture-dependent; historical verification against typical fixtures found it returning `"unknown"` on all of them.

Two historical docs are wholly superseded: `BRIARWOOD-AUDIT.md` and `UX-ASSESSMENT.md`. Both describe the deleted Dash UI and legacy `AnalysisEngine` architecture.

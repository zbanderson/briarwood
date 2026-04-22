# Briarwood Intelligence — Full Audit Report
Date: 2026-04-19
Workspace: briarwood
Supersedes: 2026-04-12

## Executive Summary

Briarwood now has a real decision-first routed core. The strongest current path is the scoped routed analysis flow: `route_user_input()` selects typed module sets, `execute_plan()` runs scoped modules against a typed `ExecutionContext`, `run_all_bridges()` records cross-module interactions, and `build_unified_output()` produces a deterministic `UnifiedIntelligenceOutput` with a trust gate, explicit `decision_stance`, `primary_value_source`, `trust_flags`, and `what_changes_my_view` fields. That core is bounded by typed contracts in `briarwood/routing_schema.py` and is covered by focused planner, executor, orchestrator, and structured-synthesis tests. `briarwood/router.py:564-586`, `briarwood/execution/context.py:8-31`, `briarwood/execution/executor.py:289-364`, `briarwood/interactions/registry.py:42-65`, `briarwood/synthesis/structured.py:34-115`, `tests/test_execution_v2.py:14-228`, `tests/test_orchestrator.py:22-435`, `tests/synthesis/test_structured_synthesizer.py:60-175`

The biggest product risk is verdict lineage. Chat/API decision flows render the deterministic routed verdict from `briarwood/synthesis/structured.py`, but Dash and report surfaces still compute a separate legacy verdict through `briarwood.decision_engine.build_decision()`. A third older pipeline stack (`briarwood/pipeline/*`) still defines its own `UnifiedIntelligenceAgent` and `DecisionAgent`. The new SSE projector explicitly rejects legacy `BUY/LEAN BUY/NEUTRAL/LEAN PASS/AVOID` labels because they are incompatible with the routed `DecisionStance` vocabulary. There is no reconciliation layer that guarantees these paths agree for the same property. `briarwood/synthesis/structured.py:63-115`, `briarwood/decision_engine.py:29-96`, `briarwood/dash_app/quick_decision.py:35-55`, `briarwood/dash_app/view_models.py:3062-3175`, `briarwood/reports/sections/thesis_section.py:8-30`, `briarwood/reports/sections/conclusion_section.py:9-52`, `api/pipeline_adapter.py:548-639`, `tests/test_pipeline_adapter_contracts.py:798-821`, `briarwood/pipeline/runner.py:31-78`

The biggest product gaps are portfolio awareness and trustworthy evidence lineage. The routed execution boundary carries property data, assumptions, market/comp context, and macro context, but no holdings, portfolio constraints, or alternative opportunity set. The only explicit “capital allocation” module, `opportunity_cost`, compares appreciation-only property CAGR to passive benchmarks; it does not compare against the user’s actual portfolio or other live property candidates. `briarwood/execution/context.py:20-31`, `briarwood/orchestrator.py:397-531`, `briarwood/modules/opportunity_cost.py:1-26`, `briarwood/modules/opportunity_cost.py:120-187`, `briarwood/interactions/opportunity_x_value.py:69-100`, `briarwood/dash_app/components.py:5928-5988`

The biggest technical risks are stale/shared state and user-facing silent degradation. The orchestrator uses process-global mutable caches for routing, module results, synthesis output, and scoped module outputs; the synthesis cache key excludes material property facts such as `beds`, `baths`, `sqft`, and `taxes`, so changed property facts under the same property id and assumption set can reuse stale outputs without warning. Separately, the decision handler silently drops town summary, comps preview, value thesis, and scenario enrichments on exception, and the chat UI drops part of the backend’s verdict and verifier payloads. `briarwood/orchestrator.py:29-33`, `briarwood/orchestrator.py:116-137`, `briarwood/orchestrator.py:433-523`, `briarwood/agent/dispatch.py:1381-1429`, `api/pipeline_adapter.py:602-660`, `web/src/lib/chat/events.ts:113-131`, `web/src/components/chat/verdict-card.tsx:37-133`, `web/src/lib/chat/use-chat.ts:350-359`

The current architecture supports the Briarwood promise best in deterministic property-level underwriting and weakest in cross-surface consistency, portfolio-level allocation, and comp/verdict provenance. The first fixes should be: collapse verdict generation to one canonical path, correct the user-facing comp provenance mismatch in CMA/event surfaces, and harden cache/state invalidation so repeated runs cannot silently reuse stale decisions. `docs/current_docs_index.md:20-27`, `briarwood/synthesis/structured.py:121-227`, `api/events.py:184-186`, `briarwood/agent/tools.py:1802-1848`, `briarwood/agent/tools.py:1892-1963`

## Phase 0 — Repo Map Reference

See `REPO_MAP.md` at the repo root for the directory map, inventory counts, dependency snapshot, and initial architecture read.

## Phase 1 — Product / Feature Audit

### 1.1 Foundational Question Coverage

| Foundational Question | Responsible Components | Prompt(s) | Output Destination | Confidence Present? |
| --- | --- | --- | --- | --- |
| 1. Is this property mispriced? | `valuation`, `valuation_x_town`, `valuation_x_risk`, `build_unified_output()` | `decision_value.md`, `decision_summary.md` | `verdict`, `value_thesis`, narrative summary | Yes: module confidence plus synth aggregate/trust gate. `briarwood/modules/valuation.py:15-63`, `briarwood/synthesis/structured.py:52-68`, `briarwood/synthesis/structured.py:233-271`, `briarwood/agent/dispatch.py:1556-1613` |
| 2. What does it cost to own? | `carry_cost`, `rental_option`, `rent_stabilization`, `hold_to_rent` | `decision_summary.md`, `rent_lookup.md`, `strategy.md` | `strategy_path`, `rent_outlook`, `scenario_table`, narrative | Yes, but split across multiple modules and surfaces. `briarwood/routing_schema.py:145-184`, `briarwood/modules/rental_option_scoped.py:16-72`, `briarwood/modules/rent_stabilization.py:13-61`, `briarwood/modules/hold_to_rent.py:10-68`, `api/events.py:189-205`, `api/events.py:196-200` |
| 3. What happens under different scenarios? | `resale_scenario`, `renovation_impact`, `arv_model`, `margin_sensitivity`, `scenario_x_risk` | `projection.md`, `decision_summary.md` | `scenario_table`, native scenario chart, renovation outlooks | Yes. `briarwood/modules/resale_scenario_scoped.py:17-78`, `briarwood/modules/renovation_impact_scoped.py:11-28`, `briarwood/modules/margin_sensitivity_scoped.py:10-87`, `api/pipeline_adapter.py:1746-1771` |
| 4. What are the real risks? | `risk_model`, `legal_confidence`, `confidence`, `conflict_detector`, `rent_x_risk`, `scenario_x_risk` | `risk.md`, `decision_summary.md` | `risk_profile`, `trust_summary`, `verdict`, narrative | Yes. `briarwood/modules/risk_model.py:19-80`, `briarwood/modules/legal_confidence.py:10-123`, `briarwood/modules/confidence.py:16-98`, `briarwood/interactions/conflict_detector.py:22-94`, `briarwood/synthesis/structured.py:274-343` |
| 5. Is this the best use of capital right now? | `opportunity_cost`, `opportunity_x_value` | No dedicated chat prompt; folded into decision/value synthesis | `key_value_drivers` or `key_risks` only when bridge fires | Partially. Confidence exists on the module, but there is no dedicated surfaced card. `briarwood/modules/opportunity_cost.py:38-187`, `briarwood/interactions/opportunity_x_value.py:25-100`, `briarwood/synthesis/structured.py:436-470` |
| 6. Is there hidden upside or optionality? | `strategy_classifier`, `renovation_impact`, `arv_model`, `unit_income_offset`, `primary_value_source`; legacy `hybrid_value` still embeds optionality math | No dedicated `hidden_upside` prompt or routed focus path | Indirectly in `value_thesis`, `strategy_path`, `primary_value_source` | Partial only. `briarwood/modules/strategy_classifier.py:64-182`, `briarwood/interactions/primary_value_source.py:38-100`, `briarwood/modules/unit_income_offset.py:11-87`, `briarwood/modules/hybrid_value.py:162-223` |

**Orphans**

- The older `briarwood/pipeline/*` stack is a parallel decision architecture with its own `Pipeline`, `UnifiedIntelligenceAgent`, and `DecisionAgent`, but it is not the chat/API routed path described in the current docs. It is still exercised by tests and chart helpers. `briarwood/pipeline/runner.py:1-78`, `briarwood/pipeline/unified.py:29-144`, `briarwood/pipeline/decision.py:16-100`, `tests/test_pipeline_e2e.py:22-125`
- Dash/report decision helpers are compatibility surfaces, not the current routed source of truth, but they still compute top-line recommendations from `build_decision(report)`. `docs/current_docs_index.md:20-27`, `briarwood/dash_app/quick_decision.py:35-55`, `briarwood/reports/sections/thesis_section.py:8-30`

**Gaps**

- `CoreQuestion.HIDDEN_UPSIDE` exists in the canonical enum, but `QUESTION_FOCUS_TO_MODULE_HINTS` never maps it to module hints, and no default intent includes it in `INTENT_TO_QUESTIONS`. Hidden upside exists only as indirect optionality/reno logic, not as a first-class routed question. `briarwood/routing_schema.py:28-38`, `briarwood/routing_schema.py:114-140`, `briarwood/routing_schema.py:227-262`
- Capital allocation is not portfolio-aware. The routed contracts carry no portfolio state, and `opportunity_cost` is explicitly appreciation-only vs passive benchmarks. `briarwood/execution/context.py:20-31`, `briarwood/modules/opportunity_cost.py:10-25`

**Overlaps**

- Briarwood answers “rent / hold economics” through multiple overlapping surfaces: `rental_option`, `rent_stabilization`, `hold_to_rent`, `get_rent_outlook()`, `get_strategy_fit()`, and the narrative layer. `briarwood/modules/rental_option_scoped.py:16-72`, `briarwood/modules/rent_stabilization.py:13-61`, `briarwood/modules/hold_to_rent.py:10-68`, `briarwood/agent/tools.py:1519-1693`, `briarwood/agent/tools.py:2015-2054`
- There are at least three top-line recommendation surfaces: deterministic routed synthesis, legacy `decision_engine`, and the older `briarwood/pipeline/decision.py` adapter. `briarwood/synthesis/structured.py:63-115`, `briarwood/decision_engine.py:29-96`, `briarwood/pipeline/decision.py:16-41`

**Conflict Risk**

- `api/events.cma_table()` says the CMA event shows “which comps fed fair value and why,” but `get_cma()` explicitly prefers live Zillow market comps before saved comps and does not read the actual valuation comp set. This creates a user-facing provenance risk: the comp table can imply fair-value lineage it does not actually represent. `api/events.py:184-186`, `briarwood/agent/tools.py:1802-1848`, `briarwood/agent/tools.py:1892-1963`
- `decision_stream()` renders both a structured verdict card and separate prose summary text; those surfaces are generated by different code paths and can drift. `api/pipeline_adapter.py:1675-1779`, `briarwood/agent/dispatch.py:1576-1613`, `web/src/components/chat/messages.tsx:128-171`

### 1.2 Verdict Lineage

There is not one verdict path.

1. The current routed/chat verdict path is deterministic:
   `run_briarwood_analysis_with_artifacts()` -> `run_all_bridges()` -> `_scoped_synthesizer()` -> `build_unified_output()` -> `PropertyView.load(depth="decision")` -> `session.last_decision_view` -> `events.verdict()`. `briarwood/orchestrator.py:505-529`, `briarwood/runner_routed.py:209-232`, `briarwood/agent/property_view.py:75-159`, `briarwood/agent/dispatch.py:1374-1379`, `api/pipeline_adapter.py:1675-1677`
2. Dash/report verdicts still come from the legacy `decision_engine.build_decision(report)` path. `briarwood/decision_engine.py:29-96`, `briarwood/dash_app/quick_decision.py:35-55`, `briarwood/dash_app/view_models.py:3062-3175`, `briarwood/reports/sections/conclusion_section.py:14-52`
3. The older pipeline stack defines a separate `UnifiedIntelligenceAgent` and `DecisionAgent`. `briarwood/pipeline/unified.py:29-144`, `briarwood/pipeline/decision.py:16-41`

**Inference:** the same property can yield different top-line calls across surfaces, because the routed stack uses `DecisionStance`/`DecisionType` plus bridge-based trust gating, while the Dash/report stack uses separate `BUY/LEAN BUY/NEUTRAL/LEAN PASS/AVOID` bands and the SSE layer explicitly rejects those legacy labels. There is no reconciliation step between the vocabularies. `briarwood/synthesis/structured.py:121-227`, `briarwood/decision_engine.py:169-285`, `api/pipeline_adapter.py:570-583`, `tests/test_pipeline_adapter_contracts.py:798-821`

This is a **P0** against trustworthy verdict lineage.

### 1.3 Summary Fidelity

The top-line decision summary is generated independently from the deterministic verdict card, but it is grounded to a structured subset of the routed output.

- `handle_decision()` passes `decision_stance`, `primary_value_source`, ask/basis/fair value, premium percentages, `trust_flags`, `what_must_be_true`, and `research_update` into the `decision_summary` prompt. `briarwood/agent/dispatch.py:1576-1603`
- The LLM output is numerically/entity verified and may be regenerated once under strict mode, then optionally reviewed by a critic. `briarwood/agent/composer.py:332-466`
- The narrative input omits `key_risks`, `why_this_stance`, `what_changes_my_view`, `contradiction_count`, and `blocked_thesis_warnings`, so the prose can remain numerically grounded while still under-surfacing the decisive break condition or conflict list. `briarwood/agent/dispatch.py:1577-1589`, `briarwood/synthesis/structured.py:59-86`

Result: summary fidelity is **Partial**. It is not an ungrounded free-for-all, but it is not a direct rendering of the full verdict object either.

### 1.4 Explainability vs Dashboard Drift

- **Verdict:** strong structured explainability exists in the routed output (`trust_flags`, `what_must_be_true`, `why_this_stance`, `what_changes_my_view`), but the main verdict card only renders stance, pricing stats, trust flags, `what_must_be_true`, and `key_risks`. `briarwood/routing_schema.py:364-375`, `api/pipeline_adapter.py:617-639`, `web/src/components/chat/verdict-card.tsx:37-133`
- **Scenarios:** `scenario_table` answers a user question and carries explicit units (`spread_unit="dollars"`), which is a strong pattern. `api/events.py:111-139`, `web/src/lib/chat/events.ts:140-152`
- **Risks:** the risk card is question-shaped and backed by structured fields; good. `api/events.py:169-173`
- **Comps:** the comp story drifts. `comps_preview` and `cma_table` are user-facing evidence surfaces, but `get_cma()` prefers live Zillow market support before saved Briarwood comps and does not guarantee those rows are the actual valuation evidence. `api/events.py:162-166`, `api/events.py:184-186`, `briarwood/agent/tools.py:1802-1848`, `briarwood/agent/tools.py:1892-1963`
- **Value:** `value_thesis` is closer to explainable intelligence because it carries drivers, `what_must_be_true`, and trust summary. `web/src/lib/chat/events.ts:235-258`
- **Cost to own / rent:** split across `strategy_path`, `rent_outlook`, and narrative; good evidence exists, but the user has to synthesize multiple cards. `api/events.py:189-200`
- **Upside:** present only indirectly through strategy/optionality signals; not first-class.
- **Charts/tables:** native chart specs are question-shaped when present, and HTML artifact fallback is secondary. `api/pipeline_adapter.py:1693-1736`, `api/pipeline_adapter.py:1765-1788`

### 1.5 Confidence Scoring

Confidence is implemented end-to-end in the routed stack, but it is unevenly surfaced.

- Each routed `ModulePayload` can carry `confidence`, `warnings`, `missing_inputs`, and `confidence_band`. `briarwood/routing_schema.py:301-325`
- `run_confidence()` computes a rule-based composite from prior module confidences, data quality, completeness, contradiction count, comp quality, model agreement, scenario fragility, legal certainty, and estimated reliance. `briarwood/modules/confidence.py:16-98`, `briarwood/modules/confidence.py:133-166`
- `build_unified_output()` aggregates module confidence, applies bridge-level penalties, and collapses stance to `CONDITIONAL` when aggregate confidence is below `0.40`. `briarwood/synthesis/structured.py:58-68`, `briarwood/synthesis/structured.py:153-161`, `briarwood/synthesis/structured.py:474-539`
- The trust summary is preserved to the API surface (`trust_summary`) and rendered in a separate card. `api/pipeline_adapter.py:642-660`, `web/src/components/chat/messages.tsx:171-178`
- The main verdict card does not display numeric confidence or the explanation lists that accompany the trust gate. `web/src/components/chat/verdict-card.tsx:37-133`

Low confidence does change verdict behavior in the routed stack; that is good. `briarwood/synthesis/structured.py:153-161`

Confidence weaknesses:

- Confidence is strong in the routed stack but absent from the legacy `decision_engine` vocabulary; Dash/report recommendations rely on `conviction` from a different model. `briarwood/decision_engine.py:95-96`, `briarwood/dash_app/quick_decision.py:39-54`
- `opportunity_cost` has confidence, but its capital-allocation signal is only surfaced indirectly through `key_value_drivers`/`key_risks`, not as a dedicated confidence-bearing card. `briarwood/modules/opportunity_cost.py:173-186`, `briarwood/synthesis/structured.py:436-470`

### 1.6 Portfolio Context

The current routed implementation is not portfolio-aware.

- The routed orchestrator takes `property_data`, `user_input`, optional `prior_context`, and produces a property-scoped `ExecutionContext`; there is no portfolio or holdings input. `briarwood/orchestrator.py:397-531`, `briarwood/execution/context.py:20-31`
- `opportunity_cost` compares the property to T-bills and the S&P 500 only, and its own docstring says the signal is appreciation-only and not IRR-grade. `briarwood/modules/opportunity_cost.py:3-25`, `briarwood/modules/opportunity_cost.py:120-171`
- A portfolio dashboard exists only in the Dash compatibility UI. `briarwood/dash_app/components.py:5928-5988`

This is a significant product gap relative to the stated “allocate capital versus other opportunities” promise.

### 1.7 Visual Narrative Alignment

- `verdict` card answers the core question but drops part of the backend meaning. `api/pipeline_adapter.py:617-639`, `web/src/components/chat/verdict-card.tsx:37-133`
- `scenario_table` is aligned and explicit about units; strong. `api/events.py:111-139`
- `comparison_table` is consistent with the backend projector, but it exposes routed `decision_stance` rather than any portfolio allocation view. `api/pipeline_adapter.py:729-760`
- `cma_table` is not aligned to its label: the event implies “comps that fed fair value,” while the implementation may be a live market-support table. `api/events.py:184-186`, `briarwood/agent/tools.py:1802-1848`
- `messages.tsx` renders prose plus cards in one assistant turn; nearby text can contradict or omit what the cards show. `web/src/components/chat/messages.tsx:128-171`

### 1.8 End-to-End User Flow

Realistic traced flow: user pastes or analyzes one property in chat and requests a decision.

1. **Input entry**
   Shape: `ChatRequest{messages, conversation_id?, pinned_listing?}`.
   File: `api/main.py:76-81`, `api/main.py:230-257`
   Failure mode: empty messages or last message not from user -> HTTP 400, visible.
2. **Tier routing**
   `classify_turn()` decides chat answer tier; “Analyze ...” on a pinned listing is forcibly promoted to decision tier even if the chat router would classify it as browse.
   File: `api/main.py:287-336`, `briarwood/agent/router.py:266-320`
   Failure mode: router exception -> SSE `error` then echo fallback, visible. `api/main.py:293-299`
3. **Session load**
   `conversation_id` is mapped directly to `Session.session_id`, and prior turn views are rehydrated from `data/agent_sessions/<id>.json`.
   File: `api/pipeline_adapter.py:125-147`, `briarwood/agent/session.py:15-124`
   Failure mode: corrupt session JSON -> fresh session silently replaces it; user is not notified. `api/pipeline_adapter.py:138-145`
4. **Decision dispatch**
   `decision_stream()` calls `dispatch()` in a threadpool, forcing `AnswerType.DECISION` if needed.
   File: `api/pipeline_adapter.py:1629-1661`
   Failure mode: dispatch exception -> streamed plain text “Decision analysis failed: ...” plus suggestions, not a structured error event. `api/pipeline_adapter.py:1654-1661`
5. **Property resolution and routed analysis**
   `handle_decision()` resolves the property id, builds `PropertyView.load(depth="decision")`, which calls `analyze_property()`, which calls `run_routed_report()`, which calls `run_routed_analysis_for_property()`, which calls `run_briarwood_analysis_with_artifacts()`.
   File: `briarwood/agent/dispatch.py:1347-1379`, `briarwood/agent/property_view.py:75-99`, `briarwood/agent/tools.py:471-492`, `briarwood/runner_routed.py:448-542`, `briarwood/orchestrator.py:397-531`
   Shape transitions:
   - `summary.json` + `inputs.json` -> `PropertyInput`
   - `ParserOutput` -> `RoutingDecision`
   - `ExecutionContext` -> `EngineOutput` / module-results dict
   - module results + `InteractionTrace` -> `UnifiedIntelligenceOutput`
6. **Scoped execution / fallback**
   The orchestrator prefers scoped execution when every selected module and dependency has a real runner; otherwise it calls the legacy full-engine runner once and projects selected modules back out.
   File: `briarwood/orchestrator.py:443-499`, `briarwood/runner_routed.py:176-206`
   Failure mode: no scoped support and no legacy runner -> exception; visible to caller. `briarwood/orchestrator.py:490-494`
7. **Bridge + synthesis**
   Cross-module bridges record adjustments and conflicts; deterministic synthesis computes the final stance, recommendation, trust summary, and explanation lists.
   File: `briarwood/interactions/registry.py:42-65`, `briarwood/synthesis/structured.py:34-115`
   Failure mode: a bridge bug is swallowed into a non-firing `BridgeRecord`; run continues. `briarwood/interactions/registry.py:53-63`
8. **Secondary evidence surfaces**
   `handle_decision()` separately builds town summary, CMA, comps preview, value thesis, and projection cards. These enrichments are each wrapped in broad `try/except` and are silently skipped on failure.
   File: `briarwood/agent/dispatch.py:1381-1429`
9. **Narrative synthesis**
   `decision_summary` prompt is composed from `PropertyView` fields and verified/criticized.
   File: `briarwood/agent/dispatch.py:1576-1613`, `briarwood/agent/composer.py:332-466`
   Failure mode: LLM budget/transport failure -> deterministic fallback or empty text depending on path; partially visible. `briarwood/agent/composer.py:355-370`
10. **API stream**
    `decision_stream()` emits verdict/town/comps/value/risk/strategy/rent/trust cards first, scenario/secondary charts later, then the listings/map and verifier report.
    File: `api/pipeline_adapter.py:1671-1800`
11. **Frontend render**
    `useChat()` parses SSE frames and stores structured payloads on the assistant message; `messages.tsx` renders verdict, text, cards, charts, map, and optional critic panel.
    File: `web/src/lib/chat/use-chat.ts:147-376`, `web/src/components/chat/messages.tsx:125-265`
    Failure mode: unknown event JSON is ignored; `tool_call` / `tool_result` are no-ops; verifier data is mostly discarded except critic telemetry. `web/src/lib/chat/use-chat.ts:163-167`, `web/src/lib/chat/use-chat.ts:346-359`

Latency: no per-hop latency telemetry is emitted in this flow. Auto-research can add an extra town-research fetch plus a second `PropertyView.load()` rerun, but runtime code does not measure or surface elapsed time. `briarwood/agent/dispatch.py:1439-1468`

### 1.9 Product Promise Test

| Dimension | Rating | Evidence |
| --- | --- | --- |
| Intelligence | **Partial** | Strong deterministic property-level routing/synthesis exists, but capital allocation is only passive-benchmark comparison and not portfolio-aware. `briarwood/synthesis/structured.py:34-115`, `briarwood/modules/opportunity_cost.py:1-26`, `briarwood/execution/context.py:20-31` |
| Explainability | **Partial** | Routed verdict objects are explainable, but UI/prose/card surfaces do not preserve all reasoning, and CMA provenance is overstated. `briarwood/routing_schema.py:364-375`, `web/src/components/chat/verdict-card.tsx:37-133`, `api/events.py:184-186`, `briarwood/agent/tools.py:1802-1848` |
| Confidence | **Strong** in routed core / **Weak** across whole workspace | Routed confidence and trust gating are explicit and tested; legacy verdict paths remain separate. `briarwood/modules/confidence.py:16-98`, `briarwood/synthesis/structured.py:153-161`, `tests/synthesis/test_structured_synthesizer.py:100-129`, `briarwood/decision_engine.py:29-96` |
| Portfolio-aware decision support | **Absent** | No portfolio input in routed contracts; only passive-benchmark comparison and a legacy Dash portfolio dashboard. `briarwood/execution/context.py:20-31`, `briarwood/modules/opportunity_cost.py:13-25`, `briarwood/dash_app/components.py:5928-5988` |
| Fast comprehension | **Partial** | The chat stack emits a top-line verdict and cards early, but users still receive prose plus multiple cards and sometimes mismatched comp/value evidence. `api/pipeline_adapter.py:1675-1779`, `web/src/components/chat/messages.tsx:128-171`, `briarwood/agent/tools.py:1802-1848` |

## Phase 2 — Technical Audit

### 2.1 LLM Call Site Inventory

| Call Site | File:Line | Provider | Model | Task Type | Structured Output? | Schema | Retry? | Timeout? | Consumer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chat intent classifier | `briarwood/agent/router.py:245-263` via `briarwood/agent/llm.py:121-188` / `245-343` | OpenAI or Anthropic | OpenAI structured default `gpt-5`; Anthropic default `claude-sonnet-4-6` | answer-type classification | Yes | `RouterClassification` | No | Yes, client ctor default 30s | `classify()` |
| Narrative composer | `briarwood/agent/composer.py:332-466` via `briarwood/agent/llm.py:93-120` / `213-244` | OpenAI by default; Anthropic for narrative tiers when available | OpenAI default `gpt-4o-mini`; Anthropic default `claude-sonnet-4-6` | free-form narrative synthesis | No | N/A | One verifier-driven regen attempt | Yes, 30s client timeout | `dispatch` handlers |
| Decision critic | `briarwood/agent/composer.py:249-269` | Anthropic | `claude-opus-4-7` by default | critic / rewrite review | Yes | `DecisionCriticReview` | No | Yes, Anthropic client timeout 30s | `decision_summary` only |
| Local intelligence extraction | `briarwood/local_intelligence/adapters.py:156-192` | OpenAI | `OpenAILocalIntelligenceConfig.model` | structured town-signal extraction | Yes | `TownSignalDraftBatch` | No | Yes, config timeout | `OpenAILocalIntelligenceExtractor.extract()` |
| Anthropic structured helper (general) | `briarwood/agent/llm.py:245-343` | Anthropic | caller override or default `claude-sonnet-4-6` | generic structured JSON emission | Yes | caller Pydantic model | No | Yes | router/critic/other structured callers |

Downstream trust of LLM output is mixed:

- Structured outputs are schema-validated and return `None` on transport/parse/schema failure. `briarwood/agent/llm.py:130-188`, `briarwood/agent/llm.py:260-343`, `briarwood/local_intelligence/adapters.py:179-192`
- Narrative outputs are verified for numeric/entity grounding and may be regenerated once, but the final prose is still free-form and not schema-validated. `briarwood/agent/composer.py:372-466`

### 2.2 Agent / Module I-O Contracts

| Component | Input Contract | Output Contract | Validated? | Consumers | Failure Handling | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Routed parser | `str -> ParserOutput` | `ParserOutput` | Yes, Pydantic | `route_user_input()` | fallback to rules/defaults | Strong contract. `briarwood/router.py:467-491`, `briarwood/routing_schema.py:266-299` |
| Scoped modules | `ExecutionContext` | `ModulePayload` dict | Yes, normalized through `ModulePayload` | executor, bridges, synth | module-specific fallback payloads | Strong pattern. `briarwood/execution/context.py:8-31`, `briarwood/routing_schema.py:301-325` |
| Interaction bridges | `ModuleOutputs` | `BridgeRecord` in `InteractionTrace` | Partially; record shape fixed, bridge bodies not | synth | exceptions downgraded to non-firing record | Safe but can hide bridge bugs. `briarwood/interactions/registry.py:42-65` |
| Unified synthesis | `property_summary + parser_output + module_results + trace` | `UnifiedIntelligenceOutput` | Yes | chat/API/property view | `model_validate()` in orchestrator | Strong pattern. `briarwood/synthesis/structured.py:34-115`, `briarwood/orchestrator.py:326-335` |
| Decision view projector | `dict(session.last_decision_view)` | verdict payload | Yes, via `_DecisionView` | SSE layer / UI | warning + empty verdict fallback | Good defensive projector. `api/pipeline_adapter.py:548-639` |
| Decision summary narrative | structured subset of `PropertyView` | string + verifier report | Partially; grounding verifier only | chat narrative | verifier/critic/fallback text | Can omit reasoning fields. `briarwood/agent/dispatch.py:1576-1613`, `briarwood/agent/composer.py:372-466` |
| Local intelligence extractor | `SourceDocument` | `TownSignalDraftBatch` -> `TownSignal[]` | Yes | local intelligence service | empty batch or exception | Strong schema-first extraction. `briarwood/local_intelligence/adapters.py:130-192` |

**Best existing pattern**

The best current pattern is the routed module -> bridge -> deterministic synth path:

- typed inputs (`ExecutionContext`)
- typed outputs (`ModulePayload`, `UnifiedIntelligenceOutput`)
- deterministic bridge trace
- explicit trust gating
- focused tests. `briarwood/execution/context.py:8-31`, `briarwood/routing_schema.py:301-375`, `briarwood/interactions/registry.py:42-65`, `tests/test_execution_v2.py:49-228`, `tests/synthesis/test_structured_synthesizer.py:60-175`

Other surfaces that should copy it:

- CMA / comp provenance surfaces
- Dash/report verdict generation
- LLM narrative summaries

### 2.3 Provider / Model Fit

- Structured router classification using OpenAI `gpt-5` by default is reliable but expensive for a tiny two-field schema. This is a poor cost/latency fit unless the env overrides it. `briarwood/agent/llm.py:144-160`, `briarwood/agent/router.py:231-263`
- Narrative decision summaries routed to Anthropic Sonnet, with optional Opus critic, are a reasonable fit for prose quality and stance review. `briarwood/agent/composer.py:50-57`, `briarwood/agent/composer.py:119-123`, `briarwood/agent/composer.py:427-466`
- Local intelligence extraction uses strict JSON schema output, which is appropriate for provider reliability and downstream validation. `briarwood/local_intelligence/adapters.py:156-192`

Recommended fit changes:

- Move router classification off default `gpt-5` to a cheaper structured-capable model tier unless accuracy evidence shows a clear need. `briarwood/agent/llm.py:144-160`
- Keep the current verifier/critic pattern for decision narration; it is one of the stronger LLM safety patterns in the repo. `briarwood/agent/composer.py:332-466`

### 2.4 Error Handling, Retries, and Budget Controls

Strengths:

- Provider budget caps are explicit and per-provider. `briarwood/cost_guard.py:64-141`
- `BudgetExceeded` propagates through LLM clients so composer can distinguish cost exhaustion from empty model output. `briarwood/agent/llm.py:93-103`, `briarwood/agent/llm.py:138-143`, `tests/agent/test_llm.py:100-113`
- Narrative composer has one strict regen retry and an optional critic pass. `briarwood/agent/composer.py:377-466`

Weaknesses:

- Most structured LLM failures return `None` with a warning and no retry. `briarwood/agent/llm.py:162-188`, `briarwood/local_intelligence/adapters.py:181-192`
- `handle_decision()` silently skips town summary, comps preview, value thesis, and scenario enrichment on exceptions. `briarwood/agent/dispatch.py:1381-1429`
- `_load_or_create_session()` silently resets a broken session file. `api/pipeline_adapter.py:138-145`
- Bridge exceptions are swallowed into a non-firing record. `briarwood/interactions/registry.py:53-63`

Flagged behaviors:

- **Silent partial-response rendering without warning:** yes, in decision enrichment. `briarwood/agent/dispatch.py:1381-1429`
- **Silent fallback to empty structured output:** yes, several LLM structured calls. `briarwood/agent/llm.py:162-188`, `briarwood/local_intelligence/adapters.py:181-192`
- **Default verdict fallback:** no direct hardcoded default verdict in the routed deterministic synth, which is a strength. `briarwood/synthesis/structured.py:153-227`

### 2.5 Data Lineage and Integrity

Strengths:

- `build_property_summary()` strips raw listing text before synthesis. `briarwood/orchestrator.py:64-113`, `tests/test_orchestrator.py:22-39`, `tests/test_orchestrator.py:286-347`
- `PropertyView` and `compute_value_position()` explicitly separate listing ask from all-in basis, and both files document the prior mismatch. `briarwood/agent/property_view.py:1-16`, `briarwood/agent/property_view.py:88-99`, `briarwood/synthesis/structured.py:237-248`
- `scenario_table` fixes spread units explicitly. `api/events.py:125-139`

Risks:

- `value_position.premium_discount_pct` is still an alias of `basis_premium_pct`, even though its name can be read as ask-vs-fair. `briarwood/synthesis/structured.py:244-268`
- The CMA surface can show live Zillow comps while claiming to show comps that fed fair value. `api/events.py:184-186`, `briarwood/agent/tools.py:1802-1848`
- Cache keys omit material property facts and can therefore serve stale data when the same property id is re-underwritten after facts change. `briarwood/orchestrator.py:116-137`, `briarwood/orchestrator.py:448-455`

### 2.6 State, Caching, and Concurrency

State locations:

- Process-global routing/module/synthesis caches in `orchestrator.py`. `briarwood/orchestrator.py:29-33`
- Per-conversation session JSON in `data/agent_sessions/<session_id>.json`. `briarwood/agent/session.py:15-24`, `briarwood/agent/session.py:86-124`

Caching risks:

- `_SYNTHESIS_OUTPUT_CACHE` and `_MODULE_RESULTS_CACHE` are keyed by `property_id` plus a narrow assumption payload, not the full normalized property facts. `briarwood/orchestrator.py:116-137`, `briarwood/orchestrator.py:448-455`
- Those caches are process-global mutable dicts with no lock, TTL, or invalidation strategy. `briarwood/orchestrator.py:29-33`
- Scoped module outputs are also stored in a process-global dict. `briarwood/orchestrator.py:32`, `briarwood/orchestrator.py:478-483`

**Inference:** two analyses of the same property id with changed structural facts but identical assumptions can reuse stale module/synthesis output. The cache key construction omits `beds`, `baths`, `sqft`, `taxes`, and other facts even though those feed valuation and carry models. `briarwood/orchestrator.py:116-137`, `briarwood/orchestrator.py:64-103`

This is a correctness risk, not just a performance concern.

### 2.7 API and Streaming Audit

- FastAPI defines typed request models for chat and conversation CRUD. `api/main.py:60-94`
- `/api/chat` is the primary streaming endpoint and returns `text/event-stream`. `api/main.py:230-366`
- Event types are centralized in `api/events.py` and mirrored in `web/src/lib/chat/events.ts`. `api/events.py:12-38`, `web/src/lib/chat/events.ts:113-339`
- There is no version field on the SSE protocol. Contract compatibility relies on comments and tests. `api/events.py:1-38`, `tests/test_pipeline_adapter_contracts.py:32-220`

Contract consistency:

- Good: `_DecisionView` validates verdict payload reads. `api/pipeline_adapter.py:548-639`
- Good: dedicated contract tests pin stream ordering and event shapes. `tests/test_pipeline_adapter_contracts.py:33-120`
- Weak: `tool_call` / `tool_result` are emitted in protocol constants but ignored by the frontend. `api/events.py:13-18`, `web/src/lib/chat/use-chat.ts:346-349`

### 2.8 Frontend Contract Fidelity

- The frontend faithfully stores most structured events, but it discards most `verifier_report` data and keeps only `critic`. `web/src/lib/chat/use-chat.ts:350-359`
- The backend verdict payload includes `trust_summary`, `why_this_stance`, `what_changes_my_view`, `contradiction_count`, and `blocked_thesis_warnings`; the TS `VerdictEvent` type omits those fields, and `VerdictCard` does not render them. `api/pipeline_adapter.py:617-639`, `web/src/lib/chat/events.ts:113-131`, `web/src/components/chat/verdict-card.tsx:37-133`
- `messages.tsx` renders verdict first and prose immediately after, so meaning can diverge even when the stream itself is correct. `web/src/components/chat/messages.tsx:128-140`

### 2.9 Tests and Observability

Test coverage is strongest around the routed core:

- planner/executor/cache behavior: `tests/test_execution_v2.py:14-284`
- orchestrator contracts: `tests/test_orchestrator.py:22-435`
- structured synthesis: `tests/synthesis/test_structured_synthesizer.py:60-175`
- SSE adapter contracts: `tests/test_pipeline_adapter_contracts.py:32-220`
- LLM client budget/schema handling: `tests/agent/test_llm.py:77-455`
- chat API stream basics: `tests/test_chat_api.py:63-102`

Observability is mixed:

- Runtime warnings exist across router, composer, local-intelligence collectors, and session persistence, but there is no general runtime metrics/tracing layer for per-agent latency or failure rates. `briarwood/router.py:81-91`, `briarwood/agent/composer.py:358-465`, `api/pipeline_adapter.py:138-145`
- Offline feedback/eval capture exists: routed analyses append JSONL captures with `execution_mode`, `contribution_map`, and `model_confidences`; separate feedback/eval harnesses compute drift and rejection metrics. `briarwood/runner_routed.py:511-533`, `briarwood/intelligence_capture.py:26-79`, `briarwood/eval/harness.py:1-225`, `briarwood/feedback/analyzer.py:21-193`

Direct answers:

- Can the team tell which agent is slowest? **No runtime evidence found.**
- Can the team tell which agent fails most? **Not from runtime metrics; only scattered warning logs.**
- Can the team detect verdict drift? **Partially offline** via capture/eval tooling, not in the live request path. `briarwood/eval/harness.py:163-225`
- Can the team detect schema breakage quickly? **Partially yes** for some surfaces because of Pydantic and stream contract tests, but not universally. `api/pipeline_adapter.py:548-639`, `tests/test_pipeline_adapter_contracts.py:798-829`

### 2.10 Dependencies and Technical Debt

Real architectural debt:

- Current docs say `resale_scenario`, `rental_option`, `renovation_impact`, `arv_model`, and `margin_sensitivity` are unsupported and should trigger fallback, but the actual registry wires concrete runners for all of them. `docs/scoped_execution_support.md:28-37`, `docs/scoped_execution_support.md:59-69`, `briarwood/execution/registry.py:87-181`
- Multiple live decision architectures coexist: routed synthesis, legacy `decision_engine`, and `briarwood/pipeline/*`. `briarwood/synthesis/structured.py:63-115`, `briarwood/decision_engine.py:29-96`, `briarwood/pipeline/runner.py:31-78`
- Many scoped modules are still wrappers around legacy modules, which is explicit debt rather than hidden debt. `docs/scoped_execution_support.md:70-85`, `briarwood/modules/valuation.py:16-23`, `briarwood/modules/rental_option_scoped.py:17-24`, `briarwood/modules/renovation_impact_scoped.py:12-16`

Harmless clutter:

- Older pipeline architecture and chart/session helpers are still tested and therefore not dead, but they are secondary to the routed/chat surface. `briarwood/pipeline/runner.py:1-78`, `tests/test_pipeline_e2e.py:22-125`

Active correctness risk:

- CMA provenance mismatch
- split verdict lineage
- stale cache keys

## Phase 3 — Cross-Cutting Findings

### 3.1 Severity Summary

- **P0:** 3
- **P1:** 6
- **P2:** 3

### 3.2 Findings Table

| ID | Severity | Title | What is happening | Why it matters | Evidence | Suggested fix direction | Rough effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F1 | **P0** | Multiple Verdict Paths | Routed chat/API uses deterministic `build_unified_output()`, while Dash/reports use `build_decision(report)` and the old pipeline keeps a third decision surface. | Briarwood does not have one trustworthy verdict lineage. | `briarwood/synthesis/structured.py:63-115`; `briarwood/decision_engine.py:29-96`; `briarwood/dash_app/quick_decision.py:35-55`; `briarwood/pipeline/runner.py:31-78`; `api/pipeline_adapter.py:570-583` | Choose one canonical verdict source and make other surfaces project from it. | L |
| F2 | **P0** | CMA Provenance Mismatch | The CMA event says it shows comps that fed fair value, but `get_cma()` prefers live Zillow market comps and does not read the actual valuation comp set. | Users can be misled about why Briarwood thinks a property is cheap or expensive. | `api/events.py:184-186`; `briarwood/agent/tools.py:1802-1848`; `briarwood/agent/tools.py:1892-1963` | Split “market support comps” from “valuation comps” into separate explicit contracts. | M |
| F3 | **P0** | Stale Routed Cache Key | Global synthesis/module caches are keyed too coarsely and omit material property facts. | Changed facts can silently reuse stale decisions. | `briarwood/orchestrator.py:29-33`; `briarwood/orchestrator.py:116-137`; `briarwood/orchestrator.py:448-455` | Re-key caches off normalized property facts or add invalidation/versioning. | M |
| F4 | **P1** | No Portfolio-Aware Allocation Logic | Routed execution carries no portfolio state, and `opportunity_cost` is passive-benchmark-only. | The product promise is capital allocation, but the implementation is property-isolation plus passive benchmark comparison. | `briarwood/execution/context.py:20-31`; `briarwood/modules/opportunity_cost.py:13-25`; `briarwood/dash_app/components.py:5928-5988` | Add portfolio/constraint inputs and a real opportunity-set comparison layer. | XL |
| F5 | **P1** | Hidden Upside Is Not First-Class Routed Logic | `HIDDEN_UPSIDE` exists in the core question enum but is not mapped to module hints or default intent coverage. | Briarwood cannot reliably answer “where is the hidden upside?” as its own routed question. | `briarwood/routing_schema.py:28-38`; `briarwood/routing_schema.py:114-140`; `briarwood/routing_schema.py:227-262` | Add dedicated question-focus routing and a surfaced optionality contract. | M |
| F6 | **P1** | Summary Prose Is Only Partially Coupled To Deterministic Verdict | The LLM summary is grounded to a subset of the routed view, but omits several decisive reasoning/trust fields. | Top-line text can remain numerically correct while under-explaining why the call is fragile. | `briarwood/agent/dispatch.py:1576-1603`; `briarwood/synthesis/structured.py:59-86`; `briarwood/agent/composer.py:372-466` | Generate prose from the full verdict object or expose its omitted fields in the summary input. | M |
| F7 | **P1** | Silent Partial Degradation In Decision Enrichment | Town summary, CMA, comps preview, value thesis, and scenarios are swallowed on exception. | Users can get a thinner answer without warning. | `briarwood/agent/dispatch.py:1381-1429` | Surface partial-data warnings in the response contract. | S |
| F8 | **P1** | Docs Contradict Scoped Registry Reality | Current docs say several modules are unsupported; registry wires concrete runners for them. | The team cannot trust the docs to reason about fallback behavior. | `docs/scoped_execution_support.md:28-37`; `docs/scoped_execution_support.md:59-69`; `briarwood/execution/registry.py:87-181` | Update current docs from the registry or generate docs from code. | S |
| F9 | **P1** | Two Routers Govern One User Flow | Chat tier routing (`briarwood/agent/router.py`) and analysis routing (`briarwood/router.py`) are separate systems. | Intent drift between “answer type” and “analysis modules” remains a structural risk. | `briarwood/agent/router.py:231-320`; `briarwood/router.py:525-586`; `api/main.py:287-336` | Define one canonical intent hierarchy or explicit translation contract between them. | M |
| F10 | **P2** | Frontend Drops Part Of Backend Meaning | Verdict UI ignores several backend verdict fields; verifier report is mostly discarded. | Explainability is weakened even when the backend produced the right information. | `api/pipeline_adapter.py:617-639`; `web/src/lib/chat/events.ts:113-131`; `web/src/components/chat/verdict-card.tsx:37-133`; `web/src/lib/chat/use-chat.ts:350-359` | Expand TS/event types and render the extra trust/explanation fields intentionally. | S |
| F11 | **P2** | Parallel Pipeline Architecture Still Lives Beside Routed Core | `briarwood/pipeline/*` still defines its own unified/decision stack and runner. | Increases maintenance load and concept duplication. | `briarwood/pipeline/runner.py:31-78`; `briarwood/pipeline/unified.py:29-144`; `briarwood/pipeline/decision.py:16-41` | Mark it deprecated, carve out its remaining use cases, or remove after migration. | M |
| F12 | **P2** | Router Classification Default Model Is Over-Tiered | Structured router classification defaults to `gpt-5` on OpenAI. | Unnecessary latency/cost for a tiny schema task. | `briarwood/agent/llm.py:144-160`; `briarwood/agent/router.py:245-263` | Down-tier the default structured router model. | S |

### 3.3 Top 10 Priorities

1. Unify verdict generation behind one canonical routed verdict path. Severity: **P0**. Owner: Routing/Platform. Effort: **L**.
2. Fix CMA/comp provenance so user-facing comp tables accurately identify valuation evidence versus market-support comps. Severity: **P0**. Owner: Chat/API + Valuation. Effort: **M**.
3. Rebuild routed cache keys and invalidation so changed property facts cannot silently reuse stale results. Severity: **P0**. Owner: Execution/Platform. Effort: **M**.
4. Add a real portfolio/opportunity-set input contract to the routed stack. Severity: **P1**. Owner: Product + Routing/Execution. Effort: **XL**.
5. Make hidden upside/optionality a first-class routed question with surfaced outputs. Severity: **P1**. Owner: Routing + Modules. Effort: **M**.
6. Tie top-line decision prose directly to the full deterministic verdict object. Severity: **P1**. Owner: Chat/API. Effort: **M**.
7. Stop silently swallowing decision enrichments; emit explicit partial-data warnings. Severity: **P1**. Owner: Chat/API. Effort: **S**.
8. Reconcile `docs/scoped_execution_support.md` with the actual module registry. Severity: **P1**. Owner: Platform/Docs. Effort: **S**.
9. Define a clear contract between chat-tier routing and analysis routing. Severity: **P1**. Owner: Platform. Effort: **M**.
10. Expand frontend rendering of trust/verdict/verifier fields so explanation survives to the user. Severity: **P2**. Owner: Frontend. Effort: **S**.

### 3.4 Architectural Patterns

- **Multiple verdict paths:** routed synth, legacy decision engine, and older pipeline decision adapters all still exist. `briarwood/synthesis/structured.py:63-115`, `briarwood/decision_engine.py:29-96`, `briarwood/pipeline/decision.py:16-41`
- **Strong contract enforcement in the routed core:** `ParserOutput`, `ModulePayload`, `ExecutionContext`, `UnifiedIntelligenceOutput`, `_DecisionView`. `briarwood/routing_schema.py:266-388`, `briarwood/execution/context.py:8-31`, `api/pipeline_adapter.py:548-639`
- **Reasoning not always tightly coupled to rendering:** deterministic verdict fields are richer than what the main verdict UI renders. `briarwood/synthesis/structured.py:88-115`, `web/src/components/chat/verdict-card.tsx:37-133`
- **Prompt-layer synthesis is bounded, not calculative:** LLMs narrate and classify, but verdict math remains deterministic in Python. `briarwood/synthesis/structured.py:34-115`, `briarwood/agent/dispatch.py:1576-1613`
- **Legacy wrappers are explicit:** many scoped modules still declare which legacy modules they wrap. `briarwood/modules/valuation.py:16-23`, `briarwood/modules/rental_option_scoped.py:17-24`, `briarwood/modules/renovation_impact_scoped.py:12-16`
- **Hidden fallback logic remains common:** chat enrichments and session reloads frequently fail open. `briarwood/agent/dispatch.py:1381-1429`, `api/pipeline_adapter.py:138-145`

### 3.5 What Is Working Well

- The routed deterministic synthesis path is the strongest implementation in the workspace. It gives Briarwood a reproducible, inspectable verdict path with trust gating and bridge-based contradiction handling. `briarwood/synthesis/structured.py:34-115`, `briarwood/interactions/conflict_detector.py:22-94`, `tests/synthesis/test_structured_synthesizer.py:60-175`
- The scoped execution boundary is clean and testable. `ExecutionContext` is explicit, the planner resolves dependencies, the executor caches module outputs by relevant inputs, and tests pin rerun behavior. `briarwood/execution/context.py:8-31`, `briarwood/execution/planner.py:20-131`, `briarwood/execution/executor.py:289-364`, `tests/test_execution_v2.py:49-228`
- The SSE adapter has meaningful contract tests, which is uncommon and valuable. `tests/test_pipeline_adapter_contracts.py:32-220`
- The narrative LLM safety stack is thoughtful: grounding markers, verifier, strict regen, budget caps, and optional critic. `api/prompts/_base.md:1-46`, `api/guardrails.py:146-303`, `briarwood/agent/composer.py:332-466`, `briarwood/cost_guard.py:64-141`
- `PropertyView` is a concrete fix for a real semantic bug around ask price versus all-in basis; this is the right kind of contract hardening. `briarwood/agent/property_view.py:1-16`, `briarwood/agent/property_view.py:88-99`

## Final Assessment

Briarwood can be trusted today for one thing more than anything else: a deterministic, property-level routed underwriting read where the verdict comes from typed module outputs and explicit trust gating. Trust is strongest in the scoped routed core, the bridge layer, and the Phase 5 deterministic synthesis path. `briarwood/execution/context.py:8-31`, `briarwood/interactions/registry.py:42-65`, `briarwood/synthesis/structured.py:34-115`

Briarwood cannot yet be fully trusted to support a capital allocation decision across the whole workspace. Trust is weakest where multiple verdict systems coexist, where user-facing comp provenance overstates what actually fed fair value, and where the routed stack still has no portfolio-aware input contract. `briarwood/decision_engine.py:29-96`, `api/events.py:184-186`, `briarwood/agent/tools.py:1802-1848`, `briarwood/execution/context.py:20-31`

What would make it materially more trustworthy is not “more AI.” It is architectural consolidation: one verdict path, one comp-provenance story, cache keys that cannot silently serve stale answers, and explicit portfolio/opportunity-set inputs so Briarwood’s top-line recommendation really answers the capital-allocation question it claims to answer. `docs/current_docs_index.md:20-27`, `briarwood/orchestrator.py:116-137`, `briarwood/modules/opportunity_cost.py:13-25`

## Stop Gate

Read-only audit complete. No code changes made. Awaiting review.

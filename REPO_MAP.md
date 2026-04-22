# Briarwood Repo Map

Date: 2026-04-19
Workspace: `briarwood`

> **Historical snapshot.** References to `briarwood/dash_app/`, `briarwood/reports/`,
> `briarwood/projections/`, `briarwood/decision_engine.py`, `briarwood/runner.py`,
> `briarwood/runner_legacy.py`, `briarwood/scorecard.py`, `briarwood/deal_curve.py`,
> `run_dash.py`, and `app.py` are retained for audit context — those modules were
> deleted during the 2026-04-22 verdict-path consolidation. The canonical verdict now
> flows through `briarwood.synthesis.structured` → `briarwood.runner_routed` →
> FastAPI (`api/`) → Next.js (`web/`).

## A. Directory Map

Tree is limited to two levels deep and excludes `.git`, `node_modules`, `.venv`, `.next`, caches, coverage, and other build artifacts.

```text
.
├── AGENTS.md
├── AUDIT_REPORT.md
├── BRIARWOOD-AUDIT.md
├── Makefile
├── README.md
├── UX-ASSESSMENT.md
├── analysis/
│   ├── 00_executive_summary.md
│   ├── 01_codebase_inventory.md
│   ├── 02_technical_debt.md
│   ├── 03_performance.md
│   ├── 04_ui_gap_analysis.md
│   ├── 05_migration_plan.md
│   ├── comp_confidence_audit.md
│   ├── comp_integrator_audit.md
│   ├── comp_selector_audit.md
│   ├── feature_adjustment_audit.md
│   ├── micro_location_audit.md
│   ├── tier1_cleanup_log.md
│   ├── town_transfer_audit.md
│   └── ui_refactor_log.md
├── api/
│   ├── __init__.py
│   ├── events.py
│   ├── guardrails.py
│   ├── main.py
│   ├── mock_listings.py
│   ├── pipeline_adapter.py
│   ├── prompts/
│   └── store.py
├── app.py
├── audit_scripts/
│   ├── 01_portfolio_summary.py
│   ├── 02_property_deep_dive.py
│   ├── 03_correlation_and_modules.py
│   └── pickup_comp_drop_folder.py
├── briarwood/
│   ├── agent/
│   ├── agents/
│   ├── charts/
│   ├── data_quality/
│   ├── data_sources/
│   ├── decision_model/
│   ├── eval/
│   ├── execution/
│   ├── feedback/
│   ├── inputs/
│   ├── interactions/
│   ├── listing_intake/
│   ├── local_intelligence/
│   ├── modules/
│   ├── pipeline/
│   ├── reports/
│   ├── synthesis/
│   ├── orchestrator.py
│   ├── router.py
│   ├── routing_schema.py
│   ├── decision_engine.py
│   ├── engine.py
│   ├── runner.py
│   ├── runner_legacy.py
│   └── runner_routed.py
├── data/
│   ├── agent_artifacts/
│   ├── agent_feedback/
│   ├── agent_sessions/
│   ├── comps/
│   ├── eval/
│   ├── learning/
│   ├── listing_index/
│   ├── local_intelligence/
│   ├── manual_entries/
│   ├── market_history/
│   ├── model_quality/
│   ├── public_records/
│   ├── sample_property.json
│   ├── saved_properties/
│   ├── town_county/
│   └── web/
├── docs/
│   ├── backtest_report.md
│   ├── chat_chart_surface_matrix.md
│   ├── chat_workflow_audit_matrix.md
│   ├── current_docs_index.md
│   ├── decision_report_strategy.md
│   ├── investment_module_spec.md
│   ├── local_intelligence_signal_classification.md
│   ├── location_intelligence_v1.md
│   ├── model_audits/
│   ├── model_inventory.md
│   ├── model_system_audit.md
│   ├── operational_model_sweep.md
│   ├── project_map.md
│   ├── scoped_execution_support.md
│   └── town_county_source_matrix.md
├── outputs/
│   └── demo/
├── requirements.txt
├── run_dash.py
├── scripts/
│   ├── audit_comp_store.py
│   ├── backfill_comp_store.py
│   ├── backfill_feedback_rows.py
│   ├── demo_eight_layers.py
│   ├── dev_chat.py
│   ├── enrich_comps.py
│   ├── fetch_attom_sales.py
│   ├── fetch_sr1a_sales.py
│   ├── ingest_excel_comps.py
│   ├── llm_ab_demo.py
│   ├── property_intel_audit_report.py
│   ├── refresh_minutes.py
│   ├── review_untracked.py
│   └── run_town_pulse.py
├── tests/
│   ├── agent/
│   ├── agents/
│   ├── fixtures/
│   ├── interactions/
│   ├── listing_intake/
│   ├── local_intelligence/
│   ├── modules/
│   ├── pipeline/
│   ├── reports/
│   ├── synthesis/
│   ├── test_execution_v2.py
│   ├── test_orchestrator.py
│   ├── test_quick_decision.py
│   └── test_runner_routed.py
├── unified_intelligence.md
└── web/
    ├── AGENTS.md
    ├── README.md
    ├── next.config.ts
    ├── package.json
    ├── pnpm-lock.yaml
    ├── public/
    ├── src/
    └── tsconfig.json
```

## B. Major Directory Summary

| Directory | Purpose | Key files | Layer |
| --- | --- | --- | --- |
| `api/` | FastAPI bridge for chat, SSE streaming, conversation storage, street-view lookup, and prompt-driven pipeline dispatch. | `api/main.py`, `api/pipeline_adapter.py`, `api/events.py`, `api/prompts/*` | Surface Layer + Cross-cutting / Infra |
| `briarwood/` | Core Python product code: routing, scoped execution, deterministic modules, synthesis, legacy runner compatibility, and data integrations. | `briarwood/orchestrator.py`, `briarwood/routing_schema.py`, `briarwood/router.py`, `briarwood/decision_engine.py`, `briarwood/runner_routed.py` | Reasoning Layer + Data Layer |
| `briarwood/agent/` | Chat-oriented agent stack: routing, prompt composition, rendering, provider wrappers, and session state for the newer conversational pipeline. | `briarwood/agent/router.py`, `briarwood/agent/composer.py`, `briarwood/agent/llm.py`, `briarwood/agent/rendering.py` | Surface Layer + Reasoning Layer |
| `briarwood/agents/` | Domain-specific analysis agents and supporting schemas for comps, current value, income, rent context, market history, scarcity, school signal, and town/county context. | `briarwood/agents/*/agent.py`, `briarwood/agents/*/schemas.py` | Reasoning Layer + Data Layer |
| `briarwood/modules/` | Module wrappers and scoped execution units that feed routed analysis and decision synthesis. | `briarwood/modules/*.py`, `briarwood/execution/planner.py`, `briarwood/execution/executor.py` | Reasoning Layer |
| `briarwood/local_intelligence/` | Structured local-intelligence extraction, normalization, storage, prompt assembly, and reconciliation. | `briarwood/local_intelligence/service.py`, `adapters.py`, `models.py`, `prompts.py` | Data Layer + Reasoning Layer |
| `web/` | Next.js 16 chat frontend and route handlers that proxy to the FastAPI backend and render card/table/chart surfaces. | `web/src/app/page.tsx`, `web/src/app/api/*/route.ts`, `web/src/lib/chat/use-chat.ts`, `web/src/components/chat/*` | Surface Layer |
| `data/` | Local persisted inputs, artifacts, sessions, saved properties, comps, local-intelligence outputs, and sample property fixtures. | `data/sample_property.json`, `data/agent_artifacts/`, `data/saved_properties/` | Data Layer |
| `tests/` | Unit-heavy regression surface across routing, execution, modules, chat API, synthesis, and domain agents. | `tests/test_execution_v2.py`, `tests/test_orchestrator.py`, `tests/agent/test_llm.py`, `tests/test_chat_api.py` | Cross-cutting / Infra |
| `docs/` | Current and historical documentation; current source-of-truth points to routing schema, orchestrator, scoped execution support, and unified intelligence. | `docs/current_docs_index.md`, `docs/scoped_execution_support.md`, `unified_intelligence.md` | Cross-cutting / Infra |
| `scripts/` and `audit_scripts/` | Operational helpers, ingestion utilities, demos, refresh jobs, and prior audit/report generation scripts. | `scripts/dev_chat.py`, `scripts/property_intel_audit_report.py`, `audit_scripts/*.py` | Cross-cutting / Infra |

Reference: current docs index names the active product flow as `landing intake -> routed analysis -> unified result`, with the orchestrator and routing schema as current implementation authority ([docs/current_docs_index.md](docs/current_docs_index.md):5-27).

## C. Inventory Counts

Counts below are from direct file-system inspection of the current workspace.

| Inventory item | Count | Notes |
| --- | --- | --- |
| Agent directories | 10 | `briarwood/agents/*` top-level directories |
| Primary agent implementations | 7 | `agent.py` files under `briarwood/agents/` |
| Module files | 43 | `briarwood/modules/*.py` excluding `__init__.py` |
| Prompt files | 13 | Markdown prompt files under `api/prompts/` |
| LLM provider invocation sites | 5 | Four direct calls in [`briarwood/agent/llm.py`](briarwood/agent/llm.py) and one adapter call in [`briarwood/local_intelligence/adapters.py`](briarwood/local_intelligence/adapters.py) |
| Chart surfaces / specs | 6 | 6 typed chat chart specs in `web/src/lib/chat/events.ts` (Dash-era renderers removed in the 2026-04-22 consolidation) |
| Table components / renderers | 3 | 3 web chat table components (Dash table renderers removed in the 2026-04-22 consolidation) |
| FastAPI endpoints | 8 | Conversation CRUD, chat stream, health, street-view in [`api/main.py`](api/main.py) |
| Next.js route handlers | 7 | `web/src/app/api/*/route.ts` exports |
| Typed-contract files | 58 | 26 Python files with `BaseModel` plus 32 TypeScript files with `type`/`interface` declarations |
| Streaming / SSE handlers | 3 | FastAPI streaming endpoint, Next route proxy, and browser-side event parser |
| Explicit caching layers | 7+ | Orchestrator caches, executor cache support, prompt cache, file-backed view-model cache, `lru_cache` helpers, and data-source caches |
| Tests | 125 | 55 root tests, 19 `tests/agent`, 28 `tests/agents`, 13 `tests/modules`, 10 grouped directory tests elsewhere |

Key evidence for notable counts:

- Scoped-first orchestrator caches routing decisions, module results, synthesis outputs, and scoped module outputs in module-level dictionaries ([briarwood/orchestrator.py](briarwood/orchestrator.py):29-33).
- FastAPI exposes eight handlers including one `StreamingResponse` SSE endpoint ([api/main.py](api/main.py):98-125, [api/main.py](api/main.py):230-361, [api/main.py](api/main.py):369-374).
- The frontend defines typed chart event/spec variants for scenario fan, CMA positioning, risk bar, rent burn, rent ramp, and value opportunity ([web/src/lib/chat/events.ts](web/src/lib/chat/events.ts):13-112).

## D. Dependency Snapshot

### Backend

| Package | Version | Declared in |
| --- | --- | --- |
| `pydantic` | `>=2,<3` | `requirements.txt` |
| `openai` | `>=1.0,<2` | `requirements.txt` |
| `anthropic` | `>=0.40,<1` | `requirements.txt` |
| `dash` | `>=2.18,<3` | `requirements.txt` |
| `plotly` | `>=5.24,<6` | `requirements.txt` |
| `weasyprint` | `>=62,<69` | `requirements.txt` |
| `pypdf` | `>=4,<6` | `requirements.txt` |
| `fastapi` | `>=0.115,<1` | `requirements.txt` |
| `uvicorn[standard]` | `>=0.30,<1` | `requirements.txt` |

### Frontend

| Package | Version | Declared in |
| --- | --- | --- |
| `next` | `16.2.4` | `web/package.json` |
| `react` | `19.2.4` | `web/package.json` |
| `react-dom` | `19.2.4` | `web/package.json` |
| `mapbox-gl` | `^3.22.0` | `web/package.json` |
| `react-map-gl` | `^8.1.1` | `web/package.json` |
| `lucide-react` | `^1.8.0` | `web/package.json` |
| `class-variance-authority` | `^0.7.1` | `web/package.json` |
| `clsx` | `^2.1.1` | `web/package.json` |
| `tailwind-merge` | `^3.5.0` | `web/package.json` |
| `typescript` | `^5` | `web/package.json` |
| `eslint` | `^9` | `web/package.json` |
| `eslint-config-next` | `16.2.4` | `web/package.json` |
| `tailwindcss` | `^4` | `web/package.json` |
| `@tailwindcss/postcss` | `^4` | `web/package.json` |
| `@types/node` | `^20` | `web/package.json` |
| `@types/react` | `^19` | `web/package.json` |
| `@types/react-dom` | `^19` | `web/package.json` |

## E. Initial Architecture Read

### Main request flow

The current authoritative flow is declared as `landing intake -> routed analysis -> unified result` in the current docs index, with routing contracts in `briarwood/routing_schema.py` and scoped-first control flow in `briarwood/orchestrator.py` ([docs/current_docs_index.md](docs/current_docs_index.md):5-27). The scoped execution support doc makes the intended routed path explicit as `router -> execution planner -> scoped executor -> synthesis`, with legacy fallback when unsupported modules are required ([docs/scoped_execution_support.md](docs/scoped_execution_support.md):5-14).

### Likely orchestration boundary

`briarwood/orchestrator.py` is the clearest orchestration hub. It imports routing, normalization, planner, executor, macro-context resolution, and interaction bridges, and it maintains caches for routing decisions, module results, synthesis outputs, and scoped module outputs ([briarwood/orchestrator.py](briarwood/orchestrator.py):10-18, [briarwood/orchestrator.py](briarwood/orchestrator.py):29-33).

### Likely synthesis boundary

`unified_intelligence.md` defines Unified Intelligence as a bounded synthesis layer that sits after selected Briarwood-native modules and returns a structured decision output with recommendation, decision, best path, key drivers, key risks, confidence, and next questions ([unified_intelligence.md](unified_intelligence.md):5-8, [unified_intelligence.md](unified_intelligence.md):13-19, [unified_intelligence.md](unified_intelligence.md):133-147).

### Likely UI rendering boundaries

The single active surface layer is the FastAPI + Next.js chat: FastAPI owns the SSE wire format and serves artifact URLs, while `web/` renders the conversational UI and proxies API calls ([api/main.py](api/main.py):1-8, [api/main.py](api/main.py):52-57, [web/src/app/page.tsx](web/src/app/page.tsx):1-15, [web/src/lib/api.ts](web/src/lib/api.ts):1-49). The Dash compatibility UI (`run_dash.py`, `briarwood/dash_app/`) was removed in the 2026-04-22 consolidation.

### Contracts that look strongest from layout alone

Routing and execution contracts look strongest: the current docs point directly at `briarwood/routing_schema.py`, `briarwood/orchestrator.py`, and scoped execution support docs as the active source of truth ([docs/current_docs_index.md](docs/current_docs_index.md):5-18). The repo also has a dedicated execution package plus targeted routing/orchestration tests such as `tests/test_execution_v2.py`, `tests/test_orchestrator.py`, `tests/test_router.py`, and `tests/test_routing_schema.py`.

### Contracts that look weakest from layout alone

The workspace still carries legacy compatibility paths: chat-specific `briarwood/agent/*` orchestration, routed/scoped core orchestration, and legacy runner files (`engine.py`, `runner.py`, `runner_legacy.py`) coexist. Inference: this increases the risk of duplicated verdict composition and uneven contract enforcement until the audit verifies the actual call graph. Supporting evidence: concurrent presence of the legacy/full-engine files and the scoped-first orchestrator files in the same package root, plus the docs note that legacy dashboard-era structures are still compatibility surfaces ([docs/current_docs_index.md](docs/current_docs_index.md):22-27).

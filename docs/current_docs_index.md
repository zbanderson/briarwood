# Briarwood Current Docs Index

Use this file as the starting point for product and implementation work.

## Current Source Of Truth

- `AGENTS.md`
  Repo rules for routing, scoped execution, UI direction, and agent behavior
- `CODEX.md`, `CLAUDE.md`
  Startup contracts for Codex / Claude sessions. These define orientation,
  README discipline, handoff expectations, and source priority.
- `CURRENT_STATE.md`
  Short bootstrap context for fresh AI sessions and handoff continuity
- `DECISIONS.md`
  Append-only record of owner decisions, landed handoffs, guardrails, and
  cross-document closeout notes. Read the relevant dated entries before
  changing architecture or product behavior.
- `ROADMAP.md`
  Active sequence, strategic initiatives, tactical backlog, resolved index,
  and known drift. For planning, read this in full.
- `ARCHITECTURE_CURRENT.md`
  Current system map for layers, directories, LLM integrations,
  orchestration, persistence, and UI boundaries.
- `GAP_ANALYSIS.md`
  Current-state vs. six-layer target architecture, including which target
  gaps are already closed and which remain.
- `TOOL_REGISTRY.md`
  Registry of callable/tool-like surfaces, module ownership, and known
  quirks. Use this when changing tool/module entry points or manifests.
- `docs/scoped_execution_support.md`
  Current V2 scoped execution coverage and fallback status
- `docs/operational_model_sweep.md`
  Operational review entrypoint for routed/scoped model and data-source audits
- `docs/backend_model_surface_matrix.md`
  Current backend-model-to-chat-surface map for the canonical decision flow
- `unified_intelligence.md`
  Unified Intelligence behavior and output contract
- `SCOUT_HANDOFF_PLAN.md`
  Historical Phase 4b Scout plan. Complete as of 2026-04-28; still useful
  for Scout architecture, verification, and closeout context.
- `CMA_HANDOFF_PLAN.md`
  Historical Phase 4a CMA quality plan. Complete as of 2026-04-28; still
  useful for live comp, SearchApi, and rent-zestimate lineage.
- `PERSISTENCE_HANDOFF_PLAN.md`, `FEEDBACK_LOOP_HANDOFF_PLAN.md`,
  `DASHBOARD_HANDOFF_PLAN.md`
  Historical AI-Native Foundation Stage 1-3 plans. Complete as of
  2026-04-28; read when touching turn traces, feedback, admin dashboard,
  or LLM-call observability.
- `STAGE4_HANDOFF_PLAN.md`
  AI-Native Foundation Stage 4 plan for closing the model-accuracy loop
  with outcome ingestion, JSONL/alignment backfills, `model_alignment`,
  receiver hooks, and analyzer reporting. Implementation substrate landed
  2026-04-28; real outcome data still needs to be supplied and run through
  the backfills.
- `BROWSE_REBUILD_HANDOFF_PLAN.md`
  Phase 4c plan for rebuilding the BROWSE response into three stacked
  sections (`BrowseRead` / `BrowseScout` / `BrowseDeeperRead`) with
  newspaper-front-page hierarchy. APPROVED 2026-04-28; **Cycle 1 LANDED
  2026-04-28** (tier marker + section primitive + Section A fully
  filled; Sections B/C are Cycle 1 stubs). Cycle 2 ready to start. Folds
  the §3.4.7 chart-library evaluation as Cycle 5 and closes
  `PRESENTATION_HANDOFF_PLAN.md` Open Design Decision #7 at Cycle 4.
- `briarwood/routing_schema.py`
  Canonical routing and output contracts
- `briarwood/orchestrator.py`
  Current routed execution entrypoint and scoped-first control flow

## Current Product Direction

- Briarwood is now intelligence-first and decision-first.
- The primary product flow is:
  - landing intake
  - routed analysis
  - unified result
- Legacy dashboard-era UI structures are compatibility surfaces, not the target architecture.

## Historical / Archived Guidance

These files are useful for context, but they are not implementation authority:

- `AUDIT_REPORT.md`
- `BRIARWOOD-AUDIT.md`
- `UX-ASSESSMENT.md`
- `analysis/*.md`

Treat them as historical analysis unless a current doc explicitly points back to one of them.

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
- `CHART_MIGRATION_HANDOFF_PLAN.md`
  Historical Apache ECharts migration plan. ✅ RESOLVED 2026-04-30 —
  all three cycles landed in one session against the canonical Belmar
  fixture. All eight chart kinds now render through ECharts via a
  single `next/dynamic({ ssr: false })` boundary at
  `web/src/components/chat/chart-frame.tsx` →
  `web/src/components/chat/chart-echarts.tsx`. Eval sandbox at
  `web/src/components/chat/_eval/` + the `/eval/charts/` route tree
  deleted in Cycle 3; `recharts`, `@nivo/core`, `@nivo/scatterplot`
  removed from `web/package.json`. Drive-by §3.4.2 + §3.4.6
  renderer-side prong closed. Useful for future chart work as a
  template for cycle structure (substrate / bulk / cleanup) and for
  the lazy-import wiring pattern.
- `docs/CHART_LIBRARY_EVAL_2026-04-29.md`
  Phase 4c Cycle 5 chart-library eval memo. Compares the production
  native-SVG `cma_positioning` renderer against Recharts 3.8, Apache
  ECharts 6, and Nivo 0.99 on the same Belmar dataset. Bundle deltas
  (gzipped): native 0 KB / Nivo 70 KB / Recharts 84 KB / ECharts
  364 KB. Memo recommendation was stay native; owner picked Apache
  ECharts (override). Migration tracked in
  `CHART_MIGRATION_HANDOFF_PLAN.md`.
- `BROWSE_REBUILD_HANDOFF_PLAN.md`
  Historical Phase 4c BROWSE summary card rebuild plan. ✅ RESOLVED
  2026-04-29 — six cycles landed across 2026-04-28 → 2026-04-29.
  Three-section newspaper-hierarchy layout (`BrowseRead` /
  `BrowseScout` / `BrowseDeeperRead`) with eight Section C drilldowns
  over the `BrowseDrilldown` primitive ships on BROWSE turns; non-BROWSE
  tiers render the legacy card stack unchanged. Cycle 5 produced the
  chart-library eval memo at `docs/CHART_LIBRARY_EVAL_2026-04-29.md`;
  the actual chart-renderer migration is `CHART_MIGRATION_HANDOFF_PLAN.md`,
  filed as a fresh handoff (NOT part of Phase 4c per the 2026-04-28
  sequencing call). Closed `PRESENTATION_HANDOFF_PLAN.md` Open Design
  Decision #7 (deferred indefinitely).
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

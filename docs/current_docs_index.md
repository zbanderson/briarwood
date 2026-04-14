# Briarwood Current Docs Index

Use this file as the starting point for product and implementation work.

## Current Source Of Truth

- `AGENTS.md`
  Repo rules for routing, scoped execution, UI direction, and agent behavior
- `docs/scoped_execution_support.md`
  Current V2 scoped execution coverage and fallback status
- `unified_intelligence.md`
  Unified Intelligence behavior and output contract
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

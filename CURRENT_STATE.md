# Briarwood Current State

Last Updated: 2026-04-28

This file is the short bootstrap context for new AI coding sessions. It
does not replace `CODEX.md`, `AGENTS.md`, `DECISIONS.md`,
`ROADMAP.md`, or module READMEs. It points a fresh session at the
minimum project state needed to avoid drift.

---

## Session Startup

Before doing implementation work in this repository:

1. Read `CODEX.md`.
2. Read `AGENTS.md`.
3. Read `docs/current_docs_index.md`.
4. Read this file.
5. Read `DECISIONS.md` and `ROADMAP.md` in full.
6. Follow the README drift-check rules in `CODEX.md`.

Do not treat this file as implementation authority when it conflicts
with code, module READMEs, `DECISIONS.md`, or `ROADMAP.md`.

---

## Project Identity

Briarwood is a residential real estate decision-intelligence platform.
The product should answer "what should I do?" before exposing deeper
diagnostics, tables, or dashboard-style surfaces.

Current direction:

- decision-first user flows
- routed analysis
- scoped module execution before legacy fallback
- Unified Intelligence as synthesis, not numeric calculation
- deterministic Python modules for valuation, risk, rent, costs, and
  scenario logic
- LLM usage limited to intent parsing and structured synthesis

---

## Current Operating Model

The repo is being built through small AI-assisted handoffs. Every new
session should preserve continuity by working from the current docs,
making one logical change at a time, and leaving a clear trail for the
next developer.

Expected handoff rhythm:

1. Orient from the required docs.
2. Confirm the active task against `DECISIONS.md` and `ROADMAP.md`.
3. Read the README for every module being changed.
4. Make the smallest coherent change.
5. Run focused tests for touched behavior.
6. Update contract docs only when behavior or public contracts changed.
7. Update the PR / handoff note before stopping.

---

## Active Continuity Files

- `CODEX.md` — rules of engagement for AI sessions.
- `AGENTS.md` — product and architecture identity.
- `docs/current_docs_index.md` — current documentation entrypoint.
- `DECISIONS.md` — append-only architectural and product decisions.
- `ROADMAP.md` — actionable backlog items discovered during work.
- `CURRENT_STATE.md` — short bootstrap context for fresh sessions.
- `.github/PULL_REQUEST_TEMPLATE.md` — required PR / handoff structure.

---

## Current Known Themes

The latest documented work centers on:

- Phase 4b Scout closeout: shared `scout(...)` dispatcher, LLM Scout
  on BROWSE / DECISION / EDGE, `ScoutFinds` UI surface, deterministic
  fallback rails, and Scout yield telemetry
- AI-Native Foundation Stages 1-3: turn traces, LLM-call JSONL,
  feedback loop, and `/admin` read-side dashboard
- Phase 4a CMA closeout: live SOLD/ACTIVE comp support and
  SearchApi-backed `rent_zestimate` substrate
- AI-Native Stage 4 closeout (2026-04-28): substrate landed; Loop 1
  exercised against the owner-estimate outcome row at
  `data/outcomes/property_outcomes.jsonl`
  (`526-w-end-ave-avon-by-the-sea-nj`). The first run surfaced an
  intake bug — `facts.town` was `"Avon By The Sea Nj"` (state suffix
  glued onto town string), breaking the comp-store lookup. Town
  corrected on this property; re-run produced 3 honest alignment rows
  (`current_value` / `valuation` $1,311,200 at APE 5.33%,
  `comparable_sales` $1,484,741 at APE 7.20%, all confidences 0.51-0.59).
  Loop 1 closed AND surfaced its first defect (intake normalizer bug
  filed in ROADMAP §4). Public-record / ATTOM-automated outcome
  ingestion still a follow-up
- remaining post-Scout sequence work: Phase 4c BROWSE summary card
  rebuild (sequence step 6 — now unblocked)

See `DECISIONS.md` for owner decisions and `ROADMAP.md` for queued
fixes. Do not rely on this summary when exact details matter.

---

## Required End-Of-Session Handoff

Before ending a meaningful work session, add or update a handoff note
using this shape:

```md
## YYYY-MM-DD — Short Handoff Title

Goal:
Files changed:
Behavior changed:
Tests run:
Decisions made:
Drift found:
Follow-ups added:
Recommended next task:
```

If the session made a code or contract change, the handoff must state
what changed clearly enough that a new developer can continue without
reconstructing the whole session from git diff.

If no files changed, record that explicitly in the session response
instead of editing this file.

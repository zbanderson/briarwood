# Briarwood Current State

Last Updated: 2026-04-30 (May 2026 Launch Cycle 1 — Sunday Scaffold — landed end-to-end; api/web hosted at briarwood.fly.dev + briarwood-ai.vercel.app; ATTOM backfill partial at 1968/3085 due to 401 quota wall; active-listings refresh complete for all 8 towns; §3.8 sub-streams 1a/1b/1c posted as outcome notes)

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

## May 2026 Launch (active)

Owner-aligned 2026-04-30 via a structured grill-me session. **Cycle 1 (Sunday Scaffold) landed 2026-04-30**, four days ahead of the wall-clock deadline.

- **Live URLs:**
  - API: `https://briarwood.fly.dev` (Fly app `briarwood`, region `ewr`, `shared-cpu-1x`, 1 GB encrypted volume `briarwood_data` mounted at `/app/data` with daily snapshots).
  - Web: `https://briarwood-ai.vercel.app` (Vercel project `briarwood-ai`, root `web`, Next.js + pnpm, `maxDuration 300` on the SSE chat route).
  - No custom domain (locked decision); no auth at launch (Vercel/Cloudflare Access SSO comes before user demo).
- **Cycle 1 outcomes** (per [`ROADMAP.md`](ROADMAP.md) §3.8 + [`DECISIONS.md`](DECISIONS.md) 2026-04-30 entry "Launch Cycle 1 (Sunday Scaffold) landed"):
  - **1a Hosting** ✅. Three deploy-blocking bugs in the Stream 2 drafts caught in flight (volume-mask-seed-data, missing pandas/requests/python-dotenv in requirements.txt, 5 seed dirs excluded by `.dockerignore`); all fixed. Smoke tests pass: `/healthz`, SEARCH turn (8 listings + 6 map pins), BROWSE turn (194 SSE events through 8 modules with full three-section hierarchy + 4 charts).
  - **1b ATTOM backfill** ✅ partial. 922 ATTOM matches → 854 newly-eligible + 687 sqft fixes across 1,968 rows; 1,117 candidate rows blocked by ATTOM 401 daily-quota wall. Comp-store eligible pool effectively doubled (833 → ~1,687). Filed as §4 follow-up: "ATTOM backfill remaining 1,117 candidate rows".
  - **1c Active-listings refresh** ✅. 176 listings across all 8 towns (was 59); all 8 clear ≥10. SearchApi quota cost: 8 cache-hit calls.
- **Two personas, one product flow:** small investors derisking renovation/hold/flip decisions, AND realtors using auto-CMA. Same browse-and-drill flow for both at launch.
- **Headline UX is browse-first.** Per-property page uses the Phase 4c three-section newspaper hierarchy (`BrowseRead` + `BrowseScout` + `BrowseDeeperRead`).
- **Geo scope:** Monmouth coast (Belmar, Manasquan, Avon By The Sea, Spring Lake, Sea Girt, Bradley Beach, Asbury Park, Wall). Hard scope.
- **Trust posture:** ranges + caveats + Scout, AND meaningfully better accuracy. §3.7 Cycle 2A baseline median APE 28–32%; the launch-gate accuracy number gets decided empirically from the post-full-backfill backtest in Cycle 2 (after ATTOM quota recovers).
- **Sequence after Sunday — what's next:**
  1. ~~Sunday: Fly.io + Vercel scaffold; ATTOM backfill; active-listings refresh.~~ ✅ LANDED 2026-04-30.
  2. **Week 1 (now):** ATTOM backfill full re-run against the unprocessed 1,117 (after ATTOM quota recovers); re-run §3.7 Cycle 2A backtest against the densified comp store; Cycle 2B `comparable_sales` per-fixture audit; Layer 3 LLM synthesizer (`synthesize_with_llm` over full `UnifiedIntelligenceOutput` with numeric guardrails); renovation-options composer change rides on Layer 3.
  3. Week 2: Phase B (MissingInputManifest substrate — schema, SSE event, frontend affordance, persistence path).
  4. Demo gate: accuracy bar met (TBD from data) + Phase B + Layer 3 + renovation-options framing + Vercel/Cloudflare Access SSO with 10-email allowlist.
- **Launch initiative tracked under [ROADMAP §3.8](ROADMAP.md).**

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
- Phase 4c BROWSE summary card rebuild closed 2026-04-29 (sequence step
  6): all six cycles landed across 2026-04-28 → 2026-04-29 via
  `BROWSE_REBUILD_HANDOFF_PLAN.md`. The BROWSE response now renders as
  three stacked sections (`BrowseRead` masthead with stance pill +
  headline + masthead `market_trend` chart + flowed prose;
  `BrowseScout` peer section with the playful Scout treatment;
  `BrowseDeeperRead` with eight chevron-list drilldowns — Comps / Value
  thesis / Projection / Rent / Town context / Risk / Confidence & data
  / Recommended path) gated on `ChatMessage.answerType === "browse"`;
  non-BROWSE tiers render the existing card stack unchanged. Cycle 5
  produced the chart-library eval memo at
  `docs/CHART_LIBRARY_EVAL_2026-04-29.md`; owner picked Apache ECharts
  (override of the memo's "stay native" recommendation). The actual
  chart-renderer migration is filed as a fresh handoff under
  `CHART_MIGRATION_HANDOFF_PLAN.md` (ROADMAP §3.6) — **not** part of
  Phase 4c, per the 2026-04-28 sequencing call
- Chart-renderer migration to Apache ECharts closed 2026-04-30 (§3.6 ✅
  RESOLVED): all three cycles landed in one session. All eight production
  chart kinds (`scenario_fan`, `cma_positioning`, `value_opportunity`,
  `market_trend`, `risk_bar`, `rent_burn`, `rent_ramp`,
  `horizontal_bar_with_ranges`) now render through Apache ECharts via a
  single `next/dynamic({ ssr: false })` boundary at
  `web/src/components/chat/chart-frame.tsx` → `web/src/components/chat/chart-echarts.tsx`.
  ECharts engine (~366 KB gz) loads lazily; non-chart routes carry zero
  ECharts cost in first-load chunks. `web/package.json` no longer carries
  `recharts`, `@nivo/core`, `@nivo/scatterplot`; eval sandbox at
  `web/src/components/chat/_eval/` and `/eval/charts/` route tree
  deleted. Drive-by §3.4.2 (vertical-character y-axis label) and the
  renderer-side prong of §3.4.6 (utilitarian styling / hand-rolled
  markers) closed. Carry-overs filed under §4 Medium: chart-content
  review (bull/base/bear spread looks formulaic), chart interaction
  affordances (expand-to-overlay + download-as-tear-sheet). Plan:
  `CHART_MIGRATION_HANDOFF_PLAN.md` (✅ RESOLVED).

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

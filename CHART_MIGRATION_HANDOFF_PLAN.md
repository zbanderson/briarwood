# Chart-Renderer Migration to Apache ECharts (Handoff Plan)

**Status:** ✅ RESOLVED 2026-04-30 — all three cycles landed in one
session against the canonical Belmar BROWSE + DECISION fixtures with
owner browser-smoke sign-off after Cycle 1 (substrate + cma_positioning)
and again after Cycle 2 (bulk migration of the remaining seven chart
kinds + drive-by §3.4.2 / §3.4.6). Cycle 3 cleaned up the eval sandbox,
removed Recharts + Nivo from `web/package.json`, and reconciled the
docs. All eight production chart kinds now render through Apache
ECharts via a single `next/dynamic({ ssr: false })` boundary. The
ECharts engine chunk (~366 KB gz) loads lazily; non-chart routes
carry zero ECharts cost in their first-load chunks.

**Original status block (kept for handoff continuity):**
ACTIVE 2026-04-29 — filed at Phase 4c Cycle 5 closeout per the
2026-04-29 owner pick that overrode the eval memo's "stay native"
recommendation. Plan APPROVED at filing. **Owner:** Zach
**Origin:** Phase 4c Cycle 5 chart-library evaluation memo at
[`docs/CHART_LIBRARY_EVAL_2026-04-29.md`](docs/CHART_LIBRARY_EVAL_2026-04-29.md);
[`ROADMAP.md`](ROADMAP.md) §3.6; [`DECISIONS.md`](DECISIONS.md)
2026-04-29 entry "Phase 4c Cycle 5 landed: chart-library eval +
Apache ECharts picked".
**Sequence position:** Bookend follow-up to step 6 (Phase 4c). The
sequence has no further bookend steps queued; this is a strategic
initiative under [`ROADMAP.md`](ROADMAP.md) §3.6, not a numbered
sequence step.
**Size:** M-L (3 cycles + closeout — `[size: M-L]` per §3.6).
**Estimate:** 60–120 LLM-development-minutes across the three cycles.
**Actual:** all three cycles + closeout landed in one session
(2026-04-30) following the Cycle 1 owner sign-off and the Cycle 2
combined-smoke sign-off.
**Risk:** Medium. Cross-cutting frontend swap with one strong gating
criterion (bundle delta on non-chart routes must stay at baseline)
and eight per-chart visual-parity gates.

---

## North-star problem statement

The 2026-04-29 owner pick from the Phase 4c Cycle 5 chart-library eval
selected Apache ECharts as the chart renderer over the production
native-SVG implementation in
[`web/src/components/chat/chart-frame.tsx`](web/src/components/chat/chart-frame.tsx).
The pick was an explicit override of the eval memo's recommendation
to stay native — the memo's argument was framed on bundle weight; the
owner's argument is framed on **product polish first, optimize cost
later** ([`project_llm_guardrails.md`](/Users/zachanderson/.claude/projects/-Users-zachanderson-projects-briarwood/memory/project_llm_guardrails.md)).

ECharts produced visibly better hover affordances, animation, and
marker-vocabulary rendering than the production native renderer at
the eval's full-vocab fixture. The owner saw that polish and chose
to absorb the bundle cost (364 KB gzipped at the chart route, ~1
second extra to first chart paint on residential 4G mobile then
cached, invisible on fiber/wifi) in exchange.

This plan is the **execution** of that pick. The decision is settled;
this is implementation work.

---

## Scope locked

- Swap [`web/src/components/chat/chart-frame.tsx`](web/src/components/chat/chart-frame.tsx)'s
  eight native-SVG chart implementations for Apache ECharts equivalents
  rendered through `echarts-for-react` with the SVG renderer
  (`opts.renderer = "svg"`):
  - `scenario_fan` — bull/base/bear/stress fan chart.
  - `cma_positioning` — comp scatter against subject ask + fair-value
    band (the Cycle 5 eval prototype is the starting point).
  - `value_opportunity` — ask vs fair-value diff chart.
  - `market_trend` — geographic trend line with year-anchor markers.
  - `risk_bar` — horizontal stacked risk-flag bars.
  - `rent_burn` — rent vs obligation trajectories with market band.
  - `rent_ramp` — net cash flow at 0/3/5% rent escalation.
  - `horizontal_bar_with_ranges` — scenario range comparison bars.
- Wrap each ECharts component in `next/dynamic()` with
  `ssr: false` so the ECharts chunk arrives **after** the page is
  interactive. Non-chart routes do not load ECharts.
- Build a small shared color-token bridge (`web/src/lib/chat/chart-tokens.ts`)
  that resolves the production CSS vars (`--chart-base`, `--chart-bull`,
  `--chart-bear`, `--chart-stress`, `--chart-neutral`, `--chart-grid`,
  `--chart-text-faint`, `--color-bg-sunken`) into the concrete hex
  ECharts wants in its options object. Single source of truth, mirrors
  the eval prototype's pattern.
- Drive-by **§3.4.2** (`value_opportunity` y-axis "Comp" label
  rendering as a vertical character stack). The bug class disappears
  in ECharts' declarative `yAxis.name` API — there is no rotated-text
  primitive to misuse.
- Drive-by **§3.4.6** (chart marker diversity / utilitarian styling).
  ECharts' `series.symbol` + `series.itemStyle` + `series.emphasis`
  give each marker class declarative diversity without hand-rolling
  SVG primitives.
- Retire the sandbox `web/src/components/chat/_eval/` directory and
  the `/eval/charts` routes after migration is complete.
- Remove unused candidate libraries from `web/package.json` once
  Cycle 1 confirms ECharts is the only renderer in use:
  - `recharts`
  - `@nivo/core`
  - `@nivo/scatterplot`
  ECharts and `echarts-for-react` stay.
- Update [`briarwood/representation/README.md`](briarwood/representation/README.md)
  per `.claude/skills/readme-discipline/SKILL.md` Job 3 if the
  renderer change reaches the Representation Agent's contract
  surface (it touches `RepresentationPlan` chart selection only at
  the registry layer, not at the renderer; so the README update is
  Cycle 3 cleanup territory unless Cycle 1 or 2 surfaces a contract
  change).

## What is NOT in scope

- **No backend changes.** [`api/events.py`](api/events.py),
  [`briarwood/agent/dispatch.py`](briarwood/agent/dispatch.py),
  [`api/pipeline_adapter.py`](api/pipeline_adapter.py)'s
  `_native_*_chart` builders, and the `ChartSpec` discriminated union
  in [`web/src/lib/chat/events.ts`](web/src/lib/chat/events.ts) all
  stay exactly as they are. The migration is a renderer swap; the
  chart-event payload contract is unchanged. The chart-spec types
  are the contract this migration consumes — same shape as today.
- **No new LLM prompts.** No changes to the synthesizer
  ([`briarwood/synthesis/llm_synthesizer.py`](briarwood/synthesis/llm_synthesizer.py)),
  Scout ([`briarwood/value_scout/`](briarwood/value_scout/)), or any
  decision-model module. Per AGENTS.md OpenAI boundary: this is
  Layer 4 (Representation) presentation work only.
- **No expansion of the chart-kind catalog.** Eight kinds in, eight
  kinds out. New kinds are filed separately under §3.4 if/when needed.
- **No changes to chart selection logic.** The Representation Agent
  (when running under the claims flag) and the legacy synthesis
  path (when running outside the flag) both continue to pick chart
  kinds the same way they do today.
- **No data-shape changes.** Production data sometimes lacks ACTIVE
  comps or `value_low` / `value_high`; the migration inherits that
  shape unchanged. Whether production should emit full-vocab data
  more often is a separate backend conversation in the CMA module.

## Hard constraints

- **Bundle-cost mitigation is mandatory.** ECharts' chunk (~364 KB
  gzipped) MUST load through `next/dynamic()` so non-chart routes
  carry zero ECharts cost. Cycle 1's gating verification is a
  before/after `next build` per-route bundle delta — non-chart routes
  must stay at the pre-Cycle-1 baseline within ±2 KB gz.
- **Theme tokens routed through a single helper.** ECharts can't
  resolve CSS vars at render time; the production color palette must
  be mirrored as concrete hex through one shared
  `web/src/lib/chat/chart-tokens.ts` module. No per-chart hex
  duplication.
- **Visual parity per chart kind, gate at the BROWSE smoke.** Every
  chart kind ships against the BROWSE smoke fixture
  (`1228-briarwood-road-belmar-nj` if usable;
  `1008-14th-ave-belmar-nj-07719` is the documented substitute) plus
  one DECISION fixture (`526-w-end-ave-avon-by-the-sea-nj`). The
  ECharts version must be **at least as readable** as the native
  version on both fixtures; readability is judged by the Phase 4c
  Cycle 5 gating criterion ("user understands the chart's verdict
  in 2-3 seconds"), not pixel-identical rendering.
- **Pre-existing baseline failure stays the only Python failure.**
  `tests/test_pipeline_adapter_contracts.py::PipelineAdapterContractTests::test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after`'s
  `value_opportunity` chart-kind assertion is the carry-over from
  Phase 4c Cycles 2/3/4/5. The migration does not fix it (it lives
  on the pipeline-adapter side); no new Python failures introduced.
- **No render-path regression on non-BROWSE tiers.** DECISION /
  EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP card stacks are
  unchanged. Chart events landing on those tiers continue to render
  through the same `ChartFrame` component, just with the ECharts
  body inside instead of native SVG.

---

## Cycle structure

Three cycles plus a closeout cycle. Each cycle is bounded; doc updates
happen at cycle close.

### Cycle 1 — Substrate + first chart migration (`cma_positioning`)

**Goal.** Stand up the migration substrate (lazy-import wiring +
color-token bridge) and prove it end-to-end against the
highest-stakes chart, `cma_positioning`. Cycle 1's sign-off is the
gating decision for whether the migration as a whole works in
production.

**Scope.**
- Add [`web/src/lib/chat/chart-tokens.ts`](web/src/lib/chat/chart-tokens.ts)
  exporting a `getChartTokens()` helper that returns the resolved
  chart palette as concrete hex. Read from `getComputedStyle` on
  the document root at first call; cache. The Cycle 5 eval prototype's
  hard-coded hex constants are the starting point — replace with
  this helper.
- Replace `chart-frame.tsx`'s `CmaPositioningChart` with an ECharts
  version. Source-of-truth is the Cycle 5 eval prototype at
  `web/src/components/chat/_eval/cma-echarts.tsx` — port and tune
  to match production framing. Lazy-import via `next/dynamic()` with
  `ssr: false`. Wrap in a Suspense fallback that mirrors the
  existing `<figure>` chrome and shows a thin shimmer where the
  chart will land.
- Verify the existing hover-sync wiring with the
  `BrowseDrilldown` Comps row still works through the new renderer.
  The eval prototype proves the pattern; production wiring just
  needs the same `dispatchAction({type:"highlight"})` call from the
  drilldown row's `onMouseEnter`.
- All other seven chart kinds continue to render via the existing
  native-SVG path. Cycle 1 is single-chart proof; bulk migration is
  Cycle 2.

**Tests.**
- `tsc --noEmit` clean. ESLint clean.
- `next build` clean. Per-route bundle delta on non-chart routes
  (homepage `/`, `/admin`, `/admin/turn/[turn_id]`, `/c/[id]`)
  stays at baseline within ±2 KB gz. The chart route picks up the
  ECharts chunk.
- Focused Python: `tests/test_pipeline_adapter_contracts.py` +
  `tests/test_chat_api.py`. Carry-over baseline failure on
  `value_opportunity` chart-kind assertion is the only acceptable
  failure.

**Verification (BROWSER).**
- BROWSE turn against `1008-14th-ave-belmar-nj-07719`: the
  `cma_positioning` chart renders through ECharts inside the Comps
  drilldown body. Subject-ask vertical, fair-value vertical, value
  band (when present), SOLD / ACTIVE / cross-town markers, axis
  labels, comp address tick labels — all match the eval prototype.
  The masthead `market_trend` chart and the Section A prose
  continue to render through the existing native-SVG path on this
  cycle.
- DECISION turn against the same property: chart events on the
  DECISION-tier card stack render correctly (cma chart inline if
  emitted; non-cma charts unchanged).
- The Comps drilldown chip + chart-marker hover-sync still highlights
  matching comps in both directions.
- First chart paint on a fresh-cache load completes within ~1.5
  seconds on a residential 4G simulation (Chrome devtools "Slow
  4G" preset). On fast wifi, the lazy fallback is invisible.

**Open Design Decisions to resolve at Cycle 1 close.**
- Theme-token cache invalidation strategy. Static computed-style
  read at first call is the simplest; if light/dark theme switching
  ever lands, the helper grows a `useSyncExternalStore` subscription
  to `prefers-color-scheme`. Out of scope for v1.
- Suspense fallback shape — solid shimmer, axis-skeleton, or
  invisible. Bias: solid shimmer matching the chart's outer rounded
  rectangle; ~120 ms minimum-display so the shimmer doesn't flash on
  fast paint.

**Estimate.** 30–45 LLM-development-minutes.
**Risk.** Medium-Low. Single chart, eval prototype already exists.

---

### Cycle 2 — Bulk migration (remaining 7 chart kinds)

**Goal.** Migrate the remaining seven chart kinds (`scenario_fan`,
`value_opportunity`, `market_trend`, `risk_bar`, `rent_burn`,
`rent_ramp`, `horizontal_bar_with_ranges`) following Cycle 1's
substrate. Drive-by §3.4.2 + §3.4.6.

**Scope.**
- One chart kind at a time, each migrated via the Cycle 1 pattern
  (lazy import + color tokens + visual-parity gate). Order by
  user-facing visibility: `market_trend` (Section A masthead) →
  `scenario_fan` (Projection drilldown) → `risk_bar` (Risk
  drilldown) → `rent_burn` (Rent drilldown) → `rent_ramp` (Rent
  drilldown) → `value_opportunity` (Value-thesis drilldown) →
  `horizontal_bar_with_ranges` (any tier).
- §3.4.2 closes when `value_opportunity` is migrated — ECharts'
  `yAxis.name` rotates declaratively without the production
  `<text transform="rotate(-90 ...)">` trick that triggered the
  vertical-character-stack bug.
- §3.4.6 closes when each chart's marker scheme uses ECharts'
  `symbol` / `itemStyle` declaratively. The native renderer's
  hand-rolled `<polygon>` and `<circle>` markers are replaced
  with first-class ECharts symbols + emphasis states.

**Tests.**
- Same gates as Cycle 1, plus: each migrated chart kind has a
  visual-parity sign-off pass against the BROWSE smoke fixture
  before the next chart starts.

**Verification (BROWSER).**
- Full BROWSE smoke walkthrough on three properties
  (`1228-briarwood-road-belmar-nj` if usable, otherwise
  `1008-14th-ave-belmar-nj-07719`; `526-w-end-ave-avon-by-the-sea-nj`;
  one freshly-promoted live listing). All eight charts render
  through ECharts.
- DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP
  smoke pass: chart events on these tiers' card stacks render
  correctly. No regression in non-BROWSE rendering.
- Per the §3.4.2 closure: `value_opportunity` y-axis "Comp" label
  renders horizontally rotated, not as a vertical character stack.
- Per the §3.4.6 closure: marker diversity for each chart's
  vocabulary (e.g., comp markers SOLD / ACTIVE / cross-town;
  bull/base/bear/stress endpoint annotations) reads cleanly.

**Open Design Decisions to resolve at Cycle 2 close.**
- Whether the existing `LegendRow` JSX in `chart-frame.tsx` stays
  or moves into ECharts' built-in legend. Bias: keep `LegendRow`
  since it's already styled to match the page chrome; ECharts'
  legend doesn't add capability we need.

**Estimate.** 30–60 LLM-development-minutes.
**Risk.** Medium. Seven chart kinds is the bulk of the work; each
has its own visual-parity tuning pass.

---

### Cycle 3 — Cleanup + closeout

**Goal.** Retire the eval sandbox, remove unused candidate libraries,
and reconcile docs.

**Scope.**
- Delete `web/src/components/chat/_eval/` (the seven prototype files).
- Delete `web/src/app/eval/` (the hub + four per-library routes).
- Remove `recharts`, `@nivo/core`, `@nivo/scatterplot` from
  `web/package.json` and run `pnpm install` to update the lock
  file. ECharts and `echarts-for-react` stay.
- Verify `web/package.json` cleanup with a final `next build` run —
  bundle-delta sanity check on all routes; the chart route should
  show only the ECharts chunk, not Recharts or Nivo chunks.
- Doc reconciliation:
  - This file's top header → ✅ RESOLVED YYYY-MM-DD with cycle
    summary.
  - [`ROADMAP.md`](ROADMAP.md) §3.6 → ✅ RESOLVED YYYY-MM-DD with
    cycle summary; §10 Resolved Index appended.
  - [`DECISIONS.md`](DECISIONS.md) — per-cycle landed entries
    (Cycle 1 / Cycle 2 / Cycle 3) plus a closeout entry recording
    that the chart-renderer migration is complete.
  - [`CURRENT_STATE.md`](CURRENT_STATE.md) — Current Known Themes
    refreshed; chart-renderer-migration paragraph removed (or
    flipped to "closed YYYY-MM-DD").
  - [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) —
    `chart-frame.tsx` row in the component table updated to
    "Apache ECharts renderer for the eight `ChartSpec` kinds";
    eval-sandbox reference removed.
  - [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md) — Layer 4 gap on
    chart-renderer migration flipped to closed; §3.4.2 + §3.4.6
    gaps closed.
  - [`docs/current_docs_index.md`](docs/current_docs_index.md) —
    `CHART_MIGRATION_HANDOFF_PLAN.md` entry marked historical
    (✅ RESOLVED YYYY-MM-DD).
- Module README discipline ([`SKILL.md`](.claude/skills/readme-discipline/SKILL.md)
  Job 3):
  - [`briarwood/representation/README.md`](briarwood/representation/README.md)
    — only if the renderer change reaches the Representation
    Agent's contract surface. The chart-spec contract is
    unchanged, so the README's "What lands in the chart" rules
    don't move; the only candidate update is a sentence noting
    that production charts now render through ECharts on the
    React side. Update only if one such sentence exists in the
    current README.

**Tests.**
- `tsc --noEmit` clean. ESLint clean. `next build` clean with
  the lighter dependency set.
- Focused Python tests (same set as Cycles 1-2). Pre-existing
  baseline failure remains the only acceptable failure.
- Module-alignment regression: the Stage 4 `model_alignment` table
  for `526-w-end-ave-avon-by-the-sea-nj` should still produce
  honest rows. The migration touches presentation only; if
  alignment drifts, the regression is presentation-side leakage
  and needs to be caught immediately.

**Verification.**
- Full BROWSE smoke walkthrough on the same three properties used
  in Cycle 2.
- Owner sign-off on the qualitative bar: "the rebuild's polish
  reads better than the native renderer at every chart kind."

**Estimate.** 4–8 LLM-development-minutes for cleanup + doc
reconciliation.
**Risk.** Low — purely closeout.

---

## Per-cycle doc-update list

This table is the canonical list of doc touches. Cycle owners use it
to avoid forgetting a reconciliation pass; Cycle 3 verifies completeness.

| Doc | Cycle 1 | Cycle 2 | Cycle 3 |
|-----|---------|---------|---------|
| `CHART_MIGRATION_HANDOFF_PLAN.md` | Status header → "Cycle 1 in progress" / "landed" | Cycle 2 status flip | Final ✅ flip + summary at top |
| `ROADMAP.md` §3.6 | Status: Active | Cycle 2 outcome | ✅ RESOLVED + cycle index |
| `ROADMAP.md` §3.4.2 | — | ✅ RESOLVED in Cycle 2 (drive-by) | Verified |
| `ROADMAP.md` §3.4.6 | — | ✅ RESOLVED in Cycle 2 (drive-by) | Verified |
| `ROADMAP.md` §10 Resolved Index | — | — | Append migration entry |
| `DECISIONS.md` | Cycle 1 landed (substrate + first chart) | Cycle 2 landed (bulk migration + drive-bys) | Cycle 3 + migration closeout entry |
| `CURRENT_STATE.md` | — | — | Themes update + bump `Last Updated` |
| `ARCHITECTURE_CURRENT.md` | UI map row update | — | Final reconciliation |
| `GAP_ANALYSIS.md` | — | — | Layer 4 gap flipped to closed |
| `docs/current_docs_index.md` | — | — | Mark plan historical |
| Module READMEs | — | — | `representation/README.md` if contract surface touched |
| `web/package.json` | (added in Phase 4c Cycle 5) | — | Remove `recharts`, `@nivo/core`, `@nivo/scatterplot` |

---

## Testing strategy

Per AGENTS.md Verification Rules + Phase 4c precedent.

- **Python.** Each cycle runs `tests/test_pipeline_adapter_contracts.py`
  + `tests/test_chat_api.py`. The clean-tree baseline carries one
  pre-existing failure on `value_opportunity` chart-kind assertion
  that lives on the pipeline-adapter side — not introduced and not
  fixed by this migration.
- **TypeScript.** Every cycle: `tsc --noEmit` clean, ESLint clean,
  `next build` clean. The repo has no Vitest/Jest framework — adding
  one is meta-infra out of scope (matches Phase 4c precedent).
- **Bundle delta.** Mandatory per cycle. Method: clean rebuild
  (`rm -rf .next && pnpm next build`); identify per-route chunk
  attribution by inspecting `.next/static/chunks/` and
  `.next/server/app/<route>/page/build-manifest.json`. Compare
  per-route gzipped totals before vs after the cycle's changes.
  Target: non-chart routes stay at baseline ±2 KB gz; chart routes
  pick up the ECharts chunk (~364 KB gz, declining as Cycle 3
  removes Recharts + Nivo).
- **Live browser smoke.** Mandatory pause after every cycle.
  Canonical queries:
  - "what do you think of 1228 Briarwood Rd, Belmar, NJ" (BROWSE,
    if usable; else 1008 14th Ave) — exercises all eight chart
    kinds across the three sections.
  - "should I buy 1228 Briarwood Rd, Belmar, NJ" (DECISION) —
    verifies non-BROWSE card-stack rendering.
- **Module-alignment regression.** Quick confidence check: the
  Stage 4 `model_alignment` table for
  `526-w-end-ave-avon-by-the-sea-nj` should still produce honest
  rows after the migration. Migration is presentation-side; if
  alignment drifts, it's leakage and needs immediate triage.

---

## Success criteria

The whole migration is done when:

1. **All eight chart kinds render through ECharts.** No native-SVG
   chart code remains in `chart-frame.tsx`.
2. **Lazy import works.** Non-chart routes (`/`, `/admin`,
   `/admin/turn/[turn_id]`, `/c/[id]`) carry zero ECharts cost in
   their `next build` chunks.
3. **Visual parity per chart kind.** Each chart kind reads at least
   as cleanly as the native version did on the same fixtures.
   Owner sign-off on the qualitative bar.
4. **Hover-sync preserved.** The Phase 4c Cycle 4 `BrowseDrilldown`
   chip ↔ chart-marker hover-sync continues to work through the new
   renderer on `cma_positioning`. Same pattern available for any
   future chart that wants the affordance.
5. **§3.4.2 closed.** `value_opportunity` y-axis "Comp" label
   renders correctly (horizontally rotated, not a vertical
   character stack).
6. **§3.4.6 closed.** Each chart's marker vocabulary uses ECharts'
   declarative symbol API, not hand-rolled SVG primitives.
7. **No backend or contract changes.** `api/events.py` /
   `dispatch.py` / `ChartSpec` / `_native_*_chart` builders all
   unchanged. Module READMEs unchanged in Cycles 1-2; only
   `briarwood/representation/README.md` may receive a Cycle 3
   sentence-level update if the renderer change is named in its
   current text.
8. **Sandbox retired.** `web/src/components/chat/_eval/` and
   `web/src/app/eval/` deleted; unused candidate libraries removed
   from `web/package.json`.
9. **No render-path regression.** DECISION / EDGE / PROJECTION /
   RISK / STRATEGY / RENT_LOOKUP card stacks unchanged. Chart
   events on those tiers continue to render via `ChartFrame` with
   the new renderer body inside.
10. **Doc discipline.** Per-cycle `DECISIONS.md` entries landed;
    ROADMAP §3.6 + §3.4.2 + §3.4.6 all marked ✅ in Cycle 3.
11. **Pre-existing baseline failure remains the only Python
    failure.** No new test failures introduced.

---

## Cross-references

- **Origin:** [`docs/CHART_LIBRARY_EVAL_2026-04-29.md`](docs/CHART_LIBRARY_EVAL_2026-04-29.md)
  (eval memo); [DECISIONS.md](DECISIONS.md) 2026-04-29 entry
  "Phase 4c Cycle 5 landed: chart-library eval + Apache ECharts
  picked".
- **Roadmap:** [`ROADMAP.md`](ROADMAP.md) §3.6 (this initiative);
  §3.4.7 ✅ (eval origin); §3.4.2 + §3.4.6 (drive-bys absorbed
  into Cycle 2); §3.5 ✅ (Phase 4c BROWSE rebuild — closed
  immediately upstream of this migration).
- **Predecessors:** Phase 4c BROWSE rebuild (closed 2026-04-29)
  shipped the three-section newspaper-hierarchy layout that the
  migrated charts will render inside. Phase 3 Cycle A retired the
  iframe-Plotly path for these eight chart kinds in favor of
  hand-written native SVG; this migration is the next step in
  that evolution.
- **Constraints:** AGENTS.md Layer 4 boundary (no LLM presentation
  logic); CLAUDE.md README discipline; user-memory
  `project_llm_guardrails.md` (perfect-product-first stance —
  the framing for the bundle-cost trade);
  `project_ui_enhancements.md` (chart polish complaint);
  `project_scout_apex.md` (Briarwood differentiates on polish,
  not parity);
  [`project_web_architecture.md`](/Users/zachanderson/.claude/projects/-Users-zachanderson-projects-briarwood/memory/project_web_architecture.md)
  (use pnpm in `web/`; don't reach for the Vercel AI SDK protocol).

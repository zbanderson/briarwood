# Chart-Library Evaluation — Phase 4c Cycle 5

**Date:** 2026-04-29
**Author:** Phase 4c Cycle 5 working session
**Status:** Recommendation produced; awaiting owner pick.
**Scope:** Eval only. Migration is a separate handoff that opens AFTER Cycle 5 closes if the owner picks a new library.

---

## TL;DR

**Recommendation: stay on the native-SVG renderer.** Fold the §3.4 polish work (animation, hover affordances, marker diversity, the §3.4.2 vertical-character y-axis bug) into a focused chart-frame refactor instead of adopting a third-party library.

If the owner overrides toward a third-party library, **Recharts is the clear runner-up.** ECharts is ruled out by bundle weight; Nivo is ruled out by per-chart-kind package sprawl plus the lack of native categorical-y support.

The eval was framed by the 2026-04-28 owner reframe ("a chart library that is very easy to understand within seconds"). The premise §3.4.7 was originally written against — *iframe-Plotly is the ceiling on visual polish* — has already partially dissolved: Phase 3 Cycle A retired iframe-Plotly for all eight production chart kinds in favor of hand-written native SVG inside `chart-frame.tsx`. The native renderer **is** the React-native solution §3.4.7 was reaching for. Its remaining gaps are polish, not architecture.

---

## What was built

Sandbox-only eval prototypes under `web/src/components/chat/_eval/` and `web/src/app/eval/charts/` (sub-routes per library so `next build` reports per-library bundle deltas independently). Nothing is wired into the production render path.

| File | Purpose |
| --- | --- |
| `_eval/cma-fixture.ts` | Real `CmaPositioningChartSpec` payload extracted from a captured BROWSE turn against `1008-14th-ave-belmar-nj-07719` (1228-briarwood-road-belmar-nj is null-priced and isn't a usable BROWSE target without first promoting/enriching it; 1008 14th Ave is in the same town, has 8 priced comps, and is a canonical fixture in `BROWSE_REBUILD_HANDOFF_PLAN.md`'s testing strategy). Plus a synthetic full-vocab variant exercising SOLD/ACTIVE/cross-town markers and the value-band overlay. |
| `_eval/eval-card.tsx` | Shared chrome (title, subtitle, metric chips, "drilldown rail") so visual differences between candidates are purely the library's plotting. |
| `_eval/eval-route-shell.tsx` | Per-route harness with a fixture toggle. |
| `_eval/cma-native.tsx` | Production native-SVG renderer extracted from `chart-frame.tsx`'s `CmaPositioningChart`, served standalone for direct comparison. |
| `_eval/cma-recharts.tsx` | Recharts `ScatterChart` with categorical y-axis, `ReferenceLine` + `ReferenceArea`, custom shape components per marker class. |
| `_eval/cma-echarts.tsx` | `echarts-for-react` with three scatter series, `markLine` + `markArea`, SVG renderer (`opts.renderer = "svg"`). External hover-sync via `dispatchAction({type:"highlight"})`. |
| `_eval/cma-nivo.tsx` | `@nivo/scatterplot` with numeric-y plus index-to-address tick formatter, custom `layers` SVG component for the value band. |
| `app/eval/charts/page.tsx` | Hub linking to per-library routes. |
| `app/eval/charts/{native,recharts,echarts,nivo}/page.tsx` | Per-library routes. |

To inspect: `cd web && pnpm dev` then visit `/eval/charts`.

The `1228-briarwood-road-belmar-nj` substitution is documented in `_eval/cma-fixture.ts` — the saved property has all-null pricing fields (`ask_price=null`, `bcv=null`, `missing_input_count=4`) and isn't a usable BROWSE target without first promoting/enriching it.

---

## Comparison

### (f) Bundle weight delta — `next build` per-route chunks

Measured by identifying library-attributable chunks in `.next/static/chunks/` after a clean `next build` against four per-library routes. Numbers are **gzipped** (what users actually download); raw in parentheses.

| Library | Gzipped | Raw | Multiplier vs Recharts |
| --- | ---: | ---: | --- |
| Native SVG | 0 KB | 0 KB | already shipped |
| @nivo/scatterplot 0.99 | **70 KB** | 214 KB | 0.83× |
| Recharts 3.8 | **84 KB** | 297 KB | 1.0× |
| Apache ECharts 6 | **364 KB** | 1.10 MB | **4.3×** |

Caveats:
- Nivo's 70 KB is *only* `@nivo/scatterplot`. Replacing the eight current chart kinds (`scenario_fan`, `cma_positioning`, `value_opportunity`, `market_trend`, `risk_bar`, `rent_burn`, `rent_ramp`, `horizontal_bar_with_ranges`) would also pull in `@nivo/line`, `@nivo/bar`, `@nivo/swarmplot`, etc. Realistic full-catalog cost: ~180–250 KB gzipped.
- ECharts is dominated by its built-in vendor blob; per-chart-kind cost is roughly flat after the first chart adds the engine.
- Recharts shares its dependencies across all chart kinds; per-additional-kind cost is small (~5–15 KB gzipped each).

### (c) Code volume per chart (cma_positioning only)

| Library | LOC | Notes |
| --- | ---: | --- |
| Native SVG | 199 | All hand-rolled SVG primitives. Reuses `chartBounds`, `linePath`, `formatTick` helpers from `chart-frame.tsx` in production (the standalone copy in this eval has these inline). |
| Apache ECharts | 214 | Mostly an `option` config object. |
| Nivo | 223 | `nodeComponent` per series + custom `layers` for the band. Index-to-address tick mapping adds friction. |
| Recharts | 240 | Component composition (`<XAxis>`, `<YAxis>`, `<ReferenceLine>`, `<ReferenceArea>`, `<Scatter shape={...}>`, `<Tooltip content={...}>`). |

LOC is similar across all four. None of them save material code volume over native at the per-chart level.

### (a) Visual quality at default

All four prototypes use the same color tokens (`--chart-base`, `--chart-bull`, `--chart-bear`, `--chart-stress`, `--chart-neutral`, `--chart-grid`, `--chart-text-faint`) so the side-by-side comparison shows pure library differences:

- **Native:** Pixels are exactly what production ships today. Subject-ask vertical line, fair-value vertical line, dashed-band overlay, marker diversity for SOLD / ACTIVE / cross-town, axis ticks, address row labels, money labels per marker.
- **Recharts:** Crisp SVG render. Built-in tick rendering is denser than the native four-row gridline; can be tuned via `interval` and `tickFormatter`. The categorical y-axis renders one tick per comp address. ReferenceLine labels render at the top by default — slight redesign needed to match the production "Fair value" / "Ask" overlay copy.
- **ECharts:** Best out-of-box polish. Hover affordances (radial highlight, tooltip with default styling) are immediately good. Vertical markLines render with built-in label positioning. SVG renderer lets the chart inherit the page's CSS color stack visually, but ECharts itself wants concrete hex (CSS vars don't resolve inside its rendering pipeline) — the prototype hard-codes resolved hex from `globals.css`.
- **Nivo:** Clean default aesthetic. Axis ticks are well-spaced. The numeric-y → index map produces correct visuals but the tick formatter has to slice the address every time. The custom `layers` injection for the value band is more code than the equivalent declarative `ReferenceArea` in Recharts.

### (b) Visual quality after ~30 LLM-development-min polish

At this stage all four converge. The candidates' default polish gives them an early advantage; native catches up after color tokens, marker shapes, and label positioning are tuned (which production has already done in `chart-frame.tsx`). The marginal polish a library affords beyond ~30 min is animation and hover transitions — see (d).

### (d) Hover / animation affordances

| Library | Hover | Animation | Notes |
| --- | --- | --- | --- |
| Native SVG | Hand-built per chart | None | Production uses pure SVG. Animations would be 1-2 days of work to add. |
| Recharts | Built-in `<Tooltip>`, `onMouseEnter` per Scatter | Animated transitions on data change (`isAnimationActive` default true) | Best out-of-box hover-sync ergonomics for React. |
| ECharts | Best-in-class default tooltip + emphasis state | Smooth animations on every config change | Configurable via `series.emphasis`. |
| Nivo | Custom `nodeComponent` mouse handlers | Animated transitions via `motionConfig` | Less idiomatic — hover state lives in the component closure. |

### (e) Ability to co-render with surrounding React state

The Phase 4c Cycle 4 ambition mentioned in the handoff: drilldown chip hover-syncs with chart marker. This was prototyped in all four candidates against the same `hoveredAddress` state owned by `EvalRouteShell`.

- **Native:** Trivial. The chart IS React; the parent state is the chart state. Marker swell on hover is a single `r={isHovered ? 8 : 6}` ternary.
- **Recharts:** Works via the `shape` prop closing over external state. Slightly noisier (ESLint's `react-hooks/static-components` flags inline named components inside the parent — the prototype hoists `TooltipBody` to module scope as workaround).
- **Nivo:** Works via custom `nodeComponent` closing over external state. Same pattern as Recharts.
- **ECharts:** Awkward. Requires a `useRef` to the ECharts instance, plus a `useEffect` that calls `inst.dispatchAction({type:"highlight", seriesIndex, dataIndex})` whenever external state changes. The chart-side `mouseover` event has to push back up. This is an imperative escape hatch wrapped in a React component — by far the heaviest co-render integration.

Native > Recharts ≈ Nivo > ECharts on this criterion.

### (g) Glance-readability — gating criterion (per 2026-04-28 owner reframe)

"Very easy to understand within seconds" is what the rebuild needs to clear. All four produce a chart whose verdict (where does subject ask sit relative to fair value and the comp distribution?) is readable in 2-3 seconds on the Belmar dataset. The library choice does not move this needle on `cma_positioning` specifically.

Where libraries *would* move the needle is on **other** chart kinds that have known issues:
- §3.4.6 marker diversity / utilitarian styling — addressable in any of the four with similar effort.
- §3.4.2 `value_opportunity` y-axis "Comp" rendering as a vertical character stack — Recharts/ECharts/Nivo all handle category-axis labels declaratively without the rotated-text trick that triggers the bug; native would need a fix in `AxisLabels`.

The bug §3.4.2 is the only criterion-(g) concern that **does** improve with a switch — and it improves for ~5 minutes of work in the native code as well.

---

## Per-library notes

### Native SVG (production today)

**Pros**
- 0 KB delta. Already shipped, already typed against the canonical `ChartSpec` discriminated union.
- Full React control. Co-render with surrounding state is trivial.
- One file, one mental model. New chart kinds are functions in `chart-frame.tsx`.
- Color tokens flow through CSS vars; no theming friction.

**Cons**
- No animations.
- Hover affordances must be hand-built per chart.
- §3.4.6 marker-diversity polish is hand-rolling SVG primitives.
- The §3.4.2 vertical character-stack y-axis bug currently lives in the native `AxisLabels` helper.

### Recharts 3.8

**Pros**
- 84 KB gzipped is in the affordable range.
- Declarative React composition (`<XAxis>`, `<ReferenceLine>`, etc.) — feels native.
- Built-in animations and tooltip primitives.
- Same primitives across all chart kinds (ScatterChart / LineChart / BarChart / AreaChart) — strongest amortization story.
- ReferenceLine/ReferenceArea map cleanly onto the production "fair value vertical / value band rect" overlays.

**Cons**
- TypeScript surface is loose in places (had to cast `Tooltip`'s `props.payload`, had to cast Scatter's `onMouseEnter` payload).
- 84 KB gzipped is **per chart route** today; grows by ~5-15 KB per additional chart kind. Whole-catalog estimate: ~120-180 KB gzipped.
- Categorical-y dedupes identical strings — would break if two comps shared an address.

### Apache ECharts 6 (echarts-for-react)

**Pros**
- Best-in-class polish out of box.
- Largest chart-type catalog of any candidate.
- SVG renderer option.

**Cons**
- **364 KB gzipped is prohibitive.** The whole `web/` First Load JS is currently <1 MB; this single library would balloon `/eval/charts/echarts` to 1.3+ MB. Production routes carrying charts would absorb the same hit.
- Config-object API is less idiomatic React. Hover-sync requires the `useRef` + `dispatchAction` escape hatch.
- CSS vars don't resolve inside the rendering pipeline — theming has to mirror tokens as concrete hex.

### Nivo @nivo/scatterplot 0.99

**Pros**
- Cleanest default aesthetic of the candidates.
- 70 KB gzipped (lightest of the third-party candidates *for one chart kind*).

**Cons**
- Per-chart-kind packages. Full catalog cost is the sum of `@nivo/scatterplot` + `@nivo/line` + `@nivo/bar` + `@nivo/swarmplot` + …; realistic 180-250 KB gzipped.
- No native categorical-y axis. The numeric-y → index map is functional but is a hack.
- `markers` prop only handles axis-aligned lines; the value band has to be injected via custom `layers` (extra LOC for what should be a one-liner).
- API has more boilerplate than Recharts for the same output.

---

## Recommendation in one paragraph

Stay on the native-SVG renderer. The §3.4.7 thesis — "iframe-Plotly is the visual ceiling" — already dissolved when Phase 3 Cycle A retired iframe-Plotly for native SVG. The native renderer is the React-native solution. Its remaining gaps (animation, hover affordances, marker diversity, the §3.4.2 y-axis bug) are 30-90 min of polish each in `chart-frame.tsx` — cheaper than absorbing 70-364 KB gzipped of third-party code plus ongoing API maintenance. If the chart-kind count doubles in the next 1-2 quarters, revisit; at that point Recharts is the clear runner-up.

If the owner overrides toward a library, pick **Recharts**. ECharts is ruled out by bundle weight (4.3× Recharts gzipped); Nivo is ruled out by per-chart-kind package sprawl plus the missing categorical-y axis.

---

## How to evaluate visually

1. `cd /Users/zachanderson/projects/briarwood/web && pnpm dev`
2. Visit `http://localhost:3000/eval/charts` for the hub.
3. Click into each library's route. Toggle between the **Belmar production** fixture (8 SOLD comps, no band) and **Full vocab** (mixed SOLD/ACTIVE/cross-town + value band).
4. Hover any chip in the "Drilldown rail" column or any chart marker to test cross-component hover-sync (criterion (e)).
5. Compare the four side-by-side mentally: which one reads the verdict fastest? Which feels closest to the production aesthetic? Which has hover affordances you'd miss if they weren't there?

After deciding, record the call in `DECISIONS.md` and (if migrating) open a fresh handoff plan — that work is **not** part of Phase 4c.

---

## Cycle-5 doc-update list (what this cycle has touched)

Done in this session:
- `docs/CHART_LIBRARY_EVAL_2026-04-29.md` — this memo.
- Eval prototypes under `web/src/components/chat/_eval/` and `web/src/app/eval/charts/` (sandbox-only).
- `web/package.json` gained `recharts`, `echarts`, `echarts-for-react`, `@nivo/core`, `@nivo/scatterplot`. **If the owner picks "stay on native," Cycle 6 closeout removes these.**

Pending owner pick (Cycle 6 closeout territory):
- `BROWSE_REBUILD_HANDOFF_PLAN.md` Cycle 5 status flip + memo link.
- `ROADMAP.md` §3.4.7 → `✅ RESOLVED` once the call is recorded.
- `DECISIONS.md` — chart-library eval entry recording the owner's call.

PAUSE for owner decision before any closeout.

---

## Verification

- `tsc --noEmit` clean.
- ESLint clean on the eval directory + the `app/eval` route directory.
- `next build` clean — 5 new static routes generated (`/eval/charts`, `/eval/charts/native`, `/eval/charts/recharts`, `/eval/charts/echarts`, `/eval/charts/nivo`). One harmless build-time warning from Recharts about "width(-1) and height(-1)" during static prerender — Recharts can't measure dimensions during SSR; the chart measures correctly client-side.
- Focused Python: `tests/test_pipeline_adapter_contracts.py` (44 passed, 1 pre-existing baseline failure on `test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after`'s `value_opportunity` chart-kind assertion — same as Cycles 2/3/4) and `tests/test_chat_api.py` (3 passed). No new failures.

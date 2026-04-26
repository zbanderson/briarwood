# Briarwood Chart Style — Phase 3 Cycle A

**Last updated:** 2026-04-26

This is the convention for how chat-tier chart events are rendered. It is the
authoritative reference for adding new chart kinds and for retuning existing
ones. The substrate (event payload + React components) lives in:

- Python event builder: `api/events.py::chart`
- Native chart payload helpers: `api/pipeline_adapter.py::_native_*_chart`
- Wedge chart payload: `briarwood/claims/representation/verdict_with_comparison.py::_build_chart_event`
- React rendering: `web/src/components/chat/chart-frame.tsx`
- TypeScript event types: `web/src/lib/chat/events.ts::ChartEvent`
- Color tokens: `web/src/app/globals.css` (`--chart-*` custom properties)

## Color tokens

All chart colors resolve through CSS custom properties so the palette tunes in
one place. SSE event payloads can reference these tokens directly via
`legend[].color` strings of the form `var(--chart-base)` — Tailwind treats them
as inline `style="stroke: var(--chart-base)"` or as legend swatch fills.

| Token | Hex (today) | Use |
|---|---|---|
| `--chart-base` | `#79b8ff` | Primary line, base case, fair value |
| `--chart-bull` | `#75d38f` | Upside, bull case, "in model" comp |
| `--chart-bear` | `#f28b82` | Downside, bear case, risk flag, subject ask |
| `--chart-stress` | `#d7b38a` | Stress floor, market regime, emphasis |
| `--chart-neutral` | `#b8b2a4` | Neutral / context-only series |
| `--chart-text-faint` | `#8a847a` | Axis tick labels, break-even markers |
| `--chart-grid` | `#2f2d2b` | Gridlines (matches `--color-border-subtle`) |

Do not hardcode hex literals inside chart components. New colors land as new
custom properties first.

## Event-payload contract

Every native chart's SSE event SHOULD carry the following fields beyond
`title`, `kind`, `spec`, and `provenance`:

| Field | Type | Convention |
|---|---|---|
| `subtitle` | `str` | One short editorial line under the title (≤80 chars). Describes what the user is looking at, not the data shape. |
| `x_axis_label` | `str \| null` | Axis label text; null when the axis is conceptual (e.g., a single-row bar chart). |
| `y_axis_label` | `str \| null` | Same convention as x. |
| `value_format` | `"currency" \| "percent" \| "count"` | Drives the React tick formatter (`formatTick`). Currency renders as `$1.2M` / `$840K`. |
| `legend` | `list[{label, color, style}]` | One entry per visible series. `style` is `solid \| dashed \| dotted`. |

The React side falls back gracefully when any field is missing — older event
shapes still render, just without polish.

## Layout convention (per chart figure)

1. **Title** — HTML `<h3>` (15px, semibold, `--color-text`) above the SVG.
2. **Subtitle** — HTML `<p>` (12px, `--color-text-muted`) below the title.
3. **Provenance chips** — small badges, when present.
4. **SVG body** — chart payload. Title text is NOT repeated inside the SVG.
   Axis labels live inside the SVG so they track its coordinate system.
5. **Legend row** — HTML below the SVG, sourced from the event's `legend` field.
6. **Companion / advisor copy** — when present.

## Axis labels inside SVG

Each chart SVG renders axis labels via `<AxisLabels>` (top of `chart-frame.tsx`).
The convention:

- X-axis label: centered horizontally below the bottom tick row, font-size 10,
  fill `--chart-text-faint`.
- Y-axis label: rotated 90° counterclockwise on the left margin, same size and
  fill.

Y-axis tick *numbers* are rendered at the four existing gridline rows for
charts where vertical magnitude matters (`scenario_fan`, `rent_burn`,
`rent_ramp`). They are formatted via `formatTick(value, value_format)`.

## Adding a new chart kind

1. Add a `ChartSpec` entry to `briarwood/representation/charts.py` with
   `id`, `name`, `description`, `required_inputs`, `claim_types`. Register a
   renderer.
2. Build the event payload in either `api/pipeline_adapter.py` (chat-tier) or
   the wedge representation layer. Populate the metadata fields above.
3. Add a TypeScript spec type in `web/src/lib/chat/events.ts` and union it
   into `ChartSpec`.
4. Add a React sub-component to `chart-frame.tsx` that accepts
   `{ spec, chrome }`. Use `CHART.*` tokens for colors. Render `<AxisLabels>`
   inside the SVG.
5. Wire the new kind into the `NativeChart` dispatch.
6. Add a regression test in `tests/representation/test_charts.py` asserting
   the metadata fields appear in the event payload.

## Anti-patterns

- Hardcoded hex strings in chart components (use `CHART.*` tokens).
- Rendering the chart title inside the SVG (it's HTML now).
- Per-chart bespoke legend code (use the shared `LegendRow` driven by the
  event's `legend` field).
- Dropping axis labels because "the title says it" — the title and axis labels
  serve different reading modes.

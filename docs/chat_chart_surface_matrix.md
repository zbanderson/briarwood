# Chat Chart Surface Matrix

This is the product rulebook for Briarwood's chat visuals.

The goal is not to show every chart we can generate. The goal is to show the
one visual and one supporting table that best answer the user's current
question, with enough clarity that the chart adds proprietary value rather than
just decoration.

## Principles

1. Every chart must answer a specific decision question.
2. Every chart should have a companion table or card that grounds the visual.
3. Low-signal or contradictory visuals should be suppressed, not rendered by default.
4. Chart titles should read like investor-facing questions, not internal artifact names.
5. The first chart layer should be legible in under 10 seconds.

## Matrix

| Section | Primary question | Default chart | Companion surface | Guardrail |
| --- | --- | --- | --- | --- |
| Value thesis | Is this overpriced or attractive? | `Ask vs fair value` | `ValueThesisCard` + comp support | Only show when ask and fair value are both present |
| CMA / comps | What evidence supports fair value? | No default chart yet | `CmaTableCard` | Prefer table over decorative chart until we have a true comp-positioning graphic |
| Scenario / projection | How wide is the 5-year range? | `5-year value range` | `ScenarioTable` | Only show when at least two scenario values exist |
| Risk | What is pulling this setup off course? | `Risk drivers` | `RiskProfileCard` + trust card | Only show when real risk or trust items exist |
| Rent carry | Does rent cover the monthly burden? | `Rent vs monthly cost` | `RentOutlookCard` | Only show when both rent and obligation are present |
| Rent stabilization | Can this become a viable rental later? | `Can rent catch up?` | `RentOutlookCard` | Only show when current rent, obligation, and multi-year points exist |

## Library strategy

Short term:
- Keep the chat surface native and React-first.
- Use Briarwood-owned SVG components with a chart-surface registry.
- Keep Plotly on the Python/report side for artifact generation and deep-dive offline visuals.

Why:
- The current problem is semantic fit and guardrails, not missing rendering horsepower.
- Native React/SVG keeps the chat fast, themeable, and easy to annotate with Briarwood-specific explanations.
- iframe/HTML artifacts should remain fallback/debug paths, not the primary product experience.

Medium term recommendation:
- If we outgrow the current SVG primitives, add `visx` rather than defaulting to heavyweight embedded Plotly in the chat UI.
- `visx` is the best fit if we want expressive, premium, highly controlled React-native charts.
- Plotly remains useful where zoom/pan/export are genuinely valuable, especially in reports or analyst workbenches.

## Next chart upgrades

1. Build a real CMA positioning chart:
   - x-axis: price or ppsf
   - marks: chosen comps, user comps, excluded comps
   - highlight which comps actually feed fair value

2. Upgrade scenario visuals:
   - annotate downside floor, upside ceiling, and base-case anchor directly on the fan
   - show basis override clearly for what-if runs

3. Upgrade rent visuals:
   - separate long-term and seasonal rent regimes visually
   - show carry coverage bands instead of a single obligation line when costs are estimated

4. Add chart-level provenance:
   - each visual should say which modules or bridges drove it
   - examples: `Valuation + CMA`, `Rent Outlook + rent_x_cost`, `Projection Engine + scenario_x_risk`

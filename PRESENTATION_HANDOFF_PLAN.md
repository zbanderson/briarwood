# Presentation Handoff Plan — 2026-04-25 (Phase 3)

**Owner:** Zach
**Origin:** Phase 2 ([OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md)) closed the substrate gap — every chat-tier handler now consolidates execution and the Layer 3 LLM synthesizer reads the full `UnifiedIntelligenceOutput`. The user's post-Cycle-5 feedback during the 2026-04-25 UI smoke set the framing for Phase 3:

> "Every Briarwood response should land like the front page of a newspaper — visually rich, intent-tight, narrative-led — so the user keeps reading and keeps clicking."

**Status:** Phase 3 — kick-off. No cycles started.

This plan is the **canonical to-do list** for the presentation layer's quality jump. Each cycle is a discrete handoff that should land as one logical change, with tests passing and a pause for browser verification before moving to the next. Same cadence as Phase 2.

---

## North-star problem statement

The substrate is rich (23 modules co-resident in one `UnifiedIntelligenceOutput`, intent-aware Layer 3 prose) but the user-visible surface — the charts and the prose framing — is lagging:

1. **Charts look half-baked.** No chart titles, no axis labels, no legends, no consistent style. They read like LLM-default placeholders instead of designed product. "OK as placeholders" but need to become a *key selling point* of the tool because most people are visual.
2. **Chart selection is too eager.** A first-impression BROWSE turn fires the kitchen sink — value, CMA, scenario, risk, rent_burn, rent_ramp. Someone about to spend a million dollars needs **market context first** (town price trend over time, town pulse), not a wall of every available card. Each chart should answer a specific question the user is implicitly asking.
3. **Prose is "string of characters" not engagement.** Even with the richer Layer 3 substrate, the prose framing reads like a list of facts. Every load is the front page of a newspaper — limited real estate, every bit must hook. The user blows through current responses; they aren't reading past sentence one.

The fix is four orthogonal levers, ordered for fast visible wins first:

1. **Visual polish** of the existing chart kinds (titles, axes, legends, style).
2. **Intent-keyed selection** so each turn fires 2-3 charts that answer the user's actual question, plus a new **market trend chart** for first-impression turns.
3. **LLM narration** of every rendered chart so it's not an orphan of the prose.
4. **Newspaper-voice prose** so the synthesizer's output hooks readers and keeps them clicking.

Detailed scope per cycle below.

---

## State of the repo at handoff

**Phase 2 (completed):**
- `briarwood/orchestrator.py::run_chat_tier_analysis` — consolidated chat-tier execution.
- `briarwood/synthesis/llm_synthesizer.py::synthesize_with_llm` — Layer 3 LLM prose generator.
- All six chat-tier handlers (browse, projection, risk, edge default, strategy, rent_lookup, decision fall-through) wired.

**Chart layer (current state):**
- 8 registered chart kinds in [`briarwood/representation/charts.py`](briarwood/representation/charts.py): `scenario_fan`, `value_opportunity`, `cma_positioning`, `risk_bar`, `rent_burn`, `rent_ramp`, `hidden_upside_band`, `horizontal_bar_with_ranges`. The last two are markers (renderer returns `None` — UI-side cards build the actual surface).
- Selection happens in [`briarwood/representation/agent.py::RepresentationAgent`](briarwood/representation/agent.py) — gpt-4o-mini with a Pydantic schema and post-validation, deterministic fallback when LLM returns nothing.
- Selection emits up to `max_selections` (default 6) — too many for a focused first-impression.
- Each selection carries a `claim` field (verdict text) and `supporting_evidence` (field citations) — these exist but **are not currently surfaced to the user**.
- React rendering layer at [`web/src/components/chat/`](web/src/components/chat/) — 6 chart components today.

**Market trend data already available:**
- `market_value_history` module runs in every consolidated plan.
- Agent at [`briarwood/agents/market_history/agent.py`](briarwood/agents/market_history/agent.py) prefers **town-level ZHVI** when available (verified line 45 — `geography_type = "town"`); falls back to county (`geography_type = "county"`) when town isn't covered.
- Output shape: `geography_name`, `geography_type`, `current_value`, `one_year_change_pct`, `three_year_change_pct`, `history_points` (full series), `confidence` (1.0 town, 0.8 county).
- Live UI smoke 2026-04-25 confirmed `confidence: 1.0, mode: "full"` for Belmar — town-level coverage exists.

**Synthesizer prompt (current voice):**
- [`briarwood/synthesis/llm_synthesizer.py::_SYSTEM_PROMPT`](briarwood/synthesis/llm_synthesizer.py) — instructs "3-7 sentences" of "human, conversational, concrete" prose with the numeric grounding rule. No structural directives (headlines / sections), no per-tier voice variants.

---

## Cycles

### Cycle A — Chart visual polish — LANDED 2026-04-26

**Status:** Landed. Chart event payloads now carry `subtitle`, `x_axis_label`, `y_axis_label`, `value_format`, and `legend` metadata across all seven chart-emitting sites (six native + the wedge `horizontal_bar_with_ranges`). React layer rewritten so each chart figure renders title + subtitle as HTML above the SVG, axis labels inside the SVG, a uniform legend row below, and y-axis tick numbers (currency formatted as `$1.2M` / `$840K`) on the three time-series charts. Color tokens centralized as `--chart-*` CSS custom properties in `web/src/app/globals.css`. Style guide at [web/CHART_STYLE.md](web/CHART_STYLE.md). 450 Python tests pass; TypeScript clean. Pause for browser smoke before kicking off Cycle B.

**Why first.** Fast, visible win. Every existing chart kind benefits immediately. The architectural cycles (B, C, D) build on top of polished charts; landing polish first means later cycles inherit a credible visual baseline.

**Scope:**
- Define a chart metadata schema additions in [`briarwood/representation/charts.py`](briarwood/representation/charts.py)::`ChartSpec`: at minimum `title`, `subtitle` (optional), `x_axis_label`, `y_axis_label`, `value_format` (currency / percent / count), `legend_items` (a list of `{label, color}` pairs or a flag for renderer-derived legend).
- Update each chart's `_render_*` function to populate the new metadata in the event payload.
- Update each React chart component in [`web/src/components/chat/`](web/src/components/chat/) to consume + render the metadata: chart title, axis titles, legend, consistent color palette, tasteful spacing/density.
- Define a one-off Briarwood chart style guide (color palette, fonts, spacing, gridline density) — short doc, lives alongside the chart components.
- The two marker specs (`hidden_upside_band`, `horizontal_bar_with_ranges`) already render in dedicated React cards; polish those cards too.

**Tests:**
- New regression tests in `tests/representation/test_charts.py` asserting that each registered chart spec's `render()` output (the SSE event payload) carries the new metadata fields.
- React-side: visual smoke. Run dev stack, walk through BROWSE / PROJECTION / RISK / EDGE flows, eyeball each chart for title / axes / legend. Take screenshots; the Phase 3 plan's definition of done references them.

**Verification (BROWSER):**
- Same query the user has been testing: "what do you think of 1008 14th Ave, Belmar, NJ" — this currently surfaces `value_opportunity`, `scenario_fan`, possibly `cma_positioning`. Each should now read as a finished chart.
- Pause for visual review.

**Trace:** User feedback 2026-04-25: "no x and y axis titles, no titles in general, no key, etc."

**Estimate:** 2-3 hours (mostly React work; the Python schema additions are minimal).
**Risk:** Low. Pure additive on the chart layer.

---

### Cycle B — Intent-keyed chart selection + market_trend chart kind — LANDED 2026-04-26

**Status:** Landed. New `market_trend` chart kind plumbed end-to-end (Python registry + native helper + TypeScript spec + React `MarketTrendChart` component) — town-level (or county fallback) Zillow Home Value Index series with anchors at "now", 1-year-ago, and 3-year-ago, plus 1y / 3y change percentages on metric chips. Two new `ClaimType` values: `MARKET_POSITION` and `TOWN_PULSE`.

`Session.last_market_history_view` (and the broader `last_unified_output` snapshot) is now populated from the chat-tier artifact in `_populate_browse_slots`, with `_browse_market_history_from_artifact` projecting the `market_value_history` module's `legacy_payload.points` into the chartable shape. `_unified_from_session` prefers the snapshot when present so the Representation Agent can read the real verdict for BROWSE turns instead of the projection-from-decision-view path used by the legacy DECISION handler.

The Representation Agent now accepts an `IntentContract` and a per-call `max_selections` override. System prompt extended with intent-first selection guidance and per-`answer_type` strong defaults. `_browse_stream_impl` replaces its prior hardcoded fan-out (`value_opportunity`, `cma_positioning`, `rent_burn`, `rent_ramp`, `scenario_fan` — 5 charts every turn) with a single `_representation_charts(...)` call gated to 3 charts and built from a `build_contract_from_answer_type("browse")` intent. Strong defaults steer BROWSE toward `[market_trend, value_opportunity, scenario_fan]`.

Tests: 46/46 in tests/representation + tests/synthesis/test_llm_synthesizer + tests/agent/test_presentation_advisor pass; new regression tests for market_trend rendering pinned. TypeScript clean. Pause for browser smoke before kicking off Cycle C.

**Why second.** Polish (Cycle A) makes individual charts look right; selection makes the *set* of charts feel intentional. The new `market_trend` chart is the highest-leverage addition because the user is making a financial decision and wants market context first.

**Scope:**

**B1: New `market_trend` chart kind.**
- Add a new ChartSpec to [`briarwood/representation/charts.py`](briarwood/representation/charts.py): `id="market_trend"`. Required inputs: `current_value`, `one_year_change_pct`, `three_year_change_pct`, `history_points` (ZHVI series), `geography_name`, `geography_type`. Claim types: `market_position`, `town_pulse`, `value_drivers`.
- Renderer: line chart over the history_points series, with an annotation marker for "now" (current_value), 1-year-ago, 3-year-ago. Y-axis: home value index. X-axis: time. Legend: shows the geography_name + `geography_type` (so user sees "Belmar, NJ (town)" vs "Monmouth County, NJ (county)").
- Add a React component for it in `web/src/components/chat/`.
- Source data is already produced by `market_value_history` — no module work needed; just plumbing into the chart event payload.

**B2: Tighter selection logic.**
- Lower `RepresentationAgent` `max_selections` default from 6 to 3 for the `decision_summary` / `browse_surface` tier; per-tier overrides in dispatch handlers if needed.
- Update the system prompt at [`briarwood/representation/agent.py::_SYSTEM_PROMPT`](briarwood/representation/agent.py) (around line 113) to say "Pick the 2-3 charts that *most directly answer the user's intent contract*, not the kitchen sink. If a chart doesn't tie back to the user's `core_questions`, omit it."
- Pass the IntentContract into the agent's `plan(...)` call (it isn't currently — the agent only sees the unified output and module views).
- Per-AnswerType chart-set hints in `briarwood/representation/agent.py` so the agent has a strong default per intent (e.g., BROWSE → `[market_trend, value_opportunity, scenario_fan]`, RISK → `[risk_bar, scenario_fan]`, RENT_LOOKUP → `[rent_burn, rent_ramp]`). LLM can override but starts from the right baseline.

**Tests:**
- Pin in `tests/representation/test_agent.py`: BROWSE intent + populated `market_value_history` view → `market_trend` is a top-3 selection.
- Pin: RISK intent → `market_trend` is NOT selected (irrelevant to risk).
- Pin: max_selections cap holds even when many specs match.

**Verification (BROWSER):**
- BROWSE: 3 charts max, with `market_trend` (town-level Belmar ZHVI line) prominent.
- PROJECTION: scenario_fan + maybe rent_burn, not value_opportunity.
- RISK: risk_bar prominent.
- The "kitchen sink" feel should be gone.

**Trace:** User feedback 2026-04-25: "loads everything it can get its hands on without actually thinking about ok, what is the user intent of this, e.g. show me this house and compare it against what the market in this area is."

**Estimate:** 3-4 hours (B1: new chart + React component; B2: agent prompt + per-intent defaults + tests).
**Risk:** Medium. Selection changes are user-visible; the LLM agent's behavior can be unpredictable until the new prompt is tuned with traces.

---

### Cycle C — LLM-narrates-the-chart

**Why third.** Charts now look right and fire intentionally. Now hook them to the prose so they aren't orphans.

**Scope:**

**C1: Surface the claim alongside each chart.**
- The Representation Agent already produces a `claim` field per `RepresentationSelection` (1-2 sentence verdict). Currently the API at [`api/pipeline_adapter.py`](api/pipeline_adapter.py) projects it into the chart event payload as `why_this_chart` and `supports_claim`, but the React rendering layer may or may not show it.
- Update React chart components to render the `why_this_chart` text as a caption or leading sentence above each chart. One sentence per chart.
- Polish the claim's voice — not just "this chart shows X" but a 1-2 sentence editorial framing ("Belmar's town-level ZHVI is up 12% in three years, which gives the comp anchor more confidence").

**C2: Weave chart narration into synthesizer prose.**
- Pass the list of selected charts (with their claims) into the Layer 3 synthesizer's user prompt. The synthesizer at [`briarwood/synthesis/llm_synthesizer.py`](briarwood/synthesis/llm_synthesizer.py) currently reads `unified` and `intent`; extend to also read `representation_plan: list[RepresentationSelection]`.
- Update the system prompt to instruct: "When you reference a chart's substance in prose, name what the user will see ('the scenario fan...') so the chart and prose tie together."
- Numeric guardrail unchanged (still verifier'd against `unified`).

**Tests:**
- React: rendered chart caption shows the claim text (snapshot or string-match test).
- Synthesizer: passing a `representation_plan` with two selections produces prose that references both charts (string-match test).
- System-prompt regression: pin the chart-narration directive in `tests/synthesis/test_llm_synthesizer.py`.

**Verification (BROWSER):**
- Each chart has a 1-line caption explaining why it's there.
- Synthesizer prose explicitly mentions at least one chart by name ("the value-position chart shows..." / "the town-trend line...").
- Charts and prose feel like one piece, not two parallel surfaces.

**Trace:** User feedback 2026-04-25: "we shouldnt be afraid to have the LLM explain the chart that is being rendered to the user."

**Estimate:** 2-3 hours (mostly synthesizer-prompt tuning + React caption rendering).
**Risk:** Low-Medium. Prose-quality risk only — the verifier still enforces grounding.

---

### Cycle D — Front-page-newspaper prose voice

**Why fourth.** Charts now polished, intent-keyed, and narrated. The remaining lever is the synthesizer's prose itself — does it hook the reader, or read like a list?

**Scope:**

**D1: Restructure the synthesizer system prompt.**
- Re-tune [`briarwood/synthesis/llm_synthesizer.py::_SYSTEM_PROMPT`](briarwood/synthesis/llm_synthesizer.py) for newspaper-voice: lead with the verdict, hook on the second beat, structured headers ("Headline" / "Why" / "What's Interesting" / "What I'd Watch"), supporting facts as quick hits.
- Numeric grounding rule preserved verbatim.
- Per-tier voice variants — BROWSE wants "first-impression analyst," RISK wants "underwriter naming the gaps," PROJECTION wants "5-year-out scenario writer." Either one prompt with intent-keyed tone instructions or per-tier templates; lean toward one prompt for less drift.

**D2: Output structure.**
- Decide whether the synthesizer's output stays as freeform prose or moves to a structured response (markdown headers, bullet points). Trade-off: structured = scannable but rigid; freeform = fluid but skimmable harder. Probably markdown headers + freeform body.
- If structured: define the schema (Pydantic-validated) and update the synthesizer to use `complete_structured` instead of `complete_text` — but lose the verifier's free-text grounding logic. Alternative: keep free text but have the system prompt require the markdown structure literally.
- I lean toward **literal-prompt structure** (system prompt says "format as: ## Headline\n\n<paragraph>\n\n## What's Interesting\n\n<paragraph>\n\n..."). Keeps the verifier infrastructure intact.

**D3: A/B trace logging.**
- Add a feature flag (`BRIARWOOD_SYNTHESIS_NEWSPAPER=1`) so the new voice can toggle on/off without redeploy. Default ON for the rollout, with the env knob as a kill switch.

**Tests:**
- Pin the new prompt's directives in `tests/synthesis/test_llm_synthesizer.py`: "front-page" / "headline" tokens present, "newspaper" framing token present, numeric rule preserved verbatim.
- Pin per-tier voice tokens (e.g., "underwriter" appears for RISK, "5-year scenario writer" for PROJECTION).
- A scripted-LLM end-to-end: feed a known unified output, get the canonical newspaper-voice output back.

**Verification (BROWSER):**
- The same BROWSE query: "what do you think of 1008 14th Ave..." — output should now read top-down: a Headline-style first sentence, a "Why" paragraph that names the comp anchor, a "What's Interesting" paragraph that names the optionality / driver, a "What I'd Watch" paragraph that names the risks/trust gaps.
- The prose should feel like the top of an editorial column, not a list.
- Pause for the user's qualitative read.

**Trace:** User feedback 2026-04-25: "Every single load needs to be treated like the front page of the newspaper, we have very limited real estate and thats going right in front of the users face, we need every bit to be engaging so they continue to click for more."

**Estimate:** 2-3 hours (prompt engineering + tests; iteration in the browser is the long pole).
**Risk:** Medium. The voice tuning is judgment-driven; expect 2-3 prompt iterations after the first browser test.

---

## Boot prompt for the next Claude context window

Copy-paste the block below into the new Claude Code session. The CLAUDE.md orientation protocol will fire automatically; this prompt picks up from there.

```
I'm continuing the presentation layer (Phase 3) of the Briarwood
output-quality work. Phase 2 closed the substrate gap (Cycles 1-5 of
OUTPUT_QUALITY_HANDOFF_PLAN.md) — every chat-tier handler now uses
the consolidated execution path and the Layer 3 LLM synthesizer.
Phase 3 is documented in PRESENTATION_HANDOFF_PLAN.md at the repo
root. Please:

1. Run the standard CLAUDE.md orientation: read CLAUDE.md, run the
   readme-discipline drift check, verify
   ARCHITECTURE_CURRENT / GAP_ANALYSIS / TOOL_REGISTRY are present,
   read DECISIONS.md and FOLLOW_UPS.md in full.

2. Read PRESENTATION_HANDOFF_PLAN.md end-to-end. That's the canonical
   to-do list for Phase 3.

3. Tell me where we are in the cycle sequence (look at git log + git
   status to determine which cycles have been committed). Then tell
   me in 3-5 bullets what's been decided / what's queued / what's
   unresolved for the cycle we're about to work on.

4. Confirm: am I starting the next cycle now, or is there earlier
   work uncommitted that needs to be reviewed / committed first?

Do not begin code work until steps 1-4 are done and reported back.
```

---

## Open design decisions (to resolve when each cycle starts)

1. **Chart style guide** — pick the color palette, font, gridline density. Probably one document at `web/CHART_STYLE.md` plus shared Tailwind classes / CSS variables.
2. **Selection cap (Cycle B)** — 3 by default? Per-tier override? Or per-intent override (e.g., BROWSE 3, RISK 2, EDGE 4)?
3. **Caption rendering (Cycle C)** — caption above the chart (more newspaper-like) or below (less obtrusive)?
4. **Output structure (Cycle D)** — markdown headers (literal-prompt) vs structured Pydantic response. Default to markdown headers per scope above; revisit if traces show inconsistency.
5. **Per-tier prompts (Cycle D)** — single prompt with intent-keyed tone vs separate per-tier files. Default to single prompt; split if drift forces it.
6. **Cycle B's market_trend chart placement** — top of the BROWSE response (most prominent), or after the value-position chart? Depends on what the user wants the eye to land on first.
7. **Editor pass (potential Cycle D scope expansion or new Cycle E)** — tabled 2026-04-26. Today's plan implements newspaper voice as a one-shot synthesizer prompt redesign in Cycle D. The owner's richer framing during 2026-04-26 kickoff: the visible problem isn't only prose voice, it's *response layout* — a single prose paragraph followed by 5–6 charts in a row reads like a brain dump even when the prose itself is sharp. A real "front-page editor" would interleave: headline → lead → first chart with its explanation → next paragraph → next chart with its explanation → etc., the way a newspaper article alternates body copy and pull-quotes / figures. That is a layout/structure decision, not just prose voice. Three options for where this lands:
   - **(7a) No editor.** Ship Cycle D as one-shot synthesizer-with-newspaper-prompt; rely on the synthesizer to weave chart references inline. Cheapest. Bet: a tight prompt + a good model gets ~90% of the way.
   - **(7b) Editor as a Cycle D variant** — synthesizer drafts grounded prose, an editor LLM rewrites for voice + interleaves chart explanations between paragraphs. Numeric verifier sits between the two passes. 2× LLM cost on the synthesis step; cleaner separation of concerns; unlocks per-tier tone iteration on the editor side without re-tuning the grounding prompt. Aligns with the user-memory directive `project_llm_guardrails.md` (loosen LLM invocation to generate training signal).
   - **(7c) Deferred Cycle E.** Ship Cycle D one-shot first; if browser smoke shows the response still feels like "paragraph + 5 charts in a row," add the editor pass as a follow-on cycle. Cost/latency bet tied to a measured quality gap rather than added speculatively.
   The post-Cycle-6-item-1 manifest now records every LLM call, so by the time Cycle D ships we'll have visibility on whether the one-shot synthesizer is producing newspaper-quality prose or close-but-not-quite. Recommendation leans toward (7c) but the decision belongs to the start of Cycle D, not now.

---

## Cross-references

- Phase 2 handoff plan: [OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md). Phase 2 closed 2026-04-25.
- Layer 4 (Representation Agent) target description: [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 4.
- Existing chart registry: [`briarwood/representation/charts.py`](briarwood/representation/charts.py).
- Representation Agent: [`briarwood/representation/agent.py`](briarwood/representation/agent.py) and [`briarwood/representation/README.md`](briarwood/representation/README.md).
- Layer 3 LLM synthesizer: [`briarwood/synthesis/llm_synthesizer.py`](briarwood/synthesis/llm_synthesizer.py) (the prompt to retune in Cycle D).
- React chart components: [`web/src/components/chat/`](web/src/components/chat/).
- Audit's "Charts don't explain" finding: [AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §4.

---

## Definition of done for the presentation fix

The whole Phase 3 effort is done when:

1. Every active chart kind renders with a chart title, axis titles (with units), and a legend or annotation. No more "designed by an LLM" feel.
2. A first-impression BROWSE turn fires ≤ 3 charts, with `market_trend` (town-level ZHVI) as one of them.
3. Each rendered chart has a 1-line caption explaining why it's there (sourced from the Representation Agent's `claim` field).
4. The synthesizer's prose explicitly references at least one chart by what the user sees, so chart and prose tie together.
5. The synthesizer's output reads top-down with a headline lead, structured beats (Headline / Why / What's Interesting / What I'd Watch), and the user wants to keep clicking.
6. The "Briarwood beats plain Claude on underwriting" qualitative bar from Phase 2 holds — the visual + narrative substrate together is now better than what plain Claude (no charts, no Briarwood data) can produce.
7. All changes traced to FOLLOW_UPS / DECISIONS / this plan. No drive-by fixes.
8. README discipline maintained. Each contract change has a dated changelog entry on the affected README.
9. Tests pass. No regressions in `tests/representation/`, `tests/synthesis/`, `tests/agent/test_dispatch.py`.

---

## Notes for the next agent

- **The user is visual and prefers iterating in the browser.** Don't skip the verification pause between cycles — the user's qualitative read is the truth-source for both chart and prose quality.
- **Don't over-spec; iterate.** The first system-prompt tune in Cycle D will likely need 2-3 iterations. Plan for it.
- **Leverage what already exists.** Cycle B's `market_trend` chart needs no new module work — `market_value_history` already runs. Cycle C's chart-narration uses the Representation Agent's existing `claim` field. The architectural cycles touch behavior, not new infrastructure.
- **Drift prevention.** This file lives at the repo root parallel to OUTPUT_QUALITY_HANDOFF_PLAN.md and is cross-referenced from DECISIONS.md and FOLLOW_UPS.md so future agents discover it via the standard orientation flow.
- **Ordering is locked.** Polish → Select → Narrate → Prose. The user confirmed this sequence 2026-04-25.

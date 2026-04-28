# Phase 4c — BROWSE Summary Card Rebuild (Handoff Plan)

**Status:** APPROVED 2026-04-28 (owner sign-off after the 2026-04-28
three-section newspaper-hierarchy reframe). Cycle 1 ready to start. No
cycles landed.
**Owner:** Zach
**Origin:** 2026-04-26 BROWSE walkthrough Thread 1; parking-lot entry at
[`ROADMAP.md`](ROADMAP.md) §3.5; sequence step 6 of [`ROADMAP.md`](ROADMAP.md)
§1, unblocked 2026-04-28 by Phase 4a (real comps), Phase 4b (Scout drilldown
surface), and AI-Native Foundation Stage 4 (model-accuracy loop closed).
**Sequence position:** Step 6 of [`ROADMAP.md`](ROADMAP.md) §1.
**Size:** XL (5 cycles + closeout — `[size: XL]` per §3.5).
**Companion sequencing call:** [`ROADMAP.md`](ROADMAP.md) §3.4.7 — owner
2026-04-28 ruling that the chart-library evaluation belongs **inside this
handoff**, not as a separate stream ahead of it.

---

## North-star problem statement

The 2026-04-26 BROWSE walkthrough captured the visible defect: even after
Phase 2 (consolidated execution), Phase 3 (newspaper voice + intent-keyed
chart selection + chart narration), and Phase 4a/4b (real comps + Scout),
the BROWSE response still ships as **prose at top, then a vertical wall of
~10 cards plus charts**. The cards individually carry good signal, but as a
stack they read like a brain dump with a verdict pinned on the front.

**Owner reframe (2026-04-28).** The right metaphor is a newspaper front
page, not a single collapsible summary block. Newspapers achieve density
through **visual hierarchy** — section labels, sub-heads, thin rules,
generous white space — not through stacked boxed cards. Screen real estate
is expensive; the user must be able to glean as much as possible in the
first few seconds of looking. The rebuild therefore organizes the BROWSE
response into **three stacked sections inside the assistant bubble**:

1. **The Read** (always renders) — stance pill + headline + masthead chart + the synthesizer's `## Headline / ## Why` beats. This is "above the fold."
2. **Scout Finds** (conditional — only renders when Scout fires) — its own sub-head and 1–2 cards. Renders nothing when Scout returned empty. This is the peer-section placement Scout's apex framing wants ([`project_scout_apex.md`](/Users/zachanderson/.claude/projects/-Users-zachanderson-projects-briarwood/memory/project_scout_apex.md)) — Scout is not a row buried in a list of eight.
3. **The Deeper Read** (always renders, collapsed) — drilldowns into comps, value thesis, projection, rent, town, risk, confidence, recommended path. Each drilldown embeds its relevant chart inline when expanded.

Visual rhythm comes from thin section rules and typographic hierarchy, not
from stacked boxed cards. The difference between "designed by a newspaper
editor" and "designed by an LLM" is exactly this: hierarchy and
restraint, not cards-on-cards.

The substrate that makes this honest now exists:

- **Real comps** ([`CMA_HANDOFF_PLAN.md`](CMA_HANDOFF_PLAN.md), Phase 4a) — same-town SOLD comps with `listing_status` + cross-town provenance, scored through a single pipeline. The summary card body can cite specific comp rows.
- **Scout Finds drilldown surface** ([`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md), Phase 4b Cycle 3) — `ScoutFinds` React component already renders 0–2 cards with category badge, confidence%, headline, reason, and routed Drill-in buttons. It can become a first-class row inside the summary card.
- **Layer 3 LLM synthesizer with newspaper voice** ([`PRESENTATION_HANDOFF_PLAN.md`](PRESENTATION_HANDOFF_PLAN.md) Cycle D) — `synthesize_with_llm` produces `## Headline / ## Why / ## What's Interesting / ## What I'd Watch` markdown with comp-roster citation discipline.
- **Closed model-accuracy loop** ([`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md)) — the rebuild can now be evaluated against `model_alignment` rows where they exist.

Without the rebuild, the substrate's quality stops at the prose layer. The
cards beneath the prose are still the dashboard-era surface that
`docs/current_docs_index.md` explicitly calls a "compatibility surface, not
the target architecture."

---

## State of the repo at handoff

### Current BROWSE response surface — end-to-end map

`handle_browse` at [`briarwood/agent/dispatch.py:4861`](briarwood/agent/dispatch.py)
is the canonical entry. The flow is:

1. Resolve `property_id` (saved-property match → live-listing fallback → unsaved-address promotion).
2. Build `chat_tier_artifact` via `_browse_chat_tier_artifact` (the consolidated `run_chat_tier_analysis` path; produces `unified_output`).
3. Compute `cma_result`, `projection`, `strategy_fit`, `rent_outlook`, `market_history` from the artifact.
4. Build a `presentation_payload` and run a property-search to surface `neighbors`.
5. `_populate_browse_slots(...)` caches the per-view slots on the session — `last_value_thesis_view`, `last_market_support_view`, `last_projection_view`, `last_rent_outlook_view`, `last_market_history_view`, `last_unified_output`, etc.
6. Run the **Representation Agent** via `_browse_compute_representation_plan`; cache the plan on `session.last_representation_plan` (Phase 3 Cycle C).
7. Run **Scout** via `briarwood.value_scout.scout(unified, llm=llm, intent=...)`; cache `session.last_scout_insights` (Phase 4b Cycle 2 wiring + Cycle 5 dispatcher).
8. Call **`synthesize_with_llm(unified, intent, llm, charts, comp_roster, scout_insights)`** for the prose lead.
9. Return prose; the SSE adapter at [`api/pipeline_adapter.py`](api/pipeline_adapter.py) `_browse_stream_impl` reads from the cached session views and emits structured events.

The SSE event surface for a BROWSE turn (per
[`api/events.py`](api/events.py) and mirrored in
[`web/src/lib/chat/events.ts`](web/src/lib/chat/events.ts)):

`text_delta` · `verdict` · `value_thesis` · `valuation_comps` ·
`market_support_comps` · `comps_preview` · `risk_profile` · `rent_outlook` ·
`town_summary` · `strategy_path` · `trust_summary` · `scenario_table` ·
`scout_insights` · `chart` (×N — `market_trend`, `value_opportunity`,
`scenario_fan`, `cma_positioning` typically) · `research_update` ·
`comparison_table` · `map` · `listings` · `modules_ran` · `verifier_report`
· `partial_data_warning` · `grounding_annotations` · `done`.

The React side at
[`web/src/components/chat/messages.tsx`](web/src/components/chat/messages.tsx)
renders, in order:

```
PartialDataBanner
VerdictCard
GroundedText (synthesizer prose)
ScoutFinds                        ← Phase 4b Cycle 3
StrategyPathCard + drill-in
EntryPointCard (uses thesis)
ValueThesisCard + drill-in
RentOutlookCard + drill-in
TrustSummaryCard + drill-in
RiskProfileCard + drill-in
CompsTableCard (valuation) + drill-in
CompsTableCard (market_support) + drill-in
CompsPreviewCard (only when no value thesis / valuation comps / market support)
TownSummaryCard + drill-in
ScenarioTable + drill-in
ChartFrame × N (charts.map)
ResearchUpdateCard
ComparisonTable
InlineMap
PropertyCarousel
ModuleBadges
VerifierReasoningPanel (collapsed details)
FeedbackBar
CriticPanel
```

`AssistantMessage` is **tier-agnostic today** — every assistant message
runs through the same render tree regardless of `answer_type`. There is no
`answerType` / `tier` field on `ChatMessage`
([`web/src/lib/chat/use-chat.ts`](web/src/lib/chat/use-chat.ts)). This is the
load-bearing coupling that Phase 4c has to break first; otherwise any BROWSE
collapse silently deletes cards on DECISION / EDGE / PROJECTION as well.

### Substrate that makes the rebuild honest

- `chat_tier_artifact["unified_output"]` is one fully-populated `UnifiedIntelligenceOutput` per turn (Phase 2 / OUTPUT_QUALITY).
- `comp_roster` is the same comp set the `cma_positioning` chart shows ([`dispatch.py:5071-5078`](briarwood/agent/dispatch.py)).
- `synthesize_with_llm` already weaves chart references and comp citations into prose (Phase 3 Cycles C/D + CMA Phase 4a Cycle 5).
- `ScoutFinds` already maps category → drill-in route via [`web/src/lib/chat/scout-routes.ts`](web/src/lib/chat/scout-routes.ts).

### Adjacent open work that touches Phase 4c's neighborhood

Recorded so the cycle owner can flag collisions early. None of these are
Phase 4c scope.

- **Comp-store town canonicalization** (`ROADMAP.md` §4, filed 2026-04-28) — `Avon By The Sea` split into 91 + 72 spelling variants. Phase 4c reads `last_market_support_view["comps"]`; whatever rows the comp store returns are what the drilldown will show. If the rebuild surfaces the spelling split visibly (e.g., a comp drilldown that doubles up on Avon variants), flag it; do not fix it here.
- **ATTOM sale-history outcome backfill** (`ROADMAP.md` §4, filed 2026-04-28) — separate slice; Phase 4c does not consume `model_alignment` rows directly.
- **Zillow URL-intake address normalization regression** + the **`facts.town` state-suffix corruption** it produced (`ROADMAP.md` §4) — affects which saved properties have honest comp lookups. Use the already-corrected `526-w-end-ave-avon-by-the-sea-nj` and `1228-briarwood-road-belmar-nj` slugs for browser smoke; properties onboarded since the regression may not produce honest BROWSE renders.
- **Property resolver matches wrong slug ("526 West End Ave" → NC)** (`ROADMAP.md` §4 Medium) — separate; affects routing into BROWSE, not BROWSE rendering.
- **§3.4 chart umbrella** — see "Folded chart fixes" below for which chart items the rebuild absorbs as drive-bys vs. defers.

### §4 High items to flag, not pull in

`ROADMAP.md` §4 High has two items adjacent to this work. Per scope, they
stay out of Phase 4c unless analysis surfaces a hard dependency.

- **Consolidate chat-tier execution: one plan per turn, intent-keyed module set** — landed in substance via Phase 2 (`run_chat_tier_analysis`); the remaining slices (`MODULE_CACHE_FIELDS leaky`, `in_active_context not safe under concurrent thread-pool callers`) are unrelated to the BROWSE render surface. **No dependency.**
- **Layer 3 LLM synthesizer: prose from full `UnifiedIntelligenceOutput`** — landed via [`briarwood/synthesis/llm_synthesizer.py`](briarwood/synthesis/llm_synthesizer.py) (Phase 2 Cycle 4 + Phase 3 Cycles C/D + CMA 4a Cycle 5). The synthesizer is the prose lead the rebuild keeps; no further synthesizer changes are required for Phase 4c. **No dependency.**

### Folded chart fixes (drive-bys allowed in cycles that touch the same files)

`ROADMAP.md` §3.4 explicitly designates Phase 4c as a legitimate landing
site for some of its sub-items ("Out of scope for any specific cycle today;
pick up in this umbrella or as a drive-by fix during Phase 4c BROWSE
rebuild"). The plan absorbs these where the diff is in the same file:

| §3.4 item | Phase 4c handling | Why |
|-----------|-------------------|-----|
| §3.4.1 — `cma_positioning` "CHOSEN COMPS: Context only" chip + retire `feeds_fair_value` | **Cycle 2 drive-by** | Cycle 2 owns the comps drilldown that embeds `cma_positioning`; the chip + the dead-architecture flag live in the same chart-frame file. |
| §3.4.2 — `value_opportunity` y-axis label vertical character stack | **Cycle 5 (chart-lib eval)** OR drive-by during whichever cycle touches `chart-frame.tsx` | The bug is in SVG axis-label rendering; if Cycle 5's eval recommends a switch, this disappears with the migration. |
| §3.4.3 — `cma_positioning` chart-prose alignment (top-8 vs top-10 roster mismatch) | **Cycle 2 drive-by** | One-line clamp on `comp_roster` to mirror the chart's slice; Cycle 2 owns the comp surface. |
| §3.4.4 — Live SSE rendering requires page reload | **Watch-item** | The rebuild may worsen, fix, or sidestep this. Fold a fix only if the rebuild's render path exposes a clean repro. Otherwise it stays a §3.4 umbrella item. |
| §3.4.5 — `cma_positioning` source-view drift (multi-view chart) | **Defer** | Already partial-resolved 2026-04-26 with a defensive fix; the suggested structural follow-on (`secondary_source_view`) is broader than Phase 4c needs. |
| §3.4.6 — Chart marker diversity / utilitarian styling | **Cycle 5 (chart-lib eval)** | Premium-feel styling is the chart-library decision, not the layout decision. |
| §3.4.7 — Evaluate React-native charting library | **Cycle 5** | This is the location the 2026-04-28 owner sequencing call placed it. Eval only — migration deferred. |

---

## Open design decisions — to resolve at cycle start

1. **Tier marker on `ChatMessage`.** The cleanest signal is to extend the existing `message` SSE event in [`api/events.py:73`](api/events.py) with an optional `answer_type: str` field, mirror in [`web/src/lib/chat/events.ts:10`](web/src/lib/chat/events.ts), and persist it on `ChatMessage`. Alternative: a new `turn_meta` event. **Recommendation:** extend `message`. Minimal protocol surface, matches AGENTS.md "every new SSE event mirrored in TS" rule. Resolve at Cycle 1 start.
2. **Masthead chart placement.** Three options: (a) `market_trend` chart inside Section A ("The Read") between the headline and the prose body; (b) `market_trend` between the headline and the prose lead, with everything else moved into Section C drilldowns; (c) no masthead chart at all — `market_trend` becomes a Town drilldown only. **Recommendation:** (a). The market_trend chart is the context-setter for the verdict (per Phase 3 Cycle B); putting it inside Section A keeps the "above the fold" content visually rich and matches the newspaper reframe (lead photo / chart appears at the top of the lead story). Resolve at Cycle 1 start.
3. **Drilldown affordance.** Inside Section C, drilldowns can be (a) chevron-led list rows (lightest, newspaper-feel), (b) accordion items with shaded backgrounds, (c) cards with their own borders. **Recommendation:** (a) — chevron + sub-head + summary chip on a thin rule; expand inline. (b) and (c) reintroduce the boxed-card stack the rebuild is moving away from. Resolve at Cycle 3 start.
4. **Drilldown expansion behavior.** Open multiple at once, or accordion (one open at a time)? **Recommendation:** independent expansion (multiple may be open). The user wants to compare across drilldowns (e.g., scout reasoning + the comps it cites); accordion forces re-clicking. State is local-only. Resolve at Cycle 3 start.
5. **Mobile vs. desktop.** Briarwood is a decision-tier surface used at desktop. **Recommendation:** desktop is the primary design target; mobile renders the same sections, single-column. Do not invest in custom mobile breakpoints in Phase 4c. Resolve at Cycle 1 start.
6. **`PRESENTATION_HANDOFF_PLAN.md` Open Design Decision #7 — editor pass.** The 2026-04-26 framing was that the layout problem (paragraph + 5 charts in a row) was conflated with the prose problem. The rebuild solves the **layout** structurally — three stacked sections with newspaper-style hierarchy, charts moved inside their relevant section — without touching prose. **Recommendation:** close OD #7 as **(7c) — deferred indefinitely**; the rebuild itself addresses the visible layout complaint. If post-Cycle-5 browser smoke shows the prose still feels list-y once layout is fixed, file an editor pass as a fresh handoff (not a Phase 4c follow-on). Resolve at Cycle 4 start when the layout is visible end-to-end. The closure goes in `DECISIONS.md`.
7. **`StrategyPathCard` fate.** Becomes a drilldown row inside Section C ("Recommended path"), OR absorbed into Section A's headline (since the strategy path is effectively "the recommendation"), OR retired in favor of the synthesizer prose's `## What's Interesting` / `## What I'd Watch` beats. **Recommendation:** drilldown row in v1 (lowest behavior change); absorb-or-retire is a follow-on after browser smoke. Resolve at Cycle 4 start.
8. **Component naming.** The three sections need names. **Recommendation:** `BrowseRead` (Section A), `BrowseScout` (Section B), `BrowseDeeperRead` (Section C). A shared `BrowseSection` primitive renders the sub-head + rule + content slot. Naming follows the `ScoutFinds` placeholder convention from Phase 4b Cycle 3 — rename when the product brand finalizes per `project_brand_evolution.md`. Resolve at Cycle 1 start.

---

## Layout target — what the user sees on a BROWSE turn

Three stacked sections inside the assistant bubble, separated by thin
rules and section sub-heads. No nested boxed cards — newspaper-style
hierarchy.

```
┌────────────────────────────────────────────────────────────────────┐
│  PartialDataBanner (warnings; only when present)                  │
│                                                                    │
│  ┌─ Section A: BrowseRead ────────────────────────────────────┐   │
│  │  THE READ                                       [sub-head] │   │
│  │  ───────────────────────────────────────────────────────── │   │
│  │  [stance pill]  $1.49M ask · $1.31M fair value · BUY      │   │
│  │                                                             │   │
│  │  Headline-style first sentence (synth ## Headline beat).   │   │
│  │                                                             │   │
│  │  [chart: market_trend — Belmar town ZHVI line]             │   │
│  │                                                             │   │
│  │  Body paragraphs (synth ## Why + remaining beats — flowed  │   │
│  │  prose, no per-beat headers visible to user).              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌─ Section B: BrowseScout (conditional) ─────────────────────┐   │
│  │  WHAT YOU'D MISS                                [sub-head] │   │
│  │  ───────────────────────────────────────────────────────── │   │
│  │  Subtitle: "Angles you didn't ask about"                   │   │
│  │                                                             │   │
│  │  [Scout card 1: category badge · confidence% · headline ·  │   │
│  │   reason · Drill-in →]                                     │   │
│  │  [Scout card 2: same shape, only when 2 insights]          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ↑ when scout_insights is empty / null, ENTIRE Section B is null   │
│    no placeholder, no header, no rule — section disappears         │
│                                                                    │
│  ┌─ Section C: BrowseDeeperRead ──────────────────────────────┐   │
│  │  THE DEEPER READ                                [sub-head] │   │
│  │  ───────────────────────────────────────────────────────── │   │
│  │  ▸ Comps                  5 SOLD + 3 ACTIVE       [chevron]│   │
│  │  ▸ Value thesis           $1.31M · 5.3% APE       [chevron]│   │
│  │  ▸ Projection             5y range $X – $Y        [chevron]│   │
│  │  ▸ Rent                   $X gross · Y% yield     [chevron]│   │
│  │  ▸ Town context           3y +12%                 [chevron]│   │
│  │  ▸ Risk                   3 flags                 [chevron]│   │
│  │  ▸ Confidence & data      band · gaps             [chevron]│   │
│  │  ▸ Recommended path       hold-to-rent            [chevron]│   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Each drilldown, expanded, embeds:                                │
│   - the relevant chart (comps → cma_positioning,                  │
│     projection → scenario_fan, risk → risk_bar, rent → rent_burn /│
│     rent_ramp, value thesis → value_opportunity)                  │
│   - the structured card content (CompsTableCard, ScenarioTable…) │
│   - any drill-in InlinePrompt the existing surface offers         │
│                                                                    │
│  ResearchUpdateCard / ComparisonTable / InlineMap /               │
│    PropertyCarousel    (kept as-is — context, not summary)        │
│  ModuleBadges                                                     │
│  VerifierReasoningPanel (collapsed, dev-facing)                   │
│  FeedbackBar                                                      │
│  CriticPanel (dev-facing)                                         │
└────────────────────────────────────────────────────────────────────┘
```

**Visual rhythm — the newspaper spec.**
- Section sub-heads in `THE READ` / `WHAT YOU'D MISS` / `THE DEEPER READ` style: small caps or uppercase tracking, distinct typographic weight from body prose. They are section labels, not card titles.
- Sections separated by a 1px rule (`border-t border-[var(--color-border-subtle)]`) and ~2rem of vertical padding. No nested borders.
- Section C's drilldown rows are list items separated by 1px rules between rows, not boxed cards. Chevron + label + summary chip + clickable header. Expanded body indents under the label and keeps the same rule separators.
- Inside an expanded drilldown, the embedded chart and the structured card content render with **no extra border** — they are the section content, not a card-in-a-card.

DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP turns continue
to render the **existing card stack** unchanged. The section-stack rebuild
is BROWSE-only because BROWSE is the "first-impression analyst" tier whose
substrate is wide and whose user is making a six-figure decision; the other
tiers already focus on a narrower slice.

---

## Retired-vs-section component map

For BROWSE only. Items not listed stay as-is.

| Today's component (BROWSE) | Phase 4c handling | Lands in |
|----------------------------|-------------------|----------|
| [`VerdictCard`](web/src/components/chat/verdict-card.tsx) | **Absorbed** into Section A header (stance pill becomes the section's lead chip) | Section A — The Read |
| [`GroundedText`](web/src/components/chat/grounded-text.tsx) | **Keep** as Section A's body prose | Section A — The Read |
| [`ChartFrame`](web/src/components/chat/chart-frame.tsx) — `market_trend` | **Inside Section A** between headline and body prose (masthead) | Section A — The Read |
| [`ScoutFinds`](web/src/components/chat/scout-finds.tsx) | **Renders inside Section B** with its existing 0/1/2 cards; the section as a whole renders null when scout returned empty | Section B — Scout Finds |
| [`EntryPointCard`](web/src/components/chat/entry-point-card.tsx) | **Absorbed** into Value-thesis drilldown body | Section C drilldown — "Value thesis" |
| [`ValueThesisCard`](web/src/components/chat/value-thesis-card.tsx) | **Absorbed** into Value-thesis drilldown body | Section C drilldown — "Value thesis" |
| [`ChartFrame`](web/src/components/chat/chart-frame.tsx) — `value_opportunity` | **Inside Value-thesis drilldown** | Section C drilldown — "Value thesis" |
| [`CompsTableCard`](web/src/components/chat/cma-table-card.tsx) (valuation variant) | **Absorbed** into Comps drilldown body | Section C drilldown — "Comps" |
| [`CompsTableCard`](web/src/components/chat/cma-table-card.tsx) (market_support variant) | **Absorbed** into Comps drilldown body | Section C drilldown — "Comps" |
| [`CompsPreviewCard`](web/src/components/chat/comps-preview-card.tsx) | **Absorbed** into Comps drilldown (fallback when value thesis absent) | Section C drilldown — "Comps" |
| [`ChartFrame`](web/src/components/chat/chart-frame.tsx) — `cma_positioning` | **Inside Comps drilldown** | Section C drilldown — "Comps" |
| [`ScenarioTable`](web/src/components/chat/scenario-table.tsx) | **Absorbed** into Projection drilldown body | Section C drilldown — "Projection" |
| [`ChartFrame`](web/src/components/chat/chart-frame.tsx) — `scenario_fan` | **Inside Projection drilldown** | Section C drilldown — "Projection" |
| [`RentOutlookCard`](web/src/components/chat/rent-outlook-card.tsx) | **Absorbed** into Rent drilldown body | Section C drilldown — "Rent" |
| [`ChartFrame`](web/src/components/chat/chart-frame.tsx) — `rent_burn` / `rent_ramp` | **Inside Rent drilldown** | Section C drilldown — "Rent" |
| [`TownSummaryCard`](web/src/components/chat/town-summary-card.tsx) | **Absorbed** into Town drilldown body | Section C drilldown — "Town context" |
| [`RiskProfileCard`](web/src/components/chat/risk-profile-card.tsx) | **Absorbed** into Risk drilldown body | Section C drilldown — "Risk" |
| [`ChartFrame`](web/src/components/chat/chart-frame.tsx) — `risk_bar` | **Inside Risk drilldown** | Section C drilldown — "Risk" |
| [`TrustSummaryCard`](web/src/components/chat/trust-summary-card.tsx) | **Absorbed** into Confidence drilldown body | Section C drilldown — "Confidence & data" |
| [`StrategyPathCard`](web/src/components/chat/strategy-path-card.tsx) | **Drilldown** in v1; revisit absorb-or-retire post-smoke (OD #7) | Section C drilldown — "Recommended path" |
| [`ResearchUpdateCard`](web/src/components/chat/research-update-card.tsx) | **Keep** at end (not part of the three sections) | After Section C |
| [`ComparisonTable`](web/src/components/chat/comparison-table.tsx) | **Keep** | After Section C |
| [`InlineMap`](web/src/components/chat/inline-map.tsx) | **Keep** | After Section C |
| [`PropertyCarousel`](web/src/components/chat/property-carousel.tsx) | **Keep** | After Section C |
| [`ModuleBadges`](web/src/components/chat/module-badges.tsx) | **Keep** | After Section C |
| `VerifierReasoningPanel` (inline in messages.tsx) | **Keep** (dev-facing) | After Section C |
| `FeedbackBar` (inline in messages.tsx) | **Keep** | After Section C |
| `CriticPanel` (inline in messages.tsx) | **Keep** (dev-facing) | After Section C |
| `PartialDataBanner` (inline in messages.tsx) | **Keep** at top, above all sections | Above Section A |

No component file is **deleted** in Phase 4c — all card components remain
exported for DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP
to render. They are simply not rendered as a stack when
`ChatMessage.answerType === "browse"`; instead, BROWSE composes them inside
the three sections' bodies. If a component proves orphaned across all
tiers after Phase 4c, file a §4 cleanup entry; do not delete in scope here.

---

## Cycles

### Cycle 1 — Tier marker + section primitive + Section A ("The Read")

**Goal.** Land the BROWSE-only render gate, the shared section primitive,
and the first fully-filled section so the newspaper feel is visible from
Cycle 1's browser smoke. Section B and Section C ship as empty stubs at
this point — the existing card stack still renders below the stubs so the
turn is functionally complete.

**Scope:**
- Extend the `message` SSE event in [`api/events.py:73`](api/events.py) with an optional `answer_type: str | None` field. Mirror in [`web/src/lib/chat/events.ts:10`](web/src/lib/chat/events.ts) per AGENTS.md SSE-parity rule.
- Wire the field on the server side at the message-event emit site so a BROWSE turn carries `answer_type: "browse"`. (Inspect `api/pipeline_adapter.py` for the emit site; do not change non-BROWSE handlers.)
- Add `answerType?: string` to `ChatMessage` in [`web/src/lib/chat/use-chat.ts:33`](web/src/lib/chat/use-chat.ts); update the reducer's `case "message"` arm to capture it.
- Create `web/src/components/chat/browse-section.tsx` — the shared primitive: sub-head label (uppercase tracking) + 1px top rule + content slot + ~2rem vertical padding. No background, no nested border. The newspaper-rule visual rhythm lives here.
- Create `web/src/components/chat/browse-read.tsx` — `BrowseRead` (Section A). Renders:
  - Stance pill (absorbed from `VerdictCard` — reuse the verdict event payload).
  - 1-line headline: `$1.49M ask · $1.31M fair value · BUY` style.
  - `market_trend` chart embedded inline (OD #2 default).
  - The synthesizer's prose (existing `GroundedText` component, just relocated inside Section A).
- Create `web/src/components/chat/browse-scout.tsx` — `BrowseScout` (Section B). Empty stub for Cycle 1: returns null.
- Create `web/src/components/chat/browse-deeper-read.tsx` — `BrowseDeeperRead` (Section C). Empty stub for Cycle 1: renders just the section sub-head and a "_Drilldowns coming in Cycles 2–4_" placeholder line so the gate is visible.
- Modify `AssistantMessage` in [`web/src/components/chat/messages.tsx`](web/src/components/chat/messages.tsx): when `answerType === "browse"`, render `<BrowseRead /> <BrowseScout /> <BrowseDeeperRead />` and SKIP the existing `VerdictCard`, `GroundedText` (it's now inside `BrowseRead`), `ScoutFinds`, the card stack (StrategyPathCard through ScenarioTable), and the trailing `charts.map`. Keep `PartialDataBanner`, `ResearchUpdateCard`, `ComparisonTable`, `InlineMap`, `PropertyCarousel`, `ModuleBadges`, `VerifierReasoningPanel`, `FeedbackBar`, `CriticPanel` rendering as today (above and below the three sections per the layout target).
- The existing card stack is fully gated off on BROWSE in Cycle 1 — even though Sections B/C are stubs. The user sees Section A fully filled, then a placeholder for Section C, then peripherals. This is intentional: it makes the visual hierarchy of the rebuild visible from Cycle 1, and forces the cycles 2–4 work to actually fill the sections rather than depending on the old stack as a fallback.

**Tests:**
- Python: extend pipeline-adapter contract test for the new `answer_type` field on the `message` event.
- TypeScript: `tsc --noEmit` clean. ESLint clean. `next build` clean.

**Verification (BROWSER):**
- Canonical query: "what do you think of 1228 Briarwood Rd, Belmar, NJ" against `1228-briarwood-road-belmar-nj`.
- Expected: stance pill + headline + `market_trend` chart + flowed prose under a `THE READ` sub-head; no Section B (stub returns null); a `THE DEEPER READ` sub-head with placeholder line. Below: ResearchUpdateCard, ModuleBadges, FeedbackBar etc. render as today. The full pre-rebuild card stack is GONE on BROWSE turns.
- DECISION turn ("should I buy 1228 Briarwood Rd, Belmar, NJ"): renders the existing card stack unchanged — verifies the tier gate works.
- Pause for owner review. Phase 4b Cycle 3 caveat applies: first BROWSE turn after a fresh `dev_chat.py` boot may need a hot-reload pass before the new component bundles in.

**Open Design Decisions to resolve at start:** #1 (tier marker mechanism), #2 (masthead chart placement — recommend Section A), #5 (mobile posture), #8 (component naming).

**Trace.** ROADMAP §3.5; owner reframe 2026-04-28 (newspaper hierarchy); user-memory `project_ui_enhancements.md` (weak decision summary).

**Estimate:** 8–12 LLM-development-minutes — the section primitive + Section A composition is meatier than a pure scaffold cycle.
**Risk:** Medium-High — Cycle 1 is the most visible cycle because Section A ships fully filled. The tier-gate plus the visible newspaper feel both have to land cleanly. Worth the front-loaded risk because the user can read the rebuild's intent from Cycle 1's browser smoke and redirect early if the visual approach is off.

---

### Cycle 2 — Section B: Scout Finds peer section

**Goal.** Section B fills in. Scout migrates from its current position
(under prose, above card stack) into a peer section with its own sub-head.
Section B renders null when scout returned empty, full-section when it
fired.

**Scope:**
- Fill `BrowseScout` (Section B). When `message.scoutInsights` is non-empty: render the section sub-head (`WHAT YOU'D MISS` or similar — owner picks at cycle start), a 1-line subtitle (existing `ScoutFinds` subtitle "Angles you didn't ask about"), and the existing `ScoutFinds` component's 0/1/2 cards inside the section body. When `message.scoutInsights` is empty / null: return null. The entire section disappears — no sub-head, no rule, no placeholder.
- The existing `ScoutFinds` component is reused as-is for the card-rendering bit. Cycle 2 changes its **placement** (now inside Section B), not its internals. The `category → drill-in` routing in `web/src/lib/chat/scout-routes.ts` continues to work without change.
- Section sub-head label is owner-pickable at cycle start. Default proposal: `WHAT YOU'D MISS`. Alternatives: `BRIARWOOD NOTICED`, `WORTH A CLOSER LOOK`. Pick at Cycle 2 start; no DECISIONS.md entry needed (UI label, not architectural).

**Tests:**
- TypeScript: `tsc --noEmit` / `next build` / ESLint clean.
- No new Python tests — pure frontend recomposition.

**Verification (BROWSER):**
- BROWSE turn for a property where scout fires (likely `1228-briarwood-road-belmar-nj` or `526-w-end-ave-avon-by-the-sea-nj`): Section B renders between Section A and Section C with sub-head + cards.
- BROWSE turn for a property where scout returns empty: Section B is invisible — Section A flows directly into Section C with no gap chrome.
- Drill-in buttons inside the scout cards still emit the right follow-up prompts.
- Pause for owner review.

**Trace.** ROADMAP §3.5; SCOUT_HANDOFF_PLAN Cycle 3 (ScoutFinds shape); owner reframe 2026-04-28 (Scout as peer section, not buried row).

**Estimate:** 3–5 LLM-development-minutes.
**Risk:** Low. Composition over an existing component; the conditional render is the only logic.

---

### Cycle 3 — Section C drilldowns: Comps + Value-thesis + Projection

**Goal.** First three drilldowns inside Section C — the highest-evidence-density
trio. Drilldown affordance (chevron list rows on rules — OD #3) is locked
this cycle.

**Scope:**
- Add a `BrowseDrilldown` primitive inside Section C: chevron + label + summary chip on a 1px rule; expand inline; independent open/close state per drilldown (OD #4 — multiple may be open). No nested borders, no boxed cards. The visual idea is a list of section anchors, not stacked cards.
- "Comps" drilldown. Summary chip uses real provenance — e.g. `5 SOLD + 3 ACTIVE` (or `5 SOLD (2 cross-town) + 3 ACTIVE`) sourced from `last_market_support_view["comps"]` per the §3.4.1 chip retire-and-replace plan. Expanded body:
  - 1 sentence editorial blurb naming a specific comp (sourced from synthesizer prose if the synth cited one, otherwise rendered from the top comp row).
  - `CmaPositioningChart` embedded inline (no border).
  - `CompsTableCard` (valuation variant) and `CompsTableCard` (market_support variant) below the chart.
- "Value thesis" drilldown. Summary chip: fair-value · alignment band. Expanded body:
  - `EntryPointCard` content + `ValueThesisCard` content, merged.
  - `ValueOpportunityChart` embedded inline.
- "Projection" drilldown. Summary chip: 5y range (low–high). Expanded body: `ScenarioTable` content + `ScenarioFanChart`.
- Drive-by absorbs **§3.4.1** (`feeds_fair_value` retirement + "CHOSEN COMPS: Context only" chip → `Comp set` chip with real provenance) and **§3.4.3** (clamp `comp_roster` slice to chart's top-N — same files).
- Existing `InlinePrompt` "Drill into …" buttons attached to each card today (e.g., "Why were these comps chosen?" / "What would change your value view?" / "Show me the downside case in more detail") attach to each drilldown's expanded body so the conversation follow-ups continue to work.

**Tests:**
- Python: regression test that `_native_cma_chart`'s `spec.comps` no longer projects `feeds_fair_value` (per §3.4.1 retirement). Update fixtures in `tests/test_pipeline_adapter_contracts.py` and `tests/agent/test_dispatch.py`.
- TypeScript: `tsc --noEmit` / `next build` / ESLint clean.

**Verification (BROWSER):**
- BROWSE turn for a property with non-empty CMA: Section C now shows three expandable drilldowns. Comps reads `5 SOLD + 3 ACTIVE` (not `Context only`); expanding it shows the embedded `cma_positioning` chart with no `Context only` chip; valuation + market-support comps tables render below. Value-thesis and Projection drilldowns expand cleanly with their embedded charts.
- Multiple drilldowns can be open at once.
- Drill-in InlinePrompts still emit the right follow-up prompt when clicked.
- Pause for owner review.

**Open Design Decisions to resolve at start:** #3 (drilldown affordance — lock to chevron list rows on rules), #4 (independent vs. accordion expansion — lock to independent).

**Trace.** ROADMAP §3.5 (drilldown integration); §3.4.1 (chip + flag retirement); §3.4.3 (chart-prose alignment).

**Estimate:** 8–12 LLM-development-minutes (drilldown primitive + three drilldowns + fixture updates).
**Risk:** Medium. The drilldown affordance has to feel right — too card-y and the rebuild slides back into the boxed-stack problem; too flat and the drilldowns blend into Section A's prose. Owner browser review is the gate.

---

### Cycle 4 — Section C drilldowns: Rent + Town + Risk + Confidence + Path; OD #6 closure

**Goal.** Section C fills out completely. Phase 4c becomes a complete
visible product after Cycle 4. OD #6 (editor-pass closure) and OD #7
(StrategyPathCard fate) resolve at cycle start once the layout is fully
visible.

**Scope:**
- "Rent" drilldown. Summary chip: gross rent estimate · yield. Expanded body: `RentOutlookCard` content + `RentBurnChart` + `RentRampChart`.
- "Town context" drilldown. Summary chip: 3y change% (already on the synthesizer's market_trend grounding). Expanded body: `TownSummaryCard` content. The `market_trend` chart stays in Section A — it does not also live inside this drilldown (avoid double-render).
- "Risk" drilldown. Summary chip: count of flags / dominant flag. Expanded body: `RiskProfileCard` content + `RiskBarChart`.
- "Confidence & data" drilldown. Summary chip: confidence band. Expanded body: `TrustSummaryCard` content (and the partial-data warnings if any are present for this turn — moved off the top banner if Cycle 4 owner review wants that consolidation; otherwise keep PartialDataBanner at top).
- "Recommended path" drilldown (`StrategyPathCard` absorbed per OD #7 v1).
- Resolve OD #6 (editor-pass closure). The rebuilt layout is what `PRESENTATION_HANDOFF_PLAN.md` Open Design Decision #7 was waiting on; Cycle 4 is the visible point at which the call can be made. Recommended closure: **(7c) deferred indefinitely** — rebuild solves the layout complaint structurally; revisit only if post-Cycle-5 browser smoke shows residual list-y prose. Record the closure in `DECISIONS.md` at Cycle 4 close.
- Resolve OD #7 (StrategyPathCard fate). Recommended: keep as drilldown in v1; absorb-or-retire is post-smoke.

**Tests:**
- TypeScript: `tsc --noEmit` / `next build` / ESLint clean.
- React: visual smoke + component-level snapshot only if a JS test framework lands first (out of scope per Phase 4b Cycle 3 precedent).

**Verification (BROWSER):**
- BROWSE turn: full target layout renders. All eight drilldowns reachable; each cites real evidence; charts embed cleanly inside Comps / Value-thesis / Projection / Rent / Risk drilldowns.
- Compare side-by-side with the pre-rebuild layout (a recent BROWSE turn from before Cycle 1) — the rebuild should feel like distinct sections under sub-heads, not a card stack.
- Pause for owner review (this is the heavy qualitative gate — does the rebuild feel right against the newspaper-front-page bar?).

**Open Design Decisions to resolve at start:** #6 (editor-pass closure), #7 (StrategyPathCard fate).

**Trace.** ROADMAP §3.5; PRESENTATION_HANDOFF_PLAN OD #7.

**Estimate:** 6–10 LLM-development-minutes.
**Risk:** Medium. Heaviest qualitative gate of the phase; expect 1–2 layout iterations after the first browser pass.

---

### Cycle 5 — React-native chart library evaluation

**Goal.** Per ROADMAP §3.4.7's 2026-04-28 owner sequencing call, run the
chart-library eval **inside** Phase 4c so the eval is grounded in the real
post-rebuild layout. Eval only — migration is a separate handoff. The
owner's 2026-04-28 reframe explicitly preserves the eval as Phase 4c
scope ("a chart library that is very easy to understand within seconds";
the *update* is later).

**Scope:**
- Build `cma_positioning` (the highest-stakes chart per §3.4.7) end-to-end in **two or three** candidate libraries against the same Belmar dataset. Default candidates (per §3.4.7): Recharts, Apache ECharts (`echarts-for-react`), Nivo. Use the dataset that's already flowing through `_native_cma_chart` for `1228-briarwood-road-belmar-nj` so the eval is comparable to today's iframe-Plotly render.
- Compare on: (a) visual quality at default, (b) visual quality after ~30 LLM-development-minutes of polish, (c) code volume, (d) hover / animation affordances, (e) ability to co-render with surrounding React state (drilldown chip can hover-sync with chart marker), (f) bundle weight delta from `next build` output, (g) **glance-readability — can a user understand the chart's verdict in 2-3 seconds?** (this gating criterion is added per the owner reframe: chart library that's very easy to understand within seconds is the explicit target).
- Produce a **recommendation memo** at the repo root: `docs/CHART_LIBRARY_EVAL_2026-MM-DD.md`. The memo names a recommended library or recommends staying on iframe-Plotly. Memo is the cycle deliverable; it does **not** migrate the chart catalog.
- Drive-by **§3.4.6** styling notes if the chosen library makes the marker-diversity / utilitarian-styling fixes free; otherwise leave §3.4.6 as a §3.4 umbrella item.
- Drive-by **§3.4.2** (vertical character-stack y-axis label) if (a) the recommendation is to switch (the bug disappears in the new library) OR (b) the eval cycle touches `chart-frame.tsx`'s `AxisLabels` helper. Otherwise leave for §3.4.

**Tests:**
- The eval libraries are sandbox-only — no production wiring in this cycle. Place prototypes under `web/src/components/chat/_eval/` (clearly throwaway). `tsc --noEmit` / ESLint / `next build` clean.

**Verification (BROWSER):**
- Side-by-side screenshots of `cma_positioning` rendered in each candidate library + the current iframe-Plotly version, on the same Belmar dataset. Owner reviews and picks (or rejects all and stays on Plotly).
- Pause for owner decision.

**Open Design Decisions to resolve at end of cycle:** the library choice itself.

**Trace.** ROADMAP §3.4.7; user-memory `project_ui_enhancements.md` ("charts need work, revisit post-grounding"); owner reframe 2026-04-28 ("very easy to understand within seconds").

**Estimate:** 30–60 LLM-development-minutes for the eval prototypes per §3.4.7; iteration time on top depends on owner review pace.
**Risk:** Low-Medium. Eval is sandboxed; the risk is the owner deciding to migrate, in which case a fresh handoff plan opens after Cycle 5 closes (NOT folded into Phase 4c).

---

### Cycle 6 — Closeout

**Goal.** Reconcile docs, mark Phase 4c complete, surface follow-ups.

**Scope:**
- Update [`ROADMAP.md`](ROADMAP.md):
  - §1 step 6 → `✅ RESOLVED YYYY-MM-DD — BROWSE_REBUILD_HANDOFF_PLAN.md` with one-paragraph outcome (mirror the §1 step 5 Stage 4 outcome shape).
  - §3.5 → Status flipped to `✅ RESOLVED`; cycles 1–5 outcomes appended; plan-doc link updated.
  - §3.4.1 / §3.4.3 / any other §3.4 sub-items absorbed → marked `✅ RESOLVED YYYY-MM-DD — Phase 4c Cycle N` with cross-reference (preserved in section, not deleted, per the resolved-stays convention).
  - §3.4.7 (chart-library eval) → marked `✅ RESOLVED YYYY-MM-DD — Phase 4c Cycle 5 produced eval memo` (whether owner picked migration or stayed on Plotly is recorded as a separate ROADMAP entry if it spawns one).
  - §10 Resolved Index — append entry per existing convention.
- Update [`DECISIONS.md`](DECISIONS.md):
  - One closeout entry per cycle landed (mirror `Phase 4b Scout Cycle N landed` pattern).
  - One entry resolving `PRESENTATION_HANDOFF_PLAN.md` Open Design Decision #7 (Cycle 4 already wrote it, but Cycle 6 cross-references the closure from the Phase 4c closeout entry).
  - One entry recording the chart-library eval memo + the resulting decision.
- Update [`CURRENT_STATE.md`](CURRENT_STATE.md) — Current Known Themes section: replace the Phase 4c parking-lot reference with "Phase 4c BROWSE rebuild closed YYYY-MM-DD; …". Bump `Last Updated`.
- Update [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) — UI surface map should mention the BROWSE summary card surface and the tier-aware rendering split.
- Update [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md) — Layer 4 (Representation) note: the BROWSE response surface is no longer a "compatibility surface, not target architecture"; if Cycle 5 produced a chart-lib migration recommendation, file it as an open Layer 4 gap.
- Update [`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) — only if any new SSE event or tool surface was introduced. The tier marker (Cycle 1) is an addition to the existing `message` event, which is internal protocol, not a tool surface; document only if the chart-library eval added one.
- Update [`docs/current_docs_index.md`](docs/current_docs_index.md) — add `BROWSE_REBUILD_HANDOFF_PLAN.md` entry at plan-doc-write time (Cycle 1 launch, not Cycle 6 closeout); confirm at closeout.
- Update [`PRESENTATION_HANDOFF_PLAN.md`](PRESENTATION_HANDOFF_PLAN.md) — Open Design Decision #7: append a 1–2 line note pointing to the closure entry in `DECISIONS.md`.
- Module README updates per `.claude/skills/readme-discipline/SKILL.md` Job 3:
  - `briarwood/representation/README.md` — only if Cycle 5 changes which library renders charts (touches `_native_*_chart` contract with the React layer).
  - `briarwood/synthesis/README.md` — no change expected; the synthesizer's contract is unchanged in Phase 4c.
  - `briarwood/value_scout/README.md` — only the "UI surface" line under Role In The Six-Layer Architecture if the Scout row's location changes meaningfully.
- `web/CHART_STYLE.md` — touch only if Cycle 5 recommends a switch.

**Tests:**
- Re-run focused test gate from each cycle plus full `tests/agent/test_dispatch.py`, `tests/representation/`, `tests/synthesis/` to confirm no regression. Full-suite re-run is **optional** per Phase 4b Cycle 5/6 precedent — the pre-handoff baseline of 10 failures / 1199 tests as of 2026-04-28 is the comparison point; any change in that count is a potential regression to investigate.

**Verification:**
- Live browser smoke walkthrough on at least three properties — `1228-briarwood-road-belmar-nj`, `526-w-end-ave-avon-by-the-sea-nj`, plus one freshly-promoted live listing — to verify the rebuild holds across data shapes.
- Owner sign-off on the qualitative bar: "front-page newspaper feel; one summary card with drilldowns; user wants to keep clicking."

**Estimate:** 4–6 LLM-development-minutes for doc reconciliation.
**Risk:** Low — purely closeout.

---

## Testing strategy

Per `AGENTS.md` Verification Rules + `STAGE4_HANDOFF_PLAN.md` precedent.

- **Python.** Each cycle runs the relevant focused tests (e.g.,
  `venv/bin/python3 -m pytest tests/test_pipeline_adapter_contracts.py
  tests/agent/test_dispatch.py` for Cycle 1; comp-roster regression for
  Cycle 2; nothing new for Cycle 3). The 2026-04-28 clean-tree baseline of
  **10 failures / 1199 tests** is the comparison point; do not chase
  unrelated failures.
- **TypeScript.** Every cycle: `tsc --noEmit` clean, ESLint clean, `next
  build` clean. The repo has no Vitest/Jest framework — adding one is a
  meta-infra decision out of Phase 4c scope (matches the 2026-04-28
  Phase 4b Cycle 3 precedent).
- **Live browser smoke.** Mandatory pause after every cycle. Canonical
  query: "what do you think of 1228 Briarwood Rd, Belmar, NJ" (BROWSE) and
  "should I buy 1228 Briarwood Rd, Belmar, NJ" (DECISION — verifies that
  the tier gate works and DECISION renders the existing card stack).
  Properties to use:
  - `1228-briarwood-road-belmar-nj` — Belmar, full comp coverage
  - `526-w-end-ave-avon-by-the-sea-nj` — Avon By The Sea (post-fix town string), Stage 4 alignment row exists
  - `1008-14th-ave-belmar-nj-07719` — the SCOUT_HANDOFF_PLAN.md canonical fixture; useful for cross-handoff comparison
- **Manifest visibility.** `BRIARWOOD_TRACE=1` to confirm BROWSE-tier turn
  manifest still records `synthesis.llm`, `value_scout.scan`, and
  `representation.plan` LLM calls in their existing positions. The rebuild
  is a presentation change; LLM-call shape should not move.
- **Module-alignment regression.** Quick confidence check: the Stage 4
  `model_alignment` table for `526-w-end-ave-avon-by-the-sea-nj` should
  still produce honest rows after Phase 4c. Phase 4c does not touch the
  modules; if alignment drifts, the regression is presentation-side leakage
  (e.g., the rebuild silently dropped a comp-roster pass into the
  synthesizer) and needs to be caught immediately.

---

## Doc-update list — per-cycle

This table is the canonical list of doc touches. Cycle owners use it to
avoid forgetting a reconciliation pass; Cycle 6 verifies completeness.

| Doc | Cycle 1 | Cycle 2 | Cycle 3 | Cycle 4 | Cycle 5 | Cycle 6 |
|-----|---------|---------|---------|---------|---------|---------|
| `BROWSE_REBUILD_HANDOFF_PLAN.md` | Status header → "Cycle 1 in progress" / "landed" | Cycle 2 status flip | Cycle 3 status flip | Cycle 4 status flip + OD #6 / #7 closures recorded | Cycle 5 status flip + memo link | Final ✅ flip + plan summary at top |
| `ROADMAP.md` §1 step 6 | Promote from parking-lot ("Active, plan: BROWSE_REBUILD…") | — | — | — | — | ✅ RESOLVED |
| `ROADMAP.md` §3.5 | Status: Active | Cycle 2 outcome | Cycle 3 outcome | Cycle 4 outcome | Cycle 5 outcome | ✅ RESOLVED + cycle index |
| `ROADMAP.md` §3.4.1 / §3.4.3 | — | — | ✅ RESOLVED in Cycle 3 (drive-bys) | — | — | Verified |
| `ROADMAP.md` §3.4.2 / §3.4.6 | — | — | — | — | ✅ RESOLVED if eval covers; else preserved | Verified |
| `ROADMAP.md` §3.4.7 | — | — | — | — | ✅ RESOLVED — eval memo | Verified |
| `ROADMAP.md` §10 Resolved Index | — | — | — | — | — | Append Phase 4c entry |
| `DECISIONS.md` | Cycle 1 landed (tier marker + Section A) | Cycle 2 landed (Section B / Scout migration) | Cycle 3 landed + §3.4.1/.3 closeout note | Cycle 4 landed + OD #6 (editor pass) closure + OD #7 (StrategyPathCard) closure | Cycle 5 + chart-lib eval result | Phase 4c closeout entry |
| `CURRENT_STATE.md` | — | — | — | — | — | Themes update + bump `Last Updated` |
| `ARCHITECTURE_CURRENT.md` | UI map note (tier marker + three-section BROWSE surface) | — | — | — | If lib switch | Final reconciliation |
| `GAP_ANALYSIS.md` | — | — | — | — | If lib switch | Layer 4 note |
| `TOOL_REGISTRY.md` | — | — | — | — | If lib switch adds tool surface | Verify |
| `docs/current_docs_index.md` | Add plan entry | — | — | — | — | Verify |
| `PRESENTATION_HANDOFF_PLAN.md` | — | — | — | OD #7 cross-reference | — | Verify |
| Module READMEs | — | — | — | — | `representation/README.md` if lib switch | Verify discipline |

---

## Phase 4c success criteria

The whole phase is done when:

1. **Tier-aware rendering.** `ChatMessage.answerType === "browse"` causes the three-section layout to render in place of the existing card stack; DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP turns render the existing stack unchanged. No assistant message renders both.
2. **Three stacked sections.** A BROWSE turn shows: PartialDataBanner (when present) → Section A (`BrowseRead`: stance pill + headline + market_trend chart + flowed prose) → Section B (`BrowseScout`: only when scout fires) → Section C (`BrowseDeeperRead`: 8 drilldowns) → existing peripherals (ResearchUpdate, ComparisonTable, InlineMap, PropertyCarousel, ModuleBadges, VerifierReasoningPanel, FeedbackBar, CriticPanel).
3. **Newspaper visual hierarchy.** Sub-heads with distinct typography (uppercase tracking) on each section. Sections separated by 1px rules and ~2rem padding. No nested boxed cards; drilldowns are chevron list rows on rules, not stacked cards.
4. **Section B's conditional render is honest.** When `message.scoutInsights` is empty / null, the entire Section B is null — no sub-head, no rule, no placeholder. When scout fires, the section is a peer of Sections A and C.
5. **Real evidence in the body.** Section A's headline and each Section C drilldown chip cite real comps / real numbers from the `UnifiedIntelligenceOutput` (no placeholder stat strings).
6. **Charts inside their sections.** `market_trend` renders inside Section A. `cma_positioning`, `value_opportunity`, `scenario_fan`, `risk_bar`, `rent_burn`, `rent_ramp` render inside their relevant Section C drilldown bodies. No trailing `charts.map` block on BROWSE.
7. **Scout retains its existing affordances.** Inside Section B, the existing `ScoutFinds` component preserves category badge / confidence% / headline / reason / Drill-in routing.
8. **Open Design Decision #7 closed.** `PRESENTATION_HANDOFF_PLAN.md` OD #7 closure recorded in `DECISIONS.md`. Recommended posture: (7c) deferred indefinitely.
9. **Chart-library evaluation produced.** Cycle 5 memo at `docs/CHART_LIBRARY_EVAL_2026-MM-DD.md` names the recommendation; §3.4.7 marked resolved. Whether the recommendation is to migrate or to stay on Plotly, the **decision** is the deliverable, not the migration.
10. **No silent expansion.** DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP card stacks are unchanged. Component files are not deleted. Any orphaned components after Phase 4c are filed as a §4 cleanup entry.
11. **Doc discipline.** Per-cycle `DECISIONS.md` entries landed; ROADMAP §1 step 6 + §3.5 + §3.4.7 + absorbed §3.4 sub-items all marked ✅ in Cycle 6. Module README discipline preserved per Job 3.
12. **Tests pass.** No regressions vs. the 2026-04-28 baseline of 10 failures / 1199 tests. `tsc --noEmit` / ESLint / `next build` clean after every cycle.
13. **Owner sign-off.** Live browser smoke against three real properties confirms the qualitative bar: newspaper-front-page hierarchy; user can glean the verdict + key evidence in the first 2-3 seconds; user wants to keep clicking.

---

## Out of scope (locked)

- Frontend redesign for non-BROWSE tiers. DECISION / EDGE / PROJECTION /
  RISK / STRATEGY / RENT_LOOKUP card stacks stay as-is. Cycle 4 might
  surface that some shared components want a coordinated change; that
  belongs in a future plan.
- The chart-library **migration**. Cycle 5 produces the eval memo only;
  any migration based on it is a separate handoff with its own plan.
- ROADMAP §4 High items "Consolidate chat-tier execution" (the residual
  cache + concurrency slices) and "Layer 3 LLM synthesizer". The
  consolidated execution and the Layer-3 LLM prose both already power the
  rebuild; the residual slices are unrelated.
- ROADMAP §4 entries filed 2026-04-28: comp-store town-name
  canonicalization, ATTOM sale-history outcome backfill, Zillow URL-intake
  parser fix, property-resolver state-aware ranking. All have their own
  slices.
- Auto-tuning, prompt rewrites, model-side changes. The synthesizer's
  prompt is unchanged in Phase 4c.
- The §3.4 chart umbrella sub-items not listed in "Folded chart fixes"
  above: §3.4.4 (live SSE rendering reload bug — watch-item only), §3.4.5
  (cma_positioning multi-source-view structural follow-on — defer).
- Mobile-specific layout work beyond single-column rendering.
- A JS test framework. Vitest/Jest/RTL adoption is meta-infra (matches
  Phase 4b Cycle 3 deferral).

---

## Cross-references

- [`ROADMAP.md`](ROADMAP.md) §1 sequence step 6; §3.4 chart umbrella; §3.4.7 chart-library eval (the 2026-04-28 owner sequencing call placing it inside Phase 4c); §3.5 Phase 4c parking-lot entry.
- [`DECISIONS.md`](DECISIONS.md) 2026-04-28 entries: AI-Native Foundation Stage 4 closed; Phase 4b Scout Cycle 3 (the ScoutFinds drilldown surface this rebuild integrates); Phase 4b Scout Cycles 5–7 (the dispatcher contract).
- [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md) Cycle 3 (ScoutFinds component shape) and Cycle 5 (`scout(...)` dispatcher).
- [`PRESENTATION_HANDOFF_PLAN.md`](PRESENTATION_HANDOFF_PLAN.md) — Cycles A–D landed substrate; Open Design Decision #7 closes here.
- [`CMA_HANDOFF_PLAN.md`](CMA_HANDOFF_PLAN.md) — Phase 4a real-comp substrate the rebuild cites.
- [`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md) — closed model-accuracy loop; the rebuild does not modify alignment, but Phase 4c regressions would surface there.
- [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) UI surface map; [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md) Layer 4 (Representation Agent); [`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) chart surfaces.
- User-memory: `project_ui_enhancements.md` (weak decision summary, charts need work); `project_brand_evolution.md` (ScoutFinds naming convention model — applied to `BrowseSummaryCard` placeholder); `project_scout_apex.md` (Scout's role in the differentiated surface); `project_llm_guardrails.md` (no LLM additions in scope; numeric guardrail rule preserved through synthesizer + scout, both already wired).

---

## Boot prompt for the next Claude context window

Once this plan is approved and Cycle 1 is the active task, paste the
following into a fresh Claude Code session. CLAUDE.md orientation fires
automatically; this prompt picks up from there.

```
I'm starting Phase 4c — BROWSE summary card rebuild. The canonical plan
is BROWSE_REBUILD_HANDOFF_PLAN.md at the repo root. Current status: plan
approved YYYY-MM-DD; no cycles started.

Please:

1. Run the standard CLAUDE.md orientation: read CLAUDE.md, run the
   readme-discipline drift check, verify ARCHITECTURE_CURRENT /
   GAP_ANALYSIS / TOOL_REGISTRY are present, read DECISIONS.md (recent
   2026-04-28 entries) and ROADMAP.md §1 + §3.4 + §3.5 + §4 High items.

2. Read BROWSE_REBUILD_HANDOFF_PLAN.md end-to-end. That's the canonical
   to-do list for Phase 4c.

3. Read briarwood/agent/dispatch.py::handle_browse, briarwood/synthesis/
   llm_synthesizer.py::synthesize_with_llm, web/src/components/chat/
   messages.tsx (the assistant render tree), web/src/components/chat/
   scout-finds.tsx, and api/events.py + web/src/lib/chat/events.ts (the
   SSE protocol pair).

4. Tell me where we are in the cycle sequence (look at git log + git
   status to determine which cycles have been committed). Then tell me
   in 3-5 bullets what's been decided / what's queued / what's
   unresolved for the cycle we're about to work on.

5. Confirm: am I starting the next cycle now, or is there earlier
   work uncommitted that needs to be reviewed / committed first?

Do not begin code work until steps 1-5 are done and reported back.
```

---

## Notes for the next agent

- **The user is visual and prefers iterating in the browser.** The
  pause-for-review between cycles is mandatory, not advisory. Phase 3
  established the same cadence; honor it here.
- **Do not delete card components in scope.** Phase 4c gates them behind
  `answerType !== "browse"`; deletion is a follow-on cleanup decision.
- **The dirty-tree warning from CLAUDE.md still applies.** Multiple
  parallel sessions (Codex CLI, web Codex) are touching this repo; check
  `git log -10` and `git status` before each cycle commit.
- **Drive-bys are scoped, not free.** Only the §3.4 sub-items explicitly
  listed in "Folded chart fixes" should be picked up. Anything else gets
  filed in `ROADMAP.md` and stays out.
- **Cycle 1 is the visible setpiece.** It lands the tier marker, the
  shared section primitive, and Section A fully filled — meaning the
  newspaper feel is visible from the first browser smoke. Cycles 2–4 are
  compositional over already-emitted SSE events. If the visual approach
  is off, redirect at Cycle 1; don't wait for Cycle 4.
- **Newspaper rhythm is a constraint, not a flourish.** No nested boxed
  cards. Section sub-heads, thin rules, generous padding. If a draft
  starts looking like cards-on-cards or a card stack with a different
  border radius, stop and revisit the visual spec in the layout target
  diagram.
- **Bookend the chart-lib eval sandboxed.** Cycle 5's prototypes live
  somewhere clearly throwaway (e.g. `web/src/components/chat/_eval/`)
  and are not wired into production. The memo is the only artifact that
  ships.

# representation — Representation Agent + Chart Registry

**Last Updated:** 2026-04-28 (Phase 4c Cycle 3 — `feeds_fair_value` retired from the `cma_positioning` chart spec)
**Layer:** Representation (Layer 4)
**Status:** STABLE

## Purpose

The Representation Agent decides which charts back which verdict claims for the decision-tier surface. Given a `UnifiedIntelligenceOutput` (the routed core's verdict + evidence) and a dict of session "module views" (e.g., `last_projection_view`, `last_risk_view`), it produces a `RepresentationPlan` — an ordered list of `RepresentationSelection` triples, each binding a claim type to a chart id from the local registry. It does NOT render UI; it returns a spec, then `render_events` projects each selection into the SSE event payload that `api/events.chart()` would have emitted. The agent prefers a `gpt-4o-mini` LLM call (with a strict Pydantic schema and post-validation) and falls back to a deterministic heuristic when no LLM is configured, when the LLM returns nothing usable, or when the post-validation rejects every selection. Replaces the previous "emit every native chart whenever the right session view exists" behavior in the routed pipeline.

## Location

- **Package root:** [briarwood/representation/](.) — re-exports from [briarwood/representation/__init__.py](__init__.py).
- **Agent entry:** [briarwood/representation/agent.py:133](agent.py#L133) — `RepresentationAgent`. Public methods: `plan(...)` at [agent.py:162](agent.py#L162), `render_events(...)` at [agent.py:194](agent.py#L194).
- **Chart registry:** [briarwood/representation/charts.py](charts.py) — `register`, `get_spec`, `all_specs`, `render`, `ChartSpec`. Eight registered chart kinds today.
- **Schemas:** `RepresentationPlan` at [agent.py:105](agent.py#L105); `RepresentationSelection` at [agent.py:85](agent.py#L85); `ClaimType` enum at [agent.py:44](agent.py#L44); `ChartSpec` at [charts.py:29](charts.py#L29).
- **Tests:** [tests/representation/test_agent.py](../../tests/representation/test_agent.py); [tests/representation/test_charts.py](../../tests/representation/test_charts.py); plus integration coverage at [tests/pipeline/test_representation.py](../../tests/pipeline/test_representation.py) and [tests/claims/test_representation.py](../../tests/claims/test_representation.py).
- **Feature flags:** None directly. Triggering today is gated by the routed-decision path that runs in `api/pipeline_adapter.py`.

## Role in the Six-Layer Architecture

- **This layer:** Representation Agent (Layer 4). Per [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 4: "Representation Agent ... Mostly plumbing. The architectural primitives are already built." This package is the substantial existing implementation.
- **Called by:** `api/pipeline_adapter.py:1422` ([api/pipeline_adapter.py](../../api/pipeline_adapter.py)) — the adapter constructs a `RepresentationAgent(llm_client=llm)` and calls `plan(...)` then `render_events(...)` to produce the chart events that ride alongside the verdict response.
- **Calls:**
  - The configured `LLMClient` (default model: env `BRIARWOOD_REPRESENTATION_MODEL`, fallback `gpt-4o-mini`) for the structured-output plan.
  - Each registered chart's renderer at [charts.py:74](charts.py#L74) (`render(chart_id, inputs)`), which lazy-imports the corresponding `_native_*_chart` helper from [api/pipeline_adapter.py](../../api/pipeline_adapter.py).
- **Returns to:** Caller (`api/pipeline_adapter.py`). Returns a `RepresentationPlan`, then a list of SSE event dicts.
- **Emits events:** Indirectly — each rendered selection becomes an SSE `chart` event with two added keys: `supports_claim` (the `ClaimType.value`) and `why_this_chart` (the `claim` text). See [agent.py:217-223](agent.py#L217-L223).

## LLM Usage

| Call site | Provider | Model | Purpose | Prompt location |
|-----------|----------|-------|---------|-----------------|
| [agent.py:229-238](agent.py#L229-L238) `_plan_via_llm` | injected `LLMClient` (typically OpenAI) | env `BRIARWOOD_REPRESENTATION_MODEL` (default `gpt-4o-mini`) | Chart selection — picks `RepresentationSelection` entries from the registered chart catalog | Inline `_SYSTEM_PROMPT` at [agent.py:108-125](agent.py#L108-L125) |

**Response parsing:** Strict structured output via the `RepresentationPlan` Pydantic schema at [agent.py:100](agent.py#L100). On parse failure or empty selections, falls back to `_deterministic_plan` at [agent.py:299](agent.py#L299).

**Retry / timeout:** Caller-controlled. The agent's own retry budget exhaustion is recorded as a `representation_plan` breadcrumb on `session.last_partial_data_warnings` so the UI can see when the deterministic fallback ran (per `plan` docstring at [agent.py:170-175](agent.py#L170-L175)).

**Cost characteristics:** One call per decision-tier turn when an LLM client is provided. The system prompt is small; user payload is the verdict digest plus the module-view digest. No streaming.

**Hard rules in the system prompt** (verbatim from [agent.py:112-125](agent.py#L112-L125)):
1. Only claim something the module evidence actually supports — flag if not.
2. Pick `chart_id` only from the registry — null if no chart fits, never invent.
3. `supporting_evidence` entries must cite real field names from `module_views`.
4. `source_view` must be one of the keys in `module_views` or null.
5. Prefer 3-5 selections; one chart per `claim_type`.
6. Do not restate the same claim with different wording.

## Inputs

`plan(unified, *, user_question, module_views, session=None)`:

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `unified` | `UnifiedIntelligenceOutput` | Routed core (Layer 3 / synthesizer) | Required. |
| `user_question` | `str` | Router / dispatch | Free text — routed into the LLM user payload. |
| `module_views` | `Mapping[str, Mapping[str, Any] \| None]` | Session (`session.last_*_view` slots populated by `handle_decision`) | Keys must be in `KNOWN_SOURCE_VIEWS` ([agent.py:69-77](agent.py#L69-L77)) for charts to resolve their inputs. None or missing views are tolerated. |
| `session` | `Any` (optional) | Session object | When provided, the agent records LLM-budget exhaustion to `session.last_partial_data_warnings`. |

`render_events(plan, module_views, *, market_view=None)`:

| Input | Type | Notes |
|-------|------|-------|
| `plan` | `RepresentationPlan` | Output of `plan(...)`. |
| `module_views` | as above | |
| `market_view` | `Mapping[str, Any] \| None` | Optional override injected into `cma_positioning`'s renderer to prefer live-market comps over valuation comps. |

## Outputs

`RepresentationPlan.selections: list[RepresentationSelection]`. Each selection carries:

| Field | Type | Notes |
|-------|------|-------|
| `claim` | `str` | Free-text verdict claim. |
| `claim_type` | `ClaimType` | One of thirteen values: `PRICE_POSITION`, `VALUE_DRIVERS`, `COMP_EVIDENCE`, `SCENARIO_RANGE`, `DOWNSIDE_RISK`, `RISK_COMPOSITION`, `RENT_COVERAGE`, `RENT_RAMP`, `AFFORDABILITY_CARRY_COST`, `RENT_VS_OWN`, `RENOVATION_IMPACT`, `SENSITIVITY`, `HIDDEN_UPSIDE`. |
| `supporting_evidence` | `list[str]` | Field-name citations into `module_views`. |
| `chart_id` | `str \| None` | Registered chart id; `None` is allowed and means "claim only, no chart event." |
| `source_view` | `str \| None` | Which `module_views` key feeds the chart's renderer. |
| `flagged` | `bool` | `True` when the agent could not back the claim with evidence — caller may drop or surface as caveat. |
| `flag_reason` | `str \| None` | Explanation. |

`render_events(...)` returns a `list[dict[str, Any]]` of SSE event payloads, each augmented with `supports_claim` (the `ClaimType` value) and `why_this_chart` (the claim text). Selections without a `chart_id`, flagged selections, and selections whose renderer returns `None` are skipped silently.

## Chart Registry

Eight registered specs in [charts.py](charts.py). Each has an `id`, a `name`, a `description`, `required_inputs` (read from the source view dict), and `claim_types` (which `ClaimType` values it can back).

| Chart id | Renders | claim_types | Required inputs |
|----------|---------|-------------|-----------------|
| `scenario_fan` | Bull/base/bear range over a 5-year hold | `scenario_range`, `downside_risk`, `renovation_impact`, `sensitivity` | `bull_case_value`, `base_case_value`, `bear_case_value` |
| `value_opportunity` | Ask vs. fair value with drivers | `price_position`, `value_drivers`, `affordability_carry_cost` | `ask_price`, `fair_value_base` |
| `cma_positioning` | Comp asks scattered against subject + value band | `comp_evidence`, `price_position` | `comps` (plus optional `_market_view` injected by `render_events`) |
| `risk_bar` | Per-risk-flag penalty share | `risk_composition`, `downside_risk` | `risk_flags` |
| `rent_burn` | Rent vs monthly cost across hold horizon | `rent_coverage`, `rent_vs_own`, `affordability_carry_cost` | `burn_chart_payload` |
| `rent_ramp` | Net cash flow at base/bull/bear rent ramps with break-even markers | `rent_ramp`, `rent_coverage`, `rent_vs_own`, `sensitivity` | `ramp_chart_payload` |
| `hidden_upside_band` | Marker only — UI renders via `HiddenUpsideBlock` React card; renderer returns `None` | `hidden_upside`, `renovation_impact` | (none) |
| `horizontal_bar_with_ranges` | Marker only — claim-object representation builds the spec directly from a `VerdictWithComparisonClaim`; renderer returns `None` | `scenario_comparison` | `scenarios` |

Renderers are thin wrappers around `_native_*_chart` helpers in [api/pipeline_adapter.py](../../api/pipeline_adapter.py); imports are lazy to avoid an import cycle. Renderers are intentionally permissive — any failure maps to `None` (no chart) at [charts.py:81-86](charts.py#L81-L86) rather than crashing the decision stream.

## Inputs / Outputs (deterministic fallback)

`_deterministic_plan` at [agent.py:299-510](agent.py#L299-L510) walks the verdict + module views and emits selections in a fixed order based on which views are populated. This is the fallback path — runs whenever `_plan_via_llm` returns `None` or an empty plan, or when post-validation strips every LLM selection. Behavior is bounded: at most `max_selections` (default 6) entries.

## Dependencies on Other Modules

- **Schema dependency on:** `UnifiedIntelligenceOutput` from `briarwood/decision_model/` (synthesizer) and the session-view shapes populated by `briarwood/agent/dispatch.py::handle_decision`. Renderers depend on `api/pipeline_adapter.py::_native_*_chart` shapes.
- **Imports:** `briarwood.agent.llm.LLMClient`. Chart renderers lazy-import `api.pipeline_adapter` (intentional to avoid the import cycle).
- **Coupled to:** `web/src/lib/chat/events.ts` — the SSE chart-event shape must match the TypeScript event types. Coupled to `KNOWN_SOURCE_VIEWS` ([agent.py:69-77](agent.py#L69-L77)) which mirrors the `Session.last_*_view` slot names.

## Invariants

- `plan` always returns a `RepresentationPlan` (possibly empty); never raises.
- Post-validation at [agent.py:517-586](agent.py#L517-L586) strips selections whose `chart_id` is not registered, whose `source_view` is not in `KNOWN_SOURCE_VIEWS`, or whose `supporting_evidence` cites a field not present in the named view. Stripped selections do NOT cause a fall-through to deterministic — only an empty plan does.
- `render_events` deduplicates by `chart_id` (one chart per id at most) and silently skips selections without a chart, flagged selections, and null-rendering selections.
- `claim_type` is an enum — Pydantic validation rejects unknown values at parse time.
- Chart renderers are catch-all in `render` at [charts.py:81-86](charts.py#L81-L86) — any unexpected exception maps to `None`.
- Deterministic per input when no LLM is configured. With LLM, deterministic given the same LLM response (the agent itself adds no randomness).
- Never mutates its inputs (`module_views` are dict-copied at [agent.py:177-181](agent.py#L177-L181)).

## State & Side Effects

- **Stateless agent class:** holds an injected LLM client and a max-selections cap; no mutable instance state.
- **Writes to disk:** no.
- **Modifies session:** Optionally — appends to `session.last_partial_data_warnings` when LLM exhaustion drives a fallback.
- **Safe to call concurrently:** yes.

## Example Call

```python
from briarwood.representation import RepresentationAgent

agent = RepresentationAgent(llm_client=llm)  # llm may be None for deterministic-only

plan = agent.plan(
    unified=unified_output,
    user_question="Is this a buy?",
    module_views={
        "last_projection_view": {"bull_case_value": 1_120_000, "base_case_value": 980_000, "bear_case_value": 870_000},
        "last_risk_view": {"risk_flags": [...]},
        "last_value_thesis_view": {"ask_price": 850_000, "fair_value_base": 790_000, ...},
    },
)
events = agent.render_events(plan, module_views=...)
# events is a list of SSE chart payloads, each with supports_claim + why_this_chart added.
```

## Known Rough Edges

- **Trigger gate is not in this module.** Per [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 4, this agent runs only on the routed-decision path. Browse-tier chart emission remains hardcoded in `api/pipeline_adapter.py`. Generalizing is mostly plumbing.
- **Chart registry is small.** Eight entries today. Adding a chart kind is additive — register a `ChartSpec` and a renderer at module-import time. Then add a matching React component on the frontend. The `claim_types` field is the matching key for selection.
- **Two markers, no rendered events.** `hidden_upside_band` and `horizontal_bar_with_ranges` are registered for discoverability/validation but their renderers return `None`. Consumers (`HiddenUpsideBlock` React card; the claim-object representation) must build the actual surface.
- **Naming history.** The claims-validation agent at `briarwood/pipeline/representation.py` was previously also named `RepresentationAgent`; it was renamed to `ClaimEvidenceValidator` in Handoff 2a Piece 5B (2026-04-24) to remove the collision. The chart-selection agent documented here keeps the `RepresentationAgent` name because it is the Layer-4 concept in [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md). The file-path prefix (`briarwood/representation/` vs `briarwood/pipeline/`) is still how the two modules are disambiguated in grep.
- **No user-type conditioning.** Per [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 4 Open Product Decisions: "Should investor and first-time-buyer user types see different chart selections for the same intent?" — undecided.

## Open Product Decisions

(Pulled from [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 4 and Layer 6; no representation-specific decisions invented here.)

- **User-type-conditioned chart selection.** Layer-1 dependency.
- **Mobile "simplicity mode"?** Open.
- **Whether to broaden Layer-4 triggering beyond the decision tier.** Mostly plumbing per the gap analysis.
- **Chart-registry expansion priorities.** New chart kinds are additive but each requires both a renderer and a frontend card. Which kinds are worth the cost is open.

## Changelog

### 2026-04-28 (Phase 4c Cycle 3 — `feeds_fair_value` retired from the cma_positioning chart spec)
- **Contract change:** `CmaPositioningChartSpec.comps[]` no longer carries `feeds_fair_value`. The "Chosen comps / Context only" `MetricChip` on the chart footer is replaced by a `Comp set` chip computed from `listing_status` + `is_cross_town` counts via the shared `formatCompSetChip(...)` helper exported from `web/src/components/chat/chart-frame.tsx`. The same helper feeds the new BROWSE Section C "Comps" drilldown summary chip so chart-prose alignment is structural, not coincidental.
- **Marker fallback retired.** Legacy / pre-Cycle-5 cached payloads with `listing_status=null` previously fell through to a `feeds_fair_value`-keyed marker tone; that path is gone. Unknown `listing_status` now renders with the SOLD marker (`var(--chart-bull)` filled circle) — saved-store comps in legacy transcripts were all SOLD by construction, so the visual fidelity of cached turns is preserved.
- **Companion text updated.** `cmaSurface` in `web/src/lib/chat/chart-surface.ts` no longer counts "comps feeding fair value"; it now narrates SOLD vs ACTIVE provenance from `listing_status` so the editorial line matches the chip.
- **Folds drive-by §3.4.1** from `ROADMAP.md` chart-quality umbrella.

### 2026-04-26 (CMA Phase 4a Cycle 5 — chart count, gated by comp-set presence; provenance markers)
- BROWSE chart count grows from 3 to 4. `_BROWSE_CHART_SET` in `briarwood/agent/dispatch.py` now reads `[market_trend, cma_positioning, value_opportunity, scenario_fan]` in that order — comp evidence sits between the market-trend context and the fair-value read so the prose can reference closed sales / active asks before naming the fair-value gap. The `cma_positioning` entry uses `comp_evidence` as its `claim_type` and `last_value_thesis_view` as its source view (the 2026-04-26 two-view defensive fix is unchanged: the renderer pulls comp rows from the injected `last_market_support_view`).
- Contract change: `_enforce_browse_chart_set(plan_dict, *, include_cma_positioning: bool = True)` accepts a gate. `_browse_compute_representation_plan` derives the gate from `session.last_market_support_view` — when the view is absent or carries no comps (Engine B's Cycle 2 invariants did not pass and `_build_market_support_view` returned `None`), `include_cma_positioning=False` and the BROWSE turn falls back to the legacy 3-chart set rather than painting an empty CMA frame.
- `RepresentationAgent` `max_selections` bump for BROWSE: `_browse_compute_representation_plan` now constructs the agent with `max_selections=4` so the LLM has room to suggest four charts in one pass; the enforcer still rewrites the plan deterministically.
- **Provenance markers (additive contract change to the cma_positioning SSE spec).** Each entry in `CmaPositioningChartSpec.comps[]` now carries `listing_status: "sold" | "active" | null` and `is_cross_town: boolean | null`. The frontend `CmaPositioningChart` renders three distinct markers: SOLD = filled circle (`var(--chart-bull)`), ACTIVE = open triangle stroked in `var(--chart-neutral)`, cross-town SOLD = filled circle with a dashed `var(--chart-base)` outline. Legacy / pre-Cycle-5 cached payloads with `listing_status=null` originally fell through to a `feeds_fair_value`-keyed fallback colour; Phase 4c Cycle 3 retired that fallback and legacy rows now render with the SOLD marker by default (saved-store comps were all SOLD by construction, so the back-compat behaviour is preserved). The chart event's `legend` was rewritten accordingly — `[SOLD comp, ACTIVE comp, Cross-town SOLD, Fair value, Subject ask]`.
- Pipeline path: `_comp_row_from_cma` (in `briarwood/agent/dispatch.py`) propagates the two new fields from `ComparableProperty` → `_build_market_support_view` → `_native_cma_chart` (in `api/pipeline_adapter.py`) → SSE → React.
- **BROWSE-only suppression of the standalone `market_support_comps` panel.** `_browse_stream_impl` and `_dispatch_stream_impl` (when the routed `answer_type` is `BROWSE`) no longer append `events.market_support_comps(...)` to the primary-event list. Reason: the new `cma_positioning` chart in the BROWSE chart set already surfaces the same comps with provenance markers, and emitting both surfaces caused a visible mid-stream layout reflow ("glitch and reload" — comp panel arrives as a primary event, chart arrives later as a secondary event). DECISION / EDGE handlers continue to emit the panel as a drilldown surface — their emit sites are unchanged. Two regression tests in `tests/test_pipeline_adapter_contracts.py` updated to expect `assertNotIn(EVENT_MARKET_SUPPORT_COMPS, ...)` for BROWSE turns.
- Tests: `BrowseChartSetEnforcementTests` updated for the 4-chart kind list when comps are present, plus a new `test_enforcer_drops_cma_positioning_when_no_comp_set` for the gating-off path. New `CmaPositioningChartProvenanceTests` in `tests/test_pipeline_adapter_contracts.py` pins the SSE comp-dict shape (carries `listing_status` + `is_cross_town`) and the new legend labels, and pins the back-compat behaviour for legacy rows missing the provenance keys.

### 2026-04-26 (Phase 3 closeout — BROWSE chart-set enforcement + cma_positioning fix)
- BROWSE-tier chart selection is now deterministic. The agent's intent-keyed prompt has strong defaults but in practice gpt-4o-mini drifted (e.g. picked `cma_positioning` instead of `market_trend`). `_enforce_browse_chart_set` (in `briarwood/agent/dispatch.py`) rewrites any agent plan dict so the BROWSE selections are exactly `[market_trend, value_opportunity, scenario_fan]` in that order, with canonical `source_view` values pinned. Agent's per-chart `claim` text is preserved when it picked one of these kinds; default deterministic claims fill any gaps. Both the synthesizer's `charts` payload and the SSE chart events read from the same enforced plan.
- Contract change: `RepresentationAgent.render_events(...)` now overrides the primary view to `last_value_thesis_view` whenever the chart kind is `cma_positioning`, regardless of what `source_view` the selection named. The `cma_positioning` chart fundamentally needs two views (value-thesis for ask/fair_value/value_band anchors, market-support for comp rows); the agent's single-source-view abstraction couldn't model that, so the renderer painted with `—` placeholders when the agent picked `last_market_support_view` as source. Defensive fix; the deeper restructure (typed `source_views: dict[role, view_key]` on `RepresentationSelection`) is recorded in [ROADMAP.md](../../ROADMAP.md) "cma_positioning source-view drift in non-BROWSE handlers" 2026-04-26.

### 2026-04-26 (Cycle D — synthesis-side, no representation change)
- Cycle D landed in [briarwood/synthesis/README.md](../synthesis/README.md). It restructured the synthesizer system prompt for newspaper voice with per-tier variants and added the `BRIARWOOD_SYNTHESIS_NEWSPAPER` kill switch. No representation-module code changed.

### 2026-04-26 (Cycle C)
- Contract change: `synthesize_with_llm(...)` in `briarwood/synthesis/llm_synthesizer.py` now accepts an optional `charts: list[{kind, claim}]` keyword. The synthesizer's system prompt instructs the LLM to reference selected charts by what the user will see ("the scenario fan shows…", "the town-trend line…") so prose and charts tie together. Numeric grounding rule preserved verbatim.
- `handle_browse` runs the Representation Agent before the synthesizer (via `_browse_compute_representation_plan`) and caches the plan on `session.last_representation_plan`. `api/pipeline_adapter.py::_representation_charts` reads the cached plan when present, so the gpt-4o-mini chart-selection call fires once per turn instead of twice.
- React: `ChartFrame` now renders `chart.why_this_chart` (the agent's per-chart claim) as a 13px italic caption with a left border above the chart body. Falls back to the `visual_advisor` summary when the agent didn't produce a claim.

### 2026-04-26 (Cycle B)
- Contract change: `RepresentationAgent.plan(...)` accepts an optional `intent` argument (`IntentContract` from `briarwood.intent_contract`). When provided, the LLM payload includes the intent so chart selection is intent-keyed; the system prompt's strong-default per-`answer_type` chart sets steer toward 2–3 charts that directly answer the user's intent rather than the kitchen sink.
- Contract change: `RepresentationAgent.__init__` already accepted `max_selections`; the value is now threaded into the LLM payload so the model sees the cap, and `api/pipeline_adapter.py::_representation_charts(...)` accepts a per-call `intent` + `max_selections` override (defaults preserved).
- Contract change (additive): two new `ClaimType` values — `MARKET_POSITION` and `TOWN_PULSE` — both backed by the new `market_trend` chart kind.
- New chart kind: `market_trend`. Town-level (or county fallback) Zillow Home Value Index series. Required inputs: `history_points`, `geography_name`, `geography_type`. Source view: `last_market_history_view` (added to `KNOWN_SOURCE_VIEWS`). Renderer at `api/pipeline_adapter.py::_native_market_trend_chart`. React component `MarketTrendChart` in `web/src/components/chat/chart-frame.tsx`.
- BROWSE chart selection is now agent-driven. `_browse_stream_impl` previously emitted 5 hardcoded charts (`value_opportunity`, `cma_positioning`, `rent_burn`, `rent_ramp`, `scenario_fan`) every turn; it now goes through `_representation_charts(...)` with `intent=build_contract_from_answer_type("browse")` and `max_selections=3`. The hardcoded fan-out is gone.

### 2026-04-26
- Contract change (additive): chart event payloads now carry presentation metadata —
  `subtitle: str`, `x_axis_label: str | null`, `y_axis_label: str | null`,
  `value_format: "currency" | "percent" | "count"`, and `legend: list[{label, color, style}]`.
  The metadata is emitted by every `_native_*_chart` helper in `api/pipeline_adapter.py`
  plus the wedge renderer at `briarwood/claims/representation/verdict_with_comparison.py::_build_chart_event`.
  All fields are optional on the `ChartEvent` TypeScript type so older event shapes still render.
  Phase 3 Cycle A. See [PRESENTATION_HANDOFF_PLAN.md](../../PRESENTATION_HANDOFF_PLAN.md) and
  [web/CHART_STYLE.md](../../web/CHART_STYLE.md) for the chart-style convention this metadata
  feeds into.
- The `ChartSpec` Pydantic descriptor (the registry shape — what the LLM agent reads) is
  unchanged. Cycle A's contract change is on the SSE event payload only, not the agent's
  selection input.

### 2026-04-25
- Contract change: `ClaimType` extended with four new values — `AFFORDABILITY_CARRY_COST`, `RENT_VS_OWN`, `RENOVATION_IMPACT`, `SENSITIVITY`. Existing values unchanged. Pydantic post-validation will accept claims tagged with the new values; previously they would have been stripped.
- Chart registry coverage broadened — `value_opportunity`, `rent_burn`, `rent_ramp`, `scenario_fan`, and `hidden_upside_band` now declare additional `claim_types` so the LLM planner can route the new claim values to existing renderers without new chart kinds. No new chart ids; renderer behavior unchanged.
- Internal: `_plan_via_llm` now routes through `briarwood.agent.llm_observability.complete_structured_observed` (added Phase 1 of the 2026-04-25 output-quality audit). LLM call is now visible in the shared ledger and the per-turn manifest under surface `representation.plan`. Side effect: the `session.last_partial_data_warnings` breadcrumb on retry exhaustion now fires only on `BudgetExceeded` propagation rather than on any caught exception, since `complete_structured_observed` swallows non-budget failures into `None`.
- Line-number cross-references in §Location updated to match current `agent.py`. Other line refs in this README (§Role table, §Inputs, §Outputs, §Determinism, §Caveats, §Coupling) accumulated drift from prior diffs and have not been swept in this commit.

### 2026-04-24
- Initial README created.
- Collision note rewritten as history: the previously-colliding class at `briarwood/pipeline/representation.py` was renamed to `ClaimEvidenceValidator` in Handoff 2a Piece 5B. This module's `RepresentationAgent` is unchanged; the rename only affected the claims-validation class. No code changes in `briarwood/representation/`.

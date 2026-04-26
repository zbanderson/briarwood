# representation — Representation Agent + Chart Registry

**Last Updated:** 2026-04-26
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

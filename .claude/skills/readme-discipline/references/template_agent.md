# [Agent / Pipeline Name]

**Last Updated:** YYYY-MM-DD
**Layer:** Intent | Orchestration | Unified Intelligence | Representation | Value Scout | Delivery
**Status:** STABLE | EVOLVING | EXPERIMENTAL | DEPRECATED

## Purpose

One paragraph. What this agent or pipeline is responsible for in the six-layer architecture. Why it exists as a separate layer rather than being folded into the layer above or below. Written so that a new Claude Code session reading this section understands where this module sits in the overall flow before looking at any code.

Example:
> The Representation Agent decides how to visualize a given Unified Intelligence
> output. It reads the intent, the synthesized facts, and the user-type hint,
> then produces a `RepresentationPlan` that specifies which chart kinds and
> tables to render. It does NOT render UI itself — it returns a spec that the
> frontend consumes via SSE events.

## Location

- **Entry point:** `briarwood/<path>/<file>.py::<class_or_function>`
- **Schemas:** `briarwood/<path>/schemas.py`
- **Tests:** `tests/<path>/`
- **Feature flags:** list any flags that gate this module, with file path

## Role in the Six-Layer Architecture

Which layer this module implements (pick one), and how it interfaces with the adjacent layers.

- **This layer:** Representation Agent (Layer 4)
- **Called by:** Unified Intelligence LLM (Layer 3) — specifically `briarwood/claims/synthesis/verdict_with_comparison.py::synthesize()`
- **Calls:** Chart registry at `briarwood/representation/charts.py`
- **Returns to:** Caller, not to a downstream layer
- **Emits events:** `representation_plan_ready` via SSE

## LLM Usage

If this agent makes LLM calls, document them here. If it does not, write `None` and move on.

| Call site | Provider | Model | Purpose | Prompt location |
|-----------|----------|-------|---------|-----------------|
| `agent.py:128` | Anthropic | claude-sonnet-4 | Chart selection | `prompts/representation.py` |
| `agent.py:187` | Anthropic | claude-sonnet-4 | Plan validation | inline |

**Response parsing:** Structured output via Pydantic schema `RepresentationPlan`. On parse failure, falls back to a default plan defined in `agent.py:45`.

**Retry / timeout:** 1 retry on parse failure, 10s timeout per call. Total budget for this agent is 20s.

**Cost characteristics:** ~2 calls per DECISION turn; ~1500 input tokens, ~400 output tokens per call.

## Inputs

What this agent consumes. This may include structured data from upstream layers, user context, session state, and feature flags.

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `unified_output` | `UnifiedIntelligenceResult` | Layer 3 | Required |
| `intent` | `AnswerType` | Layer 1 (router) | Required |
| `user_type` | `UserType \| None` | Layer 1 (session) | Optional; defaults to `UNKNOWN` |
| `chart_registry` | `ChartRegistry` | static | Loaded once at startup |

## Outputs

What this agent produces and what downstream consumers rely on.

| Output | Type | Consumer | Notes |
|--------|------|----------|-------|
| `representation_plan` | `RepresentationPlan` | Delivery layer / SSE | Always non-null |
| Telemetry | logged to `data/representation/` | feedback loop | Includes prompt hash |

## Dependencies on Other Modules

Which modules this agent reads from, calls, or is coupled to. Be specific — these are the relationships that will break silently if someone changes a schema.

- **Schema dependency on:** `briarwood/claims/schemas.py::VerdictWithComparisonClaim` (this agent expects this shape)
- **Imports:** `briarwood/representation/charts.py`, `briarwood/agent/llm.py`
- **Coupled to:** `web/src/lib/chat/events.ts` — SSE event type must match

## Invariants

What the caller can assume. What this agent guarantees even in failure cases.

- Always returns a valid `RepresentationPlan`; never raises
- On LLM failure, returns a default plan with `degraded: true` flag
- Chart kinds in the plan are always in the chart registry (validated before return)
- Never mutates its inputs

## State & Side Effects

Is this agent stateful? Does it write to disk? Does it modify session state? Anything that makes repeat calls non-equivalent to single calls.

- **Stateless:** yes
- **Writes to disk:** yes — appends to `data/representation/plans.jsonl` for feedback
- **Modifies session:** no
- **Safe to call concurrently:** yes

## Example Call

```python
from briarwood.representation.agent import RepresentationAgent

agent = RepresentationAgent(chart_registry=default_registry)

plan = agent.plan(
    unified_output=unified_result,
    intent=AnswerType.DECISION,
    user_type=UserType.INVESTOR,
)

# plan.charts == [ChartSpec(kind="fan_chart", ...), ChartSpec(kind="comp_table", ...)]
# plan.layout == "hero_plus_supporting"
# plan.degraded == False
```

## Known Rough Edges

Honest accounting of what's incomplete, hardcoded, or awaiting a decision. This is the section future-you will grep when something surprises you.

- Only wired for `VerdictWithComparisonClaim` path today — other claim archetypes fall through to default plan
- Chart registry is hardcoded; no runtime extensibility
- User-type input is accepted but not yet used in prompt (Layer 1 doesn't populate it)

## Open Product Decisions

Questions that affect this module's behavior but haven't been decided yet. Reference `DECISIONS.md` entries when they exist.

- Should investor and first-time-buyer user types see different chart selections for the same intent? (no decision yet)
- Should the agent have a "simplicity mode" for mobile? (no decision yet)

## Changelog

### YYYY-MM-DD
- Initial README created

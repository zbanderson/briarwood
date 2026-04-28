# [Model Name] — Scoped Registry Model

**Last Updated:** YYYY-MM-DD
**Status:** READY | NEEDS_ADAPTER | NEEDS_REFACTOR | LEGACY
**Registry:** scoped | legacy

## Purpose

One paragraph. What this model computes, and what user question it helps answer. Written so that an orchestrating LLM reading this section can decide whether to call this tool for a given user intent. Be concrete about the decision this model supports — avoid vague phrases like "provides analysis."

Example:
> `risk_model` computes a bounded risk score (0–1) for a property by combining
> liquidity risk (DOM, absorption), capex risk (age, condition), income
> stability (rental market depth), and valuation risk (hybrid value dispersion).
> Call this tool when the user's intent involves any form of "what could go
> wrong" or when the orchestrator needs a risk factor to gate a recommendation.

## Location

- **Entry point:** `briarwood/modules/<module>/<file>.py::<function_name>`
- **Registry entry:** `briarwood/execution/registry.py` line [N]
- **Schema definitions:** `briarwood/modules/<module>/schemas.py`

## Intent Fit

List the `AnswerType` values from `briarwood/agent/router.py` that this tool serves. If the tool is general-purpose, say "all decision-type intents" explicitly. If it's narrow, list the exact intents.

- `DECISION` — always called
- `RESEARCH` — called when user asks about risk factors specifically
- Not called for: `BROWSE`, `SEARCH`

## Inputs

Typed field list. Required vs. optional. Where each field originates (user input, upstream model, property facts, etc.).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `property_id` | `str` | yes | user / session | Canonical MLS identifier |
| `property_facts` | `PropertyFacts` | yes | `property_data_quality` | Must be quality-checked |
| `town_signal` | `TownSignal` | optional | `local_intelligence` | Falls back to town median if absent |

## Outputs

Typed field list. Units, ranges, null semantics.

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `risk_score` | `float` | 0.0–1.0 | Higher = riskier |
| `risk_components` | `dict[str, float]` | each 0.0–1.0 | liquidity, capex, income, valuation |
| `confidence` | `float` | 0.0–1.0 | Lower when inputs are sparse |
| `rationale` | `str` | ≤ 280 chars | Human-readable one-liner |

## Dependencies

Which other tools must run before this one. If this tool calls them internally, note that. If it expects their outputs as inputs, note that too.

- **Requires (inputs):** `property_data_quality` (property_facts must be validated)
- **Benefits from (optional):** `local_intelligence`, `town_development_index`
- **Calls internally:** none
- **Must not run concurrently with:** none

## Invariants

What the caller can assume about this tool's behavior. These are the promises the model makes.

- `risk_score` is always in [0, 1]; never null
- `confidence` below 0.3 indicates the caller should disclose uncertainty to the user
- The tool is deterministic for a fixed input (no LLM calls, no randomness)
- Latency is < 200ms typical, < 1s worst case
- The tool never raises; sparse inputs produce low-confidence output, not errors

## Example Call

```python
from briarwood.modules.risk_model import run_risk_model
from briarwood.execution.context import ModelContext

ctx = ModelContext(
    property_id="NJ-0000001",
    property_facts=validated_facts,
    town_signal=town_signal,
)

result = run_risk_model(ctx)
# result.risk_score == 0.34
# result.risk_components == {"liquidity": 0.4, "capex": 0.2, ...}
# result.confidence == 0.78
# result.rationale == "Moderate risk driven primarily by thin absorption."
```

## Hardcoded Values & TODOs

Document any hardcoded constants, mock returns, or known-incomplete logic. This is what future-you needs to know to trust the output.

- `briarwood/modules/risk_model/config.py::ABSORPTION_FLOOR = 0.05` — arbitrary floor for thin-market detection
- TODO: capex component currently uses age proxy; should use condition signal when `property_data_quality` produces it

## Blockers for Tool Use

For scoped-registry models this section is usually empty or `NONE`. For models that are *not* cleanly callable in isolation, list what's blocking.

- None. This model is callable in isolation via `run_risk_model(ctx)`.

## Notes

Anything else that matters: performance characteristics, cost (if it makes LLM calls), historical-audit findings that still apply, known limitations, links to related `DECISIONS.md` entries.

## Changelog

### YYYY-MM-DD
- Initial README created

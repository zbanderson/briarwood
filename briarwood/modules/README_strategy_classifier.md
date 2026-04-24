# strategy_classifier — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`strategy_classifier` labels a subject property with one of seven named deal archetypes: `owner_occ_sfh`, `owner_occ_duplex`, `owner_occ_with_adu`, `pure_rental`, `value_add_sfh`, `redevelopment_play`, or `scarcity_hold` (falling back to `unknown` when rules cannot fire). Call this tool when downstream reasoning needs to know *what kind of deal* a property is before running domain models — e.g., whether to emphasize the rental underwriting path, the renovation-upside path, or the teardown/land path. The classifier is deterministic and rule-based (no LLM); its output records which rule fired so callers can audit the label.

## Location

- **Entry point:** [briarwood/modules/strategy_classifier.py:247](strategy_classifier.py#L247) — `run_strategy_classifier(context: ExecutionContext) -> dict[str, object]`
- **Core classifier:** [briarwood/modules/strategy_classifier.py:64](strategy_classifier.py#L64) — `classify_strategy(property_input: PropertyInput) -> StrategyClassification`
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="strategy_classifier", depends_on=[], required_context_keys=["property_data"], runner=run_strategy_classifier)`
- **Schema definitions:** `StrategyClassification` dataclass at [strategy_classifier.py:46-58](strategy_classifier.py#L46-L58); `PropertyStrategyType` enum at [strategy_classifier.py:35-43](strategy_classifier.py#L35-L43).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `STRATEGY` — always called.
- `DECISION` — called to inform which domain thesis the decision should emphasize.
- `BROWSE` — called for quick "what kind of deal is this?" reads.
- Not called for: `CHITCHAT`, `VISUALIZE` (no classification needed).

## Inputs

Inputs arrive through [ExecutionContext](../execution/context.py). The runner normalizes them into a `PropertyInput` via `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.town` | `str` | recommended | listing facts | Rules do not hinge on town alone, but `PropertyInput` requires it. |
| `context.property_data.state` | `str` | recommended | listing facts | Same as above. |
| `context.property_data.sqft` | `int` | recommended | listing facts | Used by the redevelopment heuristic at [strategy_classifier.py:203-211](strategy_classifier.py#L203-L211). |
| `context.property_data.beds`, `baths` | mixed | recommended | listing facts | Required by `PropertyInput` constructor. |
| `context.property_data.property_type` | `str` | optional | listing facts | Multi-family detection at [strategy_classifier.py:77-79](strategy_classifier.py#L77-L79). |
| `context.property_data.occupancy_strategy` | `OccupancyStrategy` | optional | user / assumptions | Routes owner-occupied vs rental branches. |
| `context.property_data.adu_type`, `has_back_house`, `additional_units` | mixed | optional | listing facts | ADU-path detection at [strategy_classifier.py:74-75](strategy_classifier.py#L74-L75). |
| `context.property_data.capex_lane`, `condition_profile` | `str` | optional | user / listing facts | Value-add and redevelopment rule inputs. |
| `context.property_data.lot_size`, `purchase_price` | mixed | optional | listing facts | Redevelopment heuristic inputs. |

## Outputs

The runner returns `ModulePayload.model_dump()`. Salient fields:

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.strategy` | `str` | enum value | One of `owner_occ_sfh` / `owner_occ_duplex` / `owner_occ_with_adu` / `pure_rental` / `value_add_sfh` / `redevelopment_play` / `scarcity_hold` / `unknown`. |
| `data.rationale` | `list[str]` | — | Sentence-level reasons, one per rule-check that contributed to the result. |
| `data.rule_fired` | `str` | enum | The rule that determined the label (e.g., `redevelopment_play`, `multi_family_owner_occupy_partial`). |
| `data.candidates` | `list[str]` | — | Alternate strategies that also applied but were not selected. |
| `data.classification` | `dict` | — | Full `StrategyClassification.to_dict()` for downstream consumers. |
| `confidence` | `float` | 0.0–1.0 | From the rule that fired; typical range 0.45–0.85. |
| `summary` | `str` | prose | `"Strategy: {value} (rule: {rule_fired})"`. |
| `warnings` | `list[str]` | — | Populated only when confidence < 0.50 (the fallback-reason note), or when the error contract triggers. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]`. Consumes `property_data` from `ExecutionContext`.
- **Benefits from (optional):** none. The classifier is pure-rule over static facts.
- **Calls internally:** none.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none today; dormant consumer at [briarwood/interactions/primary_value_source.py:34, 42-64](../interactions/primary_value_source.py#L34) gates its strategy-prior branch on the classifier output and was unblocked by this promotion (H3, 2026-04-24).

## Invariants

- `strategy` is always one of the eight enum values; never null.
- `confidence ∈ [0.0, 1.0]` from the rule that fired.
- `rule_fired` is non-empty; `"none"` when no rule matched.
- Deterministic for fixed inputs — no LLM, no randomness, no IO.
- Never raises. The wrapper catches any exception from `build_property_input_from_context` or the classifier and returns `module_payload_from_error` per the canonical contract ([DECISIONS.md 2026-04-24 *Scoped wrapper error contract*](../../DECISIONS.md)).

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.strategy_classifier import run_strategy_classifier

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "address": "12 Main St",
        "town": "Montclair",
        "state": "NJ",
        "beds": 3,
        "baths": 2.0,
        "sqft": 1800,
        "occupancy_strategy": "owner_occupy_full",
    },
    assumptions={},
)

payload = run_strategy_classifier(context)
# payload["data"]["strategy"]    == "owner_occ_sfh"
# payload["data"]["rule_fired"]  == "owner_occ_sfh_default"
# payload["confidence"]          ≈ 0.70
```

## Hardcoded Values & TODOs

- Rule ordering is the behavioral contract. Changes require test-suite updates.
- Scarcity-hold rule is a placeholder at [strategy_classifier.py:232-241](strategy_classifier.py#L232-L241): returns False until a Phase 4 bridge feeds `scarcity_score` from market signals. Documented inline.
- The `classifier_version` in `assumptions_used` is pinned to `"phase3/v1"`; bump when rule semantics change.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Open product question.** Whether `strategy_classifier` should *always* run as a routing pre-step (upstream of intent-routed tool selection) or be invoked case-by-case is a Layer 2 architecture call — see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 13 "Open product question."
- Latency: sub-millisecond. No IO, no LLM.
- The previously-scoped adapter existed at this file since Phase 3 but was never registered; Handoff 3 added the `ModuleSpec` entry and wrapped the adapter body in the canonical try/except error contract.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 13.
- Contract change: `run_strategy_classifier` body now wrapped in `try`/`except` that returns `module_payload_from_error` per the canonical error contract at [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*. Previously, exceptions propagated to the executor.

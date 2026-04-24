# confidence — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`confidence` is the rollup that reconciles every other model's confidence into a single Briarwood-wide trust number. Confidence Engine v2 combines a data-quality anchor from `PropertyDataQualityModule`, a weighted mean of every other module's reported confidence (weights from `pipeline.triage.load_model_weights`), field completeness from the missing-data registry, reliance on estimated/defaulted inputs, a small contradiction count, a comp-quality signal lifted from `valuation`, model-agreement (variance across prior confidences), scenario fragility from `resale_scenario`'s bull/bear spread, and legal certainty from `legal_confidence`. The result is the `overall_confidence` + `confidence_band` surfaced to the user, plus a full component breakdown in `extra_data`. Call this tool last in any multi-module analysis — it is meaningless without upstream modules' outputs present in `context.prior_outputs`.

## Location

- **Entry point:** [briarwood/modules/confidence.py:16](confidence.py#L16) — `run_confidence(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:79-86](../execution/registry.py#L79-L86) — `ModuleSpec(name="confidence", depends_on=[], required_context_keys=["property_data"], runner=run_confidence)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316). The anchor `ModuleResult` shape comes from `PropertyDataQualityModule` at [briarwood/modules/property_data_quality.py](property_data_quality.py). Weights loaded via `load_model_weights` at [briarwood/pipeline/triage.py:30](../pipeline/triage.py#L30).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `DECISION` — always called; the verdict card reads the confidence band.
- `RISK` — called when the user asks "how sure are you?" or otherwise centers on trust.
- Effectively used by every intent that runs any decision module — the band is surfaced generically via the `trust_summary` SSE event at [api/events.py](../../api/events.py).
- Not called for: pure `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE` without analysis.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.purchase_price` | `float` | required | listing facts | Required field per [confidence.py:89](confidence.py#L89). |
| `context.property_data.sqft`, `beds`, `baths`, `town`, `state` | mixed | required | listing facts | Same. |
| `context.prior_outputs` | `dict[str, dict]` | strongly recommended | executor | Without it the module falls back to the data-quality anchor and emits a warning. |
| `context.missing_data_registry` | `dict` | optional | intake / normalization | Keys `provided`, `estimated`, `defaulted`, `missing` drive `_field_completeness` at [confidence.py:169-178](confidence.py#L169-L178) and `_estimated_reliance` at [confidence.py:181-189](confidence.py#L181-L189). |
| `context.assumptions.estimated_monthly_rent` | `float` | optional | router / session | Consulted for contradiction detection at [confidence.py:205](confidence.py#L205). |

## Outputs

`run_confidence` returns `ModulePayload.model_dump()`. Salient fields:

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `confidence` | `float \| None` | 0-1 | Top-level `ModulePayload.confidence`, overwritten at [confidence.py:91-97](confidence.py#L91-L97) with the combined value when available. Rounded to 4 decimals. |
| `confidence_band` | `str` | enum | `"High confidence" \| "Moderate confidence" \| "Low confidence" \| "Speculative"` per `confidence_band` at [scoped_common.py:152-161](scoped_common.py#L152-L161). |
| `extra_data.data_quality_confidence` | `float \| None` | 0-1 | Anchor from `PropertyDataQualityModule`. |
| `extra_data.aggregated_prior_confidence` | `float \| None` | 0-1 | Weighted mean of prior module confidences. |
| `extra_data.prior_module_confidences` | `dict[str, float]` | 0-1 each | Per-module confidences extracted from `context.prior_outputs`. |
| `extra_data.field_completeness` | `float` | 0-1 | `(provided + 0.5·estimated + 0.25·defaulted) / total`, defaulting to `0.4` when the registry is empty. |
| `extra_data.estimated_reliance` | `float` | 0-1 | `(estimated + defaulted) / total`, defaulting to `0.75` when the registry is empty. |
| `extra_data.contradiction_count` | `int` | — | Count from `_contradiction_count` at [confidence.py:192-218](confidence.py#L192-L218). |
| `extra_data.comp_quality` | `float` | 0-1 | Lifted from `valuation` output `data.metrics.comp_confidence_score`; defaults to `0.55` when absent. |
| `extra_data.model_agreement` | `float` | 0-1 | `1 - stddev(prior_confidences) / 0.35`, clamped; `0.6` when fewer than 2 priors. |
| `extra_data.scenario_fragility` | `float` | 0-1 | From `resale_scenario` bull/bear spread or (1 - scenario.confidence); `0.35` when absent. |
| `extra_data.legal_certainty` | `float` | 0-1 | From `legal_confidence.confidence`; `0.7` when absent. |
| `extra_data.combined_confidence` | `float \| None` | 0-1 | Same as top-level `confidence` field. |
| `warnings` | `list[str]` | — | Emitted when no priors were aggregated, when contradictions exist, or when `estimated_reliance >= 0.5`. |
| `assumptions_used.confidence_engine_version` | `str` | — | Always `"v2"`. |
| `assumptions_used.prior_confidence_modules` | `list[str]` | — | Sorted list of module names whose confidences were aggregated. |
| `assumptions_used.perf_log_weights_used` | `bool` | — | True when `load_model_weights` returned a non-empty dict. |

**Note on output shape:** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) reference fields `overall_confidence` and `component_breakdown` that do not literally appear in the output. See [DECISIONS.md](../../DECISIONS.md) entry "confidence output field-name drift in audit docs" (2026-04-24). The concept is correct — the top-level `confidence` serves as "overall_confidence" and `extra_data` serves as the component breakdown with slightly different key names.

## Dependencies

- **Requires (inputs):** none declared — `depends_on=[]` at [registry.py:81](../execution/registry.py#L81). Functionally, `context.prior_outputs` should contain the other modules' outputs; without them the fallback is the data-quality anchor alone plus a warning.
- **Benefits from (optional):** every other scoped module via `prior_outputs`; specifically reads `valuation` (for `comp_confidence_score`), `resale_scenario` (for spread / confidence), and `legal_confidence` (for `confidence`).
- **Calls internally:** `PropertyDataQualityModule` at [briarwood/modules/property_data_quality.py](property_data_quality.py); `load_model_weights` at [briarwood/pipeline/triage.py:30](../pipeline/triage.py#L30) (only when prior confidences are present — gated at [confidence.py:29](confidence.py#L29)).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** none — `confidence` is the rollup, not an input to another module.

## Invariants

- `confidence` is in `[0.0, 1.0]` per the clamp at [confidence.py:166](confidence.py#L166).
- `confidence_band` tiers (from [scoped_common.py:152-161](scoped_common.py#L152-L161)): `≥ 0.75 → "High confidence"`, `≥ 0.55 → "Moderate confidence"`, `≥ 0.3 → "Low confidence"`, `< 0.3 → "Speculative"`, `None → "Speculative"`.
- Penalties: `contradiction_count * 0.12` (capped at 0.45), `scenario_fragility * 0.12`, `estimated_reliance * 0.15`.
- `_combine` weights (at [confidence.py:156-164](confidence.py#L156-L164)): anchor 0.20, evidence_anchor 0.18, completeness 0.16, comp_quality 0.14, model_agreement 0.12, legal_certainty 0.10, (1 - scenario_fragility) 0.10.
- When both `aggregated` and `anchor` are `None`, `_combine` returns `None` and the payload carries the data-quality anchor confidence unchanged.
- Deterministic per input; no LLM calls, no randomness.
- Never mutates its inputs; reads `prior_outputs` as a dict but never writes back.
- Never raises on valid-shaped inputs — defensive `_as_float` handles non-numeric values; the `try/except` fallback pattern is not used because the engine should fail loudly on schema-shape bugs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.confidence import run_confidence

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "purchase_price": 850_000,
        "sqft": 2_100,
        "beds": 4,
        "baths": 2.5,
        "town": "Montclair",
        "state": "NJ",
    },
    prior_outputs={
        "valuation": {"confidence": 0.78, "data": {"metrics": {"comp_confidence_score": 0.82}}},
        "carry_cost": {"confidence": 0.72},
        "risk_model": {"confidence": 0.68},
        "resale_scenario": {"confidence": 0.66, "data": {"metrics": {"bull_bear_spread_pct": 0.18}}},
        "legal_confidence": {"confidence": 0.70},
    },
    missing_data_registry={
        "provided": ["purchase_price", "sqft", "beds", "baths", "town", "state"],
        "estimated": ["estimated_monthly_rent"],
        "defaulted": [],
        "missing": [],
    },
)

payload = run_confidence(context)
# payload["confidence"]                                          ≈ 0.71
# payload["confidence_band"]                                     == "Moderate confidence"
# payload["extra_data"]["prior_module_confidences"]              == {"valuation": 0.78, ...}
# payload["extra_data"]["contradiction_count"]                   == 0
# payload["assumptions_used"]["confidence_engine_version"]       == "v2"
```

## Hardcoded Values & TODOs

- Default `field_completeness` when the missing-data registry is empty: `0.4` at [confidence.py:177](confidence.py#L177).
- Default `estimated_reliance` when the registry is empty: `0.75` at [confidence.py:188](confidence.py#L188) — conservative high.
- Default `comp_quality` when `valuation` has no `comp_confidence_score`: `0.55` at [confidence.py:227](confidence.py#L227).
- Default `model_agreement` when < 2 prior confidences: `0.6` at [confidence.py:233](confidence.py#L233).
- Default `scenario_fragility` when `resale_scenario` is absent: `0.35` at [confidence.py:248](confidence.py#L248).
- Default `legal_certainty` when `legal_confidence` is absent: `0.7` at [confidence.py:257](confidence.py#L257).
- Contradiction thresholds at [confidence.py:207-217](confidence.py#L207-L217): `$/sqft > 1500 or < 75`; `beds ≥ 5 and baths ≤ 1.5`; `gross_yield < 2%` (`rent*12/price`).
- Warning threshold: `estimated_reliance >= 0.5` triggers a message at [confidence.py:59](confidence.py#L59).
- Combine weights (0.20 / 0.18 / 0.16 / 0.14 / 0.12 / 0.10 / 0.10) and penalty coefficients (0.12 / 0.12 / 0.15, contradiction cap 0.45) are all hardcoded in `_combine` at [confidence.py:133-166](confidence.py#L133-L166). No config file override.

## Blockers for Tool Use

- None for invocation. Functionally the module is most useful once other modules have populated `prior_outputs`; running it first produces a usable but anchor-only confidence.

## Notes

- **Output field names drift from the audit docs** ([DECISIONS.md](../../DECISIONS.md) 2026-04-24 entry). The audit talks about `overall_confidence` and `component_breakdown`; in practice the top-level `confidence` serves as overall and `extra_data` serves as breakdown with different key names.
- Weight loading via `load_model_weights` reads a JSONL performance log; absent or empty logs cause the weighted mean to degenerate to a uniform mean (each weight defaults to `1.0` in `_weighted_mean` at [confidence.py:123](confidence.py#L123)).
- Historical audit cross-ref: `calculate_final_score` (the dead 5-category investment-scoring aggregator) was a distinct scoring path from this confidence rollup. It was deleted in Handoff 4 (2026-04-24) after verification of zero production callers — see [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "PROMOTION_PLAN.md entry 15 scope-limit paragraph corrected." This module's confidence rollup is unrelated and unaffected.
- Tests: [tests/modules/test_confidence_isolated.py](../../tests/modules/test_confidence_isolated.py); comp-confidence behavior covered by [tests/test_comp_confidence_engine.py](../../tests/test_comp_confidence_engine.py).
- No direct LLM calls; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: wrapped body in `try/except` and migrated to the canonical error contract. Internal exceptions now return a `module_payload_from_error` fallback (`mode="fallback"`, `confidence=0.08`) rather than propagating. Added [tests/modules/test_confidence_degraded.py](../../tests/modules/test_confidence_degraded.py). See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."

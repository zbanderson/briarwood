# valuation — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`valuation` produces Briarwood's fair-value estimate for a property — the anchor every downstream decision-tier question depends on. It returns the current value in dollars, the signed mispricing percentage versus the listing ask, a `pricing_view` label (`fair`, `undervalued`, `overvalued`, `unavailable`), and a confidence score. Under the hood it reuses the legacy `CurrentValueModule`, which composes four internal anchors (comparable sales, market-value history, income support, and hybrid primary-plus-accessory value) into a single reconciled number, then applies a bounded macro nudge (≤ 3%) on the county's HPI momentum to adjust confidence. Call this tool any time the user's intent needs "what is this worth?" — it is a prerequisite for `risk_model`, `resale_scenario`, `rental_option`, `arv_model`, and `opportunity_cost`.

## Location

- **Entry point:** [briarwood/modules/valuation.py:15](valuation.py#L15) — `run_valuation(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:55-62](../execution/registry.py#L55-L62) — `ModuleSpec(name="valuation", depends_on=[], required_context_keys=["property_data"], runner=run_valuation)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); the inner engine-output dict is shaped by `CurrentValueModule`'s `ValuationOutput` at [briarwood/schemas.py:462](../schemas.py#L462). Payload helpers at [briarwood/modules/scoped_common.py:48-99](scoped_common.py#L48-L99).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `DECISION` — always called; the verdict sits on fair-value vs. ask.
- `BROWSE` — called when the user is browse-evaluating a property ("what do you think of this?").
- `LOOKUP` — called when the user asks the property's worth directly.
- `EDGE` — called when an edge-case question hinges on whether the property is over- or under-priced.
- Often called as a dependency of: `risk_model`, `resale_scenario`, `rental_option`, `arv_model`, `opportunity_cost` (per registry `depends_on` entries).
- Not called for: `SEARCH`, `CHITCHAT`, pure `VISUALIZE` without a property context.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized into a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.purchase_price` | `float` | recommended | user / listing facts | Drives `mispricing_pct`; absence yields degraded confidence + `pricing_view="unavailable"`. |
| `context.property_data.sqft` | `float` | required | listing facts | Required field per error branch at [valuation.py:48](valuation.py#L48). |
| `context.property_data.beds` | `int` | required | listing facts | Same. |
| `context.property_data.baths` | `float` | required | listing facts | Same. |
| `context.property_data.town` | `str` | required | listing / resolver | Same. |
| `context.property_data.state` | `str` | required | listing / resolver | Same. |
| `context.property_summary` | `dict` | optional | property intake | Accepted via `optional_context_keys`. |
| `context.comp_context` | `dict` | optional | earlier comp lookups | Accepted via `optional_context_keys`. |
| `context.market_context` | `dict` | optional | router / session | Accepted via `optional_context_keys`. |
| `context.macro_context.hpi_momentum` | signed `float` | optional | FRED via `macro_reader` | Drives the ≤ 3% confidence nudge at [valuation.py:28-33](valuation.py#L28-L33). Missing ⇒ no nudge applied. |

## Outputs

`run_valuation` returns `ModulePayload.model_dump()`. The salient engine fields (from `CurrentValueModule`'s `ValuationOutput`) sit inside the payload's output dict:

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `briarwood_current_value` | `float \| None` | USD | Reconciled fair value; null when data too sparse. |
| `mispricing_pct` | `float \| None` | signed fraction | `(ask_price − briarwood_current_value) / briarwood_current_value`. |
| `basis_mispricing_pct` | `float \| None` | signed fraction | Same but vs. all-in basis instead of ask, when `all_in_basis` is present at [current_value.py:175-179](current_value.py#L175-L179). |
| `pricing_view` | `str` | enum | `"fair" \| "undervalued" \| "overvalued" \| "unavailable"`. |
| `all_in_basis` | `float \| None` | USD | True cost-to-own anchor; see Known Rough Edges. |
| `confidence` | `float` | 0.0-1.0 | Post-macro-nudge, clamped; rounded to 4 decimals at [valuation.py:51-53](valuation.py#L51-L53). |
| `summary` | `str` | prose | One-sentence narrative, built in `CurrentValueModule._build_summary` around [current_value.py:162-170](current_value.py#L162-L170). |
| `meta.macro_nudge` | `dict` | — | `apply_macro_nudge` telemetry: signal value, raw delta, clamped delta, adjusted confidence. |
| `warnings` | `list[str]` | — | Populated by fallback or when required fields are missing. |
| `assumptions_used.legacy_module` | `str` | — | Always `"CurrentValueModule"`. |
| `assumptions_used.macro_context_used` | `bool` | — | True when an HPI momentum signal was present. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]` at [registry.py:57](../execution/registry.py#L57). Only raw `property_data` is required.
- **Benefits from (optional):** `property_summary`, `comp_context`, `market_context`, `macro_context.hpi_momentum`.
- **Calls internally:** `CurrentValueModule` at [briarwood/modules/current_value.py:19](current_value.py#L19), which itself composes `ComparableSalesModule`, `MarketValueHistoryModule`, `IncomeSupportModule`, and `HybridValueModule` (per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Specialty Models Inventory → Scoped registry). Macro application via `apply_macro_nudge` at [briarwood/modules/macro_reader.py:78](macro_reader.py#L78).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** `risk_model` ([registry.py:72-78](../execution/registry.py#L72-L78)), `resale_scenario` ([registry.py:88-94](../execution/registry.py#L88-L94)), `rental_option` ([registry.py:96-102](../execution/registry.py#L96-L102)), `arv_model` ([registry.py:127-134](../execution/registry.py#L127-L134)), `opportunity_cost` ([registry.py:159-170](../execution/registry.py#L159-L170)).

## Invariants

- Never raises. All exceptions are caught at [valuation.py:55-63](valuation.py#L55-L63) and replaced with a fallback `ModulePayload` whose `warnings` carry the exception type + message and `assumptions_used.fallback_reason == "sparse_or_contradictory_inputs"`.
- Macro nudge is bounded: `MACRO_MAX_NUDGE = 0.03` at [valuation.py:12](valuation.py#L12). `apply_macro_nudge` clamps the raw HPI signal so the final confidence shift never exceeds ±3%.
- `confidence` remains in `[0.0, 1.0]` after the nudge; `apply_macro_nudge` rounds to 4 decimals at [valuation.py:52](valuation.py#L52).
- `pricing_view == "unavailable"` whenever sparse facts or contradictions prevent a stable comp read (per [current_value.py:57-59](current_value.py#L57-L59)).
- Deterministic for a fixed input — no LLM calls, no randomness.
- Comp-driven value estimation remains the dominant signal; the macro nudge only modestly reinforces or discounts the reported confidence (module docstring at [valuation.py:20-22](valuation.py#L20-L22)).

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.valuation import run_valuation

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
    macro_context={"hpi_momentum": {"signal": 0.12, "source": "FRED"}},
)

payload = run_valuation(context)
# payload["output"]["briarwood_current_value"]     ≈ 790_000
# payload["output"]["mispricing_pct"]              ≈ 0.076
# payload["output"]["pricing_view"]                == "overvalued"
# payload["confidence"]                            ∈ [0, 1]
# payload["meta"]["macro_nudge"]["adjusted_confidence"] is not None
```

## Hardcoded Values & TODOs

- `MACRO_MAX_NUDGE = 0.03` at [valuation.py:12](valuation.py#L12) — per-dimension cap on the macro HPI confidence adjustment. Not configurable.
- The legacy `CurrentValueModule` carries the full comp / history / income / hybrid weighting logic; thresholds for `pricing_view` transitions live inside that module rather than in `valuation.py`. Changes to those thresholds are not surfaced here — treat `CurrentValueModule` as the authoritative source.
- `required_fields` hardcoded at [valuation.py:48](valuation.py#L48) and [valuation.py:62](valuation.py#L62): `["purchase_price", "sqft", "beds", "baths", "town", "state"]`.

## Blockers for Tool Use

- None. This model is callable in isolation via `run_valuation(context)` with a populated `ExecutionContext`.

## Notes

- **`all_in_basis` is live in the data path but not rendered in the UI** ([ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges, audit finding `AUDIT_REPORT.md` F-003 / `VERIFICATION_REPORT.md` confirmed-partial). `CurrentValueModule` computes `all_in_basis` and the scoped `valuation` output surfaces `basis_mispricing_pct`; the field propagates through the verdict event ([api/pipeline_adapter.py:615](../../api/pipeline_adapter.py#L615), [api/pipeline_adapter.py:658](../../api/pipeline_adapter.py#L658)) and the TypeScript event type ([web/src/lib/chat/events.ts:152](../../web/src/lib/chat/events.ts#L152)) but no card in [web/src/components/chat/](../../web/src/components/chat/) reads it. Not a code issue in this module — flagging so downstream consumers are aware.
- **`primary_value_source` bridge is adjacent** ([ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges, `NEW-V-005`). The bridge at [briarwood/interactions/primary_value_source.py](../interactions/primary_value_source.py) derives from `valuation` outputs plus other module signals; when its four signal paths all miss, it returns `"unknown"` and downstream cards gate on `!== "unknown"`. Keep in mind when changing `valuation`'s output shape.
- Macro context is opportunistic. Production calls frequently omit `macro_context`; in that case `macro_nudge.signal` is `None` and `adjusted_confidence` stays at the engine-reported confidence.
- Tests exercising `run_valuation` include [tests/test_execution_v2.py](../../tests/test_execution_v2.py), [tests/test_runner_routed.py](../../tests/test_runner_routed.py), [tests/modules/test_valuation_isolated.py](../../tests/modules/test_valuation_isolated.py), and [tests/test_orchestrator.py](../../tests/test_orchestrator.py).
- No direct LLM calls; no cost. (Sub-agents of the internal modules may call LLMs; see the respective legacy module's README once written.)

## Changelog

### 2026-04-24
- Initial README created.

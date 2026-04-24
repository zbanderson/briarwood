# rent_stabilization — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`rent_stabilization` produces a rental-durability read for a property: how easy it will be to rent, how much rent the market will bear, and how supportive the surrounding town/county outlook is. It wraps the legacy `RentalEaseModule` (which internally composes `ScarcitySupportModule` for supply signals) and surfaces `TownCountyOutlookModule` telemetry alongside the result. Call this tool whenever the user's intent involves rental viability — rent-lookup questions, hold-to-rent strategy, or risk conversations where weak rental absorption is a material downside.

## Location

- **Entry point:** [briarwood/modules/rent_stabilization.py:13](rent_stabilization.py#L13) — `run_rent_stabilization(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:103-110](../execution/registry.py#L103-L110) — `ModuleSpec(name="rent_stabilization", depends_on=[], required_context_keys=["property_data"], runner=run_rent_stabilization)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); inner engine outputs shaped by `RentalEaseModule` at [briarwood/modules/rental_ease.py:15](rental_ease.py#L15). Payload helpers at [briarwood/modules/scoped_common.py:48-99](scoped_common.py#L48-L99).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RENT_LOOKUP` — always called; this is the rental-durability anchor.
- `STRATEGY` — called for hold-to-rent and investor paths (dependency of `hold_to_rent`).
- `RISK` — called when the user's question centers on rental absorption risk.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.estimated_monthly_rent` | `float` | required | user / listing / rent context | Required field per error branch at [rent_stabilization.py:43](rent_stabilization.py#L43). |
| `context.property_data.sqft` | `float` | required | listing facts | Same. |
| `context.property_data.beds` | `int` | required | listing facts | Same. |
| `context.property_data.baths` | `float` | required | listing facts | Same. |
| `context.property_data.town` | `str` | required | listing / resolver | Same. |
| `context.property_data.state` | `str` | required | listing / resolver | Same. |
| `context.market_context` | `dict` | optional | router / session | Accepted via `optional_context_keys`. |
| `context.comp_context` | `dict` | optional | earlier lookups | Accepted via `optional_context_keys`. |

## Outputs

`run_rent_stabilization` returns `ModulePayload.model_dump()`. Salient fields (from `RentalEaseModule` output, plus `town_county_outlook` grafted into `extra_data`):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `rental_ease_label` | `str` | enum | `"easy" \| "moderate" \| "difficult" \| "unavailable"` — see [rental_ease.py:111](rental_ease.py#L111). |
| `liquidity_score` | `float` | 0-1 | Rental market liquidity. |
| `demand_depth_score` | `float` | 0-1 | Tenant-demand depth. |
| `rent_support_score` | `float` | 0-1 | Cohort support for the listing's rent level. |
| `structural_support_score` | `float` | 0-1 | Structural factors (unit count, size, zoning) supportive of rental. |
| `estimated_days_to_rent` | `int \| None` | days | Expected DOM on the rental market. |
| `scarcity_support_score` | `float` | 0-1 | Surfaced from the internal `ScarcitySupportModule` call at [rental_ease.py:40](rental_ease.py#L40) (merged into `output` at [rental_ease.py:93](rental_ease.py#L93)). |
| `zillow_context_used` | `bool` | — | True when Zillow ZORI/ZORDI/ZORF signals were available. |
| `confidence` | `float` | 0-1 | `ModulePayload.confidence`; sparse-input fallback inherits the `module_payload_from_error` default of `0.08` at [scoped_common.py:123](scoped_common.py#L123). |
| `summary` | `str` | prose | Human-readable rental-durability narrative. |
| `extra_data.town_county_outlook.score` | `float \| None` | 0-1 | From `TownCountyOutlookModule`. |
| `extra_data.town_county_outlook.confidence` | `float` | 0-1 | Same. |
| `extra_data.town_county_outlook.summary` | `str` | prose | Town-level narrative. |
| `extra_data.town_county_outlook.metrics` | `dict` | mixed | Contains `rental_ease_label` on the fallback path. |
| `warnings` | `list[str]` | — | Populated by fallback. |
| `assumptions_used.legacy_module` | `str` | — | `"RentalEaseModule"`. |
| `assumptions_used.supporting_module` | `str` | — | `"TownCountyOutlookModule"`. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]` at [registry.py:105](../execution/registry.py#L105). Only `property_data` is required.
- **Benefits from (optional):** `market_context`, `comp_context`.
- **Calls internally:** `RentalEaseModule` at [briarwood/modules/rental_ease.py:15](rental_ease.py#L15), which in turn calls `ScarcitySupportModule` at [briarwood/modules/scarcity_support.py](scarcity_support.py) (invoked at [rental_ease.py:40](rental_ease.py#L40)). Also calls `TownCountyOutlookModule` at [briarwood/modules/town_county_outlook.py:12](town_county_outlook.py#L12).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** `hold_to_rent` ([registry.py:111-118](../execution/registry.py#L111-L118)).

## Invariants

- Never raises. All exceptions are caught at [rent_stabilization.py:45-61](rent_stabilization.py#L45-L61) and replaced with a fallback `ModulePayload` (outer `confidence` defaults to `0.08` via `module_payload_from_error` at [scoped_common.py:123](scoped_common.py#L123); `extra_data.town_county_outlook.metrics.rental_ease_label` is `"Unavailable"`).
- `rental_ease_label` is `"unavailable"` when `RentalEaseModule` cannot produce a usable rent signal (per [rental_ease.py:49](rental_ease.py#L49)).
- All component scores (`liquidity`, `demand_depth`, `rent_support`, `structural_support`, `scarcity_support`) are in `[0.0, 1.0]`.
- `confidence` is in `[0.0, 1.0]`.
- Deterministic for a fixed input — no LLM calls, no randomness.
- `town_county_outlook` is always present in `extra_data`, even in fallback (shape preserved so downstream consumers do not need a presence check).

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.rent_stabilization import run_rent_stabilization

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "estimated_monthly_rent": 4_200,
        "sqft": 2_100,
        "beds": 4,
        "baths": 2.5,
        "town": "Montclair",
        "state": "NJ",
    },
)

payload = run_rent_stabilization(context)
# payload["output"]["rental_ease_label"]        == "moderate"
# payload["output"]["rent_support_score"]       ≈ 0.65
# payload["output"]["estimated_days_to_rent"]   ≈ 28
# payload["extra_data"]["town_county_outlook"]["score"] ≈ 0.72
# payload["confidence"]                         ∈ [0, 1]
```

## Hardcoded Values & TODOs

- Sparse-input fallback outer `confidence` is `0.08` (default in `module_payload_from_error` at [scoped_common.py:123](scoped_common.py#L123)). The nested `extra_data.town_county_outlook.confidence` is also hardcoded to `0.08` at [rent_stabilization.py:55](rent_stabilization.py#L55) — these are two separate literals that happen to agree.
- Rent source resolution (actual vs. estimated vs. fallback) lives inside `RentalEaseModule` and its `RentContextAgent`; no geography-specific defaults are stored in this wrapper.
- Zillow ZORI/ZORDI/ZORF signals are consumed through `FileBackedZillowRentContextProvider` inside `RentalEaseModule` — not in this wrapper (per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Specialty Models Inventory → `RentalEaseModule`).

## Blockers for Tool Use

- None. This module is callable in isolation via `run_rent_stabilization(context)` with a populated `ExecutionContext`.

## Notes

- **[ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) / [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) wording is accurate at the behavioral level.** The audit says `rent_stabilization` "Internally runs rental_ease, town_county_outlook, scarcity_support." The scoped wrapper calls `RentalEaseModule` and `TownCountyOutlookModule` directly; `ScarcitySupportModule` is reached transitively via `RentalEaseModule` at [rental_ease.py:40](rental_ease.py#L40). No contradiction to file.
- Tests exercising `run_rent_stabilization` include [tests/modules/test_rent_stabilization_isolated.py](../../tests/modules/test_rent_stabilization_isolated.py) and [tests/test_execution_v2.py](../../tests/test_execution_v2.py).
- No direct LLM calls; no cost. Internal sub-agents may call LLMs if their providers are configured (income / rent context).

## Changelog

### 2026-04-24
- Initial README created.

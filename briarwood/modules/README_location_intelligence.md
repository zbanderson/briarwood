# location_intelligence — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`location_intelligence` benchmarks a subject property's landmark proximity (beach, downtown, park, train, ski) against same-town peer comp buckets, producing per-category scores, distance benefits, percentile benefits, and a rolled-up location score. It answers the orchestrator's question *"how strong is this property's micro-location relative to similar properties in the same town?"* — the signal behind MICRO_LOCATION intents and the location-premium component of the valuation stack. Under the hood it loads same-town peer comps from `data/comps/sales_comps.json`, bucketizes subject-vs-peer distance to each landmark, and computes percentile premiums. Call this tool when the user's intent involves location quality, walkability, landmark proximity, or "is this a good block?" — it is the first tool to cover the MICRO_LOCATION intent family as a standalone.

## Location

- **Entry point:** [briarwood/modules/location_intelligence_scoped.py](location_intelligence_scoped.py) — `run_location_intelligence(context: ExecutionContext) -> dict[str, object]`.
- **Legacy module:** [briarwood/modules/location_intelligence.py:52](location_intelligence.py#L52) — `LocationIntelligenceModule.run(property_input)`.
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="location_intelligence", depends_on=[], required_context_keys=["property_data"], runner=run_location_intelligence)`.
- **Data source:** `data/comps/sales_comps.json` via `FileBackedComparableSalesProvider` (shared with `comparable_sales`).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `MICRO_LOCATION` — always called; this is the primary tool for MICRO_LOCATION intents.
- `RESEARCH` — called for "is this a good block?" / location-quality questions.
- `BROWSE` — called as context for browse-mode summaries with location signals.
- `EDGE` — called for edge-case questions about landmark premiums or flood/zone proxies.
- Not called for: `CHITCHAT`, pure `VISUALIZE` without a location context.

## Inputs

Inputs arrive through `ExecutionContext` and are normalized into a `PropertyInput` via `build_property_input_from_context`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.town` | `str` | required | listing facts | Used as the peer-comp geography key. |
| `context.property_data.state` | `str` | required | listing facts | Same. |
| `context.property_data.latitude`, `longitude` | `float` | recommended | geocoder | Absence degrades: `missing_inputs=["subject_coordinates"]` and location buckets cannot be formed. |
| `context.property_data.landmark_points` | `dict[str, list[Point]]` | recommended | landmark resolver | Per-category landmark sets (`beach`, `downtown`, `park`, `train`, `ski`). Absence degrades: `missing_inputs=["landmark_points"]`. |
| `context.property_data.zone_flags` | `list[str]` | optional | listing / resolver | Includes premium-zone flags (`in_beach_premium_zone`, `in_downtown_zone`). |
| `context.property_data.purchase_price`, `sqft` | mixed | required | listing facts | Used for subject PPSF anchor. |

## Outputs

The runner returns `ModulePayload.model_dump()`. The payload surfaces the `LocationIntelligenceOutput` dataclass.

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.metrics.location_score` | `float` | 0–1 | Rolled-up score across all available categories. |
| `data.metrics.scarcity_score` | `float` | 0–1 | Supply-side complement (distinct from `scarcity_support`'s town-level score). |
| `data.metrics.primary_category` | `str` | enum | Which landmark category dominates the narrative (`beach`, `downtown`, `park`, `train`, `ski`). |
| `data.legacy_payload.subject_ppsf` | `float \| None` | USD / sqft | Subject's price-per-sqft anchor. |
| `data.legacy_payload.location_premium_pct` | `float \| None` | fraction | Peer-relative location premium. |
| `data.legacy_payload.subject_relative_premium_pct` | `float \| None` | fraction | Subject vs. peer median. |
| `data.legacy_payload.category_results` | `list[LocationCategoryIntelligence]` | — | Per-category buckets, distances, percentiles, and narratives. |
| `data.legacy_payload.narratives` | `list[str]` | — | Category-level one-liners for synthesis. |
| `data.legacy_payload.confidence_notes` | `list[str]` | — | Why confidence is low when inputs are sparse. |
| `data.legacy_payload.missing_inputs` | `list[str]` | — | Specific missing-input flags (`subject_coordinates`, `landmark_points`, `geo_peer_comps`, `geo_comp_coordinates`). |
| `data.legacy_payload.zone_flags` | `list[str]` | — | Premium-zone flags passed through. |
| `confidence` | `float` | 0.0–1.0 | Engine confidence; low when `missing_inputs` is non-empty. |
| `warnings` | `list[str]` | — | Populated on caught-exception fallback. |
| `assumptions_used.benchmarks_against_town_peer_comps` | `bool` | — | Always `True`. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]`.
- **Benefits from (optional):** `property_summary`, `comp_context`.
- **Calls internally:** `FileBackedComparableSalesProvider` (reads `data/comps/sales_comps.json`).
- **Must not run concurrently with:** none.
- **Downstream consumers (read module outputs by key):**
  - [briarwood/micro_location_engine.py](../micro_location_engine.py)
  - [briarwood/evidence](../evidence/) (two paths)
  - [briarwood/decision_model/scoring.py:295-296](../decision_model/scoring.py#L295)
  - several eval specs under [briarwood/eval/](../eval/)

## Invariants

- Never raises. Exceptions caught and replaced with a fallback `ModulePayload` (`mode="fallback"`, `confidence=0.08`, `fallback_reason="provider_or_geocode_error"`).
- **Missing-input semantics preserved.** When `subject_coordinates`, `landmark_points`, `geo_peer_comps`, or `geo_comp_coordinates` are absent, the legacy module returns a valid `ModuleResult` with `confidence_notes` and `missing_inputs` populated. The scoped wrapper passes these through; the resulting payload may resolve to `mode="fallback"` via `_infer_payload_mode` when confidence is low, but `assumptions_used.fallback_reason` will NOT be `"provider_or_geocode_error"` — that reason is reserved for caught exceptions. This distinction lets callers tell "legitimate low-confidence answer" from "wrapper-caught failure."
- `location_score`, `scarcity_score` ∈ `[0.0, 1.0]`.
- `category_results` only includes categories with landmark points provided.
- Deterministic per input; no LLM calls, no randomness.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.location_intelligence_scoped import run_location_intelligence

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "town": "Avon By The Sea",
        "state": "NJ",
        "latitude": 40.1907,
        "longitude": -74.0158,
        "purchase_price": 1_250_000,
        "sqft": 2_000,
        "landmark_points": {
            "beach": [{"lat": 40.1915, "lon": -74.0140}],
            "downtown": [{"lat": 40.1908, "lon": -74.0151}],
        },
        "zone_flags": ["in_beach_premium_zone"],
    },
)

payload = run_location_intelligence(context)
# payload["data"]["metrics"]["location_score"]          ≈ 0.81
# payload["data"]["metrics"]["primary_category"]        == "beach"
# payload["data"]["legacy_payload"]["location_premium_pct"] ≈ 0.19
# payload["confidence"]                                 ∈ [0, 1]
```

## Hardcoded Values & TODOs

- Category-specific distance buckets (BEACH, DOWNTOWN, SKI, DEFAULT) hardcoded at [location_intelligence.py:18-46](location_intelligence.py#L18-L46).
- Category ordering hardcoded at [location_intelligence.py:48](location_intelligence.py#L48): `["beach", "downtown", "park", "train", "ski"]`.
- Premium-zone flags hardcoded at [location_intelligence.py:49](location_intelligence.py#L49): `("in_beach_premium_zone", "in_downtown_zone")`.
- Data file path is hardcoded at [location_intelligence.py:58-60](location_intelligence.py#L58-L60); the provider can be injected to override.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Shared comp provider with `comparable_sales`.** Both tools read `data/comps/sales_comps.json`; changes to the seed dataset affect both paths.
- Tests: [tests/modules/test_location_intelligence_isolated.py](../../tests/modules/test_location_intelligence_isolated.py) covers isolation, missing-input behavior, error contract, and registry integration.
- Latency: depends on comp-file size; under typical fixtures <10ms. No LLM calls.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 11.
- Contract: new scoped runner `run_location_intelligence(context)` wraps `LocationIntelligenceModule.run(property_input)` via `module_payload_from_legacy_result`. Missing-input degradation semantics preserved verbatim. Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*.

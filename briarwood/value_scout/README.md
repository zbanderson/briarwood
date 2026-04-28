# value_scout — Scout Dispatcher + Insight Surfacer

**Last Updated:** 2026-04-28
**Layer:** Value Scout (Layer 5 — sequential today; shared dispatcher + deterministic rails)
**Status:** EXPERIMENTAL

## Purpose

The Value Scout surfaces non-obvious "Finds" the user did not explicitly ask for. It now has one shared dispatcher, `scout(...)`, that handles both existing claim-wedge scout inputs and chat-tier `UnifiedIntelligenceOutput` inputs.

For claim-wedge inputs, Scout runs deterministic pure-function patterns such as `uplift_dominance`. For chat-tier inputs, Scout first runs registered deterministic patterns (`rent_angle`, `adu_signal`, `town_trend_tailwind`) and, when an LLM is provided, the LLM scout from `llm_scout.py`. All surfaced insights are ranked by `SurfacedInsight.confidence`; the top insights win regardless of whether they came from a deterministic pattern or the LLM. If the LLM scout returns empty, the deterministic chat-tier rails can still surface a Scout Find.

`scout_claim(...)` remains as a back-compat wrapper for the claims wedge. It calls `scout(claim, max_insights=1)` and returns the first insight or `None`.

## Location

- **Shared dispatcher:** [briarwood/value_scout/scout.py](scout.py) — `scout(input_obj, *, llm=None, intent=None, max_insights=2) -> list[SurfacedInsight]`.
- **Claim wrapper:** [briarwood/value_scout/scout.py](scout.py) — `scout_claim(claim: VerdictWithComparisonClaim) -> SurfacedInsight | None`.
- **Registry:** `_PATTERNS` in [scout.py](scout.py), keyed by input type:
  - `VerdictWithComparisonClaim`
  - `UnifiedIntelligenceOutput`
- **LLM scout:** [briarwood/value_scout/llm_scout.py](llm_scout.py) — `scout_unified(...) -> tuple[list[SurfacedInsight], dict]`.
- **Patterns:** [briarwood/value_scout/patterns/](patterns/). Today:
  - [patterns/uplift_dominance.py](patterns/uplift_dominance.py) — `detect(claim) -> SurfacedInsight | None`.
  - [patterns/rent_angle.py](patterns/rent_angle.py) — `detect(unified) -> SurfacedInsight | None`.
  - [patterns/adu_signal.py](patterns/adu_signal.py) — `detect(unified) -> SurfacedInsight | None`.
  - [patterns/town_trend_tailwind.py](patterns/town_trend_tailwind.py) — `detect(unified) -> SurfacedInsight | None`.
- **Schemas:** `SurfacedInsight` at [briarwood/claims/base.py](../claims/base.py); `VerdictWithComparisonClaim` at [briarwood/claims/verdict_with_comparison.py](../claims/verdict_with_comparison.py); `UnifiedIntelligenceOutput` at [briarwood/routing_schema.py](../routing_schema.py).
- **Tests:** [tests/value_scout/test_scout.py](../../tests/value_scout/test_scout.py), [tests/value_scout/test_chat_patterns.py](../../tests/value_scout/test_chat_patterns.py), [tests/value_scout/test_uplift_dominance.py](../../tests/value_scout/test_uplift_dominance.py), [tests/value_scout/test_llm_scout.py](../../tests/value_scout/test_llm_scout.py).

## Role in the Six-Layer Architecture

- **This layer:** Value Scout (Layer 5). Target-state Layer 5 eventually fires in parallel with Layer 2 orchestration; the current implementation is still sequential.
- **Claim-wedge caller:** `_maybe_handle_via_claim` in [briarwood/agent/dispatch.py](../agent/dispatch.py) calls `scout_claim` between claim synthesis and editor validation.
- **Chat-tier callers:** BROWSE, DECISION fall-through, and EDGE paths call `scout` over the full `UnifiedIntelligenceOutput` before `synthesize_with_llm`, cache insights on `session.last_scout_insights`, and pass the same insights into the synthesizer.
- **UI surface:** `api/pipeline_adapter.py` emits `scout_insights`; `web/src/components/chat/scout-finds.tsx` renders the user-facing "Scout Finds" surface.

## LLM Usage

`scout(...)` invokes the LLM only for `UnifiedIntelligenceOutput` inputs when `llm` is provided. The LLM path delegates to `scout_unified`, which uses `complete_structured_observed(surface="value_scout.scan", ...)`, applies numeric grounding via `verify_response`, and returns an empty contract on missing inputs, budget cap, blank response, exception, or ungrounded-after-regen. The LLM prompt now biases toward genuinely non-obvious Finds and prefers canonical categories (`rent_angle`, `adu_signal`, `town_trend_tailwind`, `comp_anomaly`, `carry_yield_mismatch`, `optionality`) while still allowing a new label when the evidence truly does not fit.

The deterministic claim-wedge and chat-tier pattern paths are pure: no network, disk, randomness, or LLM.

## Inputs

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `input_obj` | `VerdictWithComparisonClaim` | Claims synthesis | Runs claim-wedge deterministic patterns. |
| `input_obj` | `UnifiedIntelligenceOutput` or compatible `dict` | Chat-tier consolidated artifact | Runs registered chat-tier patterns when the input validates as `UnifiedIntelligenceOutput`; loose dicts still pass through to the LLM scout for back-compat with existing artifacts. Deterministic chat-tier patterns read typed fields plus `supporting_facts` evidence such as `rental_option`, `carry_cost`, `legal_confidence`, `market_value_history`, and comp-rent rows when present. |
| `llm` | `LLMClient | None` | Dispatch | Optional. Only used for chat-tier inputs. |
| `intent` | `IntentContract | None` | Dispatch | Optional but recommended for chat-tier calls so the LLM scout keeps per-tier voice. Defaults to a BROWSE-like contract when omitted. |
| `max_insights` | `int` | Caller | Default `2`. Applies after confidence sorting. |

## Outputs

| Output | Type | Consumer | Notes |
|--------|------|----------|-------|
| `scout(...)` | `list[SurfacedInsight]` | Chat-tier handlers, tests, future pattern rails | Sorted by `confidence` descending and capped by `max_insights`. |
| `scout_claim(...)` | `SurfacedInsight | None` | Claims wedge | Back-compat wrapper; returns the first result from `scout(claim, max_insights=1)`. |

`SurfacedInsight.confidence` is now the universal scoring channel. LLM insights provide self-rated confidence. Deterministic `uplift_dominance` derives confidence from the dominance multiple: `min(1.0, 0.5 + 0.1 * multiple)`.

## Dependencies on Other Modules

- **Schema dependency on:** `briarwood.claims.base.SurfacedInsight`, `briarwood.claims.verdict_with_comparison.VerdictWithComparisonClaim`, and `briarwood.routing_schema.UnifiedIntelligenceOutput`.
- **Intent dependency on:** `briarwood.intent_contract.IntentContract` for chat-tier LLM voice.
- **LLM dependency on:** `briarwood.value_scout.llm_scout.scout_unified`, which uses shared LLM observability and numeric guardrails.
- **Pattern dependency on:** modules in `briarwood/value_scout/patterns/`.
- **Coupled to:** the claims editor for claim-wedge `scenario_id` coherence; the SSE adapter and `ScoutFinds` surface for chat-tier presentation.

## Invariants

- `scout_claim` remains deterministic for a fixed claim input.
- Claim-wedge patterns must not mutate the claim.
- Claim-wedge insights that set `scenario_id` must point to an existing `ComparisonScenario`.
- `scout(...)` ranks by `SurfacedInsight.confidence`; missing confidence sorts as `0.0`.
- Chat-tier deterministic patterns must only use structured fields already present on the unified output; they do not fetch data.
- Chat-tier LLM scout output must be numerically grounded in the `UnifiedIntelligenceOutput`.
- Empty scout output is represented as `[]` for `scout(...)` and `None` for `scout_claim(...)`.

## State & Side Effects

- **Stateless:** yes — the dispatcher and deterministic patterns hold no mutable runtime state.
- **Writes to disk:** no direct writes from `scout.py` or deterministic patterns. The LLM scout uses shared LLM observability, which may append to `data/llm_calls.jsonl` through the existing infrastructure.
- **Manifest notes:** chat-tier `scout(...)` calls record a turn-manifest note with `insights_generated`, `insights_surfaced`, and `top_confidence` when a turn manifest is active.
- **Modifies session:** no. Dispatch caches returned insights on `session.last_scout_insights`.
- **Safe to call concurrently:** yes for deterministic paths. LLM calls inherit the provider/client concurrency posture.

## Example Calls

```python
from briarwood.value_scout import scout, scout_claim

# Back-compat claim wedge.
insight = scout_claim(claim)

# Chat tier.
insights = scout(
    unified_output,
    llm=llm,
    intent=intent_contract,
    max_insights=2,
)
```

## Patterns Today

### `uplift_dominance` ([patterns/uplift_dominance.py](patterns/uplift_dominance.py))

Looks at non-subject scenarios in a `VerdictWithComparisonClaim` and selects the renovation path with the highest uplift-to-investment ratio. Fires when:

- The winner's `uplift_total / investment` ratio is at least `UPLIFT_DOMINANCE_THRESHOLD = 1.0`.
- The winner dominates the runner-up by at least `DOMINANCE_MULTIPLE_THRESHOLD = 1.5`.
- At least two non-subject candidate scenarios exist with positive uplift.

The pattern still uses placeholder renovation costs. Its output should not be treated as a hard renovation-cost claim until a real cost model or user-supplied cost input lands.

### `rent_angle` ([patterns/rent_angle.py](patterns/rent_angle.py))

Looks for rental upside the user did not explicitly ask about. Primary rail: comp rows with `rent_zestimate` and sale/ask price imply a median gross rental yield of at least `6.0%`, or median comp rent covers monthly carry by at least `1.05x`. Secondary rail: `rental_option.rent_support_score >= 0.70` with monthly cash flow no worse than `-$500`, unless the user text already appears rent-focused.

### `adu_signal` ([patterns/adu_signal.py](patterns/adu_signal.py))

Looks for `legal_confidence` evidence that flags an accessory-unit signal with credible legal-confidence support. It does not classify legality; it only surfaces the existence of structured optionality evidence.

### `town_trend_tailwind` ([patterns/town_trend_tailwind.py](patterns/town_trend_tailwind.py))

Looks for `market_value_history.three_year_change_pct >= 10%` and surfaces the town-level appreciation tailwind as a non-obvious context angle.

## Known Rough Edges

- **Sequential, not parallel.** Layer 5 target-state calls for Scout to fire alongside Layer 2 orchestration; today it runs after consolidated output exists.
- **Thin live evidence for some rails.** Chat-tier deterministic patterns are registered, but they only fire when the unified output includes the needed supporting facts. If the chat-tier artifact omits comp-rent rows or detailed module metrics, those rails correctly stay quiet.
- **Placeholder renovation costs.** `uplift_dominance` still uses a hardcoded per-tier cost table.
- **No user-type conditioning.** Patterns do not yet vary by investor vs owner-occupant.

## Open Product Decisions

- **Parallel firing alongside Layer 2.** Deferred until profiling and product shape justify it.
- **Pure-function thresholds.** Initial Cycle 6 thresholds are intentionally conservative; tune after live Scout yield review in `/admin`.
- **User-type conditioning.** Out of scope for v1 until user-type plumbing lands.

## Changelog

### 2026-04-28
- Contract change: registered deterministic chat-tier fallback patterns under the `UnifiedIntelligenceOutput` key: `rent_angle`, `adu_signal`, and `town_trend_tailwind`.
- Contract change: chat-tier `scout(...)` can now surface deterministic insights even when the LLM scout returns empty or no LLM is provided.
- Contract change: chat-tier Scout calls record a manifest note with `insights_generated`, `insights_surfaced`, and `top_confidence`.
- Prompt change: tuned the LLM scout prompt away from synthesizer-adjacent restatements and toward canonical category discipline.
- Contract change: added `scout(input_obj, *, llm=None, intent=None, max_insights=2) -> list[SurfacedInsight]` as the shared dispatcher for claim-wedge and chat-tier Scout inputs.
- Contract change: `_PATTERNS` changed from a flat tuple to a registry keyed by `VerdictWithComparisonClaim` and `UnifiedIntelligenceOutput`.
- Contract change: `SurfacedInsight.confidence` is now the universal Scout sort key; deterministic `uplift_dominance` assigns confidence from the dominance multiple.
- Back-compat: `scout_claim` remains indefinitely as a wrapper returning the first claim insight or `None`.

### 2026-04-24
- Initial README created.
- Removed "distinguish from `value_finder`" note — `value_finder` was deleted in Handoff 4 (PROMOTION_PLAN.md entry 14); the naming collision no longer exists.

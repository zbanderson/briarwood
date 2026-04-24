# value_scout — Pattern-Driven Insight Surfacer

**Last Updated:** 2026-04-24
**Layer:** Value Scout (Layer 5 — partial; runs sequentially in the claim wedge today)
**Status:** EXPERIMENTAL

## Purpose

The Value Scout scans a fully-built `VerdictWithComparisonClaim` for non-obvious value angles the user did not explicitly ask about. It runs a registered set of pure-function patterns over the claim and returns the single strongest `SurfacedInsight` — a headline, a reason, the supporting field paths, and a `scenario_id` pointer — or `None` if no pattern matched. The Phase 3 wedge then grafts that insight onto the claim (via `claim.surfaced_insight` and `comparison.emphasis_scenario_id`) so the editor and the representation layer can treat it as part of the claim from that point forward. Today exactly one pattern is registered (`uplift_dominance`); the registry shape is multi-pattern so additional detectors can land without changing callers.

## Location

- **Entry point:** [briarwood/value_scout/scout.py:26](scout.py#L26) — `scout_claim(claim: VerdictWithComparisonClaim) -> SurfacedInsight | None`.
- **Pattern registry:** `_PATTERNS` tuple at [briarwood/value_scout/scout.py:23](scout.py#L23). Adding a pattern requires extending this tuple and importing the new detect function.
- **Patterns:** [briarwood/value_scout/patterns/](patterns/). Today: [briarwood/value_scout/patterns/uplift_dominance.py:55](patterns/uplift_dominance.py#L55) — `detect(claim) -> SurfacedInsight | None`.
- **Public surface:** `scout_claim` re-exported from [briarwood/value_scout/__init__.py](__init__.py).
- **Schemas (consumed):** `VerdictWithComparisonClaim` at [briarwood/claims/verdict_with_comparison.py:75](../claims/verdict_with_comparison.py#L75); `ComparisonScenario` at [briarwood/claims/verdict_with_comparison.py:37](../claims/verdict_with_comparison.py#L37); `SurfacedInsight` at [briarwood/claims/base.py:49](../claims/base.py#L49).
- **Tests:** [tests/value_scout/test_scout.py](../../tests/value_scout/test_scout.py); [tests/value_scout/test_uplift_dominance.py](../../tests/value_scout/test_uplift_dominance.py).
- **Feature flags:** Not directly gated. Runs only inside `_maybe_handle_via_claim` at [briarwood/agent/dispatch.py:1853](../agent/dispatch.py#L1853), which is gated by `claims_enabled_for(property_id)` at [briarwood/feature_flags.py:22](../feature_flags.py#L22).

## Role in the Six-Layer Architecture

- **This layer:** Value Scout (Layer 5) — but partial. The target-state Layer 5 in [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) describes a **parallel** process that fires alongside Layer 2 orchestration. Today the Scout runs **sequentially** after the Synthesis call inside the claim wedge, before the Editor.
- **Called by:** `_maybe_handle_via_claim` at [briarwood/agent/dispatch.py:1853](../agent/dispatch.py#L1853). Wedge order: `build_claim_for_property` → `scout_claim` → graft insight → `edit_claim` → `render_claim`.
- **Calls:** Each registered pattern in `_PATTERNS`. Patterns are pure — they read the claim and return an insight or `None`.
- **Returns to:** Caller (`_maybe_handle_via_claim`). Returns `SurfacedInsight | None`. The wedge handles the graft.
- **Emits events:** None directly. The grafted `surfaced_insight` rides on the claim into Representation, which projects relevant fields onto SSE events.

## LLM Usage

None. The Scout is entirely deterministic — pure-function pattern detection.

## Inputs

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `claim` | `VerdictWithComparisonClaim` | Claims synthesis (`build_claim_for_property` at [briarwood/claims/pipeline.py:28](../claims/pipeline.py#L28)) | Already Pydantic-validated; not yet edited. |

## Outputs

| Output | Type | Consumer | Notes |
|--------|------|----------|-------|
| `SurfacedInsight \| None` | `SurfacedInsight` from [briarwood/claims/base.py:49](../claims/base.py#L49) | `_maybe_handle_via_claim` graft step at [briarwood/agent/dispatch.py:1854-1862](../agent/dispatch.py#L1854-L1862) | `headline`, `reason`, `supporting_fields: list[str]`, `scenario_id: str \| None`. `None` means no pattern matched — the wedge proceeds without modifying the claim. |

When the Scout returns a non-null insight, the wedge:
1. Sets `claim.surfaced_insight = insight`.
2. Sets `claim.comparison.emphasis_scenario_id = insight.scenario_id`.

The editor's `check_emphasis_coherence` then verifies the two stay aligned ([briarwood/editor/checks.py:69](../editor/checks.py#L69)).

## Dependencies on Other Modules

- **Schema dependency on:** `briarwood.claims.verdict_with_comparison` (`VerdictWithComparisonClaim`, `ComparisonScenario`) and `briarwood.claims.base` (`SurfacedInsight`).
- **Imports:** the `uplift_dominance` pattern module. No network, disk, LLM, or session imports.
- **Coupled to:** the editor — patterns must produce insights whose `scenario_id` references a real scenario in `claim.comparison.scenarios`, otherwise the editor will reject the claim. Coupled to Representation — `surfaced_insight.scenario_id` flows into chart-emphasis decisions.

## Invariants

- `scout_claim` is deterministic for a fixed input — pure functions, no LLM, no randomness, no I/O.
- Never mutates the claim (the wedge mutates via `claim.model_copy(update=...)`).
- Pattern firing order is the order in `_PATTERNS`. With only one pattern today, "strongest" collapses to "first non-null" per the docstring at [scout.py:9-11](scout.py#L9-L11).
- A returned `scenario_id` always points to a real `ComparisonScenario` in the claim, because patterns derive it from `claim.comparison.scenarios` directly. The editor's `check_emphasis_coherence` enforces this from the consuming side.
- Returns `None` rather than a degraded insight when no pattern matches — the wedge treats `None` as "claim stays as-is."

## State & Side Effects

- **Stateless:** yes — module holds no mutable state; all inputs are function arguments.
- **Writes to disk:** no.
- **Modifies session:** no.
- **Safe to call concurrently:** yes.

## Example Call

```python
from briarwood.claims.pipeline import build_claim_for_property
from briarwood.value_scout import scout_claim

claim = build_claim_for_property("NJ-0000001", user_text="Is this a buy?")
insight = scout_claim(claim)
if insight is not None:
    # Wedge then grafts insight + emphasis_scenario_id onto the claim
    claim = claim.model_copy(update={
        "surfaced_insight": insight,
        "comparison": claim.comparison.model_copy(
            update={"emphasis_scenario_id": insight.scenario_id}
        ),
    })
# `insight.headline`           — short prose surfacing the angle
# `insight.reason`             — supporting reason
# `insight.supporting_fields`  — claim field paths the insight rests on
# `insight.scenario_id`        — ComparisonScenario id this insight emphasizes (or None)
```

## Patterns Today

### `uplift_dominance` ([patterns/uplift_dominance.py](patterns/uplift_dominance.py))

Looks at non-subject scenarios (e.g., `renovated_same`, `renovated_plus_bath`) and selects the one with the highest uplift-to-investment ratio. Fires when:
- The winner's `uplift_total / investment` ratio is at least `UPLIFT_DOMINANCE_THRESHOLD = 1.0` ([patterns/uplift_dominance.py:30](patterns/uplift_dominance.py#L30)).
- The winner dominates the runner-up by at least `DOMINANCE_MULTIPLE_THRESHOLD = 1.5` ([patterns/uplift_dominance.py:35](patterns/uplift_dominance.py#L35)).
- At least two non-subject candidate scenarios exist with positive uplift.

`investment` is a placeholder per-tier table at [patterns/uplift_dominance.py:39-43](patterns/uplift_dominance.py#L39-L43): `renovated_same → $100k`, `renovated_plus_bath → $175k`, default `$150k`. The pattern's docstring at [patterns/uplift_dominance.py:8-15](patterns/uplift_dominance.py#L8-L15) flags this as Phase B work — replace with a real cost model or user-supplied costs. The prose layer is told not to repeat the placeholder ratio verbatim.

## Known Rough Edges

- **Sequential, not parallel.** [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 5 calls for the Scout to fire alongside Layer 2 orchestration (parallel). Today it runs after Synthesis inside the claim wedge.
- **Single pattern.** Only `uplift_dominance` is registered. The "first non-null" selection at [scout.py:28-32](scout.py#L28-L32) collapses to "the only one" today; when a second pattern lands, a comparable scoring channel on `SurfacedInsight` (or a side-channel) needs to exist before "strongest" is meaningful.
- **Placeholder renovation costs.** `uplift_dominance` uses a hardcoded per-tier cost table. The pattern's headline/reason should not be parroted to the user as a hard claim until a real cost model lands.
- **Single archetype.** Patterns today only target `VerdictWithComparisonClaim`. Other claim archetypes ([briarwood/claims/archetypes.py](../claims/archetypes.py)) would need their own patterns, or the Scout would need an archetype dispatch.
- **No user-type conditioning.** Per [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 5, patterns should differ by user type (investor vs. first-time buyer). No mechanism today.

## Open Product Decisions

(Pulled from [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 5; no Scout-specific decisions invented here.)

- **Parallel vs. sequential firing.** Sequential keeps the wedge simple but loses the "two-steps-ahead" framing target-state describes. Parallel introduces ordering coordination with Synthesis and the Editor.
- **Trigger discipline.** Even at one pattern, the Scout's "headline/reason" framing risks reading as a noisy upsell on every turn. Once more patterns land, a "one insight per turn" cap with a confidence threshold is open.
- **Scoring across patterns.** The current "first non-null" selection works at one pattern. The shared scoring channel (`SurfacedInsight.score: float`? a per-pattern `select_strongest` function?) is undecided.

## Changelog

### 2026-04-24
- Initial README created.
- Removed "distinguish from `value_finder`" note — `value_finder` was deleted in Handoff 4 (PROMOTION_PLAN.md entry 14); the naming collision no longer exists.

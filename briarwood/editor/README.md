# editor — Claim-Object Validator

**Last Updated:** 2026-04-24
**Layer:** Unified Intelligence (Layer 3 — narrow structural validator)
**Status:** EXPERIMENTAL

## Purpose

The editor is the pass/fail gate that sits between Synthesis and Representation inside the Phase 3 claim-object pipeline. Given a fully-built `VerdictWithComparisonClaim` (with any `surfaced_insight` already grafted by the Value Scout), it runs a fixed ordered set of five pure-function checks — schema conformance, scenario sample-size presence, verdict-label/delta coherence, emphasis/insight agreement, and caveat coverage for small-sample scenarios — and returns an `EditResult(passed, failures)`. On pass, the claim is handed to Representation to render prose + chart + SSE events. On fail, the dispatch wedge falls through to the legacy synthesis path and emits an `EVENT_CLAIM_REJECTED` SSE event so dev tooling can observe rejection rates without the user-facing stream changing shape. It exists as a distinct layer because the synthesizer must not mark its own homework: the editor's job is to catch contract drift between the claim schema, the synthesizer's thresholds, and the Scout's insight attachment.

## Location

- **Entry point:** [briarwood/editor/validator.py:32](validator.py#L32) — `edit_claim(claim: VerdictWithComparisonClaim) -> EditResult`.
- **Checks:** [briarwood/editor/checks.py](checks.py) — five functions listed under "Role in the Six-Layer Architecture" below.
- **Schemas:** Consumes `VerdictWithComparisonClaim` at [briarwood/claims/verdict_with_comparison.py:75](../claims/verdict_with_comparison.py#L75) and the nested `Verdict` at [briarwood/claims/verdict_with_comparison.py:25](../claims/verdict_with_comparison.py#L25). No editor-owned schemas.
- **Public surface:** `edit_claim`, `EditResult` re-exported from [briarwood/editor/__init__.py](__init__.py).
- **Tests:** [tests/editor/test_validator.py](../../tests/editor/test_validator.py); integration coverage in [tests/claims/test_dispatch_branch.py](../../tests/claims/test_dispatch_branch.py).
- **Feature flags:** Not directly gated. The editor only runs inside the `_maybe_handle_via_claim` wedge ([briarwood/agent/dispatch.py:1809-1884](../agent/dispatch.py#L1809-L1884)), which is gated by `claims_enabled_for(property_id)` at [briarwood/feature_flags.py:22](../feature_flags.py#L22).

## Role in the Six-Layer Architecture

- **This layer:** Unified Intelligence (Layer 3) — but narrow. The editor checks structural coherence of a synthesized claim; it does NOT check intent-satisfaction (the broader Layer 3 role called out in [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 3).
- **Called by:** `_maybe_handle_via_claim` wedge in [briarwood/agent/dispatch.py:1865](../agent/dispatch.py#L1865). The wedge first runs `build_claim_for_property` ([briarwood/claims/pipeline.py](../claims/pipeline.py)), then `scout_claim` ([briarwood/value_scout/scout.py](../value_scout/scout.py)) to graft a `surfaced_insight`, then invokes `edit_claim`.
- **Calls:** None — pure-function checks.
- **Returns to:** Caller (`_maybe_handle_via_claim`). On `passed=True` the caller proceeds to `render_claim` ([briarwood/claims/representation/verdict_with_comparison.py:52](../claims/representation/verdict_with_comparison.py#L52)). On `passed=False` the caller writes `session.last_claim_rejected` and returns `None`, which causes the decision handler to fall through to the legacy synthesis path.
- **Emits events:** Indirectly. The `claim_rejected` event is constructed in [api/events.py:302-317](../../api/events.py#L302-L317) with type constant `EVENT_CLAIM_REJECTED = "claim_rejected"` at [api/events.py:41](../../api/events.py#L41). The SSE adapter reads `session.last_claim_rejected` to emit it.
- **Check order** (fixed; diagnostic readability only — every check always runs per [validator.py:17-24](validator.py#L17-L24)):
  1. `check_schema_conformance` ([checks.py:23](checks.py#L23)) — trivial today; Pydantic has already validated. Kept as a named function so future non-Pydantic invariants land here.
  2. `check_scenario_data_completeness` ([checks.py:32](checks.py#L32)) — `scenario.sample_size > 0` for every scenario in `comparison.scenarios`.
  3. `check_verdict_delta_coherence` ([checks.py:44](checks.py#L44)) — `verdict.label` matches the threshold rule on `ask_vs_fmv_delta_pct` (`<= -5% → value_find`, `>= +5% → overpriced`, else `fair`). `insufficient_data` is an escape hatch and is not coherence-checked.
  4. `check_emphasis_coherence` ([checks.py:69](checks.py#L69)) — when `comparison.emphasis_scenario_id` is set, it must match the `surfaced_insight.scenario_id`.
  5. `check_caveat_for_gap` ([checks.py:99](checks.py#L99)) — any scenario with `sample_size < 5` must be named in at least one caveat's text (loose match on scenario `label` or `id`).

## LLM Usage

None. The editor is entirely deterministic — pure Python, no LLM calls.

## Inputs

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `claim` | `VerdictWithComparisonClaim` | Claims synthesis + Scout graft | Already Pydantic-validated; already carries any `surfaced_insight` from `scout_claim`. |

## Outputs

| Output | Type | Consumer | Notes |
|--------|------|----------|-------|
| `EditResult.passed` | `bool` | `_maybe_handle_via_claim` | True only when every check returned an empty list. |
| `EditResult.failures` | `list[str]` | `_maybe_handle_via_claim` → `session.last_claim_rejected.failures` → SSE `claim_rejected.failures` ([api/events.py:316](../../api/events.py#L316)) | Concatenated across all five checks; order is diagnostic only. |

## Dependencies on Other Modules

- **Schema dependency on:** [briarwood/claims/verdict_with_comparison.py](../claims/verdict_with_comparison.py) — the editor imports `VerdictWithComparisonClaim` directly. Any change to `verdict.label`, `verdict.ask_vs_fmv_delta_pct`, `comparison.scenarios[i].sample_size`, `comparison.scenarios[i].id/label`, `comparison.emphasis_scenario_id`, `surfaced_insight.scenario_id`, or `caveats[i].text` is a potentially-breaking contract change for the editor.
- **Threshold dependency on:** [briarwood/claims/synthesis/verdict_with_comparison.py](../claims/synthesis/verdict_with_comparison.py) — `VALUE_FIND_THRESHOLD_PCT`, `OVERPRICED_THRESHOLD_PCT`, and `SMALL_SAMPLE_THRESHOLD` in [checks.py:14-20](checks.py#L14-L20) mirror the synthesizer's thresholds. [checks.py:18-20](checks.py#L18-L20) explicitly documents the no-import rule ("the editor does not import from synthesis to avoid a layering violation"). Risk: silent drift if either side changes without the other. See Known Rough Edges.
- **Imports:** only `briarwood.claims.verdict_with_comparison` and sibling `briarwood.editor.checks`. No network, disk, or LLM clients.
- **Coupled to:** [briarwood/agent/dispatch.py:1865](../agent/dispatch.py#L1865) (caller), [api/events.py:302-317](../../api/events.py#L302-L317) (downstream SSE builder), [briarwood/value_scout/scout.py](../value_scout/scout.py) (must have already grafted `surfaced_insight` before the editor runs, or `check_emphasis_coherence` can over-fail).

## Invariants

- `edit_claim` is deterministic for a fixed input — no LLM, no randomness, no disk I/O.
- Never mutates the claim. Each check takes the claim by reference and returns a `list[str]`.
- Every registered check always runs; failures are aggregated. There is no short-circuit.
- `EditResult.passed == True` iff `EditResult.failures == []`.
- Never raises on valid input. A malformed claim would have failed Pydantic validation upstream before reaching `edit_claim`.
- `check_schema_conformance` is trivially passing today; do not rely on it for invariants beyond that (per [checks.py:23-29](checks.py#L23-L29) docstring).
- `insufficient_data` is a protected verdict label: it skips the delta-coherence rule (per [checks.py:52-53](checks.py#L52-L53)).

## State & Side Effects

- **Stateless:** yes — module holds no mutable state; all inputs are function arguments.
- **Writes to disk:** no.
- **Modifies session:** no directly. The *caller* writes `session.last_claim_rejected` ([dispatch.py:1870](../agent/dispatch.py#L1870)) based on the result.
- **Safe to call concurrently:** yes.

## Example Call

```python
from briarwood.editor import edit_claim
from briarwood.claims.pipeline import build_claim_for_property
from briarwood.value_scout import scout_claim

claim = build_claim_for_property("NJ-0000001", user_text="Is this a buy?")
insight = scout_claim(claim)
if insight is not None:
    claim = claim.model_copy(update={
        "surfaced_insight": insight,
        "comparison": claim.comparison.model_copy(
            update={"emphasis_scenario_id": insight.scenario_id}
        ),
    })

result = edit_claim(claim)
# result.passed == True   → caller hands claim to render_claim
# result.failures == []   on pass; otherwise list of human-readable strings
```

## Known Rough Edges

- **Threshold duplication with synthesis (documented drift risk).** `VALUE_FIND_THRESHOLD_PCT = -5.0`, `OVERPRICED_THRESHOLD_PCT = 5.0`, and `SMALL_SAMPLE_THRESHOLD = 5` live in [checks.py:14-20](checks.py#L14-L20) and must match the synthesizer's constants at [briarwood/claims/synthesis/verdict_with_comparison.py](../claims/synthesis/verdict_with_comparison.py). The comment at [checks.py:18-20](checks.py#L18-L20) names the hazard: "Must agree with the synthesizer's SMALL_SAMPLE_THRESHOLD; the editor does not import from synthesis to avoid a layering violation." Cross-ref [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges → Hardcoded values (claim-object thresholds).
- **Single-archetype today.** Only `VerdictWithComparisonClaim` is supported. Additional archetypes listed in [briarwood/claims/archetypes.py](../claims/archetypes.py) would need their own check sets or a generalized dispatch inside `edit_claim`. See Open Product Decisions.
- **Pass/fail with no loop-back** per [validator.py:5-7](validator.py#L5-L7) docstring. On rejection, dispatch falls through to legacy synthesis; the editor offers no hint to Synthesis for a retry.
- **`check_schema_conformance` is a stub** ([checks.py:23-29](checks.py#L23-L29)). It returns `[]` unconditionally today because Pydantic already validated. Harmless but visible in the check registry — do not mistake it for active validation.
- **Emphasis-coherence assumes Scout has already run.** If `check_emphasis_coherence` runs on a claim where Synthesis wrote `emphasis_scenario_id` but Scout was skipped, the check will (correctly) fail with "no surfaced insight is present" ([checks.py:82-85](checks.py#L82-L85)). Any caller that skips the Scout step must also clear `emphasis_scenario_id` or expect rejection.
- **Rejection is silent to the end user.** On failure the wedge returns `None` and the legacy path runs; the user sees the legacy response, not a rejection notice. The `claim_rejected` SSE event is intended for dev tooling per the comment at [api/events.py:306-311](../../api/events.py#L306-L311).

## Open Product Decisions

(Pulled from [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md); no editor-specific decisions invented here.)

- **Intent-satisfaction vs. structural coherence.** [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 3 frames the Unified Intelligence layer as asking "does this answer the user's intent?" — a broader question than what the editor checks today. Whether the editor should grow into that role, or a separate intent-satisfaction LLM step should sit next to it (analogous to the grounding verifier in [briarwood/agent/composer.py](../agent/composer.py)), is not yet decided.
- **Threshold drift defense.** The threshold duplication is called out explicitly in the code but has no mechanical guard. Cross-reference the `NEW-V-003` precedent in [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 3 Risks (prompt/validator contract drift recently caught the lead recommendation verb stripping). A shared constants module or a test that imports both sides is an open design question.
- **Archetype expansion strategy.** As more claim archetypes land (see [briarwood/claims/archetypes.py](../claims/archetypes.py)), whether the editor dispatches by archetype, registers per-archetype check tuples, or hands off to per-archetype editors is undecided. See [DECISIONS.md](../../DECISIONS.md) for related framing.

## Changelog

### 2026-04-24
- Initial README created.

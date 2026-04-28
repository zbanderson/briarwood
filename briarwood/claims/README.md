# claims — Claim-Object Pipeline (Phase 3 Wedge)

**Last Updated:** 2026-04-28 (CMA Phase 4a Cycle 6 — graft now routes through canonical scoped runner)
**Layer:** Unified Intelligence + adapter (Layer 3 — feature-flagged wedge in front of legacy synthesis)
**Status:** EXPERIMENTAL (feature-flagged)

## Purpose

The `claims/` package is the Phase 3 wedge that replaces Briarwood's legacy structured-output synthesis with a typed, validated claim-object pipeline for the DECISION/LOOKUP path on pinned listings. It is gated by the `BRIARWOOD_CLAIMS_ENABLED` feature flag (and an optional per-property allowlist). Pipeline order: `build_claim_for_property` runs the routed analysis through the existing orchestrator, grafts a `comparable_sales` entry via the canonical scoped runner `run_comparable_sales` (because the orchestrator's routed run surfaces `comparable_sales` only as an internal dependency of `valuation`), and hands a `VerdictWithComparisonClaim` to the wedge. The wedge then routes via `scout_claim` (Value Scout) → `edit_claim` (Editor) → `render_claim` (Representation). On any failure the wedge falls through to the legacy synthesis path; the user-facing stream stays the same shape regardless. The package ships with exactly one archetype (`VERDICT_WITH_COMPARISON`) — the registry shape is multi-archetype so additions land without changing callers.

## Location

- **Package root:** [briarwood/claims/](.) — public surface re-exported from [briarwood/claims/__init__.py](__init__.py).
- **Pipeline entry:** [briarwood/claims/pipeline.py:28](pipeline.py#L28) — `build_claim_for_property(property_id, *, user_text, overrides=None) -> VerdictWithComparisonClaim`.
- **Archetype enum:** [briarwood/claims/archetypes.py:4](archetypes.py#L4) — `Archetype` (today: `VERDICT_WITH_COMPARISON`; six others reserved as comments).
- **Archetype routing:** [briarwood/claims/routing.py:13](routing.py#L13) — `map_to_archetype(answer_type, question_focus, has_pinned_listing)`.
- **Schemas (base):** [briarwood/claims/base.py](base.py) — `Provenance`, `Confidence`, `Caveat`, `NextQuestion`, `SurfacedInsight`.
- **Schema (archetype):** [briarwood/claims/verdict_with_comparison.py:75](verdict_with_comparison.py#L75) — `VerdictWithComparisonClaim`. Sub-models: `Subject` ([line 15](verdict_with_comparison.py#L15)), `Verdict` ([line 25](verdict_with_comparison.py#L25)), `ComparisonScenario` ([line 37](verdict_with_comparison.py#L37)), `Comparison` ([line 57](verdict_with_comparison.py#L57)).
- **Synthesizer:** [briarwood/claims/synthesis/verdict_with_comparison.py:46](synthesis/verdict_with_comparison.py#L46) — `build_verdict_with_comparison_claim(...)`. Templates at [synthesis/templates.py](synthesis/templates.py).
- **Representation:** [briarwood/claims/representation/verdict_with_comparison.py:52](representation/verdict_with_comparison.py#L52) — `render_claim(claim, llm)`. Assertion rubric at [representation/rubric.py](representation/rubric.py).
- **Feature flags:** `claims_enabled_for(property_id)` at [briarwood/feature_flags.py:22](../feature_flags.py#L22). Env vars `BRIARWOOD_CLAIMS_ENABLED` (default `false`) and `BRIARWOOD_CLAIMS_PROPERTY_IDS` (empty = all).
- **Wedge dispatch:** [briarwood/agent/dispatch.py:1809-1884](../agent/dispatch.py#L1809-L1884) — `_maybe_handle_via_claim`.
- **Tests:** [tests/claims/](../../tests/claims/) — schema, synthesis, representation, routing, dispatch-branch, fixtures.

## Role in the Six-Layer Architecture

- **This layer:** Unified Intelligence (Layer 3). The pipeline assembles a typed claim from prior module outputs, then routes it through Editor (validation) and Representation (rendering). Distinguished from Layer 2 (`orchestrator`) and Layer 4 (the Representation Agent, which lives at [briarwood/representation/](../representation/) and runs separately).
- **Called by:** `_maybe_handle_via_claim` wedge at [briarwood/agent/dispatch.py:1809](../agent/dispatch.py#L1809). The wedge is itself called from the DECISION handler.
- **Calls:**
  - `run_briarwood_analysis_with_artifacts` ([briarwood/orchestrator.py](../orchestrator.py)) for the routed analysis.
  - `run_comparable_sales(context)` ([briarwood/modules/comparable_sales_scoped.py](../modules/comparable_sales_scoped.py)) via post-hoc graft at [pipeline.py:62-114](pipeline.py#L62-L114) — see Known Rough Edges. Replaces the prior direct `ComparableSalesModule()` instantiation as of CMA Phase 4a Cycle 6.
  - `scout_claim` ([briarwood/value_scout/scout.py:26](../value_scout/scout.py#L26)).
  - `edit_claim` ([briarwood/editor/validator.py:32](../editor/validator.py#L32)).
  - `render_claim` ([briarwood/claims/representation/verdict_with_comparison.py:52](representation/verdict_with_comparison.py#L52)).
- **Returns to:** `_maybe_handle_via_claim`, which sets `session.last_claim_events` and returns the rendered prose. On failure (build raises, editor rejects, render raises), returns `None` — caller falls through to legacy synthesis.
- **Emits events:** Indirectly, via Representation. The wedge also surfaces `EVENT_CLAIM_REJECTED` ([api/events.py:41](../../api/events.py#L41)) on editor failure.

## LLM Usage

Indirect. The claim **synthesizer** is fully deterministic (no LLM). The **Representation** step at [representation/verdict_with_comparison.py:87-106](representation/verdict_with_comparison.py#L87-L106) makes one LLM call to compose 2-4 sentences of claim prose, with the prompt at `api/prompts/claim_verdict_with_comparison.yaml` (per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) LLM Integrations table). Provider/model: OpenAI (injected by caller) / default `gpt-4o-mini`.

## Inputs

`build_claim_for_property` consumes:

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `property_id` | `str` | dispatch | Used to locate `data/saved-properties/{id}/inputs.json` via `SAVED_PROPERTIES_DIR` ([briarwood/agent/tools.py](../agent/tools.py)). Missing file raises `ToolUnavailable`. |
| `user_text` | `str` | dispatch | Routed through the orchestrator as the user input. |
| `overrides` | `Mapping[str, Any] \| None` | wedge (optional) | Property-input overrides applied via `inputs_with_overrides` at [briarwood/agent/overrides.py](../agent/overrides.py). |

The wedge entrypoint `_maybe_handle_via_claim` additionally consumes `text`, `decision: RouterDecision`, `session: Session`, `llm: LLMClient | None`, `pid: str` from dispatch.

## Outputs

| Output | Type | Consumer | Notes |
|--------|------|----------|-------|
| `VerdictWithComparisonClaim` | Pydantic model at [verdict_with_comparison.py:75](verdict_with_comparison.py#L75) | Scout → Editor → Representation | Carries `subject`, `verdict`, `bridge_sentence`, `comparison`, `caveats`, `next_questions`, `provenance`, `surfaced_insight: SurfacedInsight \| None`. |
| Wedge prose return | `str \| None` | Dispatch | Rendered prose on success; `None` to fall through to legacy. |
| `session.last_claim_events` | `list[dict]` | SSE adapter | Set on success at [briarwood/agent/dispatch.py:1883](../agent/dispatch.py#L1883). |
| `session.last_claim_rejected` | `dict` | SSE adapter | Set on editor failure at [briarwood/agent/dispatch.py:1870-1874](../agent/dispatch.py#L1870-L1874). |

## Dependencies on Other Modules

- **Schema dependency on:** `briarwood.claims.archetypes` (`Archetype` enum) and `briarwood.claims.base` (shared sub-models). Any change to `Verdict.label` literals, `Verdict.ask_vs_fmv_delta_pct`, `Comparison.metric` literals, `Comparison.chart_rule` literals, `ComparisonScenario.flag` literals, or any field in `SurfacedInsight` is a contract change for the editor and representation.
- **Imports:**
  - `briarwood.orchestrator.run_briarwood_analysis_with_artifacts` — reuses the routed-execution stack, no parallel orchestrator.
  - `briarwood.runner_routed._scoped_synthesizer` — synthesizer hook for the orchestrator call.
  - `briarwood.modules.comparable_sales_scoped.run_comparable_sales` — graft entry point (canonical scoped runner; replaces the prior `ComparableSalesModule` direct call as of CMA Phase 4a Cycle 6).
  - `briarwood.modules.comparable_sales.ComparableSalesOutput` — pydantic shape used to repackage the scoped wrapper's `legacy_payload` so the synthesizer's existing `payload.comps_used` access path remains stable.
  - `briarwood.execution.context.ExecutionContext` — built from `PropertyInput.to_dict()` and passed to the scoped runner.
  - `briarwood.inputs.property_loader.load_property_from_json` — input loading.
  - `briarwood.agent.overrides.inputs_with_overrides`, `briarwood.agent.tools.SAVED_PROPERTIES_DIR`.
- **Coupled to:** `briarwood/editor/checks.py` (threshold constants must agree — see Known Rough Edges and [ROADMAP.md](../../ROADMAP.md)). Coupled to `briarwood/value_scout/` for the insight graft. Coupled to `briarwood/agent/dispatch.py` for the wedge entry.

## Invariants

- `build_claim_for_property` always returns a Pydantic-valid `VerdictWithComparisonClaim` or raises (no None return). Pydantic validation guarantees `Verdict.label` is one of the four literals, `Comparison.metric == "price_per_sqft"`, etc.
- `Comparison.emphasis_scenario_id`, when set, must reference an existing scenario id — enforced by `validate_emphasis_exists` at [verdict_with_comparison.py:64-72](verdict_with_comparison.py#L64-L72).
- `ComparisonScenario.metric_range[low] <= metric_range[high]` — enforced by `validate_range_ordering` at [verdict_with_comparison.py:47-54](verdict_with_comparison.py#L47-L54).
- `Confidence.score` is in `[0, 1]`; `Confidence.band` derives from `from_score` thresholds at [base.py:21-31](base.py#L21-L31): `>= 0.90 → "high"`, `>= 0.70 → "medium"`, `>= 0.50 → "low"`, else `"very_low"`.
- The wedge gracefully falls back to legacy synthesis on three failure paths: build raises, editor rejects, render raises. None of those cause user-facing errors.
- The post-hoc `comparable_sales` graft at [pipeline.py:62-114](pipeline.py#L62-L114) is idempotent: skipped if `outputs.comparable_sales` is already present, and gracefully no-ops when the scoped runner returns its fallback payload (no `legacy_payload`) or when shape validation fails.
- Synthesizer thresholds: price-label thresholds (`VALUE_FIND_THRESHOLD = -5.0`, `OVERPRICED_THRESHOLD = 5.0`) are imported from [briarwood/decision_model/value_position.py](../decision_model/value_position.py) and shared with the editor and current-value pricing view. `SMALL_SAMPLE_THRESHOLD = 5` remains local to [synthesis/verdict_with_comparison.py](synthesis/verdict_with_comparison.py) and must agree with the editor's small-sample check — see Known Rough Edges.

## State & Side Effects

- **Stateless package:** the synthesizer, archetypes, routing, and schemas are pure modules. Pipeline calls into the orchestrator inherit its caching behavior.
- **Writes to disk:** no direct writes from `claims/`. The post-hoc `ComparableSalesModule` graft reads `data/comps/sales_comps.json` indirectly.
- **Modifies session:** no direct modification — the wedge mutates session, not this package.
- **Safe to call concurrently:** yes for the synthesizer; the orchestrator call inherits its own concurrency posture.

## Example Call

```python
from briarwood.claims.pipeline import build_claim_for_property
from briarwood.claims.routing import map_to_archetype
from briarwood.claims.archetypes import Archetype
from briarwood.agent.router import AnswerType

archetype = map_to_archetype(
    answer_type=AnswerType.DECISION,
    question_focus=None,
    has_pinned_listing=True,
)
# archetype == Archetype.VERDICT_WITH_COMPARISON

claim = build_claim_for_property("NJ-0000001", user_text="Is this a buy?")
# claim.archetype                             == Archetype.VERDICT_WITH_COMPARISON
# claim.verdict.label                         in {"value_find", "fair", "overpriced", "insufficient_data"}
# claim.comparison.metric                     == "price_per_sqft"
# claim.comparison.chart_rule                 == "horizontal_bar_with_ranges"
# claim.surfaced_insight                      is None until the wedge runs scout_claim
```

## Known Rough Edges

- **Post-hoc `comparable_sales` graft.** [pipeline.py:62-114](pipeline.py#L62-L114) calls `run_comparable_sales(context)` (canonical scoped runner) and repackages the resulting `data.legacy_payload` as a `ComparableSalesOutput` instance under `outputs["comparable_sales"]["payload"]`. The graft is still required because the orchestrator's routed run surfaces `comparable_sales` only as an internal dependency of `valuation`, not as a top-level entry in `module_results["outputs"]` — the synthesizer would otherwise see no comp set and produce zero scenarios. Eligible for full removal if/when the orchestrator's chat-tier execution surfaces `comparable_sales` as a first-class output (open question — see consolidated chat-tier execution roadmap entry).
- **Small-sample threshold duplication with editor.** Price-label thresholds now live in [briarwood/decision_model/value_position.py](../decision_model/value_position.py), so synthesis and editor no longer mirror those constants. `SMALL_SAMPLE_THRESHOLD` still lives in both [synthesis/verdict_with_comparison.py](synthesis/verdict_with_comparison.py) and [briarwood/editor/checks.py](../editor/checks.py); silent drift is still possible for caveat coverage.
- **Single archetype.** Only `VERDICT_WITH_COMPARISON` is implemented. The six others in [archetypes.py:11-17](archetypes.py#L11-L17) are reserved as comments. Adding one requires: a new archetype enum value, a new Pydantic schema, a new synthesizer, a new representation renderer, an entry in `map_to_archetype`, and (often) editor checks specific to the archetype's invariants.
- **Routing is narrow.** `map_to_archetype` returns `VERDICT_WITH_COMPARISON` only for `AnswerType.DECISION` or `AnswerType.LOOKUP` AND `has_pinned_listing=True`. All other intent/state combinations route to legacy.
- **Cache trace recovery.** [pipeline.py:91-106](pipeline.py#L91-L106) recovers `interaction_trace` from either the top-level artifact OR the unified output — needed because the orchestrator's synthesis cache hit does not emit the trace at the top level. Brittle; surface as a "Contract change:" entry if the orchestrator's cache shape changes.
- **Wedge silently falls back.** On any failure the user sees the legacy response, not a notice. The `claim_rejected` SSE event is for dev tooling only ([api/events.py:306-311](../../api/events.py#L306-L311)).

## Open Product Decisions

(Pulled from [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) and [DECISIONS.md](../../DECISIONS.md); no claims-specific decisions invented here.)

- **Promote `comparable_sales` to the scoped registry?** ([GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 2) — would eliminate the post-hoc graft.
- **Archetype expansion strategy.** Which of the six reserved archetypes lands next, and what their schemas look like, is undecided. The Editor's [Open Product Decisions](../editor/README.md) frame this from the validator side.
- **Threshold drift defense.** See [ROADMAP.md](../../ROADMAP.md) for the suggested mechanical fix; the design choice between "shared constants module" vs. "test-time guard" is open.
- **When to flip `BRIARWOOD_CLAIMS_ENABLED` to default-on.** Open product call; gated on rejection-rate signal from the SSE `claim_rejected` event.

## Changelog

### 2026-04-28 (Semantic Value Consistency — shared value-position classifier)
- Contract change: `verdict.label` classification now imports the shared deterministic price-label thresholds from `briarwood/decision_model/value_position.py`, matching the editor and current-value pricing view.

### 2026-04-28 (CMA Phase 4a Cycle 6 — graft now routes through canonical scoped runner)
- **Contract change (internal, no user-visible behavior change):** the post-hoc `comparable_sales` graft at [pipeline.py:62-114](pipeline.py#L62-L114) now calls `run_comparable_sales(context)` (canonical scoped runner) instead of instantiating `ComparableSalesModule` directly. The graft repackages the scoped wrapper's `data.legacy_payload` as a `ComparableSalesOutput` pydantic instance under `outputs["comparable_sales"]["payload"]`, preserving the existing field-access shape (`payload.comps_used`) that the verdict_with_comparison synthesizer reads.
- **Why:** consistency with every other comp-sales caller (now uniformly through the wrapper's error contract, mode inference, and missing-input flagging via `module_payload_from_legacy_result`); closes a long-standing ROADMAP cleanup item from the 2026-04-24 promotion handoff.
- **Imports updated:** `briarwood.modules.comparable_sales.ComparableSalesModule` removed; `briarwood.modules.comparable_sales_scoped.run_comparable_sales`, `briarwood.modules.comparable_sales.ComparableSalesOutput`, and `briarwood.execution.context.ExecutionContext` added.
- **Test contract updated:** `tests/claims/test_pipeline.py` patches `run_comparable_sales` instead of `ComparableSalesModule`; the legacy `test_swallows_module_exception` case is replaced by `test_skips_when_scoped_returns_fallback`, which pins the new fallback handling (scoped runner's `mode="fallback"` path returns no `legacy_payload`, so the graft no-ops). All 82 claims tests green.
- **Graft is still load-bearing.** The orchestrator's routed run surfaces `comparable_sales` only as an internal dependency of `valuation`; without the graft, the synthesizer's `_iter_comps` would return empty and every claim would produce `insufficient_data`. Full removal is deferred until top-level surfacing is reconsidered.

### 2026-04-24
- Initial README created.

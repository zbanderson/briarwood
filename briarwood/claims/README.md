# claims — Claim-Object Pipeline (Phase 3 Wedge)

**Last Updated:** 2026-04-24
**Layer:** Unified Intelligence + adapter (Layer 3 — feature-flagged wedge in front of legacy synthesis)
**Status:** EXPERIMENTAL (feature-flagged)

## Purpose

The `claims/` package is the Phase 3 wedge that replaces Briarwood's legacy structured-output synthesis with a typed, validated claim-object pipeline for the DECISION/LOOKUP path on pinned listings. It is gated by the `BRIARWOOD_CLAIMS_ENABLED` feature flag (and an optional per-property allowlist). Pipeline order: `build_claim_for_property` runs the routed analysis through the existing orchestrator, grafts a post-hoc `ComparableSalesModule` run (because the scoped registry doesn't surface comparable_sales), and hands a `VerdictWithComparisonClaim` to the wedge. The wedge then routes via `scout_claim` (Value Scout) → `edit_claim` (Editor) → `render_claim` (Representation). On any failure the wedge falls through to the legacy synthesis path; the user-facing stream stays the same shape regardless. The package ships with exactly one archetype (`VERDICT_WITH_COMPARISON`) — the registry shape is multi-archetype so additions land without changing callers.

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
  - `ComparableSalesModule` ([briarwood/modules/comparable_sales.py](../modules/comparable_sales.py)) directly via post-hoc graft at [pipeline.py:62-88](pipeline.py#L62-L88) — see Known Rough Edges.
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
  - `briarwood.modules.comparable_sales.ComparableSalesModule` — graft target.
  - `briarwood.inputs.property_loader.load_property_from_json` — input loading.
  - `briarwood.agent.overrides.inputs_with_overrides`, `briarwood.agent.tools.SAVED_PROPERTIES_DIR`.
- **Coupled to:** `briarwood/editor/checks.py` (threshold constants must agree — see Known Rough Edges and [ROADMAP.md](../../ROADMAP.md)). Coupled to `briarwood/value_scout/` for the insight graft. Coupled to `briarwood/agent/dispatch.py` for the wedge entry.

## Invariants

- `build_claim_for_property` always returns a Pydantic-valid `VerdictWithComparisonClaim` or raises (no None return). Pydantic validation guarantees `Verdict.label` is one of the four literals, `Comparison.metric == "price_per_sqft"`, etc.
- `Comparison.emphasis_scenario_id`, when set, must reference an existing scenario id — enforced by `validate_emphasis_exists` at [verdict_with_comparison.py:64-72](verdict_with_comparison.py#L64-L72).
- `ComparisonScenario.metric_range[low] <= metric_range[high]` — enforced by `validate_range_ordering` at [verdict_with_comparison.py:47-54](verdict_with_comparison.py#L47-L54).
- `Confidence.score` is in `[0, 1]`; `Confidence.band` derives from `from_score` thresholds at [base.py:21-31](base.py#L21-L31): `>= 0.90 → "high"`, `>= 0.70 → "medium"`, `>= 0.50 → "low"`, else `"very_low"`.
- The wedge gracefully falls back to legacy synthesis on three failure paths: build raises, editor rejects, render raises. None of those cause user-facing errors.
- The post-hoc `ComparableSalesModule` graft is idempotent: skipped at [pipeline.py:77-78](pipeline.py#L77-L78) if `outputs.comparable_sales` is already present, and exception-safe at [pipeline.py:79-82](pipeline.py#L79-L82).
- Synthesizer thresholds at [synthesis/verdict_with_comparison.py:39-43](synthesis/verdict_with_comparison.py#L39-L43): `SMALL_SAMPLE_THRESHOLD = 5`, `VALUE_FIND_THRESHOLD = -5.0`, `OVERPRICED_THRESHOLD = 5.0`. **Must agree with editor's mirror constants** at [briarwood/editor/checks.py:14-20](../editor/checks.py#L14-L20) — see Known Rough Edges.

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

- **Post-hoc `ComparableSalesModule` graft.** [pipeline.py:62-88](pipeline.py#L62-L88) runs `ComparableSalesModule` directly because the scoped execution registry does not surface `comparable_sales` as a top-level module. The comment at [pipeline.py:67-72](pipeline.py#L67-L72) explicitly documents this gap. Cross-ref [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges → "ComparableSalesModule is not in the scoped registry" — promoting it would let the graft go away.
- **Threshold duplication with editor.** `SMALL_SAMPLE_THRESHOLD`, `VALUE_FIND_THRESHOLD`, `OVERPRICED_THRESHOLD` live both in [synthesis/verdict_with_comparison.py:39-43](synthesis/verdict_with_comparison.py#L39-L43) and (mirrored) in [briarwood/editor/checks.py:14-20](../editor/checks.py#L14-L20). The editor explicitly does not import from this package to avoid a layering violation. Silent drift is the hazard. See [ROADMAP.md](../../ROADMAP.md) "Editor / synthesis threshold duplication has no mechanical guard."
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

### 2026-04-24
- Initial README created.

# agent/dispatch + orchestrator — Per-AnswerType Handlers + Routed Analysis Entry

**Last Updated:** 2026-04-25
**Layer:** Orchestration (Layer 2 — rule-based handler registry, not LLM-driven)
**Status:** STABLE (the handler-registry pattern; the per-handler logic varies in maturity)

## Purpose

`briarwood/agent/dispatch.py` is the per-`AnswerType` handler registry that translates a router decision into per-tier work. Each of the 14 handlers (`handle_lookup`, `handle_decision`, etc.) hardcodes which sub-tools run, in what order, and how their outputs are framed.

**Two distinct paths use the orchestrator; the chat-tier handlers in this file do not.** The orchestrator at `briarwood/orchestrator.py::run_briarwood_analysis_with_artifacts` is invoked from exactly two production sites: [`briarwood/runner_routed.py:228`](../runner_routed.py#L228) (external entry — property pre-computation, batch) and [`briarwood/claims/pipeline.py:42`](../claims/pipeline.py#L42) (inside the claims wedge). The dispatch handlers themselves never call it directly. Verified 2026-04-25 by `grep -nE "run_briarwood_analysis(_with_artifacts)?\(" briarwood/agent/dispatch.py` — zero matches. (See [DECISIONS.md](../../DECISIONS.md) 2026-04-25 entry "README_dispatch.md overstates orchestrator coupling" for the correction history.)

What chat-tier handlers actually do: call individual functions in [`briarwood/agent/tools.py`](tools.py) (e.g., `get_value_thesis`, `get_risk_profile`, `get_cma`, `get_rent_outlook`), accumulate the structured payloads into per-handler `structured_inputs` dicts, and pass them to [`briarwood/agent/composer.py::complete_and_verify`](composer.py) (or sibling `compose_*` entries) to render prose. The composer applies an advisory grounding verifier and (when `BRIARWOOD_STRICT_REGEN` is on) a strip/regen cycle. There is no synthesizer call on the chat-tier path; `UnifiedIntelligenceOutput` is reconstructed best-effort from session views by `_unified_from_session` in [`api/pipeline_adapter.py:1266-1333`](../../api/pipeline_adapter.py#L1266-L1333) when downstream consumers (notably the Layer-4 Representation Agent) need it.

The orchestrator-using paths still matter to dispatch: handler `handle_decision` invokes `_maybe_handle_via_claim` ([dispatch.py:1809](dispatch.py#L1809)), which transitively calls the orchestrator via `claims.pipeline.build_claim_for_property`. When the wedge is enabled and the claim is admitted by the Editor, that path produces the verdict. When it falls through, the legacy chat-tier composition runs.

There is no LLM-driven tool-use loop here — model selection is encoded in handler code, and the orchestrator raises `RoutingError` rather than falling back when scoped coverage is incomplete (which only matters on the wedge / external paths).

## Location

- **Dispatch root:** [briarwood/agent/dispatch.py](dispatch.py) (4538 LOC).
- **Handler functions** (one per `AnswerType`, per the [router README](README_router.md)):
  - [briarwood/agent/dispatch.py:1752](dispatch.py#L1752) — `handle_lookup`
  - [briarwood/agent/dispatch.py:1887](dispatch.py#L1887) — `handle_decision`
  - [briarwood/agent/dispatch.py:2361](dispatch.py#L2361) — `handle_search`
  - [briarwood/agent/dispatch.py:2516](dispatch.py#L2516) — `handle_comparison`
  - [briarwood/agent/dispatch.py:2557](dispatch.py#L2557) — `handle_research`
  - [briarwood/agent/dispatch.py:2896](dispatch.py#L2896) — `handle_visualize`
  - [briarwood/agent/dispatch.py:2922](dispatch.py#L2922) — `handle_rent_lookup`
  - [briarwood/agent/dispatch.py:3130](dispatch.py#L3130) — `handle_projection`
  - [briarwood/agent/dispatch.py:3412](dispatch.py#L3412) — `handle_micro_location`
  - [briarwood/agent/dispatch.py:3473](dispatch.py#L3473) — `handle_risk`
  - [briarwood/agent/dispatch.py:3654](dispatch.py#L3654) — `handle_edge`
  - [briarwood/agent/dispatch.py:3921](dispatch.py#L3921) — `handle_strategy`
  - [briarwood/agent/dispatch.py:4028](dispatch.py#L4028) — `handle_browse`
  - [briarwood/agent/dispatch.py:4180](dispatch.py#L4180) — `handle_chitchat`
- **Claim wedge inside dispatch:** `_maybe_handle_via_claim` at [briarwood/agent/dispatch.py:1809](dispatch.py#L1809) — the Phase 3 entry that lives inside the DECISION path (see [briarwood/claims/README.md](../claims/README.md) and [briarwood/editor/README.md](../editor/README.md)).
- **Orchestrator root:** [briarwood/orchestrator.py](../orchestrator.py) (~810 LOC).
- **Routed analysis entry:** [briarwood/orchestrator.py:467](../orchestrator.py#L467) — `run_briarwood_analysis_with_artifacts(...)`. Production callers: [`runner_routed.py:228`](../runner_routed.py#L228) and [`claims/pipeline.py:42`](../claims/pipeline.py#L42).
- **Chat-tier analysis entry (added 2026-04-25, Cycle 2):** [briarwood/orchestrator.py:682](../orchestrator.py#L682) — `run_chat_tier_analysis(property_data, answer_type, user_input, *, parser_output=None, parallel=False, ...)`. Skips the intent-contract router (the chat-tier `AnswerType` is already classified at this layer) and runs a single consolidated execution plan keyed by [`briarwood/execution/module_sets.py::ANSWER_TYPE_MODULE_SETS`](../execution/module_sets.py). LOOKUP and the non-property tiers short-circuit. **No dispatch handler calls it yet** — Cycle 3 of [OUTPUT_QUALITY_HANDOFF_PLAN.md](../../OUTPUT_QUALITY_HANDOFF_PLAN.md) will rewire `handle_browse` first.
- **Convenience entry:** [briarwood/orchestrator.py:444](../orchestrator.py#L444) — `run_briarwood_analysis(...)` returns only the unified output.
- **Cache-key construction:** [briarwood/orchestrator.py:176](../orchestrator.py#L176) — `build_cache_key(property_summary, parser_output, execution_mode=...)`.
- **Tests:** [tests/agent/test_dispatch.py](../../tests/agent/test_dispatch.py); [tests/test_orchestrator.py](../../tests/test_orchestrator.py); [tests/claims/test_dispatch_branch.py](../../tests/claims/test_dispatch_branch.py).

## Role in the Six-Layer Architecture

- **This layer:** Orchestration (Layer 2) — but as a **rule-based handler registry**, not the LLM-driven tool-use loop the target architecture describes ([GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 2). Per the gap analysis: "What goes into the registry for a given turn is decided by handler code, not by an LLM reading a spec." The legacy/scoped split, the orchestrator's no-fallback policy, and the registry's missing semantics for "optional" / "user-type-dependent" dependencies are all named there as obstacles to closing the gap.
- **Called by:** `api/pipeline_adapter.py` ([api/pipeline_adapter.py](../../api/pipeline_adapter.py)), which receives the `RouterDecision` from `briarwood.agent.router.classify` and then dispatches to a tier-specific stream (`search_stream`, `browse_stream`, `decision_stream`, or the generic `dispatch_stream`).
- **Calls:**
  - From chat-tier dispatch handlers: per-tool entries in [`briarwood/agent/tools.py`](tools.py) (e.g., `get_value_thesis`, `get_risk_profile`, `get_cma`, `get_rent_outlook`, `get_projection`, `get_strategy_view`); [`briarwood/agent/composer.py::complete_and_verify`](composer.py) (and `compose_*` siblings) for prose; `briarwood/agent/resolver.py` for property-id disambiguation; `briarwood.agent.feedback` for low-confidence logging. **No direct call to `run_briarwood_analysis_with_artifacts` from any handler in this file** — verified 2026-04-25, see [DECISIONS.md](../../DECISIONS.md). Many handlers also read session views populated by sibling handlers.
  - From the DECISION wedge (`_maybe_handle_via_claim` at [dispatch.py:1809](dispatch.py#L1809)): `briarwood.feature_flags.claims_enabled_for`; `briarwood.claims.routing.map_to_archetype`; `briarwood.claims.pipeline.build_claim_for_property` (which transitively calls the orchestrator); `briarwood.value_scout.scout_claim`; `briarwood.editor.edit_claim`; `briarwood.claims.representation.render_claim`.
  - From the orchestrator (when invoked from `runner_routed.py` or the wedge, not from this file): `briarwood.router.route_user_input` ([briarwood/router.py](../router.py)) for the analysis-tier router; the planner + executor in [briarwood/execution/](../execution/); the injected synthesizer (typically `_scoped_synthesizer` from [briarwood/runner_routed.py:104](../runner_routed.py#L104)).
- **Returns to:** Caller (`api/pipeline_adapter.py`). Handlers return prose strings; the adapter chunks for SSE streaming. The orchestrator returns an artifact dict with keys `routing_decision`, `property_summary`, `module_results`, `unified_output` (and `interaction_trace` on fresh runs).
- **Emits events:** Indirectly — the adapter projects each handler's output into the SSE event stream defined at [api/events.py](../../api/events.py).

## LLM Usage

Indirect — neither dispatch nor the orchestrator calls an LLM directly. Both invoke layers that do:
- **Most chat-tier handlers** (DECISION, LOOKUP, RENT_LOOKUP, PROJECTION, RISK, EDGE, STRATEGY, BROWSE) compose prose via [`briarwood/agent/composer.py::complete_and_verify`](composer.py) or sibling `compose_*` entries. The composer wraps an LLM call with an advisory grounding verifier and (when `BRIARWOOD_STRICT_REGEN` is on, default) a strip/regen cycle. Per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) LLM Integrations table.
- **Deterministic-template handlers** (SEARCH, COMPARISON, RESEARCH, VISUALIZE, MICRO_LOCATION, CHITCHAT) return prose strings assembled from f-string templates — no LLM call.
- **The DECISION wedge** (`_maybe_handle_via_claim`) — when `BRIARWOOD_CLAIMS_ENABLED` is true and the archetype matches — calls `render_claim` which uses an LLM for claim prose ([briarwood/claims/README.md](../claims/README.md)). On wedge fall-through, the legacy DECISION handler runs and uses the composer.

## Inputs

(Each chat-tier handler has its own per-tier signature accepting some subset of `text`, `decision: RouterDecision`, `session: Session`, `llm: LLMClient | None`, plus tier-specific kwargs — read the source for the exact shape per handler. The shared orchestrator entry below is invoked only from `runner_routed.py` and the claims wedge, not from any handler in this file.)

`run_briarwood_analysis_with_artifacts(property_data, user_input, llm_parser=None, synthesizer=None, scoped_registry=None, prior_context=None)`:

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `property_data` | `dict[str, Any]` | Caller (handler / wedge) | Required; raises `TypeError` if not a dict. |
| `user_input` | `str` | Router decision text | Required non-empty; raises `ValueError`. |
| `llm_parser` | `Callable[[str], ParserOutput] \| None` | Caller | Optional; routes to `briarwood.router.route_user_input`'s default parser when `None`. |
| `synthesizer` | `Synthesizer \| None` | Caller | **Required** despite the optional default; raises `ValueError` when `None`. Typically `_scoped_synthesizer`. |
| `scoped_registry` | `dict[str, ModuleSpec] \| None` | Caller | Optional override; defaults to `_get_default_scoped_registry()` at [briarwood/orchestrator.py:230](../orchestrator.py#L230). |
| `prior_context` | `list[dict[str, object]] \| None` | Caller | Conversation history for follow-up turns. |

Each handler's signature is per-tier and not uniform — see the source for the exact shape. Most accept `RouterDecision` and a `Session` object plus tier-specific kwargs.

## Outputs

`run_briarwood_analysis_with_artifacts` returns a `dict[str, Any]` with at least:

| Key | Type | Notes |
|-----|------|-------|
| `routing_decision` | `RoutingDecision` | From the analysis-tier router. |
| `property_summary` | `dict[str, Any]` | Built by `build_property_summary` at [briarwood/orchestrator.py:94](../orchestrator.py#L94). |
| `module_results` | `dict[str, Any]` | Wraps each scoped module's output under `outputs[module_name]`. |
| `unified_output` | `UnifiedIntelligenceOutput` (or dict) | From the injected synthesizer. |
| `interaction_trace` | `dict[str, Any]` | Present on fresh runs; absent on synthesis-cache hits per [briarwood/orchestrator.py:521-528](../orchestrator.py#L521-L528). |

Handlers return `str` (prose) — the adapter chunks for streaming.

## Dependencies on Other Modules

- **From dispatch:** `briarwood.orchestrator`, `briarwood.feature_flags`, `briarwood.claims` (entire package), `briarwood.value_scout`, `briarwood.editor`, `briarwood.agent.session`, `briarwood.agent.router` (`RouterDecision`, `AnswerType`), `briarwood.agent.composer`, `briarwood.agent.resolver`, `briarwood.agent.tools`, `briarwood.agent.overrides`, `briarwood.interactions/*`, `briarwood.local_intelligence/*`, plus a wide surface of module-result accessors across `briarwood.modules`.
- **From orchestrator:** `briarwood.router` (analysis-tier), `briarwood.routing_schema`, `briarwood.execution.context`, `briarwood.execution.planner`, `briarwood.execution.executor`, `briarwood.execution.registry` (`ModuleSpec`), `briarwood.pipeline.triage` (macro nudges).
- **Coupled to:** every scoped-model README in `briarwood/modules/README_*.md` (handlers read those modules' outputs through `module_results`); the `Session` model in [briarwood/agent/session.py](session.py); the SSE event shapes in [api/events.py](../../api/events.py).

## Invariants

- The orchestrator validates `property_data is dict` and `user_input` non-empty before doing anything ([briarwood/orchestrator.py:482-487](../orchestrator.py#L482-L487)).
- `synthesizer` is required — raising `ValueError` is the documented contract at [briarwood/orchestrator.py:488-492](../orchestrator.py#L488-L492).
- **No fallback on scoped-registry coverage gap.** When `supports_scoped_execution` returns `False`, the orchestrator raises `RoutingError` at [briarwood/orchestrator.py:510-514](../orchestrator.py#L510-L514). The legacy `AnalysisEngine` fallback is deleted. This is `AUDIT_REPORT.md` F-004 (elevated in `VERIFICATION_REPORT.md`); see [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges. Implication: a router/registry mismatch is a hard failure for the entire analysis.
- Synthesis output is cached by `build_cache_key(property_summary, parser_output, execution_mode)` at [briarwood/orchestrator.py:171](../orchestrator.py#L171); `execution_mode` was made required by commit `1c21bdb`. Cache hits skip the synthesizer and return a slimmer artifact dict (no `interaction_trace` at top level — claims pipeline recovery for this is at [briarwood/claims/pipeline.py:91-106](../claims/pipeline.py#L91-L106)).
- The handler-registry pattern is the contract: every `AnswerType` value must have a `handle_*` function in `dispatch.py` (or be routed through the wedge / `_maybe_handle_via_claim`). Adding a new `AnswerType` without a handler is a runtime error.
- The DECISION wedge at [briarwood/agent/dispatch.py:1809-1884](dispatch.py#L1809-L1884) returns `None` on any wedge failure (build raises, editor rejects, render raises), which causes the legacy DECISION path to run. The user-facing stream stays the same shape regardless.
- The orchestrator never returns `None`. Either it produces a full artifact bundle or raises.

## State & Side Effects

- **Stateful via `Session`:** Most handlers mutate the `Session` instance to populate `last_*_view` slots used by the Representation Agent and SSE adapter.
- **Caches:** `_ROUTING_DECISION_CACHE`, `_SYNTHESIS_OUTPUT_CACHE`, `_MODULE_RESULTS_CACHE` at module scope in `orchestrator.py`. Process-local; no eviction.
- **Writes to disk:** indirectly via `briarwood/agent/feedback.py` for low-confidence router fallbacks; via the auto-fetch logic in `_maybe_auto_fetch_town_research` at [briarwood/agent/dispatch.py:612](dispatch.py#L612) for town research artifacts.
- **Modifies session:** yes (extensively).
- **Safe to call concurrently:** the orchestrator's caches are module-scope dicts and are not lock-protected. Concurrent identical-cache-key calls would race on dict insert (Python's GIL makes single inserts atomic, but the read-then-insert pattern is not).

## Example Call

Chat-tier handler — the path almost every chat turn takes:

```python
from briarwood.agent.dispatch import handle_decision

prose = handle_decision(text=user_text, decision=router_decision, session=session, llm=llm)
# Internally: handle_decision calls tools.py functions (get_value_thesis,
# get_risk_profile, ...), builds structured_inputs, and calls the composer.
# It also tries _maybe_handle_via_claim — which, if BRIARWOOD_CLAIMS_ENABLED
# and the archetype matches, runs the orchestrator transitively via the
# claims wedge. Otherwise the legacy composer-rendered path runs.
```

Orchestrator — invoked from `runner_routed.py` (external/batch) or
`claims/pipeline.py` (wedge). Not invoked from any chat-tier handler in
this file:

```python
from briarwood.orchestrator import run_briarwood_analysis_with_artifacts
from briarwood.runner_routed import _scoped_synthesizer

artifacts = run_briarwood_analysis_with_artifacts(
    property_data={"address": "...", "town": "Montclair", "state": "NJ", ...},
    user_input="Is this a buy at $850k?",
    synthesizer=_scoped_synthesizer,
)
# artifacts["routing_decision"]    — RoutingDecision
# artifacts["property_summary"]    — dict
# artifacts["module_results"]      — dict[str, dict] with `outputs[module_name]` shape
# artifacts["unified_output"]      — UnifiedIntelligenceOutput (or dict)
# artifacts["interaction_trace"]   — present on fresh runs
```

## Known Rough Edges

- **Audit count drift on handlers.** [DECISIONS.md](../../DECISIONS.md) entry "Dispatch handler count drift in audit docs" — the audit lists 8 handlers; there are 14, one per `AnswerType`.
- **Hard failure on scoped-registry coverage gap.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges → "No fallback on scoped-registry failure (`AUDIT_REPORT.md` F-004, elevated)." Cross-cutting: amplifies the impact of any module that raises (see [briarwood/modules/README_legal_confidence.md](../modules/README_legal_confidence.md), [briarwood/modules/README_renovation_impact.md](../modules/README_renovation_impact.md), [FOLLOW_UPS.md](../../FOLLOW_UPS.md)).
- **Mock-listings fallback has no demo-mode gate.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges (`AUDIT_REPORT.md` F-001) — `api/main.py:334-335` falls through to `_echo_stream` when the router returns `None`, which can serve fabricated listings on provider failure. Not in this package directly, but the dispatch layer is where the gate would belong.
- **Resolver state-aware disambiguation.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges → "Resolver has no state-aware disambiguation." `_resolve_property_match` at [briarwood/agent/dispatch.py:255](dispatch.py#L255) is one of the consumers of the resolver and is positioned to surface ambiguity prompts to users.
- **Handler maturity varies.** Some handlers (e.g., `handle_decision`, `handle_browse`) carry substantial logic; others (e.g., `handle_chitchat`) are essentially stubs. The README does not enumerate per-handler maturity — read the source for any handler before modifying it.
- **`briarwood.router` (analysis-tier) is not the same as `briarwood.agent.router` (chat-tier).** The orchestrator imports the analysis-tier router; the chat-tier router is the one documented at [briarwood/agent/README_router.md](README_router.md). The `IntentContract` model bridges them — see [briarwood/intent_contract.py](../intent_contract.py).
- **`prior_context` is plumbed through but not shaped.** `run_briarwood_analysis_with_artifacts` accepts `prior_context: list[dict[str, object]] | None` — the structure is conventional rather than typed.
- **Adapter stream selection is outside this package.** Per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Data Flow §4, `api/pipeline_adapter.py` decides between `search_stream`, `browse_stream`, `decision_stream`, or the generic `dispatch_stream` based on `AnswerType`. That adapter routing is upstream of the per-handler dispatch documented here.

## Open Product Decisions

(Pulled from [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 2; no dispatch-specific decisions invented here.)

- **LLM-driven tool-use loop.** Replacing the rule-based handler registry with an orchestrating LLM that reads the tool registry and picks tools is the Layer 2 target. Significant complexity; blocked partly on the legacy/scoped promotion question.
- **Legacy-to-scoped promotion.** Which legacy modules get promoted to scoped registry entries (`comparable_sales` is the obvious first). See [DECISIONS.md](../../DECISIONS.md) and the `claims/` README for the post-hoc graft pattern that exists today as a workaround.
- **Optional / user-type-dependent dependencies.** The scoped registry's DAG pattern doesn't express these. The current handler-registry encodes them implicitly — moving to LLM-driven orchestration requires data-driven semantics.
- **Where the no-fallback-on-coverage-gap policy lives going forward.** Today it's an orchestrator raise; the gap analysis frames it as a correctness requirement that raises the bar for any registry change.

## Changelog

### 2026-04-25
- Contract correction: README no longer claims "From dispatch:
  `run_briarwood_analysis_with_artifacts` (most handlers)." Verified by
  `grep -nE "run_briarwood_analysis(_with_artifacts)?\(" briarwood/agent/dispatch.py`
  — zero matches. Updated Purpose, "Calls" section, Example Call section,
  and LLM Usage section to describe the actual chat-tier topology
  (handlers compose responses by calling `briarwood/agent/tools.py`
  functions and `briarwood/agent/composer.py`; the orchestrator runs
  only from `runner_routed.py:228` and `claims/pipeline.py:42`).
  Cross-reference: [DECISIONS.md](../../DECISIONS.md) 2026-04-25 entry
  "README_dispatch.md overstates orchestrator coupling" and
  [AUDIT_OUTPUT_QUALITY_2026-04-25.md](../../AUDIT_OUTPUT_QUALITY_2026-04-25.md) §6.1.
- Cycle 2 of [OUTPUT_QUALITY_HANDOFF_PLAN.md](../../OUTPUT_QUALITY_HANDOFF_PLAN.md) added a third orchestrator entry: `run_chat_tier_analysis` at [briarwood/orchestrator.py:682](../orchestrator.py#L682). Documented under Location alongside the existing two entries. **No handler in this file calls it yet** — Cycle 3 will rewire `handle_browse` first. Until that lands, the README's chat-tier topology description (handlers compose via `tools.py` + `composer.py`, orchestrator only via wedge / external runner) remains accurate. Line numbers for the existing entries refreshed to current orchestrator.py state (LOC grew from ~589 to ~810 with the additions). Cross-reference: [DECISIONS.md](../../DECISIONS.md) 2026-04-25 entry "Consolidated chat-tier orchestrator entry: `run_chat_tier_analysis`".
- **Cycle 3 (commit `ca94d2f`):** `handle_browse` now calls `run_chat_tier_analysis` via the new `_browse_chat_tier_artifact` helper. For saved properties, the consolidated path replaces the per-tool routed runners (`get_property_brief`, `get_projection`, `get_strategy_fit`, `get_rent_estimate`) — the four functions whose internal `run_routed_report` invocations produced the audit's per-tool plan fragmentation. View extraction is now done inline from `chat_tier_artifact["module_results"]["outputs"]` via four helpers near `handle_browse`. The legacy per-tool path is preserved as a fallback when the artifact returns `None` (no inputs.json, validation failure). `get_cma` (Engine B), `get_property_enrichment`, `get_property_presentation`, `search_listings`, `get_property_summary`, and `get_rent_outlook` (now receiving a pre-computed `rent_payload`) are unchanged. **This is the first handler to use the consolidated path.** The other chat-tier handlers (`handle_decision`, `handle_risk`, `handle_edge`, `handle_strategy`, `handle_projection`, `handle_rent_lookup`) still use the per-tool pattern — Cycle 5 of the plan will roll the same rewire pattern out. The README's chat-tier topology description above ("handlers compose via tools.py + composer.py, orchestrator only via wedge / external runner") is now partially stale: `handle_browse` is the exception. Cross-reference: [DECISIONS.md](../../DECISIONS.md) 2026-04-25 entry "Consolidated chat-tier orchestrator entry" and [OUTPUT_QUALITY_HANDOFF_PLAN.md](../../OUTPUT_QUALITY_HANDOFF_PLAN.md) Cycle 3.
- **Cycle 4 (commit `fb23152`):** `handle_browse` now invokes the Layer 3 LLM synthesizer at [briarwood/synthesis/llm_synthesizer.py](../synthesis/llm_synthesizer.py) (`synthesize_with_llm`) over the full `UnifiedIntelligenceOutput` produced by Cycle 2/3, replacing `compose_browse_surface` on the happy path. The composer remains as fallback when (a) the synthesizer returns empty prose (budget cap, blank draft, exception, verifier blocked everything) or (b) the chat-tier artifact / llm is missing. The synthesizer's LLM call lands at surface `synthesis.llm` (regen at `synthesis.llm.regen`) in the per-turn manifest's `llm_calls` list — distinct from `composer.draft` and `agent_router.classify`. The intent contract is built via `briarwood.intent_contract.build_contract_from_answer_type(decision.answer_type.value, decision.confidence)`. Numeric grounding is enforced via `api.guardrails.verify_response` over the full unified output; this is the same numeric guardrail the composer applies to its own narrow inputs, just over a much larger structured payload. Cross-reference: [DECISIONS.md](../../DECISIONS.md) 2026-04-25 entry "Layer 3 LLM synthesizer" and [OUTPUT_QUALITY_HANDOFF_PLAN.md](../../OUTPUT_QUALITY_HANDOFF_PLAN.md) Cycle 4.
- **Cycle 5 (commits `1f8ab6a`, `6b861e9`, `d3293a1`, `3811dbf`, `c589635`, `a429d88`):** The Cycle 3+4 pattern (consolidated chat-tier artifact + Layer 3 synthesizer) is now wired into the remaining five chat-tier handlers plus the DECISION fall-through. Generalized `_browse_chat_tier_artifact` to `_chat_tier_artifact_for(pid, text, overrides, answer_type)` so each handler picks its tier's module set from `briarwood.execution.module_sets.ANSWER_TYPE_MODULE_SETS`. handle_projection / handle_risk / handle_edge / handle_strategy / handle_rent_lookup all build their per-tool views (proj, risk_profile, strategy_fit, rent_payload) from the artifact when populated, and run the synthesizer on the default narrative path; their tier-specific composers (`compose_structured_response` for projection, `complete_and_verify` for risk/edge/strategy/decision_summary, `compose_contract_response` for rent_lookup) remain as fallbacks. Section-followup composers (`compose_section_followup` for trust, downside, comp_set, entry_point, value_change, rent_workability) keep their narrow-payload calls — those are surgical section-specific generations. handle_decision additionally pre-loads the artifact to warm `_SCOPED_MODULE_OUTPUT_CACHE` for its dense per-tool block (PropertyView.load, get_cma, get_projection, get_risk_profile, get_strategy_fit, get_rent_estimate), so the per-tool calls hit the module cache instead of running modules fresh; the wedge interaction is unchanged. The README's chat-tier topology description above ("handlers compose via tools.py + composer.py, orchestrator only via wedge / external runner") is now fully stale — every chat-tier handler that has a property cascade calls `run_chat_tier_analysis` via `_chat_tier_artifact_for` before any per-tool work. Cross-reference: [OUTPUT_QUALITY_HANDOFF_PLAN.md](../../OUTPUT_QUALITY_HANDOFF_PLAN.md) Cycle 5.

### 2026-04-24
- Initial README created.

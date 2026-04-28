# Briarwood — Gap Analysis

Compares the current architecture (see [ARCHITECTURE_CURRENT.md](ARCHITECTURE_CURRENT.md)) to the six-layer target architecture: Intent LLM → Model Orchestration → Unified Intelligence LLM → Representation Agent → Value Scout (parallel) → Conversational Delivery.

Each layer notes: target state, current state (with file paths), gap (concrete), complexity to close (`trivial` / `moderate` / `significant` / `major rework`), and risks.

---

## Layer 1 — Intent LLM

**Target state.** A single LLM call that classifies both the user's question (buy / flip / rent / compare / etc.) and their user type (first-time buyer / investor / hybrid / developer) on every turn, so downstream orchestration can shape both what runs and how it's presented.

**Current state.** [briarwood/agent/router.py:105](briarwood/agent/router.py#L105) classifies each turn into one of 14 `AnswerType` values via `gpt-4o-mini` structured output, with two regex cache rules in front for decisive greeting and comparison turns, plus a what-if-price override short-circuit for basis-sensitive questions. The router produces `RouterDecision(answer_type, confidence, target_refs, reason)` — no user-type field. [briarwood/interactions/](briarwood/interactions/) accumulates session signal and persona hints, but nothing consolidates them into a typed user profile that dispatch keys on.

This layer splits into an engineering gap and a product decision. They need to be treated separately.

### Layer 1 — Engineering gap

**Gap.** Extend the router schema with a `user_type` field alongside `answer_type`. This is either a second classification step or a combined prompt. Plumb `user_type` through `RouterDecision` → `Session` state → dispatch handlers. Reconcile with the existing persona signals in [briarwood/interactions/](briarwood/interactions/) so they feed the router rather than diverge from it.

**Complexity.** Moderate. The router pattern is already in place; one schema field and one plumbing path. The reconciliation with `interactions/` is the trickier half because those signals accumulate across turns — the user-type classification needs to smooth over early-turn uncertainty without flip-flopping.

**Risks.** Cold-start uncertainty. A user's first message rarely reveals their type; a confident-but-wrong early classification will mis-shape the rest of the session. This pushes toward "unknown / pending" as a first-class type value, which then has to be handled everywhere downstream.

### Layer 1 — Product decision

**Gap.** Engineering cannot start without a product-level decision on the taxonomy itself:

1. What exactly are the user-type values? (The prompt suggests first-time buyer / investor / hybrid / developer, but this is the decision being asked.) Is "hybrid" one type or a compose-of-two?
2. How does user type modify the intent-tier cascade? Auto-memory note: browse-style "what do you think of X?" should go to comps + similar listings, NOT the full decision cascade. Does user type override tier choice or compose with it? An investor asking a browse question might want different info than a first-time buyer asking the same thing.
3. How much cold-start signal is required before committing to a type? Does the system need a "tell me about yourself" first turn, or infer from behavior?

**Complexity.** Moderate *once decided*. Zero progress possible until decided.

**Risks.** This interlocks with the auto-memory note that LLM guardrails are currently too tight. Loosening routing/narration and introducing user-type inference should be planned together — otherwise the training signal the looser routing generates won't be keyed to user type, and you'll have to re-label later. Put differently: start collecting user-type signal in the router before you start making decisions based on it.

---

## Layer 2 — Model Orchestration

**Target state.** Based on the detected intent (and user type), an orchestrating LLM reads a tool registry and fires the appropriate specialty models in the right order, handling their dependencies.

**Current state.** Rule-based dispatch. [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) holds per-`AnswerType` handler functions that hardcode which modules run for each tier. The scoped execution registry at [briarwood/execution/registry.py](briarwood/execution/registry.py) provides the DAG machinery (dependency resolution, caching, execution mode), but what *goes into* the registry for a given turn is decided by handler code, not by an LLM reading a spec.

A first deterministic intent → module-set mapping landed 2026-04-25 (Cycle 2 of OUTPUT_QUALITY_HANDOFF_PLAN.md): [`briarwood/execution/module_sets.py::ANSWER_TYPE_MODULE_SETS`](briarwood/execution/module_sets.py) now declares which modules each chat-tier `AnswerType` runs, and [`briarwood.orchestrator.run_chat_tier_analysis`](briarwood/orchestrator.py) executes one consolidated plan against that set per turn. The LLM tool-use loop (the actual Layer 2 target) is still absent — the mapping is hand-authored — but the affordance now exists for an LLM step to override the default set on a per-turn basis. Cycle 3 will rewire chat-tier dispatch handlers to call this entry instead of the per-tool fragmentation pattern documented under Risks below.

**Gap.** Three pieces are missing:

1. **A clean tool registry.** [TOOL_REGISTRY.md](TOOL_REGISTRY.md) is the first draft. Needs to cover all 22+ models (scoped + legacy) with typed inputs, typed outputs, dependencies, intent-fit, invariants, and `blockers_for_tool_use` flags.
2. **A tool-use loop.** An LLM that reads the registry, picks tools for the intent, invokes them, inspects results, decides whether more is needed. This doesn't exist.
3. **A legacy-model promotion decision.** Today, 15 models live in the scoped registry; another 25+ are reachable only through wrappers or post-hoc grafts like [briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88). Legacy models cannot be called as tools in isolation. Before Layer 2 can work, someone needs to decide which legacy models get promoted to first-class scoped entries and which stay internal.

**Complexity.** Significant. The tool-use loop is well-understood LLM plumbing, but the promotion decision touches every module boundary. And the scoped registry's DAG pattern doesn't express "optional" or "user-type-dependent" dependencies — those semantics would need to be added.

**Risks.**
- Module dependencies aren't fully expressed as data. Some scoped wrappers run multiple legacy modules internally (e.g., `resale_scenario` runs `bull_base_bear` which runs five more). An LLM orchestrator calling them individually could produce incoherent chains if the dep graph isn't surfaced.
- Cross-reference with the `AUDIT_REPORT.md` F-004 finding in ARCHITECTURE_CURRENT's Known Rough Edges: the orchestrator now raises `RoutingError` rather than falling back, so registry coverage must be ironclad before an LLM starts picking modules freely. A "this tool doesn't exist" error cannot degrade gracefully.
- AGENTS.md forbids LLM from doing numeric logic. Tool-use implies the LLM decides *which tools* run, not what they compute — but the line gets blurry when tool selection is driven by partial numeric results from prior tools.

---

## Layer 3 — Unified Intelligence LLM

**Target state.** An LLM ingests the outputs of all specialty models that ran and asks two questions: (a) does this answer the user's intent? (b) how do we illustrate it compellingly? The first question drives re-orchestration (go run more tools) or claim framing; the second hands off to the Representation Agent.

**Current state.** Synthesis is mechanical. [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) assembles module outputs deterministically for the legacy path. The Phase 3 claim-object pipeline at [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py) does the same for one archetype. Neither path has an LLM judging whether the intent has been answered.

The consolidation prerequisite landed 2026-04-25 (Cycle 2 of OUTPUT_QUALITY_HANDOFF_PLAN.md): [`run_chat_tier_analysis`](briarwood/orchestrator.py) produces a fully-populated `UnifiedIntelligenceOutput` from a single intent-keyed plan per turn. Cycle 3 (commit `ca94d2f`) wired `handle_browse` to the consolidated path. Cycle 4 (commit `fb23152`) added the Layer 3 LLM synthesizer at [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) — `synthesize_with_llm(unified, intent, llm)` reads the full unified output and the user's intent contract and writes 3-7 sentences of intent-aware prose. Cycle 5 (commits `1f8ab6a`, `6b861e9`, `d3293a1`, `3811dbf`, `c589635`, `a429d88`) rolled the same wiring out to `handle_projection`, `handle_risk`, `handle_edge`, `handle_strategy`, `handle_rent_lookup`, and `handle_decision`. Manifest surface `synthesis.llm`.

**The substrate-and-prose pair Layer 3 needed is now in place across every chat-tier handler that has a property cascade.** Section followups (trust mode, downside mode, comp_set, entry_point, value_change, rent_workability) keep their tight `compose_section_followup` composer calls — those are surgical section-specific generations and don't benefit from the full unified output the same way the default handler paths do.

What's still absent is the **intent-satisfaction-and-reorchestrate loop** the gap below names — the synthesizer writes prose from whatever the deterministic models produced; it does not yet ask "did we answer the user?" or trigger more tool calls. A telemetry-only prototype of that question landed earlier in [briarwood/shadow_intelligence.py](briarwood/shadow_intelligence.py) (ROADMAP "Prototype Layer 3 intent-satisfaction LLM in shadow mode" 2026-04-24); promotion-from-shadow is open.

The adjacent infrastructure is the grounding verifier in [briarwood/agent/composer.py](briarwood/agent/composer.py), which fact-checks prose against a `[[Module:field:value]]` anchor format. That's narrower than intent-satisfaction — it asks "are the numbers right?", not "did we answer the question?".

**Gap.** An LLM step that reads the intent contract (from the router) and the aggregated module outputs, and either (a) declares intent-satisfied and passes to Representation, or (b) declares gaps and either requests more tools from Layer 2 or surfaces a "I can't answer this well because X" response.

**Complexity.** Moderate-to-significant. The LLM call itself is straightforward — structured output with a yes/no + missing-fact list. The hard part is defining what "satisfies the intent" *means* per AnswerType in a way the LLM can check, and designing the re-orchestration loop without letting it retry forever.

**Risks.**
- AGENTS.md forbids LLM numeric logic. Tight prompt design needed to stay on the "is this complete?" side of the line and not drift into "does this make sense?". The grounding verifier already walks this line and has strict-regen logic as a safety net; Layer 3 needs something analogous.
- A cautionary precedent lives in the numeric guardrail at [api/guardrails.py:173-182](api/guardrails.py#L173-L182): its NEW-V-003 fix (recently landed — the prose-string tokens were previously ungrounded and the verifier stripped the lead recommendation verb) shows how easily a contract between prompt and validator drifts out of sync. Layer 3's intent-satisfaction LLM has the same shape of risk.

---

## Layer 4 — Representation Agent

**Target state.** Given the unified intelligence output, pick the right charts, tables, and layouts for this specific answer. Return a component spec, not rendered UI.

**Current state.** **This layer substantially exists.** [briarwood/representation/agent.py:128-187](briarwood/representation/agent.py#L128-L187) uses `gpt-4o-mini` structured output to map `UnifiedIntelligenceOutput` + `module_views` to a `RepresentationPlan` — a list of `RepresentationSelection` entries, each binding a claim type to a chart id from the registry at [briarwood/representation/charts.py](briarwood/representation/charts.py). Deterministic heuristic fallback when the LLM is unavailable.

**Gap.** Two narrower pieces:

1. **Triggering is gated on the claims flag.** The Representation Agent runs inside the claim-object path; the legacy synthesis path emits chart events directly from handlers. Broadening the Representation Agent to run on every turn is mostly plumbing.
2. **Chart registry is small.** Eight chart kinds per [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) (`scenario_fan`, `cma_positioning`, `risk_bar`, `rent_burn`, `rent_ramp`, `value_opportunity`, `horizontal_bar_with_ranges`, plus legacy iframe). The Representation Agent can only select from what exists.

**Complexity.** Trivial to moderate. Unflagging the agent's triggering is code-path work; expanding the chart registry is prompt + frontend component work per chart.

**Risks.** Least-risky layer. Most of the work is already done. The main design question — "what's the contract between synthesis and rendering?" — has been answered with `ClaimSpec` + `chart_id` + `evidence`. Adding charts is additive.

---

## Layer 5 — Value Scout

**Target state.** A parallel process that proactively surfaces angles the user didn't ask about but should care about, based on their inferred profile (e.g., "after a 5% rent escalation, you break even in 5 years").

**Current state.** Substantially landed as of Phase 4b Scout Cycles 1-7 (2026-04-28). [briarwood/value_scout/](briarwood/value_scout/) now exposes a shared `scout(...)` dispatcher at [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) for both claim-wedge `VerdictWithComparisonClaim` inputs and chat-tier `UnifiedIntelligenceOutput` inputs. Claim-wedge compatibility stays through `scout_claim(claim)`. BROWSE, DECISION fall-through, and EDGE handlers run Scout before the Layer 3 LLM synthesizer, cache results on `session.last_scout_insights`, pass them into `synthesize_with_llm`, and surface them through the `scout_insights` SSE event rendered by `ScoutFinds`.

**Gap.**
- Parallel-invocation machinery. Scout is no longer claim-wedge-only, but it still runs sequentially after the consolidated chat-tier artifact exists. Target-state says "parallel process" — needs to fire alongside Layer 2 orchestration if latency or architecture demands it.
- Pattern library breadth. The library now includes `uplift_dominance`, `rent_angle`, `adu_signal`, and `town_trend_tailwind`, plus the LLM scout. Target still implies more patterns over time: teardown arbitrage, scarcity premium, comp-spread widening, hidden comp-set strength, etc. Each new pattern needs deterministic trigger heuristics and confidence scoring.
- User-type conditioning. A pattern that matters for an investor ("break-even IRR") may be noise for a first-time buyer ("can I live here?"). No mechanism today keys patterns to user type.

**Complexity.** Significant. Parallel invocation plus a growing pattern library plus user-type-conditioned triggering is three non-trivial pieces that interact.

**Risks.**
- Scout firing on every turn could feel like a noisy upsell. Trigger discipline matters — one insight per turn at most, with confidence thresholds, or users will tune it out.
- Needs Layer 1 (user type) to be useful. Without it, scout insights are generic, which defeats the "two-steps-ahead" framing.
- The first deterministic chat-tier thresholds are conservative. Live `/admin/turn/[turn_id]` review should tune `rent_angle`, `adu_signal`, and `town_trend_tailwind` rather than assuming v1 thresholds are final.

**Substrate added 2026-04-28 (AI-Native Foundation Stages 1-3).** Scout
inherits a richer foundation than was available when this gap was
written:
- Every turn's `UnifiedIntelligenceOutput` is persisted in
  `turn_traces` (Stage 1) so Scout patterns can correlate across
  turns / properties.
- `data/llm_calls.jsonl` carries per-call cost + duration with
  `turn_id` linkage so `value_scout.scan` will be measurable per
  turn from day one.
- The `/admin` dashboard (Stage 3) gives the owner a read surface
  where scout's outputs can be evaluated against the cost they
  incur (top-10 highest-cost turns, drill-down to manifest with
  the `synthesis.llm` + `value_scout.scan` calls listed side-by-side).
- The closed user-feedback loop (Stage 2) means a thumbs-down on a
  scout-influenced turn flows back into the next turn's framing
  via the existing `feedback:recent-thumbs-down-influenced-synthesis`
  hint mechanism. Scout doesn't need its own loop wiring — it
  rides the synthesis hint.

These together close the "we ship scout but can't evaluate it"
risk that would have been live in a 2026-04-26 build.

**Scout closeout added 2026-04-28.** `value_scout.scan` appears in the
LLM ledger through `complete_structured_observed`, and chat-tier
`scout(...)` writes a manifest note with `insights_generated`,
`insights_surfaced`, and `top_confidence`. This leaves two Layer 5 target
items open: true parallel firing alongside Layer 2, and user-type
conditioning.

---

## Layer 6 — Conversational Delivery

**Target state.** Verbose, GPT/Claude-style streaming response that weaves prose, component specs, and scout insights together into one cohesive answer.

**Current state.** The ingredients are present, the weaving is not.

- SSE `text_delta` events stream from the composer. [briarwood/agent/composer.py](briarwood/agent/composer.py) emits prose; [api/pipeline_adapter.py](api/pipeline_adapter.py) chunks it word-by-word for streaming.
- Structured events (`verdict`, `chart`, `scenario_table`, etc.) emit as complete objects.
- Card components in [web/src/components/chat/](web/src/components/chat/) render structured payloads alongside prose.
- Scout insights emit as independent `scout_insights` SSE events and render through `ScoutFinds` for chat-tier turns. Claim-wedge insights still travel inside the claim event.

**Gap.**
- Prose and cards render in parallel but don't reference each other. The prose can't say "see the chart below" and have the chart land in the right place; ordering and relative layout are implicit.
- Scout insights now get inline treatment in BROWSE / DECISION / EDGE through the synthesizer's `scout_insights` prompt payload plus the dedicated `ScoutFinds` surface.
- Tone doesn't adapt to user type (which doesn't exist yet — Layer 1 dependency).
- Auto-memory flags: live SSE cards sometimes need a page reload to render; decision summaries are weak. These are UX regressions more than architectural gaps, but they block the "conversational delivery" feel.

**Complexity.** Moderate. Mostly prompt and glue work once Layers 1 and 5 land. The architectural primitives (event types, components, streaming) are already built.

**Risks.** UX work, not architecture. Decisions about tone, inline vs. block layout for insights, and pacing of prose-vs-card handoffs need an owner. Getting this wrong at the prompt level will feel worse than getting it wrong at the synthesis level because users don't parse synthesis failures separately from delivery failures.

---

## Cross-Cutting Concerns

### Can specialty models be called as tools in isolation?

**Mixed.**

- **Scoped registry models (15):** yes. Each has `run_<name>(context: ExecutionContext)` in [briarwood/execution/registry.py](briarwood/execution/registry.py). Stable contract, typed inputs, typed outputs.
- **Legacy models (25+):** no. Reachable only via their wrappers. E.g., `ComparableSalesModule` is invoked only inside `CurrentValueModule`, `HybridValueModule`, `ArvModule`, `UnitIncomeOffsetModule`, and (since the claims wedge) via the post-hoc graft at [briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88). Calling one of these legacy models from an LLM orchestrator would require either (a) promoting them to the scoped registry with a stable contract, or (b) building a parallel "graft" machinery like the claims pipeline uses.

### Single source of truth for model outputs?

**Partial.** Pydantic schemas exist for many modules (e.g., `ScenarioOutput`, `HybridValueOutput`, `RentalEaseOutput`, `ValueFinderOutput`). But there is no single file that maps `module_name → input_schema, output_schema` for an orchestrating LLM to read. [TOOL_REGISTRY.md](TOOL_REGISTRY.md) is the first attempt at that registry.

### Prompt/response logging?

**Substantially closed 2026-04-28** by AI-Native Foundation Stages 1+3.

- **Per-turn manifest with full module + LLM attribution** persists to
  the new `turn_traces` table in `data/web/conversations.db` (Stage 1).
  One row per chat turn with `answer_type`, `confidence`,
  `classification_reason`, `dispatch`, `duration_ms_total`, plus JSON
  columns for `modules_run`, `llm_calls_summary`, `tool_calls`, `notes`.
- **Per-LLM-call ledger** persists to `data/llm_calls.jsonl` (Stage 1).
  One JSON line per call with `surface`, `provider`, `model`,
  `prompt_hash`, `response_hash`, `status`, `attempts`, `duration_ms`,
  `cache_hit`, `error_type`, `input_tokens`, `output_tokens`,
  `cost_usd`, plus `recorded_at` and `turn_id` (Stage 3 addition for
  per-turn cost aggregation). Full prompt/response bodies excluded by
  default; flip `BRIARWOOD_LLM_DEBUG_PAYLOADS=1` to attach them.
- **Read-side admin surface** at `/admin` (Stage 3, behind
  `BRIARWOOD_ADMIN_ENABLED=1`) renders weekly aggregates of latency
  by `answer_type`, cost by `surface`, thumbs ratio, top-10 slowest
  turns, top-10 highest-cost turns, with per-turn drill-down.

Remaining gap: structured-output prompt/response cache hit ratio
(only LLM-response cache today, not prompt cache). Defer until
prompt-cache integration is on a roadmap.

Cross-reference: [`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md),
[`DASHBOARD_HANDOFF_PLAN.md`](DASHBOARD_HANDOFF_PLAN.md),
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) §"Persistence".

### Model-accuracy feedback loop?

**Substrate landed 2026-04-28; live outcome run still open.** AI-Native
Foundation Stage 4 added the mechanics Loop 1 was missing:

- Manual sale-price outcome ingestion in
  [briarwood/eval/outcomes.py](briarwood/eval/outcomes.py), with dry-run
  validation via [scripts/ingest_outcomes.py](scripts/ingest_outcomes.py).
- One-shot JSONL outcome backfill via
  [scripts/backfill_outcomes.py](scripts/backfill_outcomes.py).
- Durable per-module `model_alignment` rows in
  [api/store.py](api/store.py), storing prediction, confidence, actual
  outcome, absolute error, absolute percentage error, alignment score, and
  high-confidence underperformance flags.
- Record-only `receive_feedback(session_id, signal)` hooks on
  `current_value`, `valuation`, and `comparable_sales`.
- Analyzer reporting in
  [briarwood/feedback/model_alignment_analyzer.py](briarwood/feedback/model_alignment_analyzer.py).

Remaining gap: the owner still needs to supply a real `data/outcomes/`
file and run the backfill so the analyzer can produce live human-review
tuning candidates. Auto-recalibration remains deliberately absent.

### Caching?

- Synthesis cache in the orchestrator ([briarwood/orchestrator.py](briarwood/orchestrator.py)).
- Per-turn `session.last_*_view` stored in [briarwood/agent/session.py](briarwood/agent/session.py).
- Cache key requires `execution_mode` (recent commit `1c21bdb`: `fix(orchestrator): require execution_mode in build_cache_key`).
- LLM-response cache exists but is **off by default** (`BRIARWOOD_LLM_RESPONSE_CACHE` env-gated, in-process only) — see [briarwood/agent/llm_observability.py:175-211](briarwood/agent/llm_observability.py#L175-L211).

The "defer response caching until the call ledger exists" gate is now
satisfied (Stage 1 ledger landed 2026-04-28, Stage 3 dashboard 2026-04-28).
Turning the cache on is a roadmap-level decision; the prerequisite
telemetry exists.

### Retry?

- Router: one automatic retry on structured-output failure at [briarwood/agent/router.py:217-236](briarwood/agent/router.py#L217-L236).
- Composer: strict regen retries once on ≥2 grounding violations (default on via `BRIARWOOD_STRICT_REGEN`).
- No systemic retry layer across other LLM call sites.

### Biggest structural obstacle to the new architecture

**The legacy/scoped split.** For LLM-driven orchestration to work (Layer 2), every model that matters as a tool needs to live in the scoped registry with a stable contract. Today about a third (15 of 40+) live there; the rest are reachable only through other models. Before Layer 2 can exist as specified, someone has to decide:

- Which legacy models get promoted to first-class tools? (`comparable_sales` is the obvious first — the claims pipeline already grafts it.)
- Which stay internal because they're composition helpers, not independently meaningful tools?
- How do we express "this tool is really a composition of these sub-tools" so the orchestrator doesn't call the sub-tools separately and produce incoherent results?

Cross-reference: `AUDIT_REPORT.md` F-004 and `VERIFICATION_REPORT.md`'s coverage analysis (see ARCHITECTURE_CURRENT's Known Rough Edges) already flagged that the orchestrator raises hard rather than falling back. That makes registry coverage a correctness requirement, not just a performance one — which raises the bar for any promotion decision.

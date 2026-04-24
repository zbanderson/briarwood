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

**Current state.** Partial. [briarwood/value_scout/](briarwood/value_scout/) exists with one pattern (`uplift_dominance` at [briarwood/value_scout/patterns/uplift_dominance.py](briarwood/value_scout/patterns/uplift_dominance.py)). `scout_claim(claim)` at [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) runs patterns and returns a `SurfacedInsight`. It runs **only inside the claim-object wedge**, not in parallel with the main analysis path.

**Gap.**
- Parallel-invocation machinery. Currently scout runs after claim synthesis, sequentially. Target-state says "parallel process" — needs to fire alongside Layer 2 orchestration, not after Layer 3 synthesis.
- Pattern library is one entry. Target implies many: rent escalation break-even, optionality patterns, teardown arbitrage, scarcity premium, comp-spread widening, etc. Each pattern needs a trigger heuristic and a structured insight schema.
- User-type conditioning. A pattern that matters for an investor ("break-even IRR") may be noise for a first-time buyer ("can I live here?"). No mechanism today keys patterns to user type.

**Complexity.** Significant. Parallel invocation plus a growing pattern library plus user-type-conditioned triggering is three non-trivial pieces that interact.

**Risks.**
- Scout firing on every turn could feel like a noisy upsell. Trigger discipline matters — one insight per turn at most, with confidence thresholds, or users will tune it out.
- Needs Layer 1 (user type) to be useful. Without it, scout insights are generic, which defeats the "two-steps-ahead" framing.
- The `uplift_dominance` pattern's v1 returns "first non-null"; Phase B is marked as adding scoring to select "strongest". That scoring logic is shared across all future patterns and should be designed before the pattern count grows.

---

## Layer 6 — Conversational Delivery

**Target state.** Verbose, GPT/Claude-style streaming response that weaves prose, component specs, and scout insights together into one cohesive answer.

**Current state.** The ingredients are present, the weaving is not.

- SSE `text_delta` events stream from the composer. [briarwood/agent/composer.py](briarwood/agent/composer.py) emits prose; [api/pipeline_adapter.py](api/pipeline_adapter.py) chunks it word-by-word for streaming.
- Structured events (`verdict`, `chart`, `scenario_table`, etc.) emit as complete objects.
- Card components in [web/src/components/chat/](web/src/components/chat/) render structured payloads alongside prose.
- Scout insights emit as fields inside the claim event, not as independent visual elements.

**Gap.**
- Prose and cards render in parallel but don't reference each other. The prose can't say "see the chart below" and have the chart land in the right place; ordering and relative layout are implicit.
- Scout insights don't get inline treatment. They sit inside the verdict card; the prose doesn't call them out.
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

**Partial.**
- Router writes low-confidence / fallback classifications to `data/agent_feedback/untracked.jsonl` (per [briarwood/agent/router.py](briarwood/agent/router.py) docstring).
- Cost per call is recorded via [briarwood/cost_guard.py](briarwood/cost_guard.py).
- Composer emits a `verifier_report` SSE event with grounding violations, but full prompt/response bodies aren't systematically logged anywhere inspectable.
- Representation Agent, claim-prose LLM, and local-intelligence extraction don't emit comparable telemetry.

Action item: create a shared LLM call ledger that records call site, prompt tier,
provider/model, structured-vs-prose mode, latency, token/cost estimate,
fallback reason, verifier outcome, and whether the user saw LLM prose or a
deterministic fallback. See `FOLLOW_UPS.md`.

### Caching?

- Synthesis cache in the orchestrator ([briarwood/orchestrator.py](briarwood/orchestrator.py)).
- Per-turn `session.last_*_view` stored in [briarwood/agent/session.py](briarwood/agent/session.py).
- Cache key requires `execution_mode` (recent commit `1c21bdb`: `fix(orchestrator): require execution_mode in build_cache_key`).
- No LLM-response caching.

Action item: defer response caching until the call ledger exists; without
telemetry, cache hits would hide prompt quality and fallback behavior.

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

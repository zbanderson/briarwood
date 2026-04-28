# agent/router — Intent Router (AnswerType Classification)

**Last Updated:** 2026-04-28 (Round 2)
**Layer:** Intent (Layer 1 — answer-type half; user-type does not exist yet)
**Status:** STABLE

## Purpose

The router classifies every user turn into exactly one `AnswerType` before any tool fires, bounding what the rest of the pipeline can do. Design is **LLM-first with a tiny regex cache**: two high-precision cache rules catch greetings and explicit comparisons; a third short-circuit catches what-if-price overrides; everything else routes to a `gpt-4o-mini` structured-output classification with a single retry on transport failure. The full output is a `RouterDecision` carrying the answer type, a confidence score, extracted property/listing references, a short reason string, the LLM's raw suggestion (when it ran), and an auto-populated `IntentContract` that the analysis-tier router can thread through. Cache rules were deliberately narrowed — the previous broader regex ontology drifted out of sync with the LLM prompt; today only patterns where regex is decisive (greetings, `compare/vs` keyword) live in the cache, and the rest is the LLM's job. Per the module docstring at [router.py:11-13](router.py#L11-L13): "Everything else is classified by the LLM — the single source of truth for semantic routing. Drifting language and new intents are handled by updating the prompt, not by growing a regex list."

## Location

- **Entry point:** [briarwood/agent/router.py:239](router.py#L239) — `classify(text: str, *, client: LLMClient | None = None) -> RouterDecision`.
- **AnswerType enum:** [briarwood/agent/router.py:40-54](router.py#L40-L54) — 14 values: `LOOKUP`, `DECISION`, `COMPARISON`, `SEARCH`, `RESEARCH`, `VISUALIZE`, `RENT_LOOKUP`, `MICRO_LOCATION`, `PROJECTION`, `RISK`, `EDGE`, `STRATEGY`, `BROWSE`, `CHITCHAT`.
- **RouterDecision:** [briarwood/agent/router.py:57-76](router.py#L57-L76) — frozen dataclass; auto-populates `intent_contract` in `__post_init__` via `build_contract_from_answer_type` from [briarwood/intent_contract.py](../intent_contract.py).
- **Cache rules:** `_CACHE_RULES` tuple at [briarwood/agent/router.py:83-108](router.py#L83-L108) — two entries.
- **LLM classification path:** `_llm_classify` at [briarwood/agent/router.py:210-236](router.py#L210-L236).
- **LLM prompt:** `_LLM_SYSTEM` inline at [briarwood/agent/router.py:138-177](router.py#L138-L177).
- **Pydantic schema (LLM output):** `RouterClassification` at [briarwood/agent/router.py:196-207](router.py#L196-L207).
- **Tests:** [tests/agent/test_router.py](../../tests/agent/test_router.py).

## Role in the Six-Layer Architecture

- **This layer:** Intent (Layer 1 — answer-type half). Per [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 1, the target-state Layer 1 is a single LLM call that classifies BOTH the user's question and their user type (first-time buyer / investor / hybrid / developer). Today the router only produces the `AnswerType`. The user-type half is an open product decision; nothing in `RouterDecision` carries it yet.
- **Called by:** `api/pipeline_adapter.py::classify_turn()` at [api/pipeline_adapter.py](../../api/pipeline_adapter.py) (the FastAPI bridge), which forwards to `briarwood.agent.router.classify` per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Data Flow §3. Also called by [briarwood/agent/cli.py](cli.py), [briarwood/agent/tools.py](tools.py), [briarwood/agent/feedback.py](feedback.py).
- **Calls:** Optional `LLMClient` (when provided) for the classification path. Imports `parse_overrides` from [briarwood/agent/overrides.py](overrides.py) lazily for the what-if-price short-circuit.
- **Returns to:** The adapter / dispatch layer, which then dispatches to a tier-specific stream based on `AnswerType`.
- **Emits events:** None directly. Logs low-confidence / fallback turns to `data/agent_feedback/untracked.jsonl` (per the module docstring at [router.py:14-16](router.py#L14-L16); see [briarwood/agent/feedback.py](feedback.py) for the writer).

## LLM Usage

| Call site | Provider | Model | Purpose | Prompt location |
|-----------|----------|-------|---------|-----------------|
| [router.py:218-223](router.py#L218-L223) `_llm_classify` | injected `LLMClient` (typically OpenAI) | injected — caller controls; per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Default `gpt-4o-mini` | Classify a user turn into one of 14 `AnswerType` values | Inline `_LLM_SYSTEM` at [router.py:138-177](router.py#L138-L177) |

**Response parsing:** Strict structured output via the `RouterClassification` Pydantic schema at [router.py:196-207](router.py#L196-L207). The schema enforces `extra="forbid"`; `AnswerType` is the typed enum so unknown values fail validation.

**Retry / timeout:** One retry on `complete_structured` returning `None` (transport failure, empty response, invalid JSON, schema mismatch) at [router.py:217-227](router.py#L217-L227). Two attempts total. Persistent failures fall through to the caller's default (`AnswerType.LOOKUP` with confidence 0.3 — see Invariants).

**Cost characteristics:** One classification call per turn that doesn't hit the cache or override path. `max_tokens=80`. Per ARCHITECTURE_CURRENT.md, ~50% of traffic is unambiguous and short-circuited; the LLM sees the rest.

**Sanity guard:** When the LLM returns `CHITCHAT` for a non-greeting input, the classifier defaults to `BROWSE` instead — safer than `DECISION` (which would trigger the full cascade). At [router.py:231-235](router.py#L231-L235).

## Inputs

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `text` | `str` | User turn | Stripped at [router.py:249](router.py#L249); empty input shortcuts to `CHITCHAT` confidence `1.0`. |
| `client` | `LLMClient \| None` | Caller | Optional. When `None`, no LLM call is made; non-cache, non-override turns fall through to the `LOOKUP` default with confidence `0.3`. |

## Outputs

`RouterDecision` (frozen dataclass at [router.py:57-76](router.py#L57-L76)):

| Field | Type | Notes |
|-------|------|-------|
| `answer_type` | `AnswerType` | One of 14 enum values. |
| `confidence` | `float` | `1.0` empty input; `0.9` cache hit; `0.7` what-if-price override; `0.75` override + rent/projection hint; `0.6` LLM classify; `0.3` default fallback. |
| `target_refs` | `list[str]` | Property-id-shaped tokens extracted via `_PROPERTY_ID_RE` at [router.py:111](router.py#L111) (slug-like patterns with at least three hyphenated segments). |
| `reason` | `str` | Short string explaining the routing decision (`"empty input"`, `"greeting"`, `"compare/vs keyword"`, `"what-if price override"`, `"override with rent question"`, `"override with projection question"`, `"llm classify"`, `"default fallback"`). |
| `llm_suggestion` | `AnswerType \| None` | Set only when the LLM participated and returned a value. |
| `intent_contract` | `IntentContract \| None` | Auto-populated in `__post_init__` via `build_contract_from_answer_type` at [briarwood/intent_contract.py](../intent_contract.py). The contract carries the chat-tier intent into the analysis-tier router. |

## Routing Policy

`classify` rule order ([router.py:239-319](router.py#L239-L319)):

1. **Empty input** → `CHITCHAT` confidence `1.0`.
2. **Cache rules** (run before everything else so explicit commands aren't hijacked by override parsing):
   - Stand-alone greeting / thanks (`hi`, `hello`, `hey`, `yo`, `sup`, `thanks`, `thank you`, `ok`, `okay`, `cool`, `nice` — entire-message match) → `CHITCHAT` confidence `0.9`.
   - Explicit comparison (`compare`, slug-vs-slug, `which one is better/worse`) → `COMPARISON` confidence `0.9`.
3. **What-if-price override** — when `parse_overrides(text)` finds a price/financing override, the turn is decision-natured. Sub-routes:
   - With rent hint (`how much could X rent for`, `monthly rent`, `rental income`, `lease for`) → `RENT_LOOKUP` confidence `0.75`.
   - With projection hint (`arv`, `after repair value`, `sell it for`, `flip`, `resale`) → `PROJECTION` confidence `0.75`.
   - Otherwise → `DECISION` confidence `0.7`.
4. **LLM classification** — when `client` is not `None`. Returns `RouterDecision` with `llm_suggestion` populated; if LLM returns `CHITCHAT` for a non-greeting, falls back to `BROWSE`.
5. **Default fallback** → `LOOKUP` confidence `0.3`. Logged at WARNING.

## Dependencies on Other Modules

- **Schema dependency on:** `IntentContract` from [briarwood/intent_contract.py](../intent_contract.py). Any change to `IntentContract` or `build_contract_from_answer_type` is a contract change here. The module docstring at [intent_contract.py:1-26](../intent_contract.py#L1-L26) explicitly forbids the reverse import (intent_contract must not import the router) so the chat router can depend on it cleanly.
- **Imports:** `briarwood.agent.llm.LLMClient` for the classifier interface; `briarwood.agent.overrides.parse_overrides` (lazy import inside `classify`) for the price-override path.
- **Coupled to:** `api/pipeline_adapter.py::classify_turn` (caller) and `briarwood/agent/dispatch.py` (which routes per-`AnswerType` to handler functions). Adding an `AnswerType` value requires a matching handler in `dispatch.py` and an entry in the LLM prompt.
- **Logs to:** `data/agent_feedback/untracked.jsonl` per module docstring at [router.py:14-16](router.py#L14-L16); writer in [briarwood/agent/feedback.py](feedback.py).

## Invariants

- `classify` always returns a `RouterDecision`. Never raises on text input. Empty input is handled at [router.py:250-251](router.py#L250-L251).
- `RouterDecision` is frozen — once constructed, fields cannot be mutated (matches the "predictable behavior" intent).
- `intent_contract` is always non-`None` after `__post_init__`. Callers passing a pre-built contract (e.g., when rehydrating) bypass auto-population.
- Cache rules are scanned in tuple order; first match wins.
- LLM call retries exactly once on `None` return; persistent failure falls through (no infinite retry).
- The `CHITCHAT → BROWSE` sanity guard at [router.py:231-235](router.py#L231-L235) is the only post-LLM coercion. The LLM's other outputs are returned as-is.
- `confidence` value mapping is fixed per route: `1.0`, `0.9`, `0.75`, `0.7`, `0.6`, `0.3` — see Outputs table.
- Deterministic for empty input and cache hits. The override path is deterministic given the same `parse_overrides` output. The LLM path is non-deterministic by nature.
- Never mutates its inputs.

## State & Side Effects

- **Stateless module:** `classify` holds no state between calls.
- **Writes to disk:** indirectly — low-confidence / fallback turns are recorded by [briarwood/agent/feedback.py](feedback.py); the router itself does not write.
- **Modifies session:** no.
- **Safe to call concurrently:** yes (subject to the LLM client's own concurrency posture).

## Example Call

```python
from briarwood.agent.router import classify

decision = classify("what do you think of 526 W End Ave?", client=llm)
# decision.answer_type      == AnswerType.BROWSE   (per the IMPORTANT MAPPINGS in the prompt)
# decision.confidence       == 0.6                  (LLM classify path)
# decision.target_refs      == []                   (street-style address, not a slug)
# decision.reason           == "llm classify"
# decision.llm_suggestion   == AnswerType.BROWSE
# decision.intent_contract  is not None             (auto-populated)

decision = classify("compare 526-w-end-ave-avon-by-the-sea-nj vs 526-west-end-ave", client=None)
# decision.answer_type     == AnswerType.COMPARISON  (cache rule match)
# decision.confidence      == 0.9
# decision.target_refs     == ["526-w-end-ave-avon-by-the-sea-nj", "526-west-end-ave"]
# decision.reason          == "compare/vs keyword"
```

## Known Rough Edges

- **Audit docs say "four regex cache rules"; actual count is two.** [DECISIONS.md](../../DECISIONS.md) entry "Router cache-rule count drift in audit docs" (2026-04-24). The four-rule framing in [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) is stale — the broader cache was removed in favor of the LLM-first design described in the router's own docstring at [router.py:6-23](router.py#L6-L23).
- **What-if-price override is not in the audit-doc data flow.** [router.py:267-296](router.py#L267-L296) short-circuits to `DECISION` / `RENT_LOOKUP` / `PROJECTION` based on `parse_overrides` plus phrasing hints. Audit docs treat the router as cache-or-LLM only.
- **No user-type half.** [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 1 describes user-type as a co-equal classification; the router emits no user-type field today.
- **`target_refs` regex is slug-only.** `_PROPERTY_ID_RE` requires three+ hyphenated segments. Free-form addresses (e.g., "526 West End Ave") do not get extracted as refs by the router; resolver paths downstream handle them separately.
- **Prompt and `_CACHE_RULES` can drift independently.** The prompt is the source of truth for semantic routing. Adding a cache rule that contradicts the prompt is unenforced; the LLM's verdict is bypassed when the cache fires. Keep cache rules narrow.
- **Resolver collision risk for `target_refs`.** [project memory] flags that the resolver matches wrong slugs for ambiguous addresses ("526 West End Ave" → NC instead of NJ). The router emits the slug-shaped tokens it finds; downstream resolution is where ambiguity must be handled, not here.

## Open Product Decisions

(Pulled from [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 1; no router-specific decisions invented here.)

- **What are the user-type values?** First-time buyer / investor / hybrid / developer? Is "hybrid" one type or a composition of two? Layer-1 product decision blocks engineering work on adding user-type to `RouterDecision`.
- **How does user type modify intent-tier choice?** Browse-style "what do you think of X?" should go to comps + similar listings (per project memory); does user type override the tier choice, or compose with it?
- **How much cold-start signal is required before committing to a user type?** Open.
- **When to start collecting user-type signal in the router** even before downstream consumes it — answers the "looser routing generates training signal that needs to be keyed to user type" risk in [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 1 Risks.

## Changelog

### 2026-04-28 (Round 2)

Two guardrail-loosening fixes per `project_llm_guardrails.md`,
landed via [`ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md`](../../ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md):

- **`RouterClassification` schema gains `confidence: float`** (constrained
  `[0.0, 1.0]` via `pydantic.Field(ge=0, le=1)`) at
  [router.py:255](router.py#L255). `_LLM_SYSTEM` updated to ask the LLM
  for the score with explicit semantic anchors (1.0 = canonical, 0.7 =
  near second-choice, 0.5 = ambiguous, <0.4 = genuinely unknown).
- **`classify` plumbs LLM-emitted confidence into `RouterDecision.confidence`**
  at [router.py:411-414](router.py#L411-L414) — replaces the prior
  hardcoded `0.6`. A `max(llm.confidence, 0.4)` floor is applied
  deliberately to keep every successful classification above the 0.3
  default-fallback bucket. Stage 3 dashboards now have a real signal
  to drive low-confidence drill-downs.
- **`_PROJECTION_OVERRIDE_HINT_RE` widened** at
  [router.py:239-249](router.py#L239-L249) to catch `renovation
  scenarios?`, `run scenarios?`, `scenario`, `5-year`, `ten-year`,
  `outlook`. Defense in depth: when a real what-if-price override IS
  present, scenario / forecasting phrasings now route to PROJECTION
  rather than defaulting to DECISION.
- **Router's `has_override` tightened** at
  [router.py:380-389](router.py#L380-L389) to require a *material*
  override (`ask_price` or `repair_capex_budget`). A bare
  `mode="renovated"` from `parse_overrides` no longer triggers the
  what-if-price-override short-circuit — those turns flow to the LLM
  classifier so e.g. "Run renovation scenarios" gets correctly
  classified as PROJECTION instead of DECISION (the verdict-with-comparison
  wedge was firing on plain scenario requests). `parse_overrides`
  itself is unchanged so downstream dispatch handlers still receive
  the renovation hint via `inputs_with_overrides`.
- **Updated test fixtures** in `tests/agent/test_router.py`,
  `tests/test_intent_contract.py`, `tests/agent/test_rendering.py`:
  every `complete_structured` fake now passes `confidence=0.7`. Plus
  3 new `LLMClassifyTests` for the confidence flow + 1 new
  `PromptContentRegressionTests` pinning the prompt's confidence ask
  + 2 new `PrecedenceTests` for the bare-renovation contract change.
  One existing test
  (`test_renovation_override_with_rent_question_routes_to_rent_lookup`)
  reframed to use an explicit `if I bought... at 1.3M` price instead
  of relying on the now-removed mode-only short-circuit.
- **Contract change:** `RouterDecision.confidence` for LLM-classified
  turns is now the LLM's emission floored at 0.4, not the constant
  0.6. Callers that filtered on `confidence == 0.6` (none known) need
  to update. `parse_overrides`'s contract is unchanged; the change is
  in how the router *consumes* that output.
- Surfaced by 2026-04-28 router-audit Round 1 smoke. The
  `confidence=0.6` cap was identified in Round 1's Guardrail Review;
  the bare-renovation false-positive was identified in Round 1
  post-landing smoke. Both filed as §4 Medium ROADMAP entries on
  2026-04-28; both resolved here in Round 2.

### 2026-04-28

- Prompt content expansion to `_LLM_SYSTEM` ([router.py:169-244](router.py#L169-L244))
  closing three boundary gaps surfaced by Stage 1 turn-trace evidence:
  - **STRATEGY bucket** absorbs escalation phrasings on a pinned property:
    "recommended path", "walk me through the recommended path", "what
    should I do here", "next move", "what's the play". Previously these
    re-ran the BROWSE first-read.
  - **EDGE bucket** absorbs sensitivity / counterfactual phrasings:
    "what would change your view", "what would shift the number", "how
    sensitive is X", "what assumption is load-bearing". Previously these
    routed to RISK (which enumerates downside, not sensitivity).
  - **EDGE bucket** also absorbs comp-set follow-ups on a pinned
    property: "show me the comps", "list the comps", "what are the
    comps", "why were these comps chosen", "explain your comp choice".
  - **SEARCH bucket** absorbs list-imperative phrasings naming plural
    inventory artifacts: "show me listings here", "list the properties",
    "what is available". With explicit guard "(NOT 'show me the comps' —
    see edge.)" so the comp-set phrasings stay in EDGE.
  - **3 new IMPORTANT MAPPINGS lines** for the above.
  - **2 new counter-example pairs:** BROWSE↔STRATEGY (escalation
    boundary) and RISK↔EDGE (downside vs sensitivity boundary).
  - **RISK definition tightened:** explicit "RISK enumerates downside
    factors; it does NOT cover sensitivity / counterfactual questions
    (those are edge)" sentence added so the LLM doesn't drag
    sensitivity questions into RISK by default.
- `_COMP_SET_RE` widened in [briarwood/agent/dispatch.py:2720-2727](dispatch.py#L2720-L2727)
  to catch "show me the comps", "list the comps", "what are the comps",
  "what comps did you use", "why were the comps", "explain your comp
  choice / selection / comps". Negative case ("comparable sales market"
  in town context) deliberately not matched and pinned in the dispatch
  test.
- Regression tests added to [tests/agent/test_router.py](../../tests/agent/test_router.py):
  6 new `LLM_CANNED` cases (3 STRATEGY, 3 EDGE) + 2 SEARCH cases; 6 new
  `PromptContentRegressionTests` pinning the new bucket sentences,
  IMPORTANT MAPPINGS, and counter-example pairs. Also 2 new tests in
  [tests/agent/test_dispatch.py](../../tests/agent/test_dispatch.py)
  for the widened regex (positive list + negative case).
- **Contract change:** STRATEGY now absorbs escalation phrasings that
  previously fell to BROWSE; EDGE now absorbs sensitivity phrasings
  that previously fell to RISK. Callers that depend on "anything with
  'value' in it routes to RISK" should expect those to flow to EDGE
  now. Callers that gate on STRATEGY hitting only literal "what
  strategy" phrasings should expect a broader STRATEGY surface.
- Surfaced by 2026-04-28 AI-Native Foundation Stage 1 post-landing UI
  smoke. The `turn_traces` table is the corpus this audit was waiting
  on. See [ROUTER_AUDIT_HANDOFF_PLAN.md](../../ROUTER_AUDIT_HANDOFF_PLAN.md)
  and [DECISIONS.md](../../DECISIONS.md) 2026-04-28 entry "Router
  classification audit Cycle 1-4 landed" for the full corpus + the
  Guardrail Review.
- **Guardrail flag (DEFERRED, not fixed this pass):** every successful
  LLM classification is hardcoded to `confidence=0.6` at
  [router.py:407](router.py#L407) regardless of the model's actual
  signal. This collapses the classifier's confidence signal — the
  reason every miss in the 2026-04-28 corpus came back at exactly
  `conf=0.60`. Filed as a follow-on under §4 Medium of ROADMAP.md.

### 2026-04-25
- Prompt content change to `_LLM_SYSTEM` ([router.py:169-219](router.py#L169-L219)):
  - LOOKUP definition tightened to "single-fact retrieval that needs no
    analysis or interpretation." Words like "analysis", "analyze",
    "thoughts", "right price", "fair price", "priced right" are now called
    out as NOT lookup.
  - DECISION definition broadened to include explicit price-analysis
    phrasings: "price analysis", "analyze the price", "is this priced
    right", "is this a fair price", "how is this priced", "thoughts on
    the price." Previously these defaulted to LOOKUP because they
    contained the word "price."
  - New IMPORTANT MAPPINGS line for the price-analysis phrasings.
  - Two new counter-example pairs in the prompt: "what is the price
    analysis for X" → DECISION (not LOOKUP) vs. "what is the asking price
    of X" → LOOKUP. The pair is the clearest disambiguation signal we
    can give the model.
- Regression test cases added to [tests/agent/test_router.py](../../tests/agent/test_router.py)
  pinning the new mappings and the prompt's content shape.
- **Contract change:** the LOOKUP/DECISION boundary now distinguishes
  fact-retrieval from analysis-retrieval rather than splitting on
  decisive-verb-vs-not. Callers who relied on "any 'price' question
  routes to LOOKUP" should expect those to flow to DECISION now.
- Surfaced by 2026-04-25 output-quality audit handoff (live miss:
  "what is the price analysis for 1008 14th Ave, belmar, nj" → LOOKUP →
  one-line answer). See [AUDIT_OUTPUT_QUALITY_2026-04-25.md](../../AUDIT_OUTPUT_QUALITY_2026-04-25.md).

### 2026-04-24
- Initial README created.

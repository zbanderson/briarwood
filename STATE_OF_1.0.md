# STATE_OF_1.0

Single-file status document for the 1.0 consolidation work. Friday's
retro reads from this file; keep each dated section factual and
short. When a section is not yet filled in, leave the
`<placeholder>` slots intact.

---

## One-line status

Routed verdict is the canonical verdict; legacy surfaces render through
`briarwood.projections.legacy_verdict`; the chat-tier and analysis-tier
routers now share an `IntentContract` so they cannot drift on
`core_questions`; structured LLM calls default to `gpt-4o-mini`.

## Scope of the 1.0 cut

**In scope (being consolidated):**

- Canonical verdict path: `briarwood/synthesis/structured.py::build_unified_output()`
- Display projections: `briarwood/projections/` (new)
- Legacy consumer surfaces (to be rewired Wednesday):
  - `dash_app/quick_decision.py`
  - `dash_app/view_models.py`
  - `reports/sections/thesis_section.py`
  - `reports/sections/conclusion_section.py`

**Out of scope for this cut:**

- CMA / comps pipeline (Tuesday workstream)
- Execution cache layer (Tuesday workstream)
- Representation agent (`briarwood/pipeline/representation.py` survives
  pending Wednesday review)
- `briarwood/synthesis/structured.py`, `orchestrator.py`,
  `execution/*`, `routing_schema.py` — explicitly frozen for this cut

---

## Stance → legacy label mapping

The projector at `briarwood/projections/legacy_verdict.py` is the
single source of truth for this mapping. The table is duplicated in
`briarwood/projections/README.md` and in the projector module
docstring; keep all three in sync.

| DecisionStance | Legacy label | Notes |
|---|---|---|
| `STRONG_BUY` | `BUY` | clean |
| `BUY_IF_PRICE_IMPROVES` | `LEAN BUY` | clean |
| `EXECUTION_DEPENDENT` | `LEAN BUY` | conditional yes; caveat surfaced in narrative |
| `INTERESTING_BUT_FRAGILE` | `NEUTRAL` | value there, risk dominates |
| `CONDITIONAL` | `NEUTRAL` | trust-gate fallback — `is_trust_gate_fallback = True` |
| `PASS_UNLESS_CHANGES` | `LEAN PASS` | clean |
| `PASS` | `AVOID` | currently unemitted by classifier; mapped anyway |

Three routed stances collapse to `NEUTRAL` at the label tier; the
projector preserves the distinction in `LegacyVerdict.decision_stance`
and `LegacyVerdict.is_trust_gate_fallback` so consumers can render
more faithfully when they want to.

---

## Monday — 2026-04-20

**Goal:** one verdict path. The routed core becomes canonical; the
legacy engine is deprecated in place and will be removed Wednesday
after its four consumer surfaces rewire through the projector.

### Deleted (Monday)

Verdict-stack pipeline modules — wrappers around the legacy decision
engine that were never reached from the routed core:

- `briarwood/pipeline/runner.py`
- `briarwood/pipeline/unified.py`
- `briarwood/pipeline/decision.py`
- `briarwood/pipeline/feedback.py`
- `briarwood/pipeline/scenario_adapter.py`
- `tests/test_pipeline_e2e.py`
- `scripts/demo_eight_layers.py`

Shared pipeline infrastructure that the routed core still uses
(`session.py`, `triage.py`, `feedback_mixin.py`, `enrichment.py`,
`presentation.py`) was kept. `pipeline/representation.py` survives
pending Wednesday review.

### Modified (Monday)

- `briarwood/pipeline/__init__.py` — dropped re-exports of the deleted
  verdict-stack agents; kept shared infra re-exports; added a module
  docstring explaining the scope cut.
- `briarwood/deal_curve.py` — removed the cross-module import of
  private `decision_engine` helpers. The five helpers the curve
  renderer needed (`_valuation_band`, `_carry_band`,
  `_recommendation_from_bands`, `_conviction`, `_evidence_quality`)
  were inlined with a `_deal_curve_` prefix so the module no longer
  depends on `decision_engine`. The curve renderer is the last remaining
  price-point-recomputation caller and is scoped to Dash only.
- `briarwood/decision_engine.py` — added a top-of-file DEPRECATED
  docstring naming the scheduled deletion date (2026-04-22), the four
  surfaces that still import it, and the canonical replacement. The
  module is otherwise unchanged so Dash continues to boot.

### Added (Monday)

- `briarwood/projections/__init__.py` — package exports.
- `briarwood/projections/legacy_verdict.py` — the projector.
  `project_to_legacy(UnifiedIntelligenceOutput) -> LegacyVerdict`.
  Deterministic. No LLM calls, no timestamps, no randomness.
  `LegacyVerdict` mirrors the fields the deleted
  `decision_engine.DecisionOutput` exposed so Wednesday's rewire is a
  field-for-field swap.
- `briarwood/projections/README.md` — conventions for projectors
  (relabel-only, one-way, deterministic, typed, pass-through where
  possible, document ambiguity, tests alongside) and the stance
  mapping table.
- `tests/projections/__init__.py`, `tests/projections/test_legacy_verdict.py` —
  stance-table exhaustiveness, conviction pass-through, reason
  extraction with fallbacks, required-beliefs cap at 3, and a
  determinism smoke test. The three behavioral intents from the
  deleted `tests/test_decision_engine.py`
  (`test_buy_when_value_and_carry_are_constructive`,
  `test_avoid_when_value_and_carry_are_both_weak`,
  `test_low_evidence_caps_conviction`) are ported to the projector
  surface: same intent, expressed on the canonical routed input.

### Explicitly not touched (Monday)

- `briarwood/synthesis/structured.py`
- `briarwood/orchestrator.py`
- `briarwood/execution/*`
- `briarwood/routing_schema.py`
- CMA / comps / caches

### Known limitations to acknowledge in the demo

- **Conviction calibration has shifted.** The projector surfaces the
  routed `UnifiedIntelligenceOutput.confidence` directly (no
  blending, no legacy band-based rescaling). Numbers printed on the
  legacy surfaces are not directly comparable to pre-1.0 conviction
  values. This is intentional — blending two systems' numbers into a
  third hybrid number neither system owns is exactly the pattern the
  F1 audit flagged — but it means the conviction display will read
  differently than it did a week ago.
- **Three routed stances collapse to one legacy label.**
  `INTERESTING_BUT_FRAGILE`, `CONDITIONAL`, and any future NEUTRAL
  flavor all render as `NEUTRAL` on the five-label surfaces. The
  `is_trust_gate_fallback` flag distinguishes the trust-gate NEUTRAL
  from the fragility NEUTRAL; surfaces that do not read the flag will
  lose this nuance until they migrate off the legacy vocabulary.
- **`PASS` is mapped but unemitted.** The routed classifier does not
  currently emit `DecisionStance.PASS`; the mapping to `AVOID` is
  there for correctness and will activate when the classifier
  starts emitting it.
- **`decision_engine.py` is still on disk Monday.** The four consumer
  surfaces still call `build_decision(report)`. They rewire Wednesday
  AM; the module deletes the same day.

---

## Tuesday — 2026-04-21

**Goal:** stop silent degradation and tighten the adapter boundary.
Tuesday's work was corrective, not structural — small fixes layered on
top of Monday's consolidation while the four consumer surfaces waited
for Wednesday's rewire.

Notable commits from the week that land on the Tuesday surface (LLM
provider abstraction, adapter guardrails, composer critic ensemble):

- `2d8fb83 feat(llm): add Anthropic provider abstraction (1.3.4)`
- `243c2e6 feat(llm): wire Anthropic structured output via tool-use (1.3.3 prep)`
- `1516b7b feat(composer): route decision_summary/edge/risk to Anthropic (1.3.5)`
- `08472cc feat(composer): decision_summary critic ensemble, off by default (1.3.3)`
- `535c988 expose critic A/B draft in telemetry` + `8042e21 render critic A/B panel behind a toggle`
- `4fb62bd fix(adapter): reject legacy decision-engine labels on verdict (O.7)`
- `5bf57aa fix(adapter): credit modules cited via grounding anchors (1.5.4)`
- `8393ede fix(llm): force required to mirror properties for OpenAI strict mode`

F3 (stale cache key) also lands on Tuesday's surface:
`briarwood/orchestrator.py::build_cache_key` now includes a
`_CACHE_KEY_VERSION` literal and a normalized fingerprint of structural
property facts (sqft, taxes, purchase_price, ADU flags, etc.) so
edits to the property record invalidate routing / module / synthesis
cache entries cleanly instead of colliding by `property_id` alone.

---

## Wednesday — 2026-04-22

**Goal:** close the three remaining audit P1 surfaces before the demo
(F5 hidden upside, F7 silent degradation, F10 UI fidelity), ship the
Representation Agent, and collapse the router split (F9) plus the
over-tiered structured-model default (F12).

### Added (Wednesday)

- `briarwood/representation/` — registered chart catalog wrapping the
  `_native_*_chart` renderers, plus an LLM-backed agent that selects
  charts off the `UnifiedIntelligenceOutput`. Flags unsupported claims
  instead of fabricating. Deterministic fallback when no LLM client is
  configured. `scripts/representation_demo.py` exercises it against
  synthetic scenarios. (commit `b2d6233`)
- `briarwood/intent_contract.py` (F9) — shared `IntentContract`
  Pydantic model with `answer_type`, `core_questions`,
  `question_focus`, `confidence`. Canonical
  `ANSWER_TYPE_TO_CORE_QUESTIONS` mapping table. Helpers
  `build_contract_from_answer_type` and
  `align_question_focus_with_contract`. Imports only from
  `routing_schema` to avoid a cycle with `agent.router`.
- `tests/test_intent_contract.py` (F9) — schema exhaustiveness,
  chat-router emission, and the subset invariant between the two
  routers on cache-routed inputs (no LLM required).
- F5 contract additions on `UnifiedIntelligenceOutput`:
  `OptionalitySignal` / `HiddenUpsideItem`; Representation Agent emits
  a `HIDDEN_UPSIDE` claim; `value_thesis` SSE event carries the
  optionality signal; `value-thesis-card` renders a `HiddenUpsideBlock`.
  (part of commit `688c592`)

### Modified (Wednesday)

- `briarwood/agent/router.py` (F9) — `RouterDecision` grew an
  `intent_contract: IntentContract | None` field. A post-init hook
  auto-populates it from `answer_type` + `confidence` using
  `object.__setattr__` (frozen dataclass). `classify()` is otherwise
  untouched — no internals rewritten.
- `briarwood/router.py` (F9) — `route_user_input()` accepts an
  optional `intent_contract` kwarg. When supplied, the contract's
  `core_questions` are merged into `parser_output.question_focus` via
  `parser_output.model_copy(update=…)` before `build_routing_decision`
  runs. Analysis tier still owns intent, depth, occupancy, exit
  options, missing-inputs.
- `briarwood/agent/llm.py` (F12) — structured default changed from
  `gpt-5` to `gpt-4o-mini`. `BRIARWOOD_STRUCTURED_MODEL` env override
  preserves the old default for callers that still need it. The tiny
  two-field router classifier schema does not need a flagship model.
- F7 (silent degradation): `briarwood/agent/dispatch.handle_decision`
  replaces a broad `try/except` with explicit `_record_partial`;
  session loader decode failures now surface via
  `session.last_partial_data_warnings`; `api/events.py` emits a
  `partial_data_warning` SSE event before the primary cards; the UI
  renders a subtle reliability banner. (part of commit `688c592`)
- F10 (UI fidelity): `VerdictEvent` gains `trust_summary`,
  `why_this_stance`, `what_changes_my_view`, `contradiction_count`,
  `blocked_thesis_warnings`; `VerdictCard` and `messages.tsx` render
  progressive disclosure plus a verifier-reasoning toggle; the full
  `verifier_report` is preserved on the message object. (part of
  commit `688c592`)
- F5 (hidden upside): `HIDDEN_UPSIDE` added to `CoreQuestion` routing
  hints and to the intent question lists for `RENOVATE_THEN_SELL` and
  `HOUSE_HACK_MULTI_UNIT`; `_optionality_signal` in
  `synthesis/structured.py` reads `renovation_impact`, `arv_model`,
  and `unit_income_offset`.

### Explicitly not touched (Wednesday)

- Monday's projector surface (`briarwood/projections/`) — unchanged.
- Decision-engine module (`briarwood/decision_engine.py`) — still on
  disk; scheduled deletion after the Thursday consumer-surface rewire.
- `briarwood/synthesis/structured.py::build_unified_output` — F5
  extended the payload contract; the builder itself stayed a
  pass-through of those fields.

### Rehearsal bugs logged Wednesday

Pre-existing test-suite failures surfaced during rehearsal (none
caused by Wednesday's work; verified via `git stash` against the
pre-F9 baseline):

- `tests/test_router.py::test_route_user_input_builds_routing_decision`
- 4 failures in `tests/test_orchestrator.py`,
  `tests/test_synthesis*`, and `tests/test_routing_behavior*`
  (same class of baseline drift — assertions pin pre-F3 cache shapes
  or pre-F5 `core_questions` membership).
- `tests/test_intake_agent.py` and `tests/test_intelligence_intake.py`
  fail at collection time — both import `_build_landing_subject` from
  `dash_app/app.py`, which no longer exists. Dash surface is not on
  the demo path; these tests need to either be ported to the routed
  adapter or retired. Logged as 1.1 cleanup, not a release blocker.
- Browse gap: "Where's the hidden upside here?" without an LLM
  classifies as `lookup` at the chat tier (cache miss + fallback).
  The analysis router still picks up `hidden_upside` via rule
  keywords, so the downstream payload is correct — but the chat
  contract itself is empty in the no-LLM path. Acceptable for the
  demo (LLM is on); a cache-regex for "hidden upside" phrasing is
  parked for 1.1.

---

## Thursday — 2026-04-23 (planned)

<placeholder: `AnalysisReport → UnifiedIntelligenceOutput` adapter
lands at `briarwood/adapters/legacy_report.py`. The four consumer
surfaces (`dash_app/quick_decision.py`, `dash_app/view_models.py`,
`reports/sections/thesis_section.py`,
`reports/sections/conclusion_section.py`) rewire to
`project_to_legacy(adapt(report)) -> LegacyVerdict`.
`briarwood/decision_engine.py` deletes.
`pipeline/representation.py` review completes — either migrates
behind the new `briarwood/representation/` package or is deleted.>

---

## Friday retro — 2026-04-24

<placeholder: one paragraph on what shipped vs what slipped, one
paragraph on what the consolidation actually bought (latency,
reasoning quality, maintenance burden), one paragraph on the next
cut's scope.>

---

## 1.1 — remaining from this cut

- **Thursday's rewire.** Consumer-surface swap off
  `decision_engine.build_decision(report)` and onto
  `project_to_legacy(adapt(report))`. Module deletion follows.
- **Baseline-drift test failures.** 5+ tests pinning pre-F3 / pre-F5
  assertions need updating, not the code.
- **Dash intake tests.** `test_intake_agent.py` /
  `test_intelligence_intake.py` import a removed helper; port to the
  routed adapter or retire.
- **Chat-tier "hidden upside" cache miss.** Add an explicit cache
  regex for "where's the hidden upside" / "any upside" phrasings so
  the contract is correct without an LLM round-trip.
- **`pipeline/representation.py`.** Superseded by
  `briarwood/representation/`. Usage audit still pending; the old
  module is untouched so existing import sites keep working.
- **Conviction recalibration.** Monday's projector surfaces routed
  `confidence` directly — numbers read differently than pre-1.0.
  Intentional, but a follow-up re-anchors the scale against a labeled
  sample set before 1.1 ships.
- **`PASS` stance emission.** Classifier does not emit
  `DecisionStance.PASS` yet; the label map to `AVOID` is wired for
  when it does.

---

## Known limitations to acknowledge in the demo

- **The two routers agree on `core_questions` — not on everything.**
  F9 is a contract-level reconciliation: the analysis tier's
  `core_questions` is now guaranteed to be a superset of the chat
  tier's when the contract is threaded through. Intent type, depth,
  occupancy, and exit options are still the analysis router's call;
  the chat tier only pins "what question is the user asking?"
- **Three routed stances collapse to one legacy label** (Monday
  limitation; still true). `INTERESTING_BUT_FRAGILE`, `CONDITIONAL`,
  and any future `NEUTRAL`-flavored stance all render as `NEUTRAL` on
  the five-label surfaces; `is_trust_gate_fallback` distinguishes the
  trust-gate case.
- **Conviction calibration has shifted** (Monday limitation; still
  true). The projector surfaces routed confidence directly; numbers
  are not directly comparable to pre-1.0 conviction values.
- **`decision_engine.py` is still on disk** pending Thursday's
  rewire. It is no longer the canonical verdict, but it boots Dash.
- **`HIDDEN_UPSIDE` without an LLM** falls back to the rules-based
  parser; the chat-tier contract will be empty in that path. The
  analysis tier still emits the correct `core_questions`, but the
  contract-level guarantee only holds end-to-end when the chat
  classifier runs.
- **F7 partial-data banners are best-effort.** Session loader decode
  failures and enrichment skips now surface via
  `session.last_partial_data_warnings`; the UI banner is intentionally
  subtle. Anything below the dispatch boundary (module-internal
  swallows) is still invisible to the banner.
- **Representation Agent falls back deterministically** when no LLM
  client is configured, but the fallback chart set is narrower than
  the LLM-picked one. Demo assumes the LLM path.

---

## Follow-ups parked from this cut

- **Second projector surface.** Reports (thesis / conclusion sections)
  may want their own projection shape, not `LegacyVerdict`. Decide
  Thursday when the rewire exposes their real needs.
- **F9 end-to-end extension.** The contract currently aligns only
  `question_focus`. Depth and occupancy could also be contract-level
  once we have two call sites that want it.
- **F12 audit.** `BRIARWOOD_STRUCTURED_MODEL` is now `gpt-4o-mini` by
  default; revisit after a week of traffic to confirm the classifier
  quality hasn't regressed on edge inputs.
- **Critic A/B ensemble.** Off by default (`1.3.3`); telemetry panel
  wired. Decide after a sample whether to flip the default on.

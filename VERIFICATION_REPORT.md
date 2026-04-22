# Briarwood Verification Pass — Runtime Correctness & Contract Alignment
**Date:** 2026-04-22
**Mode:** Read-only. No source files modified. Runtime probes written to `/tmp/`.
**Scope:** Completes the wiring-audit (`AUDIT_REPORT.md`) with empirical output checks, backend↔frontend contract alignment, and LLM quality spot-checks.
**Fixtures exercised:** `1228-briarwood-road-belmar-nj`, `briarwood-rd-belmar`, `526-west-end-ave`, `1008-14th-ave-belmar-nj-07719`.

---

## Summary

- **F-004 is a stealth correctness bug, not cleanliness.** The scoped and legacy-fallback execution paths produce **incompatibly-shaped `module_results` dicts**, and the structured synthesizer silently reads nulls under the fallback shape. On one priced fixture the same property produced `decision_stance=buy_if_price_improves / confidence=0.77` via scoped, vs `pass_unless_changes / confidence=0.68 / value_position.*=None` via fallback. On a null-`purchase_price` fixture the legacy engine crashes with `TypeError` inside `income_support`. See [NEW-V-001](#new-v-001--scopedlegacy-fallback-produce-divergent-synthesis-inputs) and [appendix](#a-scoped-vs-legacy-fallback-module_results-diff).
- **F-003's field-drop framing is partially wrong.** `optionality_signal` is computed AND rendered by `value-thesis-card.tsx` (prior audit incorrect). `primary_value_source` is always `"unknown"` on every priced fixture — that's a bridge-wiring bug upstream, not a UI drop (prior audit misdiagnosed). `all_in_basis` IS dropped by the UI (prior audit correct). See [DOWNGRADED-F-003](#downgraded-f-003--primary_value_source--optionality_signal-are-not-ui-drops).
- **The stance classifier is not doing much work across priced fixtures.** Three fixtures with 6.0%, 6.1%, and 9.5% basis premium all received identical `buy_if_price_improves`. `band_upper=0.07` (not `0.05`) is the actual classifier threshold and the 9.5% case arguably should lean cautious. See [NEW-V-002](#new-v-002--stance-classifier-collapses-605-premium-range-to-one-label).
- **A grounding-verifier / prompt contract bug strips the recommendation sentence from `decision_summary`.** Numbers embedded in prose-string fields (e.g., `what_changes_my_view: ["seller cuts to 695k"]`) are not registered as grounded, so the LLM is prompted to emit them and the verifier rejects the sentence. Concrete user-visible failure: the lead stance verb disappears. See [NEW-V-003](#new-v-003--decision_summary-verifier-strips-lead-recommendation-and-buy-trigger).
- **Unified intelligence is working selectively.** `optionality_signal` fires correctly on a fixture with an accessory unit. Trust gate fires on `valuation_anchor_divergence`. But `key_value_drivers`, `key_risks`, and `why_this_stance` are empty or one-line across every priced fixture, indicating bridges aren't producing indexed output. See [NEW-V-004](#new-v-004--bridges-produce-no-key_value_drivers-or-key_risks).

---

## Confirmed Issues

### CONFIRMED — F-004 (severity upgraded Critical)
**Prior claim:** Scoped and legacy `AnalysisEngine` fallback may diverge; risk is silent divergence + no caching of the fallback engine.
**Runtime evidence ([Phase 1c](#a-scoped-vs-legacy-fallback-module_results-diff)):**
- Same fixture (`briarwood-rd-belmar`), identical `RoutingDecision` (`buy_decision/snapshot/[valuation,confidence,carry_cost,risk_model]`), both paths ran to completion.
- `module_results["outputs"][<module>].data` had **zero overlapping keys** across all 4 routed modules. Scoped writes flat `{module_name, score, summary, metrics, legacy_payload, section_evidence}`. Fallback writes `{current_value, comparable_sales, hybrid_value}` (valuation), `{cost_valuation, income_support}` (carry_cost), etc. The structured synthesizer reads only the flat `data.metrics` path.
- Resulting `UnifiedIntelligenceOutput`:
  - `decision_stance`: `buy_if_price_improves` vs `pass_unless_changes`
  - `confidence`: 0.77 vs 0.68
  - `value_position.fair_value_base / ask_price / all_in_basis / value_low / value_high / basis_premium_pct`: **all populated vs all None**
  - `trust_summary.field_completeness`: 0.71 vs None
  - `why_this_stance`: `["Current basis sits about 6.1% above Briarwood's fair-value anchor."]` vs `[]`
- On `1228-briarwood-road-belmar-nj` (null purchase_price), the legacy engine raises `TypeError: income_support module payload is not an IncomeAgentOutput` ([briarwood/modules/income_support.py:227-229](briarwood/modules/income_support.py#L227-L229)). Scoped path succeeds.

**Upgrade:** Severity **High → Critical.** This isn't two paths with slightly different caching — it's two paths that produce materially different decisions for the same property. F-004's instrumentation step (logging `execution_mode`) is necessary but insufficient; the shape gap at [briarwood/runner_routed.py:125-206](briarwood/runner_routed.py#L125-L206) must be fixed or the fallback must be deleted.

Driver: `/tmp/scoped_vs_fallback.py`. Dumps: `/tmp/scoped_results.{json,pkl}`, `/tmp/fallback_results.{json,pkl}`.

### CONFIRMED — F-002 (severity retained High)
**Prior claim:** `_assert_valuation_module_comps()` raises `AssertionError` on a single bad row, aborting the SSE stream mid-flight.
**Evidence:** [Phase 3](#test-coverage-gaps) — no regression test exists in [tests/test_pipeline_adapter_contracts.py](tests/test_pipeline_adapter_contracts.py) that exercises a row with `feeds_fair_value: false`. Code path at [api/pipeline_adapter.py:722-748](api/pipeline_adapter.py#L722-L748) still raises.

### CONFIRMED — F-001 (severity retained Critical)
**Prior claim:** `_echo_stream` serves hardcoded mock listings when the router fails, no env gate, no UI banner.
**Evidence:** [Phase 3](#test-coverage-gaps) — no gate exists at [api/main.py:319-320](api/main.py#L319-L320). No test asserts the echo path is off by default. `classify_turn` silently degrades to `LOOKUP` (not `None`) when no API key is set, so the current fallback condition is also too narrow — a misconfigured provider routes to LOOKUP instead, which has its own UX issues but doesn't trigger the echo path. Either way, the echo code path is still a demo-mode foot-gun.

### CONFIRMED — F-003 (partial — `all_in_basis` only)
**Prior claim:** Verdict card drops `primary_value_source`, `all_in_basis`, `optionality_signal`.
- `all_in_basis`: **confirmed dropped.** Computed at [briarwood/synthesis/structured.py:252-265](briarwood/synthesis/structured.py#L252-L265), projected to verdict event at [api/pipeline_adapter.py:645](api/pipeline_adapter.py#L645), but **not rendered** by [web/src/components/chat/verdict-card.tsx](web/src/components/chat/verdict-card.tsx) or any other card. Phase 1b confirms runtime value is correct (`824200 = 674200 + 150000` reno overlay).
- The other two fields turn out to be different issues — see [Downgraded](#downgraded-f-003--primary_value_source--optionality_signal-are-not-ui-drops).

### CONFIRMED — F-015 (partial)
**Prior claim:** ~13 `briarwood/modules/` files may be unreferenced.
**Evidence:** Phase 1c shows [briarwood/runner_common.py](briarwood/runner_common.py) `build_engine()` wires 19 modules that the scoped registry does not wire, but the fallback path itself is effectively dead on null-price fixtures and produces incoherent output otherwise. If F-004 is resolved by deleting the fallback, ~10 of the 19 modules in `build_engine()` become unambiguously dead (`HybridValueModule`, `BullBaseBearModule`, `RenovationScenarioModule`, `TeardownScenarioModule`, `RentalEaseModule`, `LiquiditySignalModule`, `MarketMomentumSignalModule`, `LocationIntelligenceModule`, `ValueDriversModule`).

---

## Downgraded Issues

### DOWNGRADED — F-003 — `primary_value_source` & `optionality_signal` are not UI drops

**Prior claim:** Both fields are "computed but silently dropped by the UI".
**What Phase 1b + 2a + 2c actually show:**

- `optionality_signal`:
  - **Computed:** YES, conditionally. On `526-west-end-ave` (detached cottage + ADU), the synthesizer emitted a `HiddenUpsideItem` with `label="Accessory unit income", annual_value=$182,000, confidence=0.7`. On three plain-SFR fixtures, it correctly stayed empty.
  - **On wire:** YES, via the `value_thesis` event ([api/events.py:179-184](api/events.py#L179-L184), schemaless pass-through from `session.last_value_thesis_view`).
  - **Rendered:** YES, by [web/src/components/chat/value-thesis-card.tsx:119-122](web/src/components/chat/value-thesis-card.tsx#L119-L122) with a gate (`thesis.optionality_signal && items.length > 0`).
  - **Prior claim:** Incorrect for this field. The signal is present and rendered when data justifies it.

- `primary_value_source`:
  - **Computed:** YES, but the bridge at [briarwood/interactions/primary_value_source.py:29-101](briarwood/interactions/primary_value_source.py#L29-L101) returns `"unknown"` on ALL 4 fixtures tested, including `526-west-end-ave` whose own rationale text says "Briarwood used a hybrid valuation." The classifier's signals (strategy → valuation mispricing → carry offset → scenario) aren't firing, not because the path is gated, but because the upstream signals the bridge needs aren't in the module_results shape it expects.
  - **On wire:** YES, in the verdict event payload ([api/pipeline_adapter.py:643](api/pipeline_adapter.py#L643)) and in the value_thesis event.
  - **Rendered:** YES, by [web/src/components/chat/value-thesis-card.tsx:32-36](web/src/components/chat/value-thesis-card.tsx#L32-L36) — the card renders it if the value is not `"unknown"`. NOT rendered by `verdict-card.tsx`.
  - **Real issue:** The bridge always returns "unknown" → the frontend gate `!== "unknown"` always skips rendering → it LOOKS like the field is dropped but the upstream classification never fires. See [NEW-V-005](#new-v-005--primary_value_source-bridge-always-returns-unknown).
  - **Prior claim:** Misdiagnosed. Fix location is the bridge, not the UI.

### DOWNGRADED — F-005 — `briarwood/dash_app/` dead directory
Not runtime-relevant (no one imports from `__pycache__` in a normal run). Still worth deleting; severity dropped to Low as a cleanliness item.

---

## New Issues

### NEW-V-001 — Scoped/legacy fallback produce divergent synthesis inputs
- **Severity:** Critical
- **Category:** Unified Layer / Correctness
- **Location:**
  - Branch point: [briarwood/orchestrator.py:509-568](briarwood/orchestrator.py#L509-L568)
  - Legacy adapter (root of shape mismatch): [briarwood/runner_routed.py:125-206](briarwood/runner_routed.py#L125-L206) — `_build_module_payload` buries each legacy module's `{summary, metrics, score}` under a per-module sub-key
  - Scoped executor (flat-shape reference): [briarwood/execution/executor.py:289-364](briarwood/execution/executor.py#L289-L364)
  - Synthesizer expects flat shape: [briarwood/synthesis/structured.py:34-117](briarwood/synthesis/structured.py#L34-L117)
  - Legacy engine crash on null price: [briarwood/modules/income_support.py:227-229](briarwood/modules/income_support.py#L227-L229)
- **Evidence:** [Appendix A](#a-scoped-vs-legacy-fallback-module_results-diff). Per-module key overlap between scoped and fallback `data` dicts: **zero.** Resulting `UnifiedIntelligenceOutput.value_position.*` fields are all `None` under fallback; `decision_stance` flips from `buy_if_price_improves` to `pass_unless_changes`; `confidence` drops from 0.77 → 0.68.
- **Impact:** Same property can produce materially different decisions depending on whether scoped execution covers the routed module set. `build_cache_key` does not currently include `execution_mode`, so a scoped result and a fallback result for the same property+parser collide in `_SYNTHESIS_OUTPUT_CACHE` — whichever runs first wins until TTL expiry. Users receive a recommendation computed from a null-valued value_position but phrased as if it were grounded.
- **Same-day fix options:**
  1. Pick one path, delete the other. If scoped covers every routed module set, delete `build_engine()` and the 9–10 legacy modules. Safest.
  2. Add `execution_mode` to `build_cache_key` ([briarwood/orchestrator.py:171-202](briarwood/orchestrator.py#L171-L202)) — 20 min. This prevents cross-mode cache collisions but does NOT fix the underlying shape gap.
  3. Rewrite `_build_module_payload` to emit the same flat shape the scoped executor produces — 2–4 hr, risky.
  - Pair with: add a regression test that runs one fixture both ways and asserts `UnifiedIntelligenceOutput.model_dump()` is identical.

### NEW-V-002 — Stance classifier collapses 6.0–9.5% premium range to one label
- **Severity:** High
- **Category:** Unified Layer / Synthesis
- **Location:** [briarwood/synthesis/structured.py:123-227](briarwood/synthesis/structured.py#L123-L227)
- **Evidence:** Phase 1b ran 3 priced fixtures with `basis_premium_pct = 0.0604, 0.0608, 0.0951`. All three returned `decision_stance = buy_if_price_improves`. The classifier's `band_upper` default is `0.07`, and `pass_unless_changes` only fires when `price_gap > +0.05` — i.e. the premium must exceed `0.12` to downgrade. 9.5% with a trust-flag firing arguably should lean more cautious.
- **Impact:** The stance is the single most user-consumed artifact. A classifier that labels a 9.5%-premium deal the same way it labels a 6%-premium deal is not differentiating in a user-meaningful way.
- **Same-day fix:** Tighten `band_upper` to `0.05` (matching the audit memo's assumed rubric) or introduce a `caution_if_premium_above=0.08` intermediate threshold. Effort: 30 min + re-run fixtures.

### NEW-V-003 — `decision_summary` verifier strips lead recommendation and buy-trigger
- **Severity:** High
- **Category:** LLM / Pipeline contract
- **Location:**
  - Prompt: [api/prompts/decision_summary.md](api/prompts/decision_summary.md)
  - Verifier: [api/guardrails.py:168-207](api/guardrails.py#L168-L207) (`_flatten_input_values`), [api/guardrails.py:315-359](api/guardrails.py#L315-L359) (`verify_sentence`)
  - Call site: [briarwood/agent/dispatch.py:1941-1991](briarwood/agent/dispatch.py#L1941-L1991)
- **Evidence:** Phase 4 executed the prompt against a real input payload. The prompt instructs the LLM to emit a stance-verb lead sentence and to repeat `what_changes_my_view` triggers with a `[[grounding_marker]]` tag. The LLM did. The verifier then rejected both the lead (`$750,000` — address/price extraction ambiguity) and the trigger (`$695,000` — embedded in a string field, not a numeric field, so not in the grounded-number set). Resulting prose: two generic premium sentences, no recommendation verb at all.
- **Impact:** The decision-summary is the prose the user reads alongside the verdict card. A user who receives this output sees `"The asking price is about 10.3% above the current fair value of $680,000. Additionally, the limited number of comparable properties provides weak support for this asking price."` — no buy/wait/pass verb, no trigger. This is the stealth version of F-002: the guardrails do the right thing in pieces but the pieces disagree on what counts as grounded.
- **Same-day fix:** Extend `_flatten_input_values` to also extract numeric tokens from string values inside dict/list fields. Effort: 30 min + regression test. Longer-term: emit numeric fields as explicit numbers in the payload, not as prose strings.

### NEW-V-004 — Bridges produce no `key_value_drivers` or `key_risks`
- **Severity:** High
- **Category:** Unified Layer / Interactions
- **Location:** [briarwood/interactions/](briarwood/interactions/) (bridges), surfaced through [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py)
- **Evidence:** Phase 1b: across all 4 fixtures, `key_value_drivers = []` and `key_risks = []`. `why_this_stance` is degenerate — one line on priced fixtures (just the premium), empty on the null-price fixture. Only `valuation_anchor_divergence` fired as a trust flag (once, on `526-west-end-ave`).
- **Impact:** The verdict card and decision summary are stripped of the "why" content that motivates the stance. User experience degrades to "basis is 6% above fair value" for every property.
- **Same-day fix:** Not same-day — this is a bridge-indexing bug. Add a runtime assertion in the synthesizer that when `selected_modules` contains at least one structural module, the interaction trace has at least one entry, and log when it doesn't. Then triage which bridges aren't wiring into the trace.

### NEW-V-005 — `primary_value_source` bridge always returns "unknown"
- **Severity:** Medium
- **Category:** Unified Layer
- **Location:** [briarwood/interactions/primary_value_source.py:29-101](briarwood/interactions/primary_value_source.py#L29-L101)
- **Evidence:** Phase 1b: all 4 fixtures returned `"unknown"`, including one whose rationale text explicitly names hybrid valuation. The bridge checks strategy → valuation mispricing → carry offset → scenario signals; when none fire it falls through to `"unknown"`. The signals likely live at keys the bridge reads from the scoped `module_results` shape, but the shape changed between eras and the reads no longer match.
- **Impact:** The field is silently unused by every card that gates on `!== "unknown"`. The explicit-value stories that the data model supports ("anchored on comps" vs "anchored on income") never surface.
- **Same-day fix:** Add a log statement in the bridge showing which lookup failed, run against 3 fixtures, fix the key path. Effort: 45 min.

### NEW-V-006 — Router misroutes "rental outlook for X" to PROJECTION
- **Severity:** Medium
- **Category:** LLM / Router
- **Location:** [briarwood/agent/router.py](briarwood/agent/router.py) `_LLM_SYSTEM` around line 138-177
- **Evidence:** Phase 1a: `"hows the rental outlook for belmar"` classified as `PROJECTION` (confidence 0.60). The system prompt's PROJECTION clause mentions "rent ramp" which snags rental-market questions away from town RESEARCH. This is a real intent misroute, not an adversarial edge case.
- **Impact:** User asking about a town-level rental market gets the property-level projection cascade instead of town signals. Answer quality degrades in a specific, silently-wrong way.
- **Same-day fix:** Edit the PROJECTION clause to scope it to single-property rental projections (requires an address token). Effort: 15 min + regression probe.

### NEW-V-007 — Router CHITCHAT→BROWSE guard blocks OOS rejection
- **Severity:** Medium
- **Category:** LLM / Router
- **Location:** [briarwood/agent/router.py:234-236](briarwood/agent/router.py#L234-L236)
- **Evidence:** Phase 1a: `"What's the weather in Tokyo?"` and `"Write me a poem about real estate"` both classified as BROWSE after the LLM produced CHITCHAT. The guard is intentional (avoids real-estate questions slipping to chitchat) but has no OOS bucket.
- **Impact:** OOS user inputs run through the full browse flow, which can produce confident confabulation. Especially risky on a real-estate app where the UI expects property context.
- **Same-day fix:** Add a `REFUSE` / `OUT_OF_SCOPE` enum value with a specific system-prompt clause, short-circuit in the chat endpoint with a scripted reply. Effort: 1 hr.

### NEW-V-008 — `evidence_excerpt` never verified against source document
- **Severity:** Medium
- **Category:** LLM / Extraction
- **Location:** [briarwood/local_intelligence/prompts.py:6-25](briarwood/local_intelligence/prompts.py), [briarwood/local_intelligence/models.py](briarwood/local_intelligence/models.py) (`TownSignalDraft`)
- **Evidence:** Phase 4 static read: the prompt asks for grounded excerpts but nothing downstream verifies the `evidence_excerpt` string appears in `document.cleaned_text`. `Field(min_length=1)` only guarantees non-empty.
- **Impact:** On a weaker model or a rich source document, the extractor could paraphrase or fabricate a quote that reads plausible but isn't in the document. Compared to the `decision_summary` verifier (which enforces numeric grounding), this path is unguarded on text content.
- **Same-day fix:** Add a post-parse check: `if excerpt not in normalized_cleaned_text: drop or flag`. Effort: 45 min.

### NEW-V-009 — Display drift between top-level `confidence` and `trust_summary.band`
- **Severity:** Low
- **Category:** Synthesis
- **Location:** [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py) (confidence rounding)
- **Evidence:** Phase 1b on `1008-14th-ave-belmar-nj-07719`: top-level `confidence=0.75` but `trust_summary.confidence=0.7485` and `band="Moderate confidence"` (the High threshold is `>= 0.75`). The top-level value is rounded while the band is computed on the unrounded value.
- **Impact:** User sees `confidence: 0.75` and `band: Moderate confidence` side-by-side with no explanation of the inconsistency.
- **Same-day fix:** Compute the band from the same rounded value that's displayed. Effort: 10 min.

### NEW-V-010 — `echo` fallback condition is too narrow; no-key scenario routes elsewhere
- **Severity:** Low (supersedes part of F-001)
- **Category:** Pipeline
- **Location:** [api/main.py:293-320](api/main.py#L293-L320) and `classify_turn` → [briarwood/agent/router.py:default_client](briarwood/agent/router.py)
- **Evidence:** Phase 1a: `classify_turn` does NOT return `None` when `OPENAI_API_KEY` is missing. It returns `RouterDecision(answer_type=LOOKUP, confidence=0.3, reason="default fallback")`. So the `_echo_stream` fallback guarded by `if decision is None` is rarely hit in practice; instead the whole app silently becomes a lookup-only bot.
- **Impact:** The mock-listings risk from F-001 is narrower than described (router exceptions only, not missing keys). But the missing-key case has its own UX failure: every query returns lookup prose even for decision/search intents.
- **Same-day fix:** When `default_client()` returns `None`, `classify_turn` should return `None` (or a distinct `UNAVAILABLE` sentinel), and the caller should emit an explicit "LLM unavailable" error event instead of silently running LOOKUP. Effort: 30 min.

---

## Contract Alignment Table

All 28 backend SSE events have matching TypeScript types in [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts). No event is emitted without a type; no type has no emitter. The per-event discrepancies that actually matter:

| Event | Field | Backend source | Frontend type | Issue |
|---|---|---|---|---|
| `verdict` | `primary_value_source` | [api/pipeline_adapter.py:643](api/pipeline_adapter.py#L643) emits | [events.ts:124-148](web/src/lib/chat/events.ts#L124-L148) declares | Not read by `verdict-card.tsx`. Rendered by `value-thesis-card.tsx` (via a different event). Value is always `"unknown"` due to [NEW-V-005](#new-v-005--primary_value_source-bridge-always-returns-unknown). |
| `verdict` | `all_in_basis` | [api/pipeline_adapter.py:645](api/pipeline_adapter.py#L645) emits | `events.ts` declares | Not read by ANY card. True silent drop. |
| `value_thesis` | `optionality_signal` | [briarwood/synthesis/structured.py:87,116](briarwood/synthesis/structured.py#L87) emits when populated; [api/pipeline_adapter.py:852,883](api/pipeline_adapter.py#L852) projects | `events.ts:289-314` declares `OptionalitySignal` | Rendered correctly at [value-thesis-card.tsx:119-122](web/src/components/chat/value-thesis-card.tsx#L119-L122). No discrepancy. |
| `verdict` | (all unknown-field drift) | `_DecisionView` uses `ConfigDict(extra="ignore")` at [api/pipeline_adapter.py:584](api/pipeline_adapter.py#L584) | — | No logging of dropped keys on the write side — echoes F-014. |
| 7 pass-through events (`town_summary`, `comps_preview`, `risk_profile`, `value_thesis`, `strategy_path`, `rent_outlook`, `research_update`) | all fields | [api/events.py:156-233](api/events.py#L156-L233) factories accept `dict[str, Any]` | TS types are specific | Backend can emit fields the TS type doesn't declare (dropped silently) or omit fields the TS type declares as required. No schema enforcement on the write side. |
| `scenario_table` | `spread_unit` | hardcoded `"dollars"` literal at [api/events.py:139](api/events.py#L139) | `?: "dollars"` | Consistent but brittle — if `spread` becomes a percent, the literal won't update. |
| `verifier_report` | all fields | [api/events.py:265-270](api/events.py#L265-L270) emits | [events.ts:462-472](web/src/lib/chat/events.ts#L462-L472) | Stored in dev tooling only ([use-chat.ts](web/src/lib/chat/use-chat.ts)); no user surface. Advisory by design. |
| `tool_call` / `tool_result` | — | [api/events.py:47-52](api/events.py#L47-L52) | Typed | Phase 3.5 stubs; no renderer. Low risk today. |

**Schema-enforcement summary:** Only the `verdict` event has Pydantic validation on the write side ([api/pipeline_adapter.py:570-620](api/pipeline_adapter.py#L570-L620) `_DecisionView`). All 7 schemaless pass-throughs trust dispatch to produce a valid shape, with no runtime guard. This is the root of F-014 and a standing drift risk for UI changes.

---

## Test Coverage Gaps

| Critical path | Status | Location / evidence | Risk |
|---|---|---|---|
| Router empty/malformed input → graceful `RoutingDecision` or clean error | **Covered** | [tests/agent/test_router.py:170-176](tests/agent/test_router.py#L170-L176) (`test_empty_input_is_chitchat`, `test_no_llm_non_cache_falls_back_to_lookup`) | Low |
| Valuation payload row with `feeds_fair_value: false` → pipeline continues | **Missing** | Searched [tests/test_pipeline_adapter_contracts.py](tests/test_pipeline_adapter_contracts.py), [tests/agent/test_dispatch.py](tests/agent/test_dispatch.py) | Medium — F-002 regression path |
| Scoped execution unavailable → legacy fallback produces equivalent `UnifiedIntelligenceOutput` | **Missing** | [tests/test_execution_v2.py](tests/test_execution_v2.py) covers scoped only; [tests/test_runner_routed.py](tests/test_runner_routed.py) covers the synthesizer wiring but not path equivalence | **High** — confirmed divergence ([NEW-V-001](#new-v-001--scopedlegacy-fallback-produce-divergent-synthesis-inputs)) |
| LLM provider returns malformed JSON → `complete_structured()` degrades safely | **Partial** | Anthropic covered at [tests/agent/test_llm.py:365-378](tests/agent/test_llm.py#L365-L378) (`test_complete_structured_returns_none_on_schema_failure`); OpenAI side partial at [tests/agent/test_llm.py:166-190](tests/agent/test_llm.py#L166-L190) | Medium |
| Anthropic init fails → fallback to OpenAI (F-007 contract) | **Covered** | [tests/agent/test_llm.py:42-65](tests/agent/test_llm.py#L42-L65) | Low |
| `_echo_stream` gated by demo flag → off by default (F-001 regression) | **Missing** | No gate exists; no test asserts the echo path is off in prod | Medium — but partially displaced by [NEW-V-010](#new-v-010--echo-fallback-condition-is-too-narrow-no-key-scenario-routes-elsewhere) |
| Scoped → legacy executor shape equivalence | **Missing** | Neither `test_execution_v2.py` nor `test_runner_routed.py` diffs `module_results["outputs"][m].data` keys | **High** — F-004 / NEW-V-001 |
| `primary_value_source` bridge fires on a fixture that ran hybrid valuation | **Missing** | No test exercises the bridge with realistic scoped module_results | Medium — NEW-V-005 |
| `decision_summary` verifier allows strings-with-numbers as grounded | **Missing** | [tests/agent/test_guardrails.py](tests/agent/test_guardrails.py) covers numeric fields only | High — NEW-V-003 |
| `evidence_excerpt` appears in source document | **Missing** | No test in [tests/test_local_intelligence.py](tests/test_local_intelligence.py) asserts excerpts are substring matches | Medium — NEW-V-008 |

Total: 8 critical-path gaps, 2 high-risk (executor equivalence + verifier-string-numbers).

---

## Runtime Evidence Appendix

### A. Scoped vs legacy-fallback module_results diff

**Fixture:** `data/saved_properties/briarwood-rd-belmar/inputs.json` (purchase_price=674200).
**Routing (identical on both paths):** `intent_type=buy_decision, analysis_depth=snapshot, selected_modules=[valuation, confidence, carry_cost, risk_model]`.

**Top-level module_results keys (both paths):** `["carry_cost", "confidence", "risk_model", "valuation"]` — identical module coverage.

**Per-module `data` payload shape divergence:**

| Module | Scoped `data.*` keys | Fallback `data.*` keys | Overlap |
|---|---|---|---|
| valuation | `module_name, score, summary, metrics, legacy_payload, section_evidence, macro_nudge` | `current_value, comparable_sales, hybrid_value` | **zero** |
| carry_cost | `module_name, score, summary, metrics, legacy_payload, section_evidence` | `cost_valuation, income_support` | **zero** |
| risk_model | `module_name, score, summary, metrics, legacy_payload, section_evidence, macro_nudge, valuation_bridge, legal_confidence_signal` | `liquidity_signal, market_momentum_signal, risk_constraints` | **zero** |
| confidence | `combined_confidence, data_quality_confidence, comp_quality, model_agreement, field_completeness, estimated_reliance, metrics, ...` (16 keys) | `comparable_sales, current_value, property_data_quality` (3 keys) | **zero** |

**Module confidence scores diverge on the same fixture:**

| Module | Scoped | Fallback |
|---|---|---|
| valuation | 0.73 | 0.44 |
| carry_cost | 0.95 | 0.85 |
| risk_model | 0.79 | 0.79 |
| confidence | 0.59 | 0.64 |

**UnifiedIntelligenceOutput diff (scoped vs fallback):**

| Field | Scoped | Fallback |
|---|---|---|
| `decision_stance` | `buy_if_price_improves` | `pass_unless_changes` |
| `confidence` | 0.77 | 0.68 |
| `recommendation` | "Buy if price improves — fundamentals support engagement…" | "Mixed — no single factor dominates…" |
| `best_path` | "Make an offer inside the risk-adjusted band rather than at ask." | "Identify which trust_flags or conflicts most change the picture and resolve those first." |
| `value_position.fair_value_base` | 774093.57 | None |
| `value_position.ask_price` | 674200 | None |
| `value_position.all_in_basis` | 824200 | None |
| `value_position.basis_premium_pct` | 0.0608 | None |
| `value_position.value_low / value_high` | 686976 / 861210 | None / None |
| `trust_summary.confidence / band` | 0.766 / "High confidence" | 0.68 / "Moderate confidence" |
| `trust_summary.field_completeness / estimated_reliance` | 0.71 / 0.33 | None / None |
| `why_this_stance` | `["Current basis sits about 6.1% above Briarwood's fair-value anchor."]` | `[]` |
| `what_changes_my_view` | quantified price-improvement trigger | generic basis-lock |
| `primary_value_source` | "unknown" | "unknown" |
| `optionality_signal.items` | `[]` | `[]` |
| `contradiction_count / blocked_thesis_warnings` | 0 / `[]` | 0 / `[]` |

**Fixture `1228-briarwood-road-belmar-nj` (null purchase_price):**
Scoped: succeeded, `decision_stance=pass_unless_changes, confidence=0.47, value_position.*=None`.
Fallback: **crashed** — `TypeError: income_support module payload is not an IncomeAgentOutput` at [briarwood/modules/income_support.py:227-229](briarwood/modules/income_support.py#L227-L229).

Driver: `/tmp/scoped_vs_fallback.py`. Raw dumps: `/tmp/scoped_results.{json,pkl}`, `/tmp/fallback_results.{json,pkl}`.

### B. Router classification probe

API mode: OPENAI_API_KEY loaded; chat-tier runs `gpt-4o-mini`. Analysis-tier called without `llm_parser` (rules-only) — this matches the chat path's current wiring.

| Input (≤60 chars) | chat.answer_type | conf | analysis.intent_type/depth | Reasonable? | Latency |
|---|---|---|---|---|---|
| "Should I buy 123 Main St, Belmar NJ?" | decision | 0.60 | buy_decision / snapshot | yes | 2539 ms |
| "What's 1228 Briarwood Road worth?" | **lookup** | 0.60 | buy_decision / snapshot | partial — valuation question bucketed as lookup | 3685 ms |
| "Find me 3BR houses in Asbury Park under $900k" | search | 0.60 | buy_decision / snapshot | yes | 2048 ms |
| "Tell me about the Belmar market" | research | 0.60 | buy_decision / snapshot | yes | 1248 ms |
| "How's the local real estate market in Asbury Park?" | research | 0.60 | buy_decision / snapshot | yes | 2542 ms |
| "Compare 1228 Briarwood Road and 526 West End Ave" | comparison | 0.90 | buy_decision / snapshot | yes — cache hit | 0 ms |
| "What about 123 Main?" | browse | 0.60 | buy_decision / snapshot | yes | 1430 ms |
| "thoughts on this one?" | browse | 0.60 | buy_decision / snapshot | yes | 1542 ms |
| "What's the weather in Tokyo?" | **browse** | 0.60 | buy_decision / snapshot | **no — OOS not rejected** | 1324 ms |
| "Write me a poem about real estate" | **browse** | 0.60 | buy_decision / snapshot | **no — OOS not rejected** | 1435 ms |
| "" (empty) | chitchat | 1.00 | — (short-circuit) | yes | 0 ms |
| "🏠" | browse | 0.60 | buy_decision / snapshot | partial | 1530 ms |
| "house "×900 (5400 chars) | browse | 0.60 | buy_decision / snapshot | partial — no crash | 1945 ms |

Analysis-tier rules-based default: every non-empty, non-cached input collapses to `buy_decision / snapshot / [valuation, confidence, carry_cost, risk_model]`. This is the default when no LLM parser is wired — and that is how the chat path calls it today.

Driver: `/tmp/router_probes.py`.

### C. Synthesis coherence — summary table

| Fixture | basis_premium_pct | stance | confidence / band | primary_value_source | optionality items | why_this_stance |
|---|---|---|---|---|---|---|
| briarwood-rd-belmar | 0.0608 | buy_if_price_improves | 0.77 / High | unknown | 0 | 1 line |
| 526-west-end-ave | 0.0951 | buy_if_price_improves | 0.67 / Moderate | **unknown** (despite hybrid rationale in text) | 1 (accessory unit) | 2 lines |
| 1008-14th-ave-belmar | 0.0604 | buy_if_price_improves | 0.75 / **Moderate** | unknown | 0 | 1 line |
| 1228-briarwood-road | — (null price) | pass_unless_changes | 0.47 / Low | unknown | 0 | **0 lines** |

Driver: `/tmp/audit_synthesis.py`. Raw dumps: `/tmp/audit_synthesis_results.json`.

### D. LLM-quality executed sample — `decision_summary`

Input fields included `what_changes_my_view: ["seller cuts to 695k"]`. LLM draft included the sentence `"My stance would change if the seller reduces the price to $695,000 [[what_changes_my_view]]."`. Verifier flagged the sentence because `695000` is not in the grounded-number set ([api/guardrails.py:168-207](api/guardrails.py#L168-L207)). The lead sentence (`"I recommend waiting on the purchase of 1228 Briarwood Rd, which is listed at $750,000 [[DecisionSynthesizer]]."`) was also stripped — address-grounding fallback missed because the address number and street suffix weren't in the extracted token context.

Final verifier-approved output delivered to the user:
> The asking price is about 10.3% above the current fair value of $680,000. Additionally, the limited number of comparable properties provides weak support for this asking price.

Two sentences, no stance verb, no trigger.

---

## Recommendations — sequenced

1. **Same-day (~2 hr):** Add `execution_mode` to `build_cache_key` (guards against cross-mode cache collisions) + add an assertion logger in the synthesizer when `module_results` has zero flat-`metrics` paths (early detection of NEW-V-001).
2. **Same-day (~1 hr):** Fix the `decision_summary` verifier to also extract numeric tokens from string values in `_flatten_input_values` (NEW-V-003). Add regression test.
3. **Same-day (~45 min):** Instrument the `primary_value_source` bridge with a log showing which lookup failed (NEW-V-005).
4. **Same-day (~30 min):** Tighten stance-classifier `band_upper` from `0.07` → `0.05` (NEW-V-002) and re-run fixtures.
5. **This week:** Pick one execution path. If scoped covers the full routed module set, delete `build_engine()` and the 9–10 legacy-only modules. Otherwise, rewrite `_build_module_payload` to emit the flat shape. Either way, add the scoped↔fallback equivalence regression test (NEW-V-001, F-015 partial closure).
6. **This week:** Triage the bridge-indexing gap that leaves `key_value_drivers` / `key_risks` empty on every priced fixture (NEW-V-004).
7. **This week:** Add `REFUSE` / `OUT_OF_SCOPE` router enum + scripted reply (NEW-V-007). Add `evidence_excerpt` substring check (NEW-V-008). Fix rental-outlook misroute (NEW-V-006).

---

*End of verification report.*

---

## Follow-up: NEW-V-005 signal trace

**Date:** 2026-04-22
**Scope:** Empirical log trace of `briarwood/interactions/primary_value_source.py` after the NEW-V-005 instrumentation landed ([commit 56e0d53](https://example.invalid)).

**Harness:** `/tmp/trace_primary_value_source.py` loaded each fixture's `data/saved_properties/<id>/inputs.json`, ran the four scoped modules the bridge depends on (`valuation`, `risk_model`, `carry_cost`, `strategy_classifier`), and invoked `run_all_bridges` with a `DEBUG`-level handler attached to `briarwood.interactions.primary_value_source`.

**Result:** all four fixtures now classify — the `"unknown"` INFO branch never fired. That is a meaningful finding: `primary_value_source=unknown` in production is **not** a deterministic signal failure — the bridge's strategy-classifier prior alone is enough to classify every priced fixture in the saved-property corpus. The original verification-report observation ("`primary_value_source` is always `"unknown"` on every priced fixture") reflects a pre-bridge-invocation drop, **not** a bridge-logic gap.

| Fixture | strategy_check | valuation_mispricing | carry_offset | scenario | classified as |
| --- | --- | --- | --- | --- | --- |
| `1228-briarwood-road-belmar-nj` | ✔ `owner_occ_sfh` | ✘ `None` | ✔ ratio=9.41 | ✘ | `current_value` |
| `briarwood-rd-belmar` | ✔ `value_add_sfh` | ✘ 0.132 | ✘ ratio=0.584 | ✘ | `repositioning` |
| `526-west-end-ave` | ✔ `owner_occ_sfh` | ✘ -0.08 | ✘ ratio=0.422 | ✘ | `current_value` |
| `1008-14th-ave-belmar-nj-07719` | ✔ `owner_occ_sfh` | ✘ -0.0604 | ✘ ratio=0.527 | ✘ | `current_value` |

**Implication for NEW-V-005 triage.** If production verdicts still ship with `primary_value_source=unknown`, the failure is upstream of the bridge — likely the bridge isn't being registered/run in the scoped pipeline, or the module outputs it reads (`strategy_classifier.data.strategy`) aren't being populated in the legacy-fallback shape (see NEW-V-001 for the shape divergence between scoped and fallback `module_results`). The new INFO log at the `"unknown"` return path will flag this the next time a fixture falls through without signal.

Raw log output: `/tmp/fix4_trace_output.txt`.

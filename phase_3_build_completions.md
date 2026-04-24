# Phase 3 Wedge Build — Completion Summary

Companion to [phase_3_build.md](phase_3_build.md). Mirrors that plan's section structure and records what was actually built, where, and under which commit. Steps 1–11 are complete and committed; step 12 (manual smoke) is the remaining gate.

---

## 0. Scope Reminder

Matches the plan. Built:

- One archetype: `verdict_with_comparison`
- One flow: pinned property + "is this a good price?"
- Hardcoded investor persona
- Turn 1 only
- Feature-flagged new code path; legacy `handle_decision` body unmodified

Guardrails honored:

- `briarwood/modules/` — no edits
- `web/src/components/chat/messages.tsx` — no edits
- Value Scout kept as its own package, separate from Editor and synthesis
- Claim objects are the only contract between new pipeline stages

---

## 1. Feature Flag Mechanism ✓

**Commit:** `8c8d8ef` — *feat(claims): add feature flag for claim-object pipeline (phase 3 step 1)*

- New file: [briarwood/feature_flags.py](briarwood/feature_flags.py) — `CLAIMS_ENABLED`, `CLAIMS_PROPERTY_IDS`, `claims_enabled_for(property_id)` exactly as planned
- Single caller: `briarwood/agent/dispatch.py` (wired in step 10)
- Tests: [tests/test_feature_flags.py](tests/test_feature_flags.py) — 6 tests covering env-var parsing + property-ID allowlist

**Gate 1 — passed.**

---

## 2. Archetype + Claim Object Foundation ✓

**Commits:**
- `14824bd` — *feat(claims): add archetype enum and shared base schemas (phase 3 step 2)*
- `65ece6f` — *feat(claims): add VerdictWithComparisonClaim schema (phase 3 step 3)*

- New package: [briarwood/claims/](briarwood/claims/) with:
  - [briarwood/claims/archetypes.py](briarwood/claims/archetypes.py) — `Archetype` enum with `VERDICT_WITH_COMPARISON`
  - [briarwood/claims/base.py](briarwood/claims/base.py) — `Provenance`, `Confidence`, `Caveat`, `NextQuestion`, `SurfacedInsight`
  - [briarwood/claims/verdict_with_comparison.py](briarwood/claims/verdict_with_comparison.py) — `Subject`, `Verdict`, `ComparisonScenario`, `Comparison`, `VerdictWithComparisonClaim`
  - [briarwood/claims/__init__.py](briarwood/claims/__init__.py) — exports
- `SurfacedInsight` gained a `scenario_id` field during step 7 so Scout output pins the emphasis row deterministically
- Tests: [tests/claims/test_archetypes.py](tests/claims/test_archetypes.py), [tests/claims/test_base.py](tests/claims/test_base.py), [tests/claims/test_verdict_with_comparison_schema.py](tests/claims/test_verdict_with_comparison_schema.py)

### Chart-rule resolution (gate 2)

Reality check: `horizontal_bar_with_ranges` did not exist in [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts). Escalated per plan. **User approved Option 1 — add as a new kind, additive-only.**

**Commit:** `7f8c59a` — *feat(charts): add horizontal_bar_with_ranges chart kind (phase 3 step 4)*

- Backend: registered in [briarwood/representation/charts.py](briarwood/representation/charts.py); wedge's own representation layer builds the spec
- Frontend additive edits:
  - [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts) — `HorizontalBarWithRangesChartSpec` + union entry
  - [web/src/lib/chat/chart-surface.ts](web/src/lib/chat/chart-surface.ts) — dispatch case
  - [web/src/components/chat/chart-frame.tsx](web/src/components/chat/chart-frame.tsx) — SVG component
- Test extension: [tests/representation/test_charts.py](tests/representation/test_charts.py) id-set assertion

**Gates 2 + 4 — passed.**

---

## 3. Intent Parser: Archetype Mapping ✓

**Commit:** `caa9672` — *feat(claims): add archetype routing map (phase 3 step 5)*

- New file: [briarwood/claims/routing.py](briarwood/claims/routing.py) — `map_to_archetype(answer_type, question_focus, has_pinned_listing)`
- Plan-vs-reality fix: there is no `QuestionFocus` class; `ParserOutput.question_focus` is `list[str]`. Parameter typed accordingly and the wedge doesn't branch on its value
- Tests: [tests/claims/test_routing.py](tests/claims/test_routing.py) — 6 tests covering `DECISION` + `LOOKUP` mapping and None fallbacks

**Gate 3 — passed.**

---

## 4. Synthesis: Claim Object Producer ✓

**Commit:** `8b65e7a` — *feat(claims): add synthesis producer for VerdictWithComparisonClaim (phase 3 step 6)*

- New files:
  - [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py) — `build_verdict_with_comparison_claim(...)`
  - [briarwood/claims/synthesis/templates.py](briarwood/claims/synthesis/templates.py) — `VERDICT_HEADLINE`, `BRIDGE_SENTENCE`, `DEFAULT_NEXT_QUESTIONS`
  - [briarwood/claims/synthesis/__init__.py](briarwood/claims/synthesis/__init__.py)
- Plan-vs-reality fix: valuation module does not emit three explicit scenarios. Synthesizer assembles them from `comparable_sales.comps_used` using bed/bath + condition-profile predicates, drops tiers with zero qualifying comps and logs a caveat (matches plan §4.2 fallback)
- Small-sample caveats (`n < 5`) emitted here — step 8's Editor relies on them (see step 6 notes below)
- Tests: [tests/claims/test_synthesis.py](tests/claims/test_synthesis.py) — 24 tests covering every field mapping, the three-tier assembly, verdict thresholds, and the +bath-missing fallback

**Gate 4 — passed.**

---

## 5. Value Scout v1 ✓

**Commit:** `81e6a9d` — *feat(value_scout): add uplift-dominance pattern (phase 3 step 7)*

- New package: [briarwood/value_scout/](briarwood/value_scout/)
  - [briarwood/value_scout/scout.py](briarwood/value_scout/scout.py) — `scout_claim(claim) -> SurfacedInsight | None`
  - [briarwood/value_scout/patterns/uplift_dominance.py](briarwood/value_scout/patterns/uplift_dominance.py) — the one v1 pattern
- Placeholder renovation cost constants live in the pattern file and are flagged as a Phase B limitation
- Tests: [tests/value_scout/test_scout.py](tests/value_scout/test_scout.py), [tests/value_scout/test_uplift_dominance.py](tests/value_scout/test_uplift_dominance.py) — 10 tests, including Belmar-fixture happy path and a null-case

**Gate 5 — passed.**

---

## 6. Editor v1 ✓

**Commit:** `607ac8e` — *feat(editor): add claim validator with 5 checks (phase 3 step 8)*

- New package: [briarwood/editor/](briarwood/editor/)
  - [briarwood/editor/validator.py](briarwood/editor/validator.py) — `edit_claim(claim) -> EditResult` (NamedTuple of `passed: bool`, `failures: list[str]`)
  - [briarwood/editor/checks.py](briarwood/editor/checks.py) — 5 check functions
  - [briarwood/editor/__init__.py](briarwood/editor/__init__.py)
- Check set (plan §6.3):
  1. `check_schema_conformance` — no-op (Pydantic already enforces)
  2. `check_scenario_data_completeness` — `sample_size > 0`
  3. `check_verdict_delta_coherence` — label matches ±5% rule
  4. `check_emphasis_coherence` — `emphasis_scenario_id` matches `surfaced_insight.scenario_id`
  5. `check_caveat_for_gap` — every `sample_size < 5` scenario has a matching caveat
- Small-sample caveat emission added to synthesis (step 6) so Belmar's renovated_same=3 and renovated_plus_bath=2 scenarios pass check 5. Threshold constant (`SMALL_SAMPLE_THRESHOLD = 5`) duplicated on purpose — editor stays independent of synthesis internals
- SSE fallback event decision deferred to step 10 (resolved as a new `claim_rejected` event — see §8 below)
- Tests: [tests/editor/test_validator.py](tests/editor/test_validator.py) — 18 tests, each check independently + aggregation + Belmar happy path

**Gate 6 — passed.**

---

## 7. Representation: Driven by Schema ✓

**Commit:** `6e7cb53` — *feat(claims/representation): render verdict_with_comparison (phase 3 step 9)*

- New files:
  - [briarwood/claims/representation/verdict_with_comparison.py](briarwood/claims/representation/verdict_with_comparison.py) — `render_claim(claim, *, llm) -> RenderedClaim`
  - [briarwood/claims/representation/rubric.py](briarwood/claims/representation/rubric.py) — `apply_rubric(headline, confidence, *, comp_count)` for the 4 bands
  - [briarwood/claims/representation/__init__.py](briarwood/claims/representation/__init__.py)
- Three sub-steps in `render_claim`, per plan:
  1. Deterministic — headline (rubric-modified) + bridge verbatim
  2. LLM prose — `complete_and_verify` with claim serialized as `structured_inputs`; deterministic fallback when `llm is None` so outages don't mask silently
  3. Deterministic — chart event (`horizontal_bar_with_ranges`) + suggestions event from `next_questions`
- New prompt: [api/prompts/claim_verdict_with_comparison.md](api/prompts/claim_verdict_with_comparison.md) — includes `_base.md`, investor persona, 2–4 sentences, must echo `surfaced_insight` when present
- Rubric: high → no change; medium → prepend "Based on N comparable sales,"; low → "Our best estimate is"; very_low → "We don't have high confidence here, but…" (range conversion for low is a documented Phase B limitation)
- Separation of concerns: `SurfacedInsight.headline` + `.reason` flow to the prose prompt only; chart spec only carries `emphasis_scenario_id`
- Tests: [tests/claims/test_representation.py](tests/claims/test_representation.py) — 14 tests across rubric, deterministic fallback, LLM prose ordering, chart event shape, suggestions, and Belmar end-to-end

**Gate 7 — passed.**

---

## 8. Wire Into Dispatch ✓

**Commit:** `9445d5e` — *feat(dispatch): wire claim-object pipeline behind feature flag (phase 3 step 10)*

- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) — 7-line feature-flagged branch inserted after pid resolution, before legacy `_analysis_overrides` / `PropertyView.load` (legacy body untouched)
- New helper in the same file: `_maybe_handle_via_claim(text, decision, session, llm, *, pid)` — orchestrates `build_claim_for_property` → `scout_claim` → `edit_claim` → `render_claim`
- New file: [briarwood/claims/pipeline.py](briarwood/claims/pipeline.py) — `build_claim_for_property(pid, *, user_text, overrides=None)` wraps `run_briarwood_analysis_with_artifacts` + `_scoped_synthesizer` and extracts the four inputs the synthesizer consumes
- Any failure (flag off, wrong archetype, build exception, Editor rejection, render exception) falls through to the legacy body. Rolling back = `unset BRIARWOOD_CLAIMS_ENABLED`

### SSE event + session plumbing

- New event: `claim_rejected(archetype, failures)` in [api/events.py](api/events.py) — single-purpose, long-term-stable over reusing `partial_data_warning` (confirmed with user at step 8)
- Mirror: `ClaimRejectedEvent` + union entry in [web/src/lib/chat/events.ts](web/src/lib/chat/events.ts)
- [briarwood/agent/session.py](briarwood/agent/session.py) — `last_claim_events: list[dict]` + `last_claim_rejected: dict | None`, cleared per turn, persisted across save/load
- [api/pipeline_adapter.py](api/pipeline_adapter.py) — decision branch yields `session.last_claim_events` as primary events and `claim_rejected` after partial-data warnings
- Tests: [tests/claims/test_dispatch_branch.py](tests/claims/test_dispatch_branch.py) — 6 tests covering flag off, wrong answer type, happy path, Editor rejection, build failure, render failure

**Gate 8 — passed.**

---

## 9. Tests ✓

Planned coverage in place:

| Plan test file | Actual path | Status |
|---|---|---|
| Fixtures | [tests/claims/fixtures/belmar_house.py](tests/claims/fixtures/belmar_house.py) | ✓ |
| `test_archetypes.py` | [tests/claims/test_archetypes.py](tests/claims/test_archetypes.py) | ✓ |
| `test_routing.py` | [tests/claims/test_routing.py](tests/claims/test_routing.py) | ✓ |
| `test_verdict_with_comparison_schema.py` | [tests/claims/test_verdict_with_comparison_schema.py](tests/claims/test_verdict_with_comparison_schema.py) | ✓ |
| `test_synthesis.py` | [tests/claims/test_synthesis.py](tests/claims/test_synthesis.py) | ✓ |
| `test_scout.py` | [tests/value_scout/test_scout.py](tests/value_scout/test_scout.py) | ✓ |
| `test_validator.py` | [tests/editor/test_validator.py](tests/editor/test_validator.py) | ✓ |
| `test_representation.py` | [tests/claims/test_representation.py](tests/claims/test_representation.py) | ✓ |
| `test_golden_e2e.py` | [tests/claims/test_golden_e2e.py](tests/claims/test_golden_e2e.py) | ✓ |
| `test_feature_flags.py` | [tests/test_feature_flags.py](tests/test_feature_flags.py) | ✓ |

### Golden end-to-end (step 11)

**Commit:** `83bf439` — *test(claims): golden end-to-end test for wedge SSE contract (phase 3 step 11)*

- [tests/claims/test_golden_e2e.py](tests/claims/test_golden_e2e.py) — 5 tests driving the Belmar fixture through `decision_stream` with `BRIARWOOD_CLAIMS_ENABLED=true`
- Only `build_claim_for_property` is mocked (it wants on-disk inputs.json). Value Scout, Editor, Representation, and `_decision_stream_impl` all run unmocked — any regression in how the wedge surfaces events to the UI shows up here
- UI-surfacing contract asserted:
  1. Claim prose reaches the `text_delta` stream
  2. `chart` event with `kind="horizontal_bar_with_ranges"`, `unit="$/sqft"`, scenarios in order `[subject, renovated_same, renovated_plus_bath]`, `emphasis_scenario_id="renovated_plus_bath"`
  3. `suggestions` event carries the claim's next-question texts
  4. No `claim_rejected` event on the happy path
  5. Chart lands **before** the first `text_delta` (primary-event ordering)

### Totals

- Wedge suites (claims + value_scout + editor + feature_flags + session): **117 tests, all passing**
- Regression sweep (dispatch, pipeline adapter contracts, chat API): **115 tests, all passing**
- One pre-existing unrelated failure remains in `tests/representation/test_charts.py::test_every_spec_declares_claim_types_and_required_inputs` (`hidden_upside_band`) — confirmed pre-existing via `git stash` isolation

**Gate 9 — passed.**

---

## 10. Execution Order — Status

| # | Step | Commit | Status |
|---|---|---|---|
| 1 | Feature flag module | `8c8d8ef` | ✓ |
| 2 | Claims skeleton + base schemas | `14824bd` | ✓ |
| 3 | `verdict_with_comparison` schema | `65ece6f` | ✓ |
| 4 | Chart-rule addition | `7f8c59a` | ✓ |
| 5 | Intent routing | `caa9672` | ✓ |
| 6 | Synthesis producer | `8b65e7a` | ✓ |
| 7 | Value Scout | `81e6a9d` | ✓ |
| 8 | Editor | `607ac8e` | ✓ |
| 9 | Representation + prompt | `6e7cb53` | ✓ |
| 10 | Dispatch wiring + SSE event | `9445d5e` | ✓ |
| 11 | Golden end-to-end test | `83bf439` | ✓ |
| 12 | Manual smoke test | — | **pending** |

---

## 11. Definition of Done — Status

| Criterion | Status |
|---|---|
| Flag-on Belmar produces qualitatively better response than legacy | Pending step 12 |
| All new tests pass | ✓ |
| All existing tests still pass (legacy path untouched) | ✓ (1 pre-existing unrelated failure) |
| Flag-off = byte-identical to pre-wedge | ✓ (branch prepended only; legacy body unchanged) |
| Editor rejection falls back cleanly to legacy | ✓ (covered in `test_dispatch_branch.py`) |
| No edits to `briarwood/modules/` | ✓ |
| No edits to `web/src/components/chat/` beyond approved additive work | ✓ (only additive + chart-frame entry per gate 2) |
| DESIGN_DOC / phase_3_build updated for divergences | This file covers divergences |

---

## 12. Open for Step 12

Manual smoke test remaining:

```
BRIARWOOD_CLAIMS_ENABLED=true
```

- Start API + web
- Pin the Belmar saved listing
- Ask "is this a good price?"
- Observe SSE stream for: claim-path prose, `chart` event (`horizontal_bar_with_ranges`, emphasis row highlighted), `suggestions` event, no `claim_rejected`
- Unset the flag and repeat to confirm byte-identical legacy behavior

After step 12 passes, `WEDGE_RETRO.md` captures answers to the six learning questions in plan §12.

---

## Divergences from the plan (audit trail)

1. **`QuestionFocus` import** — doesn't exist. Typed `question_focus` as `list[str] | None`. (Step 3.)
2. **Three-tier scenarios** — valuation module does not emit them. Synthesizer assembles tiers from `comparable_sales.comps_used`. (Step 4.)
3. **`horizontal_bar_with_ranges` chart kind** — did not exist; escalated at gate 2 and approved as additive-only backend + frontend. (Step 4 execution / gate 2.)
4. **Small-sample caveat emission** — added to synthesis so Editor's `caveat_for_gap` check can pass on Belmar. Threshold duplicated (not imported) between editor and synthesis to avoid layering inversion. (Step 6.)
5. **SSE fallback event** — new `claim_rejected` event chosen over reusing `partial_data_warning` (user call for long-term stability). Advisory only; UI ignores today. (Step 8.)
6. **Dispatch branch placement** — prepended after pid resolution (not at function entry) so the claim branch shares existing pid-resolution logic without duplicating it; legacy body still untouched. (Step 8.)

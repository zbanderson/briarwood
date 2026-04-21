# STATE_OF_1.0

Single-file status document for the 1.0 consolidation work. Friday's
retro reads from this file; keep each dated section factual and
short. When a section is not yet filled in, leave the
`<placeholder>` slots intact.

---

## One-line status

<placeholder: one sentence — "routed verdict is the only verdict;
legacy surfaces still render via a projector" etc.>

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

## Wednesday AM — 2026-04-22

<placeholder: AnalysisReport → UnifiedIntelligenceOutput adapter lands
at `briarwood/adapters/legacy_report.py` (or similar). The four
consumer surfaces rewire to
`project_to_legacy(adapt(report)) -> LegacyVerdict`.
`briarwood/decision_engine.py` deletes. `pipeline/representation.py`
review completes.>

### Deleted (Wednesday)

<placeholder>

### Modified (Wednesday)

<placeholder>

### Added (Wednesday)

<placeholder>

---

## Friday retro — 2026-04-24

<placeholder: one paragraph on what shipped vs what slipped, one
paragraph on what the consolidation actually bought (latency,
reasoning quality, maintenance burden), one paragraph on the next
cut's scope.>

---

## Follow-ups parked from this cut

<placeholder: anything surfaced during Monday/Wednesday that is real
but out of scope — e.g. confidence recalibration, projector for a
second display surface, deletion of `pipeline/representation.py`
pending usage audit.>

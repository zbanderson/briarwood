# briarwood/projections

Projections from the canonical routed verdict to display shapes for
compatibility surfaces that have not yet migrated to the routed
vocabulary.

## What lives here

Each projector takes a canonical routed output (today:
`UnifiedIntelligenceOutput` from `briarwood/synthesis/structured.py`) and
relabels it for a surface that still renders in an older vocabulary.

**Projectors do not re-derive verdicts.** They relabel, alias, and pass
through. If a projector is doing math that changes the decision, it is
not a projector — it is a second verdict path, which is exactly what the
F1 audit finding told us to stop building.

Current projectors:

| Projector | Purpose | Consumer surfaces |
|---|---|---|
| `legacy_verdict.py` | `UnifiedIntelligenceOutput` → legacy `BUY / LEAN BUY / NEUTRAL / LEAN PASS / AVOID` | `dash_app/quick_decision`, `dash_app/view_models`, `reports/sections/thesis_section`, `reports/sections/conclusion_section` |

## Stance mapping (legacy_verdict)

Seven routed `DecisionStance` values → five legacy labels. Three routed
stances collapse into `NEUTRAL` at the label tier; `LegacyVerdict` keeps
the underlying `decision_stance` and an `is_trust_gate_fallback` flag so
consumers can distinguish the three NEUTRAL flavors if they want to.

| DecisionStance | Legacy | Notes |
|---|---|---|
| `STRONG_BUY` | `BUY` | clean |
| `BUY_IF_PRICE_IMPROVES` | `LEAN BUY` | clean |
| `EXECUTION_DEPENDENT` | `LEAN BUY` | conditional yes; caveat surfaced in narrative |
| `INTERESTING_BUT_FRAGILE` | `NEUTRAL` | value there, risk dominates |
| `CONDITIONAL` | `NEUTRAL` | trust-gate fallback — flag with `is_trust_gate_fallback: true` |
| `PASS_UNLESS_CHANGES` | `LEAN PASS` | clean |
| `PASS` | `AVOID` | currently unemitted by the classifier; mapped anyway |

The same table is duplicated in the module docstring at
[legacy_verdict.py](legacy_verdict.py) and in `STATE_OF_1.0.md`. Keep
all three in sync.

## Conventions for new projectors

1. **One-way only.** A projector takes a routed type and returns a
   display type. Never the reverse; never "read current label and promote
   back to a stance."
2. **Deterministic.** No LLM calls, no timestamps, no randomness. Given
   the same routed input the projector must return the same output.
3. **Typed output.** Return a Pydantic model, not a `dict` or dataclass.
   The routed side is typed; projections should be too.
4. **Pass-through where possible.** Prefer surfacing the canonical field
   (e.g. `decision_stance`, `confidence`) alongside the projected label.
   Downstream surfaces will thank you when they want to render more
   faithfully later.
5. **Document ambiguity.** When a projection collapses distinctions
   (as `STANCE_TO_LEGACY_LABEL` does for three `NEUTRAL` flavors), add
   a flag or secondary field that preserves the distinction. Then
   document the collapse in this README's mapping section.
6. **Tests live alongside.** Add tests under `tests/projections/` that
   cover each enum-to-label mapping and any fallback logic.

## What does NOT belong here

- AnalysisReport → routed adapter. That lives elsewhere (Wednesday:
  likely `briarwood/adapters/legacy_report.py`). The adapter converts
  legacy module outputs into the shape `build_unified_output()` expects;
  once a routed output exists, the projector takes over. Keep the two
  concerns separate.
- New verdict logic. If you find yourself writing band thresholds or
  stance rules in this directory, stop. That work belongs in
  `briarwood/synthesis/structured.py`.

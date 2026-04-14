# Model Audits (Phase 2)

Per-module notes documenting failure modes surfaced by the Phase 2 isolation
harnesses in [`tests/modules/test_*_isolated.py`](../../tests/modules/).

Each audit doc follows the Spec §7 template:

- **Identity** — name, layer, purpose, core question
- **Inputs** — required / optional / inferred / confidence logic
- **Outputs** — raw, summary, decision-relevant, confidence
- **Dependencies** — upstream, downstream, interaction points
- **Failure Modes** — what breaks, what weakens, what causes false confidence
- **Decision Role** — informs / adjusts / gates / explains / synthesizes
- **Test Cases** — normal / thin / contradictory / unique / fragile

Each doc ends with a **Phase 3/4 fix list** — these are the concrete changes
that should land before the module is considered "done."

## Audits in this directory

- [valuation.md](valuation.md)
- [risk_model.md](risk_model.md)
- [rent_stabilization.md](rent_stabilization.md)
- [legal_confidence.md](legal_confidence.md)
- [resale_scenario.md](resale_scenario.md)

_Remaining 8 scoped modules will be audited in a later batch after the five
highest-priority silos are broken in Phase 4._

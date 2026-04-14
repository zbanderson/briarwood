# Audit: `legal_confidence`

## Identity
- **File:** [briarwood/modules/legal_confidence.py](../../briarwood/modules/legal_confidence.py)
- **Runner:** `run_legal_confidence(context: ExecutionContext) -> dict`
- **Layer:** L3F + L6 (Town/Market context + Trust)
- **Decision role:** Fact provider + decision gate
- **Core question:** Is the intended use of this property legally supported?

## Inputs
- **Required:** `context.property_data` (specifically: zone_flags, local_documents, additional_units, back_house, adu_type)
- **Optional:** `market_context`, `prior_outputs`

## Outputs
- `data.legality_evidence` — structured evidence object
- `data.data_quality` + `data.local_intelligence` — sub-module passthroughs
- `confidence` — capped at 0.65 when no accessory signal, floored at 0.55 when zone flags exist
- `warnings` — fires when accessory signals exist without zoning/local-doc backing

## Dependencies
- **Upstream declared:** none
- **Upstream used:** none
- **Downstream consumers:** synthesis only — **STRANDED**

## Failure Modes (surfaced in Phase 2 harness)
1. **Output is stranded.** No rent, risk, or valuation module consumes `legality_evidence`. The module produces a meaningful signal (2 warnings fire on the unique-property fixture) but nothing acts on it.
2. **Module is the only one in the scoped set that actually uses structured evidence for its confidence.** This is a *strength* — the pattern should spread.
3. **Data quality confidence hardcoded** via `PropertyDataQualityModule` at 0.72 / 0.48 — needs Phase 3 work to become evidence-based.

## Decision Role (today vs target)
| | Today | Target after Phase 4 |
|---|---|---|
| Informs | ✅ | Unchanged |
| Adjusts | ❌ | Should adjust `rent_stabilization` confidence |
| Gates | ~ | Caps own confidence at 0.65 — good pattern |
| Explains | ✅ | Surfaces specific warnings |
| Synthesizes | ❌ | — |

## Test Cases (`tests/modules/test_legal_confidence_isolated.py`)
| Case | Confidence | Warnings | Notes |
|---|---|---|---|
| Normal (SFH, no accessory) | 0.48 | 0 | Capped at 0.65 by design |
| Thin | 0.48 | 0 | Safe — no crash |
| Contradictory | 0.48 | 0 | Runs cleanly |
| Unique (ADU + back house, no zoning) | 0.48 | **2** | ✅ Best-behaving module in the sweep |
| Fragile | 0.48 | 0 | Runs cleanly |

## Phase 3 / 4 Fix List
- [ ] **Phase 3:** Replace hardcoded 0.72 / 0.48 in `PropertyDataQualityModule` with field-coverage scoring.
- [ ] **Phase 4 (critical):** Wire `legality_evidence` into a `rent_x_risk` bridge that downgrades rent confidence on accessory signals without zoning backing.
- [ ] **Phase 4:** Surface `zoning_unverified` as a named `trust_flag` for the new synthesizer.
- [ ] **Phase 5:** The synthesizer should refuse to emit a `strong_buy` stance if legal_confidence < 0.55 AND primary_value_source is income-from-accessory-unit.

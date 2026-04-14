# Audit: `risk_model`

## Identity
- **File:** [briarwood/modules/risk_model.py](../../briarwood/modules/risk_model.py)
- **Runner:** `run_risk_model(context: ExecutionContext) -> dict`
- **Layer:** L3E (Risk & Constraints)
- **Decision role:** Judgment engine + decision gate
- **Core question:** What could go wrong, and how badly does that matter?

## Inputs
- **Required:** `context.property_data`
- **Optional (declared):** `prior_outputs`, `market_context`
- **Actually used:** `property_data` only. The module self-documents this:
  > "this risk module remains mostly property-input-driven today"

## Outputs
- `data.risk_score` / `data.fragility_flags` / `data.decision_constraints`
- `confidence` (single float)
- `assumptions_used` includes `valuation_dependency_declared: True` as an explicit silo marker

## Dependencies
- **Upstream declared:** `valuation`
- **Upstream used:** **none** — the #1 silo in the system
- **Downstream consumers:** synthesis only

## Failure Modes (surfaced in Phase 2 harness)
1. **Confidence is constant (~0.72) across normal / contradictory / fragile inputs.** This is *the* silo signature. The harness locks it in with `assertEqual(normal, contradictory)` so the moment Phase 4 wires real inputs, the test goes red.
2. **Thin inputs do not degrade confidence.** There is no data-quality gate.
3. **Unique-property signals (accessory units, zoning ambiguity) do not raise risk.** The legal_confidence output is stranded and never reaches this module.
4. **No valuation dep is consumed** — overpay risk cannot be assessed.

## Decision Role (today vs target)
| | Today | Target after Phase 4 |
|---|---|---|
| Informs | ~ | Structured risk pillars |
| Adjusts | ❌ | Modulates valuation premium tolerance |
| Gates | ❌ | Suppresses strong-buy when fragility high |
| Explains | ~ | Flat fragility_flags list |
| Synthesizes | ❌ | Not its job |

## Test Cases (`tests/modules/test_risk_model_isolated.py`)
| Case | Current confidence | Warnings | Notes |
|---|---|---|---|
| Normal | 0.72 | 0 | Baseline |
| Thin | 0.55 | 0 | ❌ Should drop harder (missing inputs) |
| Contradictory | 0.72 | 0 | ❌ Identical to normal — silo |
| Unique | 0.72 | 0 | ❌ Accessory-unit legality ignored |
| Fragile | 0.72 | 0 | ❌ Identical to normal — silo |

## Phase 3 / 4 Fix List
- [ ] **Phase 4 (highest priority):** Implement `valuation_x_risk` bridge. Risk must read valuation's premium_vs_comps, liquidity_signal, comp_coverage.
- [ ] **Phase 4:** Implement `rent_x_risk` bridge (consume legal_confidence + seasonality signals).
- [ ] **Phase 4:** Implement `scenario_x_risk` bridge (consume execution-dependence from resale_scenario and renovation_impact).
- [ ] **Phase 4:** Risk should output structured `trust_flags` (thin_comp_set, zoning_unverified, execution_heavy, exit_liquidity_weak) consumable by the synthesis trust gate.
- [ ] **Phase 5:** Once bridges land, `confidence` should become derivable from the inputs, not a static 0.72.
- [ ] **Test change after Phase 4:** flip `assertEqual(normal, fragile)` → `assertLess(fragile, normal)` in [test_risk_model_isolated.py:33](../../tests/modules/test_risk_model_isolated.py#L33).

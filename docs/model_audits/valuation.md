# Audit: `valuation`

## Identity
- **File:** [briarwood/modules/valuation.py](../../briarwood/modules/valuation.py)
- **Runner:** `run_valuation(context: ExecutionContext) -> dict`
- **Layer:** L3A (Valuation)
- **Decision role:** Judgment engine
- **Core question:** What is the likely fair value range for this asset?

## Inputs
- **Required:** `context.property_data` (flat or canonical)
- **Optional:** `comp_context`, `market_context`, `property_summary`
- **Inferred / confidence logic:** Delegates to `CurrentValueModule`, which internally blends comparable sales, market history, income support, and a hybrid anchor. Confidence is assembled from sub-module scores.

## Outputs
- `data.current_value` / `data.comparable_sales` / `data.market_history` / `data.income_support` / `data.hybrid_value`
- `confidence` (single float in [0,1])
- `assumptions_used`: `{legacy_module: "CurrentValueModule", uses_full_engine_report: False, ...}`

## Dependencies
- **Upstream declared:** none
- **Upstream used:** none
- **Downstream consumers:** `risk_model`, `rental_option`, `resale_scenario`, `arv_model`

## Failure Modes (surfaced in Phase 2 harness)
1. **Contradictory inputs do not degrade confidence or warn.** A $2.4M ask on 700 sqft / 6 beds / 1 bath (contradictory fixture) produces `confidence ≈ 0.62` with zero warnings. There is no sanity check against sqft×$/sqft ballpark.
2. **Unique-property signals (ADU, back house, additional units) are not reflected in valuation.** The back-house fixture runs cleanly but the output data does not reference accessory-unit value.
3. **Fragile financing is correctly ignored** by valuation (price-centric), but there is no hook to surface financing-related value flags to a bridge layer.

## Decision Role (today vs target)
| | Today | Target after Phase 4 |
|---|---|---|
| Informs | ✅ Drives valuation view | Same |
| Adjusts | ❌ | Should accept premium-band modulation from `valuation_x_town` |
| Gates | ❌ | Should be gated by `valuation_x_risk` on liquidity / fragility |
| Explains | ~ | Drivers are buried in legacy payload |
| Synthesizes | ❌ | Not its job |

## Test Cases (`tests/modules/test_valuation_isolated.py`)
| Case | Current confidence | Warnings | Notes |
|---|---|---|---|
| Normal | 0.70 | 0 | ✅ Expected |
| Thin | 0.00 | 0 | ✅ Correctly collapses |
| Contradictory | ~0.62 | 0 | ❌ Should warn; no sanity check |
| Unique (ADU/back house) | ~0.60 | 0 | ❌ Accessory signals ignored |
| Fragile | ~0.70 | 0 | ✅ Identical to normal (correct for valuation) |

## Phase 3 / 4 Fix List
- [ ] **Phase 3:** Surface explicit `key_value_drivers` and `key_risks` lists in the top-level payload data (currently only in legacy_payload).
- [ ] **Phase 3:** Add a `comp_coverage_summary` field (count, quality, recency of comps used) to support the `valuation_x_risk` bridge.
- [ ] **Phase 4:** Implement `valuation_x_town` bridge to widen / tighten the premium band based on scarcity + liquidity.
- [ ] **Phase 4:** Implement `valuation_x_risk` bridge to gate "cheap-looking" valuations when liquidity or execution is weak.
- [ ] **Phase 4:** Sanity-check bridge — raise a `warnings` entry when sqft × town $/sqft disagrees with asking price by more than ~3x.

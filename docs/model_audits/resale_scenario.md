# Audit: `resale_scenario`

## Identity
- **File:** [briarwood/modules/resale_scenario_scoped.py](../../briarwood/modules/resale_scenario_scoped.py)
- **Runner:** `run_resale_scenario(context: ExecutionContext) -> dict`
- **Layer:** L3D (Scenario)
- **Decision role:** Judgment engine
- **Core question:** How does the investment evolve under different futures?

## Inputs
- **Required:** `property_data`, `assumptions`
- **Optional:** `prior_outputs`, `market_context`
- Internally runs `BullBaseBearModule`, which chains: current-value, market-history, town-county outlook, risk, scarcity.

## Outputs
- `data.bull_value` / `data.base_value` / `data.bear_value`
- `data.scenario_metrics`
- `confidence` (single float, ~0.6 for typical cases, 0.0 for thin)

## Dependencies
- **Upstream declared:** `valuation`, `carry_cost`
- **Upstream used:** none (silo) — the internal `BullBaseBearModule` runs its own sub-modules rather than reading scoped prior_outputs.
- **Downstream consumers:** synthesis only

## Failure Modes (surfaced in Phase 2 harness)
1. **Confidence is insensitive to fragile financing.** Normal and fragile fixtures produce identical ~0.6 confidence.
2. **Confidence is insensitive to contradictory inputs.** A $2.4M ask on 700 sqft produces same confidence as a clean comp-supported deal.
3. **Thin inputs correctly collapse to 0.0** — this is the one input where the sub-module chain fails fast (no purchase_price).
4. **No feedback from town regime.** The internal `TownCountyOutlookModule` runs but its output doesn't modulate bull/bear spreads.
5. **No feedback from risk model.** Execution dependence is not reflected in scenario output.

## Decision Role (today vs target)
| | Today | Target after Phase 4 |
|---|---|---|
| Informs | ✅ | Unchanged |
| Adjusts | ❌ | Should be modulated by `town_x_scenario` and `scenario_x_risk` |
| Gates | ❌ | Not its job |
| Explains | ~ | Bull/base/bear but no "what_must_be_true" decomposition |
| Synthesizes | ❌ | — |

## Test Cases (`tests/modules/test_resale_scenario_isolated.py`)
| Case | Confidence | Notes |
|---|---|---|
| Normal | 0.60 | Baseline |
| Thin | 0.00 | ✅ Correctly collapses |
| Contradictory | 0.60 | ❌ Identical to normal — silo |
| Unique | 0.60 | ❌ ADU optionality not reflected |
| Fragile | 0.60 | ❌ Identical to normal — silo |

## Phase 3 / 4 Fix List
- [ ] **Phase 4:** `town_x_scenario` bridge — adjust bull/bear spread using town liquidity + scarcity signal.
- [ ] **Phase 4:** `scenario_x_risk` bridge — output an execution_dependence label and a `what_must_be_true` list (e.g., "appreciation ≥ 3%/yr", "rent reaches $4,500").
- [ ] **Phase 4:** Scenario should emit a `fragility_score` consumable by synthesis.
- [ ] **Phase 5:** When `fragility_score` is high, synthesizer should output `execution_dependent` stance rather than `strong_buy`.
- [ ] **Test change after Phase 4:** flip `assertEqual(normal, fragile)` in [test_resale_scenario_isolated.py:37](../../tests/modules/test_resale_scenario_isolated.py#L37) to `assertLess(fragile, normal)`.

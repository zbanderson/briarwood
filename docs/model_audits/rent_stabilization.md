# Audit: `rent_stabilization`

## Identity
- **File:** [briarwood/modules/rent_stabilization.py](../../briarwood/modules/rent_stabilization.py)
- **Runner:** `run_rent_stabilization(context: ExecutionContext) -> dict`
- **Layer:** L3C (Rent / Income)
- **Decision role:** Judgment engine
- **Core question:** How durable is rent income at this property, in this town?

## Inputs
- **Required:** `context.property_data`
- **Optional:** `market_context`, `comp_context`
- Internally runs `RentalEaseModule` + `TownCountyOutlookModule`.

## Outputs
- `data.rental_ease_score` / `data.days_to_rent` / `data.rental_ease_label`
- `data.town_county_outlook` (extra_data slot)
- `confidence` (primary)

## Dependencies
- **Upstream declared:** none
- **Upstream used:** none
- **Downstream consumers:** `hold_to_rent`

## Failure Modes (surfaced in Phase 2 harness)
1. **Hard crash on thin inputs.** [test_thin_inputs_crash_today](../../tests/modules/test_rent_stabilization_isolated.py#L30) locks in a `TypeError: income_support module payload is not an IncomeAgentOutput` when property_data lacks `purchase_price`. This is the worst failure mode in the Phase 2 sweep — a production data edge case will crash the whole analysis.
2. **Flat ~0.88 confidence** across normal / contradictory / fragile fixtures. Does not react to input quality.
3. **Ignores `legal_confidence`.** The unique-property fixture (ADU + back house + no zoning flags) gets the same rent confidence as a clean SFH. Accessory-unit rent optimism is not gated by legality.
4. **No seasonality or stabilization modulation.** The module surfaces town_county_outlook but does not use it to adjust its own confidence.

## Decision Role (today vs target)
| | Today | Target after Phase 3/4 |
|---|---|---|
| Informs | ✅ | Rental ease + town outlook |
| Adjusts | ❌ | Should be adjusted by `rent_x_risk` when legality is uncertain |
| Gates | ❌ | Not its job |
| Explains | ~ | Flat metrics dict |
| Synthesizes | ❌ | — |

## Test Cases (`tests/modules/test_rent_stabilization_isolated.py`)
| Case | Current confidence | Warnings | Notes |
|---|---|---|---|
| Normal | 0.88 | 0 | Baseline |
| Thin | **CRASH** | — | ❌ `TypeError` in IncomeSupportModule |
| Contradictory | 0.88 | 0 | ❌ Identical — silo |
| Unique | 0.88 | 0 | ❌ Ignores legal_confidence |
| Fragile | 0.88 | 0 | ❌ Identical — silo |

## Phase 3 / 4 Fix List
- [ ] **Phase 3 (highest priority):** Make `IncomeSupportModule` robust to missing `purchase_price`. Either normalize in intake or guard in the scoped runner.
- [ ] **Phase 3:** Tag inferred rent numbers distinctly from user-provided ones and propagate to confidence.
- [ ] **Phase 4:** Implement `rent_x_risk` bridge — consume `legal_confidence.legality_evidence` and downgrade rent confidence when accessory signals exist without zoning support.
- [ ] **Phase 4:** Implement `town_x_scenario` bridge to modulate seasonality / rent-growth realism from town outlook.
- [ ] **Test change after Phase 3:** replace `pytest.raises(TypeError)` in [test_thin_inputs_crash_today](../../tests/modules/test_rent_stabilization_isolated.py#L30) with an assertion that confidence drops ≤ 0.4.

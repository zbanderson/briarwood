# Briarwood Model Inventory (Phase 1)

**Purpose:** Authoritative inventory of every analytic module in Briarwood, mapped against the Model Layering + Interaction Spec. This is the Phase 1 deliverable — input to Phases 2 (isolate/test), 3 (strengthen intake), 4 (build bridges), and 5 (rebuild synthesis).

**Spec layers:**
- **L1** Raw Input / Intake
- **L2** Normalized Fact
- **L3A** Valuation
- **L3B** Cost / Carry
- **L3C** Rent / Income
- **L3D** Scenario
- **L3E** Risk & Constraints
- **L3F** Town / Market
- **L4** Interaction (bridges between domain models)
- **L5** Unified Intelligence (synthesis)
- **L6** Trust Calibration

**Decision role codes:** F=Fact provider · J=Judgment engine · A=Adjustment engine · G=Decision gate · N=Narrative translator

**Scoring scale (1–5):** analytical usefulness · output clarity · confidence realism · decision relevance · interaction readiness

---

## Scoped Modules (registered in [briarwood/execution/registry.py](../briarwood/execution/registry.py))

| # | Module | File | Layer | Decision Role | Core Question | Inputs | Outputs (ModulePayload) | Confidence Method | Upstream Deps (declared / **used**) | Downstream Consumers | Interaction Rules Today | Scores (U/C/CR/DR/IR) | **Keep/Fix/Cut** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **valuation** | [modules/valuation.py](../briarwood/modules/valuation.py) | L3A | J | What is fair value? | property_data, comp_context, market_context | current_value, comparable_sales, market_history, income_support, hybrid_value | Internal (sub-modules) | none / **none** | risk_model, rental_option, resale_scenario, arv_model | None — runs standalone | 4/3/2/5/1 | **Fix** — add comp-quality aware confidence; surface drivers for bridge layer |
| 2 | **carry_cost** | [modules/carry_cost.py](../briarwood/modules/carry_cost.py) | L3B | J | What does it cost to own? | property_data, assumptions | monthly_total_cost, monthly_cash_flow, cap_rate, financing | Static | none / **none** | hold_to_rent, margin_sensitivity, unit_income_offset | None | 4/4/2/4/2 | **Fix** — expose break-even rent + owner-occ vs investor cases as first-class |
| 3 | **rent_stabilization** | [modules/rent_stabilization.py](../briarwood/modules/rent_stabilization.py) | L3C | J | How durable is rent income? | property_data, assumptions, market_context | rental_ease_score, days_to_rent, town_outlook | Composite min() | none / **none** | hold_to_rent | None — town signal not modulated by risk/legal | 3/3/3/4/2 | **Fix** — downgrade when legal_confidence flags unverified use |
| 4 | **rental_option** | [modules/rental_option_scoped.py](../briarwood/modules/rental_option_scoped.py) | L3C | J | What can it earn as a rental? | property_data, assumptions, comp_context | rental_income, rental_feasibility, income_support | Composite | valuation / **not used** | (end-of-chain for rental path) | Dep declared but not consumed | 3/3/2/4/1 | **Fix** — actually use valuation output or drop dep |
| 5 | **risk_model** | [modules/risk_model.py](../briarwood/modules/risk_model.py) | L3E | J+G | What could go wrong? | property_data | risk_score, fragility_flags, decision_constraints | Heuristic | valuation / **not used** (self-comment admits it) | (consumed by synthesis only) | **Silo** — critical gap | 2/3/2/5/1 | **Fix** — this is the #1 silo to break; must read valuation/scenario |
| 6 | **confidence** | [modules/confidence.py](../briarwood/modules/confidence.py) | L6 | A | How much should we trust this? | property_data, prior_outputs | confidence_score, data_quality | Reads priors | all / **reads but not weighted** | synthesis | Partial — collects but doesn't aggregate intelligently | 2/3/1/5/2 | **Fix** — replace with real trust-calibration rollup in Phase 5 |
| 7 | **resale_scenario** | [modules/resale_scenario_scoped.py](../briarwood/modules/resale_scenario_scoped.py) | L3D | J | How does value evolve? | property_data, assumptions, market_context | bull/base/bear value, scenario_metrics | Static range | valuation, carry_cost / **not used** | (consumed by synthesis only) | Silo — no risk/town modulation | 3/3/2/4/1 | **Fix** — appreciation realism must come from town_x_scenario bridge |
| 8 | **renovation_impact** | [modules/renovation_impact_scoped.py](../briarwood/modules/renovation_impact_scoped.py) | L3A + L3D | J | What value does reno create? | property_data, assumptions | current_bcv, renovated_bcv, roi_pct | Static | none / **none** | arv_model, margin_sensitivity | Silo | 3/4/2/4/1 | **Keep** — solid standalone; needs bridge to risk for execution-dependence |
| 9 | **hold_to_rent** | [modules/hold_to_rent.py](../briarwood/modules/hold_to_rent.py) | L4 (composite) | N | Can rent offset carry? | prior outputs | hold_path_snapshot, cash_flow | min(upstream confidence) | carry_cost, rent_stabilization / **used (read-only)** | (synthesis) | Read-only wrapper — not a real bridge | 3/4/3/4/3 | **Fix** — promote to a real `rent_x_cost` bridge (carry_offset_ratio, break-even probability) |
| 10 | **arv_model** | [modules/arv_model_scoped.py](../briarwood/modules/arv_model_scoped.py) | L4 (composite) | N | What's the post-reno value? | prior outputs | arv_snapshot, net_value_creation | min(upstream confidence) | valuation, renovation_impact / **used (read-only)** | margin_sensitivity | Read-only wrapper | 3/4/3/4/3 | **Keep** — mostly fine; add comp-coverage trust flag |
| 11 | **margin_sensitivity** | [modules/margin_sensitivity_scoped.py](../briarwood/modules/margin_sensitivity_scoped.py) | L4 (composite) | N | How fragile is the reno margin? | prior outputs | sensitivity_scenarios, breakeven_budget | min() | arv_model, renovation_impact, carry_cost / **used (read-only)** | (synthesis) | Read-only | 4/4/3/5/3 | **Keep** — already behaves like a bridge; generalize pattern to other domains |
| 12 | **unit_income_offset** | [modules/unit_income_offset.py](../briarwood/modules/unit_income_offset.py) | L3B + L3C bridge | A | How much does an extra unit offset carry? | prior outputs, assumptions | offset_snapshot, additional_unit_income | Static | carry_cost / **used** | (synthesis) | Real bridge but narrow scope | 4/4/3/4/3 | **Keep** |
| 13 | **legal_confidence** | [modules/legal_confidence.py](../briarwood/modules/legal_confidence.py) | L3F + L6 | F+G | Is the intended use legal? | property_data, market_context | legality_evidence, legal_confidence_score | Evidence-based | none / **none** | (synthesis) — **not consumed by rent_stabilization** | Silo — rent modules don't read this | 3/3/4/5/1 | **Fix** — must feed rent_x_risk bridge; output is stranded today |

---

## Legacy / Internal Modules (wrapped by scoped runners; not in registry)

These are not independently exposed to the orchestrator but are composed inside scoped runners. Listed here so the inventory is complete.

| Module | File | Wrapped By | Keep/Fix/Cut |
|---|---|---|---|
| CurrentValueModule | [modules/current_value.py](../briarwood/modules/current_value.py) | valuation | Keep |
| ComparableSalesModule | [modules/comparable_sales.py](../briarwood/modules/comparable_sales.py) | valuation, unit_income_offset | Keep |
| MarketValueHistory | [modules/market_value_history.py](../briarwood/modules/market_value_history.py) | valuation | Keep |
| IncomeSupportModule | [modules/income_support.py](../briarwood/modules/income_support.py) | valuation, rental_option | Keep |
| HybridValueModule | [modules/hybrid_value.py](../briarwood/modules/hybrid_value.py) | valuation | Keep |
| CostValuationModule | [modules/cost_valuation.py](../briarwood/modules/cost_valuation.py) | carry_cost | Keep |
| RiskConstraintsModule | [modules/risk_constraints.py](../briarwood/modules/risk_constraints.py) | risk_model | **Fix** — widen inputs |
| PropertyDataQualityModule | [modules/property_data_quality.py](../briarwood/modules/property_data_quality.py) | confidence, legal_confidence | **Fix** — hardcoded 0.72/0.48 thresholds |
| RentalEaseModule | [modules/rental_ease.py](../briarwood/modules/rental_ease.py) | rental_option, rent_stabilization | Keep |
| TownCountyOutlookModule | [modules/town_county_outlook.py](../briarwood/modules/town_county_outlook.py) | rent_stabilization | Keep — feeds town_x_scenario bridge |
| RenovationScenarioModule | [modules/renovation_scenario.py](../briarwood/modules/renovation_scenario.py) | renovation_impact | Keep |
| BullBaseBearModule | [modules/bull_base_bear.py](../briarwood/modules/bull_base_bear.py) | resale_scenario | Keep |
| LocalIntelligenceModule | [modules/local_intelligence.py](../briarwood/modules/local_intelligence.py) | legal_confidence | Keep |
| ScarcitySupport | [modules/scarcity_support.py](../briarwood/modules/scarcity_support.py) | (varies) | Keep — feeds valuation_x_town bridge |
| LiquiditySignal | [modules/liquidity_signal.py](../briarwood/modules/liquidity_signal.py) | valuation (market_context) | Keep — feeds valuation_x_risk bridge |
| MarketMomentumSignal | [modules/market_momentum_signal.py](../briarwood/modules/market_momentum_signal.py) | (varies) | Keep |
| MarketAnalyzer | [modules/market_analyzer.py](../briarwood/modules/market_analyzer.py) | (varies) | Review — scope unclear |
| LocationIntelligence | [modules/location_intelligence.py](../briarwood/modules/location_intelligence.py) | (varies) | Review |
| LocationContext | [modules/location_context.py](../briarwood/modules/location_context.py) | (varies) | Review |
| PropertySnapshot | [modules/property_snapshot.py](../briarwood/modules/property_snapshot.py) | (varies) | Review |
| TeardownScenario | [modules/teardown_scenario.py](../briarwood/modules/teardown_scenario.py) | (unwired) | **Cut or wire** — currently orphaned |
| TownAggregationDiagnostics | [modules/town_aggregation_diagnostics.py](../briarwood/modules/town_aggregation_diagnostics.py) | (diagnostic) | Keep as diagnostic |
| ValueDrivers | [modules/value_drivers.py](../briarwood/modules/value_drivers.py) | (varies) | Review |
| ValueFinder | [modules/value_finder.py](../briarwood/modules/value_finder.py) | (varies) | Review |

---

## Summary

**Keep:** 8 scoped + several legacy
**Fix:** 7 scoped (valuation, carry_cost, rent_stabilization, rental_option, risk_model, confidence, resale_scenario, hold_to_rent, legal_confidence) + 2 legacy
**Cut / Review:** teardown_scenario (orphaned); 6 legacy modules with unclear scope

**Critical silos to break in Phase 4:**
1. **risk_model ← valuation, scenario, rental_option** — declared but unused
2. **rent_stabilization ← legal_confidence** — legal output is stranded
3. **resale_scenario ← town, risk** — scenarios ignore market regime and execution risk
4. **valuation ← town scarcity, liquidity** — no premium-band adjustment
5. **confidence → gate** — collects priors but never gates synthesis

**Confidence method inventory:**
- Real evidence-based: legal_confidence
- Composite min(): hold_to_rent, arv_model, margin_sensitivity, rent_stabilization
- Hardcoded thresholds: confidence, property_data_quality
- Static / absent: valuation, carry_cost, resale_scenario, renovation_impact, risk_model

**Interaction readiness scores average 1.9/5** → this confirms the silo hypothesis and validates Phase 4 as the critical unlock.

---

## Next Steps

- **Phase 2:** Build `tests/modules/<module>.py` harness per scoped module using the Spec §7 audit template. Start with the five "Fix" modules with lowest interaction_readiness scores (risk_model, valuation, rent_stabilization, legal_confidence, resale_scenario).
- **Phase 3:** Address hardcoded confidence in property_data_quality and listing intake.
- **Phase 4:** Wire the 5 critical silo-breaking bridges above.

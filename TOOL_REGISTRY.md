# Briarwood — Tool Registry (DRAFT)

Specification for each specialty model as a tool an orchestrating LLM could invoke. Draft form — see [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 2 for the machinery that would consume this registry.

Organization: grouped by **intent cluster** ("what question is this tool for?"), not by centrality. Within each cluster, scoped-registry tools come first (no blockers); legacy tools come second with `blockers_for_tool_use` flags explaining why they can't be called in isolation today.

Each entry is a YAML block with: `name`, `path`, `entry`, `intent_fit` (matching `AnswerType` values from [briarwood/agent/router.py:40-54](briarwood/agent/router.py#L40-L54)), `inputs`, `outputs`, `depends_on`, `invariants`, `blockers_for_tool_use`, `notes`.

---

## Valuation cluster

*"What is it worth right now?"*

### valuation

```yaml
name: valuation
path: briarwood/modules/valuation.py
entry: run_valuation(context: ExecutionContext) -> dict
intent_fit: [DECISION, BROWSE, LOOKUP, EDGE]
inputs:
  property_data: dict        # required — facts about the property
outputs:
  briarwood_current_value: float     # fair-value estimate in USD
  mispricing_pct: float              # signed, (ask - bw_value) / bw_value
  pricing_view: str                  # "fair" | "undervalued" | "overvalued" | "unavailable"
  confidence: float                  # 0-1
depends_on: []                       # root-level scoped module
invariants:
  - confidence always in [0, 1]
  - returns error payload with pricing_view="unavailable" when facts are sparse or contradictory
  - applies macro nudge on hpi_momentum capped at 3%
blockers_for_tool_use: []
notes:
  - Internally runs CurrentValueModule which fans out to comparable_sales, market_value_history, income_support, hybrid_value
  - Pricing view thresholds live in module, not config
```

### property_data_quality

```yaml
name: property_data_quality
path: briarwood/modules/property_data_quality.py
entry: PropertyDataQualityModule().run(property_input) -> ModuleResult
intent_fit: [DECISION, BROWSE, LOOKUP]        # implicitly every intent, via confidence
inputs:
  property_input: PropertyInput    # required
outputs:
  completeness_score: float        # 0-1
  contradiction_flags: list[str]   # field-level issues
  confidence: float                # 0-1, 1.0 if clean, 0.0 if major issues
depends_on: []
invariants:
  - completeness_score in [0, 1]
  - contradiction_flags is never None (empty list if clean)
blockers_for_tool_use: []                     # callable standalone, but not in scoped registry today
notes:
  - Used by confidence module as an anchor
  - Currently invoked inside orchestrator, not exposed as scoped registry entry
```

### current_value

```yaml
name: current_value
path: briarwood/modules/current_value.py
entry: CurrentValueModule().run(property_input, prior_results=None) -> ModuleResult
intent_fit: [DECISION, BROWSE, LOOKUP]
inputs:
  property_input: PropertyInput                    # required
  prior_results: dict[str, ModuleResult] | None    # optional; pre-computed upstream modules to avoid recomputation
outputs:
  briarwood_current_value: float
  mispricing_pct: float
  pricing_view: str                # "fair" | "undervalued" | "overvalued" | "unavailable"
  confidence: float
depends_on: [comparable_sales, market_value_history, income_support, hybrid_value]
invariants:
  - confidence in [0, 1]
blockers_for_tool_use:
  - Not in scoped execution registry. Consumed by scoped `valuation` wrapper, which is the callable entry.
  - prior_results parameter is internal caching; exposing it as a tool input violates the orchestrator's cache semantics.
notes:
  - Would need a scoped wrapper like briarwood/modules/valuation.py to become independently callable
```

### comparable_sales

```yaml
name: comparable_sales
path: briarwood/modules/comparable_sales.py
entry: ComparableSalesModule().run(property_input) -> ModuleResult
intent_fit: [DECISION, BROWSE, COMPARISON, LOOKUP]
inputs:
  property_input: PropertyInput    # required
outputs:
  comparable_value: float
  comp_count: int
  comp_confidence: float
  direct_value_range: object       # {low, midpoint, high}
  comps_used: list[AdjustedComparable]
depends_on: []                     # but internally calls briarwood/agents/comparable_sales
invariants:
  - comp_count >= 0
  - comps_used is a list (possibly empty)
  - applies market friction discount for nonstandard products via is_nonstandard_product()
blockers_for_tool_use:
  - Not in scoped execution registry. See briarwood/claims/pipeline.py:62-88 for the post-hoc graft pattern currently used to make this callable in the claims path.
  - Comment in claims/pipeline.py: "The scoped execution registry doesn't surface comparable_sales as a top-level module."
  - Hybrid detection (_detect_hybrid_valuation, _build_hybrid_request) is baked into the run path; cross-tool composition with hybrid_value is implicit.
notes:
  - Data source: data/comps/sales_comps.json
  - Hardcoded: 15% sqft tolerance for comp matching
  - Cross-town comps TODO flagged in base_comp_selector.py
  - Renovation premium TODO: estimate_comp_renovation_premium() not yet fed through
  - Most architecturally load-bearing model not in the scoped registry — promotion is the highest-value Layer 2 unblock
```

### hybrid_value

```yaml
name: hybrid_value
path: briarwood/modules/hybrid_value.py
entry: HybridValueModule().run(property_input, prior_results) -> ModuleResult
intent_fit: [DECISION, BROWSE]         # only meaningful for multi-unit / primary+ADU properties
inputs:
  property_input: PropertyInput
  prior_results: dict                  # expects comparable_sales and income_support outputs
outputs:
  is_hybrid: bool
  reason: str
  detected_primary_structure_type: str
  detected_accessory_income_type: str
  primary_house_value: float
  rear_income_value: float             # capitalized rent
  rear_income_method_used: str
  optionality_premium_value: float
  low_case_hybrid_value: float
  base_case_hybrid_value: float
  high_case_hybrid_value: float
  market_friction_discount: float
  market_feedback_adjustment: float
  confidence: float
depends_on: [comparable_sales, income_support]
invariants:
  - is_hybrid=False means all valuation fields may be zero; orchestrator should not use them
  - cap rate fixed at _DEFAULT_ADU_CAP_RATE = 0.08, expense ratio _ADU_EXPENSE_RATIO = 0.30
blockers_for_tool_use:
  - Not in scoped execution registry.
  - prior_results is required — tool cannot run in isolation without upstream comparable_sales and income_support already having fired.
notes:
  - Applies evaluate_market_feedback() and market_friction_discount() via valuation_constraints
```

### ownership_economics

```yaml
name: ownership_economics
path: briarwood/modules/ownership_economics.py
entry: OwnershipEconomicsModule().run(property_input) -> ModuleResult
intent_fit: [DECISION, STRATEGY, RENT_LOOKUP]   # ownership-carry underwriting, consumed via scoped carry_cost
inputs:
  property_input: PropertyInput
outputs:                                         # emitted via ValuationOutput.to_metrics (briarwood/schemas.py:503)
  monthly_total_cost: float
  monthly_cash_flow: float
  monthly_mortgage_payment: float
  monthly_taxes: float
  monthly_insurance: float
  monthly_hoa: float
  monthly_maintenance_reserve: float
  annual_noi: float
  cap_rate: float
  gross_yield: float
  dscr: float
  cash_on_cash_return: float
  loan_amount: float
  down_payment_amount: float
  effective_monthly_rent: float
  confidence: float
depends_on: []
invariants:
  - Computes ownership-carry underwriting metrics (not replacement cost / land value).
blockers_for_tool_use:
  - Not in scoped execution registry directly; consumed by the scoped `carry_cost` wrapper at briarwood/modules/carry_cost.py.
notes:
  - Renamed from CostValuationModule (cost_valuation.py) in Handoff 2a Piece 5A (2026-04-24). Previous audit framing ("replacement-cost approach, $400/sqft default, teardown/redevelopment fallback") described a different module that does not exist in the codebase; see DECISIONS.md "Replacement-cost tool does not exist" (2026-04-24).
  - Settings dataclass is still named CostValuationSettings in briarwood/settings.py; a future sweep may rename it.
```

### market_value_history

```yaml
name: market_value_history
path: briarwood/modules/market_value_history.py
entry: MarketValueHistoryModule().run(property_input) -> ModuleResult
intent_fit: [DECISION, BROWSE, LOOKUP, RESEARCH]
inputs:
  property_input: PropertyInput
outputs:
  history_points: list[HistoryPoint]   # {year, estimated_value, last_sale_price, confidence}
  current_value_synthesized: float     # from trajectory
depends_on: []
invariants:
  - history_points sorted by year ascending
blockers_for_tool_use:
  - Not in scoped execution registry.
notes:
  - Consumed by current_value as trend context
```

---

## Scenario cluster

*"What could happen over time?"*

### resale_scenario

```yaml
name: resale_scenario
path: briarwood/modules/resale_scenario_scoped.py
entry: run_resale_scenario(context: ExecutionContext) -> dict
intent_fit: [DECISION, PROJECTION, STRATEGY]
inputs:
  property_data: dict
  assumptions:
    hold_period_years: int        # required
outputs:
  ask_price: float
  bull_case_value: float
  base_case_value: float
  bear_case_value: float
  spread: float                   # bull - bear
  confidence_by_scenario: dict
depends_on: [valuation, carry_cost, town_development_index]
invariants:
  - bear_case_value <= base_case_value <= bull_case_value
  - spread >= 0
blockers_for_tool_use: []
notes:
  - Internally runs BullBaseBearModule which fans out to current_value, market_value_history, town_county_outlook, risk_constraints, scarcity_support
  - Uses town_development_index velocity to project appreciation
```

### opportunity_cost

```yaml
name: opportunity_cost
path: briarwood/modules/opportunity_cost.py
entry: run_opportunity_cost(context: ExecutionContext) -> dict
intent_fit: [DECISION, PROJECTION, STRATEGY]
inputs:
  property_data: dict
  assumptions:
    hold_period_years: int
outputs:
  property_terminal_value: float
  passive_benchmark_return: float       # T-bill 5Y
  sp500_projected_terminal_value: float
  outperformance_vs_tbill: float
  outperformance_vs_sp500: float
depends_on: [valuation, resale_scenario]
invariants:
  - Appreciation-only; does NOT include cash flow
blockers_for_tool_use: []
notes:
  - Benchmarks: T-bill 5Y, S&P 500 historical
```

### bull_base_bear

```yaml
name: bull_base_bear
path: briarwood/modules/bull_base_bear.py
entry: BullBaseBearModule().run(property_input, prior_results) -> ModuleResult
intent_fit: [DECISION, PROJECTION]
inputs:
  property_input: PropertyInput
  prior_results: dict              # expects current_value, market_value_history, town_county_outlook, risk_constraints, scarcity_support
outputs:
  scenario_output:
    ask_price: float
    bull_case_value: float
    base_case_value: float
    bear_case_value: float
    spread: float
depends_on: [current_value, market_value_history, town_county_outlook, risk_constraints, scarcity_support]
invariants:
  - bear <= base <= bull
blockers_for_tool_use:
  - Not in scoped execution registry (scoped resale_scenario is the wrapper).
  - prior_results required — cannot run in isolation.
notes:
  - BullBaseBearSettings from decision_model/scoring_config
```

### scarcity_support

```yaml
name: scarcity_support
path: briarwood/modules/scarcity_support.py
entry: ScarcitySupportModule().run(property_input) -> ModuleResult
intent_fit: [DECISION, EDGE, RISK]
inputs:
  property_input: PropertyInput
outputs:
  scarcity_support_score: float    # 0-1
  confidence: float
  supply_classification: str       # "scarce" | "moderate" | "abundant"
  premium_attribution: dict        # {location, condition, size, unique_feature}
depends_on: []
invariants:
  - scarcity_support_score in [0, 1]
blockers_for_tool_use:
  - Not in scoped execution registry.
notes:
  - Signals: inventory depth, price momentum, DOM vs cohort
```

---

## Rent & income cluster

*"What does it rent for, and does the rent support the carry?"*

### carry_cost

```yaml
name: carry_cost
path: briarwood/modules/carry_cost.py
entry: run_carry_cost(context: ExecutionContext) -> dict
intent_fit: [DECISION, RENT_LOOKUP, STRATEGY, PROJECTION]
inputs:
  property_data: dict
  assumptions:
    down_payment_percent: float
    interest_rate: float
    loan_term_years: int
outputs:
  monthly_payment: float
  annual_property_tax: float
  total_annual_cost: float
  cash_flow_impact: float
  confidence: float
depends_on: []
invariants:
  - total_annual_cost > 0 if financing assumptions are valid
blockers_for_tool_use: []
notes:
  - Dependency for resale_scenario, hold_to_rent, margin_sensitivity, unit_income_offset
```

### rental_option

```yaml
name: rental_option
path: briarwood/modules/rental_option_scoped.py
entry: run_rental_option(context: ExecutionContext) -> dict
intent_fit: [RENT_LOOKUP, STRATEGY]
inputs:
  property_data: dict
outputs:                              # emitted via RentalEase + IncomeSupport composition; no `rental_viability_score` or `rental_viability_metrics` field exists
  rental_ease_label: str              # "easy" | "moderate" | "difficult" | "unavailable"
  liquidity_score: float
  demand_depth_score: float
  rent_support_score: float
  structural_support_score: float
  estimated_days_to_rent: int
  scarcity_support_score: float
  zillow_context_used: bool
  extra_data:
    income_support: dict               # from IncomeSupportModule
    macro_nudge: dict                  # employment macro signal
  confidence: float
depends_on: []
invariants: []
blockers_for_tool_use: []
notes:
  - Thin scoped wrapper around RentalEaseModule + IncomeSupportModule + employment macro nudge.
  - Historically declared depends_on=["valuation"] but never consumed valuation output; dependency removed in Handoff 2a Piece 4 (2026-04-24).
```

### rent_stabilization

```yaml
name: rent_stabilization
path: briarwood/modules/rent_stabilization.py
entry: run_rent_stabilization(context: ExecutionContext) -> dict
intent_fit: [RENT_LOOKUP, RISK, STRATEGY]
inputs:
  property_data: dict
outputs:
  rental_ease_label: str           # "easy" | "moderate" | "difficult" | "unavailable"
  rent_support_score: float
  confidence: float
depends_on: []
invariants:
  - rent_support_score in [0, 1]
blockers_for_tool_use: []
notes:
  - Internally runs rental_ease, town_county_outlook, scarcity_support
  - Reads Zillow ZORI/ZORDI/ZORF context
```

### hold_to_rent

```yaml
name: hold_to_rent
path: briarwood/modules/hold_to_rent.py
entry: run_hold_to_rent(context: ExecutionContext) -> dict
intent_fit: [STRATEGY, PROJECTION]
inputs:
  property_data: dict
  assumptions: dict
outputs:                              # composite wrapper — no `hold_to_rent_viability` or `cash_flow_metrics` field exists
  hold_path_snapshot:
    monthly_cash_flow: float
    cap_rate: float
    rental_ease_label: str
    rental_ease_score: float
    estimated_days_to_rent: int
  carry_cost: dict                    # nested sub-dict (summary, metrics, confidence)
  rent_stabilization: dict            # nested sub-dict
  confidence: float                   # min(carry_cost.confidence, rent_stabilization.confidence)
depends_on: [carry_cost, rent_stabilization]
invariants:
  - Pure composite — introduces no new math, packages prior outputs.
blockers_for_tool_use: []
notes:
  - Missing or degraded (mode in {"error","fallback"}) priors → module_payload_from_missing_prior (Handoff 2a Piece 3).
```

### unit_income_offset

```yaml
name: unit_income_offset
path: briarwood/modules/unit_income_offset.py
entry: run_unit_income_offset(context: ExecutionContext) -> dict
intent_fit: [DECISION, STRATEGY, EDGE]       # only meaningful with ADU or multi-unit
inputs:
  property_data: dict
  assumptions: dict
outputs:                                     # no `offset_monthly_income` / `offset_annual_income` / `cap_rate_assumed` field exists
  offset_snapshot:
    has_accessory_unit_signal: bool
    additional_unit_income_value: float      # capitalized value, NOT a monthly/annual income
    additional_unit_count: int
    back_house_monthly_rent: float
    unit_rents: list[float]
    monthly_total_cost: float                # echoed from carry_cost
    monthly_cash_flow: float                 # echoed from carry_cost
  comparable_sales: dict                     # nested sub-dict (summary, metrics, confidence)
  confidence: float
depends_on: [carry_cost]                     # internally runs comparable_sales for ADU/multi-unit comps
invariants:
  - _DEFAULT_ADU_CAP_RATE = 0.08 and _ADU_EXPENSE_RATIO = 0.30 live in briarwood/modules/comparable_sales.py (lines 28, 32). They are consumed transitively via ComparableSalesModule's additional_unit_income_value decomposition, not defined in unit_income_offset itself.
blockers_for_tool_use: []
notes:
  - Returns low confidence when property has no detectable accessory unit
```

### income_support

```yaml
name: income_support
path: briarwood/modules/income_support.py
entry: IncomeSupportModule().run(property_input) -> ModuleResult
intent_fit: [RENT_LOOKUP, DECISION, STRATEGY]
inputs:
  property_input: PropertyInput
outputs:
  effective_monthly_rent: float
  rent_source_type: str            # "actual" | "estimated" | "fallback"
  gross_monthly_cost: float
  income_support_ratio: float
  price_to_rent: float
  rent_support_classification: str
  monthly_cash_flow: float
  downside_burden: float
  carrying_cost_complete: bool
  financing_complete: bool
  confidence: float
depends_on: []
invariants:
  - confidence 0.0 with rent_source_type="unavailable" when purchase_price missing
blockers_for_tool_use:
  - Not in scoped execution registry.
  - Requires down_payment_percent, interest_rate, loan_term_years in property_input — partial inputs return a degraded result.
notes:
  - Backed by briarwood/agents/income/IncomeAgent
  - RentContextAgent parses unit rents; UnitRentEstimator estimates when absent
```

### rental_ease

```yaml
name: rental_ease
path: briarwood/modules/rental_ease.py
entry: RentalEaseModule().run(property_input) -> ModuleResult
intent_fit: [RENT_LOOKUP, STRATEGY]
inputs:
  property_input: PropertyInput
outputs:
  rental_ease_score: float         # 1-5
  rental_ease_label: str           # "easy" | "moderate" | "difficult" | "unavailable"
  liquidity_score: float
  demand_depth_score: float
  rent_support_score: float
  structural_support_score: float
  estimated_days_to_rent: int
  zillow_context_used: bool
  confidence: float
depends_on: [income_support, town_county_outlook, scarcity_support]
invariants:
  - rental_ease_label "unavailable" when income_support can't produce a usable payload
blockers_for_tool_use:
  - Not in scoped execution registry.
notes:
  - Uses FileBackedZillowRentContextProvider (ZORI, ZORDI, ZORF)
```

---

## Renovation cluster

*"What happens if I renovate or redevelop?"*

### renovation_impact

```yaml
name: renovation_impact
path: briarwood/modules/renovation_impact_scoped.py
entry: run_renovation_impact(context: ExecutionContext) -> dict
intent_fit: [STRATEGY, PROJECTION, DECISION]
inputs:
  property_data: dict
  assumptions:
    repair_capex_budget: float
    renovation_scenario: dict
outputs:                                 # BCV-delta + ROI calculator; no `renovation_scope` / `estimated_cost_range` / `timeline_estimate` field exists
  enabled: bool
  renovation_budget: float
  current_bcv: float
  renovated_bcv: float                   # the conceptual "estimated ARV"
  gross_value_creation: float
  net_value_creation: float
  roi_pct: float
  cost_per_dollar_of_value: float
  condition_change: str
  sqft_change: str
  comp_range_text: str
  confidence: float
  warnings: list[str]
  summary: str
depends_on: []
invariants:
  - When renovation_scenario is absent/disabled, returns a blocked result with enabled=False (not an exception).
blockers_for_tool_use: []
notes:
  - Wraps RenovationScenarioModule, which runs ComparableSalesModule and CurrentValueModule against a hypothetical renovated PropertyInput.
  - Internal exceptions return module_payload_from_error fallback (Handoff 2a Piece 3).
```

### arv_model

```yaml
name: arv_model
path: briarwood/modules/arv_model_scoped.py
entry: run_arv_model(context: ExecutionContext) -> dict
intent_fit: [STRATEGY, PROJECTION, DECISION]
inputs:
  property_data: dict
  assumptions: dict
outputs:                                 # pure composite — no `estimated_arv` / `arv_confidence` / `comparable_arv_support` / `component_cost_deltas` field exists
  arv_snapshot:
    current_bcv: float
    renovated_bcv: float                 # the conceptual after-repair value
    renovation_budget: float
    gross_value_creation: float
    net_value_creation: float
    roi_pct: float
    condition_change: str
    sqft_change: str
    comp_range_text: str
  valuation: dict                        # echoed sub-dict from prior output
  renovation_impact: dict                # echoed sub-dict from prior output
  confidence: float                      # min(valuation.confidence, renovation_impact.confidence)
  warnings: list[str]
depends_on: [valuation, renovation_impact]
invariants:
  - Does NOT call comparable_sales directly — that happens transitively inside renovation_impact → renovation_scenario.
blockers_for_tool_use: []
notes:
  - Missing or degraded priors → module_payload_from_missing_prior with extra_data={"arv_snapshot": {}} (Handoff 2a Piece 3).
```

### margin_sensitivity

```yaml
name: margin_sensitivity
path: briarwood/modules/margin_sensitivity_scoped.py
entry: run_margin_sensitivity(context: ExecutionContext) -> dict
intent_fit: [STRATEGY, RISK, DECISION]
inputs:
  property_data: dict
  assumptions: dict
outputs:                                 # no `margin_at_base_case` / `margin_at_90pct_arv` / `margin_at_110pct_cost` / `break_even_thresholds` field exists
  sensitivity_scenarios:                 # six labeled scenarios
    - label: str                         # "Base case" | "Budget +20%" | "Budget +40%" | "Value -10%" | "Value -20%" | "Budget +20%, Value -10%"
      renovation_budget: float
      gross_value_creation: float
      hold_cost: float
      net_profit: float
      roi_pct: float
      profitable: bool
  margin_snapshot:
    renovated_bcv: float
    current_bcv: float
    renovation_budget: float
    gross_value_creation: float
    monthly_carry: float
    holding_months: int                  # hardcoded 6
    total_hold_cost: float
    breakeven_budget: float
    budget_overrun_margin_pct: float
    base_roi_pct: float
  confidence: float                      # min across arv_model, renovation_impact, carry_cost
  warnings: list[str]
depends_on: [arv_model, renovation_impact, carry_cost]
invariants:
  - Six-scenario table; budget-overrun and value-miss stress.
blockers_for_tool_use: []
notes:
  - Missing or degraded priors → module_payload_from_missing_prior (Handoff 2a Piece 3).
  - Reads monthly_carry from carry_cost via the authoritative key `monthly_total_cost` at briarwood/schemas.py:503 (fix landed 2026-04-24 in Handoff 2a Piece 2).
```

---

## Risk cluster

*"What could go wrong?"*

### risk_model

```yaml
name: risk_model
path: briarwood/modules/risk_model.py
entry: run_risk_model(context: ExecutionContext) -> dict
intent_fit: [RISK, DECISION, EDGE]
inputs:
  property_data: dict
outputs:
  confidence: float                    # adjusted by valuation premium and legal certainty
  valuation_bridge:
    fair_value: float
    listed_price: float
    premium_pct: float
    flag: str
  legal_confidence_signal: float
  warnings: list[str]
depends_on: [valuation, legal_confidence]    # legal_confidence added in Handoff 2a Piece 4 (2026-04-24); previously risk_model read legal_confidence without declaring it.
invariants:
  - Overpriced (premium_pct > 0.15) reduces confidence by 0.05
  - Underpriced (premium_pct < -0.10) increases confidence by 0.05
  - legal_confidence < 0.5 reduces confidence by 0.08
  - applies macro nudge on liquidity capped at 4%
blockers_for_tool_use: []
notes:
  - Hardcoded thresholds: OVERPRICED_THRESHOLD=0.15, UNDERPRICED_THRESHOLD=-0.10
```

### legal_confidence

```yaml
name: legal_confidence
path: briarwood/modules/legal_confidence.py
entry: run_legal_confidence(context: ExecutionContext) -> dict
intent_fit: [RISK, DECISION, STRATEGY]
inputs:
  property_data: dict              # zoning, local documents, deed restrictions, adu_type, has_back_house, additional_units
outputs:                           # evidence-coverage signal; NOT a legal classifier (no permission_flags / restriction_flags fields)
  legality_evidence:
    has_accessory_signal: bool
    adu_type: str | None
    has_back_house: bool | None
    additional_unit_count: int
    zone_flags: dict
    local_document_count: int
    multi_unit_allowed: bool | None
  data_quality:
    summary: str
    metrics: dict
    confidence: float
  local_intelligence: dict | None  # present only when property_input.local_documents is non-empty
  summary: str
  confidence: float                # 0-1; min(data_quality, local) with floor 0.55 if zone_flags present, cap 0.65 if no accessory signal
depends_on: []
invariants:
  - Below 0.5 dampens risk_model confidence by 0.08 (risk_model declares legal_confidence in depends_on as of Handoff 2a Piece 4).
blockers_for_tool_use: []
notes:
  - Wraps PropertyDataQualityModule and (gated on local_documents presence) LocalIntelligenceModule.
  - Internal exceptions return module_payload_from_error fallback (Handoff 2a Piece 3).
```

### risk_constraints

```yaml
name: risk_constraints
path: briarwood/modules/risk_constraints.py
entry: RiskConstraintsModule().run(property_input) -> ModuleResult
intent_fit: [RISK, DECISION]
inputs:
  property_input: PropertyInput
outputs:
  confidence: float
  risk_flags: list[str]            # condition, title, flood, zoning gaps
  downside_scenario_estimate: float
depends_on: []
invariants: []
blockers_for_tool_use:
  - Not in scoped execution registry.
  - Primarily consumed by bull_base_bear to cap downside scenario.
notes:
  - RiskSettings from decision_model/scoring_config
```

### confidence

```yaml
name: confidence
path: briarwood/modules/confidence.py
entry: run_confidence(context: ExecutionContext) -> dict
intent_fit: [DECISION, RISK]         # rollup; every intent that needs a confidence band
inputs:
  property_data: dict
  prior_outputs: dict              # all upstream module outputs
outputs:                           # top-level ModulePayload fields (no `overall_confidence` / `component_breakdown` field name exists)
  confidence: float                # 0-1 — top-level ModulePayload.confidence
  confidence_band: str             # "High confidence" | "Moderate confidence" | "Low confidence" | "Speculative"
  extra_data:                      # component breakdown lives here, not at top level
    field_completeness: float
    comp_quality: float
    model_agreement: float
    scenario_fragility: float
    legal_certainty: float
    estimated_reliance: float
    contradiction_count: int
    aggregated_prior_confidence: float
    combined_confidence: float
    data_quality_confidence: float
    prior_module_confidences: dict[str, float]
depends_on: []                     # but consumes prior_outputs from every other module
invariants:
  - confidence in [0, 1]
  - confidence_band thresholds at briarwood/modules/scoped_common.py:152 — "High confidence" >= 0.75, "Moderate" >= 0.55, "Low" >= 0.3, else "Speculative".
blockers_for_tool_use: []
notes:
  - Runs last in the DAG, after all other modules.
  - Weights loaded from briarwood.pipeline.triage.load_model_weights().
  - Internal exceptions return module_payload_from_error fallback (Handoff 2a Piece 3).
```

---

## Location / town cluster

*"What's the market context?"*

### town_development_index

```yaml
name: town_development_index
path: briarwood/modules/town_development_index.py
entry: run_town_development_index(context: ExecutionContext) -> dict
intent_fit: [RESEARCH, STRATEGY, DECISION, MICRO_LOCATION]
inputs:
  property_data: dict              # needs town, state
outputs:
  approval_rate: float             # 0-1
  activity_volume: float           # approvals/month
  substantive_changes: float       # count
  restrictive_signals: float       # count
  contention: float                # 0-1, opposition density
  development_velocity: float      # 0-1, composite
  explanation: str
depends_on: []
invariants:
  - All scores in [0, 1] or non-negative
blockers_for_tool_use: []
notes:
  - Reads 12-month rolling window from JsonMinutesStore
  - Time decay: exp(-months_ago / 6.0) half-life
  - Target volume: 2.0 decisions/month
  - Max nudge downstream: 4% (DEFAULT_MAX_NUDGE)
```

### town_county_outlook

```yaml
name: town_county_outlook
path: briarwood/modules/town_county_outlook.py
entry: TownCountyOutlookModule().run(property_input) -> ModuleResult
intent_fit: [RESEARCH, DECISION, STRATEGY, MICRO_LOCATION]
inputs:
  property_input: PropertyInput
outputs:
  town_county_score: float
  town_county_confidence: float
  liquidity_view: str              # "strong" | "moderate" | "weak"
  narrative: str
depends_on: []
invariants: []
blockers_for_tool_use:
  - Not in scoped execution registry.
notes:
  - Backed by briarwood/agents/town_county/TownCountyAgent
  - Data: listings, DOM, inventory, tax, demographics, school ratings
```

### location_intelligence

```yaml
name: location_intelligence
path: briarwood/modules/location_intelligence.py
entry: LocationIntelligenceModule().run(property_input) -> ModuleResult
intent_fit: [MICRO_LOCATION, EDGE]
inputs:
  property_input: PropertyInput
outputs:
  walkability_score: float
  transit_score: float
  amenities_score: float
  desirability_index: float
depends_on: []
invariants: []
blockers_for_tool_use:
  - Not in scoped execution registry.
notes:
  - Signals relative to town cohort
```

### local_intelligence

```yaml
name: local_intelligence
path: briarwood/modules/local_intelligence.py
entry: LocalIntelligenceModule().run(property_input) -> ModuleResult
intent_fit: [RESEARCH, RISK, EDGE]
inputs:
  property_input: PropertyInput
outputs:
  risk_flags: list[str]
  opportunity_signals: list[str]
  zoning_clarity: float
depends_on: []
invariants: []
blockers_for_tool_use:
  - Not in scoped execution registry.
  - LLM extraction currently uses a direct OpenAI adapter rather than the shared LLMClient / cost-guard / telemetry surface.
notes:
  - Data: news, planning documents, deed restrictions, HOA rules
  - Uses the only LLM-backed extraction (OpenAILocalIntelligenceExtractor via gpt-5-mini)
  - Before LLM-driven orchestration, route extraction through the shared LLM boundary or document why this tool remains a special-case extractor.
```

---

## Classification / value-finding cluster

*"What kind of opportunity is this?"*

### strategy_classifier

```yaml
name: strategy_classifier
path: briarwood/modules/strategy_classifier.py
entry: run_strategy_classifier(context: ExecutionContext) -> dict
intent_fit: [STRATEGY, DECISION, BROWSE]
inputs:
  property_data: dict
outputs:
  strategy: PropertyStrategyType       # owner_occ_sfh | owner_occ_duplex | owner_occ_with_adu | pure_rental | value_add_sfh | redevelopment_play | scarcity_hold | unknown
  rationale: list[str]
  confidence: float
  rule_fired: str                      # which heuristic matched
  candidates: list[PropertyStrategyType]
depends_on: []
invariants:
  - Deterministic; no LLM
  - confidence in [0, 1]
blockers_for_tool_use: []
notes:
  - Runs at Layer 2 (post-intake, pre-domain models) in current orchestration
  - Rule-based; extensively documented inline
```

### value_finder

```yaml
name: value_finder
path: briarwood/modules/value_finder.py
entry: analyze_value_finder(asking_price, briarwood_value, comp_median, ...) -> ValueFinderOutput
alt_entry: analyze_property_value_finder(report: AnalysisReport) -> PropertyValueFinderOutput
intent_fit: [DECISION, BROWSE, EDGE]
inputs:
  asking_price: float
  briarwood_value: float
  comp_median: float
  dom_history: dict
  cut_history: dict
outputs:
  value_gap_pct: float                 # asking vs briarwood
  comp_gap_pct: float                  # asking vs median comp
  market_friction_score: float
  cut_pressure_score: float
  opportunity_signal: str              # "strong" | "moderate" | "weak"
  pricing_posture: str                 # "overpriced" | "fair" | "underpriced"
  dom_signal: str
  evidence_strength: str               # "high" | "moderate" | "low"
  confidence_note: str
depends_on: []                         # inputs derived from current_value, comparable_sales, market history
invariants:
  - Deterministic; no LLM
blockers_for_tool_use:
  - Not in scoped execution registry.
  - Signature takes already-computed values, not a property; effectively a derivation function, not a standalone tool.
notes:
  - NOT the same as value_scout (briarwood/value_scout/). This is deterministic value-gap analysis; value_scout does pattern-based insight surfacing.
  - Often confused with value_scout in dispatch code
```

---

## Non-production

Documented but not currently invoked in production synthesis paths.

### decision_model/calculate_final_score

```yaml
name: decision_model_final_score
path: briarwood/decision_model/scoring.py
entry: calculate_final_score(report: AnalysisReport) -> FinalScore
intent_fit: [DECISION]
inputs:
  report: AnalysisReport               # legacy structure with all module results + property input
outputs:
  score: float                         # 1.0 - 5.0
  tier: str                            # "Buy" | "Neutral" | "Avoid"
  action: str
  narrative: str
  category_scores:
    price_context: CategoryScore       # 15% weight
    economic_support: CategoryScore    # 30%
    optionality: CategoryScore         # 20%
    market_position: CategoryScore     # 20%
    risk_layer: CategoryScore          # 15%
depends_on: [current_value, comparable_sales, carry_cost, income_support, hybrid_value, town_county_outlook, scarcity_support, risk_constraints, legal_confidence]
invariants:
  - score in [1.0, 5.0]
  - tier: score >= 3.30 Buy, >= 2.50 Neutral, < 2.50 Avoid
blockers_for_tool_use:
  - DEFINED BUT NOT INVOKED in current production synthesis.
  - Current synthesis (briarwood/synthesis/structured.py) uses different scoring logic.
  - Hardcoded $400/sqft replacement cost (TODO: make geography/property-type aware).
notes:
  - Live code, dead paths. Either wire in or remove.
  - Recommendations engine (briarwood/recommendations.py) is still used for tier normalization, so any promotion here needs to align with that module.
```

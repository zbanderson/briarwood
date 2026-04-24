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
path: briarwood/modules/current_value_scoped.py       # scoped wrapper
legacy_path: briarwood/modules/current_value.py        # wrapped CurrentValueModule engine
entry: run_current_value(context: ExecutionContext) -> dict
intent_fit: [RESEARCH, EDGE]                           # scenario/stress-test view; prefer `valuation` for DECISION/BROWSE/LOOKUP
inputs:
  property_data.purchase_price: float                  # recommended
  property_data.sqft: int                              # required
  property_data.beds: int                              # required
  property_data.baths: float                           # required
  property_data.town: str                              # required
  property_data.state: str                             # required
outputs:
  data.legacy_payload.briarwood_current_value: float | None
  data.legacy_payload.mispricing_pct: float | None
  data.legacy_payload.pricing_view: str                # "fair" | "undervalued" | "overvalued" | "unavailable"
  data.legacy_payload.value_low: float | None
  data.legacy_payload.value_high: float | None
  data.legacy_payload.all_in_basis: float | None
  confidence: float                                    # pre-macro
  assumptions_used.applies_macro_nudge: false         # distinguishing flag
  assumptions_used.legacy_module: "CurrentValueModule"
depends_on: []                                         # engine composes children in-process; anti-recursion
invariants:
  - confidence in [0, 1]
  - Never raises; on exception returns module_payload_from_error (mode="fallback", confidence=0.08)
  - applies_macro_nudge is always false — distinguishes from `valuation` which applies the HPI-momentum nudge
  - Anti-recursion: valuation calls CurrentValueModule in-process; this tool does the same. Neither depends on the other.
blockers_for_tool_use: []
notes:
  - Promoted to scoped registry in Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 3.
  - Sibling to `valuation` — same engine, different contract. See README_current_value.md "When to call current_value vs. valuation" section for disambiguation rules.
  - Payload field names under data.legacy_payload preserved from CurrentValueOutput so direct callers (bull_base_bear, teardown_scenario, renovation_scenario) can migrate without reshaping.
  - See README_current_value.md for the full contract.
```

### comparable_sales

```yaml
name: comparable_sales
path: briarwood/modules/comparable_sales_scoped.py      # scoped wrapper
legacy_path: briarwood/modules/comparable_sales.py       # wrapped ComparableSalesModule
entry: run_comparable_sales(context: ExecutionContext) -> dict
intent_fit: [LOOKUP, COMPARISON, DECISION, BROWSE]
inputs:
  property_data.town: str                                # required
  property_data.state: str                               # required
  property_data.sqft: int                                # required (15% tolerance)
  property_data.beds: int                                # required
  property_data.baths: float                             # required
  property_data.property_type: str                       # optional
  property_data.lot_size: float                          # optional
  property_data.year_built: int                          # optional
  property_data.condition_profile: str                   # optional
  property_data.capex_lane: str                          # optional
  property_data.purchase_price: float                    # optional (listing-price anchor)
  property_data.has_back_house: bool                     # optional (triggers hybrid)
  property_data.adu_type: str                            # optional (triggers hybrid)
  property_data.additional_units: list                   # optional
  property_data.days_on_market: int                      # optional
  property_data.manual_comp_inputs: list                 # optional
outputs:
  data.metrics.comparable_value: float
  data.metrics.comp_count: int
  data.metrics.comp_confidence: float                    # rounded outer
  data.metrics.comp_confidence_score: float              # comp-match-quality weighted
  data.metrics.direct_value_midpoint: float | None
  data.metrics.blended_value_midpoint: float | None
  data.legacy_payload.comparable_value: float
  data.legacy_payload.comp_count: int
  data.legacy_payload.confidence: float
  data.legacy_payload.comps_used: list[AdjustedComparable]
  data.legacy_payload.rejected_count: int
  data.legacy_payload.direct_value_range: object        # {low, midpoint, high}
  data.legacy_payload.income_adjusted_value_range: object
  data.legacy_payload.location_adjustment_range: object
  data.legacy_payload.lot_adjustment_range: object
  data.legacy_payload.blended_value_range: object
  data.legacy_payload.comp_confidence_score: float
  data.legacy_payload.is_hybrid_valuation: bool          # load-bearing — read by hybrid_value
  data.legacy_payload.primary_dwelling_value: float | None
  data.legacy_payload.additional_unit_income_value: float | None
  data.legacy_payload.additional_unit_count: int
  data.legacy_payload.additional_unit_annual_income: float | None
  data.legacy_payload.additional_unit_cap_rate: float    # 0.08 default (_DEFAULT_ADU_CAP_RATE)
  data.legacy_payload.hybrid_valuation_note: str | None
  confidence: float
depends_on: []                                           # internally runs MarketValueHistoryModule + ComparableSalesAgent
invariants:
  - Never raises; on exception returns module_payload_from_error (mode="fallback", confidence=0.08)
  - comp_count >= 0; comps_used is always a list (possibly empty)
  - Applies market_friction_discount for nonstandard products via is_nonstandard_product()
  - Field names under data.legacy_payload preserved verbatim — read by hybrid_value (via prior_results) and unit_income_offset
  - Hybrid detection baked into the run path; when is_hybrid_valuation=True, primary_dwelling_value and additional_unit_income_value are set
blockers_for_tool_use: []
notes:
  - Promoted to scoped registry in Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 1.
  - **Engine A** (saved comps). Distinct from **Engine B** (get_cma at briarwood/agent/tools.py:1802, live-Zillow first, backs session.last_market_support_view). Engine B quality is its own handoff — see FOLLOW_UPS.md 2026-04-24 *Two comp engines*.
  - Graft retirement: briarwood/claims/pipeline.py:62-88 ad-hoc instantiation now unnecessary; retirement tracked in FOLLOW_UPS.md (not in H3 scope).
  - Data source: data/comps/sales_comps.json (shared with location_intelligence).
  - Hardcoded: 15% sqft tolerance for comp matching; ADU cap rate 0.08; ADU expense ratio 0.30.
  - Cross-town comps TODO flagged in base_comp_selector.py.
  - Renovation premium TODO: estimate_comp_renovation_premium() not yet fed through.
  - See README_comparable_sales.md for the full contract.
```

### hybrid_value

```yaml
name: hybrid_value
path: briarwood/modules/hybrid_value_scoped.py           # scoped composite wrapper
legacy_path: briarwood/modules/hybrid_value.py            # wrapped HybridValueModule
entry: run_hybrid_value(context: ExecutionContext) -> dict
intent_fit: [RESEARCH, EDGE, DECISION, BROWSE]           # only meaningful for multi-unit / primary+ADU subjects
inputs:
  property_data.town: str                                # required
  property_data.state: str                               # required
  property_data.sqft: int                                # required
  property_data.beds: int                                # required
  property_data.baths: float                             # required
  property_data.has_back_house: bool                     # optional (drives hybrid detection)
  property_data.adu_type: str                            # optional (drives hybrid detection)
  property_data.additional_units: list                   # optional
  property_data.back_house_monthly_rent: float           # optional
  property_data.listing_description: str                 # optional
  prior_outputs.comparable_sales: dict                   # required via depends_on; mode must not be error/fallback
  prior_outputs.income_support: dict                     # required via depends_on; mode must not be error/fallback
outputs:
  data.legacy_payload.is_hybrid: bool                    # valid zero-confidence answer when False (NOT error)
  data.legacy_payload.reason: str
  data.legacy_payload.detected_primary_structure_type: str | None
  data.legacy_payload.detected_accessory_income_type: str | None
  data.legacy_payload.primary_house_value: float | None
  data.legacy_payload.primary_house_comp_confidence: float
  data.legacy_payload.primary_house_comp_set: list[HybridCompEntry]
  data.legacy_payload.rear_income_value: float | None    # capitalized rent
  data.legacy_payload.rear_income_method_used: str | None
  data.legacy_payload.rear_income_confidence: float
  data.legacy_payload.optionality_premium_value: float | None
  data.legacy_payload.optionality_reason: str
  data.legacy_payload.low_case_hybrid_value: float | None
  data.legacy_payload.base_case_hybrid_value: float | None
  data.legacy_payload.high_case_hybrid_value: float | None
  data.legacy_payload.market_friction_discount: float | None
  data.legacy_payload.market_feedback_adjustment: float | None
  data.legacy_payload.confidence: float
  data.legacy_payload.notes: list[str]
  data.legacy_payload.narrative: str
  confidence: float | None                               # None only on missing-priors error
  mode: str                                              # full/partial (happy), error (missing priors), fallback (exception)
  missing_inputs: list[str]                              # populated on mode=error
depends_on: [comparable_sales, income_support]
invariants:
  - Composite wrapper with canonical missing-priors contract: priors with mode in {"error","fallback"} treated as missing → module_payload_from_missing_prior (mode="error", confidence=None)
  - is_hybrid=False short-circuit is a valid zero-confidence payload, NOT an error — consumers must key on data.legacy_payload.is_hybrid, not on mode
  - comp_is_hybrid passthrough at hybrid_value.py:118-132 preserved — when comparable_sales already decomposed, primary + rear values are reused to avoid double-counting
  - Never raises; internal exception → module_payload_from_error (mode="fallback", confidence=0.08)
  - Cap rate 0.08, expense ratio 0.30 live in comparable_sales.py (shared constants)
  - Applies evaluate_market_feedback() + market_friction_discount() via valuation_constraints
blockers_for_tool_use: []
notes:
  - Promoted to scoped registry in Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 2.
  - In-process dep re-computation: HybridValueModule.run() invoked without prior_results kwarg because ExecutionContext.prior_outputs holds scoped payload dicts, not typed ModuleResult objects. The legacy module re-runs its comparable_sales + income_support deps in-process. The missing-priors gate is about refusing to run on degraded upstream, not about avoiding redundant compute.
  - See README_hybrid_value.md for the full contract.
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
path: briarwood/modules/market_value_history_scoped.py          # scoped wrapper
legacy_path: briarwood/modules/market_value_history.py           # wrapped MarketValueHistoryModule
entry: run_market_value_history(context: ExecutionContext) -> dict
intent_fit: [RESEARCH, BROWSE, PROJECTION, DECISION]
inputs:
  property_data.town: str                  # required
  property_data.state: str                 # required
  property_data.county: str                # optional, fallback geography
outputs:
  data.metrics.source_name: str            # provider label (Zillow ZHVI)
  data.metrics.geography_name: str         # resolved town/county
  data.metrics.geography_type: str         # "town" | "county" | "metro"
  data.metrics.current_value: float | None # USD; null when no coverage
  data.metrics.one_year_change_pct: float | None
  data.metrics.three_year_change_pct: float | None
  data.metrics.history_points: int         # count of time-series points
  data.legacy_payload.points: list[HistoryPoint]   # {month, value, confidence}
  data.legacy_payload.summary: str
  confidence: float
depends_on: []
invariants:
  - Geography-level; NOT property-specific. Consumers must not misread as property trend.
  - Never raises; on exception returns module_payload_from_error (mode="fallback", confidence=0.08).
  - geography_name/type populated when town+state provided, even if coverage is empty.
blockers_for_tool_use: []
notes:
  - Promoted to scoped registry in Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 4.
  - Data source: data/market_history/zillow_zhvi_history.json via FileBackedZillowHistoryProvider.
  - Consumed in-process by ComparableSalesModule, CurrentValueModule, bull_base_bear (legacy); those continue to instantiate MarketValueHistoryModule directly rather than reading the scoped tool's prior_outputs.
  - See README_market_value_history.md for the full contract.
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
path: briarwood/modules/scarcity_support_scoped.py      # scoped wrapper
legacy_path: briarwood/modules/scarcity_support.py       # wrapped ScarcitySupportModule
entry: run_scarcity_support(context: ExecutionContext) -> dict
intent_fit: [RESEARCH, MICRO_LOCATION, BROWSE, DECISION]
inputs:
  property_data.town: str                                # required
  property_data.state: str                               # required
  property_data.county: str                              # optional fallback
  property_data.property_type: str                       # optional
outputs:
  data.metrics.scarcity_support_score: float             # 0-100, load-bearing key
  data.metrics.scarcity_label: str                       # categorical
  data.metrics.buyer_takeaway: str
  data.legacy_payload.demand_consistency_score: float    # 0-1
  data.legacy_payload.location_scarcity_score: float
  data.legacy_payload.land_scarcity_score: float
  data.legacy_payload.scarcity_score: float
  data.legacy_payload.demand_drivers: list[str]
  data.legacy_payload.scarcity_notes: list[str]
  confidence: float
depends_on: []
invariants:
  - Geography-driven: signal describes town/segment, not the subject property
  - Never raises; on exception returns module_payload_from_error (mode="fallback", confidence=0.08)
  - scarcity_support_score field name preserved verbatim — read by town_x_scenario, valuation_x_town, rental_ease agent, bull_base_bear (deprecating — Handoff 4). The former `decision_model/scoring.py` and `lens_scoring.py` readers were deleted in Handoff 4 alongside the dead `calculate_final_score` chain.
blockers_for_tool_use: []
notes:
  - Promoted to scoped registry in Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 7.
  - Internal: TownCountyDataService + ScarcitySupportScorer. Implementation-private.
  - See README_scarcity_support.md for the full contract.
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
path: briarwood/modules/income_support_scoped.py       # scoped wrapper
legacy_path: briarwood/modules/income_support.py        # wrapped IncomeSupportModule engine
entry: run_income_support(context: ExecutionContext) -> dict
intent_fit: [RENT_LOOKUP, LOOKUP]                       # prefer `rental_option` for STRATEGY / composite answers
inputs:
  property_data.purchase_price: float                   # required
  property_data.estimated_monthly_rent: float           # recommended (RentContextAgent estimates if absent)
  property_data.down_payment_percent: float             # recommended
  property_data.interest_rate: float                    # recommended
  property_data.loan_term_years: int                    # recommended
  property_data.taxes: float                            # optional
  property_data.insurance: float                        # optional
  property_data.monthly_hoa: float                      # optional
  property_data.sqft: int                               # required (by PropertyInput)
  property_data.beds: int                               # required
  property_data.baths: float                            # required
  property_data.town: str                               # recommended
  property_data.state: str                              # recommended
outputs:
  data.legacy_payload.income_support_ratio: float | None
  data.legacy_payload.rent_coverage: float | None
  data.legacy_payload.price_to_rent: float | None
  data.legacy_payload.monthly_cash_flow: float | None
  data.legacy_payload.effective_monthly_rent: float | None
  data.legacy_payload.gross_monthly_cost: float | None
  data.legacy_payload.rent_support_classification: str
  data.legacy_payload.price_to_rent_classification: str
  data.legacy_payload.rent_source_type: str             # "actual" | "estimated" | "fallback" | "unavailable"
  data.legacy_payload.carrying_cost_complete: bool
  data.legacy_payload.financing_complete: bool
  confidence: float
  assumptions_used.exposes_raw_underwriting_signal: true  # distinguishing flag
  assumptions_used.legacy_module: "IncomeSupportModule"
depends_on: []                                          # anti-recursion — engine composes in-process
invariants:
  - confidence in [0, 1]
  - Never raises; on exception returns module_payload_from_error (mode="fallback", confidence=0.08)
  - rent_source_type is never null; missing rent → "unavailable"
  - Field names under data.legacy_payload preserved unchanged — risk_bar / evidence / comp_intelligence / rental_ease / hybrid_value read by key
  - Anti-recursion: rental_option calls IncomeSupportModule in-process; this tool does the same. Neither depends on the other.
blockers_for_tool_use: []
notes:
  - Promoted to scoped registry in Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 8.
  - Sibling to `rental_option` — same engine, different contract. See README_income_support.md "When to call income_support vs. rental_option" for disambiguation rules.
  - Backed by briarwood/agents/income/IncomeAgent. RentContextAgent parses unit rents; UnitRentEstimator estimates when absent.
  - See README_income_support.md for the full contract.
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
path: briarwood/modules/location_intelligence_scoped.py   # scoped wrapper
legacy_path: briarwood/modules/location_intelligence.py    # wrapped LocationIntelligenceModule
entry: run_location_intelligence(context: ExecutionContext) -> dict
intent_fit: [MICRO_LOCATION, RESEARCH, BROWSE, EDGE]
inputs:
  property_data.town: str                                  # required
  property_data.state: str                                 # required
  property_data.latitude: float                            # recommended
  property_data.longitude: float                           # recommended
  property_data.landmark_points: dict[str, list[Point]]    # recommended (beach / downtown / park / train / ski)
  property_data.zone_flags: list[str]                      # optional
  property_data.purchase_price: float                      # required (anchor)
  property_data.sqft: int                                  # required
outputs:
  data.metrics.location_score: float                       # 0-1
  data.metrics.scarcity_score: float                       # 0-1
  data.metrics.primary_category: str                       # beach | downtown | park | train | ski
  data.legacy_payload.subject_ppsf: float | None
  data.legacy_payload.location_premium_pct: float | None
  data.legacy_payload.subject_relative_premium_pct: float | None
  data.legacy_payload.category_results: list[LocationCategoryIntelligence]
  data.legacy_payload.narratives: list[str]
  data.legacy_payload.confidence_notes: list[str]
  data.legacy_payload.missing_inputs: list[str]
  data.legacy_payload.zone_flags: list[str]
  confidence: float
depends_on: []
invariants:
  - Never raises; on exception returns module_payload_from_error (mode="fallback", confidence=0.08, fallback_reason="provider_or_geocode_error")
  - Missing-input semantics preserved: confidence_notes + missing_inputs populated when coords / landmarks / geo comps are absent (legitimate low-confidence output, NOT wrapper-caught failure)
  - location_score, scarcity_score in [0, 1]
blockers_for_tool_use: []
notes:
  - Promoted to scoped registry in Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 11.
  - Shares comp provider with comparable_sales (data/comps/sales_comps.json).
  - First scoped tool covering MICRO_LOCATION intent family.
  - See README_location_intelligence.md for the full contract.
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
entry: run_strategy_classifier(context: ExecutionContext) -> dict    # scoped-registry runner at line 247
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
  - Never raises; on exception returns module_payload_from_error (mode="fallback", confidence=0.08) per canonical error contract
blockers_for_tool_use: []
notes:
  - Registered in scoped execution registry as of Handoff 3 (2026-04-24). See PROMOTION_PLAN.md entry 13.
  - Runs at Layer 2 (post-intake, pre-domain models) in current orchestration
  - Rule-based; extensively documented inline
  - See README_strategy_classifier.md for the full contract
```

---

## Non-production

Documented but not currently invoked in production synthesis paths.

_(The `decision_model/calculate_final_score` entry was removed in Handoff 4 on 2026-04-24. The aggregator, its dataclasses, all supporting helpers, and the entire `lens_scoring.py` module were deleted — zero production callers verified. See DECISIONS.md 2026-04-24 "PROMOTION_PLAN.md entry 15 scope-limit paragraph corrected" and PROMOTION_PLAN.md entry 15.)_

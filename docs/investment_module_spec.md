# Briarwood Investment Module Specification

## Purpose

This document defines Briarwood by investment module rather than code package.

Each module should specify:

- decision question
- required inputs
- optional inputs
- exact calculations
- output fields
- narrative responsibility
- confidence logic
- likely data sources

The goal is to make sure every tear sheet claim is traceable to a defined calculation and a known source type.

## Source Categories

For now, source types should be classified as:

- `listing_source`
  - directly observable from listing text or listing metadata
- `public_record`
  - tax history, assessed value, parcel facts
- `market_source`
  - Zestimate, rent estimate, town trend, school rating
- `user_assumption`
  - financing, hold period, maintenance, vacancy
- `derived`
  - calculated by Briarwood from upstream inputs

## Module 1: Property Snapshot

### Decision Question

What is this asset at a basic physical and listing level?

### Required Inputs

- address
- town
- state
- property_type
- beds
- baths
- ask_price

### Optional Inputs

- sqft
- lot_sqft
- year_built
- days_on_market
- listing_description
- source_url

### Calculations

- `price_per_sqft = ask_price / sqft`
  - only when `ask_price` and `sqft` are both present and `sqft > 0`
- `property_age = current_year - year_built`
  - only when `year_built` is present

### Outputs

- normalized address
- property type
- basic size profile
- price_per_sqft
- property_age
- days_on_market
- completeness flags

### Narrative Responsibility

Describe the asset clearly and identify any missing core descriptive fields.

### Confidence Logic

Suggested weights:

- address: 0.15
- ask_price: 0.20
- beds: 0.10
- baths: 0.10
- property_type: 0.10
- sqft: 0.20
- year_built: 0.10
- days_on_market: 0.05

### Likely Data Sources

- listing_source
- public_record

## Module 2: Value / Pricing

### Decision Question

What is the property likely worth today relative to the current ask?

### Required Inputs

- ask_price
- market_reference_value

### Optional Inputs

- sqft
- price_per_sqft
- price_history
- tax_history
- town_price_trend
- comparable sale inputs later

### Calculations

- `pricing_gap_to_market = (market_reference_value - ask_price) / ask_price`
- `current_price_per_sqft = ask_price / sqft`
  - if sqft present
- `market_reference_premium = ask_price - market_reference_value`
- `price_history_direction`
  - rule-based summary of price cuts, relists, or upward revisions

### Outputs

- ask_price
- market_reference_value
- pricing_gap_to_market
- current_price_per_sqft
- pricing_position
  - example: supported / slightly rich / stretched / discounted

### Narrative Responsibility

Explain whether the property looks fairly priced, overreaching, or supported by market context.

### Confidence Logic

Suggested weights:

- ask_price: 0.25
- market_reference_value: 0.35
- sqft: 0.15
- price_history: 0.10
- town_price_trend: 0.10
- tax_history: 0.05

### Likely Data Sources

- listing_source
- market_source
- public_record

## Module 3: Appreciation / Forward Value

### Decision Question

What is the likely forward value range over the buyer's hold period?

### Required Inputs

- ask_price
- target_hold_years
- town_price_trend

### Optional Inputs

- market_reference_value
- town_population_trend
- development_tailwinds
- scarcity_notes
- liquidity_signal
- price_history

### Calculations

Initial v1 should remain simple and explicit.

- `base_growth_rate`
  - primary rule: use `town_price_trend` when present
  - fallback: use conservative default selected by Briarwood
- `bull_growth_rate = base_growth_rate + upside_adjustment`
- `bear_growth_rate = max(base_growth_rate - downside_adjustment, floor_rate)`
- `base_future_value = ask_price * (1 + base_growth_rate) ** target_hold_years`
- `bull_future_value = ask_price * (1 + bull_growth_rate) ** target_hold_years`
- `bear_future_value = ask_price * (1 + bear_growth_rate) ** target_hold_years`

Optional adjustments may later incorporate:

- market reference dislocation
- development tailwinds
- scarcity score
- liquidity penalties

### Outputs

- bull_future_value
- base_future_value
- bear_future_value
- value_range_spread
- hold_period_years
- primary appreciation drivers

### Narrative Responsibility

Explain what must happen for upside to materialize and what assumptions anchor the forward value range.

### Confidence Logic

Suggested weights:

- ask_price: 0.20
- target_hold_years: 0.15
- town_price_trend: 0.25
- market_reference_value: 0.10
- development_tailwinds: 0.10
- scarcity_notes: 0.10
- liquidity_signal: 0.10

### Likely Data Sources

- listing_source
- market_source
- user_assumption
- derived

## Module 4: Ownership Cost / Carry

### Decision Question

What does it cost this specific buyer to own the property monthly?

### Required Inputs

- ask_price
- annual_taxes
- down_payment_pct
- interest_rate
- loan_term_years

### Optional Inputs

- annual_insurance
- monthly_hoa
- maintenance_pct
- closing_cost_estimate

### Calculations

- `loan_amount = ask_price * (1 - down_payment_pct)`
- `monthly_principal_interest`
  - standard amortizing mortgage formula
- `monthly_taxes = annual_taxes / 12`
- `monthly_insurance = annual_insurance / 12`
- `monthly_maintenance_reserve = ask_price * maintenance_pct / 12`
- `gross_monthly_carry = monthly_principal_interest + monthly_taxes + monthly_insurance + monthly_hoa + monthly_maintenance_reserve`

### Outputs

- loan_amount
- monthly_principal_interest
- monthly_taxes
- monthly_insurance
- monthly_hoa
- monthly_maintenance_reserve
- gross_monthly_carry

### Narrative Responsibility

Translate financing assumptions into a simple ownership burden story.

### Confidence Logic

Suggested weights:

- ask_price: 0.15
- annual_taxes: 0.20
- annual_insurance: 0.15
- monthly_hoa: 0.10
- down_payment_pct: 0.15
- interest_rate: 0.15
- maintenance_pct: 0.10

### Likely Data Sources

- listing_source
- public_record
- user_assumption
- derived

## Module 5: Fallback Rental / Optionality

### Decision Question

If the buyer needed to pivot, could the property realistically function as a rental backstop?

### Required Inputs

- estimated_monthly_rent
- gross_monthly_carry

### Optional Inputs

- vacancy_pct
- maintenance_pct
- annual_taxes
- annual_insurance
- monthly_hoa
- rent_confidence
- rent_source

### Calculations

- `effective_monthly_rent = estimated_monthly_rent * (1 - vacancy_pct)`
- `income_support_ratio = effective_monthly_rent / gross_monthly_carry`
- `fallback_cash_flow = effective_monthly_rent - gross_monthly_carry`
- `fallback_status`
  - strong if `income_support_ratio >= 1.00`
  - partial if `0.75 <= income_support_ratio < 1.00`
  - weak if `< 0.75`

### Outputs

- effective_monthly_rent
- income_support_ratio
- fallback_cash_flow
- fallback_status
- rent_confidence

### Narrative Responsibility

Frame rent not as the main investment thesis, but as downside protection and flexibility.

### Confidence Logic

Suggested weights:

- estimated_monthly_rent: 0.35
- annual_taxes: 0.10
- annual_insurance: 0.10
- monthly_hoa: 0.05
- vacancy_pct: 0.10
- maintenance_pct: 0.10
- down_payment_pct: 0.10
- interest_rate: 0.10

### Likely Data Sources

- market_source
- user_assumption
- derived

## Module 6: Downside / Risk

### Decision Question

What are the most likely ways this property could disappoint the buyer?

### Required Inputs

- year_built
- days_on_market

### Optional Inputs

- flood_risk
- annual_taxes
- liquidity_signal
- renovation_budget
- property condition signal later
- local hazard signals later

### Calculations

Initial v1 should stay deterministic and transparent:

- `older_home_flag`
  - if age exceeds threshold
- `high_tax_flag`
  - if taxes exceed threshold
- `long_marketing_period_flag`
  - if days on market exceeds threshold
- `flood_flag`
  - if flood risk above threshold
- `risk_count = number of active flags`
- `risk_score = clamp(base_score - penalty_per_flag * risk_count)`

### Outputs

- active risk flags
- risk_count
- risk_score
- primary downside drivers

### Narrative Responsibility

Explain what could impair resale, increase cost, or reduce hold flexibility.

### Confidence Logic

Suggested weights:

- year_built: 0.20
- days_on_market: 0.20
- flood_risk: 0.25
- annual_taxes: 0.15
- renovation_budget: 0.10
- liquidity_signal: 0.10

### Likely Data Sources

- listing_source
- public_record
- market_source
- user_assumption

## Module 7: Location / Demand Quality

### Decision Question

Why should future buyers or renters continue to want this property?

### Required Inputs

- town
- state

### Optional Inputs

- town_price_trend
- town_population_trend
- school_rating
- development_tailwinds
- scarcity_notes
- flood_risk
- liquidity_signal

### Calculations

The first version can be weighted scoring, not a black-box model.

- `town_quality_score`
  - weighted combination of growth, schools, and demand durability signals
- `location_strength_label`
  - example: durable / mixed / weak

### Outputs

- town_quality_score
- location_strength_label
- top supporting demand signals
- top demand risks

### Narrative Responsibility

Explain the local demand story in a way that supports or challenges the appreciation thesis.

### Confidence Logic

Suggested weights:

- town_price_trend: 0.30
- town_population_trend: 0.20
- school_rating: 0.20
- development_tailwinds: 0.15
- scarcity_notes: 0.10
- liquidity_signal: 0.05

### Likely Data Sources

- market_source
- derived

## Module 8: Confidence / Data Quality

### Decision Question

How much of Briarwood's story is supported by real inputs versus assumptions and gaps?

### Required Inputs

- all upstream module input-completeness outputs

### Optional Inputs

- source freshness
- source ranking
- conflicting source detection later

### Calculations

For each module:

- `module_confidence = sum(weight for populated inputs) / sum(total weights)`
- `missing_inputs = list of absent weighted fields`
- `assumptions_used = list of user or fallback assumptions used`
- `unsupported_claims = list of claims not sufficiently supported`

Global confidence can then be summarized as:

- weighted average of module confidences

### Outputs

- module_confidence_map
- missing_inputs_by_module
- assumptions_used_by_module
- unsupported_claims_by_module
- overall_report_confidence

### Narrative Responsibility

Tell the user what Briarwood knows well, what it had to assume, and where caution is warranted.

### Likely Data Sources

- derived

## Tear Sheet Assembly Map

### Header

Driven by:

- Property Snapshot
- Value / Pricing
- Confidence

### Conclusion

Driven by:

- Value / Pricing
- Appreciation / Forward Value
- Downside / Risk

### Opportunity

Driven by:

- Appreciation / Forward Value
- Location / Demand Quality

### Downside

Driven by:

- Downside / Risk
- Ownership Cost / Carry

### Resilience

Driven by:

- Ownership Cost / Carry
- Fallback Rental / Optionality

### Confidence

Driven by:

- Confidence / Data Quality

### Scenario Chart

Driven by:

- Value / Pricing
- Appreciation / Forward Value
- User hold-period assumptions

## Immediate Data Acquisition Priorities

To support these modules meaningfully, the first sourcing priorities should be:

1. Ask price, HOA, taxes, price history, tax history
2. Market reference value
3. Rent estimate and rent confidence
4. Town growth and school-quality signals
5. User assumptions for financing, hold period, and reserves

## Next Step

After this module map is accepted, the next planning artifact should be a source matrix:

- field name
- owning module
- source type
- primary source
- fallback source
- parsing method
- confidence impact if missing

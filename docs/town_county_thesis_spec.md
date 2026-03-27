# Briarwood Town / County Investment Thesis Specification

## Purpose

This module should explain whether the property's surrounding town and county context support a confident medium-term hold thesis.

The point is not to produce a generic "area score." The point is to answer:

- Why should demand remain durable here?
- Why should value hold or grow here over a 2-3 year window?
- What local forces support the buyer's downside protection?
- What local weaknesses could undermine the thesis?

This module should support the agent conversation:

- "This property is not just a house; it sits inside a local market story."
- "That story is either supportive, mixed, or weak."

## Decision Question

Does the town / county context make this property more likely to appreciate, hold value, and remain liquid over the buyer's planned hold period?

## Scope

This module should evaluate location from two levels:

1. Town-level demand quality
2. County-level structural support

Town tells us what buyers directly feel.
County tells us whether the broader area is supporting or fighting the town story.

## Core Output

The module should produce:

- `location_thesis_label`
  - strong / supportive / mixed / weak
- `town_county_score`
  - 0-100
- `location_confidence`
  - 0.0-1.0
- `demand_drivers`
  - list[str]
- `demand_risks`
  - list[str]
- `liquidity_view`
  - strong / normal / fragile
- `appreciation_support_view`
  - strong / moderate / limited
- `summary`
  - short interpretation for the tear sheet

## Input Groups

### A. Town Demand Inputs

These describe buyer desirability at the town level.

- town_price_trend
- town_population_trend
- school_rating
- median household income later
- commute accessibility later
- amenity density later
- zoning / build constraints later
- flood_risk

### B. County Structural Inputs

These describe the broader support environment.

- county_price_trend
- county_population_trend
- county_inventory_trend later
- county_days_on_market later
- county_new_supply_pressure later
- employment_base_strength later
- permit / development activity later

### C. Property-Market Fit Inputs

These describe whether the specific property is aligned with what the local market tends to absorb.

- property_type
- beds
- baths
- sqft
- ask_price
- days_on_market
- price_per_sqft
- local price band context later

### D. Qualitative Thesis Inputs

These explain the story in human terms.

- development_tailwinds
- scarcity_notes
- liquidity_signal
- neighborhood quality notes later
- known infrastructure catalysts later

## Minimum Viable Input Set

For a useful v1, the minimum required set should be:

- town
- state
- town_price_trend
- town_population_trend
- school_rating
- flood_risk

The minimum useful county set should be:

- county_price_trend
- county_population_trend

If county data is missing, the module should still run, but the confidence score should drop and the narrative should explicitly say the county context is incomplete.

## Calculations

The first version should remain deterministic and easy to explain.

### 1. Town Demand Score

Suggested weighted formula:

```text
town_demand_score =
    35 * normalized_town_price_trend +
    20 * normalized_town_population_trend +
    25 * normalized_school_rating +
    10 * scarcity_signal +
    10 * liquidity_signal_score -
    flood_penalty
```

Where:

- `normalized_town_price_trend`
  - map expected annual trend into a 0-1 band
- `normalized_town_population_trend`
  - map population change into a 0-1 band
- `normalized_school_rating = school_rating / 10`
- `scarcity_signal`
  - 0.0 to 1.0 based on structured scarcity notes
- `liquidity_signal_score`
  - 0.0 to 1.0 based on liquidity evidence
- `flood_penalty`
  - 0 for low/none
  - moderate deduction for medium
  - larger deduction for high

### 2. County Support Score

Suggested weighted formula:

```text
county_support_score =
    60 * normalized_county_price_trend +
    40 * normalized_county_population_trend
```

This should stay intentionally simple in v1.

### 3. Market Alignment Score

This measures whether the property fits the local market well enough to remain liquid.

Suggested v1 rule-based scoring:

- start at 50
- add points if days_on_market is low
- add points if price_per_sqft is in a normal band for the town later
- subtract points if the property is missing critical descriptive data
- subtract points if price position appears stretched relative to market reference

### 4. Town / County Thesis Score

Combine the three:

```text
town_county_score =
    0.50 * town_demand_score +
    0.25 * county_support_score +
    0.25 * market_alignment_score
```

If county data is absent:

```text
town_county_score =
    0.65 * town_demand_score +
    0.35 * market_alignment_score
```

### 5. Location Thesis Label

Suggested interpretation:

- `>= 75`: strong
- `60-74`: supportive
- `45-59`: mixed
- `< 45`: weak

### 6. Appreciation Support View

Derived from:

- town_county_score
- town price trend
- county price trend
- scarcity signal

Labels:

- strong
- moderate
- limited

### 7. Liquidity View

Derived from:

- days_on_market
- liquidity signal
- market alignment score
- county inventory pressure later

Labels:

- strong
- normal
- fragile

## Narrative Responsibility

This module should not just say:

- "schools are good"
- "population is growing"

It should connect local data to the hold thesis.

The narrative should answer:

1. Why buyers should still want this area in 2-3 years
2. Why resale demand should remain durable
3. Whether the town story is strong enough to offset property-specific imperfections
4. Whether county conditions reinforce or weaken the town story

## Narrative Template

### Strong Example

"The town/county backdrop is supportive for a medium-term hold. Demand appears durable because town pricing, school quality, and broader county conditions all point to continued buyer interest. That improves the odds that the property remains liquid and exits into a healthy market."

### Mixed Example

"The local story is workable but not especially protective. The town has some supportive demand traits, but county-level signals and liquidity indicators are less convincing. That means the property may still work, but the location alone should not be relied on to rescue a stretched purchase."

### Weak Example

"The surrounding market does not provide strong support for the hold thesis. Weak growth, soft liquidity, or adverse risk factors mean the buyer is relying more on a perfect purchase execution than on durable local demand."

## Confidence Logic

This module should have its own confidence score separate from the thesis score.

Suggested weights:

- town_price_trend: 0.20
- town_population_trend: 0.15
- school_rating: 0.20
- county_price_trend: 0.15
- county_population_trend: 0.10
- liquidity_signal: 0.10
- scarcity_notes: 0.05
- flood_risk: 0.05

Confidence formula:

```text
location_confidence =
    populated_weight_sum / total_weight_sum
```

The module should also emit:

- `missing_inputs`
- `assumptions_used`
- `unsupported_claims`

## Source Plan

### Town-Level Sources

Primary candidates:

- market_source for town price trend
- market_source or public dataset for school rating
- market_source or census-style source for population trend
- hazard source for flood risk

### County-Level Sources

Primary candidates:

- county price trend source
- county population trend source
- county inventory / liquidity source later
- county permit / development source later

### Qualitative / Thesis Sources

Primary candidates:

- curated qualitative notes
- manually tagged development catalysts
- later news / planning board / permit feeds if Briarwood grows into deeper research

## Immediate V1 Fields To Acquire

If we want this module to become meaningful quickly, the first fields to support should be:

1. town_price_trend
2. county_price_trend
3. town_population_trend
4. county_population_trend
5. school_rating
6. flood_risk
7. liquidity_signal
8. development_tailwinds
9. scarcity_notes

## Recommended V1 Implementation Order

### Phase 1

Get the quantitative backbone in place:

- town_price_trend
- town_population_trend
- school_rating
- flood_risk

### Phase 2

Add county context:

- county_price_trend
- county_population_trend

### Phase 3

Add narrative enhancers:

- liquidity_signal
- development_tailwinds
- scarcity_notes

### Phase 4

Refine market alignment:

- local price-band fit
- county inventory pressure
- permit / supply pressure

## Tear Sheet Role

This module should primarily feed:

- Opportunity
- Appreciation thesis
- Confidence
- Downside

It should also influence:

- the forward value fan assumptions
- the overall confidence of the recommendation

## What This Module Should Never Do

This module should not:

- act like a substitute for property-level valuation
- produce black-box scores without interpretation
- overclaim certainty when county/town data is sparse
- assume that a good town automatically makes any purchase safe

## Summary

The town / county investment thesis should answer a simple but important question:

"Is the broader location helping protect this buyer's decision, or is the buyer mostly on their own?"

That is the real location-level value Briarwood should provide.

# Briarwood Town / County Thesis Source Matrix

## Purpose

This document translates the town / county investment thesis into a concrete sourcing plan.

For each field, it defines:

- owning module responsibility
- source type
- primary source direction
- fallback source direction
- acquisition method
- update expectations
- confidence penalty if missing
- notes on how the field should be used

This is the planning bridge between the thesis spec and implementation.

## Field Priority Tiers

### Tier 1: Quantitative Backbone

These fields are the minimum needed for a meaningful location thesis:

- town_price_trend
- county_price_trend
- town_population_trend
- county_population_trend
- school_rating
- flood_risk

### Tier 2: Liquidity And Demand Texture

These fields improve the realism of the hold thesis:

- liquidity_signal
- county_inventory_trend
- county_days_on_market
- market_alignment_context

### Tier 3: Narrative Enhancers

These fields improve explanation and confidence:

- development_tailwinds
- scarcity_notes
- permit_activity
- infrastructure_catalysts

## Source Matrix

### 1. `town_price_trend`

- module: town / county thesis
- source type: `market_source`
- primary source direction: town-level home value trend dataset
- fallback source direction: zip-code trend mapped to town, or county-level trend with confidence downgrade
- acquisition method:
  - API if available
  - CSV / structured dataset ingest if needed
  - internal normalization to annualized percent trend
- update expectation: monthly or quarterly
- confidence penalty if missing: high
- recommended confidence weight: `0.20`
- usage:
  - core appreciation support input
  - part of town demand score
- implementation note:
  - normalize to a trailing 12-month percentage change for consistency

### 2. `county_price_trend`

- module: town / county thesis
- source type: `market_source`
- primary source direction: county-level home value trend dataset
- fallback source direction: metro-level trend or state-level trend with explicit warning
- acquisition method:
  - API or dataset ingest
  - normalize to annualized trailing trend
- update expectation: monthly or quarterly
- confidence penalty if missing: medium-high
- recommended confidence weight: `0.15`
- usage:
  - county support score
  - helps validate whether town appreciation is locally supported or isolated

### 3. `town_population_trend`

- module: town / county thesis
- source type: `market_source`
- primary source direction: census-style town population estimate dataset
- fallback source direction: county population trend, school enrollment trend later, or no fallback
- acquisition method:
  - dataset ingest
  - compute percent change over a standardized period such as 3-year or 5-year trailing
- update expectation: annual
- confidence penalty if missing: medium
- recommended confidence weight: `0.15`
- usage:
  - town demand score
  - demand durability signal rather than a direct value signal
- implementation note:
  - keep the time window explicit so the narrative can reference it honestly

### 4. `county_population_trend`

- module: town / county thesis
- source type: `market_source`
- primary source direction: county population estimate dataset
- fallback source direction: metro population trend
- acquisition method:
  - dataset ingest
  - compute trailing percent change
- update expectation: annual
- confidence penalty if missing: medium
- recommended confidence weight: `0.10`
- usage:
  - county support score
  - broader structural growth signal

### 5. `school_rating`

- module: town / county thesis
- source type: `market_source`
- primary source direction: school quality / rating dataset
- fallback source direction: district-level rating or no fallback
- acquisition method:
  - API or normalized dataset lookup by town / district
  - standardize to 0-10 scale
- update expectation: annual or when source refreshes
- confidence penalty if missing: high
- recommended confidence weight: `0.20`
- usage:
  - town demand score
  - demand durability signal, especially for family-buyer segments
- implementation note:
  - this should be treated as one signal, not the whole location thesis

### 6. `flood_risk`

- module: town / county thesis and downside / risk
- source type: `market_source`
- primary source direction: hazard / flood exposure source
- fallback source direction: parcel- or area-level flood designation summary
- acquisition method:
  - API, hazard map lookup, or normalized hazard dataset
  - convert to categorical risk bands: low / medium / high
- update expectation: annual or when source refreshes
- confidence penalty if missing: medium
- recommended confidence weight: `0.05`
- usage:
  - flood penalty in town demand score
  - direct risk narrative input
- implementation note:
  - use this conservatively; do not overstate precision

### 7. `liquidity_signal`

- module: town / county thesis
- source type: `market_source`
- primary source direction: local days-on-market / absorption / sale velocity signal
- fallback source direction: county-level days-on-market or qualitative manual flag
- acquisition method:
  - derived from structured market activity data
  - normalized into `strong`, `normal`, or `fragile`
- update expectation: monthly
- confidence penalty if missing: medium
- recommended confidence weight: `0.10`
- usage:
  - market alignment score
  - liquidity view
- implementation note:
  - this should be a synthesized signal, not a raw single metric in the final narrative

### 8. `development_tailwinds`

- module: town / county thesis
- source type: `market_source`
- primary source direction: curated local catalyst list
- fallback source direction: manual analyst note
- acquisition method:
  - initially manual capture
  - later structured feed from planning / development sources
- update expectation: as needed
- confidence penalty if missing: low-medium
- recommended confidence weight: `0.05` to `0.10`
- usage:
  - appreciation support narrative
  - explanation of why upside could be better than raw trend data implies
- implementation note:
  - should remain evidence-backed and concise, not promotional copy

### 9. `scarcity_notes`

- module: town / county thesis
- source type: `market_source`
- primary source direction: manually tagged land / zoning / supply constraints
- fallback source direction: none
- acquisition method:
  - manual structured note first
  - later derived from zoning / supply / permitting data
- update expectation: as needed
- confidence penalty if missing: low-medium
- recommended confidence weight: `0.05`
- usage:
  - supports appreciation support view
  - supports the argument that downside may be cushioned by constrained supply

### 10. `county_inventory_trend`

- module: town / county thesis
- source type: `market_source`
- primary source direction: county inventory or months-of-supply dataset
- fallback source direction: metro inventory trend
- acquisition method:
  - structured market dataset
  - normalized into tightening / steady / loosening
- update expectation: monthly
- confidence penalty if missing: medium
- recommended confidence weight: future-phase field
- usage:
  - county support score later
  - liquidity reinforcement

### 11. `county_days_on_market`

- module: town / county thesis
- source type: `market_source`
- primary source direction: county market activity dataset
- fallback source direction: metro days-on-market dataset
- acquisition method:
  - structured market dataset
  - derive normalized local liquidity benchmark
- update expectation: monthly
- confidence penalty if missing: medium
- recommended confidence weight: future-phase field
- usage:
  - liquidity view
  - market alignment benchmarking

### 12. `permit_activity`

- module: town / county thesis
- source type: `public_record`
- primary source direction: permitting or development activity dataset
- fallback source direction: manual note
- acquisition method:
  - public record ingest later
  - structured summary field rather than raw permit table in the tear sheet
- update expectation: quarterly or annual
- confidence penalty if missing: low in v1
- recommended confidence weight: future-phase field
- usage:
  - supports or weakens supply / development thesis

## Normalization Rules

To make location signals comparable, Briarwood should normalize them before scoring.

### Price Trend Normalization

Suggested v1 bands:

- `<= -5%`: 0.10
- `-5% to 0%`: 0.30
- `0% to 3%`: 0.50
- `3% to 6%`: 0.75
- `> 6%`: 0.95

### Population Trend Normalization

Suggested v1 bands:

- `<= -2%`: 0.10
- `-2% to 0%`: 0.35
- `0% to 1%`: 0.55
- `1% to 3%`: 0.75
- `> 3%`: 0.90

### School Rating Normalization

- `normalized_school_rating = school_rating / 10`

### Flood Risk Penalty

- `low` or `none`: `0`
- `medium`: `7`
- `high`: `15`

### Liquidity Signal Normalization

- `strong`: `0.90`
- `normal`: `0.60`
- `fragile`: `0.25`

### Scarcity Signal Normalization

Initial v1 should be manual:

- no note: `0.00`
- mild scarcity support: `0.50`
- strong scarcity support: `0.90`

## Missing Data Policy

If a Tier 1 field is missing:

- reduce module confidence using its weight
- list the field in `missing_inputs`
- avoid overclaiming strong local support

If county fields are missing:

- still allow the module to run
- label county context as incomplete
- reduce confidence

If both trend and school data are sparse:

- downgrade the module to a descriptive-only location view rather than a strong investment thesis

## Narrative Guardrails

The town/county module should never imply:

- guaranteed appreciation
- that good schools alone justify the purchase
- that one catalyst ensures downside protection

The module should speak in probability language:

- supportive
- mixed
- limited
- durable
- fragile

## Recommended Implementation Sequence

### Step 1

Add schema support for:

- town_price_trend
- county_price_trend
- town_population_trend
- county_population_trend
- school_rating
- flood_risk
- liquidity_signal
- development_tailwinds
- scarcity_notes

### Step 2

Build a deterministic location scoring helper:

- normalization functions
- weighted score calculation
- label mapping
- confidence calculation

### Step 3

Rewrite the existing town module around:

- town demand score
- county support score
- market alignment score
- confidence and missing input reporting

### Step 4

Update the tear sheet narrative to reflect:

- why the local market helps or hurts the hold thesis
- whether location provides real downside protection

## Summary

The town/county thesis becomes useful when every local claim in the tear sheet can answer three questions:

1. What is the signal?
2. Where did it come from?
3. How much should we trust it?

This document is intended to make those answers explicit before implementation.

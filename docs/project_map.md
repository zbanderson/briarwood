# Briarwood Project Map

## Purpose

This document breaks Briarwood into four practical workstreams:

- calculations
- formatting / reporting
- models
- data sourcing

The goal is to make the current state legible, identify the weak points, and give the project a clearer build order.

---

## 1. Calculations

### What Exists Today

#### Ownership Economics

- `income_support`
  - location: `briarwood/modules/income_support.py`
  - backing logic: `briarwood/agents/income/`
  - computes:
    - loan amount
    - monthly principal + interest
    - monthly taxes
    - monthly insurance
    - monthly HOA
    - monthly maintenance reserve
    - gross monthly carry
    - effective rent
    - support ratio
    - fallback cash flow

- `cost_valuation`
  - location: `briarwood/modules/cost_valuation.py`
  - now reuses the Income Agent backbone rather than recalculating the carry stack separately
  - computes:
    - annual NOI
    - cap rate
    - gross yield
    - DSCR
    - cash-on-cash return
    - monthly total cost
    - monthly cash flow

#### Present-Day Value

- `current_value`
  - location: `briarwood/modules/current_value.py`
  - backing logic: `briarwood/agents/current_value/`
  - computes `Briarwood Current Value (BCV)`
  - blends:
    - market-adjusted value
    - backdated listing-aligned value
    - income-supported value
  - also returns:
    - low/high value range
    - mispricing amount
    - mispricing percentage
    - pricing view
    - component weights
    - confidence
    - assumptions
    - unsupported claims
    - warnings

#### Forward Value

- `bull_base_bear`
  - location: `briarwood/modules/bull_base_bear.py`
  - currently uses:
    - market history
    - location score
    - risk score
    - income support
  - important:
    - still heuristic
    - currently framed as 12-month outlook
    - should not be confused with BCV

#### Risk / Location / Scarcity

- `risk_constraints`
  - deterministic risk-flag module
- `town_county_outlook`
  - location thesis engine
- `scarcity_support`
  - scarcity + demand consistency layer

### Current Strengths

- ownership economics are now relatively coherent
- BCV gives the platform a real “today’s value” anchor
- forward value is more grounded than the original markup model
- confidence and unsupported-claim concepts are now established in several places

### Main Weaknesses

- forward scenario math is still heuristic
- school signal is still weak / partly placeholder
- scarcity inputs are still thin
- some calculation confidence is still implied by completeness more than true source strength

### Recommended Next Steps

1. tune BCV component weights with real-world examples
2. decide whether BCV should become the formal anchor for forward scenario generation
3. strengthen scarcity calculations with sourced anchor / lot benchmark inputs
4. add a more explicit section-level confidence model to all major calculations

---

## 2. Formatting / Reporting

### What Exists Today

- tear sheet builder:
  - `briarwood/reports/tear_sheet.py`
- renderer:
  - `briarwood/reports/renderer.py`
- HTML template:
  - `briarwood/reports/templates/tear_sheet.html`
- CSS:
  - `briarwood/reports/assets/tear_sheet.css`

### Major Report Sections

- header
- conclusion
- thesis
- historic market + forward chart
- market durability
- fallback rental support
- bull / base / bear case cards

### Current Strengths

- BCV is now visible in the tear sheet
- BCV range and pricing view are visible
- chart now shows:
  - ask
  - market reference
  - BCV
  - forward fan
- copy now distinguishes:
  - present-day value
  - 12-month outlook

### Main Weaknesses

- some report sections still do too much interpretation locally
- evidence trails are still thinner than they should be
- assumptions and unsupported claims are not yet surfaced consistently across sections
- some sections can still look more confident than their inputs deserve

### Recommended Next Steps

1. add a compact “confidence / evidence” panel to the tear sheet
2. surface assumptions and unsupported claims more consistently
3. push more narrative-ready summaries upstream from modules instead of composing so much meaning inside section builders
4. keep refining the copy so client-facing language stays honest when evidence is thin

---

## 3. Models

### What Exists Today

#### Canonical App Models

- `briarwood/schemas.py`
  - `PropertyInput`
  - `ModuleResult`
  - `ValuationOutput`
  - `ScenarioOutput`
  - `AnalysisReport`

#### Agent Models

- pydantic models inside:
  - `briarwood/agents/income/`
  - `briarwood/agents/current_value/`
  - `briarwood/agents/market_history/`
  - `briarwood/agents/town_county/`
  - `briarwood/agents/scarcity/`

#### Report Models

- `briarwood/reports/schemas.py`
  - section dataclasses
  - tear-sheet dataclass

### Current Strengths

- typed contracts are getting stronger
- agent logic is generally better isolated from rendering than earlier in the project
- the engine still stays simple

### Main Weaknesses

- `PropertyInput` is starting to accumulate too many concerns
  - raw facts
  - sourced signals
  - user assumptions
  - report-oriented convenience fields
- some older dataclass shapes are looser than the newer pydantic agent contracts

### Recommended Next Steps

1. formally split canonical inputs into:
   - property facts
   - market signals
   - user assumptions
2. keep dataclasses for orchestration where helpful, but continue using pydantic for stricter agent inputs/outputs
3. remove or archive stale module files no longer in the active pipeline
4. avoid adding more mixed-purpose fields to `PropertyInput` unless necessary

---

## 4. Data Sourcing

### What Exists Today

#### Listing / Intake Layer

- listing text parser and normalizer
- extracted fields include:
  - address
  - price
  - beds / baths
  - sqft
  - lot size
  - property type
  - year built
  - HOA
  - taxes
  - price history
  - tax history
  - DOM

#### Market / Location Sources

- Important guardrail:
  - Briarwood does not scrape live Zillow listing pages.
  - Zillow URLs are treated as metadata-only inputs.
  - richer listing fields come from user-provided pasted listing text or file-backed datasets.

- Zillow-style market history
  - `data/market_history/zillow_zhvi_history.json`
- town / county price trends
  - `data/town_county/price_trends.json`
- population trends
  - `data/town_county/population_trends.json`
- flood risk
  - `data/town_county/flood_risk.json`
- liquidity proxy
  - `data/town_county/liquidity.json`

### Current Strengths

- market-level context is now fairly strong for an early-stage project
- town/county sourcing has a clean adapter / provider / bridge / service path
- missing data generally reduces confidence rather than being fabricated

### Main Weaknesses

- school signal is not yet truly sourced in the live path
- rent sourcing is still weak or absent for many listings
- insurance is still often missing
- scarcity inputs are not yet sourced well:
  - anchor distance
  - comparable count within anchor radius
  - local median lot size
  - corner / ADU / redevelopment benchmarks
- condition / renovation clues are not yet structured into a real source-backed property adjustment input

### Recommended Next Steps

1. school signal
   - define source of truth
   - make it explicit whether it is official, market-facing, or Briarwood-derived
2. rent sourcing
   - even if v1 starts manual or estimate-based, it needs source and confidence fields
3. scarcity inputs
   - start with anchor distance + local lot benchmark support
4. insurance assumptions
   - define a safe sourcing / assumption strategy

---

## Cross-Cutting Priorities

These themes cut across all four workstreams.

### A. Make Weak Evidence Visible

Every important output should make it clear when:

- data is missing
- logic is heuristic
- confidence is low
- a conclusion depends on assumptions

### B. Separate Present Value From Forward Outlook

The product should keep these concepts distinct:

- BCV = today’s Briarwood estimate
- bull / base / bear = 12-month outlook

### C. Avoid Silent Fallbacks

Defaults are acceptable only when:

- they are intentional
- they are documented
- they lower confidence or add warnings where appropriate

### D. Prefer Reusable Business Logic

When possible:

- calculations should live in agents or helper layers
- modules should adapt those results to the engine contract
- report sections should not quietly invent new business logic

---

## Suggested Execution Order

### Near Term

1. strengthen data sourcing for school, rent, and scarcity inputs
2. keep tuning BCV and forward-scenario relationships
3. improve evidence / confidence visibility in the tear sheet

### Medium Term

1. split the canonical input model into facts / signals / assumptions
2. reduce report-layer interpretation and move more meaning upstream
3. retire stale files and cleanup repo noise

### Longer Term

1. make BCV the stable present-day valuation primitive across the platform
2. make forward scenario logic explicitly hold-period aware
3. connect richer property-specific sourcing into scarcity and current-value adjustments

# Briarwood Decision Report Strategy

## Purpose

Briarwood should help a real estate agent explain a property's likely upside, downside, and resilience in a way that reduces buyer anxiety and improves decision quality.

The report is not primarily a rental underwriting memo. It is a property-specific decision de-risking tool.

## Product Promise

For any given property, Briarwood should help answer:

- Why could this property work?
- What is the buyer really betting on?
- What is the realistic downside if the thesis is only partly right?
- How protected is the buyer if life changes?
- How confident are we in each of those claims?

## Core Lenses

The product should evaluate each property through three parallel lenses:

1. Asset Value Lens
   - What is the property likely worth now?
   - What is a reasonable forward value range over the planned hold period?

2. Owner Risk Lens
   - What are the main ownership risks?
   - What assumptions must hold for the buyer to exit safely?

3. Fallback Optionality Lens
   - If the buyer needs to pivot, can the property realistically rent?
   - Would rental income materially offset carrying cost?

## Input Taxonomy

Inputs should be separated into three categories so the report can clearly distinguish fact from estimate from personalization.

### 1. Property Facts

Observed or directly sourced data about the asset:

- property_id
- address
- town
- state
- zip_code
- property_type
- beds
- baths
- sqft
- lot_sqft
- year_built
- days_on_market
- ask_price
- hoa_monthly
- annual_taxes
- price_history
- tax_history
- source_url
- source_name

### 2. Market Signals

Externally derived or modeled inputs:

- market_reference_value
- market_reference_source
- market_reference_date
- estimated_monthly_rent
- rent_source
- rent_confidence
- town_price_trend
- town_population_trend
- school_rating
- flood_risk
- development_tailwinds
- scarcity_notes
- liquidity_signal

### 3. User Assumptions

Buyer-specific assumptions that affect ownership economics but not intrinsic property value:

- down_payment_pct
- interest_rate
- loan_term_years
- target_hold_years
- vacancy_pct
- maintenance_pct
- annual_insurance
- closing_cost_estimate
- renovation_budget

## Proposed Canonical Models

These are proposed conceptual models for the next schema refactor.

### PropertyFacts

```python
@dataclass(slots=True)
class PropertyFacts:
    property_id: str
    address: str
    town: str
    state: str
    zip_code: str | None = None
    property_type: str | None = None
    beds: int | None = None
    baths: float | None = None
    sqft: int | None = None
    lot_sqft: int | None = None
    year_built: int | None = None
    days_on_market: int | None = None
    ask_price: float | None = None
    annual_taxes: float | None = None
    monthly_hoa: float | None = None
    price_history: list[dict] = field(default_factory=list)
    tax_history: list[dict] = field(default_factory=list)
    source_url: str | None = None
    source_name: str | None = None
```

### MarketData

```python
@dataclass(slots=True)
class MarketData:
    market_reference_value: float | None = None
    market_reference_source: str | None = None
    market_reference_date: str | None = None
    estimated_monthly_rent: float | None = None
    rent_source: str | None = None
    rent_confidence: float | None = None
    town_price_trend: float | None = None
    town_population_trend: float | None = None
    school_rating: float | None = None
    flood_risk: str | None = None
    development_tailwinds: list[str] = field(default_factory=list)
    scarcity_notes: list[str] = field(default_factory=list)
    liquidity_signal: str | None = None
```

### UserAssumptions

```python
@dataclass(slots=True)
class UserAssumptions:
    down_payment_pct: float | None = None
    interest_rate: float | None = None
    loan_term_years: int = 30
    target_hold_years: int = 3
    vacancy_pct: float | None = None
    maintenance_pct: float | None = None
    annual_insurance: float | None = None
    closing_cost_estimate: float | None = None
    renovation_budget: float | None = None
```

### PropertyDossier

```python
@dataclass(slots=True)
class PropertyDossier:
    facts: PropertyFacts
    market: MarketData
    assumptions: UserAssumptions
```

## Section-Level Confidence

Confidence should be computed per claim, not as one flat project-wide number.

Each section should expose:

- confidence_score
- missing_inputs
- assumptions_used
- unsupported_claims

### Example Confidence Buckets

#### Value Confidence

- ask_price: high weight
- market_reference_value: high weight
- sqft: high weight
- price_history: medium weight
- town_price_trend: medium weight

#### Risk Confidence

- flood_risk: high weight
- year_built: medium weight
- days_on_market: medium weight
- tax_history: medium weight

#### Fallback Rental Confidence

- estimated_monthly_rent: very high weight
- annual_taxes: medium weight
- annual_insurance: medium weight
- monthly_hoa: medium weight
- vacancy_pct: medium weight
- maintenance_pct: medium weight

## Report Structure

The tear sheet should evolve toward these sections:

### 1. Opportunity

Explain why the property could work:

- town development
- scarcity
- pricing relative to market reference
- hold-period upside

### 2. Downside

Explain the main ways the thesis could fail:

- overpaying versus likely exit value
- weak liquidity
- hidden capex
- macro or local market softness

### 3. Resilience

Explain how survivable the property is if the original plan changes:

- fallback rentability
- carrying cost coverage
- likely hold flexibility
- severity of forced-sale risk

### 4. Confidence

Explain how much of the report is supported by strong inputs versus assumptions.

## Agent Narrative Standard

The report should support a simple agent conversation:

- "Here is why this property could work."
- "Here is what you are really betting on."
- "Here is what could go wrong."
- "Here is why the downside is manageable, or why it is not."
- "Here is the backup plan if life changes."

## Immediate Data Priorities

The next implementation wave should focus on the highest-value missing inputs.

### Priority 1: Preserve Existing Intake Data Better

Carry forward data already parsed but currently dropped:

- monthly_hoa
- tax_history
- price_history
- source metadata

### Priority 2: Introduce Market Data Inputs

Add first-class support for:

- market_reference_value
- estimated_monthly_rent
- rent_source
- rent_confidence
- town growth signals

### Priority 3: Introduce User Assumptions

Add a separate assumptions object for:

- interest rate
- down payment
- hold period
- insurance
- maintenance
- vacancy

### Priority 4: Add Section-Level Confidence

Every report section should describe:

- what it knows
- what it assumes
- how trustworthy the conclusion is

## Near-Term Refactor Plan

### Phase 1: Input Contract Cleanup

- extend listing-normalized data to preserve more ownership-relevant fields
- stop collapsing missing values into silent zeros when the field is decision-critical
- separate observed fields from assumption-driven fields

### Phase 2: Fallback Rental Lens

- rename the Income Agent conceptually toward fallback rental support
- treat rentability as downside protection, not the universal investment thesis
- expose warnings when rental support is based on weak or estimated data

### Phase 3: Value And Hold-Period Lens

- add market reference value
- add hold-period framing
- support a 2-year / 3-year / 5-year forward range

### Phase 4: Confidence And Narrative

- add weighted section confidence
- rewrite tear sheet language around opportunity, downside, resilience, and confidence
- expose assumptions directly in the rendered report

## Practical Definition Of "Good Enough"

A property should not receive a strong reassurance-oriented investment narrative unless Briarwood has at least:

- ask price
- taxes
- sqft or a strong substitute
- market reference value
- basic local context
- user financing assumptions for ownership-cost analysis

Fallback rental commentary should require at least:

- rent estimate
- taxes
- insurance assumption
- HOA
- vacancy
- maintenance

If those fields are missing, the report should still render, but it should explicitly downgrade confidence and narrow the scope of its claims.

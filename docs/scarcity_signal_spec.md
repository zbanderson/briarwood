# Briarwood Scarcity Signal Specification

## Purpose

This document defines how Briarwood should think about scarcity.

Scarcity is not just "low supply." It is the degree to which a property's most valuable traits are difficult to replicate in the local market.

For Briarwood, scarcity only matters if it is also paired with consistent demand.

That means the product should distinguish between:

- something that is rare
- something that is rare and consistently wanted

This distinction matters because some properties are unusual but not especially liquid.

## Core Principle

Briarwood should not say:

- "This is scarce, therefore it is safe."

It should say:

- "This property has traits that are hard to replicate, and the market appears to consistently reward those traits."

## Two-Part Model

Scarcity should be split into two related but separate ideas:

### 1. `scarcity_score`

How difficult is it to replicate the property's core value drivers?

### 2. `demand_consistency_score`

How reliably does the local market absorb and reward those scarce traits?

These should combine into:

### 3. `scarcity_support_score`

The degree to which scarcity meaningfully supports price durability, resale liquidity, and medium-term hold confidence.

## The Five Scarcity Components

### 1. Location Scarcity

This is the strongest and most intuitive form of scarcity.

Question:

- How hard is it to find comparable properties in the same proximity to a demand anchor?

Examples:

- oceanfront or beach proximity
- walkable downtown access
- ski-adjacent location
- trail adjacency

Key concepts:

- distance to anchor feature
- number of comparable properties within the same radius
- whether buyers demonstrably pay for that radius

### 2. Land Scarcity

This captures the rarity and optionality of the lot itself.

Questions:

- How many lots like this exist locally?
- Can similar lots realistically be created?
- Is the lot oversized, deeper, wider, or more flexible than neighborhood norms?

Examples:

- oversized lot in a tight-lot town
- double lot
- corner lot with superior frontage and light
- lot with ADU or redevelopment optionality

### 3. Structural Scarcity

This is about the built product, not just the land.

Questions:

- Is this home type unusual for the area?
- Does it solve a common local constraint better than nearby inventory?
- Does it offer a materially better layout, parking, bedroom count, or construction quality?

Examples:

- new construction in an older housing-stock town
- 3-bed where most supply is 2-bed
- garage and parking in a constrained market
- superior layout in a neighborhood full of functionally obsolete homes

### 4. Regulatory Scarcity

This is future-supply constraint.

Questions:

- Can more of this product type be built?
- Do zoning or local rules limit future supply?
- Do regulations increase the rarity of legal competing inventory?

Examples:

- zoning that prevents density
- ADU allowed versus disallowed
- historic district limits
- short-term rental restrictions that reduce legal rental competition

### 5. Experiential Scarcity

This is the emotional or sensory quality that buyers pay for.

Questions:

- Does the property offer something hard to replicate experientially?
- Is there a meaningful "feel premium" that nearby substitutes do not match?

Examples:

- water views
- sunset orientation
- quiet street in a busy town
- hidden-pocket location
- unusual privacy, light, or atmosphere

This is important, but it is also the least safely quantifiable in early versions.

## Computable vs Qualitative

Not all scarcity types should be forced into faux precision.

### Strongly Computable In V1 / V2

- location scarcity
- land scarcity
- parts of structural scarcity
- parts of regulatory scarcity

### Partially Computable

- demand consistency
- structural desirability premiums

### Mostly Qualitative For Now

- experiential scarcity
- nuanced neighborhood feel

## Proposed Output Model

```python
@dataclass(slots=True)
class ScarcitySignal:
    location_scarcity_score: float | None
    land_scarcity_score: float | None
    structural_scarcity_score: float | None
    regulatory_scarcity_score: float | None
    experiential_scarcity_score: float | None
    scarcity_score: float | None
    demand_consistency_score: float | None
    scarcity_support_score: float | None
    scarcity_label: str
    confidence: float
    demand_drivers: list[str]
    scarcity_notes: list[str]
    missing_inputs: list[str]
    unsupported_claims: list[str]
    summary: str
```

## Suggested Scoring Philosophy

### Step 1: Score Each Scarcity Dimension

Each component should be scored independently on a `0-100` scale when enough data exists.

### Step 2: Compute `scarcity_score`

Suggested weighting:

```text
scarcity_score =
    0.30 * location_scarcity_score +
    0.25 * land_scarcity_score +
    0.20 * structural_scarcity_score +
    0.15 * regulatory_scarcity_score +
    0.10 * experiential_scarcity_score
```

If some components are missing, Briarwood should reweight only populated components, but reduce confidence.

### Step 3: Compute `demand_consistency_score`

This should use signals like:

- local liquidity
- buyer absorption / months of supply
- town price trend
- county price trend
- repeat demand support from schools, walkability, or local buyer profile

### Step 4: Compute `scarcity_support_score`

Suggested concept:

```text
scarcity_support_score =
    0.60 * scarcity_score +
    0.40 * demand_consistency_score
```

This prevents Briarwood from overvaluing rare-but-illiquid assets.

## Labeling

Suggested labels:

- `>= 75`: high scarcity support
- `60-74`: meaningful scarcity support
- `45-59`: limited scarcity support
- `< 45`: weak scarcity support

## Component Definitions

### Location Scarcity Score

Primary idea:

- close to a demand anchor
- few comparable substitutes in the same radius

Potential inputs:

- distance to anchor feature
- count of comparable properties within same radius
- share of local stock inside premium radius

### Land Scarcity Score

Primary idea:

- unusual lot quality or development optionality

Potential inputs:

- lot size percentile within local competitive set
- frontage / corner / depth flags
- lot configuration rarity
- redevelopment / ADU potential

### Structural Scarcity Score

Primary idea:

- unusually desirable physical product for the local market

Potential inputs:

- bedroom / bathroom configuration rarity
- parking rarity
- construction vintage premium
- layout or feature premiums later

### Regulatory Scarcity Score

Primary idea:

- future competing supply is difficult to create

Potential inputs:

- zoning constraint signals
- density restriction signals
- legal rental limitation signals
- historical district / permit friction signals

### Experiential Scarcity Score

Primary idea:

- hard-to-copy emotional or sensory value

Potential inputs:

- view flags
- orientation flags
- adjacency flags
- quiet / hidden-pocket note

This should remain low-confidence unless explicitly supported.

## Demand Consistency Definition

Scarcity is only useful if demand reliably shows up for it.

Demand consistency should answer:

- Is this kind of scarcity consistently rewarded in this market?
- Does the local market absorb it with reasonable liquidity?
- Would buyers still care about this in a normal resale environment?

Potential inputs:

- liquidity signal
- months of supply
- days on market
- town trend
- county trend
- school / family demand support

## Confidence Rules

Briarwood should not force a full scarcity thesis when only one type of scarcity is present.

Confidence should drop when:

- scarcity is based mostly on qualitative notes
- demand consistency is weakly evidenced
- regulatory assumptions are not supported
- experiential scarcity is asserted without clear support

Suggested confidence buckets:

- `high`: multiple scarcity dimensions plus source-backed demand evidence
- `moderate`: one or two clear scarcity dimensions with some demand support
- `low`: mostly qualitative or manually asserted scarcity

## Narrative Role

The scarcity signal should help answer:

- Why might buyers continue to pay up for this property?
- Why might downside be cushioned?
- Why might this property remain more liquid than nearby substitutes?

It should not imply:

- guaranteed appreciation
- that rarity alone solves overpaying
- that every special-feeling property deserves a premium

## Example Narrative Styles

### Strong

"This property benefits from real scarcity support: its location and lot profile are difficult to replicate, and the local market appears to consistently reward those traits. That strengthens both the hold thesis and the resale safety net."

### Moderate

"The property has some meaningful scarcity features, but the support is not universal. Scarcity helps the story, though it should be viewed as one supporting factor rather than the sole reason the deal works."

### Weak

"The property may be appealing, but Briarwood does not yet see strong evidence that its distinctive traits translate into durable scarcity support in this market."

## Recommended Build Order

### Phase 1

Define and score:

- location scarcity
- land scarcity
- demand consistency

### Phase 2

Add:

- structural scarcity
- regulatory scarcity

### Phase 3

Layer in:

- experiential scarcity as a low-confidence qualitative support signal

## Summary

For Briarwood, scarcity should mean:

- hard to replicate
- consistently desired
- actually supportive of resale and pricing durability

That is a much more useful definition than simple rarity, and it fits the product's job of helping an agent explain why a property may be more protected than it looks on a basic spreadsheet.

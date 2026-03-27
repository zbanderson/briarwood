# Briarwood Scarcity Scorer Design

## Purpose

This document defines the first implementation design for Briarwood's scarcity scorer.

It translates the scarcity framework into:

- concrete input models
- deterministic scoring logic
- confidence handling
- narrative outputs
- implementation phases

The goal is to make scarcity useful in the report without pretending we can quantify everything on day one.

## Design Goal

The scarcity scorer should answer:

- What is hard to replicate about this property?
- Does the market consistently reward those traits?
- Does that support resale durability and medium-term downside protection?

## Output Philosophy

The scorer should not produce one mysterious number.

It should expose:

- component scores
- combined scarcity score
- demand consistency score
- final scarcity support score
- confidence
- missing inputs
- unsupported claims
- human-readable explanation

## Proposed Input Model

```python
@dataclass(slots=True)
class ScarcityInputs:
    town: str
    state: str
    county: str | None = None

    distance_to_anchor_miles: float | None = None
    comparable_count_within_anchor_radius: int | None = None
    anchor_radius_miles: float | None = None

    lot_size_sqft: int | None = None
    local_median_lot_size_sqft: int | None = None
    lot_is_corner: bool | None = None
    adu_possible: bool | None = None
    redevelopment_optional: bool | None = None

    bedrooms: int | None = None
    bathrooms: float | None = None
    parking_spaces: int | None = None
    local_median_bedrooms: float | None = None
    local_median_parking: float | None = None
    new_construction_relative_to_market: bool | None = None

    density_restricted: bool | None = None
    short_term_rental_restricted: bool | None = None
    historic_district: bool | None = None

    experiential_flags: list[str] = field(default_factory=list)

    liquidity_signal: str | None = None
    months_of_supply: float | None = None
    town_price_trend: float | None = None
    county_price_trend: float | None = None
    school_signal: float | None = None
```

## Proposed Output Model

```python
@dataclass(slots=True)
class ScarcityScore:
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

## Scoring Architecture

The scorer should work in three layers:

### Layer 1: Component Scores

Score each scarcity dimension independently.

### Layer 2: Scarcity Score

Combine component scarcity dimensions into one `scarcity_score`.

### Layer 3: Scarcity Support Score

Blend `scarcity_score` with `demand_consistency_score`.

That final score is the one the report should care about most.

## Component 1: Location Scarcity

### What It Means

The property is close to a demand anchor that has limited nearby substitutes.

### Computable Inputs

- distance_to_anchor_miles
- comparable_count_within_anchor_radius
- anchor_radius_miles

### Suggested V1 Logic

Start with a score from 50 and adjust:

- add points for tighter anchor proximity
- add points for fewer nearby comparables
- reduce score when comparable count is high

Example rule shape:

```text
location_scarcity_score = 50
```

Adjustments:

- `+20` if distance is very close to anchor
- `+15` if comparable_count_within_anchor_radius <= 10
- `+10` if comparable_count_within_anchor_radius <= 20
- `-10` if comparable_count_within_anchor_radius > 50

Clamp to `0-100`.

### Confidence

High only if anchor definition and comparable count are actually sourced.

## Component 2: Land Scarcity

### What It Means

The lot itself is hard to replicate locally.

### Computable Inputs

- lot_size_sqft
- local_median_lot_size_sqft
- lot_is_corner
- adu_possible
- redevelopment_optional

### Suggested V1 Logic

```text
land_scarcity_score = 50
```

Adjustments:

- compare lot size to local median
- add value for corner lot
- add value for ADU or redevelopment optionality

Example:

- `+15` if lot >= 1.5x local median
- `+10` if lot >= 1.25x local median
- `+5` if corner lot
- `+10` if ADU possible
- `+10` if redevelopment optional

Clamp to `0-100`.

### Confidence

Moderate to high when local lot benchmarks are source-backed.

## Component 3: Structural Scarcity

### What It Means

The structure provides a product type or feature set that is uncommon and desirable in the local market.

### Computable Inputs

- bedrooms
- bathrooms
- parking_spaces
- local_median_bedrooms
- local_median_parking
- new_construction_relative_to_market

### Suggested V1 Logic

```text
structural_scarcity_score = 50
```

Adjustments:

- `+10` if bedroom count exceeds local median
- `+10` if parking exceeds local norm
- `+10` if new-construction style product is rare in an older market

Clamp to `0-100`.

### Confidence

Moderate initially. This gets much better when local inventory benchmarks are available.

## Component 4: Regulatory Scarcity

### What It Means

Rules make future competing supply harder to create.

### Computable Inputs

- density_restricted
- short_term_rental_restricted
- historic_district

### Suggested V1 Logic

```text
regulatory_scarcity_score = 50
```

Adjustments:

- `+15` if density is restricted
- `+10` if STR supply is restricted
- `+5` if historic constraints materially limit replacement stock

Clamp to `0-100`.

### Confidence

Only high when these are actually sourced from zoning or regulatory inputs, not assumed.

## Component 5: Experiential Scarcity

### What It Means

The property offers sensory or emotional value that is hard to reproduce.

### Inputs

- experiential_flags

Examples:

- water_view
- sunset_orientation
- quiet_street
- hidden_pocket
- unusual_privacy

### Suggested V1 Logic

This should be intentionally conservative.

```text
experiential_scarcity_score = None by default
```

If structured experiential flags exist:

- start at `50`
- add small increments for supported flags
- cap confidence low unless supported by real source evidence

### Confidence

Low in v1.

## Scarcity Score

Once the component scores are available:

```text
scarcity_score =
    0.30 * location_scarcity_score +
    0.25 * land_scarcity_score +
    0.20 * structural_scarcity_score +
    0.15 * regulatory_scarcity_score +
    0.10 * experiential_scarcity_score
```

If some components are missing:

- reweight only populated components
- reduce confidence
- list missing inputs and unsupported claims

## Demand Consistency Score

### What It Means

How reliably does the market reward this scarcity?

### Inputs

- liquidity_signal
- months_of_supply
- town_price_trend
- county_price_trend
- school_signal

### Suggested V1 Logic

```text
demand_consistency_score = 50
```

Adjustments:

- `+15` for strong liquidity
- `+10` for normal liquidity
- `-15` for fragile liquidity
- `+10` if town_price_trend > 3%
- `+5` if county_price_trend > 3%
- `+10` if school_signal >= 7

Clamp to `0-100`.

### Why This Matters

This is the guardrail that prevents Briarwood from overvaluing weird but illiquid assets.

## Scarcity Support Score

```text
scarcity_support_score =
    0.60 * scarcity_score +
    0.40 * demand_consistency_score
```

This final score should be the primary report output.

## Label Mapping

Suggested:

- `>= 75`: high scarcity support
- `60-74`: meaningful scarcity support
- `45-59`: limited scarcity support
- `< 45`: weak scarcity support

## Confidence Model

Confidence should reflect:

- how many scarcity components are actually populated
- whether the inputs are source-backed or manual
- whether demand consistency is evidence-backed

Suggested component weights:

- location scarcity inputs: 0.25
- land scarcity inputs: 0.20
- structural scarcity inputs: 0.15
- regulatory scarcity inputs: 0.15
- experiential scarcity inputs: 0.05
- demand consistency inputs: 0.20

## Anti-Hallucination Rules

The scorer must not:

- invent local benchmark values
- imply experiential premiums without support
- assume regulatory constraints without source-backed evidence
- equate rarity with demand

If core inputs are missing:

- lower confidence
- narrow the summary language
- add explicit unsupported claims

## Narrative Responsibilities

The scarcity scorer should help the report say:

- why this property may hold value better than nearby substitutes
- what is difficult to replicate about it
- whether the local market consistently rewards those traits

It should not say:

- that scarcity guarantees appreciation
- that every unique property deserves a premium

## Suggested Build Order

### Phase 1

Build first:

- demand_consistency_score
- location_scarcity_score
- land_scarcity_score

These are likely the strongest early wins.

### Phase 2

Add:

- structural_scarcity_score
- regulatory_scarcity_score

### Phase 3

Add:

- experiential_scarcity_score as a low-confidence qualitative layer

## Immediate Practical Recommendation

If we want the next highest-signal implementation, start with:

1. demand consistency
2. location scarcity
3. land scarcity

That will let Briarwood say something meaningful without pretending to fully quantify every kind of specialness.

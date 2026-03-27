# Briarwood Town / County Scoring Helper

## Purpose

This document defines the first deterministic scoring helper for Briarwood's town / county investment thesis.

It is designed to answer:

- Does the location support a 2-3 year hold thesis?
- Does the broader market improve downside protection?
- Is the local market likely to remain liquid enough for a reasonable exit?

This helper should be:

- explicit
- easy to explain
- easy to test
- source-aware

## Design Principle

The scoring helper should not depend on listing-page content.

Most of the fields required for a credible town / county thesis should come from:

- official public datasets
- stable market datasets
- Briarwood-derived normalization rules

Where a consumer-facing "rating" does not exist in a stable official source, Briarwood should compute its own proxy rather than relying blindly on third-party listing UX.

## Proposed Output Shape

```python
@dataclass(slots=True)
class TownCountyScore:
    town_demand_score: float
    county_support_score: float | None
    market_alignment_score: float
    town_county_score: float
    location_thesis_label: str
    appreciation_support_view: str
    liquidity_view: str
    confidence: float
    demand_drivers: list[str]
    demand_risks: list[str]
    missing_inputs: list[str]
    assumptions_used: list[str]
    unsupported_claims: list[str]
    summary: str
```

## Input Shape

```python
@dataclass(slots=True)
class TownCountyInputs:
    town: str
    state: str
    county: str | None = None
    town_price_trend: float | None = None
    county_price_trend: float | None = None
    town_population_trend: float | None = None
    county_population_trend: float | None = None
    school_signal: float | None = None
    flood_risk: str | None = None
    liquidity_signal: str | None = None
    scarcity_signal: float | None = None
    days_on_market: int | None = None
    price_position: str | None = None
    data_as_of: str | None = None
```

## Actual Source Recommendations

These source choices are meant to be realistic and durable.

### 1. Town / County Price Trend

Recommended source:

- Zillow Research ZHVI datasets

Why:

- official Zillow research dataset
- monthly updates
- available at multiple geographies
- directly aligned with home-value trend use cases

Use:

- trailing 12-month percent change for towns / cities where available
- county-level trailing 12-month percent change for county support

Reference:

- Zillow Housing Data: https://www.zillow.com/research/data/
- ZHVI methodology: https://www.zillow.com/research/methodology-neural-zhvi-32128/

Fallback:

- FHFA HPI or other official home-price index at county / metro level if needed

Implementation note:

- use one standardized trend definition everywhere
- preferred v1 definition: `(latest_value / value_12_months_ago) - 1`

### 2. Town / County Population Trend

Recommended source:

- U.S. Census Bureau ACS 5-year data or population estimate datasets

Why:

- official source
- stable geographic coverage for places and counties
- suitable for durable-demand context

Use:

- compute trailing multi-year percent change
- keep the window explicit in the narrative

Reference:

- ACS 5-Year API/data docs: https://www.census.gov/data/developers/data-sets/acs-5year.html

Implementation note:

- this is slower-moving than price data
- treat it as structural support, not a near-term trading signal

### 3. School Signal

Recommended source strategy:

- use official NCES / CCD / EDFacts data as the foundation
- compute a Briarwood school proxy rather than importing a consumer rating as truth

Why:

- there is no single official federal "school rating" equivalent to a consumer 0-10 score
- official sources exist for school and district data, but Briarwood should own the normalization

Primary official references:

- NCES CCD: https://nces.ed.gov/ccd/
- About CCD: https://nces.ed.gov/ccd/aboutccd.asp
- EDFacts overview: https://www.ed.gov/data/edfacts-initiative

V1 recommendation:

- if a stable third-party rating is not yet integrated, allow `school_signal` to be absent
- do not fake precision
- later build a Briarwood `school_signal` from official district-level indicators

Implementation note:

- short term, a third-party school rating can be used operationally if needed
- but Briarwood should label it as a market signal, not an official fact

### 4. Flood Risk

Recommended source:

- FEMA National Risk Index

Why:

- official FEMA source
- county and census tract level coverage
- designed for hazard risk communication

Reference:

- FEMA National Risk Index overview: https://www.fema.gov/ilo/flood-maps/products-tools/national-risk-index
- NRI map/tool: https://hazards.fema.gov/nri/

Use:

- convert area-level flood risk into Briarwood bands: `low`, `medium`, `high`

Implementation note:

- this should be a risk flag, not a hyper-precise parcel claim unless Briarwood later adds parcel-level hazard data

### 5. Liquidity Signal

Recommended source strategy:

- derive from market activity datasets rather than relying on one static public number

Best near-term source options:

- Zillow market activity signals if available in research datasets
- county/city sale velocity or days-on-market datasets from stable market data providers

V1 recommendation:

- treat liquidity as a derived field that may initially be missing
- do not block the module if absent

### 6. Scarcity Signal

Recommended source strategy:

- manual structured note first
- later derive from zoning, supply, and permitting data

Why:

- scarcity is real but hard to reduce to one trustworthy public scalar immediately
- better to use an explicit note than a fake model

## Scoring Formula

### Step 1: Normalize Inputs

#### Price Trend Normalization

```python
def normalize_price_trend(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= -0.05:
        return 0.10
    if value <= 0.00:
        return 0.30
    if value <= 0.03:
        return 0.50
    if value <= 0.06:
        return 0.75
    return 0.95
```

#### Population Trend Normalization

```python
def normalize_population_trend(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= -0.02:
        return 0.10
    if value <= 0.00:
        return 0.35
    if value <= 0.01:
        return 0.55
    if value <= 0.03:
        return 0.75
    return 0.90
```

#### School Signal Normalization

```python
def normalize_school_signal(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(value / 10.0, 1.0))
```

#### Flood Penalty

```python
def flood_penalty(value: str | None) -> float:
    if value in {"none", "low", None}:
        return 0.0
    if value == "medium":
        return 7.0
    if value == "high":
        return 15.0
    return 0.0
```

#### Liquidity Normalization

```python
def normalize_liquidity_signal(value: str | None) -> float | None:
    if value is None:
        return None
    mapping = {
        "strong": 0.90,
        "normal": 0.60,
        "fragile": 0.25,
    }
    return mapping.get(value)
```

#### Scarcity Normalization

```python
def normalize_scarcity_signal(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(value, 1.0))
```

### Step 2: Town Demand Score

```python
town_demand_score = (
    35 * normalized_town_price_trend +
    20 * normalized_town_population_trend +
    25 * normalized_school_signal +
    10 * normalized_scarcity_signal +
    10 * normalized_liquidity_signal -
    flood_penalty_value
)
```

Missing fields should contribute zero to score but reduce confidence.

### Step 3: County Support Score

```python
county_support_score = (
    60 * normalized_county_price_trend +
    40 * normalized_county_population_trend
)
```

If both county inputs are missing, set `county_support_score = None`.

### Step 4: Market Alignment Score

Start simple and deterministic:

```python
market_alignment_score = 50
```

Adjustments:

- `+10` if days_on_market is not None and `< 21`
- `+5` if days_on_market is not None and `21 <= days_on_market <= 45`
- `-10` if days_on_market is not None and `> 60`
- `-10` if price_position == "stretched"
- `+5` if price_position == "supported"`
- `-10` if core property inputs are missing badly enough to impair liquidity judgment

Clamp to `0-100`.

### Step 5: Combined Score

If county score is present:

```python
town_county_score = (
    0.50 * town_demand_score +
    0.25 * county_support_score +
    0.25 * market_alignment_score
)
```

If county score is absent:

```python
town_county_score = (
    0.65 * town_demand_score +
    0.35 * market_alignment_score
)
```

### Step 6: Label Mapping

```python
def thesis_label(score: float) -> str:
    if score >= 75:
        return "strong"
    if score >= 60:
        return "supportive"
    if score >= 45:
        return "mixed"
    return "weak"
```

### Step 7: Confidence

Use weighted completeness, not the score itself.

```python
weights = {
    "town_price_trend": 0.20,
    "town_population_trend": 0.15,
    "school_signal": 0.20,
    "county_price_trend": 0.15,
    "county_population_trend": 0.10,
    "liquidity_signal": 0.10,
    "scarcity_signal": 0.05,
    "flood_risk": 0.05,
}
```

```python
confidence = populated_weight_sum / total_weight_sum
```

Suggested interpretation:

- `>= 0.80`: high
- `0.60-0.79`: moderate
- `< 0.60`: low

## Narrative Rules

### Strong

Use when:

- score high
- confidence at least moderate

Narrative direction:

- local demand appears durable
- broader market context supports exit flexibility
- location likely helps protect the hold thesis

### Mixed

Use when:

- score mid-range
- conflicting signals or missing county confirmation

Narrative direction:

- some local support exists
- location helps, but does not fully de-risk the decision

### Weak

Use when:

- score low
- or data sparse enough that support cannot be demonstrated

Narrative direction:

- buyer should rely more on purchase discipline than on local market rescue

## Recommended V1 Implementation Stance

1. Use Zillow Research for home-value trend inputs.
2. Use Census for population trend inputs.
3. Use FEMA for flood-risk inputs.
4. Treat school data carefully:
   - official source first if possible
   - otherwise clearly label any third-party school score as non-official
5. Keep liquidity and scarcity lightweight at first.

## What We Should Build Next

The next concrete implementation step should be:

1. add schema support for these location fields
2. add a pure scoring helper module with tests
3. keep source acquisition separate from scoring logic

That separation matters because the scoring helper should remain deterministic even as sources improve over time.

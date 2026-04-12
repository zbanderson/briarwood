# Micro-Location Architecture Audit

**Date:** 2026-04-12
**Scope:** All code that computes, implies, or references within-town location value adjustments

---

## 1. Where Location Value Is Currently Computed

### 1.1 modules/location_intelligence.py — `LocationIntelligenceModule.run()` (line 62)

The primary location scoring module. Produces a `LocationIntelligenceOutput` with:

| Output | Type | How Computed | Used Where |
|--------|------|-------------|------------|
| `location_score` | float (0-100) | Weighted avg of proximity (35%), scarcity (25%), lifestyle (20%), risk (20%) | value_drivers.py, decision_model |
| `scarcity_score` | float (0-100) | Weighted avg of proximity (40%), supply (35%), rarity (25%) | decision_model |
| `location_premium_pct` | float | `(peer_median_ppsf / town_median_ppsf) - 1.0` | value_drivers.py line 186 |
| `subject_relative_premium_pct` | float | `(subject_ppsf / peer_median_ppsf) - 1.0` | narrative only |
| `category_results` | list[LocationCategoryIntelligence] | Per-category (beach, downtown, park, train, ski) bucket benchmarks | narrative, display |

**How it works:**
1. Loads same-town comps with coordinates
2. For each landmark category (beach, downtown, park, train, ski):
   - Calculates subject distance to nearest landmark point (haversine)
   - Assigns subject to a distance bucket (e.g., 0-0.25mi for beach)
   - Calculates median PPSF for subject's bucket vs town median → `location_premium_pct`
3. Combines into overall `location_score` and `scarcity_score`

**Problems:**
- **Produces scores and percentages, not dollar adjustments.** The `location_premium_pct` is a relative PPSF ratio, not a valuation adjustment.
- **Categories are scored independently but combined into one number.** Beach proximity and flood risk are mixed into a single `location_score`. A property 1 block from the beach in a flood zone gets a blended score that obscures both signals.
- **No dollar output.** Downstream consumers (value_drivers) apply `location_premium_pct` as `base_value * pct`, which is a flat percentage, not an evidence-based adjustment per location factor.
- **Narrative-heavy, not structured.** Outputs 4 narrative bullets, not structured per-factor adjustments.

### 1.2 modules/comparable_sales.py — `_location_adjustment_range()` (line 298)

The only place in the codebase that produces a **dollar-valued** location adjustment:

```python
diff = comp_beach - subject_beach  # beach distance delta
adj_pct = max(-0.08, min(diff * 0.015, 0.08))  # ±8% cap
adjusted.append(float(comp.adjusted_price) * (1 + adj_pct))
```

- Only covers **beach proximity** — no downtown, train, flood, or block adjustments.
- Adjusts each comp's price by a percentage based on how much closer/farther it is from beach than the subject.
- Result feeds into `blended_value_range` at 20% weight (line 143).
- The 0.015 multiplier and ±8% cap are hardcoded with no local evidence.

**Problems:**
- Beach-only. No other location factor gets a comp-level price adjustment.
- The adjustment is on the comp's price, not directly on the subject's value. It shifts the comp-derived value range.
- Multiplier (1.5% per unit distance) is arbitrary. In shore markets, the price delta between "1 block to beach" and "6 blocks to beach" can be 25-40%.

### 1.3 comp_intelligence.py — `_location_adjustments()` (line 166)

Produces structured `LocationAdjustment` objects:

| Key | Amount | Status |
|-----|--------|--------|
| beach | Dollar value from `_location_adjustment_range` delta | Active — only when beach landmark data exists |
| downtown | None | Scaffold only — "not priced yet" |
| train | None | Scaffold only — "not priced yet" |
| flood | None | Scaffold only — "not priced yet" |
| block_quality | None | Scaffold only — "not priced yet" |

**The scaffolding is already there.** The `_location_adjustments()` function reserves structured slots for 5 location factors. Only beach is populated. The architecture is explicitly designed for a Micro-Location Engine to fill these slots.

### 1.4 modules/value_drivers.py — `_build_feature_drivers()` (line 184)

Applies location premium to base value for the waterfall chart:

```python
location_premium_pct = float(location_metrics["location_premium_pct"])  # from location_intelligence
location_raw = base_value * location_premium_pct
location_conf = 0.55 if coords else 0.35
```

**Problems:**
- **Flat percentage on base value.** A 5% location premium on a $500K base is $25K regardless of whether the premium comes from beach, downtown, train, or some combination.
- **No breakdown by factor.** Can't tell the user "beach adds $30K, flood subtracts $15K."
- **Falls back to narrative label matching** when location_intelligence metrics are missing: "beach premium" or "downtown premium" → hardcoded 2.5%.

### 1.5 modules/bull_base_bear.py — Flood Stress (line 148)

Applies flood-based stress drawdown in bear/stress scenarios:

```python
flood == "high" → stress_drawdown = 0.35 (35%)
flood == "medium" → stress_drawdown = 0.30 (30%)
else → stress_drawdown = default (25%)
```

This is a **scenario-level** adjustment, not a valuation adjustment. It affects the stress-case value, not the base or adjusted value. Not a double-counting risk with a micro-location engine.

### 1.6 agents/scarcity/location_scarcity.py — `LocationScarcityScorer.score()` (line 17)

Scores replicability of location advantages:

- Distance to anchor ≤0.20mi: +20, ≤0.50mi: +15, ≤1.0mi: +5, >2.0mi: -10
- Comparable count within radius: ≤10: +15, ≤20: +10, ≤35: +5, >50: -10

**Problems:**
- Produces a **scarcity score (0-100)**, not a dollar adjustment.
- Only considers one anchor at a time. No multi-factor analysis.
- Feeds into the decision model scoring, not into valuation.

### 1.7 agents/comparable_sales/agent.py — `_similarity_profile()` (line 364)

Location-related comp scoring adjustments:

```python
if distance_miles <= 0.5: score += 0.02   # "Very close"
elif distance_miles > 2.0: score -= 0.03  # "Farther from subject"
# Location tag overlap: +0.02 per shared tag, max +0.06
```

These adjust **comp selection weighting**, not property value. They're appropriate for what they do — closer comps and comps with matching location tags get slight scoring preference.

### 1.8 decision_model/scoring.py — Flood Risk Penalty (line varies)

- `flood_risk_high_penalty: 20.0` points (from scoring_config.py)
- `flood_risk_medium_penalty: 8.0` points
- Applied to decision model score (1-100 BUY/WATCH/PASS), not to dollar value.

---

## 2. Structured Location Data Available

### Subject Property (schemas.py: PropertyInput)

| Field | Type | Populated? | Notes |
|-------|------|-----------|-------|
| `latitude` | float \| None | Usually | From geocoding or user input |
| `longitude` | float \| None | Usually | From geocoding or user input |
| `flood_risk` | str \| None | Sometimes | "low", "medium", "high", "none" — town-level, not parcel |
| `zone_flags` | dict | Sometimes | `in_flood_zone`, `in_beach_premium_zone`, `in_downtown_zone` |
| `landmark_points` | dict[str, list[dict]] | Usually | Beach, downtown, train, park coordinates per town |
| `town` | str | Always | Town name |

### Comparable Sales (agents/comparable_sales/schemas.py)

| Field | Type | Notes |
|-------|------|-------|
| `latitude` / `longitude` | float \| None | Often available when geocoded |
| `location_tags` | list[str] | Categorical: "beach", "downtown" etc. |
| `micro_location_notes` | list[str] | Narrative: "Similar walkability profile" |
| `distance_to_subject_miles` | float \| None | Haversine distance to subject |

### Landmark Points (data/town_county/monmouth_landmark_points.json)

Town-level curated anchor points for: beach, downtown, train, park.
Each point has: label, latitude, longitude.
Coverage: Belmar, Bradley Beach, Avon-by-the-Sea, Spring Lake, etc.

### Flood Risk (data/town_county/flood_risk.json)

Town-level flood risk classification. NOT parcel-level FEMA zone data.

---

## 3. What's Missing

### M1: No per-factor dollar adjustments
Beach, downtown, train, flood, block quality all lack dollar-valued adjustments. Only beach gets a comp-level price shift (±8% cap), which is indirect and blended away.

### M2: No flood dollar impact on base value
Flood risk affects decision model scores and stress scenarios but never adjusts the base/adjusted value. In reality, flood zone properties trade at measurable discounts (5-15% in NJ coastal markets).

### M3: No downtown/train proximity valuation
Downtown walkability and train access are recognized in location scoring but never converted to dollar adjustments. In shore towns, downtown-walkable properties command measurable premiums.

### M4: No block-level context
No data or logic for same-street patterns, block quality, adjacent-property effects. The `block_quality` slot in comp_intelligence is empty.

### M5: Flood data is town-level, not parcel-level
`flood_risk` is a town classification ("Belmar: Moderate"). Two properties in Belmar — one in AE zone, one in X zone — get the same flood treatment. Parcel-level FEMA zone data would require external data integration.

### M6: Location premium and feature adjustments are independent
Location adjustments and feature adjustments don't reference each other. A beachfront property with a pool might get a pool premium that's already baked into the beach premium. No overlap detection.

---

## 4. Integration Points for a Micro-Location Engine

### 4.1 Natural home: comp_intelligence.py

The `_location_adjustments()` function (line 166) already scaffolds slots for beach, downtown, train, flood, block_quality. A Micro-Location Engine should fill these slots with evidence-based dollar adjustments.

### 4.2 Data available to the engine

The engine will have access to:
- Subject coordinates (lat/lon)
- Landmark points per category (beach, downtown, train, park)
- Comp set with coordinates, adjusted prices, location_tags
- Flood risk (town-level string)
- Zone flags (boolean dict)
- Town metrics (median lot, median price, etc.)

### 4.3 What the engine can realistically do today

| Factor | Evidence Available | Feasible Method |
|--------|-------------------|-----------------|
| Beach proximity | Subject + comp distances to beach landmarks, comp prices | Feature comparison: comps near vs far from beach |
| Downtown proximity | Subject + comp distances to downtown landmarks, comp prices | Feature comparison: comps near vs far from downtown |
| Train proximity | Subject + comp distances to train landmarks, comp prices | Feature comparison: comps near vs far from train |
| Flood risk | Town-level flood_risk string, zone_flags | Fallback rule: apply conservative discount for known flood exposure |
| Block quality | No structured data | Scaffold only — insufficient data |

### 4.4 Anti-overlap with Feature Adjustment Engine

The Micro-Location Engine produces **location-based** value adjustments. The Feature Adjustment Engine produces **physical feature** adjustments. These should be additive because they measure different things:
- Feature: "This house has a garage" → $18K
- Location: "This house is 2 blocks from the beach" → +$35K

The one overlap risk is: if beach-proximity comps systematically have features (e.g., pools are more common near the beach), the beach premium may partially capture pool value. This is a second-order effect that should be documented but not actively corrected — the evidence isn't granular enough.

---

## 5. Key Problems Summary

### P1: Location produces scores, not adjustments
The LocationIntelligenceModule produces `location_score` (0-100) and `location_premium_pct` (relative PPSF), but no structured dollar adjustments per factor.

### P2: Only beach has a comp-based adjustment
`_location_adjustment_range()` only handles beach proximity. Downtown, train, flood, and block quality have empty scaffold slots.

### P3: Flood never hits the base value
Flood risk affects decision scores and stress scenarios but never adjusts the comparable-sales-derived value. Properties in flood zones trade at real, measurable discounts.

### P4: Location factors are blended into one score
Beach, downtown, train, park, and flood are all mixed into a single `location_score`. A property with great beach access but high flood risk gets a middle-of-the-road score that hides both signals.

### P5: Adjustment coefficients are hardcoded
Beach adj: `diff * 0.015`, cap ±8%. These have no local market basis. Shore market beach premiums are well-documented but vary significantly by town and distance bucket.

### P6: No evidence hierarchy for location
Unlike the Feature Adjustment Engine, there's no fallback chain. If comp evidence is insufficient for a given factor, the factor gets zero adjustment with no fallback estimate.

### P7: Scaffolding exists but is unfilled
`comp_intelligence._location_adjustments()` already reserves structured slots. The architecture is ready for a Micro-Location Engine — the slots just need filling.

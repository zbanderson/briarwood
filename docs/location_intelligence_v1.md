# Location Intelligence v1

`briarwood/modules/location_intelligence.py` adds a benchmarked geo layer to the active Briarwood analysis engine.

## Expected inputs

Subject property:
- `latitude`
- `longitude`
- `purchase_price`
- `sqft`
- `town`
- optional `flood_risk`
- optional `zone_flags`
- optional `landmark_points`

Comp rows:
- `latitude`
- `longitude`
- `sale_price`
- `sqft`
- optional `days_on_market`
- `town`
- `state`

Landmark points are passed as a simple category map such as:

```json
{
  "beach": [{"latitude": 40.17, "longitude": -74.01}],
  "downtown": [{"latitude": 40.18, "longitude": -74.02}]
}
```

## How v1 scoring works

For each landmark category with enough data, the module:
1. measures subject and comp distance to the nearest point
2. assigns each record to a fixed distance bucket
3. calculates bucket medians and town-wide medians
4. forms:
   - `location_premium_pct`
   - `subject_relative_premium_pct`

Headline scores:
- `scarcity_score`
  - 40% proximity percentile
  - 35% constrained-supply proxy
  - 25% premium-zone rarity proxy
- `location_score`
  - 35% proximity benefit
  - 25% scarcity score
  - 20% lifestyle access
  - 20% risk adjustment

If inputs are missing, the module dynamically reweights only the components it can support.

## Confidence posture

Confidence rises when Briarwood has:
- subject coordinates
- landmark coverage across multiple categories
- geo-coded town comps
- enough peer comps in the subject bucket

Confidence falls sharply when:
- subject coordinates are missing
- landmark sets are missing
- geo peer depth is thin
- only proxy flood/zone logic is available

## Future v2 path

The v1 module is intentionally bucket-based and deterministic.

The clean v2 extension point is:
- replace or augment bucket medians with regression-based geo premiums
- add polygon joins for premium and hazard zones
- add parcel-aware scarcity features
- push validated location outputs into BCV and scenario weighting once geo inputs are sourced at higher confidence

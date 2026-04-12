# Town Transfer Engine — Architecture Audit

**Date:** 2026-04-12
**Scope:** All code that computes, implies, or references cross-town pricing, town-level metrics, or town-pair comparisons

---

## 1. Where Town-Level Pricing Data Currently Exists

### 1.1 town_aggregation_diagnostics.py — Town Baseline Metrics (line 207)

`build_town_baseline_metrics()` produces per-town aggregate statistics from the full comp dataset:

```python
def build_town_baseline_metrics(records: pd.DataFrame) -> pd.DataFrame:
    for town, group in records.groupby("town", dropna=False):
        sold = group[group["record_type"] == "sold"]
        active = group[group["record_type"] == "active"]
        grouped_rows.append({
            "town": town,
            "listing_count": int(len(active)),
            "sold_count": int(len(sold)),
            "median_list_price": _median(active["list_price"]),
            "median_sale_price": _median(sold["sale_price"]),
            "median_ppsf": _median(group["ppsf"]),
            "median_sqft": _median(group["sqft"]),
            "median_lot_size": _median(group["lot_size"]),
            ...
        })
```

| Output Field | Type | Notes |
|---|---|---|
| `median_sale_price` | float \| None | Sold comps only |
| `median_ppsf` | float \| None | All records (sold + active) |
| `median_sqft` | float \| None | All records |
| `median_lot_size` | float \| None | All records |
| `median_days_on_market` | float \| None | All records |
| `median_sale_to_list_ratio` | float \| None | Sold comps only |
| `avg_confidence_score` | float \| None | Data quality confidence |
| `missing_data_rate` | float \| None | Share of core fields missing |
| `outlier_count` | int | PPSF outliers (IQR-based) |

**Usable for town transfer:** Yes — provides the baseline per-town metrics needed to compute town-pair PPSF and price ratios.

### 1.2 town_aggregation_diagnostics.py — Town Premium Index (line 301)

`build_town_premium_index()` computes per-town index values relative to the region median:

```python
def build_town_premium_index(town_summary, records):
    region_price = _median(records.loc[records["record_type"] == "sold", "sale_price"])
    region_ppsf = _median(records["ppsf"])
    region_lot = _median(records["lot_size"])
    region_dom = _median(records["days_on_market"])
    rows.append({
        "town": row["town"],
        "town_price_index": _index_to_baseline(price_value, region_price),  # region = 100
        "town_ppsf_index": _index_to_baseline(row["median_ppsf"], region_ppsf),
        "town_lot_index": _index_to_baseline(row["median_lot_size"], region_lot),
        "town_liquidity_index": ...,  # inverse DOM + sale-to-list ratio
    })
```

| Output Field | Type | Notes |
|---|---|---|
| `town_price_index` | float \| None | Region median = 100 |
| `town_ppsf_index` | float \| None | Region median = 100 |
| `town_lot_index` | float \| None | Region median = 100 |
| `town_liquidity_index` | float \| None | Inverse DOM + sale-to-list |

**Usable for town transfer:** Yes — `town_ppsf_index` ratios can produce town-pair translation factors. If Belmar = 95 and Spring Lake = 140, the PPSF ratio is 95/140 = 0.679, meaning Belmar shell values are roughly 68% of Spring Lake's.

### 1.3 town_aggregation_diagnostics.py — Cross-Town Comparison Table (line 255)

`build_cross_town_comparison_table()` produces per-town metrics with region-relative ratios:

```python
def build_cross_town_comparison_table(town_summary, records):
    frame["ppsf_vs_region"] = frame["median_ppsf"].apply(
        lambda value: _ratio_to_baseline(value, region_ppsf)
    )
    frame["price_vs_region"] = frame.apply(
        lambda row: _ratio_to_baseline(..., region_sale_price ...),
        axis=1,
    )
    frame["sqft_vs_region"] = frame["median_sqft"].apply(
        lambda value: _ratio_to_baseline(value, region_sqft)
    )
```

| Output Field | Type | Notes |
|---|---|---|
| `ppsf_vs_region` | float \| None | Town PPSF / region PPSF |
| `price_vs_region` | float \| None | Town price / region price |
| `sqft_vs_region` | float \| None | Town sqft / region sqft |

**Usable for town transfer:** Yes — `ppsf_vs_region` ratios for two towns directly yield a town-pair translation factor.

### 1.4 town_aggregation_diagnostics.py — Town QA Flags (line 378)

`build_town_qa_flags()` flags data quality issues per town:

```python
rows.append({
    "town": town,
    "sample_size": sample_size,
    "sqft_coverage_rate": _coverage_rate(group["sqft"]),
    "low_sample_flag": sample_size < LOW_SAMPLE_THRESHOLD,  # < 8
    "high_missingness_flag": missing_data_rate > 0.35,
    "high_dispersion_flag": (ppsf_std / ppsf_median) > 0.35,
    "outlier_heavy_flag": outlier_share > 0.20,
    "low_confidence_flag": avg_confidence < 0.60,
})
```

**Usable for town transfer:** Critical — a donor town with `low_sample_flag=True` or `high_dispersion_flag=True` should not be used for transfers, or should get heavy confidence penalty.

### 1.5 town_aggregation_diagnostics.py — Town Calibration Table (line 423)

`build_town_calibration_table()` measures how well town-level medians predict individual property prices vs. the region median:

```python
working["region_price_residual"] = working["price"].apply(
    lambda value: _abs_ratio_delta(value, region_price)
)
working["town_price_residual"] = working.apply(
    lambda row: _abs_ratio_delta(row["price"], town_price_map.get(row["town"])),
    axis=1,
)
```

| Output Field | Type | Notes |
|---|---|---|
| `avg_abs_region_price_residual` | float \| None | Avg absolute price error using region median |
| `avg_abs_town_price_residual` | float \| None | Avg absolute price error using town median |
| `price_residual_improvement` | float \| None | How much better town-level prediction is than region-level |
| `calibration_note` | str | "strong", "moderate", "weak", "insufficient" |

**Usable for town transfer:** Yes — `price_residual_improvement` tells us whether a town's pricing is coherent enough to export. Towns with "weak" calibration are poor donors.

### 1.6 town_aggregation_diagnostics.py — TownContext (line 52)

`get_town_context()` (line 116) assembles all per-town diagnostics into a single `TownContext` dataclass. This is the most convenient interface for the Town Transfer Engine — it exposes median prices, indexes, QA flags, and confidence in one object.

```python
@dataclass(slots=True)
class TownContext:
    town: str
    median_sale_price: float | None
    median_ppsf: float | None
    town_price_index: float | None
    town_ppsf_index: float | None
    context_confidence: float
    low_sample_flag: bool
    high_dispersion_flag: bool
    ...
```

---

## 2. Where Cross-Town Logic Currently Exists

### 2.1 comp_intelligence.py — `_town_transfer_adjustments()` (line 200)

The only explicit cross-town function. Currently a scaffold:

```python
def _town_transfer_adjustments(ctx: _LayerContext) -> list[TownTransferAdjustment]:
    output = ctx.output
    support_type = "direct" if output.comp_count > 0 else "translated"
    return [
        TownTransferAdjustment(
            key="cross_town_shell_transfer",
            amount=None,
            from_town=None,
            to_town=ctx.property_input.town,
            method="scaffold_only",
            support_type=support_type,
            note="Current comp support is still same-town first. Cross-town transfer hooks are now reserved but not yet actively priced.",
        )
    ]
```

**Status:** Empty scaffold. The `TownTransferAdjustment` schema supports `from_town`, `to_town`, `method`, `support_type`, and `amount` — everything the engine needs to emit.

### 2.2 comp_intelligence.py — `_support_summary()` (line 218)

Tracks `same_town_count` in the support summary. Currently hardcoded:

```python
same_town_count = len(output.comps_used)  # line 233
```

**Problem:** When cross-town comps are introduced, `same_town_count` must compare each comp's town to the subject's town. The field exists but its computation will break.

### 2.3 base_comp_selector.py — `_count_same_town()` (line 356)

```python
def _count_same_town(selected, subject_town):
    # TODO: when cross-town comps are supported, compare comp.town to subject_town.
    return len(selected)
```

**Status:** Explicitly marked TODO for cross-town support. The `BaseCompSupportSummary.same_town_count` field (line 140) uses this function.

### 2.4 base_comp_selector.py — `_support_quality()` (line 269)

The activation trigger for the Town Transfer Engine:

```python
def _support_quality(selected, used_tier_names):
    if not selected:
        return "thin"
    scores = [float(item["score"]) for item in selected]
    med_score = median(scores)
    if len(selected) >= 4 and med_score >= 0.72 and not has_extended and (med_distance <= 1.5):
        return "strong"
    if len(selected) >= 3 and med_score >= 0.58:
        return "moderate"
    return "thin"
```

The engine should activate when support is "thin" — fewer than 3 comps at Tier 1+2 with adequate similarity scores.

### 2.5 agents/comparable_sales/agent.py — `FileBackedComparableSalesProvider.get_sales()` (line 66)

```python
def get_sales(self, *, town: str, state: str) -> list[ComparableSale]:
    town_key = normalize_town(town)
    state_key = normalize_state(state)
    return [
        row for row in self._rows
        if normalize_town(row.town) == town_key and normalize_state(row.state) == state_key
    ]
```

**Problem:** This provider ONLY returns same-town sales. The Town Transfer Engine does NOT need to change this — it should NOT try to load cross-town raw comps. Instead, it should use town-level aggregate metrics (PPSF indexes, price indexes) to apply a translation factor to the subject's thin local comp base. The engine borrows statistical evidence, not individual comps.

---

## 3. Town-Pair Relationship Data Available

### 3.1 Coastal Profiles — `data/town_county/monmouth_coastal_profiles.json`

Per-town coastal and scarcity signals:

```json
[
    {"name": "Spring Lake", "coastal_profile_signal": 0.97, "scarcity_signal": 0.94},
    {"name": "Avon by the Sea", "coastal_profile_signal": 0.91, "scarcity_signal": 0.88},
    {"name": "Belmar", "coastal_profile_signal": 0.84, "scarcity_signal": 0.78},
    {"name": "Bradley Beach", "coastal_profile_signal": 0.82, "scarcity_signal": 0.76},
    ...
]
```

**Usable for town transfer:** Yes — coastal profile similarity is a strong grouping signal for shore town pairs. Two towns with similar coastal profiles (within ±0.10) are more likely to have comparable pricing structures.

### 3.2 Price Trends — `data/town_county/price_trends.json`

ZHVI-style price trend data per town. Contains time series for median home values.

**Usable for town transfer:** Yes — towns with similar price trend trajectories are more likely to be valid transfer pairs. A town trending at +8% YoY is a poor donor for a town at -2%.

### 3.3 Flood Risk — `data/town_county/flood_risk.json`

Town-level flood risk classification.

**Usable for town transfer:** Yes — flood risk compatibility is a transfer eligibility filter. A high-flood-risk town should not transfer to a low-flood-risk town without adjustment.

### 3.4 Liquidity — `data/town_county/liquidity.json`

Inventory counts, monthly sales volume, months of supply per town.

**Usable for town transfer:** Yes — liquidity similarity signals whether two markets operate similarly. A liquid market (2 months supply) transferring to an illiquid one (12 months) needs heavy discounting.

### 3.5 School Signal — `data/town_county/monmouth_school_signal.json`

School quality ratings per town.

**Usable for town transfer:** Partial — school quality affects price levels but is already captured in the PPSF index. Useful as a similarity filter but not as a separate adjustment.

### 3.6 Landmark Points — `data/town_county/monmouth_landmark_points.json`

Beach, downtown, train, park coordinates per town.

**Usable for town transfer:** Partial — towns sharing the same landmark categories (both beach towns, both train towns) are better transfer pairs. Not directly used for pricing translation.

---

## 4. Town County Scoring — `agents/town_county/scoring.py`

### 4.1 TownCountyScorer (line 7)

Produces town-level investment scores but NOT pricing metrics:

```python
town_demand_score = clamp_score(
    (35 * normalized_town_price)
    + (20 * normalized_town_population)
    + (20 * normalized_school)
    + (10 * normalized_coastal)
    + (10 * normalized_scarcity)
    + (5 * normalized_liquidity)
    - flood_penalty
)
```

| Output | Type | Relevance |
|---|---|---|
| `town_demand_score` | float (0-100) | Demand signal, not pricing |
| `county_support_score` | float (0-100) | Macro backdrop |
| `location_thesis_label` | str | strong/supportive/mixed/weak |
| `appreciation_support_view` | str | Growth outlook |

**Usable for town transfer:** Partially — `location_thesis_label` can be a similarity filter (prefer donors with same or adjacent label), but these scores are investment-oriented, not pricing-oriented.

---

## 5. What's Missing

### M1: No Town-Pair Similarity Scores
No function computes a similarity score between two specific towns. The cross-town comparison table shows each town vs. the region, but never town-A vs. town-B. The Town Transfer Engine needs to compute pairwise similarity from the available per-town metrics.

### M2: No Geographic Adjacency Map
No curated list of which towns are adjacent or nearby. Shore town geography is well-known (Belmar borders Avon, Spring Lake Heights, Lake Como), but this isn't encoded. The engine should use a curated adjacency list or geographic distance as a proxy.

### M3: No Segment-Aware Translation
Town-level PPSF indexes are computed across all property types and sizes. A translation factor that works for 3BR/1500sqft bungalows may not work for 5BR/3000sqft colonials. The engine should ideally compare segment-matched medians, but the current infrastructure only provides whole-town aggregates.

### M4: No Cross-Town Comp Loading
`FileBackedComparableSalesProvider.get_sales()` only loads same-town data. The Town Transfer Engine should NOT load cross-town individual comps — it should translate using aggregate statistics instead.

### M5: No Translation Confidence Framework
No mechanism exists to penalize confidence when evidence is borrowed vs. directly observed. The engine needs a clear confidence penalty for translated values.

### M6: `same_town_count` Will Break
Both `base_comp_selector.py:356` and `comp_intelligence.py:233` hardcode `same_town_count = len(selected/comps_used)`. When the engine produces cross-town adjustments, downstream consumers need to know how much of the evidence is local vs. borrowed.

---

## 6. Integration Points for the Town Transfer Engine

### 6.1 Natural Home: `comp_intelligence.py`

The `_town_transfer_adjustments()` function (line 200) already scaffolds a `TownTransferAdjustment` with `from_town`, `to_town`, `method`, and `support_type`. The engine fills this scaffold.

### 6.2 Activation Trigger: Support Quality

The engine activates when `BaseCompSupportSummary.support_quality == "thin"` — meaning fewer than 3 comps with median similarity score ≥ 0.58. This is already computed by `base_comp_selector.py:269`.

### 6.3 Data Pipeline

The engine needs:
1. **Subject town metrics** — via `get_town_context(subject_town)` from `town_aggregation_diagnostics.py:116`
2. **Donor town candidates** — all `TownContext` objects from the dataset, filtered by eligibility
3. **Coastal profiles** — from `monmouth_coastal_profiles.json`
4. **QA flags** — from `TownContext.low_sample_flag`, `high_dispersion_flag`, etc.

### 6.4 Output Shape

The engine should return a result object (dataclass) with:
- `used: bool` — whether transfer was activated
- `reason: str` — why activated or why not
- `donor_town: str | None` — the town borrowed from
- `translation_factor: float | None` — the PPSF ratio applied
- `translated_value: float | None` — the adjusted value
- `confidence_penalty: float` — how much confidence was reduced
- `similarity_score: float | None` — town-pair similarity
- `method: str` — how the translation was computed
- `warnings: list[str]` — caveats

### 6.5 Anti-Overlap

The Town Transfer Engine produces a **shell value translation**, not a feature or location adjustment. It answers: "If the subject had adequate local comps, what would the base shell value be?" This is independent of:
- **Feature adjustments** — physical features are property-specific, not town-specific
- **Location adjustments** — micro-location (beach, downtown) is within-town positioning
- **The existing comp-derived value** — the engine augments the thin local base, not replaces it

---

## 7. Key Problems Summary

### P1: Cross-town support is scaffolded but empty
`comp_intelligence._town_transfer_adjustments()` returns a scaffold with `amount=None` and `method="scaffold_only"`. The schema is ready but no logic fills it.

### P2: Comp provider is locked to same-town
`FileBackedComparableSalesProvider.get_sales()` hard-filters on town name. The Town Transfer Engine should NOT change this — it should use aggregate metrics, not cross-town raw comps.

### P3: Town aggregation diagnostics are the evidence base
`build_town_premium_index()` and `build_cross_town_comparison_table()` produce the per-town indexes needed for translation factors, but they've never been used for this purpose.

### P4: No pairwise similarity computation
The infrastructure computes each town vs. the region, not town-A vs. town-B. The engine must derive pairwise similarity from per-town metrics.

### P5: Town-level aggregates ignore segments
PPSF indexes are whole-town. A 3BR/1200sqft translation factor may differ from a 5BR/3000sqft one. The `build_feature_sensitivity_by_town()` function (line 341) provides per-feature breakdowns that could partially address this, but segment-aware transfer is not straightforward.

### P6: Activation logic is clear
Support quality "thin" is the right trigger. It's already computed and available on `BaseCompSupportSummary.support_quality`.

### P7: Confidence penalty is undefined
No framework for how much to reduce confidence when using borrowed evidence. Should be substantial — translated evidence is weaker than direct comp evidence.

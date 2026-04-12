# Comp Selector Architecture Audit

**Date:** 2026-04-11
**Scope:** Full trace of comparable sale selection from raw data to valuation output

---

## 1. Full Call Chain: Raw Comp Data → Valuation Output

```
PropertyInput
    │
    ▼
ComparableSalesModule.run()                    [modules/comparable_sales.py:52]
    │
    ├── MarketValueHistoryModule.run()          (gets time-adjustment series)
    ├── _detect_hybrid_valuation()              (multi-unit decomposition)
    │
    ▼
ComparableSalesAgent.run()                     [agents/comparable_sales/agent.py:84]
    │
    ├── FileBackedComparableSalesProvider       [agents/comparable_sales/agent.py:29]
    │   └── get_sales(town, state)             [agent.py:66] — filters by normalized town + state
    │       └── DataQualityPipeline.run()       (stamps quality_status, comp_eligibility_gate)
    │
    ├── Dedup by normalized address             [agent.py:109-115]
    │
    ├── Per-comp gate: _passes_gate()           [agent.py:308-362]
    │   └── Rejects on: quality_status, eligibility_gate, address_verification,
    │       sale_verification, property_type, beds(±2), baths(±1.5),
    │       sqft(±35%), lot(±100%), sale_age(>1460d), price_ratio,
    │       distance(>5mi)
    │
    ├── Per-comp scoring: _similarity_profile() [agent.py:364-503]
    │   └── Rejects if similarity_score < 0.30
    │
    ├── Time adjustment: _time_adjust_price()   [agent.py:586-603]
    ├── Subject adjustment: _subject_adjustment_pct() [agent.py:522-584]
    │
    ▼
build_base_comp_selection()                    [base_comp_selector.py:14]
    │
    ├── _evaluate_comp() per comp               [base_comp_selector.py:81]
    │   ├── Weighted similarity score (0-1)
    │   └── _selection_tier() → tight_local / loose_local / broad_local / rejected
    │
    ├── Tier-based selection:
    │   ├── If ≥3 tier_1 → use only tier_1
    │   ├── If tier_1 + tier_2 ≥ 3 → use tier_1 + tier_2
    │   └── Else → use all tiers
    │
    ├── Sort by (tier_rank, -score, distance, sale_age)
    ├── Cap at 5 comps                          [base_comp_selector.py:33]
    ├── _weighted_value() → base_shell_value    [base_comp_selector.py:207]
    └── _support_quality() → strong/moderate/thin [base_comp_selector.py:178]
    │
    ▼
_enrich_comp_intelligence()                    [modules/comparable_sales.py:118]
    │
    ├── _score_comp() → proximity, recency, similarity, data_quality → weighted_score
    ├── _segmentation_bucket() → direct_comps / income_comps
    ├── _bucket_range() → direct_value_range, income_adjusted_value_range
    ├── _location_adjustment_range() → beach proximity adjustments
    ├── _lot_adjustment_range() → lot size adjustments
    ├── _blend_ranges() → blended_value_range (45% direct, 20% income, 20% location, 15% lot)
    └── build_comp_analysis()                  [comp_intelligence.py:22]
        ├── base_shell_value
        ├── feature_adjustments (ADU, garage, lot, condition, basement, pool, parking)
        ├── location_adjustments (beach, downtown, train, flood, block_quality)
        └── town_transfer_adjustments (cross_town — scaffold only)
```

---

## 2. How Comps Are Loaded

**Source:** `FileBackedComparableSalesProvider` reads from `data/comps/sales_comps.json`

- **File:** [agent.py:29-75](briarwood/agents/comparable_sales/agent.py#L29-L75)
- Town/state filter via normalized string matching (`normalize_town`, `normalize_state`)
- On load, each row gets stamped with `quality_status`, `quality_issues`, and `source_provenance` via `DataQualityPipeline`
- `classify_comp_eligibility()` sets `comp_eligibility_gate` (eligible / eligible_with_warnings / market_only / rejected)

**No radius or distance filtering at load time.** The provider returns ALL sales for the requested town/state pair.

---

## 3. How Comps Are Filtered (Gate Logic)

**File:** [agent.py:308-362](briarwood/agents/comparable_sales/agent.py#L308-L362)  
**Function:** `_passes_gate()`

| Filter                    | Threshold                   | Notes                                  |
|---------------------------|-----------------------------|----------------------------------------|
| quality_status            | "rejected" → reject         | Data quality pipeline flag             |
| quality_status            | "needs_review" → reject     | Forces manual review first             |
| eligibility_gate          | "rejected" / "market_only"  | Provenance-based eligibility           |
| address_verification      | "questioned"/"unverified"   | Address integrity gate                 |
| sale_verification          | "questioned" → reject       | Sale record integrity gate             |
| property_type             | Family mismatch → reject    | **Hard gate — good**                   |
| beds                      | ±2                          | Hard cutoff                            |
| baths                     | ±1.5                        | Hard cutoff                            |
| sqft                      | ±35%                        | Hard cutoff                            |
| lot_size                  | ±100%                       | Hard cutoff                            |
| sale_age                  | >1460 days (4 years)        | Very loose                             |
| price_ratio               | <0.35× or >2.50×           | Requires market_value_today            |
| distance                  | >5.0 miles                  | Only when lat/lon available            |

### Observations:
- Sale age cutoff of **4 years** is far too loose for a "base shell" selector
- Distance gate of **5 miles** is the only radius control, and only fires when geocoded
- No recency-based tiering at the gate level — a 4-year-old sale passes the same as a 3-month-old sale
- Bed/bath gates are reasonable but not tier-aware

---

## 4. How Comps Are Scored

### Stage 1: Agent-level similarity (`_similarity_profile`)

**File:** [agent.py:364-503](briarwood/agents/comparable_sales/agent.py#L364-L503)

Starts at 1.0 and subtracts penalties:
- Architectural style mismatch: -0.03
- Bed count: -0.10 per bed, max -0.25
- Bath count: -0.08 per bath, max -0.18
- Sqft gap: -0.45 per ratio, max -0.28
- Lot gap: -0.15 per ratio, max -0.10
- Distance: +0.02 if ≤0.5mi, -0.03 if >2mi
- Year built: -(gap/40)*0.08, max -0.10
- Stories: -0.04 per story, max -0.06
- Garage: -0.02 per space, max -0.04
- Location tags: +0.02 per overlap, max +0.06
- Condition match: ±0.02
- Capex lane match: ±0.015
- Recency: -0.05 if 1-2yr, -0.12 if >2yr

**Minimum threshold:** 0.30 (anything below is rejected)

### Stage 2: Base Comp Selector scoring (`_evaluate_comp`)

**File:** [base_comp_selector.py:81-150](briarwood/base_comp_selector.py#L81-L150)

Weighted score (0-1):
```
0.20 × property_type (1.0 match / 0.15 mismatch)
0.16 × distance_score
0.15 × sqft_score
0.10 × lot_score
0.10 × beds_score
0.08 × baths_score
0.08 × age_score
0.07 × condition_score
0.03 × structure_score
0.03 × recency_score
```

### Observations:
- **Recency is severely underweighted at 3%.** A 3-month-old sale and a 2-year-old sale score almost identically. For a "what does a similar house trade for" question, recency should be a top-3 factor.
- **Distance is weighted at 16%** — reasonable but the underlying distance_score function is coarse (only 5 buckets).
- **Two separate scoring systems** exist (agent-level and base selector level) with different methodologies and weights. This creates confusion about which score drives selection.
- **Property type gets 20% weight but allows "unknown" types through** with a full match score. If both types are unknown, `_property_type_match` returns True.

---

## 5. How Comps Are Tiered

**File:** [base_comp_selector.py:153-175](briarwood/base_comp_selector.py#L153-L175)

| Criterion     | tight_local          | loose_local          | broad_local (default) |
|---------------|----------------------|----------------------|-----------------------|
| Property type | Must match           | Must match           | Not checked (!)       |
| Distance      | ≤1.5 mi              | ≤3.0 mi              | Any                   |
| Beds          | ±1                   | ±1                   | Any                   |
| Baths         | ±0.5                 | ±1.0                 | Any                   |
| Sqft          | ±15%                 | ±25%                 | Any                   |
| Lot           | ±35%                 | ±60%                 | Any                   |
| Year built    | ±20 years            | ±35 years            | Any                   |
| Min score     | 0.45                 | 0.45                 | 0.45                  |

### Critical Problems:
1. **`broad_local` has NO property type check.** Only `score < 0.45` or `!property_type_match` triggers "rejected". But the property type mismatch only sets `score < 0.45` when the weight math works out that way — it's not a hard gate at this tier.
2. **No recency criteria in tiering at all.** A comp sold 3 years ago can be `tight_local`.
3. **No same-town requirement in tiering.** The tier labels say "local" but there's no town check — that happens upstream at the provider level (only loads same-town), so cross-town comps literally can't reach this code path today. But the tier names are misleading.
4. **The `rejected` tier catches property type mismatches, but the agent-level gate already rejects those.** So the rejected tier in the base selector is effectively dead code — it can only trigger on the score < 0.45 path.

---

## 6. How Comps Are Weighted in Valuation

### Base shell value (`_weighted_value`)
**File:** [base_comp_selector.py:207-219](briarwood/base_comp_selector.py#L207-L219)

```python
weight = max(score * tier_bonus * max(comp_confidence_weight, 0.35), 0.05)
# tier_bonus: tight_local=1.0, loose_local=0.88, broad_local=0.72
```

### Agent-level weighted value (`_weighted_value` / `_effective_weight`)
**File:** [agent.py:627-629, 834-840](briarwood/agents/comparable_sales/agent.py#L627-L629)

```python
weight = similarity_score * comp_confidence_weight * curation_weight * sale_verification_weight
```

### Observations:
- **Two competing weighted value calculations.** `base_comp_selection.base_shell_value` takes precedence (line 206), falling back to the agent's `_weighted_value`.
- **No floor on comp quality in weighting.** A very weak comp (score 0.50, broad_local) still gets at least `0.05` weight. With only 3 comps, a single garbage comp at minimum weight can still shift the base shell value.
- **`comp_confidence_weight` is floored at 0.35** in the base selector's weighting, meaning even poorly verified comps carry substantial weight.

---

## 7. Comp Count and Cap

- **Cap:** 5 comps maximum (`selected[:5]` at [base_comp_selector.py:33](briarwood/base_comp_selector.py#L33))
- **Minimum sought:** 3 (triggers tier expansion if fewer)
- **No minimum enforced:** If fewer than 3 comps survive all tiers, the system proceeds with whatever is available
- `support_quality` is set to "thin" when fewer than 3 comps with median score < 0.62

---

## 8. Explainability

### What exists:
- `match_reasons` and `mismatch_flags` per comp (up to 4 each)
- `selection_tier` label
- `support_quality` label (strong/moderate/thin)
- `support_notes` (narrative explanation)
- `why_comp` and `cautions` from agent-level scoring

### What's missing:
- **No per-dimension score breakdown exposed.** The similarity score is a black box to consumers. You can't see "this comp lost 0.15 on sqft and 0.08 on recency."
- **No tier assignment explanation.** A comp is "tight_local" but you can't see which criterion almost disqualified it.
- **No "why was this comp NOT selected" trace.** Rejected comps vanish silently.

---

## 9. Cross-Module Comp Usage

All modules share the **same comp set** produced by `ComparableSalesAgent.run()`:
- `build_base_comp_selection()` selects the top 5 for the base shell
- `_enrich_comp_intelligence()` operates on the full retained set (not just the 5 selected)
- `build_comp_analysis()` in `comp_intelligence.py` operates on the enriched output
- The `decision_engine.py`, `risk_bar.py`, and `recommendations.py` consume the final `ComparableSalesOutput`

No module has its own independent comp selection. Everything flows from one provider → one agent → one selector.

---

## 10. Key Problems Summary

### P1: Recency is negligible in selection
Recency gets 3% weight in the base selector score, and zero consideration in tier assignment. A comp sold 3 years ago can be ranked higher than one sold 3 months ago if it's slightly closer or slightly better on sqft.

### P2: Two scoring systems create confusion
The agent has its own `_similarity_profile` (start at 1.0, subtract penalties) and the base selector has `_evaluate_comp` (weighted sum of sub-scores). They use different weights, different scales, and can disagree on comp quality.

### P3: Tier thresholds don't match the design spec
- Tier 1 allows 1.5mi radius (spec says 0.5mi)
- Tier 1 allows ±15% sqft (spec says ±20%)
- No recency cutoffs in tiers (spec says 6mo / 12mo / 18mo)
- No same-town enforcement in tier logic (relies on upstream provider)
- `broad_local` has no property type check

### P4: No comp quality communication
When comp support is thin, the system proceeds with a "thin" label but doesn't clearly communicate the reliability impact to downstream modules or the user.

### P5: Hardcoded parameters
All thresholds (distances, sqft ratios, score weights, tier cutoffs) are hardcoded constants scattered across two files. No configuration or parameterization.

### P6: `same_town_count` is always `len(selected)`
In [base_comp_selector.py:58](briarwood/base_comp_selector.py#L58), `same_town_count` is hardcoded to `len(selected)` rather than actually checking town membership. This is correct today (provider only loads same-town), but will be wrong if cross-town expansion is ever implemented.

### P7: Sale age gate is too loose
The gate allows sales up to 1460 days (4 years) old. For a base shell value, anything beyond 18 months should be treated as extended support at best.

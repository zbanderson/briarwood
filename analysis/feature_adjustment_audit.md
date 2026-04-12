# Feature Adjustment Architecture Audit

**Date:** 2026-04-11
**Scope:** All code that computes, implies, or references feature-level property value adjustments

---

## 1. Where Feature Value Is Currently Computed

### 1.1 comp_intelligence.py — `_feature_adjustments()` (line 51)

This is the primary structured feature adjustment output today. Produces `FeatureAdjustment` objects for:

| Feature | Method | How Value Is Computed | Confidence |
|---------|--------|----------------------|------------|
| ADU | `income_capitalized_attachment` | Uses `additional_unit_income_value` from hybrid valuation | direct |
| Garage | `paired_difference_proxy` | `_median_feature_adjustment()` — comp-vs-subject garage difference × 0.8%/space, cap 2% | direct |
| Lot | `retained_comp_lot_range` | Delta between `lot_adjustment_range` and `direct_value_range` midpoints | direct |
| Condition | `retained_comp_condition_proxy` | Condition rank delta × 4% × base shell value, cap ±15% | direct |
| Basement | `feature_flag_only` | **No dollar value** — just flags presence | observed |
| Pool | `feature_flag_only` | **No dollar value** — just flags presence | observed |
| Parking | `feature_flag_only` | **No dollar value** — just flags presence | observed |
| Expansion | `flagged_for_next_layer` | **No dollar value** — just flags lot_size existence | observed |

**Problems:**
- Basement, pool, parking, expansion → **zero valuation**. Just feature flags with no dollar adjustment.
- Garage adjustment uses a crude 0.8%/space proxy, not actual paired-sale evidence.
- ADU value comes entirely from the hybrid valuation module — comp_intelligence just relays it.
- No confidence rating per feature. All "direct" features labeled identically regardless of evidence quality.

### 1.2 modules/hybrid_value.py — `_optionality_premium()` (line 454)

Computes an "optionality premium" as a percentage of (primary_house_value + rear_income_value):

```python
signals: list[tuple[str, float]] = []
if property_input.adu_type:
    signals.append((f"{adu_type} utility", 0.02))
if property_input.has_back_house:
    signals.append(("detached rear structure utility", 0.015))
if "beach" in description:
    signals.append(("near-beach cottage appeal", 0.015))
if "multigenerational" in description:
    signals.append(("multigenerational flexibility", 0.0125))
if "conversion" in description:
    signals.append(("future conversion optionality", 0.01))
premium_pct = min(sum(weights), 0.06)  # capped at 6%
```

**Problems:**
- **Listing-description keyword matching** drives valuation — "beach" in description adds 1.5%.
- **No comp evidence** — pure percentage assumptions.
- **Confidence is fabricated**: `min(0.72, 0.46 + 0.08 * len(signals))` — more keyword hits = higher confidence, regardless of evidence.
- **Double-counting risk with ADU income**: The hybrid module already capitalizes ADU income, then adds an optionality premium on top for the same ADU.

### 1.3 modules/comparable_sales.py — `_lot_adjustment_range()` (line 329)

Adjusts comp prices by lot size ratio: `adj_pct = max(-0.10, min((ratio - 1.0) * 0.12, 0.12))`. Applied to each comp's adjusted_price.

- Lot ratio is subject/comp, so larger subject lots get positive adjustment.
- Cap of ±12%.
- This is a **comp-level adjustment**, not a feature premium. It adjusts the comp set's value range, not the subject's value directly.

### 1.4 modules/comparable_sales.py — `_median_feature_adjustment()` (line 239)

Generic paired-difference proxy for numeric features (used for garage):
```python
pct = max(-cap, min((subject_value - comp_value) * pct_per_unit, cap))
```
- Garage: 0.8% per space difference, cap 2%.
- **Not true paired-sale analysis** — just multiplies the delta by a hardcoded percentage.

### 1.5 modules/value_drivers.py — `_build_feature_drivers()` (line 149)

Computes "value driver" impacts for the waterfall chart. Feature-related:
- **Income**: If ADU/back_house present and no income_supported_value, adds `base_value * 0.02` (2% flat premium).
- **Optionality**: ADU → +1.5%, oversized lot → +1.5%. Purely hardcoded percentages.
- **Condition**: renovated/updated → +1%, dated/needs_work → -2.5%.

**Problems:**
- Flat percentages applied to base value with no market evidence.
- ADU gets both an income bump (2%) and an optionality bump (1.5%) — potential double-count.
- "Oversized lot" is compared to `town_median_lot` from town metrics, but the premium is still a flat 1.5%.

### 1.6 modules/bull_base_bear.py — Optionality in Scenario Values (line 126)

```python
bull_optionality_pct = (scarcity_score / 100.0) * bbb_max_optionality_premium  # max 8%
base_optionality_pct = bull_optionality_pct * 0.25  # 25% of bull
bear_optionality_pct = 0.0
```

- Uses **scarcity_score** (from land/location scarcity module) as proxy for optionality.
- Not feature-specific at all — a property with high scarcity and no features gets the same premium.

### 1.7 decision_model/scoring.py — `_score_adu_expansion()` (line 836)

Scores ADU/expansion potential for the decision model (1-5 scale, not dollars):
- Existing ADU: +2 signals
- Basement: +1 signal
- Garage: +1 signal
- Lot with ≥3000sf remaining: +2 signals
- Lot with ≥1500sf remaining: +1 signal

This feeds into the **optionality category score** (20% weight in decision model), which influences the BUY/WATCH/PASS recommendation but does NOT produce a dollar value.

### 1.8 agents/comparable_sales/agent.py — `_subject_adjustment_pct()` (line 522)

Adjusts each comp for subject differences:
- Garage: 0.8% per space, cap ±1.5%
- Living area (sqft): log-based, cap ±15%
- Beds: 1% per bed, cap ±2.5%
- Baths: 0.8% per bath, cap ±2.5%
- Lot: 18% of lot_delta, cap ±4%
- Year built: 1%/40 years, cap ±2%
- Stories: 1%/story, cap ±2%
- Condition: 4%/rank, cap ±15%

These are **comp-level price adjustments** — they adjust each comp's sale price to account for differences from the subject. Not feature premiums on the subject's value.

---

## 2. Structured Feature Data in Property Schemas

### PropertyInput (schemas.py:202)

| Field | Type | Purpose | Populated? |
|-------|------|---------|------------|
| `garage_spaces` | `int \| None` | Number of garage bays | Frequently null |
| `garage_type` | `str \| None` | attached/detached/etc | Rarely populated |
| `has_detached_garage` | `bool \| None` | Detached garage flag | Rarely populated |
| `has_back_house` | `bool \| None` | ADU/cottage presence | Sometimes |
| `adu_type` | `str \| None` | Type of ADU | Rarely populated |
| `adu_sqft` | `int \| None` | ADU square footage | Rarely populated |
| `additional_units` | `list[dict]` | Multi-unit detail | Rarely populated |
| `has_basement` | `bool \| None` | Basement presence | Sometimes |
| `basement_finished` | `bool \| None` | Finished vs unfinished | Rarely populated |
| `has_pool` | `bool \| None` | Pool presence | Sometimes |
| `parking_spaces` | `int \| None` | Non-garage parking | Rarely populated |
| `corner_lot` | `bool \| None` | Corner lot flag | Sometimes |
| `driveway_off_street` | `bool \| None` | Off-street parking | Rarely populated |
| `lot_size` | `float \| None` | Lot in acres | Usually populated |
| `stories` | `float \| None` | Number of stories | Usually populated |
| `zone_flags` | `dict` | Zoning flags | Rarely populated |

### ComparableSale (agents/comparable_sales/schemas.py:104)

| Field | Type | Purpose |
|-------|------|---------|
| `garage_spaces` | `int \| None` | Number of garage bays |
| `lot_size` | `float \| None` | Lot in acres |
| `year_built` | `int \| None` | Year built |
| `stories` | `float \| None` | Number of stories |

**Missing from comp data:** `has_basement`, `has_pool`, `basement_finished`, `parking_spaces`, `has_detached_garage`, `adu_type`. This means **paired-sale analysis for basement, pool, and parking is not possible with current comp schema.**

---

## 3. Double-Counting Risk Map

| Feature | Where Valued | Risk |
|---------|-------------|------|
| ADU | hybrid_value (income cap) + comp_intelligence (ADU flag) + value_drivers (2% + 1.5%) + bull_base_bear (optionality %) + hybrid_value (optionality premium 2-6%) | **HIGH** — valued in at least 3 places |
| Garage | agent (comp adjustment) + comp_intelligence (0.8%/space) | **LOW** — different mechanisms, not stacking |
| Lot premium | comparable_sales (lot_adjustment_range) + value_drivers (1.5%) | **MODERATE** — lot adjustment and value driver overlap |
| Basement | comp_intelligence (flag only) + scoring (signal for optionality) | **LOW** — no dollar value computed |
| Pool | comp_intelligence (flag only) | **NONE** — no dollar value |
| Expansion | comp_intelligence (flag only) + value_drivers (lot optionality) | **LOW** — only if lot also oversized |

---

## 4. Key Problems Summary

### P1: Most features have ZERO dollar valuation
Basement, pool, parking, expansion potential → only flagged, never valued. These are real value drivers that get no quantification.

### P2: ADU is over-counted
ADU income value appears in: hybrid_value income capitalization, hybrid_value optionality premium, value_drivers income premium, value_drivers optionality premium, bull_base_bear optionality. At least 3 of these are additive.

### P3: Feature premiums are hardcoded percentages
Garage: 0.8%/space. ADU optionality: 2%. Lot: 1.5%. These have no local market basis and are applied identically regardless of market.

### P4: No evidence hierarchy
Every feature uses the same approach (hardcoded percentage or flag). No distinction between evidence-based adjustments and pure assumptions.

### P5: No confidence communication
All feature adjustments are tagged "direct" or "observed" with no real confidence rating based on evidence quality.

### P6: Comp data lacks feature fields
ComparableSale has no basement, pool, or parking fields. Paired-sale analysis for these features is impossible with current data.

### P7: Feature adjustments are scattered
Feature value is computed in at least 6 different files (comp_intelligence, hybrid_value, value_drivers, bull_base_bear, scoring, comparable_sales agent). No single source of truth.

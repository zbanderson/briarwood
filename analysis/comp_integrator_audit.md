# Comp Analysis Integrator — Phase 1 Audit

Comprehensive audit of the current comp analysis integration layer: what each
sub-engine produces, where duplication and conflicts exist, how outputs are
consumed, and where double-counting risks live.

---

## 1. Sub-Engine Output Structures

### 1.1 Base Comp Selector (`briarwood/base_comp_selector.py`)

**Entry:** `build_base_comp_selection(request, adjusted_comps) -> tuple[list[AdjustedComparable], BaseCompSelection]`

**Called from:** `briarwood/agents/comparable_sales/agent.py` (NOT from comp_intelligence.py)

**Output — `BaseCompSelection`:**
```
selected_comps: list[BaseCompSelectionItem]   # id, address, sale_price, distance, similarity, match_reasons, mismatch_flags, tier
base_shell_value: float | None                # weighted average of selected comps
support_summary: BaseCompSupportSummary       # comp_count, same_town_count, median_distance, support_quality, notes
```

**Key signals:**
- `support_quality` ("strong"/"moderate"/"thin") — gates Town Transfer Engine activation
- `base_shell_value` — the anchor for all downstream adjustments
- Per-comp `similarity_score` and `selection_tier` — used for weighting

---

### 1.2 Feature Adjustment Engine (`briarwood/feature_adjustment_engine.py`)

**Entry:** `evaluate_feature_adjustments(property_input, comp_output, base_comp_selection, town_metrics) -> FeatureAdjustmentResult`

**Output — `FeatureAdjustmentResult`:**
```
features: dict[str, FeatureResult]            # per-feature: present, adjustment, confidence, method, evidence, notes, overlap_check
total_feature_adjustment: float               # sum of all feature adjustments
weighted_confidence: str                      # "high"/"moderate"/"low"/"n/a"
confidence_breakdown: ConfidenceBreakdown     # dollar amounts by tier (high/moderate/low) + unvalued_features
overlap_warnings: list[str]                   # warnings about potential double-counting
adjusted_value: AdjustedValue                 # base_shell + features = feature_adjusted_value
```

**Features evaluated (9):** adu, garage, basement, pool, lot_premium, expansion, extra_parking, legal_multi_unit, special_utility

**Evidence hierarchy:** paired_sales → feature_comparison → income_proxy → fallback_rule → insufficient_data

---

### 1.3 Micro-Location Engine (`briarwood/micro_location_engine.py`)

**Entry:** `evaluate_micro_location(property_input, comp_output, base_comp_selection, town_metrics, location_intelligence) -> MicroLocationResult`

**Output — `MicroLocationResult`:**
```
factors: dict[str, LocationResult]            # per-factor: applicable, adjustment, confidence, method, evidence, notes, overlap_check
total_location_adjustment: float              # sum of all location adjustments
weighted_confidence: str                      # "high"/"moderate"/"low"/"n/a"
confidence_breakdown: LocationConfidenceBreakdown  # dollar amounts by tier + unvalued_factors
overlap_warnings: list[str]                   # warnings about potential double-counting
adjusted_value: LocationAdjustedValue         # base_shell + location = location_adjusted_value
```

**Factors evaluated (5):** beach, downtown, train, flood, block_quality

---

### 1.4 Town Transfer Engine (`briarwood/town_transfer_engine.py`)

**Entry:** `evaluate_town_transfer(property_input, comp_output, base_comp_selection, town_metrics, coastal_profiles) -> TransferResult`

**Output — `TransferResult`:**
```
used: bool                                    # whether transfer was activated
reason: str                                   # why/why not
donor_town: str | None                        # which town was borrowed from
translation_factor: float | None              # PPSF ratio
translated_shell_value: float | None          # donor-adjusted value
blended_value: float | None                   # 65/35 blend of local + translated
local_base_value: float | None                # the thin local base before transfer
confidence_penalty: float                     # -0.25 applied
transferred_confidence: float | None          # capped at 0.45
similarity_score: float | None                # town-pair similarity
method: str                                   # "ppsf_ratio_translation" or "not_activated"
evidence: DonorTownEvidence | None            # full donor town stats
candidates_evaluated: int
candidate_scores: list[TownPairScore]
warnings: list[str]
```

**Activation gate:** `support_quality == "thin"` only

---

### 1.5 Comp Confidence Engine (`briarwood/comp_confidence_engine.py`)

**Entry:** `evaluate_comp_confidence(comp_output, base_comp_selection, feature_result, location_result, transfer_result) -> CompConfidenceResult`

**Output — `CompConfidenceResult`:**
```
composite_score: float                        # 0-1 overall confidence
composite_label: str                          # "High"/"Medium"/"Low"
layers: dict[str, LayerConfidence]            # per-layer: score, label, active, dollar_contribution, weight, components, notes
weakest_layer: str                            # which layer is dragging confidence down
actionable_gaps: list[ConfidenceGap]          # what would improve confidence
narrative: str                                # human-readable explanation
notes: list[str]
```

**Depends on outputs of all 4 engines above.** Pure read-only — produces no valuation adjustments.

---

## 2. Current Integration: `build_comp_analysis()` in `comp_intelligence.py`

### 2.1 Two Parallel Systems

The current `build_comp_analysis()` runs **two independent computation paths** that overlap:

**Path A — Legacy Pydantic adjustment objects (lines 37-41, 85-233):**
- `_feature_adjustments(ctx)` → `list[FeatureAdjustment]` (garage, lot, condition, adu, basement, pool, parking, expansion)
- `_location_adjustments(ctx)` → `list[LocationAdjustment]` (beach, downtown, train, flood, block_quality)
- `_town_transfer_adjustments(ctx)` → `list[TownTransferAdjustment]` (cross_town_shell_transfer)
- `_support_summary(ctx)` → `SupportSummary`
- These are serialized into the `ComparableCompAnalysis` schema fields

**Path B — New engine dataclass calls (lines 44-68):**
- `evaluate_feature_adjustments()` → `FeatureAdjustmentResult`
- `evaluate_micro_location()` → `MicroLocationResult`
- `evaluate_town_transfer()` → `TransferResult`
- `evaluate_comp_confidence()` → `CompConfidenceResult`
- These are serialized via `asdict()` and stored as opaque `dict[str, object]` on the schema

**The two paths compute overlapping adjustments independently.** Neither reads from the other. They coexist in the same output dict without reconciliation.

### 2.2 Value Composition Chain

The current `adjusted_value` in the output is NOT computed by summing base_shell + engine adjustments. Instead:

```python
adjusted_value = _range_midpoint(output.blended_value_range) or output.comparable_value or base_shell_value
```

- `blended_value_range` is computed in `_enrich_comp_intelligence()` (comparable_sales.py line 139) as a weighted blend of 4 comp bucket ranges: direct(45%), income(20%), location(20%), lot(15%)
- This is a **statistical range blend**, not a deterministic layer-by-layer calculation
- The engine results (feature_engine, location_engine, etc.) produce their OWN `adjusted_value` fields but these are NEVER used for the final value

### 2.3 Confidence Source

```python
confidence = round(float(output.comp_confidence_score or output.confidence or 0.0), 2)
```

- `comp_confidence_score` is computed in `_enrich_comp_intelligence()` (line 148) as a blend of average weighted_score (70%) + agent confidence (30%)
- The Comp Confidence Engine's `composite_score` — which actually synthesizes all 4 layer confidences — is computed but **never used** for this field
- The confidence stored on the `ComparableCompAnalysis` is the old statistical blend, not the engine-aware composite

---

## 3. Duplication and Conflicts

### 3.1 Feature Adjustments — Double Computation

| Feature | Legacy `_feature_adjustments()` | Engine `evaluate_feature_adjustments()` |
|---|---|---|
| **garage** | `_median_feature_adjustment()` using 0.8%/unit, 2% cap | Evidence hierarchy: paired_sales → feature_comparison → fallback ($18K/space) |
| **lot** | `_range_delta(lot_range, direct_range)` from enrichment ranges | Evidence hierarchy: excess land × $5.50/sqft or feature_comparison |
| **condition** | `_condition_adjustment_amount()` — rank-based 4%/step, 15% cap | Not a separate feature — handled implicitly in comp similarity |
| **adu** | Copies `additional_unit_income_value` from hybrid valuation | Evidence hierarchy: income_proxy with cap rate, explicit overlap_check |
| **basement** | Flag only (amount=None) | Evidence hierarchy: feature_comparison → fallback ($35/sqft finished) |
| **pool** | Flag only (amount=None) | Evidence hierarchy: feature_comparison → fallback ($15K inground) |
| **parking** | Flag only (amount=None) | Evidence hierarchy: fallback ($5K/space) |
| **expansion** | Flag only (amount=None) | Evidence hierarchy: excess land calculation |

**Conflicts:**
- Garage: Legacy uses per-comp median × pct_per_unit. Engine uses evidence hierarchy with different dollar amounts. Both produce a dollar adjustment — they will disagree.
- Lot: Legacy derives from comp bucket range deltas. Engine uses excess-land pricing. Different methods, different results.
- Condition: Legacy has an explicit adjustment. Engine does not model condition as a feature at all.
- ADU: Legacy copies the hybrid valuation amount. Engine independently computes via income proxy. Both set overlap_check flags but neither reads the other's.

### 3.2 Location Adjustments — Double Computation

| Factor | Legacy `_location_adjustments()` | Engine `evaluate_micro_location()` |
|---|---|---|
| **beach** | `_range_delta(location_range, direct_range)` from enrichment ranges | Haversine distance → bucket → feature_comparison or fallback premium |
| **downtown** | Scaffold only (amount=None) | Haversine distance → bucket → feature_comparison or fallback premium |
| **train** | Scaffold only (amount=None) | Haversine distance → bucket → feature_comparison or fallback premium |
| **flood** | Scaffold only (amount=None) | Parcel flag → risk level → fallback discount |
| **block_quality** | Scaffold only (amount=None) | Insufficient data (no landmarks) |

**Conflicts:**
- Beach: Legacy derives from comp range deltas. Engine uses haversine + comp bucket splitting. Different methods, different results.
- Downtown/train/flood: Legacy is scaffolding only. Engine produces real adjustments. No conflict, but the legacy scaffolds are dead weight.

### 3.3 Town Transfer — No Conflict

Both paths produce a single `cross_town_shell_transfer` entry. The legacy version is always scaffold-only (amount=None). The engine produces a real translated value when activated. No double-counting risk — but the engine result is ignored for the actual `adjusted_value`.

### 3.4 Support Summary — Partial Overlap

Legacy `_support_summary()` reads from `BaseCompSupportSummary` + comp segmentation buckets. The Comp Confidence Engine produces a richer per-layer breakdown. Both exist in the output; neither references the other.

---

## 4. Consumption Path Tracing

### 4.1 Who reads `comp_analysis`?

| Consumer | What it reads | Notes |
|---|---|---|
| `tests/test_modules.py` (lines 250-255) | `base_shell_value`, `location_adjustments["beach"]`, `town_transfer_adjustments["cross_town_shell_transfer"]`, `confidence` | **ONLY real consumer** |

**Nobody else reads `comp_analysis`.** All downstream systems read from `ComparableSalesOutput` directly:

| Consumer | What it reads from `ComparableSalesOutput` |
|---|---|
| `current_value.py` | `direct_value_range`, `income_adjusted_value_range`, `location_adjustment_range`, `lot_adjustment_range`, `blended_value_range`, `comp_confidence_score` |
| `hybrid_value.py` | `is_hybrid_valuation`, `primary_dwelling_value`, `additional_unit_income_value`, `additional_unit_count`, `comp_confidence_score` |
| `liquidity_signal.py` | `comp_count`, `confidence` |
| `comparable_sales_section.py` | `comparable_value`, `comp_count`, `confidence`, `freshest_sale_date`, `median_sale_age_days`, `comps_used[:3]`, `assumptions`, `warnings` |
| `decision_engine.py` | `comp_count`, `comp_confidence` (from metrics dict) |
| `risk_bar.py` | `comp_count`, `comp_confidence`, `overall_confidence` |
| `truth.py` | `comp_count` (passed as parameter) |
| `evidence.py` | Module-level `confidence` float |
| `view_models.py` | `comparable_value`, `comp_count`, `confidence`, `comps_used` via `get_comparable_sales()` |
| `tear_sheet.py` / `pdf_renderer.py` | Same as `comparable_sales_section.py` |

### 4.2 Implication

`comp_analysis` is currently a **diagnostic/audit artifact** — attached to the output for inspection but not consumed by any production code path. This means:

1. The integrator can freely restructure `comp_analysis` without breaking the UI, reports, or downstream modules
2. The only breakage risk is the test at `test_modules.py:250-255`, which checks 4 specific keys
3. The engine results (feature_engine, location_engine, etc.) are computed and serialized but never deserialized or acted on

---

## 5. Value Composition — Double-Counting Risk Analysis

### 5.1 Current Value Flow

```
Agent produces ComparableSalesOutput:
  ├── comparable_value (agent's weighted average of adjusted comps)
  ├── confidence (agent's self-assessed confidence)
  └── comps_used (list of AdjustedComparable with per-comp adjustments)

_enrich_comp_intelligence() adds:
  ├── direct_value_range (from "direct_comps" bucket)
  ├── income_adjusted_value_range (from "income_comps" bucket)
  ├── location_adjustment_range (from location-tagged comps)
  ├── lot_adjustment_range (from lot-matched comps)
  ├── blended_value_range (weighted blend: 45/20/20/15)
  └── comp_confidence_score (0.7 × avg_weighted_score + 0.3 × agent_confidence)

build_comp_analysis() adds:
  └── comp_analysis:
        ├── base_shell_value (from base_comp_selection or direct_range midpoint)
        ├── feature_adjustments (legacy Pydantic — garage, lot, condition, etc.)
        ├── location_adjustments (legacy Pydantic — beach scaffold)
        ├── town_transfer_adjustments (legacy Pydantic — scaffold)
        ├── adjusted_value (blended_range midpoint — NOT base + adjustments)
        ├── support_summary
        ├── confidence (comp_confidence_score — NOT engine composite)
        ├── feature_engine (FeatureAdjustmentResult as dict)
        ├── location_engine (MicroLocationResult as dict)
        ├── town_transfer_engine (TransferResult as dict)
        └── confidence_engine (CompConfidenceResult as dict)
```

### 5.2 Double-Counting Risks

**Risk 1: `adjusted_value` ≠ `base_shell + Σ adjustments`**
The `adjusted_value` comes from `blended_value_range` which is a statistical blend of comp buckets. The legacy adjustment objects (garage, lot, etc.) are separate dollar amounts. If anyone ever sums `base_shell_value + feature_adjustments + location_adjustments`, they will get a DIFFERENT number than `adjusted_value`. These are two independent valuation methods stored side by side with no reconciliation.

**Risk 2: ADU double-counting**
The legacy `_feature_adjustments()` copies `additional_unit_income_value` from hybrid valuation as an ADU feature adjustment. The engine `evaluate_feature_adjustments()` independently computes ADU value via income proxy. Both exist in the output. If both were ever summed, the ADU value would be counted twice.

**Risk 3: Beach premium in multiple places**
- `location_adjustment_range` (enrichment) captures location-tagged comp prices as a range
- Legacy `_location_adjustments()` derives beach amount from range delta
- Engine `evaluate_micro_location()` computes beach via haversine + comp splitting
- `blended_value_range` already includes `location_adjustment_range` at 20% weight
So beach premium appears in: (a) blended_value_range → adjusted_value, (b) legacy location_adjustments, (c) engine location factors. Three representations, no reconciliation.

**Risk 4: Lot premium in multiple places**
Same pattern as beach: `lot_adjustment_range` in the enrichment blend, legacy `_feature_adjustments()` lot delta, and engine lot_premium calculation.

### 5.3 Why it hasn't broken yet

Because `comp_analysis` is never consumed. The actual valuation used by downstream modules is `comparable_value` (agent's direct output) and `blended_value_range` (enrichment layer). The engine results and legacy adjustments are write-only — they exist for diagnostic visibility but don't feed back into the numbers anyone sees.

---

## 6. What the Integrator Must Fix

### 6.1 Eliminate dual computation

Replace the two parallel paths (legacy Pydantic adjustments + engine dataclass calls) with a single execution flow. Each adjustment should be computed once, by the engine that owns it.

### 6.2 Make `adjusted_value` deterministic

The final value should be: `base_shell_value + Σ feature_adjustments + Σ location_adjustments + town_transfer_delta`. No statistical blending that can't be traced. Every dollar in the final value should be attributable to a specific layer.

### 6.3 Use engine confidence as the source of truth

The `confidence` field on `ComparableCompAnalysis` should come from the Comp Confidence Engine's `composite_score`, not from the enrichment layer's statistical blend.

### 6.4 Resolve overlap explicitly

When the feature engine and location engine both touch the same comp evidence (e.g., lot-size comps that also have location tags), the integrator must:
- Check `overlap_warnings` from both engines
- Apply a single deduplication pass
- Document which engine "owns" the overlapping signal

### 6.5 Preserve backward compatibility on `ComparableSalesOutput`

Since all downstream consumers read from `ComparableSalesOutput` fields (not `comp_analysis`), the integrator must continue populating:
- `comparable_value` — can be set to the engine-derived `adjusted_value`
- `comp_confidence_score` — can be set to the engine `composite_score`
- `blended_value_range` — can be rebuilt from engine layer outputs
- Value range fields — can be derived from engine evidence

### 6.6 Update test expectations

The test at `test_modules.py:250-255` checks legacy keys (`location_adjustments["beach"]`, `town_transfer_adjustments["cross_town_shell_transfer"]`). These must be preserved in the schema or the test updated to match the new structure.

---

## 7. Proposed Execution Order

```
1. Base Comp Selector         (already called by agent — result available on comp_output)
2. Feature Adjustment Engine   (base_shell → +features → feature_adjusted_value)
3. Micro-Location Engine       (base_shell → +location → location_adjusted_value)
4. Town Transfer Engine        (activates only if support is thin)
5. Comp Confidence Engine      (reads all 4 above, produces composite confidence)
6. Value Composition           (base_shell + features + location + transfer_delta = final)
7. Overlap Resolution          (check warnings, apply dedup, document)
8. Output Assembly             (populate ComparableCompAnalysis + back-fill ComparableSalesOutput fields)
```

Steps 2 and 3 are independent and could run in parallel. Step 4 depends on step 1's support_quality. Step 5 depends on steps 2-4. Steps 6-8 depend on step 5.

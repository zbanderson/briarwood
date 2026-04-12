# Comp Confidence Audit

Comprehensive audit of how confidence, trust, and evidence quality are currently
handled across the Briarwood valuation stack.

---

## 1. All Confidence Signals Found

### 1.1 Base Comp Selector (`briarwood/base_comp_selector.py`)

**`_support_quality()` — line 269**
- **Measures:** Overall quality of base comp support.
- **Computed from:** `len(selected)`, `median(scores)`, `median_distance`, presence of `extended_support` tier.
- **Thresholds:** strong (>=4 comps, score>=0.72, no extended, distance<=1.5), moderate (>=3 comps, score>=0.58), else thin.
- **Output:** String label: `"strong"`, `"moderate"`, `"thin"`.
- **Consumed by:** `BaseCompSupportSummary.support_quality` → Town Transfer Engine activation gate, `comp_intelligence._support_summary()`.
- **Connection to comp reality:** YES — directly reflects comp count, match quality, and tier spread.

**`_data_quality_score()` — line 498**
- **Measures:** Per-comp data verification and field completeness.
- **Computed from:** `sale_verification_status` (mls_verified=1.0 ... seeded=0.60) + field completeness bonus (beds, baths, sqft, lot_size, year_built presence → up to 0.15).
- **Output:** Float 0–1, weighted at 2% in overall similarity score.
- **Consumed by:** Similarity score → tier assignment → weighted shell value.
- **Connection to comp reality:** YES — rewards better-verified, more-complete comps.

**`_weighted_value()` — line 314**
- **Measures:** Composite weight per comp for shell value calculation.
- **Computed from:** `score * tier_bonus * recency_factor * comp_confidence_weight`.
- **Output:** Per-comp weight → weighted average → `base_shell_value`.
- **Connection to comp reality:** YES — comps with higher match quality and confidence contribute more.

**Per-comp `similarity_score` — line 217**
- **Measures:** Overall comp-to-subject similarity.
- **Computed from:** Weighted sum of 11 dimensions (property_type 15%, distance 15%, sqft 15%, recency 14%, beds 10%, baths 7%, lot 8%, age 6%, condition 5%, structure 3%, data_quality 2%).
- **Output:** Float 0–1.
- **Consumed by:** Tier selection, support quality assessment, weighted value, `base_similarity_score` on `AdjustedComparable`.

---

### 1.2 Feature Adjustment Engine (`briarwood/feature_adjustment_engine.py`)

**Per-feature `FeatureResult.confidence` — line 99**
- **Measures:** Evidence quality behind each feature adjustment.
- **Output:** String label: `"high"`, `"moderate"`, `"low"`, `"none"`, `"n/a"`.
- **Mapping to evidence hierarchy:**
  - `"high"` → paired-sale evidence (NOT currently achieved — no paired-sale data exists).
  - `"moderate"` → feature-comparison (2+ with/without pairs) or income proxy.
  - `"low"` → fallback rule (conservative hardcoded estimate).
  - `"none"` → insufficient data (feature detected but not valued).
  - `"n/a"` → not present or deferred to hybrid.
- **Connection to comp reality:** YES — directly tied to evidence hierarchy.

**`ConfidenceBreakdown` — line 109**
- **Measures:** Dollar-weighted confidence distribution across all features.
- **Computed from:** Summing adjustment amounts by confidence tier.
- **Output:** `high_confidence_portion`, `moderate_confidence_portion`, `low_confidence_portion`, `unvalued_features`.
- **Consumed by:** `weighted_confidence` label.

**`_weighted_confidence()` — line 842**
- **Measures:** Overall feature adjustment confidence.
- **Computed from:** If high portion >= 60% of total → "high". If high+moderate >= 60% → "moderate". Else "low".
- **Output:** String label: `"high"`, `"moderate"`, `"low"`, `"n/a"`.
- **Connection to comp reality:** YES — reflects which evidence tier backs the bulk of dollar adjustments.

---

### 1.3 Micro-Location Engine (`briarwood/micro_location_engine.py`)

**Per-factor `LocationResult.confidence` — line 101**
- **Measures:** Evidence quality behind each location adjustment.
- **Output:** String label: `"high"`, `"moderate"`, `"low"`, `"none"`, `"n/a"`.
- **Mapping:**
  - Beach/Downtown/Train: `"moderate"` if feature-comparison (2+ near/far comps), `"low"` via fallback.
  - Flood: `"moderate"` if parcel-level flag + high risk, else `"low"`.
  - Block quality: `"none"` (insufficient data).
- **Connection to comp reality:** YES — tied to comp-based evidence splits.

**`LocationConfidenceBreakdown` — line 112**
- **Mirrors** the Feature engine's breakdown structure.
- **Output:** Dollar amounts by confidence tier + unvalued factors list.

**`_weighted_confidence()` — line 773**
- **Same logic** as Feature engine: 60% threshold for high/moderate/low.

---

### 1.4 Town Transfer Engine (`briarwood/town_transfer_engine.py`)

**`TransferResult.transferred_confidence` — line 132**
- **Measures:** Confidence after applying transfer penalty.
- **Computed from:** `min(max(raw_confidence - 0.25, 0.05), 0.45)`.
- **Output:** Float, hard-capped at 0.45.
- **Connection to comp reality:** YES — directly penalizes for borrowing non-local evidence.

**`TransferResult.similarity_score` — line 133**
- **Measures:** Town-pair similarity between subject and donor.
- **Computed from:** Weighted sum of 5 components (ppsf_index 35%, coastal_profile 25%, price_level 20%, liquidity 10%, lot_profile 10%) + adjacency bonus.
- **Output:** Float 0–1.

**`_MIN_SIMILARITY = 0.40` — line 45**
- Gate: donors below 0.40 similarity are rejected.

**`_CONFIDENCE_PENALTY = 0.25` — line 52**
- Applied to raw confidence. Even the best transfer is weaker than direct support.

---

### 1.5 Evidence System (`briarwood/evidence.py`)

**`compute_confidence_breakdown()` — line 110**
- **Measures:** Overall analysis confidence from 4 input dimensions.
- **Computed from:** Weighted components:
  - Rent (30%): 0.88 manual → 0.22 missing.
  - CapEx (25%): 0.90 explicit budget → 0.35 low data.
  - Market (25%): aggregates market_value_history, town outlook, geo benchmarking.
  - Liquidity (20%): depends on comp count, exit velocity.
- **Output:** `ConfidenceBreakdown(overall_confidence: float, components: list, notes: list)`.
- **Consumed by:** Risk bar, view models, decision engine.
- **Connection to comp reality:** PARTIAL — the "market" component touches comp module confidence, but the comp-specific evidence hierarchy (feature/location/transfer) is NOT reflected.

**`infer_overall_report_confidence()` — line 382**
- **Measures:** Quick overall confidence with hard caps.
- **Computed from:** Average of module confidences, capped at 0.68 if any critical input missing, 0.76 if any estimated.
- **Connection to comp reality:** NO — uses per-module `confidence` float but doesn't know about evidence quality within the comp stack.

**`compute_critical_assumption_statuses()` — line 148**
- **Measures:** Whether key inputs (rent, taxes, insurance, financing, condition, capex) are confirmed/estimated/missing.
- **Output:** List of `CriticalAssumptionStatus` objects.
- **Consumed by:** Risk bar, confidence caps.
- **Connection to comp reality:** NO — focused on user-supplied inputs, not comp evidence.

---

### 1.6 Truth Module (`briarwood/truth.py`)

**`classify_confidence()` — line 14**
- **Measures:** Shared confidence band for UI and narrative.
- **Computed from:** Counting "weak" and "strong" signals:
  - Weak: comp_count < 3, rent_source = "missing", town_confidence < 0.50.
  - Strong: comp_count >= 5, rent_source in {"manual_input", "provided"}, town_confidence >= 0.75.
- **Output:** `ConfidenceClassification(band="High"/"Medium"/"Low", narrative_level="Grounded"/"Estimated"/"Provisional")`.
- **Consumed by:** UI narrative calibration, scoring module.
- **Connection to comp reality:** MINIMAL — knows comp count, but nothing about match quality, tier distribution, evidence hierarchy, or town transfer usage.

---

### 1.7 Decision Engine (`briarwood/decision_engine.py`)

**`_evidence_quality()` — line 104**
- **Measures:** Composite evidence quality for decision conviction.
- **Computed from:** `current_confidence * 0.32 + income * 0.23 + comp * 0.23 + property_quality * 0.12 + town * 0.10`.
- **Output:** Float 0–1.
- **Consumed by:** Conviction calculation — caps at 0.58 if evidence_quality < 0.35.
- **Connection to comp reality:** WEAK — uses the comp module's single `confidence` float but has no visibility into evidence hierarchy quality.

---

### 1.8 Risk Bar (`briarwood/risk_bar.py`)

**`_confidence_risk()` — line 166**
- **Measures:** Risk from evidence gaps.
- **Computed from:** `100 - (overall_confidence * 100)` + penalties for low comp_count, low comp_confidence (<0.35), low current_confidence (<0.50), missing/estimated assumptions.
- **Output:** Score 0–100 → label ("Thin evidence base" >=67, "Some evidence gaps" >=34, "Well supported").
- **Connection to comp reality:** PARTIAL — knows comp count and the comp module's single confidence float, but not why confidence is low.

---

### 1.9 UI Components (`briarwood/dash_app/components.py`)

**`confidence_badge()` — line 145**
- **Measures:** Nothing — pure display.
- **Output:** Colored percentage badge (positive >=0.75, warning >=0.55, negative <0.55).

**`section_confidence_indicator()` — line 154**
- **Measures:** Nothing — pure display.
- **Output:** Colored dot + percentage + level label ("High confidence", "Medium", "Low").

---

### 1.10 View Models (`briarwood/dash_app/view_models.py`)

**`_module_confidence()` — line 252**
- Extracts per-module confidence float from `AnalysisReport`.

**`_section_confidences()` — line 1072**
- Builds per-section confidence items from module results for the UI.

**`_compute_confidence_level()` — line 1091**
- Computes overall confidence band using `classify_confidence()` from truth.py.
- Produces `ConfidenceFactorItem` objects with component breakdown.

**`_find_top_missing_inputs()` — line 1175**
- Identifies which missing inputs would most improve confidence.
- Maps confidence components to impact estimates.

---

### 1.11 Comparable Sales Schemas (`briarwood/agents/comparable_sales/schemas.py`)

**`ComparableValueRange.confidence` — line 13**
- Float 0–1 on each value range. Currently set by agent, not by the engine stack.

**`AdjustedComparable.comp_confidence_weight` — line 222**
- Float 0–1. Per-comp weight from the agent's scoring.

**`ComparableSalesOutput.confidence` — line 257**
- Float 0–1. The agent's overall confidence — treated as authoritative by downstream.

**`ComparableSalesOutput.comp_confidence_score` — line 273**
- Float 0–1. Optional secondary confidence score.

**`ComparableCompAnalysis.confidence` — line 101**
- Float 0–1 in the comp analysis block. Set by `build_comp_analysis()`.

**`ComparableCompAnalysis.feature_engine` / `location_engine` / `town_transfer_engine` — lines 102-104**
- Dicts holding the full engine outputs. Currently stored but NOT consumed by any confidence aggregation.

---

## 2. Gap Analysis: Current Confidence vs Comp Reality

### 2.1 Does current confidence reflect comp count and match quality?

**PARTIALLY.** `classify_confidence()` in truth.py knows comp count (< 3 is weak, >= 5 is strong) but not match quality. The base comp selector computes `support_quality` (strong/moderate/thin) which considers match quality AND count, but this signal does NOT flow into the overall confidence classification — it's only consumed by the town transfer engine's activation gate.

### 2.2 Does it know when feature premiums are evidence-based vs fallback?

**NO.** The Feature Adjustment Engine produces per-feature confidence labels ("high"/"moderate"/"low"/"none") and a `weighted_confidence` label, but these are stored in `comp_analysis.feature_engine` as a dict and never read by `evidence.py`, `truth.py`, `risk_bar.py`, or `decision_engine.py`. The downstream confidence stack is completely blind to whether $50K in feature adjustments rests on paired-sale evidence or conservative guesses.

### 2.3 Does it know when town transfer was used?

**NO.** The Town Transfer Engine result is stored in `comp_analysis.town_transfer_engine` but never consumed by any downstream confidence signal. The `transferred_confidence` (hard-capped at 0.45) and confidence penalty are computed but discarded.

### 2.4 Does it reflect data missingness?

**PARTIALLY.** `evidence.py` tracks missing inputs for rent, taxes, insurance, financing, condition, capex — these are investment-level inputs. But data missingness on comp-level fields (missing condition profiles, missing lot sizes, missing flood data, missing landmark coordinates) is not tracked. The base comp selector gives a tiny 2% weight to data quality — practically invisible.

### 2.5 Can the system show "High confidence" when comp support is thin?

**YES — THIS IS THE CRITICAL BUG.** The `classify_confidence()` function only needs 3 strong signals (comp_count >= 5, rent confirmed, town confidence >= 0.75) to return "High". It does NOT check:
- Whether those 5 comps are all `extended_support` tier (far, old, poorly matched).
- Whether the feature engine is running on pure fallback rules.
- Whether 35% of the valuation comes from town-transferred evidence.
- Whether location adjustments rest on 0 comp evidence.

A property with 5 poor-match comps, all fallback-rule features, and town-transferred evidence can display "High confidence" if rent is confirmed and town context is above 0.75.

### 2.6 Is confidence computed once or updated as each module contributes?

**ONCE, AT REPORT GENERATION.** `compute_confidence_breakdown()` runs once per report build. The three new engines (feature, location, town transfer) produce their own confidence signals but these are never fed back into the overall computation.

---

## 3. Signal-to-Layer Connection Matrix

| Current Signal | Base Comps | Features | Location | Town Transfer | Data Quality |
|---|---|---|---|---|---|
| `support_quality` (base selector) | **YES** (count, match, tier) | no | no | no | partial (2% weight) |
| `FeatureResult.confidence` (feature engine) | no | **YES** (per-feature) | no | no | no |
| `LocationResult.confidence` (location engine) | no | no | **YES** (per-factor) | no | no |
| `TransferResult.transferred_confidence` (transfer engine) | no | no | no | **YES** | no |
| `compute_confidence_breakdown()` (evidence.py) | no | no | no | no | **YES** (rent/capex/market/liq) |
| `classify_confidence()` (truth.py) | partial (count only) | no | no | no | partial (rent source) |
| `_evidence_quality()` (decision engine) | partial (single float) | no | no | no | partial (module floats) |
| `_confidence_risk()` (risk bar) | partial (count + float) | no | no | no | partial (assumptions) |
| `confidence_badge()` (UI) | no (display only) | no | no | no | no |
| `section_confidence_indicator()` (UI) | no (display only) | no | no | no | no |

### Key Findings

1. **Feature, Location, and Town Transfer engines produce detailed confidence signals that nothing consumes.** The engines do their job — they compute evidence quality, trace it to methods, break it down by tier — but the information dead-ends in `comp_analysis` dict storage.

2. **The overall confidence pipeline has zero visibility into the comp valuation stack.** It sees a single `confidence` float from the comparable_sales module and treats it as a black box.

3. **No single system synthesizes comp-stack confidence.** The base selector knows comp quality. The feature engine knows feature evidence quality. The location engine knows location evidence quality. The transfer engine knows transfer confidence. But nobody aggregates these four signals into one "how much should you trust this comp-derived valuation" answer.

4. **The user-facing confidence band can be fundamentally misleading** because it's computed from input completeness (rent, capex) rather than valuation evidence quality.

---

## 4. What the Comp Confidence Engine Must Fix

1. **Aggregate layer-by-layer confidence.** Read the outputs of all four engines and produce a composite score where no single strong layer can mask a weak one.

2. **Replace decorative confidence with evidence-aware confidence.** The current "High/Medium/Low" band should reflect actual comp evidence quality, not just whether the user provided rent data.

3. **Trace every confidence component.** The user should be able to see: "Base shell support is strong (4 tight comps), feature adjustments are low confidence (all fallback rules), location is moderate (comp-based beach evidence), no town transfer needed."

4. **Prevent false precision.** If 40% of the valuation rests on fallback rules, the overall confidence should reflect that — regardless of how many comps were found for the base shell.

5. **Surface actionable gaps.** Instead of "confidence is 62%", tell the user "confidence would improve most from: (1) garage sale evidence in comps, (2) parcel-level flood data, (3) block-level quality data."

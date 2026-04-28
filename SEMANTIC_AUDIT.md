# Briarwood Semantic Model Extraction Audit

> **Phase 1 — Read-only extraction. No code changed.**
> Run on 2026-04-27. Authoritative source for every claim is the cited
> `file:line`. READMEs and `ARCHITECTURE_CURRENT.md` were *not* used to
> populate this audit; the goal IS to surface what the code says.

---

## Executive Summary

Five findings worth the user's attention before anything else.

1. **CRITICAL drift in "is this property under/fair/over priced?"** Two
   independent code paths classify the same concept with different
   thresholds. A property where BCV = ask × 1.06 lands as
   *"appears fairly priced"* in the synthesizer prose
   (`agents/current_value/agent.py:444-451`) and *"value_find"* in
   the claim verdict (`editor/checks.py:14-15` and
   `claims/synthesis/verdict_with_comparison.py:42-43`). A property at
   BCV = ask × 0.95 lands as *"appears fully valued"* and *"overpriced"*
   simultaneously. See Drift §4.1.

2. **HIGH drift in BCV component count.** The audit prompt and prior
   docs assume "BCV has 4 components." The current code blends **5**
   components with explicit base weights summing to 1.00:
   `comparable_sales 0.40, market_adjusted 0.24, town_prior 0.16,
   backdated_listing 0.12, income 0.08`
   (`briarwood/agents/current_value/agent.py:18-24`). If any prompt or
   doc still says "four anchors," it is wrong.

3. **HIGH gap: confidence floors are unanchored.** Synthesis enforces
   hard trust gates (`TRUST_FLOOR_STRONG = 0.70`, `TRUST_FLOOR_ANY =
   0.40` in `synthesis/structured.py:27-28`) that no prompt template
   references. The LLM-facing synthesis prompt
   (`llm_prompts.py:107-110`) says only "lower confidence when modules
   conflict" with no numeric anchors. The LLM can emit a CONDITIONAL
   stance at confidence 0.55 and the gate will downgrade it; the LLM
   has no way to know that.

4. **HIGH orphan: "Forward Value Gap" exists in the audit prompt and
   product vocabulary, but no module computes a metric of that name.**
   The closest implementation is `premium_pct` in
   `modules/risk_model.py:130-136` (a binary ±10/+15 flag, not a
   continuous gap). Same for "Optionality Score" — there is an
   `OptionalitySignal` Pydantic carrier in `routing_schema.py:356` and
   `value_scout/scout.py` produces qualitative `HiddenUpsideItem`
   records, but no scalar score.

5. **MEDIUM drift hazard: the editor↔synthesis threshold pair is
   currently in sync but unguarded.** `VALUE_FIND_THRESHOLD_PCT = -5.0`,
   `OVERPRICED_THRESHOLD_PCT = 5.0`, `SMALL_SAMPLE_THRESHOLD = 5` are
   defined twice — once in `editor/checks.py:14-20` and once in
   `claims/synthesis/verdict_with_comparison.py:39-43` — with no test
   guarding equality. The editor's own comment at line 18-20 names the
   hazard. Already tracked in `ROADMAP.md` 2026-04-24.

The codebase has a coherent semantic backbone — most metrics have one
clear computation site. The dangerous failure modes are at the
**boundaries**: where the same concept is rephrased for the user
(prose pricing view vs. claim verdict), and where the LLM is asked to
respect numeric guardrails it has no way to see.

---

## Step 1 — Repo orientation

### Top-level layout

| Top-level dir | Role |
|---|---|
| `briarwood/` | Core engine: modules, agents, scoring, routing, synthesis, representation |
| `briarwood/modules/` | Scoped registry of analysis modules (BCV, risk, scenarios, etc.) |
| `briarwood/agents/` | Agent-tier wrappers (current_value, comparable_sales, income, scarcity, town_county, rent_context, rental_ease, school_signal, market_history) |
| `briarwood/synthesis/` | LLM- and structured-synthesizers turning module results into narrative |
| `briarwood/representation/` | Chart + claim selection (RepresentationAgent) |
| `briarwood/value_scout/` | Hidden-upside / optionality LLM agent |
| `briarwood/decision_model/` | Aggregate scoring helpers (legacy weights file) |
| `briarwood/local_intelligence/` | Town-document ingestion + signal extraction |
| `briarwood/data_sources/` | External API clients (SearchApi/Zillow, FRED, etc.) |
| `briarwood/data_quality/` | Provenance, eligibility, normalization |
| `briarwood/inputs/` | Property loader + adapters (canonical / listing / MLS / public-record) |
| `briarwood/execution/` | Scoped execution (registry, executor, planner, context) |
| `briarwood/agent/` | Chat-tier router, dispatch, composer, session, tools |
| `briarwood/claims/` | Pydantic claim types (verdict_with_comparison etc.) |
| `briarwood/editor/` | Claim validation + threshold-coherence checks |
| `briarwood/listing_intake/` | Raw-listing parse → normalized property |
| `briarwood/charts/` | Chart payload builders |
| `briarwood/projections/` | (Legacy / partial) projection helpers |
| `briarwood/feedback/` | User-feedback capture |
| `api/` | FastAPI bridge to the chat UI |
| `api/prompts/` | 15 markdown prompt templates per answer-type tier |
| `web/` | Next.js frontend |

### Files that define a metric, score, threshold, or interpretation band

| File | What it does | Metrics it touches |
|---|---|---|
| `briarwood/agents/current_value/agent.py` | BCV blender — five-component weighted average, pricing view bands | `briarwood_current_value`, `comparable_sales_value`, `market_adjusted_value`, `backdated_listing_value`, `income_supported_value`, `town_prior_value`, `pricing_view`, `mispricing_pct`, `confidence` |
| `briarwood/agents/current_value/schemas.py` | Pydantic dataclasses for the five components and trace items | component dataclasses |
| `briarwood/modules/current_value.py` | Scoped wrapper around the agent; applies confidence caps for missing inputs | confidence caps (rent missing 0.55, rent estimated 0.70, financing incomplete 0.50, insurance missing 0.55) |
| `briarwood/modules/valuation.py` | Tiny wrapper that adds an HPI macro nudge to BCV | `briarwood_current_value`, `macro_nudge` |
| `briarwood/modules/bull_base_bear.py` | Bull/Base/Bear/Stress generator + scenario confidence | `bull_case_value`, `base_case_value`, `bear_case_value`, `stress_case_value`, `spread`, `spread_pct`, scenario confidence multi-factor formula |
| `briarwood/modules/resale_scenario.py` | Scoped wrapper around bull_base_bear with hold-period/exit-metric overlay | `base_growth_rate`, `bull_bear_spread_pct`, terminal exit values |
| `briarwood/modules/renovation_scenario.py` | Renovation BCV delta + ROI | `current_bcv`, `renovated_bcv`, `gross_value_creation`, `net_value_creation`, `roi_pct` |
| `briarwood/modules/arv_model_scoped.py` | Re-packages renovation/valuation into ARV snapshot | `arv_snapshot` |
| `briarwood/modules/margin_sensitivity_scoped.py` | Six-scenario budget×value sensitivity grid | `margin_floor`, `margin_ceiling`, `margin_fragility` |
| `briarwood/modules/ownership_economics.py` | Monthly + annual carry costs, NOI, cap rate, DSCR | `monthly_total_cost`, `annual_noi`, `cap_rate`, `dscr`, `monthly_cash_flow` |
| `briarwood/modules/carry_cost.py` | Pure wrapper around ownership_economics | (passthrough) |
| `briarwood/modules/hold_to_rent.py` | Owner-occupy → rental conversion scoring | `hold_to_rent_value`, `conversion_risk` |
| `briarwood/modules/rent_stabilization.py` | Rent growth & stability over hold | `stabilized_rent`, `rent_growth_rate` |
| `briarwood/modules/rental_option.py` | Rental viability + yield | `monthly_rent`, `rent_source`, `rental_yield`, `gross_yield` |
| `briarwood/modules/opportunity_cost.py` | Property terminal vs T-bill / S&P benchmarks | `entry_basis`, `base_growth_rate`, `tbill_terminal`, `sp500_terminal`, `excess_vs_tbill_bps`, `excess_vs_sp500_bps` |
| `briarwood/modules/risk_model.py` | Risk wrapper; legal-confidence dampener; valuation-premium flag | `risk_score`, `risk_confidence`, `risk_factors`, `premium_pct` (the unnamed "Forward Value Gap" proxy) |
| `briarwood/modules/risk_constraints.py` | The actual risk math: flood, tax, DOM, vacancy, age penalties | flood/tax/DOM/vacancy/age sub-scores; base 85.0 |
| `briarwood/modules/legal_confidence.py` | Zoning / accessory-unit legal confidence | `legal_confidence` (clamped to [0.55, 0.65] under specific signal combos) |
| `briarwood/modules/confidence.py` | Overall confidence aggregation (7-signal weighted blend with penalties) | `combined_confidence`, plus seven sub-signals |
| `briarwood/modules/comp_scoring.py` | Unified comp-similarity scoring (proximity / recency / data quality) | comp `score` weighted 30/25/30/15 |
| `briarwood/modules/comparable_sales.py` | Comp module entry; calls scoring + adjustment | `comp_value`, `comp_count`, `comp_confidence` |
| `briarwood/agents/comparable_sales/agent.py` | Agent wrapper around comp pipeline | `_score_comp`, `_proximity_score`, `_recency_score`, `_data_quality_score` (per ROADMAP.md 2026-04-26: thresholds at 10% and 20%, no hard 15% band) |
| `briarwood/comp_confidence_engine.py` | Four-layer comp-stack confidence (base shell / features / location / town transfer) with weakest-layer floor cap | `base_shell_score`, `features_score`, `location_score`, `transfer_score`, `composite_confidence` |
| `briarwood/feature_adjustment_engine.py` | Condition / style / feature dollar adjustments per comp | per-comp `feature_adj_pct`, `weighted_confidence` |
| `briarwood/micro_location_engine.py` | Per-factor location dollar adjustments (beach / downtown / train / park / ski / flood) with 3-tier confidence | per-factor confidence labels, dollar adjustments |
| `briarwood/town_transfer_engine.py` | Donor-town transfer when local comps are sparse | `town_similarity_score`, `transferred_confidence` |
| `briarwood/modules/location_intelligence.py` | Composite location score from proximity / supply / rarity / lifestyle / risk | `location_score`, `scarcity_score` (weighted 35/25/20/20) |
| `briarwood/modules/town_development_index.py` | Approval rate, activity volume, restrictive signals from minutes | `development_velocity`, `approval_rate`, `activity_volume`, `substantive_changes`, `restrictive_signals`, `contention`, ±0.04 confidence nudge |
| `briarwood/modules/strategy_classifier.py` | Rule-based seven-strategy classification | `strategy_label`, `strategy_confidence` |
| `briarwood/modules/income_support.py` | Income vs cost ratio with banded scoring | `income_support_ratio`, banded score 0–100 |
| `briarwood/agents/income/agent.py` | Income agent: Price-to-Rent + monthly cash flow + confidence formula | `price_to_rent`, `monthly_cash_flow`, income confidence (7-factor) |
| `briarwood/agents/scarcity/scarcity_support.py` | Scarcity composite (location 55%, land 45%) → support (60% scarcity, 40% demand-consistency) | `scarcity_score`, `scarcity_support_score` |
| `briarwood/agents/rental_ease/agent.py` | Liquidity score 0–100 with banded label | `liquidity_score`, label thresholds at 80 / 55 |
| `briarwood/agents/town_county/service.py` | Town-level outlook aggregation (price/population trends, flood, liquidity, macro, schools) | `TownCountyOutlookResult` with 9 fields |
| `briarwood/interactions/valuation_x_risk.py` | Risk-adjusted fair value: per-flag 2% discount, max 15% | `risk_adjusted_fair_value` |
| `briarwood/synthesis/structured.py` | Deterministic synthesizer; assembles `value_position`, applies trust floors | `fair_value_base`, `ask_premium_pct`, `basis_premium_pct`, `value_low/high`; `TRUST_FLOOR_STRONG=0.70`, `TRUST_FLOOR_ANY=0.40` |
| `briarwood/synthesis/llm_synthesizer.py` | LLM prose synthesizer with verifier + regen loop | numeric-grounding rule (no specific thresholds in code) |
| `briarwood/editor/checks.py` | Claim validation thresholds | `VALUE_FIND_THRESHOLD_PCT=-5.0`, `OVERPRICED_THRESHOLD_PCT=5.0`, `SMALL_SAMPLE_THRESHOLD=5` |
| `briarwood/claims/synthesis/verdict_with_comparison.py` | Claim verdict label assignment (mirror of editor thresholds) | `VALUE_FIND_THRESHOLD=-5.0`, `OVERPRICED_THRESHOLD=5.0`, `SMALL_SAMPLE_THRESHOLD=5` |
| `briarwood/claims/synthesis/templates.py` | Deterministic verdict headline f-strings | template strings keyed by label |
| `briarwood/recommendations.py` | Score → Buy/Neutral/Avoid label mapping | recommendation rank & cap |
| `briarwood/risk_bar.py` | Risk visualization helper | renders `risk_score` |
| `briarwood/scoring.py` | `clamp_score(x, 0, 100)` utility | (no thresholds) |
| `briarwood/decision_model/scoring.py` | Legacy weights / `estimate_comp_renovation_premium` | (largely deprecated per file header) |
| `briarwood/opportunity_metrics.py` | Net opportunity delta for comparisons | `opportunity_delta` |
| `briarwood/evidence.py` | Confidence breakdown by component (rent / capex / market / liquidity) | `compute_confidence_breakdown` |
| `briarwood/value_scout/scout.py` | Hidden-upside LLM agent producing `OptionalitySignal` + `HiddenUpsideItem` list | qualitative hidden-upside records (no numeric score) |
| `briarwood/representation/agent.py` | Picks 2-3 charts + claim_types per intent | ClaimType enum (15 types), chart selection rules |

### Prompt template inventory

15 markdown templates under `api/prompts/`:

- `_base.md` — compositional rules shared by all tiers
- `decision_summary.md`, `decision_value.md` — full decision read / value question
- `risk.md` — downside briefing
- `edge.md` — value-thesis read
- `strategy.md` — best-path strategy
- `projection.md` — bull/base/bear scenarios
- `research.md` — town-level intelligence
- `lookup.md`, `rent_lookup.md` — factual / rental factual
- `browse_surface.md` — three-line first impression
- `claim_verdict_with_comparison.md` — investor-persona verdict prose
- `section_followup.md` — section-level follow-ups
- `visual_advisor.md` — UI layout / chart selection

Plus six in-Python prompt strings:

- `briarwood/llm_prompts.py:13-58` — `build_intent_parser_prompt()`
- `briarwood/llm_prompts.py:61-142` — `build_synthesis_prompt()`
- `briarwood/synthesis/llm_synthesizer.py:64-165` — `_SYSTEM_PROMPT_NEWSPAPER`
- `briarwood/synthesis/llm_synthesizer.py:172-209` — plain-style fallback prompt
- `briarwood/agent/composer.py:219-239` — decision critic (`_CRITIC_SYSTEM`)
- `briarwood/agent/router.py:169-226` — `_LLM_SYSTEM` intent classifier
- `briarwood/representation/agent.py:122-157` — `_SYSTEM_PROMPT` (chart/claim picker)
- `briarwood/shadow_intelligence.py:79-92` — shadow planner + evaluator prompts
- `briarwood/local_intelligence/prompts.py:6-25` — `LOCAL_INTELLIGENCE_SYSTEM_PROMPT`
- `briarwood/local_intelligence/minutes_sources.py:376` — `_BUYER_LENS_SYSTEM_PROMPT`

---

## Step 2 — Entity inventory

### Property — 4 concurrent representations

| Class | File:line | Shape | Role |
|---|---|---|---|
| `PropertyFacts` | `briarwood/schemas.py:120` | dataclass, slots, immutable. Address + structural facts only (beds, baths, sqft, lot, year_built, condition, HOA, taxes, listing date, price history, sale history). | Facts-only carrier. |
| `CanonicalPropertyData` | `briarwood/schemas.py:225` | dataclass with `facts: PropertyFacts`, `market_signals: MarketLocationSignals`, `user_assumptions: UserAssumptions`, `source_metadata: SourceMetadata`, `property_id`. | Canonical internal form. |
| `PropertyInput` | `briarwood/schemas.py:236` | dataclass with all `PropertyFacts` + `UserAssumptions` + `MarketLocationSignals` fields **flattened** to one namespace. Plus optional structured nested copies, `geocoded`, `defaults_applied`. | Working model used by every legacy module. Derived via `from_canonical()`. |
| `Subject` | `briarwood/claims/verdict_with_comparison.py:15` | Pydantic, minimal: `property_id, address, beds, baths, sqft, ask_price, status`. | Claim-tier projection. |

There is also `NormalizedPropertyData` in `briarwood/listing_intake/schemas.py:71` — an intermediate intake form converted into `PropertyInput`.

**Drift risk:** No mechanical guard prevents `PropertyInput` from disagreeing with `PropertyFacts` on a field's name or type. The flattening means a renamed field on `PropertyFacts` will silently break the flat namespace.

### Comp — 2-stage pipeline

| Class | File:line | Shape |
|---|---|---|
| `ComparableSale` | `briarwood/agents/comparable_sales/schemas.py:116` | Pydantic. Raw comp from API/database. ~25 fields including `mls_id`, `zillow_id`, `address`, `price`, `beds`, `baths`, `sqft`, `sale_date`, `days_on_market`, `latitude`, `longitude`, `distance_miles`, `adjusted_price`, `adjustment_pct`, `source`. |
| `AdjustedComparable` | `briarwood/agents/comparable_sales/schemas.py:213` | Pydantic. Wraps `ComparableSale` with `feature_adjustment`, `location_adjustment`, `town_transfer_adjustment`, `final_adjusted_price`, `confidence_score`. |
| `ComparableSalesOutput` | `briarwood/agents/comparable_sales/schemas.py:266` | Pydantic. Final: `comps_used: list[AdjustedComparable]`, `comparable_value`, `comp_count`, `average_price_per_sqft`, `median_price_per_sqft`, `price_range_low/high`, `subject_ppsf`, `comparable_value_range`, `confidence`, `confidence_notes`, `missing_inputs`, `analysis_summary`. |

**Comp-confidence parallel structure** at `briarwood/comp_confidence_engine.py:118` (`CompConfidenceResult` per-comp record) and `briarwood/modules/comp_scoring.py:205` (`CompScores` with proximity/recency/data_quality/market_confidence). These are scoring outputs, not entity duplicates.

Per `ROADMAP.md` 2026-04-26: comp Engine A (saved comps for fair-value) and Engine B (live `get_cma`) were unified onto `briarwood/modules/comp_scoring.py` in CMA Phase 4a. No duplicate Comp dataclass remains, but the call sites still differ.

### Town / Market — 4 carriers

| Class | File:line | Role |
|---|---|---|
| `MarketLocationSignals` | `briarwood/schemas.py:164` | Property-level carrier of market context (trends, liquidity, scarcity, ZHVI history, schools, flood, P/R benchmark, landmarks, zone flags). |
| `TownCountyOutlookResult` | `briarwood/agents/town_county/service.py:31` | Town-level aggregate (price trend, population trend, flood, liquidity label, macro sentiment, school signal, market momentum, emerging-market flag, development pipeline). |
| `LiquiditySignalOutput` | `briarwood/schemas.py:606` | Liquidity score + label (`highly_liquid` / `liquid` / `illiquid` / `very_illiquid`) + DOM + comp count. |
| `MarketMomentumOutput` | `briarwood/schemas.py:624` | Market momentum score + label + history trend score + town market score + 1yr/3yr change pct + drivers. |

`TownCountyOutlookResult` feeds `MarketLocationSignals`. They are not duplicates but they overlap on `flood_risk`, trends, and `liquidity_label`. Risk: a write to one is not auto-mirrored to the other.

### Rental / Income — 3 carriers

| Class | File:line | Role |
|---|---|---|
| `IncomeAgentOutput` | `briarwood/agents/income/schemas.py:35` | Best-estimate monthly rent, source, confidence, yield. |
| `RentContextOutput` | `briarwood/agents/rent_context/schemas.py:19` | Market benchmark context (market rent, P/R benchmark, historical yield). |
| `ValuationOutput.effective_monthly_rent` | `briarwood/schemas.py:462` | The rent **selected** for the cash-flow calculation — may be the user override, the income agent's estimate, or the listing-parsed value. |

Three values can disagree. The selection logic lives in valuation; the divergence is not surfaced.

### Risk

| Class | File:line | Role |
|---|---|---|
| `RiskModelOutput` | (not a single dataclass — fields live in `briarwood/modules/risk_model.py` returning a `ModulePayload`) | `risk_score`, `risk_confidence`, `risk_narrative`, sub-scores for liquidity/market/structural/legal/execution, `risk_factors[]`. |
| `CriticalAssumptionStatus` | `briarwood/evidence.py:81` | Per-input status: `confirmed / estimated / missing` for rent, capex, condition. |

`risk_bar.py` is presentation-layer only.

### Scenario

| Class | File:line | Role |
|---|---|---|
| `ScenarioOutput` | `briarwood/schemas.py:520` | `ask_price`, `bull_case_value`, `base_case_value`, `bear_case_value`, `spread`, `stress_case_value` (optional). |
| `ResaleScenarioOutput` | (in `briarwood/modules/resale_scenario.py`) | Extends with `hold_period_years`, exit metrics. |

### Valuation / Fair Value

| Class | File:line | Role |
|---|---|---|
| `ValuationOutput` | `briarwood/schemas.py:462` | Comprehensive snapshot: `purchase_price`, `price_per_sqft`, `monthly_rent`, `rent_source_type`, financing flags, monthly cost decomposition (taxes/insurance/HOA/maintenance/mortgage/total), `monthly_cash_flow`, `annual_noi`, `cap_rate`, `gross_yield`, `dscr`, `cash_on_cash_return`, `loan_amount`, `down_payment_amount`. |
| `CurrentValueOutput` | `briarwood/agents/current_value/schemas.py:81` | BCV-tier output: `briarwood_current_value`, `pricing_view`, the five components, value range, confidence. |

**Note:** "ValuationOutput" and "CurrentValueOutput" overlap conceptually but live at different layers — `ValuationOutput` is the cash-flow / mortgage record; `CurrentValueOutput` is the BCV record. They both serve as "valuation" outputs in different contexts.

### Final decision shape

| Class | File:line | Role |
|---|---|---|
| `UnifiedIntelligenceOutput` | `briarwood/routing_schema.py:395` | The final synthesized decision: `recommendation`, `decision`, `best_path`, `key_value_drivers`, `key_risks`, `confidence`, `analysis_depth_used`, `next_questions`, `decision_stance`, `primary_value_source`, `value_position`, `what_must_be_true`, `next_checks`, `trust_flags`, `trust_summary`, `contradiction_count`, `blocked_thesis_warnings`, `why_this_stance`, `what_changes_my_view`, `interaction_trace`, `optionality_signal`. |
| `EngineOutput` | `briarwood/routing_schema.py:342` | `outputs: dict[str, ModulePayload]` — pre-synthesis bundle. |
| `ModulePayload` | `briarwood/routing_schema.py:316` | Per-module standard contract: `data, confidence, assumptions_used, warnings, mode, missing_inputs, estimated_inputs, confidence_band, module_name, score, summary`. |

### Analysis context

| Class | File:line | Role |
|---|---|---|
| `ExecutionContext` | `briarwood/execution/context.py:8` | The runtime carrier passed to scoped modules — `property_data, property_summary, parser_output, assumptions, prior_outputs, market_context, comp_context, macro_context, field_provenance, missing_data_registry, normalized_context`. |

### Intent

| Class | File:line | Role |
|---|---|---|
| `ParserOutput` | `briarwood/routing_schema.py:281` | Analysis-tier intent: `intent_type, analysis_depth, question_focus, hold_period_years, occupancy_type, renovation_plan, exit_options, has_additional_units, confidence, missing_inputs`. |
| `IntentContract` | `briarwood/intent_contract.py:38` | Bridge between chat-tier router and analysis tier: `answer_type, core_questions, question_focus, confidence`. |

Two parallel intent enums (`AnswerType` chat-tier vs `IntentType`/`CoreQuestion` analysis-tier) reconciled via the `ANSWER_TYPE_TO_CORE_QUESTIONS` mapping.

### Verdict / Claim (representation tier)

| Class | File:line | Role |
|---|---|---|
| `Verdict` | `briarwood/claims/verdict_with_comparison.py:25` | `label: Literal[value_find, fair, overpriced, insufficient_data]`, `headline`, `basis_fmv`, `ask_vs_fmv_delta_pct`, `method`, `comp_count`, `comp_radius_mi`, `comp_window_months`, `confidence: Confidence`. |
| `VerdictWithComparisonClaim` | `briarwood/claims/verdict_with_comparison.py:75` | Full claim: `archetype, subject, verdict, bridge_sentence, comparison, caveats, next_questions, provenance, surfaced_insight`. |

### Local intelligence

| Class | File:line | Role |
|---|---|---|
| `LocalIntelligenceProject` | `briarwood/schemas.py:591` | One development/zoning record with status, units, location, time horizon, evidence excerpt, confidence. |
| `LocalIntelligenceOutput` | `briarwood/schemas.py:665` | Aggregate: projects[], summary counts, scores (development_activity, supply_pipeline, regulatory_trend, sentiment), narrative[], confidence, signals[]. |

### Inconsistent / duplicated entities — summary

1. **Property has 4 representations.** Canonical → flattened working copy → claim subject → intake intermediate. The flattening is the dangerous step.
2. **Rent has 3 sources** that can disagree silently (`IncomeAgentOutput.monthly_rent_estimate` vs `RentContextOutput.market_rent_estimate` vs `ValuationOutput.effective_monthly_rent`).
3. **Town-level data has 2 carriers** with overlapping fields (`MarketLocationSignals` and `TownCountyOutlookResult`). One feeds the other but no symmetry guard.
4. **Hidden upside has 2 frames** (`HiddenUpsideItem` granular, `OptionalitySignal` aggregate) — these are intentional layers, not drift.
5. **Field provenance has 3 layers** (`CanonicalFieldProvenance`, `SourceCoverageItem`, `field_provenance` dict in `ExecutionContext`). They serve different stages but a downstream reader could confuse them.
6. **`ValuationOutput` vs `CurrentValueOutput`** — both "valuation" outputs but different contracts. Naming is the only collision.
7. **Two intent enums** (`AnswerType` chat-tier vs `IntentType`+`CoreQuestion` analysis-tier) bridged by an explicit map. Functional but the bridge can drift if either enum gains a value.

---

## Step 3 — Metric extraction

> Format per metric: location(s), inputs, formula, units/range, thresholds, confidence handling, downstream consumers, intent tags. Code snippets are abbreviated to the shortest line span that captures the formula.

### 3a. Valuation, BCV, and scenario metrics

#### Metric: Briarwood Current Value (BCV) — the master valuation

- **Found in:** `briarwood/agents/current_value/agent.py:18-189` (calculation), `briarwood/modules/current_value.py:44-249` (caps), `briarwood/modules/valuation.py:15-57` (HPI nudge wrapper)
- **Inputs:** `comparable_sales_value` + confidence, `market_value_today` (ZHVI), `ask_price`, `listing_date`, market history points, effective annual rent, cap rate assumption, town median ppsf / median price / median sqft / median lot, town context confidence, local-doc count, plus property facts (sqft, lot_size, beds, baths, year_built).
- **Formula:** Five-component confidence-weighted blend.
  ```python
  # agent.py:18-24
  _COMPONENT_BASE_WEIGHTS = {
      "comparable_sales": 0.40,
      "market_adjusted":  0.24,
      "backdated_listing": 0.12,
      "income":           0.08,
      "town_prior":       0.16,
  }
  # agent.py:152-189 — each weight multiplied by that component's
  # confidence, then renormalized; BCV = Σ(component_value · normalized_weight)
  ```
- **Units / range:** USD.
- **Thresholds / interpretation bands:** the `pricing_view` translation lives at `agent.py:444-451`:
  ```python
  if mispricing_pct >= 0.08:  return "appears undervalued"
  if mispricing_pct >= -0.03: return "appears fairly priced"
  if mispricing_pct >= -0.10: return "appears fully valued"
  return "appears overpriced"
  ```
  where `mispricing_pct = (BCV − ask_price) / ask_price`. **(See Drift §4.1 — disagrees with editor.)**
- **Confidence handling:** Weighted average of component confidences (`agent.py:180-189`), then capped by input quality (`current_value.py:262-273`):
  - rent missing → cap 0.55
  - rent estimated → cap 0.70
  - financing incomplete → cap 0.50
  - insurance missing → cap 0.55
- **Used by:** Bull/Base/Bear (`bull_base_bear.py:98`); renovation scenario (`renovation_scenario.py:163`); ARV (`arv_model_scoped.py:55`); margin sensitivity (`margin_sensitivity_scoped.py:54`); opportunity cost (`opportunity_cost.py:78`); structured synthesis (`structured.py:253`); chat dispatch (`agent/dispatch.py` — many sites referencing `pricing_view`).
- **Intent tags:** DECISION / VALUATION / BROWSE.

#### Metric: Comparable Sales Value (BCV component)

- **Found in:** `briarwood/agents/current_value/agent.py:31-36`, `briarwood/modules/current_value.py:201`
- **Inputs:** comp set (typically 3–10), adjusted prices, comp count, comp confidence.
- **Formula:** Direct adjusted-comp average; weighted at 0.40 in BCV multiplied by comp confidence.
- **Units:** USD.
- **Thresholds:**
  - Comp count ≥ 5 → town-prior confidence ×0.45 (`agent.py:283`)
  - Comp count 3-4 → town-prior ×0.60 (`:285`)
  - Comp count 2 → town-prior ×0.75 (`:287`)
  - Comp confidence ≥ 0.80 → town-prior ×0.60 (`:289`)
  - Comp confidence < 0.5 → "weak comp set" trust flag (`structured.py:288`)
  - ZHVI divergence > 30% from healthy comp set → ZHVI confidence ×0.35 (`agent.py:80`)
- **Confidence handling:** From `comparable_sales` module; de-emphasized on >30% market divergence.
- **Used by:** BCV blend (40%); rent-support anchor check.
- **Intent tags:** VALUATION / PRICING / BROWSE.

#### Metric: Market-Adjusted Value (BCV component, ZHVI-derived)

- **Found in:** `briarwood/agents/current_value/agent.py:48-91`
- **Inputs:** `market_value_today` (ZHVI), market history points, property-level details for adjustment factor.
- **Formula:** `market_adjusted_value = market_value_today × (1 + property_adjustment_factor)` — adjustment factor bounded. Confidence scales with history points + property detail count.
- **Units:** USD.
- **Thresholds:**
  - Divergence > 15% from ask → warning (`agent.py:61`)
  - Divergence > 30% from healthy comps → ×0.35 confidence penalty (`agent.py:80`)
- **Confidence:** `_market_component_confidence(history_points, property_detail_count)`.
- **Used by:** BCV blend (24%).
- **Intent tags:** VALUATION / MARKET / BROWSE.

#### Metric: Backdated Listing Value (BCV component)

- **Found in:** `briarwood/agents/current_value/agent.py:93-118`
- **Inputs:** `listing_date` (direct or inferred from `days_on_market`), `ask_price`, market history points, `market_value_today`.
- **Formula:** `ask_price × (market_value_today / market_value_at_listing_date)`.
- **Thresholds:** Listing gap > 31 days → coarse-alignment warning. Listing date inferred from DOM → confidence reduced.
- **Confidence:** Direct date 0.85 base / inferred 0.70 base.
- **Used by:** BCV blend (12%).

#### Metric: Income-Supported Value (BCV component)

- **Found in:** `briarwood/agents/current_value/agent.py:120-138`
- **Inputs:** effective annual rent, cap rate assumption (typically 0.04–0.08), market-adjusted value (anchor check).
- **Formula:** `income_supported_value = effective_annual_rent / cap_rate_assumption`. Anchor sanity check: if ratio to market_adjusted is <0.50 or >1.75, confidence ×0.35.
- **Used by:** BCV blend (8%); rental economics bridge.

#### Metric: Town Prior Value (BCV component)

- **Found in:** `briarwood/agents/current_value/agent.py:245-259`
- **Inputs:** town median ppsf, town median price (fallback), town median sqft + lot (for adjustment bounds), subject sqft + lot, town context confidence, local-doc count.
- **Formula:**
  ```python
  base_value = town_median_ppsf × sqft
  size_adjustment = clamp(1 + ((sqft / town_median_sqft - 1.0) × 0.10), 0.94, 1.06)
  lot_adjustment  = clamp(1 + ((lot_size / town_median_lot - 1.0) × 0.12), 0.94, 1.08)
  town_prior_value = base_value × size_adjustment × lot_adjustment
  ```
- **Confidence:** Local-doc bonus capped at +0.15 for 3+ docs; downweighted by comp count or comp confidence; floor 0.15.
- **Used by:** BCV blend (16%); fallback anchor when comps weak.

#### Metric: Bull Case Value

- **Found in:** `briarwood/modules/bull_base_bear.py:130-146`
- **Inputs:** BCV, market trailing 1-yr / 3-yr CAGR, town location score, risk penalty, scarcity score.
- **Formula:**
  ```python
  bull_drift     = max(t1, t3_cagr) if positive, capped at +0.15
  bull_location  = (town_score-50)/50 × 0.10 if score≥50, capped at +0.08
  bull_risk      = -risk_penalty × 0.50  (risk_bull_attenuation)
  bull_optionality = (scarcity_score / 100) × 0.08
  bull_value     = BCV × (1 + bull_drift + bull_location + bull_risk + bull_optionality)
  # then enforce bull >= base >= bear (line 141-146)
  ```
- **Range:** typically BCV × [1.00, 1.30].
- **Confidence:** see scenario-confidence formula below.

#### Metric: Base Case Value

- **Found in:** `briarwood/modules/bull_base_bear.py:130-146`
- **Inputs:** BCV, trailing 3-yr CAGR, town location, risk penalty, bull optionality (×0.25 attenuation).
- **Formula:**
  ```python
  base_drift     = clamp(trailing_3yr_cagr, -0.20, +0.15)
  base_location  = (town_score-50)/50 × 0.05  if score≥50,
                   else max((town_score-50)/50 × 0.075, -0.08)
  base_risk      = -risk_penalty × 0.70
  base_optionality = bull_optionality × 0.25
  base_value     = BCV × (1 + base_drift + base_location + base_risk + base_optionality)
  ```
- **Range:** typically BCV × [0.95, 1.15].

#### Metric: Bear Case Value

- **Found in:** `briarwood/modules/bull_base_bear.py:130-146`
- **Formula:**
  ```python
  bear_drift = (min(t1, t5) × 0.5) if t1 ≥ 0 else (t1 × 1.5)  # floored -0.20
  bear_location = 0 if town_score ≥ 50,
                  else max((town_score-50)/50 × 0.125, -0.08)
  bear_risk    = -risk_penalty × 1.0
  bear_value   = max(0.0, BCV × (1 + bear_drift + bear_location + bear_risk))
  ```
- **Range:** typically BCV × [0.75, 1.00].

#### Metric: Stress Case Value

- **Found in:** `briarwood/modules/bull_base_bear.py:148-159`
- **Formula:** flood-tier discount applied to BCV:
  ```python
  flood == "high"   → drawdown 0.35  (-35%)
  flood == "medium" → drawdown 0.30  (-30%)
  else              → drawdown 0.25  (-25%)
  stress_value = BCV × (1 - drawdown)
  ```
  Calibrated against 2007–2011 NJ coastal peak-to-trough (notes lines 211-215).
- **Confidence:** inherited from BCV; flagged as historical overlay, not forecast.

#### Metric: Scenario Spread

- **Found in:** `briarwood/modules/bull_base_bear.py:167`
- **Formula:** `spread = bull − bear`; `spread_pct = spread / price`.
- **Used by:** Confidence module (`scenario_fragility`); scoring contribution `min(spread_pct, 0.60) × 18 bps` (`bull_base_bear.py:191-197`).

#### Metric: Bull/Base/Bear Confidence (composite)

- **Found in:** `briarwood/modules/bull_base_bear.py:364-420`
- **Formula:**
  ```python
  conf = 0.70  # base
  if bcv_conf < 0.60:           conf -= 0.22
  if history_points < 12:       conf -= 0.25
  elif history_points < 24:     conf -= 0.12
  if town_conf < 0.70:          conf -= 0.08
  if risk_conf < 0.70:          conf -= 0.08
  if scarcity_conf < 0.60:      conf -= 0.05
  if scenario_reordered:        conf -= 0.08
  if (bcv_conf >= 0.85 and history_points >= 24
      and town_conf >= 0.75 and risk_conf >= 0.75
      and not reordered):       conf += 0.07
  conf = max(conf, 0.30)
  ```

#### Metric: Renovation Impact — gross_value_creation, net_value_creation, roi_pct

- **Found in:** `briarwood/modules/renovation_scenario.py:117-119`
- **Formula:**
  ```python
  gross_value_creation = renovated_bcv − current_bcv
  net_value_creation   = gross_value_creation − renovation_budget
  roi_pct              = (net_value_creation / renovation_budget) × 100  if budget > 0 else 0
  ```
- **Score:** `score = clamp(50 + roi_pct × 0.5, 0, 100)` (`renovation_scenario.py:192`).
- **Confidence:** `renovated_bcv` confidence; -0.15 penalty if renovated comp count < 5.

#### Metric: Margin Sensitivity grid (six scenarios)

- **Found in:** `briarwood/modules/margin_sensitivity_scoped.py:144-180`
- **Formula:** Six (`budget_mult, value_mult`) pairs:
  ```python
  ("Base case",                1.0, 1.0),
  ("Budget +20%",              1.2, 1.0),
  ("Budget +40%",              1.4, 1.0),
  ("Value -10%",               1.0, 0.9),
  ("Value -20%",               1.0, 0.8),
  ("Budget +20%, Value -10%",  1.2, 0.9),
  # for each: net = (gross × value_mult) − (budget × budget_mult) − hold_cost
  ```

#### Metric: Monthly Carry Cost / Cap Rate / DSCR

- **Found in:** `briarwood/modules/ownership_economics.py:73-98` (wrapped by `briarwood/modules/carry_cost.py`)
- **Formula:**
  ```python
  monthly_total_cost = monthly_taxes + monthly_insurance + monthly_hoa
                     + (purchase_price × maintenance_pct / 12)
                     + monthly_principal_interest
  monthly_cash_flow  = effective_monthly_rent − monthly_total_cost
  cap_rate           = annual_noi / purchase_price
  ```

#### Metric: Opportunity Cost benchmarks

- **Found in:** `briarwood/modules/opportunity_cost.py:120-145, 190-215`
- **Formula:**
  ```python
  property_terminal = entry_basis × (1 + property_cagr) ** hold_years
  tbill_terminal    = entry_basis × (1 + tbill_annual_return) ** hold_years
  sp500_terminal    = entry_basis × (1 + sp500_annual_return) ** hold_years
  excess_vs_tbill_bps = (property_cagr - tbill_annual_return) × 10_000
  excess_vs_sp500_bps = (property_cagr - sp500_annual_return) × 10_000
  ```
  Defaults: T-bill 4.5%, S&P 10%, hold 5 years. `entry_basis` priority: user → ask_price → BCV → fair_value_base.

#### Metric: Value Position (synthesizer assembly)

- **Found in:** `briarwood/synthesis/structured.py:235-273`
- **Outputs:**
  ```python
  value_position = {
      "fair_value_base":      briarwood_current_value,
      "ask_price":            listing_ask_price,
      "all_in_basis":         purchase_price + capex,
      "ask_premium_pct":      -(BCV − ask)/ask,
      "basis_premium_pct":    -(BCV − all_in_basis)/all_in_basis,
      "premium_discount_pct": basis_premium_pct,  # legacy alias
      "value_low":            BCV × (1 − band_pct),
      "value_high":           BCV × (1 + band_pct),
  }
  ```

#### Metric: Risk-Adjusted Fair Value

- **Found in:** `briarwood/interactions/valuation_x_risk.py:25-91`
- **Formula:**
  ```python
  DISCOUNT_PER_FLAG = 0.02; MAX_DISCOUNT = 0.15
  extra_discount = min(total_risk_penalty × DISCOUNT_PER_FLAG, MAX_DISCOUNT)
  if legal_conf < 0.5: extra_discount = min(MAX_DISCOUNT, extra_discount + 0.03)
  risk_adjusted_fair_value = fair_value × (1 − extra_discount)
  ```

---

### 3b. Signature metrics, risk, confidence, town, comp similarity

#### Metric: Price-to-Rent Ratio (P/R)

- **Found in:** `briarwood/agents/income/agent.py` (~lines 220-250)
- **Formula:** `price_to_rent = price / (12 × estimated_monthly_rent)`.
- **Bands (no benchmark):** < 15 strong value, 15–20 moderate, > 20 expensive.
- **Bands (with market benchmark):** ±10% of benchmark = fair; below = cheap; above = expensive.
- **Confidence:** rent-source-based; -0.06 if no benchmark; 7-factor formula in `agent.py:~410-440`.
- **Used by:** income_support, rent classification, decision narrative.

#### Metric: Scarcity Score / Scarcity Support

- **Found in:** `briarwood/agents/scarcity/scarcity_support.py:36-82`
- **Formula:**
  ```python
  scarcity_score          = 0.55 × location_scarcity + 0.45 × land_scarcity
  scarcity_support_score  = 0.60 × scarcity_score    + 0.40 × demand_consistency
  # confidence weighted: demand 50% / location 30% / land 20%
  ```
- **Bands:** confidence < 0.40 → "low-confidence"; score ≥ 75 + loc_conf ≥ 0.60 → "high"; ≥ 75 + loc_conf < 0.60 → "limited"; ≥ 60 + loc_conf ≥ 0.35 → "meaningful"; ≥ 60 + loc_conf < 0.35 → "limited"; ≥ 45 → "limited"; < 45 → "weak".

#### Metric: VALUE_FIND / OVERPRICED / SMALL_SAMPLE thresholds

- **Found in (editor):** `briarwood/editor/checks.py:14-20`:
  ```python
  VALUE_FIND_THRESHOLD_PCT  = -5.0
  OVERPRICED_THRESHOLD_PCT  = 5.0
  SMALL_SAMPLE_THRESHOLD    = 5
  ```
- **Found in (synthesizer):** `briarwood/claims/synthesis/verdict_with_comparison.py:39-43`:
  ```python
  SMALL_SAMPLE_THRESHOLD    = 5
  VALUE_FIND_THRESHOLD      = -5.0   # naming differs (no _PCT suffix)
  OVERPRICED_THRESHOLD      = 5.0
  ```
- **Currently in agreement** but no test guards equality. The editor file's own comment at line 18-20 names the hazard; ROADMAP.md 2026-04-24 already tracks it.
- **Drift risk:** see Drift §4.2.

#### Metric: Risk Score (RiskConstraintsModule)

- **Found in:** `briarwood/modules/risk_constraints.py:16-97`
- **Formula:** `score = clamp(85.0 - Σpenalties + Σcredits, 0, 100)`.
- **Sub-component penalties:**

  | Component | File line | Penalty |
  |---|---|---|
  | Flood high | 22-31 | -20 |
  | Flood medium | | -8 |
  | Flood low/none/minimal | | 0 (and +3 credit if low/none) |
  | Older home (age > 60) | 34-37 | -8 |
  | Tax (graduated 10K/12K/15K/20K/25K cap) | 39-46 | up to -20 |
  | Vacancy (graduated 5/8/12/20%) | 49-53 | up to -20 |
  | DOM (graduated 15/30/60/90 days) | 55-62 | up to -25; +2 credit if DOM < 15 |

- **Confidence:** data-completeness tier — 5 dims = 0.85, 3-4 = 0.72, ≤ 2 = 0.55.

#### Metric: Premium % (the de facto "Forward Value Gap" — see Drift §4.4)

- **Found in:** `briarwood/modules/risk_model.py:109-146`
- **Formula:** `premium_pct = (listed_price - briarwood_current_value) / briarwood_current_value`.
- **Bands:**
  - `premium_pct ≥ +0.15` → flag "overpriced_vs_briarwood_fair_value", confidence -0.05
  - `premium_pct ≤ -0.10` → flag "priced_below_briarwood_fair_value", confidence +0.05
  - middle band: no flag.

#### Metric: Legal Confidence

- **Found in:** `briarwood/modules/legal_confidence.py:13-122`
- **Formula:** `min(data_quality_conf, local_intelligence_conf)`, clamped:
  - if `has_zone_flags` → confidence ≥ 0.55
  - if **not** `has_accessory_signal` → confidence ≤ 0.65
- **Effect on risk:** `risk_model.py:50-51` — if `legal_confidence < 0.5` → `risk_confidence -= 0.08`.

#### Metric: Overall Confidence (7-signal aggregator)

- **Found in:** `briarwood/modules/confidence.py:148-181`
- **Formula:**
  ```python
  combined = (
        0.20 × anchor
      + 0.18 × evidence_anchor
      + 0.16 × completeness
      + 0.14 × comp_quality
      + 0.12 × model_agreement
      + 0.10 × legal_certainty
      + 0.10 × (1.0 - scenario_fragility)
  )
  combined -= contradiction_penalty + fragility_penalty + estimated_penalty
  # contradiction_penalty = min(count × 0.12, 0.45)
  # fragility_penalty     = max(0, scenario_fragility) × 0.12
  # estimated_penalty     = estimated_reliance × 0.15
  ```
- Component definitions:
  - **completeness** (`:184-193`): `(provided + 0.5×estimated + 0.25×defaulted) / total`; default 0.4 if total ≤ 0.
  - **estimated_reliance** (`:196-204`): `(estimated + defaulted) / total`; default 0.75. Triggers warning at ≥ 0.5.
  - **comp_quality** (`:236-242`): from valuation `comp_confidence_score`, default 0.55.
  - **model_agreement** (`:245-252`): `1.0 - stddev(prior_confidences)/0.35`; 0.6 if ≤ 1 module.
  - **scenario_fragility** (`:255-264`): from `bull_bear_spread_pct`, default 0.35.
  - **legal_certainty** (`:267-272`): from legal_confidence, default 0.7.
  - **contradiction_count** (`:207-233`): increments for ppsf > $1500 OR < $75; beds ≥ 5 with baths ≤ 1.5; gross_yield < 0.02.

#### Metric: Comp Similarity Score (unified pipeline)

- **Found in:** `briarwood/modules/comp_scoring.py:221-271`
- **Formula:**
  ```python
  weighted = proximity × 0.30 + recency × 0.25 + similarity × 0.30 + data_quality × 0.15
  ```
- **Proximity bands** (`:54-69`): ≤ 0.25 mi → 0.95; ≤ 0.5 → 0.88; ≤ 1.0 → 0.78; ≤ 2.0 → 0.64; > 2.0 → 0.42; missing → 0.55.
- **Recency SOLD** (`:77-93`): ≤ 90 d → 0.95; ≤ 180 → 0.88; ≤ 365 → 0.78; ≤ 730 → 0.62; > 730 → 0.40; missing → 0.50.
- **Recency ACTIVE** (`:96-123`): ≤ 14 d → 0.92; ≤ 30 → 0.85; ≤ 60 → 0.75; ≤ 90 → 0.62; ≤ 180 → 0.45; > 180 → 0.30; missing → 0.55.
- **Data quality** (`:168-196`): if > half fields missing → 0.30; else `present/total`, plus verification bonuses (public_record/MLS verified +0.08, Zillow +0.05) and penalties (questioned/unverified -0.10), clamped [0.20, 1.0].

#### Metric: Composite Comp-Stack Confidence (4 layers)

- **Found in:** `briarwood/comp_confidence_engine.py:134-574`
- **Layers:**
  1. **Base shell** (`:202-273`) — comp count + support quality + tier distribution + median similarity + price agreement (CV).
  2. **Feature adjustments** (`:280-357`) — weighted_confidence (40%) + evidence distribution (35%) + unvalued penalty (25%) − overlap penalty (max 0.15).
  3. **Location adjustments** (`:364-441`) — same structure as features layer.
  4. **Town transfer** (`:448-506`) — town_similarity (35%) + transferred_confidence (45%) + warnings (20%).
- **Composite** (`:513-574`): dollar-weighted with `base_shell_min_weight = 0.45`, `materiality_threshold = 0.10`, capped at `2.0 × weakest_material_layer`.
- **Label** (`:782-787`): ≥ 0.75 "High"; ≥ 0.55 "Medium"; else "Low".

#### Metric: Town Development Velocity

- **Found in:** `briarwood/modules/town_development_index.py:93-189`
- **Formula:**
  ```python
  approval_rate         = approval_w / (approval_w + denial_w)
  activity_volume       = activity_w / effective_months
  substantive_changes   = substantive_w / effective_months
  restrictive_signals   = restrictive_w / effective_months
  contention            = contention_w / total_time_w
  development_velocity  = (
        0.40 × approval_rate
      + 0.25 × min(activity_volume / target_volume, 1.0)
      + 0.15 × min(substantive_changes, 1.0)
      + 0.10 × max(1.0 - min(restrictive_signals × 2.0, 1.0), 0.0)
      + 0.10 × max(1.0 - contention, 0.0)
  )
  # time decay: each month weighted by exp(-months_ago / half_life), default half_life=6
  ```
- **Nudge** (`:286-332`): `(velocity - 0.5) × 2 × max_nudge` (default max_nudge = 0.04, so ±4%).

#### Metric: Location Intelligence Score

- **Found in:** `briarwood/modules/location_intelligence.py:62-240`
- **Formula:**
  ```python
  scarcity_score = weighted([
      (proximity, 0.40),
      (supply,    0.35),
      (rarity,    0.25),
  ])
  location_score = weighted([
      (proximity,        0.35),
      (scarcity_score,   0.25),
      (lifestyle,        0.20),
      (risk_component,   0.20),
  ])
  ```
- Confidence ranges from ~0.30 (sparse geo) to ~0.95 (full geo + landmark + zone).

#### Metric: Liquidity Score (rental-side)

- **Found in:** `briarwood/agents/rental_ease/agent.py:~145-180`
- **Formula:**
  ```python
  score = (prior_liquidity * 100) or 50.0
  if liquidity_view available: score = 0.65 × score + 0.35 × liquidity_view_score
  if DOM ≤ 14: score += 10
  elif DOM ≤ 30: score += 4
  elif DOM > 90: score -= 14
  elif DOM > 60: score -= 8
  if zillow_renter_demand_index: score = 0.75 × score + 0.25 × demand_index
  if premium_fragility: score -= premium_fragility × 8
  score = clamp(score, 0, 100)
  ```
- **Bands:** ≥ 80 "Very Liquid"; < 55 "Illiquid"; else "Liquid".

#### Metric: Strategy Classifier (rule-based)

- **Found in:** `briarwood/modules/strategy_classifier.py:67-185`
- **Output:** one of `OWNER_OCC_SFH`, `OWNER_OCC_DUPLEX`, `OWNER_OCC_WITH_ADU`, `PURE_RENTAL`, `VALUE_ADD_SFH`, `REDEVELOPMENT_PLAY`, `SCARCITY_HOLD` (placeholder, always False), `UNKNOWN`.
- **Trigger examples:**
  - Redevelopment: `lot_size ≥ 0.5 acres + sqft < 1200 + price ≥ $800K` OR `capex_lane in {redevelop, teardown}`.
  - Value-add: `condition in {needs_work, fixer}` OR `capex_lane in {major_renovation, gut}`.

#### Metric: Income Agent Confidence

- **Found in:** `briarwood/agents/income/agent.py:~410-440`
- **Formula:**
  ```python
  base = {"manual_input": 0.88, "provided": 0.82, "estimated": 0.52, "missing": 0.18}[rent_source]
  if not taxes_present:       conf -= 0.14
  if not insurance_present:   conf -= 0.18
  if not benchmark_present:   conf -= 0.06
  if not vacancy_present:     conf -= 0.05
  if not maintenance_present: conf -= 0.05
  if not financing_complete:  conf -= 0.24
  if rent_source == "missing":   conf = min(conf, 0.45)
  if rent_source == "estimated": conf = min(conf, 0.68)
  override "high" → conf += 0.10
  override "low"  → conf = max(conf - 0.15, 0.10)
  ```

#### Metric: Income Support Ratio

- **Found in:** `briarwood/agents/income/agent.py:~180-210`
- **Formula:** `ratio = effective_monthly_rent / total_monthly_cost`.
- **Bands** → score:
  - ≥ 1.40 → 100
  - 1.10–1.40 → interpolate 78→100
  - 0.90–1.10 → 55→78
  - 0.70–0.90 → 30→55
  - 0.50–0.70 → 12→30
  - < 0.50 → 0→12

#### Metric: Trust Floors (synthesis stance gates)

- **Found in:** `briarwood/synthesis/structured.py:27-28`
  ```python
  TRUST_FLOOR_STRONG = 0.70
  TRUST_FLOOR_ANY    = 0.40
  ```
- **Effect:** confidence ≥ 0.70 unlocks "strong_buy"; confidence < 0.40 collapses stance to CONDITIONAL.

---

## Step 4 — Drift Report

Drift items, ranked by severity. Severity rubric:

- **Critical** — formulas disagree → different numbers
- **High** — thresholds disagree → different verdicts on same property
- **Medium** — units, naming, or confidence handling disagree
- **Low** — cosmetic (variable naming, comment)

### 4.1 — CRITICAL: pricing-view bands disagree with verdict-label thresholds

Two code paths classify the same human concept ("is this property
under-, fair-, or over-priced?") with **different** thresholds.

| Path A — synthesizer prose | Path B — claim verdict label |
|---|---|
| `briarwood/agents/current_value/agent.py:444-451` | `briarwood/editor/checks.py:14-15` and `briarwood/claims/synthesis/verdict_with_comparison.py:42-43,150-156` |
| Input: `mispricing_pct = (BCV − ask) / ask` | Input: `delta_pct = (ask − fmv) / fmv × 100` |
| `≥ +8%`  → "appears undervalued" | `≤ -5%`  → "value_find" |
| `-3%…+8%` → "appears fairly priced" | `-5%…+5%` → "fair" |
| `-10%…-3%` → "appears fully valued" | `≥ +5%`  → "overpriced" |
| `< -10%` → "appears overpriced" | |

The two paths use opposite sign conventions. Translating to a common
sign (BCV vs ask premium):

| BCV ÷ ask | Path A (prose) | Path B (claim) |
|---|---|---|
| 1.10 | undervalued | value_find |
| 1.06 | **fairly priced** | **value_find** ← drift |
| 1.04 | fairly priced | fair |
| 0.98 | fairly priced | fair |
| 0.96 | fully valued | **overpriced** ← drift |
| 0.92 | fully valued | overpriced |
| 0.85 | overpriced | overpriced |

Worked example: BCV $1.06M, ask $1.0M → prose says *"appears fairly
priced"*; the verdict claim says *"value_find"*. Same property, two
verdicts.

**Why it matters.** A user reading the chat-tier prose ("fairly
priced") and the structured claim badge ("value_find") sees a direct
contradiction inside one analysis. This is the highest-leverage drift
in the codebase.

**Remediation belongs in Phase 2.** Centralize the verdict labels at
one site (likely a new `briarwood/decision_model/pricing_view.py`),
have both `_pricing_view` in current_value and the editor /
verdict_with_comparison thresholds import the same constants and label
strings, and add a test asserting that for a sweep of BCV/ask ratios
the two paths return the same logical band.

### 4.2 — MEDIUM: editor↔synthesis threshold pair currently in sync but unguarded

Already tracked in `ROADMAP.md` 2026-04-24 ("Editor / synthesis
threshold duplication has no mechanical guard").

| Constant | `editor/checks.py` | `claims/synthesis/verdict_with_comparison.py` |
|---|---|---|
| Value-find threshold | `:14` `VALUE_FIND_THRESHOLD_PCT = -5.0` | `:42` `VALUE_FIND_THRESHOLD = -5.0` |
| Overpriced threshold | `:15` `OVERPRICED_THRESHOLD_PCT = 5.0` | `:43` `OVERPRICED_THRESHOLD = 5.0` |
| Small-sample threshold | `:20` `SMALL_SAMPLE_THRESHOLD = 5` | `:39` `SMALL_SAMPLE_THRESHOLD = 5` |

Currently agree. Naming differs (`_PCT` suffix on editor side only).
The editor's own comment at line 18-20 is the only guard. The fix
proposed in ROADMAP.md (move to a neutral `briarwood/claims/thresholds.py`
+ equality test) still stands.

### 4.3 — HIGH: BCV component count drift in the audit prompt / docs

The audit prompt (and likely older internal docs / prompts that
predate the income + town-prior split) speaks of "BCV's 4 components."
Code at `briarwood/agents/current_value/agent.py:18-24` blends **5**:
`comparable_sales 0.40 + market_adjusted 0.24 + town_prior 0.16 +
backdated_listing 0.12 + income 0.08 = 1.00`.

Anywhere a downstream prompt or README still references "the four
anchors" of BCV, that prose is wrong. Worth a one-line grep sweep
during Phase 2 for `"four anchor"`, `"4 anchor"`, `"four component"`.

### 4.4 — HIGH: orphan signature metrics — Forward Value Gap, Optionality Score

The audit prompt names two signature metrics that **no module
computes as a scalar**:

- **Forward Value Gap (FVG).** Closest implementation:
  `risk_model.py:109-146` computes `premium_pct = (listed_price − BCV) /
  BCV` and emits a binary flag at ±10/+15. There is no continuous gap
  number. If a prompt mentions "Forward Value Gap" or "FVG" by name, it
  is making a claim the code can't back up.

- **Optionality Score.** There is no scalar `optionality_score` in any
  module. What exists:
  - `OptionalitySignal` Pydantic carrier in
    `routing_schema.py:356` with a `primary_source` field plus a list of
    `HiddenUpsideItem`.
  - `value_scout/scout.py` produces qualitative `HiddenUpsideItem`
    records with `kind / source_module / label / magnitude / rationale`.
  - Bull/Base/Bear consumes a derived `bull_optionality = scarcity_score
    / 100 × 0.08` (a dollar-impact factor, not a score).

Any prompt or doc that references "Optionality Score: 72" is
inventing the number. **Search prompts for these literal phrases as
part of Phase 2.**

### 4.5 — MEDIUM: confidence floors are unanchored in prompts

`briarwood/synthesis/structured.py:27-28` defines hard gates
(`TRUST_FLOOR_STRONG = 0.70`, `TRUST_FLOOR_ANY = 0.40`). The
LLM-facing prompts (`llm_prompts.py:107-110`,
`api/prompts/decision_summary.md`, etc.) describe the same trust
calibration in qualitative prose ("lower confidence when modules
conflict"). The LLM has no way to know that 0.70 is a stance gate. It
can produce stance="strong_buy" at confidence 0.55 — code will then
silently downgrade it to CONDITIONAL.

Either (a) expose the thresholds to the prompt
("strong_buy unlocks at confidence ≥ 0.70"), or (b) compute the stance
deterministically before composition and tell the LLM the stance
rather than asking it to choose.

### 4.6 — MEDIUM: comp scoring weight set duplication risk

`briarwood/modules/comp_scoring.py:221-271` weights are
`proximity 0.30, recency 0.25, similarity 0.30, data_quality 0.15`.
`briarwood/comp_confidence_engine.py:202-273` (Layer 1 base shell)
weights are `comp_count 0.25, support_quality 0.25, tier_distribution
0.20, median_similarity 0.15, price_agreement 0.15`.

These are scoring different things at different layers (single-comp
score vs. comp-stack base-shell layer), so they are not duplicates per
se, but a future refactor could conflate them. Worth a comment at both
sites tying each to its conceptual layer.

### 4.7 — MEDIUM: rent-source split (3 sources, no merge guard)

Three rent values can disagree silently:

- `IncomeAgentOutput.monthly_rent_estimate` (`agents/income/schemas.py:35`)
- `RentContextOutput.market_rent_estimate` (`agents/rent_context/schemas.py:19`)
- `ValuationOutput.effective_monthly_rent` (`schemas.py:462`)

The "selection" of which value flows into cash-flow lives implicitly
in the valuation module. No structured carrier of *"these three
disagree by X%"* exists, so no prompt can call attention to the
divergence.

### 4.8 — MEDIUM: numeric grounding rule in synthesizer is informal

`briarwood/synthesis/llm_synthesizer.py:64-165` instructs the LLM
"every dollar amount, percentage, multiplier, year, or count you cite
must round to a value present in the `unified` JSON." There is no
specified rounding rule (1k? 5k? nearest whole percent?). The verifier
catches *completely* ungrounded numbers but not "$820k" rendered as
"$800k" (the actual value is $820,000). Risk: model rounds toward
psychologically friendly numbers and the verifier accepts.

### 4.9 — LOW: naming — `valuation` vs `current_value` modules

`briarwood/modules/valuation.py` is a thin wrapper around
`briarwood/agents/current_value/agent.py` that adds an HPI macro
nudge. Two modules with different names producing the same primary
field (`briarwood_current_value`) makes search-and-replace
treacherous.

### 4.10 — LOW: legacy `decision_model/scoring.py`

Per its own header comment, `briarwood/decision_model/scoring.py` is
"largely deprecated" but still imported in places. The
`estimate_comp_renovation_premium()` function at
`decision_model/scoring.py:51` is consumed by the renovation_impact
module. If it remains in service, mark it as live; if not, delete.

---

## Step 5 — Prompt and narrative audit

> 23 distinct LLM-facing prompts catalogued. Per-prompt details below;
> hallucination-risk callouts at the end.

### Prompts indexed by location

| Prompt | Location | Purpose |
|---|---|---|
| Intent parser | `briarwood/llm_prompts.py:13-58` | Classify intent, depth, focus, occupancy |
| Synthesis (analytical) | `briarwood/llm_prompts.py:61-142` | Recommend buy/mixed/pass + decision statement |
| Prose synthesizer (newspaper) | `briarwood/synthesis/llm_synthesizer.py:64-165` | Convert unified output → 3-7 sentence prose |
| Prose synthesizer (plain fallback) | `briarwood/synthesis/llm_synthesizer.py:172-209` | Same, no-markdown fallback |
| Decision critic | `briarwood/agent/composer.py:219-239` | Catch softened-bearish stance + ungrounded claims |
| Router (chat-tier intent) | `briarwood/agent/router.py:169-226` | Classify AnswerType |
| Representation agent | `briarwood/representation/agent.py:122-157` | Pick claims + supporting charts |
| Shadow planner | `briarwood/shadow_intelligence.py:79-85` | Telemetry: propose tools |
| Shadow evaluator | `briarwood/shadow_intelligence.py:87-92` | Telemetry: judge intent satisfaction |
| Local-intelligence extractor | `briarwood/local_intelligence/prompts.py:6-25` | Extract town signals from documents |
| Buyer-lens minutes | `briarwood/local_intelligence/minutes_sources.py:376` | Parse minutes documents through buyer lens |
| Decision summary tier | `api/prompts/decision_summary.md` (+ `_base.md`) | Full underwriting read |
| Decision-value tier | `api/prompts/decision_value.md` | Property value question |
| Risk tier | `api/prompts/risk.md` | Downside briefing |
| Edge tier | `api/prompts/edge.md` | Value thesis |
| Strategy tier | `api/prompts/strategy.md` | Best path |
| Projection tier | `api/prompts/projection.md` | Forward scenarios |
| Research tier | `api/prompts/research.md` | Town intelligence |
| Lookup tier | `api/prompts/lookup.md` | Factual lookup |
| Rent-lookup tier | `api/prompts/rent_lookup.md` | Rental factual |
| Browse-surface tier | `api/prompts/browse_surface.md` | First-impression brief |
| Claim VWC tier | `api/prompts/claim_verdict_with_comparison.md` | Investor-persona verdict prose |
| Section-followup tier | `api/prompts/section_followup.md` | Section-level follow-up |
| Visual advisor | `api/prompts/visual_advisor.md` | UI layout / chart selection |
| Verdict headline templates | `briarwood/claims/synthesis/templates.py:9-14` | Deterministic f-strings (not an LLM prompt) |

### Hallucination-risk callouts

**HIGH — `briarwood/synthesis/llm_synthesizer.py:64-165`.** The
"every number must round to a value present in `unified`" rule is
informal. No precision constant in code. Verifier flags only
*completely* ungrounded numbers. Risk: rounding drift accepted as
grounded. (See Drift §4.8.)

**HIGH — `briarwood/llm_prompts.py:61-142` synthesis prompt.** The
prompt names "trust calibration rules" qualitatively but never
references the `TRUST_FLOOR_STRONG=0.70` / `TRUST_FLOOR_ANY=0.40`
constants in `synthesis/structured.py`. Model may produce
stance="strong_buy" at conf 0.55 → silently downgraded. (See Drift
§4.5.)

**HIGH — `api/prompts/claim_verdict_with_comparison.md`.** Prompt
echoes `verdict.headline` written by the deterministic template. No
instruction on whether a particular delta_pct value warrants
"value_find" vs "fair" — the LLM is told only "do not soften or
strengthen." Without the threshold visible to the prompt, "soften"
has no anchor.

**HIGH — `briarwood/agent/router.py:169-226`.** The router prompt
itemizes phrase mappings ("'what do you think of X' → browse"). Code
has parallel regex cache rules. No mechanism prevents the two from
diverging. The known bug `project_resolver_match_bug` (in user memory)
suggests the routing layer is already a source of incidents.

**HIGH — `api/prompts/decision_summary.md`.** Prompt requires
`[[MODULE:field:value]]` grounding markers but no code validates that
`field` is a real field on the cited module. Numeric verifier only
validates the value. Risk: invented field names that ground to a real
number.

**MEDIUM — `briarwood/synthesis/llm_synthesizer.py` regen path.**
On verifier failure the regen prompt tells the LLM "rewrite the
draft, full freedom to reframe." A regen attempt can introduce *new*
unbacked numbers that the second-pass verifier might miss.

**MEDIUM — `briarwood/agent/composer.py:219-239` decision critic.**
The criterion "ask_premium_pct is materially positive" has no
numeric anchor. Whether 1% or 5% is "material" is left to the model.

**MEDIUM — `api/prompts/decision_summary.md` and tier prompts.** All
say "do not invent" but provide no formal whitelist of allowed
risks/edges. Inventing a semantically reasonable but unsupported risk
can pass verification.

**MEDIUM — `briarwood/representation/agent.py:122-157`.** Hard cap
"Pick 2-3 charts, one per claim_type." When intent maps to 5 claim
types, the model silently drops two. The prompt does not explain how
to choose.

**LOW — `briarwood/agent/composer.py` strict-regen flag.**
`STRICT_REGEN_THRESHOLD = 2` plus environment override
`BRIARWOOD_STRICT_REGEN`. Prompt is unaware. A runtime flip disables
the guardrail invisibly.

**LOW — `briarwood/local_intelligence/prompts.py:6-25`.** Says "weak,
ambiguous, or blog-style mentions should produce lower confidence"
without defining "weak" or "ambiguous." Confidence varies run-to-run.

### Orphan and threshold cross-references inside prompts

- **No prompt references** `VALUE_FIND_THRESHOLD_PCT`,
  `OVERPRICED_THRESHOLD_PCT`, `SMALL_SAMPLE_THRESHOLD`, `TRUST_FLOOR_STRONG`,
  or `TRUST_FLOOR_ANY` by value. Prompts speak of "fair" / "strong" /
  "small sample" qualitatively only.
- **No prompt references** "Forward Value Gap" or "Optionality Score"
  explicitly *in code* — but if an older external doc still uses those
  phrases when prompting a model, the model will fabricate.

---

## Step 6 — Gap Analysis

### Orphan metrics (referenced as concepts but not formally computed)

- **Forward Value Gap.** Closest existing computation is `premium_pct`
  in `risk_model.py:109-146` (binary flag at ±10/+15, not a continuous
  gap). Prompts may name it; no code produces it.
- **Optionality Score.** `OptionalitySignal` is a *carrier*, not a
  score. `HiddenUpsideItem.magnitude` is qualitative. No
  `optionality_score` field exists on any module output.
- **Absorption rate.** Implied by DOM banding and `LiquiditySignalOutput`,
  but no field named `absorption_rate` exists.

### Dead metrics (computed but never consumed)

Worth a Phase 2 sweep. Candidates spotted:

- `briarwood/decision_model/scoring.py:51`
  `estimate_comp_renovation_premium()` — only called by
  `renovation_impact`; the rest of the file appears legacy.
- `MarketLocationSignals.coastal_profile_signal` (`schemas.py`) — set
  by some loaders, not seen consumed downstream.
- `LocalIntelligenceOutput.signals[]` — appended to but no obvious
  reader.
- The "shadow" plan + intent satisfaction outputs from
  `shadow_intelligence.py` are explicitly telemetry-only.

(This list needs verification; mark as "candidate orphans" in Phase 2.)

### Confidence gaps (metrics that drive verdicts but have no confidence)

- **`pricing_view`** (`current_value/agent.py:444`) — categorical
  output, no confidence attached. The user reads "appears overpriced"
  with no signal of how sure the engine is.
- **`scenario spread / spread_pct`** — used as a denominator for
  scenario_fragility but has no confidence band of its own.
- **`opportunity_cost.excess_vs_*` figures** — compound-growth
  projections over 5 years. Confidence is set to `min(valuation, resale)`
  (`opportunity_cost.py:255`) but no propagation of S&P/T-bill
  uncertainty.
- **Strategy classifier** — confidence field exists but most paths
  return 0.0–0.85 with weak documentation of what each level means.

### Interpretation gaps (values without thresholds)

- **`location_score`** — 0–100 score with no published low/medium/high
  bands.
- **`scarcity_score`** standalone — has support-tier labels at
  `scarcity_support` level but the underlying location/land scarcity
  components have no bands.
- **Most BCV components individually** — only the aggregate
  `pricing_view` has bands; the individual components (`market_adjusted`,
  `town_prior`, etc.) have no "this anchor disagrees with the others
  by X%" surfacing.
- **Cap rate, DSCR, gross_yield** — computed in
  `ownership_economics.py` with no good/bad bands. The synthesizer
  prompt is left to apply its own intuition.

### Intent gaps (metrics not tagged to any user intent)

- **Stress case value.** Computed and surfaced in some prose but no
  intent in the router seems to specifically demand it (no
  `STRESS` `CoreQuestion`).
- **Town development index.** Surfaces only as a confidence nudge
  (±0.04). User cannot ask for it directly via any answer_type.
- **Comp confidence layer breakdown** (`comp_confidence_engine.py`'s
  4 layers) — produced but the chat-tier router has no intent that
  surfaces them.

### Provenance gaps (inputs lacking source/pulled_at/verification metadata)

- **Cap rate assumption** in `current_value/agent.py:123` — 0.04–0.08
  default range, no record of "where did 0.045 come from for this run."
- **Risk weight constants** in `risk_constraints.py` (the -20/-12/-8
  flood penalties, 85.0 base, etc.) — no provenance/source comment.
- **`bull_drift = max(t1, t3_cagr)` capped at +0.15** — the +0.15
  cap is an editorial choice with no calibration comment.
- **Stress drawdowns 25/30/35%** — calibration note at
  `bull_base_bear.py:211-215` cites "2007–2011 NJ coastal" but the
  three numbers themselves are uncited.

### Layer-4 (LLM judgment) constraints not anchored to Layer-3 (computed metrics)

- "Trust calibration" prose in `llm_prompts.py:107-110` (no numeric
  thresholds).
- "Materially positive" in `composer.py:219-239` (no numeric anchor).
- "Lead with the biggest thing that could go wrong" in
  `api/prompts/risk.md` (no ranking algorithm in code).

---

## Step 7 — Draft canonical metrics registry

> First draft. Each metric has the same fields (some marked TODO /
> MISSING). Where multiple implementations exist, the canonical entry
> picks the one most recently edited and cites the alternative for
> human review.

### `briarwood_current_value`
- **Canonical computation:** `briarwood/agents/current_value/agent.py:18-189`
- **Wrapper:** `briarwood/modules/current_value.py:44-249` (caps), `briarwood/modules/valuation.py:15-57` (HPI nudge)
- **Inputs:** see Step 3a
- **Formula:** five-component confidence-weighted blend (weights 0.40 / 0.24 / 0.16 / 0.12 / 0.08)
- **Units:** USD
- **Bands:** the `pricing_view` translation in `agent.py:444-451` (TODO: reconcile with editor thresholds — Drift §4.1)
- **Confidence:** weighted avg + input-quality caps
- **Used by:** scenarios, ARV, opportunity cost, synthesis
- **Intent tags:** DECISION / VALUATION / BROWSE

### `comparable_sales_value`
- **Canonical:** `briarwood/agents/current_value/agent.py:31-36` (component); `briarwood/modules/comparable_sales.py` (calculation)
- **Bands:** comp-count weighting at `agent.py:283-289`
- **Confidence:** from `comparable_sales` module
- **Intent tags:** VALUATION / PRICING / BROWSE

### `market_adjusted_value`
- **Canonical:** `briarwood/agents/current_value/agent.py:48-91`
- **Confidence:** scales with history points + property detail count
- **Intent tags:** VALUATION / MARKET / BROWSE

### `backdated_listing_value`
- **Canonical:** `briarwood/agents/current_value/agent.py:93-118`
- **Intent tags:** VALUATION / HISTORICAL_PRICING

### `income_supported_value`
- **Canonical:** `briarwood/agents/current_value/agent.py:120-138`
- **Intent tags:** VALUATION / RENTAL_OPTION

### `town_prior_value`
- **Canonical:** `briarwood/agents/current_value/agent.py:245-259`
- **Intent tags:** VALUATION / LOCATION_PRIOR / BROWSE

### `bull_case_value` / `base_case_value` / `bear_case_value`
- **Canonical:** `briarwood/modules/bull_base_bear.py:130-146`
- **Bands:** TODO — what does "spread > 30%" mean for the user?
- **Confidence:** multi-factor formula at `bull_base_bear.py:364-420`
- **Intent tags:** SCENARIO / PROJECTION

### `stress_case_value`
- **Canonical:** `briarwood/modules/bull_base_bear.py:148-159`
- **Bands:** flood-tier triple (25/30/35%)
- **Confidence:** inherited from BCV; flagged historical overlay
- **Intent tags:** SCENARIO / STRESS / RISK

### `gross_value_creation` / `net_value_creation` / `roi_pct`
- **Canonical:** `briarwood/modules/renovation_scenario.py:117-119`
- **Bands:** roi_pct < 0 unfavorable narrative
- **Intent tags:** RENOVATION / VALUATION

### `monthly_total_cost` / `monthly_cash_flow` / `cap_rate` / `gross_yield` / `dscr`
- **Canonical:** `briarwood/modules/ownership_economics.py:73-98`
- **Bands:** MISSING (no "good cap rate" band)
- **Intent tags:** ECONOMICS / CARRY / HOLD

### `excess_vs_tbill_bps` / `excess_vs_sp500_bps`
- **Canonical:** `briarwood/modules/opportunity_cost.py:120-145`
- **Defaults:** T-bill 4.5%, S&P 10%, hold 5y
- **Intent tags:** DECISION / PROJECTION / BENCHMARK

### `value_position` (synthesis-assembled)
- **Canonical:** `briarwood/synthesis/structured.py:235-273`
- **Fields:** `fair_value_base, ask_price, all_in_basis, ask_premium_pct, basis_premium_pct, value_low, value_high`
- **Bands:** none on this assembly itself; flows into TRUST_FLOOR gate
- **Intent tags:** DECISION / VALUATION

### `risk_adjusted_fair_value`
- **Canonical:** `briarwood/interactions/valuation_x_risk.py:25-91`
- **Constants:** 0.02 per-flag, 0.15 max, +0.03 if legal_conf < 0.5
- **Intent tags:** DECISION / RISK / VALUATION

### `pricing_view`
- **Canonical (NEEDS RECONCILIATION):** `briarwood/agents/current_value/agent.py:444-451`
- **Alternative:** `editor/checks.py:14-15` + `claims/synthesis/verdict_with_comparison.py:42-43`
- **Bands:** disagree — see Drift §4.1
- **TODO:** centralize in a new `briarwood/decision_model/pricing_view.py`

### `price_to_rent`
- **Canonical:** `briarwood/agents/income/agent.py` (~lines 220-250)
- **Bands:** as documented; benchmark-relative if available
- **Intent tags:** DECISION / PROJECTION / STRATEGY

### `scarcity_score` / `scarcity_support_score`
- **Canonical:** `briarwood/agents/scarcity/scarcity_support.py:36-82`
- **Bands:** confidence-modulated tiers
- **Intent tags:** DECISION / EDGE / STRATEGY

### `liquidity_score`
- **Canonical:** `briarwood/agents/rental_ease/agent.py:~145-180`
- **Bands:** ≥ 80 / < 55
- **Intent tags:** STRATEGY / PROJECTION

### `forward_value_gap`
- **Canonical:** **MISSING** — no module computes it. Closest:
  `risk_model.py:109-146` `premium_pct` (binary flag).
- **Phase 2 decision needed:** define formally OR remove from
  product vocabulary.

### `optionality_score`
- **Canonical:** **MISSING** — `OptionalitySignal` is a carrier;
  `value_scout/scout.py` produces qualitative records.
- **Phase 2 decision needed:** scalar-ize OR remove from product
  vocabulary.

### `risk_score`
- **Canonical:** `briarwood/modules/risk_constraints.py:16-97`
- **Wrapper:** `briarwood/modules/risk_model.py`
- **Sub-components:** flood, age, tax, vacancy, DOM (all in `risk_constraints.py`)
- **Bands:** 0–100 raw; no "low/med/high" labels in module
- **Intent tags:** RISK / DECISION

### `legal_confidence`
- **Canonical:** `briarwood/modules/legal_confidence.py:13-122`
- **Bands:** clamps [0.55, 0.65] under specific signal combos
- **Effect:** dampens risk_confidence -0.08 when < 0.5

### `confidence (overall)`
- **Canonical:** `briarwood/modules/confidence.py:148-181`
- **Formula:** 7-signal weighted blend with three penalties
- **Bands:** TRUST_FLOOR_STRONG=0.70 / TRUST_FLOOR_ANY=0.40 in synthesis (TODO: surface in prompts)

### `comp_score`
- **Canonical:** `briarwood/modules/comp_scoring.py:221-271`
- **Weights:** proximity 0.30 / recency 0.25 / similarity 0.30 / data_quality 0.15

### `composite_comp_confidence`
- **Canonical:** `briarwood/comp_confidence_engine.py:513-574`
- **Layers:** 4 (base shell / features / location / town transfer)
- **Cap:** 2.0 × weakest_material_layer; base_shell_min_weight 0.45
- **Label:** ≥ 0.75 High / ≥ 0.55 Medium / else Low

### `development_velocity`
- **Canonical:** `briarwood/modules/town_development_index.py:93-189`
- **Nudge:** ±0.04 confidence (`:286-332`)

### `location_score` / `scarcity_score` (location module)
- **Canonical:** `briarwood/modules/location_intelligence.py:62-240`
- **Note:** the `scarcity_score` here is structurally different from
  `agents/scarcity/scarcity_support.py`'s scarcity_score — different
  inputs, different weights. Worth a naming reconciliation.

### `strategy_label` / `strategy_confidence`
- **Canonical:** `briarwood/modules/strategy_classifier.py:67-185`

---

## Step 8 — Recommendations

### The 3 most dangerous drift issues

1. **Pricing-view ↔ verdict-label drift (Drift §4.1).** Same property
   gets contradictory verdicts in prose and claim. Highest user-visible
   impact. Fix by centralizing a single pricing-view module that both
   `_pricing_view` in `current_value/agent.py` and the editor /
   verdict_with_comparison thresholds import. Add a sweep test.

2. **Confidence floors invisible to LLM (Drift §4.5).** Synthesis
   gates on 0.70 / 0.40 but the prompt only describes them in vague
   prose. Either expose the constants or compute the stance
   deterministically and tell the LLM the answer.

3. **Editor↔synthesis threshold pair unguarded (Drift §4.2).**
   Currently in sync, but one renamed import away from silent drift.
   The fix in ROADMAP.md (move to neutral module + equality test) is
   well-scoped — execute it.

### The 3 highest-leverage extractions

1. **A single `briarwood/decision_model/value_position.py`** holding
   `pricing_view` bands, `VALUE_FIND_THRESHOLD`, `OVERPRICED_THRESHOLD`,
   `TRUST_FLOOR_STRONG`, `TRUST_FLOOR_ANY`, and a small set of helper
   functions to translate `(BCV, ask)` → label. Replaces three drift
   sites at once and gives prompts a single import to reference.

2. **A `briarwood/decision_model/risk_thresholds.py` module** for the
   per-component penalties currently inlined in `risk_constraints.py`
   (the -20 flood, -8 age, etc.) and the `premium_pct` ±10/+15 flags.
   Lets the test suite + the prompts both reference one source of truth
   and makes calibration changes a one-PR event.

3. **A `briarwood/scoring_constants.py`** for the comp-scoring weights
   (0.30/0.25/0.30/0.15) and the comp-confidence layer weights
   (0.45 base-shell-min, 0.10 materiality, 2.0× weakest cap). Stops
   drift between `modules/comp_scoring.py` and
   `comp_confidence_engine.py` from being possible.

### Metrics that need redesign, not just extraction

- **Forward Value Gap.** Currently a name in search of a metric. Either
  define a continuous gap (e.g., `forward_value_gap = (base_case_value
  − BCV) / BCV` with calibrated bands) or remove from the product
  vocabulary.

- **Optionality Score.** Currently a list of qualitative items. Either
  define a scalar aggregator over `HiddenUpsideItem.magnitude` (with
  bands) or remove from the product vocabulary and lean on the
  qualitative list as the surface.

- **Rent selection across three sources.** No carrier surfaces "these
  three estimates disagree by X%." A small `RentReconciliation`
  dataclass that holds all three sources + the selected value + the
  divergence flag would pay for itself the first time a verdict says
  "rent supports this deal" and the user asks "which rent?".

### Is the codebase ready for a semantic-layer refactor?

**Mostly yes.** The metric *layer* (Step 3) is in good shape — most
metrics have a single computation site, weights are explicit, and the
recently-completed CMA Phase 4a unified the largest historical
duplication (Engine A vs Engine B comp paths). The risk and confidence
modules are mature.

**Two preconditions before refactor.** First, resolve Drift §4.1 (the
pricing-view band disagreement) — leaving it untouched while
introducing a semantic registry will bake the contradiction into the
registry's metadata. Second, decide the fate of the orphan signature
metrics (Forward Value Gap, Optionality Score) — a registry that lists
them as `MISSING` will become an answered question; a registry that
omits them invites them to come back as ad-hoc prose.

**Approach:** the registry should be code, not markdown. A
`briarwood/registry.py` exporting a list of `Metric` dataclasses
(name, location, formula reference, bands, confidence handler,
consumers) lets the test suite assert "every prompt-referenced metric
exists in the registry" and "every registered metric has at least one
test." This catches future drift mechanically.

---

*End of audit. No code modified. Phase 2 (remediation) requires explicit user approval per the project's audit-mode-is-read-only discipline.*

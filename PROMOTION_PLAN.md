# Briarwood — Promotion Plan (Handoff 2b)

**Date:** 2026-04-24
**Scope:** Decision for each legacy (non-scoped) model in
[TOOL_REGISTRY.md](TOOL_REGISTRY.md): promote to scoped registry, keep
as internal composition helper, or deprecate.
**Consumes:** Handoff 2a closure (scoped-wrapper error contract,
audit-doc reconciliation).
**Feeds:** Handoff 3 (scoped-wrapper implementation), Handoff 4+
(deprecation migrations).

---

## Context

Handoff 2a closed out the scoped-wrapper error contract
([DECISIONS.md](DECISIONS.md) 2026-04-24 *Scoped wrapper error
contract*) and reconciled audit-doc drift against module READMEs. Of
the ~38 module files under `briarwood/modules/`, 15 are registered in
the scoped execution registry at
[briarwood/execution/registry.py](briarwood/execution/registry.py); the
rest are composition helpers called transitively, a few legacy top-level
runners, and some shared utilities.

Handoff 2b decides, per legacy model, one of:

- **Promote** — wrap it in a scoped-registry entry so an orchestrating
  LLM (Layer 2) can call it directly as a tool.
- **Keep as internal composition helper** — leave it consumed-only by
  scoped wrappers; document that it is intentionally not a tool.
- **Deprecate** — mark for removal; the code exists but no caller
  justifies keeping it.

This session produces only PROMOTION_PLAN.md. No code changes. No
scoped wrappers are written — that is Handoff 3.

---

## Summary table

| # | Model | Call | Pattern |
|---|---|---|---|
| 1 | comparable_sales | **PROMOTE** | Standalone wrapper |
| 2 | hybrid_value | **PROMOTE** | Composite wrapper (missing-priors) |
| 3 | current_value | **PROMOTE** | Standalone wrapper; distinct from `valuation` |
| 4 | market_value_history | **PROMOTE** | Standalone wrapper |
| 5 | property_data_quality | **KEEP as helper** | Exposed via `confidence` |
| 6 | bull_base_bear | **DEPRECATE** | Replaced by scoped `resale_scenario` |
| 7 | scarcity_support | **PROMOTE** | Standalone wrapper |
| 8 | income_support | **PROMOTE** | Standalone wrapper; distinct from `rental_option` |
| 9 | rental_ease | **KEEP as helper** | Exposed via `rental_option` + `rent_stabilization` |
| 10 | risk_constraints | **KEEP as helper** | Exposed via `risk_model` |
| 11 | location_intelligence | **PROMOTE** | Standalone wrapper |
| 12 | local_intelligence | **KEEP as helper** | Adapter; future handoff may expose subsystem |
| 13 | strategy_classifier | **PROMOTE** | Existing adapter registered only |
| 14 | value_finder | **DEPRECATE** | Zero callers; orphaned |
| 15 | decision_model/calculate_final_score | **DEPRECATE** | Dead aggregator |

**Tally:** 8 PROMOTE · 4 KEEP as helper · 3 DEPRECATE.

---

## Cross-cutting Handoff 3 constraints

These apply to more than one model and must be treated as hard
requirements when Handoff 3 writes the scoped wrappers.

### Disambiguation READMEs for parallel-tool promotions

Two promotions create a *second* tool alongside an already-scoped
wrapper that covers overlapping user intent:

- **`valuation` (existing) + `current_value` (new, #3).** `valuation`
  applies the macro nudge and is the canonical "what is this worth?"
  tool. `current_value` exposes the pre-macro fair value — useful for
  scenario modeling, stress testing, and explicit macro isolation.
- **`rental_option` (existing) + `income_support` (new, #8).**
  `rental_option` is the composite rent-path strategy answer.
  `income_support` exposes raw DSCR / rent-coverage / income-support
  ratio for direct LOOKUP.

**Requirement.** Each pair must ship a README on *both* tools that
explicitly says *when to call which*. Without that guidance, the
orchestrating LLM will choose randomly between the two — a product
regression relative to a single canonical tool. Write the "when to
call which" guidance as the first section of each README after the
one-line summary. Keep the language concrete and intent-based, not
architecture-based.

### Canonical error contract

Every scoped wrapper follows [DECISIONS.md](DECISIONS.md) 2026-04-24
*Scoped wrapper error contract*. Two entry points; pick the right one:

- **Standalone wrapper** (no prior deps) → try/except the legacy
  runner; on exception return
  `module_payload_from_error(...)` per
  [briarwood/modules/scoped_common.py:114](briarwood/modules/scoped_common.py#L114).
- **Composite wrapper** (reads prior outputs) → collect missing
  priors; if any are missing OR have `mode in {"error","fallback"}`,
  return `module_payload_from_missing_prior(...)`.

Applies to all 8 promotions in this plan.

### Field-name stability

Multiple promotions preserve existing payload shapes because
non-registry callers read the legacy module output directly. See
per-model constraints below for the specific keys that must not
change.

---

## Decisions

### 1. comparable_sales — **PROMOTE**

**Decision.** Promote to scoped registry. Standalone wrapper
(try/except → `module_payload_from_error`). Preserve payload field
names so `hybrid_value` and `unit_income_offset` continue to read the
output from `prior_results` unchanged. Retires the ad-hoc graft at
[briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88).

**Current role.** `ComparableSalesModule` at
[briarwood/modules/comparable_sales.py:35](briarwood/modules/comparable_sales.py#L35)
with entry `run(property_input) -> ModuleResult`. Zero prior
dependencies: runs `MarketValueHistoryModule` internally and delegates
comp-matching to `ComparableSalesAgent` with a
`FileBackedComparableSalesProvider` pointed at
`data/comps/sales_comps.json`.

**Important distinction: two comp engines, not one.** The fair-value
comp engine (Engine A — this module) is NOT the same as the
user-facing "CMA report" surfaced when a user types *"run a CMA."*
That user-facing CMA lives at `get_cma()` in
[briarwood/agent/tools.py:1802](briarwood/agent/tools.py#L1802) and
prefers live Zillow candidates over saved comps; it falls back to saved
comps only if live is empty. The separation is explicit in
[dispatch.py:3697-3699](briarwood/agent/dispatch.py#L3697-L3699).
Engine A drives `value_thesis.comps` (authoritative for fair value);
Engine B drives `session.last_market_support_view`. Promotion in 2b
applies to Engine A only. Engine B quality is tracked under
[FOLLOW_UPS.md](FOLLOW_UPS.md) 2026-04-24 *Two comp engines with
divergent quality; CMA (Engine B) needs alpha-quality pass*.

**Consumers of Engine A.**
- `CurrentValueModule` (transitively via `valuation` scoped wrapper).
- `HybridValueModule` — reads output from `prior_results`.
- `unit_income_offset` — the ADU cap-rate (`_DEFAULT_ADU_CAP_RATE = 0.08`)
  and expense-ratio (`_ADU_EXPENSE_RATIO = 0.30`) live here at
  lines 28, 32 (see DECISIONS.md 2026-04-24 *unit_income_offset drift*).
- [briarwood/claims/pipeline.py:62-88](briarwood/claims/pipeline.py#L62-L88)
  runs `ComparableSalesModule()` directly because "The scoped execution
  registry doesn't surface comparable_sales as a top-level module."

**Rationale.**
1. Zero prior dependencies — the standalone scoped-wrapper pattern at
   [briarwood/modules/carry_cost.py:14-36](briarwood/modules/carry_cost.py#L14-L36)
   applies cleanly.
2. The graft at `claims/pipeline.py` already runs it as a standalone
   tool; promotion formalizes what claims is doing informally.
3. Intent coverage — `LOOKUP` and `COMPARISON` have legitimate
   standalone use cases that today force the whole valuation cascade.

**Constraints Handoff 3 must honor.**
- Hybrid detection (`_detect_hybrid_valuation`, `_build_hybrid_request`
  at lines 465, 520) is baked into `run()`. Scoped wrapper absorbs it
  — no behavior change.
- Preserve `payload` field names. `hybrid_value` and
  `unit_income_offset` read the payload from `prior_results`; a
  wrapper that reshapes keys breaks them. Replicate the existing graft's
  passthrough shape.
- ADU constants stay put. Relocation is a separate follow-up, not 2b
  or 3.

---

### 2. hybrid_value — **PROMOTE (as composite wrapper)**

**Decision.** Promote as composite wrapper. Missing-priors contract —
requires `comparable_sales` AND `income_support` in `prior_results`.
On missing, return `module_payload_from_missing_prior(...)`. Preserve
the full decomposition payload (`primary_house_value`,
`rear_income_value`, `rear_income_method_used`,
`optionality_premium_value`, `low_case_hybrid_value`,
`base_case_hybrid_value`, `high_case_hybrid_value`,
`market_friction_discount`, `market_feedback_adjustment`).

**Current role.** `HybridValueModule` at
[briarwood/modules/hybrid_value.py:50](briarwood/modules/hybrid_value.py#L50).
Decomposes primary-dwelling + accessory-income properties into primary
comp-driven value + capitalized ADU income + optionality premium +
market-friction / feedback adjustments. Only activates on
`_detect_hybrid_property → is_hybrid=True`; non-hybrid subjects get a
zero-confidence N/A payload.

**Consumers.**
- [current_value.py:85-98](briarwood/modules/current_value.py#L85-L98)
  — applies hybrid adjustment to fair value.
- [value_finder.py:128-180](briarwood/modules/value_finder.py#L128-L180)
  — surfaces `has_hybrid_value` flag for screening.
- [risk_bar.py:116](briarwood/risk_bar.py#L116) — reads for risk
  narration.

**Rationale.** `valuation` returns only a final number; the
decomposition breakdown (primary / rear income / optionality) lives
here and is the only payload that can answer *"why is this hybrid
worth what it's worth?"* Promotion opens the breakdown as a callable
tool for RESEARCH / EDGE intents on multi-unit and ADU properties.

**Constraints Handoff 3 must honor.**
- Composite-wrapper pattern, not standalone try/except.
- Treat prior `comparable_sales` / `income_support` with
  `mode in {"error","fallback"}` as missing.
- Preserve the `is_hybrid=False` short-circuit shape — a non-hybrid
  subject returns the zero-confidence payload, NOT a degraded error.
  This is a valid product answer ("not a hybrid property"), not a
  module failure.
- Do NOT collapse the `comp_is_hybrid` passthrough path at
  [hybrid_value.py:118-132](briarwood/modules/hybrid_value.py#L118-L132)
  — when `comparable_sales` already performed the decomposition, the
  primary + rear values are reused to avoid double-counting.

---

### 3. current_value — **PROMOTE (as separate tool)**

**Decision.** Promote as a standalone scoped-registry tool, distinct
from `valuation`. Produces the pre-macro-nudge fair value. Standalone
wrapper pattern. Preserve the full payload shape that
`CurrentValueModule` returns today so internal consumers
(`bull_base_bear`, `teardown_scenario`, `renovation_scenario`) and the
`valuation` wrapper continue to read it identically.

**Current role.** `CurrentValueModule` at
[briarwood/modules/current_value.py:19](briarwood/modules/current_value.py#L19).
The fair-value compute engine. Internally composes `comparable_sales`,
`market_value_history`, `income_support`, `hybrid_value`; applies the
hybrid adjustment via `_apply_hybrid_adjustment`. Does NOT apply the
macro nudge (that happens in `valuation` at
[valuation.py:27](briarwood/modules/valuation.py#L27)).

**Consumers.**
- [valuation.py:27](briarwood/modules/valuation.py#L27) — scoped
  `valuation` wrapper (macro-nudge layer).
- [bull_base_bear.py:33](briarwood/modules/bull_base_bear.py#L33),
  [teardown_scenario.py:35](briarwood/modules/teardown_scenario.py#L35),
  [renovation_scenario.py:32](briarwood/modules/renovation_scenario.py#L32)
  — direct class access.

**Constraints Handoff 3 must honor.**
- **Disambiguation README** (see cross-cutting constraints above).
  `valuation` for the user-facing "what is this worth?" number that
  includes the macro nudge; `current_value` for pre-macro reasoning
  (scenario modeling, stress testing, explicit macro isolation).
- **Field-name stability.** Existing callers read the raw payload
  directly — do not reshape.
- **No duplicate computation.** The `valuation` wrapper continues to
  call `CurrentValueModule` in-process, NOT through the scoped
  `current_value` tool (prevents double error-handling + recursive
  registry dependency).
- **README reversibility note.** The two-tool split is deliberate and
  reversible; if the orchestrator never actually needs pre-macro
  access, the promotion can be rolled back in a future handoff.

---

### 4. market_value_history — **PROMOTE**

**Decision.** Promote as standalone scoped-registry tool. Zero prior
deps; standalone wrapper pattern. Preserve existing payload
(`MarketValueHistoryOutput`) so internal consumers
(`comparable_sales`, `current_value`, `bull_base_bear`) continue to
read it unchanged via direct class access.

**Current role.** `MarketValueHistoryModule` at
[briarwood/modules/market_value_history.py:15](briarwood/modules/market_value_history.py#L15).
Thin source-backed lookup over Zillow ZHVI town/county history via
`FileBackedZillowHistoryProvider` against
`data/market_history/zillow_zhvi_history.json`. Returns geography
identifiers, current ZHVI level, 1yr / 3yr change %, time-series
`points`, summary, confidence.

**Consumers.** `comparable_sales`, `current_value`, `bull_base_bear`
(each instantiates `MarketValueHistoryModule` directly).

**Rationale.** User intent *"how has this market been trending?"* is a
standalone RESEARCH / BROWSE / PROJECTION question with no direct tool
today. Output shape is already tool-shaped (geography, current level,
change %, time-series).

**Constraints Handoff 3 must honor.**
- **Geography-level framing.** ZHVI data is town/county-level, not
  property-level. README must frame outputs as "market trend for the
  geography containing this property" so the LLM does not misuse the
  tool for property-specific trend questions.
- **Preserve payload shape** so internal callers don't need to change.

---

### 5. property_data_quality — **KEEP as internal helper**

**Decision.** Keep consumed-only by `confidence` and `legal_confidence`.
Diagnostic data-quality access to the orchestrator LLM goes through
`confidence` (already a promoted scoped tool), which aggregates this
module's NJ-tax-and-structural signals into an interpreted score.
Exposing the raw flags (`reassessment_risk_score`, `tax_burden_score`,
`comp_eligibility_score`, etc.) directly would invite misinterpretation
and duplicate `confidence`'s role.

**Current role.** `PropertyDataQualityModule` at
[briarwood/modules/property_data_quality.py:11](briarwood/modules/property_data_quality.py#L11).
NJ-specific tax-and-comp-eligibility scorer (not generic "property
data quality" — see the DECISIONS.md entry landed alongside this
plan). Optional `NJTaxIntelligenceStore` gated on
`BRIARWOOD_NJ_TAX_PATH`.

**Consumers.**
[confidence.py:32](briarwood/modules/confidence.py#L32),
[legal_confidence.py:23](briarwood/modules/legal_confidence.py#L23).

**Follow-on note.** If a future product decision wants user-facing
data-quality diagnostics, the right place to extend is the `confidence`
scoped wrapper, not a new `property_data_quality` tool.

---

### 6. bull_base_bear — **DEPRECATE**

**Decision.** Deprecate. Replaced by the scoped `resale_scenario`
wrapper under scoped execution — see explicit comment at
[briarwood/agent/tools.py:1411](briarwood/agent/tools.py#L1411):
> "resale_scenario module (which replaces bull_base_bear under scoped
> execution)."

The settings are already tombstoned at
[runner_routed.py:222](briarwood/runner_routed.py#L222):
```python
del cost_settings, bull_base_bear_settings, risk_settings  # kept for API compat
```

**Migration dependencies that block a clean removal.**
- [decision_model/scoring.py:229](briarwood/decision_model/scoring.py#L229)
  — reads `bull_base_bear` metrics directly for historical-pricing
  score. Must migrate to `resale_scenario` metric keys.
- [decision_model/lens_scoring.py:164, 229](briarwood/decision_model/lens_scoring.py#L164)
  — two reads, same migration.
- [agent/tools.py:1427](briarwood/agent/tools.py#L1427) —
  `outputs.get("resale_scenario") or outputs.get("bull_base_bear")`
  fallback. Drop the fallback arm.
- [eval/model_quality/model_specs.py:24](briarwood/eval/model_quality/model_specs.py#L24)
  — eval spec import. Re-point or remove.

**Sequence for Handoff 4+.**
1. Migrate `decision_model/scoring.py` + `lens_scoring.py` to read
   `resale_scenario` metric keys. Audit metric-name parity first:
   `ScenarioOutput` field names in `bull_base_bear` vs `resale_scenario`
   need to align, or the migration is a semantic rewrite, not a
   rename.
2. Drop the `or bull_base_bear` fallback in `tools.py:1427`.
3. Re-point or remove the eval spec.
4. Delete `bull_base_bear.py` + `BullBaseBearSettings` +
   `DEFAULT_BULL_BASE_BEAR_SETTINGS`.

Out of scope for Handoff 3. Deprecation migration is its own handoff.

---

### 7. scarcity_support — **PROMOTE**

**Decision.** Promote as standalone scoped-registry tool. Zero prior
deps; standalone wrapper pattern. Preserve `scarcity_support_score`
field name so existing readers in decision_model, interactions, and
rental_ease continue to key on it unchanged.

**Current role.** `ScarcitySupportModule` at
[briarwood/modules/scarcity_support.py:15](briarwood/modules/scarcity_support.py#L15).
Uses `TownCountyDataService` + `ScarcitySupportScorer` to produce
`scarcity_label`, `scarcity_support_score` (0-100), `buyer_takeaway`,
confidence, and a `ScarcitySupportScore` payload.

**Consumers (multiple read `scarcity_support_score` by key).**
- [bull_base_bear.py:37](briarwood/modules/bull_base_bear.py#L37) — deprecating.
- [interactions/town_x_scenario.py:40](briarwood/interactions/town_x_scenario.py#L40),
  [interactions/valuation_x_town.py:82-85](briarwood/interactions/valuation_x_town.py#L82-L85).
- [decision_model/scoring.py:291-292, 702, 735, 1083, 1177](briarwood/decision_model/scoring.py#L291),
  [lens_scoring.py:165, 196](briarwood/decision_model/lens_scoring.py#L165).
- [agents/rental_ease/agent.py:74, 202, 287, 327](briarwood/agents/rental_ease/agent.py#L74)
  — consumed as input.

**Rationale.** Widely-read signal already tool-shaped; standalone
user intent *"how scarce is this segment?"* / *"is there inventory
competition?"* (RESEARCH / MICRO_LOCATION / BROWSE) has no direct tool
today.

**Constraints Handoff 3 must honor.**
- Preserve `scarcity_support_score` field name.
- Internal `TownCountyDataService` wiring stays implementation-private;
  tool contract is `PropertyInput → ScarcitySupportScore`.

---

### 8. income_support — **PROMOTE (as separate tool)**

**Decision.** Promote as standalone scoped-registry tool, distinct
from the `rental_option` wrapper that already surfaces its output.
Parallel to the `current_value` / `valuation` split — the foundational
engine is exposed separately from the composite wrapper that presents
it to users. Standalone wrapper pattern.

**Current role.** `IncomeSupportModule` at
[briarwood/modules/income_support.py:11](briarwood/modules/income_support.py#L11).
Produces `income_support_ratio` (effective_monthly_rent /
gross_monthly_cost), rent-support classification, rent coverage,
DSCR-style signals.

**Consumers.** `rental_option_scoped` (wraps it at
`extra_data.income_support`), `rental_ease`, `hybrid_value`,
`teardown_scenario`, `current_value` (transitively via `valuation`);
read paths in `risk_bar`, `evidence`, `comp_intelligence`.

**Constraints Handoff 3 must honor.**
- **Disambiguation README** (see cross-cutting constraints above).
  `income_support` for LOOKUP *"what's the DSCR / rent coverage?"*;
  `rental_option` for the full rent-path strategy answer.
- **In-process composition.** `rental_option` continues to call
  `IncomeSupportModule` directly, NOT through the scoped
  `income_support` tool (anti-recursion, parallel to
  `valuation` → `CurrentValueModule`).
- **Field-name stability.** `income_support_ratio` and related keys
  are read by `risk_bar`, `evidence`, `comp_intelligence`,
  `rental_ease`, `hybrid_value`. Do not reshape.

---

### 9. rental_ease — **KEEP as internal helper**

**Decision.** Keep consumed-only. Two scoped wrappers already surface
RentalEase signals to the orchestrator:
- `rental_option` at
  [briarwood/modules/rental_option_scoped.py:29](briarwood/modules/rental_option_scoped.py#L29)
  (RentalEase + IncomeSupport composite).
- `rent_stabilization` at
  [briarwood/modules/rent_stabilization.py:22](briarwood/modules/rent_stabilization.py#L22)
  (RentalEase + town/county stabilization context).

Promoting a third entry point for rent-absorption / rental-liquidity
questions would create overlapping tools with no net intent coverage
gained.

**Current role.** `RentalEaseModule` at
[briarwood/modules/rental_ease.py:15](briarwood/modules/rental_ease.py#L15).
Produces `rental_ease_label`, `liquidity_score`, `demand_depth_score`,
`rent_support_score`, `structural_support_score`,
`estimated_days_to_rent`, `scarcity_support_score`.

---

### 10. risk_constraints — **KEEP as internal helper**

**Decision.** Keep consumed-only by the scoped `risk_model` wrapper at
[briarwood/modules/risk_model.py:37](briarwood/modules/risk_model.py#L37).
Raw penalty metrics (tax / DOM / vacancy) are internal weights, not a
user-addressable intent; `risk_model` already exposes the interpreted
"what are the risks?" answer with town/county legal-confidence context
layered on top.

**Current role.** `RiskConstraintsModule` at
[briarwood/modules/risk_constraints.py:10](briarwood/modules/risk_constraints.py#L10).
Graduated tax/DOM/vacancy penalties and rolled-up risk score.

**Distinction from the `current_value` / `income_support` promote
calls.** Those have distinct LOOKUP intents (pre-macro fair value,
DSCR ratio) not surfaced by their wrappers.
`risk_constraints`'s raw outputs have no analogous standalone user
question.

---

### 11. location_intelligence — **PROMOTE**

**Decision.** Promote as standalone scoped-registry tool. Zero prior
deps; standalone wrapper pattern. Preserve the existing missing-input
degradation semantics (`confidence_notes` + `missing_inputs` populated
when coords or landmarks are absent) — no change to how the module
handles data gaps.

**Current role.** `LocationIntelligenceModule` at
[briarwood/modules/location_intelligence.py:52](briarwood/modules/location_intelligence.py#L52).
Benchmarks landmark proximity against same-town geo peer comp buckets,
producing per-category scores (beach / train / parks / etc.), distance
benefits, percentile benefits, narratives, and a rolled-up location
score.

**Consumers.** `micro_location_engine`, `evidence` (two paths),
[decision_model/scoring.py:295-296](briarwood/decision_model/scoring.py#L295),
eval specs. No existing scoped wrapper covers the MICRO_LOCATION
intent family.

**Rationale.** Standalone, distinct user intent (MICRO_LOCATION /
RESEARCH / BROWSE), no existing tool. The 619-line richness suggests a
substantive tool contract.

---

### 12. local_intelligence — **KEEP as internal helper**

**Decision.** Keep consumed-only by `legal_confidence`. The module is
an explicit compatibility bridge
([local_intelligence.py:23 docstring](briarwood/modules/local_intelligence.py#L23))
that adapts `LocalIntelligenceService` output into the `ModuleResult`
shape. Promoting the bridge rather than the underlying subsystem is the
wrong abstraction layer.

**Product-direction note (not a 2b action).** Owner flagged local
intelligence as a key capability for the "replace the realtor" thesis
— the agent going out to understand whether a town is growing / up
and coming is foundational to what the product delivers. Current
surfaces:
- `legal_confidence` exposes local-intelligence signals at
  `extra_data.local_intelligence` (development-activity proxy).
- `town_development_index` (already scoped) covers town-trajectory
  framing.

**Future handoff consideration (outside 2b scope).** The right path to
elevate this capability is not promoting the bridge module; it is
deciding whether to:
1. Expose `LocalIntelligenceService` directly with a purpose-built
   scoped wrapper (distinct from this bridge), OR
2. Enrich `legal_confidence` / `town_development_index` outputs to
   surface richer local-intelligence signals, OR
3. Build a new scoped tool dedicated to "town trajectory" that
   composes local_intelligence + town_development_index signals.

That decision depends on which framing best matches how an
orchestrator LLM would naturally ask the question. Flag as a handoff
candidate after Handoff 3 completes.

See also [FOLLOW_UPS.md](FOLLOW_UPS.md) *Route local-intelligence
extraction through shared LLM boundary* (2026-04-24) — a separate but
related quality concern about the subsystem's direct-OpenAI extraction
path.

---

### 13. strategy_classifier — **PROMOTE**

**Decision.** Promote via registration. The scoped adapter
`run_strategy_classifier(context: ExecutionContext) -> dict[str, object]`
already exists at
[briarwood/modules/strategy_classifier.py:247](briarwood/modules/strategy_classifier.py#L247)
and conforms to the scoped-module contract, but is not registered in
[briarwood/execution/registry.py](briarwood/execution/registry.py).
Handoff 3 adds a `ModuleSpec` to `build_module_registry()` — no new
adapter code needed.

**Current role.** Deterministic rule-based classifier over
`PropertyInput`. Emits `PropertyStrategyType` ∈ `{owner_occ_sfh,
owner_occ_duplex, owner_occ_with_adu, pure_rental, value_add_sfh,
redevelopment_play, scarcity_hold}`. Pure function, zero IO, zero
prior deps.

**Dormant consumer.**
[briarwood/interactions/primary_value_source.py:34, 42-64](briarwood/interactions/primary_value_source.py#L34)
reads `_payload(outputs, "strategy_classifier")` and gates the
strategy-prior branch on `is not None`. Registration unblocks that
branch, which today silently never fires.

**Constraints Handoff 3 must honor.**
- **Registration shape.** `ModuleSpec(name="strategy_classifier",
  depends_on=[], required_context_keys=["property_data"],
  runner=run_strategy_classifier, description="Rule-based property
  strategy classifier.")`.
- **Error contract.** The existing adapter does NOT wrap
  `classify_strategy` in try/except. Add one
  (`module_payload_from_error` on exception) per the canonical error
  contract — safer than assuming the pure-rule implementation cannot
  raise on adversarial `PropertyInput`.

**Open product question (defer past 2b).** Strategy classification is
naturally an *upstream* signal that should inform which other tools
the orchestrator runs. Whether to always-run it as a routing
pre-step, or treat it as one tool among many, is a Handoff 3+
architecture decision — not a promotion blocker.

---

### 14. value_finder — **DEPRECATE**

**Decision.** Deprecate. Zero production callers (verified by grep
across `briarwood/` and `tests/`). Module-level functions
`analyze_value_finder` / `analyze_property_value_finder` are
referenced only in audit docs (TOOL_REGISTRY.md, GAP_ANALYSIS.md,
historical `analysis/*.md`). Not a class; not ModuleResult-shaped.

**Why not "keep as helper."** It helps nothing. `analyze_value_finder`
accepts pre-computed values (asking, briarwood value, comps) and
returns an `opportunity_signal` / `pricing_posture` — a derivation
function that assumes a caller did the upstream work. No such caller
exists.

**Product overlap.** Opportunity-detection intent is covered by
[briarwood/value_scout/](briarwood/value_scout/) (distinct module,
actively called per its README). Per TOOL_REGISTRY note at
[TOOL_REGISTRY.md:933](TOOL_REGISTRY.md) — "Often confused with
value_scout in dispatch code." Two similarly-named capabilities, with
`value_scout` being the production one.

**Sequence for Handoff 4+ removal.**
1. Delete [briarwood/modules/value_finder.py](briarwood/modules/value_finder.py).
2. Remove the `value_finder` entry from TOOL_REGISTRY.md and the
   reference in GAP_ANALYSIS.md.
3. `value_scout` is not touched by this deprecation — it is a separate,
   live module.

**Open follow-up (flag, do not act in 2b).** If opportunity-detection
is product-critical, elevate `value_scout` in a separate handoff —
either promote it to the scoped registry with a proper wrapper or
integrate its signals into existing scoped tools.

---

### 15. decision_model/calculate_final_score — **DEPRECATE**

**Decision.** Deprecate the `calculate_final_score` aggregator and
its supporting types (`FinalScore`, `CategoryScore`, `SubFactorScore`).
Live code, dead paths — no production caller per TOOL_REGISTRY blocker
note and verified by grep; production synthesis at
[briarwood/synthesis/structured.py](briarwood/synthesis/structured.py)
uses a different scoring approach.

**Scope limit.** Only the aggregator is deprecated. The per-dimension
scoring helpers in the same file (`_score_price_vs_comps`,
`_score_ppsf_positioning`, `_score_historical_pricing`,
`_score_scarcity_premium`, `_score_rent_support`,
`_score_carry_efficiency`, `_score_downside_protection`, etc.) have
active callers and remain.

**Additional cleanup.** Deprecation also retires the orphaned
`$400/sqft` replacement-cost constant flagged in DECISIONS.md
2026-04-24 *Replacement-cost tool does not exist* — reachable only
through the dead aggregator today.

**Sequence for Handoff 4+ removal.**
1. Delete `calculate_final_score(report)` and dataclasses
   `FinalScore` / `CategoryScore` / `SubFactorScore` from
   [briarwood/decision_model/scoring.py](briarwood/decision_model/scoring.py).
2. Remove the `decision_model/calculate_final_score` entry from
   TOOL_REGISTRY.md (non-production section).
3. Audit `_score_*` helper usage one more time to confirm none of them
   are only reachable through the dead aggregator.
4. Align with [briarwood/recommendations.py](briarwood/recommendations.py)
   (still used for tier normalization per TOOL_REGISTRY note 972) —
   verify no break.

---

## Associated entries landed alongside this plan

- [DECISIONS.md](DECISIONS.md) 2026-04-24 — *property_data_quality
  output schema mismatch in audit docs* (same drift pattern as the
  nine entries reconciled in Handoff 2a Piece 6).
- [FOLLOW_UPS.md](FOLLOW_UPS.md) 2026-04-24 — *Two comp engines with
  divergent quality; CMA (Engine B) needs alpha-quality pass* (surfaces
  the Engine A / Engine B split discovered during `comparable_sales`
  discussion and scopes the quality audit as its own handoff).

---

## Verification

1. **Plan coverage.** PROMOTION_PLAN.md names all 15 rows with one of
   {PROMOTE, KEEP, DEPRECATE} and links each to its TOOL_REGISTRY.md
   entry. ✓
2. **README cross-reference (Handoff 3 precondition).** For each
   PROMOTE, confirm no existing module README already promises a
   contract that Handoff 3 would violate. For each KEEP, confirm the
   scoped wrapper README that covers the helper is accurate.
3. **DECISIONS.md and FOLLOW_UPS.md drafts landed.** See "Associated
   entries" above.
4. **Regression gate.** The existing test suite passes unchanged —
   this session writes no application code.
5. **Handoff 3 pre-read.** Verify the canonical error-contract entry
   in DECISIONS.md (2026-04-24 *Scoped wrapper error contract*) is
   read into each promote plan so composite wrappers know to treat
   `mode in {"error","fallback"}` priors as missing.

---

## Open items NOT in this plan (flagged for later handoffs)

- **CMA-quality audit** (Engine A + Engine B) — FOLLOW_UPS.md entry
  landed; needs its own handoff after promotion is complete.
- **Replacement-cost tool** — still open per DECISIONS.md 2026-04-24.
  Deprecation of `calculate_final_score` retires the orphan constant
  but does not answer the product question.
- **Town-intelligence elevation** — product-direction note from the
  `local_intelligence` decision. Three possible paths (subsystem
  direct-promote / enrich legal_confidence / new town-trajectory tool).
  Separate handoff.
- **Strategy-classifier routing question** — whether to always-run as
  a pre-routing signal or treat as one scoped tool among many.
  Handoff 3+ architecture call.
- **`bull_base_bear` deprecation migration** — decision_model /
  lens_scoring / tools.py fallback / eval specs all need to re-point
  to `resale_scenario`. Multi-step; own handoff.
- **`value_finder` deprecation cleanup** — file deletion + audit-doc
  cleanup. Small; bundles with other deprecations.
- **`calculate_final_score` deprecation cleanup** — aggregator removal
  + TOOL_REGISTRY cleanup. Small.

---

## Execution record

### Handoff 3 — 2026-04-24 — all 8 PROMOTE decisions realized (commit `37df9f8`)

The 8 PROMOTE decisions listed in this plan were executed in the following
sequence (dependency order, simplicity-first, disambiguation pairs adjacent):

1. **strategy_classifier** (entry 13) — registration-only; added try/except
   wrap + `ModuleSpec`.
2. **market_value_history** (entry 4) — standalone scoped wrapper
   `market_value_history_scoped.py`.
3. **current_value** (entry 3) — standalone scoped wrapper
   `current_value_scoped.py`; disambiguation README pair with `valuation`;
   anti-recursion comment in `valuation.py`.
4. **income_support** (entry 8) — standalone scoped wrapper
   `income_support_scoped.py`; disambiguation README pair with `rental_option`;
   anti-recursion comment in `rental_option_scoped.py`.
5. **scarcity_support** (entry 7) — standalone scoped wrapper
   `scarcity_support_scoped.py`; field-name stability on
   `scarcity_support_score` preserved.
6. **location_intelligence** (entry 11) — standalone scoped wrapper
   `location_intelligence_scoped.py`; missing-input semantics preserved.
7. **comparable_sales** (entry 1) — standalone scoped wrapper
   `comparable_sales_scoped.py`; hybrid-decomposition field names preserved;
   FOLLOW_UPS.md entry added for retiring `claims/pipeline.py:62-88` graft.
8. **hybrid_value** (entry 2) — composite scoped wrapper
   `hybrid_value_scoped.py` with canonical missing-priors contract;
   `is_hybrid=False` short-circuit preserved as valid non-error payload.

Each promotion added one `ModuleSpec` to `briarwood/execution/registry.py`,
one new `README_<name>.md` under `briarwood/modules/`, and isolation +
error-contract + registry-integration tests under `tests/modules/`. The
`StrategyClassifier` test file was extended rather than duplicated.
`ARCHITECTURE_CURRENT.md` Scoped table grew from 15 → 23 models; the
Legacy table lost the 8 promoted rows. `TOOL_REGISTRY.md` blockers were
cleared on each of the 8 entries and the entry-field was updated to the
new scoped runner signature.

The scoped registry now contains 23 models. The `test_every_scoped_module_appears_once`
expected set was updated to match (it was already failing pre-H3 because
`opportunity_cost` from a prior handoff was not in the expected set —
that side-pollution is also resolved). Full test-suite baseline of
29 pre-existing failures was held through all 8 promotions; no new failures
introduced.

OUT of scope and explicitly untouched: `bull_base_bear`, `value_finder`,
and `calculate_final_score` DEPRECATE decisions (Handoff 4);
`property_data_quality`, `rental_ease`, `risk_constraints`, and
`local_intelligence` KEEP-as-helper documentation (Handoff 5); CMA Engine B
quality audit (own handoff); town-intelligence elevation (own handoff).

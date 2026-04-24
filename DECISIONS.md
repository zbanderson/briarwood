# Briarwood — Decisions Log

Deliberate, dated entries for product and architectural decisions that shape the codebase. Entries are append-only; the history is the point. Referenced from module READMEs under "Open Product Decisions" and "Notes" wherever a decision bears on a module's contract.

---

## 2026-04-24 — CostValuationModule is misnamed

The class `briarwood/modules/cost_valuation.py::CostValuationModule` computes
ownership carry economics (PITI, HOA, maintenance reserve, NOI, DSCR, cap
rate), not replacement cost. The scoped `carry_cost` wrapper uses it
correctly. ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md describe it as
"replacement-cost approach, teardown/redevelopment fallback" — that
description is wrong, inherited from the class name. Deferred rename
(proposed: `CarryCostModule` or `OwnershipEconomicsModule`). Do NOT
rename during Handoff 1.

**Resolved 2026-04-24** (Handoff 2a Piece 5A): renamed class to
`OwnershipEconomicsModule` and file to `briarwood/modules/ownership_economics.py`
via `git mv`. Updated callsites in `briarwood/modules/carry_cost.py:4,16,18`
and `tests/test_modules.py` (import + four instantiations). Updated
`ARCHITECTURE_CURRENT.md` row to use the new name and an ownership-carry
description. Updated `TOOL_REGISTRY.md` entry — renamed to
`ownership_economics`, corrected output schema to match
`ValuationOutput.to_metrics` at `briarwood/schemas.py:503`, removed the
phantom `replacement_cost` / `land_value` fields. Settings dataclass
`CostValuationSettings` left unrenamed to minimize diff; flagged in
`README_carry_cost.md` Notes.

## 2026-04-24 — Replacement-cost tool does not exist

The audit's `cost_valuation` entry in TOOL_REGISTRY.md describes a tool
with `replacement_cost` and `land_value` outputs that is NOT implemented
anywhere. The $400/sqft constant in
`briarwood/decision_model/scoring_config.py` is an orphaned seed — never
consumed. If teardown/redevelopment scenarios are in scope, a real
replacement-cost module is needed. Open question; no decision yet.

## 2026-04-24 — Two cost questions, one of them is Layer 3

Owner framing: (1) what does this cost to own over time, (2) does it make
sense to buy/rent/hold/flip. (1) is `carry_cost` (specialty model, Layer
2). (2) is synthesis across multiple tools against user intent — belongs
in Unified Intelligence (Layer 3), not a new specialty model. Do not
build a second cost-related module to answer (2).

## 2026-04-24 — legal_confidence output schema mismatch in audit docs

ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md describe
`legal_confidence` as producing `permission_flags: list[str]` and
`restriction_flags: list[str]` alongside `confidence`. The actual
implementation at `briarwood/modules/legal_confidence.py` produces
`legality_evidence` (a dict with `has_accessory_signal`, `adu_type`,
`has_back_house`, `additional_unit_count`, `zone_flags`,
`local_document_count`, `multi_unit_allowed`), plus `data_quality`,
`local_intelligence`, `summary`, and `confidence`. There are no
`permission_flags` or `restriction_flags` fields anywhere in the
output. The scoped wrapper is not a classifier — its docstring says
explicitly "This wrapper does not perform legal classification. It
surfaces how much structured evidence Briarwood has around zoning,
additional-unit signals, and local-document coverage." Surface this
discrepancy when reconciling audit docs per the "Audit docs are
drifted" entry.

**Resolved 2026-04-24** (Handoff 2a Piece 6): ARCHITECTURE_CURRENT.md
`legal_confidence` row and TOOL_REGISTRY.md `legal_confidence` block
updated to match README_legal_confidence.md — outputs now enumerate
`legality_evidence` sub-fields, `data_quality`, `local_intelligence`,
`summary`, `confidence`. No `permission_flags` / `restriction_flags`
fields are claimed.

## 2026-04-24 — renovation_impact output schema mismatch in audit docs

ARCHITECTURE_CURRENT.md (row for scoped `renovation_impact`) and
TOOL_REGISTRY.md (`renovation_impact` entry) describe outputs
`renovation_scope: str`, `estimated_cost_range: list[float]`,
`timeline_estimate: int (months)`. The actual implementation at
`briarwood/modules/renovation_impact_scoped.py` wraps
`RenovationScenarioModule` and produces `enabled`, `renovation_budget`,
`current_bcv`, `renovated_bcv`, `gross_value_creation`,
`net_value_creation`, `roi_pct`, `cost_per_dollar_of_value`,
`condition_change`, `sqft_change`, `comp_range_text`, `confidence`,
`warnings`, `summary`. The module is a BCV-delta + ROI calculator for
an already-specified renovation scenario, NOT a scope/cost-range/timeline
estimator. Surface when reconciling audit docs.

**Resolved 2026-04-24** (Handoff 2a Piece 6): ARCHITECTURE_CURRENT.md
`renovation_impact` row and TOOL_REGISTRY.md `renovation_impact` block
updated to match README_renovation_impact.md — outputs now enumerate
the BCV-delta / ROI schema. Phantom `renovation_scope`,
`estimated_cost_range`, `timeline_estimate` fields removed.

## 2026-04-24 — confidence output field-name drift in audit docs

ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md describe `confidence`
outputs as `overall_confidence: float` and `component_breakdown:
{ completeness, model_agreement, scenario_fragility, legal_certainty,
estimated_reliance }`. The actual implementation returns
`ModulePayload.confidence` and `ModulePayload.confidence_band` at the
top level (not `overall_confidence`), and the component breakdown
lives in `extra_data` with partially different keys:
`field_completeness`, `comp_quality`, `model_agreement`,
`scenario_fragility`, `legal_certainty`, `estimated_reliance`,
`contradiction_count`, `aggregated_prior_confidence`,
`combined_confidence`, `data_quality_confidence`,
`prior_module_confidences`. Concept is correct; the specific field
names in the audit docs need updating.

**Resolved 2026-04-24** (Handoff 2a Piece 6): ARCHITECTURE_CURRENT.md
`confidence` row and TOOL_REGISTRY.md `confidence` block updated to
match README_confidence.md — top-level `confidence` / `confidence_band`
named correctly; component breakdown attributed to `extra_data` with
the actual key names.

## 2026-04-24 — rental_option output schema mismatch in audit docs

ARCHITECTURE_CURRENT.md ("rental viability metrics") and
TOOL_REGISTRY.md (outputs `rental_viability_score: float`,
`rental_viability_metrics: dict`) describe a shape that does not exist
in the actual payload. The scoped `rental_option` wraps
`RentalEaseModule` and surfaces the usual RentalEase fields
(`rental_ease_label`, `liquidity_score`, `demand_depth_score`,
`rent_support_score`, `structural_support_score`,
`estimated_days_to_rent`, `scarcity_support_score`, `zillow_context_used`),
plus `extra_data.income_support` from `IncomeSupportModule` and
`extra_data.macro_nudge` from the employment macro signal. The audit
docs conflate the concept with a cleaner but non-existent schema.

**Resolved 2026-04-24** (Handoff 2a Piece 6): ARCHITECTURE_CURRENT.md
`rental_option` row and TOOL_REGISTRY.md `rental_option` block updated
to match README_rental_option.md — outputs now enumerate the
RentalEase + IncomeSupport fields. Phantom
`rental_viability_score` / `rental_viability_metrics` fields removed.

## 2026-04-24 — unit_income_offset drift: output schema and ADU constant location

Two drift items in one module:

(1) TOOL_REGISTRY.md says `unit_income_offset` outputs
`offset_monthly_income`, `offset_annual_income`, `cap_rate_assumed`,
`confidence`. The actual payload exposes `offset_snapshot` (with
`additional_unit_income_value` — a capitalized value, not a monthly /
annual income; `additional_unit_count`; `back_house_monthly_rent`;
`unit_rents`; `monthly_total_cost`; `monthly_cash_flow`;
`has_accessory_unit_signal`), plus a `comparable_sales` sub-dict and
an outer `confidence`. There is no `offset_monthly_income`,
`offset_annual_income`, or `cap_rate_assumed` field.

(2) ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md place the ADU cap
rate (0.08) and expense ratio (0.30) in `unit_income_offset.py` and
`hybrid_value.py`. Neither file defines them. The constants
`_DEFAULT_ADU_CAP_RATE = 0.08` and `_ADU_EXPENSE_RATIO = 0.30` live in
`briarwood/modules/comparable_sales.py` (lines 28 and 32), used via
the `additional_unit_income_value` decomposition that
`ComparableSalesModule` performs. Attribution should move in the audit
docs.

**Resolved 2026-04-24** (Handoff 2a Piece 6): (1) TOOL_REGISTRY.md
`unit_income_offset` block rewritten with actual `offset_snapshot` /
`comparable_sales` sub-dict schema; phantom
`offset_monthly_income` / `offset_annual_income` / `cap_rate_assumed`
removed. (2) ARCHITECTURE_CURRENT.md Hardcoded-values section and
`unit_income_offset` row updated — ADU cap rate / expense ratio now
correctly attributed to `briarwood/modules/comparable_sales.py`
(lines 28, 32).

## 2026-04-24 — arv_model output schema and behavior mismatch in audit docs

ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md describe `arv_model`
outputs as `estimated_arv`, `arv_confidence`, `comparable_arv_support`,
`component_cost_deltas` and note "internally: comparable_sales." The
actual implementation at `briarwood/modules/arv_model_scoped.py` is a
pure composite wrapper — it reads `valuation` and `renovation_impact`
from `prior_outputs` and synthesizes an `arv_snapshot` dict
(`current_bcv`, `renovated_bcv` ← renamed concept of estimated_arv,
`renovation_budget`, `gross_value_creation`, `net_value_creation`,
`roi_pct`, `condition_change`, `sqft_change`, `comp_range_text`) plus
nested `valuation` and `renovation_impact` sub-dicts. It does NOT call
`comparable_sales` directly — that call happens transitively inside
`renovation_impact → renovation_scenario`. The wrapper raises
`ValueError` if either prior output is missing (no try/except).

**Resolved 2026-04-24** (Handoff 2a Piece 6 — schema drift; Handoff 2a
Piece 3 — error-contract change): ARCHITECTURE_CURRENT.md `arv_model`
row and TOOL_REGISTRY.md `arv_model` block updated to match
README_arv_model.md — outputs now enumerate `arv_snapshot` + nested
`valuation` / `renovation_impact` sub-dicts. Phantom
`estimated_arv` / `arv_confidence` / `comparable_arv_support` /
`component_cost_deltas` fields removed. The "raises ValueError" note
is superseded by the canonical error contract (DECISIONS.md 2026-04-24
"Scoped wrapper error contract"): missing priors now return
`module_payload_from_missing_prior`.

## 2026-04-24 — hold_to_rent output schema mismatch in audit docs

ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md describe `hold_to_rent`
outputs as `hold_to_rent_viability: float` and `cash_flow_metrics: dict`.
The actual implementation is a pure composite wrapper that reads
prior `carry_cost` and `rent_stabilization` outputs and produces a
`hold_path_snapshot` dict (`monthly_cash_flow`, `cap_rate`,
`rental_ease_label`, `rental_ease_score`, `estimated_days_to_rent`)
plus nested `carry_cost` and `rent_stabilization` sub-dicts. No
`hold_to_rent_viability` field exists. The wrapper raises
`ValueError` if either prior output is missing.

**Resolved 2026-04-24** (Handoff 2a Piece 6 — schema drift; Piece 3 —
error-contract): ARCHITECTURE_CURRENT.md `hold_to_rent` row and
TOOL_REGISTRY.md `hold_to_rent` block updated to match
README_hold_to_rent.md — outputs now enumerate `hold_path_snapshot` +
nested `carry_cost` / `rent_stabilization` sub-dicts. Phantom
`hold_to_rent_viability` / `cash_flow_metrics` fields removed. The
"raises ValueError" note is superseded by the canonical error contract.

## 2026-04-24 — Router cache-rule count drift in audit docs

ARCHITECTURE_CURRENT.md ("Four regex cache rules catch explicit
phrasings") and GAP_ANALYSIS.md ("with four regex cache rules in
front") describe four cache rules. The actual implementation in
`briarwood/agent/router.py` has only TWO entries in `_CACHE_RULES`
(stand-alone greeting → CHITCHAT; explicit compare/vs → COMPARISON).
The router file's own docstring at lines 84-88 documents the choice
explicitly: "Removed rules (decision verb, renovation scenario, search
imperative, visualize keyword) are all handled by the LLM prompt." The
audit description also misses the what-if-price-override short-circuit
path at `classify` lines 267-296, which is a separate mechanism (a
price-override parser hit) that bypasses the LLM and routes to
DECISION / RENT_LOOKUP / PROJECTION based on text hints. Update audit
docs to: "Two regex cache rules (greeting, compare/vs) plus a
what-if-price-override short-circuit; everything else is LLM-classified."

**Resolved 2026-04-24** (Handoff 2a Piece 6): ARCHITECTURE_CURRENT.md
Orchestration Layer Router bullet updated to enumerate the two actual
cache rules plus the price-override short-circuit. GAP_ANALYSIS.md
Layer 1 "Current state" paragraph updated to match.

## 2026-04-24 — Dispatch handler count drift in audit docs

ARCHITECTURE_CURRENT.md Orchestration Layer says dispatch holds eight
handler functions: `handle_lookup`, `handle_decision`, `handle_research`,
`handle_projection`, `handle_risk`, `handle_edge`, `handle_strategy`,
`handle_browse`. The actual count is 14 — one per `AnswerType`.
The full list (per `grep -nE '^def handle_[a-z]+' briarwood/agent/dispatch.py`):
`handle_lookup`, `handle_decision`, `handle_search`, `handle_comparison`,
`handle_research`, `handle_visualize`, `handle_rent_lookup`,
`handle_projection`, `handle_micro_location`, `handle_risk`, `handle_edge`,
`handle_strategy`, `handle_browse`, `handle_chitchat`. Update audit docs
to "14 per-AnswerType handler functions" and consider the question of
whether all 14 carry meaningful logic or some are stubs.

**Resolved 2026-04-24** (Handoff 2a Piece 6): ARCHITECTURE_CURRENT.md
Orchestration Layer Dispatch bullet now lists all 14 handlers and
names dispatch as "14 per-AnswerType handler functions." The question
of whether all 14 carry meaningful logic is deferred — open in
FOLLOW_UPS.md (not added in this handoff; flag to user if triage is
desired).

## 2026-04-24 — Audit docs are drifted

ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md contain at least one
confirmed error (CostValuationModule description). Expect more to
surface as Handoff 1 READMEs are written against actual code. Update
the audit docs AFTER Handoff 1 completes — during that pass, walk every
Known Rough Edge, every specialty model description, and every
TOOL_REGISTRY entry against the READMEs and reconcile.

**Resolved 2026-04-24** (Handoff 2a Piece 6): parent entry; nine
specific drift entries above have been reconciled individually.
`ARCHITECTURE_CURRENT.md` and `TOOL_REGISTRY.md` no longer contradict
any README as of end of Handoff 2a.

## 2026-04-24 — Scoped wrapper error contract

**Decision.** Every scoped wrapper in `briarwood/execution/registry.py`
returns a `ModulePayload`-shaped degraded payload on failure — never
raises. Two entry points share one `ModulePayload` shape:

- **Caught internal exception** → `module_payload_from_error(...)` at
  [briarwood/modules/scoped_common.py:114](briarwood/modules/scoped_common.py#L114).
  `mode="fallback"`, `confidence=0.08`, `warnings=["{Module} fallback:
  {ExceptionClass}: {message}"]`. Existing helper — do not duplicate.
- **Missing prior outputs** (composites) → new
  `module_payload_from_missing_prior(module_name, context, missing,
  extra_data=None, summary=None)` also in `scoped_common.py`.
  `mode="error"`, `confidence=None`, `missing_inputs` populated,
  `warnings=["Missing prior module output: {name}", ...]`. Matches
  `opportunity_cost` at
  [briarwood/modules/opportunity_cost.py:59-76](briarwood/modules/opportunity_cost.py#L59-L76)
  verbatim.

Composite wrappers that read priors must treat a prior whose
`mode in {"error","fallback"}` as **missing**, not just type-check the
dict. The `_require_prior_output` helper pattern at
[briarwood/modules/arv_model_scoped.py:100-106](briarwood/modules/arv_model_scoped.py#L100-L106)
is replaced by explicit missing-priors collection followed by the
missing-prior helper call.

**Rationale.** The orchestrator has no fallback on scoped-registry
failure ([briarwood/orchestrator.py:505-514](briarwood/orchestrator.py#L505-L514)
raises `RoutingError` if coverage is incomplete), so any wrapper that
raises brings down the whole analysis pipeline. Downstream synthesis
readers ([briarwood/synthesis/structured.py:301, 374, 396](briarwood/synthesis/structured.py#L301))
already guard with `or {}` / `is not None` / `_float()`, so a degraded
payload with `metrics: {}` flows through as a no-op — the migration is
safe for consumers. Separating exception-fallback (`mode="fallback"`,
`confidence=0.08`) from missing-priors (`mode="error"`,
`confidence=None`) preserves the signal: "we tried, it blew up, here's
a stub" vs. "prior didn't run, no computation occurred." Trust gates
can key on `mode in {"error","fallback"}` uniformly.

**Analysis of the three pre-existing patterns.** (1) Propagate
exceptions — `legal_confidence` ([briarwood/modules/legal_confidence.py:10-74](briarwood/modules/legal_confidence.py#L10-L74))
and `renovation_impact` ([briarwood/modules/renovation_impact_scoped.py:11-28](briarwood/modules/renovation_impact_scoped.py#L11-L28))
have no try/except; any internal raise propagates to the executor and
halts the request. (2) Raise `ValueError` on missing priors — `arv_model`,
`hold_to_rent`, `margin_sensitivity` ([briarwood/modules/arv_model_scoped.py:100-106](briarwood/modules/arv_model_scoped.py#L100-L106),
[briarwood/modules/hold_to_rent.py:71-77](briarwood/modules/hold_to_rent.py#L71-L77),
[briarwood/modules/margin_sensitivity_scoped.py:156-162](briarwood/modules/margin_sensitivity_scoped.py#L156-L162))
raise a typed error that the caller must catch — none do. (3) Return a
degraded payload — `carry_cost` ([briarwood/modules/carry_cost.py:14-36](briarwood/modules/carry_cost.py#L14-L36)),
`valuation`, `resale_scenario`, `rental_option`, `rent_stabilization`
all wrap their body in try/except and call `module_payload_from_error`.
`opportunity_cost` ([briarwood/modules/opportunity_cost.py:54-76](briarwood/modules/opportunity_cost.py#L54-L76))
uses the same shape but with `mode="error"` / `confidence=None` for the
missing-priors case. The canonical shape (pattern 3) is already in
production for 6 of 15 wrappers and has no observed regressions.

**Downstream caller impact.** Zero callers in
`briarwood/synthesis/structured.py` need to change — every reader
already tolerates empty metrics. Composite wrappers
(`arv_model`, `margin_sensitivity`) that read priors need one
additional guard: treat `output.get("mode") in {"error","fallback"}`
the same as "prior missing."

**Canonical-example references.**
- Exception-fallback pattern: [briarwood/modules/carry_cost.py:14-36](briarwood/modules/carry_cost.py#L14-L36).
- Missing-priors pattern: [briarwood/modules/opportunity_cost.py:54-76](briarwood/modules/opportunity_cost.py#L54-L76).
- All scoped wrappers converge on one of these two entry points by
  the end of Piece 3 (see Handoff 2a plan for migration sequence).

**Scope.** Applies to all 9 currently-raising wrappers (see Handoff 2a
Piece 3 classification table): `legal_confidence`, `renovation_impact`,
`arv_model`, `hold_to_rent`, `margin_sensitivity`, `risk_model`,
`confidence`, `unit_income_offset`, `town_development_index`. The
existing 6 canonical wrappers remain unchanged.

## 2026-04-24 — property_data_quality output schema mismatch in audit docs

ARCHITECTURE_CURRENT.md and TOOL_REGISTRY.md (entry at
[TOOL_REGISTRY.md:40-61](TOOL_REGISTRY.md)) describe
`property_data_quality` outputs as `completeness_score: float`,
`contradiction_flags: list[str]`, and `confidence: float`. The actual
implementation at
[briarwood/modules/property_data_quality.py:49-68](briarwood/modules/property_data_quality.py#L49-L68)
produces `property_tax_confirmed_flag`,
`municipality_tax_context_flag`, `reassessment_risk_score`,
`tax_burden_score`, `structural_data_quality_score`,
`comp_eligibility_score`. No `completeness_score` or
`contradiction_flags` fields exist anywhere in the payload. The module
is a NJ-tax-and-comp-eligibility scorer (guarded on optional
`NJTaxIntelligenceStore` via `BRIARWOOD_NJ_TAX_PATH` env var), not a
generic property-data-quality scorer — the name and audit-doc
description both overclaim.

Same drift pattern as the nine entries reconciled in Handoff 2a
Piece 6. TOOL_REGISTRY.md and ARCHITECTURE_CURRENT.md need their
output schema rewritten against the code. Consider whether the module
should also be renamed to reflect its actual role (e.g.,
`nj_tax_quality` or `comp_eligibility`) as a separate follow-up.

Surfaced during Handoff 2b — see [PROMOTION_PLAN.md](PROMOTION_PLAN.md)
entry 5 (`property_data_quality` → KEEP as internal helper).

## 2026-04-24 — PROMOTION_PLAN.md entry 15 scope-limit paragraph corrected

Entry 15 of PROMOTION_PLAN.md deprecates `calculate_final_score` and
its supporting types. The "Scope limit" paragraph claimed that the
per-dimension scoring helpers (`_score_price_vs_comps`,
`_score_ppsf_positioning`, `_score_historical_pricing`,
`_score_scarcity_premium`, `_score_rent_support`,
`_score_carry_efficiency`, `_score_downside_protection`, etc.) had
active callers and should remain.

That claim is factually wrong. Grep verification during Handoff 4
planning found zero production callers for any `_score_*` helper
outside of `calculate_final_score` itself and its sibling
`_calculate_*` category builders. All helpers are reachable only
through the dead aggregator.

Additionally, `lens_scoring.py` in its entirety —
`calculate_lens_scores`, `LensScores`, `LensDetail`,
`_investor_lens`, `_owner_lens`, `_developer_lens`,
`_risk_assessment` — has zero production callers and is dead code.

The entry's "Additional cleanup" directive (retire the $400/sqft
replacement-cost constant) is incompatible with keeping the
`_score_*` helpers, because the constant is consumed only by
`_score_replacement_cost`, which is one of those helpers.

**Corrected scope for Handoff 4 deprecation work:**
Delete the full dead chain — `calculate_final_score`, `FinalScore`,
`CategoryScore`, `SubFactorScore`, `_conviction_adjustment`, all
`_calculate_*` category builders, all `_score_*` helpers EXCEPT
`estimate_comp_renovation_premium` and its utility helpers
(`_get_metrics`, `_get_confidence`, `_get_payload`, `_prop`,
`extract_scoring_metrics`, `_clamp`, `_lerp_score`, `_safe_ratio`)
which are alive via `components.py`. Delete the entirety of
`lens_scoring.py`. Delete `test_decision_model.py` and
`test_scoring_group2.py` which test the dead chain.

Approximate removal: ~2,300 lines across 4 files.

Preserved: `estimate_comp_renovation_premium` and its utility helpers
in `scoring.py` (~200 lines) remain in the file.

This amendment supersedes the "Scope limit" paragraph in
PROMOTION_PLAN.md entry 15 only. The deprecation decision itself is
unchanged.

## 2026-04-24 — PROMOTION_PLAN.md entry 6 decision corrected (bull_base_bear reclassified)

Entry 6 of PROMOTION_PLAN.md classified `bull_base_bear` as DEPRECATE,
citing a code comment at `briarwood/agent/tools.py:1411` that reads
"resale_scenario module (which replaces bull_base_bear under scoped
execution)."

That framing is factually incorrect. Grep verification during Handoff 4
execution found that `briarwood/modules/resale_scenario_scoped.py:30`
invokes `BullBaseBearModule().run(property_input)` as the core of its
implementation. The scoped `resale_scenario` tool does not replace
`bull_base_bear` — it wraps it, adds bounded confidence nudges (macro
HPI-momentum + town_development_index), and returns the result through
the canonical error contract.

Additional live production callers missed by the original entry:
- `briarwood/modules/teardown_scenario.py:111-112` — reads
  `prior_results["bull_base_bear"].metrics` actively
- `briarwood/agent/tools.py:1723` — second fallback arm not in the
  original deprecation list
- `briarwood/runner_routed.py:32, 208, 288, 300, 314, 330` —
  `BullBaseBearSettings` is a parameter across multiple entry-point
  signatures, not just the `:222` tombstone
- `briarwood/eval/model_quality/model_specs.py:24, 109, 113` — eval
  spec instantiates directly
- `tests/test_modules.py:5, 64, 110-111` — direct import and tests

**Corrected classification:** KEEP as internal composition helper.

This pattern matches four other KEEP decisions already in the plan:
`rental_ease` (consumed by `rental_option` and `rent_stabilization`),
`risk_constraints` (consumed by `risk_model`), `property_data_quality`
(consumed by `confidence` and `legal_confidence`), and
`local_intelligence` (consumed by `legal_confidence`). In each case,
the module is not independently tool-shaped; it serves as the
underlying engine for one or more scoped wrappers.

**Handoff 4 scope change:**
- Do not delete `bull_base_bear.py`, `BullBaseBearModule`, or
  `BullBaseBearSettings`.
- Do not migrate `decision_model/scoring.py` or `lens_scoring.py`
  references (those files were deleted in Handoff 4 entry 15; this
  is now moot).
- Do not drop the `tools.py:1427` or `tools.py:1723` fallback arms
  — they remain defensively useful.
- DO correct the misleading comment at `briarwood/agent/tools.py:1411`
  to accurately describe the wrap-not-replace relationship.
- DO update `ARCHITECTURE_CURRENT.md`, `TOOL_REGISTRY.md`, and
  `briarwood/modules/README_resale_scenario.md` to reflect that
  `bull_base_bear` is a KEEP-as-internal-helper, not a deprecation
  candidate.

**Plan tally update:**
- Original: 8 PROMOTE, 4 KEEP, 3 DEPRECATE
- Corrected: 8 PROMOTE, 5 KEEP, 2 DEPRECATE

This amendment supersedes entry 6 of PROMOTION_PLAN.md. The two
completed deprecations from Handoff 4 (`value_finder`,
`calculate_final_score`) are unaffected.

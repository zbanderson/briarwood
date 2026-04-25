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

---

## 2026-04-24 — RouterClassification schema fix — removed `$ref` + `default` sibling conflict

`briarwood/agent/router.py::RouterClassification` was emitting a JSON
schema that OpenAI's `strict: true` mode does not accept on enum-typed
fields with defaults, causing every live query to fall through to the
LOOKUP default. Fixed by removing the Pydantic-side defaults on
`persona_type` and `use_case_type`; the regex fallback at
`_classification_user_type` now handles the missing-classification case
the way the class docstring at `router.py:237` already claims.

### (a) Symptom

Every live query through the chat router came back classified as
`AnswerType.LOOKUP` with `reason="default fallback"` regardless of user
intent. The warning at `router.py:400` (`router fallthrough to LOOKUP
default (client=present, text=…)`) was firing on every turn. Unit tests
passed because `ScriptedLLM`-style fakes constructed
`RouterClassification` via `schema(answer_type=X, reason=Y)` and relied
on the Python-side defaults for `persona_type`/`use_case_type` — a path
the live LLM never takes.

### (b) Root cause

Pydantic v2 renders enum-typed fields as `$ref` pointers into `$defs`.
When such a field also has a default, Pydantic emits the default as a
sibling key alongside `$ref`:

```json
"persona_type": {
  "$ref": "#/$defs/PersonaType",
  "default": "unknown"
}
```

OpenAI's `strict: true` JSON-schema validator follows draft-07 `$ref`
semantics where siblings to `$ref` are ignored or rejected. In practice
the Responses API rejects the schema outright, `responses.create` raises
inside `OpenAIChatClient.complete_structured` at `briarwood/agent/llm.py:149-168`,
the outer `except` returns `None`, and `_llm_classify` exhausts its two
retries the same way. The router's `client-present → LOOKUP` fallthrough
branch runs on every call. The primitive `reason: str = ""` field in the
same model is not affected because primitives inline the default next to
`type` (no `$ref`). The bug is specific to enum fields with defaults —
both `persona_type` and `use_case_type` were newly added in the same
branch that introduced it.

### (c) Why Option 1 (remove defaults) over Option 2 (inline via `Literal`) or Option 3 (`model_validator`)

- **Option 2 — replace `PersonaType` with `Literal["first_time_buyer", …]`
  at the field site.** Would flatten the schema (no `$ref`, so a sibling
  `default` becomes structurally legal) but forks the ontology. The
  Python-side `PersonaType` enum still exists because `UserType` and
  `_infer_user_type_rules` depend on it, and the enum values are already
  repeated in the LLM prompt at `router.py:174-175`. Adding a third copy
  is extra drift surface with no offsetting benefit.

- **Option 3 — `@model_validator(mode='before')` that calls `setdefault`
  on missing keys.** Would remove the schema default (fixing the API
  contract) but re-introduce the silent-coercion behavior the bug was
  masking. The whole point of running `strict: true` is to surface
  partial LLM compliance as a validation failure so the regex fallback
  at `_infer_user_type_rules` takes over. A `setdefault` validator
  launders partial compliance back into "looks compliant," losing that
  signal.

- **Option 1 — remove the field-level defaults.** The only variant that
  simultaneously (i) fixes the emitted JSON schema, (ii) aligns the
  Pydantic contract with what `_force_all_required` at
  `briarwood/agent/llm.py:27-45` already tells OpenAI (every property is
  in `required`), and (iii) lets LLM non-compliance fail loudly so the
  router falls back on the regex rules the code already relies on. The
  only follow-on work is updating two test helpers that constructed
  `RouterClassification` without the new fields (one in
  `tests/test_intent_contract.py`, one in `tests/agent/test_rendering.py`,
  plus the two already in `tests/agent/test_router.py`).

### (d) Process observation — invisible to every prior handoff

The schema bug was merged cleanly through multiple handoffs because no
handoff in that sequence exercised the chat router against a real user
query end-to-end. Every checkpoint relied on the unit-test suite, and
every unit test constructed `RouterClassification` directly from a
scripted LLM that used kwargs — a path that never renders the JSON
schema, never sends it to OpenAI, and never takes the default branch
the bug lived in. The production failure only shows up when
`schema.model_json_schema()` is serialized and posted to `strict: true`,
which happens only during a real provider call.

This is the same class of blind spot catalogued in the 2026-04-24
"Decision sessions should grep-verify caller claims in real time"
entry in FOLLOW_UPS.md — decision-by-reading without mechanical
verification. The analogous lesson for handoff completion: any handoff
that claims to extend the live classifier contract needs a smoke test
that hits the real `complete_structured` path at least once (against a
staged provider, not a mock), because unit mocks cannot exercise the
Pydantic-schema → provider-strict-validation boundary that is exactly
where this bug lived. Cross-referenced as process evidence for that
FOLLOW_UPS entry.

### Fix artefacts

- `briarwood/agent/router.py:242-243` — defaults removed from
  `persona_type` and `use_case_type`.
- `tests/agent/test_router.py` — `ScriptedLLM` and `ChitChatLLM` helpers
  updated to pass the new fields explicitly; regression test
  `test_router_classification_schema_has_no_ref_sibling_defaults`
  added to `LLMClassifyTests`.
- `tests/test_intent_contract.py` — `_ScriptedLLM` updated.
- `tests/agent/test_rendering.py` — `_VisualizeLLM` updated.
- FOLLOW_UPS.md — dated entry for stripping the now-unreachable
  `or PersonaType.UNKNOWN` / `or UseCaseType.UNKNOWN` guards in
  `_classification_user_type` (left in place this commit to keep the
  bug-fix surgical).

Baseline vs. post-fix test delta: 28 pre-existing failures on `main` at
the start of this commit (unrelated to the router); 3 regressions
introduced by Option 1 before the test-helper updates; 0 regressions
after. 14/14 tests in `tests/agent/test_router.py` pass, including the
new regression test. No product-level verification (live query against
the chat router) was performed in this commit — that is the next manual
step under controlled conditions.

---

## 2026-04-25 — README_dispatch.md overstates orchestrator coupling

**Severity:** Medium — misleading for any future handoff trying to plumb
logging, observability, or refactoring through dispatch.

`briarwood/agent/README_dispatch.md` (Last Updated 2026-04-24) claimed
"From dispatch: `briarwood.orchestrator.run_briarwood_analysis_with_artifacts`
(most handlers)" at line 9 and again at lines 41-42. Verified by
`grep -nE "run_briarwood_analysis(_with_artifacts)?\(" briarwood/agent/dispatch.py`:
**zero direct calls**.

The orchestrator runs from exactly two production sites:
- [briarwood/runner_routed.py:228](briarwood/runner_routed.py#L228) — external entry (property pre-computation, batch).
- [briarwood/claims/pipeline.py:42](briarwood/claims/pipeline.py#L42) — inside the claims wedge.

Plus the convenience wrapper at
[briarwood/orchestrator.py:451](briarwood/orchestrator.py#L451) which
internally calls `_with_artifacts`. That's it.

**Implication.** Most chat-tier turns never run the full scoped
orchestration cascade. Chat-tier handlers compose responses by calling
individual functions in `briarwood/agent/tools.py` and rendering with
`briarwood/agent/composer.py`. The orchestrator + scoped synthesizer
runs only when the claims wedge fires (gated by
`BRIARWOOD_CLAIMS_ENABLED`, default `false`, AND only DECISION/LOOKUP
with pinned listing) or when an external caller (batch, pre-computation)
invokes `runner_routed.py`. This contradicts the mental model that the
README sets up — that "dispatch decides what to call; the orchestrator
decides what runs and in what order" — for the chat-tier path that the
README is most often consulted for.

**Resolved 2026-04-25** (output-quality audit handoff): README_dispatch.md
prose updated to describe the actual call topology — handlers as
tools.py-and-composer compositors, with orchestrator invocation
restricted to the wedge and the external runner. Dated changelog entry
appended. Cross-referenced from
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §6.1.

The README is not aspirational. Per project owner directive (2026-04-25,
output-quality audit session): READMEs serve as handoffs between AI
coding agents and must be kept synchronized with the code they describe.
This is the second README correction grounded in grep verification this
month — first was the Handoff 2a Piece 6 audit-doc reconciliations
(see entries above), this one closes the chat-tier dispatch story.

---

## 2026-04-25 — Composer guardrails: independent strip toggle + reframe-licensed regen prompt

**Decision.** Add `BRIARWOOD_STRICT_STRIP` env flag (default ON, preserves
existing AUDIT 1.1.10 behavior) that controls destructive sentence
stripping independently of `BRIARWOOD_STRICT_REGEN`. Master flag stays
the gate — `STRICT_REGEN=0` continues to disable both. Setting
`STRICT_STRIP=0` keeps the strict-regen retry path active but lets the
LLM's prose flow through without mechanical sentence-dropping.

**Rationale.** The strict-regen pipeline at
[briarwood/agent/composer.py:333-486](briarwood/agent/composer.py#L333-L486)
was producing template-echo prose. Two pressures stacked: (1) sentences
with ungrounded numbers were stripped from output, training the LLM
in-context to verbatim-quote `structured_inputs`, and (2) the regen
prompt at lines 313-330 said "rewrite using only values present in the
structured_inputs payload, or numbers you can cite with a marker" —
which forbids re-framing any number-bearing sentence. The composer had
license to paraphrase but not re-frame. The numeric-correctness
guardrail (the half that was actually needed) lived in the verifier and
in the critic's `_numbers_preserved` check; the strip + harsh prompt
were the over-tight components. User-memory entry
`project_llm_guardrails.md` documents the broader directive: loosen LLM
invocation, keep the numeric-logic guardrail.

**Rewritten regen prompt** (composer.py:313-348). The new prompt
explicitly licenses re-framing, paraphrase, and voice choice while
preserving the numeric rule as the only hard constraint. Pinned by
`tests/agent/test_composer.py::RegenPromptLoosenedTests` so it can't
silently revert. The literal "rewrite using only values present in"
wording is gone (asserted absent in
`test_regen_prompt_permits_reframing`).

**Telemetry.** `report["strict_regen"]["strip_enabled"]` field added so
consumers can distinguish "strip ran on dirty draft" from "strip
available but draft was clean." Backward-compatible — existing
`enabled` and `sentences_stripped` keys unchanged.

Tests: 7 new in `tests/agent/test_composer.py`; 40/40 composer suite
green; 280 broader regression green (1 pre-existing slug-zip failure,
same as 2026-04-24 router-fix entry).

Surfaced during 2026-04-25 output-quality audit handoff. Cross-ref
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §3 (robotic prose diagnosis).

---

## 2026-04-25 — Router: 'price analysis' routes to DECISION, not LOOKUP

**Decision.** Update `_LLM_SYSTEM` at
[briarwood/agent/router.py:169-219](briarwood/agent/router.py#L169-L219)
so phrasings that ask for analysis of price (rather than the price as a
single fact) route to `AnswerType.DECISION`. LOOKUP definition tightened
to "single-fact retrieval that needs no analysis or interpretation."
DECISION definition expanded to enumerate the price-analysis trigger
phrases. New IMPORTANT MAPPINGS line and counter-example pair added.

**Live miss that triggered the fix.** "what is the price analysis for
1008 14th Ave, belmar, nj" was classified as LOOKUP (conf 0.60),
routed to `handle_lookup`, which obeyed its "Reply in 1-2 sentences"
prompt and produced "The asking price for 1008 14th Avenue in Belmar,
NJ, is $767,000." User expected analysis; got one fact.

**Why the prompt fix instead of a heuristic.** The router is LLM-first
by design (per the module docstring at
[router.py:11-13](briarwood/agent/router.py#L11-L13)). Adding a regex
for "analysis" would fight the design and accumulate the same
broad-cache drift the cache rules were narrowed to escape (see
2026-04-24 router cache-rule reduction). Fixing the prompt is the
intended evolution path.

**Tests.** 3 new prompt-content regression tests in
`tests/agent/test_router.py::PromptContentRegressionTests` pin the
LOOKUP "single-fact" framing, the DECISION price-analysis enumeration,
and the counter-example pair. 4 new entries in `LLM_CANNED` covering
both DECISION ("price analysis", "analyze the price", "is X priced
right", "how is X priced") and LOOKUP ("what is the asking price")
boundary cases. 17/17 router tests green.

Surfaced during 2026-04-25 output-quality audit handoff. Cross-ref
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md)
and the live-miss trace in
[FOLLOW_UPS.md](FOLLOW_UPS.md) "Audit router classification boundaries".

---

## 2026-04-25 — Per-turn invocation manifest infrastructure

**Decision.** Add a per-turn observability layer at
[briarwood/agent/turn_manifest.py](briarwood/agent/turn_manifest.py).
Aggregates router classification, dispatch choice, wedge outcome,
scoped-module runs, tool calls (`tools.py`), and LLM calls into one
`TurnManifest` per chat turn. Emits a single JSON line to stderr at
turn end when `BRIARWOOD_TRACE=1`. Default off; in-memory record
populated regardless so post-hoc inspection is possible.

**Why this shape.** Briarwood has at least four observability surfaces
(LLM ledger, executor trace, planner skips, ad-hoc print statements)
and they don't compose. The 2026-04-25 audit's #1 finding was that the
user couldn't tell which modules ran for a given chat turn; the
manifest is the merged view. ContextVar-based so async-streaming code
in `api/main.py` and the agent layer can append without plumbing the
manifest through every signature. Read-only outside of an active turn
— all `record_*` helpers no-op when `current_manifest()` is `None`.

**Cross-thread propagation: `in_active_context`.** Python's `ContextVar`
does not propagate across thread-pool boundaries by default, and the
chat-tier streams in `api/pipeline_adapter.py` hand work off via
`loop.run_in_executor(None, dispatch, ...)`. Without explicit
propagation, the manifest's ContextVar is invisible inside `dispatch`
and every `record_*` call inside the worker silently no-ops. The fix:
`in_active_context(fn)` captures the caller's context at decoration
time and returns a wrapped callable that runs `fn` inside that context.
Applied to all 4 `loop.run_in_executor` sites in `pipeline_adapter.py`
and the `pool.map` site in `briarwood/execution/executor.py`. Pinned by
`InActiveContextTests` (4 tests, including a negative-regression test
that confirms the bug exists without the wrapper, so we'll catch it if
Python's executor semantics ever change).

**Hooks landed.**
- LLM ledger (`briarwood/agent/llm_observability.py::LLMCallLedger.append`)
  mirrors each call into the active manifest.
- Scoped executor (`briarwood/execution/executor.py::execute_plan` and
  `_execute_plan_parallel`) record per-module run + skip events with
  duration_ms, mode, confidence, warnings_count, source.
- Wedge (`briarwood/agent/dispatch.py::_maybe_handle_via_claim`) records
  6 distinct outcomes (not-enabled, archetype miss, build raised,
  editor rejected, render raised, success).
- Tools.py — 25 public entry functions decorated with `@traced_tool()`.
- Chat endpoint (`api/main.py::chat`) wraps every turn with
  `start_turn` / `end_turn` plus `record_classification` and
  `record_dispatch`.

**Tests.** 27 in `tests/agent/test_turn_manifest.py` covering
lifecycle, recorders, stderr emission, LLM-ledger integration,
context propagation, and the `traced_tool` decorator.

**Cross-references.** Implements the per-turn manifest from
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §7. Extends the existing in-memory LLM ledger
(`briarwood/agent/llm_observability.py`) — partly addresses
[FOLLOW_UPS.md](FOLLOW_UPS.md) "Add a shared LLM call ledger".

---

## 2026-04-25 — Chat-tier fragmented execution: 5+ plans per turn, 10/23 modules used, 13 never run

**Finding (not yet a fix).** Live trace data from the per-turn manifest
on a BROWSE turn ("what do you think of 1008 14th Ave, Belmar, NJ", 26.3s
total) revealed that chat-tier handlers run **multiple separate
execution plans per turn** rather than one consolidated plan. Each
`tools.py` function (`get_value_thesis`, `get_cma`, `get_projection`,
`get_strategy_fit`, `get_rent_estimate`, `get_property_brief`, etc.)
internally invokes the scoped executor with its own narrow plan. As a
result:

- `valuation` ran 5x (1 fresh + 4 cached) — different tools all needed it
- `carry_cost` ran 5x (1 fresh + 4 cached)
- `risk_model` ran 4x **all fresh** — cache key apparently varies between tools
- `confidence` ran 5x **all fresh**
- `legal_confidence` ran 4x **all fresh**
- 33 total module-execution events, but only **10 distinct modules ran**
- **13 modules never ran for this BROWSE turn:** `arv_model`,
  `comparable_sales`, `current_value`, `hybrid_value`, `income_support`,
  `location_intelligence`, `margin_sensitivity`, `market_value_history`,
  `opportunity_cost`, `renovation_impact`, `scarcity_support`,
  `strategy_classifier`, `unit_income_offset`

**Implication.** `comparable_sales` — the comp engine that drives the
value-vs-fair-value verdict — never fires for chat-tier traffic. Same
for `location_intelligence` (micro-location signals) and
`strategy_classifier` (the module behind `get_strategy_fit` apparently
isn't using it). These dormant modules are exactly the pieces of work
that would distinguish a Briarwood response from plain Claude. The
fragmented per-tool plan structure is the architectural cause.

**Composer LLM did fire.** `composer.draft` ran for 4.08s on this turn —
the audit's wiring map was right that BROWSE calls the composer. But
the composer received a narrow per-tool slice of inputs, not the full
`UnifiedIntelligenceOutput` the deterministic synthesizer would have
populated if the orchestrator had run.

**Hidden LLM call.** `get_property_presentation` (3.0s) almost certainly
calls `presentation_advisor.advise_visual_surfaces` which uses the raw
OpenAI client and bypasses the `complete_structured_observed` wrapper.
That LLM call doesn't appear in the manifest's `llm_calls` list.
Symptom of the same gap as
[FOLLOW_UPS.md](FOLLOW_UPS.md) "Route local-intelligence extraction
through shared LLM boundary."

**Decision.** Treat this as the architectural-fix anchor for the
2026-04-25 audit handoff. Two complementary moves planned (see
[FOLLOW_UPS.md](FOLLOW_UPS.md)):

1. **Consolidate per-tool execution plans into one chat-tier plan per
   turn.** Run the scoped executor *once* per turn with a module-set
   chosen by AnswerType, including `comparable_sales` and
   `location_intelligence` for any property-analysis tier. Eliminates
   the duplicate work and brings dormant modules online.

2. **Layer 3 LLM synthesizer.** Have the composer (or a new synthesis
   LLM step) read the consolidated plan's `UnifiedIntelligenceOutput`
   and write intent-aware prose. Per
   [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 3.

This is the architectural lever that makes Briarwood's modules visible
to the user. Until both land, the system is paying for module work
whose output never reaches the prose. Recorded as the open lever in
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md)
§9.

Cross-ref user-memory note `project_llm_guardrails.md` ("LLM piece is
the missing layer") and the project owner's framing during the audit
session: "if I ask Claude directly to underwrite a house, it shouldn't
be better than the models we've spent a month developing."

---

## 2026-04-25 — Consolidated chat-tier orchestrator entry: `run_chat_tier_analysis`

**Decision.** Add a new orchestrator entry at
[briarwood/orchestrator.py](briarwood/orchestrator.py) that runs ONE
execution plan per chat turn, keyed by the router's `AnswerType`. Module
set is sourced from a new constant
[`briarwood/execution/module_sets.py::ANSWER_TYPE_MODULE_SETS`](briarwood/execution/module_sets.py).
Skips the intent-contract router (the answer_type is already classified
at the chat-tier dispatch layer); synthesizes a minimal `ParserOutput`
from `_CHAT_TIER_DEFAULT_PARSER_BY_ANSWER_TYPE` when callers don't pass
one explicitly. Calls the deterministic synthesizer
(`briarwood.synthesis.structured.build_unified_output`) and returns the
same artifact shape `run_briarwood_analysis_with_artifacts` does, plus
`answer_type`, `modules_run`, `parser_output`, and `skipped_reason`.

**Why this shape.** The 2026-04-25 audit's headline finding (DECISIONS
"Chat-tier fragmented execution") was that a single BROWSE turn produced
33 module-execution events across 5+ separate execution plans — `valuation`
ran 5×, `risk_model` 4× fresh, and 13 modules including `comparable_sales`
and `location_intelligence` never fired at all. The root cause was that
each `tools.py` function (`get_value_thesis`, `get_cma`, `get_projection`,
…) invokes the scoped executor with its own narrow plan. `run_chat_tier_analysis`
replaces that fragmentation with a single intent-keyed plan so every
relevant module's output is co-resident in one `UnifiedIntelligenceOutput`
that the prose layer (Cycle 4 — Layer 3 LLM synthesizer) can read in full.
A separate function (vs. parameter on `run_briarwood_analysis_with_artifacts`)
keeps the chat-tier semantics — deterministic synthesizer, no
intent-contract router, LOOKUP short-circuit — out of the path that
batch / pre-computation callers (`runner_routed.py:228`) take. Live BROWSE
smoke at landing time produced 23 distinct modules in `modules_run`, each
running exactly once.

**LOOKUP / non-cascade tiers.** `LOOKUP`, `SEARCH`, `COMPARISON`, `RESEARCH`,
`VISUALIZE`, `MICRO_LOCATION`, and `CHITCHAT` are intentionally absent from
`ANSWER_TYPE_MODULE_SETS`. The function returns an early-skip artifact with
`skipped_reason="no_cascade_for_answer_type"`; callers (Cycle 3 dispatch
handlers) branch on it. LOOKUP is single-fact retrieval and does not
benefit from a property cascade; the others have their own non-cascade
flows.

**Parallel execution deferred.** The function ships with `parallel=False`
default. The parallel path's `in_active_context` wrapper at
[briarwood/agent/turn_manifest.py:332-336](briarwood/agent/turn_manifest.py#L332-L336)
captures `ctx = contextvars.copy_context()` once at decoration time, then
shares that single Context across pool workers — concurrent `ctx.run`
calls fail with `RuntimeError: cannot enter context: <Context> is already
entered`. Surfaced when `pool.map(in_active_context(_run_one), level)` was
called with a level containing multiple independent modules. The bug is
not exercised by any current production caller because
`loop.run_in_executor(None, fn)` only fires one call per wrapped
function. Tracked as the FOLLOW_UPS entry "in_active_context is not safe
under concurrent thread-pool callers" 2026-04-25; flip the default once
that wrapper is concurrent-safe.

**Module-set tuning.** The starting sets in `module_sets.py` mirror the
plan's text (BROWSE / DECISION → all 23 scoped modules; PROJECTION,
RISK, EDGE, STRATEGY, RENT_LOOKUP each get an intent-keyed subset). They
are starting points to tune with traces, not a fixed contract — the
docstring says so and tests assert subset membership rather than exact
equality so additions don't break.

**Tests.** 8 new in `tests/test_orchestrator.py::RunChatTierAnalysisTests`:
BROWSE runs the full first-read set; PROJECTION runs only its subset;
RISK runs only its subset; LOOKUP and CHITCHAT short-circuit; each
module appears at most once per turn (the no-duplication invariant);
explicit `parser_output` overrides the synthesized default; synthesized
parser_output carries the correct intent / depth / question_focus.

**Cross-references.** Implements step 2 of FOLLOW_UPS.md "Consolidate
chat-tier execution: one plan per turn, intent-keyed module set"
2026-04-25. Cycle 2 of [OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md).
Architectural-fix anchor recorded in
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §9.7.

---

## 2026-04-25 — Layer 3 LLM synthesizer: prose from full UnifiedIntelligenceOutput

**Decision.** Add a Layer 3 LLM synthesizer at
[briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py)
that reads a fully-populated ``UnifiedIntelligenceOutput`` (the
substrate Cycle 2/3 puts in place) and the user's intent contract,
then writes 3-7 sentences of intent-aware prose. Wired into
``handle_browse`` 2026-04-25 (Cycle 4 of OUTPUT_QUALITY_HANDOFF_PLAN.md,
commit ``fb23152``); replaces ``compose_browse_surface`` on the happy
path, falls back to it when the synthesizer returns empty.

**Why this shape.** GAP_ANALYSIS.md Layer 3 names the missing piece
explicitly: "An LLM that reads the intent contract plus the
aggregated module outputs and either declares intent-satisfied and
passes to Representation, or declares gaps." The 2026-04-25 audit's
§9.4 pinned the diagnosis: the existing composer (``composer.draft``)
saw a narrow ``_browse_surface_payload`` slice (~7 fields from the
brief plus 4 session view dicts) rather than the full
``UnifiedIntelligenceOutput`` Briarwood's deterministic synthesizer
populates. Cycle 2 produced the full output; Cycle 3 wired
``handle_browse`` to a single consolidated execution plan; Cycle 4 is
the prose-layer companion that finally lets the LLM see what the
deterministic models computed.

**Free voice + numeric grounding.** The synthesizer's system prompt
applies the same guardrail-loosening principle as DECISIONS.md
"Composer guardrails: independent strip toggle + reframe-licensed
regen prompt" 2026-04-25 — explicit license to re-frame, paraphrase,
choose voice, with numeric grounding as the only hard rule. Numbers
cited must round to a value present in the unified output; verifier
runs ``api.guardrails.verify_response`` over the full unified output
as ``structured_inputs``. On threshold-level violations a single
regen attempt fires with the offending values named; regen is kept
only when violations strictly decrease.

**Observability.** The synthesizer's LLM call lands at surface
``synthesis.llm`` in the per-turn manifest's ``llm_calls`` list,
distinct from ``composer.draft`` and ``agent_router.classify``. The
regen attempt (when it fires) lands at ``synthesis.llm.regen``.
Metadata carries ``tier=synthesis_llm`` and the ``answer_type``.

**Why a separate module instead of extending the composer.** The
composer at [briarwood/agent/composer.py](briarwood/agent/composer.py)
has accumulated provider routing (`_resolve_llm_for_tier` swapping
Anthropic for narrative tiers), critic infrastructure, the strict
strip / regen flag pair, and tier-specific behaviors. The Layer 3
synthesizer is a tighter, focused tool: one LLM call, verify, regen,
strip markers. Reusing the composer would have meant threading a new
`surface` parameter through `_run_llm_with_verify`,
`compose_structured_response`, and `compose_contract_response` and
inheriting all the composer's tier-specific complexity for a tier
that doesn't need it. Cycle 4 ships it as a small standalone module
(~200 LOC) so the contract stays inspectable and the surface name
remains clean.

**Fallback contract.** ``handle_browse`` calls the synthesizer when
both ``chat_tier_artifact`` is populated AND ``llm`` is non-None.
When the synthesizer returns empty prose (budget cap, blank draft,
exception, verifier blocked everything), ``compose_browse_surface``
fires as the fallback. The user always sees a response — empty
synthesizer output never leaks to the UI.

**Out of scope (deferred).**
- Per-tier system prompt variations. Cycle 4 ships one prompt that
  branches via the intent contract's ``answer_type`` /
  ``core_questions``. Per-tier prompts may land later if traces show
  uneven prose quality across tiers.
- Anthropic provider routing for the synthesis tier. Easy add when
  the user wants it; for now uses whatever ``llm`` the caller passes.
- Wedge interaction. When ``BRIARWOOD_CLAIMS_ENABLED=true`` and a
  DECISION turn produces a ``VerdictWithComparisonClaim`` via the
  wedge, the existing claim renderer continues to handle prose.
  Layer 3 fills the gap for the non-wedge chat-tier paths
  (BROWSE today; DECISION fall-through, RISK, EDGE, STRATEGY,
  PROJECTION, RENT_LOOKUP after Cycle 5).

**Tests.** 10 new in
[tests/synthesis/test_llm_synthesizer.py](tests/synthesis/test_llm_synthesizer.py)
covering clean draft pass-through, ledger metadata, regen-on-ungrounded,
regen-kept-only-when-better, missing-llm short-circuit, empty-unified
short-circuit, blank LLM response, swallowed exception, intent payload
serialization, and a system-prompt regression for the numeric grounding
rule. 2 new integration tests in
``tests/agent/test_dispatch.py::BrowseHandlerTests`` pin the dispatch
contract: synthesizer prose replaces composer when artifact + llm
present; composer fallback fires when synthesizer returns empty.

**Cross-references.** Cycle 4 of
[OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md);
GAP_ANALYSIS.md Layer 3 target description; FOLLOW_UPS.md "Layer 3
LLM synthesizer: prose from full UnifiedIntelligenceOutput" 2026-04-25
(this DECISION resolves that follow-up's design questions).

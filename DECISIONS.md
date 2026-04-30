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
ROADMAP.md (not added in this handoff; flag to user if triage is
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
entry in ROADMAP.md — decision-by-reading without mechanical
verification. The analogous lesson for handoff completion: any handoff
that claims to extend the live classifier contract needs a smoke test
that hits the real `complete_structured` path at least once (against a
staged provider, not a mock), because unit mocks cannot exercise the
Pydantic-schema → provider-strict-validation boundary that is exactly
where this bug lived. Cross-referenced as process evidence for that
ROADMAP entry.

### Fix artefacts

- `briarwood/agent/router.py:242-243` — defaults removed from
  `persona_type` and `use_case_type`.
- `tests/agent/test_router.py` — `ScriptedLLM` and `ChitChatLLM` helpers
  updated to pass the new fields explicitly; regression test
  `test_router_classification_schema_has_no_ref_sibling_defaults`
  added to `LLMClassifyTests`.
- `tests/test_intent_contract.py` — `_ScriptedLLM` updated.
- `tests/agent/test_rendering.py` — `_VisualizeLLM` updated.
- ROADMAP.md — dated entry for stripping the now-unreachable
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
[ROADMAP.md](ROADMAP.md) "Audit router classification boundaries".

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
[ROADMAP.md](ROADMAP.md) "Add a shared LLM call ledger".

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
[ROADMAP.md](ROADMAP.md) "Route local-intelligence extraction
through shared LLM boundary."

**Decision.** Treat this as the architectural-fix anchor for the
2026-04-25 audit handoff. Two complementary moves planned (see
[ROADMAP.md](ROADMAP.md)):

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
function. Tracked as the ROADMAP entry "in_active_context is not safe
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

**Cross-references.** Implements step 2 of ROADMAP.md "Consolidate
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
GAP_ANALYSIS.md Layer 3 target description; ROADMAP.md "Layer 3
LLM synthesizer: prose from full UnifiedIntelligenceOutput" 2026-04-25
(this DECISION resolves that follow-up's design questions).

---

## 2026-04-25 — Cycle 5: roll Layer 3 synthesizer to all chat-tier handlers

**Decision.** The Cycle 3+4 pattern (consolidated chat-tier artifact +
Layer 3 LLM synthesizer) wires into all six chat-tier handlers that
have a property cascade: `handle_browse` (Cycle 3+4), plus
`handle_projection` (commit `1f8ab6a`), `handle_risk` (`6b861e9`),
`handle_edge` default path (`d3293a1`), `handle_strategy`
(`3811dbf`), `handle_rent_lookup` (`c589635`), and `handle_decision`
fall-through (`a429d88`). Generalized
`_browse_chat_tier_artifact` to `_chat_tier_artifact_for(pid, text,
overrides, answer_type)` so each handler picks its tier's module set
from
[briarwood/execution/module_sets.py::ANSWER_TYPE_MODULE_SETS](briarwood/execution/module_sets.py).

**Pattern across all six handlers.** Each handler calls
`_chat_tier_artifact_for(...)` after pid resolution and overrides
extraction. When the artifact is populated, per-tool view reads
project from the artifact via existing helpers
(`_browse_projection_from_artifact`, `_browse_strategy_fit_from_artifact`,
`_browse_rent_payload_from_artifact`, `_browse_risk_profile_from_artifact`).
When `None`, legacy per-tool calls fall through. The final composer
call swaps to `synthesize_with_llm` first; tier-specific composers
(`projection`, `risk`, `edge`, `strategy`, `rent_lookup`,
`decision_summary`) become fallbacks.

**Section followups intentionally NOT swapped to the synthesizer.**
The `compose_section_followup` paths (trust mode in `handle_risk`,
downside mode, comp_set / entry_point / value_change in `handle_edge`,
rent_workability in `handle_rent_lookup`) keep their narrow-payload
composer calls. Those are surgical section-specific generations — the
user has already seen the full property prose and is asking a tight
follow-up question. Feeding the full unified output would distract
from the section's specific question. Worth revisiting if traces
show those followup paths producing thin or repetitive prose.

**handle_decision is minimum scope.** The wedge fall-through still
calls PropertyView.load + get_cma + get_projection + get_risk_profile
+ get_strategy_fit + get_rent_estimate. They now all hit the module
cache thanks to the artifact pre-load (the consolidated plan runs
upfront and warms `_SCOPED_MODULE_OUTPUT_CACHE`), so the duplicate
runs are gone, but the call sites themselves remain. Replacing them
with artifact-derived view builders is a separate refactor —
deferred to Cycle 6 cleanup. The wedge interaction
(`BRIARWOOD_CLAIMS_ENABLED`) is unchanged: when the wedge fires and
produces a `VerdictWithComparisonClaim`, the claim renderer still
handles prose.

**Cross-turn module caching.** Live UI traces post-Cycle-5 show that
consecutive BROWSE turns on the same property hit cache for ~20 of 23
modules (only the three known-leaky-cache modules — `confidence`,
`legal_confidence`, `risk_model` — re-run fresh, per ROADMAP.md
"Module-result caching at the per-tool boundary is leaky" 2026-04-25).
Wall-time gain on follow-up BROWSE turns: ~7s vs cold-cache. This is
a positive emergent property of the consolidation — the same
`_SCOPED_MODULE_OUTPUT_CACHE` that warms within a turn now warms
across turns when handlers all use the same consolidated path.

**Phase 2 of OUTPUT_QUALITY_HANDOFF_PLAN.md is functionally complete.**
The audit's headline gap (33 events / 10 distinct / 13 dormant for a
single BROWSE turn) is now ≤23 distinct, 0 dormant, 0 duplicates per
turn. All chat-tier handlers consolidate. Layer 3 LLM synthesizer
fires across the board. Numeric guardrail enforced via the verifier.
The two pieces remaining (Cycle 6 cleanup) are
`presentation_advisor` LLM observability and a tools.py orphan sweep
— both small, neither user-visible.

**Tests.** 79/79 in `tests/agent/test_dispatch.py`; 513 passed in
broader smoke (10 new synthesizer tests, plus +2 from the Cycle 4
synthesizer integration tests, plus +2 from the projection tests).
Two pre-existing failures unchanged from session start.

**Cross-references.** Cycle 5 of
[OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md);
the Cycle 4 entry above (which describes the synthesizer itself);
ROADMAP.md "Consolidate chat-tier execution" 2026-04-25 step 3
(which this resolves).

---

## 2026-04-25 — `get_cma` thesis-passthrough breaks the chat-tier leak

**Decision.** `get_cma` (Engine B, the user-facing live-Zillow CMA
contract) gains an optional keyword-only `thesis: dict[str, Any] | None`
parameter at [briarwood/agent/tools.py:1829](briarwood/agent/tools.py#L1829).
When provided (chat-tier callers like `handle_browse` post-Cycle-3),
the internal `get_value_thesis` call is skipped — the caller has
already paid for the routed analysis and the same fields can be
projected from the consolidated artifact. Default behavior
(`thesis=None`) is unchanged for the per-tool callers under
`handle_decision` / `handle_edge` that still use the per-tool routed
pattern (they will get the thesis-pass-through wired in once their
respective rewires graduate to the full handler refactor in Cycle 6+).

**Rationale.** Cycle 3's manifest cleanup surfaced 5 trailing
duplicate module runs after the consolidated plan finished
(`valuation`, `risk_model`, `confidence`, `legal_confidence`,
`carry_cost`). Traced to `get_cma` calling `get_value_thesis` at
[tools.py:1832](briarwood/agent/tools.py#L1832), which kicks off its
own `run_routed_report` despite all six required thesis fields
already living in `chat_tier_artifact["unified_output"]["value_position"]`
plus the `valuation` module's metrics. The simplest fix that
preserves Engine B's contract: accept a pre-computed thesis dict.
`handle_browse` builds it via the new
`_browse_thesis_from_artifact` helper and passes through.

**Out of scope.** The broader `valuation`-module cache-miss audit
(why does `valuation` re-run fresh in the routed `get_value_thesis`
path even when property structural fields are identical to the
chat-tier path?) was deferred. Once `handle_browse` no longer
triggers the duplicate, the audit's value drops to "diagnostic
curiosity unless we re-enable per-tool routed runs." Worth noting
for whoever picks up the broader `MODULE_CACHE_FIELDS` cleanup
item.

**Tests.** New regression test
`tests/agent/test_tools.py::ContractToolTests::test_get_cma_skips_internal_value_thesis_when_caller_provides_thesis`
verifies `get_value_thesis` is NOT called when a thesis is passed.

**Cross-references.** ROADMAP.md "`get_cma` internally calls
`get_value_thesis`, leaking 5 module re-runs into the chat-tier path"
2026-04-25 (step 1 resolved). Surfaced during Cycle 3 (`ca94d2f`)
post-landing UI smoke; resolved in commit `f018fc4` between Cycles 4
and 5.

---

## 2026-04-25 — Phase 3 (presentation layer) kicks off — PRESENTATION_HANDOFF_PLAN.md

**Decision.** Phase 2 ([OUTPUT_QUALITY_HANDOFF_PLAN.md](OUTPUT_QUALITY_HANDOFF_PLAN.md))
closed the architectural / substrate gap. Phase 3 targets the
*presentation layer* — chart visual quality, intent-aware chart
selection, LLM-narrated charts, and front-page-newspaper prose voice.
Tracked in [PRESENTATION_HANDOFF_PLAN.md](PRESENTATION_HANDOFF_PLAN.md)
at the repo root.

**Why now.** Live UI smoke 2026-04-25 confirmed Phase 2's work:
manifest cleanup, synthesizer firing, prose substantively richer, no
duplicate runs. User feedback the same session was direct: charts
"look like something that isn't being designed by a user rather than
by an LLM" — no axis titles, no chart titles, no legends. Prose still
reads as a "string of characters" rather than a hook. The substrate
is in place; the presentation layer needs to catch up.

**North-star problem statement** (from the plan): "Every Briarwood
response should land like the front page of a newspaper — visually
rich, intent-tight, narrative-led — so the user keeps reading and
keeps clicking."

**Cycle order** (locked 2026-04-25 in conversation): Polish → Select
→ Narrate → Prose. Cycle A (chart visual polish) is fastest visible
win. Cycle B (intent-keyed selection + new `market_trend` chart) is
the highest-leverage substrate addition. Cycle C (LLM-narrated
charts) ties chart and prose together. Cycle D (newspaper-voice
prose) is the final voice tune.

**Key design pre-decisions** (recorded in the plan's "Open design
decisions" but worth surfacing here):

1. **Town-level ZHVI is verified to work** for the `market_trend`
   chart — `market_value_history` agent prefers town-level
   (`geography_type = "town"`) and falls back to county (line 45 of
   `briarwood/agents/market_history/agent.py`). Live UI smoke
   confirmed `confidence: 1.0` for Belmar (town-level). The chart
   plumbing works without new module work.
2. **Selection cap drops from 6 → 3** for first-impression turns
   (BROWSE / decision_summary). The kitchen-sink feel was the user's
   #2 complaint after visual polish.
3. **Markdown headers in synthesizer prose** (Cycle D) — keep the
   verifier's free-text grounding logic intact; instruct the LLM to
   produce literal markdown structure ("## Headline", "## Why", "##
   What's Interesting", "## What I'd Watch") rather than moving to a
   structured Pydantic response.

**Drift prevention.** The plan lives at the repo root parallel to
`OUTPUT_QUALITY_HANDOFF_PLAN.md`. Cross-referenced from this entry
and from `ROADMAP.md` so future agents discover it via the
standard CLAUDE.md orientation flow.

**Cross-references.** [PRESENTATION_HANDOFF_PLAN.md](PRESENTATION_HANDOFF_PLAN.md)
(canonical scope); [GAP_ANALYSIS.md](GAP_ANALYSIS.md) Layer 4
(Representation Agent target description);
[AUDIT_OUTPUT_QUALITY_2026-04-25.md](AUDIT_OUTPUT_QUALITY_2026-04-25.md) §4
(the audit's "Charts don't explain" diagnosis).

## 2026-04-27 — AI-Native Foundation precedes Phase 4b (Scout)

**Decision.** The AI-Native Foundation umbrella —
[`ROADMAP.md`](ROADMAP.md) Stages 1-3 (artifact
persistence, user-feedback loop closure, business-facing dashboard) —
runs **before** Phase 4b (Scout buildout per
[`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)). Stage 4 (model-accuracy
loop closure) runs after Scout.

**Rationale.** Scout is the apex of the product (per the user-memory
note `project_scout_apex.md` and the 2026-04-26 owner direction folded
into [`ROADMAP.md`](ROADMAP.md)). Building Scout against a
substrate that has (a) persisted per-turn artifacts to mine, (b) a
closed user-feedback signal to learn from, and (c) a dashboard surface
where Scout's own outputs can be measured produces a materially better
Scout. Without Stages 1-3, every Scout iteration leaves no inspectable
trace and no mechanism for the user to signal whether the surfaced
insight was useful — exactly the failure mode the AI-native principles
in [`design_doc.md`](design_doc.md) § 3.4 are written to prevent.

The owner explicitly chose "Docs + roadmap only" as the scope of this
foundation handoff, with sequencing "Before Scout" — so this entry
records the sequencing call rather than introducing it.

**Cost.** One-handoff Scout deferral. Stages 1-3 are estimated at three
focused handoffs (one each); Scout slots in after Stage 2 or Stage 3
depending on signal at that point. The Scout substrate (`rent_zestimate`
from CMA Cycle 3a, per `ROADMAP.md`) is already landed and is not
disturbed by this sequencing.

**Reversibility.** Each stage of `ROADMAP.md` is independently
approvable; if Scout signal becomes urgent mid-roadmap, any in-flight
stage can be paused and Scout pulled forward. The principles in
[`design_doc.md`](design_doc.md) § 3.4 are load-bearing regardless of
sequencing — they constrain Scout's design either way.

**Cross-references.** [`ROADMAP.md`](ROADMAP.md)
(staged buildout); [`design_doc.md`](design_doc.md) § 3.4 (the
principles being operationalized); [`design_doc.md`](design_doc.md) § 7
(the dual feedback loops being closed); [`ROADMAP.md`](ROADMAP.md)
2026-04-27 umbrella entry "AI-Native Foundation";
[`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md) (the deferred handoff).

---

## 2026-04-28 — AI-Native Foundation Stage 1 landed: persistence, JSONL sink, message metrics

**Decision.** AI-Native Foundation Stage 1 (§3.1 of [`ROADMAP.md`](ROADMAP.md))
landed via [`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md)
Cycles 1-4. Three artifacts now persist by default for every chat
turn: the new `turn_traces` table in
[`data/web/conversations.db`](api/store.py), the new
`data/llm_calls.jsonl` JSONL sink, and four metric columns on the
existing `messages` table (`latency_ms`, `answer_type`, `success_flag`,
`turn_trace_id`). All three write paths are exception-safe with
`[turn_traces]` / `[llm_calls.jsonl]` / `[messages.metrics]` prefix
logs on failure — observability never breaks a turn. See
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) §"Persistence" for
the system-level shape.

**Four deviations from the plan, recorded for archaeology.**

1. **Failure-swallow lives inside the methods, not at the call site.**
   The plan sketched `try/except` wrappers at each `api/main.py` call
   site (Cycle 1 Scope, Cycle 3 Scope) but also said in §"Failure
   semantics" that "every persistence write is wrapped in `try: ...
   except Exception:`." Resolved by putting the try/except inside
   `insert_turn_trace`, `attach_turn_metrics`, and `_write_jsonl` so
   the call sites stay simple and future callers (Cycle 4 smoke
   matrix, Stage 3 admin scripts) inherit the same safety. Same
   observable behavior, single layer of defense instead of two. The
   prefix log convention (`[turn_traces]`, `[llm_calls.jsonl]`,
   `[messages.metrics]`) is preserved verbatim.

2. **Test files live at `tests/test_api_*.py`, not `tests/api/`.** The
   plan called for `tests/api/test_turn_traces.py` and
   `tests/api/test_messages_metrics.py`. Discovered at first test run
   that `tests/api/__init__.py` shadows the top-level `api/` package
   on import — Python resolves `from api.store import ...` to the
   empty test directory and fails with `ModuleNotFoundError`. The
   repo's existing convention is flat (`tests/test_chat_api.py`,
   `tests/test_api_strategy.py`); switched to `tests/test_api_turn_traces.py`
   and folded all messages-metrics tests into the same file. Five new
   tests in Cycle 1 (round-trip + minimal + db-error swallow + finalize
   path + delete-cascade), five in Cycle 2 (JSONL write + payload
   exclusion default + payload included on flag + write-error swallow
   + manifest-mirror regression), four in Cycle 3 (idempotent schema +
   metrics update + missing message + assistant-only metrics). Total
   14 new tests; suite delta 1496 → 1510 passed, 16 failures unchanged
   (all pre-existing).

3. **Added `tests/conftest.py` to redirect the JSONL during test runs.**
   Not in plan. Without it, every test that exercises an LLM mock
   would write to the real `data/llm_calls.jsonl` — corrupting the
   very observability artifact this stage is trying to make
   trustworthy. The `pytest_sessionstart` hook in
   [tests/conftest.py](tests/conftest.py) sets
   `BRIARWOOD_LLM_JSONL_PATH` to a per-session tmp file; tests can
   still override per-function via `monkeypatch.setenv`. Defense in
   depth: also added `data/llm_calls.jsonl` to `.gitignore` so any
   stray writes don't reach commits.

4. **`messages.success_flag` semantic locked to v1 (a).** Per the
   plan's open design decision #2, three options were offered: (a)
   manifest reached `end_turn` without exception, (b) no
   `events.error(...)` emitted during the stream, (c) user followed
   up positively. Locked to (a) — easiest to populate, ~always True
   under normal flow. Deliberately revisitable when Stage 2 (user
   feedback loop) lands and option (c) becomes implementable.

**Why these all stayed in scope.** Each deviation was a quality call
in service of the same outcome: the artifacts must be trustworthy from
day one (test pollution → conftest), the failure semantics convention
must be uniformly applied (single-layer swallow), the test discovery
must just work (flat filenames), and the success_flag must be honest
about what it currently measures (locked to (a) explicitly so it can
be widened later without a silent semantic shift).

**Manual verification gate deferred.** The plan's success criteria
include "chat one turn end-to-end, then run `sqlite3 ... 'SELECT
turn_id, answer_type, duration_ms_total, json_array_length(modules_run)
FROM turn_traces ORDER BY started_at DESC LIMIT 1'`" plus the smoke
matrix across BROWSE / DECISION / LOOKUP / EDGE / RESEARCH /
RENT_LOOKUP / CHITCHAT. Auto-mode handoff did not drive a browser
session; deferred to next live UI smoke.

**Cross-references.** [`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md)
(canonical scope); [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md)
§"Persistence" (system-level shape post-landing);
[`ROADMAP.md`](ROADMAP.md) §3.1 Stage 1 (closeout entry with `✅`
prefix and `**Status:**` line); [`ROADMAP.md`](ROADMAP.md) §10 Resolved
Index rows 6, 7, 8.

---

## 2026-04-28 — Router classification audit Cycle 1-4 landed

**Decision.** Audit-against-corpus work for the §4 ROADMAP entry
*"2026-04-25 — Audit router classification boundaries with real
traffic"* landed via [`ROUTER_AUDIT_HANDOFF_PLAN.md`](ROUTER_AUDIT_HANDOFF_PLAN.md)
Cycles 1-4 on 2026-04-28. Stage 1's `turn_traces` provided the corpus
the entry was waiting on. Two artifacts changed: `_LLM_SYSTEM` in
[`briarwood/agent/router.py`](briarwood/agent/router.py) (prompt
expansion) and `_COMP_SET_RE` in
[`briarwood/agent/dispatch.py`](briarwood/agent/dispatch.py) (regex
widening). 14 new tests; suite delta +14 passes; 16 pre-existing
failures unchanged.

**The corpus** (Cycle 1 — read-only).

| # | Text | Was | Should be | Source |
|---|------|-----|-----------|--------|
| 1 | "Why were these comps chosen?" (pinned) | RESEARCH | EDGE | ROADMAP 2026-04-25 |
| 2 | "show me the comps" (pinned) | BROWSE | EDGE | ROADMAP 2026-04-26 |
| 3 | "Show me listings here" | BROWSE | SEARCH | ROADMAP 2026-04-25 |
| 4 | "Walk me through the recommended path" (pinned) | BROWSE | STRATEGY | turn_traces 2026-04-28 |
| 5 | "What would change your value view?" (pinned) | RISK | EDGE | turn_traces 2026-04-28 |

Plus 8 synthetic boundary cases pinned in `LLM_CANNED` /
`PromptContentRegressionTests` to harden against future prompt edits.

**The five prompt edits** (Cycle 2):
1. STRATEGY definition expansion — escalation phrasings added
   ("recommended path", "walk me through", "what should I do here",
   "next move", "what's the play", "how should I approach this").
2. EDGE definition expansion — sensitivity / counterfactual phrasings
   added ("what would change your view", "what would shift the
   number", "how sensitive is X", "what assumption is load-bearing",
   "what if X were different") AND comp-set follow-ups ("show me the
   comps", "list the comps", "what are the comps", "why were these
   comps chosen", "explain your comp choice").
3. SEARCH definition expansion — list/show-imperative phrasings naming
   plural inventory artifacts ("show me listings here", "list the
   properties", "what is available") with explicit guard "(NOT 'show
   me the comps' — see edge.)" so comp-set phrasings stay in EDGE.
4. RISK definition tightened — explicit "RISK enumerates downside
   factors; it does NOT cover sensitivity / counterfactual questions
   (those are edge)" sentence so the LLM doesn't drag sensitivity
   questions in by default.
5. 3 new IMPORTANT MAPPINGS lines + 2 new counter-example pairs
   (BROWSE↔STRATEGY escalation boundary, RISK↔EDGE downside vs
   sensitivity boundary).

**The regex widening** (Cycle 3). `_COMP_SET_RE` at
[briarwood/agent/dispatch.py:2720-2727](briarwood/agent/dispatch.py#L2720-L2727)
now also catches "show me the comps", "list the comps", "what are the
comps", "what comps did you use", "why were the comps", "explain your
comp choice / selection / comps". Negative case ("the comparable sales
market in Belmar" — town context, NOT comp-set followup) pinned in the
dispatch test so future widening doesn't drag market-research turns
into EDGE.

---

### Guardrail Review (per `project_llm_guardrails.md` directive)

The user-memory entry says *"Loosen LLM invocation broadly; perfect
product first, optimize cost later. Numeric guardrail stays. Flag any
guardrail holding back quality."* Walking the router path:

| # | Guardrail | Location | Restricting quality? | Action |
|---|-----------|----------|----------------------|--------|
| 1 | LLM `max_attempts=2` | [router.py:319](briarwood/agent/router.py#L319) | No — two tries handles transient transport failures cleanly. | Keep. |
| 2 | LLM `max_tokens=120` | [router.py:324](briarwood/agent/router.py#L324) | No — output is `answer_type` + 3 enum fields + a short reason; 120 is comfortable. | Keep. |
| 3 | `RouterClassification` `extra="forbid"` strict schema | [router.py:253](briarwood/agent/router.py#L253) | No — strict mode catches LLM non-compliance loudly so the regex fallback can take over. | Keep. |
| 4 | **`confidence=0.6` hardcode on every LLM-classified turn** | [router.py:407](briarwood/agent/router.py#L407) | **YES** — every successful classification gets the same 0.6 regardless of model signal. Every miss in the 2026-04-28 corpus came back at exactly `conf=0.60` for this reason. The classifier's actual confidence is invisible downstream. Defeats Stage 3's planned "low-confidence drill-down." | **Filed as new ROADMAP §4 Medium entry "Router LLM `confidence=0.6` cap collapses classifier signal" 2026-04-28.** Out of scope for this handoff (Cycles 1-4 were prompt + regex only); ~30-min fix when next in the file. |
| 5 | `CHITCHAT → BROWSE` post-LLM coercion | [router.py:333-334](briarwood/agent/router.py#L333-L334) | No — catches a known LLM failure mode (substantive question dumped in CHITCHAT) without masking the real signal. | Keep. |
| 6 | `_CACHE_RULES` short-circuit before LLM | [router.py:114-139](briarwood/agent/router.py#L114-L139) | No — narrow + high-precision (greetings, compare/vs only). | Keep. |
| 7 | Price-override short-circuit before LLM | [router.py:371-400](briarwood/agent/router.py#L371-L400) | No — requires a concrete price token via `parse_overrides`; the path is deterministic and rarely fires on ambiguous turns. | Keep. |
| 8 | Default fallback to LOOKUP at `conf=0.3` | [router.py:419-425](briarwood/agent/router.py#L419-L425) | No — last-resort safety net when LLM and cache both fail. | Keep. |
| 9 | `BRIARWOOD_LLM_RESPONSE_CACHE` env-gated cache | [llm_observability.py:152-156](briarwood/agent/llm_observability.py#L152-L156) | Off by default — not currently restricting. WOULD be a problem if turned on with a stale prompt; the cache key includes prompt hash so the new prompt invalidates old entries. | Keep gated; document cache-key behavior if anyone ever turns it on. |

**Net finding from the guardrail walk:** one real restriction (#4),
filed as a follow-on. Everything else is intentional and defensible.

---

**Three plan deviations, recorded for archaeology.**

1. **Cycle 1's corpus aggregation lives in this entry, not in a
   separate file.** The plan called for a "in-PR-comment / in-DECISIONS
   table"; landed in DECISIONS — same outcome, lower file-count.
2. **One regression test failed initially due to a tense mismatch**
   ("escalation from first-read" vs the prompt's "escalated from
   first-read"). Fixed in the test; wording in the prompt kept as
   "escalated" (more natural in context). Recorded so future grep on
   "escalation" still finds the boundary marker.
3. **The `_COMP_SET_RE` regex deliberately does NOT widen to bare
   "the comparable sales"** — that phrase shows up in market-research
   contexts ("the comparable sales market in Belmar"). The dispatch
   test pins this negative case so a future widening can't silently
   drag RESEARCH turns into EDGE.

**Manual verification gate deferred.** The plan's verification gate is
"re-run today's three turns; each should now classify into BROWSE /
STRATEGY / EDGE." Auto-mode handoff did not drive a browser session;
deferred to next live UI smoke. The static prompt-content +
LLM_CANNED tests cover the prompt-shape and structured-output
plumbing; only the live LLM behavior against `gpt-4o-mini` requires
manual verification.

**Cross-references.** [`ROUTER_AUDIT_HANDOFF_PLAN.md`](ROUTER_AUDIT_HANDOFF_PLAN.md)
(canonical scope); [`briarwood/agent/README_router.md`](briarwood/agent/README_router.md)
Changelog 2026-04-28 (contract change notes);
[`ROADMAP.md`](ROADMAP.md) §4 Medium "Audit router classification
boundaries" (closeout entry with `✅` prefix and `**Status:**` line);
[`ROADMAP.md`](ROADMAP.md) §4 Medium "Router LLM `confidence=0.6` cap
collapses classifier signal" (the filed-during-this-handoff guardrail
follow-on); [`ROADMAP.md`](ROADMAP.md) §10 Resolved Index row 9;
user-memory `project_llm_guardrails.md` (the directive that drove the
Guardrail Review section).

---

## 2026-04-28 — Router Quality Round 2 landed

**Decision.** Two guardrail-loosening fixes from the 2026-04-28 router-audit
Round 1 landed via [`ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md`](ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md)
Cycles 1-3 on 2026-04-28. Both were filed as §4 Medium ROADMAP entries
during Round 1's closeout; both close here. Per the standing
`project_llm_guardrails.md` directive: these ARE the guardrail
loosening, so the Guardrail Review for this round is short — both
fixes themselves are the actions the prior reviews flagged.

**Fix 1 — LLM confidence flows through to `RouterDecision.confidence`.**
- `RouterClassification` Pydantic schema gained `confidence: float`
  (`Field(ge=0, le=1)`) at
  [briarwood/agent/router.py:255](briarwood/agent/router.py#L255).
- `_LLM_SYSTEM` updated to ask for the score with semantic anchors
  (1.0 = canonical, 0.7 = near second-choice, 0.5 = ambiguous, <0.4 =
  genuinely don't know — under-confidence preferred to false certainty).
- `classify` plumbs `result.confidence` into `RouterDecision.confidence`
  with `max(..., 0.4)` floor at
  [briarwood/agent/router.py:411-414](briarwood/agent/router.py#L411-L414).
  The floor is documented as a deliberate guardrail — keeps every
  successful classification above the 0.3 default-fallback bucket.

**Fix 2 — `parse_overrides` bare-renovation false-positive resolved at
the router layer (not the parser layer).** The original ROADMAP
recommendation was to tighten `parse_overrides` itself; that path
broke an existing rent-override regression test
(`test_renovation_override_with_rent_question_routes_to_rent_lookup`)
because the test relied on the mode-only signal triggering the
override branch. Cleaner approach landed:
- `parse_overrides` is unchanged — `mode="renovated"` is still set
  whenever `_RENO_RE` matches. Downstream consumers
  (`inputs_with_overrides` at
  [briarwood/agent/overrides.py:191-215](briarwood/agent/overrides.py#L191-L215))
  continue to receive the renovation hint cleanly.
- `classify` tightens its `has_override` check at
  [briarwood/agent/router.py:380-389](briarwood/agent/router.py#L380-L389)
  to require a *material* override (`ask_price` or
  `repair_capex_budget`). Bare `mode="renovated"` no longer triggers
  the what-if-price-override short-circuit; those turns flow to the
  LLM classifier so e.g. "Run renovation scenarios" gets PROJECTION
  instead of DECISION.
- `_PROJECTION_OVERRIDE_HINT_RE` widened (Layer B) to catch
  `renovation scenarios?`, `run scenarios?`, `scenario`, `5-year`,
  `ten-year`, `outlook`. Defense in depth: when a real
  what-if-price override IS present, scenario / forecasting phrasings
  route to PROJECTION rather than defaulting to DECISION.

**Plan deviations.**

1. **Layer A landed in `router.py`, not `overrides.py`.** The plan
   called for tightening `parse_overrides` to only set `mode` when
   paired with a value-question / price / capex. Implementation
   started there but broke
   `test_renovation_override_with_rent_question_routes_to_rent_lookup`,
   which relied on mode-only triggering the override branch with a
   rent-hint sub-route. Reverted Layer A in `overrides.py` and
   instead tightened the *router*'s `has_override` check to only
   short-circuit on material overrides. Net result is identical for
   the bare-renovation case (no short-circuit; LLM classifies),
   preserves `parse_overrides`'s downstream contract, and keeps the
   regression test intent (now reframed to use an explicit `if I
   bought... at 1.3M`).
2. **Test fixture sweep was wider than expected.** Adding `confidence`
   to `RouterClassification` required updating every fake LLM that
   constructs it: 3 fakes in `tests/agent/test_router.py`, 1 in
   `tests/test_intent_contract.py`, 1 in `tests/agent/test_rendering.py`.
   All updated to pass `confidence=0.7` by default. (Same shape as
   the 2026-04-24 router schema-fix entry — Pydantic strict-mode
   schema additions cascade through every test fake.)

**Test results.** Round 2 deltas in `tests/agent/test_router.py`,
`tests/agent/test_overrides.py`, `tests/test_intent_contract.py`,
`tests/agent/test_rendering.py`: +6 new tests, 5 fixture updates, 1
existing test reframed. Full agent + integration suite (425 tests):
424 pass, 1 pre-existing failure (`test_promote_unsaved_address` —
unrelated, in baseline 16). Baseline holds.

**Manual verification gate deferred.** Re-run the 2026-04-28 smoke:
- "Walk me through the recommended path" should still classify as
  STRATEGY (Round 1 fix preserved).
- "What would change your value view?" should still classify as
  EDGE (Round 1 fix preserved).
- "Run renovation scenarios" should now classify as PROJECTION (was
  DECISION via the override false-positive — Round 2 Fix 2).
- `turn_traces.confidence` for new chats should vary, no longer
  always 0.6 (Round 2 Fix 1).

**Cross-references.** [`ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md`](ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md)
(canonical scope, marked ✅ on landing);
[`briarwood/agent/README_router.md`](briarwood/agent/README_router.md)
Changelog 2026-04-28 (Round 2);
[`ROADMAP.md`](ROADMAP.md) §4 Medium both entries (`confidence=0.6
cap` and `parse_overrides bare-renovation`) marked ✅;
[`ROADMAP.md`](ROADMAP.md) §10 Resolved Index rows 10 and 11;
DECISIONS.md 2026-04-28 entry "Router classification audit Cycle
1-4 landed" (the prior round, which surfaced both fixes via its
Guardrail Review); user-memory `project_llm_guardrails.md` (the
standing directive); user-memory `feedback_size_for_llm_dev.md`
(LLM-time sizing convention adopted this session;
ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md was the first plan written
under it — sized at "M (~30-45 min LLM time)" instead of the
human-hour framing prior plans used).

---

## 2026-04-28 — AI-Native Foundation Stage 2 landed: feedback loop closed

**Decision.** AI-Native Foundation Stage 2 (§3.1 of [`ROADMAP.md`](ROADMAP.md))
landed via [`FEEDBACK_LOOP_HANDOFF_PLAN.md`](FEEDBACK_LOOP_HANDOFF_PLAN.md)
Cycles 1-4 on 2026-04-28. The user-feedback loop (Loop 2 —
Communication Calibration — per [`design_doc.md`](design_doc.md) § 7) is
now closed end-to-end: write-side via `POST /api/feedback` + a
`feedback` SQLite table + a thumbs UI in every assistant message
bubble, and read-side via an in-flight synthesis hint that fires when
the same conversation has a recent thumbs-down. The closure gate
("turn N+1 visibly influenced") is satisfied and auditable in SQL via
the `feedback:recent-thumbs-down-influenced-synthesis` manifest tag.
See [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) §"Persistence"
for the system-level shape.

**Owner-resolved design decisions during plan-mode pass.** The
2026-04-28 plan-mode pass surfaced ten ODDs; four required owner
sign-off:

1. **Rating semantics — response-quality vs asset-quality** (CLAUDE.md
   contradiction-flag). ROADMAP scoped this as response-quality
   thumbs (Loop 2). The owner clarified intent leaned toward
   asset-quality but agreed with the recommendation to ship Loop 2 in
   Stage 2 and file asset-rating as separate future work. Tier label
   for asset-rating's middle option (when built): **`mixed`** —
   reads as a real judgment rather than a non-answer. Filed for
   future scope, not addressed in this stage.
2. **Rating vocabulary — `"up"|"down"` (API) vs
   `"yes"|"partially"|"no"` (existing helper).** Resolved: map at
   the API boundary. `_RATING_API_TO_RECORD = {"up": "yes",
   "down": "no"}` in `api/main.py`. The existing
   `build_user_feedback_record` helper and the analyzer's
   threshold-recommendation logic at
   [`briarwood/feedback/analyzer.py:306-353`](briarwood/feedback/analyzer.py#L306-L353)
   stay untouched.
3. **Read-back consumer.** Resolved: in-flight synthesis hint (option
   a). The hint appends a "vary your framing" sentence to the
   synthesizer's system prompt; numeric / citation rules unchanged.
   `record_note` tag fires on the manifest so the loop closure is
   auditable in `turn_traces.notes`.
4. **Sequence-step closure convention.** Resolved: split §1 sequence
   step 3 into 3a (Stage 2) and 3b (Stage 3). Closeout flips 3a to
   ✅; 3b stays open for the dashboard handoff.

Plus one in-pass scope filing: charting library upgrade is out of
scope here, filed as ROADMAP §3.4.7 *"Evaluate React-native charting
library to replace Plotly-iframe"* (size L; depends on Stage 2).

**Five plan deviations, recorded for archaeology.**

1. **Test count came in higher than estimated.** Plan estimated 6
   for Cycle 1 + 1 for Cycle 2 + 3 for Cycle 3 = 10. Actual: 8 +
   1 + 7 = 16 (plus the rehydration test = 17 wait, count is 24
   per ROADMAP §3.1 closeout — recounting: Cycle 1 wrote 8 in
   `test_api_feedback.py`, Cycle 2 added 1 more rehydration test
   in the same file (now 9 total), Cycle 3 wrote 7 in
   `test_feedback_readback.py`. Suite delta: ~+16). Defensive
   guard tests (None store, None conversation_id, raising store)
   were cheap to add and protect against future regression.
2. **`comment` field accepted on the wire but ignored.** Per ODD
   #2 (column reserved for v2 with no v2 client today). Wire
   acceptance means the v2 client can ship without an API change
   — schema-level forward compatibility for free.
3. **ContextVar for the read-back hint instead of kwarg
   passthrough.** Plumbing a `prior_feedback_hint` kwarg through
   `synthesize_with_llm` would have meant 7 surgical edits at
   the dispatch handler call sites
   (`briarwood/agent/dispatch.py` handle_browse / handle_decision
   / handle_research / handle_rent_lookup / handle_risk /
   handle_edge / handle_strategy). The seam stays at exactly two
   files (entry layer that sets, synthesizer that reads) by
   using a `ContextVar` in
   [`briarwood/synthesis/feedback_hint.py`](briarwood/synthesis/feedback_hint.py).
   The existing `briarwood.agent.turn_manifest.in_active_context`
   decorator already propagates contextvars across the threadpool
   boundary, so the pattern composes cleanly with what dispatch
   does today. Future maintainers: the implicit coupling is
   documented in the module docstring.
4. **Module placement: `briarwood/synthesis/feedback_hint.py`,
   not `briarwood/feedback/`.** The synthesizer is the only
   consumer of the hint; placing the helper next to its consumer
   honors the "code lives where it's used" instinct better than
   placing it under `briarwood/feedback/` (where the analyzer
   lives). The two surfaces are read-back paths but for
   different consumers.
5. **Dropped a prop-syncing `useEffect` on the FeedbackBar
   (Cycle 2).** ESLint's `react-hooks/set-state-in-effect`
   flagged the initial draft. Confirmed the parent
   (`MessageList`) keys `AssistantMessage` on `m.id`, so a
   conversation switch already remounts the bar fresh; the
   effect was redundant. Mount-time prop init is enough.

**Manual verification gates deferred.** The plan's success-criteria
include three live UI smoke checks: (a) chat → 👎 → confirm SQLite
row + JSONL line; (b) refresh → confirm rating rehydrates; (c) chat
→ 👎 → chat follow-up → confirm `turn_traces.notes` carries the
audit tag. Auto-mode handoff did not drive a browser session;
deferred to next live UI smoke. The new tests
(`tests/test_api_feedback.py` + `tests/test_feedback_readback.py`)
cover the persistence contract, the boundary translator, the JSONL
mirror, the rehydration LEFT JOIN, and the contextvar lifecycle —
only live LLM behavior + browser rendering require manual
verification.

---

### Guardrail Review (per `project_llm_guardrails.md` directive)

The user-memory entry says *"Loosen LLM invocation broadly; perfect
product first, optimize cost later. Numeric guardrail stays. Flag any
guardrail holding back quality."* Walking the new feedback path:

| # | Guardrail | Location | Restricting quality? | Action |
|---|-----------|----------|----------------------|--------|
| 1 | `Literal["up", "down"]` rating in `FeedbackRequest` | [api/main.py FeedbackRequest](api/main.py) | No — the binary scope is the spec; broader rating is filed as future work, not held back here. | Keep. |
| 2 | `_RATING_API_TO_RECORD` boundary translator only maps two values | [api/main.py](api/main.py) | No — but a future tier-3 rating ("mixed") would need the map widened. Note the pin point. | Keep + note. |
| 3 | `upsert_feedback` rejects non-assistant role | [api/store.py](api/store.py) | No — rating user messages or system messages is meaningless; the guard prevents data shape errors. | Keep. |
| 4 | Synthesis hint is a single-sentence directive, not a structured rewrite recipe | [briarwood/synthesis/feedback_hint.py](briarwood/synthesis/feedback_hint.py) | No — leaves the synthesizer free to interpret "vary your framing" as it sees fit. Avoiding over-prescription is the point. | Keep. |
| 5 | Synthesis hint reads only `limit=3` recent ratings | [briarwood/synthesis/feedback_hint.py](briarwood/synthesis/feedback_hint.py) | Possibly — a long conversation with one early thumbs-down at message 1 then twenty thumbs-up after won't trigger the hint on message 22. That's by design (recency-weighted). Could matter if the user revisits a similar property a week later in a long conversation. Watch for it. | Keep + monitor. |
| 6 | JSONL mirror is exception-swallowing | [api/main.py submit_feedback](api/main.py) | No — observability must never break a turn (Stage 1 pattern). | Keep. |
| 7 | `recent_feedback_for_conversation` failure → no-op hint | [briarwood/synthesis/feedback_hint.py](briarwood/synthesis/feedback_hint.py) | No — a misbehaving feedback table cannot break synthesis; correct posture. | Keep. |
| 8 | FeedbackBar disabled while `pending !== null` | [web/src/components/chat/messages.tsx](web/src/components/chat/messages.tsx) | No — prevents the user from spamming opposite ratings during an in-flight POST and corrupting the optimistic state. | Keep. |
| 9 | FeedbackBar suppressed while `isStreaming` | [web/src/components/chat/messages.tsx](web/src/components/chat/messages.tsx) | No — rating an in-flight response would ship a half-formed signal. | Keep. |

**Net finding from the guardrail walk:** zero restrictions blocking
quality. One pin point worth monitoring (#5: 3-row recency window)
that can widen later if needed without contract change.

**Cross-references.** [`FEEDBACK_LOOP_HANDOFF_PLAN.md`](FEEDBACK_LOOP_HANDOFF_PLAN.md)
(canonical scope, marked ✅ on landing);
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) §"Persistence"
(post-landing system shape); [`ROADMAP.md`](ROADMAP.md) §3.1 Stage 2
(closeout entry with `✅` prefix and `**Status:**` line);
[`ROADMAP.md`](ROADMAP.md) §1 sequence steps 3a (closed) and 3b
(remaining open); [`ROADMAP.md`](ROADMAP.md) §10 Resolved Index rows
12 and 13; [`ROADMAP.md`](ROADMAP.md) §3.4.7 (charting library
upgrade filed during this stage); user-memory `project_scout_apex.md`
(downstream Scout buildout inherits this closed feedback signal);
user-memory `project_llm_guardrails.md` (the standing directive).

---

## 2026-04-28 — AI-Native Foundation Stage 3 landed: read-side admin surface

**Decision.** AI-Native Foundation Stage 3 (§3.1 of [`ROADMAP.md`](ROADMAP.md))
landed via [`DASHBOARD_HANDOFF_PLAN.md`](DASHBOARD_HANDOFF_PLAN.md)
Cycles 1-4 on 2026-04-28. The substrate that Stages 1+2 wrote
(`turn_traces`, `data/llm_calls.jsonl`, `feedback`) now has a read-side
UI: three FastAPI admin endpoints behind a `BRIARWOOD_ADMIN_ENABLED=1`
env-gate, plus two Next server-component routes (`/admin` for
top-line weekly aggregates, `/admin/turn/[turn_id]` for the per-turn
drill-down). With 3a + 3b both closed, sequence step 4 (Phase 4b
Scout) is unblocked.

**Owner-resolved design decisions.**

1. **Charting library v1.** Locked at plan-mode pass: plain HTML/CSS
   bars; chart-library evaluation deferred to Phase 4c UI
   reconstruction (ROADMAP §3.4.7 sequencing note added during this
   pass). Stage 3's dashboard is deliberately a small visual surface
   so the eval, when it runs, has clean canvas under real
   BROWSE-rebuild layout pressure rather than a half-mixed chart
   stack to inherit.
2. **Auth gate.** Locked: `BRIARWOOD_ADMIN_ENABLED=1` env var, FastAPI
   returns 404 (not 403) when unset so a probe doesn't reveal the
   surface exists. Single-user local product today; real auth is a
   Stage 3.5+ conversation.
3. **JSONL parse-on-request.** Locked: read the whole file on every
   metrics request. Today's file is a few thousand lines; parse is
   sub-100ms. v2 path (SQLite cost table) deferred until the JSONL
   grows past a few hundred MB.

**One scope addition during Cycle 1: turn_id linkage on JSONL writes.**
The plan assumed `LLMCallSummary` carried `cost_usd`. It does not —
`LLMCallSummary` only persists surface/provider/model/status/duration/
attempts; cost lives in the JSONL alone. Without a `turn_id` field on
the JSONL records, the "Top-10 highest-cost turns" metric required by
ROADMAP §3.1 Stage 3 was uncomputable.

Resolved by adding 8 lines to
[`briarwood/agent/llm_observability.py::LLMCallLedger._write_jsonl`](briarwood/agent/llm_observability.py)
to look up `current_manifest().turn_id` at write time and stamp it on
the JSONL payload. Lazy import + try/except mirrors the existing
manifest-mirror pattern; observability never breaks a turn. New
records carry `turn_id`; pre-Stage-3 records do not, and are excluded
from the top-N cost ranking (the dashboard's empty-state notice
explains this so the owner doesn't read the empty table as broken).

**Five plan deviations, recorded for archaeology.**

1. **Test count came in higher than estimated** (19 vs 8 in Cycle 1).
   Defensive coverage on the JSONL aggregator (corrupt-line skip,
   missing-file no-op, missing turn_id exclusion, percentile math
   with linear interp) plus end-to-end endpoint gating tests for all
   three endpoints under both env states.
2. **JSONL `turn_id` linkage shipped as part of Cycle 1, not as a
   prior Stage 1 follow-on.** The plan flagged the gap during
   drafting but estimated cost weighed in favor of doing it inline
   here. 8 LOC; failure-safe; no schema change. The alternative —
   skip the metric — would have left ROADMAP §3.1 Stage 3's
   "Top-10 highest-cost turns" requirement unimplemented.
3. **Module placement: new `api/admin_metrics.py` for the JSONL
   aggregators.** The compose layer (`compose_metrics`,
   `compose_recent_turns`, `compose_turn_detail`) lives next to the
   JSONL parsing helpers. Rationale: the helpers have no SQLite
   dependency and are testable in isolation; placing them on the
   `ConversationStore` would have crossed dependency lines (store
   shouldn't know about JSONL paths).
4. **TurnTrace JSON column deserialization in `get_turn_trace`** is
   defensive: a corrupt JSON column leaves the raw string in place
   rather than raising, so the dashboard surfaces a corrupt-row
   signal rather than crashing. Mirrors the Stage 1 pattern.
5. **Top-N tables share a single `Table` component** with bar-width
   visualization driven by per-row `(bar / barMax)`. Avoids a chart
   library while still reading visually. The owner-locked decision
   on charting kept this from sprawling.
6. **One self-inflicted regression caught + fixed during closeout.**
   `tests/test_api_admin.py::ComposeIntegrationTests::test_compose_recent_turns_with_no_data_returns_empty_lists`
   passed in isolation but failed in the full suite (17 failed
   / 1561 passed). Root cause: the suite's `pytest_sessionstart`
   hook redirects `BRIARWOOD_LLM_JSONL_PATH` to a single per-session
   tmp file. Other tests' LLM call mocks accumulate JSONL records
   over the session; with the new `turn_id` field stamped on every
   record, `top_costliest_turns` saw non-empty data when the test
   expected empty. Fixed by adding per-test JSONL isolation to
   `ComposeIntegrationTests` (override `BRIARWOOD_LLM_JSONL_PATH` in
   `setUp`, restore in `tearDown`). Also tightened
   `test_compose_metrics_with_no_data_returns_empty_aggregates` to
   assert `cost_by_surface == []` — the prior version didn't, which
   is why only one of the two compose-integration tests caught the
   pollution. Suite returned to baseline 16 failures / 1562 passed.

**Manual verification gates deferred** (auto-mode does not drive a
browser):
- `BRIARWOOD_ADMIN_ENABLED=1 uvicorn api.main:app --reload` →
  `cd web && npm run dev` → visit `/admin` → confirm latency, cost,
  thumbs sections populate from real data after some chat turns.
- Click into a slowest-turn row → confirm the drill-down loads with
  the full manifest.
- Chat → 👎 → chat a follow-up → drill into the follow-up turn →
  confirm the `feedback:recent-thumbs-down-influenced-synthesis`
  note renders with the amber highlight. (This is the visible
  closure-loop audit affordance the dashboard is uniquely
  positioned to surface.)

---

### Guardrail Review (per `project_llm_guardrails.md` directive)

The user-memory entry says *"Loosen LLM invocation broadly; perfect
product first, optimize cost later. Numeric guardrail stays. Flag any
guardrail holding back quality."* Walking the new admin path:

| # | Guardrail | Location | Restricting quality? | Action |
|---|-----------|----------|----------------------|--------|
| 1 | `BRIARWOOD_ADMIN_ENABLED` env-gate, 404 on unset | [api/main.py admin endpoints](api/main.py) | No — single-user local product; obscurity-by-default is correct posture. Trivial to flip. | Keep. |
| 2 | `days` query param clamped to [1, 90] | [api/main.py admin_metrics](api/main.py) | No — outside this window the cost goes from sub-100ms to "scan the entire JSONL." Bounding the input is appropriate. | Keep. |
| 3 | `limit` query param clamped to [1, 100] | [api/main.py admin_recent_turns](api/main.py) | No — the dashboard renders top-10 by default; the cap protects against a runaway client request scanning every turn in history. | Keep. |
| 4 | JSONL parse skips corrupt lines silently | [api/admin_metrics.py _iter_jsonl_records](api/admin_metrics.py) | No — observability must never break a request. Corrupt lines are individual turns; a pathological producer would surface in the count anyway. | Keep. |
| 5 | Top-10 cost ranking excludes records without turn_id | [api/admin_metrics.py top_costliest_turns](api/admin_metrics.py) | No — pre-Stage-3 records lack the linkage by design. Dashboard's empty-state notice explains. New records will populate the ranking going forward. | Keep + document. |
| 6 | `compose_metrics` reads the JSONL on every call | [api/admin_metrics.py](api/admin_metrics.py) | Possibly at scale (years of data), not at v1 scale. Latency budget is fine for now. | Keep + monitor. |
| 7 | Admin route unlinked from main UI | [web/src/components/chat/sidebar.tsx](web/src/components/chat/sidebar.tsx) | No — discoverability via URL only is correct posture for a single-user local admin surface. | Keep. |
| 8 | TurnTrace JSON column deserialization is defensive | [api/store.py get_turn_trace](api/store.py) | No — keeps a corrupt row visible rather than crashing the entire detail page. | Keep. |

**Net finding from the guardrail walk:** zero quality-blocking
restrictions. Two pin points worth monitoring (#5 — pre-Stage-3 cost
records exclusion; #6 — JSONL scale) that can change later without
contract changes.

**Cross-references.** [`DASHBOARD_HANDOFF_PLAN.md`](DASHBOARD_HANDOFF_PLAN.md)
(canonical scope, marked ✅ on landing);
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) §"Persistence"
(post-landing system shape, read-side surface added);
[`ROADMAP.md`](ROADMAP.md) §3.1 Stage 3 (closeout entry with `✅`
prefix and `**Status:**` line); [`ROADMAP.md`](ROADMAP.md) §1
sequence step 3b (now closed; 4 — Phase 4b Scout — unblocked);
[`ROADMAP.md`](ROADMAP.md) §10 Resolved Index rows 14 and 15;
[`ROADMAP.md`](ROADMAP.md) §3.4.7 (charting library upgrade — Stage
3 deliberately did NOT pull this in; bound to Phase 4c UI
reconstruction); [`FEEDBACK_LOOP_HANDOFF_PLAN.md`](FEEDBACK_LOOP_HANDOFF_PLAN.md)
(Stage 2's closure-loop tag is what the drill-down highlights);
user-memory `project_scout_apex.md` (Phase 4b Scout buildout, now
unblocked); user-memory `project_llm_guardrails.md` (the standing
directive).

---

## 2026-04-28 — Phase 4b Scout Cycle 1 landed: LLM scout module + tests

**Decision.** Cycle 1 of [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
landed via commit `0ce8598` on 2026-04-28. The LLM-driven Value Scout
is now a callable, fully tested module with no chat-tier handler
wiring yet (Cycle 2 takes that). This is the first step of Phase 4b
(ROADMAP.md §1 sequence step 4); the apex-differentiator buildout per
the user-memory `project_scout_apex.md` framing.

**What landed.**
- `briarwood/value_scout/llm_scout.py` —
  `scout_unified(*, unified, intent, llm, max_insights=2) ->
  tuple[list[SurfacedInsight], dict]`. One LLM call via
  `complete_structured_observed` at surface `value_scout.scan`.
  Numeric grounding via `verify_response`; single regen at surface
  `value_scout.scan.regen` when threshold-level violations are
  present.
- `briarwood/claims/base.py` — `SurfacedInsight` extended with
  optional `confidence: float | None`
  (`Field(default=None, ge=0.0, le=1.0)`) and `category: str | None`.
  Default `None` preserves back-compat for the existing
  `uplift_dominance` pattern; `scenario_id` was already nullable so
  no schema-side change for the chat-tier-vs-claim-wedge split.
- `briarwood/value_scout/__init__.py` — re-exports `scout_unified`
  alongside the existing `scout_claim`.
- `tests/value_scout/test_llm_scout.py` — 11 tests covering clean
  draft, `max_insights` cap, regen-on-ungrounded-and-keep,
  regen-without-improvement-returns-empty, missing inputs, blank
  response, no-response, persistent exception, manifest surface
  label, prompt regression.

**Open Design Decisions resolved.**
1. **#1 — Per-insight confidence scoring.** Resolved: numeric
   `[0, 1]`. Schema enforces with `Field(ge=0, le=1)`; the prompt
   asks the LLM for a self-rated score with semantic anchors (1.0 =
   canonical, 0.7 = solid, 0.5 = borderline, < 0.4 = better not to
   surface). Banding deferred to Cycle 5 if/when patterns coexist.
2. **#2 — Insight cap per turn.** Resolved: 2 for v1. May tighten
   to 1 after Cycle 2's browser smoke if surface feels noisy.

**One deviation from plan, recorded for archaeology.**

**Stricter terminal grounding rule than the synthesizer.** The plan
called for "regen kept only when violations strictly decrease (mirror
the synthesizer's pattern)" but the test scope explicitly required
"regen-without-improvement returns the empty contract." The two are
asymmetric: the synthesizer keeps the original draft when regen does
not improve and surfaces it with violations recorded; scout in this
landing returns the empty contract instead. Reasoning: the
synthesizer has a caller fallback (`compose_browse_surface` in
`handle_browse`) when prose is empty, so surfacing imperfect prose
plus a violations report is a reasonable middle ground. Scout has no
caller fallback for an ungrounded "what's interesting" beat —
surfacing one would defeat the numeric guardrail without recourse.
Resolved by honoring the test scope (the strict rule). Plan prose
(`Cycles → Cycle 1 → Scope`) and code agree post-landing; the README
copy that ships in Cycle 7 will state the asymmetry plainly.

**Manual verification gate deferred.** No browser smoke required —
Cycle 1 lands the module callable but unwired. Cycle 2's `handle_browse`
integration is the first cycle that surfaces scout output to the user
and gets a browser smoke gate.

---

### Guardrail Review (per `project_llm_guardrails.md` directive)

The user-memory entry says *"Loosen LLM invocation broadly; perfect
product first, optimize cost later. Numeric guardrail stays. Flag any
guardrail holding back quality."* Walking the new scout path:

| # | Guardrail | Location | Restricting quality? | Action |
|---|-----------|----------|----------------------|--------|
| 1 | `complete_structured_observed` `max_attempts=2` retry budget | shared infra at [briarwood/agent/llm_observability.py](briarwood/agent/llm_observability.py) | No — same default the router uses; transient transport failures get one retry, persistent failures fall through cleanly. | Keep. |
| 2 | `_ScoutScanResult` Pydantic strict-mode (`extra="forbid"`) on the structured-output schema | [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) | No — strict mode catches LLM non-compliance loudly so the empty-contract path can take over. Mirrors `RouterClassification`. | Keep. |
| 3 | Numeric grounding via `verify_response` + single-regen pattern | [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) | This IS the numeric guardrail the user-memory entry explicitly preserves. Mandatory. | Keep. |
| 4 | **Empty-contract-on-regen-without-improvement (stricter than synthesizer)** | [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) | Possibly tight. The conservative posture is correct given no caller fallback exists for an ungrounded scout angle. Could relax to "keep best-effort with violations report" later if browser smoke shows scout dropping too often. Watch for it during Cycle 2. | Keep + monitor. |
| 5 | `max_insights=2` cap | [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) | No — Open Design Decision #2 resolved here; bias toward fewer/cleaner insights. May tighten to 1 after smoke. | Keep + monitor. |
| 6 | Empty-contract on missing `unified` or missing `llm` (cheap pre-LLM gate) | [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) | No — matches the synthesizer's `llm_or_unified_missing` posture; saves a guaranteed-failure LLM call. | Keep. |
| 7 | `BudgetExceeded` re-raise from observability wrapper, caught + mapped to empty contract here | [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) | No — preserves the cost-guard semantics other LLM call sites already use. | Keep. |
| 8 | `category` is free-form `str` (not `Literal`) | [briarwood/value_scout/llm_scout.py](briarwood/value_scout/llm_scout.py) | No — deliberately permissive in v1 so the LLM can invent categories that fit a property. Will tighten when patterns coexist (Cycle 5). | Keep. |

**Net finding from the guardrail walk:** zero quality-blocking
restrictions. Guardrail #4 (terminal-empty-on-regen-failure) is the
one to watch — if Cycle 2 browser smoke shows scout silently dropping
on properties where it should fire, relax to "keep with violations
report" and surface the report in the `/admin` drill-down.

**Cross-references.** [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
Cycle 1 closeout (status flipped to ✅);
[`ROADMAP.md`](ROADMAP.md) §1 sequence step 4 (in progress);
[`ROADMAP.md`](ROADMAP.md) §3.2 (status updated);
user-memory `project_scout_apex.md` (Scout = apex; Cycle 1 first step);
user-memory `project_llm_guardrails.md` (drove the Guardrail Review
shape); commit `0ce8598`. README updates
(`briarwood/value_scout/README.md`, `briarwood/claims/README.md`)
intentionally deferred to Cycle 7 per the SCOUT_HANDOFF_PLAN.md
batching convention — Cycle 7 owns the consolidated changelog
spanning all six cycles' contract changes.

---

## 2026-04-28 — Phase 4b Scout Cycle 2 landed: handle_browse + synthesizer wiring

**Decision.** Cycle 2 of [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
landed via commit `038ca51` on 2026-04-28. The LLM-driven Value
Scout is now wired into the BROWSE chat-tier path: `handle_browse`
calls `scout_unified` between the representation-plan computation
and the synthesizer, caches surfaced insights on
`session.last_scout_insights`, and threads them into
`synthesize_with_llm` via a new optional `scout_insights` kwarg.
The synthesizer's `## What's Interesting` beat now carries an
explicit weave-the-highest-confidence-insight directive. A new
`scout_insights` SSE event carries the structured payload to the
React layer for the dedicated drilldown surface that Cycle 3
lands.

**What landed.**
- `briarwood/agent/session.py` — `last_scout_insights:
  list[dict[str, object]] | None` field on `Session`, included
  in `clear_response_views` reset.
- `briarwood/synthesis/llm_synthesizer.py` —
  `synthesize_with_llm(...)` accepts
  `scout_insights: list[SurfacedInsight] | None = None`. When
  non-empty, insights are serialized via `model_dump(mode="json")`
  into the user prompt under the `scout_insights` key. Empty list
  is treated as absent (back-compat). Newspaper system prompt
  extended with the weave directive — paraphrase the headline (do
  NOT quote), name a supporting field, tease the drilldown without
  spoiling the full reason.
- `briarwood/agent/dispatch.py::handle_browse` — runs
  `scout_unified` after `_browse_compute_representation_plan`
  and before `synthesize_with_llm`. Caches model-dumped insights
  on `session.last_scout_insights` (or `None` when scout returned
  empty). Skipped entirely when `llm` is None.
- `api/events.py` — `EVENT_SCOUT_INSIGHTS` constant +
  `scout_insights(items)` constructor.
- `api/pipeline_adapter.py::_browse_stream_impl` — emits
  `events.scout_insights(...)` from `session.last_scout_insights`
  as a primary event between `rent_outlook` and the projection
  scenario_table. `EVENT_SCOUT_INSIGHTS` registered in
  `_MODULE_REGISTRY` so the modules-ran badge credits "Value
  Scout".
- `web/src/lib/chat/events.ts` — TypeScript mirror per AGENTS.md
  parity rule: `ScoutInsightItem` (headline, reason, category,
  confidence, supporting_fields, drilldown_target) +
  `ScoutInsightsEvent` + union membership.

**Open Design Decisions resolved.**
3. **#3 — Trigger gating.** Resolved: every BROWSE turn for v1
   when `llm` is provided (no per-turn / context gating). May
   tighten to "every Nth turn" or "only when intent contract
   names a primary value source" if browser smoke shows the
   surface noisy.

**Three deviations from plan, recorded for archaeology.**

1. **Empty list semantically treated as absent.** Plan called
   for "pass scout insights into `synthesize_with_llm` as a new
   optional `scout_insights: list[SurfacedInsight]` keyword."
   Implementation passes `scout_insights=scout_insights or None`
   so an empty list (scout fired but produced nothing) does not
   surface as `"scout_insights": []` in the user prompt. Reason:
   the synthesizer's `## What's Interesting` directive becomes
   "you must weave one of these" when the field is present;
   passing an empty array would either confuse the model or
   force it to invent. Treating empty as absent makes the
   directive cleanly conditional. Pinned in
   `test_empty_scout_insights_list_is_treated_as_absent`.

2. **Scout call placement after representation plan, not
   parallel.** The plan does not specify ordering relative to
   `_browse_compute_representation_plan`; Cycle 1's plan
   discusses "parallel firing alongside Layer 2 orchestration"
   as out-of-scope target state. Cycle 2 places scout
   sequentially between the representation plan and the
   synthesizer because (a) scout reads `unified` only — no chart
   dependency, (b) synthesizer reads scout output via the new
   kwarg, (c) representation plan and scout could run in
   parallel but Python threadpool plumbing for two LLM calls is
   not justified at this latency budget. Revisit when profiling
   shows scout is on the BROWSE turn's critical path.

3. **`_MODULE_REGISTRY` wiring inline, not deferred.** Plan
   describes the SSE event but doesn't explicitly call out the
   `_MODULE_REGISTRY` registration for the modules-ran badge.
   Added "Value Scout" inline because without it the badge would
   silently omit scout — confusing for browser smoke ("did scout
   actually run?"). Same shape as the existing visualizer / town
   context entries.

**Manual verification gate deferred.** The plan's verification is
"Browser. The 2026-04-26 walkthrough query: 'what do you think of
1008 14th Ave, Belmar, NJ'. Expected: synthesizer's 'What's
Interesting' beat now mentions the rent angle (or ADU signal, or
town-trend tailwind, depending on which the LLM picks)." Auto-mode
handoff did not drive a browser session; deferred to next live UI
smoke. The new tests cover the wiring (kwarg lands in user
payload, session caches, SSE event emits) but only live LLM
behavior against `gpt-4o-mini` shows whether the angle picks
align with what an underwriter would notice on the second read —
Cycle 2's user-visible quality bar.

---

### Guardrail Review (per `project_llm_guardrails.md` directive)

The user-memory entry says *"Loosen LLM invocation broadly; perfect
product first, optimize cost later. Numeric guardrail stays. Flag
any guardrail holding back quality."* Walking the new BROWSE
scout path:

| # | Guardrail | Location | Restricting quality? | Action |
|---|-----------|----------|----------------------|--------|
| 1 | Scout call gated on `llm is not None` AND `unified` non-empty AND `chat_tier_artifact is not None` | [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) | No — scout is purely additive on the BROWSE happy path; gating ensures we don't fire when there's nothing to read or no LLM to call. | Keep. |
| 2 | Empty list treated as absent in synthesizer kwarg | [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) | No — sharpens the conditional directive; prevents the model from being forced to weave a missing insight. | Keep. |
| 3 | Synthesizer prompt instructs "do NOT quote" the scout headline | [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) | No — keeps prose in synthesizer voice; quoted headlines read robotic and break the newspaper voice. | Keep. |
| 4 | Synthesizer picks "exactly one insight" to weave per turn | [briarwood/synthesis/llm_synthesizer.py](briarwood/synthesis/llm_synthesizer.py) | Possibly conservative. The dedicated drilldown surface (Cycle 3) carries the rest of the cap-2 set; the prose shouldn't compete with it for surface area. Watch in browser smoke; if users want more in prose, relax to "one or two". | Keep + monitor. |
| 5 | `drilldown_target` emitted as null in v1 | [api/pipeline_adapter.py](api/pipeline_adapter.py) | No — Cycle 3 fills the category → route mapping. Schema is forward-compatible; null is honest about "drilldown surface not built yet". | Keep until Cycle 3. |
| 6 | Scout output not threaded into Stage 2's feedback hint | [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py) | Partially — synthesizer's prompt picks up the hint via `current_feedback_hint()`, so scout output gets re-framed when a thumbs-down was recorded. But scout's own selection of which angle to emit is not currently hint-aware. If browser smoke shows scout repeatedly emitting the same dropped category, wire scout's system prompt into the hint too. Recorded in Cycle 1 Guardrail Review #4 as a watch-item. | Keep + monitor. |
| 7 | Modules-ran badge credits "Value Scout" only when the SSE event fires | [api/pipeline_adapter.py](api/pipeline_adapter.py) | No — matches the existing convention ("ran but didn't contribute" is excluded by design). When scout fired but returned empty, the badge correctly omits Value Scout. | Keep. |

**Net finding from the guardrail walk:** zero quality-blocking
restrictions. Two pin points worth monitoring (#4 single-insight
weave, #6 hint-unaware scout) that can change later without
contract breaks.

**Cross-references.** [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
Cycle 2 closeout (status flipped to ✅);
[`ROADMAP.md`](ROADMAP.md) §1 sequence step 4 (in progress);
[`ROADMAP.md`](ROADMAP.md) §3.2 (Cycle 2 outcome added);
DECISIONS.md 2026-04-28 entry "Phase 4b Scout Cycle 1 landed"
(prior cycle); user-memory `project_scout_apex.md` (Scout =
apex); user-memory `project_llm_guardrails.md` (the standing
directive); commit `038ca51`. README updates
(`briarwood/value_scout/README.md`, `briarwood/claims/README.md`,
`briarwood/synthesis/README.md`, `briarwood/agent/README_dispatch.md`)
intentionally deferred to Cycle 7 per the SCOUT_HANDOFF_PLAN.md
batching convention — Cycle 7 owns the consolidated changelog
spanning all six cycles' contract changes.

---

## 2026-04-28 — Phase 4b Scout Cycle 3 landed: ScoutFinds drilldown surface

**Decision.** Cycle 3 of [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
landed via commit `919f0fe` on 2026-04-28. The dedicated drilldown
surface for Scout-surfaced angles now renders in BROWSE between the
synthesizer prose and the existing card stack. **Live browser smoke
2026-04-28 confirmed end-to-end render** (SSE event arrives → reducer
populates session → `ScoutFinds` renders with category badges,
confidence percent, headline, reason, and category-routed Drill-in
buttons).

**What landed (4 files).**
- `web/src/lib/chat/scout-routes.ts` — pure category → `{prompt, label}`
  mapping covering 6 known categories (`rent_angle`, `town_trend`,
  `adu_signal`, `comp_anomaly`, `carry_yield_mismatch`, `optionality`).
  Unknown / null categories fall back to a generic "Tell me more" prompt
  — no 404 path.
- `web/src/components/chat/scout-finds.tsx` — `ScoutFinds` React
  component. Renders 0-2 cards (own internal null guard). Category
  badge + confidence% + headline + one-line reason + Drill-in button
  per insight. Defensive UI cap-2 mirrors the LLM scout cap.
- `web/src/lib/chat/use-chat.ts` — `ChatMessage.scoutInsights` field +
  `case "scout_insights"` reducer mirroring existing pattern.
- `web/src/components/chat/messages.tsx` — `<ScoutFinds insights={...}
  onPrompt={onPrompt}/>` rendered between `GroundedText` and
  `StrategyPathCard`.

**Open Design Decisions resolved.**
- **#4 — Drilldown grammar.** Resolved: existing module drill-in routes
  only (plan default). Centralized in `scout-routes.ts`. Unknown
  categories fall through to a generic follow-up — graceful degradation.
- **#5 — Surface name.** Resolved: `ScoutFinds` placeholder per
  `project_brand_evolution.md` memory. UI header "Scout Finds" with
  subtitle "Angles you didn't ask about." Rename when product brand
  finalizes (ScoutAI / PropertyScout TBD).
- **#6 — Placement.** Resolved: under synthesizer prose, above card
  stack (plan default). Pairs the `## What's Interesting` beat with
  the dedicated drilldown card.

**Two browser-smoke findings filed for Cycle 6.**
1. **Scout angles too synthesizer-adjacent.** Both turns' first scout
   insight restated "ask is 6% above fair value" — exactly what the
   `## Why` beat already covers. Genuinely non-obvious angles (e.g.
   $8k Zillow market rent vs $2.3k working rent — 3.4× gap visible in
   the unified output) were not picked up. Cycle 6 owns scout prompt
   tuning; this is the iteration target.
2. **LLM invents categories outside the canonical set.** Smoke surfaced
   `optional_signal` (not in mapping). The fallback handles it
   gracefully but the visible badge "OPTIONAL SIGNAL" reads odd. Two
   options: (a) tighten scout prompt to a fixed enum, (b) loosen UI
   to format unknown categories more gracefully + expand the explicit
   mapping. Recommend (b) — preserves the "permitted to invent"
   flexibility. Cycle 6.

**Three plan deviations, recorded for archaeology.**

1. **First-turn render quirk during smoke.** First BROWSE turn after
   `dev_chat.py` start did NOT render `ScoutFinds` despite the
   `scout_insights` SSE event arriving (verified via DevTools network
   tab). Second turn rendered correctly. Diagnosed as a Turbopack
   bundle-refresh quirk for newly-created component files: the dev
   server starts before the browser-side bundle has the new module
   resolved. Hot-reload catches up by Turn 2. Not a code bug; will
   not repeat in production builds. Documented for the next person
   who hits this.
2. **No JS test framework added.** Plan called for "React component
   render test for 0/1/2 insights" + "drilldown click target test."
   The repo has no Vitest / Jest / Testing Library configured. Adding
   one is a meta-infra decision out of Cycle 3 scope. Verification
   relied on `tsc --noEmit` + ESLint + `next build` + live browser
   smoke. Real React-render coverage is a follow-up worth filing.
3. **`ScoutFinds` is a placeholder name.** The owner explicitly framed
   the component name as non-load-bearing ("we can call it ScoutFinds
   for now maybe and we can always switch it"). The internal
   filename, class name, and UI header all use this name; expect a
   batch rename when the product brand finalizes per
   `project_brand_evolution.md`.

---

### Guardrail Review (per `project_llm_guardrails.md` directive)

The user-memory entry says *"Loosen LLM invocation broadly; perfect
product first, optimize cost later. Numeric guardrail stays. Flag
any guardrail holding back quality."* Walking the new frontend path:

| # | Guardrail | Location | Restricting quality? | Action |
|---|-----------|----------|----------------------|--------|
| 1 | UI cap-2 on insight cards (defensive vs LLM cap-2) | [scout-finds.tsx](web/src/components/chat/scout-finds.tsx) | No — mirrors the server-side cap; protects against surface drift if the cap changes server-side without UI update. | Keep. |
| 2 | `ScoutFinds` returns null on empty insights | [scout-finds.tsx](web/src/components/chat/scout-finds.tsx) | No — plan-mandated empty state. | Keep. |
| 3 | Unknown categories use fallback prompt | [scout-routes.ts](web/src/lib/chat/scout-routes.ts) | No — keeps surface from breaking when LLM invents categories; graceful path. | Keep. |
| 4 | Drill-in routes limited to existing module surfaces | [scout-routes.ts](web/src/lib/chat/scout-routes.ts) | Possibly — ad-hoc deep links would let cards land on the specific evidence field, not just the surface. Owner picked existing routes for v1; revisit per Cycle 6 telemetry. | Keep + monitor (per OD #4). |
| 5 | `formatCategory` simple capitalization | [scout-finds.tsx](web/src/components/chat/scout-finds.tsx) | Minor — produces "Optional signal" badge when LLM invents `optional_signal`. Not a quality block, just a polish item. Cycle 6 handles. | Keep + iterate. |

**Net finding from the guardrail walk:** zero quality-blocking
restrictions. Two pin points (#4 ad-hoc deep links, #5 category
formatting) carried as Cycle 6 watch-items.

**Cross-references.** [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
Cycle 3 closeout (status flipped to ✅);
[`ROADMAP.md`](ROADMAP.md) §1 sequence step 4 (in progress);
[`ROADMAP.md`](ROADMAP.md) §3.2 (Cycle 3 outcome added);
DECISIONS.md 2026-04-28 entry "Phase 4b Scout Cycle 2 landed"
(prior cycle); user-memory `project_scout_apex.md`;
user-memory `project_brand_evolution.md` (ScoutFinds naming
direction); user-memory `project_llm_guardrails.md`; commit `919f0fe`.
README updates intentionally deferred to Cycle 7 per the
SCOUT_HANDOFF_PLAN.md batching convention.

---

## 2026-04-28 — Phase 4b Scout Cycle 4 landed: DECISION + EDGE + per-tier voice

**Decision.** Cycle 4 of [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
landed via commit `cc50f77` on 2026-04-28. The Cycle 2 BROWSE wiring
pattern (scout before synthesizer, cache on session, pass via kwarg)
is now generalized to `handle_decision` (wedge fall-through path)
and `handle_edge`. The scout system prompt gained a per-tier VOICE
block matching the synthesizer's Phase 3 Cycle D pattern.

**What landed (2 files).**
- `briarwood/agent/dispatch.py::handle_decision` (around line 2410) —
  on the decision_summary Layer 3 synthesizer path, runs
  `scout_unified` first, caches `session.last_scout_insights`, and
  passes `scout_insights` to `synthesize_with_llm`. Wedge-active
  DECISION path (claims renderer) is unchanged. Composer fallback
  is unchanged.
- `briarwood/agent/dispatch.py::handle_edge` (around line 4137) —
  same pattern on the EDGE Layer 3 synthesizer path. Section
  followups (`comp_set`, `entry_point`, `value_change`,
  `compose_section_followup`) intentionally not wired — those are
  surgical generations, not full intent-aware prose, and the scout's
  full-unified-output substrate would distract from the section the
  user specifically asked about.
- `briarwood/value_scout/llm_scout.py::_SYSTEM_PROMPT` — extended
  with a VOICE block: `browse` = first-impression surfacer,
  `decision` = decision-pivot surfacer, `edge` = skeptical surfacer.
  Single prompt with intent-keyed voice (mirrors synthesizer pattern,
  not a separate per-tier prompt). All tiers still cap at 1-2
  insights, still ranked by confidence, still grounded in
  `supporting_fields`.

**What did NOT change (intentional zero-edit surfaces).**
- `api/pipeline_adapter.py` — `_browse_stream_impl` already reads
  from `session.last_scout_insights`. DECISION and EDGE turns flow
  through `dispatch_stream` which surfaces the same session field —
  no adapter change needed.
- `web/src/components/chat/scout-finds.tsx` — already renders for
  any message that has `scoutInsights`. DECISION and EDGE turns
  trigger the same React render path as BROWSE.
- `web/src/lib/chat/use-chat.ts` — `case "scout_insights"` already
  handles the event regardless of which handler emitted it.

The implication is significant: the SSE protocol Cycle 2 chose
(session-cached insights → primary event in the stream) made
Cycle 4 a 2-file change instead of a multi-file frontend rewire.
Same shape would extend to handle_strategy / handle_projection /
handle_rent_lookup if Cycle 5 expands scope, with no frontend or
adapter changes needed.

**Verification.** `tests/value_scout/`, `tests/agent/test_dispatch.py`,
and `tests/synthesis/` all green (140 passed) — only the pre-existing
baseline failure (`test_interaction_trace_attached`) shows up, which
is one of the documented 16. Browser smoke deferred to next live
session; expected first DECISION turn to surface decision-pivot scout
output, EDGE turn to surface a skeptical scout output.

**Open Design Decisions resolved.**
- **#7 — Per-tier voice splitting.** Resolved: single prompt with
  intent-keyed VOICE block (mirrors synthesizer's Phase 3 Cycle D
  pattern). Separate per-tier prompts deferred — single prompt
  composes cleanly with the existing scout grounding rule and avoids
  prompt-set drift.

**Two minor deviations from plan.**

1. **DECISION wedge-active path intentionally not wired.** Plan says
   "after the wedge falls through (or when wedge is disabled), call
   `scout_unified`." I implemented the fall-through-only branch.
   The wedge-active path (when claims renderer fires) keeps its
   existing render contract; surfacing scout there would compete
   with the editor's coherence checks. Cycle 5's registry dispatcher
   refactor will unify both surfaces; until then keeping the wedge
   path stable is the safer posture.
2. **`handle_edge` section-followups intentionally not wired.**
   `compose_section_followup` paths (mode-specific narrow generations
   for comp_set / entry_point / value_change / trust / downside / etc.)
   keep their tight composer calls. Adding scout there would inflate
   surgical follow-up generations into full unified-output reads —
   wrong tradeoff for tight follow-ups.

---

### Guardrail Review (per `project_llm_guardrails.md` directive)

| # | Guardrail | Location | Restricting quality? | Action |
|---|-----------|----------|----------------------|--------|
| 1 | Scout call gated on `chat_tier_artifact is not None` AND `unified` non-empty AND `llm` provided | [dispatch.py](briarwood/agent/dispatch.py) | No — same gate as the synthesizer; scout fires when there's substrate to read. | Keep. |
| 2 | Wedge-active DECISION path bypasses scout | [dispatch.py](briarwood/agent/dispatch.py) | Possibly — wedge-active turns currently get no scout output. Cycle 5's registry refactor is the right place to unify. | Keep until Cycle 5. |
| 3 | EDGE section-followups bypass scout | [dispatch.py](briarwood/agent/dispatch.py) | No — surgical follow-ups don't need full-unified-output substrate. | Keep. |
| 4 | Per-tier VOICE block added to scout system prompt | [llm_scout.py](briarwood/value_scout/llm_scout.py) | No — single prompt with intent-keyed voice; mirrors synthesizer pattern; no new failure modes. | Keep. |

**Net finding from the guardrail walk:** zero quality-blocking
restrictions. One pin point (#2 wedge-active bypass) carried as
Cycle 5 dependency — registry dispatcher will unify the two scout
surfaces.

**Cross-references.** [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
Cycle 4 closeout (status flipped to ✅);
[`ROADMAP.md`](ROADMAP.md) §1 sequence step 4 (in progress, Cycles
1-4 closed);
[`ROADMAP.md`](ROADMAP.md) §3.2 (Cycle 4 outcome added);
DECISIONS.md prior cycle entries (Cycles 1, 2, 3); user-memory
`project_scout_apex.md`; user-memory `project_llm_guardrails.md`;
commit `cc50f77`. README updates remain deferred to Cycle 7 per the
SCOUT_HANDOFF_PLAN.md batching convention.

---

## 2026-04-28 — Phase 4b Scout Cycle 5 landed: registry dispatcher + confidence scoring

**Decision.** Cycle 5 of [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
landed on 2026-04-28. Value Scout now has a shared dispatcher across
the claim wedge and chat-tier Scout surfaces. The existing claim-wedge
contract is preserved through `scout_claim`, while BROWSE / DECISION
fall-through / EDGE handlers now call the shared `scout(...)` entry
point before the Layer 3 synthesizer.

**What landed.**
- `briarwood/value_scout/scout.py` — new
  `scout(input_obj, *, llm=None, intent=None, max_insights=2) ->
  list[SurfacedInsight]` dispatcher. `_PATTERNS` is now keyed by input
  type with entries for `VerdictWithComparisonClaim` and
  `UnifiedIntelligenceOutput`.
- `briarwood/value_scout/scout.py::scout_claim` — retained as the
  stable back-compat wrapper, returning the first result from
  `scout(claim, max_insights=1)` or `None`.
- `briarwood/value_scout/patterns/uplift_dominance.py` — deterministic
  confidence now derives from the dominance multiple via
  `min(1.0, 0.5 + 0.1 * multiple)`, making `SurfacedInsight.confidence`
  the universal Scout sort key.
- `briarwood/agent/dispatch.py` — BROWSE, DECISION fall-through, and
  EDGE scout calls now use `scout(...)` instead of direct
  `scout_unified(...)` calls. The `intent` kwarg is preserved so the
  Cycle 4 per-tier voice block still works.
- `briarwood/value_scout/README.md` — updated inline this cycle with
  the dispatcher contract and dated changelog entry, intentionally
  overriding the Cycle 7 README batching convention because Cycle 5
  changes the public module contract.

**Open Design Decisions resolved.**
1. **OD #A — Confidence for deterministic patterns.** Resolved: derive
   confidence from the dominance multiple. This bands deterministic
   Scout output into the same ranking channel as LLM insights without
   forcing deterministic insights to always outrank LLM finds.
2. **OD #B — `scout_claim` lifecycle.** Resolved: keep indefinitely as
   the claim-wedge compatibility wrapper. No deprecation target.

**Compatibility notes.**
- The claim-wedge still gets the same `uplift_dominance` insight for the
  Belmar fixture, now with confidence populated.
- Loose chat-tier unified dicts remain supported. When a dict cannot be
  validated as `UnifiedIntelligenceOutput`, the dispatcher still passes
  it through to the LLM scout; deterministic chat-tier patterns require a
  typed/valid unified object.
- Wedge-active DECISION path still renders through the claim renderer;
  Cycle 5 unifies the Scout entry point, not the user-facing wedge
  rendering surface.

**Verification.** Focused checks passed:
`tests/value_scout/`, focused BROWSE scout dispatch tests,
`tests/editor/test_validator`, `tests/claims/test_representation`, an
import smoke for `scout` / `scout_claim` / `scout_unified`, and
`git diff --check`. The sandbox printed expected `llm_calls.jsonl`
write warnings during LLM-observability tests; assertions still passed.
A full-suite rerun was not used as the Cycle 5 gate because preflight on
a clean tree already showed the repo baseline differs from the handoff
claim: 20 failures / 3 errors rather than 16 failures / 1581 passed.

**Cross-references.** [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
Cycle 5 closeout; [`ROADMAP.md`](ROADMAP.md) §1 sequence step 4 and
§3.2 Phase 4b; prior Scout Cycle 1-4 decision entries;
user-memory `project_scout_apex.md`; user-memory
`project_llm_guardrails.md`.

---

## 2026-04-28 — Phase 4b Scout Cycle 6 landed: deterministic fallback rails + yield telemetry

**Decision.** Cycle 6 of [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
landed on 2026-04-28. Value Scout now has deterministic chat-tier
fallback rails under the shared dispatcher. The rails run for
`UnifiedIntelligenceOutput` inputs before the LLM scout and are ranked in
the same `SurfacedInsight.confidence` channel, so they can surface Finds
when the LLM scout returns empty or when no LLM is available.

**What landed.**
- `briarwood/value_scout/patterns/rent_angle.py` — pure-function rail
  for rental upside. Primary trigger reads comp rows with `rent_zestimate`
  plus sale/ask price and checks median gross yield / rent-vs-carry
  coverage. Secondary trigger reads `rental_option.rent_support_score`
  and `carry_cost.monthly_cash_flow` when comp-rent rows are absent.
- `briarwood/value_scout/patterns/adu_signal.py` — pure-function rail for
  structured accessory-unit optionality evidence from `legal_confidence`.
  It does not classify legality.
- `briarwood/value_scout/patterns/town_trend_tailwind.py` — pure-function
  rail for a town-level three-year price tailwind at or above 10%.
- `briarwood/value_scout/scout.py` — registers all three rails under the
  `UnifiedIntelligenceOutput` key and records a chat-tier manifest note:
  `value_scout_yield insights_generated=... insights_surfaced=...
  top_confidence=...`.
- `briarwood/value_scout/llm_scout.py` — prompt iteration from Cycle 3
  browser smoke. The LLM scout now explicitly avoids restating
  `recommendation`, `key_value_drivers`, `why_this_stance`, and
  `value_position`, and it prefers canonical categories
  (`rent_angle`, `adu_signal`, `town_trend_tailwind`, `comp_anomaly`,
  `carry_yield_mismatch`, `optionality`) while allowing a new label only
  when the evidence truly does not fit.
- `briarwood/value_scout/README.md` — updated inline for the new
  deterministic chat-tier contract, manifest note, and prompt behavior.

**Guardrails.**
- Numeric and analytical logic remains deterministic Python. No LLM is used
  for rent math, valuation, legal classification, scenario math, or risk
  scoring.
- The ADU rail surfaces evidence only; it does not decide whether a unit is
  legal.
- Frontend drilldown click telemetry was intentionally not implemented in
  this cycle.
- Phase 4c BROWSE rebuild remains out of scope.

**Verification.** Focused checks passed:
`venv/bin/python -m pytest tests/value_scout` (32 passed) and
`venv/bin/python -m unittest
tests.agent.test_dispatch.BrowseHandlerTests.test_browse_runs_scout_and_caches_insights_when_artifact_and_llm_present
tests.agent.test_dispatch.BrowseHandlerTests.test_browse_skips_scout_when_no_llm`
(2 passed). The sandbox printed expected `llm_calls.jsonl` write warnings
during LLM-observability tests and a pytest cache warning; assertions
passed. A full-suite rerun was not used because the pre-Cycle-5 clean-tree
baseline is known to differ from the handoff count: 20 failures / 3 errors.

**Cross-references.** [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
Cycle 6 closeout; [`ROADMAP.md`](ROADMAP.md) §1 sequence step 4 and
§3.2 Phase 4b; prior Scout Cycle 1-5 decision entries.

---

## 2026-04-28 — Phase 4b Scout Cycle 7 landed: closeout docs + Phase 4b complete

**Decision.** Cycle 7 of [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
landed on 2026-04-28, closing Phase 4b Scout. The implementation
surface from Cycles 1-6 remains unchanged in this cycle; Cycle 7 is the
documentation and handoff reconciliation pass.

**What landed.**
- `GAP_ANALYSIS.md` Layer 5 now reflects the actual shipped topology:
  shared `scout(...)`, chat-tier BROWSE / DECISION / EDGE Scout, the
  `ScoutFinds` surface, deterministic fallback rails, and manifest yield
  telemetry. The remaining Layer 5 target gaps are true parallel firing
  with Layer 2 and user-type conditioning.
- `TOOL_REGISTRY.md` now includes `value_scout` with deterministic rails,
  `value_scout.scan`, `value_scout.scan.regen`, and the
  `value_scout_yield` manifest note.
- `ARCHITECTURE_CURRENT.md` now records Scout in the directory map, LLM
  integrations table, orchestration section, and persistence telemetry.
- `CURRENT_STATE.md`, `ROADMAP.md`, and `SCOUT_HANDOFF_PLAN.md` now mark
  Phase 4b complete and point the sequence to AI-Native Foundation Stage 4.
- `briarwood/value_scout/README.md` had its tests list and Cycle 1-6
  contract changelog reconciled with the final implementation.

**Verification.** Cycle 7 reused the focused verification gate from Cycle
6 after doc reconciliation: `tests/value_scout/`, focused BROWSE Scout
dispatch tests, import smoke, and `git diff --check`. Live browser smoke
was not rerun in Cycle 7; Cycle 3 already verified the end-to-end
ScoutFinds render. Full-suite rerun remains out of scope because the
pre-Cycle-5 clean-tree baseline differed from the handoff count (20
failures / 3 errors).

**Next sequence task.** AI-Native Foundation Stage 4 — model-accuracy
loop. Phase 4c BROWSE summary card rebuild remains after Stage 4 in the
current sequence.

**Cross-references.** [`SCOUT_HANDOFF_PLAN.md`](SCOUT_HANDOFF_PLAN.md)
Cycle 7 closeout; [`ROADMAP.md`](ROADMAP.md) §1 sequence step 4 and
§3.2 Phase 4b; [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md) Layer 5;
[`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) `value_scout`;
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) LLM integrations
and Persistence.

---

## 2026-04-28 — AI-Native Foundation Stage 4 handoff plan approved

**Decision.** [`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md) is the
approved planning artifact for AI-Native Foundation Stage 4, the
model-accuracy loop. Implementation has not started. The Phase 4b Scout
Cycle 5-7/docs batch was committed first as `c8b6b0d`
(`feat(scout): land Cycle 5-7 closeout`) so Stage 4 can start from a
separate change boundary.

**Scope locked for Stage 4 v1.**
- Ground-truth ingestion starts with actual sale-price outcome data from a
  manual CSV/JSONL file under `data/outcomes/`.
- A one-shot backfill attaches outcomes to historical
  `data/learning/intelligence_feedback.jsonl` rows and persisted turn
  evidence where matching is safe.
- `receive_feedback()` gets real record-only bodies for the highest
  confidence valuation modules first: `current_value`, `valuation`, and
  `comparable_sales`.
- Per-module confidence-vs-outcome alignment persists to a new
  `model_alignment` table.
- Analyzer output surfaces high-confidence module calls that underperform
  actual outcomes and produces human-reviewed prompt/weight tuning
  candidates.

**Guardrails.**
- No auto-tuning or auto-recalibration in Stage 4.
- No Phase 4c BROWSE summary rebuild or frontend redesign.
- No public-record automation in v1; filed separately as lower-priority
  ROADMAP work after the manual loop proves useful.
- No broad semantic-audit implementation unless a narrow field contract is
  needed to score Stage 4 alignment rows.

**Cross-references.** [`ROADMAP.md`](ROADMAP.md) §1 sequence step 5 and
§3.1 Stage 4; [`design_doc.md`](design_doc.md) §3.4 and §7;
AI-Native Foundation Stage 1-3 closeouts; Phase 4b Scout Cycle 7 closeout.

---

## 2026-04-28 — AI-Native Foundation Stage 4 implementation substrate landed

**Decision.** Stage 4 implementation substrate landed on 2026-04-28. The
model-accuracy loop now has manual outcome ingestion, one-shot JSONL
backfill, durable `model_alignment` persistence, record-only feedback hooks
for the highest-confidence valuation modules, and a CLI/JSON analyzer. It
does not auto-tune and it does not require Phase 4c UI work.

**What landed.**
- `briarwood/eval/outcomes.py` — manual CSV/JSONL loader for sale-price
  outcomes with row-level validation, duplicate-key reporting, strict
  `property_id` / normalized-address matching, and no public-record
  automation.
- `scripts/ingest_outcomes.py` — report-only validation CLI for outcome
  files.
- `scripts/backfill_outcomes.py` — one-shot JSONL backfill for
  `data/learning/intelligence_feedback.jsonl`, with `.bak`, `--dry-run`,
  no overwrite of non-null outcomes unless explicitly requested, and safe
  unmatched/corrupt-line reporting.
- `api/store.py` — new `model_alignment` table plus
  `insert_model_alignment` and `model_alignment_rows` helpers.
- `briarwood/eval/alignment.py` — alignment scoring helpers with named
  thresholds: high confidence at `>=0.75`, underperformance at `>=10%`
  absolute percentage error, and zero alignment score at `>=20%` error.
- `briarwood/modules/current_value_scoped.py`,
  `briarwood/modules/valuation.py`, and
  `briarwood/modules/comparable_sales_scoped.py` — record-only
  `receive_feedback(session_id, signal)` hooks that write alignment rows
  when given a module payload and sale-price outcome. Module READMEs were
  updated for the new hook contract.
- `briarwood/feedback/model_alignment_analyzer.py` — analyzer report for
  rows scored by module, mean absolute percentage error, high-confidence
  miss rates, top examples, and human-review tuning candidates.

**Deferred / explicitly not landed.**
- Real outcome data was not added. The next gate is to supply a
  `data/outcomes/` file and run the backfill to create live alignment rows.
- `/admin` alignment visibility was deferred; CLI/JSON analyzer output is
  the v1 read side. A low-priority ROADMAP item tracks optional admin
  visibility after real rows exist.
- Public-record outcome automation was deferred and remains a lower-priority
  follow-up after the manual loop proves useful.
- No module weights, thresholds, prompts, or semantic labels were changed.

**Verification.** Focused checks passed:
`tests/test_stage4_outcomes.py`, `tests/test_stage4_alignment.py`,
`tests/test_api_turn_traces.py`, `tests/test_api_feedback.py`,
`tests/test_api_admin.py`, `tests/modules/test_current_value_isolated.py`,
`tests/modules/test_valuation_isolated.py`,
`tests/modules/test_comparable_sales_isolated.py`, and
`tests/test_feedback_loop.py`. The first sandboxed `test_feedback_loop`
run failed because the existing learned-keywords test writes to
`data/learning/learned_keywords.json`; rerunning with approved filesystem
access passed. Pytest cache warnings in sandbox runs were expected and did
not affect assertions.

**Remaining gate before resolving Stage 4.** Supply a real outcome file,
run `scripts/backfill_outcomes.py`, record at least one live
`model_alignment` row, and review
`python -m briarwood.feedback.model_alignment_analyzer` output for human
tuning candidates. Auto-recalibration remains out of scope.

**Cross-references.** [`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md);
[`ROADMAP.md`](ROADMAP.md) §1 sequence step 5 and §3.1 Stage 4;
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) Persistence;
[`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) Feedback / model-accuracy cluster.

---

## 2026-04-28 — Stage 4 saved-property alignment backfill runner landed

**Decision.** Stage 4 now includes a separate saved-property alignment
backfill runner. The JSONL outcome backfill remains responsible for
attaching ground-truth outcomes to historical
`data/learning/intelligence_feedback.jsonl` rows; the new runner is
responsible for turning a manual outcome file into durable
`model_alignment` rows by re-running the Stage 4 priority modules against
matched saved properties.

**What landed.**
- `briarwood/eval/model_alignment_backfill.py` resolves outcome rows to
  `data/saved_properties/<property_id>` by exact `property_id` first and
  normalized address second.
- `scripts/backfill_model_alignment.py` runs `current_value`, `valuation`,
  and `comparable_sales` for matched saved properties, then records rows
  through the existing record-only receiver hooks.
- The runner supports `--dry-run`, custom SQLite DB paths for verification,
  and duplicate protection by default. Duplicate insertion requires
  `--allow-duplicates`.

**Guardrails.**
- The runner does not mutate `turn_traces`, module weights, thresholds,
  prompts, or semantic labels.
- Address-only matches remain strict: ambiguous saved-property matches are
  skipped rather than guessed.
- No real outcome data was added in this change; the owner still needs to
  supply `data/outcomes/` rows before Stage 4 can be marked resolved.

**Cross-references.** [`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md)
Cycle 2 / Cycle 4b; [`ROADMAP.md`](ROADMAP.md) §1 sequence step 5 and
§3.1 Stage 4; [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) Stage 4;
[`TOOL_REGISTRY.md`](TOOL_REGISTRY.md) Feedback / model-accuracy cluster.

## 2026-04-28 — AI-Native Foundation Stage 4 closed: Loop 1 validated and surfaced its first defect

**Decision.** Stage 4 is RESOLVED. The model-accuracy loop has closed
end-to-end against a real (owner-estimate) outcome row, and the first
exercise of Loop 1 surfaced and isolated a real intake bug — exactly the
kind of finding the loop is designed to surface. Sequence step 5 of
[`ROADMAP.md`](ROADMAP.md) §1 is marked `✅ RESOLVED 2026-04-28`.

**What landed in this closeout.**
- Owner supplied the first outcome row at
  `data/outcomes/property_outcomes.jsonl`
  (`526-w-end-ave-avon-by-the-sea-nj`, `outcome_type: sale_price`,
  `outcome_value: 1385000`, `outcome_date: 2026-04-28`,
  `source: owner_estimate`, `confidence: 0.6`). Marked explicitly in
  `notes` as a forecast / expected close, not a recorded public-record
  sale.
- First backfill run flagged a defect: comp-store lookup returned zero
  rows because `inputs.json:facts.town` was `"Avon By The Sea Nj"` (state
  suffix glued onto town string). Same root cause as the open
  `tests/test_searchapi_zillow_client.py::...test_url_parser_hydrates_listing_fields_via_searchapi`
  regression and the user-memory note `project_resolver_match_bug.md`.
- Town string corrected on the saved property (one-line edit to
  `data/saved_properties/526-w-end-ave-avon-by-the-sea-nj/inputs.json`,
  preserving original alongside via the surrounding pre-fix
  `model_alignment` rows for audit trail). Source code parser fix is
  out of scope for this closeout — tracked in
  [`ROADMAP.md`](ROADMAP.md) §4 (appended to existing
  "Zillow URL-intake address normalization regression" entry).
- Re-run produced 3 honest `model_alignment` rows:
  `current_value` $1,311,200 / APE 5.33% / alignment_score 0.73;
  `valuation` $1,311,200 / APE 5.33% / 0.73;
  `comparable_sales` $1,484,741 from 5 same-town SFR comps + rental
  income / APE 7.20% / 0.64. All confidences (0.51-0.59) below the 0.75
  high-confidence threshold; no human-review tuning candidates surfaced.
- Both pre-fix and post-fix rows persist (5 total); analyzer CLI prints
  them; dedupe verified.

**Why mark resolved on an owner forecast (not a recorded sale).** The
Stage 4 plan's resolution gate is "supply a real outcome file …, run the
backfill, record at least one real alignment row, and review the
analyzer output for human tuning candidates." The owner-estimate row is
real owner signal (the underwriter's expectation), not a synthesized
fixture; treating it as the closure event is honest and unblocks
sequence step 6 (Phase 4c BROWSE). Public-record sale-price ingestion
remains queued as a separate v2 path (new
[`ROADMAP.md`](ROADMAP.md) §4 entry "Backfill `data/outcomes/` from ATTOM
sale-history endpoint" — the proposed `scripts/fetch_attom_outcomes.py`
slice).

**What this closeout does NOT do.**
- Does not fix the URL-parser bug at the source. The `inputs.json` patch
  is a one-line data fix on one property; the parser regression covers
  every property onboarded since the regression landed.
- Does not consolidate the comp-store town-spelling variants
  (`"Avon By The Sea": 91 rows` vs `"Avon-by-the-Sea": 72 rows`). Filed
  as a new §4 entry.
- Does not run the JSONL outcome backfill against
  `data/learning/intelligence_feedback.jsonl`. That path was implemented
  in Cycle 2 of the substrate; running it requires the same outcome data
  the user has now provided. Optional cleanup; not a closure gate.

**Cross-references.**
[`STAGE4_HANDOFF_PLAN.md`](STAGE4_HANDOFF_PLAN.md) header status;
[`ROADMAP.md`](ROADMAP.md) §1 step 5, §3.1 Stage 4, §4 (Zillow URL
parser appendix; comp-store canonicalization; ATTOM outcome backfill);
[`CURRENT_STATE.md`](CURRENT_STATE.md) Current Known Themes.

## 2026-04-28 — Phase 4c BROWSE rebuild plan approved with three-section reframe

**Decision.** [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md)
is the approved planning artifact for Phase 4c — sequence step 6 of
[`ROADMAP.md`](ROADMAP.md) §1. Implementation has not started; Cycle 1 is
the next move. The §3.5 entry is promoted from parking-lot to ACTIVE.

**Layout reframe captured in the plan.** The owner approved the plan in
two passes on 2026-04-28. The first pass approved a "one rich summary
card with drilldowns" shape; the second pass replaced that with **three
stacked sections inside the assistant bubble**:

1. **Section A — `BrowseRead`** (always renders): stance pill + headline + masthead `market_trend` chart + flowed synthesizer prose. "Above the fold."
2. **Section B — `BrowseScout`** (conditional, only when scout fires): peer section with sub-head + the existing `ScoutFinds` 0/1/2 cards. Renders nothing when scout returned empty — no placeholder, no rule.
3. **Section C — `BrowseDeeperRead`** (always renders, drilldowns collapsed): chevron-list drilldowns into Comps / Value thesis / Projection / Rent / Town / Risk / Confidence & data / Recommended path. Each drilldown embeds its relevant chart inline.

**Reasoning for the reframe.** The newspaper-front-page metaphor argues
against a single collapsible block. Newspapers achieve glance-density
through visual hierarchy — sub-heads, thin rules, generous white space —
not through stacked boxed cards. Screen real estate is expensive; the
user must be able to glean as much as possible in the first 2-3 seconds.
Section B as a **peer** (rather than a drilldown row inside the summary
card) also honors the "Scout is the apex of the product" framing
([`project_scout_apex.md`](/Users/zachanderson/.claude/projects/-Users-zachanderson-projects-briarwood/memory/project_scout_apex.md))
— Scout is not buried as one of eight rows.

**Scope locked for Phase 4c.**
- Three-section rebuild on BROWSE turns only. DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP card stacks are unchanged.
- Tier marker on `ChatMessage` via an extension to the existing `message` SSE event (`answer_type`); mirror in TS per AGENTS.md SSE-parity rule.
- 5 cycles + closeout. Cycle 1 lands tier marker + section primitive + Section A fully filled (so the newspaper feel is visible from first browser smoke). Cycle 2 = Section B / Scout migration. Cycle 3 = Comps / Value-thesis / Projection drilldowns + drive-by §3.4.1 / §3.4.3. Cycle 4 = Rent / Town / Risk / Confidence / Path drilldowns + closes `PRESENTATION_HANDOFF_PLAN.md` Open Design Decision #7 (recommended posture: 7c — deferred indefinitely; rebuild solves the layout complaint structurally). Cycle 5 = chart-library evaluation per §3.4.7. Cycle 6 = closeout.
- Mandatory pause for owner browser smoke after every cycle.

**Guardrails.**
- No frontend redesign for non-BROWSE tiers.
- No chart-library **migration** — Cycle 5 is eval only; any migration is a separate handoff.
- No prompt rewrites or model-side changes; the synthesizer's prompt is unchanged.
- ROADMAP §4 High items "Consolidate chat-tier execution" and "Layer 3 LLM synthesizer" are NOT pulled in (already substantively landed in Phase 2 / Phase 3).
- ROADMAP §4 entries filed 2026-04-28 (comp-store canonicalization, ATTOM outcome backfill, Zillow URL-parser regression, property-resolver state ranking) all stay separate.
- §3.4 chart sub-items: §3.4.1 + §3.4.3 fold into Cycle 3 drive-bys; §3.4.7 = Cycle 5; §3.4.2 / §3.4.6 conditional on Cycle 5 outcome; §3.4.4 (live SSE reload bug) and §3.4.5 (multi-source-view structural follow-on) stay outside Phase 4c.

**Cross-references.**
[`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md);
[`ROADMAP.md`](ROADMAP.md) §1 step 6, §3.4 chart umbrella, §3.4.7
chart-library eval, §3.5 Phase 4c (status flipped from parking-lot to
ACTIVE);
[`PRESENTATION_HANDOFF_PLAN.md`](PRESENTATION_HANDOFF_PLAN.md) Open
Design Decision #7 (closes during Cycle 4);
[`docs/current_docs_index.md`](docs/current_docs_index.md) (plan-doc
entry added);
user-memory `project_ui_enhancements.md` (weak decision summary, charts
need work), `project_scout_apex.md` (Scout-as-peer-section rationale),
`project_brand_evolution.md` (placeholder naming convention).

## 2026-04-28 — Phase 4c Cycle 1 landed: tier marker + section primitive + Section A

**Decision.** Cycle 1 of [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md) landed on 2026-04-28. The tier-aware render gate is live, the shared section primitive ships the newspaper visual rhythm, and Section A ("THE READ") is fully filled end-to-end. Sections B and C are Cycle 1 stubs that fill in Cycles 2–4. The status header on the plan doc and ROADMAP.md §3.5 are updated.

**What landed.**
- `api/events.py` — `message_event(...)` extended with optional `answer_type` keyword. `EVENT_MESSAGE` payload carries the field only when present (back-compat preserved for any caller that omits it).
- `api/main.py` — message-event emit site at `/api/chat`'s `_event_source_inner` finally now passes `decision.answer_type.value` so every routed assistant turn ships the tier marker on the wire.
- `api/store.py::get_conversation` — bug fix surfaced during Cycle 1 browser smoke. The query was projecting message rows but never SELECTed `messages.answer_type`, so page-load rehydration after the chat-view auto-navigated to `/c/[id]` lost the tier marker and BROWSE turns rendered the legacy card stack on reload. Added `m.answer_type` to the SQL SELECT and to the row dict; persistence side (`attach_turn_metrics`, called in the chat endpoint's finally block) was already writing the column correctly.
- `tests/test_chat_api.py` — assistant `message` event payload now pins `answer_type: "decision"` on the wire under the patched `RouterDecision(answer_type=AnswerType.DECISION)` test fixture.
- `web/src/lib/chat/events.ts` — `MessageEvent` carries optional `answer_type: string | null`.
- `web/src/lib/chat/use-chat.ts` — `ChatMessage.answerType?: string | null` field added; the `case "message"` reducer arm captures `event.answer_type ?? null` when the server replaces the temp message id.
- `web/src/lib/api.ts` — `StoredMessage.answer_type?: string | null` for the page-load rehydration shape.
- `web/src/app/c/[id]/page.tsx` — `initialMessages` mapper now projects `m.answer_type ?? null` onto `ChatMessage.answerType` so BROWSE turns rehydrate into the new layout after the chat-view auto-navigates.
- `web/src/components/chat/browse-section.tsx` (NEW) — shared section primitive: small-caps section label (0.14em letter-spacing), 1px top rule (suppressible via `showRule={false}` on Section A), 2rem padding, optional subtitle, no nested borders.
- `web/src/components/chat/browse-read.tsx` (NEW) — Section A ("THE READ"). Subject line + `Ask $X · Fair value $Y` headline + stance pill + masthead `market_trend` chart + flowed `GroundedText` prose. Headline data coalesces from `valueThesis` first, then `verdict` (defensive). Stance pill currently falls through to `Undecided` on BROWSE because stance lives on `verdict` and BROWSE doesn't emit it — Cycle 2 carry-over.
- `web/src/components/chat/browse-scout.tsx` (NEW) — Cycle 1 stub returning null. Cycle 2 fills.
- `web/src/components/chat/browse-deeper-read.tsx` (NEW) — placeholder section with sub-head + "Drilldowns coming in Cycles 2–4" line so the gate is visible end-to-end.
- `web/src/components/chat/messages.tsx` — `AssistantMessage` adds `const isBrowse = message.answerType === "browse"`. When `isBrowse`, renders `<BrowseRead /> <BrowseScout /> <BrowseDeeperRead />` and skips the entire legacy card-stack block (verdict, prose, scout, strategy, value-thesis, rent, trust, risk, comps, town, projection, charts.map). When `!isBrowse`, the existing render tree is unchanged.

**What did NOT change (intentional zero-edit surfaces).**
- The synthesizer prompt, the synthesizer's `synthesize_with_llm` contract, and the LLM scout's contract are all untouched.
- DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP card stacks render exactly as before — confirmed by browser smoke ("should I buy 1228 Briarwood Rd, Belmar, NJ" rendered the legacy card stack unchanged).
- `dispatch.py::handle_browse` is unchanged. The rebuild is presentation-only.
- The synthesizer prose's `## Headline / ## Why / ## What's Interesting / ## What I'd Watch` markdown structure is untouched — Section A renders it via the existing `GroundedText` component.

**Open Design Decisions resolved.**
- **#1 — Tier marker mechanism.** Resolved: extend the existing `message` SSE event with optional `answer_type`. Persistence relied on the existing `messages.answer_type` column.
- **#2 — Masthead chart placement.** Resolved: `market_trend` lives inside Section A between the headline row and the prose body.
- **#5 — Mobile vs. desktop.** Resolved: desktop is the primary design target; sections render single-column on mobile with no custom breakpoints.
- **#8 — Component naming.** Resolved: `BrowseSection` / `BrowseRead` / `BrowseScout` / `BrowseDeeperRead` placeholders, rename when product brand finalizes.

**Cycle 2 carry-over: BROWSE-tier stance pill.** Section A's stance pill currently renders `Undecided` because the stance value lives on the `verdict` SSE event, which is only emitted on the DECISION path. Two equally cheap fixes; Cycle 2 picks one at start. Recommended: **(a)** add `stance: str | None` (and optionally `decision_stance: str | None`) to the `value_thesis` SSE event payload (`api/events.py::value_thesis`, `api/pipeline_adapter.py` projection from `session.last_unified_output`, mirror in `web/src/lib/chat/events.ts::ValueThesisEvent`); `BrowseRead` already coalesces stance correctly when wired. Alternative **(b)**: emit a lightweight `verdict` event on BROWSE turns from the same unified output. Recommend (a) — narrower SSE delta and avoids "verdict" semantics on a tier that isn't a final decision.

**Verification.** Focused checks passed: `tests/test_chat_api.py` (3/3), `tests/test_api_turn_traces.py` (9/9 — confirmed `get_conversation` projection fix didn't regress turn-trace queries), `tsc --noEmit`, `eslint` (0 errors / 0 warnings on touched files), `next build`. Live browser smoke 2026-04-28 confirmed end-to-end render on `1008-14th-ave-belmar-nj-07719`: `THE READ` sub-head, real ask/fair-value numbers from `last_value_thesis_view`, market_trend chart inline, flowed synthesizer prose; `THE DEEPER READ` placeholder; old card stack gone on BROWSE; DECISION turn renders the existing card stack unchanged. Plan's pause-for-browser-smoke gate was honored.

**One material deviation from plan, recorded.** The `api/store.py::get_conversation` projection bug was not anticipated in the plan's Cycle 1 scope — it surfaced only when the chat-view's auto-navigation to `/c/[id]` triggered page-load rehydration through `get_conversation`, where the missing column projection silently dropped `answer_type` from the rehydrated `ChatMessage`. The fix is a 2-line server change (added column to SELECT + row dict). Adding it to Cycle 1 was the right call because without it, the entire BROWSE-tier render gate would silently fail on every reload and look like a layout bug. Cross-references in the plan doc's Cycle 1 closeout subsection.

**Cross-references.** [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md) Cycle 1 closeout (status flipped to ✅); [`ROADMAP.md`](ROADMAP.md) §1 step 6 and §3.5 (Cycle 1 outcome appended); user-memory `project_ui_enhancements.md` (weak decision summary, charts need work).

## 2026-04-28 — Phase 4c Cycle 2 landed: Section B Scout fill + stance carry-over

**Decision.** Cycle 2 of [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md) landed on 2026-04-28, same day as Cycle 1. Section B (`BrowseScout`) is filled with the playful-yet-intelligent Scout treatment, and the Cycle 1 carry-over (BROWSE-tier stance pill) is wired. The status header on the plan doc and ROADMAP.md §3.5 are updated.

**What landed.**
- `api/pipeline_adapter.py` — new `_value_thesis_payload(session, view)` helper at `_verdict_from_view`'s neighborhood. Validates `session.last_unified_output["decision_stance"]` against the `DecisionStance` vocabulary and projects `stance` + `decision_stance` (same string, two keys) onto the value_thesis payload when present; absent when the snapshot is missing or carries an unknown vocabulary. Applied at all three `events.value_thesis(session.last_value_thesis_view)` emit sites: `_browse_stream_impl` (~L2089), `_decision_stream_impl` (~L2377), and `_dispatch_stream_impl` (~L2664).
- `web/src/lib/chat/events.ts` — `ValueThesisEvent` extended with `stance?: string | null` and `decision_stance?: string | null` (lowercase snake_case from the DecisionStance enum). The reducer at `web/src/lib/chat/use-chat.ts` already spreads the value_thesis event onto `valueThesis`, so no reducer change was needed.
- `web/src/components/chat/browse-read.tsx` — stance coalesces from `valueThesis?.stance ?? verdict?.stance ?? null` so BROWSE turns light up Section A's pill from the value_thesis event while non-BROWSE callers (which still use this component's verdict prop) continue to work. The `STANCE_TONE` map widened from 4 entries to 7 to cover the full `DecisionStance` vocabulary — `strong_buy` lights up emerald (slightly stronger than `buy`), `interesting_but_fragile` and `execution_dependent` light up amber, `pass_unless_changes` rose. `conditional` deliberately omitted so the trust-gate stance falls through to the neutral border (renders an honest "no strong stance" pill instead of a misleading colored one).
- `web/src/components/chat/scout-finds.tsx` — `ScoutFindCard` promoted from internal helper to named export. No behavior change for the existing `ScoutFinds` consumer (non-BROWSE inline drilldown surface).
- `web/src/components/chat/browse-scout.tsx` (REPLACED) — Cycle 1 stub replaced with the full Section B fill. Sentence-case sub-head **"What did Scout dig up?"** + inline four-pointed amber sparkle SVG glyph + subtitle `Angles you didn't ask about`. Magazine-sidebar L-bracket frame: 2px warm-amber top rule + 2px warm-amber left rule, no right or bottom rule (deliberately NOT a four-sided card — honors the rebuild's "no nested boxed cards" rule). Faint warm tonal background `bg-amber-500/[0.04]`. Body renders `ScoutFindCard` instances directly (no double-wrap from `ScoutFinds`'s standalone outer `<section>`); cards keep their existing chrome.
- `tests/test_pipeline_adapter_contracts.py` — new regression test `test_browse_value_thesis_event_carries_stance_from_unified_output` pins three contracts: (a) `stance` + `decision_stance` lifted onto the value_thesis event when `session.last_unified_output["decision_stance"]` is set; (b) both keys absent when the snapshot is missing; (c) both keys absent when the snapshot carries a stance string outside the `DecisionStance` vocabulary (defends against legacy labels like `lean_buy`).

**What did NOT change (intentional zero-edit surfaces).**
- The Scout pipeline (`briarwood/value_scout/`), the LLM scout prompt, and the SSE `scout_insights` event are untouched. Cycle 2 is purely presentation: Scout's output is rendered in a different visual frame, not generated differently.
- `api/events.py::value_thesis(payload)` is unchanged — it already spreads `**payload`, so adding new keys flows through without a function-signature change.
- DECISION / EDGE / PROJECTION / RISK / STRATEGY / RENT_LOOKUP card stacks render exactly as before. The `value_thesis` event now also carries stance on those tiers (additive contract change), but nothing on the non-BROWSE render tree currently reads it; the existing `verdict.stance` remains the source of truth on DECISION-tier renders. Confirmed by browser smoke.
- `dispatch.py::handle_browse` is unchanged. Cycle 2 is presentation-only.

**Open Design Decisions resolved.**
- **Cycle 1 carry-over: path (a) vs (b).** Resolved: path **(a)** — extend `value_thesis` SSE event with `stance` + `decision_stance`. Narrower SSE delta than emitting a `verdict` event on BROWSE; avoids "verdict" semantics on a tier that isn't a final decision.
- **Section B sub-head copy.** Resolved: **"What did Scout dig up?"** in sentence case, deliberate break from THE READ / THE DEEPER READ uppercase rhythm. Owner reframe: Scout is the apex differentiator (per `project_scout_apex.md`) and earns its own voice; sentence case + the dog-digging metaphor signal "this section is different / this is the value-add" without requiring a card-style frame.
- **Section B visual treatment.** Resolved: between (b) tone-only and (c) distinctive frame on the Cycle-2-start spectrum. Concretely: warm-amber top + left rules form a magazine-sidebar L-bracket (NOT a four-sided card — honors the rebuild's "no nested boxed cards" rule), faint warm tonal background, inline four-pointed sparkle SVG. Owner direction: "playful yet intelligent, premium feel via tone not boxed borders."
- **Card chrome inside Section B.** Resolved: cards keep their own border+bg; Section B bypasses the standalone `ScoutFinds` outer `<section>` wrapper and renders the inner `ScoutFindCard` instances directly inside the section content slot.

**One material deviation from plan, recorded.** The original Cycle 2 scope specified that Section B return null entirely when `scoutInsights` is empty ("the entire section disappears — no sub-head, no rule, no placeholder"). Owner overrode at Cycle 2 start: Scout is the selling feature for the demo, so Section B always renders with its full chrome (sub-head, glyph, accent rules) and the body collapses to a single italic line `Scout was quiet on this one.` when insights are empty. The "honest UI hides empty sections" discipline yields here to the "Scout-is-the-apex" framing — the section's presence on the screen is itself part of the product story. This trades a small honest-UI rule for a guaranteed-visible Scout slot, which the owner judged the right tradeoff for the one-shot demo. Cross-referenced in the plan doc's Cycle 2 closeout subsection.

**Verification.** Focused checks passed: `tests/test_pipeline_adapter_contracts.py` (43/44 passed; the one failure on `test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after`'s chart-kind assertion was confirmed pre-existing baseline noise — verified by stashing the Cycle 2 diff and re-running on Cycle 1's HEAD with the same failure). `tsc --noEmit` clean. `eslint` clean (0 errors / 0 warnings on touched files). `next build` clean (1068ms compile, all 4 static pages generated). Live browser smoke 2026-04-28 confirmed: Section A's stance pill now renders the real `decision_stance` with tone instead of "Undecided"; Section B's playful-yet-intelligent treatment lands (warm L-bracket + sparkle + sentence-case sub-head); Section B's empty-state teaser fires when Scout returns no insights; DECISION turn renders the legacy card stack unchanged. Plan's pause-for-browser-smoke gate was honored.

**Guardrail Review (per `project_llm_guardrails.md` directive).** No LLM additions in scope; no LLM prompts modified. Numeric guardrail rule preserved through synthesizer and scout — both already wired and unchanged in Cycle 2.

**Cross-references.** [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md) Cycle 2 closeout (status flipped to ✅; plan status header updated to "Cycle 2 LANDED"); [`ROADMAP.md`](ROADMAP.md) §3.5 (Cycle 2 outcome appended); user-memory `project_scout_apex.md` (Scout-as-apex framing drove the empty-state teaser and visual-accent decisions), `project_ui_enhancements.md` (weak decision summary — Section A's stance pill carry-over closes that complaint for BROWSE).

## 2026-04-28 — Phase 4c Cycle 3 landed: Section C drilldowns + §3.4.1 / §3.4.3 drive-bys + early tier marker

**Decision.** Cycle 3 of [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md) landed on 2026-04-28, same day as Cycles 1 and 2. Section C ("THE DEEPER READ") fills with three drilldown rows (Comps / Value thesis / Projection) over the new `BrowseDrilldown` primitive; the chevron-list affordance is locked; the `feeds_fair_value` flag is retired end-to-end (§3.4.1); the synthesizer's comp roster is clamped to mirror the chart's top-N slice (§3.4.3); and a new lightweight `turn_meta` SSE event eliminates the BROWSE first-load flicker by stamping `answerType` on the in-flight assistant message slot before any structured event lands.

**What landed.**

*Section C primitives + drilldowns.*
- New `web/src/components/chat/browse-drilldown.tsx` — the "Civic Ledger" row primitive: `py-3.5 px-3 -mx-3` with a per-row `border-t` (`first:border-t-0`), 17px custom-SVG chevron at stroke-width 1.75 (idle `text-muted`, hover/open `text`, 200ms `rotate-90` on open), `bg-[var(--color-surface)]/40` hover plate, sentence-case label, right-aligned `tabular-nums` summary slot, `pl-[26px] mt-4 mb-3` open-body indent. Independent open state per row. Also exports a `SummaryChip` + `ChipEyebrow` + `ChipFigure` family for the naked-text "Editorial Eyebrow" Surface-2 chips with container-query `@[480px]:` collapse to a compact form on narrow bubbles.
- New `web/src/components/chat/value-thesis-drilldown-body.tsx` — fresh component (per owner pick #2: build a new merged body rather than compose `EntryPointCard` + `ValueThesisCard` with hide-flags). Renders the good-entry-point anchor + ask vs fair vs risk-adjusted mini-stats + value drivers / what-must-be-true / why-this-stance / what-changes-my-view / hidden-upside / blocked-thesis-warnings / comp-selection-summary + comp list, all borderless. Existing `EntryPointCard` and `ValueThesisCard` stay untouched on non-BROWSE tiers.
- New `web/src/components/chat/inline-prompt.tsx` — extracted from `messages.tsx` so BROWSE Section C drilldowns and the legacy non-BROWSE card stack share one drill-in affordance. Behavior unchanged.
- `web/src/components/chat/browse-deeper-read.tsx` (REPLACED) — Cycle-1 placeholder replaced with the three drilldowns. Comps drilldown renders the `cma_positioning` chart + valuation `CompsTableCard` + market-support `CompsTableCard`, all with `framed={false}`. Value-thesis drilldown renders `ValueThesisDrilldownBody` + `value_opportunity` chart. Projection drilldown renders `ScenarioTable` + `scenario_fan` chart. Each drilldown's expanded body trails an `InlinePrompt` button so the existing follow-up prompts continue to work. The first-time coach-mark tooltip ("Tap any row to see the evidence.") with chevron-aligned arrow is wired to `useSyncExternalStore`-backed `localStorage["briarwood:section-c-hint-seen"]`; auto-dismisses on first-row expand. Container query `@container` on the drilldown stack drives the chip-collapse breakpoint.
- `web/src/app/globals.css` — new `@keyframes section-c-hint-fade-in` + a `.section-c-hint-fade-in` class gated behind `prefers-reduced-motion: no-preference` for the coach-mark entrance.

*Borderless-card threading (`framed?: boolean`).*
- `framed?: boolean` (default `true`) added to `ChartFrame` (`web/src/components/chat/chart-frame.tsx`), `CompsTableCard` (`cma-table-card.tsx`), and `ScenarioTable` (`scenario-table.tsx`). Per owner pick #1, the prop controls outer wrapper only — internal layout (table rows, header eyebrows, mini-stat grids, legend rows, companion text) is unchanged. Drilldown bodies pass `framed={false}` to drop the `rounded-2xl border bg-[var(--color-surface)] p-4` wrapper and the inner `border-b` section dividers; non-BROWSE tiers default to `framed={true}` and render unchanged. Chart titles render at `text-[14px] font-semibold` instead of `text-[18px] font-bold` when `framed={false}` so they don't compete with the drilldown row's label.

*§3.4.1 — `feeds_fair_value` retirement (end-to-end).*
- `briarwood/agent/tools.py` — `_manual_comp_input_from_row` (line ~297) and `_selected_comp_rows` (line ~386) no longer stamp `feeds_fair_value` on rows.
- `briarwood/agent/dispatch.py` — `comp_set_mode` follow-up at line ~3984 dropped the chosen/contextual split (with `feeds_fair_value` retired, every comp is load-bearing — the split was structurally degenerate). Replaced with a direct "led by" line over the top three comps.
- `api/pipeline_adapter.py` — `_native_cma_chart` no longer projects `feeds_fair_value` into chart `spec.comps`. `_sanitize_valuation_module_comps` lost its provenance-gate check (lines 794-805); the dict-shape defensive check stays. The "rows in this event came from the valuation pipeline" invariant is now structural by construction (sole constructor path is `_selected_comp_rows`).
- `web/src/lib/chat/events.ts` — `feeds_fair_value` field dropped from `CmaPositioningChartSpec.comps[]` and `ValueThesisCompRow`.
- `web/src/components/chat/chart-frame.tsx` — `CmaPositioningChart`'s "Chosen comps / Context only" `MetricChip` replaced with a `Comp set` chip computed from `listing_status` + `is_cross_town` counts via the new exported `formatCompSetChip(...)` helper. The marker fallback (line ~688) that previously keyed on `feeds_fair_value` for legacy null-`listing_status` rows is dropped — legacy rows now render with the SOLD marker (saved-store comps in pre-Cycle-5 transcripts were all SOLD by construction). Owner-locked: same shared count source feeds both the chart-footer chip and the BROWSE Section C "Comps" drilldown chip (per owner pick #4); a comment in `chart-frame.tsx` names the source so the two chips can't drift apart.
- `web/src/components/chat/cma-table-card.tsx` — "In fair value" column dropped from the valuation-variant table (column was rendered from `row.feeds_fair_value`).
- `web/src/lib/chat/chart-surface.ts` — `cmaSurface(...)` companion text rewritten: no longer narrates "X comps feeding fair value"; now narrates SOLD vs ACTIVE provenance from `listing_status` so the editorial line matches the new chip language.
- `api/events.py` — `valuation_comps(...)` docstring updated to record the retirement.
- `briarwood/representation/README.md` — `Last Updated` bumped to 2026-04-28 (Phase 4c Cycle 3); the legacy `feeds_fair_value` colouring fallback prose corrected; new Changelog entry filed per `.claude/skills/readme-discipline/SKILL.md` Job 3 (this is a contract change to the SSE chart spec event type).

*§3.4.3 — `comp_roster` clamp.*
- `briarwood/agent/dispatch.py` — new `_clamp_market_support_comp_roster(market_view)` helper at the top of the comp-row formatting block. `handle_browse`'s synthesizer wiring (line ~5076) now reads `comp_roster = _clamp_market_support_comp_roster(session.last_market_support_view)` instead of the inline projection. New module-level constant `_CMA_ROSTER_MAX_COMPS = 8` mirrors the `priced_rows[:8]` slice in `_native_cma_chart`; comments in both files cross-reference the lock-step. New `CompRosterClampTests` regression class in `tests/agent/test_dispatch.py` (4 cases: long-roster clamp, short-roster passthrough, missing-view None handling, non-dict-row filtering).

*Early tier marker (`turn_meta`) — eliminates BROWSE first-load flicker.*
- `api/events.py` — new `EVENT_TURN_META = "turn_meta"` + `turn_meta(answer_type)` factory. Mirrored in `web/src/lib/chat/events.ts` as `TurnMetaEvent` and added to the `ChatEvent` union (per AGENTS.md SSE-parity rule).
- `api/main.py` — emit `events.turn_meta(decision.answer_type.value)` immediately after `record_classification(...)` (line ~424), before the stream loop starts.
- `web/src/lib/chat/use-chat.ts` — new reducer arm for `case "turn_meta"` that stamps `answerType` on the in-flight assistant message slot. Idempotent with the terminal `message`-event arm that re-stamps `answerType` with the real server-assigned id at stream-end.
- `tests/test_chat_api.py::test_new_chat_streams_conversation_then_assistant_message_then_done` — extended to assert (a) a `turn_meta` event fires before the first `text_delta`, (b) it carries the routed `answer_type`. 3/3 chat API tests pass.

*Test fixture cleanup.*
- `tests/test_pipeline_adapter_contracts.py` — two now-irrelevant regression tests deleted (`test_guard_drops_live_market_row_without_feeds_fair_value`, `test_guard_drops_row_with_feeds_fair_value_false`). The provenance gate they pinned no longer exists. The `_VALUATION_ROW` fixture lost its `feeds_fair_value: True` field. The `_LIVE_MARKET_ROW` class attribute was removed; its one remaining reader (`test_market_support_comps_event_source_is_live_market`) inlines a local fixture with a comment recording the post-§3.4.1 invariant.
- `tests/test_pipeline_adapter_suggestions.py` — `test_valuation_comps_add_fair_value_chip` fixture lost its `feeds_fair_value: True` (the chip-generation logic at `_slot_derived_chips` line 1810 keys on comp presence, not on the flag, so the chip still appears).
- `tests/agent/test_dispatch.py` — one fixture row lost its `feeds_fair_value: True`.

**What did NOT change (intentional zero-edit surfaces).**
- `briarwood/value_scout/`, the synthesizer (`briarwood/synthesis/llm_synthesizer.py`), the Representation Agent (`briarwood/representation/agent.py`), the comp-scoring pipeline, and any decision-model module are untouched. Cycle 3 is a presentation rebuild + provenance retirement; nothing in the decision math moved.
- The `EntryPointCard` and `ValueThesisCard` components are unchanged. They still render with their `framed=true` chrome on non-BROWSE tiers; the BROWSE Value-thesis drilldown body is a fresh component (`ValueThesisDrilldownBody`), not a reskin of the existing cards.
- `_native_cma_chart`'s `priced_rows[:8]` slice is unchanged. The clamp adjustment was on the *synthesizer-side* roster (`comp_roster` in `dispatch.py`), not the chart-side.
- The `verdict` SSE event is unchanged (Cycle 2 already plumbed stance through `value_thesis`; Cycle 3 didn't need to touch it).

**Open Design Decisions resolved at Cycle 3 start.**
- **OD #3 — Drilldown affordance.** Resolved: locked to chevron list rows on 1px rules. NO mini-cards inside Section C, NO accordions, NO four-sided boxed frames. Section C reads as the calm third section against Section A's lead and Section B's warm-amber accent.
- **OD #4 — Drilldown expansion behavior.** Resolved: default-CLOSED, independent open/close per row (multiple may be open simultaneously). Owner direction: chevron must be VERY OBVIOUSLY expandable — implemented as 17px custom SVG (heavier than CSS `›`) at stroke-width 1.75 + hover plate + cursor pointer + 200ms `rotate-90`.
- **Pick #1 — Borderless variant pattern.** Resolved: `framed?: boolean` (default `true`) on the absorbed cards + `ChartFrame`. The prop controls the OUTER WRAPPER ONLY; internal layout is unchanged. Drilldown bodies pass `framed={false}`.
- **Pick #2 — Value-thesis "merged" body.** Resolved: build `ValueThesisDrilldownBody` as a fresh component rather than composing existing cards with hide-flags. Cleaner contract, no flag-driven internal-layout drift.
- **Pick #3 — `_sanitize_valuation_module_comps` provenance assertion deletion.** Resolved: greenlight delete after a 5-minute grep confirmed `_selected_comp_rows` is the sole construction path for valuation_comps event rows. The "rows came from the valuation pipeline" invariant is now structural by construction.
- **Pick #4 — Comp-set chip co-source.** Resolved: same `formatCompSetChip(...)` helper feeds both the `cma_positioning` chart-footer `MetricChip` and the BROWSE Section C "Comps" drilldown `SummaryChip`, with a code comment naming the shared source so the two chips can't drift apart.
- **Pick #5 — Responsive chip collapse.** Resolved: container-query axis (Tailwind v4 `@container` + `@[480px]:` variants), measured against the bubble's container, not the viewport. Compact forms preserve both numbers (e.g. "FAIR $1.31M · 5.3% APE" → "$1.31M · 5.3%") rather than dropping the dollar figure to keep APE.
- **First-time hint variant.** Resolved: Variant Q (quiet coach-mark tooltip) per owner pick. Arrow x-position aligns with first chevron's center via stacked CSS triangles (outer border-color + inner surface-color). Persistence via `localStorage["briarwood:section-c-hint-seen"]`. State backed by `useSyncExternalStore` (the `react-hooks/set-state-in-effect` lint rule that flagged Cycle 2's FeedbackBar effect-rewrite also flagged the naive `useEffect(() => setShowHint(...), [])` pattern; the canonical alternative is an external store with manual same-window listener notification, since `localStorage` only fires the `storage` event in *other* windows).

**One material deviation from plan, recorded.** The plan tabled the BROWSE first-load flicker as a §3.4.4 watch-item (`Live SSE rendering requires a page reload`). Cycle 3's browser smoke surfaced that the tier-marker arrival sequence was making the flicker dramatically more visible: the assistant `message` event (carrier of `answer_type`) lands second-to-last in the stream, so BROWSE turns rendered the legacy card stack against streaming events for ~half a second before the terminal `message` event flipped the layout to the three-section view. Owner judgment: bundle the fix into Cycle 3 rather than file as a §3.4.4 sub-item. The fix added the `turn_meta` SSE event (early tier marker, fires immediately after `classify_turn`); ~30 lines across `api/events.py`, `api/main.py`, `web/src/lib/chat/events.ts`, `web/src/lib/chat/use-chat.ts` + parity test in `tests/test_chat_api.py`. Smoke-confirmed elimination of the flicker.

**Carry-overs to Cycle 4.**
- **Bigger hook per drilldown chip.** Owner browser smoke 2026-04-28 noted that the Surface-2 summary chips (e.g. `8 SOLD`, `FAIR $1.31M · 6.0% APE`, `5Y $686K – $796K`) tell users the *shape* of the evidence but not *why they'd care*. Candidate Cycle 4 design: an italic one-line teaser below each closed row (`text-[13px] text-muted`, ~13px), e.g. `1209 16th led the set at $800K — 6 within $50K of subject`. Prototype across all 8 drilldowns at once during Cycle 4 (not retrofitted onto the three Cycle-3 rows in isolation).
- **Address-normalization promotion (`ROADMAP.md` §4 Medium → High).** Cycle 3's wider test pass surfaced `tests/test_searchapi_zillow_client.py::test_url_parser_hydrates_listing_fields_via_searchapi` failing with `'1223 Briarwood Rd Belmar Nj 07719' != '1223 Briarwood Rd, Belmar, NJ 07719'`. Verified pre-existing on clean HEAD (not a Cycle 3 regression). Owner flagged that "these are the same property" — the normalization is dropping commas and casing the state, which propagates into `property_id` slug generation and the property-identity resolver. Promoted to High in §4. To be sliced as the first work item of the Cycle 4 round.

**Verification.**
- Focused Python: `tests/test_pipeline_adapter_contracts.py` + `tests/test_chat_api.py` + `tests/agent/test_dispatch.py` + `tests/test_pipeline_adapter_suggestions.py` — 156 passed, 1 pre-existing baseline failure (`test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after`'s chart-kind assertion, confirmed pre-existing across Cycles 1–3 closeouts).
- Wider Python regression scan: 16 failures total, sampled 5; 4 confirmed pre-existing on clean HEAD via stash + re-run (router classification, comparable_sales agent + dataset, listing-intake URL parser, structured synthesizer interaction-trace, town-county scoring); the 5th passed in isolation and only failed under the wider run, confirming test-pollution rather than a Cycle 3 regression.
- TypeScript: `tsc --noEmit` clean. ESLint clean on touched directories (one pre-existing `_chrome` warning from 2026-04-26 commit `ee9e4b8` in `RiskBarChart`). `next build` clean — 1407ms compile, 4 static pages generated, no warnings.
- Live browser smoke 2026-04-28 confirmed: three drilldowns render with real chips, chevrons rotate, embedded charts and structured cards render borderless, coach-mark tooltip appears once and persists dismissal across reload, FAIR-spacing fix landed (`FAIR $721K`, not `FAIR$721K`), DECISION/EDGE/VALUATION/TRUST follow-up turns render the legacy card stack unchanged. The `turn_meta` early-marker fix eliminated the visible first-load flicker.

**Guardrail Review (per `project_llm_guardrails.md` directive).** No LLM additions in scope; no LLM prompts modified. The `_native_cma_chart` chart spec change is data-only (drops a flag from row dicts). The dispatch.py `comp_set_mode` follow-up's degenerate split removal preserves the same composer-fallback prose path; no LLM behavior change. Numeric guardrail rule preserved through synthesizer + scout — both unchanged in Cycle 3.

**Cross-references.** [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md) Cycle 3 closeout (status flipped to ✅; plan status header updated to "Cycle 3 LANDED"); [`ROADMAP.md`](ROADMAP.md) §3.4.1 (`✅ RESOLVED 2026-04-28 — Phase 4c Cycle 3`), §3.4.3 (`✅ RESOLVED 2026-04-28 — Phase 4c Cycle 3`), §3.5 (Cycle 3 outcome appended), §4 (address-normalization Medium → High); [`briarwood/representation/README.md`](briarwood/representation/README.md) Changelog entry filed per Job 3; user-memory `project_ui_enhancements.md` (BROWSE first-load flicker call-out closed by `turn_meta`), `project_resolver_match_bug.md` (related to the address-normalization promotion).


## 2026-04-29 — Phase 4c Cycle 4 — Section C drilldowns complete; OD #6 + OD #7 closed

**Cycle outcome.** Section C ("THE DEEPER READ") fills out completely.
Five new drilldowns (Rent, Town context, Risk, Confidence & data,
Recommended path) ship on the `BrowseDrilldown` "Civic Ledger" primitive
introduced in Cycle 3. Each drilldown row now also carries a one-line
italic teaser hook below the label (`text-[13px] italic leading-snug
text-[var(--color-text-muted)]`, `pl-[29px]` aligned with label start),
data-derived per row, that tells the reader *why* the drilldown is
interesting before they expand it. The teaser was the Cycle 3 → Cycle 4
carry-over filed in ROADMAP §3.5 — owner browser smoke had noted that
chips communicated the *shape* of the evidence but not *why care*.
Implemented across all 8 drilldowns in one pass rather than retrofitted
onto Cycle 3's three rows in isolation.

**OD #6 — editor pass (PRESENTATION_HANDOFF_PLAN Open Design Decision #7)
closure.** Resolved as **(7c) deferred indefinitely**. The 2026-04-26
framing was that the layout problem (paragraph + 5 charts in a row) was
conflated with the prose problem; Phase 4c's three-section newspaper
rebuild solves the **layout** structurally — section sub-heads + thin
rules + chart-inside-its-relevant-drilldown + no nested boxed cards —
without touching prose. If post-Cycle-5 browser smoke shows the prose
still feels list-y once layout is fixed, file an editor pass as a fresh
handoff (NOT a Phase 4c follow-on). PRESENTATION_HANDOFF_PLAN's OD #7 is
considered closed by this DECISIONS entry.

**OD #7 — `StrategyPathCard` fate.** Resolved as **drilldown row in v1**.
The card is absorbed into Section C as the "Recommended path" drilldown
with `framed={false}`; non-BROWSE tiers continue to render the card
unchanged at top of the card stack. Absorb-or-retire is a post-smoke
follow-up, not a Cycle 4 task. Rationale: v1 keeps behavior change
minimal — same data surfacing under a chevron — and lets the owner
review the rebuilt layout end-to-end before deciding whether the
strategy path is better expressed as Section A's headline (since the
recommendation IS the headline) or as a stand-alone drilldown.

**Files changed.**
- `web/src/components/chat/browse-drilldown.tsx` — new optional `teaser?: ReactNode` prop on `BrowseDrilldown`; renders below the label when the row is closed and hides on open. Button restructured from a single `flex` row to a `block` button with an inner flex row (label + chip) plus an optional second-line teaser. Indent matches the chevron+gap so the teaser visually hangs under the label.
- `web/src/components/chat/browse-deeper-read.tsx` — five new drilldowns (Rent / Town context / Risk / Confidence & data / Recommended path) added to the existing three (Comps / Value thesis / Projection). Per-row chip + per-row data-derived teaser. New props `rentOutlook`, `townSummary`, `riskProfile`, `trustSummary`, `strategyPath`, `onSelectTownSignal`. The `market_trend` chart deliberately stays in Section A (BrowseRead masthead) and is NOT double-rendered inside the Town drilldown body.
- `web/src/components/chat/messages.tsx` — wires the new event props through to `BrowseDeeperRead` from `AssistantMessage`. The non-BROWSE card stack continues to render the same five cards unchanged.
- `web/src/components/chat/{rent-outlook-card,risk-profile-card,town-summary-card,trust-summary-card,strategy-path-card}.tsx` — new `framed?: boolean` (default `true`) prop on each. Mirrors the Cycle 3 prop introduced on `ChartFrame`, `CompsTableCard`, `ScenarioTable`. Outer wrapper only — internal layout unchanged. Drilldown bodies pass `framed={false}` to drop the `mt-4 rounded-2xl border bg-[var(--color-surface)] p-4` chrome.

**Teaser content rules (per drilldown).** All teasers are deterministic
and derived from event payloads already on the message — no
LLM-generated text on the closed-row affordance. Per AGENTS.md OpenAI
boundary: teasers are layer-3 presentation, not synthesis.
- *Comps:* "Top sale: <addr-short> at <price> · <N> within ±10% of ask".
  Source: `cma_positioning` chart spec comps (same source-of-truth as
  the chip + the chart's "Comp set" footer chip).
- *Value thesis:* "Fair <X> sits <Y>% under/over ask · top driver: <text>".
  Source: `value_thesis` event's `fair_value_base`, `premium_discount_pct`,
  and `key_value_drivers` (or `value_drivers` fallback).
- *Projection:* "<+X>% bull / <-Y>% bear vs base <$Z>". Source:
  `scenario_table` event Bull/Base/Bear rows.
- *Rent:* "<$X>/mo · <ease-label> to rent · covers <ratio>× carry".
  Source: `rent_outlook` event.
- *Town context:* "Median <$X> · <N> bullish vs <M> bearish". Source:
  `town_summary` event.
- *Risk:* "Lead: <first-flag> · <N> risk drivers, <M> trust flags".
  Source: `risk_profile` event.
- *Confidence & data:* "<band> (<N>%) · limit: <first-flag> ·
  <K> contradictions". Source: `trust_summary` event.
- *Recommended path:* "<best-path> · <±$X>/mo · <Y>% cash-on-cash".
  Source: `strategy_path` event.

**Verification.**
- `tsc --noEmit` clean. ESLint clean on the eight touched files.
- `next build` clean — 1140ms compile, 4 static pages generated.
- Focused Python: `tests/test_pipeline_adapter_contracts.py` (44 passed),
  `tests/test_chat_api.py` (3 passed). One pre-existing baseline failure
  carries over (`test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after`'s
  `value_opportunity` chart-kind assertion), unrelated to Cycle 4 — same
  failure logged in Cycle 2 and Cycle 3 closeouts on a clean HEAD.
- Browser smoke SIGNED OFF 2026-04-29. Owner ran the eight-drilldown
  layout end-to-end against the newspaper-front-page bar and signed
  off with no layout iterations. Cycle 5 (chart-library evaluation)
  is now unblocked.

**What did NOT change (intentional).**
- The synthesizer (`briarwood/synthesis/llm_synthesizer.py`), Scout
  (`briarwood/value_scout/`), Representation Agent
  (`briarwood/representation/agent.py`), and any decision-model module
  are untouched. Cycle 4 is a presentation rebuild only.
- The Section A masthead `market_trend` chart placement is unchanged.
  The Town drilldown body is the `TownSummaryCard` content only — the
  chart deliberately does not double-render.
- The non-BROWSE card stack in `messages.tsx` renders identically to
  pre-Cycle-4. All five cards still receive `framed={true}` (their
  default) when called from non-BROWSE branches.
- The first-time coach-mark hint, hint-storage key
  (`briarwood:section-c-hint-seen`), and `useSyncExternalStore` pattern
  introduced in Cycle 3 are unchanged.

**Carry-overs to Cycle 5.**
- Owner browser smoke on the eight-drilldown layout. Plan note (Cycle 4
  Risk: medium): heaviest qualitative gate of the phase; expect 1–2
  layout iterations before sign-off.
- §3.4.7 React-native chart-library evaluation begins after sign-off,
  scoped to `cma_positioning` against 2–3 candidate libraries with
  glance-readability as the gating criterion. Per the 2026-04-28 owner
  sequencing call.

**Cross-references.** [`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md)
Cycle 4 closeout; [`ROADMAP.md`](ROADMAP.md) §3.5 (Cycle 4 outcome
appended); [`PRESENTATION_HANDOFF_PLAN.md`](PRESENTATION_HANDOFF_PLAN.md)
Open Design Decision #7 (closed by this entry — see OD #6 closure
above).

## 2026-04-29 — Phase 4c Cycle 5 landed: chart-library eval + Apache ECharts picked

Cycle 5 of the Phase 4c BROWSE rebuild — a sandboxed evaluation of
React-native chart libraries against the production native-SVG
`cma_positioning` renderer — produced a recommendation memo and an
owner pick. The cycle's goal was the **decision**, not a migration;
the migration is filed as a fresh handoff per the 2026-04-28 sequencing
call and is **not** folded into Phase 4c.

**Eval setup.** Sandbox-only prototypes under
`web/src/components/chat/_eval/` and per-library routes
`/eval/charts/{native,recharts,echarts,nivo}` so `next build` reports
per-library bundle deltas independently. Real `CmaPositioningChartSpec`
payload extracted from a captured BROWSE turn against
`1008-14th-ave-belmar-nj-07719`. The `1228-briarwood-road-belmar-nj`
saved property named in the handoff prompt has all-null pricing fields
(`ask_price=null`, `bcv=null`, `missing_input_count=4`) and isn't a
usable BROWSE target without first promoting/enriching it; 1008 14th
Ave is in the same town, has 8 priced comps, and is one of the
canonical fixtures listed in the testing-strategy section of
`BROWSE_REBUILD_HANDOFF_PLAN.md`. Substitution documented in
`_eval/cma-fixture.ts`.

**Bundle deltas (gzipped) per `next build`.**
- Native SVG (production today): **0 KB** — already shipped.
- @nivo/scatterplot 0.99: **70 KB** for one chart kind only;
  realistic full-catalog cost (line + bar + swarm + …) ~180–250 KB gz.
- Recharts 3.8: **84 KB**.
- Apache ECharts 6: **364 KB** — 4.3× Recharts.

**Code volume per chart.** Native 199 LOC, ECharts 214, Nivo 223,
Recharts 240 — similar across all four. None saves material code volume
at the per-chart level.

**Memo recommendation: stay on the native-SVG renderer.** Phase 3 Cycle
A already retired iframe-Plotly for hand-written native SVG inside
`chart-frame.tsx` — the native renderer **is** the React-native
solution §3.4.7 was reaching for. Remaining gaps (animation, hover
affordances, marker diversity, the §3.4.2 vertical-character y-axis
bug) are 30–90 LLM-development-min of polish each in `chart-frame.tsx`,
cheaper than absorbing 70–364 KB gz of third-party code plus ongoing
API maintenance. Recharts named as the runner-up; ECharts ruled out by
bundle weight; Nivo ruled out by per-chart-kind package sprawl + the
missing categorical-y axis. Memo at
[`docs/CHART_LIBRARY_EVAL_2026-04-29.md`](docs/CHART_LIBRARY_EVAL_2026-04-29.md).

**Owner pick: Apache ECharts (override of memo recommendation).**
Owner reviewed all four candidate routes against the **full-vocab**
fixture (synthetic SOLD/ACTIVE/cross-town markers + value-band
overlay) and picked ECharts on visual quality and the polish of the
hover affordances. The memo's recommendation against ECharts was
weighted on bundle cost; the owner override is **consistent with** the
running "perfect product first, optimize cost later" stance recorded
in user-memory `project_llm_guardrails.md` and explicitly affirmed
again in this session.

**Bundle-cost trade explicitly accepted.** 364 KB gz over a residential
4G connection (~5 Mbps real-world) translates to roughly 600 ms
download + ~300 ms parse on a mid-range phone — about 1 second extra
to first chart paint on the first BROWSE turn of a new session, then
cached. On fiber/wifi the cost is invisible. The migration handoff is
expected to mitigate further via lazy import (`dynamic()`) so the page
becomes interactive on schedule and the chart paints a beat later.

**Why this matters beyond aesthetics.** ECharts' polish is the kind of
trade Briarwood has explicitly chosen to make: it differentiates the
product from Zillow/Redfin (per user-memory `project_scout_apex.md`
on the Scout-as-apex thesis) and the chart surface is one of the
two top-line UI complaints (`project_ui_enhancements.md`). The owner
weighted product polish over bundle weight, knowing the cost.

**What this decision is NOT.**
- It is **not** a backend data-shape change. Production data sometimes
  lacks ACTIVE comps or `value_low` / `value_high`; the migration
  handoff inherits that data shape unchanged. The "full vocab" fixture
  used in the eval was synthetic, included specifically so each
  library's marker vocabulary could be visually compared. Whether
  production should emit full-vocab data more often is a separate
  backend conversation in the CMA module — not blocked on this
  decision.
- It is **not** a swap of the SSE event shape. `ChartSpec` (the
  discriminated union in `web/src/lib/chat/events.ts` mirrored by
  `api/events.py`) stays exactly as it is today; only the React-side
  renderer in `chart-frame.tsx` swaps.
- It is **not** part of Phase 4c. The migration is a fresh handoff
  per the 2026-04-28 sequencing call ("a fresh handoff plan opens
  AFTER Cycle 5 closes").

**Migration filed as new handoff.** Plan doc:
[`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md).
Tracked in `ROADMAP.md` §3.6 as a new strategic initiative
(`[size: M-L]` `[impact: UI & Charts]`). Cycle structure: (1) substrate
+ lazy-load wiring + first chart migration (`cma_positioning`),
(2) bulk migration of remaining 7 chart kinds + drive-by §3.4.2
(vertical y-axis label) + §3.4.6 (marker diversity), (3) cleanup
(remove unused candidate libs, retire `_eval/`, doc reconciliation).

**Files changed in Cycle 5.**
- `web/package.json`, `web/pnpm-lock.yaml` — added `recharts`,
  `echarts`, `echarts-for-react`, `@nivo/core`, `@nivo/scatterplot`.
  Recharts and Nivo will be removed in the migration handoff's Cycle
  3 cleanup; ECharts + echarts-for-react stay.
- `web/src/components/chat/_eval/{cma-fixture.ts, eval-card.tsx,
  eval-route-shell.tsx, cma-native.tsx, cma-recharts.tsx,
  cma-echarts.tsx, cma-nivo.tsx}` — sandbox prototypes. Retired in
  the migration handoff's cleanup cycle.
- `web/src/app/eval/charts/page.tsx`,
  `web/src/app/eval/charts/{native,recharts,echarts,nivo}/page.tsx`
  — sandbox routes. Retired in the migration handoff's cleanup cycle.
- `docs/CHART_LIBRARY_EVAL_2026-04-29.md` — eval memo.

**Verification.**
- `tsc --noEmit` clean. ESLint clean on the eval directory + the
  `app/eval` route directory.
- `next build` clean — 5 new static routes generated. One harmless
  build-time warning from Recharts about `width(-1)`/`height(-1)`
  during static prerender (Recharts can't measure dimensions during
  SSR; chart measures correctly client-side; will be sidestepped in
  the migration via lazy import).
- Focused Python: `tests/test_pipeline_adapter_contracts.py` 44 passed
  + 1 pre-existing baseline failure on
  `test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after`'s
  `value_opportunity` chart-kind assertion (carries over from Cycles
  2/3/4); `tests/test_chat_api.py` 3 passed. No new failures.

**What did NOT change.**
- `api/events.py` / `dispatch.py` / the `ChartSpec` discriminated
  union are untouched. The eval reads existing payloads.
- No new LLM prompts. No changes to the synthesizer, Scout, or any
  decision-model module. Per AGENTS.md OpenAI boundary: this is
  Layer 4 (Representation) presentation work only.
- Module READMEs under `briarwood/` — Cycle 5 didn't change any
  module's contract. Per `.claude/skills/readme-discipline/SKILL.md`
  Job 3, no README updates required by this cycle. The migration
  handoff's Cycle 1 will update `briarwood/representation/README.md`
  if/when the chart-renderer change reaches that boundary.

**Cross-references.**
[`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md)
Cycle 5 closeout (status flipped to ✅; plan-doc top header set to
"✅ RESOLVED 2026-04-29");
[`ROADMAP.md`](ROADMAP.md) §3.4.7 (`✅ RESOLVED 2026-04-29 — Phase 4c
Cycle 5 produced eval memo + owner pick = ECharts`), §3.5 (Cycle 5
outcome appended), §3.6 (new chart-renderer migration entry filed),
§10 Resolved Index (Phase 4c entry appended);
[`docs/CHART_LIBRARY_EVAL_2026-04-29.md`](docs/CHART_LIBRARY_EVAL_2026-04-29.md)
(eval memo);
[`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md)
(new migration plan); user-memory
`project_ui_enhancements.md` (chart polish complaint),
`project_llm_guardrails.md` (perfect-product-first stance),
`project_scout_apex.md` (Briarwood differentiates on polish, not
parity).

## 2026-04-29 — Phase 4c BROWSE rebuild closed

Phase 4c (BROWSE summary card rebuild — three-section newspaper-front-page
layout) closes with all six cycles landed. Plan doc:
[`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md).

**What landed.**
- **Cycle 1** (2026-04-28) — Tier marker `message.answer_type` plumbed
  end-to-end; shared `BrowseSection` primitive; Section A
  (`BrowseRead`) fully filled.
- **Cycle 2** (2026-04-28) — Section B (`BrowseScout`) playful
  Scout treatment; `decision_stance` carry-over wired onto
  `value_thesis`.
- **Cycle 3** (2026-04-28) — Section C (`BrowseDeeperRead`) drilldown
  primitive `BrowseDrilldown`; first three drilldowns (Comps / Value
  thesis / Projection); `framed?` prop on `ChartFrame` /
  `CompsTableCard` / `ScenarioTable`; coach-mark hint; `turn_meta`
  early SSE event eliminating BROWSE first-load flicker; drive-bys
  §3.4.1 (`feeds_fair_value` retired) + §3.4.3 (`comp_roster`
  clamped to chart's top-N).
- **Cycle 4** (2026-04-29) — Remaining five Section C drilldowns
  (Rent / Town context / Risk / Confidence & data / Recommended
  path); italic teaser hook below each closed row; `framed?` prop on
  the five absorbed cards; OD #6 (editor pass) resolved as deferred
  indefinitely; OD #7 (StrategyPathCard fate) resolved as drilldown
  row in v1.
- **Cycle 5** (2026-04-29) — Chart-library evaluation memo + owner
  pick (Apache ECharts). Migration filed as fresh handoff. (Closeout
  entry above.)
- **Cycle 6** (2026-04-29) — Doc reconciliation (this entry +
  ROADMAP / CURRENT_STATE / ARCHITECTURE_CURRENT / GAP_ANALYSIS /
  current_docs_index updates).

**Phase 4c success criteria — verification (per
`BROWSE_REBUILD_HANDOFF_PLAN.md` §"Phase 4c success criteria").**
1. ✅ Tier-aware rendering — `ChatMessage.answerType === "browse"`
   gates the three-section layout.
2. ✅ Three stacked sections rendering on BROWSE turns; existing card
   stack preserved on DECISION/EDGE/PROJECTION/RISK/STRATEGY/RENT_LOOKUP.
3. ✅ Newspaper visual hierarchy with sub-heads, thin rules, ~2rem
   padding; no nested boxed cards.
4. ✅ Section B conditional render is honest (renders nothing when
   scout is empty — minor exception: empty-state italic teaser
   shipped in Cycle 2 per owner judgment that Scout's section
   presence is part of the product story).
5. ✅ Real evidence in the body — Section A's headline and each
   Section C drilldown chip cite real comps/numbers from
   `UnifiedIntelligenceOutput`.
6. ✅ Charts inside their sections — `market_trend` in Section A;
   `cma_positioning` / `value_opportunity` / `scenario_fan` /
   `risk_bar` / `rent_burn` / `rent_ramp` inside relevant Section C
   drilldowns. No trailing `charts.map` block on BROWSE.
7. ✅ Scout retains its existing affordances — category badge /
   confidence% / headline / reason / Drill-in routing.
8. ✅ Open Design Decision #7 (PRESENTATION_HANDOFF_PLAN) closed —
   posture (7c) deferred indefinitely; recorded in 2026-04-29 OD #6
   closure entry above.
9. ✅ Chart-library evaluation produced — memo at
   `docs/CHART_LIBRARY_EVAL_2026-04-29.md`; §3.4.7 marked ✅;
   owner picked Apache ECharts; migration filed as new handoff.
10. ✅ No silent expansion — non-BROWSE card stacks unchanged;
    component files preserved.
11. ✅ Doc discipline — per-cycle `DECISIONS.md` entries landed;
    ROADMAP §1 step 6 + §3.5 + §3.4.7 + absorbed §3.4 sub-items all
    marked ✅ in this closeout pass.

**Follow-ups not folded into Phase 4c.**
- Chart-renderer migration (Apache ECharts) — fresh handoff at
  [`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md);
  ROADMAP §3.6.
- §3.4.2 (vertical-character y-axis label) and §3.4.6 (marker
  diversity / utilitarian styling) absorbed into the migration
  handoff's Cycle 2 drive-bys (the bug class mostly disappears in
  ECharts' declarative axis API).
- Editor pass (PRESENTATION_HANDOFF_PLAN OD #7 / Phase 4c OD #6) —
  deferred indefinitely; revisit only if post-migration smoke shows
  residual list-y prose.
- StrategyPathCard absorb-or-retire (Phase 4c OD #7) — post-smoke
  follow-up; not blocking.

**Cross-references.**
[`ROADMAP.md`](ROADMAP.md) §1 step 6 (`✅ RESOLVED 2026-04-29 —
BROWSE_REBUILD_HANDOFF_PLAN.md`), §3.5 (`✅ RESOLVED 2026-04-29` with
six-cycle index), §3.6 (new migration entry), §10 Resolved Index
(Phase 4c entry appended);
[`BROWSE_REBUILD_HANDOFF_PLAN.md`](BROWSE_REBUILD_HANDOFF_PLAN.md)
(plan-doc top header set to `✅ RESOLVED 2026-04-29` with six-cycle
summary);
[`CURRENT_STATE.md`](CURRENT_STATE.md) (Current Known Themes
refreshed to mark Phase 4c closed);
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) (UI surface map
mentions tier-aware BROWSE rendering);
[`GAP_ANALYSIS.md`](GAP_ANALYSIS.md) (Layer 4 note: BROWSE no longer
a compatibility surface; chart-renderer migration filed as open
gap);
[`docs/current_docs_index.md`](docs/current_docs_index.md)
(BROWSE_REBUILD_HANDOFF_PLAN marked historical; CHART_MIGRATION
plan added).

## 2026-04-30 — Chart-renderer migration Cycle 1 landed: substrate + cma_positioning

Chart-renderer migration to Apache ECharts ([§3.6](ROADMAP.md#36-chart-renderer-migration-to-apache-echarts-size-m-l-impact-ui--charts);
plan doc [`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md))
opens with Cycle 1 — substrate plus the `cma_positioning` chart end-to-end.
The Cycle 5 eval prototype is now the production renderer for that chart;
the gating decision for whether the migration approach works in production
is taken with this cycle's owner sign-off.

**Files changed.**
- New: `web/src/lib/chat/chart-tokens.ts` — `getChartTokens()` resolves the
  production CSS-var palette (`--chart-base/bull/bear/stress/neutral/grid/text-faint`,
  `--color-bg-sunken/surface/text/text-muted/border-subtle`) to concrete
  hex via `getComputedStyle(document.documentElement)` at first call,
  with SSR-safe static fallback. Read-once + cache (no `useSyncExternalStore`
  on `prefers-color-scheme` until light/dark theming lands).
- New (transient — folded into Cycle 2): `web/src/components/chat/cma-positioning-echarts.tsx`
  with the ported eval prototype.
- `web/src/components/chat/chart-frame.tsx` — `CmaPositioningChart` is now
  a thin wrapper around the lazy ECharts component plus its existing
  MetricChip row. Lazy boundary: `dynamic(() => import("./cma-positioning-echarts"), { ssr: false, loading: ShimmerFallback })`.
  Suspense fallback is a 320 px solid shimmer matching the chart's outer
  rounded rectangle (Open-Design resolution: solid shimmer).
- `web/src/components/chat/_eval/cma-echarts.tsx` — eval prototype
  swapped from local `CHART_COLORS` constants to `getChartTokens()` so
  the sandbox tracks production palette changes for free.

**Files unchanged (per hard constraints).** `api/events.py`,
`briarwood/agent/dispatch.py`, `api/pipeline_adapter.py`'s
`_native_*_chart` builders, the `ChartSpec` discriminated union in
`web/src/lib/chat/events.ts` — all untouched. The migration is a
renderer swap; the chart-event payload contract is unchanged.

**Open Design resolutions.**
- *Theme-token cache invalidation strategy.* v1: read-once + cache.
  `useSyncExternalStore` on `prefers-color-scheme` is deferred until
  light/dark theming lands.
- *Suspense fallback shape.* Solid shimmer matching the chart's outer
  rounded rectangle, with implicit paint-time minimum-display. Layout is
  not-flashy on fast wifi and explicit on Slow 4G.

**Bundle delta (gz, first-load).**
- `/` 186.3 → 185.9 KB (−0.4 KB) — well within ±2 KB tolerance.
- `/admin` 145.0 → 145.0 KB (±0).
- `/admin/turn/[turn_id]` 145.0 → 145.0 KB (±0).
- `/c/[id]` 186.3 → 185.9 KB (−0.4 KB).
ECharts engine + the new component land in separate lazy chunks (~362 KB
gz + ~83.5 KB gz) — neither chunk is in any non-chart route's
`firstLoadChunkPaths`.

**Verification.**
- tsc clean. ESLint clean on touched files.
- `next build` clean (one carry-over harmless ECharts SSR-prerender warning
  that was present at Cycle 5 as well).
- Focused pytest: 44 passing, 1 failing — the carry-over baseline
  `value_opportunity` chart-kind assertion failure on
  `tests/test_pipeline_adapter_contracts.py`. No new failures.
- Owner browser smoke against `1008-14th-ave-belmar-nj-07719` — BROWSE
  Comps drilldown renders `cma_positioning` through ECharts with
  subject-ask vertical, fair-value vertical, value band (when present),
  SOLD/ACTIVE/cross-town markers, axis labels, comp address tick labels.
  DECISION turn against the same property — non-`cma` charts still
  render through the native-SVG path (Cycle 1 preserves this); chart
  events on the DECISION-tier card stack render correctly.

**Surfaced contradiction (handed off to Cycle 2 / follow-up):** the
Cycle 1 prompt and plan call for "verifying the existing hover-sync
wiring with BrowseDrilldown's Comps row" — but no production hover-sync
wiring exists today between the Comps drilldown body and the chart.
Hover-sync exists only in the eval prototype's `EvalCard` +
`CompChipRail`. The new ECharts component preserves the
`dispatchAction({type:"highlight"})` + `useEffect`-on-`hoveredAddress`
pattern internally so a future Comps-table-row mirror is "wire one
`onMouseEnter` against the chart's instance ref" — but lifting state
up to `BrowseDeeperRead` and wiring `CompsTableCard` rows is filed as
a small follow-up under §3.6, not part of Cycle 1.

**Cross-references.**
[`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md)
(Cycle 1 spec); [`ROADMAP.md`](ROADMAP.md) §3.6 (Cycle 1 outcome
appended in this closeout).

## 2026-04-30 — Chart-renderer migration Cycle 2 landed: bulk migration of remaining 7 chart kinds + drive-by §3.4.2 / §3.4.6

Cycle 2 migrates the remaining seven chart kinds (`market_trend`,
`scenario_fan`, `risk_bar`, `rent_burn`, `rent_ramp`,
`value_opportunity`, `horizontal_bar_with_ranges`) following Cycle 1's
substrate. Drive-bys §3.4.2 (vertical-character y-axis label) and the
renderer-side prong of §3.4.6 (utilitarian styling / hand-rolled
markers) close as drive-bys. Cycle 1's per-chart file
(`cma-positioning-echarts.tsx`) was consolidated into a single
multi-kind router so there's one lazy boundary for all chart code.

**Files changed.**
- New: `web/src/components/chat/chart-echarts.tsx` — default-exports a
  `<ChartECharts>` router that switches on `spec.kind` and renders one
  of eight option-builder functions (`buildCmaOption`,
  `buildScenarioFanOption`, `buildMarketTrendOption`,
  `buildRiskBarOption`, `buildRentBurnOption`, `buildRentRampOption`,
  `buildValueOpportunityOption`, `buildHorizontalBarWithRangesOption`).
  All colors resolve through `getChartTokens()`. CMA hover-sync wiring
  preserved on this kind only.
- Removed: `web/src/components/chat/cma-positioning-echarts.tsx`
  (Cycle 1's transient file; logic rolled into the router).
- `web/src/components/chat/chart-frame.tsx`:
  - Single `LazyChartECharts = dynamic(() => import("./chart-echarts"), { ssr: false, loading: ShimmerFallback })` replaces the per-chart Cycle 1 dynamic.
  - Each chart-kind wrapper (`ScenarioFanChart`, `CmaPositioningChart`,
    `RiskBarChart`, `RentBurnChart`, `RentRampChart`,
    `ValueOpportunityChart`, `HorizontalBarWithRangesChart`,
    `MarketTrendChart`) shrunk to a thin shell over
    `<LazyChartECharts>` plus its existing MetricChip row /
    chip rail / footer-note chrome.
  - Removed unused native-SVG helpers: `SVG_W`, `SVG_H`, the `CHART`
    palette, `formatTick`, `AxisLabels`, `linePath`, `areaPath`,
    `chartBounds`. `LegendRow`, `strokeDashFor`, `formatCompSetChip`,
    `MetricChip`, `breakEvenLabel` stay (still in use).
  - `NativeChart` dispatch function renamed to `ChartBody` since
    nothing renders natively on this path anymore.
- ~700 LOC removed from `chart-frame.tsx`; ~1,200 LOC added in
  `chart-echarts.tsx`. Net code size roughly comparable; the structural
  win is the one-boundary lazy graph.

**ECharts patterns picked per chart kind.**
- `cma_positioning` — three scatter series (SOLD / cross-town SOLD /
  ACTIVE) with `markLine` verticals + `markArea` band. Same as Cycle 1.
- `scenario_fan` — bull/base/bear/stress lines with shaded band via
  the "stacked transparent + delta-fill" pattern; ECharts `endLabel`
  for Upside / Base / Downside / Floor annotations.
- `market_trend` — single line with three `markPoint` anchors
  (Now / 1y / 3y).
- `risk_bar` — declarative horizontal bars on a category y-axis;
  rose for `tone === "risk"`, amber for `tone === "trust"`.
- `rent_burn` — base + obligation + market lines plus two stacked
  bands (bull/bear scenario, market low/high).
- `rent_ramp` — three rent-escalation lines (0% / 3% / 5%) with a
  zero-line `markLine`.
- `value_opportunity` — number-line dot plot with two annotated dots
  (Fair / Ask). y-axis suppressed entirely (`yAxis.show = false`),
  which structurally closes §3.4.2.
- `horizontal_bar_with_ranges` — stacked transparent-offset + range
  bar, plus a median-tick scatter; tones: `stress` for emphasized,
  `bear` for subject, `base` for others.

**Drive-by closures.**
- ✅ §3.4.2 — `value_opportunity` y-axis label "Comp" rendering as a
  vertical character stack. The bug class is structurally gone:
  `value_opportunity` suppresses its y axis entirely; other chart
  kinds use ECharts' declarative `nameRotate: 90` on `yAxis.name`,
  which routes through ECharts' text layout instead of the
  per-character SVG fallback that triggered the original bug. The
  hand-rolled `AxisLabels` SVG helper containing the bug was deleted.
- ✅ §3.4.6 (renderer-side prong) — every chart's marker scheme is
  now declarative `series.symbol` / `series.itemStyle` /
  `series.emphasis`. Hand-rolled `<polygon>` / `<circle>` / `<rect>`
  primitives are gone. The producer-side prong (CMA marker diversity
  in real comp sets — owner observation that Belmar's top-N is
  all-SOLD same-town) carries over to a comp-scorer follow-up.

**Files unchanged (per hard constraints).** Same as Cycle 1 — backend
contract surfaces all untouched.

**Open Design resolutions.**
- *Whether `LegendRow` JSX in `chart-frame.tsx` stays or moves into
  ECharts' built-in legend.* Stays. It's already styled to match the
  page chrome; ECharts' legend doesn't add capability we need.

**Bundle delta vs pre-Cycle-1 baseline (gz, first-load).**
- `/` 186.3 → 183.0 KB (−3.3 KB).
- `/admin` 145.0 → 145.0 KB (±0).
- `/admin/turn/[turn_id]` 145.0 → 145.0 KB (±0).
- `/c/[id]` 186.3 → 183.0 KB (−3.3 KB).
The chart route is now *smaller* than pre-migration because all
native-SVG body code lives in a lazy chunk. ECharts engine chunk
(~362 KB gz) confirmed not present in any non-chart route's
`firstLoadChunkPaths`.

**Verification.** tsc + ESLint + `next build` clean (carry-over
SSR-prerender warning persists in Cycle 2; goes away in Cycle 3 once
the eval routes are deleted). Focused pytest 44 passing + 1 carry-over
baseline failure. Owner combined browser-smoke against the canonical
Belmar fixture confirmed parity across all eight chart kinds; no
regressions on non-BROWSE tier card stacks.

**Carry-over to follow-ups.** Two new §4 Medium tactical items filed
during this cycle:
- *Chart-content review (bull/base/bear spread looks formulaic;
  broader chart-logic audit)* — owner-flagged at Cycle 2 closeout.
  Lead anchor: `briarwood/modules/bull_base_bear.py`. The renderer is
  fine; the producer-side numbers may not always carry signal
  proportional to chart real estate.
- *Chart interaction affordances: expand-to-overlay +
  download-as-tear-sheet* — owner-flagged at Cycle 2 closeout.
  ECharts' `getDataURL` + a `next/dynamic` PDF generator make both
  cheap.

**Cross-references.**
[`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md)
(Cycle 2 spec); [`ROADMAP.md`](ROADMAP.md) §3.6 (Cycle 2 outcome
appended in this closeout); ROADMAP §3.4.2 / §3.4.6 (drive-by closures).

## 2026-04-30 — Chart-renderer migration Cycle 3 + closeout: sandbox cleanup, dep removal, doc reconciliation

Cycle 3 — sandbox cleanup, removal of unused candidate libraries, doc
reconciliation. With Cycle 3 landed, §3.6 (chart-renderer migration to
Apache ECharts) closes.

**Files changed.**
- Deleted `web/src/components/chat/_eval/` (seven prototype files:
  `cma-fixture.ts`, `eval-card.tsx`, `eval-route-shell.tsx`,
  `cma-native.tsx`, `cma-recharts.tsx`, `cma-echarts.tsx`,
  `cma-nivo.tsx`).
- Deleted `web/src/app/eval/charts/` (hub `page.tsx` + four per-library
  routes: `native/`, `recharts/`, `echarts/`, `nivo/`).
- `web/package.json` — removed `recharts` (^3.8.1), `@nivo/core`
  (^0.99.0), `@nivo/scatterplot` (^0.99.0). `pnpm install` purged 72
  transitive packages from the lockfile.
- `web/pnpm-lock.yaml` updated.

**Bundle delta vs pre-Cycle-1 baseline (gz, first-load).**
- `/` 186.3 → 182.9 KB (−3.4 KB).
- `/admin` 145.0 → 145.0 KB (±0).
- `/admin/turn/[turn_id]` 145.0 → 145.0 KB (±0).
- `/c/[id]` 186.3 → 182.9 KB (−3.4 KB).
- 5 `/eval/charts/*` routes removed from the build entirely.

Final ECharts lazy chunk: 365.8 KB gz (matches the
[`docs/CHART_LIBRARY_EVAL_2026-04-29.md`](docs/CHART_LIBRARY_EVAL_2026-04-29.md)
~364 KB estimate). Confirmed not present in the chat route's
`firstLoadChunkPaths`. Recharts and Nivo no longer in any chunk.

**Verification.** tsc clean, ESLint clean, `next build` clean (the
carry-over Recharts SSR-prerender warning that lingered through Cycles
1-2 is also gone now that the only remaining chart consumer is the
dynamic chat route, which never SSR-prerenders). Focused pytest:
44 passing, 1 failing (carry-over baseline only).

**Doc reconciliation pass (this cycle).**
- This file: three new entries (Cycle 1, Cycle 2, this closeout).
- [`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md):
  top status header → ✅ RESOLVED 2026-04-30 with three-cycle summary.
- [`ROADMAP.md`](ROADMAP.md): §3.6 → ✅ RESOLVED 2026-04-30 with
  per-cycle outcomes; §3.4.2 → ✅ RESOLVED in §3.6 Cycle 2;
  §3.4.6 → ✅ PARTIALLY RESOLVED (renderer prong closed; producer
  prong carries over); §10 Resolved Index entries 26 / 27 / 28 added.
- [`CURRENT_STATE.md`](CURRENT_STATE.md): Current Known Themes
  refreshed to mark §3.6 closed; `Last Updated` bumped.
- [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md):
  `chart-frame.tsx` row updated from "Native-SVG renderer for the
  eight `ChartSpec` kinds" to "Apache ECharts renderer for the eight
  `ChartSpec` kinds (lazy-imported via `next/dynamic`); eval-sandbox
  reference removed.
- [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md): Layer 4 chart-renderer-migration
  gap flipped to closed.
- [`docs/current_docs_index.md`](docs/current_docs_index.md):
  CHART_MIGRATION plan marked historical.

**Module READMEs.** Unchanged.
[`briarwood/representation/README.md`](briarwood/representation/README.md)'s
prose continues to describe chart selection at the registry layer
(not the renderer); the chart-spec contract is unchanged; no Job-3
update warranted per
[`.claude/skills/readme-discipline/SKILL.md`](.claude/skills/readme-discipline/SKILL.md).

**Closeout summary — three-cycle stats.**
- Estimate: 60–120 LLM-development-minutes across the three cycles
  (per the handoff plan). Actual: all three cycles + closeout in one
  session (2026-04-30) following the Cycle 1 owner sign-off and the
  Cycle 2 combined-smoke sign-off.
- Net code size: roughly neutral (chart-frame.tsx shrank by ~700 LOC;
  chart-echarts.tsx added ~1,200 LOC). The structural win is the
  single lazy boundary, the declarative chart APIs, and the deletion
  of three rejected candidate libraries.
- Net bundle: chart route −3.4 KB gz vs pre-migration baseline; ECharts
  engine (~366 KB gz) loads lazily and is never in a non-chart route's
  first-load.
- Open follow-ups filed: chart-content review (bull/base/bear),
  chart interaction affordances (expand + download tear sheet),
  CMA marker-diversity producer-side prong of §3.4.6.

**Cross-references.** This entry is the closeout; the per-cycle
entries above hold the implementation detail.
[`CHART_MIGRATION_HANDOFF_PLAN.md`](CHART_MIGRATION_HANDOFF_PLAN.md);
[`ROADMAP.md`](ROADMAP.md) §3.6 + §3.4.2 + §3.4.6 + §10;
[`CURRENT_STATE.md`](CURRENT_STATE.md);
[`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md);
[`GAP_ANALYSIS.md`](GAP_ANALYSIS.md);
[`docs/current_docs_index.md`](docs/current_docs_index.md).

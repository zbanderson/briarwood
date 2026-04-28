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

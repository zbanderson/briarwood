# Phase 2 — Stage A: Scoped Coverage Analysis

**Date:** 2026-04-22
**Scope:** Read-only. Enumerate every `selected_modules` combination the router
can produce and verify scoped-registry coverage.
**Conclusion:** Scoped registry covers **100%** of routable module sets.
Recommended path: **B1 — delete the fallback.**

---

## 1. Enumeration of routable module sets

### 1.1 How `RoutingDecision.selected_modules` is actually constructed

The only call site that builds `selected_modules` is
[`briarwood/router.py:498-526`](briarwood/router.py#L498-L526)
(`filter_modules_by_depth_and_focus`). It returns:

```
selected = (INTENT_TO_MODULES[intent] ∩ DEPTH_BASELINE_MODULES[depth])
         + (QUESTION_FOCUS_TO_MODULE_HINTS[q] ∩ INTENT_TO_MODULES[intent]  for q in focus)
         + CONFIDENCE  (only if CONFIDENCE ∈ INTENT_TO_MODULES[intent])
```

Every module that can appear in `selected_modules` must be in
`INTENT_TO_MODULES[intent]` for some intent. That universe is the fixed set
below. There are no dynamic/LLM-suggested module names — `ParserOutput` has no
module field; the LLM only supplies `intent_type`, `analysis_depth`, and
`question_focus`, which are enums whose module expansion is table-driven.

### 1.2 Router-reachable module universe

Union over all `INTENT_TO_MODULES` values ([briarwood/routing_schema.py:146-187](briarwood/routing_schema.py#L146-L187)):

| Module (`ModuleName`) | Reachable via intent(s) |
|---|---|
| `valuation` | every intent |
| `carry_cost` | every intent |
| `risk_model` | every intent |
| `confidence` | every intent |
| `resale_scenario` | short_hold, renovate_then_sell |
| `rental_option` | owner_then_rent, house_hack |
| `rent_stabilization` | house_hack |
| `hold_to_rent` | owner_then_rent |
| `renovation_impact` | renovate_then_sell |
| `arv_model` | renovate_then_sell |
| `margin_sensitivity` | renovate_then_sell |
| `unit_income_offset` | house_hack |
| `legal_confidence` | house_hack |

**Unreachable via the router:** `OPPORTUNITY_COST` is listed in
`QUESTION_FOCUS_TO_MODULE_HINTS[CAPITAL_ALLOCATION]` but not in any
`INTENT_TO_MODULES` entry, so the `hinted_module in intent_universe` guard
always drops it. `CAPITAL_ALLOCATION` is not in any `INTENT_TO_QUESTIONS`
entry either — it is dead in the current router. (The scoped registry
implements it; it just never gets asked for.)

### 1.3 Enumerated `(intent × depth)` combinations

There are 5 intents × 4 depths = **20 distinct module sets** before
question-focus hints are applied. Observed outputs:

| intent / depth | selected_modules (base) |
|---|---|
| buy_decision / snapshot | valuation, confidence |
| buy_decision / decision | valuation, carry_cost, risk_model, confidence |
| buy_decision / scenario | valuation, carry_cost, risk_model, confidence |
| buy_decision / deep_dive | valuation, carry_cost, risk_model, confidence |
| owner_occupant_short_hold / snapshot | valuation, confidence |
| owner_occupant_short_hold / decision | valuation, carry_cost, risk_model, confidence |
| owner_occupant_short_hold / scenario | valuation, carry_cost, risk_model, resale_scenario, confidence |
| owner_occupant_short_hold / deep_dive | valuation, carry_cost, risk_model, resale_scenario, confidence |
| owner_occupant_then_rent / snapshot | valuation, confidence |
| owner_occupant_then_rent / decision | valuation, carry_cost, risk_model, confidence |
| owner_occupant_then_rent / scenario | valuation, carry_cost, risk_model, rental_option, confidence |
| owner_occupant_then_rent / deep_dive | valuation, carry_cost, risk_model, rental_option, hold_to_rent, confidence |
| renovate_then_sell / snapshot | valuation, confidence |
| renovate_then_sell / decision | valuation, risk_model, confidence |
| renovate_then_sell / scenario | valuation, risk_model, resale_scenario, confidence |
| renovate_then_sell / deep_dive | valuation, renovation_impact, arv_model, margin_sensitivity, resale_scenario, risk_model, confidence |
| house_hack_multi_unit / snapshot | valuation, confidence |
| house_hack_multi_unit / decision | valuation, carry_cost, risk_model, confidence |
| house_hack_multi_unit / scenario | valuation, carry_cost, risk_model, rental_option, confidence |
| house_hack_multi_unit / deep_dive | valuation, carry_cost, rental_option, unit_income_offset, rent_stabilization, legal_confidence, risk_model, confidence |

Question-focus hints only add modules already in that intent's universe, so
they never introduce a new module beyond the 13 listed in §1.2.

### 1.4 Fixture / test evidence

All asserts in [tests/test_routing_behavior.py](tests/test_routing_behavior.py),
[tests/test_router.py](tests/test_router.py), and
[tests/test_routing_schema.py](tests/test_routing_schema.py) use only
`ModuleName` enum values — no test asserts a module outside the 13 above.

---

## 2. Scoped-registry coverage

Scoped registry ([briarwood/execution/registry.py:51-186](briarwood/execution/registry.py#L51-L186))
wires **15** real runners (no `_not_implemented_runner` stubs):

`valuation, carry_cost, risk_model, confidence, resale_scenario,
rental_option, rent_stabilization, hold_to_rent, renovation_impact,
arv_model, margin_sensitivity, unit_income_offset, legal_confidence,
opportunity_cost, town_development_index`.

### 2.1 Coverage table

| Routable module | In scoped registry? | `supports_scoped_execution` returns |
|---|---|---|
| valuation | ✅ | True |
| carry_cost | ✅ | True |
| risk_model | ✅ (deps: valuation) | True |
| confidence | ✅ | True |
| resale_scenario | ✅ (deps: valuation, carry_cost, town_development_index) | True |
| rental_option | ✅ (deps: valuation) | True |
| rent_stabilization | ✅ | True |
| hold_to_rent | ✅ (deps: carry_cost, rent_stabilization) | True |
| renovation_impact | ✅ | True |
| arv_model | ✅ (deps: valuation, renovation_impact) | True |
| margin_sensitivity | ✅ (deps: arv_model, renovation_impact, carry_cost) | True |
| unit_income_offset | ✅ (deps: carry_cost) | True |
| legal_confidence | ✅ | True |

All 20 `(intent × depth)` base combinations from §1.3 resolve to scoped-only
module sets. `supports_scoped_execution()` returns `True` for each.

### 2.2 Deep-dive superset check

The deep_dive row for `renovate_then_sell` and `house_hack_multi_unit`
exercises the largest module sets the router produces. Both are fully covered:

- `renovate_then_sell / deep_dive` → valuation, renovation_impact, arv_model, margin_sensitivity, resale_scenario, risk_model, confidence → all scoped.
- `house_hack_multi_unit / deep_dive` → valuation, carry_cost, rental_option, unit_income_offset, rent_stabilization, legal_confidence, risk_model, confidence → all scoped.

### 2.3 Stub check

Registry validation (`validate_registry`) rejects any spec without a callable
runner; `_module_has_scoped_runner` additionally rejects the
`_not_implemented_runner` factory's `_runner`. No stubs ship in the current
registry, so scoped support is not contingent on lazy-loaded runners.

---

## 3. Legacy modules that become dead if Path B1 is chosen

Reference only — not a deletion plan (Stage B decides scope).

[`briarwood/runner_common.build_engine`](briarwood/runner_common.py#L64-L144) wires 20 modules.
[`briarwood/runner_routed.ROUTING_MODULE_MAP`](briarwood/runner_routed.py#L48-L62) is the
fallback's shape adapter and references a subset; modules outside that map
are wired but never surfaced to the router. Under B1, each would need a
repo-wide reference check before deletion.

**Referenced by `ROUTING_MODULE_MAP` (would need a usage audit):**
CurrentValueModule, ComparableSalesModule, HybridValueModule,
CostValuationModule, IncomeSupportModule, RiskConstraintsModule,
LiquiditySignalModule, MarketMomentumSignalModule, PropertyDataQualityModule,
BullBaseBearModule, TeardownScenarioModule, RentalEaseModule,
TownCountyOutlookModule, RenovationScenarioModule, ValueDriversModule.

**Wired in `build_engine` but not referenced by `ROUTING_MODULE_MAP`
(stronger deletion candidates):** PropertySnapshotModule,
MarketValueHistoryModule, ScarcitySupportModule, LocationIntelligenceModule,
LocalIntelligenceModule.

Several modules are cross-referenced by other legacy modules' constructors
(e.g. MarketValueHistoryModule is injected into ComparableSalesModule), so
the ordering matters — leaves first. The verification report's estimate of
"~9–10 unambiguously dead modules" is consistent with the second group plus
anything exclusive to the fallback synthesis path.

---

## 4. Probe re-run (`/tmp/scoped_vs_fallback.py`)

Re-executed today (2026-04-22) against `briarwood-rd-belmar`. State has not
changed since the verification report:

- Scoped path: `decision_stance=buy_if_price_improves`, `confidence=0.77`, `value_position.*` fully populated, `why_this_stance=1 line`.
- Forced fallback path: `decision_stance=pass_unless_changes`, `confidence=0.68`, `value_position.*=all None`, `why_this_stance=[]`.
- Per-module `data` key overlap across all 4 shared modules remains **zero** (scoped emits `{module_name, score, summary, metrics, legacy_payload, section_evidence}`; fallback emits nested per-legacy-module sub-keys).

The shape gap is live. Cache-key disambiguation (Phase 1) prevents cross-mode
collisions but does not prevent per-request divergence when the fallback
branch is reached.

---

## 5. Recommendation

**Path B1 — delete the fallback.**

Rationale:

1. **Coverage is 100%.** Every `selected_modules` combination the router
   produces (20 base × focus hints) resolves to modules with real scoped
   runners and no stubbed dependencies. `supports_scoped_execution` returns
   `True` for all of them. There is no routed module set that requires the
   fallback today.
2. **The fallback is unreachable from production paths.** In the current
   orchestrator flow the fallback branch at
   [briarwood/orchestrator.py:567-582](briarwood/orchestrator.py#L567-L582)
   only fires if `supports_scoped_execution` returns False — which §2.1
   shows it never does. The probe only reproduces divergence by
   monkey-patching that function to force `False`.
3. **The fallback is actively harmful when forced.** The probe shows it
   produces a different decision on the same fixture and crashes on
   null-price fixtures ([briarwood/modules/income_support.py:227-229](briarwood/modules/income_support.py#L227-L229)).
   Keeping it as a safety net means shipping a crash path.
4. **Fixing the adapter (Path B2) is higher-risk and lower-value.** The
   `_build_module_payload` shape (nested per-legacy-module sub-keys) was
   designed for the legacy report's `AnalysisReport.module_results` shape;
   rewriting it to emit the scoped flat shape without also rewiring the
   synthesizer's `metrics` expectations means re-deriving values
   (fair_value_base, basis_premium_pct, etc.) that the scoped executor
   already computes. That is work to make a branch produce outputs
   equivalent to the branch we're already running.

If §3's reference audit turns up a legacy module that lives outside the
fallback (e.g. LocalIntelligenceModule used by the town-intel path), that
module stays; B1 only removes modules exclusive to the fallback. No scoped
reimplementations required.

### 4.1 Minor caveat

`opportunity_cost` and `town_development_index` are scoped-only and
currently unreached by the router. B1 preserves them — deletion scope is
"modules the router can't reach AND that are wired only into the fallback".
If future routing adds `CAPITAL_ALLOCATION` to some intent, opportunity_cost
becomes reachable with no registry changes needed.

---

*End of Stage A. Awaiting human confirmation before proceeding to Stage B.*

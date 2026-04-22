# Briarwood V2 Scoped Execution Support

## What Scoped Execution Means

Scoped execution means Briarwood does not run the full legacy engine by default for a routed analysis when the requested path is already supported in the V2 registry.

The routed flow becomes:

`router -> execution planner -> scoped executor -> synthesis`

The planner selects the requested modules plus dependencies. The executor runs only those modules, can reuse cached module outputs when inputs have not changed, and reruns only affected modules plus downstream dependents when assumptions change.

If a routed path needs any module that is not yet implemented in the scoped registry, Briarwood falls back to the legacy full-engine path.

## Current Supported Modules

These modules have real scoped runners today (see `briarwood/execution/registry.py`):

- `valuation`
- `carry_cost`
- `risk_model`
- `confidence`
- `rent_stabilization`
- `hold_to_rent`
- `unit_income_offset`
- `legal_confidence`
- `resale_scenario`
- `rental_option`
- `renovation_impact`
- `arv_model`
- `margin_sensitivity`
- `opportunity_cost`
- `town_development_index`

## Fully Scoped Intents And Depths Today

Fully scoped means every selected module and dependency for that routed path is supported in the V2 registry.

With the full module set now registered, every routed intent/depth combination runs through the scoped executor by default. The legacy fallback remains as a safety net for validation failures or registry-bypass scenarios, not for missing modules.

## Known Legacy Coupling

Scoped execution is real, but several current runners still wrap legacy module classes.

Known coupling areas:

- `valuation`
  Wraps `CurrentValueModule`, which still pulls internal comparable, market-history, income-support, and hybrid anchors
- `rent_stabilization`
  Wraps `RentalEaseModule`, which still depends on legacy rent-support and town/scarcity logic
- `unit_income_offset`
  Reuses `ComparableSalesModule` hybrid decomposition for additional-unit income evidence
- `legal_confidence`
  Is an evidence-confidence wrapper, not a standalone legal review engine
- `hold_to_rent`
  Is a thin composite of prior scoped outputs, not yet a fully native standalone module

## Practical Summary

Briarwood V2 scoped execution now covers the buy-decision core, rent durability, hold-to-rent packaging, extra-unit offset evidence, legality-confidence evidence, resale and rental-option paths, renovation-heavy paths (`renovation_impact` + `arv_model` + `margin_sensitivity`), and forward-looking modules (`opportunity_cost`, `town_development_index`).

Legacy fallback is no longer expected for any routed intent — every module referenced by the router has a concrete runner in the registry. Remaining work in this area is decoupling runners from legacy module classes, not filling missing coverage.

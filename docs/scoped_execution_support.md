# Briarwood V2 Scoped Execution Support

## What Scoped Execution Means

Scoped execution means Briarwood does not run the full legacy engine by default for a routed analysis when the requested path is already supported in the V2 registry.

The routed flow becomes:

`router -> execution planner -> scoped executor -> synthesis`

The planner selects the requested modules plus dependencies. The executor runs only those modules, can reuse cached module outputs when inputs have not changed, and reruns only affected modules plus downstream dependents when assumptions change.

If a routed path needs any module that is not yet implemented in the scoped registry, Briarwood falls back to the legacy full-engine path.

## Current Supported Modules

These modules have real scoped runners today:

- `valuation`
- `carry_cost`
- `risk_model`
- `confidence`
- `rent_stabilization`
- `hold_to_rent`
- `unit_income_offset`
- `legal_confidence`

## Current Unsupported Modules

These modules still use clean registry stubs and trigger fallback when required:

- `resale_scenario`
- `rental_option`
- `renovation_impact`
- `arv_model`
- `margin_sensitivity`

## Fully Scoped Intents And Depths Today

Fully scoped means every selected module and dependency for that routed path is supported in the V2 registry.

Currently fully scoped:

- `buy_decision` + `snapshot`
- `buy_decision` + `decision`
- direct routed runs whose selected modules stay within the supported set above

Partially supported but not fully scoped at the intent level:

- `owner_occupant_then_rent`
  Because it still requires `rental_option`
- `house_hack_multi_unit`
  Some differentiated modules are scoped (`unit_income_offset`, `legal_confidence`, `rent_stabilization`), but full routed coverage still depends on `rental_option`
- `owner_occupant_short_hold`
  Still depends on `resale_scenario`
- `renovate_then_sell`
  Still depends on `renovation_impact`, `arv_model`, and `margin_sensitivity`

## Paths That Still Use Fallback

Legacy fallback is used whenever the routed module set includes an unsupported module.

Common fallback cases:

- short-hold resale paths
- owner-occupant then rent paths that need `rental_option`
- renovate-then-sell paths
- any deep-dive run that expands into unsupported renovation or resale modules

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

## Next Modules To Decouple

Highest-value next modules:

1. `rental_option`
   This unlocks full scoped support for owner-occupant-then-rent and most house-hack routed paths
2. `resale_scenario`
   This unlocks short-hold decision paths without legacy fallback
3. `renovation_impact`
   This is the first step toward scoped renovation execution
4. `arv_model`
5. `margin_sensitivity`

## Practical Summary

Today, Briarwood V2 scoped execution covers the buy-decision core plus rent durability, hold-to-rent packaging, extra-unit offset evidence, and legality-confidence evidence.

It does not yet fully replace the legacy engine for resale, rental-option, or renovation-heavy paths.

# Briarwood Model System Audit

## Summary

- Generated at: `2026-04-19T11:18:36.672522+00:00`
- Rows audited: `34`
- Sample cases: `36` across `6` properties and `6` prompts
- Highest-priority components right now: rent_stabilization, confidence, legal_confidence, hold_to_rent, renovation_impact

## Master Scorecard

| component | row type | purpose | property read | determination | forward to user | unified relativity | contract/test | overall health | improvement priority | top gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rent_stabilization | module | How durable is rent income? | 40 | 70 | 35 | 40 | 75 | 48 | 62 | **Hard crash on thin inputs.** [test_thin_inputs_crash_today](../../tests/modules/test_rent_stabilization_isolated.py#L30) locks in a `TypeError: income_support module payload is not an IncomeAgentOutput` when property_data lacks `purchase_price`. This is the worst failure mode in the Phase 2 sweep — a production data edge case will crash the whole analysis. |
| confidence | module | How much should we trust this? | 40 | 90 | 20 | 40 | 80 | 50 | 60 | Module output is weakly represented or invisible in current user-facing surfaces. |
| legal_confidence | module | Is the intended use legal? | 40 | 90 | 20 | 20 | 75 | 45 | 55 | **Output is stranded.** No rent, risk, or valuation module consumes `legality_evidence`. The module produces a meaningful signal (2 warnings fire on the unique-property fixture) but nothing acts on it. |
| hold_to_rent | module | Can rent offset carry? | 60 | 70 | 35 | 60 | 80 | 57 | 53 | Module output is weakly represented or invisible in current user-facing surfaces. |
| renovation_impact | module | What value does reno create? | 60 | 85 | 20 | 20 | 55 | 48 | 52 | Module output is weakly represented or invisible in current user-facing surfaces. |
| resale_scenario | module | How does value evolve? | 30 | 70 | 100 | 20 | 100 | 59 | 51 | **Confidence is insensitive to fragile financing.** Normal and fragile fixtures produce identical ~0.6 confidence. |
| rental_option | module | What can it earn as a rental? | 50 | 70 | 100 | 20 | 55 | 62 | 48 | Declared dependency chain is not being meaningfully consumed: valuation / **not used**. |
| risk_model | module | What could go wrong? | 30 | 90 | 100 | 20 | 100 | 64 | 46 | **Confidence is constant (~0.72) across normal / contradictory / fragile inputs.** This is *the* silo signature. The harness locks it in with `assertEqual(normal, contradictory)` so the moment Phase 4 wires real inputs, the test goes red. |
| arv_model | module | What's the post-reno value? | 60 | 85 | 20 | 60 | 55 | 56 | 44 | Module output is weakly represented or invisible in current user-facing surfaces. |
| carry_cost | module | What does it cost to own? | 80 | 70 | 65 | 40 | 80 | 66 | 44 | None |
| unit_income_offset | module | How much does an extra unit offset carry? | 80 | 85 | 20 | 60 | 55 | 61 | 39 | Module output is weakly represented or invisible in current user-facing surfaces. |
| valuation | module | What is fair value? | 60 | 90 | 100 | 20 | 100 | 72 | 38 | **Contradictory inputs do not degrade confidence or warn.** A $2.4M ask on 700 sqft / 6 beds / 1 bath (contradictory fixture) produces `confidence ≈ 0.62` with zero warnings. There is no sanity check against sqft×$/sqft ballpark. |
| margin_sensitivity | module | How fragile is the reno margin? | 80 | 100 | 20 | 60 | 55 | 65 | 35 | Module output is weakly represented or invisible in current user-facing surfaces. |
| town_x_scenario | bridge | Cross-check scenario appreciation assumptions against town strength and regime. | 68 | 72 | 50 | 82 | 82 | 68 | 32 | Realism checks are present in bridge logic but not rendered as a dedicated scenario realism indicator for the user. |
| session_slot_population | ui_surface | Persist model-derived render state in session slots before SSE translation. | 72 | 68 | 88 | 76 | 86 | 76 | 29 | Every feature depends on slot completeness, so missing slot population silently strands good model output. |
| town_development_index | module | Registry-defined scoped module. | 60 | 85 | 65 | 80 | 55 | 71 | 29 | Registry-present, inventory doc missing. |
| ui_surface_comps_preview | ui_surface | Show the comp evidence backing the current pricing stance. | 78 | 74 | 88 | 66 | 88 | 78 | 27 | Comp evidence is now present, but dedicated CMA visualization is still thinner than the underlying comp logic. |
| ui_surface_module_attribution | ui_surface | Show which model layers materially contributed to the response. | 64 | 70 | 78 | 78 | 84 | 73 | 27 | Module attribution exists, but it still reflects surfaced events more than true causal contribution strength. |
| conflict_detector | bridge | Enumerate cross-model contradictions that should block a clean recommendation. | 74 | 78 | 58 | 84 | 84 | 74 | 26 | Conflicts are synthesized into risks but do not appear as a dedicated contradiction section in the UI. |
| rent_x_risk | bridge | Downgrade rent confidence when legal, stabilization, or risk signals weaken rental realism. | 75 | 80 | 52 | 90 | 86 | 74 | 26 | Adjusted rent confidence influences synthesis but is still mostly hidden from the user beyond narrative caution. |
| valuation_x_town | bridge | Adjust acceptable premium band using town scarcity and desirability. | 72 | 78 | 55 | 90 | 85 | 74 | 26 | Town modulation is consumed indirectly through synthesis, not exposed as a first-class user-facing explanation. |
| sse_event_translation | ui_surface | Translate session slots into ordered SSE events with typed payloads. | 74 | 72 | 92 | 78 | 90 | 80 | 25 | Ordering and omission bugs here can make valid backend output look missing in the UI. |
| ui_surface_native_charts | ui_surface | Render native chart specs for scenario, risk, value gap, and rent visuals. | 78 | 82 | 92 | 70 | 86 | 81 | 24 | Charts are now native, but bridge-derived annotations and explicit interpretive labels still lag behind the math. |
| ui_surface_value_thesis | ui_surface | Render ask vs fair value plus the comps and thesis behind it. | 80 | 84 | 88 | 70 | 88 | 81 | 24 | Value thesis is strong, but bridge-derived rationale like premium band adjustment still gets compressed into prose. |
| unified_intelligence | unified | Synthesize structured module and bridge evidence into the decision-first answer. | 82 | 88 | 82 | 94 | 92 | 86 | 24 | Unified Intelligence is strong structurally, but bridge-derived nuances are still more legible in code than in the user-facing UI. |
| ui_surface_strategy_path | ui_surface | Show the recommended path and strategic posture clearly. | 74 | 78 | 82 | 70 | 86 | 77 | 23 | Strategy path is present, but some turns still surface it as a secondary detail instead of an action-first card. |
| valuation_x_risk | bridge | Demand extra discount when risk flags weaken price acceptability. | 74 | 82 | 60 | 92 | 85 | 77 | 23 | The bridge adjusts decision logic but the extra discount demand is still not legible as its own visible UI element. |
| rent_x_cost | bridge | Translate rent and carry into carry-offset and break-even logic. | 78 | 84 | 68 | 88 | 86 | 79 | 21 | Bridge output affects path logic but the carry-offset ratio is not shown as a named metric in the current rent UI. |
| scenario_x_risk | bridge | Turn scenario assumptions into fragility and what-must-be-true conditions. | 77 | 84 | 66 | 92 | 86 | 79 | 21 | Fragility is used by Unified Intelligence, but scenario visuals still do not explicitly annotate the what-must-be-true burden. |
| primary_value_source | bridge | Classify which value story dominates the property thesis. | 80 | 82 | 72 | 88 | 86 | 80 | 20 | Primary value source is attached to synthesis but still under-explained in the UI outside terse labels. |
| ui_surface_risk_profile | ui_surface | Render structured risk outputs and downside visuals. | 78 | 82 | 86 | 72 | 88 | 80 | 20 | Risk is visible on risk turns but still underrepresented in browse/decision first impressions. |
| ui_surface_scenario_table | ui_surface | Render bull/base/bear scenario values against the working basis. | 84 | 88 | 92 | 74 | 90 | 85 | 20 | Scenario math now flows through, but scenario realism and fragility are still not visually annotated enough. |
| ui_surface_verdict | ui_surface | Render the decision verdict in a clear user-facing card. | 82 | 86 | 96 | 74 | 90 | 85 | 20 | Verdict is strong in decision turns but not reused as a strong framing primitive in browse-like first impressions. |
| ui_surface_rent_outlook | ui_surface | Render rent setup, rent regime context, and rental support. | 82 | 84 | 88 | 74 | 88 | 83 | 17 | Rent is now clearer, but carry-offset and adjusted rent confidence still remain implicit. |

## User-Forwarding Matrix

| source component | session slot | SSE event | UI component/card/chart | narrative mention | status |
| --- | --- | --- | --- | --- | --- |
| valuation | last_decision_view | verdict | VerdictCard | decision recommendation | full |
| town_development_index | last_town_summary | town_summary | TownSummaryCard | town backdrop | partial |
| valuation | last_comps_preview | comps_preview | CompsPreviewCard | comp support | full |
| valuation | last_value_thesis_view | value_thesis | ValueThesisCard | value gap explanation | full |
| risk_model | last_risk_view | risk_profile | RiskProfileCard | risk narrative | full |
| carry_cost | last_strategy_view | strategy_path | StrategyPathCard | best path | partial |
| rental_option | last_rent_outlook_view | rent_outlook | RentOutlookCard | rent setup | full |
| resale_scenario | last_projection_view | scenario_table | ScenarioTable | scenario range | full |
| valuation | last_value_thesis_view | chart | ChartFrame | value gap chart | full |
| risk_model | last_risk_view | chart | ChartFrame | risk chart | full |
| rental_option | last_rent_outlook_view | chart | ChartFrame | rent burn / ramp chart | full |
| resale_scenario | last_projection_view | chart | ChartFrame | scenario fan | full |
| pipeline_adapter | tracked event order | modules_ran | Module badge row | module attribution | partial |
| listing_discovery | last_live_listing_results | listings | PropertyCarousel | focal property card | full |
| geocoder | n/a | map | InlineMap | map context | full |

## Unified / Bridge Coherence

| bridge or unified rule | upstream components | expected adjustment/gate | current behavior | coherence score | main failure mode |
| --- | --- | --- | --- | --- | --- |
| valuation_x_town | valuation, town_development_index / scarcity priors | Widen or tighten acceptable premium band by town strength. | Feeds synthesis premium tolerance, not a dedicated UI band display. | 82 | Adjustment is real but under-explained to the user. |
| valuation_x_risk | valuation, risk_model | Demand extra discount when risk flags accumulate. | Used in decision stance and recommendation wording. | 88 | Risk-adjusted discount is not surfaced as an explicit metric. |
| rent_x_cost | carry_cost, rental_option / hold_to_rent | Expose carry-offset ratio and break-even probability. | Influences strategy classification and synthesis. | 84 | Named bridge outputs are still mostly hidden from the UI. |
| rent_x_risk | rental_option / hold_to_rent, legal_confidence, rent_stabilization, risk_model | Downgrade rent confidence when legal or regulatory risks weaken realism. | Feeds synthesis caution but not a strong visible rent-confidence indicator. | 80 | Bridge value is trapped in synthesis rather than shown directly. |
| scenario_x_risk | resale_scenario / arv_model / margin_sensitivity, risk_model | Translate scenario assumptions into fragility and what-must-be-true conditions. | Drives fragility inside Unified Intelligence. | 90 | Scenario visuals do not yet label fragility explicitly enough. |
| town_x_scenario | resale_scenario / arv_model, town priors | Mark appreciation assumptions as realistic, optimistic, or aggressive. | Available to synthesis, not shown as a named chart/table attribute. | 76 | Scenario realism is under-surfaced. |
| primary_value_source | strategy_classifier, valuation, carry_cost, scenario outputs | Pick the dominant value story for recommendation framing. | Attached to unified output and some value-thesis surfaces. | 86 | Source classification is visible but not yet a strong UI framing primitive. |
| conflict_detector | valuation, risk_model, legal_confidence, rental_option, carry_cost | Surface contradictions that should block a clean stance. | Feeds trust/risk framing inside synthesis. | 78 | Conflicts are not exposed as their own first-class user section. |
| Unified Intelligence trust gate | module outputs, bridge trace | Collapse strong stances when trust is too low. | Implemented deterministically in structured synthesis. | 92 | Trust logic is strong but still difficult to inspect in UI terms. |

## Sample-Case Heatmap

| property | prompt | expected core components | actual components surfaced | missing user evidence | pass/partial/fail |
| --- | --- | --- | --- | --- | --- |
| 1008-14th-ave-belmar-nj-07719 | what do you think of [property] | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | — | pass |
| 1008-14th-ave-belmar-nj-07719 | should I buy this | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | — | pass |
| 1008-14th-ave-belmar-nj-07719 | what does the CMA look like | comps_preview, value_thesis, value_chart, modules_ran | comps_preview, value_thesis, value_chart, modules_ran | dedicated_cma_table | partial |
| 1008-14th-ave-belmar-nj-07719 | what would a 10% price cut do | scenario_table, scenario_fan, modules_ran | scenario_table, scenario_fan, modules_ran | — | pass |
| 1008-14th-ave-belmar-nj-07719 | what's the rental potential | rent_outlook, rent_burn, rent_ramp, modules_ran | rent_outlook, rent_burn, rent_ramp, modules_ran | — | pass |
| 1008-14th-ave-belmar-nj-07719 | what could go wrong | risk_profile, risk_chart, modules_ran | risk_profile, risk_chart, modules_ran | — | pass |
| 1600-l-street-belmar-nj-07719 | what do you think of [property] | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | — | pass |
| 1600-l-street-belmar-nj-07719 | should I buy this | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | — | pass |
| 1600-l-street-belmar-nj-07719 | what does the CMA look like | comps_preview, value_thesis, value_chart, modules_ran | comps_preview, value_thesis, value_chart, modules_ran | dedicated_cma_table | partial |
| 1600-l-street-belmar-nj-07719 | what would a 10% price cut do | scenario_table, scenario_fan, modules_ran | scenario_table, scenario_fan, modules_ran | — | pass |
| 1600-l-street-belmar-nj-07719 | what's the rental potential | rent_outlook, rent_burn, rent_ramp, modules_ran | rent_outlook, rent_burn, rent_ramp, modules_ran | — | pass |
| 1600-l-street-belmar-nj-07719 | what could go wrong | risk_profile, risk_chart, modules_ran | risk_profile, risk_chart, modules_ran | — | pass |
| 1228-briarwood-road-belmar-nj | what do you think of [property] | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | — | pass |
| 1228-briarwood-road-belmar-nj | should I buy this | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | — | pass |
| 1228-briarwood-road-belmar-nj | what does the CMA look like | comps_preview, value_thesis, value_chart, modules_ran | comps_preview, value_thesis, value_chart, modules_ran | dedicated_cma_table | partial |
| 1228-briarwood-road-belmar-nj | what would a 10% price cut do | scenario_table, scenario_fan, modules_ran | scenario_table, scenario_fan, modules_ran | — | pass |
| 1228-briarwood-road-belmar-nj | what's the rental potential | rent_outlook, rent_burn, rent_ramp, modules_ran | rent_outlook, rent_burn, rent_ramp, modules_ran | — | pass |
| 1228-briarwood-road-belmar-nj | what could go wrong | risk_profile, risk_chart, modules_ran | risk_profile, risk_chart, modules_ran | — | pass |
| 526-west-end-ave | what do you think of [property] | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | — | pass |
| 526-west-end-ave | should I buy this | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | — | pass |
| 526-west-end-ave | what does the CMA look like | comps_preview, value_thesis, value_chart, modules_ran | comps_preview, value_thesis, value_chart, modules_ran | dedicated_cma_table | partial |
| 526-west-end-ave | what would a 10% price cut do | scenario_table, scenario_fan, modules_ran | scenario_table, scenario_fan, modules_ran | — | pass |
| 526-west-end-ave | what's the rental potential | rent_outlook, rent_burn, rent_ramp, modules_ran | rent_outlook, rent_burn, rent_ramp, modules_ran | — | pass |
| 526-west-end-ave | what could go wrong | risk_profile, risk_chart, modules_ran | risk_profile, risk_chart, modules_ran | — | pass |
| briarwood-rd-belmar | what do you think of [property] | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | — | pass |
| briarwood-rd-belmar | should I buy this | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | — | pass |
| briarwood-rd-belmar | what does the CMA look like | comps_preview, value_thesis, value_chart, modules_ran | comps_preview, value_thesis, value_chart, modules_ran | dedicated_cma_table | partial |
| briarwood-rd-belmar | what would a 10% price cut do | scenario_table, scenario_fan, modules_ran | scenario_table, scenario_fan, modules_ran | — | pass |
| briarwood-rd-belmar | what's the rental potential | rent_outlook, rent_burn, rent_ramp, modules_ran | rent_outlook, rent_burn, rent_ramp, modules_ran | — | pass |
| briarwood-rd-belmar | what could go wrong | risk_profile, risk_chart, modules_ran | risk_profile, risk_chart, modules_ran | — | pass |
| 1223-ocean-rd-bridgehampton-ny-11932 | what do you think of [property] | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | town_summary, comps_preview, value_thesis, strategy_path, rent_outlook, scenario_table, native_chart, modules_ran | — | pass |
| 1223-ocean-rd-bridgehampton-ny-11932 | should I buy this | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | verdict, town_summary, comps_preview, scenario_table, native_chart, modules_ran | — | pass |
| 1223-ocean-rd-bridgehampton-ny-11932 | what does the CMA look like | comps_preview, value_thesis, value_chart, modules_ran | comps_preview, value_thesis, value_chart, modules_ran | dedicated_cma_table | partial |
| 1223-ocean-rd-bridgehampton-ny-11932 | what would a 10% price cut do | scenario_table, scenario_fan, modules_ran | scenario_table, scenario_fan, modules_ran | — | pass |
| 1223-ocean-rd-bridgehampton-ny-11932 | what's the rental potential | rent_outlook, rent_burn, rent_ramp, modules_ran | rent_outlook, rent_burn, rent_ramp, modules_ran | — | pass |
| 1223-ocean-rd-bridgehampton-ny-11932 | what could go wrong | risk_profile, risk_chart, modules_ran | risk_profile, risk_chart, modules_ran | — | pass |

## Top Priority Fixes

- `rent_stabilization` (module, priority 62): **Hard crash on thin inputs.** [test_thin_inputs_crash_today](../../tests/modules/test_rent_stabilization_isolated.py#L30) locks in a `TypeError: income_support module payload is not an IncomeAgentOutput` when property_data lacks `purchase_price`. This is the worst failure mode in the Phase 2 sweep — a production data edge case will crash the whole analysis. Fix: **Phase 3 (highest priority):** Make `IncomeSupportModule` robust to missing `purchase_price`. Either normalize in intake or guard in the scoped runner.
- `confidence` (module, priority 60): Module output is weakly represented or invisible in current user-facing surfaces. Fix: Fix — replace with real trust-calibration rollup in Phase 5
- `legal_confidence` (module, priority 55): **Output is stranded.** No rent, risk, or valuation module consumes `legality_evidence`. The module produces a meaningful signal (2 warnings fire on the unique-property fixture) but nothing acts on it. Fix: **Phase 3:** Replace hardcoded 0.72 / 0.48 in `PropertyDataQualityModule` with field-coverage scoring.
- `hold_to_rent` (module, priority 53): Module output is weakly represented or invisible in current user-facing surfaces. Fix: Fix — promote to a real `rent_x_cost` bridge (carry_offset_ratio, break-even probability)
- `renovation_impact` (module, priority 52): Module output is weakly represented or invisible in current user-facing surfaces. Fix: Keep — solid standalone; needs bridge to risk for execution-dependence
- `resale_scenario` (module, priority 51): **Confidence is insensitive to fragile financing.** Normal and fragile fixtures produce identical ~0.6 confidence. Fix: **Phase 4:** `town_x_scenario` bridge — adjust bull/bear spread using town liquidity + scarcity signal.
- `rental_option` (module, priority 48): Declared dependency chain is not being meaningfully consumed: valuation / **not used**. Fix: Fix — actually use valuation output or drop dep
- `risk_model` (module, priority 46): **Confidence is constant (~0.72) across normal / contradictory / fragile inputs.** This is *the* silo signature. The harness locks it in with `assertEqual(normal, contradictory)` so the moment Phase 4 wires real inputs, the test goes red. Fix: **Phase 4 (highest priority):** Implement `valuation_x_risk` bridge. Risk must read valuation's premium_vs_comps, liquidity_signal, comp_coverage.
- `arv_model` (module, priority 44): Module output is weakly represented or invisible in current user-facing surfaces. Fix: Keep — mostly fine; add comp-coverage trust flag
- `carry_cost` (module, priority 44): None Fix: Fix — expose break-even rent + owner-occ vs investor cases as first-class

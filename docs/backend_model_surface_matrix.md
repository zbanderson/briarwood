# Backend Model Surface Matrix

This is the current audit doc for Briarwood's canonical chat experience.

Baseline flow:
- Decision-tier turn using `Analyze 1008 14th Avenue, Belmar, NJ 07719`
- Follow-up value-view questions such as `What would change your value view?`

Status meanings:
- `surfaced`: backend output is populated on the canonical decision turn and rendered in the Next.js chat UI
- `decision-followup-only`: backend output exists and is rendered, but not on the canonical first decision turn
- `indirect`: backend logic contributes through another surfaced model/card rather than its own first-class UI surface
- `unwired`: model exists in Python but does not currently reach the canonical chat UI

## Chat Surface Contract

| Backend model / source | Session slot | SSE event | Reducer field | UI surface | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Decision synthesis / `PropertyView.load(..., depth="decision")` | `last_decision_view` | `verdict` | `verdict` | `VerdictCard` | `surfaced` | Canonical first-turn decision contract |
| Town summary | `last_town_summary` | `town_summary` | `townSummary` | `TownSummaryCard` | `surfaced` | Built from town diagnostics + local intelligence |
| Comp preview | `last_comps_preview` | `comps_preview` | `compsPreview` | `CompsPreviewCard` | `surfaced` | Compact preview layer, not provenance-safe valuation evidence |
| Value thesis | `last_value_thesis_view` | `value_thesis` | `valueThesis` | `EntryPointCard`, `ValueThesisCard` | `surfaced` | Decision-first value framing |
| Valuation-module comps | `last_value_thesis_view.comps` | `valuation_comps` | `valuationComps` | `CompsTableCard` | `surfaced` | Only comps that fed fair value |
| Live-market support comps | `last_market_support_view` | `market_support_comps` | `marketSupportComps` | `CompsTableCard` | `surfaced` | Context comps, not fair-value evidence |
| Risk profile | `last_risk_view` | `risk_profile` | `riskProfile` | `RiskProfileCard` | `surfaced` | Decision turn now populates this explicitly |
| Strategy fit | `last_strategy_view` | `strategy_path` | `strategyPath` | `StrategyPathCard` | `surfaced` | Decision turn now populates this explicitly |
| Rent outlook | `last_rent_outlook_view` | `rent_outlook` | `rentOutlook` | `RentOutlookCard` | `surfaced` | Decision turn now populates this explicitly |
| Trust summary | `last_trust_view` or derived trust payload | `trust_summary` | `trustSummary` | `TrustSummaryCard` | `surfaced` | Surfaced on decision/browse/rent flows when present |
| Projection / scenarios | `last_projection_view` | `scenario_table` | `scenarioTable` | `ScenarioTable` | `surfaced` | First-turn decision scenario table |
| Representation-selected charts | `last_*_view` set | `chart` | `charts` | `ChartFrame` | `surfaced` | Claim-driven chart selection layer |
| Grounding verifier | `last_verifier_report` | `verifier_report`, `grounding_annotations` | `verifierReport`, `groundingAnchors` | `VerifierReasoningPanel`, `GroundedText` | `surfaced` | Advisory verification shown inline |
| Partial-data degradation notices | `last_partial_data_warnings` | `partial_data_warning` | `partialDataWarnings` | `PartialDataBanner` | `surfaced` | Now reserved for real lost surfaces / enrichment failures |

## Backend Model Status

| Model / module | Primary chat path | Status | Notes |
| --- | --- | --- | --- |
| `valuation` | verdict, value thesis, valuation comps, value chart | `surfaced` | Main fair-value engine in the canonical decision flow |
| `current_value` | via `valuation` | `indirect` | Contributes to fair value, not shown as its own card |
| `comparable_sales` | via `valuation` / valuation comps | `indirect` | Provenance-safe surface is `valuation_comps` |
| `market_value_history` | via `valuation` | `indirect` | Influences valuation but has no direct chat card |
| `income_support` | via `valuation`, strategy, rent | `indirect` | Supports decision/value/rent surfaces |
| `hybrid_value` | via `valuation` | `indirect` | Folded into the unified fair-value read |
| `risk_model` | risk card + risk chart | `surfaced` | Now populated on the canonical decision turn |
| `resale_scenario` | scenario table + scenario chart | `surfaced` | Decision turn populates the projection view |
| `strategy_fit` | strategy card | `surfaced` | Surfaced through `strategy_path` |
| `rent_outlook` / `rent_lookup` | rent card + rent charts | `surfaced` | Decision turn now populates the canonical rent surface |
| `confidence` | trust summary / warnings | `indirect` | Contributes through trust payloads rather than a dedicated model card |
| `legal_confidence` | trust / blocked-thesis effects | `indirect` | Present only through synthesis/trust outputs today |
| `carry_cost` | strategy/rent outputs | `indirect` | Reflected in monthly cash flow / break-even framing |
| `rental_option` | rent/strategy outputs | `indirect` | No dedicated UI surface |
| `rent_stabilization` | rent outlook | `indirect` | Reflected in rent range / ease labels |
| `hold_to_rent` | strategy/rent narrative | `indirect` | No dedicated UI artifact |
| `arv_model` | renovation / projection paths | `decision-followup-only` | Available outside the canonical first-turn decision surface |
| `margin_sensitivity` | renovation follow-up | `decision-followup-only` | Not part of the standard purchase decision turn |
| `unit_income_offset` | niche rent/strategy follow-up | `decision-followup-only` | No first-turn canonical surface |
| `renovation_impact` | renovation follow-up | `decision-followup-only` | Surfaces in specialized projection flows |
| `value_drivers` | folded into value thesis | `indirect` | Not a standalone first-class chart/card anymore |
| `value_finder` | folded into value thesis | `indirect` | Decision-first value framing absorbs it |
| `teardown_scenario` | none | `unwired` | Exists in codebase, not routed into canonical chat UI |

## Belmar Baseline Notes

- For `1008 14th Avenue, Belmar, NJ 07719`, the canonical first-turn UI should now carry verdict, value thesis, valuation comps, live-market comps, risk, strategy, rent outlook, town context, trust, scenario, and representation-selected charts when the underlying model outputs are available.
- Follow-up value questions should ground ask, fair value, and premium/discount using structured payload fields rather than forcing the LLM to improvise numbers.
- Bare address numbers such as `1008` should only bypass `ungrounded_number` when they appear as part of a grounded address string; invented numeric claims should still be flagged.

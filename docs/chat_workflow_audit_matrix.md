# Chat Workflow Audit Matrix

This matrix tracks the live chat contract from backend model output to UI render.

| Tier | Model / handler source | Session slot(s) | SSE event(s) | Frontend reducer field(s) | UI render |
| --- | --- | --- | --- | --- | --- |
| `search` | `handle_search` | `last_live_listing_results`, `search_context` | `listings`, `map`, `suggestions` | `listings`, `map` | `PropertyCarousel`, `InlineMap` |
| `browse` | `handle_browse` + presentation helpers | `current_property_id` | `listings`, `map`, `suggestions` | `listings`, `map` | `PropertyCarousel`, `DetailPanel`, `InlineMap` |
| `decision` | `handle_decision` | `last_decision_view`, `last_town_summary`, `last_comps_preview`, `last_projection_view` | `verdict`, `town_summary`, `comps_preview`, `scenario_table`, `chart` | `verdict`, `townSummary`, `compsPreview`, `scenarioTable`, `charts` | `VerdictCard`, `TownSummaryCard`, `CompsPreviewCard`, `ScenarioTable`, `ChartFrame` |
| `risk` | `handle_risk` | `last_risk_view` | `risk_profile`, `chart` | `riskProfile`, `charts` | `RiskProfileCard`, `ChartFrame` |
| `edge` | `handle_edge` | `last_value_thesis_view` | `value_thesis`, `chart` | `valueThesis`, `charts` | `ValueThesisCard`, `ChartFrame` |
| `strategy` | `handle_strategy` | `last_strategy_view` | `strategy_path` | `strategyPath` | `StrategyPathCard` |
| `rent_lookup` | `handle_rent_lookup` | `last_rent_outlook_view` | `rent_outlook`, `chart` | `rentOutlook`, `charts` | `RentOutlookCard`, `ChartFrame` |
| `research` | `handle_research` | `last_research_view` | `research_update` | `researchUpdate` | `ResearchUpdateCard` |

## Notes

- Core decision-style cards are emitted before prose so the user sees the structured result even while narration is still streaming.
- Primary charts now flow through native `chart.spec` payloads for `scenario_fan`, `risk_bar`, `rent_burn`, and `value_opportunity`.
- Listing payloads now carry `streetViewImageUrl`, sourced from saved enrichment artifacts when available and otherwise derived from geocoded coordinates.

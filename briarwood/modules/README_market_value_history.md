# market_value_history — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`market_value_history` surfaces the Zillow ZHVI (Zillow Home Value Index) historical price trajectory for the town/county containing a subject property. It answers the orchestrator's question *"how has this market been trending?"* with a time-series of monthly ZHVI points, the current level, and 1yr / 3yr change percentages. Call this tool when the user's intent involves market trend context (`RESEARCH`, `BROWSE`, `PROJECTION`) or when downstream modules need a historical anchor for scenario framing. **The tool operates at geography level** — the output describes the town/county, not the subject property, and should not be used to answer property-specific trend questions.

## Location

- **Entry point:** [briarwood/modules/market_value_history_scoped.py](market_value_history_scoped.py) — `run_market_value_history(context: ExecutionContext) -> dict[str, object]`
- **Legacy module:** [briarwood/modules/market_value_history.py:15](market_value_history.py#L15) — `MarketValueHistoryModule.run(property_input)` wrapped in-process by the scoped runner.
- **Registry entry:** [briarwood/execution/registry.py](../execution/registry.py) — `ModuleSpec(name="market_value_history", depends_on=[], required_context_keys=["property_data"], runner=run_market_value_history)`
- **Data source:** `data/market_history/zillow_zhvi_history.json` (file-backed via `FileBackedZillowHistoryProvider` at [briarwood/agents/market_history/](../agents/market_history/)).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RESEARCH` — called for "how has this market moved?" questions.
- `BROWSE` — called as context for browse-mode summaries.
- `PROJECTION` — called as a historical anchor when projecting forward.
- `DECISION` — called indirectly via `current_value` / `valuation`.
- Not called for: `LOOKUP` questions about the subject property itself (this is geography-level).

## Inputs

Inputs arrive through [ExecutionContext](../execution/context.py) and are normalized into a `PropertyInput` via `build_property_input_from_context`.

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.town` | `str` | yes | listing facts / user | Used as the geography key. |
| `context.property_data.state` | `str` | yes | listing facts / user | Used as the geography key. |
| `context.property_data.county` | `str` | optional | listing facts | Fallback geography when town-level data is absent. |

No property-level facts (sqft, beds, baths, purchase price) are consulted — the lookup is purely geography-keyed.

## Outputs

The runner returns `ModulePayload.model_dump()`. Metrics are populated from the underlying `MarketValueHistoryOutput` at [briarwood/agents/market_history/](../agents/market_history/).

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `data.metrics.source_name` | `str` | — | Provider label (e.g., Zillow ZHVI). |
| `data.metrics.geography_name` | `str` | — | Town or county name resolved from input. |
| `data.metrics.geography_type` | `str` | enum | `"town"` \| `"county"` \| `"metro"` depending on coverage hit. |
| `data.metrics.current_value` | `float \| None` | USD | Most recent ZHVI level for the geography. |
| `data.metrics.one_year_change_pct` | `float \| None` | fraction | YoY change. Null when <12 months of data. |
| `data.metrics.three_year_change_pct` | `float \| None` | fraction | 3-year change. Null when <36 months of data. |
| `data.metrics.history_points` | `int` | count | Number of time-series points available. |
| `data.legacy_payload.points` | `list[HistoryPoint]` | — | Full time-series (passed through for callers that chart). |
| `data.legacy_payload.summary` | `str` | prose | Human-readable one-liner. |
| `confidence` | `float` | 0.0–1.0 | 0.0 when no points; higher when deep coverage. |
| `warnings` | `list[str]` | — | Populated on fallback. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]`.
- **Benefits from (optional):** `property_summary`, `market_context`.
- **Calls internally:** `MarketValueHistoryAgent` + `FileBackedZillowHistoryProvider`.
- **Must not run concurrently with:** none.
- **Downstream scoped consumers (in-process):** `CurrentValueModule` (transitively via `valuation`), `ComparableSalesModule`, `bull_base_bear` (deprecating). These consume the legacy module directly via `MarketValueHistoryModule()`; they do NOT read the scoped tool's `prior_outputs`.

## Invariants

- Never raises. Any exception returns `module_payload_from_error` (`mode="fallback"`, `confidence=0.08`).
- `geography_name` and `geography_type` are populated whenever `town` + `state` are provided, even if the ZHVI file has no coverage for that town (in which case `current_value` will be `None` and `history_points == 0`).
- The payload describes the *geography containing the property*, never the property itself. Callers must not misuse it as a property-level signal.
- Deterministic for fixed inputs; no LLM, no randomness, file-backed lookup only.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.market_value_history_scoped import run_market_value_history

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "address": "12 Main St",
        "town": "Montclair",
        "state": "NJ",
        "county": "Essex",
    },
)

payload = run_market_value_history(context)
# payload["data"]["metrics"]["geography_name"]        == "Montclair"
# payload["data"]["metrics"]["geography_type"]        == "town"
# payload["data"]["metrics"]["current_value"]         ≈ 780_000.0   # or None if no coverage
# payload["data"]["metrics"]["one_year_change_pct"]   ≈ 0.034
# payload["confidence"]                               ∈ [0, 1]
```

## Hardcoded Values & TODOs

- Data file path is hardcoded at [market_value_history.py:22-24](market_value_history.py#L22-L24): `data/market_history/zillow_zhvi_history.json`. Changing the provider backend requires changing this path or constructing the module with a custom `MarketValueHistoryAgent`.
- Five-year change percentage is exposed by the legacy output but not surfaced in `metrics` — only `one_year_change_pct` and `three_year_change_pct` are populated. Five-year figures live in `legacy_payload.five_year_change_pct`.

## Blockers for Tool Use

- None — promoted to scoped registry in Handoff 3 on 2026-04-24.

## Notes

- **Geography framing is load-bearing.** The orchestrating LLM must never paraphrase this tool's output as a property-specific forecast. The README, registry description, and runner docstring all repeat this constraint to keep the LLM on rails.
- The ZHVI dataset is refreshed on a cadence outside Briarwood's control; freshness warnings surface via `confidence_notes` (when present) on the underlying agent output.
- Latency: sub-millisecond (file-backed lookup, no network). No LLM cost.

## Changelog

### 2026-04-24
- Initial README created.
- Promoted to scoped execution registry; see [PROMOTION_PLAN.md](../../PROMOTION_PLAN.md) entry 4.
- Contract: new scoped runner `run_market_value_history(context)` wraps `MarketValueHistoryModule.run(property_input)` via `module_payload_from_legacy_result`. Legacy module contract unchanged. Error contract per [DECISIONS.md](../../DECISIONS.md) 2026-04-24 *Scoped wrapper error contract*.

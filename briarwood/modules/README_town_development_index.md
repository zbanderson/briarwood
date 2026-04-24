# town_development_index — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`town_development_index` produces a single forward-looking development-velocity score (0-1) for the property's town, derived from the rolling window of planning/zoning board minutes stored as `MinutesRecord` fixtures under `JsonMinutesStore`. The composite weighs approval rate, activity volume (decisions/month, time-weighted), substantive ordinance/subdivision activity, restrictive signals (moratoria, denials), and public-contention density extracted from meeting summaries. Recent months dominate via an exponential decay with a 6-month half-life. Call this tool whenever the user's intent involves forward-looking resale, town-level research, or a strategy question where the local regulatory pipeline matters; downstream it is the anchor for `resale_scenario`'s forward projection and a supplementary confidence nudge for `valuation`.

## Location

- **Entry point:** [briarwood/modules/town_development_index.py:337](town_development_index.py#L337) — `run_town_development_index(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:171-181](../execution/registry.py#L171-L181) — `ModuleSpec(name="town_development_index", depends_on=[], required_context_keys=["property_data"], runner=run_town_development_index)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); internal signals dataclass `TownDevelopmentSignals` at [town_development_index.py:57-90](town_development_index.py#L57-L90). Minutes schemas at [briarwood/local_intelligence/minutes_schema.py](../local_intelligence/minutes_schema.py); persistence at [briarwood/local_intelligence/minutes_store.py](../local_intelligence/minutes_store.py); town-feed registry at [briarwood/local_intelligence/minutes_registry.py](../local_intelligence/minutes_registry.py).
- **Helpers exported for nudge application:** `read_dev_index` at [town_development_index.py:276](town_development_index.py#L276), `apply_dev_index_nudge` at [town_development_index.py:286](town_development_index.py#L286), `DevIndexNudgeResult` at [town_development_index.py:256](town_development_index.py#L256).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RESEARCH` — called when the user asks about town/regulatory activity.
- `STRATEGY` — called for hold-and-appreciate paths and redevelopment reasoning.
- `DECISION` — called indirectly as a dependency of `resale_scenario` ([registry.py:88-94](../execution/registry.py#L88-L94)).
- `MICRO_LOCATION` — called when the user asks place-specific questions where local permit velocity matters.
- Not called for: `SEARCH`, `CHITCHAT`, pure `VISUALIZE` without a property context.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)). Unlike most scoped modules this one does NOT convert to `PropertyInput`; it reads town/state directly from the context via `_resolve_town_state` at [town_development_index.py:394-399](town_development_index.py#L394-L399).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.town` (or `property_data.facts.town`, or `property_summary.town`) | `str` | required | resolver / intake | Resolved with fallbacks at [town_development_index.py:397](town_development_index.py#L397). |
| `context.property_data.state` (or `facts.state`, or `property_summary.state`) | `str` | required | resolver / intake | Resolved with fallbacks at [town_development_index.py:398](town_development_index.py#L398). |
| `context.property_summary` | `dict` | optional | intake | Accepted via `optional_context_keys`; read as a town/state fallback. |

Absent town/state yields an empty payload with `confidence=None` and `reason="missing town/state in property_data"` (see [town_development_index.py:346-348](town_development_index.py#L346-L348)).

## Outputs

`run_town_development_index` returns `ModulePayload.model_dump()`. When signals exist, the payload's `data` dict contains `TownDevelopmentSignals.to_data()` plus `all_boards`:

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `town` | `str \| None` | — | Resolved town name. |
| `state` | `str \| None` | — | Resolved state. |
| `board` | `str` | — | Selected primary board — `"planning_board"` preferred, else most-observations (see `_select_primary` at [town_development_index.py:402-408](town_development_index.py#L402-L408)). |
| `window_months` | `int` | months | From `record.rolling_window_months` (source data, not hardcoded). |
| `observations_used` | `int` | — | Count of `status == "fetched"` entries used. |
| `as_of` | `str` | YYYY-MM-DD | `now.date().isoformat()`. |
| `approval_rate` | `float \| None` | 0-1 | `grants / (grants + denials)`; `None` if neither appears. |
| `activity_volume` | `float` | decisions/month-ish | Time-weighted observations ÷ `effective_months`. |
| `substantive_changes` | `float` | density | Weighted months with subdivision / site plan / ordinance / zoning tags. |
| `restrictive_signals` | `float` | density | Weighted months with moratorium / denial tags. |
| `contention` | `float` | 0-1 density | Regex hit density over meeting summaries. |
| `development_velocity` | `float` | 0-1 | Weighted composite: `0.40·approval + 0.25·volume + 0.15·substantive + 0.10·(1-restrictive·2) + 0.10·(1-contention)` at [town_development_index.py:220-226](town_development_index.py#L220-L226). |
| `explanation` | `str` | prose | Human-readable component summary. |
| `all_boards` | `list[dict]` | — | Per-board signal dicts in `to_data` shape for boards that had data. |
| `confidence` | `float \| None` | 0-1 | `min(0.85, 0.25 + 0.05·observations)` at [town_development_index.py:411-415](town_development_index.py#L411-L415); `None` when no observations. |
| `warnings` | `list[str]` | — | "Only N month(s) of minutes available; development signal is provisional." when `observations_used < 3`; "High restrictive-signal density" when > 0.5. |
| `assumptions_used.half_life_months` | `float` | months | `6.0`. |
| `assumptions_used.target_volume_per_month` | `float` | decisions | `2.0`. |
| `assumptions_used.feeds_considered` | `list[str]` | — | Slugs from the minutes registry that matched the town/state. |
| `assumptions_used.boards_with_data` | `list[str]` | — | Boards whose records had observations. |
| Empty-payload fields (when no signals): `town`, `state`, `development_velocity: None`, `reason: str` | — | See `_empty_payload` at [town_development_index.py:430-446](town_development_index.py#L430-L446). |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]` at [registry.py:173](../execution/registry.py#L173). Town and state are the only hard inputs.
- **Benefits from (optional):** `property_summary` as a town/state fallback.
- **Calls internally:** `feeds_for_town` at [briarwood/local_intelligence/minutes_registry.py](../local_intelligence/minutes_registry.py); `JsonMinutesStore.load` at [briarwood/local_intelligence/minutes_store.py](../local_intelligence/minutes_store.py). All I/O happens at the edges — `compute_town_development_index` is a pure function (docstring at [town_development_index.py:100-105](town_development_index.py#L100-L105)).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** `resale_scenario` ([registry.py:88-94](../execution/registry.py#L88-L94)).
- **Also consumed via nudge helper:** any module that imports `apply_dev_index_nudge` or `read_dev_index` to apply a bounded confidence shift from velocity.

## Invariants

- `development_velocity` is always in `[0.0, 1.0]` per the clamp at [town_development_index.py:227](town_development_index.py#L227).
- All component densities (`substantive_changes`, `restrictive_signals`, `contention`) are non-negative and, in `_compose_velocity`, clamped to `[0, 1]` before contributing to velocity.
- `apply_dev_index_nudge` clamps the applied nudge to `±DEFAULT_MAX_NUDGE (= 0.04)` at [town_development_index.py:322](town_development_index.py#L322) — 4% maximum upward or downward shift to `base_confidence`.
- Time decay is exponential: `exp(-months_ago / 6.0)`. Entries in the future relative to `now` return weight `0.0`.
- Returns a neutral payload (never raises) on missing town/state, missing feeds, or no loaded records — see `_empty_payload` cases at [town_development_index.py:347-374](town_development_index.py#L347-L374).
- `confidence` maxes at `0.85` even with many months of data, per the formula at [town_development_index.py:415](town_development_index.py#L415).
- Primary board selection is deterministic: planning_board first, then most observations (no randomness).
- Deterministic per input (given a fixed `now`). Production invocations let `now` default to current UTC, so identical property inputs called at different wall-clock times can produce different velocities as data ages.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.town_development_index import run_town_development_index

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={"town": "Montclair", "state": "NJ"},
)

payload = run_town_development_index(context)
# payload["data"]["town"]                  == "Montclair"
# payload["data"]["development_velocity"]  ∈ [0, 1]  or None on empty path
# payload["data"]["approval_rate"]         ≈ 0.68
# payload["data"]["as_of"]                 == "2026-04-24"
# payload["confidence"]                    ≈ 0.70   (for 9 months of data)
# payload["assumptions_used"]["feeds_considered"] == ["montclair-nj-planning-board"]
```

## Hardcoded Values & TODOs

- `DEFAULT_MAX_NUDGE = 0.04` at [town_development_index.py:42](town_development_index.py#L42) — per-dimension cap on downstream confidence nudges.
- `DEFAULT_HALF_LIFE_MONTHS = 6.0` at [town_development_index.py:43](town_development_index.py#L43) — time-decay half-life.
- `DEFAULT_TARGET_VOLUME_PER_MONTH = 2.0` at [town_development_index.py:44](town_development_index.py#L44) — normalization for `activity_volume`.
- Velocity-composite weights at [town_development_index.py:220-226](town_development_index.py#L220-L226): approval 0.40, volume 0.25, substantive 0.15, restrictive 0.10, contention 0.10. Not config-overridable.
- Confidence formula `min(0.85, 0.25 + 0.05·observations)` at [town_development_index.py:415](town_development_index.py#L415) — ceiling 0.85 is hardcoded.
- Contention regex at [town_development_index.py:50-54](town_development_index.py#L50-L54) — English only; no localization.
- Tag sets at [town_development_index.py:46-49](town_development_index.py#L46-L49): `_SUBSTANTIVE_TAGS`, `_RESTRICTIVE_TAGS`, `_APPROVAL_TAGS`, `_DENIAL_TAGS` — matched via set intersection.
- Per-entry contention is normalized as `min(1.0, hits/3.0)` at [town_development_index.py:139](town_development_index.py#L139) to prevent a single long meeting from dominating.

## Blockers for Tool Use

- None for normal invocation. Module degrades cleanly to empty payloads on missing town/state or missing minutes.

## Notes

- **Audit-doc alignment.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) describe this module accurately — no contradictions flagged.
- Tests: [tests/modules/test_town_development_index.py](../../tests/modules/test_town_development_index.py).
- The module uses system wall-clock time when `now` defaults to `datetime.now(timezone.utc)`. Callers testing velocity against fixtures should pass `now` explicitly to `compute_town_development_index` (the runner always defaults to current UTC).
- No direct LLM calls in this runner. The underlying minutes summaries *were* produced via LLM extraction (see the separate minutes-runner and [briarwood/local_intelligence/adapters.py](../local_intelligence/adapters.py)), but that extraction is offline and not reached by `run_town_development_index`.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: wrapped body in `try/except` so unexpected internal exceptions return a `module_payload_from_error` fallback (`mode="fallback"`, `confidence=0.08`). The pre-existing `_empty_payload` branches ("no town/state", "no registered feeds", "no minutes loaded") remain the primary degraded path — they are distinguishable by `warnings` content. Added [tests/modules/test_town_development_index_degraded.py](../../tests/modules/test_town_development_index_degraded.py). See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."

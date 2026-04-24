"""Town development index — per-town rolling signal derived from minutes.

The minutes runner stores ~12 months of LLM summaries + keyword tags per
town (``JsonMinutesStore``). This module turns that history into a small set
of numeric signals:

- ``approval_rate``       : grants ÷ (grants + denials) across the window
- ``activity_volume``     : average decisions per month (raw throughput)
- ``substantive_changes`` : months with subdivision / site plan / ordinance tags
- ``restrictive_signals`` : months with moratorium / denial tags
- ``contention``          : summary-text density of "opposition"-style language
- ``development_velocity``: weighted composite in [0, 1]

Time decay: each month's contribution is scaled by
``exp(-months_ago / half_life)`` so recent activity dominates. That keeps
the index responsive to direction changes without a hard cliff at the
window boundary.

Consumers are forward-looking models (resale_scenario, valuation) that
treat the velocity as a *supplementary* signal via a bounded nudge —
similar to the macro pattern in ``briarwood.modules.macro_reader``.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.local_intelligence.minutes_registry import feeds_for_town
from briarwood.local_intelligence.minutes_schema import MinuteEntry, MinutesRecord
from briarwood.local_intelligence.minutes_store import JsonMinutesStore
from briarwood.routing_schema import ModulePayload

logger = logging.getLogger(__name__)


DEFAULT_MAX_NUDGE = 0.04
DEFAULT_HALF_LIFE_MONTHS = 6.0
DEFAULT_TARGET_VOLUME_PER_MONTH = 2.0

_SUBSTANTIVE_TAGS = {"subdivision", "site plan", "ordinance", "zoning"}
_RESTRICTIVE_TAGS = {"moratorium", "denied"}
_APPROVAL_TAGS = {"approv"}
_DENIAL_TAGS = {"denied"}
_CONTENTION_PATTERN = re.compile(
    r"\b(opposition|opposed|objection|concerns? (?:from|raised)|public comment|"
    r"neighbors? (?:objected|protested)|contested|appeal(?:ed)?)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class TownDevelopmentSignals:
    """Derived signals for one town/board over the rolling window."""

    town: str
    state: str
    board: str
    window_months: int
    observations_used: int
    as_of: str
    approval_rate: float | None
    activity_volume: float
    substantive_changes: float
    restrictive_signals: float
    contention: float
    development_velocity: float
    explanation: str

    def to_data(self) -> dict[str, Any]:
        return {
            "town": self.town,
            "state": self.state,
            "board": self.board,
            "window_months": self.window_months,
            "observations_used": self.observations_used,
            "as_of": self.as_of,
            "approval_rate": _round(self.approval_rate),
            "activity_volume": _round(self.activity_volume),
            "substantive_changes": _round(self.substantive_changes),
            "restrictive_signals": _round(self.restrictive_signals),
            "contention": _round(self.contention),
            "development_velocity": _round(self.development_velocity),
            "explanation": self.explanation,
        }


def compute_town_development_index(
    *,
    record: MinutesRecord,
    now: datetime | None = None,
    half_life_months: float = DEFAULT_HALF_LIFE_MONTHS,
    target_volume_per_month: float = DEFAULT_TARGET_VOLUME_PER_MONTH,
) -> TownDevelopmentSignals:
    """Derive TownDevelopmentSignals from a persisted ``MinutesRecord``.

    This is a pure function — all I/O happens at the edges (the runner loads
    the record, callers pass it in). Easy to unit-test with a synthetic
    record; easy to benchmark without hitting disk.
    """

    now = now or datetime.now(timezone.utc)
    window = record.rolling_window_months

    fetched = [e for e in record.entries if e.status == "fetched"]
    observations = len(fetched)

    approval_weight = 0.0
    denial_weight = 0.0
    substantive_weight = 0.0
    restrictive_weight = 0.0
    activity_weight = 0.0
    contention_weight = 0.0
    total_time_weight = 0.0

    for entry in fetched:
        w = _time_weight(entry.month, now=now, half_life=half_life_months)
        if w <= 0:
            continue
        tags = {t.lower() for t in (entry.tags or [])}
        total_time_weight += w
        activity_weight += w
        if tags & _APPROVAL_TAGS:
            approval_weight += w
        if tags & _DENIAL_TAGS:
            denial_weight += w
        if tags & _SUBSTANTIVE_TAGS:
            substantive_weight += w
        if tags & _RESTRICTIVE_TAGS:
            restrictive_weight += w
        text = entry.summary or ""
        hits = len(_CONTENTION_PATTERN.findall(text))
        # Normalize per-entry hits so one very long meeting can't dominate.
        contention_weight += w * min(1.0, hits / 3.0)

    if approval_weight + denial_weight > 0:
        approval_rate: float | None = approval_weight / (approval_weight + denial_weight)
    else:
        approval_rate = None

    # activity_volume = weighted observation count normalized to months-of-
    # window. Not per-month throughput exactly, but proportional — and it
    # stays comparable across towns that publish different month counts.
    effective_months = max(1.0, min(window, observations or 1))
    activity_volume = activity_weight / effective_months if effective_months else 0.0

    substantive_changes = substantive_weight / effective_months
    restrictive_signals = restrictive_weight / effective_months
    contention = contention_weight / max(1.0, total_time_weight)

    velocity = _compose_velocity(
        approval_rate=approval_rate,
        activity_volume=activity_volume,
        substantive_changes=substantive_changes,
        restrictive_signals=restrictive_signals,
        contention=contention,
        target_volume=target_volume_per_month,
    )

    explanation = _explain(
        approval_rate=approval_rate,
        activity_volume=activity_volume,
        substantive_changes=substantive_changes,
        restrictive_signals=restrictive_signals,
        contention=contention,
        velocity=velocity,
        observations=observations,
    )

    return TownDevelopmentSignals(
        town=record.town,
        state=record.state,
        board=record.board,
        window_months=window,
        observations_used=observations,
        as_of=now.date().isoformat(),
        approval_rate=approval_rate,
        activity_volume=activity_volume,
        substantive_changes=substantive_changes,
        restrictive_signals=restrictive_signals,
        contention=contention,
        development_velocity=velocity,
        explanation=explanation,
    )


def _time_weight(month: str, *, now: datetime, half_life: float) -> float:
    try:
        year, mo = month.split("-")
        month_dt = datetime(int(year), int(mo), 1, tzinfo=timezone.utc)
    except Exception:
        return 0.0
    diff = (now.year - month_dt.year) * 12 + (now.month - month_dt.month)
    if diff < 0:
        return 0.0
    return math.exp(-diff / max(0.1, half_life))


def _compose_velocity(
    *,
    approval_rate: float | None,
    activity_volume: float,
    substantive_changes: float,
    restrictive_signals: float,
    contention: float,
    target_volume: float,
) -> float:
    """Weighted composite in [0, 1]. Missing approval_rate defaults to 0.5."""

    approval_component = approval_rate if approval_rate is not None else 0.5
    volume_component = min(1.0, activity_volume / max(0.1, target_volume))
    substantive_component = min(1.0, substantive_changes)
    restrictive_component = max(0.0, 1.0 - min(1.0, restrictive_signals * 2.0))
    contention_component = max(0.0, 1.0 - contention)
    score = (
        0.40 * approval_component
        + 0.25 * volume_component
        + 0.15 * substantive_component
        + 0.10 * restrictive_component
        + 0.10 * contention_component
    )
    return max(0.0, min(1.0, score))


def _explain(
    *,
    approval_rate: float | None,
    activity_volume: float,
    substantive_changes: float,
    restrictive_signals: float,
    contention: float,
    velocity: float,
    observations: int,
) -> str:
    if observations == 0:
        return "No recent minutes available; development signal unavailable."
    parts: list[str] = []
    if approval_rate is not None:
        parts.append(f"approval rate {approval_rate:.0%}")
    parts.append(f"~{activity_volume:.1f} decisions/mo (time-weighted)")
    if substantive_changes > 0.25:
        parts.append("active ordinance/subdivision pipeline")
    if restrictive_signals > 0.25:
        parts.append("elevated restrictive activity")
    if contention > 0.25:
        parts.append("notable public opposition")
    parts.append(f"velocity {velocity:.2f}")
    return ", ".join(parts)


@dataclass(slots=True)
class DevIndexNudgeResult:
    original_confidence: float | None
    adjusted_confidence: float | None
    velocity: float | None
    applied_nudge: float
    max_nudge: float
    town: str | None
    as_of: str | None

    def to_meta(self) -> dict[str, Any]:
        return {
            "velocity": _round(self.velocity),
            "applied_nudge": round(self.applied_nudge, 4),
            "max_nudge": self.max_nudge,
            "town": self.town,
            "as_of": self.as_of,
        }


def read_dev_index(context: ExecutionContext) -> dict[str, Any] | None:
    """Return the stored ``town_development_index`` data dict, if available."""

    payload = context.get_module_output("town_development_index") if context else None
    if not payload:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def apply_dev_index_nudge(
    *,
    base_confidence: float | None,
    context: ExecutionContext,
    max_nudge: float = DEFAULT_MAX_NUDGE,
) -> DevIndexNudgeResult:
    """Bounded confidence nudge from town development velocity.

    Velocity > 0.5 pulls confidence up (positive for bullish / value
    scenarios); velocity < 0.5 pulls it down. The nudge is clamped to
    ``max_nudge`` so comp-driven and property-specific evidence continues
    to dominate.
    """

    data = read_dev_index(context)
    if base_confidence is None or not data:
        return DevIndexNudgeResult(
            original_confidence=base_confidence,
            adjusted_confidence=base_confidence,
            velocity=None,
            applied_nudge=0.0,
            max_nudge=max_nudge,
            town=data.get("town") if data else None,
            as_of=data.get("as_of") if data else None,
        )
    velocity = data.get("development_velocity")
    if not isinstance(velocity, (int, float)):
        return DevIndexNudgeResult(
            original_confidence=base_confidence,
            adjusted_confidence=base_confidence,
            velocity=None,
            applied_nudge=0.0,
            max_nudge=max_nudge,
            town=data.get("town"),
            as_of=data.get("as_of"),
        )
    nudge = max(-max_nudge, min(max_nudge, (float(velocity) - 0.5) * 2 * max_nudge))
    adjusted = max(0.0, min(1.0, float(base_confidence) + nudge))
    return DevIndexNudgeResult(
        original_confidence=float(base_confidence),
        adjusted_confidence=round(adjusted, 4),
        velocity=round(float(velocity), 4),
        applied_nudge=nudge,
        max_nudge=max_nudge,
        town=data.get("town"),
        as_of=data.get("as_of"),
    )


# ─── Scoped runner ────────────────────────────────────────────────────────

def run_town_development_index(context: ExecutionContext) -> dict[str, object]:
    """Compute the town development index for the current property's town.

    Looks up the property's town/state, finds matching feeds in the minutes
    registry, loads each record from ``JsonMinutesStore``, and derives the
    composite signal. If no feed or record exists, returns a neutral payload
    with ``confidence=None`` so downstream nudges cleanly no-op.

    Error contract (DECISIONS.md 2026-04-24): the existing ``_empty_payload``
    branches for "no town/state" and "no feeds" remain the primary degraded
    path — distinguishable by the ``warnings`` content. Unexpected internal
    exceptions are caught and returned as a ``module_payload_from_error``
    fallback (``mode="fallback"``, ``confidence=0.08``).
    """

    try:
        town, state = _resolve_town_state(context)
        if not town or not state:
            return _empty_payload(reason="missing town/state in property_data").model_dump()

        feeds = feeds_for_town(town=town, state=state)
        if not feeds:
            return _empty_payload(
                reason=f"no registered minutes feeds for {town}, {state}",
                town=town,
                state=state,
            ).model_dump()

        store = JsonMinutesStore()
        boards: list[TownDevelopmentSignals] = []
        for feed in feeds:
            record = store.load(feed)
            if record is None:
                continue
            signals = compute_town_development_index(record=record)
            if signals.observations_used == 0:
                continue
            boards.append(signals)

        if not boards:
            return _empty_payload(
                reason=f"no minute history loaded for {town}, {state}",
                town=town,
                state=state,
            ).model_dump()

        primary = _select_primary(boards)
        payload = ModulePayload(
            data={
                **primary.to_data(),
                "all_boards": [b.to_data() for b in boards],
            },
            confidence=_confidence_from_observations(primary.observations_used),
            warnings=_warnings(primary),
            assumptions_used={
                "half_life_months": DEFAULT_HALF_LIFE_MONTHS,
                "target_volume_per_month": DEFAULT_TARGET_VOLUME_PER_MONTH,
                "feeds_considered": [f.slug for f in feeds],
                "boards_with_data": [b.board for b in boards],
            },
        )
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        from briarwood.modules.scoped_common import module_payload_from_error
        return module_payload_from_error(
            module_name="town_development_index",
            context=context,
            summary="Town development index unavailable — internal failure reading minutes feeds.",
            warnings=[f"Town-development-index fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={"uses_full_engine_report": False, "fallback_reason": "internal_exception"},
        ).model_dump()


def _resolve_town_state(context: ExecutionContext) -> tuple[str | None, str | None]:
    pd = context.property_data or {}
    facts = pd.get("facts") if isinstance(pd.get("facts"), dict) else {}
    town = facts.get("town") or pd.get("town") or (context.property_summary or {}).get("town")
    state = facts.get("state") or pd.get("state") or (context.property_summary or {}).get("state")
    return (str(town).strip() if town else None, str(state).strip() if state else None)


def _select_primary(boards: list[TownDevelopmentSignals]) -> TownDevelopmentSignals:
    """Prefer planning_board, else most observations."""

    for b in boards:
        if b.board == "planning_board":
            return b
    return max(boards, key=lambda b: b.observations_used)


def _confidence_from_observations(n: int) -> float | None:
    if n <= 0:
        return None
    # 12+ months → 0.8; 6 → ~0.6; 3 → ~0.45; 1 → ~0.30.
    return round(min(0.85, 0.25 + 0.05 * n), 4)


def _warnings(signals: TownDevelopmentSignals) -> list[str]:
    warnings: list[str] = []
    if signals.observations_used < 3:
        warnings.append(
            f"Only {signals.observations_used} month(s) of minutes available; "
            "development signal is provisional."
        )
    if signals.restrictive_signals > 0.5:
        warnings.append("High restrictive-signal density (moratoria or denials).")
    return warnings


def _empty_payload(
    *,
    reason: str,
    town: str | None = None,
    state: str | None = None,
) -> ModulePayload:
    return ModulePayload(
        data={
            "town": town,
            "state": state,
            "development_velocity": None,
            "reason": reason,
        },
        confidence=None,
        warnings=[reason],
        assumptions_used={},
    )


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


__all__ = [
    "DEFAULT_HALF_LIFE_MONTHS",
    "DEFAULT_MAX_NUDGE",
    "DEFAULT_TARGET_VOLUME_PER_MONTH",
    "DevIndexNudgeResult",
    "TownDevelopmentSignals",
    "apply_dev_index_nudge",
    "compute_town_development_index",
    "read_dev_index",
    "run_town_development_index",
]

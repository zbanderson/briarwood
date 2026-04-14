"""Shared types for the Phase 4 interaction layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# A ModuleOutputs map is {module_name: ModulePayload-as-dict}. We keep this
# loose (dict, not a Pydantic model) so bridges can be called with either a
# live orchestrator result or a recorded fixture.
ModuleOutputs = dict[str, dict[str, Any]]


@dataclass(slots=True)
class BridgeRecord:
    """One cross-model adjustment.

    - ``name`` identifies the bridge that fired (e.g. ``valuation_x_town``).
    - ``inputs_read`` is the list of module names whose output this bridge consumed.
    - ``adjustments`` is a free-form dict describing *what* the bridge wants the
      synthesizer to use instead of / in addition to the raw module outputs.
      Synthesis in Phase 5 consumes these; modules themselves are never mutated.
    - ``reasoning`` is a human-readable justification (what changed and why).
    - ``confidence`` captures how strongly the bridge stands behind its adjustment.
    - ``fired`` is False when the bridge ran but the inputs did not satisfy its
      preconditions — recorded so the trace shows negative results too.
    """

    name: str
    inputs_read: list[str] = field(default_factory=list)
    adjustments: dict[str, Any] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)
    confidence: float = 0.0
    fired: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InteractionTrace:
    """All bridge outputs for a single property run."""

    records: list[BridgeRecord] = field(default_factory=list)

    @property
    def fired(self) -> list[BridgeRecord]:
        return [r for r in self.records if r.fired]

    def add(self, record: BridgeRecord) -> None:
        self.records.append(record)

    def get(self, name: str) -> BridgeRecord | None:
        for record in self.records:
            if record.name == name:
                return record
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "fired_count": len(self.fired),
            "total_count": len(self.records),
        }


# ─── Helpers for reading module payloads safely ─────────────────────────────


def _payload(outputs: ModuleOutputs, name: str) -> dict[str, Any] | None:
    """Return the payload dict for a module, or None if missing."""

    value = outputs.get(name)
    if isinstance(value, dict):
        return value
    return None


def _metrics(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    data = payload.get("data") or {}
    return dict(data.get("metrics") or {})


def _legacy(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    data = payload.get("data") or {}
    return dict(data.get("legacy_payload") or {})


def _confidence(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    value = payload.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _score(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    value = payload.get("score")
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = [
    "BridgeRecord",
    "InteractionTrace",
    "ModuleOutputs",
    "_payload",
    "_metrics",
    "_legacy",
    "_confidence",
    "_score",
]

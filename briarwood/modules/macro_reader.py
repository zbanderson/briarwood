"""Read-side helpers for consuming county macro context in specialty modules.

All helpers here enforce the invariant that macro signals are *supplementary*:
their effect on confidence is bounded so that strong town-specific and
property-specific evidence continues to dominate. Callers should always pass
``max_nudge`` defaults unchanged unless they have a specific reason.

The macro slice lives at ``ExecutionContext.macro_context`` and is populated
once per session by the orchestrator via ``resolve_macro_context``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from briarwood.execution.context import ExecutionContext
from briarwood.execution.macro_context import MacroContextSlice


MacroDimension = Literal[
    "employment",
    "income_growth",
    "hpi_momentum",
    "liquidity",
    "overall",
]

_DIMENSION_FIELD: dict[MacroDimension, str] = {
    "employment": "employment_signal",
    "income_growth": "income_growth_signal",
    "hpi_momentum": "hpi_momentum_signal",
    "liquidity": "liquidity_signal",
    "overall": "overall_sentiment",
}

DEFAULT_MAX_NUDGE = 0.05


@dataclass(slots=True)
class MacroNudgeResult:
    """Outcome of applying a bounded macro nudge to a module's confidence."""

    original_confidence: float | None
    adjusted_confidence: float | None
    dimension: MacroDimension
    signal: float | None
    applied_nudge: float
    max_nudge: float
    macro_as_of: str | None
    macro_county: str | None

    def to_meta(self) -> dict[str, Any]:
        """Return a dict suitable for ``ModulePayload.data.macro_nudge``."""

        return {
            "dimension": self.dimension,
            "signal": self.signal,
            "applied_nudge": round(self.applied_nudge, 4),
            "max_nudge": self.max_nudge,
            "macro_as_of": self.macro_as_of,
            "macro_county": self.macro_county,
        }


def read_macro(context: ExecutionContext) -> MacroContextSlice | None:
    """Return the typed macro slice from an ExecutionContext, when available."""

    payload = context.macro_context if context else None
    if not payload:
        return None
    try:
        return MacroContextSlice.model_validate(payload)
    except Exception:
        return None


def apply_macro_nudge(
    *,
    base_confidence: float | None,
    context: ExecutionContext,
    dimension: MacroDimension,
    max_nudge: float = DEFAULT_MAX_NUDGE,
) -> MacroNudgeResult:
    """Adjust a module's confidence by a bounded macro nudge.

    The nudge is proportional to how far the macro signal sits from 0.5
    (neutral), scaled so that the extreme signal (0.0 or 1.0) produces
    exactly ±``max_nudge``. Result is clamped to [0, 1]. When macro data is
    missing or ``base_confidence`` is ``None``, returns a no-op result.
    """

    slice_ = read_macro(context)
    if base_confidence is None or slice_ is None:
        return MacroNudgeResult(
            original_confidence=base_confidence,
            adjusted_confidence=base_confidence,
            dimension=dimension,
            signal=None,
            applied_nudge=0.0,
            max_nudge=max_nudge,
            macro_as_of=slice_.as_of if slice_ else None,
            macro_county=slice_.county if slice_ else None,
        )

    signal = getattr(slice_, _DIMENSION_FIELD[dimension], None)
    if signal is None:
        return MacroNudgeResult(
            original_confidence=base_confidence,
            adjusted_confidence=base_confidence,
            dimension=dimension,
            signal=None,
            applied_nudge=0.0,
            max_nudge=max_nudge,
            macro_as_of=slice_.as_of,
            macro_county=slice_.county,
        )

    nudge = max(-max_nudge, min(max_nudge, (float(signal) - 0.5) * 2 * max_nudge))
    adjusted = max(0.0, min(1.0, float(base_confidence) + nudge))
    return MacroNudgeResult(
        original_confidence=float(base_confidence),
        adjusted_confidence=round(adjusted, 4),
        dimension=dimension,
        signal=round(float(signal), 4),
        applied_nudge=nudge,
        max_nudge=max_nudge,
        macro_as_of=slice_.as_of,
        macro_county=slice_.county,
    )


__all__ = [
    "DEFAULT_MAX_NUDGE",
    "MacroDimension",
    "MacroNudgeResult",
    "apply_macro_nudge",
    "read_macro",
]

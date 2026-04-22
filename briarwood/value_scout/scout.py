"""Value Scout v1 entrypoint.

Runs each registered pattern over a claim; returns the single strongest
SurfacedInsight, or None if no pattern matched. Patterns are pure
functions — ``def detect(claim) -> SurfacedInsight | None``.

Phase 3 ships with exactly one pattern (uplift_dominance). The registry
is already multi-pattern so Phase B can add detectors without changing
callers. For v1 "strongest" collapses to "first non-null" since there's
only one pattern; when a second pattern is added, we'll need a scoring
signal on SurfacedInsight or a comparable side-channel.
"""
from __future__ import annotations

from typing import Callable

from briarwood.claims.base import SurfacedInsight
from briarwood.claims.verdict_with_comparison import VerdictWithComparisonClaim
from briarwood.value_scout.patterns import uplift_dominance

Pattern = Callable[[VerdictWithComparisonClaim], SurfacedInsight | None]

_PATTERNS: tuple[Pattern, ...] = (uplift_dominance.detect,)


def scout_claim(claim: VerdictWithComparisonClaim) -> SurfacedInsight | None:
    """Scan the claim for non-obvious value. Returns None if nothing notable."""
    for pattern in _PATTERNS:
        result = pattern(claim)
        if result is not None:
            return result
    return None

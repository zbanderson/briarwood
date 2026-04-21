"""Projections from the canonical routed verdict to display shapes.

The canonical verdict lives in ``briarwood/synthesis/structured.py`` and
produces a ``UnifiedIntelligenceOutput`` with the routed vocabulary
(``DecisionStance``, ``DecisionType``). Surfaces that have not yet migrated
off the legacy ``BUY / LEAN BUY / NEUTRAL / LEAN PASS / AVOID`` vocabulary
get a display-only projection here — the projector never re-derives a
verdict, it only relabels.

See ``briarwood/projections/README.md`` for the stance mapping table and
the conventions every new projector should follow.
"""

from briarwood.projections.legacy_verdict import (
    LegacyVerdict,
    STANCE_TO_LEGACY_LABEL,
    project_to_legacy,
)

__all__ = [
    "LegacyVerdict",
    "STANCE_TO_LEGACY_LABEL",
    "project_to_legacy",
]

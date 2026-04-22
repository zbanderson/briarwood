"""Archetype routing for the claim-object pipeline.

Minimal mapping layer that decides whether the wedge path applies for a
given router classification. Returns None when nothing matches — callers
(dispatch) fall back to the legacy handler.
"""
from __future__ import annotations

from briarwood.agent.router import AnswerType
from briarwood.claims.archetypes import Archetype


def map_to_archetype(
    answer_type: AnswerType,
    question_focus: list[str] | None,
    has_pinned_listing: bool,
) -> Archetype | None:
    """Map existing classification to a claim archetype.

    Returns None if no archetype matches (caller falls back to the legacy
    path). Deliberately narrow: the wedge ships one archetype, so everything
    else routes None. ``question_focus`` is accepted for forward compatibility
    with future archetypes that branch on it.
    """
    del question_focus
    if not has_pinned_listing:
        return None
    if answer_type in {AnswerType.DECISION, AnswerType.LOOKUP}:
        return Archetype.VERDICT_WITH_COMPARISON
    return None

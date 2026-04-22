"""Confidence-to-assertion rubric (plan §7.3).

Applied to the deterministic verdict headline after synthesis produces it
and before prose is assembled. Only the verdict-bearing sentence gets
rewritten; the LLM prose around it is left alone.

PHASE B LIMITATION
------------------
The "low" band's "convert point claims to ranges" rule is not implemented.
The chart already carries ranges (horizontal_bar_with_ranges), so leading
the sentence with "Our best estimate is" is sufficient for the wedge
until Phase B adds range-rendering in prose.
"""
from __future__ import annotations

from briarwood.claims.base import Confidence


def apply_rubric(headline: str, confidence: Confidence, *, comp_count: int) -> str:
    """Return the verdict headline modified for the confidence band.

    `comp_count` is used for the "medium" band prefix; callers pass
    `claim.verdict.comp_count`.
    """
    band = confidence.band
    if band == "high":
        return headline
    if band == "medium":
        return f"Based on {comp_count} comparable sales, {_lowercase_first(headline)}"
    if band == "low":
        return f"Our best estimate is {_lowercase_first(headline)}"
    if band == "very_low":
        return (
            "We don't have high confidence here, but "
            f"{_lowercase_first(headline)}"
        )
    return headline


def _lowercase_first(text: str) -> str:
    if not text:
        return text
    return text[0].lower() + text[1:]

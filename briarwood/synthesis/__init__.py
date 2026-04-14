"""Phase 5: structured synthesis.

Replaces the LLM-pass-through synthesizer with a deterministic, reproducible
decision-building pipeline. The LLM may translate the structured output into
narrative (later), but it does not make the decision.
"""

from briarwood.synthesis.structured import (
    build_unified_output,
    classify_decision_stance,
    collect_trust_flags,
    compute_value_position,
)

__all__ = [
    "build_unified_output",
    "classify_decision_stance",
    "collect_trust_flags",
    "compute_value_position",
]

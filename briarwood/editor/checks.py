"""Individual Editor checks for VerdictWithComparisonClaim.

Each check is a pure function returning a list of human-readable failures.
An empty list means the check passed. Checks do not mutate the claim.

See plan §6.3 for the set of checks in v1. The Editor aggregates these in
a fixed order; checks do not know about one another.
"""
from __future__ import annotations

from briarwood.claims.verdict_with_comparison import VerdictWithComparisonClaim

# Mirrors the synthesizer's thresholds. If those drift, this catches it.
VALUE_FIND_THRESHOLD_PCT = -5.0
OVERPRICED_THRESHOLD_PCT = 5.0

# Sample size below which a scenario must carry a caveat. Must agree with
# the synthesizer's SMALL_SAMPLE_THRESHOLD; the editor does not import from
# synthesis to avoid a layering violation.
SMALL_SAMPLE_THRESHOLD = 5


def check_schema_conformance(claim: VerdictWithComparisonClaim) -> list[str]:
    """Trivially passes — Pydantic already validated the claim.

    Present for completeness with the plan's v1 check list; kept as an
    explicit function so future non-pydantic invariants can land here.
    """
    return []


def check_scenario_data_completeness(claim: VerdictWithComparisonClaim) -> list[str]:
    """Every scenario in comparison.scenarios has non-zero sample_size."""
    failures: list[str] = []
    for scenario in claim.comparison.scenarios:
        if scenario.sample_size <= 0:
            failures.append(
                f"Scenario '{scenario.id}' has non-positive sample_size "
                f"({scenario.sample_size})."
            )
    return failures


def check_verdict_delta_coherence(claim: VerdictWithComparisonClaim) -> list[str]:
    """verdict.label matches the threshold rule on ask_vs_fmv_delta_pct.

    insufficient_data is its own escape hatch and not coherence-checked
    against delta — the synthesizer uses it when FMV is unavailable.
    """
    label = claim.verdict.label
    delta = claim.verdict.ask_vs_fmv_delta_pct
    if label == "insufficient_data":
        return []
    expected: str
    if delta <= VALUE_FIND_THRESHOLD_PCT:
        expected = "value_find"
    elif delta >= OVERPRICED_THRESHOLD_PCT:
        expected = "overpriced"
    else:
        expected = "fair"
    if label != expected:
        return [
            f"Verdict label '{label}' does not match delta {delta:.2f}% "
            f"(expected '{expected}')."
        ]
    return []


def check_emphasis_coherence(claim: VerdictWithComparisonClaim) -> list[str]:
    """If comparison.emphasis_scenario_id is set, it matches the surfaced
    insight's scenario_id (when Scout fired).

    Schema validation already guarantees the emphasis target exists in
    scenarios; this check catches a different bug — emphasis and insight
    pointing at different scenarios.
    """
    emphasis = claim.comparison.emphasis_scenario_id
    if emphasis is None:
        return []
    insight = claim.surfaced_insight
    if insight is None:
        return [
            f"Emphasis scenario '{emphasis}' is set but no surfaced insight "
            "is present."
        ]
    if insight.scenario_id is None:
        return [
            f"Emphasis scenario '{emphasis}' is set but the surfaced insight "
            "does not name a scenario."
        ]
    if insight.scenario_id != emphasis:
        return [
            f"Emphasis scenario '{emphasis}' does not match surfaced "
            f"insight scenario '{insight.scenario_id}'."
        ]
    return []


def check_caveat_for_gap(claim: VerdictWithComparisonClaim) -> list[str]:
    """Every scenario with sample_size < threshold has a matching caveat.

    "Matching" = a caveat whose text contains the scenario's id or label.
    Loose match keeps the editor decoupled from the synthesizer's wording.
    """
    failures: list[str] = []
    for scenario in claim.comparison.scenarios:
        if scenario.sample_size >= SMALL_SAMPLE_THRESHOLD:
            continue
        matched = any(
            scenario.label in caveat.text or scenario.id in caveat.text
            for caveat in claim.caveats
        )
        if not matched:
            failures.append(
                f"Scenario '{scenario.id}' has sample_size "
                f"{scenario.sample_size} but no caveat references it."
            )
    return failures

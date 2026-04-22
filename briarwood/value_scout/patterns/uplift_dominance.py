"""Uplift-dominance pattern.

Looks at the non-subject scenarios in a ``VerdictWithComparisonClaim`` and
asks: which renovation path buys the most upside per dollar invested? If
one scenario dominates the others by a comfortable margin AND its uplift
meaningfully exceeds the (placeholder) cost to get there, we surface it.

PHASE B LIMITATION
------------------
The wedge does not model renovation costs. The ``PLACEHOLDER_INVESTMENT_BY_TIER``
table below is a crude per-tier stand-in. Phase B replaces it with either a
real cost model or user-supplied cost inputs; until then treat the ratio as
directional, not a hard dollar claim. The prose layer should not repeat the
exact ratio to the user — Scout surfaces the finding; Representation decides
how strongly to assert it.
"""
from __future__ import annotations

from dataclasses import dataclass

from briarwood.claims.base import SurfacedInsight
from briarwood.claims.verdict_with_comparison import (
    ComparisonScenario,
    VerdictWithComparisonClaim,
)

# Pattern fires when the top non-subject scenario's uplift-to-investment
# ratio is at least this value. 1.0 means the placeholder uplift at least
# pays back the placeholder investment.
UPLIFT_DOMINANCE_THRESHOLD: float = 1.0

# Pattern also requires the winner to dominate the runner-up by this margin
# (winner_ratio / runner_ratio). Otherwise both paths look comparable and
# there's no genuine "dominance" to surface.
DOMINANCE_MULTIPLE_THRESHOLD: float = 1.5

# Placeholder renovation costs by scenario tier (in dollars).
# Intentionally on the high side so the pattern stays conservative.
PLACEHOLDER_INVESTMENT_BY_TIER: dict[str, float] = {
    "renovated_same": 100_000.0,
    "renovated_plus_bath": 175_000.0,
}
DEFAULT_PLACEHOLDER_INVESTMENT: float = 150_000.0


@dataclass(frozen=True)
class _Candidate:
    scenario: ComparisonScenario
    uplift_per_sqft: float
    uplift_total: float
    investment: float
    ratio: float


def detect(claim: VerdictWithComparisonClaim) -> SurfacedInsight | None:
    subject = _find_subject(claim.comparison.scenarios)
    if subject is None:
        return None
    sqft = claim.subject.sqft
    if sqft <= 0:
        return None

    candidates: list[_Candidate] = []
    for scenario in claim.comparison.scenarios:
        if scenario.is_subject:
            continue
        uplift_per_sqft = scenario.metric_median - subject.metric_median
        if uplift_per_sqft <= 0:
            continue
        investment = _investment_for(scenario)
        if investment <= 0:
            continue
        uplift_total = uplift_per_sqft * sqft
        ratio = uplift_total / investment
        candidates.append(
            _Candidate(
                scenario=scenario,
                uplift_per_sqft=uplift_per_sqft,
                uplift_total=uplift_total,
                investment=investment,
                ratio=ratio,
            )
        )

    # Need at least two non-subject scenarios to claim dominance.
    if len(candidates) < 2:
        return None

    candidates.sort(key=lambda c: c.ratio, reverse=True)
    winner = candidates[0]
    runner = candidates[1]

    if winner.ratio < UPLIFT_DOMINANCE_THRESHOLD:
        return None
    if runner.ratio <= 0:
        return None
    multiple = winner.ratio / runner.ratio
    if multiple < DOMINANCE_MULTIPLE_THRESHOLD:
        return None

    return SurfacedInsight(
        headline=(
            f"The {winner.scenario.label} path shows the strongest "
            "upside for the investment required."
        ),
        reason=(
            f"${winner.uplift_per_sqft:,.0f}/sqft median uplift is "
            f"{multiple:.1f}x higher than the {runner.scenario.label} "
            "path per dollar of renovation investment."
        ),
        supporting_fields=[
            f"comparison.scenarios[{winner.scenario.id}].metric_median",
            f"comparison.scenarios[{runner.scenario.id}].metric_median",
            "subject.sqft",
        ],
        scenario_id=winner.scenario.id,
    )


def _find_subject(scenarios: list[ComparisonScenario]) -> ComparisonScenario | None:
    for scenario in scenarios:
        if scenario.is_subject:
            return scenario
    return None


def _investment_for(scenario: ComparisonScenario) -> float:
    return PLACEHOLDER_INVESTMENT_BY_TIER.get(scenario.id, DEFAULT_PLACEHOLDER_INVESTMENT)

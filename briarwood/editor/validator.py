"""Editor v1 entrypoint.

Runs every registered check against a VerdictWithComparisonClaim and
returns an aggregated EditResult. v1 is pass/fail — no loop-back, no
partial pass. Dispatch handles a failing result by falling through to
the legacy path (see plan §6.4).
"""
from __future__ import annotations

from typing import Callable, NamedTuple

from briarwood.claims.verdict_with_comparison import VerdictWithComparisonClaim
from briarwood.editor import checks

Check = Callable[[VerdictWithComparisonClaim], list[str]]

# Order matters only for diagnostic readability — all checks always run.
_CHECKS: tuple[Check, ...] = (
    checks.check_schema_conformance,
    checks.check_scenario_data_completeness,
    checks.check_verdict_delta_coherence,
    checks.check_emphasis_coherence,
    checks.check_caveat_for_gap,
)


class EditResult(NamedTuple):
    passed: bool
    failures: list[str]


def edit_claim(claim: VerdictWithComparisonClaim) -> EditResult:
    """Validate a claim. Returns passed=True with failures=[] when clean."""
    failures: list[str] = []
    for check in _CHECKS:
        failures.extend(check(claim))
    return EditResult(passed=not failures, failures=failures)

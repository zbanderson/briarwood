"""Canonical first-turn underwrite benchmark for the chat experience.

This benchmark is intentionally product-surface-oriented. It checks the same
things a user actually feels on the first decision turn:

- the compact underwrite narrative
- the verdict card payload
- the first proof chart claim

It does not score specialist models in isolation.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from api.pipeline_adapter import decision_stream
from briarwood.agent.router import AnswerType, RouterDecision


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "data" / "eval" / "canonical_underwrite_benchmark.json"

_GENERIC_POSITIVE_PHRASES = (
    "worth a closer look",
    "interesting opportunity",
    "promising setup",
    "encouraging setup",
    "some upside",
)


@dataclass(slots=True)
class UnderwriteBenchmarkCase:
    fixture_id: str
    prompt: str
    expected_stance_band: list[str]
    must_mention_evidence_fields: list[str]
    required_flip_condition: str
    required_next_step_hook: str
    required_primary_chart_claim: str
    chatgpt_reference: str


@dataclass(slots=True)
class UnderwriteBenchmarkResult:
    fixture_id: str
    passed: bool
    failures: list[str]
    narrative: str
    stance: str | None
    first_chart_kind: str | None
    first_chart_claim: str | None
    chatgpt_reference: str


def load_cases(path: Path = CASES_PATH) -> list[UnderwriteBenchmarkCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [UnderwriteBenchmarkCase(**row) for row in payload]


def run_benchmark(cases: list[UnderwriteBenchmarkCase] | None = None) -> dict[str, Any]:
    loaded_cases = cases or load_cases()
    results = [_run_case(case) for case in loaded_cases]
    failures = [result.fixture_id for result in results if not result.passed]
    return {
        "cases_total": len(results),
        "cases_passed": len(results) - len(failures),
        "cases_failed": len(failures),
        "failing_fixture_ids": failures,
        "results": [asdict(result) for result in results],
    }


def evaluate_case(
    case: UnderwriteBenchmarkCase,
    *,
    events: list[dict[str, Any]],
) -> UnderwriteBenchmarkResult:
    narrative = "".join(
        str(event.get("content") or "")
        for event in events
        if event.get("type") == "text_delta"
    ).strip()
    verdict = next(
        (event for event in events if event.get("type") == "verdict"),
        {},
    )
    first_chart = next(
        (event for event in events if event.get("type") == "chart"),
        {},
    )
    failures: list[str] = []

    stance = verdict.get("stance")
    if stance not in set(case.expected_stance_band):
        failures.append(
            f"stance {stance!r} not in expected band {case.expected_stance_band!r}"
        )

    for field in case.must_mention_evidence_fields:
        value = verdict.get(field)
        if field == "evidence_items":
            if not list(value or []):
                failures.append("verdict missing evidence_items")
        elif value in (None, "", [], {}):
            failures.append(f"verdict missing surfaced evidence field {field!r}")

    if case.required_flip_condition == "what_changes_my_view":
        if not list(verdict.get("what_changes_my_view") or []):
            failures.append("verdict missing what_changes_my_view")
    elif case.required_flip_condition == "flip_condition":
        if not narrative and verdict.get("lead_reason") is None:
            failures.append("narrative missing flip condition context")

    if case.required_next_step_hook == "next_step_teaser" and not verdict.get("next_step_teaser"):
        failures.append("verdict missing next_step_teaser")

    first_chart_claim = first_chart.get("supports_claim")
    if first_chart_claim != case.required_primary_chart_claim:
        failures.append(
            f"first chart claim {first_chart_claim!r} != expected {case.required_primary_chart_claim!r}"
        )

    narrative_lower = narrative.lower()
    if any(phrase in narrative_lower for phrase in _GENERIC_POSITIVE_PHRASES):
        if not verdict.get("lead_reason") or not list(verdict.get("evidence_items") or []):
            failures.append("generic positive language appeared without surfaced evidence")

    return UnderwriteBenchmarkResult(
        fixture_id=case.fixture_id,
        passed=not failures,
        failures=failures,
        narrative=narrative,
        stance=stance,
        first_chart_kind=first_chart.get("kind"),
        first_chart_claim=first_chart_claim,
        chatgpt_reference=case.chatgpt_reference,
    )


def _run_case(case: UnderwriteBenchmarkCase) -> UnderwriteBenchmarkResult:
    events = _collect_events(
        decision_stream(
            case.prompt,
            RouterDecision(
                AnswerType.DECISION,
                confidence=0.99,
                target_refs=[case.fixture_id],
                reason="canonical_underwrite_benchmark",
            ),
            pinned_listing=_pinned_listing(case.fixture_id),
        )
    )
    return evaluate_case(case, events=events)


def _collect_events(stream) -> list[dict[str, Any]]:
    async def _collect() -> list[dict[str, Any]]:
        return [event async for event in stream]

    return asyncio.run(_collect())


def _pinned_listing(fixture_id: str) -> dict[str, Any]:
    summary_path = ROOT / "data" / "saved_properties" / fixture_id / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "id": fixture_id,
        "address_line": summary.get("address"),
        "city": summary.get("town"),
        "state": summary.get("state"),
        "price": summary.get("ask_price"),
        "beds": summary.get("beds"),
        "baths": summary.get("baths"),
        "sqft": summary.get("sqft"),
        "status": "active",
    }


def _print_report(report: dict[str, Any]) -> None:
    print("=== Canonical Underwrite Benchmark ===")
    print(
        f"Passed {report['cases_passed']} / {report['cases_total']} "
        f"({report['cases_failed']} failing)"
    )
    for row in report["results"]:
        status = "pass" if row["passed"] else "fail"
        print(
            f"- {row['fixture_id']}: {status} | stance={row['stance']} "
            f"| chart={row['first_chart_kind']} ({row['first_chart_claim']})"
        )
        if row["failures"]:
            for failure in row["failures"]:
                print(f"    {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canonical-underwrite-benchmark")
    parser.add_argument("--json", type=str, default=None, help="write full report JSON here")
    args = parser.parse_args(argv)

    report = run_benchmark()
    _print_report(report)

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote report -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

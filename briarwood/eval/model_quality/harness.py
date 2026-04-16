"""Model quality harness — score each specialist model against six criteria.

Run:
    python -m briarwood.eval.model_quality.harness
    python -m briarwood.eval.model_quality.harness --models income,risk
    python -m briarwood.eval.model_quality.harness --limit 3 --json report.json

For each (model × fixture) pair, evaluates:
    accuracy, consistency, sensitivity, explainability,
    decision_usefulness, trust_calibration

Produces a per-model, per-criterion scorecard. Distinct from
``briarwood.eval.harness`` (which scores deployed-model outcomes from
captured feedback). This harness is a pre-deployment QA check.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from briarwood.eval.model_quality.criteria import ALL_CRITERIA
from briarwood.eval.model_quality.fixtures import load_all_fixtures
from briarwood.eval.model_quality.model_specs import ALL_MODEL_SPECS
from briarwood.eval.model_quality.types import (
    CriterionResult,
    Fixture,
    ModelReport,
    ModelSpec,
)


def run_quality_suite(
    model_names: list[str] | None = None,
    fixture_limit: int | None = None,
    parallel: bool = True,
) -> dict[str, Any]:
    """Execute the quality suite; return a structured report dict."""

    specs = _select_specs(model_names)
    fixtures = load_all_fixtures()
    if fixture_limit:
        fixtures = fixtures[:fixture_limit]
    if not fixtures:
        return {
            "models": {},
            "fixtures": [],
            "error": "no fixtures available",
        }

    tasks = [(spec, fix) for spec in specs.values() for fix in fixtures]
    reports: list[ModelReport] = []

    if parallel and len(tasks) > 1:
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as ex:
            futures = {ex.submit(_score_one, spec, fix): (spec.name, fix.fixture_id)
                       for spec, fix in tasks}
            for fut in as_completed(futures):
                reports.append(fut.result())
    else:
        for spec, fix in tasks:
            reports.append(_score_one(spec, fix))

    return _aggregate(reports, fixtures, specs)


def _select_specs(names: list[str] | None) -> dict[str, ModelSpec]:
    if not names:
        return dict(ALL_MODEL_SPECS)
    picked = {}
    for n in names:
        key = n.strip()
        if key in ALL_MODEL_SPECS:
            picked[key] = ALL_MODEL_SPECS[key]
        else:
            print(f"[warn] unknown model: {key}", file=sys.stderr)
    return picked


def _score_one(spec: ModelSpec, fixture: Fixture) -> ModelReport:
    results: dict[str, CriterionResult] = {}
    for name, fn in ALL_CRITERIA.items():
        try:
            results[name] = fn(spec, fixture)
        except Exception as exc:  # pragma: no cover — diagnostic
            results[name] = CriterionResult(name, False, 0.0, [f"harness error: {exc}"])
    return ModelReport(model=spec.name, fixture_id=fixture.fixture_id, results=results)


def _aggregate(
    reports: list[ModelReport],
    fixtures: list[Fixture],
    specs: dict[str, ModelSpec],
) -> dict[str, Any]:
    per_model: dict[str, dict[str, Any]] = {}
    for model_name in specs:
        model_reports = [r for r in reports if r.model == model_name]
        if not model_reports:
            continue
        criterion_scores: dict[str, list[float]] = defaultdict(list)
        criterion_pass: dict[str, list[bool]] = defaultdict(list)
        for r in model_reports:
            for cname, cres in r.results.items():
                criterion_scores[cname].append(cres.score)
                criterion_pass[cname].append(cres.passed)
        per_criterion = {
            c: {
                "mean_score": round(sum(s) / len(s), 3),
                "pass_rate": round(sum(p) / len(p), 3),
                "n": len(s),
            }
            for c, s, p in (
                (c, criterion_scores[c], criterion_pass[c]) for c in criterion_scores
            )
        }
        overall = (
            sum(r.overall_score for r in model_reports) / len(model_reports)
        )
        per_model[model_name] = {
            "overall_score": round(overall, 3),
            "per_criterion": per_criterion,
            "per_fixture": [
                {
                    "fixture_id": r.fixture_id,
                    "overall": round(r.overall_score, 3),
                    "criteria": {
                        c: {
                            "score": res.score,
                            "passed": res.passed,
                            "details": res.details,
                        }
                        for c, res in r.results.items()
                    },
                }
                for r in model_reports
            ],
        }
    return {
        "models": per_model,
        "fixtures": [
            {"id": f.fixture_id, "kind": f.kind, "notes": f.notes}
            for f in fixtures
        ],
    }


# ---------- CLI printing ----------

def _print_report(report: dict[str, Any]) -> None:
    models = report.get("models", {})
    if not models:
        print("No models evaluated.")
        return
    print("\n=== Model Quality Scorecard ===")
    criteria = list(ALL_CRITERIA.keys())
    header = f"{'model':<14}" + "".join(f"{c[:10]:>12}" for c in criteria) + f"{'overall':>10}"
    print(header)
    print("-" * len(header))
    for name, data in models.items():
        row = f"{name:<14}"
        for c in criteria:
            pc = data["per_criterion"].get(c, {})
            row += f"{pc.get('mean_score', 0):>12.2f}"
        row += f"{data['overall_score']:>10.2f}"
        print(row)
    print()
    for name, data in models.items():
        print(f"\n-- {name} (overall {data['overall_score']:.2f}) --")
        for c in criteria:
            pc = data["per_criterion"].get(c, {})
            print(f"  {c:<22} score={pc.get('mean_score', 0):.2f} "
                  f"pass={pc.get('pass_rate', 0):.0%} n={pc.get('n', 0)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="model-quality")
    parser.add_argument("--models", default="", help="comma-separated subset")
    parser.add_argument("--limit", type=int, default=None, help="cap fixtures")
    parser.add_argument("--serial", action="store_true")
    parser.add_argument("--json", type=str, default=None, help="write full report JSON here")
    parser.add_argument("--details", action="store_true", help="print first-failing-fixture details")
    args = parser.parse_args(argv)

    model_names = [m for m in args.models.split(",") if m.strip()] or None
    t0 = time.time()
    report = run_quality_suite(
        model_names=model_names,
        fixture_limit=args.limit,
        parallel=not args.serial,
    )
    elapsed = time.time() - t0

    _print_report(report)
    print(f"\nElapsed: {elapsed:.1f}s over {len(report.get('fixtures', []))} fixtures.")

    if args.details:
        _print_details(report)

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Wrote full report → {path}")
    return 0


def _print_details(report: dict[str, Any]) -> None:
    for model_name, data in report.get("models", {}).items():
        for fix in data["per_fixture"]:
            failed = [c for c, r in fix["criteria"].items() if not r["passed"]]
            if not failed:
                continue
            print(f"\n[{model_name}] {fix['fixture_id']} — failing: {failed}")
            for c in failed:
                for d in fix["criteria"][c]["details"][:4]:
                    print(f"    {c}: {d}")
            break


if __name__ == "__main__":
    raise SystemExit(main())

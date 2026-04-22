"""Operational architecture and model sweep for Briarwood.

This tool is intentionally broader than ``briarwood.eval.model_quality``.
It audits execution surfaces, environment readiness, and external-data
integration posture so architecture pauses can produce a concrete scorecard.

CLI:
    python -m briarwood.eval.operational_sweep
    python -m briarwood.eval.operational_sweep --json outputs/operational_sweep.json
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
REGISTRY_PATH = ROOT / "briarwood" / "execution" / "registry.py"


@dataclass(slots=True)
class EnvironmentCheck:
    package: str
    installed: bool
    note: str = ""


@dataclass(slots=True)
class EvaluationSurface:
    name: str
    command: list[str]
    status: str
    detail: str


@dataclass(slots=True)
class ModuleAuditRow:
    name: str
    scoped_runner: bool
    dependencies: list[str] = field(default_factory=list)
    runner_name: str | None = None


@dataclass(slots=True)
class OperationalSweepReport:
    generated_at: str
    environment: list[EnvironmentCheck]
    scoped_modules: list[ModuleAuditRow]
    fully_scoped_paths: list[str]
    partial_or_fallback_paths: list[str]
    evaluation_surfaces: list[EvaluationSurface]
    archived_ui_note: str
    tavily_recommendations: list[str]
    attom_recommendations: list[str]
    prioritized_findings: list[str]


def run_operational_sweep() -> dict[str, Any]:
    environment = _environment_checks()
    scoped_modules = _load_scoped_modules()
    fully_scoped_paths, partial_paths = _read_scoped_execution_paths()
    evaluation_surfaces = _evaluation_surfaces()
    report = OperationalSweepReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        environment=environment,
        scoped_modules=scoped_modules,
        fully_scoped_paths=fully_scoped_paths,
        partial_or_fallback_paths=partial_paths,
        evaluation_surfaces=evaluation_surfaces,
        archived_ui_note=(
            "Archived Dash-era UI remains out of scope for this sweep except where "
            "legacy compatibility still affects routed execution."
        ),
        tavily_recommendations=[
            "Use Tavily Search for targeted freshness-sensitive discovery with domain/date filters.",
            "Use Tavily Extract after search for municipal pages and local articles that need normalized text.",
            "Reserve Tavily Crawl for stable town ordinance/minutes sites rather than the hot decision loop.",
            "Do not make Tavily Research the default routed path; keep it for offline analyst workflows.",
            "Use TAVILY_PROJECT / X-Project-ID to segment spend by workflow.",
        ],
        attom_recommendations=[
            "Prioritize ATTOM sales-history detail for comp and subject-property history over last-sale-only lookups.",
            "Use sales-history snapshot for lighter triage and cache-friendly pre-checks.",
            "Normalize repeat-sale chains, hold periods, price-per-sqft history, and disclosure caveats into Briarwood facts.",
            "Feed history confidence into comp-confidence and comp curation rather than hiding history gaps.",
            "Keep property-detail enrichment secondary to history-aware comp validation.",
        ],
        prioritized_findings=_prioritized_findings(environment, evaluation_surfaces),
    )
    return asdict(report)


def _environment_checks() -> list[EnvironmentCheck]:
    checks: list[EnvironmentCheck] = []
    for package in ("pydantic", "openai", "plotly", "pypdf", "fastapi"):
        installed = importlib.util.find_spec(package) is not None
        note = ""
        if package == "pydantic" and not installed:
            note = "Blocks model-quality harness imports and most repo-native execution surfaces."
        checks.append(EnvironmentCheck(package=package, installed=installed, note=note))
    return checks


def _load_scoped_modules() -> list[ModuleAuditRow]:
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        r'ModuleSpec\(\s*name="(?P<name>[^"]+)",\s*depends_on=\[(?P<deps>[^\]]*)\].*?runner=(?P<runner>[a-zA-Z0-9_]+)',
        re.S,
    )
    rows: list[ModuleAuditRow] = []
    for match in pattern.finditer(text):
        deps_raw = match.group("deps").strip()
        deps = re.findall(r'"([^"]+)"', deps_raw)
        runner_name = match.group("runner")
        rows.append(
            ModuleAuditRow(
                name=match.group("name"),
                scoped_runner=runner_name != "_runner",
                dependencies=deps,
                runner_name=runner_name,
            )
        )
    return rows


def _read_scoped_execution_paths() -> tuple[list[str], list[str]]:
    path = DOCS_DIR / "scoped_execution_support.md"
    text = path.read_text(encoding="utf-8")
    fully = _bullet_block_after(text, "Currently fully scoped:")
    partial = _bullet_block_after(text, "Partially supported but not fully scoped at the intent level:")
    partial.extend(_bullet_block_after(text, "Common fallback cases:"))
    return fully, partial


def _bullet_block_after(text: str, heading: str) -> list[str]:
    if heading not in text:
        return []
    section = text.split(heading, 1)[1]
    lines: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            if lines:
                break
            continue
        if not line.startswith("- "):
            if lines:
                break
            continue
        lines.append(line[2:])
    return lines


def _evaluation_surfaces() -> list[EvaluationSurface]:
    commands = [
        (
            "model_quality_harness",
            ["python3", "-m", "briarwood.eval.model_quality.harness", "--limit", "1"],
        ),
        (
            "scoped_execution_tests",
            ["python3", "-m", "unittest", "tests.test_execution_v2"],
        ),
        (
            "orchestrator_tests",
            ["python3", "-m", "unittest", "tests.test_orchestrator"],
        ),
        (
            "isolated_model_tests",
            [
                "python3",
                "-m",
                "unittest",
                "tests.modules.test_valuation_isolated",
                "tests.modules.test_risk_model_isolated",
                "tests.modules.test_resale_scenario_isolated",
            ],
        ),
    ]
    return [_run_surface(name, command) for name, command in commands]


def _run_surface(name: str, command: list[str]) -> EvaluationSurface:
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:
        return EvaluationSurface(
            name=name,
            command=command,
            status="blocked_by_environment",
            detail=str(exc),
        )

    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    if proc.returncode == 0:
        return EvaluationSurface(
            name=name,
            command=command,
            status="runnable_and_passing",
            detail=_trim_detail(combined or "pass"),
        )
    if "ModuleNotFoundError" in combined or "No module named" in combined:
        return EvaluationSurface(
            name=name,
            command=command,
            status="blocked_by_environment",
            detail=_trim_detail(combined),
        )
    return EvaluationSurface(
        name=name,
        command=command,
        status="runnable_but_failing",
        detail=_trim_detail(combined),
    )


def _trim_detail(text: str, limit: int = 400) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _prioritized_findings(
    environment: list[EnvironmentCheck],
    evaluation_surfaces: list[EvaluationSurface],
) -> list[str]:
    findings: list[str] = []
    if any(check.package == "pydantic" and not check.installed for check in environment):
        findings.append(
            "Environment drift: `pydantic` is missing, which blocks the model-quality harness and most import-driven checks."
        )
    blocked = [surface.name for surface in evaluation_surfaces if surface.status == "blocked_by_environment"]
    if blocked:
        findings.append(
            "Runnable baseline is incomplete because these evaluation surfaces are blocked by setup drift: "
            + ", ".join(blocked)
        )
    findings.extend(
        [
            "Tavily integration should move from search-only to search-plus-extract, with crawl reserved for stable municipal sites.",
            "ATTOM should emphasize sales-history detail/snapshot for comp and subject history rather than last-sale-only enrichment.",
            "Comp confidence should expose history confidence explicitly so sales-history gaps reduce trust without altering valuation math ownership.",
        ]
    )
    return findings


def _print_report(report: dict[str, Any]) -> None:
    print("=== Briarwood Operational Sweep ===")
    print(f"Generated: {report['generated_at']}")
    print("\nEnvironment")
    for check in report["environment"]:
        status = "ok" if check["installed"] else "missing"
        note = f" ({check['note']})" if check["note"] else ""
        print(f"  - {check['package']}: {status}{note}")
    print("\nEvaluation Surfaces")
    for surface in report["evaluation_surfaces"]:
        print(f"  - {surface['name']}: {surface['status']}")
        print(f"    {surface['detail']}")
    print("\nFully Scoped Paths")
    for path in report["fully_scoped_paths"]:
        print(f"  - {path}")
    print("\nPartial / Fallback Paths")
    for path in report["partial_or_fallback_paths"]:
        print(f"  - {path}")
    print("\nPrioritized Findings")
    for finding in report["prioritized_findings"]:
        print(f"  - {finding}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="operational-sweep")
    parser.add_argument("--json", type=str, default=None, help="write report JSON here")
    args = parser.parse_args(argv)

    report = run_operational_sweep()
    _print_report(report)

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote report -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

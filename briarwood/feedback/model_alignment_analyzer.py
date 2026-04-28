"""Analyzer for Stage 4 model confidence-vs-outcome alignment rows."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ModuleAlignmentSummary:
    module_name: str
    rows: int = 0
    mean_absolute_pct_error: float | None = None
    high_confidence_rows: int = 0
    underperformed_rows: int = 0
    underperformance_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModelAlignmentReport:
    rows_scored: int = 0
    modules: list[ModuleAlignmentSummary] = field(default_factory=list)
    top_examples: list[dict[str, Any]] = field(default_factory=list)
    tuning_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_scored": self.rows_scored,
            "modules": [module.to_dict() for module in self.modules],
            "top_examples": list(self.top_examples),
            "tuning_candidates": list(self.tuning_candidates),
        }


def analyze_rows(rows: list[dict[str, Any]]) -> ModelAlignmentReport:
    report = ModelAlignmentReport(rows_scored=len(rows))
    by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_module[str(row.get("module_name") or "unknown")].append(row)

    summaries: list[ModuleAlignmentSummary] = []
    for module_name, module_rows in by_module.items():
        apes = [
            float(row["absolute_pct_error"])
            for row in module_rows
            if isinstance(row.get("absolute_pct_error"), (int, float))
        ]
        high_conf = [row for row in module_rows if bool(row.get("high_confidence"))]
        under = [row for row in module_rows if bool(row.get("underperformed"))]
        summaries.append(
            ModuleAlignmentSummary(
                module_name=module_name,
                rows=len(module_rows),
                mean_absolute_pct_error=round(sum(apes) / len(apes), 6) if apes else None,
                high_confidence_rows=len(high_conf),
                underperformed_rows=len(under),
                underperformance_rate=round(len(under) / len(high_conf), 6) if high_conf else None,
            )
        )

    report.modules = sorted(
        summaries,
        key=lambda item: (item.underperformed_rows, item.rows),
        reverse=True,
    )
    report.top_examples = _top_examples(rows)
    report.tuning_candidates = _tuning_candidates(rows)
    return report


def load_rows_from_store(
    *,
    module_name: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from api.store import get_store

    return get_store().model_alignment_rows(module_name=module_name, limit=limit)


def format_report(report: ModelAlignmentReport) -> str:
    lines = ["=" * 64, "  BRIARWOOD MODEL ALIGNMENT REPORT", "=" * 64]
    lines.append(f"\nRows scored: {report.rows_scored}")
    if report.modules:
        lines.append("\n-- Module summaries --")
        for module in report.modules:
            mean = (
                f"{module.mean_absolute_pct_error:.2%}"
                if module.mean_absolute_pct_error is not None
                else "n/a"
            )
            rate = (
                f"{module.underperformance_rate:.0%}"
                if module.underperformance_rate is not None
                else "n/a"
            )
            lines.append(
                f"  {module.module_name:<24} rows={module.rows:<4} "
                f"mean_ape={mean:<8} high_conf={module.high_confidence_rows:<4} "
                f"misses={module.underperformed_rows:<4} miss_rate={rate}"
            )
    if report.tuning_candidates:
        lines.append("\n-- Human-review tuning candidates --")
        for candidate in report.tuning_candidates[:10]:
            lines.append(
                f"  - {candidate['module_name']}: {candidate['reason']} "
                f"(turn={candidate.get('turn_trace_id') or 'n/a'}, "
                f"property={candidate.get('property_id') or 'n/a'})"
            )
    lines.append("\n" + "=" * 64)
    return "\n".join(lines)


def _top_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sortable = [
        row for row in rows
        if isinstance(row.get("absolute_pct_error"), (int, float))
    ]
    sortable.sort(key=lambda row: float(row["absolute_pct_error"]), reverse=True)
    return [_example_payload(row) for row in sortable[:10]]


def _tuning_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        row for row in rows
        if bool(row.get("high_confidence")) and bool(row.get("underperformed"))
    ]
    candidates.sort(key=lambda row: float(row.get("absolute_pct_error") or 0.0), reverse=True)
    out: list[dict[str, Any]] = []
    for row in candidates[:20]:
        module_name = str(row.get("module_name") or "unknown")
        ape = float(row.get("absolute_pct_error") or 0.0)
        out.append(
            {
                **_example_payload(row),
                "reason": (
                    f"Review {module_name} on high-confidence sale-price calls "
                    f"with {ape:.1%} absolute percentage error."
                ),
            }
        )
    return out


def _example_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "turn_trace_id": row.get("turn_trace_id"),
        "conversation_id": row.get("conversation_id"),
        "property_id": row.get("property_id"),
        "module_name": row.get("module_name"),
        "predicted_value": row.get("predicted_value"),
        "predicted_label": row.get("predicted_label"),
        "confidence": row.get("confidence"),
        "outcome_value": row.get("outcome_value"),
        "outcome_date": row.get("outcome_date"),
        "absolute_pct_error": row.get("absolute_pct_error"),
        "alignment_score": row.get("alignment_score"),
        "high_confidence": bool(row.get("high_confidence")),
        "underperformed": bool(row.get("underperformed")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Stage 4 model alignment rows.")
    parser.add_argument("--module", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = analyze_rows(load_rows_from_store(module_name=args.module, limit=args.limit))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "ModelAlignmentReport",
    "ModuleAlignmentSummary",
    "analyze_rows",
    "format_report",
    "load_rows_from_store",
]

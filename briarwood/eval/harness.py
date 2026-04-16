"""Model eval harness — Layer 08.

Loads captured feedback sessions from ``data/learning/intelligence_feedback.jsonl``
and produces a per-model scorecard at ``data/eval/model_performance_log.jsonl``.

Metrics produced per model per run:
  - accuracy_delta: rough proxy — mean confidence on accepted sessions
    minus mean confidence on rejected sessions.
  - confidence_calibration: mean |confidence − outcome_alignment| where
    outcome is 1.0 for aligned/accepted, 0.0 for diverged/rejected.
  - rejection_rate: fraction of sessions the model contributed to that
    were explicitly rejected.
  - contribution_weight: mean contribution_map[model] across sessions —
    fed back into Triage routing weights.
  - drift_score: |mean_confidence_recent − mean_confidence_historical|.

The harness is intentionally tolerant of the legacy schema — rows without
``session_id`` / ``contribution_map`` / ``explicit_signal`` are treated as
weak implicit signals and counted only toward confidence calibration.

Schedule attachment point:
    This script is idempotent and safe to run repeatedly. To wire it on a
    weekly cron, call ``python -m briarwood.eval.harness`` from a cron job
    or a scheduler hook. A scheduler is deliberately not bundled here.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_PATH = ROOT / "data" / "learning" / "intelligence_feedback.jsonl"
EVAL_DIR = ROOT / "data" / "eval"
MODEL_PERF_LOG = EVAL_DIR / "model_performance_log.jsonl"


def iter_feedback(path: Path = FEEDBACK_PATH) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    results: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def _captured_at(row: dict[str, Any]) -> datetime | None:
    val = row.get("captured_at")
    if not isinstance(val, str):
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None


def score_model(model_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one specialist model across the provided feedback rows."""

    weights: list[float] = []
    confidences: list[float] = []
    accepted_confidences: list[float] = []
    rejected_confidences: list[float] = []
    alignments: list[float] = []
    recent_confidences: list[float] = []
    historical_confidences: list[float] = []

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    for row in rows:
        contrib = row.get("contribution_map") or {}
        if isinstance(contrib, dict) and model_name in contrib:
            weight = float(contrib.get(model_name) or 0.0)
            weights.append(weight)

        model_conf = (row.get("model_confidences") or {}).get(model_name)
        if not isinstance(model_conf, (int, float)):
            continue
        confidences.append(float(model_conf))

        ts = _captured_at(row)
        if ts is None or ts >= cutoff:
            recent_confidences.append(float(model_conf))
        else:
            historical_confidences.append(float(model_conf))

        explicit = row.get("explicit_signal")
        if explicit == "accepted":
            accepted_confidences.append(float(model_conf))
            alignments.append(abs(float(model_conf) - 1.0))
        elif explicit == "rejected":
            rejected_confidences.append(float(model_conf))
            alignments.append(abs(float(model_conf) - 0.0))

    total_contrib_sessions = len(weights)
    rejection_rate = (
        len(rejected_confidences) / total_contrib_sessions
        if total_contrib_sessions
        else 0.0
    )
    accuracy_delta = (
        (sum(accepted_confidences) / len(accepted_confidences))
        - (sum(rejected_confidences) / len(rejected_confidences))
        if accepted_confidences and rejected_confidences
        else None
    )
    calibration = (
        sum(alignments) / len(alignments) if alignments else None
    )

    if recent_confidences and historical_confidences:
        drift = abs(
            (sum(recent_confidences) / len(recent_confidences))
            - (sum(historical_confidences) / len(historical_confidences))
        )
    else:
        drift = None

    mean_weight = sum(weights) / len(weights) if weights else 1.0

    return {
        "model": model_name,
        "sessions_contributed": total_contrib_sessions,
        "sessions_with_confidence": len(confidences),
        "mean_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "accuracy_delta": round(accuracy_delta, 4) if accuracy_delta is not None else None,
        "confidence_calibration": round(calibration, 4) if calibration is not None else None,
        "rejection_rate": round(rejection_rate, 4),
        "contribution_weight": round(mean_weight, 4),
        "drift_score": round(drift, 4) if drift is not None else None,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def discover_models(rows: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for row in rows:
        for key in ("contribution_map", "model_confidences"):
            payload = row.get(key)
            if isinstance(payload, dict):
                names.update(payload.keys())
        # Also pick up the legacy "selected_modules" so legacy rows produce
        # something scoreable even before pipeline sessions exist.
        for m in row.get("selected_modules") or []:
            if isinstance(m, str):
                names.add(m)
    return sorted(names)


def run_regression(rows: list[dict[str, Any]], threshold: float = 0.15) -> dict[str, Any]:
    """Compare recent-window mean confidence vs historical baseline per model.

    Flags any model whose mean confidence moved more than ``threshold``
    from its prior baseline.
    """

    alerts: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    per_model_recent: dict[str, list[float]] = defaultdict(list)
    per_model_older: dict[str, list[float]] = defaultdict(list)

    for row in rows:
        ts = _captured_at(row)
        confs = row.get("model_confidences") or {}
        if not isinstance(confs, dict):
            continue
        bucket = per_model_recent if (ts and ts >= cutoff) else per_model_older
        for model, c in confs.items():
            if isinstance(c, (int, float)):
                bucket[model].append(float(c))

    for model, recent in per_model_recent.items():
        older = per_model_older.get(model, [])
        if not recent or not older:
            continue
        mean_recent = sum(recent) / len(recent)
        mean_older = sum(older) / len(older)
        delta = mean_recent - mean_older
        if abs(delta) >= threshold:
            alerts.append({
                "model": model,
                "delta": round(delta, 4),
                "mean_recent": round(mean_recent, 4),
                "mean_older": round(mean_older, 4),
            })
    return {"alerts": alerts, "threshold": threshold}


def run_eval(
    feedback_path: Path = FEEDBACK_PATH,
    output_path: Path = MODEL_PERF_LOG,
) -> dict[str, Any]:
    """Run the full eval pass and append per-model scorecards to the log."""

    rows = list(iter_feedback(feedback_path))
    models = discover_models(rows)

    scorecards = [score_model(name, rows) for name in models]
    regression = run_regression(rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for scorecard in scorecards:
            handle.write(json.dumps(scorecard, sort_keys=True, default=str) + "\n")

    return {
        "sessions_scanned": len(rows),
        "models_scored": len(scorecards),
        "scorecards": scorecards,
        "regression": regression,
        "output_path": str(output_path),
    }


def _print_summary(result: dict[str, Any]) -> None:
    print(f"Sessions scanned: {result['sessions_scanned']}")
    print(f"Models scored:    {result['models_scored']}")
    print(f"Written to:       {result['output_path']}")
    alerts = result.get("regression", {}).get("alerts") or []
    if alerts:
        print(f"\nRegression alerts: {len(alerts)}")
        for a in alerts:
            print(f"  - {a['model']}: Δ={a['delta']:+.3f} "
                  f"(recent {a['mean_recent']} vs older {a['mean_older']})")
    print("\nPer-model scorecards:")
    for row in result["scorecards"]:
        print(
            f"  {row['model']:<28} "
            f"mean_conf={row['mean_confidence']}  "
            f"rej={row['rejection_rate']}  "
            f"weight={row['contribution_weight']}  "
            f"drift={row['drift_score']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Briarwood model eval harness")
    parser.add_argument("--feedback", type=Path, default=FEEDBACK_PATH)
    parser.add_argument("--output", type=Path, default=MODEL_PERF_LOG)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    result = run_eval(feedback_path=args.feedback, output_path=args.output)
    if not args.quiet:
        _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())

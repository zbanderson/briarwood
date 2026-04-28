"""One-shot Stage 4 outcome backfill for intelligence feedback rows.

Adds non-null ``outcome`` objects to historical
``data/learning/intelligence_feedback.jsonl`` rows when a strict match exists
against a manual outcome file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from briarwood.eval.outcomes import build_outcome_index, load_outcomes


ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_PATH = ROOT / "data" / "learning" / "intelligence_feedback.jsonl"


def backfill_outcomes(
    *,
    feedback_path: Path,
    outcomes_path: Path,
    dry_run: bool = False,
    overwrite_outcome: bool = False,
) -> dict[str, Any]:
    outcome_result = load_outcomes(outcomes_path)
    index = build_outcome_index(outcome_result.records)
    summary: dict[str, Any] = {
        "feedback_path": str(feedback_path),
        "outcomes_path": str(outcomes_path),
        "outcomes_valid": outcome_result.valid_count,
        "outcome_errors": [err.to_dict() for err in outcome_result.errors],
        "outcome_duplicate_keys": list(outcome_result.duplicate_keys),
        "total": 0,
        "updated": 0,
        "skipped_existing_outcome": 0,
        "unmatched": 0,
        "corrupt_lines": 0,
        "dry_run": dry_run,
        "overwrite_outcome": overwrite_outcome,
    }
    if outcome_result.errors:
        summary["error"] = "outcome file has validation errors"
        return summary
    if outcome_result.duplicate_keys:
        summary["error"] = "outcome file has duplicate match keys"
        return summary
    if not feedback_path.exists():
        summary["error"] = f"{feedback_path} not found"
        return summary

    lines_out: list[str] = []
    with feedback_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            summary["total"] += 1
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                summary["corrupt_lines"] += 1
                lines_out.append(text)
                continue
            if not isinstance(row, dict):
                summary["corrupt_lines"] += 1
                lines_out.append(text)
                continue

            if row.get("outcome") is not None and not overwrite_outcome:
                summary["skipped_existing_outcome"] += 1
                lines_out.append(json.dumps(row, sort_keys=True, default=str))
                continue

            match = index.match_mapping(row)
            if match is None:
                summary["unmatched"] += 1
                lines_out.append(json.dumps(row, sort_keys=True, default=str))
                continue

            row["outcome"] = match.outcome.to_dict()
            row["outcome_match"] = {
                "method": match.method,
                "key": match.key,
            }
            summary["updated"] += 1
            lines_out.append(json.dumps(row, sort_keys=True, default=str))

    if dry_run:
        return summary

    backup = feedback_path.with_suffix(feedback_path.suffix + ".bak")
    shutil.copy2(feedback_path, backup)
    with feedback_path.open("w", encoding="utf-8") as handle:
        for line in lines_out:
            handle.write(line + "\n")
    summary["backup"] = str(backup)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill feedback rows with outcomes.")
    parser.add_argument("--feedback", type=Path, default=FEEDBACK_PATH)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite-outcome", action="store_true")
    args = parser.parse_args(argv)
    result = backfill_outcomes(
        feedback_path=args.feedback,
        outcomes_path=args.outcomes,
        dry_run=args.dry_run,
        overwrite_outcome=args.overwrite_outcome,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())

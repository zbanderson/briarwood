"""One-shot backfill for legacy feedback rows.

Rewrites data/learning/intelligence_feedback.jsonl so every row has the new
pipeline fields (session_id, contribution_map, explicit_signal, outcome).

- session_id: synthesized from captured_at + question hash (stable, deterministic).
- contribution_map: equal-weighted across selected_modules.
- explicit_signal: left as None (we don't know retroactively).
- outcome: left as None.

Writes a .bak next to the original before rewriting. Idempotent: rows that
already have all four fields are left untouched.

Usage:
    python scripts/backfill_feedback_rows.py
    python scripts/backfill_feedback_rows.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_PATH = ROOT / "data" / "learning" / "intelligence_feedback.jsonl"


def _synth_session_id(row: dict) -> str:
    seed = f"{row.get('captured_at', '')}|{row.get('question', '')}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _synth_contribution_map(row: dict) -> dict:
    modules = row.get("selected_modules") or []
    if not isinstance(modules, list) or not modules:
        return {}
    weight = round(1.0 / len(modules), 4)
    return {str(m): weight for m in modules}


def backfill(path: Path, dry_run: bool = False) -> dict:
    if not path.exists():
        return {"error": f"{path} not found"}

    updated = 0
    skipped = 0
    total = 0
    lines_out: list[str] = []

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                lines_out.append(line)
                skipped += 1
                continue

            has_all = all(k in row for k in ("session_id", "contribution_map", "explicit_signal", "outcome"))
            if has_all:
                skipped += 1
                lines_out.append(json.dumps(row, sort_keys=True, default=str))
                continue

            row.setdefault("session_id", _synth_session_id(row))
            row.setdefault("contribution_map", _synth_contribution_map(row))
            row.setdefault("explicit_signal", None)
            row.setdefault("outcome", None)
            updated += 1
            lines_out.append(json.dumps(row, sort_keys=True, default=str))

    if dry_run:
        return {"path": str(path), "total": total, "updated": updated, "skipped": skipped, "dry_run": True}

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8") as handle:
        for line in lines_out:
            handle.write(line + "\n")

    return {
        "path": str(path),
        "backup": str(backup),
        "total": total,
        "updated": updated,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill legacy feedback rows.")
    parser.add_argument("--path", type=Path, default=FEEDBACK_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = backfill(args.path, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
